# Traversing Multiple Windows and Managing Continuation Positions in Spring Data JPA

## 1. What Is Scrolling and What Problem Does It Solve?

When querying a table with hundreds of thousands or millions of records, loading the entire result set into a `List<T>` can consume significant memory and time. Pagination with `Page<T>` splits results into pages, but typically requires an additional query to count the total number of records. When you only need to process large data sequentially, computing the total count can be unnecessary.

Spring Data provides the **Scroll API** to read data in small batches called `Window<T>`. Each window contains a slice of results and provides a `ScrollPosition` to continue querying from the last position. The application can process one window, obtain the next position, and request the subsequent window until all data is exhausted.

Scrolling is useful for:

- Exporting large datasets to files in chunks.
- Synchronizing data between two systems.
- Running background jobs across many records.
- Performing batch calculations or reporting.
- Traversing data in a stable order without loading everything into memory.
- Saving checkpoints to resume processing after an interruption.

The Scroll API has two primary positioning strategies:

1. **Offset-based scrolling:** resumes by the number of skipped records.
2. **Keyset-based scrolling:** resumes by the sort key values of the last record in the window.

The two approaches have different performance characteristics and resilience to data changes. Choose based on data size, sorting requirements, and job resumption needs.

## 2. Return Types: List, Page, Slice, Window, and Stream

Spring Data JPA supports several ways to retrieve data. They do not completely replace one another:

| Return type | How it works | Has total count? | Best suited for |
|---|---|---|---|
| `List<T>` | Fetches all matching results | No | Small datasets |
| `Page<T>` | Fetches one page and usually runs an extra count query | Yes | UIs needing total pages/records |
| `Slice<T>` | Fetches a slice and indicates whether a next page exists | No | UIs only needing a next button |
| `Window<T>` | Fetches a window, using `ScrollPosition` to continue | No | Traversing large datasets in chunks |
| `Stream<T>` | Processes results via a Java Stream tied to query resources | No | Single continuous pass within a transaction |

`Page<T>` fits when users need to know total page counts. `Slice<T>` eliminates total counting overhead. `Window<T>` provides explicit continuation positions and supports offset or keyset. `Stream<T>` is a resource that may be tied to a JDBC ResultSet; its lifecycle must be managed and the stream closed properly.

An important point: `Window<T>` is not a Java `Stream<T>`. A Window is an already-queried batch of results; `ScrollPosition` is used to request the next batch. A Stream is a resource consumed sequentially that must be closed.

## 3. How Do ScrollPosition and Window Work?

A scroll query typically has three components:

- **Query predicate:** defines the dataset to traverse, such as order status.
- **Stable order:** defines which record comes before or after another.
- **Continuation position:** defines where to start querying the next window.

A repository method can return `Window<T>` and accept `ScrollPosition`:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Window<User> findFirst100ByStatusOrderByIdAsc(
        UserStatus status,
        ScrollPosition position
    );
}
~~~

The method above fetches up to 100 users matching the status, sorted by ID ascending. `ScrollPosition` tells Spring Data where to resume.

A `Window<T>` can be iterated like a collection:

~~~java
Window<User> window = repository.findFirst100ByStatusOrderByIdAsc(
    UserStatus.ACTIVE,
    ScrollPosition.offset()
);

for (User user : window) {
    process(user);
}
~~~

To fetch the next window, obtain the position of the last element in the current window:

~~~java
ScrollPosition nextPosition = window.positionAt(window.size() - 1);
~~~

This position serves as the marker for the next query. Scroll positions have **exclusive** semantics: the next query begins after the element represented by that position. As a result, the last element of the previous window is not returned again as the first element of the next window.

If the window is empty, do not call `positionAt(window.size() - 1)` because the index will be invalid. Always check `isEmpty()` before obtaining the position.

## 4. Manually Traversing Multiple Windows

You can write a loop to explicitly control each query and processing step:

~~~java
public void exportActiveUsers() {
    ScrollPosition position = ScrollPosition.offset();

    while (true) {
        Window<User> window =
            userRepository.findFirst100ByStatusOrderByIdAsc(
                UserStatus.ACTIVE,
                position
            );

        if (window.isEmpty()) {
            break;
        }

        for (User user : window) {
            exportUser(user);
        }

        if (window.isLast()) {
            break;
        }

        position = window.positionAt(window.size() - 1);
    }
}
~~~

Flow:

1. Start from `ScrollPosition.offset()`.
2. Fetch a window of up to 100 elements.
3. If the window is empty, finish.
4. Process each element in the window.
5. If it is the last window, finish.
6. Obtain the position of the last element and query the next window.

In this example, `exportUser` is application-defined business logic. Ensure each window is processed successfully before advancing the checkpoint to the next window.

A manual loop fits when you need logging, timing metrics, checkpoint saving, error handling, or batch-level commits. For simple traversal flows, `WindowIterator` reduces boilerplate control code.

## 5. Using WindowIterator to Simplify Traversal

`WindowIterator` is a Spring Data Commons utility that simplifies iterating continuously across multiple windows. It automatically calls the query with the next position as needed, so the application does not have to write empty-window checks and `ScrollPosition` updates manually.

Example:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

public void processActiveUsers() {
    WindowIterator<User> users = WindowIterator
        .of(position ->
            userRepository.findFirst100ByStatusOrderByIdAsc(
                UserStatus.ACTIVE,
                position
            )
        )
        .startingAt(ScrollPosition.offset());

    while (users.hasNext()) {
        User user = users.next();
        process(user);
    }
}
~~~

`WindowIterator.of(...)` accepts a function taking a `ScrollPosition` and returning a `Window<T>`. `startingAt(...)` defines the initial position.

It can be initialized with either offset or keyset:

~~~java
WindowIterator<User> offsetUsers = WindowIterator
    .of(position -> userRepository.findFirst100ByStatusOrderByIdAsc(
        UserStatus.ACTIVE, position
    ))
    .startingAt(ScrollPosition.offset());
~~~

`WindowIterator` is helpful when only sequential traversal is needed. If you need transaction control, checkpoint saving, retries, or per-window commits, a manual loop can be easier to structure.

`WindowIterator` has been available since Spring Data Commons 3.1. Verify the Spring Data version in your project before using it.

## 6. Offset-Based Scrolling

Offset scrolling works similarly to offset pagination. The query skips a number of results and fetches the next group.

Repository example:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    Window<Order> findFirst200ByStatusOrderByIdAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Initialization:

~~~java
Window<Order> firstWindow =
    orderRepository.findFirst200ByStatusOrderByIdAsc(
        OrderStatus.PAID,
        ScrollPosition.offset()
    );
~~~

When moving to the next window, Spring Data uses the offset corresponding to the saved position.

### Distinguishing offset() and offset(0)

This detail can easily cause the first record to be missed:

- `ScrollPosition.offset()` represents the starting position, not yet pointing to a specific element.
- `ScrollPosition.offset(0)` represents the position of the first element, which has offset 0.

Because scroll positions are exclusive, the query starts after the specified position. Therefore, using `ScrollPosition.offset(0)` as the initial position will skip the element at offset 0. To start from the very first record, use `ScrollPosition.offset()` or `OffsetScrollPosition.initial()`.

### Advantages and Limitations of Offset

Advantages:

- Easy to understand and implement.
- Does not require storing sort key values of the last record.
- Can be used with many sorting styles.
- Does not require a total record count query like `Page<T>`.

Limitations:

- As the offset grows large, the database typically has to process or skip many rows before returning results.
- Deep queries can progressively slow down on very large datasets.
- If records are inserted or deleted before the current offset between queries, numeric positions can shift, causing duplicate or skipped records.
- Results require a stable order; sorting by a non-unique column can leave the order among tied rows non-deterministic.

Offset fits moderately sized datasets, shallow queries, or cases needing simple continuation. For very large datasets, keyset is usually a better fit.

## 7. Keyset-Based Scrolling

Keyset scrolling resumes based on the values of sort properties at the last record of the previous window. Instead of asking the database to skip thousands or millions of results, the query adds filter conditions to fetch only records coming after the current keyset.

For example, data is sorted by `createdAt` ascending. The continuation position stores the `createdAt` value of the last element. The next query can be illustrated conceptually as:

~~~sql
SELECT *
FROM orders
WHERE status = ?
  AND (
      created_at > ?
      OR (created_at = ? AND id > ?)
  )
ORDER BY created_at ASC, id ASC
LIMIT 200;
~~~

This SQL illustrates the principle. Spring Data and the JPA provider construct the keyset condition appropriate for the database, sort order, and primary key.

Keyset can leverage indexes on sort fields to reduce the amount of data processed. It is especially useful when traversing large datasets in a stable ascending or descending order.

### Declaring a Keyset Query

Example entity with non-null `createdAt`:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    Window<Order> findFirst200ByStatusOrderByCreatedAtAsc(
        OrderStatus status,
        ScrollPosition position
    );
}
~~~

Initializing with keyset:

~~~java
Window<Order> firstWindow =
    orderRepository.findFirst200ByStatusOrderByCreatedAtAsc(
        OrderStatus.PAID,
        ScrollPosition.keyset()
    );
~~~

`ScrollPosition.keyset()` represents starting from the beginning of the result set, with no key continuation predicate applied yet. After receiving a window, the position of the last element holds the values required for the next query.

Spring Data appends the primary key to the ordering when necessary to ensure each row has a unique position. If multiple orders share the same `createdAt`, the primary key disambiguates their order.

### Key Requirements for Keyset

Keyset scrolling has several requirements:

1. **Order must be stable.** Sort fields must have clear meaning and not change arbitrarily during traversal.
2. **Sort properties must be non-nullable.** NULL comparisons have differing semantics across databases; keyset on nullable properties can produce unexpected results.
3. **Projections must include sort fields.** Spring Data needs to read key values to build the continuation position. If returning a DTO, include all sort fields in the DTO projection.
4. **Suitable indexes should exist.** Indexes covering filter and sort fields help the database execute keyset conditions efficiently.
5. **Sort keys should be stable.** If a record's sort value changes while the process runs, it may move past an already-traversed or untraversed position.

When sorting by `createdAt`, that property should be mapped and have non-NULL values. The primary key is used as a tie-breaker to create a unique ordering.

## 8. Comparing Offset and Keyset

| Criterion | Offset scrolling | Keyset scrolling |
|---|---|---|
| Continuation position | Number of skipped rows | Sort key values at the last row |
| Query mechanism | Skip offset then take limit | Add WHERE condition by keyset |
| Deep traversal cost | Can grow with offset | Usually more stable with suitable indexes |
| Sort requirements | Should have stable order and unique tie-breaker | Needs stable sort, non-null sort keys |
| Projection | More flexible | Must include sort properties |
| Data changes between calls | Inserts/deletes before offset can shift positions | Less affected by inserts before position, though key updates/deletes can still affect |
| Best suited for | Medium sets, simple logic | Large sets, ordered processing, efficient continuation |

Neither approach automatically guarantees a consistent snapshot across multiple requests or transactions. Keyset reduces certain offset-shift issues, but does not replace transaction isolation, snapshots, or application checkpointing.

## 9. Saving and Restoring Continuation Positions

An advantage of scrolling is that the application can save a checkpoint after each window. If the process stops, a subsequent run can resume from the saved position instead of starting over from the beginning.

Checkpoints should be bound to:

- Filter conditions, such as status or date range.
- Sort order and sort direction.
- Scroll type (offset or keyset).
- Last offset or keyset values.
- Query definition version if logic may change.
- Timestamp and completion state of the processed batch.

Do not store only an offset without storing the accompanying query conditions and ordering. When filters or sorting change, an old offset/keyset may no longer represent the same position.

With keyset, the application can store the key values of the last element in an application-managed checkpoint DTO. When restoring, reconstruct the corresponding position via the API of your Spring Data version. Do not assume a `ScrollPosition` object can be safely serialized, persisted long-term, or reused across upgrades without checking the API contract.

### Checkpoint Update Order

A batch processing workflow should:

1. Read a window from the saved position.
2. Process all elements in the window.
3. Confirm batch changes committed successfully.
4. Save the checkpoint corresponding to the last successfully processed element.
5. Move to the next window.

If the checkpoint is saved before data is successfully processed, the process may skip incomplete work. If processing finishes without saving the checkpoint and the process stops, the window may be reprocessed.

Therefore, tasks should be idempotent or have duplicate-processing guards. If data updates and checkpoints reside in the same database, they can be designed within the same transaction to reduce state divergence risks. If external systems are involved, consider a transactional outbox or corresponding acknowledgment mechanism.

## 10. Data Changing During Scrolling

Scroll queries usually execute multiple queries, each potentially in a different transaction or at a different time. Thus, source data can change between windows.

Example with offset:

- The first window reads rows at positions 0–99.
- A row at the start of the set is deleted.
- The next query starts at offset 100.
- The row previously at position 100 shifted to 99 and may be skipped.

With keyset, the query resumes after the last-read key value, so inserting records with keys smaller than the current position generally does not shift the continuation position. However:

- New records with keys larger than the current position may appear in later windows.
- Unread records that are deleted will no longer appear.
- Already-read records whose sort key changes to after the cursor may appear again.
- Unread records whose sort key changes to ahead of the cursor may be skipped.

If traversing an exact fixed dataset is required, define a snapshot policy. You can use an appropriate transaction isolation level, a timestamp/ID cutoff bounding the dataset, or a staging table holding the worklist. Keeping a very long transaction open to preserve a snapshot also carries costs for connections, locks, or row versions depending on the database; weigh these before choosing.

## 11. Scrolling with DTO Projections

Windows can return projections instead of entities. This is useful when only a few fields are needed and you want to reduce the volume of loaded data.

Record example:

~~~java
public record UserExportRow(
    Long id,
    String email,
    Instant createdAt
) {}
~~~

Repository:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Window<UserExportRow> findFirst500ByStatusOrderByCreatedAtAsc(
        UserStatus status,
        ScrollPosition position
    );
}
~~~

If using keyset by `createdAt`, the projection must contain `createdAt` so Spring Data can obtain the continuation key. If Spring Data automatically appends ID to the order, ensure the projection mechanism exposes sufficient key information as required by your provider/version; the safe approach is to include all required sort and identifier fields in the DTO.

DTO projections also avoid keeping many managed entities in the persistence context when only reading and exporting data. Still, inspect the generated SQL and verify the selected fields are accurate.

## 12. Scrolling Support Limitations in Spring Data JPA

The Scroll API supports query methods, Query by Example, and Querydsl. However, in current Spring Data JPA documentation, **scrolling with string-based query methods is not yet supported**. This includes methods declared via query strings such as `@Query`; stored query methods using `@Procedure` also do not support scrolling.

When scrolling is needed:

- Prefer derived query methods with `Window<T>` and `ScrollPosition`.
- Consider Query by Example if search criteria fit.
- Consider Querydsl when dynamic predicate expressions are needed.
- If a complex query can only be expressed via `@Query`, consider a custom repository with an appropriate batching mechanism, or redesign the query as a query method/Querydsl.
- Check documentation for your project's exact Spring Data JPA version because support may change across releases.

Do not force a complex query into a derived query solely to use scrolling if doing so makes the method name unreadable or fails to express the business logic accurately.

## 13. Java Stream<T> for Processing Large Data

Spring Data JPA also supports repository methods returning `Stream<T>`:

~~~java
public interface UserRepository extends JpaRepository<User, Long> {

    Stream<User> findByStatusOrderByIdAsc(UserStatus status);
}
~~~

A service can consume the stream:

~~~java
@Service
public class UserExportService {

    private final UserRepository userRepository;

    public UserExportService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional(readOnly = true)
    public void exportActiveUsers() {
        try (Stream<User> users =
                 userRepository.findByStatusOrderByIdAsc(
                     UserStatus.ACTIVE
                 )) {

            users.forEach(this::exportUser);
        }
    }

    private void exportUser(User user) {
        // Write data to the application's export target.
    }
}
~~~

There are three important rules:

1. **Close the stream:** use try-with-resources because streams can hold JDBC ResultSets, Statements, and connections.
2. **Keep the transaction open while consuming:** the stream requires an active persistence context and database resources. Do not return the stream outside the transaction and process it afterward.
3. **Do not assume streams automatically use low memory:** the JPA provider and JDBC driver determine fetching behavior. Check fetch size and driver cursor settings if incremental reading is desired.

`@Transactional(readOnly = true)` fits read-only flows and clearly declares the transaction scope. It does not replace closing the stream and does not guarantee the driver always uses a cursor.

## 14. Stream Does Not Mean Incremental Fetching

The `Stream<T>` return type only expresses a sequential consumption API. It does not by itself guarantee the provider or JDBC driver loads only a few rows at a time.

Several things to verify:

- Does the JPA provider support streaming/cursors for that query?
- What fetch size does the JDBC driver require?
- Does the database/driver require a transaction or disabled autocommit to use cursors?
- Is the fetch size query hint supported by the provider?
- Do streamed entities accumulate in the persistence context?

When streaming entities, each loaded entity typically becomes managed by the persistence context. If iterating over millions of entities in one transaction, the persistence context can grow in memory even when results are consumed via a Stream.

Ways to reduce memory pressure:

- Select only needed fields using DTO/scalar projections when appropriate.
- Configure fetch size per provider and driver documentation.
- Process in batches and consider `EntityManager.clear()` or `detach()` when appropriate.
- If performing batch writes, flush and clear periodically while keeping track of entities/relationships still needed.
- Avoid accessing lazy associations after an entity has been detached.

Clearing the persistence context while streaming must be tested with your specific provider and driver. Do not do it mechanically if logic still relies on managed entities or lazy relationships.

## 15. Do Not Use Parallel Streams for a Single Persistence Context

A Java Stream can support `parallel()`, but you should not default to parallel streams for processing JPA results.

`EntityManager` and the persistence context are not thread-safe. A Stream can be tied to a single JDBC ResultSet and transaction on one connection. Splitting processing across multiple threads can cause unsafe concurrent access or entity usage outside the transaction.

If parallel processing is needed:

1. Read each window or batch into independent DTOs.
2. Close or finish the query and transaction boundaries cleanly.
3. Pass immutable data to workers.
4. Have each worker use its own transaction and persistence context if database access is required.
5. Design idempotency and commit/checkpoint ordering.

Never pass an open JPA Stream across multiple threads and never share an `EntityManager` across workers.

## 16. Choosing Window or Stream?

| Scenario | Consider using |
|---|---|
| Need to read in chunks and control batch boundaries | `Window<T>` |
| Need to persist position and resume after process stops | `Window<T>` with `ScrollPosition` and checkpoints |
| Large data, indexed sort, wanting to avoid deep offsets | Keyset `Window<T>` |
| Medium data, wanting simple implementation | Offset `Window<T>` |
| UI needs total record count | `Page<T>` |
| Only need to know if a next page exists | `Slice<T>` |
| Single continuous pass within one transaction and driver supports cursors | `Stream<T>` |
| Need parallel execution by batch | Read windows/batches into DTOs then distribute to workers |

`Window<T>` is usually easier to control when tasks require retries, checkpoints, and batch commits. `Stream<T>` fits a single sequential pass when the transaction and JDBC resources can stay open during consumption.

## 17. Testing and Monitoring Scrolling

Use integration tests against an appropriate database to verify window traversal and continuation positions.

Scenarios to test:

1. Dataset smaller than window size.
2. Dataset exactly equal to window size.
3. Dataset spanning many windows.
4. Last window and empty window.
5. No skipped or duplicated elements between consecutive windows.
6. Offset starting with `ScrollPosition.offset()` and the common mistake `offset(0)`.
7. Keyset with multiple rows sharing sort values and primary key used as tie-breaker.
8. NULL sort properties and projections missing sort keys should be caught in tests.
9. Resuming from a checkpoint after completing a window.
10. Inserts, updates, or deletes occurring between queries.
11. Stream always closed on both success and exception.
12. Fetch size and memory usage on the target database/driver.

Metrics you can measure:

- Query duration per window.
- Number of processed records.
- Processing time per batch.
- Retry counts and failed batches.
- Latest committed checkpoint position.
- Heap usage and connections held during execution.

Avoid logging full entities or personal data unnecessarily. Logging IDs/checkpoints and counts is usually sufficient to track progress.

## 18. Process for Implementing a Large-Data Traversal Task

A practical workflow can follow these steps:

1. Define filter predicates and a fixed sort order.
2. Choose a window size suitable for query duration, memory, and transaction limits.
3. Choose offset for medium datasets or keyset for large datasets with suitable sort keys.
4. Create a repository method returning `Window<T>` and accepting `ScrollPosition`.
5. For simple traversal, use `WindowIterator`; if checkpoints and retries are needed, write a manual loop.
6. Process the complete window and commit work successfully.
7. Save the checkpoint after the batch completes.
8. On failure, retry per policy and ensure operations can be re-run safely.
9. Monitor record counts, duration, errors, and checkpoints.
10. With Stream, keep a transaction open while consuming, use try-with-resources, and confirm the provider/driver actually fetches incrementally.

## 19. Takeaways

- The Scroll API splits results into `Window<T>` and uses `ScrollPosition` to query the next portion.
- Scroll positions are exclusive: queries resume after the element represented by the position.
- Use `ScrollPosition.offset()` to start from the beginning; `offset(0)` points to the first element and can cause that element to be skipped.
- Offset is simple but can be slow at deep positions and susceptible when rows before the cursor are inserted/deleted.
- Keyset uses the sort values of the last element, typically performing better on large datasets with proper indexes.
- Keyset requires non-NULL sort keys and projections containing the sort fields.
- Ordering must be stable; the primary key is used to distinguish rows sharing the same sort values.
- `WindowIterator` iterates across multiple windows without manually updating positions.
- Per current Spring Data JPA documentation, scrolling supports query methods, Query by Example, and Querydsl; string-based query methods and stored `@Procedure` do not yet support scrolling.
- Java `Stream<T>` must be closed and consumed within a transaction; it does not automatically guarantee incremental fetching.
- Streaming entities can cause the persistence context to grow in memory; consider DTOs, fetch size, and batch detach/clear.
- Do not share a JPA Stream or `EntityManager` across multiple threads.
- Checkpoints must be saved after a batch finishes processing successfully; design idempotency for safe reprocessing.

Use `Window<T>` when splitting work into batches and managing continuation positions. Choose offset for simple traversal, keyset for large datasets with stable ordering, and `Stream<T>` when a single sequential pass within a transaction with properly managed JDBC resources is needed.

## References

- [Spring Data JPA — JPA Query Methods, Scrolling Large Query Results](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Repository Query Return Types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html)
- [Spring Data Commons — WindowIterator API](https://docs.spring.io/spring-data/jpa/reference/data-commons/api/java/org/springframework/data/support/WindowIterator.html)
