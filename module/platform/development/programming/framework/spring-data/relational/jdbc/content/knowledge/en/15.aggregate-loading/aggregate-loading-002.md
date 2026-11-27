# Number of Queries When Reading an Aggregate or a List

When calling a repository in Spring Data JDBC, the application usually expects to receive a **complete aggregate**: the root together with the entities owned by the root. Because Spring Data JDBC does not use lazy proxies like JPA/Hibernate, the mapped parts of the aggregate are loaded during the repository read operation. This loading behavior directly affects how many SQL statements are executed.

There are two strategies to distinguish:

- **Traditional loading:** queries the root first, then executes separate SQL statements to load referenced entities. When reading a list of many roots with collections, this approach can produce an N+1 pattern.
- **Single Query Loading:** introduced in Spring Data JDBC 3.2, allows loading multiple complete aggregates in a single SELECT statement if the model and query method meet the supported conditions.

The number of SQL statements depends not only on the number of records returned. It also depends on the aggregate structure, number of collections, nesting depth, repository method type, pagination, and the active loading strategy.

This lesson uses an order example with multiple order lines and notes:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- OrderLine (0..n)
    |
    +-- OrderNote (0..n)
~~~

The goal is to understand how to estimate query counts, recognize N+1, know when Single Query Loading can reduce round-trips, and measure using SQL logs.

## 1. A single repository call can produce multiple SQL statements

Consider a simple aggregate:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Each `OrderLine` is stored in a separate table and has a foreign key `order_id` pointing to `purchase_orders.id`.

Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

When calling:

~~~java
PurchaseOrder order = repository.findById(100L).orElseThrow();
~~~

The expected result is a `PurchaseOrder` containing its `lines` list. In the traditional loading strategy, Spring Data JDBC runs a query to fetch the root, then a separate query to fetch the collection:

~~~sql
-- Query 1: aggregate root
SELECT *
FROM purchase_orders
WHERE id = :id;

-- Query 2: child entities
SELECT *
FROM order_lines
WHERE order_id = :id;
~~~

For an aggregate with one collection, this example typically requires **2 SELECT statements**. If the root also has another collection, that collection must also be loaded in a separate statement under the traditional strategy.

The key point: both SQL statements execute during `findById(...)`. Calling the `order.getLines()` getter afterward merely reads an already materialized collection; the getter does not trigger a new lazy query.

## 2. Counting queries when reading a single aggregate

For a single root, you can estimate based on structure:

| Aggregate structure | Traditional loading, illustrative |
|---|---:|
| Root only, no referenced entities | 1 SELECT |
| Root with one collection | 1 SELECT root + 1 SELECT collection |
| Root with two direct collections | 1 SELECT root + 2 SELECT collection |
| Root with a collection nested inside a child | Root + SELECT child + SELECT child's collection |
| Root with multiple collection levels | Additional statements for collection relationships at each level |

Example:

~~~text
PurchaseOrder
    |
    +-- List<OrderLine>
    |
    +-- List<OrderNote>
~~~

In traditional mode:

~~~text
1. SELECT purchase_orders
2. SELECT order_lines
3. SELECT order_notes

Illustrative total: 3 SELECT statements
~~~

If there are nested relationships:

~~~text
PurchaseOrder
    |
    +-- List<Shipment>
             |
             +-- List<Parcel>
~~~

A single aggregate may require:

~~~text
1. SELECT purchase_orders
2. SELECT shipments
3. SELECT parcels

Illustrative total: 3 SELECT statements
~~~

This is a way of counting by relationship loading steps. The specific mapping structure, relationship types, and Spring Data JDBC version can affect the actual SQL; therefore, the numbers in the table serve as a reasoning model rather than a fixed guarantee for every mapping.

### 2.1. Row count is not query count

An order with 100 order lines can still be loaded with one SELECT for the root and one SELECT for the collection when reading a single aggregate under the traditional strategy.

~~~text
PurchaseOrder #100
    100 OrderLine

SQL:
    1 SELECT purchase_orders
    1 SELECT order_lines WHERE order_id = 100
~~~

The database returns 100 child rows in the second ResultSet. That is **100 result rows**, not 100 queries.

Distinguish between:

- Query count: the number of SQL statements executed.
- Result row count: the number of rows returned by the database.
- Network round-trip: the actual number of communications between the application and the database, which may depend on the driver, batching, and execution path.
- Processing time: time spent by the database executing SQL, transferring data, and Spring building the object graph.

Reducing query count often helps reduce round-trips, but it does not automatically guarantee faster queries if the new SQL returns too much data or has a poor execution plan.

## 3. Reading a list of multiple aggregates and the N+1 problem

The issue becomes evident when reading many roots at once.

Suppose a repository has 100 orders, each with a `lines` collection. In the traditional loading strategy, Spring Data JDBC loads the root list first, then loads referenced entities for each root in separate statements.

~~~text
N = 100 PurchaseOrder

1. SELECT * FROM purchase_orders

2. SELECT * FROM order_lines WHERE order_id = 1
3. SELECT * FROM order_lines WHERE order_id = 2
4. SELECT * FROM order_lines WHERE order_id = 3
...
101. SELECT * FROM order_lines WHERE order_id = 100
~~~

Total:

\[
Q = 1 + N
\]

With 100 orders and one collection to load per order:

\[
Q = 1 + 100 = 101
\]

This is the **N+1 query** pattern:

- 1 query fetches the list of roots.
- N subsequent queries load the collection for each of the N roots.

If each root has two independent collections, such as `lines` and `notes`, the model can become:

\[
Q = 1 + 2N
\]

With 100 roots:

\[
Q = 1 + 2 \times 100 = 201
\]

If there are nested collections, the number of statements can continue to grow with the number of parent objects at each level.

### 3.1. Example with two collection levels

~~~text
PurchaseOrder
    |
    +-- Shipment
            |
            +-- Parcel
~~~

Suppose there are 100 orders, each order has 2 shipments, and each shipment has a parcel collection.

Under traditional loading, the illustrative query pattern is:

- 1 SELECT to fetch the 100 orders.
- 100 SELECTs to fetch the shipments of each order.
- 200 SELECTs to fetch the parcels of each shipment.

Total:

\[
Q = 1 + 100 + 200 = 301
\]

The count depends on the actual number of parent objects at each level, not just the number of roots. If an order has no shipments, there are no parcel collections beneath that order to load.

### 3.2. Why does a single findAll call still produce N+1?

The method name `findAll()` only tells us that the application invokes one repository operation. It does not mean the database receives only one SQL statement under all loading strategies.

Spring Data JDBC must build complete aggregates. In the traditional approach, each root is read, and then referenced entities are loaded with separate statements. When there are N roots and a collection, the collection-loading statements can repeat per root.

This is why you should observe actual SQL rather than counting Java method calls.

## 4. Comparing reading one root vs. reading a list

The same aggregate can produce different query counts depending on how many roots are loaded:

| Operation | Roots loaded | One collection per root, traditional strategy |
|---|---:|---:|
| `findById(100L)` | 1 | 2 SELECTs |
| `findAllById(ids)` with 10 IDs | 10 | 1 + 10 = 11 SELECTs |
| `findAll()` returning 100 roots | 100 | 1 + 100 = 101 SELECTs |
| `findAll()` returning 1,000 roots | 1,000 | 1 + 1,000 = 1,001 SELECTs |

This is the N+1 pattern described for an aggregate with one collection. If each root has multiple collections or multiple levels, the statement count grows with the relationships that need to be loaded.

A practical consequence: querying a single aggregate by ID may be fast, while using `findAll()` on the same design for hundreds of aggregates generates many round-trips.

Do not benchmark only `findById()` and assume list screens will have similar performance.

## 5. How does Single Query Loading solve the problem?

Spring Data JDBC 3.2 introduced **Single Query Loading**. For eligible aggregates and query methods, Spring Data JDBC can load multiple complete aggregates in a single SELECT statement.

~~~text
Traditional loading:

SELECT roots
    |
    +-- SELECT children for root 1
    +-- SELECT children for root 2
    +-- SELECT children for root 3
    +-- ...
    +-- SELECT children for root N

Single Query Loading:

SELECT roots + collections in one SQL statement
    |
    v
Construct multiple aggregates from the ResultSet
~~~

With 100 orders that each have one collection:

| Strategy | Illustrative query count |
|---|---:|
| Traditional loading | 101 |
| Eligible Single Query Loading | 1 |

Single Query Loading uses window functions such as `row_number()` and `count()` to represent collection elements within a single ResultSet while avoiding duplicating all root data via a Cartesian product across multiple collections.

It is not simply joining every table and accepting a bloated ResultSet. The generated SQL is structured to align collection elements by their positions.

### 5.1. Why not join collections naively?

Suppose an order has:

- 5 order lines.
- 4 notes.
- 3 charges.

Joining all three collections directly can produce:

\[
5 \times 4 \times 3 = 60
\]

result rows for a single order, even though the aggregate actually contains only 12 child elements.

This is **Cartesian multiplication**: independent collections multiply row counts together and duplicate root data as well as data from other collections.

Single Query Loading uses window functions and row-number alignment to avoid this naive data multiplication.

## 6. Conditions and limitations of Single Query Loading

Single Query Loading does not automatically apply to every aggregate and every repository method.

According to current Spring Data Relational documentation, the main conditions include:

1. The aggregate has no nested collections, including `Map`.
2. The aggregate does not use `AggregateReference` or embedded entities.
3. The database dialect must support it. Among the dialects provided by Spring Data JDBC, H2 and HSQL are not supported for this strategy; the remaining dialects are supported.
4. The strategy applies to `CrudRepository` find methods; derived queries and `@Query`-annotated methods are excluded.
5. The Single Query Loading flag must be enabled on `JdbcMappingContext`.

If any condition is not met, Spring Data JDBC falls back to the default loading strategy.

**Version note:** Single Query Loading was introduced in Spring Data JDBC 3.2, and current documentation still describes it as an experimental feature. Check the documentation for the exact Spring Data JDBC version your application uses before relying on it in performance-critical designs.

### 6.1. Multiple direct collections vs. nested collections

Example of an aggregate with two direct collections:

~~~java
class PurchaseOrder {

    @Id
    Long id;

    List<OrderLine> lines;
    List<OrderNote> notes;
}
~~~

This structure can qualify for Single Query Loading if the remaining conditions are met.

However, an aggregate with a nested collection:

~~~java
class PurchaseOrder {

    @Id
    Long id;

    List<Shipment> shipments;
}

class Shipment {

    List<Parcel> parcels;
}
~~~

This is a nested collection, so Single Query Loading does not currently support this case according to the documented limitations.

### 6.2. Enabling Single Query Loading

You can configure `JdbcMappingContext` in your JDBC configuration:

~~~java
@Configuration
class DataJdbcConfig extends AbstractJdbcConfiguration {

    @Override
    public JdbcMappingContext jdbcMappingContext(
            Optional<NamingStrategy> namingStrategy,
            JdbcCustomConversions customConversions,
            RelationalManagedTypes jdbcManagedTypes
    ) {
        JdbcMappingContext context = super.jdbcMappingContext(
                namingStrategy,
                customConversions,
                jdbcManagedTypes
        );

        context.setSingleQueryLoadingEnabled(true);
        return context;
    }
}
~~~

Imports and method signatures must match the Spring Data Relational version in use. If the application already customizes `AbstractJdbcConfiguration` or `JdbcMappingContext`, integrate the flag into the existing configuration to avoid registering two mapping context beans.

When the flag is enabled, the framework **will attempt to use** Single Query Loading when the dialect and aggregate qualify. Enabling the flag does not mean every method is guaranteed to run in a single query.

## 7. Repository methods affect query count

Not only the aggregate structure, but also the method type affects the loading strategy.

| Method | Meaning | Query count considerations |
|---|---|---|
| `findById(id)` | Loads one aggregate by ID | Root and referenced parts; can use Single Query Loading if eligible |
| `findAll()` | Loads a list of aggregates | Can cause N+1 under the traditional strategy |
| `findAllById(ids)` | Loads aggregates by a set of IDs | Also needs consideration of root count and collections |
| Derived query | Finds aggregates by root property | Loads aggregates using the default strategy; does not use Single Query Loading under current limitations |
| `@Query` | Developer-declared SQL | Custom queries do not use Single Query Loading |
| `findAll(Pageable)` | Loads one page of aggregates | Runs a page query, possibly a count query, then loads referenced parts |
| `findAll(Sort)` | Loads a sorted list | Follows the aggregate loading strategy of the corresponding method |

### 7.1. A derived query does not mean only one table is read

Example:

~~~java
List<PurchaseOrder> findByStatus(String status);
~~~

A derived query generates the condition to find roots by the `status` property. If the method returns aggregates, referenced parts still need to be loaded via the aggregate loading mechanism.

A short method name does not mean only one SQL statement is executed.

### 7.2. `@Query` also requires understanding result mapping

Example:

~~~java
@Query("SELECT * FROM purchase_orders WHERE status = :status")
List<PurchaseOrder> findOpenOrders(String status);
~~~

The custom SQL fetches the roots. When the results are mapped into aggregates, Spring Data JDBC may still emit separate queries to load referenced entity collections. `@Query` does not automatically join and materialize every collection.

Spring Data JDBC documentation also states that mapping from string-based queries uses a RowMapper for the root, embedded entities, and one-to-one relationships, whereas collections such as Map, List, Set, and arrays of entities are loaded via separate queries.

Therefore, when you need a joined report result, consider a DTO/read model instead of returning full aggregates.

## 8. Pagination: what extra queries do Page and Slice add?

Pagination changes query counts in specific ways.

### 8.1. Page

`Page<T>` needs to know the total number of elements to provide total pages and total records. Spring Data JDBC may execute:

1. A query to fetch roots within the page range.
2. A count query to compute total records, if needed.
3. Queries to load referenced entities for the aggregates on the page according to the active loading strategy.

Example of a page of 20 orders, each with one collection, under traditional loading:

~~~text
SELECT purchase_orders ... LIMIT 20 OFFSET ...
SELECT COUNT(*) FROM purchase_orders ...
SELECT order_lines ... (for root 1)
SELECT order_lines ... (for root 2)
...
SELECT order_lines ... (for root 20)
~~~

Illustrative maximum query count for this pattern:

\[
Q = 1 + 1 + 20 = 22
\]

Where:

- 1 query fetches the page of roots.
- 1 query counts the total.
- 20 queries load collections for the roots on the page.

The query count can be lower if Spring Data determines the count query is unnecessary, such as when the total can be inferred from the page content.

### 8.2. Slice

`Slice<T>` only needs to know whether there is a next page. Spring Data fetches `LIMIT + 1` rows to determine whether more data exists, avoiding the total count query used by `Page`.

With 20 elements in a slice and one collection per root, the traditional loading pattern:

~~~text
SELECT purchase_orders ... LIMIT 21
SELECT order_lines ... (for each root kept in the slice)
~~~

Illustrative query count:

\[
Q \approx 1 + 20
\]

The actual number of materialized roots can be 20; the 21st row only helps determine `hasNext`.

### 8.3. Pagination does not solve N+1 by itself

Pagination limits the number of roots in a single read, but if each root still needs its own collection queries, the query count still scales with the page size.

For example, a page of 100 roots can still produce around 101 queries for one collection under the traditional strategy. Choosing a smaller page size reduces queries per request, but increases the number of requests needed to traverse all data.

## 9. Reading lists purely for display: do you really need to load aggregates?

An order list screen typically only needs:

- Order ID.
- Order code.
- Status.
- Customer name.
- Total amount.
- Created date.

If you call:

~~~java
List<PurchaseOrder> orders = repository.findAll();
~~~

the application may load order line collections, notes, and other aggregate components even though the screen does not use them.

That is unnecessary read overhead.

When only a summary list is needed, use a **read query or DTO projection** to select just the required columns.

Example with `NamedParameterJdbcTemplate`:

~~~java
public record PurchaseOrderSummary(
        Long id,
        String orderCode,
        String status,
        BigDecimal totalAmount
) {
}
~~~

~~~java
@Repository
public class PurchaseOrderSummaryQuery {

    private final NamedParameterJdbcTemplate jdbc;

    public PurchaseOrderSummaryQuery(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    public List<PurchaseOrderSummary> findSummaries(String status) {
        String sql = """
            SELECT
                o.id,
                o.order_code,
                o.status,
                COALESCE(SUM(l.quantity * l.unit_price), 0) AS total_amount
            FROM purchase_orders o
            LEFT JOIN order_lines l ON l.order_id = o.id
            WHERE o.status = :status
            GROUP BY o.id, o.order_code, o.status
            ORDER BY o.id DESC
            """;

        return jdbc.query(
                sql,
                Map.of("status", status),
                (rs, rowNum) -> new PurchaseOrderSummary(
                        rs.getLong("id"),
                        rs.getString("order_code"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                )
        );
    }
}
~~~

This query returns DTOs for the screen. It does not require building `PurchaseOrder` objects along with every aggregate's collections.

Remember: this is a **read model**. Business operations that modify an order should still load the aggregate root and invoke domain behavior by design.

### 9.1. Choosing a read model does not mean breaking the aggregate

You can organize two read paths:

~~~text
Command / write operations:
    PurchaseOrderRepository
        -> Load full aggregate
        -> Check invariants
        -> Save aggregate

Query / display screens:
    PurchaseOrderSummaryQuery
        -> SQL projection / DTO
        -> Fetch only display columns
~~~

An aggregate can be loaded in full when business logic needs to execute, while lists and reports use dedicated read-optimized queries.

## 10. Streaming large lists

If you need to process many aggregates, returning `List<T>` can cause the entire result set to be held in memory.

Spring Data JDBC supports some query methods returning `Stream<T>`, allowing elements to be supplied as data becomes available. However, a Stream keeps the database connection open and must be closed.

Example:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Stream<PurchaseOrder> streamAllByStatus(String status);
}
~~~

Usage:

~~~java
@Transactional(readOnly = true)
public void processOrders(String status) {

    try (Stream<PurchaseOrder> orders =
                 repository.streamAllByStatus(status)) {

        orders.forEach(this::process);
    }
}
~~~

Notes:

- Always close the Stream using try-with-resources.
- The connection is held while the Stream is being consumed.
- Manage transactions and processing duration so connections are not held open for too long.
- Streaming reduces the need to hold the entire root list in memory, but does not automatically turn collection loading into a single query.
- If each aggregate is still loaded with multiple statements, query counts still need to be measured.

Streaming is suitable for batch processing, not necessarily for HTTP requests that need fast responses.

## 11. How to measure query counts in an application

Do not infer query counts solely from the number of repository calls. Observe the actual SQL.

### 11.1. Enabling JDBC logging

You can enable logging in `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc: DEBUG
~~~

Or `application.properties`:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

Logs help observe the SQL statements executed by Spring JDBC. In high-traffic environments, enable SQL logging only during investigation because logs can grow very large and expose sensitive information in bind parameters depending on configuration.

### 11.2. Counting the right types of statements

When measuring, classify them:

- Queries fetching aggregate roots.
- Queries loading collections/referenced entities.
- Pagination count queries.
- Additional queries explicitly invoked by the service.
- Existence checks or other business queries.
- Initialization/metadata queries outside the use case being benchmarked.

Do not add every startup SQL statement in the log to the query count of a single repository operation.

### 11.3. Integration tests to measure SQL

You can use a datasource proxy or JDBC instrumentation tool in integration tests to count statements for an operation.

Example workflow:

1. Prepare fixed test data: 10 orders, each with 3 lines.
2. Reset the SQL counter before calling the repository.
3. Call `findAll()` or `findAllById(ids)`.
4. Count root SELECTs and collection SELECTs.
5. Repeat with Single Query Loading if the aggregate is eligible.
6. Compare query count, total row count, and execution time.

Do not benchmark only on an in-memory database and draw conclusions for PostgreSQL/MySQL. Dialect, driver, indexes, data, and execution plans all affect results.

## 12. A complete comparison example

Suppose there are 50 orders. Each order has 2 direct collections: `lines` and `notes`.

### Traditional loading

~~~text
1 SELECT purchase_orders

50 SELECT order_lines
50 SELECT order_notes

Total: 101 SELECT statements
~~~

Formula:

\[
Q = 1 + N \times C
\]

Where:

- `N`: number of aggregate roots loaded.
- `C`: number of direct collections loaded per root.

With `N = 50`, `C = 2`:

\[
Q = 1 + 50 \times 2 = 101
\]

### Single Query Loading

If the aggregate meets all conditions and the method is within the supported scope:

~~~text
1 SELECT generated to load:
    purchase_orders
    order_lines
    order_notes

Total: 1 SELECT statement
~~~

This query may return more rows than a simple root query, but it is designed to represent collections without creating unnecessary Cartesian products.

### Summary list with a DTO

If the screen only needs ID, status, and total amount, a SQL projection may suffice:

~~~text
1 SELECT purchase_orders
    JOIN order_lines
    GROUP BY purchase_orders
    -> List<PurchaseOrderSummary>

Total: 1 SELECT statement
~~~

This read path does not construct full aggregates. Choose based on purpose: business logic needs aggregates, list screens need projections.

## 13. Things not to confuse

| Assumption | Accurate understanding |
|---|---|
| `findAll()` always runs only one SELECT | Traditional loading can produce N+1 when aggregates have collections |
| An aggregate with 100 children always needs 101 queries | A single root with one collection usually needs a root query and a child query; 100 is the result row count, not the query count |
| N+1 only happens in JPA/Hibernate | Spring Data JDBC can also hit N+1 when loading a list of aggregates with collections |
| Calling a collection getter triggers SQL | Spring Data JDBC loads aggregates during the repository read; getters are not lazy proxies |
| Enabling Single Query Loading turns every query into one statement | Only applies when the aggregate, dialect, and repository method are eligible |
| `@Query` automatically joins every collection | Entity collections may still be loaded with separate statements |
| `Page<T>` and `Slice<T>` have the same query count | Page may add a count query; Slice uses LIMIT+1 |
| `Stream<T>` eliminates N+1 | Streaming mainly helps consume results; it does not change the aggregate loading strategy by itself |
| One query is always faster than multiple queries | Must consider returned data, execution plan, indexes, network, and object construction cost |
| DTO queries replace repositories for all operations | DTO/read queries are for reading; domain operations still need aggregates and invariants |

## 14. Process for analyzing query count on a screen

When an endpoint or screen is slow, proceed in order:

**Step 1 — Identify the needed data.** Does the screen need the full aggregate or only a few columns?

**Step 2 — Identify the number of roots.** One root by ID, a list of 20 items, or thousands of items?

**Step 3 — Sketch the loaded structure.** How many collections does the root have? Are there nested collections? Are there one-to-one references or `AggregateReference` fields?

**Step 4 — Identify the method.** `findById`, `findAll`, `findAllById`, derived query, `@Query`, `Page`, or `Stream`?

**Step 5 — Identify the strategy.** Traditional loading, or is Single Query Loading enabled and eligible?

**Step 6 — Estimate query count.** Include root queries, collection queries, count queries, and any extra queries called by the service.

**Step 7 — Enable SQL logging.** Compare your estimate with the actual statements executed.

**Step 8 — Choose an optimization.** Single Query Loading, fewer roots per page, read DTOs, SQL projections, redesigning aggregates, or intentional custom queries.

**Step 9 — Re-measure.** Compare query count, total rows, transferred data, database time, and endpoint duration.

~~~text
Use case / screen
       |
       v
Need full aggregate?
       |
       +---- Yes -----------------------------+
       |                                      |
       v                                      v
Count roots N                          Sketch aggregate structure
       |                                      |
       +----------------+---------------------+
                        |
                        v
               Identify repository method
                        |
                        v
               Single Query Loading eligible?
                    /             \
                  Yes              No
                  |                  |
                  v                  v
               One SQL           Root + statements
                                  for references
                                       |
                                       v
                                  Check for N+1
                                       |
                                       v
                                Measure actual SQL
                                       |
                                       v
                              Optimize for purpose
~~~

## 15. Reasoning exercises

**Scenario A — An aggregate with 20 order lines**

Calling `findById(10L)` under the traditional strategy. Can we conclude there are 21 queries?

**Hint:** No. With one root and one collection, the pattern is typically one root query and one collection query. 20 is the number of result rows in the collection.

**Scenario B — A list of 100 aggregates, each root having one collection**

How many queries can traditional loading produce?

**Hint:** Following the N+1 pattern, 1 root query plus 100 collection queries, totaling 101.

**Scenario C — A list of 100 aggregates, each root having two collections**

If both collections are loaded under the traditional strategy, what is the illustrative query count?

**Hint:** `1 + 2 × 100 = 201`.

**Scenario D — A Page of 20 orders**

What kind of query can `Page<PurchaseOrder>` add besides root and collection queries?

**Hint:** A `COUNT(*)` query to determine the total number of records, if Spring Data needs to run a count query.

**Scenario E — An aggregate with a nested collection**

Can you enable Single Query Loading and assume every level is loaded with a single SQL statement?

**Hint:** No. Nested collections, including Map, are among the current limitations; the framework can fall back to traditional loading.

**Scenario F — A screen displaying only order number and status**

Do you need to load the entire aggregate along with its collections?

**Hint:** Not necessarily. A read query returning a DTO with only the needed columns can save many queries and memory.

## 16. Key takeaways

| Concept | Meaning |
|---|---|
| Aggregate loading | Loading the root and its referenced entities |
| Traditional loading | Root and references are loaded via multiple statements |
| N+1 | One query fetches N roots, then N queries load collections |
| Single Query Loading | Can load multiple aggregates in one SQL statement if eligible |
| Nested collection | One of the current limitations of Single Query Loading |
| `Page<T>` | May add a count query |
| `Slice<T>` | Uses `LIMIT + 1` to check for a next page |
| `Stream<T>` | Consumes results incrementally; requires closing the stream and managing connections |
| DTO/read model | Fetches only the data the screen needs without building full aggregates |
| SQL logging | A way to verify the actual number of executed statements |

**Query count must be reasoned about from the number of roots, aggregate structure, and loading strategy.** A single `findById()` call may only require a couple of SQL statements, whereas `findAll()` across hundreds of aggregates with collections can cause N+1. Single Query Loading helps mitigate this problem when its limitations are met; for screens that only read partial data, projections/DTOs are often the better choice. Measure actual SQL on the target database before drawing performance conclusions.

## References

- [Spring Data Relational — Persisting Entities / Loading Aggregates](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): traditional loading and Single Query Loading, support conditions, and limitations.
- [Spring Blog — This is the Beginning of the End of the N+1 Problem: Introducing Single Query Loading](https://spring.io/blog/2023/08/31/this-is-the-beginning-of-the-end-of-the-n-1-problem-introducing-single-query/): description of the N+1 pattern and how Single Query Loading uses window functions.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): Page, Slice, Stream, and custom `@Query`.
- [Spring Data Relational — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): enabling `org.springframework.jdbc` logging to observe SQL.
