# Complex Mapping With @SqlResultSetMapping and @ConstructorResult

## Objectives

After this lesson, you will be able to:

- Explain the role of `@SqlResultSetMapping` when mapping native SQL results in JPA.
- Distinguish the three result types: entities via `@EntityResult`, DTOs via `@ConstructorResult`, and single values via `@ColumnResult`.
- Map SQL column names/aliases into a DTO constructor in the exact order and data types required.
- Use `EntityManager.createNativeQuery()` to execute SQL and receive structured results.
- Handle multi-part results, null values, numeric types, and column aliases.
- Choose between native result mapping, JPQL constructor expressions, and Spring Data projections.
- Test mappings on a real database and avoid common pitfalls.

## 1. When Do You Need @SqlResultSetMapping?

JPQL works with entities and Java properties. For standard queries, Spring Data JPA can generate SQL from JPQL or derived queries. However, applications sometimes need to write SQL directly, for example:

- Using CTEs, window functions, database-specific functions, or specialized SQL syntax.
- Tuning reports with multiple joins, `GROUP BY`, and aggregates.
- Querying data from views or legacy table structures.
- Combining data from multiple tables into a DTO without loading full entities.
- Using native queries to leverage features that JPQL cannot express conveniently.

When running native SQL, results come back as JDBC rows and columns. JPA needs to know how to turn those columns into entities, DTOs, or scalar values. `@SqlResultSetMapping` declares these conversion rules.

For example, suppose SQL returns:

| customer_id | customer_name | paid_order_count |
|---:|---|---:|
| 10 | An | 3 |
| 11 | Bình | 0 |

The application may want each row as a `CustomerOrderSummary` object instead of receiving `Object[]` and reading positions manually.

## 2. Three Core Components of SQL Result Mapping

JPA provides three mapping elements commonly used inside `@SqlResultSetMapping`:

| Component | When to Use | Result |
|---|---|---|
| `@EntityResult` | A SQL row represents a mapped entity | Entity |
| `@ConstructorResult` | A SQL row should construct a DTO via its constructor | New DTO instance |
| `@ColumnResult` | A SQL column is a scalar value | Value such as `String`, `Long`, `BigDecimal`, `Date`, etc. |

A single `@SqlResultSetMapping` can declare one or more result groups. Crucially, the SQL statement must return the exact column labels expected by the mapping.

### @EntityResult

Use when mapping native SQL results into an entity:

- `entityClass` specifies the entity class.
- `@FieldResult(name = "...", column = "...")` links a persistent entity property to a column label in the result set.
- `name` is the Java property name on the entity.
- `column` is the SQL column name or alias.

When mapping an entity, the SQL must return all columns needed by the provider to construct the entity per its mapping, including the identifier and columns needed for entity state, associations, or inheritance. Do not select just a few columns and ask JPA to treat the result as a full entity.

### @ConstructorResult

Use when constructing a DTO via a constructor:

- `targetClass` is the DTO class to instantiate.
- `columns` is an array of `@ColumnResult`.
- The declaration order of `columns` must match the constructor parameter order.
- Column names refer to SQL aliases/labels, not Java field names.
- `type` can specify the desired Java type for each column.

This is well suited for reports or native SQL projections.

### @ColumnResult

Use to map a scalar value. For example, if SQL returns a `total_amount` column, the mapping can declare `@ColumnResult(name = "total_amount", type = BigDecimal.class)`.

If a mapping has only one column result, each row is usually returned as a scalar. If there are multiple scalar columns without wrapping them in a constructor DTO, each row is typically returned as an array of values in mapping order.

## 3. Complete Example: Mapping Native SQL Into a DTO

Suppose there are two tables:

**customers**

| id | full_name | enabled |
|---:|---|---|
| 10 | An | true |
| 11 | Bình | true |
| 12 | Chi | false |

**orders**

| id | customer_id | status |
|---:|---:|---|
| 100 | 10 | PAID |
| 101 | 10 | PAID |
| 102 | 10 | PENDING |
| 103 | 11 | PENDING |

Task: retrieve active customers along with their count of paid orders. Customers with no `PAID` orders must still appear with a count of `0`.

### Target DTO

Create a DTO class with a three-argument constructor:

~~~java
package com.example.reporting;

public class CustomerOrderSummary {

    private final Long customerId;
    private final String customerName;
    private final Long paidOrderCount;

    public CustomerOrderSummary(
            Long customerId,
            String customerName,
            Long paidOrderCount) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.paidOrderCount = paidOrderCount;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public Long getPaidOrderCount() {
        return paidOrderCount;
    }
}
~~~

The constructor parameter order is:

1. `Long customerId`
2. `String customerName`
3. `Long paidOrderCount`

This order must match the `@ColumnResult` list declared next.

### Declaring the Mapping on an Entity

You can declare `@SqlResultSetMapping` on a managed type, typically an entity class:

~~~java
package com.example.customer;

import com.example.reporting.CustomerOrderSummary;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.ConstructorResult;
import jakarta.persistence.ColumnResult;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SqlResultSetMapping(
    name = "CustomerOrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = CustomerOrderSummary.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "customer_name", type = String.class),
            @ColumnResult(name = "paid_order_count", type = Long.class)
        }
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false)
    private boolean enabled;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }
}
~~~

The mapping name `CustomerOrderSummaryMapping` must be unique within the persistence unit. When executing the native query, the application passes this exact mapping name to `EntityManager`.

### Native SQL

The SQL uses aliases matching the names in `@ColumnResult`:

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS customer_name,
    COUNT(o.id) AS paid_order_count
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.id
   AND o.status = 'PAID'
WHERE c.enabled = true
GROUP BY c.id, c.full_name
ORDER BY c.id
~~~

The condition `o.status = 'PAID'` is in the `ON` clause. Because this is a `LEFT JOIN`, active customers still appear even when they have no `PAID` orders; `COUNT(o.id)` returns `0` in that case.

Moving `o.status = 'PAID'` into `WHERE` would filter out rows where the `orders` side is null, dropping customers without paid orders.

### Executing With EntityManager

~~~java
package com.example.reporting;

import java.util.List;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerReportRepository {

    @PersistenceContext
    private EntityManager entityManager;

    private static final String SQL = """
        SELECT
            c.id AS customer_id,
            c.full_name AS customer_name,
            COUNT(o.id) AS paid_order_count
        FROM customers c
        LEFT JOIN orders o
            ON o.customer_id = c.id
           AND o.status = 'PAID'
        WHERE c.enabled = true
        GROUP BY c.id, c.full_name
        ORDER BY c.id
        """;

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<CustomerOrderSummary> findPaidOrderSummaries() {
        return entityManager
            .createNativeQuery(SQL, "CustomerOrderSummaryMapping")
            .getResultList();
    }
}
~~~

`createNativeQuery(sql, mappingName)` tells JPA to apply the declared mapping. The result is a list of DTOs instantiated via the constructor, not a list of `Customer` entities.

With the sample data, the expected output is:

~~~text
customerId=10, customerName=An, paidOrderCount=2
customerId=11, customerName=Bình, paidOrderCount=0
~~~

Customer Chi is excluded because `enabled = false`.

This is an integrated example spanning a DTO, entity mapping, and repository; running it requires JPA dependencies, a Spring context, both tables, and matching test data.

## 4. Why Does ConstructorResult Order Matter?

`@ConstructorResult` does not match constructor arguments by DTO field name. The provider passes column results in declared order to invoke the constructor.

Correct example:

~~~java
public CustomerOrderSummary(
        Long customerId,
        String customerName,
        Long paidOrderCount) {
    // ...
}
~~~

Corresponding mapping:

~~~java
@ConstructorResult(
    targetClass = CustomerOrderSummary.class,
    columns = {
        @ColumnResult(name = "customer_id", type = Long.class),
        @ColumnResult(name = "customer_name", type = String.class),
        @ColumnResult(name = "paid_order_count", type = Long.class)
    }
)
~~~

If you reorder the columns:

~~~java
columns = {
    @ColumnResult(name = "customer_name", type = String.class),
    @ColumnResult(name = "customer_id", type = Long.class),
    @ColumnResult(name = "paid_order_count", type = Long.class)
}
~~~

then the constructor must also change to `(String, Long, Long)`. Otherwise, the provider may report that no matching constructor was found during mapping initialization or query execution.

Always verify three places together:

1. Aliases in `SELECT`.
2. Names in `@ColumnResult`.
3. Constructor parameter order and types.

## 5. Data Types and NULL Values

Native SQL returns data types defined by the database and JDBC driver. Types for `COUNT`, `SUM`, `AVG`, timestamps, or numerics can differ across databases.

Use `type` in `@ColumnResult` to declare the desired Java type:

~~~java
@ColumnResult(name = "total_amount", type = BigDecimal.class)
~~~

Key considerations:

- `COUNT` is typically represented as a large integer; `Long` is a common DTO type.
- `SUM` over decimal columns should generally map to `BigDecimal`.
- Nullable columns must use wrapper types like `Long`, `Integer`, `Boolean`—never primitives if null is possible.
- Do not assume all drivers perform numeric conversions identically.
- Test the mapping on the actual deployed database and driver.

For instance, if a query can return a null `discount_rate`, the DTO should use nullable `BigDecimal`. Using `double` could fail on null or fail to represent the absence of a value.

### Column Aliases

`@ColumnResult(name = "customer_id")` references the column label supplied by the JDBC result set. Use clear, stable aliases in SQL:

~~~sql
SELECT c.id AS customer_id
~~~

Alias names can be affected by database case-folding rules when using quoted identifiers. A safe approach is to use lowercase, snake_case, non-duplicate aliases and test on the target database.

Do not confuse:

- `@ColumnResult(name = "...")`: column/alias name in the SQL result.
- `@FieldResult(name = "...", column = "...")`: `name` is the entity property, `column` is the SQL column.
- `@ConstructorResult(targetClass = ...)`: DTO class instantiated via constructor.

## 6. Mapping Results to an Entity With @EntityResult

If native SQL returns a full entity, you can use `@EntityResult`.

Conceptual example:

~~~java
@SqlResultSetMapping(
    name = "CustomerEntityMapping",
    entities = @EntityResult(
        entityClass = Customer.class,
        fields = {
            @FieldResult(name = "id", column = "customer_id"),
            @FieldResult(name = "fullName", column = "customer_name"),
            @FieldResult(name = "enabled", column = "is_enabled")
        }
    )
)
~~~

Where:

- `entityClass` is the entity to instantiate.
- `name` in `FieldResult` is the Java persistent attribute name.
- `column` is the alias in the result set.
- SQL must provide all columns needed by the provider to initialize the entity per its mapping.

Entities are mapped according to identity and persistence context rules. If an entity with the same identity is already managed in the context, JPA honors persistence context identity semantics instead of creating a duplicate Java instance for the same identity.

Do not use `EntityResult` just to fetch a couple of reporting columns. If you do not need entity lifecycle, dirty checking, or associations, a DTO via `ConstructorResult` is lighter and clearer in intent.

## 7. Mapping Scalar Values With @ColumnResult

If a query returns only a single aggregate value, you can use a scalar mapping:

~~~java
@SqlResultSetMapping(
    name = "CustomerRevenueMapping",
    columns = {
        @ColumnResult(name = "total_revenue", type = BigDecimal.class)
    }
)
~~~

Native SQL:

~~~sql
SELECT SUM(o.total_amount) AS total_revenue
FROM orders o
WHERE o.status = 'PAID'
~~~

Execution:

~~~java
BigDecimal revenue = (BigDecimal) entityManager
    .createNativeQuery(SQL, "CustomerRevenueMapping")
    .getSingleResult();
~~~

If no rows match, `SUM` typically returns a single row containing `null`; handle `null` per business rules. By contrast, `COUNT(*)` typically returns `0` when no rows match.

If a mapping has multiple scalar columns, define the result structure and order clearly; use DTO constructor mapping when you want named fields instead of reading `Object[]` by index.

## 8. Combining EntityResult, ConstructorResult, and ColumnResult

A single result set mapping can describe multiple parts of a result row, for example:

- An `Order` entity.
- A DTO holding summary info.
- A scalar such as a total amount or computed flag.

This is useful for reports that need both an entity and aggregated metrics. However, multi-part results are harder to read and tightly coupled to the mapping structure; consider a simple composite DTO if the application only needs a view model.

When declaring multiple result types in one mapping, check the Jakarta Persistence semantics carefully and verify the exact object types returned by your provider. Do not assume a mixed mapping returns a single DTO if it declares multiple result components.

## 9. Using Mappings With NamedNativeQuery

You can name a native query with `@NamedNativeQuery` and associate it with a mapping:

~~~java
@NamedNativeQuery(
    name = "Customer.paidOrderSummary",
    query = """
        SELECT
            c.id AS customer_id,
            c.full_name AS customer_name,
            COUNT(o.id) AS paid_order_count
        FROM customers c
        LEFT JOIN orders o
            ON o.customer_id = c.id
           AND o.status = 'PAID'
        WHERE c.enabled = true
        GROUP BY c.id, c.full_name
        ORDER BY c.id
        """,
    resultSetMapping = "CustomerOrderSummaryMapping"
)
~~~

Invoking via `EntityManager`:

~~~java
List<CustomerOrderSummary> rows = entityManager
    .createNamedQuery(
        "Customer.paidOrderSummary",
        CustomerOrderSummary.class
    )
    .getResultList();
~~~

Typed named queries with DTO constructor mappings are supported by compatible Jakarta Persistence versions. If an older project API/provider lacks the required typed overload, use `createNativeQuery(sql, mappingName)` and verify/cast the results according to the mapping.

Named queries fit well when SQL is static, named, and reused. If SQL depends heavily on runtime conditions, a custom repository with `EntityManager` is more flexible.

## 10. Comparison With JPQL Constructor Expressions

If a query can be written in JPQL, do not use native SQL just to build a DTO.

JPQL constructor expression:

~~~java
@Query("""
    select new com.example.reporting.CustomerOrderSummary(
        c.id,
        c.fullName,
        count(o)
    )
    from Customer c
    left join c.orders o on o.status = :status
    where c.enabled = true
    group by c.id, c.fullName
    order by c.id
    """)
List<CustomerOrderSummary> findSummaryByStatus(
    @Param("status") OrderStatus status
);
~~~

Differences:

| Criterion | JPQL Constructor Expression | Native SQL + SqlResultSetMapping |
|---|---|---|
| Language | Entity names and Java properties | Database table/column names and SQL |
| Portability | Generally higher across databases | May depend on database/dialect |
| DTO | Uses `select new package.Dto(...)` | Uses `@ConstructorResult` |
| Vendor-specific SQL features | Limited by JPQL | Can use database-specific SQL features |
| Mapping | Constructor expression lives inside the query | Mapping is declared separately and reusable |
| Maintenance | Renaming entity properties may require JPQL updates | Changing schema/aliases requires SQL and mapping updates |

Prefer JPQL when the query can be expressed cleanly using the entity model. Choose native SQL when database capabilities or explicit SQL control are required.

## 11. Using With Spring Data JPA

Spring Data JPA supports several ways to declare native queries, though not every version provides the same API for result set mappings.

The most stable, direct approach is a custom repository implementation using `EntityManager`, as shown in section 3. This lets you pass the mapping name explicitly and control transactions, pagination, and parameter binding.

Newer versions of Spring Data JPA provide `@NativeQuery` with a `sqlResultSetMapping` attribute. Availability of that API depends on your Spring Data JPA version; check the documentation for your project's exact BOM version before using it. Do not assume the attribute exists in every version simply because an online example uses it.

If you use standard `@Query(nativeQuery = true)`, confirm how Spring Data converts results. Native queries returning interface projections or DTOs follow their own rules; do not assume they automatically apply a `@SqlResultSetMapping` name unless explicitly configured.

## 12. Paginating Native Queries

With paginated native SQL, you need both a data query and a count query. The count query must count the right logical result set, especially when joins or `GROUP BY` are present.

Example in a custom repository:

~~~java
Query dataQuery = entityManager.createNativeQuery(
    DATA_SQL,
    "CustomerOrderSummaryMapping"
);

dataQuery.setFirstResult(page * size);
dataQuery.setMaxResults(size);

@SuppressWarnings("unchecked")
List<CustomerOrderSummary> content = dataQuery.getResultList();

Query countQuery = entityManager.createNativeQuery(COUNT_SQL);
long total = ((Number) countQuery.getSingleResult()).longValue();
~~~

If the query uses `GROUP BY`, the count query may need to count groups via a subquery rather than counting rows in the base table directly. Do not use `COUNT(*)` over join rows if the goal is counting unique customers.

Validate `page` and `size` to avoid negative values or excessively large page sizes. Sort ordering must be deterministic; add a unique key as a tie-breaker when multiple rows share the same sort values.

## 13. Security and Parameterizing SQL

Never concatenate user input directly into SQL strings:

~~~java
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
~~~

This creates an SQL injection vulnerability.

Use parameter binding:

~~~java
Query query = entityManager.createNativeQuery(
    "SELECT * FROM customers WHERE email = :email",
    "CustomerEntityMapping"
);

query.setParameter("email", email);
~~~

Parameter binding applies to data values, not table names, column names, or SQL keywords. If you need dynamic sorting or column selection, use a whitelist of valid choices and assemble controlled identifiers only.

Never inject mapping names, table names, or SQL fragments from external requests into a query without validation.

## 14. Testing Mappings

Integration tests should verify:

- SQL returns the expected column labels.
- The mapping name is spelled correctly and registered in the persistence unit.
- DTO constructor order and types match.
- Nullable columns map to appropriate wrapper types.
- `LEFT JOIN` results produce null/zero properly on unmatched sides.
- Aggregates like `COUNT`/`SUM` return expected data types.
- The query runs on the target database and driver.
- Pagination and count queries count accurately.

Repository test example:

~~~java
@DataJpaTest
@Import(CustomerReportRepository.class)
class CustomerReportRepositoryTest {

    @Autowired
    CustomerReportRepository reportRepository;

    @Test
    void mapsNativeRowsIntoCustomerSummaryDto() {
        List<CustomerOrderSummary> rows =
                reportRepository.findPaidOrderSummaries();

        assertEquals(2, rows.size());

        assertEquals(10L, rows.get(0).getCustomerId());
        assertEquals("An", rows.get(0).getCustomerName());
        assertEquals(2L, rows.get(0).getPaidOrderCount());

        assertEquals(11L, rows.get(1).getCustomerId());
        assertEquals("Bình", rows.get(1).getCustomerName());
        assertEquals(0L, rows.get(1).getPaidOrderCount());
    }
}
~~~

This test assumes the test database is seeded with the `customers`/`orders` data from section 3. You can seed data using `@Sql`, `data.sql`, or repository setup inside the test. When using Testcontainers, run the same database engine as production to verify real aliases, data types, and SQL dialect behavior.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Mapping not found | Misspelled mapping name or not registered in persistence unit | Check spelling and the managed type holding the annotation |
| DTO constructor not found | `ColumnResult` order or types do not match constructor | Compare aliases, column order, and constructor signature |
| DTO values are swapped | `columns` declared in a different order than constructor | Reorder `ColumnResult` entries to match parameter order |
| Unexpected null columns | Wrong alias, unmatched `LEFT JOIN`, or actual null data | Inspect SQL result set and column labels |
| `ClassCastException` on `COUNT`/`SUM` | JDBC type differs from assumed DTO type | Specify `ColumnResult` `type` explicitly and verify driver behavior |
| SQL executes but mapping fails | `SELECT` aliases do not match `ColumnResult`/`FieldResult` | Use stable aliases and consistent names |
| `EntityResult` missing data | SQL does not return all required entity columns | Select all columns or use a DTO if partial data is enough |
| Native query is not portable | Uses database-specific functions or syntax | Test per target database and isolate vendor SQL |
| Wrong `Page` total | Count query counts joined rows instead of groups/entities | Write a count query with the right semantics |
| SQL injection | Input strings concatenated directly into SQL | Use named or positional parameter binding |

## Pre-Merge Checklist

- [ ] Determined whether the result should be an entity, DTO, or scalar.
- [ ] Mapping name is unique and registered in the persistence unit.
- [ ] `SELECT` aliases match `ColumnResult`/`FieldResult` exactly.
- [ ] `ConstructorResult` columns match constructor order and types.
- [ ] DTO uses wrapper types for nullable columns.
- [ ] Aggregate types verified on target database/driver.
- [ ] `EntityResult` returns all columns required by the entity.
- [ ] Native SQL uses parameter binding; no user input concatenated.
- [ ] Count query and pagination semantics are accurate.
- [ ] Integration tests verify data, nulls, numeric types, and mapping on an appropriate database.

## Conclusion

`@SqlResultSetMapping` describes how JPA transforms native SQL results into entities, DTOs, or scalars. `@EntityResult` maps entities, `@ConstructorResult` creates DTOs via constructors, and `@ColumnResult` maps individual columns. For constructor mappings, SQL aliases must match column result names, while column order and types must match the constructor. Use `EntityManager` with a mapping name when you need explicit control over native queries; prefer JPQL constructor expressions when the query can be expressed over the entity model. Always test mappings against a real database and driver, especially for aliases, aggregates, nulls, and pagination.