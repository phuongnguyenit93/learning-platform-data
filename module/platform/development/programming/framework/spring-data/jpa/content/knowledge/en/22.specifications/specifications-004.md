# Building Comparison, String, Range, Null, and Collection Predicates with Specification

## 1. Objectives

Spring Data JPA's `Specification<T>` allows you to build dynamic query conditions using the JPA Criteria API. Instead of creating a repository method for every filter combination, you can write small conditions, reuse them, and combine them with `and`, `or`, and `not`.

This lesson focuses on five common predicate groups:
- **Comparison:** equal, not equal, greater than, greater than or equal to, less than, less than or equal to.
- **String:** case-insensitive equality, substring contains, prefix starts-with, and wildcard handling.
- **Range:** values within numeric or date/time bounds.
- **Null:** matching properties that are null or not null.
- **Collection:** `IN` and `NOT IN` conditions, including policies for empty collections and null elements.

After this lesson, you will be able to enable Specification support on a Repository, create reusable predicates, compose dynamic conditions in a Service, paginate results, and test database behavior.

## 2. Specification and the JPA Criteria API

`Specification<T>` is a Spring Data JPA abstraction representing a filter condition for an Entity of type `T`. It relies on the JPA Criteria API without concatenating JPQL or SQL strings.

A Specification implements the method:

```java
Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder);
```

The three objects have specific roles:

| Object | Role |
| --- | --- |
| `Root<T>` | Represents the Entity being queried; used to access attributes via `root.get("property")`. |
| `CriteriaQuery<?>` | Represents the query structure; can be used to configure distinct or subqueries when needed. |
| `CriteriaBuilder` | Builds predicates such as `equal`, `greaterThan`, `like`, `between`, `isNull`, `in`, `and`, `or`. |

Simple example:

```java
Specification<Product> expensive = (root, query, cb) ->
        cb.greaterThan(root.get("price"), new BigDecimal("100"));
```

This Specification describes the condition `price > 100`. It does not execute the query yet; the Repository runs it when `findAll(specification)` is called.

## 3. Enabling Specification on a Repository

The repository must extend `JpaSpecificationExecutor<T>` in addition to `JpaRepository<T, ID>`.

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>, JpaSpecificationExecutor<Product> {
}
```

`JpaSpecificationExecutor` provides commonly used operations:

| Method | Purpose |
| --- | --- |
| `findAll(spec)` | Retrieves all Entities matching the condition. |
| `findAll(spec, sort)` | Retrieves results matching the condition in the specified sort order. |
| `findAll(spec, pageable)` | Retrieves a single page matching the condition. |
| `count(spec)` | Counts the number of Entities matching the condition. |
| `exists(spec)` | Checks whether any Entity matches the condition. |

Specifications can be reused across many methods without redeclaring query strings.

## 4. Sample Entity Model Used in Examples

The examples use Java 17+, Maven, Spring Boot 3.5.x, Spring Data JPA, and H2. The `Product` entity has a name, price, status, creation timestamp, and optional description.

### 4.1. ProductStatus Enum

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

### 4.2. Product Entity

`src/main/java/com/example/catalog/Product.java`:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(length = 500)
    private String description;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(
            String name,
            BigDecimal price,
            ProductStatus status,
            LocalDateTime createdAt,
            String description) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Product name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price cannot be negative");
        }
        if (status == null || createdAt == null) {
            throw new IllegalArgumentException("Status and createdAt are required");
        }
        if (description != null && description.length() > 500) {
            throw new IllegalArgumentException("Description is too long");
        }
        this.name = name.trim();
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.description = description;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public String getDescription() { return description; }
}
```

`description` is nullable to demonstrate `IS NULL` and `IS NOT NULL`. `status` uses `EnumType.STRING` to store enum names, and `createdAt` uses `LocalDateTime` as this example treats it as system-local date/time.

## 5. Comparison Predicates

`CriteriaBuilder` provides comparison methods for compatible data types. For numbers or types implementing `Comparable`, you can use:

| Meaning | Criteria API |
| --- | --- |
| Equal | `cb.equal(path, value)` |
| Not equal | `cb.notEqual(path, value)` |
| Greater than | `cb.greaterThan(path, value)` |
| Greater than or equal to | `cb.greaterThanOrEqualTo(path, value)` |
| Less than | `cb.lessThan(path, value)` |
| Less than or equal to | `cb.lessThanOrEqualTo(path, value)` |

Specification examples:

```java
public static Specification<Product> priceEqualTo(BigDecimal value) {
    return (root, query, cb) -> cb.equal(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceGreaterThan(BigDecimal value) {
    return (root, query, cb) -> cb.greaterThan(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceAtLeast(BigDecimal value) {
    return (root, query, cb) ->
            cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), value);
}

public static Specification<Product> priceAtMost(BigDecimal value) {
    return (root, query, cb) ->
            cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), value);
}
```

In production code, place these methods in a utility class such as `ProductSpecifications`. Do not pass `null` into these comparison methods; if a filter is not provided, the Service should skip the corresponding predicate.

## 6. String Predicates

### 6.1. Case-Insensitive Equality

To compare strings case-insensitively, normalize both the property and the search value to the same case:

```java
public static Specification<Product> nameEqualsIgnoreCase(String value) {
    String normalized = value.trim().toLowerCase(Locale.ROOT);
    return (root, query, cb) ->
            cb.equal(cb.lower(root.get("name")), normalized);
}
```

For example, `nameEqualsIgnoreCase("KEYBOARD")` matches the name `Keyboard`. `Locale.ROOT` avoids depending on the host machine's default locale.

### 6.2. Contains and Starts-With

`LIKE` supports wildcards:
- `%` matches zero or more characters.
- `_` matches exactly one character.

Example contains and starts-with conditions:

```java
public static Specification<Product> nameContainsIgnoreCase(String value) {
    String pattern = "%" + escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
    return (root, query, cb) ->
            cb.like(cb.lower(root.get("name")), pattern, '\\');
}

public static Specification<Product> nameStartsWithIgnoreCase(String value) {
    String pattern = escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
    return (root, query, cb) ->
            cb.like(cb.lower(root.get("name")), pattern, '\\');
}

private static String escapeLike(String value) {
    return value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
}
```

Escaping `%` and `_` ensures user-entered characters are treated as literal text rather than accidental wildcards. The escape character is passed explicitly to the `CriteriaBuilder.like` overload.

Examples:

- Searching `key` matches `Mechanical Keyboard` when using contains.
- Searching `wire` matches `Wireless Mouse` when using starts-with.
- Searching `100%` matches only strings containing a literal `%` character, rather than treating `%` as a wildcard.

For case-insensitive queries, the database may need an appropriate index (such as a functional index on `lower(name)`) for optimization. A predicate like `lower(column) like '%value%'` typically cannot leverage a standard B-tree index efficiently; inspect the execution plan on large tables.

## 7. Range Predicates

### 7.1. Numeric Ranges

`between` is inclusive of both endpoints. For example, prices from 100 to 500:

```java
public static Specification<Product> priceBetween(
        BigDecimal minimum, BigDecimal maximum) {
    return (root, query, cb) -> cb.between(
            root.<BigDecimal>get("price"), minimum, maximum);
}
```

This condition is equivalent to `price >= minimum AND price <= maximum`. Validate `minimum <= maximum` before running the query to avoid nonsensical input criteria.

### 7.2. Date/Time Ranges

With `LocalDateTime`, `between` works if business logic requires both start and end timestamps to be inclusive:

```java
public static Specification<Product> createdAtBetweenInclusive(
        LocalDateTime from, LocalDateTime to) {
    return (root, query, cb) -> cb.between(
            root.<LocalDateTime>get("createdAt"), from, to);
}
```

For timestamps, many systems prefer a half-open interval `[from, to)`: inclusive start and exclusive end. This avoids constructing end-of-day timestamps that depend on database precision:

```java
public static Specification<Product> createdAtOnOrAfter(LocalDateTime from) {
    return (root, query, cb) ->
            cb.greaterThanOrEqualTo(root.<LocalDateTime>get("createdAt"), from);
}

public static Specification<Product> createdAtBefore(LocalDateTime toExclusive) {
    return (root, query, cb) ->
            cb.lessThan(root.<LocalDateTime>get("createdAt"), toExclusive);
}
```

Combining these two Specifications with `and()` creates `createdAt >= from AND createdAt < toExclusive`. For consecutive intervals, records falling right on the boundary are not duplicated across both intervals.

## 8. Null Predicates

Do not check for null using `equal(path, null)`. In SQL, `column = NULL` never evaluates to TRUE; you must use `IS NULL` or `IS NOT NULL`.

```java
public static Specification<Product> descriptionIsNull() {
    return (root, query, cb) -> cb.isNull(root.get("description"));
}

public static Specification<Product> descriptionIsNotNull() {
    return (root, query, cb) -> cb.isNotNull(root.get("description"));
}
```

Null conditions can be combined with other predicates:

```java
Specification<Product> missingDescription =
        ProductSpecifications.descriptionIsNull()
                .and(ProductSpecifications.priceAtLeast(new BigDecimal("50")));
```

This finds products without a description whose price is at least 50.

Distinguish clearly:
- No description filter passed: add no null predicate.
- Want null descriptions: add `descriptionIsNull()`.
- Want non-null descriptions: add `descriptionIsNotNull()`.

Never overload a single null parameter with multiple implicit meanings. Let the Service decide whether to attach the predicate.

## 9. Collection Predicates IN and NOT IN

The Criteria API supports `in()` to test whether a value belongs to a set.

```java
public static Specification<Product> statusIn(Collection<ProductStatus> statuses) {
    if (statuses == null) {
        throw new IllegalArgumentException("statuses must not be null");
    }
    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("statuses must not contain null");
    }
    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.disjunction();
    }
    return (root, query, cb) -> root.get("status").in(statuses);
}

public static Specification<Product> statusNotIn(Collection<ProductStatus> statuses) {
    if (statuses == null) {
        throw new IllegalArgumentException("statuses must not be null");
    }
    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException("statuses must not contain null");
    }
    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.conjunction();
    }
    return (root, query, cb) -> root.get("status").in(statuses).not();
}
```

Invocation example:

```java
Specification<Product> activeOrDraft =
        ProductSpecifications.statusIn(
                List.of(ProductStatus.ACTIVE, ProductStatus.DRAFT));
```

### 9.1. Policy for Empty Collections

The example above adopts two explicit semantics:

| Condition | Empty Collection | Meaning |
| --- | --- | --- |
| `statusIn(empty)` | `cb.disjunction()` | Always-FALSE predicate, returns no products. |
| `statusNotIn(empty)` | `cb.conjunction()` | Always-TRUE predicate, does not restrict by status. |

This is the policy chosen for the example; other applications may specify differently. What matters is deciding before calling the Repository rather than relying on how a provider/database handles `IN ()` SQL.

### 9.2. Why Reject Null Elements?

SQL uses three-valued logic: TRUE/FALSE/UNKNOWN. With `NOT IN`, even a single null element in the set can turn the comparison into UNKNOWN and exclude rows the author expected to keep.

In this example, `status` is NOT NULL in the database and the helper rejects null elements. If a property is nullable, define explicitly whether null rows should be retained under `NOT IN`; never assume `NOT IN` automatically includes them.

## 10. Organizing the ProductSpecifications Class

The methods from earlier sections are grouped into one class for reuse by Repositories and Services.

`src/main/java/com/example/catalog/ProductSpecifications.java`:

```java
package com.example.catalog;

import jakarta.persistence.criteria.CriteriaBuilder;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.Locale;
import java.util.Objects;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> nameEqualsIgnoreCase(String value) {
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        return (root, query, cb) ->
                cb.equal(cb.lower(root.get("name")), normalized);
    }

    public static Specification<Product> nameContainsIgnoreCase(String value) {
        String pattern = "%" + escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
        return (root, query, cb) ->
                cb.like(cb.lower(root.get("name")), pattern, '\\');
    }

    public static Specification<Product> nameStartsWithIgnoreCase(String value) {
        String pattern = escapeLike(value.trim().toLowerCase(Locale.ROOT)) + "%";
        return (root, query, cb) ->
                cb.like(cb.lower(root.get("name")), pattern, '\\');
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), maximum);
    }

    public static Specification<Product> priceBetween(
            BigDecimal minimum, BigDecimal maximum) {
        return (root, query, cb) -> cb.between(
                root.<BigDecimal>get("price"), minimum, maximum);
    }

    public static Specification<Product> createdAtOnOrAfter(LocalDateTime from) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<LocalDateTime>get("createdAt"), from);
    }

    public static Specification<Product> createdAtBefore(LocalDateTime toExclusive) {
        return (root, query, cb) ->
                cb.lessThan(root.<LocalDateTime>get("createdAt"), toExclusive);
    }

    public static Specification<Product> descriptionIsNull() {
        return (root, query, cb) -> cb.isNull(root.get("description"));
    }

    public static Specification<Product> descriptionIsNotNull() {
        return (root, query, cb) -> cb.isNotNull(root.get("description"));
    }

    public static Specification<Product> statusIn(Collection<ProductStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses must not be null");
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }
        if (statuses.isEmpty()) {
            return (root, query, cb) -> cb.disjunction();
        }
        return (root, query, cb) -> root.get("status").in(statuses);
    }

    public static Specification<Product> statusNotIn(Collection<ProductStatus> statuses) {
        Objects.requireNonNull(statuses, "statuses must not be null");
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }
        if (statuses.isEmpty()) {
            return (root, query, cb) -> cb.conjunction();
        }
        return (root, query, cb) -> root.get("status").in(statuses).not();
    }

    private static String escapeLike(String value) {
        return value.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_");
    }
}
```

In this utility class example, comparison methods expect non-null values. The Service calls them only when the corresponding filter is supplied. `statusIn` and `statusNotIn` proactively define empty collection semantics and reject null elements.

## 11. Combining Specifications with AND, OR, and NOT

Each Specification can be combined with others:

- `and(other)`: both conditions must hold.
- `or(other)`: at least one condition holds.
- `not(spec)`: negates the condition.

Example finding products whose name contains `keyboard` or `mouse` and whose price is at most 200:

```java
Specification<Product> keyboardOrMouse =
        ProductSpecifications.nameContainsIgnoreCase("keyboard")
                .or(ProductSpecifications.nameContainsIgnoreCase("mouse"));

Specification<Product> affordable =
        ProductSpecifications.priceAtMost(new BigDecimal("200"));

Specification<Product> finalSpec = keyboardOrMouse.and(affordable);
```

Equivalent condition:

```text
(name contains 'keyboard' OR name contains 'mouse')
AND price <= 200
```

`not` can negate a Specification:

```java
Specification<Product> notDraft = Specification.not(
        (root, query, cb) -> cb.equal(root.get("status"), ProductStatus.DRAFT));
```

Keep `and`/`or` groups logically parenthesized and clear. Chaining many conditions blindly can easily alter AND vs. OR precedence by accident.

## 12. Building Dynamic Queries in the Service

Sample criteria object holding filters a search screen can send:

`src/main/java/com/example/catalog/ProductSearchCriteria.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public record ProductSearchCriteria(
        String name,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        List<ProductStatus> statuses,
        Boolean descriptionMissing) {
}
```

`null` in criteria means skipping that filter. An empty `statuses` list means no status is accepted, because `statusIn(empty)` yields a FALSE predicate. `descriptionMissing` takes `true` for null descriptions, `false` for non-null descriptions, and `null` to skip the condition.

`src/main/java/com/example/catalog/ProductSearchService.java`:

```java
package com.example.catalog;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductSearchService {
    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<Product> search(ProductSearchCriteria criteria, Pageable pageable) {
        Objects.requireNonNull(criteria, "criteria is required");
        Objects.requireNonNull(pageable, "pageable is required");

        if (criteria.minimumPrice() != null
                && criteria.maximumPrice() != null
                && criteria.minimumPrice().compareTo(criteria.maximumPrice()) > 0) {
            throw new IllegalArgumentException("minimumPrice must not exceed maximumPrice");
        }
        if (criteria.createdFrom() != null
                && criteria.createdBefore() != null
                && !criteria.createdFrom().isBefore(criteria.createdBefore())) {
            throw new IllegalArgumentException("createdFrom must be before createdBefore");
        }
        if (criteria.statuses() != null
                && criteria.statuses().stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("statuses must not contain null");
        }

        List<Specification<Product>> filters = new ArrayList<>();

        if (criteria.name() != null && !criteria.name().isBlank()) {
            filters.add(ProductSpecifications.nameContainsIgnoreCase(criteria.name()));
        }
        if (criteria.minimumPrice() != null) {
            filters.add(ProductSpecifications.priceAtLeast(criteria.minimumPrice()));
        }
        if (criteria.maximumPrice() != null) {
            filters.add(ProductSpecifications.priceAtMost(criteria.maximumPrice()));
        }
        if (criteria.createdFrom() != null) {
            filters.add(ProductSpecifications.createdAtOnOrAfter(criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            filters.add(ProductSpecifications.createdAtBefore(criteria.createdBefore()));
        }
        if (criteria.statuses() != null) {
            filters.add(ProductSpecifications.statusIn(criteria.statuses()));
        }
        if (criteria.descriptionMissing() != null) {
            filters.add(criteria.descriptionMissing()
                    ? ProductSpecifications.descriptionIsNull()
                    : ProductSpecifications.descriptionIsNotNull());
        }

        Specification<Product> specification =
                (root, query, cb) -> cb.conjunction();
        for (Specification<Product> filter : filters) {
            specification = specification.and(filter);
        }

        return repository.findAll(specification, pageable);
    }
}
```

The Service validates input ranges before querying. It then adds only predicates for supplied filters. The initial `Specification` is a TRUE conjunction; when no filters are passed, the query returns products according to Pageable. When `statuses` is an empty list, the FALSE predicate makes the result empty per the chosen policy.

## 13. Repository

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>, JpaSpecificationExecutor<Product> {
}
```

Call `repository.findAll(specification, pageable)` to retrieve a Page. Sort keys in Pageable use Java property names such as `createdAt` or `price`, not physical column names like `created_at`.

## 14. Testing Specifications with H2

Examples use `spring-boot-starter-data-jpa`, H2, and `spring-boot-starter-test`. `@DataJpaTest` initializes the test slice for Entities and Repositories.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:specdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`src/test/java/com/example/catalog/ProductSpecificationTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class ProductSpecificationTest {
    @Autowired
    private ProductRepository repository;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Mechanical Keyboard", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Tactile keys"),
                new Product("Wireless Mouse", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"),
                        null),
                new Product("Mechanical Keyboard Pro", new BigDecimal("180.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "RGB keys"),
                new Product("Mechanical Keyboard Budget", new BigDecimal("80.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T11:00:00"),
                        "Compact layout"),
                new Product("Keyboard Draft", new BigDecimal("140.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T12:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void combinesStringComparisonRangeAndCollectionPredicates() {
        insertProducts();

        Specification<Product> spec =
                ProductSpecifications.nameContainsIgnoreCase("KEYBOARD")
                        .and(ProductSpecifications.priceAtLeast(new BigDecimal("100")))
                        .and(ProductSpecifications.priceAtMost(new BigDecimal("200")))
                        .and(ProductSpecifications.createdAtOnOrAfter(
                                LocalDateTime.parse("2026-01-02T00:00:00")))
                        .and(ProductSpecifications.createdAtBefore(
                                LocalDateTime.parse("2026-01-05T00:00:00")))
                        .and(ProductSpecifications.statusIn(List.of(ProductStatus.ACTIVE)));

        Page<Product> page = repository.findAll(
                spec,
                PageRequest.of(0, 10,
                        Sort.by(Sort.Order.desc("price"), Sort.Order.asc("id"))));

        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getContent()).extracting(Product::getName)
                .containsExactly("Mechanical Keyboard Pro", "Mechanical Keyboard");
    }

    @Test
    void findsNullAndNonNullDescriptions() {
        insertProducts();

        List<Product> missing = repository.findAll(
                ProductSpecifications.descriptionIsNull());
        List<Product> present = repository.findAll(
                ProductSpecifications.descriptionIsNotNull());

        assertThat(missing).extracting(Product::getName)
                .containsExactly("Wireless Mouse");
        assertThat(present).hasSize(4);
    }

    @Test
    void emptyInMatchesNothingAndEmptyNotInAddsNoRestriction() {
        insertProducts();

        List<Product> inResult = repository.findAll(
                ProductSpecifications.statusIn(List.of()));
        List<Product> notInResult = repository.findAll(
                ProductSpecifications.statusNotIn(List.of()));

        assertThat(inResult).isEmpty();
        assertThat(notInResult).hasSize(5);
    }

    @Test
    void supportsOrCompositionAndEscapedLikeText() {
        insertProducts();

        Specification<Product> keyboardOrMouse =
                ProductSpecifications.nameContainsIgnoreCase("keyboard")
                        .or(ProductSpecifications.nameContainsIgnoreCase("mouse"));

        List<Product> result = repository.findAll(keyboardOrMouse);

        assertThat(result).hasSize(5);
    }

    @Test
    void rejectsNullMembersInStatusCollection() {
        assertThatThrownBy(() ->
                ProductSpecifications.statusIn(java.util.Arrays.asList(ProductStatus.ACTIVE, null)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is `BUILD SUCCESS`. These tests verify AND composition across string, comparison, range, and collection predicates; `IS NULL`/`IS NOT NULL`; empty collection semantics; OR composition; and rejection of null elements. This is the expected outcome of the example, not a build log executed in an actual environment.

## 15. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| Property not found at query runtime | String in `root.get("...")` does not match Java property name. | Check Entity fields/access strategy; consider static metamodel for type safety. |
| String filter returns more results than expected | `%` or `_` in input is interpreted as a wildcard. | Escape LIKE characters and pass an explicit escape character. |
| Null comparison does not work | Using `equal(path, null)` instead of a null predicate. | Use `cb.isNull()` or `cb.isNotNull()`. |
| `IN` with an empty collection generates invalid SQL | Relying on provider/database handling of `IN ()`. | Define semantics explicitly and return an appropriate TRUE/FALSE predicate before executing. |
| `NOT IN` gives unexpected results | Collection contains null or database column can be null. | Reject/filter nulls in the set and decide explicitly how to handle rows with null columns. |
| Time-range results miss or include boundary rows | Using closed intervals for timestamps or imprecise end-of-day timestamps. | Use `[from, to)` with `>=` and `<` where appropriate. |
| OR predicate makes query too broad | Combining AND/OR without clear logical grouping. | Build Specifications for each group and combine with parentheses via `.and()`/`.or()`. |
| Page query runs a costly count query | Specification contains joins or expensive predicates. | Inspect SQL/count plan; use projections or an appropriate pagination approach. |
| Using fetch join in Specification breaks pagination | Collection fetch multiplies rows and affects the count query. | Avoid collection fetches in Specifications used with Page; use EntityGraph or separate queries. |
| Contains string filter query is slow | `lower(name) like '%...%'` rarely leverages a standard B-tree index. | Measure execution plans and consider full-text/trigram or database indexing strategies. |

## 16. Design Principles

1. Each Specification should represent a clearly named, easily testable, reusable condition.
2. Let the Service decide which filters are added; do not overload null with multiple implicit meanings.
3. Validate numeric and time ranges before constructing predicates.
4. Use `cb.isNull`/`cb.isNotNull` for nulls, not equality with null.
5. Define empty-collection semantics and reject null elements unless business rules define them.
6. Escape `%` and `_` when searching literal strings with LIKE.
7. Use half-open intervals for timestamps when stitching consecutive intervals.
8. Compose conditions with `.and()`, `.or()`, and `.not()` using readable logical grouping.
9. Use `Pageable` to paginate Specifications; add deterministic sorting with a unique tie-breaker.
10. Avoid mutating `CriteriaQuery` inside a Specification unless necessary; be especially careful with distinct, fetch, and count queries.
11. Consider the static metamodel if you want compile-time property name checking.
12. Test individual predicates and realistic combinations against the target database.

## 17. Completion Checklist

- [ ] Can explain the roles of `Specification`, `Root`, `CriteriaQuery`, and `CriteriaBuilder`.
- [ ] Enabled `JpaSpecificationExecutor` on the Repository.
- [ ] Built equality, greater-than, less-than, and boundary comparison predicates.
- [ ] Wrote case-insensitive, contains, and starts-with string conditions.
- [ ] Escaped `%` and `_` in LIKE conditions.
- [ ] Created numeric and time range conditions.
- [ ] Used `isNull` and `isNotNull` properly.
- [ ] Used `IN`/`NOT IN` and defined semantics for empty/null collections.
- [ ] Combined conditions with AND, OR, and NOT.
- [ ] Built dynamic queries from a criteria object in a Service.
- [ ] Paginated and sorted results using Pageable.
- [ ] Tested edge cases with `@DataJpaTest`.

Once finished, you can build dynamic search filters using Specification, combining comparison, string, range, null, and collection conditions in a testable and maintainable way.
