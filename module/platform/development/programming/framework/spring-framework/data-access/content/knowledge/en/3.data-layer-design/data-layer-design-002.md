# Separating Data Access Contracts from Implementations

## 1. The Design Problem: Who Needs to Know Where Data Is Stored?

In a Spring application, the business layer needs operations such as "find a customer by ID", "create an order", and "check whether an account exists". Those operations carry **business meaning**, whereas `SELECT`, `ResultSet`, `EntityManager`, table names, HTTP calls to a data service, and how connections are opened are merely **implementation details**.

If a service depends directly on storage details, changing the technology or table layout often forces changes to business logic:

```java
// Anti-pattern example: excerpt, not a standalone Java program.
class CustomerService {
    private final JdbcTemplate jdbc;

    CustomerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    String greet(long id) {
        return jdbc.queryForObject(
            "SELECT name FROM customers WHERE id = ?",
            String.class,
            id
        );
    }
}
```

Even though `JdbcTemplate` already eliminates much boilerplate JDBC code, the service above still knows the `customers` table, the `name` column, SQL, and the "exactly one row" contract. If you switch to Spring Data JPA, change the database schema, or fetch customers from an API, the service itself must be modified.

**Lesson goal:** the service knows only *what operation is needed and what the result means*, while *how it is done using JDBC, JPA, memory, or a gateway* belongs to the data access implementation layer. This separation creates a boundary that is easier to test, replace, and evolve independently.

## 2. What Is a Data Access Contract?

A **contract** is the set of operations, data types, input preconditions, result semantics, and error rules that a caller can rely on. In Java, a contract is typically expressed as an `interface`, but **method signatures alone are not enough**: behavior must be specified.

Minimal example:

```java
public interface CustomerRepository {
    Optional<Customer> findById(long id);
    void create(Customer customer);
}
```

In this contract, we must agree on:

- `findById(id)` returns a customer if one exists, or `Optional.empty()` if absent; it does not throw an error merely because nothing was found.
- `create(customer)` adds a new customer; if the ID already exists, it throws a consistent business exception, such as `CustomerAlreadyExistsException`.
- `Customer` is a model that the business side understands, not a `ResultSet`, `Tuple`, proxy entity requiring an open session, or driver-specific type.
- Infrastructure errors (DB unavailable, query timeout, broken connection) should be reported as data access failures; do not conflate them with "not found".
- If a method guarantees ordering, pagination, concurrency locking, or an exact record count, those guarantees must be part of the contract description.

**The contract is defined by its consumer's needs.** Do not create an interface simply by copying every method of `JdbcTemplate` or `JpaRepository`. The first question is: what business operations does the service actually need?

### 2.1. Dependency Direction in the Design

```text
       Application / business layer
                 |
                 | calls methods on
                 v
       CustomerRepository (contract)
                 ^
                 | implements
        +--------+---------+
        |                  |
 JdbcCustomerRepository   InMemoryCustomerRepository
        |                  |
    JdbcTemplate        Map<Long, Customer>
        |
    DataSource / DB
```

The `implements` arrow shows that the concrete class must **conform to** the contract. To keep source code free of technology coupling, the interface is often placed in a `domain` or `application.port` package, while JDBC/JPA code lives in `infrastructure.persistence`. At runtime, Spring wires the parts together via dependency injection.

You do not have to adopt full hexagonal architecture to achieve this. The core idea is **Dependency Inversion**: high-level policy components depend on a stable abstraction defined by their own needs, rather than depending directly on low-level storage classes.

### 2.2. Distinguishing Interface, Implementation, and Configuration

| Component | Responsibility | Example |
| --- | --- | --- |
| Contract (port/repository interface) | States operations and semantics needed by the caller | `CustomerRepository.findById` |
| Service/use case | Validates business rules, coordinates operations, defines transaction boundaries | `CustomerService.register` |
| Adapter/implementation | Translates abstract operations into concrete statements/driver calls | `JdbcCustomerRepository` |
| Mapping | Converts data rows/entities/responses into a contract-compliant model | `RowMapper<Customer>` |
| Composition root | Selects implementations and wires dependencies into services | `@Configuration`, `@Bean`, or component scanning |

**Do not confuse "separating an interface" with "every class needs an interface".** Creating an abstraction pays off when there is a clear responsibility boundary, a need to test with fakes, a likelihood of swapping adapters, or a desire to prevent persistence APIs from leaking into services. For small prototype code with a single call path, a pass-through interface that adds no semantics may only increase complexity.

## 3. Java 17+ Example: Switching from Memory to JDBC Without Changing the Service

The example below is a **complete program** using Java 17+, Spring Framework 6.2.x, and in-memory H2. Both implementations share the same `CustomerRepository` and the same `CustomerService`. The application intentionally runs two separate `ApplicationContext` instances to illustrate implementation selection, so there are no two competing beans at the same time.

Directory structure:

```text
data-contract-demo/
├── pom.xml
└── src/main/java/example/ContractDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>data-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/ContractDemo.java`:

```java
package example;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;

public class ContractDemo {
    // Business model, independent of JDBC and H2.
    public record Customer(long id, String name) {}

    // Contract: method semantics are identical across all implementations.
    public interface CustomerRepository {
        Optional<Customer> findById(long id);
        void create(Customer customer);
    }

    public static class CustomerAlreadyExistsException extends RuntimeException {
        public CustomerAlreadyExistsException(long id) {
            super("Customer already exists: " + id);
        }

        public CustomerAlreadyExistsException(long id, Throwable cause) {
            super("Customer already exists: " + id, cause);
        }
    }

    // Service depends only on the contract, without importing JDBC/JPA.
    public static class CustomerService {
        private final CustomerRepository repository;

        public CustomerService(CustomerRepository repository) {
            this.repository = repository;
        }

        public void register(long id, String name) {
            if (id <= 0 || name == null || name.isBlank()) {
                throw new IllegalArgumentException("Invalid customer");
            }
            repository.create(new Customer(id, name));
        }

        public String greeting(long id) {
            return repository.findById(id)
                    .map(c -> "Hello, " + c.name())
                    .orElse("Not found");
        }
    }

    // First adapter: in-memory storage. Suitable for demo/tests, not durable.
    public static class InMemoryCustomerRepository implements CustomerRepository {
        private final Map<Long, Customer> items = new HashMap<>();

        @Override
        public Optional<Customer> findById(long id) {
            return Optional.ofNullable(items.get(id));
        }

        @Override
        public void create(Customer customer) {
            if (items.putIfAbsent(customer.id(), customer) != null) {
                throw new CustomerAlreadyExistsException(customer.id());
            }
        }
    }

    // Second adapter: persists to the database using Spring JDBC.
    public static class JdbcCustomerRepository implements CustomerRepository {
        private final JdbcTemplate jdbc;

        public JdbcCustomerRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public Optional<Customer> findById(long id) {
            List<Customer> rows = jdbc.query(
                    "SELECT id, name FROM customers WHERE id = ?",
                    (rs, rowNum) -> new Customer(
                            rs.getLong("id"),
                            rs.getString("name")),
                    id);
            return rows.stream().findFirst();
        }

        @Override
        public void create(Customer customer) {
            try {
                jdbc.update(
                        "INSERT INTO customers (id, name) VALUES (?, ?)",
                        customer.id(),
                        customer.name());
            } catch (DuplicateKeyException e) {
                throw new CustomerAlreadyExistsException(customer.id(), e);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MemoryConfig {
        @Bean
        public CustomerRepository customerRepository() {
            return new InMemoryCustomerRepository();
        }

        @Bean
        public CustomerService customerService(CustomerRepository repository) {
            return new CustomerService(repository);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JdbcConfig {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:contracts;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate jdbc = new JdbcTemplate(ds);
            // For demo purposes only. Real applications should manage schema with migrations.
            jdbc.execute(
                    "CREATE TABLE customers (" +
                    "id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL)");
            return jdbc;
        }

        @Bean
        public CustomerRepository customerRepository(JdbcTemplate jdbc) {
            return new JdbcCustomerRepository(jdbc);
        }

        @Bean
        public CustomerService customerService(CustomerRepository repository) {
            return new CustomerService(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(MemoryConfig.class)) {
            CustomerService service = context.getBean(CustomerService.class);
            service.register(1L, "Lan");
            System.out.println("Memory: " + service.greeting(1L));
            System.out.println("Memory missing: " + service.greeting(99L));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            CustomerService service = context.getBean(CustomerService.class);
            service.register(1L, "Lan");
            System.out.println("JDBC: " + service.greeting(1L));
            System.out.println("JDBC missing: " + service.greeting(99L));
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.ContractDemo
```

Lines printed by the program (ignoring external framework logs if configured differently by the environment):

```text
Memory: Hello, Lan
Memory missing: Not found
JDBC: Hello, Lan
JDBC missing: Not found
```

**Look at what changed:** `CustomerService`, `CustomerRepository`, and `Customer` remained untouched. Only the composition root chose between `InMemoryCustomerRepository` and `JdbcCustomerRepository`. The JDBC version converts SQL/`ResultSet` into `Customer`; the in-memory version reads/writes a `Map`. Both return `Optional.empty()` when not found and both throw `CustomerAlreadyExistsException` on duplicate ID creation (with H2 and Spring's exception translator recognizing duplicate-key errors).

The example uses a plain `HashMap` for illustration; it is not thread-safe for concurrent access across multiple threads, is not durable across process restarts, and provides no transactions. Creating the table inside a `@Bean` method is also for demo purposes only: production should use Flyway/Liquibase or managed migrations.

## 4. A Good Contract Has Stable Semantics

Suppose a service handles customer registration. If the contract returns JDBC types, it has leaked implementation details:

```java
// Should not be used as a business-layer contract:
ResultSet getCustomer(long id);
SQLException saveCustomer(Customer customer);
```

`ResultSet` depends on an open connection; `SQLException` forces callers to understand driver errors. Moreover, the signature of `saveCustomer` in the second example has a meaningless return type for a create operation.

A better contract is:

```java
// Illustrative interface snippet; domain types are defined in the application module.
interface CustomerRepository {
    Optional<Customer> findById(CustomerId id);
    Customer create(NewCustomer command);
    boolean existsByEmail(Email email);
}
```

**Note:** it is not mandatory to create `CustomerId`/`Email` value objects for every project; `long` and `String` are still valid if validation and meaning are clear enough. What matters is that the interface describes the needs of the use case.

To evaluate contract quality, answer five questions:

1. **What does the caller need?** Reading an aggregate, searching, creating, updating, deleting, or simply checking a condition?
2. **What does "no data" mean?** `Optional.empty()`, an empty list, `null` (avoid if possible), or a business exception?
3. **What does "success" mean?** Must `create` guarantee creating exactly one record or allow an idempotent upsert? Does `update` return a new version, affected row count, or nothing?
4. **Which errors are consistent across implementations?** Duplicate keys, version conflicts, and invalid arguments are business rules; broken DB connections are usually infrastructure errors.
5. **Are there guarantees about ordering, pagination, concurrency, and transactions?** Without explicit definitions, two adapters can return results that have the "right types" but different meanings.

### 4.1. Avoid Overly Broad Contracts

A `GenericRepository<T, ID>` interface with dozens of CRUD, flush, lock, paging, and query-builder methods may fit a persistence library, but easily gives use cases far more capabilities and DB concepts than needed.

Instead of:

```java
interface GenericRepository<T, ID> {
    T save(T value);
    void delete(ID id);
    List<T> findAll();
    List<T> findByRawSql(String sql);
}
```

A boundary tailored for an ordering use case could be:

```java
interface OrderStore {
    Optional<Order> findById(OrderId id);
    OrderId add(NewOrder order);
    boolean reserveIfAvailable(OrderId id, long expectedVersion);
}
```

A name like `reserveIfAvailable` (if the business model truly needs it) exposes a result and a concurrency condition, rather than forcing the service to assemble unsafe SQL update strings. However, the condition, version check, and atomic operation still must be implemented properly in the DB; the method name alone does not guarantee atomicity.

**Interface Segregation:** split contracts according to actual caller needs (read models, write operations, specialized queries) when doing so reduces coupling. Do not mechanically split into dozens of single-method interfaces.

### 4.2. Error Semantics Must Be Consistent

Do not let adapter A return `null` when missing while adapter B throws `EmptyResultDataAccessException` if the contract specifies `Optional.empty()`. In the example above, the JDBC implementation uses `query(...)` + `Optional` to keep "0 rows" handling consistent.

Exceptions to distinguish:

- **Not found:** a normal case when allowed by the contract; return `Optional.empty()`.
- **Duplicate key or business constraint violation:** translate into an application-level exception/result (such as `CustomerAlreadyExistsException`) after identifying the cause.
- **System failure:** `DataAccessException` may be allowed to propagate to an infrastructure error handler, or be converted into a dedicated application exception if required by the architecture. Never "disguise" a DB failure as "customer does not exist".
- **Unexpected result:** if the data store can return multiple rows for a query on an identifier that ought to be unique, enforce DB constraints and report invalid data errors; never silently pick an arbitrary row.

The demo catches `DuplicateKeyException`; in practice, driver classification is not guaranteed to be identical across all databases. Test error paths and unique constraints against the actual database engine in use.

## 5. Using Spring DI to Wire Contracts to Implementations

The service only needs to accept the interface via its constructor:

```java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    // Business methods...
}
```

This is an illustrative snippet in an application using `@Service`; when Spring finds a matching `CustomerRepository` bean, it injects it into the constructor. Swapping implementations does not require changing the constructor or service logic.

There are two common ways to register an adapter:

**Option A — stereotype + component scanning:**

```java
@Repository
public class JdbcCustomerRepository implements CustomerRepository {
    // Constructor receives JdbcTemplate; implements the contract.
}
```

**Option B — explicit configuration:**

```java
@Configuration(proxyBeanMethods = false)
class PersistenceConfiguration {
    @Bean
    CustomerRepository customerRepository(JdbcTemplate jdbc) {
        return new JdbcCustomerRepository(jdbc);
    }
}
```

Both snippets are **illustrative** and require the corresponding classes, imports, and beans to build. `@Repository` declares the persistence role and can participate in exception translation for certain persistence APIs when configured; `JdbcTemplate` translates its own `SQLException`s and does not require `@Repository` to do so.

### 5.1. When Multiple Beans Implement the Same Interface

If both `InMemoryCustomerRepository` and `JdbcCustomerRepository` are registered as beans in the same context without disambiguation, injecting by type `CustomerRepository` usually cannot resolve a unique bean (`NoUniqueBeanDefinitionException`).

Options:

- **Register only one bean** per environment configuration: production uses JDBC, tests use a fake.
- **`@Qualifier`** explicitly specifies which implementation to inject when both must coexist in the same context.
- **`@Primary`** designates a default among multiple beans; use cautiously to avoid hidden choices.
- **`@Profile`** or property-driven configuration for different adapters; the configuration must guarantee that exactly one bean is active for the consumer.

Profile example (illustrative snippet):

```java
@Bean
@Profile("dev")
CustomerRepository memoryRepository() {
    return new InMemoryCustomerRepository();
}

@Bean
@Profile("prod")
CustomerRepository jdbcRepository(JdbcTemplate jdbc) {
    return new JdbcCustomerRepository(jdbc);
}
```

Do not use profiles as a security mechanism. Names like `prod` or `dev` are no substitute for credentials, authorization, and deployment environment controls. In many applications, a single adapter is configured across all environments and changing only the `DataSource` is sufficient.

### 5.2. Who Depends on Whom at Compile Time?

One way to organize packages:

```text
com.example.app
├── domain
│   └── Customer.java
├── application
│   ├── CustomerService.java
│   └── port
│       └── CustomerRepository.java
├── infrastructure
│   └── persistence
│       └── jdbc
│           └── JdbcCustomerRepository.java
└── config
    └── PersistenceConfiguration.java
```

Under this layout, `CustomerService` imports `CustomerRepository` and `Customer`; `JdbcCustomerRepository` imports back into the contract types to implement them. `PersistenceConfiguration` is allowed to know both sides to assemble the application. Multi-module builds can enforce this via dependency direction; single-module projects still need code-review discipline and architectural tests.

These exact package names are not mandatory: what must be preserved is that business source code is not forced to import `ResultSet`/`JdbcTemplate`/`EntityManager` just to execute a use case.

## 6. Mapping: Preventing Data Details from Leaking into Contracts

The same customer can take three forms:

```text
SQL table: customers(id, full_name, status_code)
             |
       JDBC RowMapper
             v
Customer(id, name, status)   <- returned by contract
             ^
         JPA mapper
             |
CustomerJpaEntity(id, fullName, statusCode)
```

If a contract returns `CustomerJpaEntity` directly and the caller accesses a lazy relationship after the transaction ends, business logic becomes coupled to the persistence context and suffers lazy-loading failures. With JDBC, returning `ResultSet` ties callers to an open connection.

The adapter should convert data into a boundary-appropriate model:

```java
// Example RowMapper as part of the JDBC adapter.
RowMapper<Customer> mapper = (rs, rowNum) ->
    new Customer(
        rs.getLong("id"),
        rs.getString("full_name")
    );
```

You do not always need to duplicate every entity/DTO. If the model is simple, has no lazy loading, and has clear ownership, sharing a type can be considered. However, **do not share types solely for initial convenience** if the consequence is DB APIs or persistence annotations spreading through the business layer.

### 6.1. A Boundary Does Not Eliminate All Technology Differences

One implementation uses JDBC SQL, another uses JPA or HTTP. They can keep the same interface, yet each must handle separately:

- SQL dialects, transaction semantics, isolation levels, locking/optimistic locking.
- Lazy loading, fetch strategies, and query counts.
- `NULL` values, type conversions, precision, and timezones.
- Stable pagination/sorting, consistency when reading from caches or remote APIs.
- Network errors, timeouts, retries, idempotency, and eventual consistency.

Swapping an adapter succeeds when **contract behavior remains valid**, not merely because the new class implements every method signature.

## 7. Transactions Belong to the Use-Case Boundary, Not the Interface

A repository contract decouples the service from SQL, but **an interface does not automatically provide transactions**. For example, a use case that must create an invoice and reserve stock as one consistent unit:

```java
// Illustrative snippet; interfaces are designed for each domain.
@Service
class CheckoutService {
    private final OrderRepository orders;
    private final StockRepository stock;

    CheckoutService(OrderRepository orders, StockRepository stock) {
        this.orders = orders;
        this.stock = stock;
    }

    @Transactional
    public void checkout(NewOrder order) {
        stock.reserve(order.items());
        orders.create(order);
    }
}
```

To work properly, this requires a configured transaction manager, calls routed through a Spring proxy (under the default proxy mode), and both adapters participating in **the same appropriate resource/transaction**. If `stock` calls a separate HTTP service, JDBC `@Transactional` cannot automatically roll back the remote system; you must design coordination mechanisms such as outbox, saga, or idempotency depending on the problem.

Pitfalls to avoid:

- Placing `@Transactional` on an interface and assuming every proxy/weaving mode and configuration picks up the annotation identically. In practice, place it on concrete service methods and test the active proxy configuration.
- Calling an annotated method via `this.method()` under default proxying: self-invocation bypasses advice.
- By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions require `rollbackFor` or other configuration. Catching and swallowing exceptions can lead to commits.
- Opening a new JDBC connection inside a transaction without using Spring-managed connection mechanisms can prevent the operation from joining the active transaction.
- Using an in-memory fake in a unit test and assuming real rollback works: a `Map` has no transactions, so database transaction integration tests are required.

**Useful rule:** the service decides *which steps must be business-atomic*; adapters and Spring configuration ensure how transactions are executed for the corresponding data source.

## 8. Testing Along Boundaries: Service Tests vs. Adapter Tests

Separating contracts pays off when you want to test business logic without booting a database.

### 8.1. Unit Testing Services with Fakes

Use an in-memory implementation to verify how the service uses the contract:

```java
// JUnit 5 excerpt, using the classes in ContractDemo.
@Test
void registerAndGreet() {
    CustomerRepository fake = new InMemoryCustomerRepository();
    CustomerService service = new CustomerService(fake);

    service.register(7L, "Hoa");

    assertEquals("Hello, Hoa", service.greeting(7L));
    assertEquals("Not found", service.greeting(8L));
    assertThrows(CustomerAlreadyExistsException.class,
            () -> service.register(7L, "Trung"));
}
```

This snippet is not part of the standalone `ContractDemo.java`; it requires JUnit Jupiter, static imports `Assertions.assertEquals`/`assertThrows`, and imports of nested types from `ContractDemo`. Its purpose is to isolate the service to test business rules quickly without starting Spring.

A fake can mislead tests if it behaves differently from the real database. For instance, a `Map` does not enforce VARCHAR column lengths, collation, DB constraints, isolation, or query ordering. Therefore, unit tests do not prove an adapter obeys the contract.

### 8.2. Contract Tests for Implementations

Write a shared suite of behavioral tests and run it against both the in-memory and JDBC implementations:

| Scenario | Contract outcome to align on |
| --- | --- |
| Finding a nonexistent ID | `Optional.empty()` |
| Creating then finding the same ID | Reads back the exact created data |
| Creating a duplicate ID | `CustomerAlreadyExistsException` |
| Invalid input data | Rejected by the service under the same rules |
| Query returning multiple results | Satisfies cardinality/ordering contract |
| Concurrent updates | Matches conflict policy if specified by the contract |

To test cleanly, each case needs isolated data and clear setup/cleanup. Contract tests catch adapters that "match the signature" without matching behavior.

### 8.3. Adapter Integration Tests with a DB

Test `JdbcCustomerRepository` separately against H2 or a real test database. Verify SQL syntax, column mapping, unique constraints, database-specific behavior, rollbacks, and `NULL` values. When SQL depends on PostgreSQL/MySQL/Oracle, testing against the matching database (e.g., via Testcontainers) is more reliable than simulating everything in H2.

Spring test support includes: `@JdbcTest` for the JDBC slice and `@DataJpaTest` for JPA. These are two distinct mechanisms serving two different implementations; do not assume `@DataJpaTest` tests `JdbcTemplate`. When testing bean wiring, test the Spring context with the real adapter configuration to catch missing beans, wrong qualifiers, or misselected profiles.

## 9. Advanced Design: Read/Write Splitting, Pagination, and Consistency

A single interface does not have to handle both broad querying and every write operation. As a system grows, separate read and write ports may emerge:

```java
interface CustomerReader {
    Optional<CustomerSummary> findSummaryById(long id);
    List<CustomerSummary> search(CustomerSearchFilter filter, int limit);
}

interface CustomerWriter {
    CustomerId create(NewCustomer command);
    boolean updateName(CustomerId id, String newName, long expectedVersion);
}
```

This is an illustrative snippet requiring the corresponding domain types. `expectedVersion` represents optimistic concurrency: the adapter updates when the current version matches, e.g., SQL `UPDATE ... WHERE id = ? AND version = ?` and checks the row count. If it returns `false`, the service decides whether that means a conflict or a deleted record based on the agreed contract. Do not blindly interpret every `update count = 0` as the same error.

When a contract returns a list, clarify:

- **Ordering:** databases do not guarantee a default order without `ORDER BY`; memory fakes must also choose an order matching the contract.
- **Limits:** for large collections, do not force `findAll()` to load everything into memory; use appropriate limits plus cursors/page keys.
- **Pagination:** offset pagination and keyset pagination behave differently under concurrent writes; interfaces should describe cursor/sort clearly enough.
- **Visibility timing:** queries through caches or read replicas may be stale; do not promise "read-your-writes" if the infrastructure does not guarantee it.
- **Multiple data sources:** one interface can hide calls to multiple adapters, but distributed transactions, retries, and consistency must be designed explicitly.

If Spring Data already fits, `JpaRepository` or `CrudRepository` can serve as a ready-made abstraction. However, its methods, `Pageable`/`Page` types, and entity mechanics can couple the application layer to Spring Data. Use it directly only when that coupling is a deliberate choice; if you want an independent business port, add a small application-owned interface and let an adapter delegate to the Spring Data repository behind it.

## 10. Common Design Mistakes

| Mistake | Why it causes trouble | How to fix |
| --- | --- | --- |
| Service imports `JdbcTemplate`/`EntityManager` and writes SQL | Data technology leaks into business logic | Move queries and mapping into an adapter |
| Interface returns `ResultSet` or entities with lazy proxies | Callers depend on open resources/persistence context | Return properly mapped domain/DTO types |
| Creating 1:1 interfaces for every class without need | Adds forwarding layers with no semantic boundary | Abstract only where there are clear consumers and responsibilities |
| Defining `save` without stating insert, update, or upsert | Adapters may handle it inconsistently | Choose precise names and contract descriptions |
| Fake returns `null` while JDBC throws when data is missing | Service tests pass while production fails | Use contract tests and `Optional` consistently |
| Catching every `DataAccessException` and returning "not found" | Masks DB failures/outages | Distinguish system errors from valid missing cases |
| Registering multiple beans for one interface without clear selection | Injection fails or picks an unintended bean | Register only the right bean, or use `@Qualifier`/`@Primary` deliberately |
| Using `@Transactional` and trusting a fake proves rollback | Tests fail to prove DB atomicity | Write integration tests with a transaction manager and DB |
| Passing arbitrary raw SQL strings as repository interface parameters | Contract leaks query layer | Express queries by business intent and typed criteria |
| Assuming a new adapter is equivalent just because it implements the interface | Differs in ordering, isolation, errors, nullability | Specify postconditions and run contract tests |

## 11. Process for Applying This to an Existing Spring Project

1. **Pick a concrete use case** that currently mixes SQL and logic: e.g., customer registration, profile reading, order creation. Observe the exact data the service needs.
2. **Write the contract from the consumer's perspective**, specifying operation names, inputs, outputs, not-found behavior, duplicates, and system errors. Do not automatically copy the entire persistence API.
3. **Move DB access into an adapter**: SQL, `JdbcTemplate`, `RowMapper`, JPA entity mapping, and exception translation. Keep the service calling only the contract.
4. **Register the implementation in Spring configuration** and use constructor injection. Verify each context unambiguously has the right implementation.
5. **Choose transaction boundaries at the service** when multiple operations must be consistent; ensure the same transaction manager and resources, and test rollback.
6. **Split tests**: business unit tests with fakes, shared behavioral contract tests, and adapter integration tests against a DB.
7. **Measure value before expanding**: if an abstraction becomes a pointless pass-through layer, shrink it. If additional data sources appear, focus on verifying behavioral equivalence.

### When Should You Prioritize This Approach?

It is especially valuable when a use case has business rules that need protection from schema/driver changes, when you want to test services without a DB, when multiple data sources may be used, or when a team wants clear ownership boundaries between application and persistence.

Not every operation warrants splitting out an interface: in a small CRUD system, a service calling a Spring Data repository directly can be simple and maintainable enough. Match the level of abstraction to expected change cost and testing needs.

### Self-Check Questions

1. Why does merely moving SQL from a service into another class not automatically produce a good data access contract?
2. What is the difference between "an interface has all the methods" and "an implementation complies with contract semantics"?
3. Why is `Optional.empty()` usually clearer than letting adapters arbitrarily return `null` or throw an exception when nothing is found?
4. When both an in-memory adapter and a JDBC adapter exist, which part needs to change for Spring to select an implementation?
5. Why can a unit test using a `Map` not prove that transaction rollback works properly on a database?
6. If an application migrates from JDBC to JPA, what factors besides method signatures must be re-verified?

**Conclusion:** separating data access contracts from implementations means separating *what the business needs* from *how infrastructure executes it*. The service depends on an interface with clear semantics; the adapter uses Spring JDBC/JPA or another source to fulfill that behavior; Spring configuration wires the two together. Real value comes from consistent contracts, clean mapping, intentional transaction design, and testing on both the service and adapter sides.

### Official References

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Dependency Injection: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html
- Spring Data Commons — Repository Abstraction: https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html
