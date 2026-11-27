# The Window, ScrollPosition, and Scrolling Query Model

Spring Data provides the Scroll API to read a large result set in small portions. Instead of loading all data into memory or asking the database to skip an ever-growing offset, the application fetches a Window<T>, processes the elements in that window, and then uses ScrollPosition to request the next window.

Three concepts to understand are:

- **Window<T>:** a bounded group of results containing information to continue scrolling.
- **ScrollPosition:** the position used to start or resume reading results.
- **Scrolling query:** a Repository method capable of accepting a ScrollPosition and returning a Window<T>.

Spring Data supports scrolling by offset and by keyset. Offset is easy to understand and close to pagination; keyset uses the sort values of the last element to continue querying and is usually better suited for large datasets. The choice of scrolling mode, sort order, and supported query type directly affects correctness and performance.

## 1. What Problem Does Scrolling Solve?

Suppose a table has several million records and a task needs to process all records in batches of 500 elements. Calling findAll() may load the entire result set into memory, putting pressure on the heap and garbage collection.

You could use Pageable to fetch each Page, but Page typically requires the total element count to provide totalElements and totalPages. The count query can be expensive, while a batch task only needs to fetch the next chunk of data.

Scrolling provides a way to read in Window chunks without requiring the total result count. Each query fetches only a finite portion and returns a position that can be used to continue.

| Reading approach | Characteristics |
|---|---|
| findAll() | May load the entire result set into memory |
| Page<T> | Contains page content and total count; may require a count query |
| Slice<T> | Contains content and whether a next page exists, no total count needed |
| Window<T> | Contains a window of results along with a position to continue scrolling |
| Stream<T> | Returns a result stream; tied to query resources and must be closed properly |

Window is not a JDBC Stream and does not by itself guarantee that the database/driver will not buffer data. It is an abstraction for fetching results in bounded windows. The application processes each Window and then requests the next Window.

## 2. What Is Window<T>?

Window<T> represents a slice of query results. T is the type of each element, typically an Entity or projection returned by the query.

A Window provides key operations:

- Iterating over the elements in the window.
- Checking whether the window is empty.
- Checking whether more results follow.
- Obtaining a ScrollPosition at an element via positionAt(index).
- Using the last element's position to request the next window.

Repository signature example:

~~~java
Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
        ScrollPosition position
);
~~~

This method returns up to 100 active Products, sorted by ID ascending, starting from the passed position.

Window does not provide totalElements or totalPages like Page does. Therefore, if the UI needs to display the exact total number of records or pages, Page may be more appropriate. If the task only needs to keep processing until data is exhausted, Window is usually a better fit.

## 3. How Does ScrollPosition Represent a Position?

ScrollPosition identifies a point in the overall query results so the application can start or resume reading. There are two main position types:

- OffsetScrollPosition: stores the position by the number of skipped elements.
- KeysetScrollPosition: stores the sort key values of the last-read element.

Common factory methods:

~~~java
ScrollPosition.offset()
ScrollPosition.keyset()
~~~

These two methods create the initial position for each scrolling mode. After receiving a Window, the application obtains the position of the processed element using:

~~~java
ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);
~~~

The position follows **exclusive** semantics: the next query starts after the element at the passed position. Therefore, take the position of the last element in the current Window so the last element is not read again.

Do not manually add or subtract indices if you are using positionAt(). The API creates the ScrollPosition appropriate for the active scrolling mode.

## 4. Repository Queries Supporting Scrolling

Spring Data JPA supports the Scroll API with supported query method types, especially derived query methods. A scrolling method typically has:

- Return type Window<T>.
- A ScrollPosition parameter to specify the starting point.
- Result limiting via First or Top, or a limit supported by the query API.
- A stable sort order.

Example:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
            ScrollPosition position
    );
}
~~~

The method name expresses:
- find: query data.
- First100: limit each Window to at most 100 results.
- ByActiveTrue: fetch only active Products.
- OrderByIdAsc: sort by ID ascending.

When calling the method for the first time, pass the initial position. On subsequent calls, pass the position obtained from the previous Window.

This example uses a derived query. Ensure the property names active and id match the actual Entity.

## 5. Manually Scrolling Through Windows

You can control the loop directly to clearly see how ScrollPosition is updated.

~~~java
ScrollPosition position = ScrollPosition.offset();

Window<Product> window =
        productRepository.findFirst100ByActiveTrueOrderByIdAsc(position);

while (!window.isEmpty()) {
    for (Product product : window) {
        process(product);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);

    window = productRepository
            .findFirst100ByActiveTrueOrderByIdAsc(position);
}
~~~

Execution flow:

1. Start with the initial ScrollPosition.
2. Repository returns the first Window.
3. The application processes all Products in the Window.
4. If no more elements follow, the loop ends.
5. If more data exists, obtain the position of the last element.
6. Call the Repository again with the new position to receive the next Window.

It is important to advance the position only after finishing the current Window. Advancing from an element in the middle of the window would skip the remaining elements.

If per-element processing can fail, you need to design checkpoint persistence and retry logic per business requirements. ScrollPosition does not automatically persist long-term progress for the application.

## 6. WindowIterator Simplifies the Loop

WindowIterator is a Spring Data Commons utility for continuously iterating across multiple Windows. It automatically obtains the next position, saving code from manually writing window checks and ScrollPosition updates.

Example:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Product> iterator =
        WindowIterator.of(position ->
                productRepository
                    .findFirst100ByActiveTrueOrderByIdAsc(position)
        ).startingAt(ScrollPosition.offset());

while (iterator.hasNext()) {
    Product product = iterator.next();
    process(product);
}
~~~

Explanation:

- WindowIterator.of(...) accepts a query function to which Spring Data passes ScrollPosition for each Window fetch.
- startingAt(...) specifies the starting position.
- hasNext() checks whether there are remaining elements to read.
- next() retrieves the next element across Windows.

WindowIterator is convenient when processing each Entity sequentially. If you need batch processing, checkpoint saving, per-Window logging, or batch-level transaction control, a manual loop can be easier to customize.

Do not invoke the iterator multiple times for the same task if doing so causes unintended query re-execution. Create the iterator once and consume it within the lifecycle of the job.

## 7. Offset-Based Scrolling

Offset scrolling uses an integer representing a position in the sorted results. The database is instructed to skip a number of rows and return the next portion.

Example:

~~~java
Window<Product> findFirst100ByActiveTrueOrderByIdAsc(
        ScrollPosition position
);
~~~

Starting:

~~~java
Window<Product> first =
        productRepository.findFirst100ByActiveTrueOrderByIdAsc(
                ScrollPosition.offset()
        );
~~~

Offset is simple because it closely mirrors SQL LIMIT/OFFSET. However, as the offset grows very large, the database typically has to identify and skip many rows before returning the needed results. Consequently, deep windows can become progressively slower.

### Distinguishing offset() and offset(0)

These two values do not mean the same thing:

- ScrollPosition.offset() represents starting from the beginning of the query, not yet pointing to a specific element.
- ScrollPosition.offset(0) points to the element at position 0.

ScrollPosition is exclusive. Therefore, if you pass offset(0), the next query starts after the first element and may skip that element.

To fetch results from the very beginning, use:

~~~java
ScrollPosition.offset()
~~~

Do not use offset(0) as the starting position if you want to receive the first element as well.

## 8. Keyset-Based Scrolling

Keyset scrolling continues querying based on the sort values of the last element in the current Window, instead of counting how many rows to skip.

Suppose the results are sorted:

~~~sql
ORDER BY created_at ASC, id ASC
~~~

After reading the last element with created_at = timestamp T and id = 500, the next query can be logically written as:

~~~sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at ASC, id ASC
LIMIT 100
~~~

This is a lexicographic keyset condition. Spring Data constructs the continuation predicate based on the key values stored in ScrollPosition.

Keyset allows the database to seek records after the last-read position via a suitable index, avoiding the cost of skipping a huge offset. It is a strong choice when sequentially reading a large dataset.

## 9. Starting Keyset Scrolling

Repository example:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product>
    findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(
            ScrollPosition position
    );
}
~~~

Starting from the beginning:

~~~java
Window<Product> window =
        productRepository
            .findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(
                ScrollPosition.keyset()
            );
~~~

Or using WindowIterator:

~~~java
WindowIterator<Product> products =
        WindowIterator.of(position ->
            productRepository
                .findFirst100ByActiveTrueOrderByCreatedAtAscIdAsc(position)
        ).startingAt(ScrollPosition.keyset());

while (products.hasNext()) {
    process(products.next());
}
~~~

The order must be stable and well-defined. If multiple Products share the same createdAt, ID provides a secondary criterion to establish a unique order. The Spring Data keyset mechanism also appends the primary key (or remaining components of a composite primary key) to ensure positions can be uniquely identified.

Even so, explicitly declaring the tie-breaker in the sort usually helps readers understand the order and makes index design easier.

## 10. Requirements for Keyset Scrolling to Work Properly

Keyset requires sort properties to have deterministic values:

- Sort properties should be non-null.
- Query results must return the properties used for sorting.
- The primary key must be present to distinguish elements sharing the same sort value.
- The sort order must remain stable throughout scrolling.
- The database should have indexes matching the filter predicates and sort order.

Spring Data needs the sort values of the last element to build the next ScrollPosition. If a projection omits a sort property, the framework cannot extract the complete keyset and may throw an error or fail to continue scrolling.

Example projection retaining sort fields:

~~~java
public interface ProductScrollView {
    Long getId();
    Instant getCreatedAt();
    String getName();
}
~~~

If the query sorts by createdAt and id, the projection must include both createdAt and id. You do not have to expose these fields to end users, but they must be present in the query result to construct the keyset position.

### Avoiding Nullable Sort Properties

Keyset filtering relies on comparison operators such as greater than, less than, and equal to. NULL has special semantics in SQL and NULL ordering can vary across databases. Therefore, Spring Data requires keyset properties to be non-nullable to avoid non-deterministic continuation results.

If a business field can be null, choose another non-null sort field or normalize the data and mapping according to a clear rule before using keyset.

## 11. Index Design for Keyset

Keyset performs well when the database has an index matching the sort order and filter predicates.

Example query:

~~~sql
WHERE active = true
ORDER BY created_at ASC, id ASC
LIMIT 100
~~~

A composite index can be considered:

~~~sql
CREATE INDEX idx_products_active_created_id
ON products (active, created_at, id);
~~~

This index illustrates a column order matching the active filter predicate and the sort columns. The actual optimal index structure also depends on the database, selectivity, other filter predicates, and write workload.

If queries always filter by tenant_id first, the index may need to start with tenant_id. If sorting in descending order or with other conditions, check the database's index usage capabilities.

Use EXPLAIN or EXPLAIN ANALYZE to inspect:
- Is the expected index being used?
- How many rows need to be read before returning the Window?
- Is there a large sort step?
- Is the cost of the first Window and deep Windows consistent?

Do not create indexes solely based on method names. Measure on data and a database close to production.

## 12. Which Queries Support the Scroll API in Spring Data JPA?

According to current Spring Data JPA documentation, the Scroll API can be used with:

- **Query methods:** supported query methods, such as derived queries accepting ScrollPosition and returning Window<T>.
- **Query by Example (QBE):** can use the fluent API and the terminal operation scroll(position).
- **Querydsl:** can use the scrolling API when the repository supports Querydsl.

The derived query example was shown above. With Query by Example, the idea is to call a fluent query:

~~~java
Window<Customer> window = customerRepository.findBy(
        Example.of(probe),
        query -> query.scroll(ScrollPosition.offset())
);
~~~

Exact syntax depends on the repository type and Spring Data Commons/JPA version. The terminal operation scroll() returns Window<T> and accepts ScrollPosition.

### Limitations with @Query and String-Based Queries

Current Spring Data JPA documentation explicitly states that scrolling with string-based query methods is not yet supported. This includes methods declaring queries via strings such as @Query; stored @Procedure query methods also do not support the Scroll API according to that documentation.

Therefore, do not assume you can write:

~~~java
@Query("select p from Product p where p.active = true")
Window<Product> findActiveProducts(ScrollPosition position);
~~~

and expect every version of Spring Data JPA to handle scrolling automatically. Check the documentation for your exact dependency version. If complex conditions are required, consider an appropriate derived query, Query by Example, Querydsl, or a custom repository using Criteria API/EntityManager while managing limits, ordering, and cursors yourself.

Scrolling capabilities vary by Spring Data version. The Scroll API was introduced in the Spring Data 3.1 line; verify the actual Spring Boot BOM and Spring Data JPA versions in your project before adopting it.

## 13. Scrolling with Projections

You can return projections instead of full Entities to load only the required fields. This is useful when processing large datasets where the task only needs a few properties.

Example:

~~~java
public interface ProductExportRow {
    Long getId();
    Instant getCreatedAt();
    String getName();
}
~~~

A query method can return Window<ProductExportRow> if the query type and projection are supported:

~~~java
Window<ProductExportRow>
findFirst200ByActiveTrueOrderByCreatedAtAscIdAsc(
        ScrollPosition position
);
~~~

With keyset scrolling, include all sort properties in the projection. In this example, both createdAt and id are present. If only name is returned while omitting createdAt or ID, the framework may fail to generate the next keyset.

Projections reduce the columns read and Entity hydration overhead, though you still need to inspect the actual SQL and projection mapping on your provider.

## 14. Scrolling and Concurrently Changing Data

ScrollPosition does not automatically create an immutable snapshot of the entire result set. If data changes while the application is scrolling, results can be affected.

### Offset Scrolling

If new records are inserted before the current offset, row number positions can shift. The application may read some records twice or skip others. Deleting data before the position can also shift the offset.

### Keyset Scrolling

Keyset relies less on skipped row counts, but can still be affected if:
- A record's sort value changes during scrolling.
- Records are inserted before or after the current keyset.
- Records are deleted before being read.
- Filter conditions change over time.

To mitigate risks:
- Use stable, rarely changing sort fields.
- Use ID as a tie-breaker.
- If business logic requires a consistent snapshot, choose an appropriate transaction isolation or snapshot strategy.
- For long exports/batches, consider bounding the dataset by a point in time or a high-water mark.
- Design idempotent processing if retries occur.

Do not assume scrolling automatically guarantees exactly-once processing when data is changing or a process stops mid-way.

## 15. Distinguishing Scrolling from Stream<T>

The term scrolling can easily be confused with Java Stream. The two abstractions serve different purposes and lifecycles.

| Criterion | Window<T> scrolling | Stream<T> |
|---|---|---|
| Reading unit | A bounded window | A stream of elements |
| Continuation mechanism | ScrollPosition | Continuing to consume the stream |
| Resource management | Each Window fetch is a separate query | May hold JDBC/cursor resources open during streaming |
| Resource closing | Window is an already-fetched result set | Stream must be closed |
| Used for | Chunking results and resuming via cursor | Stream processing within a transaction/resource scope |

Example using Stream:

~~~java
@Transactional(readOnly = true)
public void processAllProducts() {
    try (Stream<Product> products = repository.streamAllByActiveTrue()) {
        products.forEach(this::process);
    }
}
~~~

The repository method must be declared to return Stream<Product> and the provider must support it properly. Stream is typically tied to persistence/JDBC resources; it must be closed with try-with-resources and consumed inside an appropriate transaction.

Window scrolling fetches data in separate batches. After finishing one Window, the application requests the next Window. It is a good fit when explicit checkpoints or per-batch transaction control are needed.

Do not treat Window as a continuously open JDBC cursor, and do not treat Stream as a complete replacement for keyset pagination.

## 16. Choosing Offset or Keyset?

| Criterion | Offset scrolling | Keyset scrolling |
|---|---|---|
| Continuation position | Number of skipped rows | Sort field values of the last row |
| Simplicity | Easy to understand and implement | Requires stable sort and valid keyset |
| Deep windows | Can be slow due to large offsets | Usually more stable with suitable indexes |
| Index requirement | Helpful but not the core requirement | Crucial for efficiency |
| Nullable properties | Offset lacks the same keyset constraint | Sort properties must be non-null |
| Projection | Fewer constraints | Must contain sort fields and ID |
| Concurrent data changes | Offset easily shifts | Less sensitive to inserts/deletes before position, though mutable sort keys still pose risks |

Choose offset when:
- The dataset is not overly large.
- A simple implementation is desired.
- Offsets do not grow excessively deep.
- Ordering and data change rarely during reading.

Choose keyset when:
- Sequential scrolling through a large dataset is needed.
- Stable, non-null sort keys are available.
- Appropriate indexes can be created.
- Jumping to an arbitrary page number is not required.

If arbitrary navigation to page 1000 is needed, offset may fit the UX even though the cost can be high. Keyset fits "next" flows and sequential processing better.

## 17. Testing Scrolling Queries

You should test the following scenarios:

1. The first Window starts accurately from the first element.
2. The next Window starts after the last element of the previous Window.
3. No elements are duplicated or skipped when data is stable.
4. The final Window has hasNext() equal to false.
5. A query with no matching data returns an empty Window.
6. Initial offset uses ScrollPosition.offset(), not offset(0) when intending to fetch the first element.
7. Keyset sort has non-null values and a deterministic order.
8. Projections include all sort properties and ID.
9. The query method used is supported by the Spring Data JPA version.
10. Indexes and execution plans are verified on the target database.

Conceptual test example using offset:

~~~java
@Test
void scrollingReadsAllProductsWithoutDuplicates() {
    List<Long> ids = new ArrayList<>();

    Window<Product> window =
            repository.findFirst2ByActiveTrueOrderByIdAsc(
                    ScrollPosition.offset()
            );

    while (!window.isEmpty()) {
        window.forEach(product -> ids.add(product.getId()));

        if (!window.hasNext()) {
            break;
        }

        window = repository.findFirst2ByActiveTrueOrderByIdAsc(
                window.positionAt(window.size() - 1)
        );
    }

    assertEquals(List.of(1L, 2L, 3L, 4L, 5L), ids);
}
~~~

Expected output in a fixture with five active Products having IDs 1 through 5:

~~~text
[1, 2, 3, 4, 5]
~~~

This is an illustrative test. In a real project, set up fixture data, verify IDs in order, and ensure no other data alters the results. Integration tests can be run against a real database to verify keyset behavior, index usage, and generated SQL.

## 18. Common Pitfalls

**Using offset(0) to start from the beginning**

Because positions are exclusive, the element at offset 0 may be skipped. Use ScrollPosition.offset() to start.

**Taking the position from the first element instead of the last**

The next Window will start too early and may duplicate data. Use positionAt(window.size() - 1).

**Forgetting to check hasNext()**

You may continue querying even after data is exhausted or handle loop termination improperly. Check Window state before requesting the next window.

**Using an unstable sort**

Multiple records sharing the same sort value without a tie-breaker can make ordering non-deterministic. Use ID as a secondary criterion.

**Using keyset on nullable fields**

NULL comparison semantics vary across databases. Choose non-null sort keys and verify the data.

**Projections omitting sort fields**

Spring Data cannot extract the full keyset. Include all sort properties and ID in the projection.

**Assuming @Query always supports scrolling**

String-based query methods are not yet supported according to current Spring Data JPA documentation. Check your version and use supported query mechanisms.

**Using very deep offsets for large batches**

The database may have to skip many rows. Consider keyset and appropriate indexes.

**Confusing Window with Stream**

Window represents individual result chunks; Stream has a resource lifecycle and must be closed properly.

**Assuming ScrollPosition persists checkpoints automatically**

ScrollPosition only represents a position. If resumption after a restart is required, the application must persist checkpoints safely along with the corresponding query/sort/filter metadata.

## 19. Process for Designing a Scrolling Query

When building a large-data reading feature, follow these steps:

1. Determine whether sequential results are sufficient or an exact total count is needed.
2. Choose Window over Page if totalElements is not needed.
3. Choose offset for simple flows or keyset for large datasets with suitable indexes.
4. Define a stable sort with a unique tie-breaker.
5. Create a derived query method returning Window<T> and accepting ScrollPosition.
6. Verify whether the query style is supported by your Spring Data JPA version.
7. For keyset, ensure sort properties are non-null and present in the projection.
8. Use WindowIterator for simple sequential iteration; use a manual loop if batching/checkpointing is needed.
9. Define how to handle concurrently changing data and batch retries.
10. Measure SQL, execution plans, indexes, heap, and processing time on production-like data.
11. Write integration tests verifying no duplicates, no missed records, and proper termination on the final Window.

## 20. Conclusion

Window<T> is a bounded group of results used to scroll through large datasets; ScrollPosition specifies the start or continuation point. OffsetScrollPosition relies on skipped row counts, while KeysetScrollPosition relies on the sort values of the last element and is usually better suited for large sequential queries with good indexes. Use positionAt() on the last element to continue, or WindowIterator to simplify the loop. Keyset requires a stable sort, non-null sort properties, and projections containing all keys. In Spring Data JPA, derived query methods, Query by Example, and Querydsl support scrolling per current documentation; string-based @Query and stored @Procedure are not yet supported. Always check your Spring Data version, generated SQL, and actual execution plans before deploying.

## References

- [Spring Data JPA Reference — Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.scrolling)
- [Spring Data Commons API — ScrollPosition](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data Commons API — KeysetScrollPosition](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/domain/KeysetScrollPosition.html)
