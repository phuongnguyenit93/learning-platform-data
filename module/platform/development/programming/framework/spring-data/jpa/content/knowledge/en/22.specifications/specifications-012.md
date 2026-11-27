# Testing Reusable Specification Suites

## Objectives

Spring Data JPA Specifications let you separate query criteria into small predicates that can be composed and reused across multiple repository methods or use cases. However, a Specification is truly trustworthy only once tested against JPA mappings and a database: a condition can be syntactically valid Java yet emit wrong SQL, JOINs can multiply rows, or a count query can return a different total than the content query.

This lesson focuses on designing reusable Specifications and testing them with repository integration tests. We verify individual conditions, AND/OR composition, optional filters, pagination/counting, association JOINs, and edge cases.

After this lesson, you can:

- Understand the structure and lifecycle of `Specification<T>`.
- Write small, independent, stateless Specifications.
- Combine conditions using `and`, `or`, and `not`.
- Test predicates via `JpaSpecificationExecutor`.
- Verify optional filters, nulls, blank strings, and dates.
- Catch JOIN, DISTINCT, pagination, and count query bugs.
- Choose between unit tests and integration tests with a real JPA provider.
- Structure test suites so Specifications remain safely reusable as business rules evolve.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What Is a Specification?

`Specification<T>` is a Spring Data JPA abstraction for representing a Criteria API predicate. The interface defines the method:

```java
Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
);
```

The three parameters have specific roles:

- `Root<T>`: represents the entity being queried; used to access properties and associations.
- `CriteriaQuery<?>`: represents the query structure; can be used for DISTINCT, subqueries, or other query parts when truly needed.
- `CriteriaBuilder`: supplies the API to build conditions such as equal, like, greaterThan, and, or, isNull.

A Specification returns a Predicate describing a WHERE condition. Spring Data takes that predicate and integrates it into the query executed by the repository.

Example:

```java
public static Specification<Employee> isActive(boolean active) {
    return (root, query, cb) ->
            cb.equal(root.get("active"), active);
}
```

This is a standalone Specification. It can be used in lists, pagination, row counts, or composed with other Specifications.

## 2. Enabling Specification Execution on a Repository

The repository must extend `JpaSpecificationExecutor<T>`:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

Commonly used methods:

```java
repository.findAll(specification);
repository.findAll(specification, sort);
repository.findAll(specification, pageable);
repository.findOne(specification);
repository.count(specification);
repository.exists(specification);
```

`JpaSpecificationExecutor` executes Specifications on the domain entity type. The repository does not need separate methods for every filter combination.

If you need DTO projections, custom queries, or complex fetch plans, pair Specifications with custom repositories or other APIs. Never force every query shape into one shared Specification.

## 3. Sample Entity Used in Testing

We use `Employee` with three filterable properties: `fullName`, `active`, and `createdAt`.

```java
package com.example.demo.employee;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private Instant createdAt;

    protected Employee() {
    }

    public Employee(String fullName, boolean active, Instant createdAt) {
        this.fullName = fullName;
        this.active = active;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Repository:

```java
package com.example.demo.employee;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface EmployeeRepository
        extends JpaRepository<Employee, Long>,
                JpaSpecificationExecutor<Employee> {
}
```

This entity and repository serve as the foundation for the following examples. In real projects, use the exact package, constructors, and attributes of your existing domain model.

## 4. Splitting Specifications into Small Conditions

A reusable Specification should focus on one business condition. Avoid building one giant Specification holding every filter, sort, fetch, and screen-specific quirk.

Example:

```java
package com.example.demo.employee;

import java.time.Instant;
import java.util.Locale;

import jakarta.persistence.criteria.Path;
import org.springframework.data.jpa.domain.Specification;

public final class EmployeeSpecifications {

    private EmployeeSpecifications() {
    }

    public static Specification<Employee> isActive(Boolean active) {
        return (root, query, cb) -> {
            if (active == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("active"), active);
        };
    }

    public static Specification<Employee> fullNameContains(String keyword) {
        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return cb.conjunction();
            }

            String normalized = keyword.trim().toLowerCase(Locale.ROOT);
            Path<String> fullName = root.get("fullName");

            return cb.like(
                    cb.lower(fullName),
                    "%" + normalized + "%"
            );
        };
    }

    public static Specification<Employee> createdAtOnOrAfter(Instant from) {
        return (root, query, cb) -> {
            if (from == null) {
                return cb.conjunction();
            }

            Path<Instant> createdAt = root.get("createdAt");
            return cb.greaterThanOrEqualTo(createdAt, from);
        };
    }

    public static Specification<Employee> createdBefore(Instant to) {
        return (root, query, cb) -> {
            if (to == null) {
                return cb.conjunction();
            }

            Path<Instant> createdAt = root.get("createdAt");
            return cb.lessThan(createdAt, to);
        };
    }
}
```

Each method returns a stateless Specification. Arguments are passed when constructing the Specification, while Root/CriteriaBuilder are used only when the provider evaluates the predicate.

### 4.1. Why Write Small Conditions?

You can reuse `isActive` across list screens, reports, and search APIs. `fullNameContains` can combine with other filters without duplicating condition logic.

Benefits:

- Each condition has one clear purpose.
- Conditions can be tested individually.
- Conditions compose across diverse use cases.
- When a business rule changes, you update it in one place.
- Method names express intent without leaking Criteria API details into services.

Do not build an overly fragmented Specification library. Split along conditions that carry clear business meaning and actual reuse.

### 4.2. Why Do Optional Filters Return a Conjunction?

`cb.conjunction()` produces an always-true predicate—an identity condition that does not narrow results. When combined with AND, this predicate leaves results unchanged:

```java
isActive(null).and(fullNameContains("an"))
```

The effective result applies only the name filter. Returning a `null` predicate per Spring Data Specification conventions is also possible in supported versions, though `cb.conjunction()` expresses "do not filter" explicitly and reads clearly.

Distinguish "do not apply filter" from "find rows where property is null". Those two cases have distinct semantics. If business rules require matching rows with a null column, create a dedicated Specification using `cb.isNull(...)`.

### 4.3. Handling Blank Strings and Wildcards

In the example, `fullNameContains` treats null or whitespace-only strings as no filter. It uses `LIKE '%keyword%'`; `%` and `_` entered by users still behave as LIKE wildcards.

If literal string matching is required, escape wildcards and declare the escape character:

```java
private static String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

Then pass the escaped pattern into `cb.like(expression, pattern, '!')`. Parameter binding is still handled by the provider; wildcard escaping addresses search semantics rather than replacing parameter binding.

## 5. Combining Specifications with AND and OR

Specifications combine via interface methods:

```java
Specification<Employee> specification =
        EmployeeSpecifications.isActive(true)
                .and(EmployeeSpecifications.fullNameContains("an"))
                .and(EmployeeSpecifications.createdAtOnOrAfter(
                        Instant.parse("2026-01-01T00:00:00Z")
                ));
```

Equivalent logic:

```sql
WHERE active = true
  AND lower(full_name) LIKE '%an%'
  AND created_at >= '2026-01-01T00:00:00Z'
```

OR composition:

```java
Specification<Employee> nameMatches =
        EmployeeSpecifications.fullNameContains("an")
                .or(EmployeeSpecifications.fullNameContains("binh"));
```

You can group conditions explicitly:

```java
Specification<Employee> specification =
        EmployeeSpecifications.isActive(true)
                .and(
                    EmployeeSpecifications.fullNameContains("an")
                            .or(EmployeeSpecifications.fullNameContains("binh"))
                );
```

Equivalent logic:

```sql
WHERE active = true
  AND (
      lower(full_name) LIKE '%an%'
      OR lower(full_name) LIKE '%binh%'
  )
```

Parentheses in Java composition matter greatly. Omitting the OR grouping can create logic differing from business rules.

### 5.1. Negating with not

You can invert a Specification:

```java
Specification<Employee> inactive =
        Specification.not(EmployeeSpecifications.isActive(true));
```

The result negates the active predicate. When dealing with nulls or SQL three-valued logic, check predicate semantics carefully; `NOT` over a condition can evaluate to `UNKNOWN`, unlike simple Java booleans.

## 6. Structuring a Service for Dynamic Queries

The service accepts a search DTO and combines only supported conditions:

```java
public record EmployeeSearchForm(
        String name,
        Boolean active,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Service:

```java
@Service
@Transactional(readOnly = true)
public class EmployeeSearchService {

    private final EmployeeRepository repository;

    public EmployeeSearchService(EmployeeRepository repository) {
        this.repository = repository;
    }

    public Page<Employee> search(
            EmployeeSearchForm form,
            Pageable pageable
    ) {
        if (form.createdFrom() != null
                && form.createdTo() != null
                && !form.createdFrom().isBefore(form.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        Specification<Employee> specification =
                EmployeeSpecifications.isActive(form.active())
                        .and(EmployeeSpecifications.fullNameContains(form.name()))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(
                                form.createdFrom()
                        ))
                        .and(EmployeeSpecifications.createdBefore(
                                form.createdTo()
                        ));

        return repository.findAll(specification, pageable);
    }
}
```

The service validates relationships among parameters—for example, start date must precede end date. Specifications focus on expressing database conditions.

Never accept arbitrary property names from clients to pass into Criteria paths or Sort. For dynamic sorting, use an enum/allowlist and bound page size at the service/controller layer.

## 7. Testing Specifications Through the Repository

A Specification uses the Criteria API and depends on JPA mappings. The most valuable test typically runs it through the repository against a real JPA provider and test database.

`@DataJpaTest` is well-suited for testing the persistence slice:

- Entity mappings and repositories are configured.
- Specifications build valid predicates.
- Queries return the right dataset.
- JOIN, DISTINCT, and count queries behave as intended.
- Pageable and Sort are applied.

Full test example:

```java
package com.example.demo.employee;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class EmployeeSpecificationsTest {

    @Autowired
    private EmployeeRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAllAndFlush(List.of(
                new Employee(
                        "An Nguyen",
                        true,
                        Instant.parse("2026-01-10T08:00:00Z")
                ),
                new Employee(
                        "Binh Tran",
                        true,
                        Instant.parse("2026-02-10T08:00:00Z")
                ),
                new Employee(
                        "An inactive",
                        false,
                        Instant.parse("2026-03-10T08:00:00Z")
                ),
                new Employee(
                        "Chi Le",
                        true,
                        Instant.parse("2025-12-10T08:00:00Z")
                )
        ));

        // Force subsequent reads to fetch via queries.
        repository.flush();
    }

    @Test
    void combinesActiveNameAndDateFilters() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true)
                        .and(EmployeeSpecifications.fullNameContains("an"))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(
                                Instant.parse("2026-01-01T00:00:00Z")
                        ))
                        .and(EmployeeSpecifications.createdBefore(
                                Instant.parse("2026-03-01T00:00:00Z")
                        ));

        List<Employee> result = repository.findAll(
                specification,
                Sort.by(Sort.Direction.ASC, "id")
        );

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("An Nguyen");
    }

    @Test
    void ignoresOptionalFiltersWhenValuesAreNull() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(null)
                        .and(EmployeeSpecifications.fullNameContains(null))
                        .and(EmployeeSpecifications.createdAtOnOrAfter(null))
                        .and(EmployeeSpecifications.createdBefore(null));

        assertThat(repository.count(specification)).isEqualTo(4);
    }

    @Test
    void groupsOrConditionsInsideActiveFilter() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true)
                        .and(
                            EmployeeSpecifications.fullNameContains("an")
                                    .or(EmployeeSpecifications.fullNameContains("binh"))
                        );

        List<Employee> result = repository.findAll(
                specification,
                Sort.by("id")
        );

        assertThat(result)
                .extracting(Employee::getFullName)
                .containsExactly("An Nguyen", "Binh Tran");
    }

    @Test
    void appliesSpecificationToPageContentAndCount() {
        Specification<Employee> specification =
                EmployeeSpecifications.isActive(true);

        Page<Employee> page = repository.findAll(
                specification,
                PageRequest.of(
                        0,
                        2,
                        Sort.by(Sort.Direction.ASC, "id")
                )
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

This example assumes the entity/repository from earlier sections along with Spring Boot JPA test, JUnit 5, AssertJ dependencies, and a configured test database. `@DataJpaTest` normally runs inside a transaction and rolls back after each test method.

Test setup can call `saveAllAndFlush` to force INSERTs to the database before querying. To ensure queries do not accidentally hit entity instances still sitting in the persistence context, inject `TestEntityManager` and call `clear()` after saving fixtures.

## 8. Testing Individual Specifications in Isolation

Beyond testing combinations, write tests for each key predicate. This pinpoints which exact condition broke as filters evolve.

Case-insensitive name test:

```java
@Test
void fullNameContainsIgnoresCase() {
    Specification<Employee> specification =
            EmployeeSpecifications.fullNameContains("NGUYEN");

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .contains("An Nguyen");
}
```

Testing false status:

```java
@Test
void filtersInactiveEmployees() {
    Specification<Employee> specification =
            EmployeeSpecifications.isActive(false);

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .containsExactly("An inactive");
}
```

Testing a half-open time interval:

```java
@Test
void filtersCreatedAtUsingInclusiveStartAndExclusiveEnd() {
    Specification<Employee> specification =
            EmployeeSpecifications.createdAtOnOrAfter(
                    Instant.parse("2026-01-10T08:00:00Z")
            ).and(
                    EmployeeSpecifications.createdBefore(
                            Instant.parse("2026-02-10T08:00:00Z")
                    )
            );

    List<Employee> result = repository.findAll(specification);

    assertThat(result)
            .extracting(Employee::getFullName)
            .containsExactly("An Nguyen");
}
```

Using `[from, to)` includes the start timestamp and excludes the end timestamp. This is convenient when partitioning by day or month because adjacent intervals do not overlap on boundaries. Align timezone and timestamp precision between Java and the database.

## 9. Testing Association JOINs

Specifications can traverse associations via JOIN. Suppose Employee belongs to Department:

```java
public static Specification<Employee> belongsToDepartment(Long departmentId) {
    return (root, query, cb) -> {
        if (departmentId == null) {
            return cb.conjunction();
        }

        return cb.equal(
                root.join("department").get("id"),
                departmentId
        );
    };
}
```

Tests should create Departments and linked Employees, then verify only Employees in the target department are returned. Never assert merely that the query throws no exception; assert the exact result set.

When a Specification JOINs a collection, a parent entity can appear multiple times—one row per collection element. You may need:

```java
query.distinct(true);
```

However, DISTINCT affects both how the database counts and how the provider builds count queries. Test `findAll(spec, pageable)` and `count(spec)` explicitly to confirm total elements count logical entities rather than joined rows.

## 10. Do Not Arbitrarily Mix Fetch Joins into Shared Specifications

Specifications can access `CriteriaQuery<?>` and add fetches:

```java
root.fetch("department", JoinType.LEFT);
```

However, a Specification containing a fetch join can be reused for both the content query and the Page count query. Count queries do not always permit fetch joins, particularly collection fetches or queries rewritten into counts.

Therefore:

- Keep reusable Specifications focused on WHERE predicates.
- Use `@EntityGraph` or separate queries to control fetch plans when needed.
- If a fetch must live inside a Specification, distinguish content queries from count queries intentionally and integration-test both.
- Avoid letting a simple search Specification alter selection, ordering, or fetch behavior beyond its goal.

This is why small predicate Specifications are far more reusable than Specifications carrying query-level side effects.

## 11. Testing Specifications with Nulls and Boundary Data

Optional filters are a frequent source of bugs. Explicitly verify:

| Case | Expectation |
|---|---|
| Null filter | Adds no corresponding condition |
| Empty string | Normalized or skipped per form rules |
| Whitespace-only string | Does not accidentally generate an empty LIKE pattern |
| Boolean false | Still acts as a valid filter condition |
| Start date boundary | Included or excluded per contract |
| End date boundary | Included or excluded per contract |
| Inverted date range | Rejected at the validation layer |
| `%` and `_` characters | Defined wildcard or literal semantics |
| No matching rows | Returns empty list/page, count equals 0 |
| Completely empty probe/filter | Clearly defined behavior, avoiding accidental full-table scan |

Never use primitives for optional filters when "not provided" must be distinguished from false or 0. Use wrappers like `Boolean` or `Integer` to preserve the unset state.

## 12. Unit Tests or Integration Tests?

Specifications can be tested at multiple levels, each proving different things.

### 12.1. Pure Java Unit Tests

Unit tests suit input normalization, date-range validation, DTO mapping, or filter selection logic. For example, testing blank-to-null normalization:

```java
assertThat(blankToNull("   ")).isNull();
assertThat(blankToNull(" An ")).isEqualTo("An");
```

Do not mock the entire Root, CriteriaBuilder, Path, and Predicate hierarchy just to verify a Specification calls a few methods. Mocking the Criteria API is brittle and fails to prove the query executes on the provider.

### 12.2. Repository Integration Tests

Use `@DataJpaTest` to verify the Specification actually compiles into a query and returns accurate data. This is the primary test level for:

- Predicates and data types.
- Property paths and association mappings.
- AND/OR composition.
- DISTINCT and JOINs.
- Page content/count.
- Nulls and time boundaries.

### 12.3. Testing Against the Production Database

H2 or embedded databases are handy for fast tests, yet do not guarantee parity with PostgreSQL, MySQL, Oracle, or SQL Server on collations, data types, functions, indexes, or query plans.

If Specifications use database functions, vendor-specific types, collations, or dialect-dependent logic, run tests with Testcontainers or a test database matching production.

## 13. Checking Specification Performance

Specification is simply a query builder. It does not make queries inherently faster than derived queries or JPQL.

When queries run slowly, inspect:

- SQL generated by the provider.
- Number of JOINs and potential row multiplication.
- LIKE conditions with leading wildcards.
- Indexes on filter columns and join keys.
- Page count queries.
- Sort columns and page sizes.
- N+1 queries caused by accessing lazy associations after reading results.

Enable SQL logging in development or inspect datasource metrics. Run EXPLAIN/EXPLAIN ANALYZE on the target database to examine index scans, row estimates, sorts, and buffer usage.

Do not assert exact full SQL strings in routine tests, as generated SQL can shift across provider versions. Assert business behavior via data; reserve SQL/plan verification for performance-critical queries.

## 14. Directory Layout and Naming Conventions

A maintainable layout:

```text
employee/
  Employee.java
  EmployeeRepository.java
  EmployeeSearchForm.java
  EmployeeSearchService.java
  EmployeeSpecifications.java
  EmployeeSpecificationsTest.java
```

Conventions:

- Method names express business conditions: `isActive`, `fullNameContains`, `createdBefore`.
- Each method produces one predicate with no mutable state.
- Normalize inputs in the service or a dedicated class; avoid repeating trim/null rules everywhere.
- Shared Specifications should not implicitly inject request-specific authorization filters unless tenant/user context is passed explicitly.
- Mandatory security filters must always be composed server-side on every access path, never trusting client inputs.
- Avoid building a "generic" Specification accepting arbitrary property names from requests.

For large domains, organize into cohesive groups such as `EmployeeSpecifications`, `OrderSpecifications`, and `InvoiceSpecifications` instead of one class holding hundreds of unrelated conditions.

## 15. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| Null filter still narrows results | Inconsistent null handling or primitive default | Use wrappers and explicit no-op predicates |
| OR returns unexpectedly many rows | Wrong AND/OR grouping | Enforce parentheses by grouping Specifications before combining |
| Test passes yet Page total is wrong | Collection JOIN creates duplicate rows or count differs from content | Verify DISTINCT and count query |
| Count query fails | Specification adds fetch join or mutates selection | Keep predicates independent, separate fetch plan |
| Duplicate entities in results | Collection JOIN multiplies rows | Use tested distinct handling |
| H2 test passes but production fails | Different dialect/collation/types | Test against production database via Testcontainers |
| Specification cannot be reused | Contains screen-specific filters or state | Split into small predicates with explicit parameters |
| LIKE fails to match literal %/_ | Wildcards are not escaped | Define semantics and use an escape character |
| Query slows down as filters grow | Missing indexes or non-indexable predicates | Inspect SQL and execution plans |
| Overly complex Criteria API mocks | Testing at the wrong layer | Test predicates through repository integration tests |

## 16. Checklist for a Reusable Specification Suite

- [ ] Repository extends `JpaSpecificationExecutor<T>`.
- [ ] Each Specification expresses one clearly named predicate.
- [ ] Specifications hold no mutable state across calls.
- [ ] Optional filters have defined null/blank semantics.
- [ ] Boolean false and numeric 0 are not confused with "not provided".
- [ ] AND/OR combinations are grouped per business logic.
- [ ] Tests cover every key predicate individually.
- [ ] Tests cover realistic filter combinations.
- [ ] Tests cover null, empty strings, date boundaries, and empty results.
- [ ] Tests verify JOIN/DISTINCT if Specifications traverse associations.
- [ ] Tests verify Page content and total count.
- [ ] Shared Specifications do not arbitrarily add fetch joins or alter selection.
- [ ] Authorization/tenant conditions are always enforced server-side.
- [ ] Critical queries have verified SQL and execution plans.
- [ ] Compatible test databases are used when dialect-dependent behavior exists.

## Conclusion

Reusable Specifications should be small, independent, stateless predicates. Spring Data lets you combine them with AND, OR, and NOT and execute them via `JpaSpecificationExecutor`. This organization helps services assemble dynamic filters without duplicating JPQL for every combination.

A thorough test suite runs Specifications through the repository against a real JPA provider. Verify individual conditions, logical grouping, null/blank handling, JOINs, DISTINCT, pagination, and count queries. Keep fetch plans separate from shared predicates, enforce authorization server-side, and test against production-equivalent databases whenever queries rely on dialect-specific behavior. Doing so keeps Specifications genuinely reusable and accurate as the application grows.
