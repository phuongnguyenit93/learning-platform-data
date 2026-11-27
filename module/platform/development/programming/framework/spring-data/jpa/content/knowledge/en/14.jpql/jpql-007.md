# GROUP BY, HAVING, and Aggregate Functions

JPQL is not limited to retrieving individual entities. You can also group data, calculate total revenue, count orders, compute averages, and filter groups by aggregate conditions. Three clauses commonly work together: **GROUP BY**, **HAVING**, and aggregate functions such as **COUNT**, **SUM**, **AVG**, **MIN**, and **MAX**.

- **GROUP BY** groups result rows by one or more entity attributes.
- **HAVING** filters groups after aggregation.
- **WHERE** filters individual rows before grouping.
- Aggregate functions compute a single value per group or across the entire result set.

JPQL queries entities and Java attributes rather than table/column names directly as in SQL. Understanding this distinction helps you write data reports aligned with the JPA model and return results cleanly through DTOs.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17+, Jakarta Persistence, and Spring Data JPA. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a matching schema. These are files inside a Spring Boot application, not standalone programs runnable via **javac** alone.

## 1. Data Model Used in Examples

We use the **PurchaseOrder** entity to represent orders. Each order has a status, total amount, creation timestamp, and owning customer.

~~~java
package com.example.sales.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

The Customer entity has **id** and **name** attributes:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Suppose the data contains the following orders:

| Order | Customer | Status | Total Amount |
|---|---|---|---:|
| 1 | An | PAID | 500 |
| 2 | An | PAID | 300 |
| 3 | Binh | NEW | 200 |
| 4 | An | SHIPPED | 700 |
| 5 | Binh | PAID | 400 |

A status report needs to return the order count and total amount for each status. This is a classic use case for GROUP BY.

## 2. GROUP BY: Grouping Records

Basic syntax:

~~~sql
SELECT expression, aggregate_function(...)
FROM Entity e
WHERE condition
GROUP BY e.attribute
~~~

In JPQL, entity names and Java attributes are used:

~~~java
@Query("""
    select o.status, count(o), sum(o.totalAmount)
    from PurchaseOrder o
    group by o.status
    """)
List<Object[]> summarizeByStatus();
~~~

The result has one row per status:

| status | count(o) | sum(totalAmount) |
|---|---:|---:|
| NEW | 1 | 200 |
| PAID | 3 | 1200 |
| SHIPPED | 1 | 700 |

Each element in **Object[]** holds status, order count, and total amount in order. This return style works but requires positional casting, which is error-prone when queries evolve. Later sections switch to DTO projections.

### Grouping by Multiple Attributes

You can group by multiple attributes at the same time:

~~~java
@Query("""
    select o.customer.id, o.status, count(o)
    from PurchaseOrder o
    group by o.customer.id, o.status
    """)
List<Object[]> countByCustomerAndStatus();
~~~

Each group is a **customer.id + status** combination. For example, a customer with PAID and SHIPPED orders will appear as two separate groups.

Rule to remember: an expression selected directly in SELECT outside an aggregate function must generally appear in GROUP BY. For instance, if SELECT contains **o.customer.name** and **o.status**, both attributes must be grouped.

~~~java
@Query("""
    select o.customer.name, o.status, sum(o.totalAmount)
    from PurchaseOrder o
    group by o.customer.name, o.status
    """)
List<Object[]> revenueByCustomerAndStatus();
~~~

Do not select a detail attribute that is neither grouped nor aggregated. SQL will reject such queries, and JPQL likewise requires SELECT expressions to conform to grouping semantics.

## 3. Aggregate Functions in JPQL

Standard JPQL supports five common aggregate functions:

| Function | Purpose | Example |
|---|---|---|
| **COUNT** | Count entities or non-null values | **count(o)** |
| **SUM** | Sum numeric values | **sum(o.totalAmount)** |
| **AVG** | Compute average | **avg(o.totalAmount)** |
| **MIN** | Find minimum value | **min(o.totalAmount)** |
| **MAX** | Find maximum value | **max(o.totalAmount)** |

Example calculating overall statistics:

~~~java
@Query("""
    select count(o), sum(o.totalAmount),
           avg(o.totalAmount), min(o.totalAmount),
           max(o.totalAmount)
    from PurchaseOrder o
    where o.status = :status
    """)
Object[] calculateStatistics(@Param("status") OrderStatus status);
~~~

Because the query has no GROUP BY, it returns a single summary row across all orders matching WHERE. The return value is an object array ordered according to SELECT.

### Return Types

Not all aggregate functions return the same type:

| Function | JPQL Result Type |
|---|---|
| **COUNT** | **Long** |
| **AVG** | **Double** |
| **MIN**, **MAX** | Same type as the aggregated expression |
| **SUM** on standard integer types | **Long** |
| **SUM** on **Float/Double** | **Double** |
| **SUM** on **BigInteger** | **BigInteger** |
| **SUM** on **BigDecimal** | **BigDecimal** |

For example, **sum(o.totalAmount)** returns **BigDecimal** because `totalAmount` is `BigDecimal`. Meanwhile, **avg(o.totalAmount)** returns **Double** per JPQL return-type rules, even when the input field is `BigDecimal`.

Declare DTO field types and casts accurately. Never assume `AVG` of `BigDecimal` returns `BigDecimal`.

### COUNT and DISTINCT

**COUNT(o)** counts entities in each group. DISTINCT can be added to count unique values:

~~~java
@Query("""
    select count(distinct o.customer.id)
    from PurchaseOrder o
    where o.status = :status
    """)
Long countDistinctCustomers(@Param("status") OrderStatus status);
~~~

The query above counts distinct customers with orders in the chosen status. If one customer has multiple PAID orders, that customer is counted only once.

**COUNT(path)** ignores null values of the expression. **COUNT(o)** counts selected entities; **COUNT(DISTINCT o.customer.id)** counts distinct customer IDs.

JPQL uses **COUNT(expression)**; do not write SQL-style **COUNT(*)** in standard JPQL.

## 4. How Do WHERE and HAVING Differ?

This is the most important distinction when writing reports.

- **WHERE** filters individual records before grouping.
- **HAVING** filters groups after GROUP BY and aggregation.

Example: keep only orders within a window excluding cancelled orders, then keep statuses with at least 10 orders:

~~~java
@Query("""
    select o.status, count(o), sum(o.totalAmount)
    from PurchaseOrder o
    where o.createdAt >= :from
      and o.createdAt < :to
      and o.status <> :cancelled
    group by o.status
    having count(o) >= :minimumOrders
    order by count(o) desc
    """)
List<Object[]> summarizeStatus(
    @Param("from") LocalDateTime from,
    @Param("to") LocalDateTime to,
    @Param("cancelled") OrderStatus cancelled,
    @Param("minimumOrders") long minimumOrders
);
~~~

Logical execution order:

1. FROM identifies the source entity.
2. WHERE filters out orders not matching the criteria.
3. GROUP BY groups remaining orders by status.
4. HAVING eliminates groups failing the minimum count threshold.
5. SELECT produces aggregate values for each group.
6. ORDER BY sorts the grouped results.

For example, if a status has 8 orders after WHERE filtering and **minimumOrders = 10**, the entire group is eliminated by HAVING.

Do not place aggregate conditions like **count(o) >= 10** inside WHERE. WHERE operates row-by-row before grouping; aggregate conditions belong in HAVING.

### HAVING Does Not Strictly Require an Explicit GROUP BY

You can apply aggregates over the entire result set and filter with HAVING without grouping by an attribute:

~~~java
@Query("""
    select count(o)
    from PurchaseOrder o
    having count(o) >= :minimumOrders
    """)
List<Long> countIfThresholdReached(
    @Param("minimumOrders") long minimumOrders
);
~~~

This query treats the entire dataset as a single aggregate group. If the total order count does not meet the threshold, no row is returned. If you always need a count returned, use a plain COUNT query and inspect the returned value in code.

## 5. Using DTO Projections Instead of Object[]

For reporting queries, DTOs give explicit names to each result field and eliminate manual casting.

Record DTO:

~~~java
package com.example.sales.dto;

import com.example.sales.domain.OrderStatus;
import java.math.BigDecimal;

public record StatusSummary(
    OrderStatus status,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

Repository using a JPQL constructor expression:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select new com.example.sales.dto.StatusSummary(
            o.status,
            count(o),
            sum(o.totalAmount)
        )
        from PurchaseOrder o
        where o.createdAt >= :from
          and o.createdAt < :to
        group by o.status
        having count(o) >= :minimumOrders
        order by count(o) desc
        """)
    List<StatusSummary> summarizeByStatus(
        @Param("from") LocalDateTime from,
        @Param("to") LocalDateTime to,
        @Param("minimumOrders") long minimumOrders
    );
}
~~~

JPQL **new com.example...StatusSummary(...)** requires a constructor whose parameter types and order match the SELECT expressions. Java records provide a canonical constructor, making them convenient for immutable DTOs.

Result handling:

~~~java
List<StatusSummary> summaries =
    repository.summarizeByStatus(
        startOfMonth,
        startOfNextMonth,
        5L
    );

for (StatusSummary summary : summaries) {
    System.out.println(summary.status());
    System.out.println(summary.orderCount());
    System.out.println(summary.revenue());
}
~~~

An aggregate DTO is not a managed entity. It simply holds the report data returned by the query.

## 6. Aggregating by Customer

A common report is total revenue per customer. We group by customer ID and name:

~~~java
public record CustomerRevenue(
    Long customerId,
    String customerName,
    Long orderCount,
    BigDecimal revenue
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.sales.dto.CustomerRevenue(
        o.customer.id,
        o.customer.name,
        count(o),
        sum(o.totalAmount)
    )
    from PurchaseOrder o
    where o.createdAt >= :from
      and o.createdAt < :to
    group by o.customer.id, o.customer.name
    having sum(o.totalAmount) >= :minimumRevenue
    order by sum(o.totalAmount) desc
    """)
List<CustomerRevenue> findCustomerRevenue(
    @Param("from") LocalDateTime from,
    @Param("to") LocalDateTime to,
    @Param("minimumRevenue") BigDecimal minimumRevenue
);
~~~

Here:

- **customer.id** and **customer.name** are the grouped attributes.
- **count(o)** counts orders per customer.
- **sum(o.totalAmount)** calculates revenue per customer.
- **having sum(...) >= ...** retains customers meeting the revenue threshold.
- **order by sum(...) desc** puts highest-revenue customers first.

JPQL uses the property path **o.customer.name** without requiring an explicit JOIN when navigating a valid single-valued association. If the query needs control over join type, join conditions, or optional associations, declare JOIN explicitly.

## 7. Aggregating with JOIN and DISTINCT

When grouping across associations, a JOIN can multiply input rows. For example, an order has multiple line items. Joining PurchaseOrder with OrderLine causes each order to appear multiple times.

~~~java
select o.status, count(o)
from PurchaseOrder o
join o.lines line
group by o.status
~~~

If an order has three line items, that order may be counted three times. When the goal is counting unique orders, use:

~~~java
select o.status, count(distinct o.id)
from PurchaseOrder o
join o.lines line
group by o.status
~~~

If the goal is summing order totals, joining a collection can likewise cause **sum(o.totalAmount)** to add the same order total repeatedly per line row. Understand join cardinality before aggregating.

You may need a subquery, two separate queries, or aggregation at the appropriate entity level to avoid double counting. Do not blindly fix bugs by adding DISTINCT to every aggregate; **SUM(DISTINCT value)** has a very different meaning from deduplicating parent entities by ID.

## 8. NULLs and Empty Result Sets in Aggregate Functions

Aggregate functions follow specific null-handling rules:

- **COUNT(expression)** skips null values of the expression.
- **COUNT(entity)** counts selected entities.
- **SUM**, **AVG**, **MIN**, and **MAX** ignore null values.
- In GROUP BY, rows sharing a null grouping key value are placed into the same group.
- In an aggregate query without GROUP BY over an empty input set, COUNT returns 0 while SUM, AVG, MIN, and MAX return null.

Example:

~~~java
@Query("""
    select count(o), sum(o.totalAmount), avg(o.totalAmount)
    from PurchaseOrder o
    where o.status = :status
    """)
Object[] summarize(@Param("status") OrderStatus status);
~~~

If no orders match, COUNT is 0 while SUM and AVG may be null. When mapping to a DTO or performing further calculations, handle null appropriately.

You can use **COALESCE** in JPQL to substitute a default value for null:

~~~java
@Query("""
    select coalesce(sum(o.totalAmount), 0)
    from PurchaseOrder o
    where o.status = :status
    """)
BigDecimal totalForStatus(@Param("status") OrderStatus status);
~~~

Numeric literals in JPQL must be type-compatible with the aggregated type. For BigDecimal, if a provider/database has type-inference issues with literals, test and consider passing a BigDecimal parameter or handling null in Java.

## 9. ORDER BY with Aggregate Results

You can sort groups by aggregate expressions:

~~~java
@Query("""
    select o.status, count(o)
    from PurchaseOrder o
    group by o.status
    order by count(o) desc
    """)
List<Object[]> findStatusesByOrderCount();
~~~

In some queries, you can alias a SELECT expression and reference the alias in ORDER BY:

~~~java
@Query("""
    select o.status as status, count(o) as orderCount
    from PurchaseOrder o
    group by o.status
    order by orderCount desc
    """)
List<Object[]> findStatusCounts();
~~~

When using constructor DTOs, the simplest approach is sorting directly by the aggregate expression in ORDER BY. Support for aliases and exact syntax details can depend on the provider/version, so verify the query in your actual application.

## 10. Paginating GROUP BY Results

Spring Data JPA can paginate queries via **Pageable**, though GROUP BY queries require careful attention to the count query used to compute total pages.

Example:

~~~java
@Query(
    value = """
        select new com.example.sales.dto.StatusSummary(
            o.status, count(o), sum(o.totalAmount)
        )
        from PurchaseOrder o
        group by o.status
        """,
    countQuery = """
        select count(distinct o.status)
        from PurchaseOrder o
        """
)
Page<StatusSummary> pageStatusSummary(Pageable pageable);
~~~

This count query works because grouping is by a single status attribute. When grouping by multiple attributes, **count(distinct ...)** on a single field no longer counts the number of group combinations accurately. In such cases, design an appropriate count query, use a different projection, or return **Slice**/**List** if total page counts are not required.

Do not assume Spring Data can always derive an accurate count query for every JPQL query with GROUP BY/HAVING. For complex aggregate queries, declare **countQuery** explicitly and test the total element count.

## 11. How Does JPQL Differ from SQL When Using GROUP BY?

JPQL operates on the entity model:

| JPQL | Conceptual SQL Equivalent |
|---|---|
| **PurchaseOrder** | Table **purchase_orders** |
| **o.totalAmount** | Column **total_amount** |
| **o.customer.name** | Accessing an attribute via association/join |
| **count(o)** | Counting matching entities/rows |
| **group by o.status** | Grouping by status column |

In JPQL:

- Use entity names, defaulting to the entity class name or the custom name in **@Entity(name = "...")**.
- Use Java attribute names, not database column names when they differ.
- Use association paths or JOINs to traverse relationships.
- Avoid depending directly on physical table/column names or database-specific syntax.

If database-specific functions or SQL syntax absent from standard JPQL are needed, consider native queries. However, native queries reduce portability and require careful management of result mappings and count queries.

## 12. Common Errors

| Error | Cause | Solution |
|---|---|---|
| Database reports GROUP BY error | SELECT contains a field that is neither grouped nor aggregated | Add the field to GROUP BY or wrap in an aggregate function |
| Putting count condition in WHERE | WHERE executes before grouping | Use HAVING |
| Order count is multiplied | Collection JOIN produces multiple rows per entity | Use `count(distinct entity.id)` when counting unique entities |
| Total amount is multiplied | Join duplicates parent total across child rows | Restructure query or aggregate at the proper data granularity |
| DTO constructor mismatch | Wrong parameter order or types | Verify aggregate return types against constructor |
| AVG of BigDecimal cast wrongly | JPQL AVG returns Double | Declare DTO/variable with the right type or convert intentionally |
| SUM/AVG returns null | No input values or empty dataset | Handle null or use COALESCE |
| Page has wrong total pages | Count query does not count actual groups | Write a `countQuery` matching the grouping |
| JPQL cannot find attribute | Using SQL column name instead of Java field | Use entity names and entity attributes |
| COUNT(*) fails to run | Standard JPQL requires an expression inside COUNT | Use `count(o)` or `count(o.id)` |

## 13. Checklist for Writing Aggregate Queries

- [ ] Determine whether groups are formed by one or multiple attributes.
- [ ] Use entity names and Java attributes in JPQL.
- [ ] Include every non-aggregated SELECT expression in GROUP BY.
- [ ] Use WHERE to filter rows before grouping.
- [ ] Use HAVING to filter groups based on aggregate results.
- [ ] Choose COUNT, SUM, AVG, MIN, or MAX for the right purpose.
- [ ] Verify the return type of each aggregate function.
- [ ] Use DTO projections instead of `Object[]` for long-lived queries.
- [ ] Check whether JOINs multiply rows before counting or summing.
- [ ] Handle null and empty result sets.
- [ ] Declare an explicit `countQuery` when paginating complex groups.
- [ ] Test SQL and results with multiple groups, empty groups, and repeated associations.

## 14. Conclusion

**GROUP BY** organizes entities into groups by attributes; **COUNT**, **SUM**, **AVG**, **MIN**, and **MAX** compute metrics per group; **HAVING** filters groups after aggregation, whereas **WHERE** filters records before grouping.

When writing reporting queries, ensure SELECT fields align with GROUP BY, verify aggregate return types, account for JOIN row multiplication, and handle null values. DTO projections make results clear, and explicit count queries keep pagination accurate.