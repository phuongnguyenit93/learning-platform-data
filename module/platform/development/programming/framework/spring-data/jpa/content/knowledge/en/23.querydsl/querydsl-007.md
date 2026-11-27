# Pagination, Sorting, and Controlling Count Queries with Querydsl

Querydsl lets you build dynamic queries with sorting and pagination while preserving the data types of Entity properties. In Spring Data JPA, there are two main levels of usage:

- **QuerydslPredicateExecutor:** provides convenient methods such as findAll(predicate, pageable). Spring Data manages both the content query and the count query.
- **Custom repository with JPAQueryFactory:** gives you control over SELECT, JOIN, ORDER BY, LIMIT/OFFSET, and a dedicated count query.

The choice depends on query complexity. Simple predicates can usually use QuerydslPredicateExecutor. When collection JOINs, DISTINCT, GROUP BY/HAVING, projections, or optimizing count cost become important, a custom repository gives clearer control over how data is fetched and how totals are calculated.

## 1. What Is Pagination in Querydsl?

Pagination splits a result set into smaller chunks. For example, a screen displays only 20 customers at a time instead of loading all customers into memory.

Spring Data represents pagination requests using Pageable. Pageable holds:
- Page number, zero-based.
- Page size.
- Sorting information.
- Offset computed from the page number and page size.

Example:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        )
);
~~~

This requests the first page, up to 20 elements, sorted by name then id. Adding id as a secondary criterion makes ordering deterministic when multiple customers share the same name.

With Querydsl, Spring Data translates Pageable into query limits and sorting. If returning `Page<T>`, the framework also needs to provide totalElements and totalPages, so a separate count query may be required.

## 2. Using QuerydslPredicateExecutor with Pageable

A repository can extend QuerydslPredicateExecutor:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Example building a predicate and calling findAll:

~~~java
QCustomer customer = QCustomer.customer;

BooleanBuilder predicate = new BooleanBuilder()
        .and(customer.active.isTrue());

if (keyword != null && !keyword.isBlank()) {
    predicate.and(customer.name.containsIgnoreCase(keyword));
}

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("name"),
                Sort.Order.asc("id")
        )
);

Page<Customer> page =
        customerRepository.findAll(predicate, pageable);
~~~

Spring Data executes a query matching the predicate and pageable, and supplies the total element count for the Page. The application can read:

~~~java
List<Customer> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

The advantage of this approach is minimal code and good fit for standard dynamic filters. The trade-off is less direct control over the count query structure. If you need DISTINCT, grouped queries, or custom counting, switch to a custom repository.

## 3. How Page, Slice, and List Differ

| Return type | Page data | Exact total count | Count query |
|---|---|---|---|
| Page<T> | Yes | Yes | May be needed |
| Slice<T> | Yes | No | No full count needed |
| List<T> with Pageable | Limited | No | No full count needed |

Page fits when the UI must display the total number of records or total pages. Slice fits a "Load more" button or advancing to the next page without needing a total count. List with Pageable returns only the bounded content.

QuerydslPredicateExecutor provides findAll(predicate, pageable) returning Page. If you need Slice or want to decide yourself how to fetch one extra row to check hasNext, write a custom query with JPAQueryFactory.

Do not pick Page just because you want to use Pageable. If the UI only needs content and whether more data exists, counting the entire result set can be an unnecessary expense.

## 4. Sorting with Sort

With QuerydslPredicateExecutor, you can pass Sort directly:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Iterable<Customer> customers =
        customerRepository.findAll(predicate, sort);
~~~

Property names in Sort are the Entity's Java property names, not SQL column names. For instance, use createdAt if the Entity declares createdAt, even though the database column might be named created_at.

When using Pageable, Sort can be embedded directly in PageRequest:

~~~java
Pageable pageable = PageRequest.of(
        1,
        25,
        Sort.by("createdAt").descending()
                .and(Sort.by("id").ascending())
);
~~~

Only use properties allowed for sorting. If Sort comes from a user request, whitelist valid property names; never pass raw arbitrary strings straight into query expressions.

## 5. Why Is Deterministic Sort Ordering Needed?

Pagination based on a non-deterministic order can cause duplicate or skipped records across calls.

Suppose multiple customers have the same name and the query only orders by `ORDER BY name`. The database is not required to preserve a stable order among rows with identical `name` values. When the first page and subsequent pages are fetched at different times, the ordering among ties can shift.

Append a unique key as a tie-breaker:

~~~java
.orderBy(customer.name.asc(), customer.id.asc())
~~~

This rule helps both offset pagination and keyset pagination. With composite primary keys, include enough components to uniquely determine the order.

## 6. When Is a Custom Repository with JPAQueryFactory Needed?

QuerydslPredicateExecutor fits finding Entities by Predicate. When you need explicit control over:
- JOINs and fetch joins.
- DTO projections.
- DISTINCT and counting unique Entities.
- GROUP BY/HAVING.
- Custom count queries.
- Whitelisted dynamic sorting.
- Skipping count queries when unnecessary.

use a custom repository with JPAQueryFactory.

Declare the fragment:

~~~java
public interface CustomerSearchRepository {
    Page<Customer> search(
            BooleanBuilder predicate,
            Pageable pageable
    );
}
~~~

Main repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerSearchRepository {
}
~~~

Fragment implementation following Spring Data conventions:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    // Implementation of search() is shown in the following sections.
}
~~~

You can declare JPAQueryFactory as a bean taking EntityManager:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Place the implementation in a package where Spring Data repository configuration can discover it. Do not place persistence queries directly inside controllers.

## 7. Applying Offset and Limit Manually

JPAQueryFactory lets you control bounds using offset() and limit():

~~~java
QCustomer customer = QCustomer.customer;

List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.name.asc(), customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();
~~~

Meaning:
- offset() skips rows preceding the page position.
- limit() caps the number of returned rows.
- fetch() executes the query and returns a List.

pageable.getOffset() returns a long, matching Querydsl's offset method. Pageable uses zero-based page indices.

This is only the content query. If you want to return `Page<Customer>`, you must still compute totalElements using a matching count query or use a Spring Data utility to defer counting.

## 8. Writing a Separate Count Query

Simple count query example:

~~~java
Long total = queryFactory
        .select(customer.id.count())
        .from(customer)
        .where(predicate)
        .fetchOne();

long totalElements = total == null ? 0L : total;
~~~

The count query must keep all filtering conditions that affect the result set. ORDER BY is unnecessary because the result is a single count.

You can wrap content and total into a Page:

~~~java
return new PageImpl<>(
        content,
        pageable,
        totalElements
);
~~~

PageImpl requires:
- The content list.
- The Pageable used to fetch the page.
- The total logical element count across the entire result set.

This example assumes each Customer appears once in the content query with no collection JOIN multiplying rows. If there is a collection JOIN, the count query may need `COUNT(DISTINCT customer.id)`.

## 9. Using PageableExecutionUtils to Avoid Unnecessary Counts

Spring Data provides `PageableExecutionUtils.getPage()`. This utility takes content, Pageable, and a `Supplier<Long>` so it only runs the count query when the total cannot be inferred from the page content.

Example:

~~~java
List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.name.asc(), customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();

return PageableExecutionUtils.getPage(
        content,
        pageable,
        () -> {
            Long total = queryFactory
                    .select(customer.id.count())
                    .from(customer)
                    .where(predicate)
                    .fetchOne();

            return total == null ? 0L : total;
        }
);
~~~

If the page content allows the framework to deduce the total, the Supplier may not be invoked. For example, a first page returning fewer items than the page size indicates no further results follow. When the page is full, the framework usually runs the count query to determine the total.

Crucially, do not call `fetchOne()` beforehand and pass the computed value into `getPage()`. Doing so runs the count query immediately, eliminating the deferral.

## 10. Complete Custom Repository Example for Simple Queries

Here is an implementation combining the content query, default sorting, and count query:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public Page<Customer> search(
            BooleanBuilder predicate,
            Pageable pageable) {

        QCustomer customer = QCustomer.customer;

        JPAQuery<Customer> query = queryFactory
                .selectFrom(customer)
                .where(predicate);

        query.orderBy(customer.name.asc(), customer.id.asc());

        List<Customer> content = query
                .offset(pageable.getOffset())
                .limit(pageable.getPageSize())
                .fetch();

        return PageableExecutionUtils.getPage(
                content,
                pageable,
                () -> {
                    Long total = queryFactory
                            .select(customer.id.count())
                            .from(customer)
                            .where(predicate)
                            .fetchOne();

                    return total == null ? 0L : total;
                }
        );
    }
}
~~~

This example covers a query filtering solely on Customer, with no collection JOINs and no GROUP BY. In a real application, handle `Pageable.unpaged()` if the API permits unpaged requests, and validate page sizes and maximum bounds in the service/API layer.

If Sort comes from Pageable, the `orderBy` clause should convert Sort to safe `OrderSpecifier` instances as shown in the next section.

## 11. Converting Sort to Safe OrderSpecifiers

JPAQueryFactory uses Querydsl's `OrderSpecifier` rather than accepting Spring Data's `Sort` directly. You can map allowed properties using a switch:

~~~java
private OrderSpecifier<?> toOrderSpecifier(
        Sort.Order order,
        QCustomer customer) {

    boolean ascending = order.isAscending();

    return switch (order.getProperty()) {
        case "name" ->
                ascending ? customer.name.asc() : customer.name.desc();

        case "createdAt" ->
                ascending ? customer.createdAt.asc()
                          : customer.createdAt.desc();

        case "id" ->
                ascending ? customer.id.asc() : customer.id.desc();

        default ->
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + order.getProperty()
                );
    };
}
~~~

Applying it in the query:

~~~java
List<OrderSpecifier<?>> orders = new ArrayList<>();

for (Sort.Order order : pageable.getSort()) {
    orders.add(toOrderSpecifier(order, customer));
}

if (orders.stream().noneMatch(
        order -> pageable.getSort().getOrderFor("id") != null)) {
    orders.add(customer.id.asc());
}

query.orderBy(orders.toArray(OrderSpecifier<?>[]::new));
~~~

In production code, check and append the ID tie-breaker cleanly. The illustrative snippet can be written more concisely by checking Sort before appending ID:

~~~java
boolean sortsById =
        pageable.getSort().getOrderFor("id") != null;

if (!sortsById) {
    orders.add(customer.id.asc());
}
~~~

Whitelisting avoids injecting arbitrary property names from requests into queries. If supporting ignoreCase or null handling, map those options explicitly. Do not assume every property is sortable or that all databases order NULLs identically.

## 12. Collection JOINs and COUNT(DISTINCT)

A collection JOIN can cause a single Entity to appear across multiple SQL result rows. In that case, a count query using `COUNT(entity.id)` can double-count.

Example where a Customer has multiple Orders:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> content = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();
~~~

Corresponding count:

~~~java
Long total = queryFactory
        .select(customer.id.countDistinct())
        .from(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .fetchOne();
~~~

`COUNT(DISTINCT customer.id)` counts each Customer once even if one customer has multiple matching Orders.

If you only need to check whether a matching order exists, you can write an EXISTS condition to avoid multiplying Customer rows via JOIN. Whether choosing JOIN or EXISTS, the count query must reflect the same logical set of Customers returned by the content query.

Do not apply `COUNT(DISTINCT)` mechanically. If the JOIN relationship cannot multiply the selected-side Entity, regular COUNT may suffice. Determine the relationship cardinality and verify actual results.

## 13. Count Queries for GROUP BY and HAVING

A grouped query returns one row per group. Therefore, `totalElements` must be the number of groups satisfying HAVING, not the number of source rows before grouping.

Example querying total orders by status:

~~~java
List<Tuple> groups = queryFactory
        .select(order.status, order.id.count())
        .from(order)
        .where(predicate)
        .groupBy(order.status)
        .having(order.id.count().goe(minimumCount))
        .fetch();
~~~

If a Page is needed for the grouped result, the count query must count how many statuses have groups reaching `minimumCount`. That is a different problem from counting Orders.

JPQL does not provide a standard derived table in FROM to wrap a GROUP BY query and apply an outer `COUNT(*)`. Querydsl JPA shares this limitation. For complex grouped counts, options include:
- Writing a separate equivalent query to count distinct group keys.
- Using native SQL with a derived table/CTE if supported by the database.
- Using a view or summary table if the report is queried frequently.
- Returning a Slice or a bounded list if an exact total group count is not needed.

Do not run a count query that merely counts source rows and assign it to a grouped Page. `totalElements` will be wrong whenever multiple source rows belong to the same group.

## 14. Why Shouldn't You Rely on fetchCount() for All Queries?

Some older Querydsl examples use:

~~~java
long total = query.fetchCount();
~~~

or:

~~~java
QueryResults<Customer> results = query.fetchResults();
~~~

The `fetchCount()` and `fetchResults()` APIs were deprecated in Querydsl 5.x. For queries with complex GROUP BY/HAVING, computing the result count may require loading all groups into memory and counting them instead of executing a simple SQL COUNT. That can be very expensive.

For simple queries, write an explicit count query using `select(count(...))`. For collection JOINs, consider `countDistinct()`. For grouped queries, design a dedicated group-counting query or use appropriate native SQL.

Do not replace a complex count query with `fetchCount()` without understanding the actual SQL and cost in your Querydsl version.

## 15. Avoiding Count Queries When You Only Need to Know If More Data Exists

If `totalElements` is not needed, you can fetch `pageSize + 1` elements. The extra element determines whether a next page exists.

Example:

~~~java
int pageSize = pageable.getPageSize();

List<Customer> rows = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageSize + 1L)
        .fetch();

boolean hasNext = rows.size() > pageSize;

List<Customer> content = hasNext
        ? rows.subList(0, pageSize)
        : rows;

return new SliceImpl<>(content, pageable, hasNext);
~~~

Slice has no totalElements or totalPages. This works well for "load more" UIs and avoids running a count query over the whole result set.

QuerydslPredicateExecutor does not offer the same custom count control for every Slice case; a custom repository enables implementing this `pageSize + 1` pattern.

## 16. Offset Pagination and Deep Page Costs

Offset pagination usually translates to LIMIT/OFFSET or equivalent syntax:

~~~sql
SELECT ...
FROM customers
ORDER BY id
LIMIT 20 OFFSET 100000;
~~~

When the offset is large, the database may have to scan and discard many rows before returning the 20 needed rows. Consequently, deeper pages can become progressively slower.

Offset remains useful when:
- Data size is modest.
- Users need to jump directly to a specific page number.
- Deep pages are uncommon.
- The query has suitable indexes and execution plans.

If you need to read sequentially across hundreds of thousands or millions of records, consider keyset/seek pagination.

## 17. Keyset Pagination with Querydsl

Keyset pagination uses the sort values of the last item already read to locate subsequent items. For example, sorting descending by createdAt then id:

~~~java
.orderBy(customer.createdAt.desc(), customer.id.desc())
~~~

After reading the last item with `createdAt = lastCreatedAt` and `id = lastId`, the next-batch condition is:

~~~java
BooleanExpression afterCursor =
        customer.createdAt.lt(lastCreatedAt)
                .or(
                    customer.createdAt.eq(lastCreatedAt)
                            .and(customer.id.lt(lastId))
                );
~~~

Next query:

~~~java
List<Customer> nextBatch = queryFactory
        .selectFrom(customer)
        .where(predicate, afterCursor)
        .orderBy(customer.createdAt.desc(), customer.id.desc())
        .limit(batchSize)
        .fetch();
~~~

Because the order is descending, subsequent records have a smaller createdAt; if createdAt is equal, ID must be smaller. If sorting ascending, switch comparisons to greater-than.

Keyset avoids the cost of skipping large offsets, but requires:
- Deterministic sorting with a unique secondary key.
- Non-null values in cursor fields.
- Cursor preserving exact values of the last element.
- Indexes aligned with filter conditions and sort order.
- Explicit handling of data modifications during scrolling.

Keyset fits "next" feeds or batch processing; it is not convenient for jumping directly to page 500 like offset pagination.

## 18. Designing Indexes for Paginated Queries

Indexes should reflect common filter conditions and sort orders.

Example:

~~~sql
SELECT *
FROM customers
WHERE active = true
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

You can consider a composite index:

~~~sql
CREATE INDEX idx_customers_active_created_id
ON customers (active, created_at DESC, id DESC);
~~~

This is only a directional example. Actual index design depends on the database engine, selectivity of `active`, tenant conditions, other filters, and write workload.

For foreign-key JOIN queries, an index on the foreign key can help locate related records. For `COUNT(DISTINCT)`, the database may require a sort or hash step to deduplicate.

Use EXPLAIN or EXPLAIN ANALYZE to check:
- Is the index used?
- How many rows are read?
- Is there a large sort or hash aggregate?
- Is the count query more expensive than the content query?
- Do deep pages increase cost noticeably?

Do not create indexes based solely on method names. Measure on production-like data and weigh INSERT/UPDATE/DELETE overhead and storage cost.

## 19. Consistency Under Concurrent Data Changes

Content queries and count queries are usually two separate SQL statements. If another transaction inserts or deletes records between executions, `totalElements` may not match the content just read.

Offset pagination is also sensitive to inserts/deletes occurring before the offset position. Keyset depends less on skipped row counts, though it can still be affected if sort values change or records are deleted.

If business requirements demand a consistent snapshot, evaluate transaction isolation levels and database snapshot capabilities. For long batch/export jobs, bound the dataset by a timestamp or maximum ID captured at start. If a process retries, make processing idempotent to avoid duplicate writes.

Do not assume Page or a cursor automatically guarantees an immutable snapshot under all isolation levels.

## 20. Testing Pagination and Count Queries

An integration test should verify both content and `totalElements`:

~~~java
@DataJpaTest
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void returnsCorrectPageAndTotal() {
        repository.save(new Customer("An", true));
        repository.save(new Customer("Binh", true));
        repository.save(new Customer("Chi", false));

        Pageable pageable = PageRequest.of(
                0,
                1,
                Sort.by("id").ascending()
        );

        Page<Customer> page =
                repository.findAll(
                        QCustomer.customer.active.isTrue(),
                        pageable
                );

        assertEquals(1, page.getContent().size());
        assertEquals(2, page.getTotalElements());
        assertEquals(2, page.getTotalPages());
        assertTrue(page.hasNext());
    }
}
~~~

The example requires the Customer Entity to have a matching constructor and the Repository to extend QuerydslPredicateExecutor. QCustomer must be generated by the annotation processor.

For custom count queries, add test cases for:
1. Empty result set: totalElements equals 0.
2. Fewer results than page size.
3. Full page and final page.
4. Collection JOIN with multiple related records for the same Entity.
5. COUNT(DISTINCT) returning the accurate count of unique Entities.
6. GROUP BY/HAVING counting groups rather than source rows.
7. Sort with duplicate values and ID as tie-breaker.
8. Keyset without duplicates or skipped rows on stable data.
9. Native count query executing on the target database.
10. Tenant and soft-delete filters applied consistently to both content and count.

Measure SQL and execution plans on a production-like database. H2 or a few rows of test data are not enough to evaluate count cost on large tables.

## 21. Common Pitfalls

**Paginating the content query while forgetting the count**

If returning a manually constructed Page, totalElements must reflect the full result set. Use a matching count query or PageableExecutionUtils.

**Count query missing WHERE conditions**

Page content may be right while totalElements is inflated. Keep every condition that affects the result set.

**Double counting after a collection JOIN**

Use `COUNT(DISTINCT entity.id)` when the query logically returns unique Entities but the JOIN produces multiple rows.

**Counting source rows instead of groups**

With GROUP BY/HAVING, the count must count groups satisfying the condition.

**Putting ORDER BY in the count query**

Usually unnecessary and can add extra cost. Counting only needs the total number.

**Passing input Sort straight into dynamic property names**

Whitelist allowed properties and sort directions. Never let clients control arbitrary identifiers.

**Missing tie-breaker**

Non-unique sorting can cause records to duplicate or disappear across pages. Append the primary key at the end of the ordering.

**Using Page in a feed that only needs "load more"**

Use Slice or `pageSize + 1` to avoid unnecessary counts.

**Using fetchCount() on complex grouped queries**

Legacy `fetchCount()`/`fetchResults()` APIs are deprecated in Querydsl 5.x and may count groups by loading results into memory. Write a dedicated count query or use suitable native SQL.

**Using very deep offsets for large batches**

Consider keyset pagination with deterministic sorting and suitable indexes.

**Assuming count and content always see the same snapshot**

Two SQL queries can observe data at different points in time depending on the isolation level.

## 22. Workflow for Choosing Pagination and Counting Strategies

When designing Querydsl queries, follow these steps:

1. Determine whether the UI needs an exact total count.
2. Use QuerydslPredicateExecutor if predicates and pagination are simple.
3. Use a custom repository with JPAQueryFactory when control over JOINs, projections, DISTINCT, or counts is needed.
4. Establish deterministic ordering with ID as a tie-breaker.
5. Map Sort via a whitelist to OrderSpecifier.
6. For Page, keep the count query aligned with the logical result set.
7. For collection JOINs, check for duplicates and consider countDistinct().
8. For GROUP BY/HAVING, count groups rather than source rows.
9. Use PageableExecutionUtils when the total can be inferred without running a count.
10. Use Slice/`pageSize + 1` if totalElements is not needed.
11. Use keyset when scanning large datasets sequentially with a suitable sort key.
12. Verify indexes, SQL, execution plans, transaction isolation, and integration tests on the target database.

## 23. Conclusion

Querydsl integrates with Pageable via QuerydslPredicateExecutor to generate Pages and automatic counts; when deeper control is needed, a custom repository with JPAQueryFactory lets you write separate content and count queries. Use `COUNT(DISTINCT id)` when collection JOINs duplicate Entities, count groups when using GROUP BY/HAVING, and use PageableExecutionUtils to defer counting whenever the total can be inferred. Page fits when an exact total is required; Slice fits when you only need to know if more data remains. Offset is straightforward to implement but can slow down on deep pages, whereas keyset suits large sequential streams with deterministic ordering and good indexes. Always verify SQL, execution plans, and the accuracy of totalElements through integration tests.