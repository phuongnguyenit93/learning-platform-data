# Handling Null, Boolean, In, and NotIn in Spring Data JPA

## Objectives

After this lesson, you will be able to write derived queries to find `NULL` values, filter boolean properties, and match a set of values using `In`/`NotIn`; explain why SQL handles `NULL` differently from ordinary values; identify pitfalls when collections contain `null` or are empty; and test repositories to verify results.

The examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). Entities and repositories belong to a Spring Boot application with `spring-boot-starter-data-jpa`, a `DataSource`, and a JDBC driver. Integration tests require `spring-boot-starter-test` with a test database such as H2.

## 1. SQL NULL and three-valued logic

In Java, `null` represents the absence of a reference value. In SQL, `NULL` represents an unknown or missing value. Therefore, you cannot compare `NULL` using `=` or `<>` like an ordinary value.

```sql
SELECT * FROM customers WHERE email = NULL;
```

The condition `email = NULL` evaluates to `UNKNOWN`, not `TRUE`. In a `WHERE` clause, only rows where the condition evaluates to `TRUE` are kept; both `FALSE` and `UNKNOWN` are filtered out. SQL therefore uses three-valued logic:

| Expression | Result |
| --- | --- |
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> 'a@example.test'` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `'a@example.test' IS NULL` | `FALSE` |
| `NULL IS NOT NULL` | `FALSE` |

To find missing values, use `IS NULL`; to find present values, use `IS NOT NULL`:

```sql
SELECT * FROM customers WHERE email IS NULL;
SELECT * FROM customers WHERE email IS NOT NULL;
```

This rule also affects booleans, `IN`, `NOT IN`, and combined conditions. Understanding `UNKNOWN` helps prevent queries from returning fewer rows than expected.

## 2. Derived queries with IsNull and IsNotNull

Spring Data JPA parses repository method names and builds queries based on entity properties. Keywords for null checks include:

- `IsNull` or `Null`: `IS NULL` condition.
- `IsNotNull` or `NotNull`: `IS NOT NULL` condition.

Example `CustomerRepository.java`:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByEmailIsNull();

    List<Customer> findByEmailIsNotNull();
}
```

These two methods correspond to SQL conditions `email IS NULL` and `email IS NOT NULL`. No `null` argument needs to be passed; the method name clearly states the query intent.

### 2.1. Null is not an empty string

`NULL`, the empty string `''`, and a whitespace-only string `'   '` are distinct values:

- `email IS NULL`: the column has no value.
- `email = ''`: the column holds an empty string.
- `TRIM(email) = ''`: after removing whitespace, no characters remain.

JPA does not automatically treat empty or whitespace strings as `NULL`. If business rules consider them the same state, normalize input data or write queries that explicitly express the policy.

```java
@Query("select c from Customer c where c.email = ''")
List<Customer> findWithEmptyEmail();
```

This is JPQL for finding empty strings. If whitespace needs to be handled, consider `trim(c.email) = ''`; test this on the target database and provider.

### 2.2. Combining null conditions

Keywords can be combined with `And` and `Or`:

```java
List<Customer> findByEmailIsNotNullAndActiveTrue();
List<Customer> findByEmailIsNullOrActiveFalse();
```

The first method finds customers who have an email and are active. The second method finds customers missing an email or having `active = false`. When logic has multiple branches, use `@Query` or `Specification` if the method name becomes hard to read or cannot express logical grouping.

## 3. Boolean: True, False, and unknown values

Spring Data JPA supports `True`/`IsTrue` and `False`/`IsFalse` keywords:

```java
List<Customer> findByActiveTrue();
List<Customer> findByActiveFalse();
```

Their meanings correspond to `active = TRUE` and `active = FALSE`. SQL `NULL` is not treated as `false`; if a boolean property can be missing, that state must be queried separately.

### 3.1. boolean or Boolean?

| Java type | Possible values | When appropriate |
| --- | --- | --- |
| `boolean` | `true`, `false` | State is always known |
| `Boolean` | `true`, `false`, `null` | Business domain has an unknown/unset state |

Example entity with a three-valued state:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
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

    @Column
    private String email;

    @Column
    private Boolean active;

    protected Customer() {
    }

    public Customer(String email, Boolean active) {
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
}
```

Repository:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByActiveTrue();
    List<Customer> findByActiveFalse();
    List<Customer> findByActiveIsNull();
    List<Customer> findByActiveIsNotNull();
}
```

With `Boolean active`, the methods above respectively match `true`, `false`, `NULL`, and non-null values. `findByActiveFalse()` does not include rows where `active IS NULL`.

If the state is always required, use `boolean` and declare the column `NOT NULL` in the schema, such as `@Column(nullable = false)`. If you need to distinguish “undetermined” from “disabled”, use `Boolean` and clearly define the meaning of all three states. Do not use `null` instead of `false` merely to avoid making a business decision.

### 3.2. Property names must match the entity

Spring Data parses persistent property names. For a field `active`, the getter may be `getActive()` for `Boolean` or `isActive()` for `boolean`; the JavaBeans property name is still `active`, so the repository uses `findByActiveTrue()`.

If an entity names a field `isActive`, check the actual property name rather than inferring it from the getter name. The cleanest approach is to name the property `active` and follow JavaBeans conventions.

## 4. IN: finding values within a set

`In` creates a condition checking whether a property belongs to a supplied set of values. The parameter can be a `Collection`, `List`, array, or varargs; the example uses `Collection`:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);
}
```

Enum mapped as a string:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW, ACTIVE, SUSPENDED, CLOSED
}
```

In the entity, declare:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status")
private CustomerStatus status;
```

Calling the repository:

```java
List<Customer> result = repository.findByStatusIn(
    List.of(CustomerStatus.NEW, CustomerStatus.ACTIVE)
);
```

Equivalent SQL meaning:

```sql
SELECT * FROM customers WHERE status IN ('NEW', 'ACTIVE');
```

Parameters are bound separately; input strings are not concatenated into SQL. This ensures the database handles data types properly and prevents SQL injection from manual string building.

### 4.1. Combining In with other conditions

```java
List<Customer> findByStatusInAndActiveTrue(
    Collection<CustomerStatus> statuses
);

List<Customer> findByStatusInAndEmailIsNotNull(
    Collection<CustomerStatus> statuses
);
```

The first method finds customers in one of the given statuses who are also active. The second method retrieves only customers who have an email.

### 4.2. In with null columns

If `status` is `NULL`, the expression `status IN ('NEW', 'ACTIVE')` evaluates to `UNKNOWN`, so that row is not returned. If you want to include rows with null status, express that condition separately:

```java
List<Customer> findByStatusInOrStatusIsNull(
    Collection<CustomerStatus> statuses
);
```

This means `status IN (...) OR status IS NULL`. Before calling, still decide clearly how to handle empty collections and null elements.

## 5. NOT IN: excluding a set of values

`NotIn` returns rows whose property is not in the supplied set:

```java
List<Customer> findByStatusNotIn(
    Collection<CustomerStatus> excludedStatuses
);
```

SQL looks like:

```sql
SELECT * FROM customers WHERE status NOT IN ('CLOSED', 'SUSPENDED');
```

Key point to remember: `NOT IN` keeps only rows where the expression evaluates to `TRUE`. Rows with `status IS NULL` evaluate to `UNKNOWN` and are excluded. Therefore, `findByStatusNotIn(...)` excludes entities with null status by default.

If you want to exclude a set while still including null status, declare a dedicated method:

```java
List<Customer> findByStatusNotInOrStatusIsNull(
    Collection<CustomerStatus> excludedStatuses
);
```

This represents `status NOT IN (...) OR status IS NULL`. Use this only when null should be a valid result group according to business requirements.

## 6. Pitfall: null elements inside a NOT IN collection

Suppose the argument is `('CLOSED', NULL)`:

```sql
status NOT IN ('CLOSED', NULL)
```

For a row with `status = 'ACTIVE'`, the comparison is equivalent to:

```sql
status <> 'CLOSED' AND status <> NULL
```

The left side is `TRUE`, the right side is `UNKNOWN`; `TRUE AND UNKNOWN` evaluates to `UNKNOWN`. That row is excluded. A single null element in the list can cause `NOT IN` to return far fewer rows than expected, or even no rows at all.

With `IN`, a null element also does not automatically match null values in the column. For example, `status IN ('NEW', NULL)` only reliably matches `'NEW'` rows; rows not matching any non-null value evaluate to `UNKNOWN`.

Practical rules:

- Do not pass `null` elements in a collection used for `In`/`NotIn`, unless handling is explicitly defined.
- If you need to match null columns, use `IsNull` or add an `Or...IsNull` branch.
- For `NotIn`, validate and reject or filter out null elements before calling the repository.
- For `NOT IN (subquery)`, ensure the subquery cannot return null; if not guaranteed, consider `NOT EXISTS`.

## 7. Empty collections and null collections

A null collection and an empty collection are two different scenarios. Null usually means the caller did not supply a set; an empty collection means the set has zero elements.

Under set logic, `x IN empty` matches no rows, while `x NOT IN empty` excludes no values. However, SQL does not have a uniform `IN ()` representation across all databases; exact behavior also depends on the provider. Handle empty collections in the service layer before calling the repository.

Example service applying an explicit policy:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CustomerSearchService {
    private final CustomerRepository customers;

    public CustomerSearchService(CustomerRepository customers) {
        this.customers = customers;
    }

    public List<Customer> findWithStatuses(
            Collection<CustomerStatus> statuses) {
        requireCollection(statuses, "statuses");
        if (statuses.isEmpty()) return List.of();
        rejectNullElements(statuses, "statuses");
        return customers.findByStatusIn(statuses);
    }

    public List<Customer> findOutsideStatuses(
            Collection<CustomerStatus> excludedStatuses) {
        requireCollection(excludedStatuses, "excludedStatuses");
        if (excludedStatuses.isEmpty()) return customers.findAll();
        rejectNullElements(excludedStatuses, "excludedStatuses");
        return customers.findByStatusNotIn(excludedStatuses);
    }

    private static void requireCollection(
            Collection<?> values, String name) {
        if (values == null) {
            throw new IllegalArgumentException(name + " must not be null");
        }
    }

    private static void rejectNullElements(
            Collection<?> values, String name) {
        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                name + " must not contain null elements"
            );
        }
    }
}
```

In this example, the service chooses two concrete rules: an empty search set returns an empty list; an empty exclusion set means exclude no statuses, so it returns all customers. `findOutsideStatuses` uses `findByStatusNotIn`, so entities with `status IS NULL` are still excluded. If business logic requires including nulls, use `findByStatusNotInOrStatusIsNull`.

Do not apply this policy mechanically to every API. For one endpoint, an empty collection might mean “no filter”; for another, it might mean “no results”. Define the input contract clearly.

## 8. Complete entity and repository for the example

`Customer.java`:

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

    @Column
    private String email;

    @Column
    private Boolean active;

    @Enumerated(EnumType.STRING)
    @Column
    private CustomerStatus status;

    protected Customer() {
    }

    public Customer(String email, Boolean active, CustomerStatus status) {
        this.email = email;
        this.active = active;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public Boolean getActive() { return active; }
    public CustomerStatus getStatus() { return status; }
}
```

`CustomerStatus.java`:

```java
package com.example.learning.customer;

public enum CustomerStatus {
    NEW, ACTIVE, SUSPENDED, CLOSED
}
```

`CustomerRepository.java`:

```java
package com.example.learning.customer;

import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByEmailIsNull();
    List<Customer> findByEmailIsNotNull();
    List<Customer> findByActiveTrue();
    List<Customer> findByActiveFalse();
    List<Customer> findByActiveIsNull();
    List<Customer> findByActiveIsNotNull();
    List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);
    List<Customer> findByStatusNotIn(Collection<CustomerStatus> statuses);
    List<Customer> findByStatusNotInOrStatusIsNull(
        Collection<CustomerStatus> statuses
    );
}
```

These files share the same package. If your project already has a corresponding entity or enum, add the appropriate methods to the existing repository using the exact property names in your entity; do not create duplicate classes.

## 9. Integration test for null, boolean, In, and NotIn

The test below saves four customers representing different states and queries them via the repository. `@DataJpaTest` configures the persistence slice, runs tests in a transaction, and typically rolls back data after each test.

`CustomerRepositoryQueryTest.java`:

```java
package com.example.learning.customer;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerRepositoryQueryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void handlesNullBooleanInAndNotIn() {
        customers.saveAll(List.of(
            new Customer(null, true, CustomerStatus.NEW),
            new Customer("paid@example.test", false, CustomerStatus.ACTIVE),
            new Customer("suspended@example.test", null, CustomerStatus.SUSPENDED),
            new Customer("unknown@example.test", true, null)
        ));
        customers.flush();

        assertThat(customers.findByEmailIsNull()).hasSize(1);
        assertThat(customers.findByEmailIsNotNull()).hasSize(3);
        assertThat(customers.findByActiveTrue()).hasSize(2);
        assertThat(customers.findByActiveFalse()).hasSize(1);
        assertThat(customers.findByActiveIsNull()).hasSize(1);

        assertThat(customers.findByStatusIn(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(2);

        assertThat(customers.findByStatusNotIn(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(1);

        assertThat(customers.findByStatusNotInOrStatusIsNull(
            List.of(CustomerStatus.NEW, CustomerStatus.SUSPENDED)
        )).hasSize(2);
    }
}
```

The test assumes the project has `spring-boot-starter-data-jpa`, `spring-boot-starter-test`, and H2 in test runtime, along with test database configuration. The fixture includes one null email, one null Boolean, and one null status.

Expected results:

| Query | Row count | Explanation |
| --- | ---: | --- |
| `findByEmailIsNull()` | 1 | Customer without an email |
| `findByEmailIsNotNull()` | 3 | Three customers with an email |
| `findByActiveTrue()` | 2 | Two customers with active true |
| `findByActiveFalse()` | 1 | One customer with active false |
| `findByActiveIsNull()` | 1 | One customer without an active state |
| `findByStatusIn(NEW, SUSPENDED)` | 2 | Two statuses inside the search set |
| `findByStatusNotIn(NEW, SUSPENDED)` | 1 | Only ACTIVE; null status is excluded |
| `findByStatusNotInOrStatusIsNull(NEW, SUSPENDED)` | 2 | ACTIVE and null status |

Run the test with Maven Wrapper:

```bash
./mvnw -Dtest=CustomerRepositoryQueryTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=CustomerRepositoryQueryTest test
```

The test must run in a project with proper dependencies and configuration. Do not copy the test class alone into a plain Java project, because `@DataJpaTest`, the Spring context, and repository proxies require a Spring Boot environment.

## 10. When should you use @Query?

Derived queries work well for simple conditions. When logic has multiple branches, optional parameters, or requires `NOT EXISTS`, `@Query` can express it more clearly.

JPQL example including null status when excluding a set:

```java
@Query("""
    select c
    from Customer c
    where c.status not in :excluded
       or c.status is null
    """)
List<Customer> findOutsideStatusesIncludingNull(
    @Param("excluded") Collection<CustomerStatus> excluded
);
```

This snippet uses a Java text block and JPQL. For empty collections, still handle them in the service before calling. If many filters can be toggled per request, consider `Specification` to add predicates conditionally instead of writing a long `(:param is null OR ...)` clause.

In native SQL, `:param is null` can run into parameter type inference issues on some databases/drivers. Test against a real database and avoid using ambiguous null parameters to mean “skip filter”.

## 11. Performance and limits of IN/NOT IN

For small lists, `IN` is usually a natural way to filter by a set. When the list is very large, each element can become a bind parameter and cause issues:

- Databases have limits on bind parameter counts or statement sizes.
- Long SQL statements increase parsing and data transfer overhead.
- The optimizer may choose a poor execution plan when the value set is large or selectivity fluctuates heavily.
- `NOT IN` can be difficult to optimize if the exclusion set is large or comes from a subquery.

For large lists, consider controlled batching, temporary tables, staging tables, table-valued parameters (if supported by the database), joining with a table containing the value set, or another search strategy. If merging results from multiple batches, handle pagination, deduplication, and ordering carefully.

Indexes on filtered columns can help `IN`, `NOT IN`, `IS NULL`, or `IS NOT NULL`, though effectiveness depends on the database, null ratio, selectivity, and other conditions. Boolean columns usually have few distinct values so a standalone index may not be useful; a composite index with more selective columns may be appropriate. Inspect the execution plan before adding indexes.

## 12. Common mistakes

- **Using `= NULL` or `<> NULL`.** Use `IS NULL`/`IS NOT NULL` because comparing with NULL produces UNKNOWN.
- **Treating null as false.** `Boolean` has three states; `findByActiveFalse()` does not return rows where active is null.
- **Using primitive boolean when business logic needs an undetermined state.** Primitives only have true/false; use `Boolean` if null is a valid state.
- **Using `NotIn` with a collection containing null.** A single null element can turn the NOT IN condition into UNKNOWN and exclude desired rows.
- **Assuming `NotIn` includes null columns.** `NULL NOT IN (...)` is UNKNOWN; add `OrStatusIsNull` if needed.
- **Passing empty collections directly to the repository.** Handle them in the service according to business contracts to avoid SQL/provider dependencies.
- **Treating a null collection the same as an empty collection.** The two inputs can carry different meanings; validate and decide explicitly.
- **Using `In` to find null values in a column.** Use `IsNull` or add an `Or...IsNull` branch.
- **Concatenating values into SQL strings.** Use derived queries or parameter binding.
- **Using a very large IN list without measuring.** Check parameter limits, execution plans, and consider temporary tables or joins.

## 13. Pre-deployment checklist for queries

- [ ] Can the property be null or is it always required? Are the Java mapping and database constraint consistent?
- [ ] Do you need to match null, empty strings, or whitespace-only strings?
- [ ] For Boolean, does null carry a distinct business meaning?
- [ ] Do `In`/`NotIn` receive non-null collections without null elements?
- [ ] Do empty collections have a clear contract in the service layer?
- [ ] Does `NotIn` need to include rows whose property is null?
- [ ] Do tests cover true, false, null, non-empty sets, and empty collections?
- [ ] Have queries with large lists been measured against a real database?
- [ ] Does SQL use bound parameters, and have indexes been verified with an execution plan?

## Conclusion

In Spring Data JPA, use `IsNull`/`IsNotNull` to explicitly express missing-value checks; use `True`/`False` for boolean properties; and use `In`/`NotIn` for sets of values. SQL uses three-valued logic, so `NULL` does not automatically match `IN` and is normally excluded from `NOT IN`. Validate null collections, empty collections, and null elements in the service layer, write methods that make the null policy explicit, and test against your database to ensure results match business requirements.