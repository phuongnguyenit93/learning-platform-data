# IN Queries, Empty Parameter Sets, and Parameter Limits

In Spring Data Relational R2DBC, the `IN` condition is commonly used when finding rows whose key or attribute belongs to a set of values—such as a selected list of IDs, allowed statuses, or a group of product codes. Spring Data supports expressing this condition via derived queries like `findByIdIn(...)`, via `@Query`, and via `Criteria.in(...)` when using `R2dbcEntityTemplate`.

Important details to watch out for are that the input collection may be empty, contain `null`, contain duplicate elements, or grow too large. When a collection is expanded into multiple bind parameters, the actual number of SQL parameters grows with the element count. Databases and drivers impose their own limits on bind markers, statement size, and the number of expressions in an `IN` list. Therefore, the application must define the semantics of empty sets, normalize input data, and choose an appropriate strategy when lists become large.

## 1. Meaning of the IN condition

`IN` checks whether a value belongs to a set of values. SQL example:

```sql
SELECT id, name, status
FROM product
WHERE status IN ('ACTIVE', 'PENDING');
```

The result includes products whose `status` is `ACTIVE` or `PENDING`. Logically, this condition is equivalent to multiple equality comparisons joined with OR:

```sql
WHERE status = 'ACTIVE' OR status = 'PENDING'
```

`NOT IN` expresses the opposite condition: the value does not belong to the listed set.

```sql
SELECT id, name, status
FROM product
WHERE status NOT IN ('DELETED', 'ARCHIVED');
```

The `IN` condition works well for sets of IDs or codes gathered by the application. However, you need to understand how Spring Data translates collections into SQL parameters and how SQL handles empty sets and `NULL`.

## 2. Derived queries with In and NotIn

Spring Data R2DBC supports the `In` and `NotIn` keywords in repository method names. Example:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByIdIn(Collection<Long> ids);

    Flux<Product> findByStatusIn(Collection<String> statuses);

    Flux<Product> findByStatusNotIn(Collection<String> excludedStatuses);
}
```

These methods mean:

- `findByIdIn(ids)`: retrieves products whose ID is in the `ids` collection.
- `findByStatusIn(statuses)`: retrieves products whose status is in the `statuses` collection.
- `findByStatusNotIn(excludedStatuses)`: retrieves products whose status is not in the excluded set.

Spring Data generates the query and binds values using R2DBC's mechanism. There is no need to concatenate IDs into a SQL string manually. Collections can be represented as a `Collection`, array, or varargs depending on the signature and parser support of the Spring Data version.

Usage example:

```java
Flux<Product> findSelectedProducts(Collection<Long> selectedIds) {
    return productRepository.findByIdIn(selectedIds);
}
```

For ID lists coming from requests, validate the collection before calling the repository. Do not let an abnormal or excessively large collection pass straight down to the database.

## 3. Using IN inside @Query

In declared queries, you can place a named parameter inside an `IN` expression:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    @Query("""
        SELECT id, name, status
        FROM product
        WHERE id IN (:ids)
        ORDER BY id
        """)
    Flux<Product> findProductsByIds(@Param("ids") Collection<Long> ids);
}
```

In Spring APIs that support named parameter expansion, the collection is expanded into bind markers matching the number of elements. For example, a collection of three IDs might conceptually produce SQL like:

```sql
WHERE id IN ($1, $2, $3)
```

The actual marker format depends on the driver. This illustrates collection expansion, not a SQL string that the application should construct itself.

Collection expansion support and exact syntax depend on the Spring Data/DatabaseClient API and version in use. Consult your version's documentation and run integration tests against a real driver. Do not assume a `List` can be bound as a single scalar value in every R2DBC API.

## 4. Using Criteria.in with R2dbcEntityTemplate

When conditions are built dynamically, `Criteria.in(...)` represents a value set:

```java
Criteria criteria = Criteria.where("id").in(ids);
Query query = Query.query(criteria);

Flux<Product> products = template.select(query, Product.class);
```

It can be combined with other conditions:

```java
Criteria criteria = Criteria.where("id").in(ids)
    .and("status").is("ACTIVE");

Query query = Query.query(criteria)
    .sort(Sort.by(Sort.Order.asc("id")))
    .limit(100);

Flux<Product> products = template.select(query, Product.class);
```

This example retrieves products whose ID is in the given set and whose status is `ACTIVE`, sorted by ID and limited to at most 100 rows.

`Criteria.in(...)` still requires handling empty collections and `null` before building the query. Never let a request with no IDs accidentally turn into an unfiltered query.

## 5. Empty sets: the most important edge case

A collection can be empty because the client selected nothing, a previous filtering step produced zero elements, or input data was missing.

Example:

```java
List<Long> ids = List.of();
```

By set logic:

- `x IN empty-set` is always false: no value belongs to an empty set.
- `x NOT IN empty-set` is always true: every value is absent from an empty set.

However, do not rely on the database accepting `IN ()` or `NOT IN ()` syntax. Many dialects disallow empty parenthesized lists; how Spring expands empty collections can also vary across APIs and versions. If the generated statement becomes `IN ()`, the query may fail with a syntax error.

**The application must explicitly define the meaning of an empty collection before calling the repository.**

### 5.1. Empty IN often means no results

If a user requests items matching a list of IDs and the list contains no IDs, the sensible result is usually empty:

```java
Flux<Product> findSelectedProducts(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    return productRepository.findByIdIn(ids);
}
```

This approach offers several benefits:

- Issues no unnecessary SQL.
- Does not depend on how the dialect handles `IN ()`.
- Eliminates any risk of accidentally dropping the filter and returning the whole table.
- Makes the service contract explicit that selecting no IDs returns no products.

### 5.2. Empty IN can mean skipping the filter

Some search APIs define an empty collection as "do not filter by this field." For example, if a user selects no statuses, it means searching across all statuses. In that case, the service should omit the predicate and run a query using the remaining conditions:

```java
Flux<Product> search(Collection<String> statuses, String category) {
    if (statuses == null || statuses.isEmpty()) {
        return productRepository.findByCategory(category);
    }

    return productRepository.findByStatusInAndCategory(statuses, category);
}
```

This is a business rule of the API, not an automatic meaning of SQL `IN`. Document clearly in the API contract how omitted lists, empty lists, and non-empty lists are interpreted.

### 5.3. Distinguishing a null collection from an empty collection

These two states can carry different meanings:

| Input | Possible intended meaning | Example handling |
|---|---|---|
| `null` | Client did not supply the filter | Skip the condition |
| Empty collection | Client supplied the filter with zero selected values | Return empty results |
| Non-empty collection | Filter by selected values | Execute `IN` |

Another API might choose a different convention, but it must remain consistent across controller, service, and repository. Do not collapse them into a single `if (ids == null || ids.isEmpty())` branch if business rules need to distinguish the two cases.

## 6. Empty sets with NOT IN

`NOT IN` must be handled according to its own business semantics. Under set logic, `x NOT IN empty-set` holds for every value `x`. If an empty exclusion list means "exclude nothing," the application can omit the `NOT IN` condition:

```java
Flux<Product> findNotExcluded(Collection<Long> excludedIds) {
    if (excludedIds == null || excludedIds.isEmpty()) {
        return productRepository.findAll();
    }

    return productRepository.findByIdNotIn(excludedIds);
}
```

This example is only suitable when business logic truly permits fetching all products when no IDs are excluded. For large datasets, pagination or result limits are still necessary; avoid calling `findAll()` on a large table just because a collection is empty.

If an empty collection means the request is invalid, return a validation error instead of guessing.

## 7. NULL in collections and SQL three-valued logic

SQL uses three-valued logic: an expression can evaluate to TRUE, FALSE, or UNKNOWN. Comparing against `NULL` typically produces UNKNOWN, not TRUE or FALSE.

Example:

```sql
WHERE status IN ('ACTIVE', NULL)
```

If `status = 'ACTIVE'`, the condition is TRUE. If `status = 'PENDING'`, there is no matching value and a NULL element is in the list, so the result can become UNKNOWN. If the row's `status` is NULL, the comparison does not become TRUE either. In a `WHERE` clause, only rows where the condition evaluates to TRUE are retained.

### 7.1. Why is NOT IN with NULL so dangerous?

Consider:

```sql
WHERE id NOT IN (10, 20, NULL)
```

For an ID different from 10 and 20, the database must check whether that ID differs from 10, 20, and NULL. Comparing with NULL yields UNKNOWN, so the entire expression can evaluate to UNKNOWN. The result is typically zero rows returned, even for IDs seemingly outside the exclusion list.

Therefore, never pass a collection containing `null` into `NOT IN`.

### 7.2. Normalizing and stripping nulls before querying

If null has no valid meaning inside an ID set, filter it out or reject the input:

```java
List<Long> normalizedIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();
```

For APIs with strict input contracts, rejecting collections containing null is usually better than silently dropping elements:

```java
if (ids.stream().anyMatch(Objects::isNull)) {
    return Flux.error(new IllegalArgumentException(
        "ID list must not contain null"));
}
```

Whether to reject or normalize depends on the API contract. What matters is preventing SQL three-valued logic from producing surprising results.

### 7.3. If rows with NULL columns should be included

`IN` does not automatically include rows whose column value is SQL NULL. If business rules want rows whose status is in the set or whose status is unassigned, write two explicit branches:

```sql
WHERE status IN ('ACTIVE', 'PENDING')
   OR status IS NULL
```

With `NOT IN`, if you want values outside the list as well as NULL rows, write:

```sql
WHERE (status NOT IN ('DELETED', 'ARCHIVED') OR status IS NULL)
```

If you want only non-null values outside the exclusion list, express that explicitly:

```sql
WHERE status IS NOT NULL
  AND status NOT IN ('DELETED', 'ARCHIVED')
```

Choose the expression matching business rules rather than assuming `NOT IN` always includes null values.

## 8. Removing duplicate elements

A collection may contain duplicate IDs:

```java
List<Long> ids = List.of(10L, 20L, 10L, 30L, 20L);
```

With `IN`, duplicates normally do not change the result set of rows. However, they still inflate the bind parameter count, SQL size, and statement parsing cost. Therefore, normalize using `distinct()` if order and multiplicity carry no other meaning:

```java
List<Long> uniqueIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();
```

For huge collections, deduplication also has memory cost. Consider using a `Set` from the outset if the data contract represents a unique set of reasonable size.

## 9. Bind parameter limits

When Spring expands a collection into bind markers, each element typically adds another parameter to the SQL statement. A query with multiple conditions can use more parameters than the collection's element count alone.

Example:

```sql
SELECT id, name
FROM product
WHERE tenant_id = ?
  AND status = ?
  AND id IN (?, ?, ?, ...);
```

With 2 fixed parameters and 5,000 IDs, the total bind parameter count can reach 5,002. If the query also has date filters, authorization filters, or additional `IN` sets, the count climbs further.

Databases, protocols, and drivers may restrict:

- Maximum bind parameters in a prepared statement.
- Maximum elements inside an `IN` expression.
- Maximum SQL string length or packet/request size.
- Number of expressions or parse resources in a single statement.

These limits differ across database engines and can change by version, configuration, or driver. For example, SQL Server caps parameters in a stored procedure/batch; Oracle limits the number of expressions in an `IN` list in many versions; SQLite has host parameter limits depending on version and build options. Do not apply one universal number to every database.

Check the official documentation for your deployed database, R2DBC driver, and wire protocol. Then set an application limit well below the real ceiling to leave headroom for fixed parameters and avoid oversized statements.

## 10. Calculating the actual parameter count

Suppose a query has:

- 1 `tenantId` parameter.
- 1 `status` parameter.
- 1 `createdAfter` parameter.
- A collection of `n` IDs.

If the collection expands into one marker per ID, the total number of bind parameters is:

\[
P = 3 + n
\]

If there is also a collection of `m` category IDs:

\[
P = 3 + n + m
\]

This estimates parameter count when each element is bound individually. A driver may support array parameters or specialized types to pass an entire set as a single parameter, but that is a driver/database-specific capability rather than default behavior across all `IN` APIs.

When setting limits, do not check only the ID count. Account for all fixed parameters and every expanded collection in the statement.

## 11. Limiting input size in the service layer

An endpoint should never accept an unbounded collection. Enforce a maximum size:

```java
private static final int MAX_IDS = 500;

Flux<Product> findProducts(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    if (ids.size() > MAX_IDS) {
        return Flux.error(new IllegalArgumentException(
            "At most " + MAX_IDS + " IDs can be queried at once"));
    }

    if (ids.stream().anyMatch(Objects::isNull)) {
        return Flux.error(new IllegalArgumentException(
            "ID list must not contain null"));
    }

    List<Long> uniqueIds = ids.stream().distinct().toList();
    return productRepository.findByIdIn(uniqueIds);
}
```

The value `500` is only an example. Your actual limit should be based on:

- Database and driver parameter limits.
- Number of fixed parameters in the query.
- SQL length after collection expansion.
- Latency and execution plans.
- Concurrent request volume.
- Memory and result-processing cost.

If an API needs to handle more IDs, design batching or a dedicated set-passing mechanism instead of raising the limit arbitrarily.

## 12. Splitting large collections into batches

When a list exceeds a reasonable single-query limit, split it into smaller batches. For instance, each batch holds up to 500 IDs:

```java
Flux<Product> findInBatches(List<Long> ids) {
    int batchSize = 500;

    return Flux.fromIterable(ids)
        .buffer(batchSize)
        .concatMap(productRepository::findByIdIn);
}
```

`buffer(batchSize)` forms groups of IDs. `concatMap` runs queries sequentially, avoiding excessive concurrent queries and preserving batch-by-batch processing order.

If the database and connection pool can handle it, you can use bounded concurrency:

```java
Flux<Product> findInBatches(List<Long> ids) {
    int batchSize = 500;
    int concurrency = 4;

    return Flux.fromIterable(ids)
        .buffer(batchSize)
        .flatMap(productRepository::findByIdIn, concurrency);
}
```

A concurrency of 4 means at most four batch queries execute concurrently inside this `flatMap`. Balance this against pool size, database load, and other application traffic. Raising concurrency can boost throughput, but can also cause connection and CPU contention.

### 12.1. Batch results do not necessarily follow input ID order

SQL `IN` does not guarantee result order matches collection element order. Even when batches run sequentially, the database can return rows in execution-plan order.

If deterministic order is required:

- Add an appropriate `ORDER BY` in the query.
- Or keep a position map of input IDs and sort results in the application.
- Handle nonexistent IDs according to explicit rules.

When using `flatMap`, cross-batch order is not guaranteed either. Use `concatMap` when emitting results in batch order, or add a final sort once the result set is bounded.

### 12.2. Batched queries do not automatically guarantee a single data snapshot

Multiple batches are separate SQL statements. If data changes mid-processing, batches may observe database state at different points in time. If business rules require a consistent snapshot, configure an appropriate isolation level and transaction. A long transaction spanning many batches can hold a connection open and increase lock pressure; weigh consistency against resource usage.

### 12.3. Deduplicating IDs before batching

If the same ID appears in multiple batches, the same row can be emitted multiple times. Deduplicate before batching if results should be unique:

```java
List<Long> uniqueIds = ids.stream()
    .filter(Objects::nonNull)
    .distinct()
    .toList();

return Flux.fromIterable(uniqueIds)
    .buffer(500)
    .concatMap(productRepository::findByIdIn);
```

## 13. When should you avoid application-side batching?

Batching is practical, but not always optimal. Every batch adds a round trip and a SQL statement. For very large lists, hundreds or thousands of batches can raise latency and database load.

Alternatives depend on the database engine:

### 13.1. Using temporary or staging tables

If a very large ID set is reused across multiple queries, insert IDs into a temporary or staging table and join against it:

```sql
SELECT p.id, p.name
FROM product p
JOIN requested_ids r ON r.id = p.id;
```

Advantages:

- No need to create thousands of bind markers in a single `IN` statement.
- The database can optimize the join using indexes and statistics.
- The ID set can be reused across multiple queries in one workflow.

Considerations:

- Creating/populating staging tables is database-dependent.
- Temporary table lifetimes depend on session or transaction rules in the engine.
- Operations must stay pinned to the right connection/session.
- Staging data must be cleaned up and isolated between concurrent requests.

### 13.2. Using array parameters or driver-specific features

Some databases support passing an entire array as one parameter with dedicated operators or functions. For example, PostgreSQL supports `= ANY(array)` with an appropriate array type:

```sql
SELECT id, name
FROM product
WHERE id = ANY(:ids);
```

This is PostgreSQL-specific; binding arrays with R2DBC depends on the driver and element types. Never assume `Collection<Long>` automatically becomes a SQL array across all APIs. Use the Java types and array-binding APIs supported by the PostgreSQL driver.

SQL Server has table-valued parameters; other databases offer collection/table types or similar mechanisms. These features are non-portable and require dedicated configuration.

### 13.3. Using joins instead of an IN list

If input values already reside in a relational table, querying via a join is usually cleaner than fetching IDs into the application and sending them back:

```sql
SELECT p.id, p.name
FROM product p
JOIN category_product cp ON cp.product_id = p.id
WHERE cp.category_id = :categoryId;
```

A join keeps filtering inside the database and avoids building large collections on the application heap. Ensure proper indexes exist on join keys.

## 14. IN and NOT IN with nullable data

Beyond `null` elements inside collections, consider whether the filtered column itself can hold SQL NULL.

Example:

```sql
SELECT id
FROM customer
WHERE external_code IN ('A', 'B');
```

Rows with `external_code IS NULL` are not returned. If business logic needs null rows as well, add `OR external_code IS NULL`.

With `NOT IN`, null columns also fail to match because the comparison yields UNKNOWN. To exclude certain codes while keeping rows with unassigned codes, write explicitly:

```sql
WHERE external_code NOT IN ('A', 'B')
   OR external_code IS NULL
```

To retrieve only rows that have a non-null code outside the excluded set:

```sql
WHERE external_code IS NOT NULL
  AND external_code NOT IN ('A', 'B')
```

This is standard SQL NULL semantics in comparison predicates. Write tests for both null columns and null collection elements to prevent subtle business bugs.

## 15. Controlling performance and indexes

`IN` is neither inherently slow nor inherently fast. Performance depends on element count, data distribution, indexes, statistics, and how the database constructs execution plans.

Points to evaluate:

- Does the column used in `IN` have an appropriate index?
- Does the collection contain too many elements or many duplicates?
- Is the value set selective, or does it cover almost the entire table?
- Could a join or staging table replace `IN`?
- How many other fixed parameters are in the query?
- Will concurrent requests noticeably increase database load?
- Do you need all columns, or is a small projection sufficient?

For small ID sets, an index on the key usually helps the database locate rows efficiently. For sets covering most of the table, the database may prefer a table scan as cheaper. Never force index usage without inspecting actual execution plans and metrics.

## 16. Testing IN queries and parameter limits

Tests should cover input semantics, generated SQL, and behavior near limits.

Important cases:

- Single-element collection.
- Multi-element collection.
- Empty collection.
- Null collection.
- Collection containing null elements.
- Collection with duplicate IDs.
- `NOT IN` with null values and empty exclusion sets.
- Database columns containing SQL NULL.
- Collection sizes below, at, and above the application limit.
- Total bind parameters when the query includes other conditions.
- Batching behavior and result ordering.
- Database timeouts or rejection of oversized statements.

Example service test with `StepVerifier`:

```java
StepVerifier.create(productService.findSelectedProducts(List.of()))
    .verifyComplete();
```

This test confirms an empty set produces an empty publisher per the example contract without issuing a repository query.

Testing a populated collection:

```java
StepVerifier.create(
        productService.findSelectedProducts(List.of(10L, 20L))
    )
    .expectNextCount(2)
    .verifyComplete();
```

This assumes the database holds two matching rows. Integration tests should set up explicit fixtures, including nonexistent IDs and duplicate IDs if the service deduplicates.

For parameter limits, include integration tests near your chosen maximum against the actual database/driver. You do not have to push right up to the database engine's absolute maximum in every test; what matters is confirming your application limit maintains a safe margin and errors clearly when exceeded.

## 17. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Calling `findByIdIn(emptyList)` without defined semantics | Possible `IN ()` syntax error or version-dependent behavior | Handle empty collections in the service layer |
| Treating null and empty collections identically | Cannot distinguish omitting a filter from matching nothing | Define an explicit API contract |
| Passing null elements into `NOT IN` | SQL UNKNOWN may cause zero rows to return | Reject or strip nulls before querying |
| Failing to deduplicate elements | Inflates bind parameters and SQL size | Deduplicate when appropriate |
| Sending huge collections in one statement | Exceeds driver/database limits or causes heavy queries | Enforce a maximum and batch/change strategy |
| Counting only IN elements while ignoring other parameters | Total bind markers exceed limit | Count fixed parameters and all other collections |
| Assuming Collection is always one bind value | Driver may not support binding List as a scalar | Use Spring-supported collection expansion or array APIs |
| Using unbounded `flatMap` for batches | Spawns too many concurrent queries | Set bounded concurrency or use `concatMap` |
| Assuming IN preserves input order | Results arrive in indeterminate order | Use `ORDER BY` or sort by input position |
| Batching without deduplication | Duplicate rows may be emitted across batches | Normalize IDs before batching |
| Using IN instead of joining existing table data | Extra round trips and large ID lists | Move the condition into a SQL join |
| Not testing against a real driver | Expansion, array, and limit differences only appear at runtime | Run integration tests on the target database |

## 18. Checklist for processing collections before querying

A service accepting an ID list can follow these steps:

1. Determine whether the collection is omitted, empty, or populated per the API contract.
2. Reject or strip `null` elements according to business rules.
3. Deduplicate elements if multiplicity is irrelevant.
4. Check maximum collection size and estimated total bind parameters.
5. If empty, return empty, skip the filter, or return an error per chosen semantics.
6. If within limits, run a single `IN` query.
7. If oversized, split into bounded batches or use staging tables/arrays/joins suited to the database.
8. Define result ordering, missing-ID handling, and cross-batch consistency.
9. Monitor query latency, parameter-limit errors, and batch counts in production.

## 19. Key principles to remember

- Use `In`/`NotIn` in derived queries, `IN (:values)` in `@Query`, or `Criteria.in(...)` in templates when filtering by sets.
- Verify how collections are expanded and bound in your specific Spring Data/driver version.
- Define explicit semantics for null collections and empty collections; never rely on `IN ()`.
- Under set logic, `IN` with an empty set yields no results and `NOT IN` with an empty set excludes nothing; implement these with explicit application branches.
- Never pass null elements into `NOT IN`; understand SQL three-valued logic and `IS NULL`.
- Deduplicate and normalize collections when appropriate.
- Count total bind parameters after expanding every collection, including fixed parameters.
- Enforce maximum limits in the API/service layer based on real database, driver, and workload limits.
- Split into batches with bounded concurrency when necessary; weigh ordering and cross-batch snapshot needs.
- Use array parameters, staging tables, or joins for huge sets when supported by the database.
- Test empty, null, duplicate, and large collections on the target database/driver.

`IN` queries are a natural way to filter by a set of values, but input collections must be treated as part of the query contract. When an application defines clear semantics for empty sets and nulls, removes duplicates, bounds total bind parameters, and switches to batching or alternative set-passing strategies when needed, queries stay reliable and avoid failures that only surface as production data grows.
