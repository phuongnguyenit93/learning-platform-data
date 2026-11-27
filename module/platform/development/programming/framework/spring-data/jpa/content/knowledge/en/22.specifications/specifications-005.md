# Combining Conditions with and, or, not, and Logical Grouping

## Objectives

`Specification<T>` in Spring Data JPA represents a reusable query condition. Each Specification builds a `Predicate` via the Criteria API; Specifications can be combined using `and`, `or`, and `not` to assemble filters from small building blocks.

This composability is valuable when filters depend on user input or business rules with multiple logical branches. Instead of manually concatenating JPQL strings, you build typed conditions, arrange them into groups, and pass them to `JpaSpecificationExecutor` for execution.

Example requirement:

```text
Only select products that are active and not discontinued,
and satisfy one of two groups:
  (category is BOOK or TOOL)
  OR (price from 100 to 500),
and if entered by the user, name must contain 'spring'
and price must be at least 100.
```

Corresponding expression:

```text
active
AND NOT discontinued
AND ((category = BOOK OR category = TOOL)
     OR (price >= 100 AND price <= 500))
AND (name contains spring AND price >= 100)
```

This lesson focuses on building clear condition groups, handling optional filters, understanding `NOT` semantics with null values, and avoiding pitfalls when combining Specifications with joins, pagination, and count queries.

## 1. Specification and Predicate

`Specification<T>` is a Spring Data JPA abstraction for describing a condition for entity `T`. It creates a `Predicate` from three Criteria API objects:

- `Root<T>`: the root entity in `FROM`, used to access properties and associations.
- `CriteriaQuery<?>`: the query under construction; can configure distinct, subqueries, or appropriate query parts.
- `CriteriaBuilder`: factory for creating conditions such as `equal`, `like`, `greaterThan`, `isNull`, `and`, `or`, `not`.

Basic definition:

```java
public interface Specification<T> {
    Predicate toPredicate(
            Root<T> root,
            CriteriaQuery<?> query,
            CriteriaBuilder criteriaBuilder
    );
}
```

In applications, Specifications are typically written as lambdas:

```java
static Specification<Product> hasCategory(String category) {
    return (root, query, cb) ->
            cb.equal(root.get("category"), category);
}
```

A Specification only describes a condition; it does not run the query by itself. The Repository must support `JpaSpecificationExecutor<T>` to accept and execute Specifications.

```java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
```

## 2. Creating Small, Reusable Conditions

Each condition should represent a single, clearly named rule. Example:

```java
public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, cb) ->
                cb.equal(root.get("category"), category);
    }

    public static Specification<Product> isActive(boolean active) {
        return (root, query, cb) ->
                cb.equal(root.get("active"), active);
    }

    public static Specification<Product> isDiscontinued() {
        return (root, query, cb) ->
                cb.isTrue(root.get("discontinued"));
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.get("price"), maximum);
    }
}
```

This snippet illustrates how conditions are defined; the runnable section at the end of the lesson provides complete imports, entity, and repository code.

### Avoiding Duplicated Logic

If multiple screens filter by category or status, share one Specification. When the rule changes, update it in one place rather than editing multiple JPQL strings.

Avoid building one monolithic Specification full of nested `if` branches for every condition. Splitting into small conditions allows unit-level testing, clear naming, and flexible composition per use case.

## 3. Combining with AND

`and()` requires both Specifications to hold:

```java
Specification<Product> spec = hasCategory("BOOK")
        .and(isActive(true));
```

Logic:

```sql
where category = 'BOOK'
  and active = true
```

You can chain multiple conditions:

```java
Specification<Product> spec = hasCategory("BOOK")
        .and(isActive(true))
        .and(priceAtLeast(new BigDecimal("100")))
        .and(priceAtMost(new BigDecimal("500")));
```

Each `and()` call produces a composite Specification. Chaining fits when every condition must hold.

## 4. Combining with OR

`or()` requires at least one Specification to hold:

```java
Specification<Product> categoryGroup = hasCategory("BOOK")
        .or(hasCategory("TOOL"));
```

Logic:

```sql
where category = 'BOOK'
   or category = 'TOOL'
```

Multiple branches can be combined:

```java
Specification<Product> spec = hasCategory("BOOK")
        .or(hasCategory("TOOL"))
        .or(hasCategory("COURSE"));
```

Do not use OR instead of AND merely to make a query "more likely to return results". Every operator must reflect business rules; OR widens the result set, whereas AND narrows it.

## 5. Using NOT to Negate a Condition

`Specification.not(spec)` creates a condition negating the input Specification:

```java
Specification<Product> notDiscontinued =
        Specification.not(isDiscontinued());
```

Equivalent logic:

```sql
where not (discontinued = true)
```

Or written directly via CriteriaBuilder inside a Specification:

```java
static Specification<Product> notInCategory(String category) {
    return (root, query, cb) ->
            cb.not(cb.equal(root.get("category"), category));
}
```

`NOT` is useful when rules are naturally stated as exclusions: not in a category, not discontinued, not locked.

### Watch Out for NULL and SQL Three-Valued Logic

In SQL, comparing against `NULL` typically evaluates to `UNKNOWN`, rather than `TRUE` or `FALSE`. Therefore:

```sql
not (discontinued = true)
```

does not automatically include rows where `discontinued IS NULL`. `NOT UNKNOWN` remains `UNKNOWN`, so those rows are excluded by `WHERE`.

If business rules treat `NULL` as "not discontinued", write the condition explicitly:

```java
static Specification<Product> isNotDiscontinuedOrUnknown() {
    return (root, query, cb) -> cb.or(
            cb.isFalse(root.get("discontinued")),
            cb.isNull(root.get("discontinued"))
    );
}
```

In the runnable example below, `discontinued` is a `NOT NULL` column, so `Specification.not(isDiscontinued())` has unambiguous meaning.

## 6. Logical Grouping and Parentheses

This is the most critical part when queries have multiple branches. Do not rely on intuitive reading of a long fluent chain; assign each group to a Specification variable first, then combine them according to the desired structure.

Example:

```java
Specification<Product> categoryGroup = hasCategory("BOOK")
        .or(hasCategory("TOOL"));

Specification<Product> priceGroup = priceAtLeast(new BigDecimal("100"))
        .and(priceAtMost(new BigDecimal("500")));

Specification<Product> eligible = isActive(true)
        .and(Specification.not(isDiscontinued()))
        .and(categoryGroup.or(priceGroup));
```

Equivalent structure:

```sql
where active = true
  and not (discontinued = true)
  and (
       (category = 'BOOK' or category = 'TOOL')
       or
       (price >= 100 and price <= 500)
  )
```

`categoryGroup` is grouped first, `priceGroup` is grouped first, and then the two groups are ORed together. Finally, that combined group is ANDed with the active state and the NOT condition.

### Example of a Missing-Grouping Bug

Requirement: products must be active and belong to category BOOK or TOOL.

Correct:

```java
Specification<Product> correct = isActive(true)
        .and(hasCategory("BOOK").or(hasCategory("TOOL")));
```

```sql
where active = true
  and (category = 'BOOK' or category = 'TOOL')
```

Logically wrong if written as:

```java
Specification<Product> wrong = isActive(true)
        .and(hasCategory("BOOK"))
        .or(hasCategory("TOOL"));
```

This expression composes into:

```sql
where (active = true and category = 'BOOK')
   or category = 'TOOL'
```

The TOOL branch is no longer constrained by `active = true`, so inactive TOOL products can leak into the results.

Rule: create child Specifications for each OR/AND group first, then combine the groups. This makes logical structure explicit in code and prevents bugs when adding conditions.

## 7. Combining Optional Filters from a Request

In search APIs, users may provide only a few criteria. Only append a Specification when its corresponding filter has a value:

```java
Specification<Product> filters = (root, query, cb) -> cb.conjunction();

if (filter.name() != null && !filter.name().isBlank()) {
    filters = filters.and(nameContains(filter.name()));
}

if (filter.minimumPrice() != null) {
    filters = filters.and(priceAtLeast(filter.minimumPrice()));
}
```

`cb.conjunction()` builds an always-true predicate, acting as the identity element for AND. When no optional filters are given, the query remains valid without extra filtering.

When dynamically assembling an OR group, `cb.disjunction()` builds an always-false predicate, acting as the identity element for OR. Choose the right identity:

| Combinator | Neutral Predicate |
| --- | --- |
| AND | `cb.conjunction()` (TRUE) |
| OR | `cb.disjunction()` (FALSE) |

Never pass a null value into a condition in a way that accidentally emits `field = null`. To match rows where a field is null, use `cb.isNull(root.get("field"))`; if null means the filter is not applied, skip that Specification.

### Separating Request Filters from Business Rules

User-supplied filters and mandatory business conditions should be constructed separately:

```java
Specification<Product> businessRules = isActive(true)
        .and(Specification.not(isDiscontinued()));

Specification<Product> requestFilters = filtersFromRequest(filter);

Specification<Product> finalSpec = businessRules.and(requestFilters);
```

This guarantees callers cannot bypass mandatory rules simply by omitting filters. Every request passes through `businessRules`.

## 8. Combining a List of Specifications

When the number of dynamic filters varies, you can accumulate Specifications in a list:

```java
List<Specification<Product>> parts = new ArrayList<>();

if (category != null) {
    parts.add(hasCategory(category));
}
if (minimumPrice != null) {
    parts.add(priceAtLeast(minimumPrice));
}

Specification<Product> combined = (root, query, cb) -> cb.conjunction();
for (Specification<Product> part : parts) {
    combined = combined.and(part);
}
```

This combines all filters with AND. For an OR group, use a separate list initialized with `cb.disjunction()`, or use the collection combinator APIs provided by your Spring Data JPA version.

Spring Data JPA offers `and`, `or`, `not`, and factory helpers such as `allOf`/`anyOf` in modern releases. When projects must stay compatible across versions, verify available APIs in the actual dependency; accumulating with `and()`/`or()` as above works broadly.

## 9. Joins, Subqueries, and Complex Conditions

Specifications do more than compare fields on the root entity. They can join associations:

```java
static Specification<Product> hasBrandName(String brandName) {
    return (root, query, cb) -> {
        Join<Product, Brand> brand = root.join("brand", JoinType.INNER);
        return cb.equal(brand.get("name"), brandName);
    };
}
```

`root.join` defaults to an inner join; pass `JoinType.LEFT` when root entities without matching associations must be retained. The name in `join("brand")` is the Java property on the entity, not the table name.

For to-many relationships, a join can generate multiple SQL rows for the same root entity. If the query returns entities and duplicates must be eliminated, set `query.distinct(true)`, while verifying the count query when using `Page`.

Specifications can also create subqueries, such as checking whether an entity has a matching child record:

```java
static Specification<Product> hasReviewWithScoreAtLeast(int minimum) {
    return (root, query, cb) -> {
        Subquery<Long> subquery = query.subquery(Long.class);
        Root<Review> review = subquery.from(Review.class);
        subquery.select(review.get("product").get("id"))
                .where(
                    cb.equal(review.get("product"), root),
                    cb.greaterThanOrEqualTo(review.get("score"), minimum)
                );
        return cb.exists(subquery);
    };
}
```

This is an illustrative pattern for the `Review.product` association; your application needs the corresponding entity and mapping.

## 10. Pagination, Count Queries, and Specification

`JpaSpecificationExecutor` lets you use the same Specification for both fetching data and counting:

```java
Page<Product> page = repository.findAll(
        finalSpec,
        PageRequest.of(0, 20, Sort.by("name").ascending().and(Sort.by("id").ascending()))
);

long total = repository.count(finalSpec);
```

`Page<T>` may require a count query to calculate the total number of rows. If you only need to know whether a next page exists, consider an API returning `Slice<T>` or an appropriate bounded query.

A Specification should primarily describe predicates. Avoid stuffing `fetch`, `orderBy`, or structural query mutations into shared Specifications, since the same Specification may be used for both the entity query and the count query. Collection fetch joins can break count queries or emit invalid SQL.

If you genuinely need to fetch associations, consider `@EntityGraph`, custom repositories, or a two-step approach that fetches the IDs/page first and loads associations separately. Always inspect the SQL and results when combining Specification with pagination.

## 11. Null and Type Control

- Use matching Java types with CriteriaBuilder: `BigDecimal` for prices, `Instant`/`LocalDate` for time, enums for enum statuses.
- Use `isNull` and `isNotNull` for null checks; never use `equal(field, null)` in place of `isNull`.
- Understand SQL three-valued logic when negating a predicate that may evaluate to UNKNOWN.
- If a Boolean property is nullable, explicitly define whether null is treated as false, true, or a distinct state.
- For strings, normalize casing and wildcards per business rules; if input contains `%` or `_`, consider escaping them so they do not accidentally act as wildcards.
- For dates/times, specify timezone and boundary rules; using half-open intervals `[from, to)` usually avoids millisecond/microsecond edge bugs at day boundaries.

## 12. Runnable Example with Java 17+, Spring Boot, and H2

This example creates five products and queries them with logical groups. Mandatory conditions are active and not discontinued; products must belong to BOOK/TOOL or be priced between 100–500; request filters require the name to contain `spring` and price to be at least 100.

### Project Structure

```text
specification-logic/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/specification/
        │   ├── SpecificationApplication.java
        │   ├── Product.java
        │   ├── ProductRepository.java
        │   └── ProductSpecifications.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>specification-logic</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:specificationdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Product.java`

```java
package com.example.specification;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 30)
    private String category;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private boolean discontinued;

    protected Product() {
    }

    public Product(String name, String category, BigDecimal price,
                   boolean active, boolean discontinued) {
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
        this.discontinued = discontinued;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
```

### `ProductRepository.java`

```java
package com.example.specification;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface ProductRepository extends
        JpaRepository<Product, Long>,
        JpaSpecificationExecutor<Product> {
}
```

### `ProductSpecifications.java`

```java
package com.example.specification;

import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecifications {
    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, cb) ->
                cb.equal(root.<String>get("category"), category);
    }

    public static Specification<Product> isActive(boolean active) {
        return (root, query, cb) ->
                cb.equal(root.<Boolean>get("active"), active);
    }

    public static Specification<Product> isDiscontinued() {
        return (root, query, cb) ->
                cb.isTrue(root.<Boolean>get("discontinued"));
    }

    public static Specification<Product> priceAtLeast(BigDecimal minimum) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), minimum);
    }

    public static Specification<Product> priceAtMost(BigDecimal maximum) {
        return (root, query, cb) ->
                cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), maximum);
    }

    public static Specification<Product> nameContains(String text) {
        String pattern = "%" + text.toLowerCase(Locale.ROOT) + "%";
        return (root, query, cb) -> cb.like(
                cb.lower(root.<String>get("name")), pattern);
    }

    public static Specification<Product> fromOptionalFilters(
            String name, BigDecimal minimumPrice) {
        Specification<Product> filters =
                (root, query, cb) -> cb.conjunction();

        if (name != null && !name.isBlank()) {
            filters = filters.and(nameContains(name));
        }
        if (minimumPrice != null) {
            filters = filters.and(priceAtLeast(minimumPrice));
        }
        return filters;
    }
}
```

### `SpecificationApplication.java`

```java
package com.example.specification;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

import static com.example.specification.ProductSpecifications.*;

@SpringBootApplication
public class SpecificationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpecificationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Product("Spring Data JPA", "BOOK",
                            new BigDecimal("150.00"), true, false),
                    new Product("Hibernate Tips", "BOOK",
                            new BigDecimal("90.00"), true, false),
                    new Product("Spring Boot Course", "COURSE",
                            new BigDecimal("250.00"), true, false),
                    new Product("Legacy ORM", "TOOL",
                            new BigDecimal("300.00"), false, false),
                    new Product("Retired JPA", "BOOK",
                            new BigDecimal("200.00"), true, true)
            ));
            repository.flush();

            Specification<Product> categoryGroup = hasCategory("BOOK")
                    .or(hasCategory("TOOL"));

            Specification<Product> priceGroup = priceAtLeast(new BigDecimal("100.00"))
                    .and(priceAtMost(new BigDecimal("500.00")));

            Specification<Product> mandatoryRules = isActive(true)
                    .and(Specification.not(isDiscontinued()))
                    .and(categoryGroup.or(priceGroup));

            Specification<Product> requestFilters = fromOptionalFilters(
                    "spring", new BigDecimal("100.00"));

            Specification<Product> finalSpec = mandatoryRules.and(requestFilters);

            Page<Product> page = repository.findAll(
                    finalSpec,
                    PageRequest.of(0, 10,
                            Sort.by(Sort.Order.asc("name"), Sort.Order.asc("id")))
            );

            page.getContent().forEach(product ->
                    System.out.println(product.getName() + " | " + product.getPrice()));
            System.out.println("Total: " + page.getTotalElements());
        };
    }
}
```

### Running the Program

```bash
mvn spring-boot:run
```

Stdout:

```text
Spring Boot Course | 250.00
Spring Data JPA | 150.00
Total: 2
```

Result explanation:

- `Legacy ORM` is excluded because `active = false`.
- `Retired JPA` is excluded because `discontinued = true`.
- `Hibernate Tips` is in category BOOK and active, but its name does not contain `spring` and its price is under 100, so it fails the request filters.
- `Spring Boot Course` is not in BOOK/TOOL, yet its price is within 100–500; it passes the OR group and the request filters.
- `Spring Data JPA` is in BOOK, active, not discontinued, contains `spring` in its name, and meets the minimum price.

Sorting by name then id makes the result order deterministic. `Page` supplies the total count, so Spring Data may run an extra count query.

## 13. Testing Specifications

Testing each small Specification verifies whether individual conditions are right; database integration tests verify the Criteria API, joins, nulls, and actual SQL.

Scenarios to include:

- `hasCategory("BOOK")` only returns products in BOOK.
- `A.and(B)` only returns rows matching both conditions.
- `A.or(B)` returns rows matching at least one branch.
- `Specification.not(A)` excludes rows matching A.
- Group `(A OR B) AND C` does not turn into `(A AND C) OR B`.
- Null or empty request filters do not emit unintended conditions.
- Nullable Booleans are handled according to business rules.
- To-many joins do not duplicate entities or distort total counts.
- `Page` returns accurate content, sorting, and totals.

Composition tests can use `@DataJpaTest`, persist representative fixtures, call `repository.findAll(spec)`, and assert result IDs or names. Do not verify a Specification solely by inspecting SQL strings; data results are the critical confirmation.

## 14. Common Pitfalls

1. **Chaining AND/OR without grouping:** build child Specifications first and combine them to preserve intended parentheses.
2. **Using AND instead of OR or vice versa:** write down the logical expression before translating it into code.
3. **Using NOT on a nullable field without considering UNKNOWN:** define NULL handling explicitly and use `isNull`/`isFalse` as appropriate.
4. **Using `equal(field, null)`:** use `isNull`, or omit the filter if null means "do not apply".
5. **Forgetting the repository executor:** the repository must extend `JpaSpecificationExecutor<T>`.
6. **Hardcoding optional filters in a fixed query:** create Specifications only when inputs have values.
7. **Letting callers bypass business rules:** combine mandatory Specifications at the service layer with request-supplied filters.
8. **Collection joins duplicating roots:** consider `distinct`, `EXISTS`, or subqueries; verify the count query.
9. **Adding fetch joins to shared Specifications:** can make count/pagination queries invalid or expensive.
10. **Using SQL column names instead of property names:** the Criteria API accesses Java properties via `root.get`.
11. **Building oversized Specifications:** break them into small predicates with clear names and responsibilities.
12. **Not testing against the target database:** null semantics, collation, and execution plans depend on the database/provider.

## 15. Practical Guidelines

- Each Specification should describe one clearly named condition.
- Use `and()` when all conditions must hold; use `or()` when any branch suffices.
- Use `Specification.not(...)` to negate a condition and account for NULL under SQL logic.
- Build Specifications for each logical group before combining them to reflect parentheses.
- Use `cb.conjunction()` as the neutral identity when accumulating AND filters; use `cb.disjunction()` for OR groups.
- Separate mandatory business rules from optional request filters.
- Keep Specifications primarily focused on predicates; manage fetch, sort, and pagination in the appropriate places.
- Verify distinct/count behavior when joining to-many relationships.
- Write integration tests for AND/OR/NOT groups, nulls, and boundary data.

Core takeaway: **`and` requires every condition to hold, `or` requires at least one branch to hold, and `not` negates a condition. Build small Specification groups first and combine them according to business parentheses; this clarifies logic, eases adding dynamic filters, and prevents bugs from wrong AND/OR grouping.**
