# Optimizing Joins, DISTINCT, Subqueries, and Large Filters

Spring Data JPA query performance depends on more than table row counts. A query can be slow because a JOIN multiplies rows, DISTINCT must deduplicate a large result set, a subquery executes with a poor plan, or an IN parameter list is too long.

To optimize properly, you need to understand relationship **cardinality**, the number of rows the database actually processes, the data that must be returned, and the execution plan. Do not add DISTINCT or rewrite a JOIN as a subquery on guesswork. Define the desired result first, write a semantically accurate query, and then measure SQL and execution plans on a database close to production.

This lesson focuses on four technique groups: JOIN, DISTINCT, subqueries, and large filters. Examples use JPQL and Spring Data JPA; database-specific aspects are noted explicitly.

**Example prerequisites:** Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence, and Hibernate. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and an appropriate schema. The classes below are snippets of a Spring Boot application, not standalone programs runnable via `javac` alone.

## 1. Starting from Relationship Cardinality

JOIN combines data from multiple tables. The first thing to understand is whether the relationship between the two sides is one-to-one, many-to-one, one-to-many, or many-to-many.

For example, an order has multiple order items:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    private String sku;

    private Integer quantity;

    @Enumerated(EnumType.STRING)
    private ItemStatus status;
}
~~~

If an order has three order lines, a query joining from PurchaseOrder to items can produce three SQL rows for the same order:

~~~sql
SELECT o.id, i.id, i.sku
FROM purchase_orders o
JOIN order_items i ON i.order_id = o.id;
~~~

| order_id | item_id | sku |
|---:|---:|---|
| 10 | 101 | KB-01 |
| 10 | 102 | MS-02 |
| 10 | 103 | USB-03 |
| 11 | 104 | HD-04 |

The parent entity can appear repeatedly in the SQL result set because each child row forms a distinct combination. This is the root cause of many wrong counts, broken pagination, and misplaced DISTINCT clauses.

Before writing a JOIN, answer:

- Does the result need one row per parent entity or one row per parent-child pair?
- Is child entity data needed in the response, or do we only need to know whether at least one matching child exists?
- How many child entities can a parent entity have?
- Are filter conditions on the parent table, the child table, or both?

## 2. INNER JOIN and LEFT JOIN Have Different Semantics

**INNER JOIN** returns only rows with matching relationships on both sides. **LEFT JOIN** retains every row from the left side even when no matching right-side row exists; right-side columns are NULL in that case.

JPQL example:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
List<PurchaseOrder> findOrdersWithItemStatus(
    @Param("status") ItemStatus status
);
~~~

Orders without matching items are excluded. If the goal is to find orders with at least one item in that status, this query expresses the intent, though the JOIN can produce multiple rows for a single order.

LEFT JOIN:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    left join p.items i
    """)
List<PurchaseOrder> findOrdersIncludingWithoutItems();
~~~

This query preserves orders that have no items. However, if you place a right-side condition in the WHERE clause:

~~~java
select p
from PurchaseOrder p
left join p.items i
where i.status = :status
~~~

rows without items have `i.status = NULL` and are filtered out by WHERE. The result is effectively equivalent to an INNER JOIN for that condition.

If you want to keep all orders and only join items matching a specific status, put the condition in the ON clause:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    left join p.items i on i.status = :status
    """)
List<PurchaseOrder> findOrdersAndMatchingItems(
    @Param("status") ItemStatus status
);
~~~

The ON condition preserves LEFT JOIN semantics. Note that the query can still return an order multiple times if multiple items match.

## 3. Row Multiplication from JOIN and Its Impact on Results

When joining a collection, a parent entity can appear multiple times at the SQL level. This affects:

- Returned element count and deduplication.
- COUNT and aggregations.
- LIMIT/OFFSET and pagination.
- Data volume transferred from the database.
- Sort, hash, and duplicate elimination costs.

Example:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    join p.items i
    where i.sku like :prefix
    """)
List<PurchaseOrder> findOrdersByItemSkuPrefix(
    @Param("prefix") String prefix
);
~~~

An order with two items matching the prefix may appear twice in the logical query result. If the goal is a list of distinct orders, consider **select distinct p** or rewrite the query using EXISTS if item data is not needed.

Do not assume every JOIN causes row multiplication. Joining along a many-to-one or one-to-one association typically does not multiply a parent row into multiple child rows when data constraints are valid. Joining along one-to-many and many-to-many associations can multiply rows by the number of related elements.

## 4. DISTINCT in JPQL and SQL

**DISTINCT** removes duplicate values across the selected expressions. In JPQL, it can be used with entities or projections:

~~~java
@Query("""
    select distinct p
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
List<PurchaseOrder> findDistinctOrdersByItemStatus(
    @Param("status") ItemStatus status
);
~~~

The goal here is a list of unique PurchaseOrder entities, even if multiple items in the same order match the condition.

DISTINCT does not mean "deduplicate by whichever field you want." When selecting multiple scalar expressions, uniqueness applies to the combination of selected values:

~~~java
select distinct p.status, i.sku
from PurchaseOrder p
join p.items i
~~~

Two rows are considered duplicates only if both status and sku match.

### DISTINCT Has a Cost

The database may need to sort or hash to eliminate duplicates. Cost rises with input row count and the size of the columns being compared. Therefore:

- Do not add DISTINCT simply to mask an unnecessary JOIN.
- Select only the columns you actually need.
- Inspect the execution plan to see which sort/hash step the database uses.
- If you only need an existence check, consider EXISTS instead of JOIN followed by DISTINCT.

In Hibernate 6, duplicate root entities caused by collection fetch joins are deduplicated in entity results in certain cases per provider behavior. Even so, **select distinct** retains explicit JPQL semantics and can affect the generated SQL. Do not rely on a specific provider/version quirk instead of understanding query semantics; inspect the actual SQL.

## 5. COUNT(DISTINCT ...) to Count Unique Entities

If you join a collection and count parent entities, **count(p)** may count joined rows instead of unique orders, depending on query structure and how the provider translates it.

For example, counting orders that have an ACTIVE item:

~~~java
@Query("""
    select count(distinct p.id)
    from PurchaseOrder p
    join p.items i
    where i.status = :status
    """)
long countDistinctOrdersByItemStatus(
    @Param("status") ItemStatus status
);
~~~

**count(distinct p.id)** counts unique order IDs. If the actual goal is counting items, use `count(i.id)`; if counting order-item pairs, define the appropriate key/structure.

Do not mechanically replace every COUNT with COUNT DISTINCT. DISTINCT can make queries more expensive; use it only when cardinality shows an entity can appear multiple times and the business requirement is to count unique entities.

For Page queries, the count query must reflect the same logical criteria as the content query:

~~~java
@Query(
    value = """
        select distinct p
        from PurchaseOrder p
        join p.items i
        where i.status = :status
        """,
    countQuery = """
        select count(distinct p.id)
        from PurchaseOrder p
        join p.items i
        where i.status = :status
        """
)
Page<PurchaseOrder> pageOrdersByItemStatus(
    @Param("status") ItemStatus status,
    Pageable pageable
);
~~~

If a query uses GROUP BY, the count query must count the number of returned groups rather than total source rows. For native queries or complex structures, declare a dedicated `countQuery` and test it on the target database.

## 6. EXISTS: When You Only Need to Know Related Records Exist

If the use case only needs orders that have at least one matching item, and does not need item data in the result, **EXISTS** usually expresses the intent better than JOIN + DISTINCT.

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where exists (
        select i.id
        from OrderItem i
        where i.order = p
          and i.status = :status
    )
    """)
List<PurchaseOrder> findOrdersHavingItemStatus(
    @Param("status") ItemStatus status
);
~~~

The subquery correlates with the outer query via **i.order = p**. This is a correlated subquery: the inner condition references entity `p` from the outer query.

The database may optimize EXISTS as a semi-join and stop scanning once a single matching row is found, depending on the optimizer and indexes. There is no guarantee EXISTS is always faster than JOIN on every database; the main benefit is clearly expressing "at least one" semantics and avoiding duplicate parent rows in the result.

An index on the foreign key and filter column, such as **order_items(order_id, status)**, can help locate matching items. Index column ordering should be based on actual queries, selectivity, and execution plans.

## 7. NOT EXISTS to Find Entities Without Related Records

To find orders that have no items in status CANCELLED:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where not exists (
        select i.id
        from OrderItem i
        where i.order = p
          and i.status = :status
    )
    """)
List<PurchaseOrder> findOrdersWithoutItemStatus(
    @Param("status") ItemStatus status
);
~~~

NOT EXISTS is usually clearer than `LEFT JOIN ... IS NULL` when expressing the absence of related records. It also avoids mistakes from misplacing conditions in ON vs WHERE.

Be careful to distinguish:

- Having no items at all.
- Having items, none of which are in a specific status.
- Having items whose status is NULL.

These are distinct business conditions. Write predicates matching the exact requirement and test empty collections as well.

## 8. Subqueries with IN and Aggregate Values

JPQL supports subqueries in WHERE and HAVING. Example finding orders whose total amount exceeds the average:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.totalAmount > (
        select avg(p2.totalAmount)
        from PurchaseOrder p2
    )
    """)
List<PurchaseOrder> findOrdersAboveAverageAmount();
~~~

This example uses an uncorrelated subquery: it computes the average across orders, and then the outer query compares each order against that value.

Example using IN with a subquery:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.customer.id in (
        select c.id
        from Customer c
        where c.active = true
    )
    """)
List<PurchaseOrder> findOrdersOfActiveCustomers();
~~~

In this case, you could also write it using a JOIN to customer. The choice depends on whether Customer data is needed in the output or only as an existence filter.

Standard JPQL permits subqueries in WHERE and HAVING; it does not support arbitrary subqueries in FROM as SQL derived tables. If you need CTEs, window functions, or complex derived tables, consider native queries or provider-specific features and document the database dependency.

## 9. How to Choose Between JOIN, EXISTS, or IN

| Need | Commonly clearest expression |
|---|---|
| Need fields from both entities | JOIN |
| Need parent entity and child data for reading | JOIN/FETCH JOIN or DTO join depending on use case |
| Only need to know at least one child entity exists | EXISTS |
| Need to know no matching child entity exists | NOT EXISTS |
| Compare against a set of values from a subquery | IN (subquery) |
| Count unique parent entities after joining a collection | COUNT(DISTINCT parent.id) |
| Need aggregated results by field combinations | GROUP BY, aggregates, and HAVING |

There is no rule saying "EXISTS is always faster than JOIN" or "IN is always slower than EXISTS." Optimizers can transform equivalent query forms into the same execution plan. Prioritize clear semantics first, then measure on real data.

## 10. IN Filters with Small and Medium ID Lists

Spring Data JPA supports collection parameters:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByIdIn(Collection<Long> ids);
}
~~~

Or JPQL:

~~~java
@Query("""
    select p
    from Product p
    where p.id in :ids
    """)
List<Product> findAllByIds(
    @Param("ids") Collection<Long> ids
);
~~~

This is convenient when the list is moderate in size. The framework/provider binds values as parameters rather than concatenating SQL strings.

Do not do this:

~~~java
String sql = "select * from products where id in (" +
    ids.stream().map(String::valueOf).collect(Collectors.joining(",")) +
    ")";
~~~

Concatenating inputs into SQL risks injection, escaping bugs, and hard-to-maintain queries. Use parameter binding for values.

### Handling Empty Lists

Do not rely on every provider/database handling an empty IN list the same way. Decide the semantics in the service:

- If an empty list means "no IDs were selected," return an empty list immediately.
- If an empty list means "do not apply the ID filter," omit the IN predicate from the query.
- If the API forbids empty lists, return an appropriate validation error.

Example:

~~~java
public List<Product> findSelected(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return productRepository.findByIdIn(ids);
}
~~~

If `ids` can contain nulls, filter out nulls or handle NULL as a separate predicate. SQL IN with NULL follows three-valued logic; it is not equivalent to comparing against an ordinary value.

## 11. What Problems Do Very Large IN Lists Cause?

A list of a few dozen IDs is usually straightforward. However, a list with thousands or tens of thousands of IDs can cause problems:

- Many bind parameters, potentially hitting database or driver limits.
- Huge SQL strings, increasing parsing and statement preparation overhead.
- Difficulty for the optimizer to estimate list cardinality.
- Poor plan cache efficiency if placeholder counts fluctuate constantly.
- Large data payloads sent from application to database.
- Large result sets consuming significant memory and entity mapping time.

Bind parameter limits vary by database, version, driver, and how Hibernate generates SQL. There is no single safe number across all environments. Check your engine/driver documentation and measure with realistic data sizes.

Before optimizing, ask whether the ID list can be replaced by a simpler business condition, such as a date range, status, tenant, or a relationship already stored in the database.

## 12. Splitting Large Lists into Batches

If the ID list is large yet still must be passed from the application, you can split it into smaller chunks:

~~~java
public List<Product> findInBatches(
        Collection<Long> ids,
        int batchSize) {

    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    List<Long> values = ids.stream()
        .filter(Objects::nonNull)
        .distinct()
        .toList();

    List<Product> result = new ArrayList<>();

    for (int start = 0; start < values.size(); start += batchSize) {
        int end = Math.min(start + batchSize, values.size());
        List<Long> batch = values.subList(start, end);

        result.addAll(productRepository.findByIdIn(batch));
    }

    return result;
}
~~~

`batchSize` must be chosen based on parameter limits, query size, latency, and database capacity. Do not assume 500 or 1000 is always optimal.

Batching has trade-offs:

- Causes multiple round-trips instead of one query.
- Reduces the size and parameter count of each individual SQL statement.
- Overall ordering may differ from the input ID list order.
- Deduplication is needed if an ID appears across multiple batches.
- Combined results can still consume considerable memory.

If input ordering must be preserved, build a map by ID and reorder according to the original list. If global pagination is needed, you cannot simply paginate each batch and concatenate results while preserving global order and totals; redesign the query or use a staging table.

## 13. Using Temporary or Staging Tables for Very Large Filters

When the input list has tens of thousands of items or more, passing all IDs as bind parameters may no longer be viable.

One strategy is loading IDs into a temporary or staging table and then JOINing:

~~~sql
SELECT p.id, p.name, p.price
FROM products p
JOIN request_product_ids r
  ON r.product_id = p.id
WHERE r.request_token = ?;
~~~

General workflow:

1. Create or use a staging table with `request_token` and `product_id` columns.
2. Batch-insert the IDs under a shared request token.
3. Run the query joining the staging table with products.
4. Delete staging data afterward or rely on a policy-based cleanup job.
5. Ensure data from different requests cannot mix.

Session/connection-scoped temporary tables must be created, populated, and queried on the same appropriate connection. A connection pool may return a connection after a transaction; do not assume a temporary table still exists or is visible from another connection.

Persistent staging tables keyed by a request token are easier to manage for large or async jobs, but require indexes, cleanup, retention limits, and handling for failed requests.

## 14. Database-Specific Large List Mechanisms

Some databases offer more efficient ways to pass value sets than numerous placeholders:

- **PostgreSQL**: can use array parameters and appropriate operators, such as **= ANY(...)**, or **unnest()** to expand an array into rows. Array binding depends on the JDBC driver and native queries.
- **SQL Server**: table-valued parameters allow passing a set of rows using a defined table type.
- **Oracle**: can use SQL collection types, global temporary tables, or staging tables; collection binding depends on JDBC APIs and configuration.
- **MySQL**: can use temporary tables or staging tables and JOIN; lacks SQL Server's table-valued parameter mechanism.

These are database-specific techniques, not portable JPQL. Place them behind a repository/service abstraction so the rest of the application does not depend directly on engine-specific syntax.

If the application supports multiple databases, provide engine-specific implementations or maintain a portable batching fallback for moderate sets.

## 15. Large Filters with Many Dynamic Conditions

A search screen may accept numerous filters: status, list of customer IDs, date range, and keywords. Avoid manual SQL string concatenation. You can use Specification to append predicates only for criteria actually supplied.

Example:

~~~java
public static Specification<PurchaseOrder> hasStatus(
        OrderStatus status) {
    return (root, query, cb) ->
        status == null ? null : cb.equal(root.get("status"), status);
}

public static Specification<PurchaseOrder> createdFrom(
        Instant from) {
    return (root, query, cb) ->
        from == null ? null : cb.greaterThanOrEqualTo(
            root.get("createdAt"), from);
}
~~~

Combining:

~~~java
Specification<PurchaseOrder> spec =
    Specification.where(hasStatus(status))
        .and(createdFrom(from));

Page<PurchaseOrder> page =
    repository.findAll(spec, pageable);
~~~

For an ID list filter, add the IN predicate only when the list is non-empty and validated. If the list is too large, switch to your chosen batching or staging strategy instead of building a gigantic predicate.

Specification helps construct dynamic WHERE clauses, but does not automatically solve performance issues. Collection joins inside a Specification can still multiply rows and affect DISTINCT, count queries, and pagination.

## 16. Indexes for JOIN, EXISTS, and Large Filters

Indexes should be based on filter conditions, join columns, sort order, and selectivity. For example, querying items by `order_id` and `status`:

~~~sql
SELECT i.id
FROM order_items i
WHERE i.order_id = ?
  AND i.status = ?;
~~~

A composite index such as:

~~~sql
CREATE INDEX idx_order_items_order_status
ON order_items(order_id, status);
~~~

can support the query above. However, optimal column ordering depends on other queries, data distribution, selectivity, and the database's indexing capabilities.

Guidelines:

- Foreign key indexes are often helpful for JOIN and EXISTS.
- Composite indexes can support combined equality conditions.
- Sort columns can be included in an index when queries frequently filter and sort by the same pattern.
- Too many indexes increase INSERT/UPDATE/DELETE costs and storage.
- Wrapping columns in functions like `LOWER(column)` can prevent ordinary index usage unless the database has functional indexes or matching collations.
- Do not create an index merely because a column appears in WHERE; check the workload and execution plan.

For large IN filters, a primary key index usually supports single-ID lookups, though list transfer costs and cardinality estimation can still dominate total time.

## 17. Reading Execution Plans Instead of Guessing

Use database tools to see how the optimizer plans to execute a query:

- PostgreSQL: **EXPLAIN** and **EXPLAIN (ANALYZE, BUFFERS)**.
- MySQL: **EXPLAIN** or **EXPLAIN ANALYZE** depending on version.
- SQL Server: actual execution plan and IO/time statistics.
- Oracle: execution plan and runtime statistics via appropriate tools.

**EXPLAIN ANALYZE** may execute the real query, so run it only in suitable environments and on safe data. Be especially careful about side effects on write queries.

Signals to watch for:

- Full table scans on large tables when index lookups are expected.
- Nested loops iterating too many times due to high cardinality.
- Hash joins or sorts consuming excessive memory.
- DISTINCT creating large sort/hash steps.
- Estimated rows differing wildly from actual rows.
- Count queries slower than content queries.
- Intermediate row counts after JOIN vastly exceeding final entity counts.

Measure duration, rows read, rows returned, and round-trips. A query returning 20 entities can still process millions of intermediate rows.

## 18. JOIN FETCH, DTOs, and Pagination

JOIN FETCH loads associations in the same query, but fetching collections multiplies SQL rows. Combining a collection fetch join with Pageable can apply limit/offset to joined rows instead of parent entities as expected. Hibernate may paginate in memory or emit warnings depending on configuration.

For pages of parent entities with child collections, a safer strategy is:

1. Paginate parent entity IDs.
2. Fetch detailed entities/DTOs for the page's ID list.
3. Preserve ID order if required by the response.
4. Run a separate count query if Page metadata is needed.

If the endpoint only needs a few fields from parent and child, DTO projections usually transfer less data than loading the full entity graph.

Do not fetch multiple large collections just to avoid LazyInitializationException. Choose fetch plans by use case and inspect actual cardinality.

## 19. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Parent entity appears repeatedly | Collection JOIN produces multiple rows | DISTINCT or EXISTS depending on goal |
| COUNT exceeds entity count | Counting joined rows instead of unique IDs | COUNT(DISTINCT parent.id) |
| LEFT JOIN still drops childless parents | Right-side condition placed in WHERE | Place condition in ON or revise intended semantics |
| DISTINCT slows query down | Deduplicating a large result set | Avoid unnecessary joins; use EXISTS if only checking existence |
| Page has wrong totalElements | Count query does not reflect cardinality | Declare an accurate countQuery |
| IN list fails as data grows | Hits parameter limit or SQL too large | Batching, array/table parameters, or staging table |
| Empty IN list causes SQL error | Empty list semantics unhandled | Return empty or omit filter per business rules |
| NOT IN returns unexpected results | List contains NULL | Filter out NULL or use NOT EXISTS |
| JOIN FETCH pagination is slow | Collection join multiplies rows | Paginate IDs first, load details afterward |
| Indexed query still slow | Index mismatches selectivity/order or plan ignores it | Read execution plan and measure on real data |
| Native SQL reduces portability | Database-dependent syntax | Isolate behind repository adapters and test each engine |

## 20. Query Optimization Checklist

- [ ] Determine whether one result row represents a parent entity, a child entity, or a combination.
- [ ] Check the cardinality of every JOIN, especially one-to-many and many-to-many.
- [ ] Put LEFT JOIN filters in ON when childless parent entities must be retained.
- [ ] Use DISTINCT only when deduplicating across the exact SELECT expression list.
- [ ] Use COUNT(DISTINCT id) when counting unique entities after a join.
- [ ] Use EXISTS/NOT EXISTS when only checking presence or absence of related records.
- [ ] Choose JOIN when data from both sides is genuinely needed.
- [ ] Handle empty IN lists and NULLs explicitly.
- [ ] Use parameter binding; never concatenate values into SQL.
- [ ] Batch or use staging/array/table-valued parameters for very large lists.
- [ ] Verify batching's impact on ordering, duplicates, and global pagination.
- [ ] Create indexes aligned with actual query workloads, foreign keys, filters, and sorts.
- [ ] Inspect execution plans and measure on production-like data.
- [ ] Check count queries and collection fetch joins when paginating.
- [ ] Use DTOs when only a subset of data is needed.
- [ ] Write integration tests against the actual target database/driver.

## 21. Conclusion

JOIN optimization starts with cardinality: collection JOINs multiply rows, duplicate entities, and break COUNT or pagination. **DISTINCT** is useful when deduplicating SELECT results, though it carries a cost; **COUNT(DISTINCT id)** counts unique entities. When you only need to know whether a parent entity has matching child records, **EXISTS** or **NOT EXISTS** usually expresses the goal more clearly.

For large IN filters, handle empty/NULL lists explicitly, bind parameters, split into batches when appropriate, or use staging tables and database-specific mechanisms. Finally, verify indexes and execution plans on realistic data. Good optimization reduces the work the database performs while preserving exact business semantics.