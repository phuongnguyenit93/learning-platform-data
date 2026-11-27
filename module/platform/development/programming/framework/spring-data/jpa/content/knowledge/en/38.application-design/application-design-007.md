# Choosing Between Derived Queries, JPQL, Specifications, Querydsl, or Native SQL

Spring Data JPA provides several ways to build queries. Each approach solves a different kind of need: **derived queries** fit simple conditions, **JPQL** fits fixed queries needing clear control, **Specifications** fit dynamic filters, **Querydsl** offers a compile-time type-safe query API, and **native SQL** targets cases requiring database-specific features or optimizations.

There is no single best choice for every repository. Picking the wrong option can lead to overly long method names, hard-to-maintain JPQL, Specifications turning into unreadable predicate blocks, Querydsl adding build complexity, or native SQL coupling the application to a specific database.

This article compares the five approaches on the same data domain, explains how Spring Data JPA executes them, provides selection criteria based on query complexity and rate of change, and covers pagination, count queries, projections, parameter-binding security, and testing.

**Example prerequisites:** Java 17+, Spring Boot 3.x, Spring Data JPA, Jakarta Persistence, and Hibernate. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a matching schema. Querydsl requires additional Jakarta-compatible dependencies and annotation processor setup. The code snippets are components of a Spring Boot application, not standalone Java programs compiled solely with `javac`.

## 1. Starting from the Same Business Requirement

Suppose the application manages `Product` with the following properties:

- `id`: primary key.
- `name`: product name.
- `category`: category.
- `status`: status.
- `price`: price.
- `createdAt`: creation timestamp.

A search screen might need:

1. Find products by status.
2. Find names containing a keyword, case-insensitively.
3. Filter optionally by category.
4. Filter price within a range.
5. Sort by price or creation timestamp.
6. Paginate results.
7. Support adding new filters later as requirements evolve.

A repository may use one or more query approaches depending on the use case. The key is not forcing every kind of search into a single mechanism.

Simplified example entity:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String category;

    @Enumerated(EnumType.STRING)
    private ProductStatus status;

    private BigDecimal price;

    private Instant createdAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

The example uses simple fields to focus on query selection. In a real project, the entity needs full constructors, accessors, mappings, and lifecycle hooks matching application conventions.

## 2. Overview of the Five Query Approaches

| Approach | How it is written | Best suited when | Main trade-offs |
|---|---|---|---|
| Derived query | Encode conditions in the method name | Short, stable, readable conditions | Method names grow long with many conditions |
| JPQL | Write queries over entities/properties | Fixed queries needing joins, projections, or aggregates | Query strings are not fully checked at compile time |
| Specification | Compose predicates with the Criteria API | Optional filters, dynamic combinations | Can add abstraction and become hard to read if split too finely |
| Querydsl | Use a fluent, type-safe API | Complex dynamic queries needing type checks | Adds dependencies, generated Q-types, and build setup |
| Native SQL | Write database-specific SQL | Need CTEs, window functions, hints, or engine-specific SQL | Coupled to engine, schema, and result mapping |

You can start with derived queries for small needs. As logic grows, move to JPQL or Specification. If you have many complex dynamic queries and the team accepts Querydsl, it is a type-safe option. Native SQL should be used intentionally when the benefits of concrete SQL outweigh database coupling costs.

## 3. Derived Queries: Querying by Method Name

Spring Data parses repository method names to generate queries. A method name consists of a query prefix, properties, and keywords such as **And**, **Or**, **Containing**, **StartingWith**, **Between**, **In**, and **OrderBy**.

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByStatus(ProductStatus status);

    List<Product> findByCategoryAndStatus(
        String category,
        ProductStatus status
    );

    List<Product> findByNameContainingIgnoreCase(String keyword);

    List<Product> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
    );

    Page<Product> findByStatus(
        ProductStatus status,
        Pageable pageable
    );

    List<Product> findByStatusOrderByCreatedAtDesc(
        ProductStatus status
    );
}
~~~

Spring Data inspects the method name and resolves properties on the entity. For example:

~~~java
List<Product> products =
    repository.findByNameContainingIgnoreCase("keyboard");
~~~

has the semantics of finding names containing the keyword while ignoring case differences according to the JPA provider and database capabilities.

### Common Keywords

| Keyword | Meaning |
|---|---|
| `findBy` / `readBy` / `getBy` | Starts a read query |
| `And` / `Or` | Combines conditions |
| `Is` / `Equals` | Equality comparison |
| `Not` | Negation |
| `IsNull` / `IsNotNull` | Null checks |
| `GreaterThan` / `LessThan` | Greater-than/less-than comparisons |
| `Between` | Within a range |
| `Like` / `Containing` | LIKE matching / substring match |
| `StartingWith` / `EndingWith` | Starts with / ends with |
| `In` / `NotIn` | In / not in a collection of values |
| `IgnoreCase` | Case-insensitive string comparison |
| `OrderBy` | Sorts results |
| `Top` / `First` | Limits result count |

Keywords and method-name parsing rules are defined in the Spring Data documentation; when traversing nested properties, check name-resolution rules and use underscores if needed to disambiguate paths.

### When Do Derived Queries Become Hard to Maintain?

For example, the following method already expresses quite a few conditions:

~~~java
Page<Product> findByStatusAndCategoryAndNameContainingIgnoreCaseAndPriceBetweenOrderByCreatedAtDesc(
    ProductStatus status,
    String category,
    String name,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Pageable pageable
);
~~~

This method is still valid if every condition is always mandatory. However, if `category`, `name`, `minPrice`, and `maxPrice` are all optional, expressing every combination as method names quickly becomes impractical.

Do not create dozens of methods for every filter combination. As optional conditions increase, switching to Specification or Querydsl is usually much cleaner.

## 4. JPQL: Writing Queries Over Entities and Properties

JPQL uses entity names and Java property names rather than raw database table and column names. It fits queries with a fixed shape that need explicit control over joins, projections, aggregates, or predicates.

Example:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.status = :status
          and lower(p.name) like lower(concat('%', :keyword, '%'))
        order by p.createdAt desc
        """)
    List<Product> search(
        @Param("status") ProductStatus status,
        @Param("keyword") String keyword
    );
}
~~~

In the query:

- `Product` is the entity name.
- `p.name` and `p.status` are Java properties.
- `:status` and `:keyword` are named parameters.
- `concat` builds the pattern for LIKE; JPQL expression syntax is translated to SQL by the provider.

To prevent wildcards in user input from retaining special LIKE meaning, escape wildcard characters appropriately and add an `ESCAPE` clause. Do not assume user-entered strings are always literals when using LIKE.

### JPQL Joins and Projections

Suppose `Product` belongs to a `Category` entity instead of using a category string:

~~~java
@Query("""
    select p
    from Product p
    join p.category c
    where c.name = :categoryName
      and p.status = :status
    """)
List<Product> findByCategoryNameAndStatus(
    @Param("categoryName") String categoryName,
    @Param("status") ProductStatus status
);
~~~

If only a subset of data is needed, a DTO projection can be used:

~~~java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {
}
~~~

~~~java
@Query("""
    select new com.example.catalog.dto.ProductSummary(
        p.id,
        p.name,
        p.price
    )
    from Product p
    where p.status = :status
    order by p.name
    """)
List<ProductSummary> findSummariesByStatus(
    @Param("status") ProductStatus status
);
~~~

Constructor expressions must use the fully qualified DTO class name, and argument order and types must match the constructor. With Java records, the canonical constructor satisfies this invocation when component types and order match.

### @Query and Named Queries

You can declare JPQL directly on the repository via **@Query** or use named query metadata. `@Query` is convenient when the query belongs to a specific repository method. Named queries fit when you want queries placed near entity mappings or reused by name.

Avoid embedding lengthy business logic inside a hard-to-read JPQL string. When a query becomes dynamic or has many branches, Specification or Querydsl is easier to organize.

## 5. JPQL with Pagination and Count Queries

A method returning `Page` requires both the page content and the total element count to populate metadata. Spring Data can derive a count query for simple JPQL queries, but queries with joins, `distinct`, `group by`, or complex projections should declare an explicit `countQuery`.

~~~java
@Query(
    value = """
        select p
        from Product p
        where p.status = :status
        """,
    countQuery = """
        select count(p)
        from Product p
        where p.status = :status
        """
)
Page<Product> findPageByStatus(
    @Param("status") ProductStatus status,
    Pageable pageable
);
~~~

The count query must count the exact result set of the content query. If the content query joins a collection and can duplicate parent entities, the count may require **count(distinct p.id)**. If there is a `GROUP BY`, the count must reflect the number of returned groups.

You can use **Slice** if you only need to know whether a next page exists and do not need `totalElements` or `totalPages`. `Slice` avoids requiring a count query, though it still reads enough rows to determine `hasNext`.

Do not use `Page` simply because an API is paginated. Consider the cost of counting on large datasets.

## 6. Specification: Composing Dynamic Conditions with the Criteria API

**Specification<T>** represents a predicate on an entity. The repository must extend **JpaSpecificationExecutor<T>**:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Each Specification can produce a predicate or return null to omit the condition. Specifications can be combined using `and` or `or`.

Example independent filters:

~~~java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasStatus(
            ProductStatus status) {
        return (root, query, cb) ->
            status == null
                ? null
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Product> inCategory(
            String category) {
        return (root, query, cb) ->
            category == null || category.isBlank()
                ? null
                : cb.equal(root.get("category"), category);
    }

    public static Specification<Product> nameContains(
            String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return null;
            }

            String pattern =
                "%" + keyword.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                cb.lower(root.get("name")),
                pattern
            );
        };
    }

    public static Specification<Product> priceAtLeast(
            BigDecimal minimum) {
        return (root, query, cb) ->
            minimum == null
                ? null
                : cb.greaterThanOrEqualTo(
                    root.get("price"),
                    minimum
                );
    }

    public static Specification<Product> priceAtMost(
            BigDecimal maximum) {
        return (root, query, cb) ->
            maximum == null
                ? null
                : cb.lessThanOrEqualTo(
                    root.get("price"),
                    maximum
                );
    }
}
~~~

Composing in the service:

~~~java
@Transactional(readOnly = true)
public Page<Product> search(ProductSearchRequest request,
                            Pageable pageable) {

    Specification<Product> specification =
        Specification.where(
            ProductSpecifications.hasStatus(request.status())
        )
        .and(ProductSpecifications.inCategory(request.category()))
        .and(ProductSpecifications.nameContains(request.keyword()))
        .and(ProductSpecifications.priceAtLeast(request.minimumPrice()))
        .and(ProductSpecifications.priceAtMost(request.maximumPrice()));

    return repository.findAll(specification, pageable);
}
~~~

This example uses **Specification.where()** and **and()** to show composition. Depending on the Spring Data JPA version, the composition API may include additional factory methods; use the API provided by the version your project manages.

### Advantages of Specification

- Optional conditions are isolated into small predicates.
- Can be combined with AND/OR as needed.
- Conditions can be reused across multiple use cases.
- The repository does not need a method for every filter combination.
- Compatible with `JpaSpecificationExecutor` and `Pageable`.

### Limitations to Watch For

Specifications build on the Criteria API, so the code can be verbose and less intuitive than JPQL. If over-split into tiny classes for every condition, readers must jump through too many files to understand the complete query.

Additionally, a Specification can alter query shape via joins, distinct, or fetches. When shared with paginated queries, inspect the count query; a collection fetch join should not be added indiscriminately to a Specification used for `Page`.

## 7. EXISTS in Specifications When Filtering by Collections

If you only need to filter Products that have at least one Review meeting a minimum score, you do not need to join the collection and deduplicate rows.

Illustrative example with a `Review` entity having a `product` association:

~~~java
public static Specification<Product> hasReviewScoreAtLeast(
        Integer minimumScore) {
    return (root, query, cb) -> {
        if (minimumScore == null) {
            return null;
        }

        Subquery<Integer> subquery =
            query.subquery(Integer.class);

        Root<Review> review = subquery.from(Review.class);

        subquery.select(cb.literal(1))
            .where(
                cb.equal(review.get("product"), root),
                cb.greaterThanOrEqualTo(
                    review.get("score"),
                    minimumScore
                )
            );

        return cb.exists(subquery);
    };
}
~~~

The correlated subquery references the outer query's `root`. This directly expresses "has at least one matching review" while avoiding duplicate `Product` rows from a collection join.

If Reviews must be shown in the response, `EXISTS` only filters `Product` without loading Reviews. Choose a dedicated fetch plan or DTO projection for the returned data.

## 8. Querydsl: Type-Safe Dynamic Queries

Querydsl provides a fluent API to construct predicates and queries in Java. Q-type classes are generated from entities, such as **QProduct**. IDEs and compilers can validate property names and types better than JPQL strings.

The repository can extend:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
~~~

Simple predicate:

~~~java
QProduct product = QProduct.product;

BooleanExpression predicate =
    product.status.eq(ProductStatus.ACTIVE)
        .and(product.price.goe(new BigDecimal("100000")));

Iterable<Product> products =
    repository.findAll(predicate);
~~~

`QProduct` is a generated class derived from the `Product` entity; it is not written by hand. The build configuration must run the annotation processor before compiling sources that reference `QProduct`.

### Composing Optional Filters

~~~java
public Predicate buildPredicate(ProductSearchRequest request) {
    QProduct p = QProduct.product;

    BooleanBuilder builder = new BooleanBuilder();

    if (request.status() != null) {
        builder.and(p.status.eq(request.status()));
    }

    if (request.category() != null
            && !request.category().isBlank()) {
        builder.and(p.category.eq(request.category()));
    }

    if (request.keyword() != null
            && !request.keyword().isBlank()) {
        builder.and(p.name.containsIgnoreCase(request.keyword()));
    }

    if (request.minimumPrice() != null) {
        builder.and(p.price.goe(request.minimumPrice()));
    }

    if (request.maximumPrice() != null) {
        builder.and(p.price.loe(request.maximumPrice()));
    }

    return builder;
}
~~~

Calling it:

~~~java
Predicate predicate = buildPredicate(request);

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id"))
);

Page<Product> page =
    repository.findAll(predicate, pageable);
~~~

**BooleanBuilder** adds conditions conditionally from inputs. Querydsl can also be used directly via `JPAQueryFactory` for projections, joins, `group by`, subqueries, and more complex queries.

### Querydsl Requires Generated Q-Types

With Spring Boot 3/Jakarta, select Querydsl artifacts and annotation processors compatible with Jakarta Persistence. Maven/Gradle configuration depends on the Querydsl version and build plugins used by the project. Do not mix `javax.persistence` artifacts with entities using `jakarta.persistence`.

General steps:

1. Add Jakarta-compatible Querydsl JPA dependencies.
2. Add the corresponding annotation processor to the build.
3. Configure the generated sources directory.
4. Run compile to generate Q-types.
5. Include generated sources in the compile path per build configuration.
6. Verify CI can regenerate Q-types from clean source without relying on leftover generated files on a developer's machine.

Querydsl increases type safety but also adds build complexity and library dependencies. Before choosing it, verify version compatibility with Hibernate, Jakarta Persistence, Spring Data, and project dependency policies.

### QuerydslPredicateExecutor or JPAQueryFactory?

**QuerydslPredicateExecutor** is convenient for CRUD repositories with `Predicate`, `Sort`, and `Pageable`. However, this abstraction does not expose all query control capabilities of `JPAQueryFactory`.

Use **JPAQueryFactory** when you need:

- Complex DTO projections.
- Joins across multiple entities.
- `Group by`/`having`.
- Subqueries.
- Fine-grained control over fetch plans and query shape.
- Queries tuned specifically for a use case.

You can keep the repository interface for simple operations and place complex Querydsl queries inside a custom repository implementation.

## 9. Native SQL: When Database-Specific Capabilities Are Needed

Native SQL lets you write SQL directly against the physical schema. It is useful when you need:

- Common Table Expressions (CTEs).
- Window functions.
- Database hints or optimizer-specific features.
- JSON operators or array operators.
- Reporting/aggregation queries hard to express in JPQL.
- Engine-specific features.
- Query tuning after measuring execution plans and proving JPQL/provider output is insufficient.

Spring Data repository example:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query(
        value = """
            select p.*
            from products p
            where p.status = :status
              and p.price >= :minimumPrice
            order by p.created_at desc
            """,
        nativeQuery = true
    )
    List<Product> findNativeByStatusAndMinimumPrice(
        @Param("status") String status,
        @Param("minimumPrice") BigDecimal minimumPrice
    );
}
~~~

This SQL matches an illustrative schema. Table/column names, enum representations, and bind types must match the actual database. If `status` is stored as VARCHAR via `EnumType.STRING`, a String parameter fits; if mapped differently, adjust accordingly.

### Native Queries with DTO/Interface Projections

If full entities are unnecessary, an interface projection can be returned when column aliases match projection properties:

~~~java
public interface ProductNativeView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

~~~java
@Query(
    value = """
        select p.id as id,
               p.name as name,
               p.price as price
        from products p
        where p.status = :status
        """,
    nativeQuery = true
)
List<ProductNativeView> findNativeViews(
    @Param("status") String status
);
~~~

Aliases matter because the provider/framework must map result columns to properties. For DTO classes, constructor mapping from native queries may require **@SqlResultSetMapping** or projection mechanisms supported by your Spring Data JPA version. Do not assume every native result set automatically maps to any DTO constructor.

### Paginated Native Queries

When using a native query returning `Page`, declare a separate `countQuery` if Spring Data cannot infer it accurately:

~~~java
@Query(
    value = """
        select p.*
        from products p
        where p.status = :status
        """,
    countQuery = """
        select count(*)
        from products p
        where p.status = :status
        """,
    nativeQuery = true
)
Page<Product> findNativePageByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Complex native queries may need a `countQuery` matching the `DISTINCT`/`GROUP BY` logic of the main query. Dynamic sorting with native queries has limitations depending on Spring Data version and SQL parsing; never concatenate column names from user input. If dynamic sorting is needed, use an allow-list of valid columns and a controlled query builder or custom repository.

## 10. Security: Bind Values, Never Concatenate SQL Strings

With JPQL, Specification, Querydsl, and derived queries, the framework binds values using the respective parameter mechanisms. With native queries, you must still use named or positional parameters.

Do not do this:

~~~java
String sql =
    "select * from products where name = '" + userInput + "'";
~~~

Concatenating input creates SQL injection risks and escaping bugs.

Parameter binding is for **values**, not for binding table names, column names, `ORDER BY` keywords, or `ASC`/`DESC` directions. If an API lets callers choose a sort field, map the user's selection through an allow-list:

~~~java
Sort sort = switch (sortKey) {
    case "price" -> Sort.by("price");
    case "createdAt" -> Sort.by("createdAt");
    case "name" -> Sort.by("name");
    default -> Sort.by("id");
};
~~~

Never pass a raw sort string from the request into SQL. When a native query requires a dynamic identifier, select only from identifiers defined by the application.

## 11. Comparing Query Evolvability

| Criterion | Derived | JPQL | Specification | Querydsl | Native SQL |
|---|---|---|---|---|---|
| Simple conditions | Very suitable | Suitable | Often too heavy | Often too heavy | Usually unnecessary |
| Optional filters | Limited | Requires multiple branches | Very suitable | Very suitable | Requires controlled builder/dynamic SQL |
| Joins and projections | Limited by method structure | Good | Criteria supports them | Very good | Very good |
| Compile-time type safety | Properties parsed at repository startup; not as complete as Q-types | Lower than fluent APIs | Properties often strings or metamodel | High | Low |
| Cross-database portability | High | High within JPQL scope | High within JPA scope | High within Querydsl JPA scope | Lower |
| Engine-specific complex queries | Unsuitable | Limited | Limited | Limited by JPA | Suitable |
| Build/dependency complexity | Low | Low | Low | Higher due to code generation | Low at build, higher SQL maintenance |
| SQL debugging | Inspect generated SQL | Inspect generated SQL | Inspect generated SQL | Inspect generated SQL | SQL is written directly |

Type safety does not guarantee a query is business-correct or fast. Every approach still requires inspecting the SQL, data, indexes, and execution plans.

## 12. How to Choose by Complexity

You can walk through these questions:

**Are the conditions short and always fixed?**

- Yes: derived queries are usually enough.
- No: continue.

**Does the query have a fixed shape needing clear joins, projections, or aggregates?**

- Yes: JPQL is usually easy to review.
- No: continue.

**Are filters optional with combinations varying per request?**

- Yes: Specification is the natural choice in the Spring Data JPA ecosystem.
- If dynamic queries are complex with many joins/projections and the team favors a fluent API: consider Querydsl.

**Do you need SQL features JPQL/Criteria cannot express well, or engine-specific optimizations backed by measurements?**

- Yes: use native SQL for that specific use case.
- No: keep queries on JPA abstractions to minimize database coupling.

You do not need to convert an entire repository to Querydsl or native SQL just for one complex query. Multiple approaches can coexist in the same repository/service as long as boundaries and rationale are documented clearly.

## 13. Organizing Repositories and Custom Implementations

Repositories should focus on data access. Business logic for access control, state validation, and processing rules belongs in services/domain.

A possible layout:

~~~text
product/
  domain/
    Product.java
  repository/
    ProductRepository.java
    ProductRepositoryCustom.java
    ProductRepositoryImpl.java
  specification/
    ProductSpecifications.java
  query/
    ProductSearchRequest.java
  service/
    ProductService.java
  dto/
    ProductSummary.java
~~~

Main repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
    List<Product> findByStatus(ProductStatus status);
}
~~~

Custom repository interface:

~~~java
public interface ProductRepositoryCustom {
    Page<ProductSummary> searchAdvanced(
        ProductSearchRequest request,
        Pageable pageable
    );
}
~~~

The implementation can use Querydsl or `EntityManager`/Criteria depending on project decisions. Spring Data wires custom implementations into repository fragments using the naming/configuration conventions of the version in use. Keeping complex queries in custom implementations prevents the repository interface from turning into an unwieldy list of methods.

## 14. Do Not Choose Queries Based Solely on Line Count

A one-line derived query is easy to write, yet long method names become hard to change. A slightly longer JPQL query can sometimes be more readable because it shows joins and predicates explicitly. Small reusable Specification classes can be modular, yet can also make it harder to trace the final query.

Evaluate based on:

- Can others understand the business conditions from the query?
- Can correctness be verified with tests?
- When adding a new filter, do many methods have to change?
- Is the query database-dependent?
- Can SQL and execution plans be observed?
- Is the count query accurate?
- Are you loading more entities/associations than the response needs?
- Can predicates be reused without creating confusing coupling?

Pick the simplest approach that still expresses requirements clearly and offers an upgrade path if queries grow more complex.

## 15. Testing Each Query Approach

Repository tests should run against an appropriate database with representative data. For JPQL, Specification, and Querydsl queries, assert actual query results rather than merely verifying a method was invoked.

Example `@DataJpaTest` for derived queries and JPQL:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void derivedQueryFindsProductsIgnoringCase() {
        repository.save(product("Mechanical Keyboard", ProductStatus.ACTIVE));
        repository.save(product("Monitor", ProductStatus.ACTIVE));

        List<Product> result =
            repository.findByNameContainingIgnoreCase("keyboard");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getName())
            .isEqualTo("Mechanical Keyboard");
    }

    @Test
    void jpqlFiltersByStatus() {
        repository.save(product("Keyboard", ProductStatus.ACTIVE));
        repository.save(product("Mouse", ProductStatus.INACTIVE));

        List<Product> result =
            repository.findByStatus(ProductStatus.ACTIVE);

        assertThat(result).hasSize(1);
    }

    private Product product(String name, ProductStatus status) {
        // Factory helper creating a valid entity matching the project's mapping.
        return ProductTestFactory.create(name, status);
    }
}
~~~

The factory in the example is a project-defined test helper; replace it with your entity's actual constructor or builder. This test illustrates structure rather than a standalone compilable class without `ProductTestFactory` and domain types.

### Testing Specifications with Optional Filters

Create rows with varied categories, statuses, and prices. Verify:

- No filters returns the entire permitted set.
- When only status is provided, other filters are ignored.
- Two filters combine with AND.
- Null/blank values are handled properly.
- Page content and `totalElements` match.
- Sorting remains stable when multiple rows share the same sort value.

### Testing Querydsl

Test both individual filters and multiple filters combined. A clean build must generate Q-types successfully; do not rely solely on tests passing on a developer machine with stale generated sources.

### Testing Native SQL

Run against the exact target engine/version. H2 may lack support for CTEs, JSON operators, hints, or production database syntax. For native queries with `countQuery`, check totals and results across first, middle, and last pages.

Testcontainers can spin up the matching database engine in CI to verify queries, data types, collations, functions, and migrations close to production.

## 16. Measuring SQL and Execution Plans After Choosing a Query

Regardless of the approach, Spring Data JPA ultimately relies on the provider to generate SQL and the database to execute it.

When a query is slow:

1. Enable SQL logging in an appropriate environment or use a datasource/proxy to observe SQL.
2. Inspect bind parameters and data types.
3. Count all emitted SQL statements, not just the primary query.
4. Check for N+1 queries and lazy loading.
5. Read the execution plan on the target database.
6. Check indexes, cardinality, sorts, joins, and actual row counts.
7. Measure latency against production-like data volumes.

Do not log sensitive bind parameters in production if logs could expose emails, tokens, or personal data. Use test/staging environments or proper masking.

Even clean JPQL can produce inefficient SQL. A hand-written native query is not automatically faster either. Performance is determined by actual SQL, data distribution, indexes, the optimizer, and workload.

## 17. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Derived method too long | Too many conditions and optional filters | Switch to Specification or Querydsl |
| JPQL cannot find property | Using column name instead of entity property | Use entity name and Java property |
| JPQL returns duplicate entities | Collection JOIN multiplies rows | Consider DISTINCT or EXISTS |
| `Page` has wrong `totalElements` | Count query does not match content query logic | Declare `countQuery` and write tests |
| Specification hard to follow | Over-splitting predicates or mixing fetch with filters | Group by use case and separate fetch plans |
| Page query is slow | Expensive count query or collection fetch | Consider `Slice`, ID pagination, or DTOs |
| Querydsl fails to compile | Missing annotation processor or wrong Jakarta artifact | Align dependencies and generated sources |
| Q-types missing in CI | Generated sources exist only locally | Configure build to generate Q-types from clean source |
| Native query fails in production | Engine-dependent syntax, schema, or types | Test against exact database/version |
| Native pagination broken | Incorrect count query or unsupported sort | Write explicit `countQuery` and control sorting |
| SQL injection via sort | Concatenating identifiers from input | Use a sort-key allow-list |
| Query fast locally but slow in production | Differences in data volume, indexes, statistics, and execution plans | Benchmark with production-like data |

## 18. Query Selection Checklist

- [ ] Use derived queries for short, stable, readable conditions.
- [ ] Use JPQL for fixed queries needing explicit joins, projections, or aggregates.
- [ ] Use Specification when optional filters must combine dynamically.
- [ ] Use Querydsl for complex dynamic queries when the project accepts code generation/dependencies.
- [ ] Use native SQL when database-specific features or optimizations are clearly justified.
- [ ] Prefer DTO projections when responses need only a subset of data.
- [ ] Use parameter binding for all input values.
- [ ] Use allow-lists for dynamic identifiers and sort fields.
- [ ] Verify `countQuery` and cardinality when returning `Page`.
- [ ] Consider `Slice` when total page counts are unnecessary.
- [ ] Do not place collection fetch joins indiscriminately in paginated queries.
- [ ] Extract complex queries into custom repository implementations.
- [ ] Inspect actual SQL, round-trip counts, N+1 issues, and execution plans.
- [ ] Test native queries against the exact database engine.
- [ ] Configure Querydsl generated Q-types so clean CI builds reproduce them.

## 19. Conclusion

**Derived queries** are a great starting point for simple conditions. **JPQL** fits fixed queries that need explicit joins and projections. **Specification** handles optional filters cleanly using the Criteria API. **Querydsl** provides a type-safe fluent API for complex dynamic queries, at the cost of managing generated Q-types and dependencies. **Native SQL** targets database-specific features or optimizations, though it increases coupling and requires testing on the target engine.

Choose based on complexity, rate of change, portability, and SQL observability. Never choose merely for fewer lines of code or because a technique is trendy. A good query accurately expresses business rules, is testable, maintainable, and measured against realistic data.