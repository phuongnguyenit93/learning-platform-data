# Limitations of Offset Pagination as Data Grows

Offset pagination is a familiar pagination approach: the application sends a page number and a page size, and Spring Data JPA translates them into a limit and an offset in the query. This approach is simple, supports jumping directly to any page, and works well for moderately sized lists. When data grows large or users navigate to very deep pages, the cost can increase significantly because the database must locate and discard many rows before returning the requested page.

The issue is not just the number of rows returned. For a page with a large offset, the database may have to scan, read, or sort a large volume of rows before discarding the leading portion. If data is continuously inserted or deleted between requests, offset pages can also drift, leading to duplicate or skipped rows. This lesson explains how offset works, when it becomes a bottleneck, and how to transition to keyset/cursor pagination in Spring Data JPA.

## 1. How Does Offset Pagination Work?

Offset pagination specifies:

- **Page number**: the page index, typically 0-based in Spring Data.
- **Page size**: the maximum number of rows per page.
- **Offset**: the number of rows to skip before fetching the current page.

Formula:

`offset = pageNumber × pageSize`

For example, with a page size of 20:

| Page number | Offset | Requested rows |
|---:|---:|---|
| 0 | 0 | 1–20 |
| 1 | 20 | 21–40 |
| 2 | 40 | 41–60 |
| 100 | 2,000 | 2,001–2,020 |
| 10,000 | 200,000 | 200,001–200,020 |

In SQL, the database typically executes an equivalent idea:

```sql
select id, name, created_at
from product
where active = true
order by created_at desc, id desc
limit 20 offset 200000;
```

Row-limiting syntax varies by database. PostgreSQL/MySQL support LIMIT/OFFSET; SQL Server commonly uses OFFSET/FETCH; Oracle has its own syntax or standard syntax depending on the version.

An offset of 200,000 does not mean the database jumps instantaneously to row 200,001. Depending on the execution plan, indexes, and filter predicates, the database may have to read/traverse the preceding entries and then discard them. If sorting is required, the cost may also include sorting a large result set before applying offset/limit.

## 2. Using Pageable in Spring Data JPA

Spring Data JPA supports offset pagination via `Pageable` and `PageRequest`.

Repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);
}
```

Service:

```java
@Service
public class ProductQueryService {

    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<Product> findActiveProducts(int page, int size) {
        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        return repository.findByActiveTrue(pageable);
    }
}
```

`PageRequest.of(0, 20)` requests the first page with up to 20 rows. `PageRequest.of(100, 20)` requests an offset of 2,000. The page index starts at 0, while the page size must be a positive number.

The sort should have a deterministic order. In the example, `createdAt` is the primary criterion and `id` is the unique tie-breaker. If you sort only by createdAt, rows with the same timestamp can change order between executions.

Do not accept an arbitrary page size from the client. Set a maximum limit to avoid requests asking for tens of thousands or millions of results at once.

## 3. Why Do Deep Offsets Become Increasingly Expensive?

Suppose a query needs to return 20 rows. The first page only needs to find and return about 20 matching rows. Page 10,000 has an offset of 199,980; the database still needs to identify and skip the vast majority of results before returning the next 20 rows.

Common sources of cost:

1. **Traversing indexes or rows before the offset:** an index can help find rows in order, but the database still needs to walk past the entries preceding the target position.
2. **Filtering:** if the WHERE predicate has low selectivity or lacks an index, the database may have to inspect many rows to find enough rows to skip and return.
3. **Sorting:** if no index satisfies the ORDER BY, the database may have to sort a large result set. The sort cost can far exceed the cost of returning the final page.
4. **JOINs:** queries with multiple JOINs, especially collection JOINs, can multiply intermediate rows before pagination.
5. **Count query:** the Page return type typically requires the total result count to compute totalElements/totalPages. The count can be expensive even when the data page only contains a few rows.
6. **Database resources:** CPU, buffer/cache, I/O, sort memory, and connection hold time can all increase.

Offset pagination is not necessarily slow merely because the page number is large. If the dataset is small, indexes are suitable, filters are selective, and the execution plan is good, the query may still be responsive. You need to measure at realistic data scale.

## 4. Do Indexes Completely Solve Deep Offsets?

A proper index can reduce filter and sort costs, but it cannot eliminate the fundamental need to skip a large number of results before the offset.

Example query:

```sql
select id, created_at, name
from product
where tenant_id = ?
  and active = true
order by created_at desc, id desc
limit 20 offset 200000;
```

A candidate index might start with equality filter columns followed by the sort keys, for example:

```sql
create index ix_product_tenant_active_created_id
on product(tenant_id, active, created_at desc, id desc);
```

The actual index must be designed based on the database, cardinality, update frequency, filters, and workload. Some databases can scan indexes backward, so declaring DESC is not always necessary for every case. Use EXPLAIN/EXPLAIN ANALYZE to inspect:

- Is the right index being used?
- Is there a full table scan or a large sort?
- Do estimated and actual row counts diverge?
- Are many rows being read to return a small page?
- Are the JOIN order and filters appropriate?

Indexes can make deep offsets much better, but when offsets reach hundreds of thousands or millions, the database still has to process the preceding portion of results according to the execution plan.

## 5. Page, Slice, and List: How Do They Differ?

Spring Data JPA can return several result types when using Pageable:

| Type | Contents | Total count info | Count query |
|---|---|---|---|
| `Page<T>` | Current page data | Has totalElements and totalPages | Usually requires a count query when total must be determined |
| `Slice<T>` | Current page data | Only knows whether there is a next page | Usually does not need a count query; may read one extra row to determine hasNext |
| `List<T>` | Data limited by Pageable | No Page/Slice metadata | Does not need a count query |

Slice example:

```java
Slice<Product> findByActiveTrue(Pageable pageable);
```

Using Slice can eliminate the cost of counting total records. However, Slice still uses an offset if the Pageable is a PageRequest. Therefore, Slice helps reduce count queries but does not solve the cost of skipping rows at deep offsets.

If the UI only needs a "Load more" button and does not need the total number of pages, Slice is usually a better fit than Page. If page numbers or total result counts are needed, Page provides useful metadata, though the count query must be considered.

## 6. The Problem of Data Changing Between Requests

Offset pagination can be unstable when data changes between page loads.

Suppose the first page displays rows A–J. Before loading the next page with offset 10, a new row is inserted at the beginning of the list. Then offset 10 may start at J instead of K, causing J to appear a second time.

Conversely, if a row before the offset is deleted, offset 10 may skip a row that originally belonged to the next page.

A stable ORDER BY with a unique key resolves non-determinism when multiple rows share the same sort value, but **does not prevent offset shifting caused by inserts/deletes**.

Drift can be reduced by:

- Using snapshot isolation or a single snapshot transaction for the entire read process if the workload and transaction duration permit.
- Attaching a fixed boundary condition such as `created_at <= :snapshotTime` to exclude data newer than the start time.
- Using cursor/keyset instead of offset when users only move forward through a list.
- Accepting eventual/near-real-time semantics if the UI does not require a consistent snapshot.

Keeping a single transaction open across multiple HTTP requests is usually inappropriate because it holds connections and resources for too long. Choose a consistency model based on business requirements rather than keeping long transactions open by default.

## 7. What Is Keyset Pagination?

Keyset pagination (also called seek pagination) determines the next page based on **the values of the last row already read**, rather than counting how many rows to skip.

Suppose the sort order is:

```sql
order by created_at desc, id desc
```

After the previous page ends at:

```text
created_at = 2026-11-09T10:00:00Z
id = 500
```

The next page fetches rows that come after that position in descending order:

```sql
select id, name, created_at
from product
where active = true
  and (
       created_at < :lastCreatedAt
       or (created_at = :lastCreatedAt and id < :lastId)
  )
order by created_at desc, id desc
limit 20;
```

The database seeks from the last keyset and fetches the next 20 rows. It does not have to skip 200,000 rows like offset 200,000. With appropriate indexes on the filter and sort keys, keyset can maintain more consistent performance as users go deeper into the dataset.

The predicate must match the exact sort order:

- For ASC, use the `>` operator for subsequent positions.
- For DESC, use the `<` operator.
- For multiple columns, compare left to right; only evaluate the next column when preceding columns are equal.
- A unique tie-breaker, usually the primary key, is required.

## 8. Keyset with Multiple Properties and Mixed Directions

Example sort:

```sql
order by priority desc, created_at asc, id asc
```

The cursor consists of `lastPriority`, `lastCreatedAt`, `lastId`. The predicate for rows after the cursor is:

```sql
where priority < :lastPriority
   or (
       priority = :lastPriority
       and created_at > :lastCreatedAt
   )
   or (
       priority = :lastPriority
       and created_at = :lastCreatedAt
       and id > :lastId
   )
```

Each comparison level uses the operator matching that property's direction. This is a common mistake: using the same `<` or `>` sign for every property even when ORDER BY has mixed directions.

For multi-property keysets:

1. The sort order must be deterministic and have a unique tie-breaker.
2. The cursor must contain all required sort values.
3. The predicate must accurately reflect each ASC/DESC direction.
4. Filter conditions must remain consistent across requests.
5. NULLs must be handled explicitly; standard Spring Data keyset scrolling requires sort properties used as the keyset to have non-NULL values.
6. Test cases with many rows sharing identical sort keys as well as start/end boundaries.

Some databases support row-value comparisons such as `(created_at, id) < (?, ?)`, but syntax and optimization capabilities vary. An expanded predicate using AND/OR as shown above is easier to express in portable JPQL.

## 9. Keyset Pagination with JPQL in Spring Data JPA

You can build a seek query manually for a fixed sort order.

Repository example:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.active = true
          and (
              p.createdAt < :lastCreatedAt
              or (
                  p.createdAt = :lastCreatedAt
                  and p.id < :lastId
              )
          )
        order by p.createdAt desc, p.id desc
        """)
    List<Product> findNextActiveProducts(
        @Param("lastCreatedAt") Instant lastCreatedAt,
        @Param("lastId") Long lastId,
        Pageable limit
    );
}
```

This illustrates subsequent pages when a cursor is already available. Fetching the first page requires a separate query without the cursor predicate:

```java
@Query("""
    select p
    from Product p
    where p.active = true
    order by p.createdAt desc, p.id desc
    """)
List<Product> findFirstActiveProducts(Pageable limit);
```

The service only passes Pageable to limit the row count; you should use page number 0 and a fixed page size for the initial query, or use a custom repository with `setMaxResults(limit)` to clearly express that this is a limit rather than a deep offset.

Upon receiving the last page, save `createdAt` and `id` of the last row as the cursor for the next request. Do not take the cursor from the first row if moving forward in the defined order.

The example above assumes `createdAt` is non-NULL and both createdAt/id are ordered DESC. If createdAt is nullable or the sort direction differs, the predicate must be adjusted according to NULL and direction rules. Ensure timestamp values in the cursor preserve the database's precision.

## 10. Spring Data Scroll API and Window

Spring Data versions that support the Scroll API provide the `Window<T>` abstraction, `ScrollPosition`, and repository methods returning Window. This API lets you read results one window at a time and obtain the continuation position from the last element.

Derived query example:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product>
    findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
        ScrollPosition position
    );
}
```

Fetching the first window using keyset:

```java
Window<Product> window =
    repository.findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
        ScrollPosition.keyset()
    );
```

Obtaining the continuation position from the last element:

```java
if (window.hasNext() && !window.isEmpty()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Product> nextWindow =
        repository.findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
            nextPosition
        );
}
```

`ScrollPosition.keyset()` initializes keyset scrolling. `ScrollPosition.offset()` initializes offset-based scrolling through the same abstraction. On each continuation, obtain the position at the last element of the current Window.

The Scroll API depends on the Spring Data Commons/Spring Data JPA version. Support varies by query type; current Spring Data JPA documentation notes limitations with string-based query methods such as `@Query`. Check the documentation for your exact version before designing repositories around the Scroll API. Derived query methods and supported query types are safer choices for this example.

### 10.1. Requirements for Keyset Scrolling

For keyset scrolling to work reliably:

- The sort must be deterministic and unique; if the sort property is not unique, add the ID as a tie-breaker.
- Sort properties must be present in the result/projection so Spring Data can construct the keyset.
- Sort values used as the keyset must be non-NULL as required by keyset scrolling.
- Use valid property paths and comparable data types.
- Keep filters and sorting consistent across calls.
- Create indexes supporting the filters and sort order.

If a query only returns a DTO/projection, ensure the projection includes the properties needed to build the keyset. If a sort property is not selected, the framework may fail to generate the continuation position.

## 11. Offset Scrolling Still Has Its Place

Offset is not always wrong. It is appropriate when:

- Users need to jump directly to page 1, 5, 20, or a specific page number.
- The dataset is not overly large.
- Offsets are generally small and bounded.
- Result counts are needed to display total pages.
- Data changes infrequently while users are browsing.
- Queries have good indexes and measured performance is satisfactory.

Keyset is more suitable when:

- Users only need to load more items.
- There is a feed, activity stream, history, or latest items list.
- A batch job must process millions of records in chunks.
- The dataset is very large and users frequently scroll deep.
- You want to avoid the cost of skipping rows before the cursor.

The trade-off: keyset generally does not support jumping directly to page 10,000 without a dedicated positioning mechanism. It relies on a cursor of the last-read position rather than absolute page numbers.

## 12. Cursor API for Web Applications

Instead of the client sending `page=10000`, a cursor API can return:

```json
{
  "items": [
    {"id": 500, "name": "Product A"}
  ],
  "nextCursor": "opaque-cursor-token",
  "hasNext": true
}
```

The client sends the cursor in the next request:

```http
GET /api/products?limit=20&cursor=opaque-cursor-token
```

The cursor should contain enough information to resume in the exact order:

- The last sort key values, e.g., createdAt.
- The unique tie-breaker, e.g., ID.
- A sort/filter version if the API needs to detect stale cursors.
- A snapshot cutoff if business requirements demand fixing the dataset.

Do not trust cursor contents arbitrarily modified by the client. You can serialize and sign (HMAC) or encrypt it if cursor data integrity or confidentiality is needed. Base64 is only encoding, not encryption or a signature. The cursor should also avoid containing sensitive information unless necessary.

Cap `limit` on the server and validate the cursor before building the query. Never allow the client to send column names, WHERE fragments, or raw SQL directly.

## 13. Impact of Concurrent Insert/Update/Delete on Keyset

Keyset reduces position drift caused by inserts/deletes before the offset, because the next page starts from the cursor value rather than a row count.

However, keyset does not automatically create a consistent snapshot:

- A new row inserted before the cursor may not appear in the stream being traversed in the current direction.
- A row whose sort key is updated can move from behind the cursor to ahead of it or vice versa.
- A row deleted before its turn is reached will no longer be returned.
- Changes in filter membership can cause a row to appear or disappear between requests.

If a point-in-time consistent export is required, you need to design a snapshot/cutoff or a mechanism storing the set of IDs/versions. Keyset efficiently solves page positioning; it does not replace transaction isolation or snapshot semantics.

## 14. Batch Processing and Very Large Datasets

For batch jobs processing millions of rows, do not load all entities into a single List or use an unbounded increasing offset.

A cursor-based processing loop can:

1. Fetch the first chunk by sort key.
2. Process each row or convert it to a DTO.
3. Save the cursor of the last row.
4. Fetch the next chunk using the keyset predicate.
5. Repeat until no rows remain.

Illustrative example:

```java
Instant lastCreatedAt = null;
Long lastId = null;

while (true) {
    List<Product> batch;

    if (lastCreatedAt == null) {
        batch = repository.findFirstActiveProducts(
            PageRequest.of(0, 500)
        );
    } else {
        batch = repository.findNextActiveProducts(
            lastCreatedAt,
            lastId,
            PageRequest.of(0, 500)
        );
    }

    if (batch.isEmpty()) {
        break;
    }

    process(batch);

    Product last = batch.get(batch.size() - 1);
    lastCreatedAt = last.getCreatedAt();
    lastId = last.getId();
}
```

This is an illustrative skeleton; ensure the initial query and subsequent queries use the same filters/sorting, that createdAt is non-NULL, and that batch processing has proper transaction/retry/idempotency handling. If processing can fail mid-way, persist the cursor only after the batch has been successfully processed and committed to avoid skipping records.

For large entities, consider DTO projections to reduce memory usage and persistence context overhead. If using a Stream from a repository, you must manage transactions and close the stream properly; Stream does not automatically mean keyset pagination and may keep connections/cursors open throughout traversal.

## 15. Native Queries, JOINs, and Count Queries

Offset pagination can be used with native SQL, but pay attention to:

- Databases may have different LIMIT/OFFSET syntax.
- Native queries returning Page usually need a separate countQuery to count accurately.
- Collection JOINs can produce multiple SQL rows per parent entity; direct pagination may return fewer actual entities than the page size or introduce duplicates.
- DISTINCT and GROUP BY make count queries more complex.
- Dynamic Sort on native queries has limitations depending on the parser and Spring Data version.

With keyset, native SQL can express predicates very clearly and leverage row-value comparisons if the database supports them. In return, queries and cursors are more tightly coupled to the database. Test both the data query and the count query on the production engine.

## 16. Index Design for Keyset

Suppose the query is:

```sql
select id, created_at, name
from product
where tenant_id = ?
  and active = true
  and (
      created_at < ?
      or (created_at = ? and id < ?)
  )
order by created_at desc, id desc
limit 50;
```

A candidate index:

```sql
create index ix_product_tenant_active_created_id
on product(tenant_id, active, created_at desc, id desc);
```

Principles:

- Put selective equality predicates at the start of the index when appropriate.
- Follow with the sort/keyset columns.
- Place the unique tie-breaker at the end.
- Verify the index types and scan directions supported by the database.
- Avoid overly wide indexes if write cost and storage size are significant.
- Measure against realistic data distributions; optimal index ordering cannot be deduced from the SQL statement alone.

With multi-property keysets and dynamic filters, multiple indexes may be needed for different query shapes. Do not try to create a single index to serve every filter/sort combination.

## 17. Comparing Offset, Slice, and Keyset

| Criterion | Page + Offset | Slice + Offset | Keyset/Cursor |
|---|---|---|---|
| Page positioning | Page number | Page number | Cursor value |
| Jump to any page | Yes | Yes | Not directly |
| Total count | Available | Not needed | Usually not available |
| Very deep page cost | Can grow sharply | Still grows due to offset | Usually more stable with proper indexes |
| Data changes between requests | Can drift | Can drift | Less offset shift, but not a snapshot |
| Stable sort | Needed | Needed | Mandatory, including unique tie-breaker |
| Suitable API | Numbered table pages | Simple "Load more" | Feeds, infinite scroll, large batches |
| Implementation complexity | Low | Low | Higher; requires cursor/predicate |
| Random access support | Good | Good | Limited |

Slice eliminates the count query but does not change how the database skips the offset. Keyset changes how pages are positioned, thereby addressing a core limitation of deep offsets.

## 18. Process for Migrating from Offset to Keyset

Do not switch merely because you heard keyset is faster. Follow these steps:

1. Measure the current query on the first page, middle pages, and very deep pages.
2. Inspect the SQL, count query, and execution plan.
3. Define a stable sort order; add the primary key as a tie-breaker.
4. Check whether sort keys can be NULL and define handling rules.
5. Design a cursor containing all required sort key values.
6. Write the keyset predicate accurately for each direction.
7. Create/adjust indexes to match the filters and sort order.
8. Test duplicate sort keys, concurrent inserts/deletes/updates, and expired cursors.
9. Compare latency, rows read, CPU, I/O, and connection usage.
10. Switch the API from page number to nextCursor if UX does not require jumping between pages.

If the product needs both random access and load-more navigation, you can keep offset for initial pages and use keyset for the "load more" flow, but you must unify semantics and prevent clients from switching back and forth in ways that cause duplicates or missed rows.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| First page fast but deep pages slow | Large offset forces database to skip many rows | Switch to keyset or cap depth |
| Slice still slow on deep pages | Slice skips count but still uses offset | Use keyset/cursor |
| Duplicate rows across two pages | Insert/delete before offset or non-unique ORDER BY | Add tie-breaker; use cursor if appropriate |
| Skipped rows | Offset shifts when data is deleted/inserted | Keyset or business-level snapshot/cutoff |
| Unstable ordering | Sort keys have duplicate values without unique tie-breaker | Add ID/unique key at the end of ORDER BY |
| Keyset misses rows with same timestamp | Predicate only compares timestamp, missing ID condition | Use lexicographic predicate including all sort keys |
| Keyset returns wrong rows with mixed directions | Using the same comparison sign for all properties | Build predicate per ASC/DESC direction |
| Keyset fails with NULLs | Nullable sort key | Normalize/define non-NULL or use a different query strategy |
| Slow count query | Page requires total result count | Use Slice if total is unneeded or optimize count separately |
| Query with JOIN returns fewer entities | Collection JOIN duplicates rows before pagination | Paginate IDs first then fetch associations; check DISTINCT |
| Batch job consumes excessive memory | Loading too many entities at once | Small chunks, DTOs, and control PersistenceContext |
| Cursor tampered with by client | Trusting unvalidated cursor data | Sign/validate tokens and whitelist filters/sorts |
| Keyset still slow | Index does not support filters/sort or complex predicate | Check execution plan and indexes |

## 20. Pagination Selection Checklist

- [ ] Do users need to jump directly to an arbitrary page?
- [ ] How large is the data expected to grow, and what is the typical page depth?
- [ ] Is the page count truly required by the UI?
- [ ] Is Slice sufficient if only knowing whether more data exists is needed?
- [ ] Does ORDER BY have a unique tie-breaker?
- [ ] Can data change between requests?
- [ ] Is a consistent snapshot required for export/batch?
- [ ] Are keyset sort properties non-NULL?
- [ ] Does the cursor contain all sort keys and is it validated?
- [ ] Do indexes support filters + ORDER BY + keyset predicate?
- [ ] Does the query have collection JOINs that duplicate rows?
- [ ] Have first/deep pages been measured and EXPLAIN inspected?
- [ ] Are Page, Slice, Window, and Scroll API supported by the current Spring Data JPA version?

## 21. Conclusion

Offset pagination is simple and useful when page numbers, direct page jumping, and moderately sized datasets are involved. However, deep offsets can force the database to scan or skip huge numbers of rows before returning a small page; Page can also incur expensive count queries. Slice drops the count query but retains the offset cost.

When data is large and the access flow is primarily forward traversal, keyset/cursor pagination is usually a better fit. It relies on the last sort key values, uses a predicate to locate the next elements, and can leverage indexes. To be correct, it requires a deterministic ORDER BY with a unique tie-breaker, a complete cursor, predicates matching each direction, and appropriate indexes. Keyset improves page positioning but does not automatically create a consistent snapshot; if data changes heavily or exports need a point-in-time state, design consistency explicitly.

Measure real queries before switching. Keep offset for reasonably sized random-access needs; use keyset for feeds, infinite loading, and large batches when it aligns with UX and consistency requirements.
