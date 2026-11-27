# Choosing Unit Tests, Repository Tests, and Integration Tests by Goal

In a **Spring Data Relational JDBC** application, a single change can pass through multiple layers: domain rules, application services, repositories, aggregate mapping, the JDBC driver, and the database. Not every test needs to start up all of those layers. Choosing the right scope keeps tests fast, pinpoints failures in the right place, and still protects critical behaviors.

The three common test groups are:

- **Unit test:** tests a single class or a small rule in memory, without needing a Spring context or a database.
- **Repository test:** tests the Spring Data JDBC persistence adapter against a database, focusing on mapping, SQL, and repository behavior.
- **Integration test:** tests multiple components wired together in an application context, typically including services, transactions, repositories, migrations, and a real database.

No single test type completely replaces the other two. Unit tests verify rules quickly; repository tests confirm that mappings and SQL statements work; integration tests prove that components collaborate properly in a near-production configuration.

## 1. Start from the Question You Need to Verify

Before choosing annotations or a test framework, write down clearly what needs to be proven.

| Question | Appropriate Scope |
|---|---|
| Does an order refuse to transition to PAID when not yet confirmed? | Domain unit test |
| Does the repository save and reload the full order along with order lines? | Repository test |
| Does a custom converter convert Money to DECIMAL properly? | Repository test, optionally with a converter unit test |
| Does the migration create FKs, unique constraints, and indexes properly? | Integration test with a compatible database |
| Does the service save the order and audit in the same transaction? | Integration test |
| Does optimistic locking reject a stale update? | Repository test with a database |
| Does an AFTER_COMMIT event run only when the transaction commits? | Integration test |
| Does the endpoint call the service and return the right response? | Application-layer web/integration test |

The same feature may require multiple tests if there are multiple independent risks. For example, payment domain rules can be unit tested, whereas persisting the status and publishing an event after commit require repository/integration tests.

### 1.1. Distinguish Logic Bugs from Integration Bugs

A unit test can prove that a method calculating the total amount returns the right result. However, it does not prove that:

- Spring Data JDBC mapping writes to the right column.
- The converter is registered.
- The JDBC driver supports the data type.
- The database has the appropriate constraints.
- A transaction rolls back all changes.
- The migration runs on the production database version.

Conversely, an end-to-end integration test can catch failures, but it usually takes longer and makes it harder to pinpoint the exact cause. Therefore, place each test at the closest layer that can prove the behavior in question.

## 2. Unit Tests: Testing Domain and Isolated Logic

Unit tests verify a small unit in memory. They typically do not start Spring, create a DataSource, or access a database.

Suitable targets:

- Aggregate state transition rules.
- Validation and invariants in the domain model.
- Price, tax, and discount calculations.
- Business condition selection.
- Pure Java conversion logic.
- Handling results from a mocked dependency.

Example aggregate:

```java
public class PurchaseOrder {

    private OrderStatus status;
    private final List<OrderLine> lines;

    public PurchaseOrder(
            OrderStatus status,
            List<OrderLine> lines) {
        this.status = status;
        this.lines = new ArrayList<>(lines);
    }

    public void markPaid() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "An empty order cannot be paid"
            );
        }

        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a new order can be paid"
            );
        }

        status = OrderStatus.PAID;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

Unit test:

```java
class PurchaseOrderTest {

    @Test
    void marksNonEmptyNewOrderAsPaid() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.NEW,
            List.of(new OrderLine("BOOK-01", 2))
        );

        order.markPaid();

        assertThat(order.getStatus())
            .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void rejectsPaymentForEmptyOrder() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.NEW,
            List.of()
        );

        assertThatThrownBy(order::markPaid)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("empty order");
    }

    @Test
    void rejectsPayingAnAlreadyPaidOrder() {
        PurchaseOrder order = new PurchaseOrder(
            OrderStatus.PAID,
            List.of(new OrderLine("BOOK-01", 2))
        );

        assertThatThrownBy(order::markPaid)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("new order");
    }
}
```

These tests only verify the aggregate's rules. There is no need to mock a repository because no persistence is involved in the behavior under test.

### 2.1. When Should Dependencies Be Mocked?

If an application service orchestrates multiple external ports, a unit test can mock dependencies to verify orchestration decisions.

```java
class PaymentApplicationServiceTest {

    private final PurchaseOrderRepository repository =
        mock(PurchaseOrderRepository.class);

    private final PaymentGateway paymentGateway =
        mock(PaymentGateway.class);

    private final PaymentApplicationService service =
        new PaymentApplicationService(repository, paymentGateway);

    @Test
    void requestsPaymentForTheOrder() {
        PurchaseOrder order = newOrder();
        when(repository.findById(42L))
            .thenReturn(Optional.of(order));

        when(paymentGateway.charge(any()))
            .thenReturn(PaymentResult.approved("PAY-100"));

        service.pay(42L);

        verify(paymentGateway).charge(any());
        verify(repository).save(order);
    }
}
```

This test verifies that the service calls the gateway and saves the aggregate according to the expected flow. It does not prove that a real repository can persist the aggregate. That behavior requires a repository test.

### 2.2. Avoid Mocking Too Deeply

Do not mock internal Spring Data JDBC classes such as `JdbcConverter`, `DataAccessStrategy`, `JdbcTemplate`, or `MappingContext` just to test a real repository. When mocking too deeply, tests easily verify the current implementation rather than the behavior the application needs.

For persistence, using a real test database usually provides more reliable evidence than mocking multiple framework components.

### 2.3. When Unit Tests Are Not Enough

If logic depends on database semantics such as NULL, collation, decimal precision, transaction isolation, generated keys, or FKs, unit tests cannot prove that behavior. Move this verification to a repository or integration test.

## 3. Repository Tests: Verifying Mapping and Persistence

Repository tests focus on how Spring Data JDBC interacts with the database. They verify things that unit tests cannot confirm:

- Entities and aggregates map to the right tables and columns.
- `@Id`, `@Column`, `@Table`, and `@MappedCollection` work properly.
- The aggregate root and its members are saved and reloaded accurately.
- Custom reading/writing converters are applied.
- Query methods and `@Query` return the right results.
- Generated IDs and optimistic locking work.
- Database constraints reject invalid data.

With Spring Boot, the commonly used annotation is `@DataJdbcTest`.

### 3.1. What Does @DataJdbcTest Provide?

`@DataJdbcTest` is a test slice for Spring Data JDBC. By default, Spring Boot creates a limited application context for the persistence layer, configures Spring Data JDBC repositories, `JdbcTemplate`, and an embedded database if an embedded database dependency is on the classpath.

Typically:

- Repositories and entities are included in the test context.
- Configurations extending `AbstractJdbcConfiguration` are considered.
- Regular application components are not automatically scanned as in `@SpringBootTest`.
- Tests run in a transaction and roll back when the test finishes.
- `@AutoConfigureTestDatabase` can be used to control which DataSource is used.

The import for `@DataJdbcTest` differs across Spring Boot generations. For Spring Boot 3.x, the package is typically `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest`. For newer Spring Boot lines that split test modules, use the package specified by your project version's documentation.

### 3.2. Example: Testing Saving and Loading an Aggregate

Aggregate:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            List<OrderLine> lines) {
        this.orderNumber = orderNumber;
        this.lines = new ArrayList<>(lines);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
```

Member:

```java
public class OrderLine {

    @Id
    private Long id;

    private String productCode;
    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(String productCode, int quantity) {
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Repository test:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void savesAndLoadsTheCompleteAggregate() {
        PurchaseOrder order = new PurchaseOrder(
            "ORD-1001",
            List.of(
                new OrderLine("BOOK-01", 2),
                new OrderLine("PEN-02", 5)
            )
        );

        PurchaseOrder saved = repository.save(order);

        assertThat(saved.getId()).isNotNull();

        PurchaseOrder loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getOrderNumber())
            .isEqualTo("ORD-1001");

        assertThat(loaded.getLines())
            .extracting(OrderLine::getProductCode)
            .containsExactly("BOOK-01", "PEN-02");

        assertThat(loaded.getLines())
            .extracting(OrderLine::getQuantity)
            .containsExactly(2, 5);
    }
}
```

This test proves that Spring Data JDBC saves and loads the aggregate according to the declared mapping. It can catch wrong table/column names, missing schema, wrong `idColumn`, or incorrect member mapping.

### 3.3. Testing Custom Converters

Suppose the domain uses an `EmailAddress` value object, while the database stores a VARCHAR string. A repository test should verify both directions:

1. Save an aggregate containing `EmailAddress`.
2. Read the aggregate from the database.
3. Verify that the domain value is accurately restored.

```java
@DataJdbcTest
@Import(CustomerJdbcConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void writesAndReadsEmailAddress() {
        Customer customer = new Customer(
            new EmailAddress("an@example.com")
        );

        Customer saved = repository.save(customer);

        Customer loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmail())
            .isEqualTo(new EmailAddress("an@example.com"));
    }
}
```

`@Import` brings additional configuration into the test slice if that configuration is not automatically discovered. For converter configuration, verify the exact registration mechanism for the Spring Data JDBC version in use.

### 3.4. Testing Query Methods

Example repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);

    boolean existsByOrderNumber(String orderNumber);

    long countByStatus(OrderStatus status);
}
```

The repository test should create multiple records with different statuses, then verify that the query returns only rows matching the condition.

```java
@Test
void findsOnlyOrdersWithRequestedStatus() {
    repository.save(newOrder("ORD-1"));
    repository.save(paidOrder("ORD-2"));

    List<PurchaseOrder> paid =
        repository.findByStatus(OrderStatus.PAID);

    assertThat(paid)
        .extracting(PurchaseOrder::getOrderNumber)
        .containsExactly("ORD-2");
}
```

If a query depends on database-specific data types or syntax, run the test against the corresponding dialect.

### 3.5. Testing Database Constraints

You can use `JdbcTemplate` in a repository test to directly attempt inserting a row that violates a constraint. This proves that the database genuinely enforces the rule, rather than only verifying domain validation.

```java
@DataJdbcTest
class OrderConstraintTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rejectsDuplicateOrderNumber() {
        insertOrder("ORD-1001");

        assertThatThrownBy(() -> insertOrder("ORD-1001"))
            .isInstanceOf(DataIntegrityViolationException.class);
    }

    private void insertOrder(String orderNumber) {
        jdbcTemplate.update(
            "INSERT INTO purchase_orders(order_number) VALUES (?)",
            orderNumber
        );
    }
}
```

The test requires a schema with the corresponding unique constraint. If an embedded database does not fully support production syntax or semantics, move this test to an appropriate database.

## 4. Should Repository Tests Use an Embedded Database or a Real Database?

An embedded database such as H2 is useful because it:

- Starts quickly.
- Is easy to run in CI.
- Requires no separate database installation.
- Fits basic mapping and CRUD verification.
- Can create a fresh database for each test context.

However, an embedded database does not guarantee full compatibility with production.

Differences may appear in:

- SQL syntax.
- Data types and conversions.
- Identity, sequences, and generated keys.
- JSON, ARRAY, and vendor-specific types.
- Collation and string comparison.
- NULL and unique semantics.
- Foreign keys, cascades, and deferred constraints.
- Locking and isolation.
- Execution plans and indexes.

Therefore, do not treat a test passing on H2 as complete proof that the application will work on PostgreSQL, MySQL, Oracle, or SQL Server.

### 4.1. When Is an Embedded Database Enough?

H2 is usually sufficient for simple mapping checks if the application uses common SQL types and does not rely on vendor-specific behavior.

For example:

- Saving and loading a simple aggregate.
- Testing repository CRUD.
- Testing a converter from String to a value object.
- Testing basic equality queries.
- Testing dialect-independent domain-to-database mapping.

### 4.2. When Is a Production-Compatible Database Needed?

Use a database of the same engine and compatible version when tests involve:

- Sequence or identity behavior.
- Custom SQL and vendor-specific syntax.
- JSONB, ARRAY, UUID, or spatial types.
- Locking, transaction isolation, and concurrency.
- Migrations with vendor-specific syntax.
- Constraints or indexes with specific semantics.
- Query plans or performance.

In these cases, Testcontainers is usually the right choice.

## 5. Integration Tests: Verifying Multiple Collaborating Components

Integration tests verify multiple layers working together inside an application context. With Spring Data JDBC, an integration test can span:

```text
HTTP Controller
      |
Application Service
      |
Repository / JdbcAggregateTemplate
      |
JdbcConverter / DataAccessStrategy
      |
DataSource / JDBC Driver
      |
Database
```

The goal is to confirm the actual behavior of a use case in a configuration close to the deployed application.

Integration tests are suited for checking:

- Services coordinating multiple repositories.
- Transactions spanning multiple persistence operations.
- Rollback when one step fails.
- Events processed only after commit.
- Outbox records written together with the aggregate.
- Flyway/Liquibase migrations running on the target database.
- Custom converter, dialect, and DataSource configuration.
- Wiring between controller, service, and persistence.

### 5.1. Using @SpringBootTest

`@SpringBootTest` starts the Spring application context to verify application configuration and beans.

```java
@SpringBootTest
class CheckoutServiceIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Test
    void completesCheckout() {
        Long orderId = checkoutService.checkout(testOrder());

        PurchaseOrder saved = orderRepository.findById(orderId)
            .orElseThrow();

        assertThat(saved.getStatus())
            .isEqualTo(OrderStatus.NEW);
    }
}
```

This example verifies that the service and repository are wired together in the Spring context. With an embedded database, it still does not fully prove compatibility with the production database.

### 5.2. Using Testcontainers

Testcontainers creates a database in a container so that tests use the real JDBC driver and database engine.

PostgreSQL example with Spring Boot `@ServiceConnection` support:

```java
@Testcontainers
@SpringBootTest
class CheckoutPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    CheckoutService checkoutService;

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void persistsOrderUsingPostgres() {
        Long id = checkoutService.checkout(testOrder());

        PurchaseOrder loaded = repository.findById(id)
            .orElseThrow();

        assertThat(loaded.getId()).isEqualTo(id);
    }
}
```

This configuration requires the Testcontainers PostgreSQL dependency and the `spring-boot-testcontainers` module when using Spring Boot service connections. `@ServiceConnection` was introduced in Spring Boot 3.1; match packages and modules to your project's Boot version.

If using the `@DataJdbcTest` slice with a container, ensure auto-configuration does not replace the container DataSource with an embedded database. You can use `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)` when the test configuration needs to keep the declared DataSource.

### 5.3. Running Migrations in Integration Tests

If production uses Flyway or Liquibase, integration tests should use the same migrations to verify the real schema.

Workflow:

1. Start a clean database container.
2. Create the DataSource from the container.
3. Run migrations.
4. Initialize repositories and services.
5. Execute the use case.
6. Read back the data and verify the result.

Do not maintain a hand-written test schema that differs completely from the production schema. Doing so can let tests pass even when the real migration is broken or missing constraints.

## 6. Testing Transactions and Rollback

Transactions are one of the behaviors that require integration tests when using Spring Data JDBC.

Example service:

```java
@Service
public class CheckoutService {

    private final PurchaseOrderRepository orders;
    private final JdbcTemplate jdbcTemplate;

    public CheckoutService(
            PurchaseOrderRepository orders,
            JdbcTemplate jdbcTemplate) {
        this.orders = orders;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public Long checkout(PurchaseOrder order) {
        PurchaseOrder saved = orders.save(order);

        jdbcTemplate.update(
            "INSERT INTO order_audit(order_id, action) VALUES (?, ?)",
            saved.getId(),
            "CHECKOUT"
        );

        return saved.getId();
    }
}
```

An integration test must prove that both changes roll back together when the audit step fails.

```java
@Test
void rollsBackOrderWhenAuditInsertFails() {
    assertThatThrownBy(() ->
        checkoutService.checkout(orderThatCausesAuditFailure())
    ).isInstanceOf(DataAccessException.class);

    assertThat(orderRepository.findByOrderNumber("ORD-FAIL"))
        .isEmpty();
}
```

The test assumes data or constraints can be configured so that the audit insert fails. The goal is to confirm that the order is not committed separately before the entire use case completes.

### 6.1. Pay Attention to the Test's Own Transaction

`@DataJdbcTest` runs each test in a transaction by default and rolls back when finished. This is convenient for repository tests.

However, if an integration test needs to observe a transaction opened by the service itself—especially with `AFTER_COMMIT`—do not accidentally wrap the entire test in an outer transaction.

You can disable the test transaction for a method or class:

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class TransactionBoundaryIntegrationTest {
    // The service will open its own transaction via Spring proxy.
}
```

Then the service's transaction actually commits or rolls back before the test reads the data back.

### 6.2. Testing Rollback and Exceptions

Spring rolls back by default on `RuntimeException` and `Error`; checked exceptions do not roll back by default unless `rollbackFor` is configured.

Tests should reflect the service's actual policy. If an exception is caught and not rethrown, the transaction may commit. Verify the exact exception path.

## 7. Testing Optimistic Locking

If an aggregate uses `@Version`, a repository test should verify that two reads of the same version cannot overwrite each other without detecting the conflict.

Example:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
```

Scenario:

1. Read the same order into two independent objects.
2. Update and save the first object.
3. Try to save the second object with the stale version.
4. Verify that Spring Data JDBC throws `OptimisticLockingFailureException`.

```java
@Test
void rejectsStaleAggregateUpdate() {
    PurchaseOrder first = repository.findById(42L).orElseThrow();
    PurchaseOrder second = repository.findById(42L).orElseThrow();

    first.setStatus("PAID");
    repository.save(first);

    second.setStatus("CANCELLED");

    assertThatThrownBy(() -> repository.save(second))
        .isInstanceOf(OptimisticLockingFailureException.class);
}
```

This behavior depends on the database update and the version column, so it requires a repository test with a real database.

## 8. Testing Custom Queries and SQL

If a repository uses query methods or `@Query`, choose the test scope based on the SQL complexity.

- Simple property-based queries can be tested with `@DataJdbcTest`.
- Queries with joins, projections, or vendor-specific SQL should be tested on a production-compatible database.
- Queries returning an aggregate must provide all required columns for mapping.
- Queries with LIMIT, OFFSET, named parameters, or custom SQL expressions must be verified with a real JDBC driver.

Example:

```java
@Query("""
    SELECT *
    FROM purchase_orders
    WHERE status = :status
      AND created_at >= :from
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
    String status,
    LocalDateTime from
);
```

Tests should seed data on both sides of the date and status conditions, then verify the results. Do not just assert that the list is non-empty, because that test could pass even if the query filters incorrectly.

## 9. Testing Lifecycle Callbacks and Domain Events

If an aggregate uses callbacks or events, tests should separate two questions:

- Does the repository trigger callbacks/event publication properly?
- Is the listener invoked in the right transaction phase?

Repository tests can verify mapping callbacks such as `BeforeConvertCallback` or `AfterSaveCallback`.

Integration tests are better suited when you need to prove that `@TransactionalEventListener(AFTER_COMMIT)` runs only after commit:

1. Call the service inside a transaction.
2. Confirm the listener has not run before commit.
3. Let the transaction commit.
4. Confirm the listener was called.
5. Run a rollback case and confirm the AFTER_COMMIT listener does not execute.

If the listener sends a message to a broker, add a test for that integration or use an outbox test to verify the record is written in the same transaction. Do not use a mock listener to conclude that the broker received the message.

## 10. Testing Repositories and Services with Clear Boundaries

You can organize tests with a structure like:

```text
src/test/java/
  domain/
    PurchaseOrderTest.java
    MoneyTest.java

  persistence/
    PurchaseOrderRepositoryTest.java
    CustomerRepositoryTest.java
    JdbcConverterTest.java

  integration/
    CheckoutServiceIntegrationTest.java
    TransactionBoundaryIntegrationTest.java
    MigrationIntegrationTest.java
```

Package names can follow your project's structure. What matters is that each test class has one clear purpose.

### 10.1. Unit Tests Need No Database

Place tests for domain objects and pure Java logic in the unit test layer. These tests run fast without needing a database profile or migrations.

### 10.2. Repository Tests Do Not Need the Whole Application

Use `@DataJdbcTest` for the persistence slice. Import only the additional configurations that are genuinely needed.

### 10.3. Integration Tests Need a Near-Production Configuration

Use `@SpringBootTest` and Testcontainers when you need to verify services, transactions, migrations, or dialect configuration. You can group expensive tests into a separate CI task/profile if pipeline duration is a concern.

## 11. Choose Tests by Risk, Not by Count

You do not need to write all three test types for every method. Choose based on the risk of the behavior:

| Behavior | Unit | Repository | Integration |
|---|---:|---:|---:|
| Domain state transition | Primary | Not needed | Depends on use case |
| Pure Java total calculation | Primary | Not needed | Not needed |
| Aggregate mapping | Insufficient | Primary | Optional supplement |
| Custom converter | Can test separately | Primary | When vendor-dependent |
| Repository query | Insufficient | Primary | When SQL is complex |
| Unique/FK/CHECK | Insufficient | Primary | With production database |
| Flyway/Liquibase migration | Insufficient | Possible | Primary |
| Multi-repository transaction | Insufficient | Insufficient | Primary |
| AFTER_COMMIT listener | Insufficient | Partial | Primary |
| API + service + database | Insufficient | Insufficient | Primary |

A practical rule of thumb:

- If a behavior requires neither Spring nor a database, write a unit test.
- If the question involves persistence, write a repository test.
- If you need to verify multiple beans, transactions, migrations, or database vendor behavior, write an integration test.

## 12. Common Mistakes When Choosing Test Scope

| Symptom | Cause | Fix |
|---|---|---|
| Unit tests pass but repository writes to wrong column | No mapping test | Add `@DataJdbcTest` |
| H2 passes but PostgreSQL fails | Dialect differences | Use PostgreSQL Testcontainers |
| `@DataJdbcTest` cannot find service | Slice does not scan regular components | Use `@Import` or `@SpringBootTest` if needed |
| Test converter is not applied | Converter configuration not included in slice | Import configuration or check `AbstractJdbcConfiguration` |
| Transaction test does not see commit | Test opens its own outer transaction | Use `Propagation.NOT_SUPPORTED` when observing real commits |
| Production migration fails while tests pass | Tests use custom schema different from migrations | Run real migrations in tests |
| Tests depend on fixed IDs | Sequences/identity do not guarantee contiguous numbers | Assert valid IDs or data relationships only |
| Repository tests are too slow | Starting full context unnecessarily | Use `@DataJdbcTest` |
| Integration test is too hard to debug | Packing too many behaviors into one test | Separate domain, persistence, and use case tests |
| Mocking too many framework internals | Test verifies internal implementation | Use a test database for persistence |
| Tests depend on execution order | Shared data or unclear cleanup | Use transaction rollback or isolated fixtures |
| Concurrency test fails to reproduce race condition | Running sequentially only | Use multiple transactions/threads and a real database |

## 13. Example of a Complete Test Suite for a Payment Feature

Suppose the payment feature has three requirements:

1. An empty order cannot be paid.
2. The PAID status must be persisted.
3. An audit record is written in the same transaction as the order change.

They can be split as follows.

### 13.1. Domain Unit Test

```java
@Test
void emptyOrderCannotBePaid() {
    PurchaseOrder order = emptyNewOrder();

    assertThatThrownBy(order::markPaid)
        .isInstanceOf(IllegalStateException.class);
}
```

This test verifies the aggregate invariant.

### 13.2. Repository Test

```java
@DataJdbcTest
class PurchaseOrderPersistenceTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void persistsPaidStatus() {
        PurchaseOrder order = newNewOrder();
        order.markPaid();

        PurchaseOrder saved = repository.save(order);

        PurchaseOrder loaded = repository.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getStatus())
            .isEqualTo(OrderStatus.PAID);
    }
}
```

This test verifies status mapping and persistence.

### 13.3. Transaction Integration Test

```java
@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class PaymentTransactionIntegrationTest {

    @Autowired
    PaymentService paymentService;

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackOrderWhenAuditFails() {
        PurchaseOrder order = createOrderWithAuditConflict();

        assertThatThrownBy(() ->
            paymentService.pay(order.getId())
        ).isInstanceOf(DataAccessException.class);

        PurchaseOrder reloaded = orderRepository
            .findById(order.getId())
            .orElseThrow();

        assertThat(reloaded.getStatus())
            .isEqualTo(OrderStatus.NEW);
    }
}
```

This test assumes conditions can be set up to make the audit step violate a constraint. It tests the service transaction with the repository, JDBC, and database together.

The test suite above avoids using one giant test to prove everything at once. Each test has a single objective, so when a failure occurs it is easy to identify which layer needs fixing.

## 14. CI Integration

A pipeline can group tests by cost:

```text
Pull request:
  1. Compile
  2. Unit tests
  3. Repository tests with embedded database
  4. Critical integration tests with Testcontainers

Main branch / nightly:
  1. Full test suite
  2. Integration tests per supported database
  3. Migration compatibility tests
  4. Concurrency or performance tests requiring dedicated environments
```

Not every project needs every group. Choose based on the number of supported databases, persistence complexity, and business risk.

### 14.1. Keep Test Data Independent

Each test should create the data it needs and avoid relying on execution order. Use IDs returned by the repository instead of assuming sequences start at a fixed number.

If tests need baseline data, use explicit fixtures or SQL scripts. Avoid using a database containing development data as a test source.

### 14.2. Run Migrations on a Clean Database

CI should have at least one path that runs migrations from an empty schema on a production-compatible database. This catches DDL errors that unit tests or H2 might miss.

For projects supporting multiple dialects, you can create matrix jobs for each major database rather than checking only one engine.

## 15. Practice Exercises

**Exercise 1.** A domain method rejects payment when an order is empty. Which test type should be used?

*Answer:* A unit test, because this is a pure Java domain rule.

**Exercise 2.** You want to prove that `@MappedCollection` saves and reloads child rows properly. Which test type is needed?

*Answer:* A repository test with `@DataJdbcTest` and a database.

**Exercise 3.** You want to verify that a custom converter works with PostgreSQL JSONB. What should you use?

*Answer:* A repository/integration test with a production-compatible PostgreSQL instance, typically via Testcontainers.

**Exercise 4.** Does `@DataJdbcTest` automatically load all application services?

*Answer:* No. It is a test slice for Spring Data JDBC; regular components must be imported or tested using the full application context.

**Exercise 5.** Why do repository tests roll back by default after each test?

*Answer:* Spring Boot configures `@DataJdbcTest` with test transactions so data does not leak to other tests. This is not proof that a service transaction committed.

**Exercise 6.** You need to confirm that a service saves an order and audit in the same transaction. Which test type should be used?

*Answer:* An integration test with the service, repository/JDBC, and a real database; intentionally fail one step and confirm all changes roll back.

**Exercise 7.** Why does passing on H2 not prove passing on PostgreSQL?

*Answer:* The two databases can differ in SQL dialect, type mapping, sequences, locking, constraints, and transaction semantics.

**Exercise 8.** When is `@SpringBootTest` needed instead of `@DataJdbcTest`?

*Answer:* When you need to test multiple beans and application configuration such as services, transactions, event listeners, security, or HTTP flows.

**Exercise 9.** A test checks whether a query returns the right rows without checking the execution plan. Does that test prove the query is optimized?

*Answer:* Not yet. Correct results prove filtering logic; performance requires representative data, execution plans, and proper measurement.

## 16. Key Takeaways

- **Unit tests** are for domain logic and pure Java code; they run fast and need no Spring context or database.
- **Repository tests** use `@DataJdbcTest` to verify aggregate mapping, converters, queries, generated IDs, constraints, and optimistic locking.
- **Integration tests** use `@SpringBootTest` when verifying services, transactions, migrations, events, or multiple collaborating beans.
- `@DataJdbcTest` typically uses an embedded database and rolls back the transaction after each test; this is convenient for a persistence slice but does not prove production dialect behavior.
- Use Testcontainers when behavior depends on the database engine, JDBC driver, vendor-specific SQL, or transaction semantics.
- Use real migrations in tests so that the schema is verified the same way it is deployed.
- Do not mock all Spring Data JDBC internals to simulate persistence; verify mapping against a real database.
- Disable the test's transaction with `Propagation.NOT_SUPPORTED` when observing commits managed by a service.
- Split tests by objective so failures are easy to diagnose and pipelines stay fast.
- Choose tests based on risk and the behavior to prove, not based on test count per class.

### Official References

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@DataJdbcTest`, `@JdbcTest`, `@SpringBootTest`, and test slice transaction behavior.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): container management and service connections in integration tests.
- [Spring Boot 3.5 — DataJdbcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html): component scan scope, embedded databases, and default rollback.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): integration testing support with the Spring TestContext Framework.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): aggregate mapping and relational data in Spring Data JDBC.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): starting a PostgreSQL container for tests.

When choosing, start from the behavior you need to prove: pure Java logic gets unit tests; mapping and SQL get repository tests; transactions, migrations, and collaborating components get integration tests on a production-compatible database.
