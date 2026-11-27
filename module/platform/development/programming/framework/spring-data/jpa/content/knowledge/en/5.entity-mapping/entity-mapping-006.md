# Repository, CrudRepository, and Data Access Contracts

## Objectives

A repository is a data access contract provided by Spring Data. With Spring Data JPA, an application declares an interface based on an entity and its primary key type; Spring Data generates the implementation at runtime, bridging repository calls to JPA and Hibernate.

This lesson focuses on `Repository<T, ID>`, `CrudRepository<T, ID>`, and how to design data access contracts. After completing it, you will be able to:

- Distinguish the marker repository from CRUD, pagination, and JPA contracts.
- Choose the right base interface for a repository.
- Understand the semantics, return types, and limitations of `CrudRepository` operations.
- Declare queries via method names or `@Query`.
- Use repositories in services with appropriate transactions.
- Test repositories and avoid common mistakes.

Examples use Java 17+, Spring Boot 3.x, Spring Data JPA, and PostgreSQL. The code snippets sit within a Spring Boot project that already has the `spring-boot-starter-data-jpa` dependency and a valid DataSource configuration.

## 1. What is a Repository?

In application architecture, a repository represents where data is accessed and stored. Services call meaningful methods such as `findById`, `save`, or `findByEmail`, instead of manually managing JDBC connections, SQL statements, and EntityManager lifecycles in every business operation.

Spring Data defines the root interface:

```java
package org.springframework.data.repository;

public interface Repository<T, ID> {
}
```

This is a marker interface: by itself it declares no CRUD methods. The two generic parameters represent:

- `T`: the domain object/entity type managed by the repository, e.g., `Customer`.
- `ID`: the identifier type of the entity, e.g., `Long`, `UUID`, or `String`.

When declaring:

```java
public interface CustomerRepository
        extends Repository<Customer, Long> {
}
```

we mark `CustomerRepository` as a Spring Data-managed repository. However, this interface does not yet have data access methods. We can declare query methods ourselves or extend a concrete contract such as `CrudRepository`.

Spring Data discovers repository interfaces within configured packages, usually the package containing the `@SpringBootApplication` class and its subpackages. The framework generates a proxy implementation at application startup. Thus, applications normally only declare the interface without manually writing an implementation class for every CRUD method.

In Spring Boot, auto-configuration usually locates repositories automatically. For special configurations or packages outside the default scan root, `@EnableJpaRepositories` can specify repository packages explicitly.

### Contract vs. implementation

A contract describes allowed method calls, input parameters, result types, and operation semantics. Repositories decouple services from storage implementation details via a data access API.

For instance, `CrudRepository` promises basic CRUD operations. Spring Data JPA implements that contract using JPA. With a different Spring Data module, the implementation may rely on another storage technology while most caller code remains unchanged.

A repository interface is not a class containing hand-written query logic. At runtime, Spring Data creates a proxy for the interface and delegates known methods to the appropriate implementation. Developer-declared query methods are parsed or bound to defined queries.

## 2. Common repository interfaces

Spring Data provides several contracts with different capability levels. Common interfaces in Spring Data Commons and Spring Data JPA include:

| Interface | Role |
|---|---|
| `Repository<T, ID>` | Root marker interface, provides no CRUD out of the box |
| `CrudRepository<T, ID>` | Basic create, read, update, and delete operations |
| `ListCrudRepository<T, ID>` | CRUD variant returning `List` for collection operations |
| `PagingAndSortingRepository<T, ID>` | List queries with sorting or pagination |
| `ListPagingAndSortingRepository<T, ID>` | Paging/sorting variant returning `List` |
| `JpaRepository<T, ID>` | Extended JPA-specific contract with CRUD, paging/sorting, and additional JPA operations |
| `QueryByExampleExecutor<T>` | Executes queries by Example object |

### Note on hierarchy changes since Spring Data 3.x

Starting in Spring Data 3.0, CRUD and pagination contracts are more cleanly separated. `PagingAndSortingRepository` extends `Repository` directly and no longer extends `CrudRepository` as in older Spring Data versions.

Therefore, if a repository needs both CRUD and paging/sorting in Spring Data 3.x, extend both contracts or use `JpaRepository` when working with JPA. Example:

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

`JpaRepository` provides List-based CRUD APIs, paging/sorting, and JPA-specific features. It also supports methods such as `flush`, `saveAndFlush`, batch deletes, and obtaining entity references. Only use these APIs when business logic actually requires them.

In Spring Data 2.x, the inheritance relationship between `PagingAndSortingRepository` and `CrudRepository` differed from 3.x. When reading legacy documentation or code, check your project's actual Spring Data version. Do not assume which methods an interface offers solely from examples targeting another version.

### When to use which interface?

- Use `Repository` when designing a minimal custom contract exposing only required methods.
- Use `CrudRepository` when basic CRUD is needed without `List`-returning collection operations.
- Use `PagingAndSortingRepository` when paging/sorting is needed; in Spring Data 3.x, combine with `CrudRepository` if CRUD is also required.
- Use `JpaRepository` for most standard JPA repositories. It is a convenient choice when CRUD, pagination, and JPA APIs are needed.
- Use an intermediate interface when multiple repositories share a common set of methods.

An intermediate interface meant solely as a parent for other repositories can be annotated with `@NoRepositoryBean` so Spring Data does not try to instantiate a repository bean for it directly:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    boolean existsByIdAndArchivedFalse(ID id);
}
```

Concrete repositories extend `BaseRepository` and supply the entity and ID types. Only introduce a base repository when there is a real shared rule; avoid adding interface layers that bring no benefit.

## 3. The CrudRepository contract

`CrudRepository<T, ID>` declares the following basic operations. These are the key method names and return types of the Spring Data Commons contract:

| Method | Meaning | Return type |
|---|---|---|
| `save(entity)` | Saves a new entity or updates an entity | `<S extends T> S` |
| `saveAll(entities)` | Saves a group of entities | `Iterable<S>` |
| `findById(id)` | Finds by primary key | `Optional<T>` |
| `existsById(id)` | Checks whether primary key exists | `boolean` |
| `findAll()` | Fetches all entities | `Iterable<T>` |
| `findAllById(ids)` | Fetches entities for a set of IDs | `Iterable<T>` |
| `count()` | Counts entities | `long` |
| `deleteById(id)` | Deletes by ID | `void` |
| `delete(entity)` | Deletes the specified entity | `void` |
| `deleteAllById(ids)` | Deletes by multiple IDs | `void` |
| `deleteAll(entities)` | Deletes a group of entities | `void` |
| `deleteAll()` | Deletes all entities | `void` |

The methods fall into three groups:

### 3.1. Create and Update: save, saveAll

`save` accepts an entity and returns the saved entity. In Spring Data JPA, this operation typically uses `EntityManager.persist` when the entity is determined to be new and `EntityManager.merge` when the entity is determined to already exist.

Important point: always use the object returned from `save`. With merge operations, the returned object may be a different managed instance from the input object.

```java
Customer customer = new Customer("linh@example.com", "Linh Nguyen");

Customer saved = customerRepository.save(customer);

Long generatedId = saved.getId();
```

Spring Data JPA determines new-entity status using its new-state detection strategy. Normally, the framework checks a non-primitive version field if present, then checks the ID. If the ID is null, the entity is usually treated as new. For entities with manually assigned IDs, detection may need adjustment via `Persistable` or an appropriate strategy; otherwise, a new entity might be treated as an existing one.

`saveAll` accepts an `Iterable` and returns the saved entities. It is a convenient API for multi-record operations. Do not assume it always executes a single SQL bulk insert; execution depends on the JPA provider, batch configuration, ID generation strategy, and database.

### 3.2. Read: findById, findAll, findAllById

`findById` returns `Optional<T>`, making absence explicit:

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

`findAll` and `findAllById` return `Iterable` in `CrudRepository`. `findAllById` returns only records that actually exist; do not assume the result contains every input ID or preserves the requested ID order. If a specific order is required, sort explicitly in the query or at the appropriate layer.

Do not use `findAll()` to load a large table just to display one page of data. Use pagination to bound the amount of data read.

### 3.3. Delete: deleteById, delete, deleteAll

Delete methods remove records by ID, entity, or a collection of entities. Under the standard CRUD contract, requesting deletion of a non-existent ID is silently ignored.

```java
customerRepository.deleteById(10L);
```

If business logic needs to distinguish "not found" from "deleted", check first with `findById` and handle explicitly in the service. Note that check-then-delete operations can encounter concurrency races; database constraints and transactions remain the final safeguard.

`deleteAll()` deletes all data of the entity type managed by the repository. This is a broad operation; call it only when business logic truly requires it and its impact is well understood.

## 4. Example CustomerRepository declaration

Suppose the `Customer` entity has a `Long` ID, email, and full name. Minimal entity code:

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
        // JPA requires a no-argument constructor.
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

Spring Data generates the implementation for `CustomerRepository` at startup. There is no need to write a `CustomerRepositoryImpl` class just to implement the methods above.

Points to note:

- `Customer` is the entity type; `Long` is the ID type. Both generic types must match the entity.
- `findByEmailIgnoreCase` is a derived query: Spring Data parses the method name to build the query.
- `Optional<Customer>` represents the possibility that no matching email is found.
- `List<Customer>` returns a list capped at 10 records ordered by name.
- `Page<Customer>` carries the current page's data along with pagination metadata and total element/page counts.

## 5. Derived queries: building queries from method names

Spring Data can derive queries from repository method names. Common structure:

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
| `existsByEmail(String email)` | Check if a matching record exists |
| `countByEmailContaining(String part)` | Count records whose email contains substring |
| `findTop10ByFullNameOrderByIdDesc(String name)` | Fetch up to 10 records, sorted by ID descending |
| `findByIdBetween(Long from, Long to)` | Filter ID within range |

Common keywords:

- `And`, `Or`: combine conditions.
- `Between`, `LessThan`, `GreaterThanEqual`: value comparisons.
- `Containing`, `StartingWith`, `EndingWith`: substring/prefix/suffix matching.
- `IgnoreCase`: case-insensitive string comparison when data type and database support it.
- `In`, `NotIn`: compare against a collection of values.
- `IsNull`, `IsNotNull`: null checks.
- `OrderBy`: declare sort order.
- `Top` or `First`: limit result count.

Method names must use the entity's Java property names, not necessarily database column names. For example, an entity with property `fullName` mapped to column `full_name` uses `FullName` in derived queries.

Very long method names with many conditions can become hard to read. When a query is complex, needs special joins, or requires explicit control over JPQL/SQL, consider `@Query`.

### Property paths and entity relationships

Spring Data can resolve nested property paths. For example, if entity `Customer` has an `address.city` relationship, a query can be declared as:

```java
List<Customer> findByAddress_City(String city);
```

The underscore separates property path segments when property names could be ambiguous. Verify the actual property names and relationships in the entity. Query methods only work when Spring Data can resolve the property path.

## 6. Declaring queries with @Query

`@Query` lets you write explicit queries directly in the repository. By default in Spring Data JPA, the query string is JPQL, using entity names and Java properties instead of table/column names.

Example searching customers by partial email:

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

JPQL references the `Customer` entity and `email` property. To write SQL directly against table/column names, use `nativeQuery = true`:

```java
@Query(
    value = "select * from customers where email = :email",
    nativeQuery = true
)
Optional<Customer> findByEmailNative(@Param("email") String email);
```

Native SQL depends on the database management system and actual schema; consider portability and verify SQL syntax against the target database.

### Modifying queries

For JPQL update/delete queries, annotate with `@Modifying`. Example:

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

The method returns the number of affected rows. Call it within a transaction, typically opened in the service with `@Transactional`. Bulk update/delete executes directly at the query level and bypasses individual entity lifecycle callbacks unlike modifying managed objects one by one. Entities already loaded in the persistence context may become stale; depending on the situation, `clearAutomatically` clears the persistence context after the operation and `flushAutomatically` flushes pending changes before running the query.

Do not use `@Modifying` for regular SELECT queries.

## 7. Pagination and sorting

When tables hold large datasets, repositories should return a slice of results. `Pageable` describes the requested page; `Page<T>` holds the content along with page metadata.

Example calling the previously declared `findByEmailContainingIgnoreCase`:

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

- Page indices are zero-based: `PageRequest.of(0, 20)` is the first page with size 20.
- Property names in `Sort.by` are entity properties, e.g., `email`.
- Use a deterministic ordering, typically adding the primary key as a secondary sort criterion if the primary sort column can have duplicates.
- `Page<T>` usually requires an extra count query to compute total results. For screens that only need to know whether a next page exists, `Slice<T>` can reduce cost since it does not need total page counts.
- Do not fetch all records and paginate in Java when the database can paginate directly.

## 8. save behavior, entity state, and persistence context

`save` does not always mean immediately executing an INSERT or UPDATE statement. JPA manages entities through states:

- **New/transient:** new entity, not yet managed by a persistence context.
- **Managed:** entity currently managed by EntityManager; changes may be synchronized on flush/commit.
- **Detached:** entity previously managed but no longer attached to a persistence context.
- **Removed:** entity marked for deletion in the persistence context.

In Spring Data JPA, `save` typically calls `persist` for new entities or `merge` for entities considered existing. `merge` copies the input object's state onto a managed instance and returns that instance. Therefore, use the return value of `save` if you need to continue working with the entity after merging.

For entities already managed in the current transaction, field changes are typically detected by JPA dirty checking. Example:

```java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow();

    customer.setFullName(newName);
    // When the transaction commits, JPA synchronizes changes.
}
```

Calling `save(customer)` after modifying a managed entity is not strictly necessary. However, if the entity is detached or logic is not inside a persistence context as expected, handle entity state explicitly.

## 9. Transactions and service boundaries

Inherited repository CRUD methods have default transaction configuration in Spring Data JPA's implementation. Application-declared query methods should not be assumed to be transactional automatically. Common practice is to place transactions on services so one business operation can span multiple repository calls.

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String name) {
        if (repository.existsByEmailIgnoreCase(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, name));
    }

    @Transactional(readOnly = true)
    public Customer getRequired(Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );
    }
}
```

Key takeaways:

- `@Transactional` in the service defines the business boundary.
- Repository calls within the same transaction normally participate in the current transaction.
- `readOnly = true` is a hint for read-only transactions; do not use it for write operations.
- By default, Spring rolls back on unchecked exceptions. If rollback on checked exceptions is needed, configure `rollbackFor` accordingly.
- Transactional proxies operate on calls from outside the bean. Self-invocation of another `@Transactional` method within the same instance normally bypasses the proxy.
- Avoid holding transactions open while calling external APIs or performing slow non-database work.

## 10. Customizing repository contracts

Applications do not always want to expose the entire `JpaRepository` API. You can create a base interface to restrict operations or provide shared queries.

For example, a base interface declaring only needed methods:

```java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}
```

Concrete repositories can extend this interface and declare additional queries. However, if custom method implementations are required, you must provide an appropriate implementation mechanism; marker interfaces do not automatically synthesize implementations for arbitrary custom methods.

Another option is extending `JpaRepository` while injecting and using only the needed API in services. This is simpler, though the interface still exposes the full contract to other callers.

### Custom repository implementation

When queries or persistence behavior cannot be expressed cleanly via derived queries or `@Query`, you can create a custom repository fragment. A fragment consists of an interface describing the methods and an implementation class. The main repository extends that fragment alongside the required Spring Data interfaces.

Example:

```java
public interface CustomerSearchRepository {
    List<Customer> searchActiveCustomers(String keyword);
}
```

```java
@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Customer> searchActiveCustomers(String keyword) {
        return entityManager.createQuery("""
                select c
                from Customer c
                where c.active = true
                  and lower(c.fullName) like lower(:keyword)
                """, Customer.class)
            .setParameter("keyword", "%" + keyword + "%")
            .getResultList();
    }
}
```

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchRepository {
}
```

Naming conventions and discovery of custom implementations can vary by Spring Data version/configuration. Follow your project version's conventions and verify that Spring Data detects the implementation class on startup. For simple queries, prefer derived queries or `@Query` to minimize hand-maintained code.

## 11. Testing repositories

`@DataJpaTest` is the test slice for JPA. It configures required persistence components and repositories; it typically uses an embedded database if the project has a matching dependency. To verify PostgreSQL-specific behavior, configure tests against a real database or Testcontainers.

Example:

```java
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

The test assumes entities, repositories, and test dependencies are configured. `@DataJpaTest` typically runs each test in a transaction and rolls back afterward. When using PostgreSQL-specific queries, custom data types, or differing constraints, test with PostgreSQL to avoid discrepancies with embedded databases.

Scenarios worth testing:

- Saving a new entity and confirming the generated ID.
- Finding existing and non-existent records.
- Derived queries with conditions, ignore case, sorting, and pagination.
- JPQL/native queries and modifying queries.
- Unique constraints and behavior on invalid data.
- Relevant entity relationships, lazy loading, and fetch strategies.

## 12. Common design mistakes

**Repository containing business logic.** Repositories should focus on querying and persistence. Registration rules, authorization, status checks, and coordinating multiple repositories belong in the service or domain layer.

**Using findAll on large datasets.** Loading an entire table can consume excessive memory and time. Use Page/Slice/Scroll appropriate for the requirement.

**Assuming save always inserts.** `save` can invoke persist or merge. Understand entity state and use the returned instance.

**Assuming saveAll is a bulk insert.** The API does not guarantee a single SQL statement. Check batch settings and ID strategies when optimizing.

**Using Optional for a query that can return multiple rows.** If a query returns multiple results while the method declares a single entity or Optional, Spring Data can throw a non-unique result exception. Use List/Page or enforce uniqueness with constraints.

**Not handling the missing-record case.** `findById` returns Optional; the service should decide whether to return 404, raise a business error, or apply a fallback.

**Relying on exists before save to guarantee uniqueness.** Two concurrent requests can both pass the check. Use a database unique constraint and handle constraint violation errors.

**Ignoring the Spring Data version.** Interface hierarchy examples online may target Spring Data 2.x or 3.x. Check Spring Boot dependency management before choosing interfaces.

**Returning entities directly from APIs.** This can expose internal fields, cause JSON cycles on bidirectional relationships, or trigger lazy loading outside transactions. Consider DTOs and mapping at the service/web layer.

## 13. Checklist when designing a repository

- [ ] Entity and ID generic types match the JPA mapping.
- [ ] Chosen the minimal contract meeting needs; hierarchy understood for the active version.
- [ ] Optional used for single-result lookups that may find nothing.
- [ ] List/Page/Slice chosen appropriately for data volume.
- [ ] Derived queries have readable names and valid property paths.
- [ ] Complex queries cleanly separated with @Query or custom fragments.
- [ ] Transactions spanning business operations placed in services.
- [ ] Critical integrity rules protected by database constraints.
- [ ] Repository tested for both success and error cases.
- [ ] No business logic or secrets placed inside repositories.

## Conclusion

`Repository<T, ID>` is the marker interface identifying a repository; `CrudRepository<T, ID>` provides the standard CRUD contract. Spring Data JPA generates implementations for repository interfaces and maps operations to JPA. Extended contracts like `PagingAndSortingRepository` and `JpaRepository` add pagination, sorting, and JPA-specific persistence features.

A good repository exposes only needed operations, uses accurate entity/ID types, and keeps queries readable. Services orchestrate business logic and transactions; the database protects data integrity. Understanding the contract keeps the application less coupled to implementation details and easier to test.
