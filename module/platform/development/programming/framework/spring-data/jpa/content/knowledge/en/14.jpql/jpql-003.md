# SELECT, WHERE, ORDER BY, and Conditional Expressions in JPQL

JPQL (Jakarta Persistence Query Language) is JPA's entity-oriented query language. JPQL uses entity names and Java attributes from the persistence model, and a provider such as Hibernate translates the query into database-specific SQL. Therefore, JPQL typically does not reference physical table or column names directly.

The three basic clauses of a read query are:

- **SELECT** specifies the data to return: entities, single attributes, multiple values, or DTOs.
- **WHERE** filters rows based on a logical condition.
- **ORDER BY** sorts the results by attributes or expressions.

Conditional expressions include comparisons, logical operators, NULL checks, BETWEEN, IN, LIKE, EXISTS, and other expressions. Understanding data types, null semantics, and parameter binding helps make queries accurate, safe, and easy to optimize.

This document uses Jakarta Persistence with the `jakarta.persistence` namespace in Spring Boot 3 / Spring Framework 6 and later. Older Spring Boot 2 projects typically use `javax.persistence`.

## 1. How Does JPQL Differ from SQL?

Suppose we have an entity:

```java
@Entity
@Table(name = "product")
public class Product {
    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    private Boolean active;

    @Column(name = "created_at")
    private Instant createdAt;
}
```

SQL queries tables and columns:

```sql
select p.id, p.name
from product p
where p.price >= 100
order by p.name;
```

JPQL queries entities and attributes:

```jpql
select p
from Product p
where p.price >= 100
order by p.name
```

Key differences:

- `Product` is the entity name; by default it is the entity class name, not the table name.
- `p.price` and `p.name` are mapped Java attributes, not physical column names.
- JPQL understands entity relationships and can navigate associations.
- JPQL does not write `select *`.
- JPQL does not write physical table names in `FROM`, unless using native SQL via a separate API.
- JPQL is validated against the entity model and translated by the provider into dialect-specific SQL.

JPQL keywords are generally case-insensitive, while entity names, aliases, and attributes should match the casing in the mapping. The entity name can be customized with `@Entity(name = "...")`; in that case, JPQL uses the declared entity name.

## 2. Basic SELECT Query Structure

A JPQL select query has the general form:

```jpql
SELECT [DISTINCT] select_item
FROM entity_name identification_variable
[JOIN ...]
[WHERE conditional_expression]
[GROUP BY ...]
[HAVING ...]
[ORDER BY ...]
```

This lesson focuses on SELECT, WHERE, ORDER BY, and conditional expressions. GROUP BY/HAVING is a separate topic and appears only when distinguishing aggregate results.

Example:

```jpql
select p
from Product p
where p.active = true
order by p.createdAt desc, p.id desc
```

- `Product p`: declares the entity range variable `p`.
- `select p`: returns the `Product` entity.
- `where p.active = true`: retrieves only active products.
- `order by p.createdAt desc, p.id desc`: sorts newest first; if timestamps are equal, larger ID comes first.

Alias `p` is used to reference attributes. An alias can be a single letter or a meaningful name like `product`, while avoiding reserved keywords.

## 3. SELECT Result Types

### 3.1. Returning an Entity

```jpql
select p
from Product p
where p.active = true
```

In a repository:

```java
@Query("""
    select p
    from Product p
    where p.active = true
    order by p.name asc, p.id asc
    """)
List<Product> findActiveProducts();
```

The result is the `Product` entity. If loaded within a transaction/persistence context, the entity can be managed and attribute changes will be tracked by dirty checking.

Do not expose entities beyond the service boundary and serialize them arbitrarily if the entity has lazy associations. Use DTOs/projections when an API only needs a subset of data.

### 3.2. Returning a Single Attribute

```jpql
select p.name
from Product p
where p.active = true
order by p.name
```

Repository:

```java
@Query("""
    select p.name
    from Product p
    where p.active = true
    order by p.name
    """)
List<String> findActiveProductNames();
```

The return type must match the selected attribute. Selecting `p.price` corresponds to `BigDecimal`; selecting `p.id` corresponds to `Long`.

### 3.3. Selecting Multiple Values

When selecting multiple expressions without a DTO constructor expression, each row is typically returned as an `Object[]`:

```jpql
select p.id, p.name, p.price
from Product p
where p.active = true
```

You can receive it as:

```java
List<Object[]> rows = query.getResultList();
for (Object[] row : rows) {
    Long id = (Long) row[0];
    String name = (String) row[1];
    BigDecimal price = (BigDecimal) row[2];
}
```

This approach is quick to demonstrate but lacks type safety and is prone to index errors. In real applications, DTO projections are usually clearer.

### 3.4. DISTINCT

`DISTINCT` eliminates duplicate results according to the semantics of the select item:

```jpql
select distinct p.category
from Product p
where p.active = true
```

With entities and JOINs, DISTINCT is commonly used to avoid repeating an entity in results when one parent row matches multiple child rows. Distinguish deduplication of JPQL results from the fact that the database may return multiple rows after a JOIN; the provider may apply distinct in SQL or at the result layer depending on the query and version.

Do not add DISTINCT out of habit without understanding why a JOIN produces duplicate records. DISTINCT can make a query heavier and cannot fix a JOIN with the wrong cardinality.

## 4. DTO Projection with Constructor Expressions

JPQL supports constructor expressions with the syntax `select new fully.qualified.Dto(...)`. The DTO must have a constructor matching the order and types of the expressions.

```java
package com.example.product;

public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
```

JPQL:

```java
@Query("""
    select new com.example.product.ProductSummary(
        p.id, p.name, p.price
    )
    from Product p
    where p.active = true
    order by p.name asc, p.id asc
    """)
List<ProductSummary> findActiveSummaries();
```

With a Java record, the canonical constructor can be used if the provider supports constructor expressions and matching parameter types properly. The class name in JPQL must be a fully qualified class name; JPQL does not support `new ProductSummary(...)` without full qualification.

DTO projections help:

- Fetch only the needed columns.
- Avoid passing managed entities/lazy proxies outside the service layer.
- Produce stable shapes for APIs and reports.
- Reduce data transferred from the database when the query does not need the full entity.

## 5. WHERE and Comparison Operators

WHERE accepts a conditional expression returning a boolean value. Basic comparison operators:

| Operator | Meaning | Example |
|---|---|---|
| `=` | Equal | `p.status = :status` |
| `<>` | Not equal | `p.status <> :status` |
| `>` | Greater than | `p.price > :min` |
| `>=` | Greater than or equal | `p.price >= :min` |
| `<` | Less than | `p.createdAt < :cutoff` |
| `<=` | Less than or equal | `p.price <= :max` |

Example:

```jpql
select p
from Product p
where p.price >= :minPrice
  and p.price <= :maxPrice
```

Do not compare two incompatible types. For example, avoid comparing a `LocalDate` attribute with an arbitrary string or comparing an enum with a table name. Parameter types must match the entity attribute.

## 6. AND, OR, NOT, and Parentheses

JPQL supports logical operators:

- `AND`: both conditions must be true.
- `OR`: at least one condition must be true.
- `NOT`: negates a condition.

Standard operator precedence is NOT, AND, OR. When an expression has multiple operators, use parentheses to clarify intent:

```jpql
select p
from Product p
where p.active = true
  and (p.category = :category or p.featured = true)
```

If parentheses are omitted:

```jpql
where p.active = true
  and p.category = :category
   or p.featured = true
```

Then OR may cause the query to return featured products even when `active=false`, because AND has higher precedence than OR. This is a common logic bug.

With many optional filters, expressions can grow long and hard to maintain. Consider `Specification`, the Criteria API, or dynamic query building rather than creating a WHERE clause with dozens of OR branches.

## 7. NULL and Three-Valued Logic

SQL/JPQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. When an operand is NULL, standard comparisons typically evaluate to UNKNOWN rather than TRUE/FALSE.

Incorrect:

```jpql
where p.description = null
```

Correct:

```jpql
where p.description is null
```

Checking for non-NULL:

```jpql
where p.description is not null
```

Combined example:

```jpql
select p
from Product p
where p.deletedAt is null
  and p.price is not null
```

Do not use `= null` or `<> null`. Use `IS NULL` and `IS NOT NULL`.

When a parameter can be null, a common pattern is:

```jpql
where (:status is null or p.status = :status)
```

If `status` is null, the filter is skipped; if a value is provided, only matching statuses are returned. While convenient, OR can make it harder for the optimizer to use indexes in some databases. For many optional filters or large datasets, dynamic queries/`Specification` can produce cleaner predicates.

## 8. BETWEEN

`BETWEEN` checks whether a value lies within an inclusive range:

```jpql
select p
from Product p
where p.price between :minPrice and :maxPrice
```

Semantically equivalent to:

```jpql
where p.price >= :minPrice
  and p.price <= :maxPrice
```

For dates and times, watch the upper bound. When filtering data within a single day, using a half-open interval is generally safer:

```jpql
where p.createdAt >= :start
  and p.createdAt < :nextDay
```

This avoids timestamp precision issues and eliminates guessing an "end-of-day" value like `23:59:59.999`.

## 9. IN and NOT IN

`IN` checks whether a value is contained in a list or subquery result:

```jpql
select p
from Product p
where p.status in :statuses
```

Repository:

```@Query("""
    select p
    from Product p
    where p.status in :statuses
    """)
List<Product> findByStatuses(
    @Param("statuses") Collection<ProductStatus> statuses
);
```

You can also use `NOT IN`:

```jpql
where p.status not in :excludedStatuses
```

Notes:

- An empty collection parameter may be handled differently across providers or produce invalid SQL. Check the list before calling the query; if empty, explicitly return empty or omit the filter.
- Very large lists may exceed database/driver bind parameter limits. Split into chunks or use temporary tables/arrays/table-valued parameters depending on the database.
- `NOT IN` combined with NULL in the list can evaluate to UNKNOWN and match no rows as expected. Strip NULLs from the list or use `NOT EXISTS` when appropriate.

## 10. LIKE and String Searching

`LIKE` supports wildcards:

- `%`: matches a string of any length, including empty.
- `_`: matches exactly one character.

Example searching for names starting with a prefix:

```jpql
select p
from Product p
where p.name like :pattern
```

Pass `pattern = "Sam%"` via the parameter. For substring search use `"%Sam%"`; for suffix search use `"%Sam"`.

You can use `ESCAPE` when searching for wildcard characters as literal text:

```jpql
where p.name like :pattern escape '\\'
```

If searching for user-entered strings containing `%` or `_`, escape the wildcards and escape character before adding application wildcards.

JPQL supports `LOWER` and `UPPER`:

```jpql
where lower(p.name) like lower(:pattern)
```

Applying a function to a column can prevent the database from using a regular index. For case-insensitive searches on large datasets, consider functional indexes, collations, or normalized columns depending on the database.

## 11. EXISTS, IS EMPTY, and MEMBER OF

### EXISTS

`EXISTS` checks whether a subquery returns at least one row:

```jpql
select c
from Customer c
where exists (
    select o.id
    from Order o
    where o.customer = c
)
```

This retrieves Customers that have at least one Order without returning every Customer/Order pair. EXISTS fits "whether any exists" questions well, though performance still depends on the query plan and indexes.

### IS EMPTY

Used with collection-valued associations:

```jpql
select c
from Customer c
where c.orders is empty
```

Opposite:

```jpql
where c.orders is not empty
```

### MEMBER OF

Checks whether an element belongs to a collection association:

```jpql
select c
from Customer c
where :order member of c.orders
```

The parameter must be an entity compatible with the collection elements. For complex associations, an explicit JOIN or EXISTS may be easier to optimize and read.

## 12. Arithmetic and String Expressions

JPQL supports arithmetic expressions on compatible data types:

```jpql
select p
from Product p
where p.price * p.stockQuantity > :threshold
```

Common operators:

- `+`: addition.
- `-`: subtraction.
- `*`: multiplication.
- `/`: division.

Expressions must have compatible types. Integer division may behave unexpectedly depending on types and database; for monetary precision, use `BigDecimal` and verify the mapping type.

For portable string concatenation, use `CONCAT`:

```jpql
select concat(p.code, '-', p.name)
from Product p
```

Do not rely on a database-specific concatenation operator in portable JPQL.

## 13. Common JPQL Functions

Useful standard functions:

| Function | Purpose | Example |
|---|---|---|
| `CONCAT(a, b)` | Concatenate strings | `concat(p.code, p.name)` |
| `LOWER(x)` | Convert to lowercase | `lower(p.name)` |
| `UPPER(x)` | Convert to uppercase | `upper(p.name)` |
| `TRIM(x)` | Strip leading/trailing whitespace | `trim(p.name)` |
| `LENGTH(x)` | String length | `length(p.name) > 3` |
| `LOCATE(a, b)` | Position of substring | `locate('Pro', p.name) > 0` |
| `SUBSTRING(x, start, len)` | Extract substring | `substring(p.code, 1, 3)` |
| `ABS(x)` | Absolute value | `abs(p.balance)` |
| `SQRT(x)` | Square root | `sqrt(p.area)` |
| `MOD(x, y)` | Remainder | `mod(p.quantity, 2) = 0` |
| `COALESCE(a, b)` | First non-NULL value | `coalesce(p.nickname, p.name)` |
| `NULLIF(a, b)` | Return NULL if both values are equal | `nullif(p.score, 0)` |

Commonly used date/time function:

```jpql
select p
from Product p
where p.createdAt < CURRENT_TIMESTAMP
```

Database-specific functions are not part of the portable JPQL set. Hibernate supports additional functions; you can invoke functions via `FUNCTION('function_name', ...)` in JPQL, though doing so introduces database/provider coupling and requires inspecting generated SQL.

## 14. CASE, COALESCE, and Conditional Expressions

JPQL supports `CASE` expressions:

```jpql
select
    p.id,
    case
        when p.stockQuantity = 0 then 'OUT_OF_STOCK'
        when p.stockQuantity < 5 then 'LOW_STOCK'
        else 'AVAILABLE'
    end
from Product p
```

It can be used in `WHERE`:

```jpql
where case
        when p.active = true then p.price
        else 0
      end >= :minPrice
```

However, a `CASE` expression in `WHERE` can be harder to optimize than direct predicates:

```jpql
where p.active = true
  and p.price >= :minPrice
```

Use `CASE` when you genuinely need to compute conditional values, such as generating labels in a projection or sorting by groups.

`COALESCE` handles NULL values:

```jpql
select coalesce(p.nickname, p.name)
from Person p
```

If `nickname` is null, the query returns `name`. `NULLIF` can prevent division by zero:

```jpql
select p.total / nullif(p.quantity, 0)
from ProductMetric p
```

When `quantity` is 0, the division evaluates to NULL rather than raising a division-by-zero error, subject to type and database support.

## 15. ORDER BY and Result Ordering

ORDER BY sorts results by one or more expressions:

```jpql
select p
from Product p
where p.active = true
order by p.createdAt desc, p.name asc, p.id asc
```

- `ASC`: ascending, the default.
- `DESC`: descending.
- Multiple criteria can be specified; subsequent criteria are used only when preceding ones are equal.
- Row order is not guaranteed without `ORDER BY`.

Append a unique tie-breaker such as ID at the end for stable ordering when paginating:

```jpql
order by p.createdAt desc, p.id desc
```

If sorting only by `createdAt` and multiple rows share the same timestamp, the relative order among them is nondeterministic. This can cause records to duplicate or be skipped across pages when data changes.

### 15.1. Sorting by Expressions

JPQL can sort by valid state-field path expressions or scalar expressions:

```jpql
select p
from Product p
order by lower(p.name) asc
```

With constructor projections or select items that have a result variable, you can use the alias in ORDER BY when valid in JPQL:

```jpql
select p.name as productName
from Product p
order by productName asc
```

Do not use SQL column names like `product_name` in JPQL unless that is actually the Java/entity mapped attribute name.

### 15.2. NULL in ORDER BY

NULL placement (first or last) can differ across databases. Portable JPQL does not provide a `NULLS FIRST/LAST` syntax uniformly supported across all providers and versions. Hibernate or specific databases may offer extensions.

If portability is needed, you can use `CASE`:

```jpql
order by
    case when p.createdAt is null then 1 else 0 end asc,
    p.createdAt desc,
    p.id desc
```

This example places NULL values at the end. Check the generated SQL and execution plan if sort expressions hinder index usage.

## 16. Parameter Binding: Named and Positional

Never concatenate input strings directly into JPQL. Use parameter binding to prevent injection, handle data types properly, and improve query plan reuse.

Named parameter:

```java
@Query("""
    select p
    from Product p
    where p.category = :category
      and p.price >= :minPrice
    order by p.price asc, p.id asc
    """)
List<Product> search(
    @Param("category") String category,
    @Param("minPrice") BigDecimal minPrice
);
```

Positional parameter:

```java
@Query("""
    select p
    from Product p
    where p.category = ?1
      and p.price >= ?2
    """)
List<Product> search(String category, BigDecimal minPrice);
```

Named parameters are usually easier to read and less prone to order mistakes when there are many conditions. Do not mix positional and named syntax in the same query without a specific reason.

Parameters are for **values**, not for substituting entity names, attribute names, keywords, or ORDER BY directions. For example, `order by :column` does not turn a parameter into an attribute name. For dynamic sorting, use `Sort`/`Pageable` or build dynamic queries from an allowlist of permitted attributes.

## 17. Combining ORDER BY with Pageable and Sort

Spring Data JPA enables pagination and sorting:

```java
Page<Product> findByActiveTrue(Pageable pageable);
```

Calling it:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<Product> page = productRepository.findByActiveTrue(pageable);
```

Property names in `Sort` are entity property paths, such as `createdAt`, not physical column names like `created_at`.

With `@Query`, Spring Data can apply dynamic `Sort` to a query if the sort property is valid. When a query has aliases/projections, ensure `Sort` references valid supported properties or aliases. Never pass arbitrary sort strings from users into JPQL unchecked.

Difference between `Page` and `Slice`:

- `Page<T>` typically needs the total record count, which can trigger a count query.
- `Slice<T>` only needs to know whether a next page exists, typically avoiding a count query.
- Both require a stable ORDER BY for reliable pagination.

When joining collections, a single parent can appear in multiple SQL rows. Combining a collection fetch join with pagination may trigger warnings or in-memory pagination depending on the provider. Inspect the query and consider a two-step approach: paginate IDs first, then load the required data.

## 18. DISTINCT, JOIN, and Duplicate Results

When joining a collection, each parent can appear multiple times in SQL results:

```jpql
select c
from Customer c
join c.orders o
where o.status = :status
```

If a `Customer` has multiple matching Orders, the result may contain duplicate Customers. Use `DISTINCT` if the goal is a unique list of Customers:

```jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
```

If you only need to check whether at least one Order exists, `EXISTS` often expresses the intent better:

```jpql
select c
from Customer c
where exists (
    select o.id
    from Order o
    where o.customer = c
      and o.status = :status
)
```

DISTINCT is not a universal fix for every JOIN. It can add sorting/hashing overhead and cannot correct the wrong join cardinality.

## 19. Indexes and WHERE/ORDER BY Performance

JPQL does not create indexes directly. Indexes must be defined in schema/migrations. Principles:

- Index columns frequently used in equality predicates and joins.
- Composite indexes should follow column ordering aligned with actual filters/sorting and selectivity.
- If a query filters by `category` and sorts by `created_at`, evaluate a composite index `(category, created_at)`.
- Functions on columns such as `lower(name)` may require functional indexes or an appropriate collation.
- `LIKE` with a leading wildcard such as `%term%` generally cannot use a standard B-tree index effectively.
- Multi-column ORDER BY requires inspecting the query plan to see whether an index can satisfy it.
- Indexes can speed up SELECTs at the cost of write overhead and storage space.

Example query:

```jpql
select p
from Product p
where p.category = :category
  and p.active = true
order by p.createdAt desc, p.id desc
```

A candidate index might be `(category, active, created_at, id)`, though optimal ordering and index type depend on the database, cardinality, and workload. Use `EXPLAIN`/`EXPLAIN ANALYZE` to verify rather than applying rules mechanically.

## 20. Common Errors

| Error | Cause | Solution |
|---|---|---|
| Using SQL table/column names in JPQL | JPQL uses entity names and Java attributes | Use entity/field names; if physical SQL is needed, use `nativeQuery` |
| Using `= null` | SQL/JPQL null logic does not work like normal equality | Use `IS NULL` or `IS NOT NULL` |
| OR widens results unexpectedly | Conditions not grouped with parentheses | Rewrite predicate with explicit parentheses |
| IN with empty list | SQL/provider may handle it unexpectedly | Handle empty collections in the service before querying |
| NOT IN containing NULL | Three-valued logic yields UNKNOWN | Exclude NULLs or consider `NOT EXISTS` |
| Sorting by database column name | Spring Data Sort typically uses property paths | Use entity attribute names |
| Pagination has duplicate rows | Collection JOIN multiplies results | Use DISTINCT, EXISTS, or paginate IDs first |
| Page query is slow | Both count query and data query are expensive | Use `Slice` if total count is unnecessary; optimize count separately |
| Unstable ORDER BY | No unique tie-breaker | Append ID or unique key at the end |
| Function disables index usage | Applying LOWER/UPPER/CAST on a column | Consider functional indexes or normalized data |

## 21. Checklist for Reviewing a JPQL Query

1. Confirm entity names and Java attributes match the mapping.
2. Decide whether SELECT returns an entity, scalar, `Object[]`, or DTO.
3. Build WHERE incrementally by condition, using parameter binding.
4. Handle NULLs with `IS NULL`/`IS NOT NULL` and check for empty collections.
5. Use parentheses for complex AND/OR expressions.
6. Add an explicit ORDER BY with a stable tie-breaker when paginating.
7. Check DISTINCT and cardinality when JOINs are present.
8. Inspect generated SQL and bind parameters in a safe environment.
9. Run `EXPLAIN`/`EXPLAIN ANALYZE` on a real database.
10. Write integration tests for edge cases: NULLs, duplicates, empty sets, boundary dates, and tied sort values.

## 22. Conclusion

SELECT specifies the returned data, WHERE defines the filtering predicate, ORDER BY determines the order, and expressions allow computations/comparisons right inside the query. JPQL uses the entity model instead of the physical schema, so accurate entity names, property paths, and parameter types are essential.

Prefer named parameters, handle NULLs properly, group AND/OR with parentheses, avoid empty IN lists, use DTO projections when full entities are unnecessary, and sort deterministically when paginating. Finally, always inspect the SQL and execution plan on an actual database; a short JPQL query does not guarantee cheap SQL.