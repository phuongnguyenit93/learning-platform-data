# Building Reports with Projections, Aggregations, and Accurate Pagination

A Spring Data JPA report often needs to retrieve a subset of data, compute grouped aggregations, and paginate the results. For a report to be both fast and accurate, three parts must be designed together:

- **Projection** specifies the exact columns or values the report actually needs.
- **Aggregation** uses `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` along with `GROUP BY` and `HAVING` to compute results directly in the database.
- **Pagination** slices the report rows and accurately computes the total row count after grouping/filtering.

The most common mistake is when the content query and the page-count query have different definitions of a result row. In a report with `GROUP BY`, one result row typically represents a group, not an individual entity record. Therefore, `countQuery` must count the number of groups returned after filtering.

## 1. Define the Grain of a Report Row

Before writing a query, answer this question: **what does a single row in the report represent?**

Example revenue-by-customer report:

| customerId | customerName | orderCount | revenue |
|---:|---|---:|---:|
| 101 | An | 3 | 12,500,000 |
| 102 | Bình | 1 | 2,000,000 |
| 103 | Chi | 0 | 0 |

Each row is one customer, not one order. Consequently:

- `GROUP BY` customer.
- `COUNT` counts each customer's orders.
- `SUM` totals the order amounts.
- Pagination slices the customers after aggregation.
- `totalElements` must be the number of qualifying customers, not the number of orders.

If the report changes to one row per month and customer, the grouping grain becomes the `(customer, month)` pair. In that case, `countQuery` must count the qualifying `(customer, month)` pairs, not just customers.

Write down the grouping grain before choosing projections or pagination. This serves as the baseline for verifying `countQuery`.

## 2. Projections: Fetch Only the Data the Report Needs

Projections ensure the query returns only the attributes needed for the screen or report export. This reduces data transferred from the database, avoids loading full entity graphs, and clarifies the output contract.

Spring Data JPA commonly uses three projection styles:

| Type | How It Works | Best Suited When |
|---|---|---|
| Interface projection | Spring creates a proxy reading attributes from query results | Simple reports with clear aliases |
| Class/record DTO projection | JPA instantiates the object via constructor | Explicit, immutable return types are needed |
| Dynamic projection | Caller selects the projection type at repository call time | Same query serves multiple display shapes |

### 2.1. Interface Projection

Declare the interface:

~~~java
import java.math.BigDecimal;

public interface CustomerSalesView {

    Long getCustomerId();

    String getCustomerName();

    Long getOrderCount();

    BigDecimal getRevenue();
}
~~~

Aliases in `SELECT` must match the property names the projection reads:

~~~java
@Query("""
    select
        c.id as customerId,
        c.name as customerName,
        count(o.id) as orderCount,
        coalesce(sum(o.totalAmount), :zero) as revenue
    from Customer c
    left join c.orders o
        on o.createdAt >= :from
       and o.createdAt < :to
    where c.active = true
    group by c.id, c.name
    order by revenue desc, c.id asc
    """)
List<CustomerSalesView> findSalesRows(
    @Param("from") Instant from,
    @Param("to") Instant to,
    @Param("zero") BigDecimal zero
);
~~~

The example above is unpaginated; it demonstrates building a projection from aggregate expressions. A `LEFT JOIN` preserves customers who had no orders during the period. The time range condition goes in `ON` so it does not turn the `LEFT JOIN` into an `INNER JOIN`.

If `o.createdAt` conditions were placed in `WHERE`, rows with `o` null would be filtered out, causing customers with zero orders to disappear from the report.

### 2.2. Class or Record DTO Projection

If you want an immutable result type, you can use a Java record:

~~~java
package com.example.reporting;

import java.math.BigDecimal;

public record CustomerSalesReport(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

JPQL uses a constructor expression with the fully qualified name of the DTO:

~~~java
@Query("""
    select new com.example.reporting.CustomerSalesReport(
        c.id,
        c.name,
        count(o.id),
        coalesce(sum(o.totalAmount), :zero)
    )
    from Customer c
    left join c.orders o
        on o.createdAt >= :from
       and o.createdAt < :to
    where c.active = true
    group by c.id, c.name
    order by coalesce(sum(o.totalAmount), :zero) desc, c.id asc
    """)
List<CustomerSalesReport> findSalesReports(
    @Param("from") Instant from,
    @Param("to") Instant to,
    @Param("zero") BigDecimal zero
);
~~~

Constructor parameter types must match the JPQL expression types:

- `COUNT` returns `Long`.
- `SUM` on a `BigDecimal` attribute returns `BigDecimal`.
- `COALESCE` requires type-compatible arguments.
- `id` and `name` must match the entity attribute types.

Do not `SELECT c` in a report when you only need those four fields. Fetching full entities can bring along unnecessary persistence context state, dirty checking, or lazy associations.

### 2.3. When to Use Nested Projections?

Nested projections can be useful when reading relational hierarchies, but they are not the default choice for aggregate reports. With `COUNT`/`SUM`/`GROUP BY`, prefer scalar values and flat aliases to avoid accidentally loading associations or producing complex queries.

Do not use projections as a substitute for `GROUP BY`. Projections shape the output; aggregation still must be expressed properly in the query.

## 3. Aggregation with COUNT, SUM, and COALESCE

Common aggregate functions in JPQL:

| Function | Meaning | Typical Result Type |
|---|---|---|
| COUNT(x) | Counts non-null values | Long |
| SUM(x) | Sum of values | Corresponding numeric type per JPA |
| AVG(x) | Average | Double |
| MIN(x) | Minimum value | Expression type |
| MAX(x) | Maximum value | Expression type |

### 3.1. COUNT(o.id) vs. COUNT(*)

With a `LEFT JOIN`, a customer without orders still produces one joined row with null order columns. Using `COUNT(*)` in SQL counts that row as 1. Use **COUNT(o.id)** to count only orders that actually have an ID.

Example:

~~~sql
SELECT
    c.id,
    COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id;
~~~

A customer with no orders will have `order_count` equal to 0.

### 3.2. SUM Can Return Null

When a group has no values to sum, `SUM` can return `null`. Use **COALESCE** to normalize the result to 0 per reporting conventions:

~~~sql
COALESCE(SUM(o.total_amount), 0)
~~~

For currency, use `BigDecimal` in Java and `DECIMAL`/`NUMERIC` in the database. Avoid converting monetary values to `double` because floating-point rounding errors can skew report totals.

### 3.3. WHERE and HAVING Are Different

- **WHERE** filters input rows before grouping.
- **HAVING** filters groups after `GROUP BY` and aggregation.

Example selecting orders in a time range and keeping only customers whose revenue meets a minimum threshold:

~~~sql
SELECT
    customer_id,
    COUNT(id) AS order_count,
    SUM(total_amount) AS revenue
FROM purchase_order
WHERE created_at >= ?
  AND created_at < ?
GROUP BY customer_id
HAVING SUM(total_amount) >= ?;
~~~

The date condition goes in `WHERE` because it filters individual input orders. The revenue condition goes in `HAVING` because it applies to the group total.

If you need to keep customers with zero orders, be careful where you place child-table conditions when using `LEFT JOIN`. Putting them in `WHERE` can eliminate groups with no orders.

## 4. GROUP BY Must Match the Projection

Every non-aggregated expression in `SELECT` must generally appear in `GROUP BY` under JPQL/database rules.

Example:

~~~sql
SELECT
    c.id,
    c.name,
    COUNT(o.id),
    SUM(o.total_amount)
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
GROUP BY c.id, c.name;
~~~

If you add `c.email` to `SELECT`, update `GROUP BY` accordingly. Do not rely on a database inferring functional dependencies from the primary key if you want the query to run consistently across DBMS engines.

When grouping at multiple levels, such as customer and month, both grouping keys must appear in `GROUP BY`:

~~~sql
SELECT
    customer_id,
    EXTRACT(YEAR FROM created_at) AS report_year,
    EXTRACT(MONTH FROM created_at) AS report_month,
    SUM(total_amount)
FROM purchase_order
GROUP BY
    customer_id,
    EXTRACT(YEAR FROM created_at),
    EXTRACT(MONTH FROM created_at);
~~~

Year/month extraction syntax can vary across databases and JPQL providers. If a query depends on a dialect, test it against the production-equivalent database or intentionally use a native query.

## 5. Paginating with Page and countQuery

Spring Data JPA supports returning **Page\<T\>** to provide both page content and total element/page metadata.

Example customer reporting repository:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query(
        value = """
            select new com.example.reporting.CustomerSalesReport(
                c.id,
                c.name,
                count(o.id),
                coalesce(sum(o.totalAmount), :zero)
            )
            from Customer c
            left join c.orders o
                on o.createdAt >= :from
               and o.createdAt < :to
            where c.active = true
            group by c.id, c.name
            order by coalesce(sum(o.totalAmount), :zero) desc, c.id asc
            """,
        countQuery = """
            select count(c.id)
            from Customer c
            where c.active = true
            """
    )
    Page<CustomerSalesReport> findSalesReport(
        @Param("from") Instant from,
        @Param("to") Instant to,
        @Param("zero") BigDecimal zero,
        Pageable pageable
    );
}
~~~

The count query above is accurate because:

- The content query produces exactly one group per active customer.
- The `LEFT JOIN` retains customers with no orders in the period.
- There is no `HAVING` clause filtering out any groups.
- Therefore, the total number of groups equals the number of active customers.

If you add a `HAVING` condition such as total revenue exceeding a threshold, the count query above would become wrong because it would still count customers below the threshold. `countQuery` must always reflect the exact conditions producing rows in the content query.

### 5.1. Page Requires Counting Total Rows

`Page` contains the current page data along with metadata like `totalElements` and `totalPages`. To compute those values, Spring Data typically executes a count query when needed. In some cases, the framework can infer the total from the final page content without running the count query; however, never rely on that optimization as a substitute for a correct `countQuery`.

For aggregate queries, declare an explicit `countQuery` whenever the query is complex or Spring cannot derive the right count expression.

### 5.2. Count Queries for GROUP BY and HAVING

Suppose the report has one row per customer, keeping only groups with at least three orders. The content query includes `HAVING`:

~~~sql
SELECT
    c.id,
    c.name,
    COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
WHERE c.active = true
GROUP BY c.id, c.name
HAVING COUNT(o.id) >= 3;
~~~

You cannot use a simple `countQuery` like:

~~~sql
SELECT COUNT(DISTINCT c.id)
FROM customer c
LEFT JOIN purchase_order o
    ON o.customer_id = c.id
WHERE c.active = true;
~~~

That query counts customers with fewer than three orders too. Because it does not apply `HAVING`, `totalElements` will be larger than the actual number of groups.

With native SQL, you can count the groups using a subquery:

~~~sql
SELECT COUNT(*)
FROM (
    SELECT c.id
    FROM customer c
    LEFT JOIN purchase_order o
        ON o.customer_id = c.id
    WHERE c.active = true
    GROUP BY c.id
    HAVING COUNT(o.id) >= 3
) grouped_customers;
~~~

When using a native query with `Page`, declare a dedicated `countQuery` inside `@Query`. Subqueries in `FROM` and aliasing syntax depend on the SQL dialect, so run them against the real database. If JPQL cannot express the required group count, a native count query or a separate query step can be clearer.

### 5.3. When Is COUNT DISTINCT Sufficient?

If each group corresponds to exactly one customer and there is no `HAVING` clause, **COUNT(DISTINCT c.id)** can count the groups. But if a group is `(customer, month)`, you must count those pairs. `COUNT(DISTINCT c.id)` would count customers and ignore the number of months.

If `HAVING` is present, group filtering must be reflected in the count query. Do not just see a `JOIN` and add `DISTINCT` to patch duplicates; determine the exact grain of the report.

## 6. When You Do Not Need Total Elements: Slice

If the UI only needs a "Next page" button and does not display total page counts, using **Slice\<T\>** can save cost.

- `Page` typically requires a total count to supply `totalElements`/`totalPages`.
- `Slice` only needs to know if more data exists; Spring Data usually fetches one extra row to determine `hasNext`.
- For large aggregate reports, skipping the count query can significantly reduce cost.

Example:

~~~java
Slice<CustomerSalesView> findByActiveTrue(Pageable pageable);
~~~

This is a derived query example illustrating the return type; actual aggregate reports still require the corresponding projection query. If business requirements do not need a total count, consider `Slice` instead of `Page`.

Do not return a `List` when callers need database-level pagination. Fetching all results and slicing in Java consumes memory and time proportional to the entire dataset.

## 7. Stable Sorting to Avoid Duplicate or Skipped Rows

Reports need deterministic ordering. If you only sort by revenue, multiple customers can have the exact same revenue. Add a unique key as a tie-breaker:

~~~sql
ORDER BY revenue DESC, customer_id ASC
~~~

Stable ordering keeps pages consistent when aggregate values tie.

With `Sort` passed from `Pageable`:

- Allow sorting only on whitelisted attributes/expressions.
- Projection aliases are not always entity attributes.
- Native queries and dynamic sorting have differences depending on the Spring Data JPA version/provider.
- Never concatenate raw sort strings from requests into SQL.

If the query already has a fixed `ORDER BY`, pass a `Pageable` without additional sorting or use `Sort.unsorted()` to prevent conflicting or duplicated sort clauses.

## 8. Pagination and Concurrent Data Changes

`Page` usually involves at least two logical SQL statements: the content query and the count query. If data changes between the two executions, the page content and `totalElements` can reflect two different points in time.

For example:

1. The content query returns 20 customers.
2. Another transaction inserts a new customer or modifies an order.
3. The count query runs afterward and counts the new number of groups.

The result may not represent a single consistent snapshot, depending on the isolation level and database. For typical operational reports, this is acceptable. For financial or reconciliation reports requiring reproducibility:

- Run content and count within a transaction using an isolation/snapshot level supported by the database.
- Use a fixed report time window.
- Store a cutoff timestamp or snapshot version.
- For very large reports, consider summary tables or materialized views updated on a dedicated schedule.

Do not assume that merely adding `@Transactional` guarantees both queries see the same snapshot on every database. Isolation semantics depend on the engine and configuration.

## 9. Avoiding N+1 and Broken Pagination on Collection Joins

For reports, scalar/DTO projections are generally better than loading entities and traversing lazy associations in a loop.

Mistakes to avoid:

- Loading `Page<Customer>` and calling `customer.getOrders()` for each customer, causing N+1 queries.
- Using `JOIN FETCH` for a collection in a paginated query; the join can multiply rows, break pagination, or force the provider to paginate in memory.
- Counting `JOIN` rows instead of report groups.
- Selecting entire entities when only a few columns are needed.
- Using `DISTINCT` to mask a join bug without understanding the report's grain.

Let the database compute aggregations and return one DTO row per group. If details of individual orders are needed, provide a separate endpoint/query paginated by order.

## 10. Testing Reports with Projections and Pagination

An integration test should verify both the projection contents and the pagination metadata.

Use a fixed fixture, for example:

| Customer | Orders in Period | Total Amount | Active? |
|---|---:|---:|---|
| A | 2 | 1,000 | Yes |
| B | 1 | 500 | Yes |
| C | 0 | 0 | Yes |
| D | 4 | 4,000 | No |

For a report of all active customers, the result must have three rows: A, B, and C. Order counts are 2, 1, and 0; revenues are 1,000, 500, and 0.

Tests should verify:

1. The projection contains only the exact report fields needed.
2. `COUNT(o.id)` does not count null rows from `LEFT JOIN`.
3. `SUM`/`COALESCE` returns 0 for customers with no orders.
4. `GROUP BY` produces exactly one row per customer.
5. The count query returns `totalElements = 3`.
6. Page size 2 yields two rows on the first page and one row on the next page.
7. Revenue is ordered descending with a stable tie-breaker.
8. Inactive customers do not appear.
9. The `from`/`to` time range filters properly; follow the convention `from` inclusive, `to` exclusive.
10. When `HAVING` is used, `countQuery` counts the exact number of groups remaining after `HAVING`.

### 10.1. Example Test with Page

~~~java
@DataJpaTest
class CustomerSalesReportRepositoryTest {

    @Autowired
    private CustomerRepository customers;

    @Test
    void returnsCorrectGroupsAndTotalPages() {
        Pageable pageable = PageRequest.of(0, 2, Sort.unsorted());

        Page<CustomerSalesReport> page = customers.findSalesReport(
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2026-02-01T00:00:00Z"),
            BigDecimal.ZERO,
            pageable
        );

        assertEquals(2, page.getContent().size());
        assertEquals(3, page.getTotalElements());
        assertEquals(2, page.getTotalPages());

        CustomerSalesReport first = page.getContent().get(0);
        assertEquals(2L, first.orderCount());
        assertEquals(new BigDecimal("1000.00"), first.revenue());
    }
}
~~~

This example assumes the fixture is created before the test, `CustomerSalesReport` is the declared record, the repository defines `findSalesReport` as shown earlier, and monetary values are stored with scale 2. Import JUnit assertions, `Page`, `Pageable`, `PageRequest`, `Sort`, `Instant`, and `BigDecimal`.

With `@DataJpaTest`, test methods run inside a transaction by default and usually roll back afterward. Fixtures can be inserted using repositories/`EntityManager` in the same transaction or via `@Sql` according to the chosen transaction mode.

### 10.2. Testing Dedicated countQuery with HAVING

Create a fixture containing groups that both meet and fail the threshold, then verify:

- The content query returns only groups passing `HAVING`.
- `totalElements` counts only groups passing `HAVING`.
- When paging through results, no groups are duplicated by joins.
- The last page has the right number of rows.
- Native count queries execute cleanly on the production database.

This is a critical test because a report can display the first page accurately while reporting an incorrect `totalPages` if `countQuery` fails to mirror `GROUP BY`/`HAVING`.

### 10.3. Choosing the Right Database

H2 is useful for fast tests, but it can differ from PostgreSQL/MySQL/SQL Server in date/time functions, numeric types, native query aliases, group-by validation, and SQL dialects. If a report relies on native SQL or dialect-specific expressions, run integration tests using Testcontainers with a production-like database.

Do not only test results against a tiny fixture. Check query plans and indexes on larger datasets to ensure grouping, sorting, and counting do not become bottlenecks.

## 11. Optimizing Report Performance

Measures that typically pay off:

- `SELECT` only columns required by the projection.
- Filter by time range and business conditions before grouping.
- Create indexes matching join keys and filters, such as `customer_id`, `created_at`, or composite indexes matching actual queries.
- Avoid expensive count queries if the UI only needs `Slice`.
- Inspect `EXPLAIN`/`EXPLAIN ANALYZE` on the target database.
- Measure content queries and count queries separately.
- If periodic aggregations repeat frequently, consider summary tables or materialized views.
- Use keyset pagination when compatible with ordering and navigation needs; keyset pagination does not provide automatic total counts.

Do not create indexes by guesswork. Indexes should be guided by actual `WHERE`, `JOIN`, `GROUP BY`, and `ORDER BY` clauses; excessive indexing slows down `INSERT`/`UPDATE`.

## 12. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `totalElements` larger than report row count | Count query counts JOIN rows instead of groups | Count the right grain using `count distinct` or a grouped subquery |
| Wrong `totalPages` with `HAVING` | Count query omits `HAVING` | Count a subquery containing the same `GROUP BY`/`HAVING` |
| Customers with no orders vanish | Child-table filter placed in `WHERE` after `LEFT JOIN` | Move the filter into the `ON` clause |
| `orderCount` is 1 for zero-order customers | Using `COUNT(*)` with `LEFT JOIN` | Use `COUNT(o.id)` |
| `revenue` returns null | `SUM` over a group with no values | Use `COALESCE` with a matching numeric type |
| DTO constructor mismatch | Wrong constructor parameter order or types | Check `COUNT`, `SUM`, and constructor expression |
| Interface projection returns null | Aliases do not match getters | Align aliases with property names |
| Duplicate rows across pages | Join multiplies rows or sort is unstable | Group by the proper grain and add a unique tie-breaker sort |
| Page query is very slow | Expensive count query or `GROUP BY` | Profile count/content separately, add indexes, or use `Slice` |
| H2 passes but production fails | Dialect-dependent native SQL or functions | Test on the production-equivalent database |
| Totals shift between content and count | Data mutated between the two queries | Choose isolation/snapshot semantics matching report needs |

## 13. Implementation Checklist

- [ ] Identified which entity or group each report row represents.
- [ ] Projection fetches only fields required by the report.
- [ ] Interface projection aliases match getters, or DTO constructor types match expressions.
- [ ] `COUNT(o.id)` is used properly with `LEFT JOIN`.
- [ ] `SUM` nulls are handled via `COALESCE` when required by business rules.
- [ ] `WHERE` filters input rows and `HAVING` filters groups.
- [ ] `GROUP BY` includes all non-aggregated `SELECT` expressions.
- [ ] Content query and `countQuery` share the same business filters.
- [ ] `countQuery` counts groups after `HAVING`, not raw `JOIN` rows.
- [ ] `Slice` is used if `totalElements`/`totalPages` are not needed.
- [ ] `ORDER BY` includes a unique tie-breaker for stable pagination.
- [ ] Dynamic sorting is whitelisted; raw input is never concatenated into SQL.
- [ ] Concurrent modifications between content and count queries have been evaluated.
- [ ] Integration tests verify projections, aggregations, page size, `totalElements`, and `totalPages`.
- [ ] Native queries are tested on a production-appropriate database.
- [ ] Content query, count query, and query plans have been measured on sufficiently large data.

## 14. Key Takeaways

Projections determine what data is returned; aggregations determine how the database builds groups; pagination slices those groups into pages. For an accurate `Page`, `countQuery` must count the exact grain of a report row and apply the same filtering conditions, especially `GROUP BY` and `HAVING`.

For aggregate reports, prefer flat DTO/interface projections, `COUNT(o.id)` on `LEFT JOIN`s, `COALESCE` for empty sums, stable `ORDER BY` clauses, and integration tests verifying both content and `totalElements`. If total page counts are unnecessary, `Slice` avoids an expensive count query.

## References

- [Spring Data JPA — Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data JPA — Query methods and countQuery](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data Commons — Paging and sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Jakarta Persistence — JPQL and aggregate functions](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
