# Scalar Queries and Mapping Aggregate Values

JPQL does not only return full Entities. A query can select a single property, a computed expression, or the result of aggregate functions such as COUNT, SUM, AVG, MIN, and MAX. These are called scalar results: each row returns a value or group of values instead of a complete Entity.

In Spring Data JPA, the Repository method's return type must match the result type produced by JPQL. If selecting one value, you can return the corresponding Java type such as Long, BigDecimal, or String. If selecting multiple values, map them using an interface projection or a DTO constructor expression rather than letting Object[] spread throughout the application.

## 1. What is a scalar query?

A standard Entity query selects an Entity:

~~~java
@Query("select p from Product p where p.id = :id")
Optional<Product> findProduct(@Param("id") Long id);
~~~

A scalar query selects a single property or expression:

~~~java
@Query("select p.name from Product p where p.id = :id")
Optional<String> findProductName(@Param("id") Long id);
~~~

~~~java
@Query("select p.price from Product p where p.id = :id")
Optional<BigDecimal> findProductPrice(@Param("id") Long id);
~~~

In the latter two examples, the result is not Product. JPQL only returns the value of the name or price property. Therefore, the return type must be String or BigDecimal respectively.

A scalar query can return multiple rows:

~~~java
@Query("select p.name from Product p where p.active = true order by p.name")
List<String> findActiveProductNames();
~~~

Each element in the List is a String value. If no rows match, the list is empty.

## 2. Return types must match the SELECT expression

When designing a Repository method, determine what Java type the SELECT expression returns.

| JPQL expression | Typical result type |
|---|---|
| select p.name | String |
| select p.id | Java type of the ID, e.g. Long |
| select p.price | BigDecimal if property is BigDecimal |
| select count(p) | Long |
| select avg(p.price) | Double |
| select sum(p.price) | BigDecimal if price is BigDecimal |
| select min(p.createdAt) | Type of the createdAt property |
| select max(p.createdAt) | Type of the createdAt property |

Example:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("select count(p) from Product p where p.active = true")
    long countActiveProducts();

    @Query("select max(p.price) from Product p")
    Optional<BigDecimal> findHighestPrice();

    @Query("select avg(p.price) from Product p")
    Optional<Double> findAveragePrice();
}
~~~

COUNT always returns Long according to JPQL rules. If using primitive long in the Repository method, the count always yields a numeric value, even when no rows match (result is 0).

AVG returns Double per JPQL rules, even when the input expression is a decimal numeric type. MIN and MAX return the type of the aggregated expression. SUM's result type depends on the input numeric type; common cases are detailed in the next section.

Do not choose the return type based solely on SQL column types. Base it on the Entity property's Java type and JPQL result type rules.

## 3. Basic aggregate functions

JPQL supports standard aggregate functions:

- COUNT: counts values or Entities.
- SUM: sums numeric values.
- AVG: calculates the arithmetic average.
- MIN: finds the minimum value.
- MAX: finds the maximum value.

Example with a Product Entity having price of type BigDecimal and active of type boolean:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("select count(p) from Product p")
    Long countAllProducts();

    @Query("select sum(p.price) from Product p")
    Optional<BigDecimal> sumAllPrices();

    @Query("select avg(p.price) from Product p")
    Optional<Double> averagePrice();

    @Query("select min(p.price) from Product p")
    Optional<BigDecimal> minimumPrice();

    @Query("select max(p.price) from Product p")
    Optional<BigDecimal> maximumPrice();
}
~~~

These signatures illustrate JPQL result types. For SUM, AVG, MIN, and MAX, if no matching data exists, the result can be null; in real applications, use a wrapper or Optional to express potential absence, or use COALESCE if business rules specify a fallback value.

### COUNT

COUNT counts matching results:

~~~java
@Query("""
    select count(p)
    from Product p
    where p.active = true
    """)
long countActiveProducts();
~~~

COUNT returns Long. If there are no active products, the result is 0 rather than null.

COUNT can use DISTINCT:

~~~java
@Query("""
    select count(distinct p.category.id)
    from Product p
    """)
Long countDistinctCategoriesWithProducts();
~~~

This query counts distinct categories appearing across Products. Categories without products are not counted because the query starts from Product.

### SUM

SUM adds numeric values:

~~~java
@Query("""
    select sum(p.price)
    from Product p
    where p.active = true
    """)
Optional<BigDecimal> sumActiveProductPrices();
~~~

For a BigDecimal property, SUM returns BigDecimal. If there are no values to sum, the result is null.

### AVG

AVG computes the average and returns Double:

~~~java
@Query("select avg(p.price) from Product p")
Optional<Double> averageProductPrice();
~~~

If monetary results require specific rounding rules, explicitly define conversion and scale in the business layer. Do not cast an average to BigDecimal while ignoring rounding rules.

### MIN and MAX

MIN/MAX return the type of the input expression:

~~~java
@Query("select min(p.createdAt) from Product p")
Optional<Instant> findFirstProductCreatedAt();

@Query("select max(p.price) from Product p")
Optional<BigDecimal> findHighestProductPrice();
~~~

They work with numbers, dates/times, and comparable types supported by JPA/provider/database.

## 4. Exact result types of SUM

Per JPQL rules, the return type of SUM depends on the numeric type of the expression:

| Input property type | SUM result type |
|---|---|
| Byte, Short, Integer, Long and corresponding integer types | Long |
| Float, Double | Double |
| BigInteger | BigInteger |
| BigDecimal | BigDecimal |

COUNT returns Long; AVG returns Double; MIN and MAX preserve the aggregated expression's type.

This matters when declaring Repository return types or DTO constructors. For example, if Product.quantity is Integer, SUM(p.quantity) returns Long, not Integer:

~~~java
@Query("select sum(p.quantity) from Product p")
Long sumAllQuantities();
~~~

Declaring the method to return Integer may cause type conversion errors or runtime failures depending on provider handling. Use the exact type dictated by the JPQL specification.

## 5. NULL and results when no data matches

Aggregate functions behave differently on an empty dataset:

| Function | When no matching values exist |
|---|---|
| COUNT | 0 |
| SUM | NULL |
| AVG | NULL |
| MIN | NULL |
| MAX | NULL |

Example:

~~~java
Long count = repository.countActiveProducts(); // 0 if no products match
Optional<BigDecimal> total = repository.sumActiveProductPrices(); // empty if SUM is NULL
~~~

COUNT returns 0 because the size of an empty set is 0. SUM, AVG, MIN, and MAX return NULL when there are no input values to compute.

Also distinguish two situations:
- No Entity matches WHERE.
- Entities match, but the aggregated property is NULL.

For SUM/AVG/MIN/MAX, both cases can produce NULL if no non-null values remain to aggregate. If you need to distinguish them, also query COUNT or inspect the Entities/data per business rules.

### Using COALESCE to replace NULL

If business logic specifies that a total amount with no data counts as 0, you can use COALESCE:

~~~java
@Query("""
    select coalesce(sum(p.price), :zero)
    from Product p
    where p.active = true
    """)
BigDecimal sumActivePricesOrZero(
        @Param("zero") BigDecimal zero
);
~~~

Call the method with BigDecimal.ZERO:

~~~java
BigDecimal total =
        repository.sumActivePricesOrZero(BigDecimal.ZERO);
~~~

COALESCE returns the first non-null value. The zero parameter must have a type compatible with SUM's result type. Alternatively, accept Optional<BigDecimal> and call orElse(BigDecimal.ZERO) in the service layer to keep a clear boundary between data access and business rules.

## 6. Scalar expressions and CASE

SELECT can return expressions rather than a direct property. JPQL supports arithmetic expressions, string functions, date/time functions, and CASE within specification/provider bounds.

Example calculating discounted price:

~~~java
@Query("""
    select p.price * (1 - p.discountRate)
    from Product p
    where p.id = :id
    """)
Optional<BigDecimal> findDiscountedPrice(@Param("id") Long id);
~~~

Example CASE classifying products by price:

~~~java
@Query("""
    select case
        when p.price >= :premiumThreshold then 'PREMIUM'
        when p.price >= :standardThreshold then 'STANDARD'
        else 'BUDGET'
    end
    from Product p
    """)
List<String> classifyProducts(
        @Param("premiumThreshold") BigDecimal premiumThreshold,
        @Param("standardThreshold") BigDecimal standardThreshold
);
~~~

The return type of a CASE expression must be consistent and compatible across all branches. If branches return different types, the provider may fail to determine a valid result type.

With arithmetic expressions, pay attention to operand types and division. If monetary precision is needed, control BigDecimal types, scale, and rounding in the business layer.

## 7. GROUP BY: aggregating per group

To compute aggregates separately for each category, use GROUP BY. For example, count products in each Category:

~~~java
@Query("""
    select c.name, count(p)
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<Object[]> countProductsByCategory();
~~~

Each result row has two elements:
- First element is the Category name (String).
- Second element is the Product count (Long).

LEFT JOIN ensures categories without products still appear; COUNT(p) for that group is 0. If using INNER JOIN, categories with no products are excluded from the results.

In JPQL, selected expressions not wrapped in an aggregate function must generally appear in GROUP BY. Here, c.name is selected, so c.id and c.name are grouped to form one group per category by identifier and name.

Avoid selecting an entire Entity alongside an arbitrary aggregate without proper grouping. Select the exact grouping properties and aggregate values to return.

## 8. HAVING: filtering after grouping

WHERE filters rows before grouping; HAVING filters groups after applying GROUP BY and aggregate functions.

Example fetching only categories with at least 5 products:

~~~java
@Query("""
    select c.name, count(p)
    from Category c
    left join c.products p
    group by c.id, c.name
    having count(p) >= :minimumCount
    order by c.name
    """)
List<Object[]> findCategoriesWithEnoughProducts(
        @Param("minimumCount") Long minimumCount
);
~~~

Distinguish:

~~~sql
WHERE p.active = true
GROUP BY c.id, c.name
HAVING COUNT(p) >= 5
~~~

- WHERE excludes inactive products before computing COUNT.
- GROUP BY groups the remaining rows by category.
- HAVING retains only groups meeting the product count threshold.

If a condition depends only on individual row properties, prefer WHERE. If a condition depends on COUNT, SUM, AVG, or group aggregate results, use HAVING.

## 9. Mapping multiple values with Object[]

JPQL can SELECT multiple expressions:

~~~java
@Query("""
    select p.category.name, count(p), max(p.price)
    from Product p
    group by p.category.id, p.category.name
    """)
List<Object[]> getCategoryStatistics();
~~~

Each Object[] contains elements in the exact SELECT order:
- index 0: category.name, String.
- index 1: count(p), Long.
- index 2: max(p.price), BigDecimal if price is BigDecimal.

This approach is simple but has drawbacks:
- Callers must remember index positions.
- Easy to cast to the wrong type.
- Adding or changing a SELECT expression can break many call sites.
- The meaning of each element is unclear when reading code.

For a small internal query, Object[] may be acceptable. For results returned through services/APIs or shared across callers, prefer projections or DTOs.

## 10. Interface projections for aggregate results

Spring Data JPA supports interface projections. Each getter corresponds to the alias of a SELECT expression.

Projection:

~~~java
public interface CategoryStatistics {
    String getCategoryName();
    Long getProductCount();
    BigDecimal getHighestPrice();
}
~~~

Repository:

~~~java
@Query("""
    select c.name as categoryName,
           count(p) as productCount,
           max(p.price) as highestPrice
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<CategoryStatistics> findCategoryStatistics();
~~~

Aliases must match the property names expected by the projection. For example, categoryName maps to getCategoryName(). Getter types must be compatible with the expression types: COUNT is Long, MAX(price) is the type of price.

Projections fit when:
- Only a subset of data is needed.
- Clear property names are preferred over Object[] indices.
- Results are read-only and do not need Entity management.

Do not use a projection as an Entity that can be modified and persisted. It is a read-only result structure.

## 11. DTO constructor expressions

JPQL supports constructor expressions to instantiate DTOs directly from SELECT. The DTO requires a constructor whose parameter order and types match the expressions.

DTO:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public record CategoryStatisticsDto(
        String categoryName,
        Long productCount,
        BigDecimal highestPrice
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.CategoryStatisticsDto(
        c.name,
        count(p),
        max(p.price)
    )
    from Category c
    left join c.products p
    group by c.id, c.name
    order by c.name
    """)
List<CategoryStatisticsDto> findCategoryStatisticsDto();
~~~

In a constructor expression:
- The new keyword must be followed by the fully qualified DTO class name.
- Argument order must match the constructor.
- count(p) is Long.
- max(p.price) has the type of the price property.

DTO constructor projections provide strong compile-time type checking and work cleanly when passing results across services or APIs. Java 17 records have a canonical constructor, making them convenient for read-only DTOs.

## 12. Aggregates with JOIN and avoiding double counting

When combining multiple one-to-many relationships, JOINs can multiply rows. For instance, a Customer has many Orders and each Order has many OrderItems. Joining both collections and counting Orders can count an Order with multiple items multiple times.

Example counting orders per customer:

~~~java
@Query("""
    select c.id, count(distinct o.id)
    from Customer c
    left join c.orders o
    left join o.items i
    group by c.id
    """)
List<Object[]> countCustomerOrders();
~~~

COUNT(DISTINCT o.id) counts each Order once even if the JOIN produces multiple rows for that Order.

Determine the exact level you want to count:
- COUNT(p): counts matching Entities/rows after joins.
- COUNT(DISTINCT p.id): counts unique Entities.
- COUNT(i.id): counts child items.
- SUM(i.quantity): sums quantities across child rows.

Do not add DISTINCT mechanically. DISTINCT carries overhead and should only be used when deduplication is required by query semantics. Whenever possible, write queries that join only the needed relationships.

## 13. Returning Page for aggregate queries

Grouped queries can return Page<Projection> or Page<DTO> if Spring Data can determine an appropriate count query. With complex GROUP BY/HAVING clauses, declare an explicit countQuery and ensure it counts the number of returned groups rather than source rows after JOIN.

Structural example:

~~~java
@Query(
    value = """
        select c.name as categoryName,
               count(p) as productCount
        from Category c
        left join c.products p
        group by c.id, c.name
        having count(p) >= :minimumCount
        """,
    countQuery = """
        select count(c.id)
        from Category c
        where (
            select count(p2)
            from Product p2
            where p2.category = c
        ) >= :minimumCount
        """
)
Page<CategoryStatistics> findCategoryStatisticsPage(
        @Param("minimumCount") Long minimumCount,
        Pageable pageable
);
~~~

The countQuery in the example counts Categories meeting the threshold corresponding to the number of groups in the main query. In real queries, if JOIN or HAVING conditions differ, adjust countQuery with the same logic. Test content, totalElements, and totalPages—not just the first few elements.

## 14. Using native queries for database-specific aggregations

If you need aggregate functions or syntax specific to a database not supported by standard JPQL, you can use native SQL. Result types then depend on the JDBC driver and database.

Example:

~~~java
@Query(value = """
    SELECT
        category_id AS categoryId,
        COUNT(*) AS productCount,
        SUM(price) AS totalPrice
    FROM products
    GROUP BY category_id
    """, nativeQuery = true)
List<Object[]> getNativeCategoryTotals();
~~~

With native queries:
- COUNT is typically returned by the driver as a numeric type such as Long or BigInteger depending on the database and driver.
- SUM/AVG JDBC types depend on the column type and database engine.
- Aliases and result mappings must be verified.
- Do not assume native aggregate types always match JPQL aggregate types.

For complex results, use @SqlResultSetMapping, appropriate DTO mapping, or convert inside a dedicated adapter/repository. Run integration tests on the production database to confirm actual data types.

## 15. Common mistakes

**Declaring the wrong return type**

For example, SUM(Integer) returns Long in JPQL, yet the method declares Integer. Check aggregate type rules before choosing the Repository signature.

**Using primitives for nullable aggregates**

SUM, AVG, MIN, and MAX can return NULL when there is no data. Use wrappers/Optional or COALESCE. COUNT is different because it returns 0.

**Assuming AVG returns BigDecimal**

JPQL AVG returns Double. If monetary rules apply, handle conversion and rounding explicitly.

**Using Object[] and casting wrong indices**

Element order must match SELECT. Prefer projections/DTOs for explicit names and types.

**Missing GROUP BY**

Every non-aggregated SELECT expression must align with GROUP BY under JPQL rules. Check both expressions and path properties.

**Putting aggregate conditions in WHERE**

WHERE filters rows before grouping; conditions such as COUNT(...) >= n belong in HAVING.

**Double counting from JOINs**

Joining multiple collections can duplicate rows. Determine the exact unit to count and use COUNT(DISTINCT ...) when necessary.

**Projection alias not matching getter**

Alias names must correspond to projection properties. Verify spelling and data types.

**Mismatched DTO constructor**

Constructor expressions require the fully qualified class name, exact parameter order, and matching result types.

**Not handling NULL from aggregates**

SUM/AVG/MIN/MAX can return NULL. Decide clearly whether business logic expects null, Optional, or a default value.

## 16. Testing scalar and aggregate queries

A repository test should verify result types and empty-data cases:

~~~java
@DataJpaTest
class ProductAggregateRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void countReturnsZeroWhenNoProductMatches() {
        assertEquals(0L, repository.countActiveProducts());
    }

    @Test
    void sumReturnsEmptyWhenThereAreNoMatchingPrices() {
        Optional<BigDecimal> total =
                repository.sumActiveProductPrices();

        assertTrue(total.isEmpty());
    }

    @Test
    void scalarQueryReturnsTheSelectedProperty() {
        Product saved = repository.save(
                new Product("Keyboard", new BigDecimal("125.50"), true)
        );

        Optional<BigDecimal> price =
                repository.findProductPrice(saved.getId());

        assertEquals(new BigDecimal("125.50"), price.orElseThrow());
    }
}
~~~

The example requires a Product Entity and Repository with matching constructors and methods. @DataJpaTest tests normally run inside a transaction and roll back afterward. If you need to verify constraints or ensure data is sent to the database, call flush as needed.

Add tests for:
- Single-row and multi-row scalar results.
- Aggregates over empty sets.
- Input properties containing NULL.
- Groups with data and empty groups with LEFT JOIN.
- COUNT(DISTINCT ...) when joining multiple associations.
- BigDecimal, Long, and Double return types.
- DTO constructor and interface projections.
- HAVING and pagination/countQuery.

## 17. Process for choosing result types

When writing a query returning aggregate values, follow these steps:

1. Determine whether the query should return an Entity, a single scalar, multiple scalars, or grouped results.
2. Determine the Java type of each SELECT expression.
3. For COUNT, use Long; for AVG, use Double; for SUM, apply the rule based on input type; for MIN/MAX, use the expression's type.
4. Define behavior when no data exists: 0, NULL, Optional.empty(), or a default value.
5. If selecting multiple columns, prefer interface projections or DTO constructor expressions.
6. If JOINs and aggregates are combined, check for duplicate counting and use COUNT(DISTINCT ...) when needed.
7. Place row conditions in WHERE and group conditions in HAVING.
8. Verify aliases, constructors, parameter types, and countQuery.
9. Run integration tests on the target database, especially for native aggregates.

## 18. Conclusion

JPQL can return single properties, scalar expressions, and aggregate results without loading full Entities. COUNT returns Long and equals 0 when no data matches; AVG returns Double; SUM's type depends on the input numeric type; MIN/MAX preserve the expression type, and these functions may return NULL on empty sets. For multiple values or GROUP BY, use interface projections or DTO constructor expressions for clear mapping instead of relying on Object[] and index positions. Verify NULL handling, result types, GROUP BY/HAVING, JOIN-induced duplicates, and countQuery via integration tests on the target database.