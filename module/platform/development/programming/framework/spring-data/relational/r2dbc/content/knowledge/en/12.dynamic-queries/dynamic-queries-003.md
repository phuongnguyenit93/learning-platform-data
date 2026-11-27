# Comparison, Value Set, and Range Conditions

In Spring Data Relational R2DBC, dynamic queries are commonly formed from filter conditions. A condition may compare a property against a value, check whether a property belongs to a set of values, or determine whether it falls within a range. These filters appear in product search, filtering orders by status, querying time-series data, and many other business flows.

Spring Data R2DBC supports several ways to express these conditions: derived query methods from method names, Criteria combined with R2dbcEntityTemplate, or explicit SQL via DatabaseClient. Whichever approach you choose, you must understand exact operator semantics, NULL handling, range boundaries, and parameter binding.

## 1. Model of a Query Condition

A filter condition can be viewed as a comparison between an entity property and an input value:

```text
property  operator  value
price     >=        100
status    IN        (NEW, PAID)
createdAt BETWEEN   startTime AND endTime
```

In SQL, these conditions usually appear in the WHERE clause:

```sql
SELECT id, name, price, status
FROM products
WHERE price >= 100
  AND status IN ('ACTIVE', 'PREORDER');
```

In Spring Data, conditions can be derived from method names or entity metadata. Spring Data converts Java properties to their corresponding columns via mapping. For example, the property createdAt may be mapped to the column created_at.

A query with multiple conditions must clearly specify how they combine:

- AND: every condition must be true.
- OR: at least one condition must be true.
- NOT: negates a condition.
- Parentheses grouping: controls evaluation order when mixing AND and OR.

Do not just glance at a long method name and assume combination precedence. For complex logic, use Criteria or SQL with explicit parentheses and test the results.

## 2. Basic Comparison Operators

Commonly used comparison operators in SQL and Spring Data include:

| Operator | Meaning | SQL Example |
| --- | --- | --- |
| = | Equal | status = 'ACTIVE' |
| <> or != | Not equal | status <> 'CANCELLED' |
| > | Greater than | price > 100 |
| >= | Greater than or equal | price >= 100 |
| < | Less than | quantity < 10 |
| <= | Less than or equal | quantity <= 10 |
| IS NULL | SQL value is NULL | deleted_at IS NULL |
| IS NOT NULL | Has a SQL value | deleted_at IS NOT NULL |

Ordering comparisons are appropriate for ordered data types such as numbers, dates/times, and certain string types depending on collation. Do not apply greater-than/less-than comparisons to a property if its business semantics lack a defined order.

### Equality and Inequality Comparisons

With derived query methods:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, UUID> {

    Flux<Product> findByStatus(ProductStatus status);

    Flux<Product> findByStatusNot(ProductStatus status);
}
```

findByStatus expresses an equality condition. findByStatusNot expresses an inequality condition. Keywords are parsed based on the entity's status property.

### Greater-Than and Less-Than Comparisons

Threshold queries can be declared as:

```java
Flux<Product> findByPriceGreaterThan(BigDecimal minimum);

Flux<Product> findByPriceGreaterThanEqual(BigDecimal minimum);

Flux<Product> findByPriceLessThan(BigDecimal maximum);

Flux<Product> findByPriceLessThanEqual(BigDecimal maximum);
```

GreaterThan corresponds to >; GreaterThanEqual corresponds to >=; LessThan corresponds to <; LessThanEqual corresponds to <=.

For example, if the requirement is "price 100 or above", use GreaterThanEqual. If the requirement is "price higher than 100", use GreaterThan. Boundary differences can change results, especially when filtering monetary amounts, quantities, or timestamps.

### Combining Multiple Comparisons

A method can combine conditions with And:

```java
Flux<Product> findByPriceGreaterThanEqualAndStockQuantityGreaterThan(
        BigDecimal minimumPrice,
        int minimumStock);
```

The method above selects products priced at least minimumPrice with stock quantity greater than minimumStock. Both conditions must hold.

When method names grow long, involve multiple OR branches, or require optional conditions, Criteria is usually more readable and maintainable.

## 3. Comparison Conditions Using Criteria

Criteria in Spring Data Relational represents query conditions programmatically via an API. It enables building dynamic queries without SQL string concatenation.

Example using R2dbcEntityTemplate to find products priced above a threshold:

```java
import java.math.BigDecimal;

import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;

import reactor.core.publisher.Flux;

public class ProductQueryService {

    private final R2dbcEntityTemplate template;

    public ProductQueryService(R2dbcEntityTemplate template) {
        this.template = template;
    }

    public Flux<Product> findExpensiveProducts(BigDecimal minimum) {
        Query query = Query.query(
            Criteria.where("price").greaterThan(minimum)
        ).sort(Sort.by(Sort.Direction.ASC, "price"));

        return template.select(query, Product.class);
    }
}
```

Criteria.where("price") references the entity's price property. greaterThan(minimum) builds a greater-than condition. Query.query(...) wraps the condition into a query; template.select(...) executes it and maps rows into Product.

Commonly used comparison methods:

| Criteria method | Meaning |
| --- | --- |
| is(value) | Equal to value |
| not(value) | Not equal to value |
| greaterThan(value) | Greater than |
| greaterThanOrEquals(value) | Greater than or equal to |
| lessThan(value) | Less than |
| lessThanOrEquals(value) | Less than or equal to |
| between(lower, upper) | Within range |
| in(values) | In set of values |
| notIn(values) | Not in set of values |
| isNull() | Is SQL NULL |
| isNotNull() | Is not SQL NULL |

Specific names and overloads must match your project's Spring Data Relational version. These examples use the Spring Data Relational Criteria API; when upgrading dependencies, check the corresponding version's Javadoc.

## 4. Comparing Dates/Times and Numeric Types

Greater-than/less-than comparisons are particularly useful for ordered data.

For instance, querying orders created after a specific point in time:

```java
Flux<Order> findByCreatedAtAfter(LocalDateTime moment);

Flux<Order> findByCreatedAtBefore(LocalDateTime moment);
```

After and Before typically express strictly after/before a timestamp. If the boundary timestamp itself must be included, use GreaterThanEqual or LessThanEqual on the corresponding property.

For monetary amounts, use BigDecimal instead of double to avoid binary floating-point representation errors:

```java
Flux<Product> findByPriceGreaterThanEqual(BigDecimal minimumPrice);
```

Inputs and columns should have matching precision/scale. If the database stores NUMERIC(12, 2), standardize rounding rules and decimal places before querying.

For dates and times, timezone and column type must be consistent. A LocalDateTime value carries no timezone info on its own; if business logic requires an absolute instant, design the schema and Java types to align with your system's UTC or offset/time zone convention.

## 5. Set Membership Conditions: IN and NOT IN

When a property can take one of several allowed values, use an IN condition. For example, finding orders with status NEW, PAID, or SHIPPED.

In derived query methods:

```java
Flux<Order> findByStatusIn(Collection<OrderStatus> statuses);

Flux<Order> findByStatusNotIn(Collection<OrderStatus> statuses);
```

You can invoke the repository with a set of statuses:

```java
List<OrderStatus> visibleStatuses = List.of(
    OrderStatus.NEW,
    OrderStatus.PAID,
    OrderStatus.SHIPPED
);

Flux<Order> result = orders.findByStatusIn(visibleStatuses);
```

IN returns records whose value belongs to the input set. NOT IN returns records whose value is not in that set.

With Criteria:

```java
Criteria criteria = Criteria.where("status")
    .in(OrderStatus.NEW, OrderStatus.PAID, OrderStatus.SHIPPED);

Query query = Query.query(criteria);

return template.select(query, Order.class);
```

If the input list is constructed dynamically:

```java
List<OrderStatus> statuses = request.statuses();

if (statuses == null || statuses.isEmpty()) {
    // Choose a clear policy: do not filter by status,
    // or return an empty result per the API contract.
} else {
    Criteria criteria = Criteria.where("status").in(statuses);
    return template.select(Query.query(criteria), Order.class);
}
```

### Handling Empty Sets

An empty set is a case requiring an explicit decision. An SQL query shaped like IN () is usually invalid or lacks consistent semantics across database engines. Thus, do not let results depend on how a driver handles empty lists.

Define the semantics at the application layer:

- If an empty list means "do not apply this filter", omit the IN condition from the query.
- If an empty list means "no values are permitted", return Flux.empty() or construct an always-false condition.
- If the field is omitted from the request, handle it separately from a field present with an empty list if the API distinguishes these two states.

Never automatically turn every empty list into "unfiltered". In an authorization-scoped endpoint, an empty list may have to mean zero permitted records.

### NULL in Value Sets

SQL uses three-valued logic. If a NOT IN list contains NULL, the result can evaluate to UNKNOWN for rows that do not match any value. This often causes the query to return fewer rows than expected.

For example:

```sql
SELECT id, status
FROM orders
WHERE status NOT IN ('CANCELLED', NULL);
```

Do not include NULL in an IN/NOT IN list if the goal is ordinary set comparison. If you need to include or exclude rows with a NULL column, write an explicit IS NULL or IS NOT NULL condition.

For example, finding orders that are not cancelled and have a defined status:

```sql
SELECT id, status
FROM orders
WHERE status IS NOT NULL
  AND status <> 'CANCELLED';
```

## 6. Range Conditions: BETWEEN

BETWEEN checks whether a value lies within two bounds. In SQL, BETWEEN is inclusive of both endpoints, equivalent to greater-than-or-equal-to the lower bound and less-than-or-equal-to the upper bound.

```sql
SELECT id, name, price
FROM products
WHERE price BETWEEN 100 AND 500;
```

The condition above is equivalent to:

```sql
WHERE price >= 100 AND price <= 500
```

A derived query method can express this with Between:

```java
Flux<Product> findByPriceBetween(
        BigDecimal minimum,
        BigDecimal maximum);
```

With Criteria:

```java
Criteria criteria = Criteria.where("price")
    .between(minimum, maximum);

return template.select(Query.query(criteria), Product.class);
```

### Validating Bounds Before Querying

Before constructing the query, verify:

- Is the lower bound less than or equal to the upper bound?
- Are both endpoints inclusive?
- Do input values match the column's type and precision?
- If one bound is omitted, is it an open-ended range or an invalid request?

If minimum exceeds maximum, it is usually best to return a validation error or empty result according to the defined contract. Avoid silently swapping the two bounds, as that can mask client bugs.

### Time Ranges and Half-Open Intervals [start, end)

For timestamps, a half-open interval is generally easier to compose: inclusive of the start instant and exclusive of the end instant. For example, fetching events within one day:

```sql
SELECT id, occurred_at
FROM audit_event
WHERE occurred_at >= :start
  AND occurred_at < :end;
```

If the start date is 2026-11-15 and the next day is 2026-11-16 in the business timezone, a query using [start, end) captures all timestamps on the 15th without manually constructing 23:59:59.999999.

This avoids bugs caused by timestamp precision differences across the database, driver, and application. When paginating by time, half-open intervals also ensure two adjacent windows neither overlap nor drop boundary records.

A derived method can be declared using two conditions:

```java
Flux<AuditEvent> findByOccurredAtGreaterThanEqualAndOccurredAtLessThan(
        LocalDateTime start,
        LocalDateTime end);
```

If querying time by calendar date, convert the date and timezone into concrete start/end bounds before calling the repository. Do not assume every day is exactly 24 hours in regions observing daylight saving time.

## 7. Combining Value Sets with Value Ranges

A business query often combines multiple condition types. For example, finding active products belonging to certain categories and priced within a range:

```java
Flux<Product> findByStatusAndCategoryIdInAndPriceBetween(
        ProductStatus status,
        Collection<Long> categoryIds,
        BigDecimal minimum,
        BigDecimal maximum);
```

SQL equivalent:

```sql
SELECT id, name, status, category_id, price
FROM products
WHERE status = :status
  AND category_id IN (:categoryIds)
  AND price BETWEEN :minimum AND :maximum;
```

Conditions are joined with AND, so a record must satisfy all of them. If you need to express OR groups, use Criteria or SQL with parentheses to avoid changing meaning via operator precedence.

For example, the requirement "active products within the price range, or promotional products regardless of price" has the logical structure:

```text
(status = ACTIVE AND price BETWEEN min AND max)
OR
(status = PROMOTION)
```

Avoid writing a long chain of conditions without clarifying logical groups. Express groups with SQL parentheses or separate Criteria groups.

## 8. Building Dynamic Queries Using Criteria

Derived query methods work well when the set of conditions is relatively fixed. When requests have many optional filters, a single method approach can lead to too many method variants. Criteria lets you add conditions only when parameters are actually supplied.

For example, searching products by a mandatory status while optionally filtering by minimum price, maximum price, and a set of categories:

```java
public Flux<Product> search(
        ProductStatus status,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        Collection<Long> categoryIds) {

    Criteria criteria = Criteria.where("status").is(status);

    if (minimumPrice != null) {
        criteria = criteria.and("price").greaterThanOrEquals(minimumPrice);
    }

    if (maximumPrice != null) {
        criteria = criteria.and("price").lessThanOrEquals(maximumPrice);
    }

    if (categoryIds != null && !categoryIds.isEmpty()) {
        criteria = criteria.and("categoryId").in(categoryIds);
    }

    Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Direction.ASC, "price"));

    return template.select(query, Product.class);
}
```

In this example:

- Status is always a mandatory condition.
- Minimum price is added only when the request provides a value.
- Maximum price is added only when the request provides a value.
- Category filter is added when the list contains elements.
- Sorting uses the entity's price property.

This code illustrates the case where an empty category list means no category filtering. If the API contract defines an empty list as "no valid categories", return an empty result instead of skipping the condition.

### Distinguishing Omitted Filters from NULL-Valued Filters

For an optional filter, three situations exist:

- Filter omitted: skip the condition.
- Filter provided with a value: compare against that value.
- Filter provided requesting rows with SQL NULL: use an IS NULL condition.

A single Java null variable is usually insufficient to represent all three states. Search DTOs need a clear contract; if clients need to search for NULL, use a flag or a separate condition representation rather than defaulting all nulls to "skip".

## 9. Using DatabaseClient When Explicit SQL Is Needed

For complex queries, SQL can be written directly via DatabaseClient. Input values must be bound rather than concatenated into the SQL string.

Example finding products within a price range and by status:

```java
import java.math.BigDecimal;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;

@Repository
public class ProductSqlRepository {

    private final DatabaseClient databaseClient;

    public ProductSqlRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<ProductSummary> findByPriceRange(
            ProductStatus status,
            BigDecimal minimum,
            BigDecimal maximum) {

        return databaseClient.sql("""
                SELECT id, name, price, status
                FROM products
                WHERE status = :status
                  AND price >= :minimum
                  AND price <= :maximum
                ORDER BY price ASC
                """)
            .bind("status", status.name())
            .bind("minimum", minimum)
            .bind("maximum", maximum)
            .map((row, metadata) -> new ProductSummary(
                row.get("id", UUID.class),
                row.get("name", String.class),
                row.get("price", BigDecimal.class),
                ProductStatus.valueOf(row.get("status", String.class))
            ))
            .all();
    }
}
```

Bind parameters offer several advantages:

- The driver handles values according to their corresponding data types.
- Input data cannot alter SQL structure as string concatenation can.
- The query clearly displays its conditions and parameter types.
- It can help the database/driver reuse query plans or prepared statements depending on execution mechanisms.

Never concatenate client-supplied strings directly into SQL. Bind parameters are for values, not table names, column names, or SQL keywords. If dynamic sorting is needed, map client choices through a list of allowed property/column names before building the ORDER BY clause.

## 10. NULL and Three-Valued Logic in SQL

SQL does not use simple two-valued boolean logic when NULL is present. A comparison against NULL typically yields UNKNOWN rather than TRUE or FALSE.

For example:

```sql
SELECT id
FROM products
WHERE discontinued_at = NULL;
```

This query fails to find rows where discontinued_at is NULL. You must use:

```sql
SELECT id
FROM products
WHERE discontinued_at IS NULL;
```

Similarly, use IS NOT NULL to select rows that have a value.

In derived query methods, you can declare:

```java
Flux<Product> findByDiscontinuedAtIsNull();

Flux<Product> findByDiscontinuedAtIsNotNull();
```

With Criteria:

```java
Criteria criteria = Criteria.where("discontinuedAt").isNull();

Criteria hasDate = Criteria.where("discontinuedAt").isNotNull();
```

Do not replace NULL checks with comparisons against empty strings, 0, or sentinel values. Those values carry their own meaning and may be valid data.

### NOT IN and NULL

A common mistake is using NOT IN with a list containing NULL. Due to three-valued logic, unknown comparisons can prevent the condition from returning expected rows.

If you need to exclude a set of statuses while keeping rows with a NULL status, write it explicitly:

```sql
WHERE status IS NULL
   OR status NOT IN ('CANCELLED', 'ARCHIVED')
```

If you do not want NULL rows, use:

```sql
WHERE status IS NOT NULL
  AND status NOT IN ('CANCELLED', 'ARCHIVED')
```

This policy must come from business rules. Never add or drop an IS NULL branch just to make a query "return something".

## 11. Controlling Order and Grouping of Conditions

A query with AND and OR must clearly express its logical grouping. For instance, selecting active products within a price range or featured products:

```sql
WHERE (status = 'ACTIVE' AND price BETWEEN 100 AND 500)
   OR featured = TRUE
```

When building Criteria, group conditions into clear objects and combine AND/OR according to the API supported by your Spring Data version. If an expression becomes hard to read, explicit SQL with parentheses is often easier to audit.

## 12. Property Names, Column Names, and Data Types

Criteria and derived query methods typically reference entity properties, not physical database column names.

Entity example:

```java
@Table("products")
public record Product(
    @Id UUID id,
    @Column("unit_price") BigDecimal price,
    @Column("created_at") LocalDateTime createdAt
) {}
```

In the repository, use Java properties:

```java
Flux<Product> findByPriceGreaterThan(BigDecimal minimum);

Flux<Product> findByCreatedAtAfter(LocalDateTime moment);
```

In Criteria, also reference properties:

```java
Criteria.where("price").greaterThan(minimum);
```

When writing explicit SQL via DatabaseClient, use actual column names:

```sql
SELECT id, unit_price, created_at
FROM products
WHERE unit_price > :minimum;
```

Confusing property names with column names can prevent query methods from resolving properties or cause explicit SQL to fail with missing-column errors.

Parameter types must also be compatible with column types. For example, compare NUMERIC with BigDecimal, timestamps with mapped temporal types, and enums with the storage representation used by the schema. If custom converters are needed, test both write operations and query conditions.

## 13. Performance: Choosing Appropriate Conditions and Indexes

Logically correct conditions are not guaranteed to run fast. As data grows, the database must decide how to locate matching rows based on indexes, statistics, and execution plans.

Some principles:

- Create indexes for columns frequently used for filtering or joining, based on actual workload.
- For composite indexes, column order should reflect common query conditions and column selectivity.
- Avoid applying functions to columns in WHERE if you want to leverage ordinary indexes, unless a matching functional index exists.
- Select only needed columns instead of always running SELECT on all data.
- Inspect query plans with representative data volumes; do not infer performance solely from the number of conditions.

For example, a common query filtering by status and price range:

```sql
SELECT id, name, price
FROM products
WHERE status = 'ACTIVE'
  AND price >= 100
  AND price < 500;
```

A composite index worth considering:

```sql
CREATE INDEX idx_products_status_price
    ON products (status, price);
```

This is only a design example. The right index depends on query frequency, value distribution, row count, database optimizer behavior, and the write overhead of maintaining additional indexes. Adding an index for every filter increases storage and slows inserts/updates.

### Avoid Transforming Columns in Conditions Unless Necessary

Conditions like:

```sql
WHERE LOWER(email) = LOWER(:email)
```

may fail to use a normal index on email if the database lacks a matching functional index. If case-insensitive search is a frequent requirement, consider an appropriate collation, a normalized column, or a functional index depending on your database engine.

Similarly, type conversions inside WHERE can degrade index usage or produce unintended comparisons. Bind parameters using types that match the column.

## 14. Testing Conditions and Boundary Values

Comparison queries should be tested inside, outside, and right on condition boundaries.

For a price range from 100 to 500 using BETWEEN:

| Value | Expected Result |
| --- | --- |
| 99.99 | No match |
| 100.00 | Match |
| 250.00 | Match |
| 500.00 | Match |
| 500.01 | No match |

For a half-open time interval [start, end):

| Instant | Expected Result |
| --- | --- |
| Before start | No match |
| Exactly at start | Match |
| Between start and end | Match |
| Exactly at end | No match |
| After end | No match |

For value sets, test:

- Single-element list.
- Multi-element list.
- Empty list.
- Omitted list.
- List containing NULL if the API permits that input.
- Rows whose database column value is NULL.

StepVerifier can be used to assert publishers:

```java
@Test
void findsProductsWithinInclusivePriceRange() {
    StepVerifier.create(
            repository.findByPriceBetween(
                new BigDecimal("100.00"),
                new BigDecimal("500.00")
            )
        )
        .expectNextMatches(product ->
            product.price().compareTo(new BigDecimal("100.00")) >= 0
                && product.price().compareTo(new BigDecimal("500.00")) <= 0
        )
        .verifyComplete();
}
```

The example assumes the repository and test data are configured. When comparing BigDecimal in Java, use compareTo for numerical value comparison; equals also compares scale, so 100.0 and 100.00 may not be equal under equals.

For repository query methods and Criteria, write integration tests against the real database type. Mock tests only verify that a service calls a method; they do not prove that generated SQL has the right semantics or that the driver binds data types accurately.

## 15. Common Mistakes When Building Conditions

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using GreaterThan when business logic requires inclusive bounds | Misses records equal to the threshold. | Use GreaterThanEqual or LessThanEqual appropriately. |
| Thinking BETWEEN excludes endpoints | Boundary records are misinterpreted. | Remember BETWEEN includes both lower and upper bounds. |
| Using BETWEEN for full-day dates with end-of-day timestamps | May drop records due to timestamp precision differences. | Use a start-inclusive, end-exclusive half-open interval. |
| Using NOT IN with a list containing NULL | Result can evaluate to UNKNOWN and drop many rows. | Remove NULL from the set or add explicit IS NULL conditions. |
| Not defining empty-list semantics | Query may fail or behave differently across drivers/databases. | Explicitly decide whether to omit the filter or return empty results. |
| Comparing column with = NULL | Fails to find rows with NULL values. | Use IS NULL or IS NOT NULL. |
| Concatenating user values into SQL | SQL injection risk and quoting bugs. | Use bind parameters. |
| Using column names in derived methods | Spring Data cannot resolve the corresponding property. | Use entity property names. |
| Mixing AND and OR without clear grouping | Filter logic diverges from business requirements. | Use parentheses or explicit Criteria groups. |
| Using double for money | Comparison precision errors can appear. | Use BigDecimal with appropriate precision/scale. |

## 16. Workflow for Designing a Dynamic Filter

When implementing a search endpoint or repository query, follow this sequence:

1. **Write rules in business terms:** identify which conditions are mandatory and which are optional.
2. **Choose operators:** equal, not equal, greater than, greater than or equal, less than, IN, NOT IN, or BETWEEN.
3. **Define boundaries:** are range endpoints inclusive; for time ranges, should a half-open interval be used?
4. **Define null semantics:** does a null value mean skip filter, find NULL column, or invalid data?
5. **Define empty sets:** does an empty list mean unrestricted or no results?
6. **Choose implementation:** derived query methods for fixed queries; Criteria for optional conditions; DatabaseClient for SQL requiring direct control.
7. **Bind parameters safely:** never concatenate input data into SQL.
8. **Verify properties and data types:** check against entity mapping, column types, and converters.
9. **Evaluate indexes:** review query plans and actual workload.
10. **Test boundaries:** test values just below, equal to, and just above thresholds; test NULL and empty sets.

Comparison, value set, and range conditions are the foundation of dynamic queries. Spring Data R2DBC allows expressing them via repository method names, Criteria, or explicit SQL. When operator semantics are accurately defined, NULL and boundaries are handled clearly, parameters are safely bound, and real database tests are run, filters produce consistent and maintainable results.
