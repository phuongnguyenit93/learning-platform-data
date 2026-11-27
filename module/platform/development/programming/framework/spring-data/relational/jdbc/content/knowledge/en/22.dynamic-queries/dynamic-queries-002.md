# Comparison Conditions, Ranges, IN, and NULL

Spring Data JDBC lets you generate queries from repository method names. Keywords such as **GreaterThan**, **LessThan**, **Between**, **In**, **NotIn**, **IsNull**, and **IsNotNull** express filter conditions without writing SQL for every method.

This mechanism is called **query derivation**: Spring Data parses the method name, resolves properties in the domain model, and generates the corresponding query. When using these operators, you must understand both Spring Data naming conventions and SQL semantics, especially around NULL and empty parameter collections.

This lesson uses a product catalog example to demonstrate value comparisons, range filtering, set filtering, NULL handling, and combining multiple predicates in Spring Data Relational/JDBC.

## 1. Query Derivation and Domain Properties

Spring Data Commons provides method-name parsing; Spring Data JDBC uses that mechanism to execute queries against a relational database.

Example:

```java
List<Product> findByPriceGreaterThan(BigDecimal price);
```

The method name reads as:

- `findBy`: begins a read query.
- `Price`: property to check.
- `GreaterThan`: greater-than operator.

The framework maps the Java property `price` to a database column based on entity metadata. Method names use **domain model property names**, not physical column names when the two differ.

Example domain:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
    @Id Long id,
    @Column("product_name") String name,
    @Column("unit_price") BigDecimal price,
    ProductStatus status,
    @Column("released_at") LocalDate releasedAt,
    @Column("discontinued_at") LocalDate discontinuedAt,
    boolean active
) {}
```

Enum:

```java
public enum ProductStatus {
    DRAFT,
    AVAILABLE,
    OUT_OF_STOCK,
    DISCONTINUED
}
```

With this mapping, the query method is written as `findByPriceGreaterThan`; generated SQL uses the `unit_price` column according to metadata.

Repository:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface ProductRepository
        extends ListCrudRepository<Product, Long> {
}
```

`ListCrudRepository` returns `List` for multi-result methods. If extending `CrudRepository`, multi-element read methods in the CRUD contract return `Iterable`.

## 2. Comparison Operators

Common keywords:

| Keyword | Meaning | SQL Condition |
| --- | --- | --- |
| `Is`, `Equals` | Equal | `= ?` |
| `Not`, `IsNot` | Not equal | `<> ?` |
| `GreaterThan`, `After` | Greater than | `> ?` |
| `GreaterThanEqual` | Greater than or equal | `>= ?` |
| `LessThan`, `Before` | Less than | `< ?` |
| `LessThanEqual` | Less than or equal | `<= ?` |
| `Between` | Within range | `BETWEEN ? AND ?` |
| `In` | In set of values | `IN (...)` |
| `NotIn` | Not in set of values | `NOT IN (...)` |
| `IsNull`, `Null` | NULL value | `IS NULL` |
| `IsNotNull`, `NotNull` | Not NULL | `IS NOT NULL` |

Aliases can express the same kind of predicate. Choose the form that is easiest to read and consistent across the codebase.

### 2.1. GreaterThan and LessThan

A repository can declare:

```java
List<Product> findByPriceGreaterThan(BigDecimal price);

List<Product> findByPriceGreaterThanEqual(BigDecimal price);

List<Product> findByPriceLessThan(BigDecimal price);

List<Product> findByPriceLessThanEqual(BigDecimal price);
```

Example:

```java
List<Product> expensive =
    products.findByPriceGreaterThan(new BigDecimal("500000"));

List<Product> affordable =
    products.findByPriceLessThanEqual(new BigDecimal("200000"));
```

Meaning:

- `GreaterThan` excludes the threshold value itself.
- `GreaterThanEqual` includes the threshold value.
- `LessThan` excludes the threshold value itself.
- `LessThanEqual` includes the threshold value.

For monetary data, use `BigDecimal` instead of `double` to avoid binary floating-point representation errors.

### 2.2. Date and Time Comparisons

Comparison operators also apply to date/time properties:

```java
List<Product> findByReleasedAtAfter(LocalDate date);

List<Product> findByReleasedAtBefore(LocalDate date);

List<Product> findByReleasedAtGreaterThanEqual(LocalDate date);
```

`After` and `Before` express chronological comparison. If business logic needs to include the boundary date, use an inclusive operator or `Between`.

For timestamps, choose matching Java and SQL types. `LocalDate` represents a calendar date; `Instant` represents a point on the timeline. Define timezone and conversion rules explicitly rather than relying only on column names.

### 2.3. Equals and Not

Example:

```java
List<Product> findByStatus(ProductStatus status);

List<Product> findByStatusNot(ProductStatus status);
```

These methods compare status values. With enums, ensure mapping/conversion matches how the database stores the enum, such as the string `AVAILABLE` or a numeric code.

`Not` compares for inequality with the supplied value. It is not synonymous with `IsNotNull`; checking NULL is a separate predicate.

## 3. Range Queries with Between

`Between` is used when a property must fall between two values:

```java
List<Product> findByPriceBetween(
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Call:

```java
List<Product> selected = products.findByPriceBetween(
    new BigDecimal("100000"),
    new BigDecimal("500000")
);
```

Corresponding SQL condition:

```sql
WHERE unit_price BETWEEN ? AND ?;
```

In SQL, `BETWEEN` is inclusive on both endpoints. The condition above is equivalent to:

```sql
WHERE unit_price >= :minPrice
  AND unit_price <= :maxPrice;
```

If business rules require a half-open interval (inclusive lower bound, exclusive upper bound), combine two operators:

```java
List<Product> findByPriceGreaterThanEqualAndPriceLessThan(
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

### 3.1. Validating Both Endpoints

`Between` does not automatically enforce that min is less than or equal to max according to business rules. Validate this in the service or during request validation:

```java
public List<Product> findByPriceRange(
    BigDecimal min,
    BigDecimal max
) {
    if (min == null || max == null) {
        throw new IllegalArgumentException(
            "Both price range bounds are required"
        );
    }

    if (min.compareTo(max) > 0) {
        throw new IllegalArgumentException(
            "Minimum price must not exceed maximum price"
        );
    }

    return products.findByPriceBetween(min, max);
}
```

For date ranges, specify clearly whether both endpoints are included. For timestamps, a `[start, end)` interval (inclusive start, exclusive end) usually avoids computing "end of day" values that depend on timestamp precision.

Example:

```java
List<Order> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
    Instant startInclusive,
    Instant endExclusive
);
```

## 4. Filtering by a Set of Values with In

`In` is used when a property's value must belong to a set of options:

```java
List<Product> findByStatusIn(Collection<ProductStatus> statuses);
```

Example:

```java
List<ProductStatus> visibleStatuses = List.of(
    ProductStatus.AVAILABLE,
    ProductStatus.OUT_OF_STOCK
);

List<Product> visible =
    products.findByStatusIn(visibleStatuses);
```

SQL meaning:

```sql
WHERE status IN (?, ?);
```

`In` works well when filters contain multiple statuses, IDs, SKUs, or categories.

It can be combined with other conditions:

```java
List<Product> findByActiveTrueAndStatusInAndPriceBetween(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Predicate meaning:

```sql
WHERE active = TRUE
  AND status IN (...)
  AND unit_price BETWEEN ? AND ?;
```

### 4.1. In by ID

Example:

```java
List<Product> findByIdIn(Collection<Long> ids);
```

This method is a derived query method on the `id` property. It differs from `findAllById(ids)`, which is a built-in CRUD method in the repository contract.

If you only need to look up aggregates by a set of IDs, `findAllById` is usually the direct API. Use `findByIdIn` when combining with additional conditions or expressing the query via query derivation.

### 4.2. Empty Collections

A SQL `IN ()` clause is invalid on many databases. Do not rely on the framework or driver to guess the business meaning of an empty collection.

Make an explicit decision at the application layer:

- If an empty set means no values are allowed, return an empty list without calling the repository.
- If an empty set means skip the filter, call a different method without that condition.
- If an empty set is invalid input, return a validation error.

Example:

```java
public List<Product> findByStatuses(
    Collection<ProductStatus> statuses
) {
    if (statuses == null) {
        throw new IllegalArgumentException(
            "Status list must not be null"
        );
    }

    if (statuses.isEmpty()) {
        return List.of();
    }

    return products.findByStatusIn(statuses);
}
```

Do not let the accidental semantics of an empty collection dictate API output.

## 5. Excluding a Set of Values with NotIn

`NotIn` finds rows whose value does not belong to the input set:

```java
List<Product> findByStatusNotIn(
    Collection<ProductStatus> excludedStatuses
);
```

Example:

```java
List<ProductStatus> excluded = List.of(
    ProductStatus.DRAFT,
    ProductStatus.DISCONTINUED
);

List<Product> listed =
    products.findByStatusNotIn(excluded);
```

SQL condition:

```sql
WHERE status NOT IN (?, ?);
```

### 5.1. NULL in a NotIn List

Pay special attention if the collection contains NULL. Under SQL three-valued logic, a `NOT IN` expression whose list contains NULL can prevent other rows from matching as well.

Example:

```sql
WHERE status NOT IN ('DRAFT', NULL)
```

For a row with status `AVAILABLE`:

- `AVAILABLE <> 'DRAFT'` evaluates to TRUE.
- `AVAILABLE <> NULL` evaluates to UNKNOWN.
- `TRUE AND UNKNOWN` evaluates to UNKNOWN.

WHERE selects only rows where the predicate evaluates to TRUE. Therefore, the `AVAILABLE` row will not appear in the result either.

Remove null elements from the collection unless intended, and express NULL conditions separately using `IS NULL` when needed.

## 6. Combining Conditions with And and Or

Multiple predicates can be chained in a method name:

```java
List<Product> findByStatusAndActiveTrue(
    ProductStatus status
);

List<Product> findByStatusInAndPriceLessThan(
    Collection<ProductStatus> statuses,
    BigDecimal maxPrice
);

List<Product> findByNameContainingIgnoreCaseOrStatus(
    String keyword,
    ProductStatus status
);
```

Example:

```java
List<Product> findByStatusAndPriceBetween(
    ProductStatus status,
    BigDecimal min,
    BigDecimal max
);
```

Meaning:

```sql
WHERE status = ?
  AND unit_price BETWEEN ? AND ?;
```

### 6.1. Be Careful with Multiple OR Groups

A method such as:

```java
findByStatusAndActiveTrueOrPriceLessThan(...)
```

can become hard to read if business rules require complex grouping. Method names do not provide arbitrary parentheses like a Java boolean expression.

When there are multiple AND/OR groups, use `@Query` or a custom repository to write the SQL condition explicitly. Test representative data combinations to make sure predicates are grouped as required by business rules.

## 7. Handling NULL in Query Derivation

In SQL, NULL represents an unknown or missing value. It is not equal to another value, not even another NULL.

Comparisons such as:

```sql
column = NULL
column <> NULL
column > NULL
```

do not return TRUE or FALSE; they evaluate to UNKNOWN. In a WHERE clause, only rows whose predicate is TRUE are selected.

To check for NULL, SQL uses `IS NULL` and `IS NOT NULL`. Spring Data query derivation provides corresponding keywords.

### 7.1. Finding Properties with NULL Values

```java
List<Product> findByDiscontinuedAtIsNull();
```

This method finds products without a discontinuation date:

```sql
WHERE discontinued_at IS NULL;
```

You can use the alias `findByDiscontinuedAtNull`, though `IsNull` is usually easier to read.

### 7.2. Finding Non-NULL Properties

```java
List<Product> findByReleasedAtIsNotNull();
```

SQL condition:

```sql
WHERE released_at IS NOT NULL;
```

You can use `findByReleasedAtNotNull`. Choose a consistent style.

### 7.3. Passing Null to an Equality Predicate

With query derivation, when the parameter to an equality predicate is null, Spring Data applies corresponding NULL semantics, typically turning the condition into `IS NULL`. For example:

```java
List<Product> findByDiscontinuedAt(LocalDate date);
```

When called with `date == null`, the condition may be derived into a query checking for NULL. However, the method name does not communicate intent as clearly as `findByDiscontinuedAtIsNull()`.

For negated predicates, null has corresponding rules for `IS NOT NULL`. For clearer code, prefer methods named `IsNull`/`IsNotNull` when the actual goal is checking NULL.

### 7.4. NULL Is Different from an Empty String

```sql
WHERE product_name IS NULL
```

differs from:

```sql
WHERE product_name = '';
```

NULL means no value; an empty string is a string value of length 0. A whitespace-only string is also not NULL. If business rules treat empty strings as missing data, check for them explicitly with an appropriate condition rather than substituting `IsNull`.

## 8. NULL in @Query and Hand-Written SQL

When using `@Query`, developers write SQL directly and must follow database semantics.

Example:

```java
@Query("""
    SELECT id, product_name, unit_price, status,
           released_at, discontinued_at, active
    FROM products
    WHERE discontinued_at = :date
    """)
List<Product> findByDiscontinuedDate(
    @Param("date") LocalDate date
);
```

If `date` is null, the SQL expression `discontinued_at = NULL` does not match rows with NULL values. To find NULLs, write `IS NULL` explicitly or design clear optional predicates.

A common pattern for optional filter parameters:

```sql
WHERE (:status IS NULL OR status = :status)
```

Meaning: if status is null, skip the filter; if it has a value, compare for equality. However, some databases/drivers require explicit types for null parameters, and OR expressions can affect execution plans. For critical queries, consider splitting into two queries or building controlled dynamic SQL.

### 8.1. A Null Parameter Does Not Automatically Mean Skip the Filter

For instance, `findByStatus(null)` should not be assumed to mean "return all statuses". Query derivation handles null parameters according to predicate semantics; if you want to skip a filter when no value is provided, coordinate in the service or define a separate optional query.

Distinguish between:

- Finding rows where a property is NULL.
- Not applying a filter condition on that property.

The two requirements produce different results.

## 9. Collections Containing Null Elements

Example:

```java
List<ProductStatus> statuses = Arrays.asList(
    ProductStatus.AVAILABLE,
    null
);
```

With `IN`, a NULL element is not a clear way to match rows whose status is NULL. With `NOT IN`, it can cause the predicate to evaluate to UNKNOWN for other rows.

If you want to find rows whose status is in a set **or** whose status is NULL, express that explicitly:

```sql
WHERE status IN (:statuses)
   OR status IS NULL
```

It is best to reject or strip null from collection parameters and use a separate predicate for NULL.

## 10. Combining Comparisons, Between, In, and NULL

A product filter might require:

- Currently active.
- Status in an allowed set.
- Price within a range.
- No discontinuation date yet.

Query derivation:

```java
List<Product>
findByActiveTrueAndStatusInAndPriceBetweenAndDiscontinuedAtIsNull(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
);
```

Service input validation:

```java
public List<Product> findAvailableProducts(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice
) {
    if (statuses == null || statuses.isEmpty()) {
        return List.of();
    }

    if (statuses.contains(null)) {
        throw new IllegalArgumentException(
            "Status list must not contain null"
        );
    }

    if (minPrice == null || maxPrice == null
            || minPrice.compareTo(maxPrice) > 0) {
        throw new IllegalArgumentException(
            "Invalid price range"
        );
    }

    return repository
        .findByActiveTrueAndStatusInAndPriceBetweenAndDiscontinuedAtIsNull(
            statuses,
            minPrice,
            maxPrice
        );
}
```

The method name is long, though the predicates remain independent. If more optional filters or multiple OR groups are added, consider `@Query` or a custom repository instead of creating an unmaintainably long method name.

## 11. @Query with IN and Named Parameters

When specific SQL is needed, you can declare:

```java
@Query("""
    SELECT id, product_name, unit_price, status,
           released_at, discontinued_at, active
    FROM products
    WHERE status IN (:statuses)
      AND unit_price BETWEEN :minPrice AND :maxPrice
      AND discontinued_at IS NULL
    ORDER BY unit_price ASC, id ASC
    """)
List<Product> searchAvailable(
    @Param("statuses") Collection<String> statuses,
    @Param("minPrice") BigDecimal minPrice,
    @Param("maxPrice") BigDecimal maxPrice
);
```

Named parameters make SQL readable and bind values safely. Spring JDBC supports expanding collection parameters for IN clauses in compatible queries.

Remember:

- Collections should be checked to be non-empty before calling.
- Avoid null elements unless intentional.
- Table/column names in SQL are physical schema names; hand-written queries do not automatically translate Java properties to column names.
- `@Query` does not automatically drop a condition just because a parameter is null.
- Database-specific SQL must be tested on the target dialect.

When many filters can be toggled per request, a custom repository can assemble predicates from controlled SQL fragments and bind all values via named parameters. Never concatenate user input directly into SQL.

## 12. Pagination and Sorting with Filter Conditions

Query derivation can combine conditions with `Pageable` or `Sort` when the method and query type support them:

```java
Page<Product> findByStatusInAndPriceBetween(
    Collection<ProductStatus> statuses,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Pageable pageable
);
```

Example call:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.asc("id")
    )
);

Page<Product> page = repository.findByStatusInAndPriceBetween(
    statuses,
    minPrice,
    maxPrice,
    pageable
);
```

`Sort` uses domain property names (`price`), not SQL column names (`unit_price`). Mapping metadata translates properties into the corresponding identifiers.

If the UI only needs to know whether a next page exists, `Slice<Product>` may fit better than `Page<Product>` because `Page` may require an extra query to count total rows.

With string-based `@Query` in Spring Data JDBC, do not assume the framework automatically rewrites SQL to add `Pageable`, `Sort`, or `Limit`. If a hand-written query needs dynamic limiting or sorting, use a mechanism supported by the current version or write the corresponding SQL explicitly.

## 13. Choosing Query Derivation or @Query?

| Need | Approach |
| --- | --- |
| Compare one property to a value | `findByPriceGreaterThan` |
| Filter by range | `findByPriceBetween` |
| Filter by set of values | `findByStatusIn` |
| Exclude set of values | `findByStatusNotIn` |
| Find NULL / non-NULL | `findByReleasedAtIsNull` / `findByReleasedAtIsNotNull` |
| Combine a few simple AND conditions | Query derivation |
| Multiple OR groups or optional filters | `@Query` or custom repository |
| SQL JOIN, aggregate/reporting queries | `@Query` or custom repository |
| Database-specific SQL | Explicit dialect-specific SQL |
| Dynamic filters with many options | Controlled custom repository/query builder |

Query derivation fits simple, stable, readable conditions. `@Query` fits when SQL control is needed or when logic makes method names too long.

## 14. Testing Query Conditions

Repository tests should cover both normal cases and boundary cases.

Example test for Between:

```java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void findsProductsWithinInclusivePriceRange() {
        Product low = products.save(product("A", "100000"));
        Product middle = products.save(product("B", "250000"));
        Product high = products.save(product("C", "600000"));

        List<Product> found = products.findByPriceBetween(
            new BigDecimal("100000"),
            new BigDecimal("250000")
        );

        assertThat(found)
            .extracting(Product::id)
            .containsExactlyInAnyOrder(low.id(), middle.id())
            .doesNotContain(high.id());
    }
}
```

Helpers like `product` are fixture factories matching the entity constructor and must be defined in actual tests.

Additional cases to test:

- Values equal to min and max are included.
- Values just below min and just above max are excluded.
- In with a single element and multiple elements.
- Empty In collections are handled by the service according to chosen rules.
- NotIn does not unintentionally receive collections containing NULL.
- IsNull and IsNotNull distinguish data accurately.
- Combined And/Or queries return the expected combinations.
- Sort/Pageable use property names and produce deterministic ordering.
- Custom SQL runs on the target database/dialect.

Do not write tests that depend on arbitrary ordering when a query has no ORDER BY. For unsorted results, use order-insensitive assertions.

## 15. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Property not found | Name in method does not match domain model | Use Java property names and check mapping |
| NULL comparison returns no results | Using `= NULL` or `<> NULL` | Use `IS NULL`/`IS NOT NULL` |
| Null parameter returns unexpected results | Confusing null with skipping the filter | Design separate optional conditions |
| Between misses boundary values | Misunderstanding range semantics | SQL BETWEEN includes both endpoints |
| In with empty collection fails | SQL `IN ()` unsupported by database | Short-circuit or use a query without the filter |
| NotIn returns fewer rows than expected | Collection contains NULL | Strip NULL and handle separately with a predicate |
| Query method name too long | Chaining many And/Or clauses | Use @Query or a custom repository |
| Sort does not work | Using SQL column name instead of property, or query lacks dynamic sort support | Use property names and check query type |
| @Query ignores Pageable | String-based query not rewritten as expected | Write limit/sort explicitly |
| H2 passes but production fails | Differences in SQL, data types, or dialect | Run integration tests on the real database |

## 16. Workflow for Designing Dynamic Filters

When building a search feature:

1. List each filter and identify the corresponding domain property.
2. Choose the operator: equals, not equals, greater than, less than, Between, In, or NULL.
3. Decide semantics when a filter is omitted: skip condition, match NULL, or reject request.
4. Validate min/max bounds and input collections.
5. Strip or explicitly handle null elements in In/NotIn sets.
6. Use query derivation for simple, stable conditions.
7. Use @Query/custom repositories when there are multiple logic groups or specialized SQL.
8. Bind values via named parameters; never concatenate input into SQL.
9. Add sorting/pagination and stable tie-breaking sort keys for large datasets.
10. Test boundaries, NULLs, empty sets, and the target database dialect.

> **GreaterThan/LessThan express comparison conditions; Between filters an inclusive range; In/NotIn filter by a set of values; IsNull/IsNotNull check for NULL.** Define the semantics of null parameters and empty collections explicitly, because SQL uses three-valued logic and does not automatically interpret null as "skip filter".

### References

- [Spring Data Commons — Query Method Details](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): keywords and query method name parsing rules.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query derivation and querying in Spring Data JDBC.
- [Spring Data Commons — Repository Query Keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html): list of supported keywords.
- [PostgreSQL — Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): comparison operators, BETWEEN, IN, and NULL handling.
- [PostgreSQL — Logical Operators](https://www.postgresql.org/docs/current/functions-logical.html): three-valued TRUE/FALSE/UNKNOWN logic in SQL.
