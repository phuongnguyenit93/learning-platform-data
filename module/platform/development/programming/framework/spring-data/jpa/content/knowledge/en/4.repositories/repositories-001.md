# Repository, CrudRepository, and Data Access Contracts

## Objectives

A repository is an abstraction provided by Spring Data so applications can work with data through a Java contract. With Spring Data JPA, we declare a repository interface based on an entity and its primary key type; Spring Data generates the implementation at runtime, connecting repository calls to JPA and Hibernate.

This lesson focuses on `Repository<T, ID>`, `CrudRepository<T, ID>`, and how to design data access contracts. After completing it, you will be able to:

- Distinguish the repository marker interface from CRUD, paging, and JPA contracts.
- Choose the right base interface for a repository.
- Understand the semantics and return types of operations in `CrudRepository`.
- Declare queries by method name or using `@Query`.
- Use a repository in a service with appropriate transactions.
- Test repositories and avoid common mistakes.

Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, and PostgreSQL. The code snippets are placed in a Spring Boot project that already has the `spring-boot-starter-data-jpa` dependency and a valid DataSource configuration.

## 1. What Is a Repository?

In application architecture, a repository represents the place for accessing and persisting data. Services call meaningful methods such as `findById`, `save`, or `findByEmail`, instead of manually managing JDBC connections, SQL statements, and the EntityManager lifecycle in every business operation.

Spring Data defines the root interface:

```java
package org.springframework.data.repository;

public interface Repository<T, ID> {
}
```

This is a marker interface: by itself, it declares no CRUD methods. Its two generic type parameters mean:

- `T`: the domain object/entity type managed by the repository, such as `Customer`.
- `ID`: the identifier type of the entity, such as `Long`, `UUID`, or `String`.

When declaring:

```java
public interface CustomerRepository
        extends Repository<Customer, Long> {
}
```

we have marked `CustomerRepository` as a Spring Data-managed repository. However, this interface does not yet have any data access methods. We can declare query methods ourselves or extend a concrete contract such as `CrudRepository`.

Spring Data discovers repository interfaces in configured packages, typically the package containing the `@SpringBootApplication` class and its subpackages. The framework creates a proxy implementation when the application starts. Therefore, applications usually only need to declare an interface without writing a class that implements every CRUD method.

In Spring Boot, auto-configuration usually finds repositories automatically. For special configurations or packages outside the default scan area, `@EnableJpaRepositories` can be used to specify the repository packages explicitly.

### Contracts and Implementations

A contract describes:

- Which methods are allowed to be called.
- Input parameters and result types.
- The meaning of the operation at the business/data level.
- Conditions and behaviors that the implementing side must adhere to.

For example, `CrudRepository` commits to providing basic CRUD operations. Spring Data JPA implements that contract using JPA. If a different Spring Data module is used, the implementation may be based on another storage technology, while most of the code calling the repository remains unchanged.

This reduces the service's dependency on data access details. The service depends on the interface; Spring Data supplies the appropriate proxy at runtime.

## 2. Common Repository Interfaces

Spring Data has multiple contracts with increasing levels of functionality. Commonly used interfaces in Spring Data Commons and Spring Data JPA include:

| Interface | Role |
|---|---|
| `Repository<T, ID>` | Root marker interface; provides no CRUD operations yet |
| `CrudRepository<T, ID>` | Basic create, read, update, and delete operations |
| `ListCrudRepository<T, ID>` | CRUD with methods returning `List` instead of `Iterable` for certain collection operations |
| `PagingAndSortingRepository<T, ID>` | Querying lists with sorting or pagination |
| `ListPagingAndSortingRepository<T, ID>` | Variant returning `List` for sorting/pagination operations |
| `JpaRepository<T, ID>` | Extended contract for JPA, including CRUD, paging/sorting, and additional JPA operations |
| `QueryByExampleExecutor<T>` | Executing queries by an Example object |

### Note on the Hierarchy Since Spring Data 3.x

Starting in Spring Data 3.0, the CRUD and paging contracts are more clearly separated. `PagingAndSortingRepository` extends `Repository` directly and no longer extends `CrudRepository` as it did in older Spring Data versions.

Therefore, if a repository needs both CRUD and pagination/sorting in Spring Data 3.x, extend both contracts or use `JpaRepository` when working with JPA. For example:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

With Spring Data JPA, a common choice is:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

`JpaRepository` provides list-based CRUD operations, pagination/sorting, and JPA-specific features. In Spring Data 3.x, it extends the corresponding list contracts along with `QueryByExampleExecutor`.

In Spring Data 2.x, the inheritance relationship between `PagingAndSortingRepository` and `CrudRepository` differs from 3.x. When reading older documentation or code, check against the actual Spring Data version of the project. Do not infer which methods an interface has solely from examples targeting another version.

### When Should You Use Which Interface?

- Use `Repository` when you want to design a very small contract yourself, exposing only the required methods.
- Use `CrudRepository` when you need basic CRUD and do not need `List`-returning APIs for collection operations.
- Use `PagingAndSortingRepository` when you need pagination/sorting; with Spring Data 3.x, also combine it with `CrudRepository` if CRUD is needed as well.
- Use `JpaRepository` for most standard JPA repositories. It provides a rich API, though you do not have to use every method.
- Use an intermediate interface when multiple repositories share a common set of methods.

An intermediate interface used solely as a parent for other repositories can be annotated with `@NoRepositoryBean` so that Spring Data does not attempt to create a repository instance directly for it:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    boolean existsByIdAndArchivedFalse(ID id);
}
```

Concrete repositories extend `BaseRepository` and supply the entity and ID types. Only create a base repository when there is a genuine shared rule; avoid adding an interface layer that brings no benefit.

## 3. The `CrudRepository` Contract

`CrudRepository<T, ID>` declares the following basic operations. Return types are shown according to the Spring Data Commons contract:

| Method | Meaning | Return Type |
|---|---|---|
| `save(entity)` | Saves a new entity or updates an existing entity | `<S extends T> S` |
| `saveAll(entities)` | Saves a group of entities | `Iterable<S>` |
| `findById(id)` | Finds by primary key | `Optional<T>` |
| `existsById(id)` | Checks whether a primary key exists | `boolean` |
| `findAll()` | Retrieves all entities | `Iterable<T>` |
| `findAllById(ids)` | Retrieves entities by a collection of IDs | `Iterable<T>` |
| `count()` | Counts the number of entities | `long` |
| `deleteById(id)` | Deletes by ID | `void` |
| `delete(entity)` | Deletes the specified entity | `void` |
| `deleteAllById(ids)` | Deletes by multiple IDs | `void` |
| `deleteAll(entities)` | Deletes a group of entities | `void` |
| `deleteAll()` | Deletes all entities | `void` |

The methods can be described by group:

### 3.1. Create and Update: `save`, `saveAll`

`save` accepts an entity and returns the saved entity. In Spring Data JPA, this operation typically uses `EntityManager.persist` when the entity is determined to be new and `EntityManager.merge` when the entity is determined to already exist.

Important point: use the object returned by `save`. With a merge operation, the returned object may be a different managed instance from the input object.

```java
Customer customer = new Customer("linh@example.com", "Linh Nguyen");

Customer saved = customerRepository.save(customer);

Long generatedId = saved.getId();
```

`saveAll` accepts an `Iterable` and returns the saved entities. It is a convenient API for operating on multiple records. You should not assume it always executes a single SQL bulk insert; execution depends on the JPA provider, batch configuration, ID generation strategy, and database.

If IDs are assigned manually, Spring Data may need additional information to determine whether an entity is new or existing. When the default detection mechanism is unsuitable, you can use a `@Version` field or implement `Persistable` with `isNew()` according to the Spring Data JPA documentation.

### 3.2. Read: `findById`, `findAll`, `findAllById`

`findById` returns `Optional<T>`, so an absent result is represented explicitly:

```java
Optional<Customer> result = customerRepository.findById(10L);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getEmail());
}
```

It can be combined with `orElseThrow` when business logic requires the record to exist:

```java
Customer customer = customerRepository.findById(10L)
        .orElseThrow(() -> new IllegalArgumentException(
                "Customer not found: 10"
        ));
```

`findAll` and `findAllById` return `Iterable` in `CrudRepository`. `findAllById` only returns records that actually exist; do not assume the result contains every input ID or preserves the requested ID order. If a specific order is needed, sort explicitly in the query or in appropriate logic.

Do not use `findAll()` to load a large table just to display a single page of data. Use pagination to limit the amount of data read.

### 3.3. Delete: `deleteById`, `delete`, `deleteAll`

The delete methods perform deletion by ID, entity, or a collection of entities. Detailed behavior depends on the implementation and module contract; with a standard CRUD repository, a request to delete a non-existent ID is silently ignored.

Deleting an entity by ID:

```java
customerRepository.deleteById(10L);
```

If business logic needs to distinguish between “not found” and “deleted”, check first with `findById` and handle it explicitly in the service. Note that check-then-delete can encounter concurrency races; database constraints and transactions remain the final layer of protection.

`deleteAll()` deletes all data of the entity type managed by the repository. This is a wide-scope operation; call it only when business logic truly requires it and the impact is clearly understood.

## 4. Example `CustomerRepository` Declaration

Suppose the `Customer` entity has an ID of type `Long`, an email, and a full name. Minimal entity code:

```java
package com.example.demo.customer;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {
        // JPA requires a no-arg constructor.
    }

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Corresponding repository:

```java
package com.example.demo.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    boolean existsByEmailIgnoreCase(String email);

    List<Customer> findTop10ByFullNameContainingIgnoreCaseOrderByFullNameAsc(
            String keyword
    );

    Page<Customer> findByEmailContainingIgnoreCase(
            String keyword,
            Pageable pageable
    );
}
```

Spring Data creates the implementation for `CustomerRepository` at startup. There is no need to write a `CustomerRepositoryImpl` class just to implement the methods above.

A few points to note:

- `Customer` is the entity type; `Long` is the ID type. Both generic types must match the entity.
- `findByEmailIgnoreCase` is a derived query: Spring Data parses the method name to generate the query.
- `Optional<Customer>` represents the possibility that no matching email is found.
- `List<Customer>` returns a list limited to 10 records ordered by name.
- `Page<Customer>` carries the current page's data along with pagination metadata and total element/page counts.

## 5. Derived Queries: Generating Queries from Method Names

Spring Data can generate a query from a repository method name. Common structure:

```text
<subject><predicate><By><property><condition><OrderBy><property><Direction>
```

Examples:

| Method | Meaning |
|---|---|
| `findByEmail(String email)` | Find by email |
| `findByFullName(String name)` | Find by full name |
| `findByEmailAndFullName(String email, String name)` | Combine two conditions with AND |
| `findByEmailOrFullName(String email, String name)` | Combine two conditions with OR |
| `existsByEmail(String email)` | Check whether a matching record exists |
| `countByEmailContaining(String part)` | Count records whose email contains a substring |
| `findTop10ByFullNameOrderByIdDesc(String name)` | Fetch at most 10 records, ordered by ID descending |
| `findByIdBetween(Long from, Long to)` | Filter IDs within a range |

Some commonly used keywords:

- `And`, `Or`: combine conditions.
- `Between`, `LessThan`, `GreaterThanEqual`: compare values.
- `Containing`, `StartingWith`, `EndingWith`: match substring/prefix/suffix.
- `IgnoreCase`: case-insensitive string comparison when supported by the data type and database.
- `In`, `NotIn`: compare against a collection of values.
- `IsNull`, `IsNotNull`: check for null.
- `OrderBy`: declare sort order.
- `Top` or `First`: limit the number of results.

The method name must use the Java property name of the entity, not necessarily the column name in the database. For example, if the entity has property `fullName` mapped to column `full_name`, the derived query uses `FullName`.

Method names that are too long and contain many conditions can become hard to read. When a query is complex, requires special joins, or needs explicit control over JPQL/SQL, consider `@Query`.

## 6. Declaring Queries with `@Query`

`@Query` lets you write an explicit query directly in the repository. By default in Spring Data JPA, the query string is JPQL, using entity names and Java properties instead of table/column names.

Example finding customers by part of their email:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("""
       select c
       from Customer c
       where lower(c.email) like lower(concat('%', :keyword, '%'))
       """)
List<Customer> searchByEmail(@Param("keyword") String keyword);
```

JPQL references the `Customer` entity and the `email` property. If you want to write SQL directly using table and column names, use `nativeQuery = true`:

```java
@Query(
    value = "select * from customers where email = :email",
    nativeQuery = true
)
Optional<Customer> findByEmailNative(@Param("email") String email);
```

Native SQL depends on the database engine and actual schema; consider database portability and verify SQL syntax against the target database.

### Modifying Queries

For JPQL update/delete statements, mark the method with `@Modifying`. For example:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
       update Customer c
       set c.fullName = :name
       where c.id = :id
       """)
int updateFullName(
        @Param("id") Long id,
        @Param("name") String name
);
```

The method returns the number of affected rows. Call it within a transaction, typically opened in the service with `@Transactional`. Bulk updates/deletes run directly at the query level and do not go through the individual entity lifecycle as when modifying managed objects one by one. Previously loaded entities in the persistence context may become out of sync; depending on the situation, `clearAutomatically` clears the persistence context after the operation and `flushAutomatically` flushes pending changes before running the query.

Do not use `@Modifying` for regular SELECT queries.

## 7. Pagination and Sorting

When a table has a large amount of data, the repository should return a portion of the results. `Pageable` describes the page to retrieve; `Page<T>` contains the content along with page metadata.

Example calling the previously declared `findByEmailContainingIgnoreCase` method:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "email")
);

Page<Customer> page =
        customerRepository.findByEmailContainingIgnoreCase(
                "example",
                pageable
        );

List<Customer> customers = page.getContent();
int currentPage = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Notes:

- Page index is 0-based: `PageRequest.of(0, 20)` is the first page with size 20.
- Property names in `Sort.by` are entity properties, such as `email`.
- Maintain a stable sort order, often adding the primary key as a secondary criterion if the sorted column can have duplicate values.
- `Page<T>` usually requires an additional count query to calculate the total number of results. For screens that only need to know whether there is a next page, `Slice<T>` can reduce cost because it does not need the total page count.
- Do not fetch all records and paginate in Java if the database can perform pagination directly.

`PagingAndSortingRepository` provides the pagination/sorting contract; `JpaRepository` already provides these methods for JPA repositories.

## 8. Using Repositories in Services and Transactions

A repository is the data access boundary. A service orchestrates business logic and is usually where transactions spanning multiple repository operations are placed.

Example:

```java
package com.example.demo.customer;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String fullName) {
        if (repository.existsByEmailIgnoreCase(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, fullName));
    }

    @Transactional(readOnly = true)
    public Customer getRequired(Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );
    }

    @Transactional
    public Customer rename(Long id, String newName) {
        Customer customer = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );

        customer.setFullName(newName);
        return customer;
    }
}
```

In `rename`, the entity is loaded within a transaction and is managed by the persistence context. When the transaction commits, JPA dirty checking detects the change and writes it to the database; calling `save` again for this managed entity is not mandatory.

Transaction principles:

- CRUD methods inherited from the repository have Spring Data's default transaction configuration. Read methods are typically configured as read-only; write operations have a transaction.
- Application-declared query methods should not be assumed to automatically have a transaction. Place the transaction in the service or configure it explicitly on the query method.
- If a business operation calls multiple repositories, placing `@Transactional` on the service lets the operations participate in the same transaction.
- `readOnly = true` is an optimization hint for read-only transactions; do not use it for operations that need to write data.
- By default, Spring transactions roll back on unchecked exceptions. If rollback on checked exceptions is needed, declare `rollbackFor` appropriately.
- Transactional proxies work through calls from outside the bean. Calling another `@Transactional` method on the same instance (self-invocation) usually bypasses the proxy and may not apply the transaction as expected.

Do not put complex business logic inside a repository. Repositories focus on queries and persistence operations; services decide when to read, write, check conditions, and coordinate multiple data sources.

## 9. Testing Repositories

`@DataJpaTest` is a test slice for JPA. It configures the necessary persistence components, creates repositories, and typically uses an embedded database if the project has the appropriate dependency. Tests can use a real database/Testcontainers when behavior needs to be verified against the exact target database engine.

Example testing a derived query:

```java
package com.example.demo.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerIgnoringEmailCase() {
        repository.save(new Customer("linh@example.com", "Linh Nguyen"));

        assertThat(repository.findByEmailIgnoreCase("LINH@example.com"))
                .isPresent()
                .get()
                .extracting(Customer::getFullName)
                .isEqualTo("Linh Nguyen");
    }
}
```

This test assumes the entity and repository are placed in a package scanned by Spring Boot and the project includes a test dependency such as `spring-boot-starter-test`. `@DataJpaTest` normally rolls back each test's transaction after execution, keeping tests isolated.

What to test:

- Saving an entity and verifying the generated ID.
- Finding existing and non-existing entities.
- Verifying derived queries, conditional queries, and sort order.
- Verifying pagination with sufficient data.
- Verifying update/delete queries and affected row counts.
- Verifying constraints such as unique email on a real database if that is a critical requirement.

## 10. Common Errors and How to Avoid Them

| Error | Cause | Resolution |
|---|---|---|
| Repository bean not found | Repository package is outside component/repository scan scope | Place in an appropriate package or configure `@EnableJpaRepositories` |
| Wrong ID type | Generic ID does not match the `@Id` field type | Declare the exact type, e.g., `JpaRepository<Customer, Long>` |
| Spring fails to parse query name | Derived method references a wrong property name or keyword | Check against entity properties and Spring Data syntax |
| No CRUD methods when only extending PagingAndSortingRepository | Hierarchy changed in Spring Data 3.0 | Also extend CrudRepository or use JpaRepository |
| Query returns multiple results when Optional is declared | Query does not guarantee at most one result | Use List/Page or enforce an appropriate unique constraint |
| Unstable order when calling findAll | No Sort/OrderBy declared | Define ordering in the query or pass a Sort |
| LazyInitializationException | Accessing a lazy relationship after the persistence context closes | Load data inside a transaction, use a fetch query/entity graph, or map to an appropriate DTO |
| Entity changes not saved | Detached entity or transaction/persistence context is no longer active | Ensure the entity is managed in a transaction; use save when merging a detached entity |
| Bulk update leaves loaded entities with stale data | Bulk query bypasses entity state in the persistence context | Flush/clear appropriately or reload the entities |
| saveAll not as fast as expected | Not equivalent to a single bulk SQL insert | Check JDBC batching, ID strategy, Hibernate settings, and round trips |
| Two requests register the same email concurrently | Checking exists before insert cannot prevent race conditions | Use a UNIQUE constraint in the database and handle constraint violation errors |

An important rule: checking with `existsByEmail` before `save` is helpful for friendly error messages, but it does not guarantee uniqueness under concurrent requests. A `UNIQUE` constraint in the database is the ultimate safeguard.

## 11. Repository Selection and Design Checklist

- [ ] Choose the right entity and ID types for the generic repository.
- [ ] Extend only the contracts the service actually needs.
- [ ] Understand the differences between `CrudRepository`, `PagingAndSortingRepository`, and `JpaRepository` for your Spring Data version.
- [ ] Use `Optional` for single-result queries that may find nothing.
- [ ] Use `Pageable` or `Sort` when limiting and ordering results.
- [ ] Use derived queries for simple conditions and `@Query` for queries needing explicit control.
- [ ] Place transactions in the service for business operations involving multiple data operations.
- [ ] Use database unique/foreign key/check constraints for critical integrity rules.
- [ ] Test both matching data, missing data, and constraint violation cases.
- [ ] Do not put passwords, sensitive data, or business logic inside repositories.

## Conclusion

`Repository<T, ID>` marks a data access interface; `CrudRepository<T, ID>` adds the standard CRUD contract. Spring Data JPA generates the repository implementation and maps methods to JPA operations. When pagination, sorting, or richer JPA APIs are needed, extended interfaces such as `JpaRepository` can be chosen.

Good repository design starts with small contracts, accurate entity/ID types, and readable queries. Services are responsible for coordinating business logic and transactions; the database continues to protect data integrity through constraints. Mastering these boundaries keeps data access code easy to test, change, and maintain.
