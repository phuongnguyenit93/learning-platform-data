# Returning Scalar Results, Interface Projections, and DTOs in Spring Data JPA Native SQL

When running native SQL through Spring Data JPA, a query can return a single value, a set of columns, or an application-specific data structure. Choosing the result type determines how Spring Data JPA and the JPA provider map SQL rows into Java objects.

Three common options are:

- **Scalar result**: returns a single value such as `Long`, `String`, `BigDecimal`, `LocalDate`, or another simple type.
- **Interface projection**: maps result columns into getter methods of an interface; column aliases must match projection properties.
- **DTO projection**: instantiates an object or record whose constructor receives values from the query result; complex native SQL may require explicit result set mapping.

Native SQL lets you use database-specific syntax and features, but the application must manage column names, aliases, JDBC types, constructor parameter order, pagination, and portability. This guide focuses on Spring Data JPA with Jakarta Persistence (`jakarta.persistence`) and Spring Boot 3+. Legacy projects may use `javax.persistence`; do not mix the two namespaces.

## 1. Native SQL and JPQL

JPQL queries entities and Java properties:

```jpql
select p.name
from Product p
where p.active = true
```

Native SQL queries physical tables and columns:

```sql
select p.name
from product p
where p.active = true
```

Declaring a native query in Spring Data JPA:

```java
@Query(
    value = "select p.name from product p where p.active = true",
    nativeQuery = true
)
List<String> findActiveNames();
```

Native queries are useful when:

- You need CTEs, window functions, JSON operators, full-text search, or database-specific syntax.
- Complex reporting queries need direct SQL tuning.
- You need to query views, stored procedures, or schema structures that are awkward in JPQL.
- You have measured and confirmed that provider-generated JPQL SQL is suboptimal.

In return, native queries are more tightly coupled to the schema and database. Renaming a table/column or changing databases may force query edits. Do not use native SQL merely because a query looks shorter; JPQL is usually easier to maintain when querying over the entity model.

## 2. Common Result Types

| Result Form | Java Example | When Suitable |
|---|---|---|
| Single scalar | `Long`, `String`, `BigDecimal`, `Optional<String>` | `COUNT`, `SUM`, single column, or single value |
| List of scalars | `List<Long>`, `List<String>` | Lists of IDs, names, codes, or single values |
| Raw multi-column | `Object[]` | Dynamic queries or quick inspection; less type-safe |
| Interface projection | `List<ProductView>` | Subset of columns with stable aliases and clear getters |
| DTO/class/record | `List<ProductSummary>` | Well-structured result for services, APIs, or reports |
| Entity | `Product`, `List<Product>` | When a managed entity is needed and all mapped columns are selected |

Not every result type can be inferred automatically from a method name. The return type, column count, aliases, and provider conversion support must align with the query.

## 3. Returning Scalar Results

A scalar is a single value such as an ID, name, total quantity, or total amount. If a query selects only one column, JPA typically returns each row as a single value rather than an `Object[]`.

### 3.1. Returning a Single Value

Example fetching a product name:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
            select p.name
            from product p
            where p.id = ?1
            """,
        nativeQuery = true
    )
    Optional<String> findNameById(Long id);
}
```

Example counting active products:

```java
@Query(
    value = "select count(*) from product where active = true",
    nativeQuery = true
)
Long countActiveProducts();
```

Spring Data JPA and the provider convert the JDBC result to the method return type when a compatible conversion exists. For aggregates like `COUNT`/`SUM`, the returned JDBC type can depend on the database and driver; when using `EntityManager` directly, receive the result as a `Number` and convert with `longValue()` or `intValue()` as appropriate.

### 3.2. Scalars With EntityManager

```java
Object result = entityManager
    .createNativeQuery("""
        select count(*)
        from product
        where active = true
        """)
    .getSingleResult();

long count = ((Number) result).longValue();
```

Using `Number` is safer than assuming every database returns `COUNT` as the exact same Java class. The concrete type may be `Long`, `BigInteger`, or another `Number` subclass depending on the provider and driver.

### 3.3. Lists of Scalars

```java
@Query(
    value = """
        select p.id
        from product p
        where p.category = ?1
        order by p.id
        """,
    nativeQuery = true
)
List<Long> findIdsByCategory(String category);
```

The single selected column should match the `List` element type. If the query selects multiple columns, do not declare `List<Long>` just because the first column is an ID; use a DTO/interface or receive structured raw results.

### 3.4. Single Results vs. Multiple Results

With `EntityManager`:

- `getSingleResult()` throws `NoResultException` if no rows are found.
- `getSingleResult()` throws `NonUniqueResultException` if more than one row is found.
- `getResultList()` returns a list, empty if no rows match.

With Spring Data repositories, use `Optional<T>` when a result may be absent and the method is designed to return at most one row. If the query can return multiple rows, use `List` or `Page`. Do not use `Optional` to mask a query that should be unique but currently returns multiple rows.

## 4. Nullable Scalars and Data Types

SQL columns can return `NULL`. When mapping to Java:

- Use wrapper types such as `Long`, `Integer`, `Boolean` instead of primitives if a column can be `NULL`.
- Use `Optional<T>` for methods that may return no rows; `Optional` does not automatically replace `NULL` values inside individual columns of a projection.
- Verify types for `DATE`/`TIMESTAMP`, `DECIMAL`, `UUID`, enums, JSON, and database-specific types.
- For `SUM`/`AVG`, check the actual returned type for your database and provider.

Nullable column example:

```java
@Query(
    value = "select p.discount_rate from product p where p.id = ?1",
    nativeQuery = true
)
BigDecimal findDiscountRate(Long id);
```

If `discount_rate` can be `NULL`, `BigDecimal` can accept `null`; design the service API accordingly. Do not use primitive `double` or `int` to receive a nullable column.

An aggregate such as `SUM` can return `NULL` when no rows match or all values are `NULL`. You can use `COALESCE` in SQL if a default value is desired:

```sql
select coalesce(sum(p.price), 0)
from product p
where p.active = true
```

The default value must have a type compatible with the expression and database.

## 5. Multiple Columns and Object[]

If a native query selects multiple columns without a specific mapping, JPA typically returns each row as an `Object[]`:

```java
List<Object[]> rows = entityManager
    .createNativeQuery("""
        select p.id, p.name, p.price
        from product p
        where p.active = true
        """)
    .getResultList();

for (Object[] row : rows) {
    Long id = ((Number) row[0]).longValue();
    String name = (String) row[1];
    BigDecimal price = (BigDecimal) row[2];
}
```

The element order in `Object[]` corresponds to the column order in `SELECT`. This approach has drawbacks:

- No compile-time type safety.
- Reordering columns in `SELECT` can silently make code read the wrong column.
- Prone to `ClassCastException` if the JDBC/provider type differs from assumptions.
- Code depends on indices `0`, `1`, `2`, making maintenance harder.

`Object[]` is suited for quick checks or highly dynamic queries. For stable results in an application, interface projections or DTOs are much clearer.

## 6. Interface Projections

Interface projections allow Spring Data JPA to map result columns into interface getters. Each getter corresponds to a projection property.

Example:

```java
public interface ProductView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
```

Native query:

```java
@Query(
    value = """
        select
            p.id as id,
            p.name as name,
            p.price as price
        from product p
        where p.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductView> findActiveProductViews(boolean active);
```

Spring Data JPA can use tuple/map-backed results to construct a projection proxy. Aliases in `SELECT` bridge SQL column names and Java getters:

- `id` → `getId()`
- `name` → `getName()`
- `price` → `getPrice()`

Aliases should be unique and match projection properties explicitly. Avoid selecting two columns with the same label like `id`; when joining multiple tables, use distinct aliases such as `productId` and `categoryId`.

### 6.1. camelCase and snake_case Aliases

Databases often use columns like `created_at`, whereas the Java property may be `createdAt`.

You can write an explicit alias:

```sql
select p.created_at as createdAt
from product p
```

Some databases normalize unquoted alias casing; some versions of Spring Data JPA or providers attempt camelCase-to-snake_case resolution for native tuples. This behavior depends on version and database. If an alias must preserve exact casing, you can use quoted aliases per database syntax, for example:

```sql
select p.created_at as "createdAt"
from product p
```

Quoted identifiers do not follow identical rules across all databases; test on your running engine. The safest approach is to use simple, unique aliases, verify projection metadata/values in integration tests, and avoid relying on unguaranteed naming fallbacks.

### 6.2. Nullable Getters

If a column can be `NULL`, the getter should return a wrapper type:

```java
public interface ProductView {
    Long getId();
    String getName();
    BigDecimal getDiscountRate();
}
```

Do not declare `long getId()` or `boolean isActive()` if the query can return `NULL` for the corresponding column. Primitives cannot represent `null`.

### 6.3. Nested Projections

Interface projections can support nested projections in many JPQL/entity-mapping scenarios, but a native SQL result is a flat set of columns. Do not assume an alias like `category.id` automatically constructs a nested `Category` object from a native query. With native queries, prefer:

- Selecting the needed columns with flat aliases.
- Using a DTO to group values into a structured object.
- Or running a separate query for the association if appropriate.

## 7. DTO Projections Using Classes or Records

A DTO is a plain object holding only the data to be returned. A DTO is not an entity and is not managed by the `PersistenceContext`.

Record example:

```java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
```

Native query in Spring Data JPA:

```java
@Query(
    value = """
        select p.id, p.name, p.price
        from product p
        where p.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductSummary> findActiveSummaries(boolean active);
```

For class-based projections from native queries, direct mapping works when `SELECT` column order and returned types match the DTO constructor. Example:

1. First column → parameter `Long id`.
2. Second column → parameter `String name`.
3. Third column → parameter `BigDecimal price`.

If column count, order, or types do not match, mapping can fail at runtime. Do not reorder DTO constructor parameters expecting the framework to infer property names from aliases in every case.

DTOs are appropriate when:

- You need a stable result structure for services or APIs.
- You want to avoid `Object[]` and manual casting.
- The query joins multiple tables and returns aggregated data.
- You do not need entity lifecycle, dirty checking, or lazy associations.
- You want exact control over the loaded fields.

## 8. Native DTO Mapping When Constructors Do Not Match Directly

When a native query has complex aliases, data types, or structure, use `@SqlResultSetMapping` to declare an explicit mapping.

DTO example:

```java
public class ProductRevenue {
    private final Long productId;
    private final String productName;
    private final BigDecimal revenue;

    public ProductRevenue(
            Long productId,
            String productName,
            BigDecimal revenue) {
        this.productId = productId;
        this.productName = productName;
        this.revenue = revenue;
    }

    public Long getProductId() { return productId; }
    public String getProductName() { return productName; }
    public BigDecimal getRevenue() { return revenue; }
}
```

Declare the mapping on an entity:

```java
@Entity
@Table(name = "product")
@SqlResultSetMapping(
    name = "ProductRevenueMapping",
    classes = @ConstructorResult(
        targetClass = ProductRevenue.class,
        columns = {
            @ColumnResult(name = "product_id", type = Long.class),
            @ColumnResult(name = "product_name", type = String.class),
            @ColumnResult(name = "revenue", type = BigDecimal.class)
        }
    )
)
public class Product {
    @Id
    private Long id;
}
```

Execute the native query via `EntityManager`:

```java
@SuppressWarnings("unchecked")
List<ProductRevenue> results = entityManager
    .createNativeQuery("""
        select
            p.id as product_id,
            p.name as product_name,
            sum(oi.quantity * oi.unit_price) as revenue
        from product p
        join order_item oi on oi.product_id = p.id
        group by p.id, p.name
        """, "ProductRevenueMapping")
    .getResultList();
```

`@ConstructorResult` matches `@ColumnResult` entries to the constructor in declaration order. Column names in the mapping must match the `SELECT` aliases; types must be compatible with the constructor. Even with `type` declared, test what types the driver/provider actually returns, especially for aggregates, enums, and database-specific types.

With Spring Data JPA versions whose `@NativeQuery` annotation supports `sqlResultSetMapping` (Spring Data JPA 3.4 and later), you can link a named mapping directly to a repository method. Example:

```java
@NativeQuery(
    value = """
        select
            p.id as product_id,
            p.name as product_name,
            sum(oi.quantity * oi.unit_price) as revenue
        from product p
        join order_item oi on oi.product_id = p.id
        group by p.id, p.name
        """,
    sqlResultSetMapping = "ProductRevenueMapping"
)
List<ProductRevenue> findRevenueByProduct();
```

If your current version does not yet support `@NativeQuery` or that mapping attribute, use `EntityManager.createNativeQuery(sql, mappingName)` as shown earlier, or upgrade after checking compatibility. Do not assume newer annotations exist in older Spring Data JPA versions.

## 9. Differences Between Entity Results and DTO Results

Native queries can return entities:

```java
@Query(
    value = "select p.* from product p where p.id = ?1",
    nativeQuery = true
)
Optional<Product> findEntityById(Long id);
```

When mapping an entity, the result must supply all columns required for the entity mapping, including any inheritance or association columns required by the mapping and provider. Missing columns can produce invalid results or runtime errors.

Entity results:

- Can become managed inside `PersistenceContext` when executed in an appropriate context.
- Have lifecycle callbacks, dirty checking, and association mappings.
- May trigger lazy/eager loading behavior.

DTO/interface projections:

- Represent query result data only.
- Are not managed as entities.
- Have no dirty checking or cascades.
- Are generally better suited for read models, reports, and API responses.

Do not return an entity simply because a query reads from a single table. If you only need three columns, a projection reduces fetched data and avoids coupling to persistence lifecycle behavior.

## 10. Native Interface Projections With Multi-Table JOINs

Example returning product names and category names:

```java
public interface ProductCategoryView {
    Long getProductId();
    String getProductName();
    String getCategoryName();
}
```

Query:

```java
@Query(
    value = """
        select
            p.id as productId,
            p.name as productName,
            c.name as categoryName
        from product p
        join category c on c.id = p.category_id
        where c.active = ?1
        order by p.name, p.id
        """,
    nativeQuery = true
)
List<ProductCategoryView> findProductsWithCategory(boolean categoryActive);
```

Aliases must be unique and match the getters. If both tables have an `id` column, do not return both under alias `id`; use `productId` and `categoryId`. With quoted aliases, pay attention to database casing rules.

If you want to return a nested DTO such as `ProductSummary(category = new CategorySummary(...))`, flat interface projections do not automatically build that structure from native SQL. You can use DTO constructor mapping, multi-step mapping in the service, or a separate query.

## 11. Native Queries With Page and countQuery

When a native query returns `Page`, make sure Spring Data can produce an accurate count query. For SQL with `JOIN`, `GROUP BY`, `DISTINCT`, CTEs, or complex subqueries, declare `countQuery` explicitly.

```java
@Query(
    value = """
        select
            p.id as id,
            p.name as name,
            p.price as price
        from product p
        where p.active = ?1
        order by p.created_at desc, p.id desc
        """,
    countQuery = """
        select count(*)
        from product p
        where p.active = ?1
        """,
    nativeQuery = true
)
Page<ProductView> findActivePage(
    boolean active,
    Pageable pageable
);
```

This example uses a fixed `ORDER BY` in SQL. When using `Pageable`, verify whether the query already includes `ORDER BY` and how your Spring Data JPA version handles dynamic `Sort` with native SQL. Native query rewriting capabilities depend on the parser and SQL complexity; do not assume every `Sort` property can be appended safely to SQL.

If dynamic sorting is needed, allow only columns in an application-defined whitelist and build an appropriate custom repository query. Never concatenate user-supplied column names or sort directions directly.

If the query returns grouped or aggregated rows, the count query must count the number of results after grouping, which may require a subquery:

```sql
select count(*)
from (
    select p.category_id
    from product p
    group by p.category_id
) grouped_categories
```

This is illustrative SQL; `FROM` subquery syntax and how Spring Data analyzes counts depend on the database and provider. Test `Page.getTotalElements()` and each page's content on the actual engine.

## 12. Parameter Binding and SQL Safety

Never concatenate input directly into native SQL:

```java
// Unsafe: avoid concatenating input strings into SQL.
String sql = "select * from product where name = '" + userInput + "'";
```

Use parameter binding:

```java
@Query(
    value = "select p.id from product p where p.name = ?1",
    nativeQuery = true
)
List<Long> findIdsByName(String name);
```

With native SQL, positional parameters are generally the most portable choice per Jakarta Persistence. Named parameters in native queries are supported by some providers and commonly seen in Spring Data JPA apps, but you should not assume identical support across all providers. If high portability is needed, use positional parameters and test against your target provider and database.

Parameters substitute values only. You cannot use parameters to replace table names, column names, keywords, or `ASC`/`DESC`. If you need to choose a sort column, use a whitelist:

```java
String orderBy = switch (sortKey) {
    case "name" -> "p.name";
    case "price" -> "p.price";
    case "createdAt" -> "p.created_at";
    default -> "p.id";
};
```

This `switch` illustrates whitelisting; when constructing dynamic SQL, only assemble application-controlled literals while keeping all data values bound as parameters.

## 13. Specialized Data Types and Conversions

Native queries receive types from the JDBC driver and provider. Key points to watch:

- **COUNT/SUM/AVG:** returned types can vary by database; verify `Number`/`BigDecimal` and conversions.
- **DECIMAL/NUMERIC:** use `BigDecimal` for money and precision; avoid unnecessary conversion through `double`.
- **DATE/TIMESTAMP:** mapping to `LocalDate`, `LocalDateTime`, `Instant`, or other types depends on JDBC/provider and timezone.
- **BOOLEAN:** some databases store booleans as numeric or char types; check conversions.
- **ENUM:** native SQL usually returns the raw column value and requires mapping/conversion compatible with how the enum is stored.
- **UUID:** JDBC representation can differ across databases.
- **JSON/ARRAY/vendor types:** typically require provider-specific mappings, converters, or reading via the corresponding JDBC type.
- **NULL:** use wrapper/reference types; handle nullable columns in DTOs.

If automatic conversion is unclear, use `@ColumnResult(type = ...)`, a converter, custom repository mapping, or explicit conversion in the service. Do not hardcode casts based on a single run against H2 if production uses PostgreSQL, MySQL, or Oracle.

## 14. Projections Are Not Entities and Do Not Sync Automatically

Interface projections are typically proxies reading data from query results. DTOs are plain data objects. Neither automatically becomes a managed entity simply by holding an entity's ID.

Example:

```java
ProductView view = repository.findViewById(id);
```

You cannot call `view.setName(...)` on a getter-only interface and expect JPA to automatically `UPDATE` the database. To modify data, load a managed entity or execute an explicit `UPDATE` query.

If a projection contains associations or nested properties, mapping may trigger additional queries in certain implementations. With native SQL, prefer selecting only the needed columns and returning flat projections or DTOs to avoid hidden queries.

## 15. Choosing Between Scalar, Interface, or DTO

| Criterion | Scalar | Interface Projection | DTO |
|---|---|---|---|
| Result complexity | Single value | Multiple named properties | Multiple structured properties |
| Declaration | Direct return type | Interface getters | Class/record constructor |
| Mapping | By column type | By alias/property | By constructor or result set mapping |
| Type safety | Good if scalar conversion is clear | Good on getter API; runtime aliases must match | Good when constructor/type mapping matches |
| Multi-table native SQL | Good for single aggregates | Good for flat results | Good for clear or complex structures |
| Nested objects | No | Do not assume with native SQL | Can be built via mapping/service |
| PersistenceContext | Not an entity | Not an entity | Not an entity |
| Best suited for | Counts, sums, IDs, names | Simple read-only lists | Stable APIs, reports, read models |

Selection rules:

1. A single value: return a scalar.
2. A few flat columns with clear aliases: interface projection.
3. Multi-column structured result needing constructor and type control: DTO/record.
4. Need entity lifecycle and associations: entity result.
5. Complex native mapping or incompatible constructor order: `@SqlResultSetMapping` or custom repository.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `ClassCastException` when reading `COUNT` | Wrong assumption about concrete `Number` type | Receive `Number` and convert; check driver |
| Interface projection returns `null` from getters | Alias mismatches property or database normalizes casing | Use clear, unique aliases; test on real database |
| DTO constructor mapping fails | Mismatched column order, count, or constructor types | Align `SELECT` with constructor; use `SqlResultSetMapping` |
| Duplicate aliases | Multi-table `JOIN` has columns with the same name | Give each column a unique alias |
| DTO native query passes on H2 but fails in production | Different JDBC types/dialects | Test on the same database engine or Testcontainers |
| `Page` `totalElements` is wrong | Count query is not equivalent to data query | Write an explicit `countQuery` and test edge cases |
| Dynamic sorting fails | Native SQL parser cannot rewrite complex query | Use fixed `ORDER BY` or custom repository with whitelist |
| Primitive getter receives `NULL` | Nullable column mapped to primitive in projection | Use wrapper/reference types |
| Query vulnerable to SQL injection | Concatenating input into SQL or unvalidated sort identifiers | Bind values; whitelist identifiers and order directions |
| Entity result missing columns | Native `SELECT` omits columns required by entity mapping | Select all columns or switch to projection/DTO |
| Named parameter is not portable | Providers handle native named bindings differently | Use positional parameters if portability is required |
| Nested projection mapping does not work | Native result is a flat set of columns | Use DTO mapping or multi-step assembly |

## 17. Testing Native Result Mappings

For each query, integration tests should verify:

- Column count and aliases match what the projection expects.
- Scalars return the expected type and handle `NULL`.
- Interface getters receive proper values, especially camelCase/snake_case aliases.
- DTO constructors receive parameters in the right order and types.
- `JOIN`s do not produce unintended duplicate rows.
- `Page` content and `countQuery` return accurate totals.
- Sorting, pagination, and `ORDER BY` are deterministic.
- The query runs on the actual production database engine and driver.
- Parameter binding handles special characters without corrupting SQL.
- The query does not accidentally return an entity when only a DTO is needed.

Do not rely solely on mocked repositories to test mappings. Mocks do not execute SQL, perform JDBC conversions, or validate aliases. Use `@DataJpaTest` with Testcontainers or a test database matching the production engine whenever mapping depends on database behavior.

## 18. Checklist Before Deploying Native Projections to Production

- [ ] Does the query truly need native SQL, or is JPQL enough?
- [ ] Is the result type a scalar, interface projection, DTO, or entity?
- [ ] Are `SELECT` column count and return types compatible with the method?
- [ ] Are aliases unique and matching getters/properties?
- [ ] Does the DTO constructor match order and types, or is `SqlResultSetMapping` configured?
- [ ] Do nullable columns use nullable Java types?
- [ ] Have actual return types for `COUNT`/`SUM`/`AVG` aggregates been verified?
- [ ] Are named/positional parameters appropriate for the provider and portability goals?
- [ ] Is input prevented from being concatenated into SQL identifiers or `ORDER BY`?
- [ ] Does `Page` have an accurate `countQuery`?
- [ ] Is dynamic sorting whitelisted and tested?
- [ ] Do integration tests run on the target database/driver?
- [ ] Does SQL logging avoid exposing sensitive data?

## 19. Conclusion

Scalars suit single values; interface projections suit flat column sets with clear aliases; DTOs and records suit structured read models with controlled constructors. When native SQL returns an entity, the query must satisfy the full entity mapping and the entity can participate in the `PersistenceContext`.

With native SQL, aliases and JDBC types largely determine mapping reliability. Use unique aliases, handle `NULL` values and aggregate types carefully, match DTO constructor order or declare `@SqlResultSetMapping`, and write an explicit `countQuery` for `Page` when needed. Test on a real database to catch differences in dialect, driver, and provider behavior before deployment.