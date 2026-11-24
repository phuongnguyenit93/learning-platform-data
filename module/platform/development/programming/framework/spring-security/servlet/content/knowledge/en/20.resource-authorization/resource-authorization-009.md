# Pagination, Performance, and Choosing Between Query Filtering and Post-Read Filtering in Spring Security Servlet

## 1. The Problem: Resource Authorization and Pagination Must Be Consistent

Suppose a Spring Security Servlet application exposes a report list via an API:

```text
GET /api/reports?page=0
Authorization: Basic <credentials>
```

Each report has `id`, `tenantId`, `ownerUsername`, and `title`. Regular users may only read reports belonging to their own **tenant** and **owner**; tenant admins may view all reports within **their own tenant**, never another tenant.

Two seemingly similar ways to write the query produce vastly different results:

**Approach A — filter permissions before pagination in the database:**

```sql
SELECT id, title
FROM reports
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_user
ORDER BY id ASC
LIMIT :page_size OFFSET :offset;
```

**Approach B — fetch a page from global data, then filter in Java:**

```java
Page<ReportEntity> globalPage = repository.findAll(pageable);
List<ReportEntity> allowed = globalPage.getContent().stream()
    .filter(report -> mayRead(authentication, report))
    .toList();
```

Approach B can produce **a page with only one result even when many permitted resources exist on later pages**, corrupt `totalElements`, leak the count of other users' resources, and waste effort loading records that will never be returned to the user. If sensitive data is loaded into the process before filtering, the security boundary is also pushed deeper into the application.

**Core message:** For large lists and policies expressible in queries, apply **authorization predicates before `LIMIT/OFFSET` or before cursor/seek**. Only then paginate, compute totals, and map DTOs over **the dataset the user is genuinely allowed to see**.

Learning objectives:

1. Understand how `Authentication`, `AuthorizationManager`, ownership/tenant rights, and queries interact.
2. Distinguish **in-query filtering**, **post-query pre-pagination filtering**, and **post-pagination filtering**.
3. Explain why `@PostFilter`/`Stream.filter` does not automatically preserve `Page<T>` correctness.
4. Choose among `Page`, `Slice`, offset pagination, or keyset/cursor pagination.
5. Design `countQuery`/`hasNext` with the exact same access boundary as the content query.
6. Mitigate N+1 queries, overfetching, heavy queries, wrong-tenant caches, snapshot drift, and metadata leaks.
7. Build a Spring Boot 3.3.5 / Java 17 / Spring Data JPA / H2 application with MockMvc tests.

This applies to the **Servlet stack**; either HTTP Basic or form login can supply Authentication. The example uses HTTP Basic to make testing 401/403 straightforward, which does not mean production APIs should send passwords over unencrypted HTTP.

## 2. Four Filtering Points That Are Easily Confused

| Implementation | When Policy Applies | Page Correctness | Cost / Safety |
| --- | --- | --- | --- |
| **Filter in DB WHERE/JOIN/EXISTS then paginate** | Before ORDER BY and LIMIT/OFFSET/seek on the permitted set | Accurate when content/count share the same predicate and stable order | Usually optimal; DB can use indexes and avoids sending forbidden rows to the app |
| Load **all** records into Java, filter permissions, **then** paginate in-memory | Before pagination, after reading the entire dataset | Can be accurate on a small snapshot under the same policy | Wastes RAM/bandwidth, does not scale to large datasets, risks loading unnecessary data |
| **Fetch a global page first**, then `filter(...)` or `@PostFilter` | After LIMIT/OFFSET already applied to global data | **Incorrect/incomplete pages** when forbidden rows sit in between; total/hasNext wrong | Loads unauthorized rows, leaks information via metadata |
| Fetch multiple batches, check each record's permissions until a page is filled | After each batch query | Can reach target item count via overfetching, but hard to keep hasNext/total/cursor accurate | Complex, variable cost; must prevent infinite loops and snapshot inconsistency |

**Do not equate "filtering in the service" with "post-pagination filtering".** A service can structure policies and build safe query predicates; in that case, data is still filtered in the database. What matters is **when filtering happens relative to limiting/paging**.

### 2.1. Authorization Is Not Just hasRole

`hasRole("READER")` can confirm a general role, but cannot answer whether user A may read report ID 812 in tenant B. A list policy typically needs at least:

```text
CanSee(report, principal) =
    principal is authenticated
    AND report.tenant_id == tenant granted to principal
    AND (
        report.owner_username == principal.username
        OR principal has TENANT_ADMIN permission in that tenant
    )
    AND other business state conditions (if any)
```

This expression is a **conceptual policy**, not an automatically executed SQL statement. Identity, tenant membership, and roles must come from **trusted sources**; never treat query `?owner=lan` or header `X-Tenant: t1` sent by a browser as proof of permission.

### 2.2. "Hiding Items After Fetching" May Not Be Enough Protection

If a query reads full entities including private content and Java filters afterward, unauthorized rows have already passed through the connection, heap, ORM persistence context, instrumentation, or debug logs. That does not automatically leak data to clients, yet it increases attack surface and cost compared to querying only permitted rows.

For sensitive data, prefer **data minimization**: filter accurately in the query, use projections fetching only columns needed for the list, and re-verify permissions on the detail endpoint.

## 3. Numerical Example: Why Post-Page Filtering Produces Broken Pages

Suppose the database has 8 reports ordered by ascending ID. User `lan` may only read IDs `3, 5, 7, 8`; the rest belong to others. Each page holds at most 3 results.

```text
All rows after ORDER BY id ASC:
  [1, 2, 3, 4, 5, 6, 7, 8]
Visible to lan:
  [3, 5, 7, 8]

FETCH GLOBAL PAGE THEN FILTER:
  page 0 global = [1, 2, 3]  -> filter lan = [3]
  page 1 global = [4, 5, 6]  -> filter lan = [5]
  page 2 global = [7, 8]     -> filter lan = [7, 8]

FILTER IN QUERY THEN FETCH PAGE:
  visible = [3, 5, 7, 8]
  page 0 = [3, 5, 7]
  page 1 = [8]
```

Consequences of the wrong approach:

- The first page returns only 1 item even though the permitted set has 3 more items.
- Borrowing `totalElements=8` from the global query **leaks the system-wide total**, not the user's permitted count.
- Taking `totalElements=1` from the filtered count of **one page** fails to reflect the total visible items.
- The client cannot accurately tell whether the next page contains permitted items using `globalPage.hasNext()`.
- Page indexes no longer index **the visible set**; they point into pages of the broader dataset.
- With unevenly distributed data, several consecutive pages can be empty even when visible records exist much further down.

**Correct:** For the visible set `[3,5,7,8]` with size 3, `totalElements=4`, `totalPages=2`, page 0 has 3 items, and page 1 has 1 item.

### 3.1. A Line of Code That Looks Reasonable Yet Is Wrong

```java
Page<ReportEntity> page = repo.findAll(pageable);

List<ReportEntity> allowed = page.getContent().stream()
    .filter(row -> canRead(authentication, row))
    .toList();

// Wrong if using page.getTotalElements(): that is the total of the entire DB.
// Wrong if using allowed.size(): that is only the number of kept items on the current page.
```

There is no "quick adjustment" trick to fix `totalElements` accurately from an already-filtered page. You need **the complete visible set** (or an equivalent filtered count query).

### 3.2. Page.map() Is Not Page.filter()

Spring Data's `Page.map(...)` is useful for **transforming** item types, such as entity to DTO. It is not meant to recompute pagination and totals after dropping elements. Never write a mapper returning `null` and claim you have a filtered Page: null items appear in content, and metadata still comes from before mapping.

```java
Page<ReportSummary> summaries =
    authorizedPage.map(report ->
        new ReportSummary(report.getId(), report.getTitle()));
```

This snippet is valid when **`authorizedPage` is already an authorization-filtered page**, not when `authorizedPage` contains every tenant and mapping tries to hide rows.

## 4. Prefer Database Filtering When the Policy Is Expressible in SQL/JPQL

With a basic policy:

```text
member: tenant_id = trustedTenant AND owner_username = authenticatedUsername
tenant admin: tenant_id = trustedTenant
```

A clear design uses **two separate queries**:

```sql
-- Regular user:
SELECT id, title
FROM reports
WHERE tenant_id = :tenant_id
  AND owner_username = :username
ORDER BY id ASC
LIMIT :limit OFFSET :offset;

-- Tenant admin:
SELECT id, title
FROM reports
WHERE tenant_id = :tenant_id
ORDER BY id ASC
LIMIT :limit OFFSET :offset;
```

This is illustrative SQL, not JPA `@Query` syntax. Spring Data `Pageable` translates sort/limit/offset for your database dialect.

Advantages:

1. The DB filters while scanning rows and can use indexes on tenant/owner.
2. List queries never load other tenants' records into Java.
3. `COUNT(*)` can reuse **the exact same authorization predicate** to return the visible total.
4. Content and metadata cannot accidentally use two different scopes.
5. The same predicate can be reused across search and sort operations while preserving the access boundary.

### 4.1. Avoid Unchecked OR Conditions with Admin Rights

A conceptual query:

```sql
WHERE tenant_id = :tenant
  AND (owner_username = :username OR :is_tenant_admin = TRUE)
```

can be correct if `is_tenant_admin` is genuinely computed server-side from Authentication/permissions for that exact tenant. However, a client-supplied boolean `?admin=true` is **insecure**. In the code example, the service picks separate admin/owner queries for easier auditing and to avoid hard-to-optimize OR predicates or mis-bound parameters.

### 4.2. Queries Must Share Semantics with Resource Authorization

Suppose `GET /api/reports/{id}` checks owner + tenant + `"VISIBLE"` status, while the list query filters only by owner + tenant. Then the list can leak titles/IDs of locked reports even though detail access is blocked. **Lists and details must share the same intentional visibility policy**.

If permissions vary by group, ACL, or time, embed the corresponding predicate via JOIN/EXISTS, row-level security, a materialized access table, or a view, rather than maintaining Java filters that diverge from queries.

### 4.3. The Count Query Must Also Enforce Permissions

A `Page<T>` typically runs a second query for total items to compute:

```text
totalElements = COUNT(visible rows under the same policy)
totalPages = ceil(totalElements / pageSize)
```

Wrong SQL/JPQL:

```sql
-- Content filters tenant, but count does not filter tenant/owner:
SELECT COUNT(*) FROM reports;
```

This produces wrong results and leaks data. Correct count for a member:

```sql
SELECT COUNT(*)
FROM reports
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_username;
```

If the content query includes a one-to-many JOIN that duplicates a report across rows, the count may need `COUNT(DISTINCT report.id)` or an `EXISTS` structure to avoid inflation. Never assume `COUNT(*)` always equals the number of distinct reports.

## 5. When to Use Page, Slice, or a Total-Free List

| Result Type | Includes Total Count? | Includes hasNext? | When Suitable |
| --- | --- | --- | --- |
| `Page<T>` | Has `totalElements`/`totalPages` (usually needs a count query) | Yes | UI needs page numbers / visible total and counting is affordable |
| `Slice<T>` | Does not promise a full total count | Yes, by fetching one extra row to check for a next page | Infinite scrolling, APIs not needing totals; counting is expensive |
| `List<T>` with explicit limit | No automatic total/hasNext | Must design separately | Fixed/small queries, or endpoints without pagination |
| Cursor/keyset window | Usually no total count | Has next cursor if more rows exist after seek | Large feeds, deep pagination, and stable ordering |

### 5.1. Page and the Count Query

Spring Data JPA `Page<ReportSummary>` computes `getTotalElements()` and `getTotalPages()`. Repositories usually execute a count query when needed (the framework may optimize it in certain cases, so do not assume a fixed SQL count).

Most importantly: the count query must be constrained by the exact same **tenant, owner, status, search filters, and other policies** as the content query.

### 5.2. Slice Avoids Counting but Does Not Fix Post-Pagination Filtering

`Slice` avoids counting the full visible set. However, if you first fetch a **global slice** and then filter permissions in Java, `hasNext` still reflects the global dataset and pages can be empty or short. For `Slice` to be right, apply the policy before determining the slice boundary.

### 5.3. Not Every UI Needs totalElements

If the UX is just a "Load more" button, computing a large count may be unnecessary. You can use `Slice` with authorization predicates in the query and `hasNext` in the response, or a keyset cursor. Never expose a global count merely because `Page` supports it, as doing so adds query overhead and can leak data scale.

## 6. Stable Sorting: Pagination Requires Deterministic Ordering

A query with `LIMIT/OFFSET` and no `ORDER BY` does not guarantee a consistent item set across pages. Even with `ORDER BY created_at`, multiple items sharing the same timestamp can swap relative positions.

Therefore a sort key should be **unique** or include a tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

The runnable example uses `ORDER BY id ASC` via `PageRequest.of(page, 2, Sort.by("id").ascending())` because IDs are unique and demo data is static.

### 6.1. Offset Pagination and Changing Data

Suppose page 0 fetches IDs `[10, 9, 8]` in descending time order. A new record is inserted at the top before the client requests page 1. Offset 3 may return ID 8 again or skip an item as data shifts.

This is **pagination drift**, not a Spring Security bug. Options include snapshot isolation / point-in-time cursors, keyset pagination, and UI designs tolerant of changing data.

### 6.2. Keyset / Cursor Pagination

With `created_at DESC, id DESC` ordering, the next call can seek using the last item's key pair:

```sql
SELECT id, title, created_at
FROM reports
WHERE tenant_id = :tenant
  AND owner_username = :username
  AND (
    created_at < :last_created_at
    OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
```

This is illustrative SQL; initial cursor absence must be handled separately. **Authorization predicates must be present in every cursor query**, not only on the first page. Never let clients tamper with tenant/owner inside a cursor. Cursors should be opaque, integrity-protected, or validated against the current user/tenant/search/sort.

### 6.3. Keyset Does Not Always Replace Page

Keyset fits "continue from the last record" better than "jump to page 300". If the UI genuinely needs random page jumps, offset pagination may be reasonable within acceptable bounds and cost. Do not prematurely adopt keyset before understanding the UI, data distribution, and actual indexes.

## 7. Impact on Performance and System Resources

### 7.1. Data Movement Volume

Suppose out of 1 million reports, a user can see only 500 items. Wrong filtering may read thousands of global pages to assemble one page, or even scan the entire table if permitted rows are sparse. Query-level filtering can use an index to fetch rows matching tenant/owner directly.

**This is a qualitative example**, not a benchmark. Real speed depends on indexes, the optimizer, query plans, cardinality, joins, and the backend.

### 7.2. Indexes for Authorization Predicates + Ordering

If the member query has:

```sql
WHERE tenant_id = :tenant
  AND owner_username = :owner
ORDER BY id ASC
```

an index like:

```sql
CREATE INDEX idx_reports_tenant_owner_id
ON reports (tenant_id, owner_username, id);
```

can help the DB locate and order within the user's visible subset. For tenant-only admin queries, another index can help:

```sql
CREATE INDEX idx_reports_tenant_id
ON reports (tenant_id, id);
```

Do not blindly add every index in production without measuring: indexes consume storage and write overhead. Use `EXPLAIN`/query plans on realistic data to decide. Skewed data across tenants can give the same query different costs.

### 7.3. COUNT Can Be Very Expensive

`COUNT(*)` can be slow with complex predicates, multiple joins/ACLs, or huge data volumes. Options:

- `Slice` when the UI only asks "is there a next page?".
- Optimize the count query with matching predicates while omitting unnecessary joins.
- Expose totals only when the product truly needs them.
- Controlled caching partitioned by user/tenant/policy/search with suitable TTLs.
- Some UIs accept estimates, **but must clearly label them as approximate counts** rather than presenting them as exact.

### 7.4. N+1 When Checking Permissions Per Row

If Java calls `permissionService.canRead(user, row)` and each call loads an ACL or group from the DB, 20 items can trigger 20+ queries. With large pages and many users, N+1 spikes p95 latency.

Solutions typically push permissions into the query via `JOIN`/`EXISTS` or load ACLs in **batches** with proper indexes. When permission logic genuinely requires per-row evaluation, measure cost and cap candidate reads.

### 7.5. Projection DTOs Reduce Bandwidth

If a list needs only ID and title, queries can construct `ReportSummary(id,title)` directly without loading full contents, attachments, or sensitive fields:

```java
public record ReportSummary(Long id, String title) {}
```

A properly scoped projection reduces data pulled into Java. Still, **projection is not authorization**: the query producing the DTO must still filter tenant/owner/status and never return out-of-scope metadata.

## 8. @PostFilter and Post-Read Filtering: When Appropriate?

Spring Security method security offers `@PostFilter` to filter elements from a returned collection/array or supported result type after the method executes. Illustrative syntax:

```java
// ILLUSTRATING API ONLY for a small List already fetched from a service;
// do not use for pagination on a large database.
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<ReportRow> allRowsForSmallTest() {
    return tinyRepository.loadAllRows();
}
```

`filterObject` is the element currently being evaluated. This snippet is just an example inside a class with `@EnableMethodSecurity`, `ReportRow`, and an appropriate repository; **not a standalone runnable Java file**.

### 8.1. When @PostFilter Has Value

It can be useful when:

- The dataset is very small, bounded, and already loaded for another business reason.
- The policy is difficult to express in a single query and no page metadata is required.
- It serves as an extra defense-in-depth layer, not the sole access control.
- The difference between visibility and pagination is explicitly designed, without returning a global `Page<T>` with wrong metadata.

### 8.2. Why Not Blindly Use @PostFilter Directly on Page<T>?

`Page<T>` contains both content and metadata (total, page, hasNext); method-security filtering implementations **do not necessarily support mutating Page directly as a collection**, and even if content were filtered, metadata was already computed by the original query.

So **never assume** adding `@PostFilter` to a method returning `Page<ReportEntity>` automatically fixes:

- items per page;
- totalElements;
- totalPages;
- offsets between calls;
- hasNext;
- which data was loaded before filtering.

The practical demo uses **filtered repository queries**, returning `Page<ReportSummary>` and a matching count query.

### 8.3. Is Post-Read Filtering Followed by In-Memory Pagination Ever Accurate?

If the source has only a few dozen elements, you can load them all, filter by policy, and then apply `skip/limit` afterward. In that case, page contents can match the current snapshot set, yet the approach **does not scale** and is unsuitable for large data or PII that must not enter the process.

Evaluate cost and security rather than dismissing all in-memory filtering outright. The mistake to avoid is **filtering after taking a global page**.

### 8.4. Hybrid: Controlled Overfetching

When a policy depends on an external service and cannot be expressed in SQL, you can pre-filter candidates by tenant/status in the DB, fetch batches, and check permissions in Java until enough items accumulate. You must design:

1. Minimal server-side pre-filtering, **never leaking other tenants**.
2. Caps on batches/candidates/time to prevent DoS.
3. Cursor advancement based on scanned candidates, not merely returned items, to avoid infinite loops.
4. `hasNext` calculation accounting for unchecked remaining candidates.
5. Never claiming an exact `totalElements` if you cannot count the entire visible set.
6. Auditing and handling permissions that change mid-fetch, with sound caching/consistency.
7. Never returning an empty page as if no resources remain simply because one batch contained only denied items.

If the product requires offset pages with exact totals and policies cannot run in the database, that is a **real architectural problem**; consider materialized visibility, an ACL index, or changing the UX/API.

## 9. HTTP Authorization and List Queries Must Protect Two Layers

Spring Security Servlet uses `SecurityFilterChain` to authenticate and guard endpoints. Example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports").authenticated()
    .anyRequest().denyAll()
);
```

This rule only ensures the caller is not anonymous per policy; **it has not filtered reports by owner/tenant at all**. The service/query must enforce resource-level policies.

A proper flow:

```text
GET /api/reports?page=0
    |
    v
HTTP Basic filter authenticates principal
    |
    v
authorizeHttpRequests verifies request is authenticated
    |
    v
ReportController
    |
    v
ReportService
    +-- look up trusted tenant scope from backend
    +-- check TENANT_ADMIN role from Authentication
    +-- build PageRequest(size=2, sort=id ASC)
    |
    v
ReportRepository queries owner or tenant
    +-- SELECT projection filtering exact permission conditions
    +-- COUNT with the exact same permission conditions
    |
    v
PageResponse contains only ID/title and visible metadata
```

Note: when using multiple `SecurityFilterChain` beans, `securityMatcher` selects which chain applies to a request; `requestMatchers` defines authorization rules **inside the chosen chain**. Never assume an HTTP rule automatically filters returned data.

### 9.1. Identity and Tenant Are Not Taken from Query Strings

An endpoint receiving:

```text
GET /api/reports?tenantId=t2&owner=admin
```

must not switch scope based on those two parameters just because the user asked. In tenant-scoped applications, tenant membership must be verified in server-side identity/authorization context or the database. A client-provided tenant parameter may act as a **requested tenant switch target**, but must pass permission checks before taking effect.

In the runnable example, the endpoint **does not accept** tenant/owner from the client: it uses `Authentication.getName()` and server-side `TenantScope`.

### 9.2. Admins Are Also Tenant-Scoped

A `ROLE_TENANT_ADMIN` holds administrative rights **within their assigned tenant**, not across all tenants automatically. If the admin query includes `WHERE tenant_id = :trustedTenant`, admin1 never sees tenant2's rows.

Conversely, an admin query like `SELECT * FROM reports` simply because of an admin role breaks data isolation unless the admin holds platform-wide rights.

### 9.3. An Authenticated Request Does Not Guarantee Fresh Sessions/Roles

In the sample, HTTP Basic authenticates every request. Other apps use sessions or remember-me; roles/tenants can go stale if permissions were revoked. Use appropriate revalidation/revocation policies so queries continue using active scopes. This limitation is separate from pagination yet affects visibility correctness.

## 10. Runnable Application: Spring Boot 3.3.5 / Java 17 / JPA / H2

This example builds a report listing API **filtered in the database before pagination**. To keep tests simple, it uses a fixed page size of **2**, ascending ID sort, and deterministic seed data.

### 10.1. Data Matrix

| ID | Tenant | Owner | Title |
| --- | --- | --- | --- |
| 1 | t1 | lan | Lan report A |
| 2 | t1 | minh | Minh report A |
| 3 | t1 | lan | Lan report B |
| 4 | t1 | lan | Lan report C |
| 5 | t1 | minh | Minh report B |
| 6 | t2 | binh | Binh report A |
| 7 | t2 | binh | Binh report B |
| 8 | t1 | lan | Lan report D |

User scopes:

- `lan`: tenant `t1`, ROLE_USER → visible IDs `1,3,4,8`, total **4**, 2 pages of size 2.
- `minh`: tenant `t1`, ROLE_USER → visible IDs `2,5`, total **2**.
- `admin1`: tenant `t1`, ROLE_TENANT_ADMIN → visible IDs `1,2,3,4,5,8`, total **6**.
- `binh`: tenant `t2`, ROLE_USER → visible IDs `6,7`, total **2**.
- `admin2`: tenant `t2`, ROLE_TENANT_ADMIN → visible IDs `6,7`, total **2**.

Tests for pages, counts, and tenant leakage rely on this fixed dataset.

### 10.2. Project Structure

```text
resource-pagination-security/
  pom.xml
  src/
    main/
      java/example/page/
        PageApplication.java
        SecurityConfig.java
        ReportEntity.java
        ReportSummary.java
        ReportRepository.java
        TenantScope.java
        ReportService.java
        PageResponse.java
        ReportController.java
        SeedData.java
      resources/
        application.properties
    test/
      java/example/page/
        ReportPaginationSecurityTest.java
```

### 10.3. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>resource-pagination-security</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.4. application.properties

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:pages;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

`create-drop` and in-memory H2 are only for **demo/testing**. Production uses schema migrations, a proper database, secret credentials, and configured connection pools. Disabling open-in-view prevents relying on lazy loading outside the service during JSON serialization.

### 10.5. PageApplication.java

```java
package example.page;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PageApplication {
    public static void main(String[] args) {
        SpringApplication.run(PageApplication.class, args);
    }
}
```

### 10.6. ReportEntity.java: Data with Owner and Tenant

```java
package example.page;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "reports")
public class ReportEntity {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_username", nullable = false)
    private String ownerUsername;

    @Column(nullable = false)
    private String title;

    protected ReportEntity() {
    }

    public ReportEntity(Long id, String tenantId,
                        String ownerUsername, String title) {
        this.id = id;
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }
}
```

`id` in the demo is manually seeded so `@GeneratedValue` is omitted. In real products, choose appropriate ID generators and constraints, trusted tenant IDs, row-level permissions, and resource states like deleted/archived.

### 10.7. ReportSummary.java: Projection for List Pages

```java
package example.page;

public record ReportSummary(Long id, String title) {
}
```

The DTO exposes only ID and title. Before adding owner, tenant, or sensitive content to a DTO, review policies; "owner-filtered" does not mean every field is safe to disclose.

### 10.8. ReportRepository.java: Two Filtered Queries and Filtered Counts

```java
package example.page;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReportRepository
        extends JpaRepository<ReportEntity, Long> {

    @Query(
        value = """
            select new example.page.ReportSummary(r.id, r.title)
            from ReportEntity r
            where r.tenantId = :tenant
              and r.ownerUsername = :owner
            """,
        countQuery = """
            select count(r)
            from ReportEntity r
            where r.tenantId = :tenant
              and r.ownerUsername = :owner
            """
    )
    Page<ReportSummary> findOwnerPage(
        @Param("tenant") String tenant,
        @Param("owner") String owner,
        Pageable pageable
    );

    @Query(
        value = """
            select new example.page.ReportSummary(r.id, r.title)
            from ReportEntity r
            where r.tenantId = :tenant
            """,
        countQuery = """
            select count(r)
            from ReportEntity r
            where r.tenantId = :tenant
            """
    )
    Page<ReportSummary> findTenantPage(
        @Param("tenant") String tenant,
        Pageable pageable
    );
}
```

Explanation:

- `findOwnerPage` applies tenant **and** owner in both the content query and the count query.
- `findTenantPage` omits the owner condition only after the service confirms the caller holds the tenant admin role; it **still constrains tenant**.
- JPQL `select new example.page.ReportSummary(...)` builds DTOs directly, avoiding loading full entities before mapping.
- `Pageable` is passed by the service with a fixed size and `id ASC` sort; Spring Data JPA applies pagination/sorting to the query.
- `countQuery` provides the visible total. Never use table-wide `repository.count()` for user metadata.
- If adding a `title` search, `isDeleted` status, or group policy, add the exact same condition to **both queries**, not only the content query.

**Version note:** `select new ...` for a record uses its Java 17 canonical constructor; the Spring Data JPA/Hibernate versions in Boot 3.3.x support constructor expressions. When running another provider or modifying queries/mappings, verify query parsing and sorting with tests.

### 10.9. TenantScope.java: Trusted Server-Side Tenant Membership

```java
package example.page;

import java.util.Map;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class TenantScope {

    private final Map<String, String> tenantByUsername = Map.of(
        "lan", "t1",
        "minh", "t1",
        "admin1", "t1",
        "binh", "t2",
        "admin2", "t2"
    );

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public String requireTenant(Authentication authentication) {
        if (authentication == null
                || !trust.isAuthenticated(authentication)) {
            throw new AccessDeniedException("Authentication required");
        }

        String tenant = tenantByUsername.get(authentication.getName());
        if (tenant == null) {
            throw new AccessDeniedException("Tenant membership required");
        }

        return tenant;
    }
}
```

The static map is strictly for the demo; production needs a trusted tenant membership source such as a verified database or identity service. For users in multiple tenants, switching tenants must verify membership in the selected tenant rather than trusting a client-sent ID.

### 10.10. PageResponse.java: Metadata for the Visible Set Only

```java
package example.page;

import java.util.List;

public record PageResponse(
    List<ReportSummary> items,
    int page,
    int size,
    long totalElements,
    int totalPages
) {
}
```

Never copy a global count into `totalElements`; both the item list and metadata must reflect **the exact same visible set**. With `Slice`, you can replace totals with `hasNext` if the product does not need counts.

### 10.11. ReportService.java: Enforce Policy Before Pageable

```java
package example.page;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    private final ReportRepository repository;
    private final TenantScope tenantScope;

    public ReportService(ReportRepository repository,
                         TenantScope tenantScope) {
        this.repository = repository;
        this.tenantScope = tenantScope;
    }

    public PageResponse listVisible(
            Authentication authentication, int page) {

        // Demo fixed size=2 and reject overly large offsets.
        if (page < 0 || page > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid page");
        }

        String tenant = tenantScope.requireTenant(authentication);
        String username = authentication.getName();

        boolean tenantAdmin = authentication.getAuthorities().stream()
            .anyMatch(a ->
                "ROLE_TENANT_ADMIN".equals(a.getAuthority()));

        Pageable pageable = PageRequest.of(
            page, 2, Sort.by(Sort.Direction.ASC, "id"));

        Page<ReportSummary> visible = tenantAdmin
            ? repository.findTenantPage(tenant, pageable)
            : repository.findOwnerPage(tenant, username, pageable);

        return new PageResponse(
            visible.getContent(),
            visible.getNumber(),
            visible.getSize(),
            visible.getTotalElements(),
            visible.getTotalPages()
        );
    }
}
```

**Trusted workflow:** principal name comes from `Authentication`, tenant from server-side `TenantScope`, and admin status from provider-issued authorities. Only after establishing scope and choosing the right query does the service fetch the repository-filtered `Page<ReportSummary>`.

`PageRequest.of(page, 2, Sort.by("id"))` ensures deterministic sorting. The demo page bound `<=1000` is not a universal standard; production should configure page/size bounds and consider keyset pagination for deep paging.

### 10.12. ReportController.java: Client Cannot Pick Owner or Tenant

```java
package example.page;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/reports")
    public PageResponse list(
            @RequestParam(defaultValue = "0") int page,
            Authentication authentication) {

        return reports.listVisible(authentication, page);
    }
}
```

The client controls only bounded `page`; even if `?tenantId=t2&owner=admin2` is sent, those values do not enter the query. In applications with multi-tenant switching, add explicit authorized tenant selection.

### 10.13. SecurityConfig.java: HTTP Basic and Authenticated Rule

```java
package example.page;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
            .password(encoder.encode("lan-demo")).roles("USER").build();

        UserDetails minh = User.withUsername("minh")
            .password(encoder.encode("minh-demo")).roles("USER").build();

        UserDetails admin1 = User.withUsername("admin1")
            .password(encoder.encode("admin1-demo"))
            .roles("TENANT_ADMIN").build();

        UserDetails binh = User.withUsername("binh")
            .password(encoder.encode("binh-demo")).roles("USER").build();

        UserDetails admin2 = User.withUsername("admin2")
            .password(encoder.encode("admin2-demo"))
            .roles("TENANT_ADMIN").build();

        return new InMemoryUserDetailsManager(
            lan, minh, admin1, binh, admin2);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(sc -> sc
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(rc -> rc
                .requestCache(new NullRequestCache()));

        // Demo has GET only. Never disable CSRF by default for write endpoints.
        return http.build();
    }
}
```

`SessionCreationPolicy.STATELESS` indicates each Basic request is processed without relying on a logged-in HTTP session. `NullSecurityContextRepository` avoids saving authentication context into a session; `NullRequestCache` avoids saving prior URLs for form redirects.

Default `CSRF` is not disabled. If adding POST/PUT/DELETE, evaluate CSRF against real clients/browsers and credential mechanisms; never treat "stateless API" as an automatic reason to disable all CSRF protection.

### 10.14. SeedData.java: Deterministic Data

```java
package example.page;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SeedData {

    @Bean
    CommandLineRunner seedReports(ReportRepository repository) {
        return args -> repository.saveAll(List.of(
            new ReportEntity(1L, "t1", "lan", "Lan report A"),
            new ReportEntity(2L, "t1", "minh", "Minh report A"),
            new ReportEntity(3L, "t1", "lan", "Lan report B"),
            new ReportEntity(4L, "t1", "lan", "Lan report C"),
            new ReportEntity(5L, "t1", "minh", "Minh report B"),
            new ReportEntity(6L, "t2", "binh", "Binh report A"),
            new ReportEntity(7L, "t2", "binh", "Binh report B"),
            new ReportEntity(8L, "t1", "lan", "Lan report D")
        ));
    }
}
```

Data has fixed IDs and tests perform no mutations, making page 0, page 1, and counts completely predictable. Production must use versioned migrations/seeding rather than unconditionally writing data on every startup.

### 10.15. JUnit 5 / MockMvc Integration Tests

File `src/test/java/example/page/ReportPaginationSecurityTest.java`:

```java
package example.page;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportPaginationSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotListReports() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void lanPageZeroContainsTwoOwnedItemsAndScopedTotal()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(3))
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.totalElements").value(4))
            .andExpect(jsonPath("$.totalPages").value(2));
    }

    @Test
    void lanPageOneContainsRemainingOwnedItems() throws Exception {
        mvc.perform(get("/api/reports").param("page", "1")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.items[0].id").value(4))
            .andExpect(jsonPath("$.items[1].id").value(8))
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void minhSeesOnlyHisTwoReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("minh", "minh-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(2))
            .andExpect(jsonPath("$.items[1].id").value(5))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void tenantOneAdminSeesSixTenantOneReports()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin1", "admin1-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(2))
            .andExpect(jsonPath("$.totalElements").value(6))
            .andExpect(jsonPath("$.totalPages").value(3));
    }

    @Test
    void tenantOneAdminThirdPageNeverContainsTenantTwo()
            throws Exception {
        mvc.perform(get("/api/reports").param("page", "2")
                .with(httpBasic("admin1", "admin1-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(5))
            .andExpect(jsonPath("$.items[1].id").value(8))
            .andExpect(jsonPath("$.totalElements").value(6));
    }

    @Test
    void tenantTwoAdminSeesOnlyTenantTwo() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin2", "admin2-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(6))
            .andExpect(jsonPath("$.items[1].id").value(7))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void tenantTwoMemberSeesOnlyOwnedReports() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("binh", "binh-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(6))
            .andExpect(jsonPath("$.items[1].id").value(7))
            .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void cannotOverrideServerTenantUsingQueryParameters()
            throws Exception {
        mvc.perform(get("/api/reports")
                .param("tenantId", "t2")
                .param("owner", "admin2")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(1))
            .andExpect(jsonPath("$.items[1].id").value(3))
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void clientCannotInflateFixedPageSize() throws Exception {
        mvc.perform(get("/api/reports")
                .param("size", "100000")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.size").value(2))
            .andExpect(jsonPath("$.items.length()").value(2));
    }

    @Test
    void outOfRangePageIsEmptyButTotalRemainsScoped()
            throws Exception {
        mvc.perform(get("/api/reports").param("page", "9")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items").isEmpty())
            .andExpect(jsonPath("$.totalElements").value(4));
    }

    @Test
    void negativePageIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "-1")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void excessivePageIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "1001")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPageTypeIsRejected() throws Exception {
        mvc.perform(get("/api/reports").param("page", "abc")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownRouteIsDeniedEvenWithValidCredentials()
            throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("lan", "lan-demo")))
            .andExpect(status().isForbidden());
    }
}
```

**Key tests:**

- Missing/invalid Basic credentials → 401, proving authentication works.
- `lan` sees only 4 reports across **exactly 2 pages**; page 0 has 2 items, page 1 has 2 items.
- `admin1` sees 6 tenant1 reports and never sees tenant2 IDs 6/7; `admin2` sees only tenant2.
- Query parameters `tenantId=t2&owner=admin2` **cannot alter** Lan's server-side scope.
- `size=100000` cannot inflate page size because the controller enforces a fixed page size.
- Out-of-range pages return empty content while **the user's** total remains unchanged.
- Negative/oversized/non-numeric pages are rejected with 400.
- Out-of-scope URLs are denied even with valid credentials.

### 10.16. Run Commands

In the `resource-pagination-security` project directory with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

**Sixteen tests are designed to pass** with the dependencies and configuration above. This is a source-level check and **expected** outcome, not a claim that Maven was executed in the reader's environment.

Try the local API (using demo accounts only):

```bash
curl -i http://localhost:8080/api/reports
curl -i -u lan:lan-demo "http://localhost:8080/api/reports?page=0"
curl -i -u lan:lan-demo "http://localhost:8080/api/reports?page=1"
curl -i -u admin1:admin1-demo "http://localhost:8080/api/reports?page=2"
curl -i -u admin2:admin2-demo "http://localhost:8080/api/reports"
```

`curl -u` can expose passwords in shell history or process listings; never use such commands with real secrets. HTTP Basic requires **HTTPS** in production; Base64 is not transport encryption.

Example JSON for Lan, page 0:

```json
{
  "items": [
    {"id": 1, "title": "Lan report A"},
    {"id": 3, "title": "Lan report B"}
  ],
  "page": 0,
  "size": 2,
  "totalElements": 4,
  "totalPages": 2
}
```

Both the array and total are produced from a **tenant + owner filtered query**, without `repository.findAll(pageable)` and without global counts.

## 11. Standalone Java 17: Proving the Post-Pagination Filtering Bug

If Spring Boot is not installed yet, you can run the following Java 17 program to see the math clearly. It simulates list + filter + pagination only, without executing SQL or method security.

Create file `PaginationFilteringDemo.java`:

```java
import java.util.List;

public class PaginationFilteringDemo {

    record Report(int id, String owner) {}

    static List<Integer> visibleIds(List<Report> data, String user) {
        return data.stream()
            .filter(report -> report.owner().equals(user))
            .map(Report::id)
            .toList();
    }

    public static void main(String[] args) {
        List<Report> all = List.of(
            new Report(1, "minh"),
            new Report(2, "minh"),
            new Report(3, "lan"),
            new Report(4, "minh"),
            new Report(5, "lan"),
            new Report(6, "minh"),
            new Report(7, "lan"),
            new Report(8, "lan")
        );

        int pageSize = 3;

        // WRONG: fetch a global page first, then filter.
        List<Report> globalPageZero = all.subList(0, pageSize);
        System.out.println("global page 0, then filter: " +
            visibleIds(globalPageZero, "lan"));

        // MATHEMATICALLY RIGHT: filter the entire set before splitting pages.
        // Real DBs should apply the filter before LIMIT/OFFSET.
        List<Integer> scoped = visibleIds(all, "lan");

        System.out.println("filtered first page: " +
            scoped.subList(0, pageSize));
        System.out.println("filtered second page: " +
            scoped.subList(pageSize, scoped.size()));
        System.out.println("visible total: " + scoped.size());
    }
}
```

Compile/run on Java 17:

```bash
javac PaginationFilteringDemo.java
java PaginationFilteringDemo
```

**Exact** stdout:

```text
global page 0, then filter: [3]
filtered first page: [3, 5, 7]
filtered second page: [8]
visible total: 4
```

Takeaway from the demo: the two operations **do not commute**:

```text
filter(page(globalData))  !=  page(filter(globalData))
```

This Java code scans a small list for clarity. For real large data, push filter conditions into the DB query rather than using `stream().filter` over all real records.

## 12. Count and Metadata Are Also Sensitive Data

Sometimes an API returns zero forbidden rows yet still leaks:

- The entire tenant's report count even though the user can view only their own.
- Customer/order counts of other tenants via `totalElements`.
- `hasNext` computed from the global dataset, revealing hidden items on later pages.
- Growth/decline in report counts via timestamps, ETags, or cache keys.
- Out-of-scope IDs via differing responses across 403, 404, and empty lists.

Thus data minimization does not stop at `content`. **Pagination metadata must follow the exact same access rules**. When counts are unnecessary, omitting counts is safer than exposing a global number.

### 12.1. 403 and 404 on Detail Endpoints

A `GET /api/reports/{id}` API may return 404 for both "not found" and "unauthorized" to limit enumeration. That is a threat-model design choice; never assume a filtered list query automatically makes every 404 safe. Detail resource access must enforce owner/tenant with the same policy without leaking data via unintended timing or metadata.

### 12.2. Preventing Cross-User Cached Responses

If `/api/reports?page=0` responses are cached by URL without principal/tenant, user B's request can receive user A's page and total. In Spring Security resource lists, every cache layer (HTTP reverse proxy, CDN, service, DB query cache, application cache) needs proper policies and keys.

Conceptual cache key example:

```text
tenantId | principalId | role/policyVersion | page | size | sort | filters
```

Even this key is incomplete for every domain. For sensitive data, consider `Cache-Control: private/no-store` as required; never include raw credentials, cookies, or session IDs in cache keys or logs.

## 13. When Permissions Are Complex: ACLs, Groups, and Per-Resource Roles

Owner-only is a simple policy. Real systems may have:

- Reports shared with group A; users belonging to multiple groups.
- `EDITOR` role only on project X.
- Tenant admin allowed to view, but not export.
- ACL grants per report ID, action, and principal/group.
- Locked, expired, or soft-deleted reports.
- Temporary permissions tied to schedules/review cycles.
- ABAC policies based on account state, purpose, location, or service constraints.

When visibility involves many-to-many relationships, embed permissions into the query:

```sql
SELECT r.id, r.title
FROM reports r
WHERE r.tenant_id = :trusted_tenant
  AND r.deleted = FALSE
  AND (
    r.owner_username = :username
    OR EXISTS (
      SELECT 1
      FROM report_grants g
      WHERE g.report_id = r.id
        AND g.grantee_username = :username
        AND g.permission = 'READ'
    )
  )
ORDER BY r.id ASC
LIMIT :limit OFFSET :offset;
```

This is illustrative SQL. `EXISTS` avoids duplicating rows when a user holds multiple grants, keeping counts and pagination consistent. Index the join/permission keys; never rely on mutable string usernames as the sole security key in real systems.

### 13.1. Permission Changes Must Reflect in Queries and Counts

If a grant is revoked between page 0 and page 1, the two requests can observe different sets. Consider requirements:

- Ordinary UI lists can tolerate shifting snapshots.
- Financial audits/exports may require consistent snapshots or jobs capturing permissions at authorization time.
- Permission caches must satisfy revocation latency via invalidation/TTLs.
- Never use a long-lived "last known permit" for sensitive data when policy demands near-instant revocation.

### 13.2. Row-Level Security (RLS) as a Defense Layer

Some DBs support row-level security to enforce visibility close to the data. RLS reduces risk if an application omits a predicate, but requires **trusted session context / DB roles**, strict connection-pool hygiene, and tests preventing one request's tenant context from leaking into the next.

RLS does not replace HTTP authentication and does not automatically solve pagination ordering, count cost, or object-level business actions. Treat it as **defense in depth** alongside query/service policies.

### 13.3. Materialized Visibility and Search Indexes

When permission policies are too complex per query, large systems may maintain materialized visibility tables or search indexes tagged with principal/group/tenant permissions. However, visibility indexes must update on grants/revocations, ownership transfers, and group changes. If an index goes stale, lists can expose revoked items.

Evaluate consistency lag, auditing, rebuild strategies, and "fail closed if index is missing/stale" policies before using this for high-risk data.

## 14. Client-Chosen Search Filters and Sorting

### 14.1. Search Filters Must Share the Same Scope

Endpoint:

```text
GET /api/reports?query=finance&page=0
```

must not search system-wide by keyword and then filter tenant/owner after pagination. Correct predicates include:

```sql
WHERE tenant_id = :trusted_tenant
  AND owner_username = :authenticated_username
  AND lower(title) LIKE :trusted_escaped_keyword
```

`query` is untrusted input requiring wildcard escaping, length bounds, bound parameters, and query-cost controls. The count query must include the exact same keyword + tenant/owner predicates. With full-text search, indexes or search services must enforce permission filters before returning results and metadata.

### 14.2. Sort Allowlist

Never accept raw SQL column names from `?sort=...` and concatenate them into statements. Use an allowlist of valid sort keys such as `id`, `createdAt`, `title`, capping sort-key count, direction, and including an ID tie-breaker.

Sorting by a sensitive hidden field can still leak information via result ordering; evaluate against your threat model.

### 14.3. Page Size Bounds

An API allowing `size=10000000` can trigger heavy queries and massive responses. Cap page size (e.g., 20–100 depending on purpose), bound offsets, and rate-limit. The sample fixes size=2 for clarity, which should not be copied literally as `2` for every product.

### 14.4. Totals Do Not Guarantee Cross-Request Snapshots

Content queries and count queries are usually two separate DB operations. Under concurrent inserts/deletes, totals can shift between them depending on isolation and transactions. If strict consistency is needed, evaluate transaction isolation, snapshots, or versioned data; never claim `Page` guarantees an immutable read snapshot on every DB.

## 15. Proper Testing Strategy for Correctness and Performance

### 15.1. Authorization Matrix

At minimum test:

| Scenario | Content | Metadata |
| --- | --- | --- |
| Anonymous | Cannot enter protected endpoint | No count returned |
| Authenticated user A | Only rows A is permitted | Total reflects only A's rows |
| User B in same tenant | Cannot see A's rows | Total reflects only B's rows |
| Tenant admin | Only assigned tenant scope | Total reflects only tenant rows |
| Other tenant's admin | Cannot see into tenant A | Never leaks tenant A's total |
| Client tampers `tenantId/owner` | Does not change scope | Does not change total |
| Last page | No duplicate/missing items on static data | Accurate total/hasNext |
| Page beyond end | Empty content | Total remains visible total |
| Negative/oversized page | 400 | Does not run unbounded queries |
| New/soft-deleted row | Query/count share policy | No metadata leak |

### 15.2. Testing Filter Ordering and Boundaries

Deliberately seed **interleaved owners** within the same tenant, such as ID 1 Lan, 2 Minh, 3 Lan... If tests only have one user or contiguous IDs, a broken "global page then filter" implementation can accidentally pass. Testing Lan's page 0 and page 1 with total 4 exposes the bug.

### 15.3. Measuring Query Counts and Indexes

Common tools:

- Controlled SQL logging in development to inspect predicates and ORDER BY.
- `EXPLAIN`/`EXPLAIN ANALYZE` on the target DB to inspect index scans, rows examined, and sorts.
- p95/p99 latency separated between content queries and count queries.
- Query count per API call to catch N+1 issues.
- Heap/GC and response size under large page sizes.
- Load tests with production-like tenant/permission distributions.

**Never use in-memory H2 as a benchmark representing PostgreSQL/MySQL/Oracle.** It illustrates query/pagination behavior, while real performance must be measured on the target DB/dialect with anonymized realistic data.

### 15.4. Regression Checks When Adding Filters

After adding `status` or `query`:

1. Test each filter combined with owner/tenant.
2. Test that the count query updates together with the content query.
3. Test sort tie-breakers and page boundaries.
4. Test that query parameters never act as permission proofs.
5. Test denial when a user is revoked or tenant scope changes.
6. Test JOINs that could duplicate rows and verify distinct counts.
7. Test data caches/search indexes to ensure no prior principal's rows or metadata leak.

## 16. Common Pitfalls and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `findAll(pageable)` then `filter(canRead)` | Short pages, wrong total/hasNext | Filter in DB before paging |
| Returning `Page.getTotalElements()` from global query | Leaks others' record counts | Count within user/tenant scope |
| Using single-page `allowed.size()` as total | Wrong total for visible set | Run filtered count query or omit total |
| `@PostFilter` on `Page<T>` expecting auto-fixed metadata | Broken page semantics / unsupported | Query-filter or separate total-free API |
| Filtering content query properly while leaving count broad | Metadata leak and wrong page counts | Share predicates across content/count |
| Member query omitting tenant | Cross-tenant leak on matching usernames/owners | Always constrain tenant |
| Tenant admin query lacking WHERE tenant | Tenant A admin reads Tenant B | Enforce trusted tenant scope |
| Trusting `?tenantId=t2&owner=admin` | User picks scope / escalates privileges | Server verifies identity/tenant/permission |
| `Page.map` returning null to hide items | Nulls in content, wrong counts | Map projections only on an authorized page |
| Missing `ORDER BY` | Pages shift order arbitrarily | Stable sort with unique tie-breaker |
| Sorting by timestamp without ID | Rows with identical timestamps repeat/drop | `ORDER BY created_at, id` |
| Unbounded deep offsets | Slow queries / DoS | Bounds, rate limits, keyset where appropriate |
| Letting clients inflate page size unboundedly | Heavy DB/network/heap load | Enforce max page size |
| Running `Slice` on global data then filtering | `hasNext` does not reflect visible data | Filter before Slice |
| Calling permission DB per row | N+1 queries | JOIN/EXISTS, batch ACL, scoped cache |
| Queries without projections | Loads unnecessary PII/large blobs | Select list columns only |
| `OR isAdmin` with header-derived boolean | Easy privilege escalation | Take roles from Authentication and server scope |
| Counting raw rows on ACL JOINs | Duplicate resources and inflated totals | Use `EXISTS` or `count(distinct ...)` |
| Protecting list while omitting detail owner checks | BOLA via direct ID | Same policy in detail/service |
| Caching by URL without principal/tenant | Cross-user data leak | Scoped private cache/keys, no-store if needed |
| Assuming count and content always share a snapshot | Skew under concurrent writes | Consider transactions/snapshots |
| Wrong predicates for soft-deleted/archived rows | Leaks sensitive status/IDs | Apply status predicates to query and count |
| Forgetting revocation/cached permissions | Displays items after access revoked | Invalidation / policy versioning |
| Testing with only one owner | Misses post-page filtering bugs | Seed interleaved multi-owner data |
| Using H2 to declare production indexes optimal | Wrong query plans on real DBs | Run EXPLAIN on target DB |
| Disabling CSRF just because API is stateless | Browsers can still auto-send credentials | Evaluate CSRF per threat model |

## 17. Debugging Workflow When Pagination Shows Wrong Data

1. **Right SecurityFilterChain?** Check `securityMatcher` and `@Order` if multiple chains exist; is the request truly authenticated?
2. **Where is user scope from?** Are `Authentication.getName()` and trusted tenant membership correct?
3. **Which role policy?** Tenant admins are admin only in their tenant, not globally.
4. **Which query is called?** `findOwnerPage` or `findTenantPage`; does the predicate bind tenant?
5. **Is WHERE applied before OFFSET?** Is the service calling `repo.findAll(pageable).getContent().filter(...)`?
6. **What is the COUNT query?** Does it match content WHERE, status, search, and joins?
7. **Is sorting stable?** Is there an ID tie-breaker, right direction, or concurrent row updates?
8. **Page size/offset?** Are negative, oversized, and overflow inputs guarded?
9. **Does metadata leak data?** Do totalElements/totalPages/hasNext come from the global dataset?
10. **What does the DTO expose?** Are owner/tenant/private fields serialized unnecessarily?
11. **Is there an N+1 permission check?** Is a repository or evaluator querying per row?
12. **Do JOINs duplicate rows?** Are `DISTINCT`/`EXISTS` and matching counts used?
13. **Is a cache stale?** URL-only cache or un-invalidated principal/tenant cache?
14. **Did permissions change between pages?** Snapshot drift, revocation, or data mutations.
15. **Do queries leak in errors/logs?** Never print credentials, session IDs, or PII.
16. **If using @PostFilter**, does the return type actually support filtering and is metadata accurate?
17. **If users see empty pages despite existing resources**, check for post-global-page filtering.
18. **If count is too slow**, consider Slice/keyset, indexes, and real-DB query plans.

Controlled SQL/debug logging can be enabled in test environments, provided bind parameters with private data or full report payloads are never logged. A test with interleaved tenant/owner data usually exposes bugs faster than reading long logs.

## 18. Practice Questions with Answers

**1.** The database has 100 rows, and a user can see 8 rows. Does fetching a global page of size 20 and filtering in Java guarantee the first page returns all 8 items?

**Answer:** No. Those 8 visible rows may lie outside the first 20 global rows. Apply the visibility filter before pagination.

**2.** After filtering one global page, 3 items remain. Can you set `totalElements=3`?

**Answer:** No, that is only the remaining count on **the current page**, not the total visible across the dataset.

**3.** Does `Page.map(...)` recompute totals when mapping forbidden entities to null?

**Answer:** No. Mapping neither replaces resource-level authorization nor pre-page filtering.

**4.** Why must `countQuery` share the same tenant/owner/search predicates as the content query?

**Answer:** So `totalElements/totalPages` metadata accurately reflects the visible set without leaking global counts or another tenant's resource counts.

**5.** Does `Slice` eliminate the need for database security filters?

**Answer:** No. It only omits the API total count; `hasNext` and slice boundaries must still be computed on the permitted set.

**6.** A user modifies the query to `?tenantId=otherTenant`. Should the server trust that parameter?

**Answer:** No. If tenant switching is supported, the server must verify membership/authorization first; the sample derives tenant from a trusted scope.

**7.** A tenant admin holds ROLE_TENANT_ADMIN. Can the query omit WHERE tenantId?

**Answer:** No, when administration is **tenant-scoped**. A role does not imply cross-tenant rights.

**8.** Sorting only by `createdAt DESC` when multiple rows share timestamps—what is the risk?

**Answer:** Non-deterministic ordering among equal timestamps causes duplicate or skipped items across pages. Add a unique tie-breaker like ID.

**9.** When can `@PostFilter` on a small List be useful?

**Answer:** When data is bounded, already validly fetched, and Page metadata accuracy is not required; still weigh PII, performance, and defense in depth.

**10.** When should you prefer keyset/cursor pagination?

**Answer:** Large feeds/lists needing next-page navigation where deep offsets are too slow and sort keys are stable. Every cursor query must still include visibility predicates and tamper-resistant scopes.

**11.** An ACL JOIN query returns multiple rows per report due to multiple grants; how can direct `count(*)` go wrong?

**Answer:** The count inflates with the number of grants instead of unique reports. Use EXISTS or a matching count distinct.

**12.** A user passes the HTTP rule `authenticated()`. Is that enough to read any report in the database?

**Answer:** No. HTTP authentication is only one layer; owner/tenant/action must be verified in queries/services.

**13.** Why should tests for Lan's page 0/1 include interleaved Minh rows?

**Answer:** It exposes post-global-pagination filtering bugs that stay hidden when all rows of one owner are contiguous.

**14.** Why can page count differ from content even when SQL predicates are correct?

**Answer:** Data can change between the count and content queries due to transaction isolation and concurrent writes; use snapshot policies if strict consistency is required.

**15.** What is the risk of sharing a cached `/api/reports?page=0` response across all users?

**Answer:** It can serve another user's or tenant's items and metadata. Caches must be partitioned by principal/tenant/policy or disabled for sensitive data.

## 19. Pre-Deployment Checklist

### Data Access and Policy

- [ ] Trusted tenant, principal, roles, and visibility predicates are clearly defined.
- [ ] Content queries apply predicates before `ORDER BY + LIMIT/OFFSET` or keyset seek.
- [ ] Count queries use the exact same tenant/owner/status/search predicates.
- [ ] Protected lists never use global `findAll(pageable)` followed by per-row filtering.
- [ ] Resource-level checks also protect detail/update/delete endpoints, not just lists.
- [ ] DTOs include only required fields, avoiding loading/exposing unnecessary sensitive payloads.
- [ ] Revocation and permission caching satisfy consistency requirements.

### Pagination and Performance

- [ ] Page size and offset have bounds and rate limits.
- [ ] Sorting uses a unique tie-breaker; tested against inserts, deletes, and permission changes between pages.
- [ ] Page vs. Slice vs. cursor chosen according to UI requirements.
- [ ] EXPLAIN/metrics collected on the target DB and production-like data distributions.
- [ ] No N+1 permission queries.
- [ ] Indexes support tenant, owner, status, and sort columns.
- [ ] Metadata reflects only the visible scope or is intentionally omitted.

### Security and Testing

- [ ] Tested anonymous, owner, non-owner, tenant admin, and cross-tenant admin.
- [ ] Tested forged `tenantId/owner` query params being ignored or rejected.
- [ ] Tested interleaved IDs to catch post-page filtering.
- [ ] Tested that count/totalPages/hasNext do not leak data.
- [ ] Tested negative page, excessive page, oversized page size, and invalid sort inputs.
- [ ] Tested CSRF, HTTPS, and auth mechanisms when mutation endpoints exist.
- [ ] Caches/proxies/logs/audits contain no credentials or cross-user results.
- [ ] H2 performance tests are not used to draw production DB conclusions.

## 20. Key Summary

- **Filter permissions before pagination**: `WHERE tenant/owner/ACL` must run before `LIMIT/OFFSET` or cursor seek whenever the policy fits in a query.
- **Never paginate globally and then filter in Java**: doing so creates underfilled pages, corrupts `totalElements/totalPages/hasNext`, and risks metadata leaks.
- `Page<T>` carries count metadata requiring the same scope as the content query; `Slice<T>` omits total counts yet still requires visibility filtering before page boundaries.
- `@PostFilter`/`Stream.filter` can help on small collections, but never replaces database-level pagination for large lists, and must not be assumed to handle `Page<T>` properly.
- **Derive tenant and owner from trusted sources**, never self-declared query params or headers; tenant admins must still be constrained to their tenant.
- Choose DTO projections, deterministic sorting, proper indexes, bounded page sizes/offsets, avoid N+1, and consider keyset pagination for deep paging.
- **Counts, hasNext, cache keys, sort order, and JSON metadata are all security surfaces**, not just the returned items themselves.
- Test with interleaved-owner data, check page 0, page 1, and totals, and verify 200/401/403 so both HTTP auth and data-access policies do their jobs properly.
