# Evaluating Limit, Scrolling, and Specification APIs by Spring Data JPA Version

Spring Data JPA adds APIs across multiple release trains. Familiar capabilities such as Pageable and Specification have existed for a long time; newer APIs such as ScrollPosition/Window, Limit, PredicateSpecification, and fluent query operations only appear in specific versions.

When evaluating a new API, check three things: the versions of Spring Data Commons and Spring Data JPA the application actually runs, the capabilities of the repository/query type in use, and execution cost at the database. Do not simply take examples from the latest documentation and drop them directly into an older project.

This lesson focuses on three API groups:

- Limit: dynamically capping the number of results per call.
- Scrolling: reading large result sets Window by Window using offset or keyset.
- Specification: building and composing dynamic predicates; distinguishing traditional Specification from PredicateSpecification and new APIs in Spring Data JPA 4.x.

## 1. Identify versions before using APIs

Spring Data JPA depends on Spring Data Commons. Many types such as Limit, ScrollPosition, Window, and WindowIterator are defined in Spring Data Commons, and the JPA module integrates them with JPA queries.

In a Spring Boot application, versions are usually managed via dependency management/BOM. Before upgrading, check:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

Determine the actual versions of at least:

- spring-data-jpa.
- spring-data-commons.
- spring-boot-dependencies or the corresponding BOM.
- Hibernate ORM and the Jakarta Persistence provider.

Do not upgrade spring-data-jpa alone to a newer version while the Spring Boot BOM still manages an older release train. Spring Data modules within the same release train are tested and released for mutual compatibility.

At the time of writing, Spring Data JPA documentation lists 4.1.x as the latest stable line; examples below use APIs whose version milestones are explicitly noted. Always verify patch versions and the compatibility matrix in official documentation before changing your build.

## 2. API map by version

Key milestones:

| API | Version introduced | Meaning |
|---|---:|---|
| Pageable, Page, Slice | Available since older Spring Data lines | Offset-based pagination |
| ScrollPosition, Window, WindowIterator | Spring Data 3.1 | Scroll results window by window |
| Limit | Spring Data 3.2 | Pass a dynamic limit into a query method |
| Specification.unrestricted() | Spring Data JPA 3.5.2 | Specification that contributes no predicate |
| Specification.where(Specification) nullable | Deprecated in 3.5, null support removed in 4.0 | Stop using null to represent an empty condition |
| PredicateSpecification | Spring Data JPA 4.0 | Query-type-independent predicate |
| UpdateSpecification, DeleteSpecification | Spring Data JPA 4.0 | Predicates bound to CriteriaUpdate/CriteriaDelete |
| Expanded SpecificationFluentQuery | Spring Data JPA 4.x | Limit, projection, page, slice, scroll, stream in fluent API |

An API appearing in Spring Data Commons does not guarantee every Spring Data module supports it identically. For example, the Scroll API lives in shared infrastructure, yet Spring Data JPA has limitations for specific query types. Always read the store-specific section of the Spring Data JPA documentation.

## 3. What need does Limit solve?

Limit represents the maximum number of results a query is allowed to return. Unlike Pageable, Limit requires no page number, offset, or total page count.

Repository example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByStatus(
        CustomerStatus status,
        Limit limit
    );
}
~~~

The caller chooses the limit at invocation time:

~~~java
List<Customer> firstTwenty =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        Limit.of(20)
    );

List<Customer> allActive =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        Limit.unlimited()
    );
~~~

Limit belongs to the org.springframework.data.domain package. It is a special parameter recognized by Spring Data, not an entity property, and is not bound into a WHERE condition.

Use Limit when an API needs a dynamic per-request cap, such as fetching at most 10 autocomplete suggestions or at most 100 records for a processing task.

## 4. How does Limit differ from Top and First?

Spring Data has long supported the Top and First keywords in query method names:

~~~java
List<Customer> findTop10ByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);

Optional<Customer> findFirstByEmailOrderByCreatedAtDesc(
    String email
);
~~~

Top/First express a fixed limit in the method name. Limit allows passing a dynamic value:

~~~java
List<Customer> findByStatusOrderByCreatedAtDesc(
    CustomerStatus status,
    Limit limit
);
~~~

Comparison:

| Approach | Limit | Best fit |
|---|---|---|
| Top10/First10 | Fixed in method name | Rule is always the same |
| Limit.of(n) | Dynamic per call | Client/service chooses the cap |
| Pageable | Dynamic page size and offset | Paginated screens |
| Scroll Window | Read multiple chunks and resume by position | Batch/export/reading large datasets |

Do not combine Top/First keywords with a Limit parameter in the same query method. Choose one place to define the cap so two limits do not compete.

## 5. Rules for combining Limit with Sort and Pageable

Limit can be combined with Sort:

~~~java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort,
    Limit limit
);
~~~

Example:

~~~java
List<Customer> newest = repository.findByStatus(
    CustomerStatus.ACTIVE,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ),
    Limit.of(50)
);
~~~

Do not pass null for special parameters. If you do not want sorting or a limit, use:

- Sort.unsorted().
- Limit.unlimited().
- Pageable.unpaged() when the method takes Pageable.

Do not combine Pageable and Limit in the same method because Pageable already holds page size/offset. Similarly, Pageable already carries Sort, so do not pass a separate Sort alongside it. Top/First can be used with Pageable; the keyword sets an overall ceiling while Pageable controls pages within that ceiling.

## 6. Limit does not generate pagination metadata

A method returning List with Limit returns only the capped list. It does not provide:

- Total matching records.
- Total pages.
- Current page.
- Whether a next page exists.

If the UI needs totalElements and totalPages, use Page. If you only need to know whether more results exist, use Slice. If you need continuous positional processing without a total count, consider the Scroll API.

Do not run a separate count query just to display metadata if business requirements do not need it. Counting a large table or multi-join query can cost more than querying the data itself.

## 7. What components make up the Scroll API?

The Scroll API is designed to read a large result set in multiple small Windows.

Main components:

- Window<T>: the current window of results.
- ScrollPosition: position from which to continue reading.
- OffsetScrollPosition: offset-based position.
- KeysetScrollPosition: position based on the values of the sort columns.
- WindowIterator<T>: iterator that manages fetching subsequent Windows automatically.

A scrolling query needs:

1. Stable filter conditions.
2. Deterministic sort order.
3. Size of each Window.
4. ScrollPosition to start or resume.

Scrolling does not require computing the total record count. Hence, it fits exports, data synchronization, batch jobs, or reading many records for background processing.

## 8. Declaring a query method returning Window

Example reading Customers by status, up to 100 records at a time:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Window<Customer> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus status,
        ScrollPosition position
    );
}
~~~

First call:

~~~java
Window<Customer> window =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.offset()
    );
~~~

The Window holds at most 100 Customers and supplies the position for fetching the next window.

You can use WindowIterator to avoid manually writing a loop that checks hasNext and updates ScrollPosition:

~~~java
WindowIterator<Customer> customers = WindowIterator
    .of(position ->
        repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
            CustomerStatus.ACTIVE,
            position
        )
    )
    .startingAt(ScrollPosition.offset());

while (customers.hasNext()) {
    Customer customer = customers.next();
    process(customer);
}
~~~

The example assumes process(Customer) is an application processing method. WindowIterator tracks the scroll position and calls the repository to fetch subsequent Windows.

## 9. Offset scrolling

Offset scrolling identifies the position by the number of skipped rows.

Example:

~~~java
Window<Customer> first =
    repository.findFirst100ByStatusOrderByIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.offset()
    );

Window<Customer> next =
    repository.findFirst100ByStatusOrderByIdAsc(
        CustomerStatus.ACTIVE,
        first.positionAt(first.size() - 1)
    );
~~~

ScrollPosition.offset() represents starting from the beginning of the result set.

Common pitfall: ScrollPosition is an exclusive position. ScrollPosition.offset(0) points to the element at offset 0 and the next query starts after that element, which can skip the first element. When starting from the beginning, use ScrollPosition.offset() instead of offset(0).

Offset scrolling is easy to understand and works well for moderate datasets. However, at very large offsets, the database still has to process or skip many rows before returning the next Window. Cost can grow with depth.

## 10. Keyset scrolling

Keyset scrolling uses the sort column values of the last element in the current Window to continue.

Example sorting by createdAt then id:

~~~java
Window<Customer> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
    CustomerStatus status,
    ScrollPosition position
);
~~~

Starting:

~~~java
Window<Customer> window =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        ScrollPosition.keyset()
    );
~~~

Continuing from the last element:

~~~java
ScrollPosition nextPosition =
    window.positionAt(window.size() - 1);

Window<Customer> next =
    repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE,
        nextPosition
    );
~~~

Logically, if the last element has createdAt = T and id = 500, the next query finds rows after that sort key:

~~~sql
WHERE status = 'ACTIVE'
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at ASC, id ASC
FETCH FIRST 100 ROWS ONLY
~~~

This illustrates the keyset logic. The actual SQL is generated by Spring Data JPA and Hibernate according to the database dialect.

Keyset avoids skipping thousands of offset rows on deep pages. The database can use an index on the sort columns to seek directly to the continuation point.

## 11. Conditions for keyset scrolling to work correctly

Keyset requires a stable sort order that uniquely identifies a position.

Rules:

- Properties used for sorting must be mapped on the entity.
- Sort values should be non-null; keyset filtering handles nullable properties poorly because NULL comparison semantics vary across databases.
- Projections must contain the properties needed to reconstruct the keyset.
- There should be an index matching the filter conditions and sort order.
- The sort order needs a unique key. Spring Data may append the primary key to guarantee uniqueness, but you must understand the actual query and projection.
- If a sort value changes while scrolling, records can shift positions and cause omissions or duplicates during reading.

For example, an appropriate index for querying by status and sorting by createdAt, id could be a composite index on (status, created_at, id). The final index design must be based on execution plans and workload.

## 12. Offset vs. keyset: which to choose?

| Criterion | Offset | Keyset |
|---|---|---|
| Continuation position | Number of skipped rows | Last sort key values |
| Deep pages | Can be slow | Usually more stable when indexed |
| Sort requirements | Needs stable sort | Needs stable sort and suitable keys |
| Nullable properties | Easier to handle | Limited; prefer non-null keys |
| Data shifts | Offset can skip/duplicate when data changes | Less sensitive to inserts before position, though updating sort keys can still shift rows |
| Complexity | Low | Higher; requires key/index design |

Use offset when users need to jump to arbitrary pages or the dataset is not very large. Use keyset when reading sequentially through large datasets and the database has supporting indexes.

Keyset is not an automatic transaction snapshot. If data changes while a batch runs, define a consistency policy such as a fixed time window, watermark, or suitable transaction.

## 13. Scrolling support limitations in Spring Data JPA

The Scroll API does not work with every query type.

According to current Spring Data JPA documentation:

- Works with derived query methods.
- Works with Query by Example.
- Works with Querydsl.
- Spring Data JPA 4.x supports scrolling via fluent Specification queries.
- Scrolling with string-based query methods declared via @Query is not currently supported.
- Stored @Procedure query methods also do not support scrolling.

If you need scrolling for queries with complex JPQL, native SQL, or stored procedures, consider a custom repository using EntityManager/JdbcTemplate with a dedicated cursor/seek mechanism. Do not assume simply changing the return type from List to Window makes @Query scrollable.

## 14. How does Window differ from Stream?

Window is an abstraction that segments a query across multiple executions. Each call returns a finite chunk and a continuation position.

Stream<T> can hold a JDBC/result set resource open while being consumed. You must close the Stream with try-with-resources:

~~~java
try (Stream<Customer> stream = repository.streamAllByStatus(
        CustomerStatus.ACTIVE)) {
    stream.forEach(this::process);
}
~~~

Not every query method or provider supports streaming identically. Stream does not replace the Scroll API when you need to persist a continuation position, split chunks across multiple requests, or resume from a keyset.

For long-running batches, Window is often easier to manage for memory and transaction boundaries because each chunk can be processed in its own unit of work.

## 15. Traditional Specification

Specification is Spring Data JPA's abstraction for representing Criteria API-based predicates.

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Traditional Specification:

~~~java
public static Specification<Customer> hasStatus(
        CustomerStatus status) {

    return (root, query, cb) ->
        status == null
            ? null
            : cb.equal(root.get(Customer_.status), status);
}
~~~

Three parameters:

- Root<T>: root entity being queried.
- CriteriaQuery<?>: overall query; can be used to create subqueries or adjust query-level behavior.
- CriteriaBuilder: creates predicates such as equal, like, greaterThan, and, or, isNull.

Specification fits when you need predicates tied to a specific query, or need CriteriaQuery to build subqueries, set distinct, or implement query-bound logic.

## 16. PredicateSpecification in Spring Data JPA 4.0

Spring Data JPA 4.0 adds PredicateSpecification, a smaller API not tied to a specific query type.

~~~java
public static PredicateSpecification<Customer> hasStatus(
        CustomerStatus status) {

    return (from, cb) ->
        status == null
            ? null
            : cb.equal(from.get(Customer_.status), status);
}
~~~

Signature:

~~~java
public interface PredicateSpecification<T> {
    Predicate toPredicate(
        From<?, T> from,
        CriteriaBuilder builder
    );
}
~~~

PredicateSpecification takes only From and CriteriaBuilder. It is suited for query-type-independent conditions that can be reused across query operations.

Because it does not take CriteriaQuery, PredicateSpecification cannot directly create subqueries or adjust query-level selection/ordering. If logic requires CriteriaQuery, use traditional Specification.

## 17. Comparing Specification and PredicateSpecification

| Criterion | PredicateSpecification | Specification |
|---|---|---|
| Introduced in | Spring Data JPA 4.0 | Older Spring Data JPA lines |
| Parameters | From, CriteriaBuilder | Root, CriteriaQuery, CriteriaBuilder |
| Scope | Query-type-agnostic | Query-bound |
| Used for | Simple, reusable predicates | Predicates needing query context |
| Subqueries | No direct CriteriaQuery | Can use CriteriaQuery.subquery |
| Composition | and/or/not | and/or/not |
| Executor | JpaSpecificationExecutor in 4.x | JpaSpecificationExecutor |

You do not need to convert every Specification to PredicateSpecification. If an implementation uses CriteriaQuery or subqueries, keeping Specification makes sense. For simple conditions such as status, email, or creation date, PredicateSpecification keeps code less coupled.

## 18. UpdateSpecification and DeleteSpecification in 4.0

Spring Data JPA 4.0 adds Specification types tied to CriteriaUpdate and CriteriaDelete:

~~~java
public interface UpdateSpecification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaUpdate<T> update,
        CriteriaBuilder builder
    );
}

public interface DeleteSpecification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaDelete<T> delete,
        CriteriaBuilder builder
    );
}
~~~

These types reflect the exact query kind to execute:

- Specification: select query.
- UpdateSpecification: bulk update query.
- DeleteSpecification: bulk delete query.

This API is useful when you want to reuse filter conditions for Criteria API update or delete queries.

Bulk updates/deletes have different semantics from loading entities and calling setters/remove: they do not automatically synchronize entities already in the persistence context. After bulk operations, consider flush/clear/refresh to avoid reading stale state.

## 19. Specification.unrestricted() and changes from 3.5 to 4.0

In older versions, code often used null to represent a Specification with no conditions:

~~~java
Specification<Customer> spec = null;
spec = spec == null ? nextSpec : spec.and(nextSpec);
~~~

Spring Data JPA 3.5 deprecated Specification.where(Specification) when passing null and introduced Specification.unrestricted() in 3.5.2.

New way:

~~~java
Specification<Customer> spec =
    Specification.unrestricted()
        .and(hasStatus(CustomerStatus.ACTIVE))
        .and(createdAfter(startTime));
~~~

unrestricted() returns a Specification contributing no predicate. It is not semantically identical to a TRUE predicate created via cb.conjunction() for composition purposes; it is omitted from the composition.

In Spring Data JPA 4.0, do not pass null into Specification.where(Specification). Use unrestricted() to represent the no-filter case.

If upgrading from 3.4 or lower, verify the version because unrestricted() did not exist before 3.5.2.

## 20. Combining PredicateSpecification with Specification

In Spring Data JPA 4.0, both types can be combined together.

Example:

~~~java
PredicateSpecification<Customer> isActive =
    (from, cb) -> cb.isTrue(from.get(Customer_.active));

Specification<Customer> createdAfter =
    (root, query, cb) ->
        cb.greaterThanOrEqualTo(
            root.get(Customer_.createdAt),
            startTime
        );

Specification<Customer> combined =
    createdAfter.and(isActive);
~~~

This lets you write simple conditions with PredicateSpecification while keeping Specification for parts needing query context.

Do not convert back and forth mechanically. Choose the smallest abstraction that satisfies the predicate's needs; only use query-bound Specification when query context is required.

## 21. SpecificationFluentQuery in 4.x

JpaSpecificationExecutor provides a fluent API via the findBy method:

~~~java
Page<CustomerSummary> page = repository.findBy(
    combined,
    query -> query
        .as(CustomerSummary.class)
        .page(PageRequest.of(
            0,
            20,
            Sort.by("createdAt").descending()
        ))
);
~~~

The fluent API lets you configure the result right at the call site:

- sortBy: add ordering.
- limit: cap result count.
- as: select projection/result type.
- project: restrict properties read when applicable.
- first/firstValue: fetch the first element.
- one/oneValue: require at most one result.
- all: fetch all results.
- page: return Page.
- slice: return Slice.
- scroll: return the next Window by ScrollPosition.
- stream: return Stream.
- count/exists: count or check existence.

Example fetching only the first 10 results:

~~~java
Optional<Customer> newest = repository.findBy(
    combined,
    query -> query
        .sortBy(Sort.by("createdAt").descending())
        .limit(10)
        .first()
);
~~~

Example keyset scrolling:

~~~java
Window<Customer> window = repository.findBy(
    combined,
    query -> query
        .sortBy(Sort.by("createdAt").ascending())
        .limit(100)
        .scroll(ScrollPosition.keyset())
);
~~~

Intermediate and terminal operations must be called inside the query function. Do not return the query object outside the callback for later use.

## 22. Choosing Page, Slice, Limit, or Window

| Need | API | Count query |
|---|---|---|
| Pages 1, 2, 3 and need total pages | Page + Pageable | May be needed |
| Only need to know if another page exists | Slice + Pageable | No total count needed |
| Fetch at most N results | Limit | No |
| Read chunks sequentially with a continuation position | Window + ScrollPosition | No |
| Read in key order for large batch processing | Keyset Window | No |
| Fetch only the single best record | First/Top or fluent first | No total count needed |

Page is convenient for UIs, but the count query can be expensive. Slice and Window suit next-page/continuation reading. Limit suits simple dynamic capping.

Do not use Page just because a method returns a list; verify whether the UI actually needs total page counts.

## 23. Example combining Specification with Limit

In Spring Data JPA 4.x, you can use the fluent API:

~~~java
List<Customer> topCustomers = repository.findBy(
    hasStatus(CustomerStatus.ACTIVE),
    query -> query
        .sortBy(Sort.by("createdAt").descending())
        .limit(25)
        .all()
);
~~~

For derived query methods, use Limit directly:

~~~java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort,
    Limit limit
);
~~~

Both approaches avoid declaring multiple methods that differ only in the limit number.

If you need a page with a total, use page(Pageable) instead of limit().all().

## 24. Combining Specification with scrolling

Fluent Specification queries in Spring Data JPA 4.x can use scroll:

~~~java
Window<Customer> firstWindow = repository.findBy(
    hasStatus(CustomerStatus.ACTIVE),
    query -> query
        .sortBy(Sort.by("id").ascending())
        .limit(500)
        .scroll(ScrollPosition.keyset())
);
~~~

If you need to iterate through the whole dataset, use WindowIterator or a loop managing ScrollPosition. For derived query methods, use methods returning Window as in earlier examples.

String-based @Query methods do not currently support the Scroll API in Spring Data JPA. If a complex query cannot be expressed with a derived method, Specification, or Querydsl, consider a custom repository.

## 25. Specification example for dynamic filters

DTO:

~~~java
public record CustomerFilter(
    CustomerStatus status,
    Boolean active,
    Instant createdFrom,
    Instant createdTo
) {
}
~~~

PredicateSpecification for simple conditions:

~~~java
public final class CustomerPredicates {

    private CustomerPredicates() {
    }

    public static PredicateSpecification<Customer> hasStatus(
            CustomerStatus status) {
        return (from, cb) -> status == null
            ? null
            : cb.equal(from.get(Customer_.status), status);
    }

    public static PredicateSpecification<Customer> isActive(
            Boolean active) {
        return (from, cb) -> active == null
            ? null
            : cb.equal(from.get(Customer_.active), active);
    }
}
~~~

Specification for date ranges:

~~~java
public static Specification<Customer> createdBetween(
        Instant from,
        Instant to) {

    return (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (from != null) {
            predicates.add(
                cb.greaterThanOrEqualTo(
                    root.get(Customer_.createdAt),
                    from
                )
            );
        }

        if (to != null) {
            predicates.add(
                cb.lessThan(root.get(Customer_.createdAt), to)
            );
        }

        return predicates.isEmpty()
            ? null
            : cb.and(predicates.toArray(Predicate[]::new));
    };
}
~~~

Combining them:

~~~java
Specification<Customer> specification =
    Specification.unrestricted()
        .and(CustomerPredicates.hasStatus(filter.status()))
        .and(CustomerPredicates.isActive(filter.active()))
        .and(createdBetween(
            filter.createdFrom(),
            filter.createdTo()
        ));
~~~

The example uses the Customer_ metamodel to avoid string property names. Generate the static metamodel in your build or replace with root.get("property") if the project has not configured the metamodel processor.

## 26. Checking the semantics of empty Specifications

A Specification can return null from toPredicate to contribute no condition. Specification.unrestricted() expresses that state explicitly.

Distinguish these cases:

- No filter: return unrestricted or skip the condition.
- Want all records within the query scope: unrestricted may be appropriate.
- Want zero records: create a FALSE predicate with cb.disjunction().
- Empty OR filter list: do not guess business meaning automatically.

In Spring Data JPA, Specification.anyOf(emptyList) can return unrestricted per API contract. This means "no participating Specifications," not "OR over an empty set must evaluate to false." If business rules require zero results, construct an explicit false predicate.

This is an easy logic bug to introduce when migrating from legacy Specifications to the new composition API.

## 27. Upgrading from Spring Data JPA 3.x to 4.x

Before upgrading, check:

1. Does Spring Boot/BOM manage Spring Data JPA 4.x?
2. Do Java and Spring Framework meet the new release train requirements?
3. Are Hibernate ORM and Jakarta Persistence compatible?
4. Does the code use Specification.where(null)?
5. Can simple predicates be replaced with PredicateSpecification?
6. Do custom repository implementations depend on internal APIs?
7. Do query methods use Limit, ScrollPosition, or Window that were unsupported in older versions?
8. Are any string-based @Query methods expected to support scrolling?
9. Do integration tests run against a real database and matching provider?

Do not upgrade a single Spring Data module outside the release train. After upgrading, compile and test all repositories to catch signature, nullability, generic type, and query behavior changes.

## 28. Key differences to note between 3.1, 3.2, 3.5, and 4.0

| Version | Notable change | Action needed |
|---|---|---|
| 3.1 | ScrollPosition, Window, WindowIterator | Can design batch scrolling instead of deep offset pages |
| 3.2 | Limit | Use dynamic limits instead of many fixed TopN methods |
| 3.5.0 | Specification.where(nullable) deprecated | Start removing null Specifications from code |
| 3.5.2 | Specification.unrestricted() | Use explicit API for unapplied filters |
| 4.0 | PredicateSpecification, UpdateSpecification, DeleteSpecification | Separate simple predicates from query-bound Specification |
| 4.0 | Specification.where(Specification) no longer accepts null | Switch to unrestricted() |
| 4.x | SpecificationFluentQuery supports limit, projection, page, slice, scroll, and stream | Centralize result configuration inside findBy callbacks |

Version milestones refer to Spring Data API versions, not Spring Boot versions. Check the BOM to see which release train Spring Boot pulls in.

## 29. Performance and execution limits

**Page and count query**

Page may require a count query to compute totalElements. For queries with joins, distinct, or subqueries, the count query can be costly. Slice avoids the total count.

**Offset scrolling**

Deep offsets can force the database to process many skipped rows. Do not use very deep offset pages for multi-million-row batches.

**Keyset scrolling**

Keyset requires a stable sort, non-null keys, and appropriate indexes. When sorting across multiple columns, indexes should reflect the filter conditions and that sort order.

**Limit**

Limit reduces the number of returned rows but does not automatically make a query fast. If filter conditions lack an index, the database may still scan many rows before finding N matches.

**Specification**

Specification builds dynamic queries, but does not guarantee a good query plan. Collection joins, subqueries, distinct, and OR can complicate queries. Inspect SQL and EXPLAIN.

**Fluent projection**

Use as/project when only a subset of data is needed. Projections can reduce data read and avoid unnecessary entity hydration.

## 30. Testing Limit, scrolling, and Specification

Include integration tests on a database matching production for features that depend on sorting, keyset, query translation, or count queries.

Cases to test:

- Limit.of(10) returns at most 10 results.
- Limit.unlimited() does not cap results.
- Limit rejects null.
- Sort is deterministic when multiple records share the same sort value.
- Top/First and Limit are not declared on the same method.
- Pageable and Limit are not combined.
- Page totalElements is accurate.
- Slice.hasNext() is accurate.
- First Window uses ScrollPosition.offset() or ScrollPosition.keyset().
- Next position does not duplicate the last element of the previous Window.
- Offset(0) does not accidentally skip the first element.
- Keyset works with non-null properties and proper indexes.
- Projections include the sort fields needed for keyset.
- String-based @Query is not expected to support scrolling.
- Specification.unrestricted() adds no predicate.
- PredicateSpecification composes AND/OR accurately.
- Specifications with subqueries still use query context.
- UpdateSpecification/DeleteSpecification affect only the intended rows.
- Empty anyOf/allOf follows API and business semantics.

## 31. Common errors and fixes

**1. Limit class not found**

The project may be using Spring Data Commons older than 3.2. Check the dependency tree and release train.

**2. ScrollPosition or Window not found**

The Scroll API requires Spring Data Commons 3.1 or higher and store module support. Check the actual versions.

**3. Passing null to Limit or Sort**

Use Limit.unlimited() and Sort.unsorted(). Special parameters require non-null values.

**4. Combining Pageable with Limit**

Invalid because Pageable already contains page size/limit. Choose one abstraction.

**5. Using Top10 together with Limit**

Do not combine two limiting mechanisms in one query method. Use fixed Top10 or dynamic Limit.

**6. Scrolling with @Query does not work**

Spring Data JPA does not currently support scrolling for string-based query methods. Switch to a derived method, Querydsl, Specification fluent API, or custom repository.

**7. Keyset skips or duplicates data**

Check whether the sort is stable, keys are non-null, projections include sort properties, and sort values are not mutated while scrolling.

**8. Offset scroll skips the first element**

Use ScrollPosition.offset() to start. ScrollPosition.offset(0) is exclusive and can skip the first row.

**9. Specification.where(null) fails after upgrading to 4.0**

Replace with Specification.unrestricted() or only construct Specifications when filters actually have values.

**10. PredicateSpecification does not compile on 3.x**

PredicateSpecification was introduced in Spring Data JPA 4.0. On 3.x, use traditional Specification.

**11. Specification does not generate the expected query**

Check whether toPredicate returns null or an actual predicate, AND/OR logic, and joins/subqueries.

**12. Page is very slow even though the content query is fast**

Inspect the count query separately. If total page count is unnecessary, switch to Slice or Window.

## 32. Process for evaluating new APIs

When considering Limit, scrolling, or Specification:

1. Identify the Spring Data JPA and Commons versions via the dependency tree.
2. Check which version introduced the API and whether the JPA module supports the query type in use.
3. Determine whether the UI needs Page, Slice, Limit, or Window.
4. For reading large batches, evaluate offset vs. keyset.
5. Choose a stable sort and matching index for keyset.
6. For dynamic filters, evaluate Specification and PredicateSpecification.
7. Keep Specification when CriteriaQuery/subqueries are needed.
8. Use UpdateSpecification/DeleteSpecification if on 4.0+ and needing bulk Criteria mutations.
9. Use Specification.unrestricted() instead of null Specifications.
10. Use the fluent API to configure limits, sorting, projections, and scrolling per use case.
11. Check limitations on string-based @Query and @Procedure.
12. Write integration tests against the target database.
13. Measure count queries, deep offsets, keysets, and projections.
14. Upgrade via the BOM/release train rather than upgrading a single module alone.

## 33. Self-assessment checklist

- [ ] I know how to check the actual Spring Data JPA/Commons versions.
- [ ] I know Limit appeared in Spring Data 3.2.
- [ ] I can distinguish Limit from Top/First and Pageable.
- [ ] I know Limit.unlimited() and not passing null.
- [ ] I know not to combine Pageable with Limit.
- [ ] I understand Page needs a count while Slice does not need a total count.
- [ ] I know ScrollPosition, Window, and WindowIterator from 3.1.
- [ ] I can distinguish offset scrolling from keyset scrolling.
- [ ] I know to use ScrollPosition.offset() to start.
- [ ] I understand ScrollPosition is exclusive.
- [ ] I know the sort/index/nullability requirements for keyset.
- [ ] I know string-based @Query and @Procedure have scrolling limitations.
- [ ] I can distinguish Specification from PredicateSpecification.
- [ ] I know PredicateSpecification appeared in Spring Data JPA 4.0.
- [ ] I know UpdateSpecification and DeleteSpecification.
- [ ] I know Specification.unrestricted() from 3.5.2.
- [ ] I do not pass null into Specification.where in 4.0.
- [ ] I know fluent Specification queries support limit, projection, page, slice, and scroll.
- [ ] I test the semantics of anyOf/allOf on empty lists.
- [ ] I inspect SQL, count queries, and execution plans.

## 34. Review questions

**1. Which version introduced Limit?**

Limit has been in Spring Data Commons since 3.2 and is integrated into query methods by supporting modules.

**2. How does Limit differ from Pageable?**

Limit only sets a maximum result count; Pageable carries page size, offset, and Sort, and can be used to produce Page metadata.

**3. Can Pageable and Limit be combined?**

No. Pageable already contains the limit and pagination position.

**4. Since when has the Scroll API existed?**

ScrollPosition, Window, and WindowIterator were introduced in Spring Data 3.1; specific availability depends on the store module.

**5. How do offset and keyset differ?**

Offset continues by the number of skipped rows; keyset continues from the sort column values of the last row in the previous Window.

**6. Why does keyset need non-null sort keys?**

Comparisons with NULL have varying semantics across databases and make reconstructing a stable continuation position difficult.

**7. Can Spring Data JPA scroll with every @Query?**

No. Scrolling with string-based @Query and stored @Procedure is not currently supported.

**8. Which version introduced PredicateSpecification?**

Spring Data JPA 4.0. It takes only From and CriteriaBuilder, making it suited for query-type-independent predicates.

**9. When is traditional Specification still needed?**

When you need CriteriaQuery, subqueries, or query-type-dependent logic. Traditional Specification remains appropriate for complex queries.

**10. Why should Specification.where(null) be replaced?**

This nullable API was deprecated in 3.5 and no longer accepts null in 4.0. Use Specification.unrestricted() to represent an unconditional state.

**11. What does fluent Specification query help with?**

It lets you configure sort, limit, projection, and choose result formats like first/all/page/slice/scroll/stream directly at the call site.

**12. When should Window be chosen instead of Page?**

When processing data in chunks without needing total page counts, especially when using keyset to read large datasets sequentially.

Choosing new APIs must begin with actual versions and the shape of the query to execute. Limit suits dynamic caps, Window suits positional reading, and Specification helps reuse dynamic filters. By clearly distinguishing the 3.1, 3.2, 3.5, and 4.0 milestones, development teams can upgrade in a controlled way, avoid calling APIs that do not exist yet, and pick query strategies suited to the database.

## References

- [Spring Data JPA 4.1 — Query Methods and Scrolling](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data Commons — Defining Query Methods, Paging and Limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons — ScrollPosition API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ScrollPosition.html)
- [Spring Data Commons — Limit API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Limit.html)
- [Spring Data JPA 3.5 — Specification API and deprecations](https://docs.spring.io/spring-data/jpa/reference/3.5/api/java/org/springframework/data/jpa/domain/Specification.html)
