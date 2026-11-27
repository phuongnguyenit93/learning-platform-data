# findAll, findAllById, and Limits When Reading Large Datasets

Spring Data JPA provides findAll() to read all entities managed by a repository and findAllById(Iterable<ID>) to read entities whose IDs are in an input set. Both methods are convenient for ordinary CRUD, but can cause high memory usage, excessive SQL, or slowness on large datasets.

When designing read flows, you need to know exactly what each method returns, whether order is guaranteed, how nonexistent IDs are handled, and when entities become managed in the persistence context. For large datasets, choose pagination, Slice, projections, streaming, or keyset pagination according to actual needs.

This lesson uses Spring Data JPA 3.x and Spring Boot 3.x. Repository examples extend JpaRepository.

## 1. What Does findAll() Read?

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Call:

```java
List<Customer> customers = customerRepository.findAll();
```

findAll() returns a list of all entities visible to the repository's query based on its mappings and any active filters. With JpaRepository in Spring Data 3.x, the return type is List<T>. When using CrudRepository in older versions/APIs, the base contract may return Iterable<T>; check the interface your repository extends.

This method does not accept Pageable, so it does not limit the number of records. If a table has tens of thousands or millions of rows, the entire result may be loaded into application memory. Entities loaded within a transaction are typically managed by the persistence context, adding further memory and dirty checking overhead.

findAll() is appropriate when:

- The table is small and data growth is bounded.
- An admin tool needs to display an entire small list.
- Configuration data has a small number of entries.
- A test or simple task needs a small dataset.

Do not call findAll() in list APIs that can grow unbounded, large-scale data synchronization tasks, or scheduled jobs running over large transaction tables.

## 2. findAll(Sort) and Result Ordering

findAll() does not guarantee record order. If business logic requires a stable order, pass Sort:

```java
List<Customer> customers = customerRepository.findAll(
    Sort.by(Sort.Direction.ASC, "id")
);
```

Property names in Sort are Java properties on the entity, such as id, createdAt, or name. Do not pass SQL column names if the property name differs from the column name.

Sorting by a non-unique property can produce an unstable order among records sharing the same value. When paginating or batch processing, append a unique key as the final tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
);
```

Ordering by createdAt then id distinguishes records with the same creation timestamp. However, findAll(Sort) still loads the entire list; Sort only changes ordering, not record count or memory usage.

## 3. How Does findAllById() Work?

findAllById accepts an Iterable of IDs and returns entities with matching IDs:

```java
List<Long> ids = List.of(10L, 20L, 30L);

List<Customer> customers =
        customerRepository.findAllById(ids);
```

With JpaRepository in Spring Data 3.x, the result is List<T>. Nonexistent IDs are skipped; the method neither creates placeholders nor throws an error just because an ID is missing.

For example, if the database only has customers 10 and 30, calling it with 10, 20, 30 returns two entities corresponding to 10 and 30.

**There is no guarantee that the result preserves the order of the input Iterable.** Do not write code assuming the first element in the result always corresponds to the first ID passed. If exact input order is required, re-sort after querying or use a query with an appropriate ORDER BY.

```java
List<Long> requestedIds = List.of(30L, 10L, 20L);

List<Customer> found =
        customerRepository.findAllById(requestedIds);

Map<Long, Customer> byId = found.stream()
        .collect(Collectors.toMap(Customer::getId, Function.identity()));

List<Customer> inRequestedOrder = requestedIds.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
```

The example above preserves the input list's order and skips nonexistent IDs. If the input contains duplicate IDs, the reordered result will also repeat the corresponding entity for each occurrence in the requested list. If business logic does not want duplicates, normalize the input into a unique ID set before querying.

## 4. findAllById Is Not a Paginated Query

findAllById only accepts a set of IDs; it does not accept Pageable or Sort. When passing a large set of IDs, the provider usually has to construct a query filtering by those IDs, such as IN (...). Depending on the provider and database, you may hit bind parameter count limits, SQL length limits, or query parsing overhead.

Example to avoid—passing hundreds of thousands of IDs at once:

```java
List<Long> allIds = loadAllIdsFromExternalSource();

List<Customer> customers =
        customerRepository.findAllById(allIds);
```

The solution is to split the input into small batches and process each batch:

```java
public void processIds(List<Long> ids) {
    int batchSize = 500;

    for (int start = 0; start < ids.size(); start += batchSize) {
        int end = Math.min(start + batchSize, ids.size());

        List<Long> batchIds = ids.subList(start, end);

        List<Customer> batch =
                customerRepository.findAllById(batchIds);

        processBatch(batch);
    }
}
```

500 is only an illustrative value. Choose batch size based on database bind parameter limits, SQL length, driver behavior, and data volume per entity. Some providers may handle collection parameters differently; observe actual SQL and test on the target database.

Splitting input into batches limits the number of IDs in each query. If processBatch retains all entities in a large collection, total memory can still grow with the full dataset size. Process each batch and release references if they do not need to be retained.

## 5. findAllById Can Return Partial Data Without Error

Per the method contract, nonexistent IDs are skipped. Therefore, if business logic requires every input ID to exist, the application must check manually:

```java
List<Long> requestedIds = List.of(10L, 20L, 30L);

List<Customer> found =
        customerRepository.findAllById(requestedIds);

Set<Long> foundIds = found.stream()
        .map(Customer::getId)
        .collect(Collectors.toSet());

List<Long> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .distinct()
        .toList();

if (!missingIds.isEmpty()) {
    throw new IllegalArgumentException(
        "Customers not found: " + missingIds
    );
}
```

This works well when the ID list is moderately sized. For very large inputs, check per batch and aggregate missing counts/IDs according to business requirements, avoiding holding a huge set of entities in memory solely for validation.

If the input IDs come from a user request, also check access permissions. Existence in the database does not mean the caller is authorized to read that entity.

## 6. Why Does Reading All Entities Consume So Much Memory?

When calling findAll(), the application may have to hold simultaneously:

1. A list of references to every entity.
2. The loaded object graph of each entity.
3. Management state in the persistence context.
4. Collections/associations loaded eagerly or accessed during processing.
5. Temporary memory for query results, DTOs, or subsequent transformation steps.

An entity with a few simple fields can be quite small, but a large list with relationships and collections can consume far more memory than expected. If code invokes getters on LAZY relationships for each entity, it can also trigger N+1 queries.

@Transactional(readOnly = true) can help the provider/transaction manager optimize certain read operations, but it does not turn findAll() into streaming and does not guarantee entities are excluded from the persistence context.

Do not solve memory issues merely by increasing heap size. Reduce the number of records read at once, choose projections, and control the persistence context lifecycle.

## 7. Using Pageable When Pagination Is Needed

JpaRepository supports findAll(Pageable):

```java
Pageable pageable = PageRequest.of(
    0,
    100,
    Sort.by(Sort.Direction.ASC, "id")
);

Page<Customer> page =
        customerRepository.findAll(pageable);
```

PageRequest.of(pageNumber, pageSize, sort) uses zero-based page numbers. The example above fetches the first page with up to 100 entities, sorted by id ascending.

Useful information on Page:

- getContent(): list of entities on the current page.
- getNumber(): current page number.
- getSize(): requested page size.
- getNumberOfElements(): actual number of elements on the page.
- getTotalElements(): total number of matching records.
- getTotalPages(): total number of pages.
- hasNext(): whether a next page exists.

API example returning DTOs:

```java
Page<CustomerResponse> response = customerRepository
        .findAll(pageable)
        .map(customer -> new CustomerResponse(
            customer.getId(),
            customer.getName()
        ));
```

map() converts page contents to DTOs while preserving pagination metadata. Do not return entities directly if the API only needs a few fields, as serialization can access lazy relationships, causing N+1 queries or errors outside a transaction.

Page typically requires an extra count query to compute total elements. For large tables and complex filters, the count query can be significantly expensive.

## 8. Using Slice When Total Record Count Is Not Needed

If the UI only needs to know whether there is a next page, use Slice:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Slice<Customer> findByActiveTrue(Pageable pageable);
}
```

Service:

```java
Slice<Customer> slice = customerRepository.findByActiveTrue(
    PageRequest.of(
        0,
        100,
        Sort.by(Sort.Direction.ASC, "id")
    )
);

List<Customer> content = slice.getContent();
boolean hasNext = slice.hasNext();
```

Slice typically fetches one extra element to determine whether more data follows, avoiding counting the entire result set like Page. This is a useful choice for "Load more" buttons or infinite-scroll lists.

Page is appropriate when the UI needs total record count and page count. Slice is appropriate when only current content and a continuation signal are needed. Both limit the number of entities read per call.

## 9. Offset Pagination Has Limitations at Deep Pages

PageRequest uses offset pagination. Early pages have small offsets; when users jump to very deep pages, the database may have to skip a huge number of rows before returning results.

Example:

```java
Pageable deepPage = PageRequest.of(
    10000,
    100,
    Sort.by(Sort.Direction.ASC, "id")
);
```

This page's offset is 1,000,000 rows. Even if the database has an index, skipping a massive number of rows can still be costly. When data is continuously inserted or deleted, offset pagination can also cause records to be duplicated or skipped across page fetches.

For large lists, consider keyset/seek pagination: instead of asking to "skip one million rows", ask to "fetch rows with a key greater than the last key read". A stable sort order and supporting index are required.

## 10. Keyset Pagination Using a Stable Key

Suppose a Customer table has an ascending id. You can fetch subsequent batches:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findTop500ByIdGreaterThanOrderByIdAsc(Long lastId);
}
```

Processing flow:

```java
@Transactional(readOnly = true)
public void processAllCustomers() {
    Long lastId = 0L;

    while (true) {
        List<Customer> batch =
                repository.findTop500ByIdGreaterThanOrderByIdAsc(lastId);

        if (batch.isEmpty()) {
            break;
        }

        processBatch(batch);

        lastId = batch.get(batch.size() - 1).getId();
    }
}
```

Each query starts after the last ID of the previous batch. The database can utilize the primary key index and avoid skipping an ever-growing offset.

The example assumes positive IDs and data ordered by ascending ID. With random UUIDs or non-unique sort criteria, choose a different cursor. If sorting by createdAt, add id as a tie-breaker:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at ASC, id ASC
```

Keyset pagination does not automatically guarantee a consistent snapshot for the entire job if data changes continuously. Define a data boundary, such as fixing an upper timestamp or maximum ID at the start, if business logic requires processing a stable set. Spring Data offers a Scroll API with Window and ScrollPosition in supporting versions; check your Spring Data JPA version's support and query type limitations.

## 11. Projections Reduce Data Read

If a screen only needs ID and name, there is no need to load the entire entity along with associations. Use an interface projection:

```java
public interface CustomerSummary {
    Long getId();
    String getName();
}
```

Repository:

```java
List<CustomerSummary> findByActiveTrueOrderByIdAsc();
```

For large sets, combine with Pageable:

```java
Page<CustomerSummary> findByActiveTrue(Pageable pageable);
```

Or use a DTO projection:

```java
public record CustomerSummaryDto(Long id, String name) {
}
```

JPQL constructor expression:

```java
@Query("""
    select new com.example.customer.CustomerSummaryDto(
        c.id,
        c.name
    )
    from Customer c
    where c.active = true
    order by c.id
    """)
List<CustomerSummaryDto> findActiveSummaries();
```

Projections select only the required columns, reducing data transferred over JDBC and avoiding creating managed entities for DTO results. However, an unpaginated List projection can still return huge numbers of rows. Combine projections with Page, Slice, or batch cursors for large datasets.

## 12. Streaming Results

Spring Data JPA supports repository methods returning Stream<T> in appropriate cases:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where c.active = true
        order by c.id
        """)
    Stream<Customer> streamActiveCustomers();
}
```

Use within a transaction and close the stream:

```java
@Transactional(readOnly = true)
public void processActiveCustomers() {
    try (Stream<Customer> customers =
             repository.streamActiveCustomers()) {

        customers.forEach(this::processCustomer);
    }
}
```

A Stream can hold open JDBC/result set resources. Therefore:

- Consume the stream inside an appropriate transaction.
- Always close the stream, ideally via try-with-resources.
- Do not return a stream from a service and consume it after the transaction has ended.
- Check provider and JDBC driver fetch size if cursor-based reading is desired.
- Do not assume Stream<T> always guarantees partial loading or zero memory accumulation.

The JPA provider may still retain read entities in the persistence context. For very large streams, memory can grow steadily even though results are consumed incrementally. Projections/DTOs or window/batch processing may be more suitable. If you need to clear the persistence context periodically, design it so still-needed entities are not detached and check how the provider implements streaming.

## 13. findAllById and Streaming Have Different Roles

findAllById fits when you already have a set of IDs to look up. Streaming fits when iterating through a large query result set. There is no standard findAllByIdStream method in JpaRepository to replace all cases.

If the ID source is very large, split IDs into batches and call findAllById per batch. If the goal is scanning the entire table in order, keyset pagination or a streaming query is usually more natural than reading all IDs first and calling findAllById.

Avoid doing two large passes: first findAll IDs, then findAllById for all IDs. That can consume more memory and queries than a single filtered/projected query.

## 14. Lazy Loading and N+1 When Reading Lists

findAll() might issue just one query for the main table. However, if code iterates over each entity and accesses a LAZY association, the provider can issue an additional query per entity.

Example:

```java
List<PurchaseOrder> orders = orderRepository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

If there are N orders and each customer access generates an extra query, the total query count can approach N+1. Identify the data needed for display and use fetch join, EntityGraph, or DTO projections for the exact use case.

Do not indiscriminately fetch-join OneToMany collections when paginating. Joining collections can duplicate parent rows and cause inaccurate pagination/counts or force the provider to paginate in memory. For large lists, DTO projections or two-step ID pagination followed by loading details can be safer.

## 15. Transactions and Persistence Context in Batch Reads

CRUD read methods inherited from SimpleJpaRepository, such as findAll() and findById(), are configured with read-only transactions. Application-declared query methods do not automatically receive transaction configuration by default; place @Transactional on the service or repository as needed. If the service already has an outer @Transactional, the repository joins the existing transaction under default propagation.

For batch processing, decide whether a transaction spans the entire job or each batch:

- One large transaction holds snapshots/locks and the persistence context longer, potentially increasing memory and connection hold times.
- Per-batch transactions limit resources and allow committing progress per batch, but data can change between batches and the job may complete partially on failure.
- If business logic requires a consistent point-in-time result, design appropriate isolation/snapshots or data boundaries.

For read-only operations, @Transactional(readOnly = true) is an optimization hint to the transaction manager/provider. It does not guarantee all writes are blocked, does not automatically enable streaming, and does not replace row limits.

If processing managed entities and updating each one, the persistence context can grow with the batch. You can flush/clear per batch when writing, keeping in mind clear detaches all managed entities. If only reading without modifying, DTO projections typically reduce overhead further.

## 16. Choosing an API by Scenario

| Need | Suitable approach | Notes |
|---|---|---|
| Small table, need everything | findAll() | No row limit |
| Full list with ordering | findAll(Sort) | Still loads everything |
| Look up moderate ID set | findAllById(ids) | Missing IDs skipped, order not guaranteed |
| List with total page count | findAll(Pageable) returning Page | May require a count query |
| Load more, no total needed | Slice<T> | Avoids full count |
| Large data, deep pages | Keyset/seek pagination | Requires cursor and stable ordering |
| Sequential iteration via DB cursor | Stream<T> | Requires transaction, closing stream, checking driver/provider |
| Only need a few columns | Projection/DTO | Combine with pagination/batching |
| Many IDs from external source | findAllById in batches | Choose batch size per database limits |

## 17. Common Pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| API slows down as table grows | findAll() loads all records | Use Pageable, Slice, or keyset |
| OutOfMemoryError | Holding too many entities and persistence context | Limit batches, projections, appropriate transactions |
| findAllById result missing items | Some IDs do not exist | Compare input ID set against returned IDs |
| findAllById order looks wrong | Method does not guarantee input order | Re-sort by input or query with ORDER BY |
| SQL too large or exceeds bind parameter limit | Passed ID set is too large | Split IDs into small batches |
| Deep pages get progressively slower | Large offset | Use keyset pagination and indexes |
| Page query slow despite small content | Expensive count query | Use Slice when total count is unnecessary |
| Stream holds connections too long | Stream not closed or processing too slow | try-with-resources and appropriately short transactions |
| Stream still consumes memory | Entities accumulate in persistence context or driver does not truly stream | Use projections/windows, check fetch size and provider |
| N+1 when reading lists | Accessing lazy association per entity | EntityGraph, suitable fetch join, or DTO |
| Wrong pagination with collection fetch join | Join duplicates parent rows | Paginate IDs first or use projections |
| Data changes between batches | Multiple transactions or isolation lacks shared snapshot | Fix data scope or pick appropriate isolation |

## 18. Practice Exercises

1. Create CustomerRepository and call findAll() on a small table; observe SQL and result type.
2. Call findAll(Sort.by("id")) and confirm stable ordering.
3. Call findAllById() with one existing ID and one nonexistent ID; verify the missing ID is skipped.
4. Pass IDs in an order different from database order and verify the result makes no guarantee to preserve input order.
5. Write code to re-order results according to the input ID list.
6. Split 5,000 IDs into batches of 500 and observe SQL/query size.
7. Build Page and Slice APIs; compare query counts and count queries.
8. Create a keyset query by id and process batches sequentially.
9. Use an interface projection to read only id/name.
10. Write a Stream<T> repository method, consume it with try-with-resources inside a transaction, and observe connection lifetime.
11. Measure memory usage of findAll() versus projection + pagination.
12. Enable SQL logging to detect N+1 when accessing each order's customer.

**Overarching principle:** findAll reads all results with no memory limit; findAllById looks up a set of IDs, skips nonexistent IDs, and does not guarantee input order. When data is large, limit each read using Page/Slice or keyset, choose projections to reduce transferred data, and use Stream only when transactions, JDBC resources, and the persistence context are properly managed.