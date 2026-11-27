# Combining Dynamic Search Conditions with BooleanBuilder

## 1. Objectives

Querydsl's `BooleanBuilder` lets you combine search conditions selected at runtime. For screens with many optional filters, you can append each predicate to a builder rather than creating a dedicated Repository method for every combination of conditions.

This lesson builds a product search with the following condition groups:
- Numeric comparisons: minimum price, maximum price, and greater-than/less-than operators.
- Strings: case-insensitive keyword search across name or SKU.
- Date/time ranges: from an inclusive start timestamp to an exclusive end timestamp.
- Null checks: finding products with a null or non-null description.
- Sets: status belonging to a selected list.
- Logic: combining filters with AND and grouping multiple choices with OR.

After this lesson, you will be able to configure Querydsl for Spring Data JPA, understand automatically generated Q-types, create a BooleanBuilder per request, handle empty collections intentionally, and paginate results using `QuerydslPredicateExecutor`.

## 2. What Is BooleanBuilder?

`BooleanBuilder` is a mutable implementation of Querydsl's `Predicate`. It starts empty and lets you append conditions incrementally with `and()` or `or()`.

```java
QProduct product = QProduct.product;
BooleanBuilder predicate = new BooleanBuilder();

predicate.and(product.status.eq(ProductStatus.ACTIVE));
predicate.and(product.price.goe(new BigDecimal("100")));
predicate.and(product.price.loe(new BigDecimal("500")));
```

Equivalent logic:

```text
status = ACTIVE
AND price >= 100
AND price <= 500
```

A condition is added only when the user provides the filter:

```java
if (keyword != null && !keyword.isBlank()) {
    predicate.and(product.name.containsIgnoreCase(keyword.trim()));
}
```

If keyword is blank, the product name predicate is not added. `BooleanBuilder` mutates with each call; create a fresh builder for every search, and do not store it in a singleton Service field or share it across multiple requests.

## 3. Querydsl, Q-Types, and Spring Data JPA

Querydsl provides a typed Java API for representing queries. Its annotation processor reads JPA Entities and generates the corresponding Q-type classes. For the `Product` Entity, the generated class is `QProduct`, usually located in `target/generated-sources/annotations`.

| Entity property | Typically generated Q-type | Example |
| --- | --- | --- |
| `Long id` | `NumberPath<Long>` | `product.id.eq(10L)` |
| `String name` | `StringPath` | `product.name.containsIgnoreCase("keyboard")` |
| `BigDecimal price` | `NumberPath<BigDecimal>` | `product.price.goe(minimum)` |
| Enum `status` | `EnumPath<ProductStatus>` | `product.status.in(statuses)` |
| `LocalDateTime createdAt` | `DateTimePath<LocalDateTime>` | `product.createdAt.lt(end)` |

Q-types let the compiler catch many type mismatches or wrong property names before running the application. Do not manually edit Q classes because they are regenerated from Entities on every build.

Spring Data JPA provides `QuerydslPredicateExecutor<T>` so Repositories can execute Querydsl predicates, including paginated queries.

## 4. Configuring Querydsl for Spring Boot 3

The examples use Java 17+, Spring Boot 3.5.x, Spring Data JPA 3.5.x, and Querydsl 5.1.0 with Jakarta Persistence. Because Spring Boot 3 uses `jakarta.persistence.*` annotations, you must select the `jakarta` artifact classifier.

In `pom.xml`, declare the dependencies and annotation processor:

```xml
<properties>
    <java.version>17</java.version>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>${java.version}</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>${querydsl.version}</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                    <path>
                        <groupId>jakarta.annotation</groupId>
                        <artifactId>jakarta.annotation-api</artifactId>
                        <version>2.1.1</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Spring Boot dependency management supplies versions for the starters. Querydsl uses its own version pinned at `querydsl.version`; keep `querydsl-jpa` and `querydsl-apt` on the same version.

Run the build to generate Q-types:

```bash
mvn clean compile
```

After building, verify `target/generated-sources/annotations/com/example/catalog/QProduct.java`. If Q-types are not generated, check the annotation processor path, `jakarta` classifier, Entity package, and compiler configuration.

## 5. Entity Model

### 5.1. Enum ProductStatus

`src/main/java/com/example/catalog/ProductStatus.java`:

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    DISCONTINUED
}
```

### 5.2. Entity Product

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

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

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

    public Product(String name, String sku, BigDecimal price, ProductStatus status,
            LocalDateTime createdAt, String description) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Name is required");
        }
        if (sku == null || sku.isBlank() || sku.length() > 40) {
            throw new IllegalArgumentException("SKU is required");
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
        this.sku = sku.trim();
        this.price = price;
        this.status = status;
        this.createdAt = createdAt;
        this.description = description;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public String getDescription() { return description; }
}
```

`description` is nullable to illustrate `isNull()` and `isNotNull()`. The enum uses `EnumType.STRING` to persist status names.

## 6. Criteria Object for Optional Filters

Avoid passing too many separate parameters when a search screen has many fields. A record groups criteria into a single object.

`src/main/java/com/example/catalog/ProductSearchCriteria.java`:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Set;

public record ProductSearchCriteria(
        String keyword,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice,
        LocalDateTime createdFrom,
        LocalDateTime createdBefore,
        Set<ProductStatus> statuses,
        Boolean descriptionMissing) {
}
```

Conventions for this example:
- A null scalar field means skip the filter.
- `statuses == null` means do not filter by status.
- An empty `statuses` set means the user selected no statuses, so the result must be empty.
- `descriptionMissing == true` finds null descriptions; `false` finds non-null descriptions; null skips the description condition.
- Time range uses `createdAt >= createdFrom` and `createdAt < createdBefore`.

Defining semantics upfront distinguishes omitting a filter from submitting an empty collection.

## 7. Building Predicates with BooleanBuilder

The Q-type is generated from the Entity:

```java
QProduct product = QProduct.product;
BooleanBuilder predicate = new BooleanBuilder();
```

### 7.1. Comparison Conditions

Querydsl provides typed operators:

| Meaning | Querydsl |
| --- | --- |
| Equal | `product.status.eq(ProductStatus.ACTIVE)` |
| Not equal | `product.status.ne(ProductStatus.DRAFT)` |
| Greater than | `product.price.gt(value)` |
| Greater than or equal | `product.price.goe(value)` |
| Less than | `product.price.lt(value)` |
| Less than or equal | `product.price.loe(value)` |

Add price conditions conditionally based on input:

```java
if (criteria.minimumPrice() != null) {
    predicate.and(product.price.goe(criteria.minimumPrice()));
}
if (criteria.maximumPrice() != null) {
    predicate.and(product.price.loe(criteria.maximumPrice()));
}
```

Querydsl preserves property types in the Q-type, so the compiler can catch many type errors before the application runs.

### 7.2. String Conditions and OR Grouping

To search a keyword in either name or SKU:

```java
if (criteria.keyword() != null && !criteria.keyword().isBlank()) {
    String keyword = criteria.keyword().trim();
    BooleanBuilder keywordMatch = new BooleanBuilder();
    keywordMatch.or(product.name.containsIgnoreCase(keyword));
    keywordMatch.or(product.sku.containsIgnoreCase(keyword));
    predicate.and(keywordMatch);
}
```

Equivalent logic:

```text
AND (name contains keyword OR sku contains keyword)
```

Group the OR branches first and then add the whole group to the main predicate with AND. If you call `predicate.or(...)` directly for each branch, the result can become `(previous filters AND name-match) OR sku-match`, allowing a matching SKU to bypass price or status conditions.

`containsIgnoreCase` suits case-insensitive substring matching. If `%` or `_` in user input must be treated as literal characters rather than wildcards, verify the behavior of your Querydsl/provider version and add appropriate escaping rules.

### 7.3. Time Range Conditions

For timestamps, half-open intervals are convenient when chaining consecutive ranges:

```java
if (criteria.createdFrom() != null) {
    predicate.and(product.createdAt.goe(criteria.createdFrom()));
}
if (criteria.createdBefore() != null) {
    predicate.and(product.createdAt.lt(criteria.createdBefore()));
}
```

The condition is equivalent to `createdAt >= from AND createdAt < before`. A record at exactly `createdBefore` is excluded from the range. If business rules require including both endpoints, use `between(from, to)` after validating that the bounds are valid.

### 7.4. Null Conditions

Querydsl has dedicated APIs for null checks:

```java
if (Boolean.TRUE.equals(criteria.descriptionMissing())) {
    predicate.and(product.description.isNull());
} else if (Boolean.FALSE.equals(criteria.descriptionMissing())) {
    predicate.and(product.description.isNotNull());
}
```

Do not use `product.description.eq(null)` to express SQL `IS NULL`. Use `isNull()` or `isNotNull()`.

### 7.5. Set Conditions: IN and NOT IN

For a collection of statuses:

```java
if (criteria.statuses() != null) {
    if (criteria.statuses().isEmpty()) {
        predicate.and(Expressions.asBoolean(false));
    } else {
        predicate.and(product.status.in(criteria.statuses()));
    }
}
```

`Expressions.asBoolean(false)` adds an always-false predicate when the user passes an empty list per the chosen semantics. If `statuses` is null, the filter is skipped; if it is a non-empty list, Querydsl builds an IN condition.

For `NOT IN`, you can write:

```java
predicate.and(product.status.notIn(excludedStatuses));
```

Do not pass null elements inside collections used with `IN`/`NOT IN` unless handling is explicitly defined. SQL uses three-valued logic; in particular, a null element in `NOT IN` can evaluate comparisons to UNKNOWN. Validate collections before adding the predicate.

## 8. Complete Predicate Builder Class

Put condition-composition logic into a dedicated class so the Service remains readable and testable.

`src/main/java/com/example/catalog/ProductPredicates.java`:

```java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.dsl.Expressions;
import java.util.Objects;

public final class ProductPredicates {
    private ProductPredicates() {
    }

    public static BooleanBuilder from(ProductSearchCriteria criteria) {
        Objects.requireNonNull(criteria, "criteria must not be null");

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

        QProduct product = QProduct.product;
        BooleanBuilder predicate = new BooleanBuilder();

        if (criteria.keyword() != null && !criteria.keyword().isBlank()) {
            String keyword = criteria.keyword().trim();
            BooleanBuilder keywordMatch = new BooleanBuilder();
            keywordMatch.or(product.name.containsIgnoreCase(keyword));
            keywordMatch.or(product.sku.containsIgnoreCase(keyword));
            predicate.and(keywordMatch);
        }

        if (criteria.minimumPrice() != null) {
            predicate.and(product.price.goe(criteria.minimumPrice()));
        }
        if (criteria.maximumPrice() != null) {
            predicate.and(product.price.loe(criteria.maximumPrice()));
        }
        if (criteria.createdFrom() != null) {
            predicate.and(product.createdAt.goe(criteria.createdFrom()));
        }
        if (criteria.createdBefore() != null) {
            predicate.and(product.createdAt.lt(criteria.createdBefore()));
        }
        if (criteria.statuses() != null) {
            if (criteria.statuses().isEmpty()) {
                predicate.and(Expressions.asBoolean(false));
            } else {
                predicate.and(product.status.in(criteria.statuses()));
            }
        }
        if (Boolean.TRUE.equals(criteria.descriptionMissing())) {
            predicate.and(product.description.isNull());
        } else if (Boolean.FALSE.equals(criteria.descriptionMissing())) {
            predicate.and(product.description.isNotNull());
        }

        return predicate;
    }
}
```

`from()` creates a new builder on every call. It validates input ranges and null collection elements before constructing the query. A predicate is added only when the corresponding filter is provided.

## 9. Repository with QuerydslPredicateExecutor

The Repository extends `QuerydslPredicateExecutor<Product>` to execute BooleanBuilder:

`src/main/java/com/example/catalog/ProductRepository.java`:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>, QuerydslPredicateExecutor<Product> {
}
```

Commonly used methods:

| Method | Purpose |
| --- | --- |
| `findAll(Predicate)` | Retrieves all Entities matching the predicate. |
| `findAll(Predicate, Sort)` | Retrieves results matching the predicate and ordering. |
| `findAll(Predicate, Pageable)` | Retrieves a Page matching the predicate. |
| `count(Predicate)` | Counts matching results. |
| `exists(Predicate)` | Checks whether any matching result exists. |

Because `BooleanBuilder` implements `Predicate`, it can be passed directly to all of the methods above.

## 10. Search Execution Service

`src/main/java/com/example/catalog/ProductSearchService.java`:

```java
package com.example.catalog;

import com.querydsl.core.BooleanBuilder;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
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
        Objects.requireNonNull(pageable, "pageable must not be null");
        BooleanBuilder predicate = ProductPredicates.from(criteria);

        if (!predicate.hasValue()) {
            return repository.findAll(pageable);
        }
        return repository.findAll(predicate, pageable);
    }
}
```

`hasValue()` indicates whether the builder contains any predicate. When no filter is present, the Service calls `findAll(pageable)` to avoid passing an empty builder. When conditions exist, it calls `findAll(predicate, pageable)`.

Pageable can carry a Sort. Use Java Entity property names and whitelist which fields the API allows sorting by. For deterministic results, add ID as a secondary criterion:

```java
Pageable pageable = PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id")));
```

## 11. Query Logic with Multiple Filters

Suppose the user submits:

```text
keyword = "keyboard"
minimumPrice = 100
maximumPrice = 200
statuses = [ACTIVE]
descriptionMissing = false
```

BooleanBuilder produces equivalent logic:

```text
(lower(name) contains 'keyboard' OR lower(sku) contains 'keyboard')
AND price >= 100
AND price <= 200
AND status IN (ACTIVE)
AND description IS NOT NULL
```

If `createdFrom` and `createdBefore` are present, the two time conditions are appended with AND. If keyword is blank, the OR group is omitted. If `statuses` is null, status is unfiltered; if `statuses` is empty, a FALSE predicate is added and no rows match.

These conventions define this example's contract. If an application wants an empty collection to mean "skip filter," update the logic and corresponding tests.

## 12. Testing with H2

The example uses `spring-boot-starter-data-jpa`, Querydsl JPA, H2, and `spring-boot-starter-test`. Q-types must be generated before tests compile.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:querydsldb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/ProductBooleanBuilderTest.java`:

```java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
@Import(ProductSearchService.class)
class ProductBooleanBuilderTest {
    @Autowired
    private ProductRepository repository;

    @Autowired
    private ProductSearchService searchService;

    private void insertProducts() {
        repository.saveAll(List.of(
                new Product("Mechanical Keyboard", "KB-100", new BigDecimal("120.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-02T10:00:00"),
                        "Tactile keys"),
                new Product("Wireless Mouse", "MS-200", new BigDecimal("35.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-03T10:00:00"), null),
                new Product("Mechanical Keyboard Pro", "KB-200", new BigDecimal("180.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T10:00:00"),
                        "RGB keys"),
                new Product("Mechanical Keyboard Budget", "KB-050", new BigDecimal("80.00"),
                        ProductStatus.ACTIVE, LocalDateTime.parse("2026-01-04T11:00:00"),
                        "Compact layout"),
                new Product("Keyboard Draft", "KB-300", new BigDecimal("140.00"),
                        ProductStatus.DRAFT, LocalDateTime.parse("2026-01-04T12:00:00"),
                        "Not published")));
        repository.flush();
    }

    @Test
    void combinesKeywordPriceTimeStatusAndNullPredicates() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                "KEYBOARD", new BigDecimal("100.00"), new BigDecimal("200.00"),
                LocalDateTime.parse("2026-01-02T00:00:00"),
                LocalDateTime.parse("2026-01-05T00:00:00"),
                Set.of(ProductStatus.ACTIVE), false);

        Page<Product> result = searchService.search(criteria,
                PageRequest.of(0, 10,
                        Sort.by(Sort.Order.desc("price"), Sort.Order.asc("id"))));

        assertThat(result.getTotalElements()).isEqualTo(2);
        assertThat(result.getContent()).extracting(Product::getName)
                .containsExactly("Mechanical Keyboard Pro", "Mechanical Keyboard");
    }

    @Test
    void keywordMatchesEitherNameOrSku() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                "MS-200", null, null, null, null, null, null);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getTotalElements()).isEqualTo(1);
        assertThat(result.getContent().get(0).getName()).isEqualTo("Wireless Mouse");
    }

    @Test
    void emptyStatusSetMatchesNoProducts() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, Set.of(), null);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getContent()).isEmpty();
        assertThat(result.getTotalElements()).isZero();
    }

    @Test
    void canSearchForNullDescription() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, null, true);

        Page<Product> result = searchService.search(criteria, PageRequest.of(0, 10));

        assertThat(result.getTotalElements()).isEqualTo(1);
        assertThat(result.getContent().get(0).getName()).isEqualTo("Wireless Mouse");
    }

    @Test
    void rejectsAnInvalidPriceRange() {
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, new BigDecimal("200"), new BigDecimal("100"),
                null, null, null, null);

        assertThatThrownBy(() -> searchService.search(criteria, PageRequest.of(0, 10)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void emptyCriteriaReturnsPagedResults() {
        insertProducts();
        ProductSearchCriteria criteria = new ProductSearchCriteria(
                null, null, null, null, null, null, null);

        Page<Product> result = searchService.search(criteria,
                PageRequest.of(0, 2, Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id"))));

        assertThat(result.getTotalElements()).isEqualTo(5);
        assertThat(result.getContent()).hasSize(2);
        assertThat(result.getNumber()).isZero();
    }
}
```

Run tests:

```bash
mvn clean test
```

The expected result is Maven finishing with `BUILD SUCCESS`. The tests verify the OR group between name and SKU, AND across price/time/status/null, empty collections, invalid price ranges, and pagination when no filters are given. This is the expected outcome of the example, not an actual build log.

## 13. BooleanBuilder and Other Query Approaches

| Approach | Best suited when |
| --- | --- |
| Derived query | Conditions are few, stable, and method names remain readable. |
| JPQL `@Query` | Query structure is fixed and can be expressed concisely in JPQL. |
| JPA Specification | You want to use the standard JPA Criteria API and compose dynamic predicates. |
| Querydsl `BooleanBuilder` | You want typed predicates, dynamic fluent composition, and Q-types. |
| Custom repository | You need projections, complex joins/fetches, multi-step queries, or custom optimizations. |

`BooleanBuilder` and `Specification` both solve dynamic conditions but rely on different APIs. Querydsl requires an annotation processor and Q-types; Criteria Specification uses the standard JPA API, though property names are typically passed as strings if not using the static metamodel.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `QProduct` not found at compile time | Annotation processor did not run or wrong classifier | Check `querydsl-apt` `jakarta` classifier, compiler plugin, and run `mvn clean compile`. |
| Cannot resolve `BooleanBuilder` | Missing Querydsl dependency or wrong package import | Use `com.querydsl:querydsl-jpa` with `jakarta` classifier and import `com.querydsl.core.BooleanBuilder`. |
| OR filter bypasses other conditions | Added each OR branch directly to the main builder | Group OR branches in a child builder and add the group via `predicate.and(group)`. |
| Unexpected query when no filters are given | Passed an empty builder to the executor | Check `hasValue()` and call `findAll(pageable)` when there is no predicate. |
| Empty collection returns unexpected results | Undefined semantics for empty lists | Choose explicitly between FALSE predicate, skipping filter, or throwing an error; enforce in service and tests. |
| `NOT IN` skips rows | Collection contains null or column can be null | Validate null elements and decide clearly how null column values should be handled. |
| Special string search produces wrong results | `%` or `_` has wildcard semantics in LIKE | Define literal/wildcard rules and test escaping with the provider/database. |
| Builder shared across multiple requests | `BooleanBuilder` is mutable and modified per call | Create a new builder per search; do not store in singleton fields. |
| Duplicate or missing records across pages | Unstable sort or changing data | Add a unique sort criterion; consider keyset pagination. |
| Querydsl and JPA incompatible | Mixed `javax` artifacts with Jakarta Entities or version mismatch | Align `jakarta` classifier, Querydsl JPA, and annotation processor. |

## 15. Design Principles

1. Create a fresh `BooleanBuilder` for each search; never share a mutable builder across requests.
2. Group related OR branches into a child builder, then combine the group with remaining filters using AND.
3. Define clear semantics for null and empty collections before building predicates.
4. Validate numeric ranges, time ranges, and null elements inside collections before querying.
5. Use Q-types to leverage compile-time type checking; never edit auto-generated Q files.
6. Add predicates only when filters are supplied; when the builder is empty, call the Repository without a predicate.
7. Use `Pageable` and Sort with whitelisted Entity properties; add a unique key for deterministic ordering.
8. Choose Querydsl when typed dynamic conditions are needed; choose Specification or JPQL if better aligned with existing architecture.
9. Test individual predicates and important AND/OR combinations, especially empty collections and null values.
10. Monitor SQL and execution plans when queries have many conditions or large tables.

## 16. Completion Checklist

- [ ] Can explain `BooleanBuilder` and the role of Q-types.
- [ ] Configured the Querydsl JPA Jakarta annotation processor.
- [ ] Generated and used `QProduct`.
- [ ] Built predicates for equality, greater-than, less-than, and boundary limits.
- [ ] Searched strings with `containsIgnoreCase` and combined multiple branches with OR.
- [ ] Built time ranges with `goe` and `lt`.
- [ ] Used `isNull()` and `isNotNull()` for nullable properties.
- [ ] Used `in()`/`notIn()` and handled empty/null collections intentionally.
- [ ] Combined condition groups with AND and OR without breaking logical precedence.
- [ ] Executed predicates via `QuerydslPredicateExecutor`.
- [ ] Paginated and sorted results with `Pageable`.
- [ ] Tested condition combinations with `@DataJpaTest`.

Once complete, you can build dynamic search filters with Querydsl `BooleanBuilder`, keep AND/OR logic clear, and execute type-safe predicates through Spring Data JPA.