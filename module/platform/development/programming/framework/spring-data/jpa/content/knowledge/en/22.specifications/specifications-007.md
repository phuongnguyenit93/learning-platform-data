# Building Optional Filters Without Generating Redundant Conditions

A search screen often has many criteria: keyword, status, category, price range, creation date, active flag, or email. Users may enter only a few criteria in any given search. Always including every condition in the query tends to produce OR expressions checking null parameters, unnecessary predicates, and queries that are difficult to optimize.

Spring Data JPA Specification lets you build predicates dynamically using the Criteria API. Only when the user supplies a valid filter does the application add the corresponding condition to the query. This keeps the query aligned with actual search intent, distinguishes skipped filters from explicit NULL searches, and makes individual conditions easy to test.

This lesson uses a Product example to explain Specification, JpaSpecificationExecutor, building predicates from a filter DTO, handling blank strings, Boolean false, empty collections, numeric/date ranges, AND/OR, relationships, NULLs, pagination, sorting, count queries, security, and performance.

## 1. What Are Optional Filters?

Suppose a product search API exposes these criteria:

- Keyword in the product name.
- Category ID.
- Minimum and maximum price.
- One or more statuses.
- Whether the product is available.
- Creation date range.
- Contact email present, absent, or unfiltered.

A user might supply only keyword and minPrice; the remaining criteria do not participate in that search.

Example request:

~~~json
{
  "keyword": "keyboard",
  "minPrice": 500000,
  "maxPrice": null,
  "categoryId": null,
  "available": true
}
~~~

Meaning:

- Search for products whose name contains keyboard.
- Price of at least 500,000.
- Do not filter by maxPrice or categoryId.
- Only return products where available = true.

An optional filter must clearly define its input states:

| Input State | Recommended Meaning |
|---|---|
| Field omitted or null | Skip that filter |
| Empty or whitespace-only string | Normalize to no filter |
| Boolean false | Filter by value false |
| Number 0 | Filter by value 0 if allowed by the domain |
| Null collection | Do not apply the collection condition |
| Empty collection | Define explicitly: skip, return empty, or reject request |
| Dedicated NULL mode | Explicitly search for NULL or NOT NULL values |

Never use a single null value to represent multiple meanings that the API cannot tell apart.

## 2. Why Avoid Always Writing OR Conditions with Null Parameters?

A common pattern is:

~~~java
@Query("""
    select p
    from Product p
    where (:keyword is null or lower(p.name) like lower(:pattern))
      and (:categoryId is null or p.category.id = :categoryId)
      and (:available is null or p.available = :available)
    """)
List<Product> search(
    @Param("keyword") String keyword,
    @Param("pattern") String pattern,
    @Param("categoryId") Long categoryId,
    @Param("available") Boolean available
);
~~~

While logically valid in simple cases, this has drawbacks:

- The query always carries every conditional branch even when most filters are unused.
- OR expressions can hinder index selection in some databases and workloads.
- As the number of filters grows, the query becomes long and hard to read.
- Distinguishing a skipped filter from searching for NULL values becomes harder.
- Testing individual condition combinations is less straightforward.
- Some parameters require normalization or escaping before binding.

Not all OR expressions are slow; database optimizers handle many cases well. The issue is assuming a query packed with nullable parameter branches will always yield a good execution plan. Build predicates only for received filters and verify with execution plans on realistic data.

## 3. Specification in Spring Data JPA

Specification is Spring Data JPA's abstraction for expressing a query condition based on the Criteria API.

A Specification has the shape:

~~~java
public interface Specification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
    );
}
~~~

The three parameters have specific roles:

- Root: represents the root entity being queried and provides access to properties and associations.
- CriteriaQuery: describes the overall query, such as select, distinct, subqueries.
- CriteriaBuilder: builds predicates and expressions such as equal, like, greaterThan, and, or, isNull.

A Specification does not execute SQL itself. It supplies the condition for the repository to construct the query when invoked.

Specifications can be combined using AND, OR, and NOT, letting you organize conditions by business logic and reuse them across use cases.

## 4. Declaring a Specification-Capable Repository

The repository must extend JpaSpecificationExecutor:

~~~java
package example.repository;

import example.domain.Product;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

JpaSpecificationExecutor provides methods such as:

- findAll(specification)
- findAll(specification, sort)
- findAll(specification, pageable)
- findOne(specification)
- count(specification)
- exists(specification)

Thus, the exact same filter can list items, paginate, count, or check existence.

## 5. Designing the Filter DTO

Create an object containing the search criteria. Use wrapper types like Boolean instead of primitive boolean whenever omitting a filter must be distinguished from false.

~~~java
package example.dto;

import example.domain.ProductStatus;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Set;

public record ProductFilter(
    String keyword,
    Long categoryId,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Set<ProductStatus> statuses,
    Boolean available,
    LocalDateTime createdFrom,
    LocalDateTime createdTo,
    NullMode emailNullMode
) {
    public enum NullMode {
        ANY,
        IS_NULL,
        IS_NOT_NULL
    }
}
~~~

Field meanings:

- keyword null or blank: do not filter by name.
- categoryId null: do not filter by category.
- minPrice/maxPrice null: omit the corresponding bound.
- statuses null or empty: in this example, do not filter by status.
- available null: do not filter; both true and false are valid filter values.
- createdFrom/createdTo null: omit the corresponding time bound.
- emailNullMode ANY: do not filter email; IS_NULL or IS_NOT_NULL is an explicit request.

Document this contract clearly in the API. If products can have a price of 0, never check something like `minPrice > 0` to decide whether the filter was supplied. Only check for null.

## 6. Building All Predicates in One Specification

A clean pattern is building a list of predicates and appending conditions only when the filter carries a value:

~~~java
package example.repository.specification;

import example.domain.Product;
import example.dto.ProductFilter;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.jpa.domain.Specification;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> from(ProductFilter filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (filter.keyword() != null
                    && !filter.keyword().isBlank()) {
                String keyword = escapeLike(filter.keyword().strip())
                    .toLowerCase(Locale.ROOT);

                predicates.add(
                    cb.like(
                        cb.lower(root.<String>get("name")),
                        "%" + keyword + "%",
                        '!'
                    )
                );
            }

            if (filter.categoryId() != null) {
                predicates.add(
                    cb.equal(
                        root.get("category").get("id"),
                        filter.categoryId()
                    )
                );
            }

            if (filter.minPrice() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.<BigDecimal>get("price"),
                        filter.minPrice()
                    )
                );
            }

            if (filter.maxPrice() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(
                        root.<BigDecimal>get("price"),
                        filter.maxPrice()
                    )
                );
            }

            if (filter.statuses() != null
                    && !filter.statuses().isEmpty()) {
                predicates.add(
                    root.get("status").in(filter.statuses())
                );
            }

            if (filter.available() != null) {
                predicates.add(
                    cb.equal(
                        root.get("available"),
                        filter.available()
                    )
                );
            }

            if (filter.createdFrom() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(
                        root.<LocalDateTime>get("createdAt"),
                        filter.createdFrom()
                    )
                );
            }

            if (filter.createdTo() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(
                        root.<LocalDateTime>get("createdAt"),
                        filter.createdTo()
                    )
                );
            }

            if (filter.emailNullMode()
                    == ProductFilter.NullMode.IS_NULL) {
                predicates.add(cb.isNull(root.get("contactEmail")));
            } else if (filter.emailNullMode()
                    == ProductFilter.NullMode.IS_NOT_NULL) {
                predicates.add(cb.isNotNull(root.get("contactEmail")));
            }

            if (predicates.isEmpty()) {
                return null;
            }

            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }

    private static String escapeLike(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }
}
~~~

This example requires a Product entity with the matching properties: name, category, price, status, available, createdAt, and contactEmail. Imports, enums, and domain mappings must match the actual project when applied.

Key points:

- A Predicate is added only when its corresponding filter has a value.
- Boolean false is still added because the check tests for null, not `if (available)`.
- Price range can include only min, only max, or both.
- An empty status list is treated as "do not filter by status" under this example's contract.
- IS NULL and IS NOT NULL are represented via an explicit mode.
- When there are no predicates, the Specification returns null so Spring Data omits the WHERE clause.
- When predicates exist, they are combined with AND.

Returning null from toPredicate means "apply no predicate" in Spring Data JPA's Specification mechanism. Avoid adding `cb.conjunction()` mechanically if the goal is to avoid emitting unnecessary WHERE conditions.

## 7. Distinguishing null, false, and 0

A frequent mistake is checking values using truthiness or improper non-null checks.

Wrong example:

~~~java
if (filter.available()) {
    predicates.add(cb.isTrue(root.get("available")));
}
~~~

This skips the `available = false` case because false never enters the `if` branch.

Correct approach:

~~~java
if (filter.available() != null) {
    predicates.add(
        cb.equal(root.get("available"), filter.available())
    );
}
~~~

Likewise for numbers:

~~~java
if (filter.minPrice() != null) {
    predicates.add(
        cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            filter.minPrice()
        )
    );
}
~~~

If minPrice is 0 and the domain permits it, the condition is still included.

General rule: use wrapper types and check for null when null means skipping the filter; never check whether a value differs from false or 0.

## 8. Empty Strings and Whitespace

A null, empty, or whitespace-only keyword should generally normalize to no filter.

Example:

~~~java
if (filter.keyword() != null
        && !filter.keyword().isBlank()) {
    String keyword = filter.keyword().strip();
    // Add search predicate.
}
~~~

isBlank() checks whether a string is empty or contains only whitespace; strip() trims leading and trailing whitespace according to Java's Unicode rules.

If business logic requires searching for an actual empty string in the database, make that an explicit filter mode. Do not let blank represent both "skip filter" and "find empty data".

You can normalize inputs at the service layer before creating the Specification to keep query logic cleaner. Keep the same normalization policy across saving and searching.

## 9. LIKE and Escaping Wildcards

When using LIKE, `%` and `_` act as wildcards:

- `%` matches zero or more characters.
- `_` matches exactly one character.

If the user enters these characters intending a literal match, escape them. In the example, `!` is chosen as the escape character:

~~~java
private static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

CriteriaBuilder predicate:

~~~java
cb.like(
    cb.lower(root.<String>get("name")),
    "%" + escapedKeyword.toLowerCase(Locale.ROOT) + "%",
    '!'
)
~~~

Escaping order matters: escape the escape character first, then escape `%` and `_`. Doing it in reverse can double-escape newly inserted `!` characters.

Parameter binding and wildcard escaping solve two distinct problems:

- Parameter binding separates data from query syntax.
- Wildcard escaping ensures user-entered `%` and `_` characters are searched as literals.

## 10. Building Small, Reusable Specifications

When filters have many criteria, you can decompose them into small business-focused Specifications.

Example:

~~~java
public static Specification<Product> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }

        String value = escapeLike(keyword.strip())
            .toLowerCase(Locale.ROOT);

        return cb.like(
            cb.lower(root.<String>get("name")),
            "%" + value + "%",
            '!'
        );
    };
}

public static Specification<Product> priceAtLeast(
        BigDecimal minPrice) {
    return (root, query, cb) -> {
        if (minPrice == null) {
            return null;
        }

        return cb.greaterThanOrEqualTo(
            root.<BigDecimal>get("price"),
            minPrice
        );
    };
}

public static Specification<Product> isAvailable(Boolean available) {
    return (root, query, cb) -> {
        if (available == null) {
            return null;
        }

        return cb.equal(root.get("available"), available);
    };
}
~~~

Composition:

~~~java
Specification<Product> spec =
    ProductSpecs.hasCategory(categoryId)
        .and(ProductSpecs.priceAtLeast(minPrice))
        .and(ProductSpecs.isAvailable(available));
~~~

Specifications without an active filter return a null predicate. Spring Data JPA's composition mechanism treats null predicates as no-op conditions omitted from the combination.

In newer Spring Data JPA versions, some composition APIs may emit deprecation warnings or offer new ways to construct unrestricted specifications. Use the API matching your project's release train; the core principle remains adding no predicate for skipped filters.

If a project prefers avoiding version differences, it can use a single Specification building a `List<Predicate>` as shown in Section 6.

## 11. Combining AND and OR with Proper Grouping

By default, the previous example combines filters with AND:

~~~text
keyword AND category AND minPrice AND available
~~~

Sometimes one group of conditions requires OR—for instance, finding products whose name or SKU contains a keyword:

~~~java
Predicate nameMatches = cb.like(
    cb.lower(root.<String>get("name")),
    pattern,
    '!'
);

Predicate skuMatches = cb.like(
    cb.lower(root.<String>get("sku")),
    pattern,
    '!'
);

predicates.add(cb.or(nameMatches, skuMatches));
~~~

Resulting condition group:

~~~text
(name matches keyword OR sku matches keyword)
AND category filter
AND price filter
~~~

Create the OR group as a single predicate and add that predicate to the outer AND list. Avoid chaining operators in ways that alter meaning due to AND/OR precedence.

If an OR branch is optional, include it only when its input is valid. Do not add a null-comparison branch just to keep a fixed predicate count.

## 12. Price Ranges and Date/Time Ranges

For minPrice and maxPrice:

- Only minPrice: price >= minPrice.
- Only maxPrice: price <= maxPrice.
- Both: price within range.
- Both null: no price filter.

Validate `minPrice <= maxPrice` at the validation layer. If minPrice exceeds maxPrice, return a clear input error instead of running a query guaranteed to return nothing.

For time values, decide whether bounds are inclusive or exclusive:

- GreaterThanOrEqualTo and LessThanOrEqualTo are inclusive.
- GreaterThan and LessThan are exclusive.

If the API accepts LocalDate while the database stores timestamps, clarify the timezone and how the end date translates to an end-of-day instant. Never add one day or shift timezones silently inside a Specification without explicit business rules.

With half-open intervals `[from, to)`, `createdAt >= from` and `createdAt < to` are commonly used. This helps when filtering by dates or consecutive time windows without boundary overlap.

## 13. Collection Filters and Empty Lists

An IN condition fits when users select multiple statuses:

~~~java
if (filter.statuses() != null
        && !filter.statuses().isEmpty()) {
    predicates.add(root.get("status").in(filter.statuses()));
}
~~~

Define semantics explicitly:

| statuses Value | Behavior in Example |
|---|---|
| null | Do not filter status |
| Empty set | Do not filter status |
| Non-empty | Only return statuses in the set |

If business logic dictates an empty list means matching no products, express that explicitly with an always-false predicate:

~~~java
if (filter.statuses() != null
        && filter.statuses().isEmpty()) {
    predicates.add(cb.disjunction());
}
~~~

cb.disjunction() is a FALSE predicate. Conversely, cb.conjunction() is a TRUE predicate.

Never pass an empty collection into `IN` and rely on whatever SQL the provider generates. Empty `IN` handling varies across providers and databases. Decide at the API contract level and build the matching predicate.

## 14. Relationships and Joining Only When Filters Require It

Only if the user filters by categoryId does the query need to reference category. If categoryId is absent, do not create a join just to evaluate an inactive condition.

Example:

~~~java
if (filter.categoryId() != null) {
    predicates.add(
        cb.equal(
            root.get("category").get("id"),
            filter.categoryId()
        )
    );
}
~~~

If explicit JOIN type control is needed:

~~~java
if (filter.categoryId() != null) {
    Join<Product, Category> category =
        root.join("category", JoinType.INNER);

    predicates.add(
        cb.equal(category.get("id"), filter.categoryId())
    );
}
~~~

Create the Join only when the filter needs it. For optional relationships, an INNER JOIN filters out entities without a category; that makes sense when a categoryId filter is active, but not if your goal is to retain products lacking a category.

Never create the join upfront before checking whether the filter is null. Unnecessary joins can alter the result set or inflate query cost.

## 15. Collection Relationships and Duplicate Root Entities

If filtering Products by a collection association such as tags, joining can produce multiple rows for the same Product.

Example:

~~~java
Join<Product, Tag> tag = root.join("tags");
predicates.add(tag.get("id").in(filter.tagIds()));
query.distinct(true);
~~~

DISTINCT can deduplicate root entities in the result, though joining a collection can still complicate count queries and pagination.

If you only need to check whether a Product has at least one matching Tag, consider a correlated EXISTS subquery to avoid multiplying rows in the main query. Illustrative structure:

~~~java
Subquery<Integer> subquery = query.subquery(Integer.class);
Root<ProductTag> productTag = subquery.from(ProductTag.class);

subquery.select(cb.literal(1))
    .where(
        cb.equal(productTag.get("product"), root),
        productTag.get("tag").get("id").in(filter.tagIds())
    );

predicates.add(cb.exists(subquery));
~~~

This example assumes a domain entity ProductTag with `product` and `tag` relationships. Adjust entity/property names to your actual mapping.

EXISTS often makes existence-check intent clearer and prevents outer-query Product row multiplication. Still measure performance on the real database.

## 16. Distinguishing Skipping a Filter from Finding NULL Values

This is one of the most important API design decisions.

For example, for the contactEmail field:

- ANY: apply no email condition.
- IS_NULL: only return products where contactEmail is NULL.
- IS_NOT_NULL: only return products where contactEmail is not NULL.

A single nullable String cannot represent all three states cleanly if null means both "not sent" and "find NULL".

Use an enum or a separate mode field:

~~~java
public enum NullMode {
    ANY,
    IS_NULL,
    IS_NOT_NULL
}
~~~

Specification:

~~~java
if (filter.emailNullMode() == NullMode.IS_NULL) {
    predicates.add(cb.isNull(root.get("contactEmail")));
} else if (filter.emailNullMode() == NullMode.IS_NOT_NULL) {
    predicates.add(cb.isNotNull(root.get("contactEmail")));
}
~~~

If the API uses JSON, expose an explicit operation field such as emailMode. Avoid relying on distinguishing omitted fields from null fields if your serialization framework deserializes both into the same state.

For PATCH or filter APIs that genuinely need to distinguish missing from explicit null, use a wrapper/JSON node/tri-state DTO compatible with your serialization framework.

## 17. Validation Before Query Creation

Specification is responsible for turning valid filters into predicates. Input validation should live in the API/service layer or inside the filter DTO constructor.

Common validations:

- minPrice is non-negative if the domain forbids negative prices.
- minPrice does not exceed maxPrice.
- createdFrom is not after createdTo.
- keyword stays within a maximum length.
- status list size stays within bounds.
- categoryId and other IDs are validly formatted.
- page size and page number stay within limits.
- sort keys belong to an allowed list.

Do not use Specification as a substitute for validation. Invalid requests should be rejected with clear errors instead of silently executing queries doomed to return no matches.

## 18. Combining Specification with Pageable and Sort

Specification describes filter criteria; Pageable describes pagination and ordering. Keep these two responsibilities separate.

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Service:

~~~java
public Page<Product> search(
        ProductFilter filter,
        Pageable pageable) {

    Specification<Product> specification =
        ProductSpecifications.from(filter);

    return productRepository.findAll(specification, pageable);
}
~~~

Pageable can carry a Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Adding a unique key as the final sort criterion guarantees deterministic ordering when multiple rows share the same createdAt.

Avoid setting `orderBy` inside every Specification if that Specification is also used with a Pageable containing Sort. Modifying query order inside a Specification can conflict with caller sorting or interfere with the count query.

If sorting by a special expression is needed, handle it explicitly via a controlled query or custom repository.

## 19. Page, Slice, and Count Queries

findAll(specification, pageable) typically returns a Page. Page provides total elements and total pages; to compute them, Spring Data may run a count query.

If a Specification creates a collection JOIN, the count query might count joined rows rather than root entities. Use appropriate DISTINCT or EXISTS structures to count accurately.

If the UI only needs to know whether a next page exists, consider Slice. Slice typically avoids counting totals, lowering cost on large queries.

When queries involve complex joins, collection fetches, or distinct, inspect the generated SQL and count query. If custom count control is needed, use an explicit repository query or custom repository.

## 20. Client Sort Keys Must Be Whitelisted

Never accept arbitrary property names from clients and pass them directly into Sort.

Example public sort key mapping:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "newest", "createdAt",
    "price", "price",
    "name", "name"
);

public Sort resolveSort(String key, String direction) {
    String property = SORT_FIELDS.get(key);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction sortDirection =
        Sort.Direction.fromString(direction);

    return Sort.by(
        new Sort.Order(sortDirection, property)
    );
}
~~~

Whitelisting restricts queries to approved properties and prevents exposing internal fields through sorting. Never pass raw input into JpaSort.unsafe.

Also bound page size, number of sort criteria, and direction. If direction is invalid, throw a clear error rather than silently defaulting to DESC.

## 21. Splitting Specifications by Criterion

In large systems, each condition can be its own reusable method:

~~~java
public final class ProductSpecs {

    private ProductSpecs() {
    }

    public static Specification<Product> hasCategory(Long categoryId) {
        return (root, query, cb) -> categoryId == null
            ? null
            : cb.equal(root.get("category").get("id"), categoryId);
    }

    public static Specification<Product> priceAtLeast(
            BigDecimal minPrice) {
        return (root, query, cb) -> minPrice == null
            ? null
            : cb.greaterThanOrEqualTo(
                root.<BigDecimal>get("price"),
                minPrice
            );
    }

    public static Specification<Product> isAvailable(Boolean available) {
        return (root, query, cb) -> available == null
            ? null
            : cb.equal(root.get("available"), available);
    }
}
~~~

Composing Specifications:

~~~java
Specification<Product> spec =
    ProductSpecs.hasCategory(categoryId)
        .and(ProductSpecs.priceAtLeast(minPrice))
        .and(ProductSpecs.isAvailable(available));
~~~

This supports reuse and testing per predicate. However, with many filters, a single `from(filter)` method building a `List<Predicate>` can be easier to follow because the entire filter contract resides in one place.

Choose the structure suited to your complexity. Avoid creating dozens of tiny classes if they are neither reused nor helpful for readability.

## 22. When to Use Specification vs. @Query?

| Situation | Appropriate Choice |
|---|---|
| A fixed query with few conditions | Derived query or @Query |
| Many optional filters combined dynamically | Specification |
| Need to reuse predicates across multiple queries | Specification |
| Query with projections, group by, or complex expressions | @Query or custom repository |
| Query requiring diverse dynamic structural changes | Criteria API or Specification |
| Database-specific SQL | Native query/custom repository |
| Simple filters with just a few parameters | Derived query may suffice |

Do not use Specification just because you can. For simple, fixed queries, repository methods are easier to read. Specification excels when condition combinations vary per request and need reuse.

## 23. Testing Specifications

Include both unit tests for predicate/normalization logic and integration tests for database results.

Test data can include:

| Product | category | price | available | contactEmail |
|---|---|---:|---|---|
| Keyboard A | 1 | 700000 | true | a@example.com |
| Keyboard B | 1 | 400000 | false | NULL |
| Mouse A | 2 | 250000 | true | m@example.com |
| Mouse B | 2 | 0 | false | NULL |

Cases to verify:

1. All filters null: emits no WHERE predicate and returns all data permitted by the application's access/default scope.
2. Blank keyword: skips name filter.
3. Non-blank keyword: returns only matching products.
4. Keyword containing `%` or `_`: matches literals if required by contract.
5. available = true: returns only true.
6. available = false: returns only false.
7. minPrice = 0: still adds the condition if 0 is valid.
8. Only minPrice or maxPrice: applies only that bound.
9. Both bounds: returns the exact range.
10. statuses null and empty: matches documented semantics.
11. emailNullMode IS_NULL: returns only NULL emails.
12. emailNullMode IS_NOT_NULL: returns only non-NULL emails.
13. OR group: verifies correct logical parentheses.
14. Collection JOIN: does not multiply entities unintentionally.
15. Page: totalElements counts entities accurately.
16. Sort: ordering with tie-breaker is deterministic.

Integration test example:

~~~java
@DataJpaTest
class ProductSpecificationTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void falseIsARealFilterValue() {
        ProductFilter filter = new ProductFilter(
            null,
            null,
            null,
            null,
            null,
            false,
            null,
            null,
            ProductFilter.NullMode.ANY
        );

        List<Product> products = repository.findAll(
            ProductSpecifications.from(filter)
        );

        assertTrue(products.stream().allMatch(
            product -> !product.getAvailable()
        ));
    }
}
~~~

This test assumes fixtures are prepared and Product has an `available` getter. In a real project, add imports, data setup, and test transaction settings per your configuration.

To prove no redundant predicates are emitted, enable SQL logging or use a StatementInspector/query counter to inspect the SQL generated for each filter combination. Do not inspect only the final results when different queries could happen to return the same rows.

## 24. Performance and Query Plans

Dynamic Specifications can produce many SQL shapes depending on filter combinations. While this avoids unnecessary OR branches, it does not guarantee fast queries by itself.

Pay attention to:

- Indexes on columns frequently used in equality/range filters.
- Column order in composite indexes matching real workloads.
- Leading-wildcard LIKE patterns rarely leverage B-tree indexes.
- `LOWER(column)` may require a functional index or a normalized column.
- Collection JOINs can multiply rows and make count queries expensive.
- Multiple AND/OR predicates require execution plan review.
- Page triggers a count query; Slice may fit better when totals are unnecessary.
- Never create joins or fetch joins when filters do not need those associations.

Use EXPLAIN/EXPLAIN ANALYZE or your database's equivalent tool to inspect plans. Measure with production-like data and common filter combinations.

## 25. Common Pitfalls

**1. Using primitive boolean for optional filters**

Primitive false cannot distinguish an omitted filter from filtering for false. Use Boolean wrapper.

**2. Using `if (available)`**

This skips false. Check `available != null`.

**3. Treating blank strings as valid filters**

Empty keywords can produce `LIKE '%%'` with no filtering value. Normalize blank to skip the filter if that is the API contract.

**4. Using null both to skip a filter and to search for NULL**

These are two distinct meanings. Use a separate enum or operation mode.

**5. Passing an empty collection into IN**

Can generate invalid SQL or vary by provider. Handle empty collections before building the predicate.

**6. Creating a JOIN before knowing whether the filter needs it**

Unneeded joins can drop entities or increase cost. Create joins only when the matching condition is active.

**7. Using DISTINCT to mask every JOIN issue**

DISTINCT has overhead and does not fix wrong join conditions. Consider EXISTS if only checking existence.

**8. Passing client sort fields directly**

Whitelist properties and directions. Never feed raw input into Sort expressions.

**9. Putting ORDER BY inside a Specification**

Specifications should focus on predicates. Let Pageable/Sort determine ordering unless a custom query has special needs.

**10. Forgetting count queries during pagination**

Collection JOINs can make totalElements wrong or expensive. Test Page and consider EXISTS, DISTINCT, or Slice.

**11. Not validating price/date ranges**

min greater than max builds meaningless queries. Reject invalid requests before querying.

**12. Creating too many unnecessary tiny Specifications**

Extract when there is reuse or a clear business boundary. Otherwise, a centralized builder can be easier to read.

## 26. Workflow for Building Optional Filters

1. List each filter and its data type.
2. Define clearly what null, blank, false, 0, and empty collections mean.
3. Distinguish skipping a filter from searching for NULL values.
4. Validate inputs and price/date ranges.
5. Normalize keywords and escape wildcards if needed.
6. Create predicates only when valid filters are supplied.
7. Combine AND and OR conditions according to business groups.
8. JOIN associations only when active conditions need them.
9. Use EXISTS when only checking whether a collection has a matching element.
10. Keep sorting and pagination in Pageable.
11. Verify the count query when using Page.
12. Whitelist sort keys and cap page size.
13. Write unit/integration tests for every filter state.
14. Inspect SQL and execution plans on the target database.

## 27. Self-Assessment Checklist

- [ ] I can explain Specification and JpaSpecificationExecutor.
- [ ] I know how to build dynamic predicates from a Filter DTO.
- [ ] I only add conditions when a filter has a value.
- [ ] I know when to return a null predicate if no condition applies.
- [ ] I distinguish Boolean null from false.
- [ ] I distinguish numeric 0 from a skipped filter.
- [ ] I define null and empty collection semantics explicitly.
- [ ] I distinguish skipping a filter from searching for NULL values.
- [ ] I normalize empty and whitespace strings per API contract.
- [ ] I escape LIKE wildcards when literal matching is needed.
- [ ] I combine AND/OR with proper grouping.
- [ ] I only create JOINs when needed.
- [ ] I consider EXISTS for collection relationships.
- [ ] I pair Specification with Pageable/Sort with clear separation of concerns.
- [ ] I check count queries and pagination.
- [ ] I whitelist sort keys and validate inputs.
- [ ] I have integration tests for false, 0, NULL, empty collections, and price ranges.
- [ ] I inspect SQL and execution plans when tuning performance.

## 28. Review Questions

**1. What problem does Specification solve?**

It lets you construct dynamic query conditions from multiple optional filters using the Criteria API and compose them with AND, OR, or NOT.

**2. Why shouldn't you always write `param IS NULL OR condition`?**

That keeps unnecessary branches in the query and can hinder index usage in some scenarios. Specification lets you emit only predicates actually used.

**3. Why must Boolean filters use Boolean instead of boolean?**

Boolean null represents omitting the filter; both true and false are active filter values. Primitive boolean lacks a null state.

**4. When does a Specification return a null predicate?**

When no corresponding condition needs to be applied. Spring Data JPA omits null predicates while building the query.

**5. What should an empty collection mean?**

That is an API/domain decision: skip the filter, return empty results, or reject the request. Define it explicitly rather than relying on how a provider handles an empty IN clause.

**6. How do you distinguish not filtering email from finding only NULL emails?**

Use an explicit mode such as ANY, IS_NULL, and IS_NOT_NULL rather than a single nullable String parameter.

**7. Why only JOIN when the filter needs the relationship?**

Unnecessary JOINs can change the result set, multiply rows, or add overhead. Joining only when needed keeps the query faithful to the request.

**8. When should you use EXISTS instead of JOIN?**

When you only need to know at least one related record matches without fetching columns from that record. EXISTS avoids multiplying rows in the main query.

**9. Should Specification be responsible for sorting?**

Normally no. Specification describes predicates; Pageable and Sort describe ordering and pagination. Separating them aids reuse and prevents conflicts.

**10. Why test SQL in addition to testing results?**

Two query constructions may return identical results on small fixtures yet carry vastly different costs. SQL logging, query counters, and execution plans expose redundant conditions, unneeded joins, and expensive count queries.

Good optional filters put only the conditions the user actually requested into the query. Once the semantics of null, false, 0, blank strings, and empty collections are clearly defined, Specification keeps repositories readable, testable, and easier to optimize.

## References

- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
