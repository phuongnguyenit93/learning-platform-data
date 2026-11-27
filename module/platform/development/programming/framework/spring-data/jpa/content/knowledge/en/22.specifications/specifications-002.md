# JpaSpecificationExecutor and the Specification<T> Contract

## Objectives

After this lesson, you can accurately describe the `Specification<T>.toPredicate(...)` contract; combine multiple conditions using `and`, `or`, and `not`; build optional filters from a request; execute specifications via `JpaSpecificationExecutor<T>`; and handle issues involving joins, duplicate results, pagination, count queries, and testing.

The examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). Sample code belongs to package `com.example.learning.customer`; if your project already has entities/repositories with the same role, add the necessary methods into your existing structure.

## 1. What Problem Does Specification Solve?

Derived queries work well when search conditions are simple and fixed, such as `findByActiveTrueAndStatus(...)`. However, search screens typically allow users to enter multiple optional filters: name, email, status, creation date, or related conditions. The number of combinations grows rapidly if you create one repository method per case.

`Specification<T>` allows you to describe a query condition as a reusable, composable object. Each specification produces a Criteria API predicate. The repository takes that predicate and executes the query.

For example, instead of creating many separate methods:

```java
findByActiveTrueAndStatus(...);
findByFirstNameContainingIgnoreCaseAndActiveTrue(...);
findByEmailContainingIgnoreCaseAndStatus(...);
```

You can define independent conditions like `firstNameContains(...)`, `activeEquals(...)`, and `hasStatus(...)`, then combine them according to the active filter.

## 2. The Specification<T>.toPredicate Contract

`Specification<T>` is a Spring Data JPA functional interface. Its core method has the signature:

```java
Predicate toPredicate(
    Root<T> root,
    CriteriaQuery<?> query,
    CriteriaBuilder criteriaBuilder
);
```

The three parameters have distinct roles:

| Parameter | Role |
| --- | --- |
| `Root<T> root` | Represents the root entity being queried; used to access properties and create joins |
| `CriteriaQuery<?> query` | Represents the query structure; can be used for distinct or creating subqueries when needed |
| `CriteriaBuilder criteriaBuilder` | Factory for building predicates and expressions such as `equal`, `like`, `and`, `or`, `greaterThan`, `isNull` |

The method returns a `Predicate` describing the filter condition. Example:

```java
public static Specification<Customer> isActive() {
    return (root, query, cb) -> cb.isTrue(root.get("active"));
}
```

A Specification does not execute SQL or open a transaction on its own. It only describes a predicate; `JpaSpecificationExecutor` executes the query.

If a specification does not need to add a condition, it can return `cb.conjunction()` — an always-true predicate. Spring Data also supports a `null` predicate as a condition that contributes nothing to composition, though using `cb.conjunction()` often makes intent clearer in code.

## 3. Enabling JpaSpecificationExecutor in the Repository

The repository must extend `JpaSpecificationExecutor<T>` alongside `JpaRepository<T, ID>`:

```java
package com.example.learning.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

`JpaSpecificationExecutor<Customer>` provides the main operations:

| Method | Result |
| --- | --- |
| `findAll(spec)` | List of entities matching the condition |
| `findAll(spec, sort)` | Sorted list of entities |
| `findAll(spec, pageable)` | `Page<T>` containing content and pagination metadata |
| `findOne(spec)` | `Optional<T>`; throws an error if more than one result exists |
| `count(spec)` | Total number of entities matching the condition |
| `exists(spec)` | Whether at least one entity matches the condition |

This is an executor for the repository's entity type `T`. If you need projections, special query shapes, or custom count optimizations, check the API of your Spring Data JPA version or add an appropriate custom repository.

## 4. Creating a Sample Entity and Filter

Simple entity for illustration:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "first_name", nullable = false)
    private String firstName;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private Boolean active;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CustomerStatus status;

    protected Customer() {
    }

    public Customer(String firstName, String email, Boolean active, CustomerStatus status) {
        this.firstName = firstName;
        this.email = email;
        this.active = active;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getFirstName() { return firstName; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
    public CustomerStatus getStatus() { return status; }
}
```

Enum:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW,
    ACTIVE,
    SUSPENDED
}
```

Request filter:

```java
package com.example.learning.customer;

public record CustomerFilter(
    String firstName,
    String email,
    Boolean active,
    CustomerStatus status
) {
}
```

`Boolean active` lets you distinguish an omitted filter (`null`) from requesting `active = true` or `active = false`. If business rules need to search for rows where the active column stores `NULL`, add a dedicated filter option; do not use the same `null` to mean both "skip filter" and "find NULL values".

## 5. Writing Small, Single-Responsibility Specifications

Create a class containing factory methods that return `Specification<Customer>`:

```java
package com.example.learning.customer;

import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {
    private CustomerSpecifications() {
    }

    public static Specification<Customer> firstNameContains(String value) {
        return (root, query, cb) -> {
            if (value == null || value.isBlank()) {
                return cb.conjunction();
            }
            String pattern = "%" + value.trim().toLowerCase(Locale.ROOT) + "%";
            return cb.like(cb.lower(root.get("firstName")), pattern);
        };
    }

    public static Specification<Customer> emailEqualsIgnoreCase(String value) {
        return (root, query, cb) -> {
            if (value == null || value.isBlank()) {
                return cb.conjunction();
            }
            return cb.equal(
                cb.lower(root.get("email")),
                value.trim().toLowerCase(Locale.ROOT)
            );
        };
    }

    public static Specification<Customer> activeEquals(Boolean value) {
        return (root, query, cb) -> {
            if (value == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("active"), value);
        };
    }

    public static Specification<Customer> hasStatus(CustomerStatus value) {
        return (root, query, cb) -> {
            if (value == null) {
                return cb.conjunction();
            }
            return cb.equal(root.get("status"), value);
        };
    }

    public static Specification<Customer> from(CustomerFilter filter) {
        return ((Specification<Customer>) (root, query, cb) -> cb.conjunction())
            .and(firstNameContains(filter.firstName()))
            .and(emailEqualsIgnoreCase(filter.email()))
            .and(activeEquals(filter.active()))
            .and(hasStatus(filter.status()));
    }
}
```

Each method has one responsibility:

- `firstNameContains` searches for names containing the entered substring, case-insensitively.
- `emailEqualsIgnoreCase` compares emails after lowercasing and trimming leading/trailing whitespace.
- `activeEquals` adds a predicate only when the caller sends true or false.
- `hasStatus` filters status only when a value is provided.
- `from` combines all conditions with `and`.

In this example, `cb.conjunction()` acts as a neutral condition: when a filter is absent, it excludes no records. Input values are still bound via the Criteria API; user input is never concatenated into SQL.

### 5.1. Filter Null Rules

"Do not filter by email" differs from "email in the database must be NULL". If `null` in the request means skipping the filter, use `cb.conjunction()` as above. If the API needs to find null emails, declare an explicit flag or filter mode and produce `cb.isNull(root.get("email"))`.

Similarly, `active = null` in the sample filter means not applying the active condition. It does not mean `active IS NULL`.

### 5.2. Escaping LIKE Characters for Literal Searches

In `LIKE`, `%` and `_` are wildcards. If users enter them expecting literal character matches, escape them according to your chosen escape character:

```java
private static String escapeLike(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
```

The predicate can use the `cb.like(expression, pattern, '\\')` overload to specify the escape character. Test escaping against your target database; if the business rule intends for `%` and `_` to act as wildcards, do not escape them.

## 6. Combining Specifications with and, or, and not

Each specification can be used standalone or composed with others:

```java
Specification<Customer> activeAndNamed =
    CustomerSpecifications.activeEquals(true)
        .and(CustomerSpecifications.firstNameContains("an"));

Specification<Customer> suspendedOrInactive =
    CustomerSpecifications.hasStatus(CustomerStatus.SUSPENDED)
        .or(CustomerSpecifications.activeEquals(false));

Specification<Customer> notSuspended =
    Specification.not(
        CustomerSpecifications.hasStatus(CustomerStatus.SUSPENDED)
    );
```

`and` and `or` can be combined into multi-level expressions. Use intermediate variables or explicit parentheses so readers understand the exact logical precedence. For example, `A.and(B).or(C)` equals `(A AND B) OR C`, not `A AND (B OR C)`.

A Specification should represent a reusable condition description. Avoid storing mutable state in a specification object or mutating shared variables across requests; factory methods that create predicates from input parameters are safer and easier to test.

## 7. Executing Specifications with Pagination and Sorting

The service can convert a request filter into a specification and call the repository:

```java
package com.example.learning.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerSearchService {
    private final CustomerRepository customers;

    public CustomerSearchService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Page<Customer> search(CustomerFilter filter, Pageable pageable) {
        return customers.findAll(CustomerSpecifications.from(filter), pageable);
    }
}
```

Caller example constructing a page request:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("lastName"), Sort.Order.asc("id"))
);
```

The sample entity above does not have `lastName`; therefore, when using that exact entity, sort by an existing property such as `Sort.by("firstName").and(Sort.by("id"))`. Sort properties must be valid Java entity properties, not SQL column names.

`Page<T>` provides the page content, `totalElements`, and `totalPages`. To compute the total element count, Spring Data typically runs an additional count query. For large tables or specifications with complex joins, counting can be expensive.

## 8. Association Joins and Duplicate Result Risks

A specification can join to a related entity. For example, suppose `Customer` has an `orders` collection and each order has a `status`:

```java
public static Specification<Customer> hasOrderWithStatus(OrderStatus status) {
    return (root, query, cb) -> {
        var orders = root.join("orders", JoinType.INNER);
        query.distinct(true);
        return cb.equal(orders.get("status"), status);
    };
}
```

This is an illustrative fragment assuming the entity has an `orders` association and an `OrderStatus` enum. When a customer has multiple matching orders, the join can produce multiple SQL rows for the same customer. `query.distinct(true)` requests non-duplicate entity results.

Setting `distinct` can affect how the database/provider generates the count query and how pagination is calculated. Test `content`, `totalElements`, and page counts with data containing multiple related records. In some cases, an `exists` subquery is better than a direct join because it checks existence without multiplying result rows.

Do not add a join merely because an association exists on the entity. Every join can increase cost, change cardinality, or complicate the count query.

## 9. Using Subqueries to Check Existence

For one-to-many relationships, `exists` can express "customer has at least one matching order" without returning order rows in the main query:

```java
public static Specification<Customer> hasPaidOrder() {
    return (root, query, cb) -> {
        var subquery = query.subquery(Long.class);
        var order = subquery.from(PurchaseOrder.class);

        subquery.select(order.get("id"));
        subquery.where(
            cb.equal(order.get("customer"), root),
            cb.equal(order.get("status"), OrderStatus.PAID)
        );

        return cb.exists(subquery);
    };
}
```

This snippet assumes `PurchaseOrder.customer` references `Customer` and `PurchaseOrder.status` has type `OrderStatus`. The `exists` predicate returns true when the subquery finds at least one paid order for the current customer.

Subqueries can help avoid duplicate root rows caused by joins, though they are not automatically faster on every database. Compare execution plans and foreign-key/status indexes on realistic data.

## 10. Keep Specifications Focused on Predicates

The `CriteriaQuery<?> query` parameter lets a specification affect the query structure. However, `JpaSpecificationExecutor` can reuse a specification for both the data retrieval query and the count query during pagination.

Consequently, a specification containing a `fetch join`, `orderBy`, `groupBy`, or altering the select list can cause issues when Spring Data reuses it for the count query. For example, a collection fetch join may be invalid in a count query or cause incorrect pagination results.

Practical design rules:

- Prefer returning predicates and keep specifications focused on filter conditions.
- Use `Pageable`/`Sort` to control pagination and ordering instead of setting `orderBy` inside the specification.
- Avoid putting collection fetch joins in specifications used for `Page<T>`.
- When associations must be loaded, consider `@EntityGraph`, projections, a separate query, or a custom repository.
- When you must use distinct/joins/subqueries, test both the content query and the count query.

In Spring Data JPA, `findAll(spec, pageable)` overloads can trigger a count query. Do not check only the content list and assume pagination is right; verify total counts and trailing pages as well.

## 11. Testing Specifications

The test below verifies composition and pagination through the repository. It assumes the project has the entity, enum, filter, specifications, and repository from the examples above, along with `spring-boot-starter-test`, `spring-boot-starter-data-jpa`, and a test database such as H2.

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerSpecificationTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void combinesOptionalFiltersAndPaginatesResults() {
        customers.saveAll(List.of(
            new Customer("An", "an@example.test", true, CustomerStatus.ACTIVE),
            new Customer("Lan", "lan@example.test", false, CustomerStatus.NEW),
            new Customer("Binh", "binh@example.test", true, CustomerStatus.SUSPENDED)
        ));
        customers.flush();

        CustomerFilter filter = new CustomerFilter("an", null, true, null);
        Page<Customer> page = customers.findAll(
            CustomerSpecifications.from(filter),
            PageRequest.of(0, 10, Sort.by("id").ascending())
        );

        assertThat(page.getContent())
            .extracting(Customer::getFirstName)
            .containsExactly("An");
        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getTotalPages()).isEqualTo(1);
    }
}
```

The test saves three customers: `An` and `Binh` are active, `Lan` is inactive. The filter asks for names containing `an` and `active = true`; only `An` satisfies both conditions. `flush()` forces data to be sent to the database before the repository runs the query.

This test checks basic predicates, composition, and pagination metadata. For specifications with joins, subqueries, or distinct, add fixtures with multiple orders per customer and verify there are no duplicates and that `totalElements` is accurate.

## 12. Static Metamodel and Refactoring Safety

In the examples above, `root.get("firstName")` uses a String property name. This is easy to read, but the compiler will not catch errors if a property is renamed.

The JPA static metamodel allows typed attribute references, for example:

```java
root.get(Customer_.firstName)
```

`Customer_` is a metamodel class generated by an annotation processor compatible with the JPA provider. When a project configures a metamodel generator, the IDE/compiler can detect property name errors earlier. If no generator is configured, use string paths carefully and ensure tests cover the specifications.

Static metamodels are helpful in codebases with many specifications or frequently refactored entities. There is no need to add them solely for a few simple predicates if setup overhead outweighs the benefit.

## 13. Common Pitfalls

- **Confusing a Specification with an executed query.** A Specification only builds a predicate; the executor sends the query to the database.
- **Forgetting to have the repository extend `JpaSpecificationExecutor<T>`.** Without this interface, `findAll(spec, pageable)` is unavailable.
- **Using request `null` to mean both "skip filter" and "find NULL column".** These two meanings must be represented separately.
- **Concatenating conditions as SQL strings.** Use CriteriaBuilder to create predicates and bind values safely.
- **Misunderstanding `and`/`or` precedence.** `A.and(B).or(C)` is `(A AND B) OR C`; use intermediate variables or clear parentheses.
- **Joining collections without handling duplicates.** Check `distinct`, cardinality, and the count query.
- **Putting fetch joins inside paginated specifications.** Count queries may fail or return inaccurate results; consider EntityGraph or separate queries.
- **Putting sorting inside specifications.** Use `Sort`/`Pageable` to keep predicates independent of display ordering.
- **Testing only content and ignoring totalElements.** Joins and distinct can distort counts.
- **Using the wrong property path name.** JPQL/Criteria uses Java property names; static metamodels make refactoring safer.
- **Creating one giant specification containing every condition.** Split into small factory methods for reuse and testing.

## 14. Workflow for Building Dynamic Filters

1. Identify which fields are optional and the exact meaning of null/empty values.
2. Create one `Specification<T>` factory method for each independent condition.
3. Use `CriteriaBuilder` to build predicates; never concatenate SQL from input.
4. Combine conditions with `and`, `or`, `not` according to business logic.
5. Have the repository extend `JpaSpecificationExecutor<T>` and call the appropriate overload.
6. Use `Pageable`/`Sort` for pagination and ordering.
7. If joins, subqueries, or distinct are used, verify both content and count queries.
8. Test no-filter, single-filter, multi-filter, null, empty-result, and multi-child relationship cases.
9. Inspect SQL/execution plans and add indexes when bottlenecks are evidenced.

## Conclusion

`Specification<T>` is a contract describing a predicate via `Root`, `CriteriaQuery`, and `CriteriaBuilder`; it does not execute queries itself. `JpaSpecificationExecutor<T>` provides `findAll`, `findOne`, `count`, `exists`, and pagination methods to run specifications. Write small conditions, compose them clearly, define null-filter semantics explicitly, keep specifications focused on predicates, and test both data and count queries when joins are involved. This structure keeps dynamic filters reusable, extensible, and well-controlled.
