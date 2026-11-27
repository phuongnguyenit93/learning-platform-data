# Building Multi-Criteria Search with Specification

## 1. Why Do We Need Specification?

Search screens in applications often have multiple optional filters: keyword, status, category, price range, date range, creator, or attributes of related entities. Users might enter only one condition, combine multiple conditions with AND, or create OR groups.

If you create a repository method for every combination of conditions, the number of methods grows rapidly. Manually concatenating JPQL/SQL strings is also prone to syntax, parameter, and security errors.

**Spring Data JPA Specification** lets you model query conditions as small, reusable, and composable components. Specification is built on the JPA Criteria API, so conditions are constructed with typed expressions instead of SQL string concatenation.

A Specification typically returns a `Predicate` for a `CriteriaQuery`:

- **AND**: all conditions must hold.
- **OR**: at least one condition in the group must hold.
- **NOT**: negates a condition.
- **Join**: filters by attributes of a related entity.
- **Subquery/EXISTS**: filters by the existence of related records.

This lesson uses a `Product` search example. Entity and attribute names can be adapted to your application's domain.

## 2. Preparing the Entity and Repository

Suppose the application has `Product` with name, SKU, price, status, creation timestamp, active flag, and category:

```java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProductStatus status;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
    }

    // Constructors, getters, and domain methods omitted.
}
```

The example uses Jakarta Persistence (Spring Boot 3 or later). With Spring Boot 2, the persistence package is typically `javax.persistence`. The entity must have an identifier, an appropriate no-arg constructor, and mappings matching the schema/migrations.

Status enum:

```java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

The repository needs to extend **JpaSpecificationExecutor**:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
```

`JpaSpecificationExecutor` provides commonly used methods:

- `findAll(Specification<T>)`: retrieves entities matching the condition.
- `findAll(Specification<T>, Pageable)`: searches with pagination and sorting.
- `findOne(Specification<T>)`: finds at most one result; if more than one result matches, an error can be thrown.
- `count(Specification<T>)`: counts records matching the condition.
- `exists(Specification<T>)`: checks whether any matching record exists.

Declaring a `Specification` does not execute a query by itself. The repository converts the `Specification` into a `CriteriaQuery` when the corresponding method is called.

## 3. Structure of Specification

A `Specification` describes a condition via its `toPredicate` method:

```java
public interface Specification<T> {
    Predicate toPredicate(
            Root<T> root,
            CriteriaQuery<?> query,
            CriteriaBuilder criteriaBuilder
    );
}
```

Three key parameters:

- **Root\<T\> root**: the root entity in the `FROM` clause; used to access entity attributes.
- **CriteriaQuery\<?\> query**: the query being built; can be used to set `distinct` or create subqueries.
- **CriteriaBuilder cb**: creates predicates such as `equal`, `like`, `greaterThan`, `between`, `and`, `or`, and `not`.

Example filtering by status:

```java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasStatus(ProductStatus status) {
        return (root, query, cb) -> status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }
}
```

`cb.conjunction()` creates an always-true predicate, equivalent to adding no condition. This is useful when a filter is omitted: that condition does not affect the overall result.

Do not return an always-false predicate when a filter is omitted, because the query would always return empty results. Nor should you turn an empty string into a `LIKE` wildcard if business logic expects skipping the filter.

## 4. Building Optional Filters

Turn each condition into a small `Specification`. The methods below can be placed in the `ProductSpecifications` class.

### 4.1 Keyword Search Across Multiple Columns

Search by name or SKU, case-insensitively:

```java
import java.util.Locale;
import org.springframework.util.StringUtils;

public static Specification<Product> nameContains(String keyword) {
    return textContains("name", keyword);
}

public static Specification<Product> skuContains(String keyword) {
    return textContains("sku", keyword);
}

private static Specification<Product> textContains(
        String property,
        String keyword) {

    if (!StringUtils.hasText(keyword)) {
        return (root, query, cb) -> cb.conjunction();
    }

    String value = escapeLike(keyword.trim().toLowerCase(Locale.ROOT));
    String pattern = "%" + value + "%";

    return (root, query, cb) ->
            cb.like(cb.lower(root.<String>get(property)), pattern, '\\');
}

public static Specification<Product> keywordContains(String keyword) {
    return nameContains(keyword).or(skuContains(keyword));
}

private static String escapeLike(String value) {
    return value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
}
```

Use `lower()` for case-insensitive comparison according to the collation/database. The `escapeLike` helper ensures user-entered `%` and `_` characters are treated as literal characters rather than accidentally becoming wildcards; the escape character itself is also escaped.

Performance note: patterns starting with `%` typically cannot utilize a standard B-tree index. For large datasets, consider full-text search, trigram indexes, a search engine, or a DBMS-appropriate search strategy.

### 4.2 Filtering by Related Category

`Product` has a `ManyToOne` relationship with `Category`. Use a join to filter by category ID:

```java
public static Specification<Product> belongsToCategory(Long categoryId) {
    return (root, query, cb) -> {
        if (categoryId == null) {
            return cb.conjunction();
        }

        Join<Product, Category> category =
                root.join("category", JoinType.INNER);

        return cb.equal(category.get("id"), categoryId);
    };
}
```

The attribute name passed to `root.join("category")` is the Java entity field/property name, not the SQL column name `category_id`. If the relationship can be null, the choice between `INNER` and `LEFT` join must accurately reflect business logic.

### 4.3 Filtering by Numeric Range

A price range can specify a min, a max, or both:

```java
public static Specification<Product> priceAtLeast(BigDecimal minPrice) {
    return (root, query, cb) -> minPrice == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"), minPrice);
}

public static Specification<Product> priceAtMost(BigDecimal maxPrice) {
    return (root, query, cb) -> maxPrice == null
            ? cb.conjunction()
            : cb.lessThanOrEqualTo(
                    root.<BigDecimal>get("price"), maxPrice);
}
```

Do not use `float`/`double` for currency. `BigDecimal` preserves precision and scale per database mappings. Validate that `minPrice` is non-negative and not greater than `maxPrice` before building the query.

### 4.4 Filtering by Time Range

Example finding `Product`s created from a timestamp and before another timestamp:

```java
public static Specification<Product> createdFrom(LocalDateTime from) {
    return (root, query, cb) -> from == null
            ? cb.conjunction()
            : cb.greaterThanOrEqualTo(
                    root.<LocalDateTime>get("createdAt"), from);
}

public static Specification<Product> createdBefore(LocalDateTime before) {
    return (root, query, cb) -> before == null
            ? cb.conjunction()
            : cb.lessThan(
                    root.<LocalDateTime>get("createdAt"), before);
}
```

Using a half-open interval `[from, before)` is often convenient when filtering by day/month because you avoid guessing millisecond/microsecond/nanosecond precision at the end of the day. If the API accepts dates instead of timestamps, explicitly convert timezones and start/end-of-day boundaries according to the business timezone.

### 4.5 Filtering by Boolean

Do not check a boolean using `if (active)`, because that cannot distinguish between the user selecting `false` and omitting the filter:

```java
public static Specification<Product> isActive(Boolean active) {
    return (root, query, cb) -> active == null
            ? cb.conjunction()
            : cb.equal(root.get("active"), active);
}
```

With a nullable `Boolean`, there are three states: `true`, `false`, and `null` (do not filter). Enum values must also be validated on input; never accept arbitrary strings and concatenate them into JPQL/SQL.

## 5. Combining Conditions with AND and OR

### 5.1 Combining with AND

Suppose the requirement is to find `Product`s matching all conditions: matching keyword, `ACTIVE` status, price between 100 and 500, and belonging to category 10.

```java
Specification<Product> specification = Specification.allOf(
        ProductSpecifications.keywordContains("phone"),
        ProductSpecifications.hasStatus(ProductStatus.ACTIVE),
        ProductSpecifications.priceAtLeast(new BigDecimal("100.00")),
        ProductSpecifications.priceAtMost(new BigDecimal("500.00")),
        ProductSpecifications.belongsToCategory(10L)
);

Page<Product> page = productRepository.findAll(
        specification,
        PageRequest.of(0, 20, Sort.by(Sort.Direction.DESC, "createdAt"))
);
```

`Specification.allOf(...)` combines specifications with `AND`. In Spring Data JPA 3.x, you can use `allOf(Iterable)` or varargs. If your project uses an older version without this API, chain them sequentially with `Specification.where(...)` and `and(...)` per your version.

### 5.2 Combining OR Within a Group

For example, finding `Product`s whose name or SKU contains a keyword. You can combine two separate `Specification`s:

```java
Specification<Product> nameOrSku =
        ProductSpecifications.nameContains("camera")
                .or(ProductSpecifications.skuContains("camera"));

Specification<Product> activeAndMatches =
        ProductSpecifications.hasStatus(ProductStatus.ACTIVE)
                .and(nameOrSku);
```

The expression above corresponds to:

`status = ACTIVE AND (name LIKE '%camera%' OR sku LIKE '%camera%')`

Logical parentheses are crucial. Writing `(status = ACTIVE AND name LIKE ...) OR sku LIKE ...` by mistake would allow products with matching SKUs that are not `ACTIVE` to slip into the results.

### 5.3 Combining Multiple Condition Groups

A complex search might have groups such as:

- Required: `ACTIVE` status.
- Keyword group: name or SKU matches.
- Price group: within min/max range.
- Time group: created within the requested range.

Place each group in its own `Specification` and combine them with `and`/`or` to accurately express business parentheses. Avoid creating one giant lambda containing every `if/else` branch when conditions can be reused or tested independently.

## 6. Creating Search Criteria and Dynamically Composing Specifications

### 6.1 DTO Holding Filters

Use a request/criteria object to group search conditions:

```java
public record ProductSearchCriteria(
        String keyword,
        Long categoryId,
        ProductStatus status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        Boolean active
) {
}
```

Bean Validation or constructor validation can be used to verify:

- `minPrice` and `maxPrice` are non-negative.
- `minPrice` is not greater than `maxPrice`.
- `createdFrom` is before `createdBefore`.
- `keyword` has a reasonable maximum length.
- `categoryId` is valid and accessible to the user if categories are also tenant-scoped.

Do not allow clients to pass arbitrary entity field names or free-form JPQL snippets to build filters. The DTO should expose only API-permitted fields.

### 6.2 Specification Factory

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecificationFactory {

    private ProductSpecificationFactory() {
    }

    public static Specification<Product> from(
            ProductSearchCriteria criteria) {

        List<Specification<Product>> filters = new ArrayList<>();

        filters.add(ProductSpecifications.keywordContains(
                criteria.keyword()));
        filters.add(ProductSpecifications.belongsToCategory(
                criteria.categoryId()));
        filters.add(ProductSpecifications.hasStatus(
                criteria.status()));
        filters.add(ProductSpecifications.priceAtLeast(
                criteria.minPrice()));
        filters.add(ProductSpecifications.priceAtMost(
                criteria.maxPrice()));
        filters.add(ProductSpecifications.createdFrom(
                criteria.createdFrom()));
        filters.add(ProductSpecifications.createdBefore(
                criteria.createdBefore()));
        filters.add(ProductSpecifications.isActive(
                criteria.active()));

        return Specification.allOf(filters);
    }
}
```

Each filter returns a conjunction when inapplicable, so the factory can add all conditions without writing numerous null checks. On Spring Data JPA versions supporting `Specification.unrestricted()`, you can use that for unapplied filters; conjunction remains an easy-to-understand Criteria API expression.

Service calling the repository:

```java
@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Product> search(
            ProductSearchCriteria criteria,
            Pageable pageable) {

        Specification<Product> specification =
                ProductSpecificationFactory.from(criteria);

        return repository.findAll(specification, pageable);
    }
}
```

In a real API, return DTOs rather than entities directly to control the returned data and avoid lazy loading outside transactions. You can convert a page via `page.map(ProductResponse::from)`.

## 7. Safe Pagination and Sorting

`Specification` only defines conditions; `Pageable` determines page, size, and sort. Do not allow clients to request unbounded page sizes or sort by arbitrary properties.

Example sort field whitelist:

```java
public enum ProductSortField {
    NAME,
    PRICE,
    CREATED_AT
}

public static Sort toSort(
        ProductSortField field,
        Sort.Direction direction) {

    String property = switch (field) {
        case NAME -> "name";
        case PRICE -> "price";
        case CREATED_AT -> "createdAt";
    };

    return Sort.by(direction, property).and(Sort.by("id"));
}
```

Add `id` as a secondary sort criterion for a stable ordering when multiple rows share the same sort value. The API should cap page size—for example, at most 100 records—and validate that direction accepts only `ASC`/`DESC`.

For large datasets:

- `Page<T>` usually requires an extra count query to calculate `totalElements`/`totalPages`.
- `Slice<T>` only needs to know whether a next page exists, reducing count overhead.
- Keyset/scroll pagination can be appropriate when offsets are deep and data changes continuously.
- Indexes must match the actual filter conditions and sort order.

Having a query with multiple filters does not mean the database automatically optimizes every combination. Inspect execution plans and actual row counts.

## 8. Joins, Distinct, and Relationship Queries

### 8.1 Joining ManyToOne/OneToOne Relationships

Use a join when filtering by attributes of a related entity, such as `category.name`:

```java
public static Specification<Product> categoryNameContains(String keyword) {
    if (!StringUtils.hasText(keyword)) {
        return (root, query, cb) -> cb.conjunction();
    }

    String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

    return (root, query, cb) -> {
        Join<Product, Category> category =
                root.join("category", JoinType.INNER);

        return cb.like(
                cb.lower(category.<String>get("name")),
                pattern
        );
    };
}
```

If the relationship can be absent and you want to preserve entities without that relationship in another query, the choice between `INNER` and `LEFT` join must accurately reflect business logic.

### 8.2 Joining Collections Can Duplicate Rows

When joining a collection such as `Product` having many `Tag`s, one `Product` can appear multiple times in the SQL result. You may need:

```java
return (root, query, cb) -> {
    Join<Product, Tag> tags = root.join("tags", JoinType.INNER);
    query.distinct(true);
    return cb.equal(tags.get("name"), tagName);
};
```

`distinct(true)` removes duplicate entity records in the query result. However, when combined with pagination, the count query can become complex or expensive. Check the generated count SQL and returned data on the actual DBMS.

If you only need to confirm that at least one matching tag exists, an `EXISTS` subquery generally avoids row multiplication better than a collection join.

### 8.3 Using EXISTS with a Subquery

Example finding `Product`s with at least one `Review` rated 4 or higher:

```java
public static Specification<Product> hasHighRating() {
    return (root, query, cb) -> {
        Subquery<Integer> subquery = query.subquery(Integer.class);
        Root<Review> review = subquery.from(Review.class);

        subquery.select(cb.literal(1))
                .where(
                    cb.equal(review.get("product").get("id"), root.get("id")),
                    cb.greaterThanOrEqualTo(review.get("rating"), 4)
                );

        return cb.exists(subquery);
    };
}
```

The `EXISTS` subquery checks only for the existence of at least one qualifying review. It avoids joining and returning multiple `Product` rows. Ensure `Review.product` is properly mapped and appropriate indexes exist on `product_id`/`rating`.

## 9. Projections and Fetching Only Needed Data

If a search screen only displays name, SKU, price, and status, you do not necessarily need to load the entire entity graph. Use projections or DTO queries where appropriate.

With `Specification`, `JpaSpecificationExecutor` primarily returns entities. You can use `findBy(specification, queryFunction)` in supported Spring Data JPA versions to select projections, slices, or other query forms; verify the API for your project's version. If projections are complex, consider a custom repository using `CriteriaQuery`/JPQL DTO constructors or dedicated queries.

Do not fetch-join multiple collections merely to avoid a couple of queries. Doing so can multiply rows, break pagination, and increase memory consumption. Choose DTO projections, `EntityGraph`, or batch fetching based on the data actually needed.

## 10. Performance and Correctness Considerations

### 10.1 Workload-Driven Indexing

`Specification` is flexible, but it does not create indexes automatically. Analyze common filter combinations:

- `status` + `createdAt`.
- `category_id` + `status`.
- Price range.
- `tenant_id` + business key in multi-tenant systems.
- Name/SKU search per the chosen search strategy.

Do not mechanically index every column. Indexes speed up reads but increase insert/update cost and storage footprint. Use execution plans and DBMS statistics to decide.

### 10.2 Avoiding N+1 and Inappropriate Fetch Joins

Filtering entities with `Specification` does not automatically load their associations. When the response needs `category`, choose an explicit fetch strategy with `EntityGraph`, DTO queries, or batch fetching. Avoid fetch-joining collections alongside `Page` unless you understand the impact on counts and pagination.

### 10.3 Nulls, Empty Strings, and Boundary Ranges

Define clearly how the API handles:

- `null`: ignore filter or match rows where column is `NULL`?
- Empty/whitespace string: ignore or match empty string?
- Price range: both bounds inclusive or exclusive?
- Date range: which timezone, inclusive or exclusive?
- Empty list: ignore filter or return empty results?
- `Boolean.FALSE`: a valid filter, not an ignored value.

Do not let semantics vary inconsistently across filters.

### 10.4 Never Accept Arbitrary Column Names

Criteria API avoids SQL string concatenation, yet not all inputs are automatically safe. Map only API-allowed filter/sort fields. Never use reflection or `root.get(clientField)` directly from client input without whitelisting.

### 10.5 Tenant Scope and Access Control

If `Product` belongs to a tenant, every search `Specification` must enforce the mandatory tenant predicate from the server context. Never let clients disable or override the tenant predicate. If the entity has a `tenantId` field, you can define a dedicated condition:

```java
public static Specification<Product> belongsToTenant(String tenantId) {
    return (root, query, cb) ->
            cb.equal(root.get("tenantId"), tenantId);
}
```

Then `AND` the tenant scope with user-selected filters:

```java
Specification<Product> tenantScope =
        ProductSpecifications.belongsToTenant(
                TenantContext.requireTenantId());

Specification<Product> userFilters =
        ProductSpecificationFactory.from(criteria);

Specification<Product> finalSpecification =
        tenantScope.and(userFilters);
```

The tenant predicate is an authorization constraint, not an optional UI filter. Test that every search, export, count, and pagination path preserves this condition.

## 11. Testing Specifications

Test against repositories and databases to confirm the Criteria API translates into correct SQL. `@DataJpaTest` fits JPA slice tests; if queries depend on DBMS-specific behavior, use Testcontainers with the target DBMS.

Example:

```java
@DataJpaTest
class ProductSpecificationTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void combinesStatusAndPriceFilters() {
        repository.save(product("Phone A", ProductStatus.ACTIVE,
                new BigDecimal("300.00")));
        repository.save(product("Phone B", ProductStatus.ACTIVE,
                new BigDecimal("700.00")));
        repository.save(product("Phone C", ProductStatus.DRAFT,
                new BigDecimal("250.00")));

        Specification<Product> specification = Specification.allOf(
                ProductSpecifications.hasStatus(ProductStatus.ACTIVE),
                ProductSpecifications.priceAtLeast(
                        new BigDecimal("200.00")),
                ProductSpecifications.priceAtMost(
                        new BigDecimal("500.00"))
        );

        List<Product> result = repository.findAll(specification);

        assertEquals(1, result.size());
        assertEquals("Phone A", result.get(0).getName());
    }
}
```

This is an illustrative test; you will need the `product(...)` factory helper, entity constructor/getters, `Category` if required by mappings, and JUnit/Spring Test imports. If `Product` has a unique SKU, the helper must generate distinct SKUs for each record.

Important test cases:

1. No filters: returns results per default policy without unexpectedly returning empty.
2. Single filter: only that condition is applied.
3. Multiple combined filters: `AND`/`OR` and logical parentheses are accurate.
4. Min/max boundaries: whether prices equal to thresholds are included.
5. `null`, empty strings, and `Boolean.FALSE`.
6. Keywords containing `%`, `_`, escape characters, and Vietnamese characters.
7. Collection joins: no duplicate records and accurate pagination/count.
8. Zero results or multiple results when using `findOne`.
9. Non-whitelisted sort fields are rejected.
10. Tenant scope is always applied and cannot be overridden by clients.

## 12. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Null filter causes query to return empty | Using a false predicate instead of an unrestricted condition | Use `cb.conjunction()` or `unrestricted` |
| OR lets unwanted records leak through | Missing logical parentheses grouping | Build group `Specification`s and combine with `AND`/`OR` explicitly |
| Property not found at runtime | Using SQL column name instead of Java property | Check entity fields and join paths |
| Duplicate results | Collection join produces multiple rows per root entity | Use `distinct` or `EXISTS` |
| Incorrect or slow page total | Complex count query due to join/distinct | Inspect count SQL; use `Slice`/`EXISTS` or a custom query |
| Slow search | `LIKE '%keyword%'` or missing suitable index | Use full-text/trigram or optimize indexes |
| `Boolean.FALSE` does not filter | Code only checks for `true` | Use nullable `Boolean` and check for `null` |
| Wrong date range results | Timezone mismatch or inclusive/exclusive mistake | Normalize timezone and use half-open intervals |
| Client can sort by unintended fields | Passing property directly from request | Whitelist fields and directions |
| Search query bypasses tenant | Tenant predicate treated as an optional filter | `AND` mandatory server-side tenant scope |

## 13. Workflow for Implementing a Search Screen

1. Identify business-allowed filters and null/range/OR semantics.
2. Create a request/criteria DTO with validation.
3. Write small single-condition `Specification`s.
4. Group `OR`/`AND` conditions according to business logic.
5. Combine the `Specification` list using `allOf` or a version-compatible API.
6. Call `JpaSpecificationExecutor` with `Pageable` and whitelisted sorting.
7. Return an appropriate DTO/projection without exposing unnecessary entity graphs.
8. Test single filters, combined filters, boundary data, pagination, joins, and access control.
9. Measure SQL/execution plans on production-like data and add workload-specific indexes.

## 14. Key Takeaways

- A `Specification` encapsulates a reusable predicate for the Criteria API.
- `JpaSpecificationExecutor` extends repositories to execute `Specification`s.
- `and`, `or`, `not`, and `allOf` combine conditions clearly.
- Use `cb.conjunction()` when an optional filter is not applied.
- Join on Java property names; collection joins can multiply rows and affect pagination.
- Restrict sort/filter fields via a whitelist; never accept arbitrary property paths from clients.
- Test `null`, `Boolean.FALSE`, boundary ranges, timezones, and `LIKE` special characters.
- Use `Pageable` with bounded page sizes, stable sorting, and suitable indexes.
- Authorization predicates like tenant scope must always be enforced server-side.

## 15. References

- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence — Criteria API](https://jakarta.ee/specifications/persistence/)
- [Spring Data Commons — Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)