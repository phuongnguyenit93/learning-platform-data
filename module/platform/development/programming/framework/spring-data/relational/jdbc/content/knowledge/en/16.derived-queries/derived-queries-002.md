# Querying by Direct Properties of the Aggregate Root

Spring Data JDBC supports **derived queries**: the framework parses the repository method name, resolves properties in the domain type, and generates the appropriate SQL. This approach is useful when the filter conditions reside directly on the aggregate root, such as `customerId`, `status`, `totalAmount`, or `createdAt` on `PurchaseOrder`.

This lesson focuses on naming methods after direct Java properties of the root, combining conditions, sorting, and limiting results. At the same time, we will distinguish root queries from queries across child collections or other aggregates.

## 1. Order Model

Suppose `PurchaseOrder` is the aggregate root:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    Long customerId,
    String status,
    BigDecimal totalAmount,
    LocalDateTime createdAt,
    String note,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}
```

Direct properties:

| Java property | Meaning | Conventional SQL column |
| --- | --- | --- |
| `id` | Order ID. | `id` |
| `customerId` | Referenced customer ID. | `customer_id` |
| `status` | Order status. | `status` |
| `totalAmount` | Total amount. | `total_amount` |
| `createdAt` | Creation timestamp. | `created_at` |
| `note` | Optional note. | `note` |

`customerId` is a scalar ID sitting directly on `PurchaseOrder`, not a `Customer` object loaded automatically. Therefore, the `findByCustomerId(...)` method targets a property of the root.

## 2. Derived Query Name Structure

Repository:

```java
package com.example.orders.repository;

import java.util.List;
import java.util.Optional;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByCustomerId(Long customerId);

    List<PurchaseOrder> findByStatus(String status);

    Optional<PurchaseOrder> findByIdAndCustomerId(
        Long id,
        Long customerId
    );
}
```

Spring Data generates implementations of the query methods when initializing the repository. A derived query typically follows the structure:

```text
findBy + Property + Operator + And/Or + Property + OrderBy + Sort
```

For example, `findByStatusAndCustomerIdOrderByCreatedAtDesc` means:

1. `findBy`: begins the query.
2. `Status`: filters by the `status` property.
3. `And`: combines the next condition using AND.
4. `CustomerId`: filters by `customerId`.
5. `OrderByCreatedAtDesc`: sorts by `createdAt` descending.

Method names are based on **Java properties**, not SQL column names. Even if the naming strategy maps `customerId` to `customer_id`, the method name remains `findByCustomerId`.

## 3. Querying by a Single Property

Commonly used methods:

```java
List<PurchaseOrder> findByCustomerId(Long customerId);

List<PurchaseOrder> findByStatus(String status);

List<PurchaseOrder> findByTotalAmount(BigDecimal totalAmount);

List<PurchaseOrder> findByCreatedAt(LocalDateTime createdAt);
```

These methods express equality conditions on the corresponding properties:

| Method | Conceptual SQL condition |
| --- | --- |
| `findByCustomerId(7L)` | `WHERE customer_id = ?` |
| `findByStatus("CREATED")` | `WHERE status = ?` |
| `findByTotalAmount(amount)` | `WHERE total_amount = ?` |
| `findByCreatedAt(time)` | `WHERE created_at = ?` |

Calling the repository:

```java
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByCustomerId(7L);

List<PurchaseOrder> createdOrders =
    purchaseOrderRepository.findByStatus("CREATED");
```

Parameter values are bound via JDBC. Do not concatenate input directly into an SQL string. Parameter binding ensures the driver handles data types properly and prevents SQL injection caused by arbitrary string concatenation.

## 4. Combining Conditions with And and Or

Use `And` when all conditions must be true:

```java
List<PurchaseOrder> findByCustomerIdAndStatus(
    Long customerId,
    String status
);
```

SQL intent:

```sql
SELECT ...
FROM purchase_order
WHERE customer_id = ?
  AND status = ?;
```

Use `Or` when either condition may be true:

```java
List<PurchaseOrder> findByStatusOrNote(
    String status,
    String note
);
```

SQL intent:

```sql
SELECT ...
FROM purchase_order
WHERE status = ?
   OR note = ?;
```

When a method has multiple `And` and `Or` keywords, read carefully how the parser groups conditions. If an expression requires multiple parenthesized groups or hard-to-express logic, `@Query` or a custom repository with explicit SQL is usually easier to understand and review.

## 5. Common Filtering Operators

The set of supported keywords may depend on the repository type and Spring Data JDBC version. The examples below are common query derivation forms; for less common keywords, check the documentation for your project's exact version.

### Comparisons and ranges

```java
List<PurchaseOrder> findByTotalAmountGreaterThan(BigDecimal minimum);

List<PurchaseOrder> findByTotalAmountGreaterThanEqual(BigDecimal minimum);

List<PurchaseOrder> findByTotalAmountLessThan(BigDecimal maximum);

List<PurchaseOrder> findByTotalAmountBetween(
    BigDecimal minimum,
    BigDecimal maximum
);
```

Illustrative SQL meaning:

```sql
WHERE total_amount > ?
WHERE total_amount >= ?
WHERE total_amount < ?
WHERE total_amount BETWEEN ? AND ?
```

`Between` typically represents a range inclusive of both endpoints under SQL semantics. If business rules require a half-open interval such as [from, to), combine `GreaterThanEqual` and `LessThan` to make it explicit.

### Null checks

```java
List<PurchaseOrder> findByNoteIsNull();

List<PurchaseOrder> findByNoteIsNotNull();
```

These correspond to `WHERE note IS NULL` and `WHERE note IS NOT NULL`. Use `IsNull`/`IsNotNull` to express intent clearly rather than passing null to an equality method.

### String matching

For `String` properties, you can use:

```java
List<PurchaseOrder> findByNoteContaining(String text);

List<PurchaseOrder> findByNoteStartingWith(String prefix);

List<PurchaseOrder> findByNoteEndingWith(String suffix);

List<PurchaseOrder> findByNoteLike(String pattern);
```

These forms are generally translated into `LIKE` conditions with the corresponding wildcards. With `Like`, be mindful of `%` and `_`. Case sensitivity depends on collation and dialect; do not assume every database performs case-insensitive searches.

### Searching within a list of values

```java
List<PurchaseOrder> findByStatusIn(Collection<String> statuses);

List<PurchaseOrder> findByStatusNotIn(Collection<String> statuses);
```

Example:

```java
var statuses = List.of("CREATED", "CONFIRMED");
List<PurchaseOrder> orders =
    purchaseOrderRepository.findByStatusIn(statuses);
```

In SQL terms, `IN` creates a parameter list. Handle empty collections in the service layer before calling the repository because `IN ()` is not uniformly supported; whether to return an empty list or omit the filter must follow the business contract.

## 6. Sorting and Limiting Results

You can declare the sort order directly in the method name:

```java
List<PurchaseOrder> findByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);

List<PurchaseOrder> findByStatusOrderByTotalAmountAscCreatedAtDesc(
    String status
);
```

- `Asc`: ascending order.
- `Desc`: descending order.

Fetching a customer's newest order:

```java
Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDesc(
    Long customerId
);
```

Fetching up to 10 newest orders with a given status:

```java
List<PurchaseOrder> findTop10ByStatusOrderByCreatedAtDesc(
    String status
);
```

`First` and `Top` limit the number of results. If multiple rows can share the same timestamp, add a deterministic secondary property such as ID:

```java
List<PurchaseOrder> findTop10ByStatusOrderByCreatedAtDescIdDesc(
    String status
);
```

Do not load all orders for a customer and slice the list in Java when the database can filter, sort, and limit directly in SQL. Pagination capabilities and paging parameter types should be verified against your Spring Data JDBC version; do not assume every Spring Data JPA API is present in JDBC.

## 7. Choosing the Right Return Type

| Return type | Meaning | Use when |
| --- | --- | --- |
| `List<PurchaseOrder>` | A list, possibly empty. | Multiple orders are possible. |
| `Iterable<PurchaseOrder>` | An iterable result set. | Specific `List` APIs are not needed. |
| `Optional<PurchaseOrder>` | Zero or one result. | Unique condition or method with First/Top. |
| `long` | Number of matching rows. | `countBy...`. |
| `boolean` | Whether any match exists. | `existsBy...`. |

Example:

```java
long countByCustomerId(Long customerId);

boolean existsByCustomerIdAndStatus(
    Long customerId,
    String status
);
```

`Optional` is only suitable when the query returns at most one result. If the condition is not unique and multiple rows match, the framework may throw a non-unique result error. If you only need one row in a specific order, use `First`/`Top` with `OrderBy`.

Methods such as `findById`, `existsById`, and `deleteById` are already provided by `CrudRepository`. There is no need to redeclare them just to query by ID.

## 8. Java Property Name Differs from SQL Column Name

Suppose a property is mapped using an annotation:

```java
@Column("order_state")
String status
```

Even though the actual column name is `order_state`, the method still uses the property name:

```java
List<PurchaseOrder> findByStatus(String status);
```

Do not use `findByOrderState(...)` unless the class actually has an `orderState` property. `@Column` changes the property-to-column mapping, not the property name in the domain model.

Similarly, a naming strategy may convert `createdAt` to `created_at`, yet the method still uses `findByCreatedAt...`.

## 9. Root Boundaries and Querying Child Entities or Other Aggregates

A derived query on direct properties can target:

- `PurchaseOrder.customerId`
- `PurchaseOrder.status`
- `PurchaseOrder.totalAmount`
- `PurchaseOrder.createdAt`

Meanwhile, `PurchaseOrder.lines` is a child collection; each `OrderLine` has `productId`. A query to "find orders that have an order line containing productId = 11" involves the child table, not a direct property of the root. Do not assume the parser can traverse arbitrary collections or object graphs as in JPA.

When you need to query by child rows, you can write an explicit SQL join:

```sql
SELECT DISTINCT po.id,
       po.customer_id,
       po.status,
       po.total_amount,
       po.created_at,
       po.note
FROM purchase_order po
JOIN order_line ol ON ol.order_id = po.id
WHERE ol.product_id = :productId;
```

This SQL illustrates the join condition. If mapping the result into a full aggregate, ensure the query and mapping provide all required data according to Spring Data JDBC's contract. For reports or search screens, a DTO or projection is often a better fit.

Likewise, `findByCustomerId(7L)` only filters by the `customer_id` column; it does not automatically join the customer table and construct a `Customer` object. If you need to filter by customer name, use an explicit SQL join or look up the customer first and then use its ID, depending on requirements and performance.

## 10. Derived SQL and How to Observe It

Method:

```java
List<PurchaseOrder> findByCustomerIdAndStatusOrderByCreatedAtDesc(
    Long customerId,
    String status
);
```

Conceptually, the SQL is:

```sql
SELECT id,
       customer_id,
       status,
       total_amount,
       created_at,
       note
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC;
```

Runtime SQL may add aliases, quoting, mapping adjustments, or child-collection loading queries depending on the version and dialect. The SQL above only describes the intent, not a guaranteed verbatim output.

Enable logging in development to inspect it:

```yaml
logging:
  level:
    org.springframework.jdbc.core: DEBUG
    org.springframework.data.jdbc.core: DEBUG
```

When reading the logs, verify the root table, WHERE columns, parameter order and types, as well as queries loading child collections. Do not enable logs containing sensitive data in production without proper protection policies.

## 11. Indexes and Performance

Derived queries do not automatically make queries fast. The database still needs appropriate indexes for filtering and sorting conditions.

If the application frequently looks up orders by customer, status, and most recent timestamp:

```sql
CREATE INDEX idx_order_customer_status_created
ON purchase_order (customer_id, status, created_at DESC);
```

If it frequently filters by status and timestamp:

```sql
CREATE INDEX idx_order_status_created
ON purchase_order (status, created_at DESC);
```

Do not create an index for every property simply because a `findBy...` method exists. Indexes increase write cost and storage usage. Base index decisions on workload, selectivity, execution plans, and query statistics.

A derived query returning `List<PurchaseOrder>` may load the aggregate together with its child components according to the mapping. If a customer has tens of thousands of orders, avoid returning all of them at once; use result limits or an appropriate query/projection.

## 12. When to Use @Query or a Custom Repository

Derived queries work well when conditions lie on direct properties and can be expressed concisely in the method name.

| Need | Commonly appropriate choice |
| --- | --- |
| Filter by `status` or `customerId` | Derived query. |
| Combine a few AND/OR conditions | Derived query if the name remains easy to understand. |
| Filter by date/price range | Derived query with appropriate operators. |
| Join child tables or other aggregates | `@Query` or custom repository. |
| Complex `SUM/COUNT/GROUP BY` aggregations | Explicit SQL and DTO/projection. |
| Vendor-specific functions or hints | Custom SQL suited to the database. |
| Method name becomes too long | `@Query` for clear expression. |

Example of SQL declared on a repository method (annotation syntax and parameter binding must match your Spring Data JDBC version):

```java
@Query("""
    SELECT id, customer_id, status, total_amount, created_at, note
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
    Long customerId,
    String status
);
```

When using `@Query`, the application is responsible for SQL syntax, column names, parameter binding, and dialect compatibility. For aggregates with child collections, verify how the query method maps results and loads child collections. Do not treat a query returning only a few columns as a complete aggregate.

## 13. Common Mistakes in Method Naming

| Error | Cause | How to fix |
| --- | --- | --- |
| Property not found | Method uses SQL column name or wrong Java property name. | Use the actual property name in the class. |
| Method too long | Packing too many conditions into a derived query. | Split the query or use `@Query`. |
| `Optional` throws error | Condition returns multiple rows when method expects one. | Use `List` or limit with `First`/`Top`. |
| Case sensitivity differences | Expecting collation to match another database. | Check collation/dialect and normalize data. |
| Empty `IN` list | SQL `IN ()` is not portable. | Handle empty input in the service layer. |
| Root query too heavy | Returning full aggregates along with child collections. | Limit results or use a DTO/projection. |
| Querying related table field fails | Assuming derived queries auto-join other aggregates. | Use scalar IDs or explicit SQL joins. |
| Unsupported keyword | Version/repository differences. | Check reference docs and startup errors. |

An invalid method name can cause Spring to fail repository initialization as soon as the application context is created. Read the property-not-found error and compare it against the domain type in `CrudRepository<PurchaseOrder, Long>`.

## 14. Practice Exercise

Sample data:

```sql
INSERT INTO purchase_order
    (customer_id, status, total_amount, created_at, note)
VALUES
    (7, 'CREATED',   285000.00, '2026-11-01 09:00:00', NULL),
    (7, 'CONFIRMED', 450000.00, '2026-11-02 10:30:00', 'Morning delivery'),
    (8, 'CREATED',   120000.00, '2026-11-03 11:00:00', NULL),
    (7, 'CANCELLED',  99000.00, '2026-11-04 14:00:00', 'Cancelled by customer');
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByCustomerId(Long customerId);

    List<PurchaseOrder> findByStatusAndCustomerIdOrderByCreatedAtDesc(
        String status,
        Long customerId
    );

    List<PurchaseOrder> findByTotalAmountBetween(
        BigDecimal min,
        BigDecimal max
    );

    List<PurchaseOrder> findByNoteIsNull();

    Optional<PurchaseOrder> findFirstByCustomerIdOrderByCreatedAtDesc(
        Long customerId
    );

    long countByStatus(String status);

    boolean existsByCustomerIdAndStatus(
        Long customerId,
        String status
    );
}
```

Practice tasks:

1. Find all orders for customer 7 using `findByCustomerId`.
2. Find `CREATED` orders for customer 7 and sort newest first.
3. Find orders with total amount in a range using `Between`.
4. Find orders without a note using `IsNull`.
5. Fetch the newest order for customer 7 using `First` and `OrderBy`.
6. Count orders by status and check whether the customer has any `CONFIRMED` orders.
7. Enable SQL logging, and compare the conditions and parameters with the results.
8. Add an appropriate index for a frequent query and compare execution plans before and after.
9. Write integration tests for empty results, a single result, multiple results, and null values.
10. Try querying by `OrderLine.productId` with an SQL join and compare it with a derived query on the root.

## 15. Self-Check Questions

- What is a derived query, and where does Spring Data JDBC get property names from?
- Why does `findByCustomerId` use `customerId` instead of the column name `customer_id`?
- What logic do `And` and `Or` express?
- When are `Between`, `IsNull`, `In`, and `Containing` used?
- When should you return `List`, and when should you use `Optional`?
- What problem does `Top10By...OrderBy...Desc` solve?
- Why doesn't `findByCustomerId` automatically load the `Customer` object?
- When should you use `@Query` or a custom repository?
- Why doesn't a derived query guarantee performance if indexes are missing?
- When searching by `OrderLine.productId`, why must you consider querying the child table?

Derived queries work best when filter conditions sit on direct properties of the aggregate root and can be expressed clearly in the method name. Name methods after **Java properties**, choose return types according to cardinality, inspect the SQL, and add indexes based on the workload. When a query crosses root boundaries or requires complex joins or aggregations, switch to explicit SQL and an appropriate DTO instead of stretching out an unreadable method name.
