# Designing Base Interfaces with @NoRepositoryBean

## 1. Why do we need a base repository interface?

In a Spring Data JDBC application, each aggregate typically has its own repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

As the number of aggregates grows, multiple repositories may repeat shared operations: finding a record that must exist, checking an ID, or project-standardized utility methods. We can declare a **base repository interface** containing the shared contract, and have concrete repositories extend it.

The issue is that Spring Data automatically detects repository interfaces within the scan scope and creates implementations/proxies for eligible interfaces. A base interface with generic types like `T` and `ID` does not yet represent a concrete aggregate. We do not want the framework to create a standalone repository bean for that intermediate interface.

The `@NoRepositoryBean` annotation solves this exact scenario: it marks a repository interface as a **base interface, without creating a repository bean directly for that interface itself**. Concrete repositories extending it are still discovered and turned into beans normally.

In this lesson, we will:

- Understand repository scanning and why `@NoRepositoryBean` is needed.
- Design a shared generic base interface for Spring Data JDBC.
- Extend the base interface from concrete repositories for each aggregate.
- Distinguish default methods, derived queries, `@Query`, and repository fragments.
- Recognize common mistakes when placing the annotation incorrectly or declaring unimplemented methods.

## 2. What does `@NoRepositoryBean` do?

`@NoRepositoryBean` belongs to package:

```java
import org.springframework.data.repository.NoRepositoryBean;
```

It is placed on a repository interface to inform Spring Data:

> This interface is part of a repository inheritance hierarchy. Do not create a separate repository bean for this interface.

Example:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`BaseRepository` is generic. There is no concrete aggregate type yet for Spring Data JDBC to map to a table. We only use it as a parent for repositories with concrete types:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {
}
```

At this point Spring Data knows the concrete repository manages `Customer` with ID type `UUID`. It creates a bean for `CustomerRepository`, while `BaseRepository` only provides the inherited contract.

### What does this annotation NOT mean?

`@NoRepositoryBean`:

- Does not disable repository scanning for the entire package.
- Does not disable repositories for child interfaces.
- Does not automatically generate implementations for custom abstract methods.
- Does not replace `@Repository` on a hand-written DAO.
- Does not generate SQL, change aggregate mapping, or alter transactions.
- Is not an annotation marking an entity or aggregate root.

It solely controls whether Spring Data creates a repository instance for **the annotated interface itself**.

## 3. Why must generic interfaces be excluded from repository instantiation?

Spring Data JDBC creates repositories based on the domain type and ID type it resolves from the interface. For a concrete repository:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

The framework can determine:

```text
Domain type = Customer
ID type     = UUID
```

But for a base interface:

```java
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`T` and `ID` are not yet bound to a concrete aggregate. This interface is not a repository the application should inject to manipulate data. If Spring Data tries to instantiate a repository for it, the framework lacks a suitable concrete domain type to construct the repository.

`@NoRepositoryBean` excludes that intermediate interface from bean creation while preserving the generic relationship so child interfaces inherit its methods.

### Inheritance structure

```text
                 CrudRepository<T, ID>
                           |
                           v
             @NoRepositoryBean
                 BaseRepository<T, ID>
                    /          \
                   /            \
                  v              v
       CustomerRepository   PurchaseOrderRepository
          <Customer, UUID>       <PurchaseOrder, Long>
                  |              |
                  v              v
          Repository bean  Repository bean
```

Only the two concrete interfaces below receive repository beans. The base interface serves as a shared contract.

## 4. Designing a minimal base repository

With Spring Data JDBC, you can start from `CrudRepository<T, ID>`:

```java
package com.example.shared;

import java.util.NoSuchElementException;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    default T getRequiredById(ID id) {
        return findById(id)
                .orElseThrow(() -> new NoSuchElementException(
                        "Entity not found: " + id));
    }
}
```

Explanation:

1. `T` is the aggregate type managed by the concrete repository.
2. `ID` is the corresponding primary key type; it can be `Long`, `UUID`, or another ID type.
3. `extends CrudRepository<T, ID>` inherits standard CRUD operations.
4. `@NoRepositoryBean` prevents Spring Data from creating a bean for `BaseRepository` itself.
5. `getRequiredById` is a Java default method. It calls the inherited `findById` and turns `Optional.empty()` into an exception when not found.

Default methods fit genuinely shared utility logic that can be implemented purely using existing repository methods. Avoid piling unrelated methods into the base interface just to group operations that happen to share similar names.

### Why use a default method?

If you declare:

```java
T getRequiredById(ID id);
```

that is an abstract method. Spring Data may treat it as a query method and try to derive a query or require an implementation. It will not automatically know that you intend to call `findById` and throw an exception.

With `default`, the method body is already provided in the Java interface, so no separate query implementation is needed.

If shared logic is complex, depends on multiple repositories, or involves business rules, consider placing it in an application service or domain service rather than turning the base repository into a catch-all service layer.

## 5. Concrete repositories extending the base interface

Suppose we have a `Customer` aggregate:

```java
package com.example.customer;

import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id UUID id,
        String name,
        String email
) {
}
```

Concrete repository:

```java
package com.example.customer;

import java.util.Optional;
import java.util.UUID;

import com.example.shared.BaseRepository;

public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {

    Optional<Customer> findByEmail(String email);
}
```

`CustomerRepository` inherits:

- `save(Customer)`.
- `findById(UUID)`.
- `findAll()`.
- `existsById(UUID)`.
- `deleteById(UUID)`.
- `getRequiredById(UUID)` provided by the base interface.
- `findByEmail(String)` derived by Spring Data JDBC from the method name.

Another aggregate with a `Long` ID:

```java
package com.example.orders;

import com.example.shared.BaseRepository;

public interface PurchaseOrderRepository
        extends BaseRepository<PurchaseOrder, Long> {
}
```

Both repositories share the common contract, while their domain types and ID types remain specified on the child interfaces.

## 6. Which repositories does Spring Data JDBC create beans for?

In a standard Spring Boot setup, repository scanning starts from the application class's package and its subpackages, or from scopes explicitly specified via repository configuration. Spring Data finds matching repository interfaces.

With the structure:

```text
com.example
├── Application.java
├── shared
│   └── BaseRepository.java
├── customer
│   ├── Customer.java
│   └── CustomerRepository.java
└── orders
    ├── PurchaseOrder.java
    └── PurchaseOrderRepository.java
```

`Application` can live in `com.example` so default component and repository scanning cover subpackages. `BaseRepository` is recognized as a repository interface but is not instantiated as a bean due to `@NoRepositoryBean`. The two concrete interfaces are registered.

Example usage in a service:

```java
package com.example.customer;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Customer get(UUID id) {
        return customers.getRequiredById(id);
    }
}
```

The application injects `CustomerRepository`. Do not inject `BaseRepository<Customer, UUID>` as a standalone bean unless you have manually designed a different bean/implementation; a base interface annotated with `@NoRepositoryBean` is not a bean created by Spring Data.

## 7. Can many shared methods be placed in a base interface?

Yes, though you need to distinguish between method kinds.

### 7.1. Inherited CRUD methods

These are methods from `CrudRepository`. Spring Data already provides implementations:

```java
save(entity);
findById(id);
findAll();
deleteById(id);
existsById(id);
```

There is no need to redeclare them in the base interface unless changing the contract.

### 7.2. Java default methods

Suitable for simple logic built on top of existing repository methods:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    default boolean isMissing(ID id) {
        return !existsById(id);
    }
}
```

This is ordinary Java code. It does not require Spring Data to derive a new SQL statement.

However, avoid using `existsById` followed by `save` to decide a concurrent write operation. Another transaction can interleave between those two operations; database constraints or an appropriate atomic SQL statement are the reliable protection mechanism.

### 7.3. Derived query methods

Methods declared following naming conventions, for example:

```java
Optional<Customer> findByEmail(String email);
```

Spring Data JDBC can parse the method name to generate the corresponding query if it falls within supported query derivation features. This method belongs on the concrete repository because the email predicate is tied to the `Customer` model—not every aggregate has an email.

Do not place `findByEmail` in a generic base interface merely because several tables happen to have similarly named columns; the field name and domain meaning must genuinely apply to all types `T`.

### 7.4. Methods with `@Query`

If a specialized SQL query only applies to one aggregate, put it on the concrete repository:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {

    @Query("SELECT * FROM customers WHERE email = :email")
    Optional<Customer> lookupByEmail(String email);
}
```

This example illustrates a static query. Parameter binding syntax, column names, and result mapping must match Spring Data JDBC and the database in use. Do not move a SQL statement tied to the `customers` table up into a generic base interface.

## 8. When custom implementation is needed: repository fragments

`@NoRepositoryBean` does not generate implementations for custom abstract methods. If an operation requires custom code, Spring Data supports the repository fragment model.

For example, suppose we want to add a custom customer operation:

### 8.1. Declare the fragment interface

```java
package com.example.customer;

public interface CustomerSearch {
    long countWithEmailDomain(String domain);
}
```

### 8.2. Write the implementation

```java
package com.example.customer;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

public class CustomerSearchImpl implements CustomerSearch {

    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public long countWithEmailDomain(String domain) {
        String sql = """
                SELECT COUNT(*)
                FROM customers
                WHERE email LIKE ?
                """;

        Long count = jdbcTemplate.queryForObject(
                sql,
                Long.class,
                "%@" + domain
        );
        return count == null ? 0 : count;
    }
}
```

The implementation name follows the fragment convention `CustomerSearchImpl`. Depending on the repository implementation postfix configuration and module structure, ensure Spring Data can locate the fragment implementation. Here the fragment merely illustrates the idea; real projects should check naming/configuration for their Spring Data version.

### 8.3. Combine the fragment into the repository

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID>, CustomerSearch {
}
```

`CustomerRepository` combines:

- Shared CRUD from `BaseRepository`.
- Custom search behavior from `CustomerSearch`.
- Customer-specific query methods or `@Query` if needed.

Do not put implementations that depend on `JdbcTemplate` inside the base interface. The base interface should hold the shared contract; specialized implementations belong in fragments or separate adapters.

## 9. Distinguishing base repository interface vs custom repository base class

These two mechanisms sound similar but solve different problems:

| Mechanism | Role | Usage |
| --- | --- | --- |
| `@NoRepositoryBean` + generic interface | Share contracts and default methods across repositories | Concrete repository extends the generic interface |
| Repository fragment | Add custom implementations for a repository or group of repositories | Concrete repository extends the fragment interface and Spring composes the implementation |
| Custom repository base class | Replace the underlying base implementation class Spring Data uses for repository proxies | Configure repository factory/base class via the appropriate extension point |

`@NoRepositoryBean` does not turn an interface into a custom base class. Nor does it let you override the entire way Spring Data executes `save` or `findById`. If the goal is to alter the algorithm of core repository methods, study custom repository base classes and corresponding factory configuration; that is a different topic from creating a generic base interface.

## 10. Design principles so the base interface does not become a “God Repository”

An oversized base interface can force every repository to carry methods inappropriate for its aggregate. For example:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    Optional<T> findByEmail(String email);
    List<T> findByStatus(String status);
    BigDecimal calculateRevenue();
    void archiveAll();
}
```

These methods cannot share a consistent meaning across every type `T`:

- Not every aggregate has an email.
- Not every aggregate has a status.
- Calculating revenue is not a universal responsibility of every repository.
- Bulk archiving may violate aggregate and transaction rules.

Practical principles:

1. Include in the base interface only operations that genuinely make sense for every participating aggregate.
2. Prefer short, clear default methods built from the existing CRUD contract.
3. Queries on entity-specific properties belong on concrete repositories.
4. Complex SQL queries or specialized operations should use `@Query`, fragments, or dedicated adapters.
5. Do not turn repositories into application services; a repository should not orchestrate multiple aggregates and external systems.
6. Do not add methods just to save a few lines of declaration if they make the API harder to understand.

A good base interface reduces duplication without obscuring each aggregate's distinct responsibilities.

## 11. Common errors when using @NoRepositoryBean

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Application tries to create a repository for a generic interface | Forgot `@NoRepositoryBean` on the base interface | Add the annotation from the right package to the intermediate interface. |
| Cannot inject concrete repository | Child interface is outside repository scan scope or generic types are not properly declared | Check package scan and explicitly declare `BaseRepository<Customer, UUID>`. |
| Custom method has no implementation | Declared an abstract method in the base interface that is neither a valid query method nor a fragment | Use a default method, query method, `@Query`, or fragment implementation. |
| All repositories expose unrelated methods | Placed an aggregate-specific query onto the base interface | Move the method to the concrete repository. |
| Wrong `NoRepositoryBean` import | Used wrong package or another annotation with a similar name | Use `org.springframework.data.repository.NoRepositoryBean`. |
| Thinking the annotation stops child repositories from being created | Interpreting the annotation as disabling scanning entirely | Only the annotated interface gets no bean of its own; child repositories are still registered. |
| Thinking a base interface can alter core SQL | Confusing an interface with a custom base implementation class | Use a repository fragment or custom base class as needed. |
| Generic types are lost | Child repository extends raw type or leaves generics unspecified | Always pass concrete domain type and ID type on child repositories. |

When application startup fails, check which interface Spring Data is attempting to instantiate a repository for. If it is the generic base interface, check `@NoRepositoryBean`; if it is a concrete repository, verify the domain class has valid mapping and the generic types are clearly resolved.

## 12. Practice exercises

**Exercise 1 — Create a base interface.** Create `BaseRepository<T, ID>` extending `CrudRepository<T, ID>` and annotated with `@NoRepositoryBean`. Add a default method `getRequiredById`.

**Exercise 2 — Two concrete repositories.** Create `CustomerRepository extends BaseRepository<Customer, UUID>` and `PurchaseOrderRepository extends BaseRepository<PurchaseOrder, Long>`. Inject each repository into a service and call the shared method.

**Exercise 3 — Intentionally omit the annotation.** Temporarily remove `@NoRepositoryBean` and start the application. Observe how Spring Data handles the generic interface in your project version. Restore the annotation and compare.

**Exercise 4 — Separate specific queries.** Place `findByEmail` on `CustomerRepository`. Explain why this method does not belong in `BaseRepository`.

**Exercise 5 — Default method vs abstract method.** Declare a utility method as abstract, then convert it to a default method calling `findById`. Compare repository startup behavior and explain the difference between a Java implementation and query derivation.

**Exercise 6 — Repository fragment.** Create a fragment interface for a Customer-specific statistics query, write an implementation using `JdbcTemplate`, and compose it into `CustomerRepository`. Observe how Spring combines the fragment with the CRUD repository.

**Exercise 7 — Responsibility boundaries.** Pick an operation currently in a base repository that only makes sense for one aggregate. Move it to the concrete repository or application service and explain why the API becomes clearer.

## 13. Key takeaways

`@NoRepositoryBean` marks an intermediate repository interface so that Spring Data **does not create a bean for that interface itself**. It is commonly used with generic base interfaces:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
    // Shared contract and default methods
}
```

Concrete repositories supply the domain type and ID type:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {
}
```

Spring Data JDBC still creates a bean for `CustomerRepository`. Keep base interfaces small, containing only truly shared behavior; specific queries belong on concrete repositories, while custom implementations belong in repository fragments or custom base classes. `@NoRepositoryBean` controls repository bean creation—**it does not implement methods automatically, change SQL, or replace application services**.

### References

- [Spring Data Commons – NoRepositoryBean API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/NoRepositoryBean.html)
- [Spring Data Relational – JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html)
- [Spring Data Commons – Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
