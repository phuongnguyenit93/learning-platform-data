# Declaring ReactiveCrudRepository and R2dbcRepository

## 1. What is a Repository in Spring Data R2DBC?

Spring Data R2DBC provides the repository model so applications can work with relational data using a reactive API. Instead of writing SQL statements manually for every read, insert, update, and delete operation, you declare a repository interface bound to an entity type and an ID type. Spring Data generates the implementation at runtime based on mapping metadata, query methods, and R2DBC configuration.

Two commonly encountered base interfaces are:

- ReactiveCrudRepository: provides CRUD operations that return reactive types such as Mono and Flux.
- R2dbcRepository: combines reactive CRUD operations with the sorting capabilities provided by ReactiveSortingRepository.

Both are reactive repositories. They are not synchronous CRUD interfaces from Spring Data Commons and do not return List, Optional, or synchronous result objects for standard operations.

For example, a repository for Customer can be declared as follows:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

This interface describes the data access contract. You do not need to write an implementation class for the basic CRUD methods yourself. Spring Data creates a repository proxy at application startup and connects that proxy to the mapping mechanism and R2DBC.

## 2. Two Generic Parameters of a Repository

Both ReactiveCrudRepository and R2dbcRepository take two generic parameters:

~~~java
ReactiveCrudRepository<T, ID>
~~~

Where:

- T is the entity type managed by the repository.
- ID is the data type of the identifier property in the entity.

For example:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

The repository above manages the Product entity with an ID of type Long.

If the entity uses UUID:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, UUID> {
}
~~~

The ID type in the repository must be compatible with the type of the property marked with @Id. If the entity uses Long while the repository declares UUID, lookup or delete operations by ID will have an incompatible data type and may cause compile-time or runtime errors depending on usage.

An illustrative entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String fullName;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Spring Data uses @Id to identify the identifier property. Table and column names are derived according to mapping conventions or specified with @Table and @Column. The repository relies on that metadata to build CRUD operations.

## 3. ReactiveCrudRepository

### 3.1. Purpose

ReactiveCrudRepository is the foundational choice when reactive CRUD operations are needed. This interface extends Repository and provides the common methods for saving, reading, and deleting entities.

For example:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

There is no need to implement save, findById, findAll, or deleteById. Spring Data creates an implementation suited to the R2DBC repository infrastructure.

### 3.2. Commonly Used CRUD Methods

Commonly encountered methods include:

| Method | Common reactive return type | Meaning |
|---|---|---|
| save(entity) | Mono<S> | Saves a new entity or updates an entity according to the persistence mechanism |
| saveAll(Iterable) | Flux<S> | Saves an existing collection of entities |
| saveAll(Publisher) | Flux<S> | Receives entities from a publisher and saves them |
| findById(id) | Mono<T> | Finds an entity by ID |
| findById(Publisher<ID>) | Mono<T> | Finds by an ID emitted from a publisher |
| existsById(id) | Mono<Boolean> | Checks whether an entity exists by ID |
| findAll() | Flux<T> | Reads the entities |
| findAllById(Iterable<ID>) | Flux<T> | Reads entities by multiple IDs |
| count() | Mono<Long> | Counts the number of entities |
| deleteById(id) | Mono<Void> | Deletes by ID |
| delete(entity) | Mono<Void> | Deletes an entity |
| deleteAll() | Mono<Void> | Deletes all entities belonging to the repository |

Exact signatures may vary across Spring Data versions. When you need to verify the return type of an overload, consult the API documentation for the version in use. The general idea is that results are represented by reactive publishers, not synchronous values.

### 3.3. save() Does Not Always Simply Mean INSERT

The save(entity) method persists an entity. Spring Data determines whether an entity is new or already exists via newness detection, typically based on the ID or the Persistable mechanism if the entity customizes how newness is determined.

Therefore, you should not conclude solely from the name save that the SQL statement is always INSERT. Depending on entity state, mapping, and dialect, Spring Data may perform the appropriate insert or update operation.

For example:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

The saved publisher describes the save operation. It executes when subscribed to. On success, the Mono emits the saved entity as returned by the repository.

If you need to guarantee a new record, design the ID and newness state explicitly. If you need to update an existing record, determine how the ID is managed and handle the case where the record does not exist. You should not assume save always performs an upsert with identical semantics across every database.

### 3.4. Reading One Entity and Reading Multiple Entities

findById returns a Mono because an ID can match at most one entity:

~~~java
Mono<Customer> customer = customerRepository.findById(42L);
~~~

If no record exists, the Mono completes without emitting a value. You can handle this case with switchIfEmpty:

~~~java
return customerRepository.findById(customerId)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(customerId)
    ));
~~~

findAll returns a Flux because the number of results can be zero, one, or many:

~~~java
Flux<Customer> customers = customerRepository.findAll();
~~~

Flux emits each entity as a stream. You do not need to load the entire result into a List before starting to process it. If you want to collect results into a List, you can use collectList(), but consider the data size because that operation holds the entire result in memory.

### 3.5. Deleting Data and the Mono<Void> Type

Delete operations typically return Mono<Void>:

~~~java
Mono<Void> deletion = customerRepository.deleteById(42L);
~~~

Mono<Void> represents an operation that completes or errors without emitting a result entity. To run a subsequent step after deletion, use then():

~~~java
return customerRepository.deleteById(customerId)
    .then(auditRepository.recordCustomerDeletion(customerId));
~~~

If you need to know whether a record was deleted, design an appropriate check operation or statement. Do not assume Mono<Void> provides the number of affected rows.

## 4. R2dbcRepository

### 4.1. Purpose and Inheritance Hierarchy

R2dbcRepository is the specialized repository interface for Spring Data R2DBC. It inherits reactive CRUD operations and the reactive sorting capabilities provided by ReactiveSortingRepository.

It can be declared as:

~~~java
import org.springframework.data.r2dbc.repository.R2dbcRepository;

public interface CustomerRepository
        extends R2dbcRepository<Customer, Long> {
}
~~~

In typical usage, this repository still provides CRUD operations like ReactiveCrudRepository while also having the find/sort contract with Sort.

A key point to remember is that R2dbcRepository does not turn reactive operations into blocking ones. Methods still return Mono or Flux.

### 4.2. Sorting Capabilities

ReactiveSortingRepository provides the findAll(Sort sort) method to read data in the requested order:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.r2dbc.repository.R2dbcRepository;

public interface CustomerRepository
        extends R2dbcRepository<Customer, Long> {
}
~~~

Usage:

~~~java
Sort sort = Sort.by(Sort.Direction.ASC, "fullName");

Flux<Customer> customers =
    customerRepository.findAll(sort);
~~~

The property passed to Sort is the property name on the entity, not necessarily the SQL column name. Mapping metadata translates the property to the corresponding column based on conventions or annotations.

For example, the fullName property may map to the full_name column. When using Sort.by("fullName"), Spring Data works with property metadata to sort by the corresponding column.

When sorting by multiple properties:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("lastName"),
    Sort.Order.asc("firstName")
);

Flux<Customer> customers = customerRepository.findAll(sort);
~~~

Only allow sorting by valid entity properties. If sort names come from an external request, map a list of allowed values to the corresponding properties instead of passing unchecked strings directly.

### 4.3. Which Interface Should You Choose?

| Need | Commonly suitable interface |
|---|---|
| Only reactive CRUD needed | ReactiveCrudRepository |
| Reactive CRUD and findAll(Sort) needed | R2dbcRepository |
| Want to explicitly declare the repository uses R2DBC | R2dbcRepository |
| Want to keep a minimal contract for the service | ReactiveCrudRepository |

R2dbcRepository is a convenient choice when the sorting repository contract is needed. If sorting is not needed, ReactiveCrudRepository helps the interface express the exact scope of functionality used by the service.

There is no need to extend both interfaces in the same repository just to get CRUD and sorting, because R2dbcRepository already includes those contracts through Spring Data R2DBC's inheritance hierarchy.

Interface details and inheritance relationships may change between Spring Data versions. Check the Javadoc of the exact dependency version in your project before relying on a specific method or extended interface.

## 5. Declaring Query Methods by Method Name

A major benefit of Spring Data repositories is the ability to derive queries from method names. You declare a method following conventions, and Spring Data parses the name to build the query.

For example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByLastName(String lastName);

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByActiveTrue();

    Mono<Void> deleteByEmail(String email);
}
~~~

Common prefixes:

| Prefix | Meaning |
|---|---|
| findBy / readBy / getBy | Finds records matching a condition |
| existsBy | Checks whether a matching record exists |
| countBy | Counts matching records |
| deleteBy / removeBy | Deletes matching records |

The part after By describes the condition. For example, findByLastName queries by the lastName property. Spring Data uses mapping metadata to associate that property with a database column.

### 5.1. Combining Multiple Conditions

You can use And and Or:

~~~java
Flux<Customer> findByFirstNameAndLastName(
    String firstName,
    String lastName
);

Flux<Customer> findByActiveTrueOrEmailIsNull();
~~~

The method name must reflect valid properties and operators supported by Spring Data. For complex queries, overly long method names become hard to read and maintain. In such cases, consider @Query or a repository fragment.

### 5.2. Comparison and Search Conditions

For example:

~~~java
Flux<Product> findByPriceGreaterThan(BigDecimal minPrice);

Flux<Product> findByPriceBetween(
    BigDecimal min,
    BigDecimal max
);

Flux<Customer> findByLastNameContaining(String fragment);

Flux<Order> findByStatusIn(Collection<OrderStatus> statuses);
~~~

Keywords such as GreaterThan, Between, Containing, and In are parsed by Spring Data according to property types and query derivation rules.

Not every Spring Data JPA keyword has the same level of support in R2DBC. Check the query derivation capabilities of the Spring Data Relational version in use, especially for specialized operators, functions, joins, and database-specific queries.

### 5.3. Sorting by Method Name

A default ordering can be expressed directly in the method name:

~~~java
Flux<Customer> findByActiveTrueOrderByLastNameAscFirstNameAsc();

Flux<Order> findByStatusOrderByCreatedAtDesc(OrderStatus status);
~~~

If the order needs to vary per request, use Sort on methods that support sorting or use R2dbcRepository with findAll(Sort). For custom derived queries, check the method signature and Sort support in your current Spring Data version.

## 6. Using @Query When Method Names Are Not Expressive Enough

When a query requires explicit SQL, you can use Spring Data R2DBC's @Query:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT id, customer_id, status, created_at
        FROM orders
        WHERE customer_id = :customerId
        ORDER BY created_at DESC
        """)
    Flux<Order> findRecentOrdersByCustomer(Long customerId);
}
~~~

@Query lets you specify the SQL statement directly. Parameter names are bound via Spring Data R2DBC's query method mechanism; make sure placeholder names and corresponding parameters match according to the rules of the version in use.

When writing manual SQL:

- Write table and column names matching the actual schema.
- Do not assume the naming strategy will automatically rename identifiers inside the SQL string.
- Use parameter binding instead of concatenating input data into SQL.
- Select only the columns compatible with the mapping of the result type.
- Verify SQL against your database dialect.
- Use integration tests with an actual database for important queries.

If a query modifies data, declare it according to the modifying query rules of the Spring Data R2DBC version in use, typically combining @Modifying with @Query. The return type should match the affected row count or semantics supported by the API.

Illustrative example:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(Long id, String status);
~~~

Return signatures and modifying query annotations should be checked against the specific Spring Data version. For multi-step writes or operations that must roll back together, use an appropriate reactive transaction.

## 7. Repository Methods Always Return Publishers

ReactiveCrudRepository and R2dbcRepository are reactive APIs. Read methods typically return Mono or Flux; write/delete methods also return publishers.

Service example:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Mono<Customer> getCustomer(Long id) {
        return customerRepository.findById(id);
    }

    public Flux<Customer> searchByLastName(String lastName) {
        return customerRepository.findByLastName(lastName);
    }

    public Mono<Customer> createCustomer(Customer customer) {
        return customerRepository.save(customer);
    }
}
~~~

The service returns the publisher to the controller or the next calling layer. It does not need to call subscribe() inside each method.

WebFlux controller example:

~~~java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/{id}")
    public Mono<Customer> getById(@PathVariable Long id) {
        return customerService.getCustomer(id);
    }

    @GetMapping
    public Flux<Customer> findAll() {
        return customerService.searchByLastName("Nguyen");
    }
}
~~~

Spring WebFlux subscribes to the publisher to write the response when the request is processed. There is no need to manually subscribe or block in the controller.

### 7.1. Mono and Flux

| Type | Used when | Example |
|---|---|---|
| Mono<T> | Zero or at most one result | findById, findByEmail, save |
| Flux<T> | Potentially multiple results | findAll, findByStatus, findByLastName |
| Mono<Void> | Only care whether the operation completes or errors | deleteById |
| Mono<Long> | Count result | count |
| Mono<Boolean> | Existence check result | existsById |

If a query is expected to return at most one row, using Mono<T> is appropriate. If the database returns more than one row when the method expects a single result, the operation may throw a cardinality error rather than silently picking an arbitrary row.

### 7.2. Do Not Use Synchronous Types in a Reactive Repository

Do not declare an R2DBC repository like a blocking repository:

~~~java
// Not suitable for ReactiveCrudRepository
Customer findByEmail(String email);

List<Customer> findAll();
~~~

Instead:

~~~java
Mono<Customer> findByEmail(String email);

Flux<Customer> findAll();
~~~

If the application needs a List to process a small dataset at a specific boundary, you can call collectList() on a Flux. However, that is a step that collects results within the reactive pipeline, not a reason to turn the repository into a blocking API.

Do not call block() on a WebFlux event-loop thread. Blocking can reduce throughput and cause runtime errors in a reactive environment.

## 8. The Repository Is an Interface; Spring Generates the Implementation

You usually only need to declare the interface:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByCategoryId(Long categoryId);
}
~~~

The Spring Data repository infrastructure performs the main tasks:

1. Discovers repository interfaces within the scan scope.
2. Determines the entity type and ID type from the generic parameters.
3. Reads the entity's mapping metadata.
4. Generates implementations/proxies for CRUD methods.
5. Parses query methods by name or @Query.
6. Connects operations to the R2DBC infrastructure and conversion configuration.
7. Exposes repository beans for services to inject.

You do not need to write a ProductRepositoryImpl class just to implement standard CRUD methods. If you need custom query logic that cannot be expressed with a query method or @Query, you can use a repository fragment.

## 9. Configuration for Repository Discovery

### 9.1. Spring Boot

In a Spring Boot application, the appropriate starter dependency and ConnectionFactory configuration allow Spring Boot to set up many R2DBC components. Repository interfaces are typically discovered automatically within the application's scan package.

A commonly used Gradle dependency setup:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-data-r2dbc"
    runtimeOnly "io.r2dbc:r2dbc-postgresql"
}
~~~

The driver name depends on the database. The example above illustrates PostgreSQL; for MySQL or SQL Server, use the corresponding R2DBC driver.

Connection configuration can be placed in application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: app_user
    password: change-me
~~~

Connection details in the example are for illustration only. In real environments, do not store sensitive passwords directly in source control; use appropriate secret/configuration management.

### 9.2. @EnableR2dbcRepositories

When configuring manually or when specifying repository packages, you can use @EnableR2dbcRepositories:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.shop.repository"
)
public class R2dbcRepositoryConfiguration {
}
~~~

This annotation instructs Spring Data to scan repository interfaces in the specified package. In a Boot application where repositories are already auto-configured within the proper scope, adding it just to repeat the default configuration is usually unnecessary.

If repositories reside outside the scan package, adjust component/repository scanning accordingly. An undiscovered interface will have no bean available for injection.

### 9.3. ConnectionFactory and Transaction Manager

A repository needs an appropriate ConnectionFactory to access the database. In a reactive application with transactions, configure an R2DBC transaction manager matching the ConnectionFactory used by the repository.

Do not configure repositories to use one ConnectionFactory and the transaction manager to use a different ConnectionFactory if operations are expected to participate in the same transaction. Keep the data access infrastructure consistent.

## 10. Organizing Repositories by Business Domain

A repository is typically tied to an aggregate root or entity that the application needs to access. For example:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Flux<Order> findByCustomerId(Long customerId);

    Flux<Order> findByStatus(OrderStatus status);

    Mono<Long> countByStatus(OrderStatus status);
}
~~~

The service uses the repository to execute business logic:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Flux<Order> findCustomerOrders(Long customerId) {
        return orderRepository.findByCustomerId(customerId);
    }

    public Mono<Long> countPendingOrders() {
        return orderRepository.countByStatus(OrderStatus.PENDING);
    }
}
~~~

Do not cram all business logic into the repository interface. Repositories focus on data access and querying. Services orchestrate business rules, transactions, and interactions between repositories when needed.

Nor should you mechanically create a repository for every Java class. A value object or child component belonging to an aggregate may not need its own repository. Base this on aggregate boundaries and how data is accessed.

## 11. When a Custom Repository Is Needed

Query methods and @Query cover many cases. When access logic becomes complex, you can extract a repository fragment.

Main interface example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Fragment:

~~~java
public interface CustomerSearchRepository {
    Flux<Customer> searchCustomers(String keyword);
}
~~~

Fragment implementation:

~~~java
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final DatabaseClient databaseClient;

    public CustomerSearchRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<Customer> searchCustomers(String keyword) {
        return databaseClient.sql("""
                SELECT id, full_name, email
                FROM customers
                WHERE full_name LIKE :pattern
                """)
            .bind("pattern", "%" + keyword + "%")
            .map((row, metadata) -> {
                Customer customer = new Customer();
                // Map columns using the appropriate constructor or factory.
                return customer;
            })
            .all();
    }
}
~~~

The mapping snippet in the example is simplified to focus on fragment structure. In a real implementation, map all columns thoroughly and handle nulls/data types according to the schema.

The fragment implementation name follows Spring Data's naming conventions and repository fragment configuration. Follow the conventions of the version in use so Spring discovers the implementation.

## 12. Notes on Pagination in Reactive Repositories

Reactive repositories typically use Flux to stream data. The synchronous Page<T> concept with total element count and page metadata requires the framework to know the total record count, usually needing an additional count query. Therefore, do not assume every reactive method supports Page<T> like blocking repositories do.

When you need to limit data, you can use Sort and query mechanisms supported by your Spring Data R2DBC version, or write SQL with LIMIT/OFFSET:

~~~sql
SELECT id, full_name, email
FROM customers
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

If the API requires total page count, execute a separate count query or design a response with appropriate metadata. For large tables, consider keyset pagination / seek pagination instead of deep offsets to reduce scan and sort overhead.

Pageable, Page parameter types, and paging capabilities depend on the version and how the query is declared. Verify against the API docs of the Spring Data R2DBC version in use rather than inferring from Spring Data JPA.

## 13. Transactions Across Multiple Repository Calls

If a business operation needs to update multiple tables, use a reactive transaction. Repository publishers must be chained within the same pipeline and run under the appropriate transaction context.

For example:

~~~java
@Transactional
public Mono<Void> completeOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Order not found")
        ))
        .flatMap(order -> {
            order.setStatus(OrderStatus.PAID);
            return orderRepository.save(order);
        })
        .flatMap(order ->
            paymentRepository.markPaid(order.getId())
        )
        .then();
}
~~~

This is a structural example. The method must return a reactive publisher, the transaction manager must be an R2DBC reactive transaction manager, and the repositories must share the same ConnectionFactory to participate in the same transaction.

Do not call subscribe() inside a @Transactional method. Doing so creates an independent subscription that may run outside the transaction context. Return the publisher and compose with flatMap, then, concatMap, or other suitable operators.

If operations need to run in parallel, consider how the connection and driver handle multiple statements on the same transaction connection. Serialize with then() or concatMap when ordering guarantees are needed.

## 14. Common Mistakes

| Mistake or confusion | Common cause | How to handle |
|---|---|---|
| Cannot inject repository | Interface not discovered by component/repository scan | Check packages and @EnableR2dbcRepositories |
| ID type mismatch | Generic ID differs from @Id property type | Align the ID types |
| Query method not created | Method name uses nonexistent property or unsupported keyword | Check entity properties and query derivation rules |
| Query cannot find table/column | Mapping metadata does not match schema | Check @Table, @Column, and DDL |
| Using List or synchronous entity in reactive repository | Confusing reactive repository with blocking repository | Use Mono/Flux |
| Query never executes | Publisher has not been subscribed to | Return publisher to framework or subscribe at the proper application boundary |
| Query runs twice | Cold publisher subscribed multiple times | Inspect pipeline and avoid manual subscribe |
| Transaction does not cover all operations | Separate subscription created or different ConnectionFactory used | Chain publishers and unify ConnectionFactory |
| findById result has no value | No matching row | Use switchIfEmpty or handle empty Mono |
| Loading too much data | Using findAll on a large table followed by collectList | Filter, limit, sort, or paginate appropriately |

## 15. Process for Declaring a New Repository

When adding a repository in Spring Data R2DBC, you can follow this sequence:

1. Identify the entity/aggregate root to be accessed.
2. Ensure the entity has accurate mapping metadata, especially @Id and table/column names.
3. Choose the exact ID type matching the identifier property.
4. Choose ReactiveCrudRepository if only reactive CRUD is needed.
5. Choose R2dbcRepository if the sorting repository contract is also needed.
6. Declare query methods for simple, frequent conditions.
7. Use @Query or a repository fragment for specialized SQL queries.
8. Ensure methods return Mono/Flux or an appropriate reactive type.
9. Verify the repository is scanned and created as a bean.
10. Verify the ConnectionFactory, driver, and transaction manager.
11. Write integration tests for CRUD, query methods, and empty-result cases.
12. Test actual queries against the deployed schema and database.

## 16. Self-Check Exercises

### Exercise 1: Basic Repository Declaration

The Customer entity has a Long ID. Declare a repository that only needs reactive CRUD.

Hint:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

### Exercise 2: Choosing R2dbcRepository

You need CRUD and findAll(Sort). Which interface should you use?

Hint: R2dbcRepository provides reactive CRUD and the sorting contract. You can use findAll(Sort) to sort by entity properties.

### Exercise 3: Choosing the Return Type

A method finds a customer by email, given that email is unique. Should it return Mono<Customer> or Flux<Customer>?

Hint: Mono<Customer> represents at most one result. A unique constraint in the database is needed to guarantee emails are truly unique.

### Exercise 4: Finding by Condition

Write a query method to find orders by customerId sorted by createdAt descending.

Hint:

~~~java
Flux<Order> findByCustomerIdOrderByCreatedAtDesc(Long customerId);
~~~

### Exercise 5: Handling Not Found

findById may emit no entity. Convert the empty case into a business error.

Hint:

~~~java
return customerRepository.findById(id)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(id)
    ));
~~~

### Exercise 6: Avoiding Manual Subscription

A service calls repository.save(customer).subscribe() and then returns Mono<Void>. Why is this approach unsuitable?

Hint: subscribe() starts an independent stream, making it hard for the framework to manage the lifecycle and transaction of the overall pipeline. Return the publisher from the repository and chain it into the service pipeline.

## 17. Key Takeaways

- ReactiveCrudRepository provides reactive CRUD operations based on entity and ID types.
- R2dbcRepository is the specialized repository for R2DBC, combining reactive CRUD with the sorting repository contract.
- T and ID generics must match the entity type and the @Id property type.
- Read/result-returning operations use Mono or Flux; delete operations usually use Mono<Void>.
- Query methods can be derived from method names, but keywords and support should be verified against your Spring Data R2DBC version.
- @Query allows writing SQL directly; manual SQL must match the schema and use parameter binding.
- Spring generates the repository implementation/proxy when the interface is discovered and repository configuration is valid.
- Repositories focus on data access; services orchestrate business logic and transactions.
- In a reactive pipeline, do not call subscribe() or block() inside services.
- Multiple repositories sharing a transaction must use a compatible transaction manager and ConnectionFactory.

When declaring a repository, pick the smallest interface that meets your needs, declare the correct entity and ID types, and add query methods or custom SQL when needed. Keep the entire data access flow reactive so Spring can manage subscriptions, connections, and transactions consistently.
