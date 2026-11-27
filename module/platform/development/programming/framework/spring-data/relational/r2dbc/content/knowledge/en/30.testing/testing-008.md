# Testing Rollback Without Assuming JDBC Test Transaction Semantics

When testing Spring Data Relational R2DBC, do not assume test transactions behave like transactions in Spring JDBC or JPA. Traditional JDBC tests usually rely on `PlatformTransactionManager` with transactions bound to the current thread. R2DBC uses `ReactiveTransactionManager`; transactions propagate via Reactor Context and cover only reactive operations actually subscribed within that context.

Therefore, a test method annotated with `@Transactional` or `@Rollback` does not by itself prove that an R2DBC publisher rolls back. You must verify the actual transaction manager, `ConnectionFactory`, and subscription boundaries. An explicit way to test this is wrapping the entire write publisher with `TransactionalOperator`, intentionally emitting an error to trigger rollback, and then querying again in a fresh subscription outside the transaction to confirm data was not committed.

## 1. Why Can't JDBC Testing Patterns Be Copied Directly to R2DBC?

In the imperative JDBC model, a test can run inside a transaction managed by Spring Test. The connection is typically bound to the thread via transaction synchronization. When the test ends, a listener rolls back the transaction so no data persists after the test.

R2DBC is reactive and does not rely on a fixed thread. A transaction is managed by `ReactiveTransactionManager`, and transaction state travels inside Reactor Context. Repository/`DatabaseClient` operations must belong to the reactive chain covered by the transaction.

| Aspect | Traditional JDBC test | R2DBC reactive test |
| --- | --- | --- |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager`, typically `R2dbcTransactionManager` |
| Context | Usually bound to the current thread | Reactor Context |
| Operation API | Synchronous JDBC calls | `Mono`/`Flux` and subscriptions |
| Completion boundary | Test method/transaction listener | Publisher completion, error, or cancellation |
| Rollback mechanism | Test framework can roll back test-managed transaction | Reactive transaction manager rolls back on reactive signals inside the boundary |
| How to verify | Read back after the test transaction ends | Subscribe to a new query after `TransactionalOperator` finishes |

The key point is that `@Transactional` on a test method does not automatically make every publisher created inside that method part of a reactive transaction. A publisher might only be subscribed to later by `StepVerifier`, and a JDBC-style test transaction does not automatically carry over into that reactive subscription.

## 2. `@Transactional` and `@Rollback` in Tests Must Be Understood Accurately

In JDBC/JPA tests, a familiar pattern is:

```java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {

    @Test
    void createsCustomer() {
        // Synchronous JDBC/JPA work inside a test-managed transaction.
        // Spring Test rolls back the transaction when the test ends.
    }
}
```

Do not copy this pattern to R2DBC and assume it automatically rolls back publishers:

```java
@SpringBootTest
@Transactional
class CustomerR2dbcTest {

    @Test
    void createsCustomer() {
        StepVerifier.create(customerRepository.save(customer))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

The second snippet does not by itself prove that a test-managed transaction wrapped the R2DBC publisher. Test transaction support depends on the Spring Framework/Spring Boot version and how test infrastructure is configured. Do not infer behavior from JDBC `@Transactional` or `@Rollback`.

If your project's version and test slice support reactive test transactions, check the documentation for that exact version and verify with a real rollback test. When you want an explicit boundary independent of assumptions about test listeners, use `TransactionalOperator` directly in the test.

`@DataR2dbcTest` is useful for configuring repositories and R2DBC infrastructure for a slice test, yet you still need to check the transaction semantics provided by your specific version. A test slice annotation does not replace verifying the connection factory and reactive transaction boundaries.

## 3. Reactive Transactions Are Attached to Reactor Context

`R2dbcTransactionManager` manages a `ConnectionFactory`. When `TransactionalOperator` begins a transaction, the manager acquires a connection, opens a transaction, and attaches the resource to the reactive context. Compatible Spring R2DBC operations in the same chain can reuse that managed connection.

Configuration example:

```java
@TestConfiguration
class R2dbcTestTransactionConfiguration {

    @Bean
    R2dbcTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            R2dbcTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

In an application that already defines a transaction manager, inject the existing bean rather than redeclaring it. What matters is that the operator uses the exact same `ConnectionFactory` as the repository, `R2dbcEntityTemplate`, or `DatabaseClient` under test.

Do not build a `TransactionalOperator` with factory A and expect a repository using factory B to join the transaction. Likewise, do not acquire a raw connection directly from the factory mid-transaction if doing so bypasses Spring's transaction-aware connection lookup.

## 4. Testing Rollback Explicitly with `TransactionalOperator`

A reliable rollback test has four steps:

1. Create a write publisher.
2. Chain an intentional error after writes complete.
3. Wrap the entire publisher with `TransactionalOperator`.
4. Wait for the publisher to terminate with the error, then query again outside the transaction to verify the data does not exist.

Example with `DatabaseClient`:

```java
class ForcedRollbackException extends RuntimeException {
}

@SpringBootTest
class R2dbcRollbackIntegrationTest {

    @Autowired
    DatabaseClient databaseClient;

    @Autowired
    TransactionalOperator transactionalOperator;

    @Test
    void rollsBackInsertWhenPublisherFails() {
        String email = "rollback-" + UUID.randomUUID() + "@example.test";

        Mono<Void> writeThenFail = databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Rollback candidate')
                """)
                .bind("email", email)
                .fetch()
                .rowsUpdated()
                .then(Mono.error(new ForcedRollbackException()));

        StepVerifier.create(transactionalOperator.transactional(writeThenFail))
                .expectError(ForcedRollbackException.class)
                .verify();

        Mono<Long> count = databaseClient.sql("""
                SELECT COUNT(*) AS total
                FROM customer
                WHERE email = :email
                """)
                .bind("email", email)
                .map((row, metadata) -> row.get("total", Long.class))
                .one();

        StepVerifier.create(count)
                .expectNext(0L)
                .verifyComplete();
    }
}
```

The test runs an insert inside the transaction, then emits `ForcedRollbackException`. `TransactionalOperator` sees the publisher end with `onError` and rolls back the transaction. The `COUNT` query is subscribed to after `verify()` has waited for the transaction to finish; this query runs outside the rolled-back transaction and verifies zero committed rows.

In a real project, table and column names must match the test schema. The return type of `COUNT(*)` must match the driver/database; if a driver returns a different numeric type, map accordingly. A random email keeps the test independent of seed data and prevents collisions with parallel tests.

## 5. Why Must Verification Use a New Subscription?

If the verification query runs inside the same transaction, it may observe uncommitted changes from that transaction. The test would then fail to prove rollback across the commit boundary.

Unsuitable idea example:

```java
Mono<Boolean> work = databaseClient.sql("INSERT INTO customer ...")
        .fetch()
        .rowsUpdated()
        .then(databaseClient.sql("SELECT ...")
                .map((row, metadata) -> row.get("exists", Boolean.class))
                .one());
```

Here the read query executes inside the same chain/transaction if the whole publisher is wrapped by the same operator. It can see the inserted row before the transaction rolls back.

To verify rollback, wait until `transactionalOperator.transactional(work)` emits its terminal signal, and only then subscribe to a fresh query. This checks the state observed by the database after the transaction finishes.

If the test environment has an outer transaction, such as one opened by the test framework, verify which connection and transaction the verification query uses. Avoid letting an outer transaction mask the rollback outcome of an inner transaction.

## 6. Let Errors Escape the Transaction Boundary

The reactive transaction manager decides commit versus rollback based on the terminal signal of the wrapped publisher. If the publisher completes normally, the transaction normally commits; if it terminates with an error, the transaction rolls back according to rollback rules.

Correct: recover from the error outside `TransactionalOperator`:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
        repository.save(entity)
                .then(Mono.error(new ForcedRollbackException())));

Mono<Void> handledForTest = transactionalWork
        .onErrorResume(ForcedRollbackException.class, error -> Mono.empty());
```

The error crosses the transaction boundary first, causing rollback. Only then does the outer `onErrorResume` convert the error to empty completion if the test needs to continue.

Wrong if the goal is rollback: swallowing the error inside the transaction:

```java
Mono<Void> wrong = transactionalOperator.transactional(
        repository.save(entity)
                .then(Mono.error(new ForcedRollbackException()))
                .onErrorResume(error -> Mono.empty()));
```

Here the error turns into `onComplete` before reaching the transaction operator. The transaction manager can treat the publisher as having completed successfully and commit the change. The test might think it triggered an error while actually verifying the wrong behavior.

When catching errors to assert on them, place assertions after the transaction operator has emitted the error. Do not swallow errors inside the transactional chain unless you explicitly mark rollback-only via the appropriate transaction API.

## 7. Testing Rollback When a Service Uses `@Transactional`

In an application, a service may use the annotation:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Customer> createThenFail(Customer customer) {
        return repository.save(customer)
                .flatMap(saved -> Mono.error(
                        new ForcedRollbackException()));
    }
}
```

Tests should invoke the service through the Spring bean proxy and subscribe to the publisher:

```java
StepVerifier.create(customerService.createThenFail(customer))
        .expectError(ForcedRollbackException.class)
        .verify();
```

Then query again with a new publisher to verify no row was committed. Do not call the method via `new CustomerService(...)` in the test if you want to verify the transaction interceptor; self-invocation or calling an unproxied instance bypasses `@Transactional`.

For reactive methods, the transaction interceptor wraps the returned publisher and attaches the transaction to subscription. The method must return `Mono`/`Flux` for reactive transactions to work properly. If a method calls `subscribe()` internally and returns `Mono.empty()`, the write work detaches from the publisher managed by the interceptor.

## 8. Do Not Mix `PlatformTransactionManager` with `ReactiveTransactionManager`

An application may use both JDBC and R2DBC at the same time. In that case, both may exist:

- `DataSourceTransactionManager` or `JdbcTransactionManager` for JDBC.
- `R2dbcTransactionManager` for R2DBC.

These are two distinct transaction managers managing two distinct resource types. `@Transactional` must specify the right manager when multiple beans exist:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Customer> saveReactive(Customer customer) {
    return customerRepository.save(customer);
}
```

A JDBC transaction does not automatically enlist an R2DBC connection. Nor can you assume a JDBC test rollback will roll back operations performed via R2DBC. If a test uses both stacks, separate boundaries or design appropriate coordination; do not treat them as the same connection just because they target the same database URL.

## 9. `@Sql` and JDBC Test Utilities Are Not Automatically R2DBC

Utilities such as `@Sql`, `JdbcTestUtils`, `TestTransaction`, and many helpers in Spring Test JDBC work with `DataSource`/JDBC. They do not automatically turn into reactive operations just because the application has a `ConnectionFactory`.

If a test uses only R2DBC:

- Use `DatabaseClient`, repositories, or `R2dbcEntityTemplate` to prepare and clean up data.
- Use SQL initialization or migration fixtures configured for the test environment.
- Use `TransactionalOperator` to control reactive transactions.
- Use `StepVerifier` or explicit test subscription mechanisms to wait for completion.

If the application has both a JDBC `DataSource` and an R2DBC `ConnectionFactory`, `@Sql` may execute over a JDBC connection while test code uses an R2DBC connection. They may reach the same database without sharing a transaction. An `@Sql` setup inside a JDBC test transaction does not guarantee an R2DBC repository can see those uncommitted changes. Commit fixtures before R2DBC reads, or use a single consistent fixture mechanism.

## 10. Using `@DataR2dbcTest` Within Its Right Scope

`@DataR2dbcTest` is a test slice focused on R2DBC mapping and repositories. It usually configures R2DBC repositories, entity mapping, and `DatabaseClient` needed for the test. However, do not assume identical transaction behavior to `@DataJpaTest` based solely on annotation naming.

Check according to your Spring Boot version:

- Whether the test slice creates an `R2dbcTransactionManager`.
- Whether `TransactionalOperator` is present or must be defined in test configuration.
- Whether multiple `ConnectionFactory` beans or transaction managers exist.
- Whether test methods are wrapped by a specific reactive test transaction mechanism.
- Which transaction the verification query runs in.

If the goal of the test is rollback, write an explicit rollback test using `TransactionalOperator` and verify state after the transaction finishes. Slice tests narrow context scope, but do not replace reasoning about transaction boundaries.

## 11. Verifying Whether the Same `ConnectionFactory` Is Used

Rollback covers only operations using connections managed by the transaction manager. For instance, if `TransactionalOperator` uses factory A while the repository uses factory B, the test may emit an error while data in B still gets committed.

Check the configuration:

```java
@Bean
R2dbcTransactionManager r2dbcTransactionManager(
        @Qualifier("applicationConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}

@Bean
DatabaseClient databaseClient(
        @Qualifier("applicationConnectionFactory") ConnectionFactory factory) {
    return DatabaseClient.create(factory);
}
```

Repositories, templates, and `DatabaseClient` must be configured with the matching factory. If using a routing factory, the transaction manager must use the same routing factory as the repository; the routing key must be available before the transaction acquires a connection and remain stable throughout the transaction.

With multiple data sources, one `R2dbcTransactionManager` manages one `ConnectionFactory`. Rolling back transaction A does not roll back transaction B. Tests must verify each boundary individually rather than assuming one operator spans all sources.

## 12. Testing Multiple Operations Within the Same Transaction

A meaningful rollback test should perform at least two mutations within the same transaction, then emit an error after both complete. After rollback, verify that neither exists.

```java
Mono<Void> writeTwoRowsThenFail =
        databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Customer A')
                """)
                .bind("email", emailA)
                .fetch()
                .rowsUpdated()
                .then(databaseClient.sql("""
                        INSERT INTO customer (email, display_name)
                        VALUES (:email, 'Customer B')
                        """)
                        .bind("email", emailB)
                        .fetch()
                        .rowsUpdated())
                .then(Mono.error(new ForcedRollbackException()));

StepVerifier.create(transactionalOperator.transactional(writeTwoRowsThenFail))
        .expectError(ForcedRollbackException.class)
        .verify();
```

Then query each email or run a count query matching both values to confirm neither row was committed. This test proves both operations participate in the same transaction. If one operation used a different factory, the test reveals that data in the other source remains after the failure.

## 13. Testing Rollback When Failure Occurs on the Second Operation

Another scenario is when the first operation succeeds and the second fails due to a constraint. The transaction must roll back the first operation if both share the same transaction.

Example:

```java
Mono<Void> work = databaseClient.sql("""
        INSERT INTO customer (email, display_name)
        VALUES (:email, 'First row')
        """)
        .bind("email", uniqueEmail)
        .fetch()
        .rowsUpdated()
        .then(databaseClient.sql("""
                INSERT INTO customer (email, display_name)
                VALUES (:email, 'Duplicate row')
                """)
                .bind("email", uniqueEmail)
                .fetch()
                .rowsUpdated())
        .then();

StepVerifier.create(transactionalOperator.transactional(work))
        .expectError()
        .verify();
```

Both statements use the same email to trigger a unique constraint violation on the second statement. After the error propagates out and the transaction rolls back, a new query must confirm zero rows with that email. This test verifies a real database error, distinct from a synthetic error emitted with `Mono.error`.

In some databases, a constraint error puts the transaction into an aborted/failed state until rollback. Do not attempt a verification query inside the same transaction after an error; let the transaction manager roll back and then run a fresh query.

## 14. Rollback When a Publisher Is Cancelled

A reactive transaction can receive a cancellation signal when the subscriber no longer wants results. The transaction manager handles cancellation according to rollback semantics to avoid committing partially cancelled work. However, the driver and database may need time to cancel statements or release resources.

A cancellation test can use a controlled publisher to cancel after a write operation has run. Conceptual example:

```java
Mono<Void> work = databaseClient.sql("""
        INSERT INTO customer (email, display_name)
        VALUES (:email, 'Cancelled write')
        """)
        .bind("email", email)
        .fetch()
        .rowsUpdated()
        .then(Mono.never());
```

`Mono.never()` keeps the transaction unfinished after the insert. The test can subscribe, wait for the insert to be confirmed via a test synchronization signal or probe, and then cancel the subscription. Afterward, query via a new subscription to verify the row was not committed.

Do not use `Thread.sleep` to guess when the insert ran. Use `Sinks.One`, `CountDownLatch` strictly for test synchronization at necessary boundaries, `StepVerifier` with controlled `thenAwait`, or a confirmation signal emitted after the write operation. Cancellation behavior should be tested on the real driver/database if the application relies on it.

## 15. Rollback-Only and Error Handling

If an error must be handled inside a transaction while still forcing the transaction to roll back, do not simply swallow the error and complete normally. Use the appropriate reactive transaction API to mark the transaction rollback-only, or let the error escape the boundary and handle it outside.

In tests, the simplest and clearest approach is usually:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
        performWrites()
                .then(Mono.error(new ForcedRollbackException())));

return transactionalWork.onErrorResume(error -> {
    // Handle/assert after the transaction boundary has rolled back.
    return Mono.empty();
});
```

If the application needs to return a success response after deciding to roll back, explicitly design rollback-only marking using your version's `ReactiveTransaction`/`TransactionalOperator` API. Do not rely on an exception caught inside the chain to tell the transaction to roll back automatically.

## 16. Testing Commit Failures vs. Failures Inside the Transaction Body

Failures can happen while executing a statement, during commit, or when a connection drops. A test intentionally emitting `Mono.error` after an insert proves rollback due to an in-publisher error, but does not simulate every commit failure scenario.

When commit fails or the connection drops right at commit time, the application cannot be sure whether the database committed or not. From the client perspective, the outcome is indeterminate. For retryable operations, use an idempotency key or unique business key to query status and avoid duplicate side effects.

Key test scenarios include:

- Error before writing: no data exists.
- Error after a write but before commit: transaction rolls back.
- Constraint violation on a subsequent operation: entire transaction rolls back.
- Commit error or connection loss: verify database state and application recovery.
- Retry after indeterminate outcome: no duplicate resources or side effects created.

Do not simulate a commit failure merely by throwing an exception in the service and conclude you tested driver commit failures. Those two events happen at different stages.

## 17. Setting Up and Cleaning Up Test Data with R2DBC

Do not use JDBC fixtures and assume they belong to the same transaction as R2DBC. Create data using `DatabaseClient`:

```java
Mono<Long> insertFixture(String email) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, 'Fixture')
            """)
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
```

And clean up with R2DBC:

```java
Mono<Long> deleteFixture(String email) {
    return databaseClient.sql("DELETE FROM customer WHERE email = :email")
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
```

In tests, you must subscribe so the operation executes:

```java
StepVerifier.create(insertFixture(email))
        .expectNext(1L)
        .verifyComplete();
```

JUnit's `@BeforeEach`/`@AfterEach` are synchronous callbacks; calling a method returning `Mono` and discarding the publisher means the operation will not run. Use `StepVerifier.verify()` or an appropriate test waiting mechanism to finish fixture setup/cleanup before the test proceeds.

## 18. Isolating Data Across Tests

If not relying on test-managed rollback, you need a data isolation strategy:

- Generate a unique ID/email/key per test.
- Use a dedicated schema or database per test suite if suitable.
- Clean up data via R2DBC in `@AfterEach` and await publisher completion.
- Use explicit transactions for each scenario needing rollback.
- Never let parallel tests share a key or delete each other's rows.
- Respect foreign keys and cleanup ordering.

A rollback test can use a record with a unique key, then query to verify the row count is 0. Other passing tests should use their own fixtures. This keeps tests order-independent and avoids false positives from leftover rows from previous runs.

## 19. Using Testcontainers to Verify Real Database Behavior

H2 or mocks cannot fully represent transactions, locking, constraints, and drivers of production PostgreSQL/MySQL. If production runs PostgreSQL R2DBC, integration tests should run against a compatible PostgreSQL instance, for example via Testcontainers.

Testcontainers helps verify:

- Real R2DBC URL/driver behavior.
- Transaction begin/commit/rollback.
- Unique/foreign key/check constraints.
- Data types and mapping.
- Behavior when connections close or statements fail.
- Pool and transaction manager configuration.

You do not need a container for every unit test. Use fast tests for pure Java logic and integration tests with a real database for driver/database-dependent behavior. Ensure containers/databases start before the Spring context creates `ConnectionFactory` and are cleaned up after the test suite completes.

## 20. Testing Transactions Through the Service Proxy

When the goal is testing `@Transactional` on a service, invoke the Spring-managed bean rather than constructing an instance manually. Example:

```java
@SpringBootTest
class CustomerServiceTransactionTest {

    @Autowired
    CustomerService customerService;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void serviceTransactionRollsBackOnError() {
        Customer customer = new Customer(
                null,
                "rollback-" + UUID.randomUUID() + "@example.test");

        StepVerifier.create(customerService.createThenFail(customer))
                .expectError(ForcedRollbackException.class)
                .verify();

        StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
                .expectNext(false)
                .verifyComplete();
    }
}
```

The `createThenFail` method must be annotated with `@Transactional` pointing to the right reactive transaction manager and return the publisher. The `existsByEmail` query runs after the service transaction has finished. If the service catches errors and returns success inside the transaction, adjust the test to verify rollback-only behavior per contract.

## 21. Checking Multiple Transaction Managers

If the test context contains both JDBC and R2DBC or multiple `ConnectionFactory` beans, specify the right manager:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> reactiveOperation() {
    return customerRepository.save(customer).then();
}
```

A `TransactionalOperator` bound to a different manager may open a transaction on another database. If the repository uses factory A while the operator uses factory B, the test will reveal that inserts do not roll back as expected.

Each `R2dbcTransactionManager` manages a single `ConnectionFactory`. Do not assume one reactive transaction spans multiple independent databases. If a workflow writes to multiple sources, test each local transaction and coordination pattern such as outbox/saga; rolling back one source does not automatically roll back another.

## 22. Transaction Tests and Async Operations Outside the Publisher

A common mistake is creating a secondary publisher and subscribing to it separately:

```java
Mono<Void> operation = customerRepository.save(customer)
        .doOnNext(saved -> auditRepository.save(
                Audit.created(saved.getId())).subscribe())
        .then();
```

The test may wait for `operation` to complete while the audit publisher still runs independently. It could commit outside the transaction or finish after test cleanup. When both operations must share the same transaction, chain them together:

```java
Mono<Void> operation = customerRepository.save(customer)
        .flatMap(saved -> auditRepository.save(
                Audit.created(saved.getId())))
        .then();
```

To roll back together, both repositories must use the same `ConnectionFactory` managed by the transaction manager. Chaining publishers is necessary to preserve order and errors, though insufficient if they target two different data sources.

## 23. Reading Verification Data Outside the Transaction

After rollback, verification queries should:

- Be created and subscribed to after `TransactionalOperator.transactional(...)` emits a terminal signal.
- Target the same database/schema used by the write operation.
- Not participate in an uncommitted outer transaction that could mask results.
- Filter by the test's unique key, avoiding whole-table counts on shared data.
- Check both row counts and related state when writes touch multiple tables.

Example checking two tables:

```java
Mono<Long> customerCount = customerRepository.countByEmail(email);
Mono<Long> auditCount = auditRepository.countByCorrelationId(correlationId);

StepVerifier.create(Mono.zip(customerCount, auditCount))
        .assertNext(counts -> {
            assertThat(counts.getT1()).isZero();
            assertThat(counts.getT2()).isZero();
        })
        .verifyComplete();
```

The queries execute after rollback and confirm neither change persists. If one repository used a different factory, results will expose that the transaction did not cover it.

## 24. Rollback Tests Should Not Assert Only That a Publisher Emits an Error

A test that only does this:

```java
StepVerifier.create(service.createThenFail(command))
        .expectError()
        .verify();
```

proves only that the publisher emits an error as expected. It does not prove data rolled back. The service might have written on an un-transactional connection, selected the wrong transaction manager, or subscribed separately to a secondary operation.

A complete rollback test must verify database state after the transaction. Also include a success test proving the same pipeline commits when completing normally; if you only test rollback, you could accidentally write code that always rolls back and still pass.

## 25. Testing Commit and Rollback as Symmetric Branches

Commit test:

```java
StepVerifier.create(transactionalOperator.transactional(
                customerRepository.save(customer)))
        .expectNextCount(1)
        .verifyComplete();

StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
        .expectNext(true)
        .verifyComplete();
```

Rollback test:

```java
StepVerifier.create(transactionalOperator.transactional(
                customerRepository.save(customer)
                        .then(Mono.error(new ForcedRollbackException()))))
        .expectError(ForcedRollbackException.class)
        .verify();

StepVerifier.create(customerRepository.existsByEmail(customer.getEmail()))
        .expectNext(false)
        .verifyComplete();
```

Both tests use distinct data. The commit branch proves a normally completing transaction persists data; the rollback branch proves an error inside the boundary does not commit changes.

## 26. Isolation Levels and Verification Order

When testing rollback, verification queries must run after the transaction ends. The isolation levels of write and read transactions affect visibility of uncommitted data, yet you should never rely on reading inside the same transaction to conclude commit/rollback.

When using two concurrent connections, a query on another connection typically cannot see uncommitted changes under common isolation levels like READ COMMITTED. Even so, tests need not infer from in-flight state; wait until the transaction completes and query again.

For race conditions or concurrent transactions, write dedicated tests with two subscriptions and appropriate barriers. Never use sleep to assume ordering. Verify final outcomes via constraints and durable state.

## 27. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming test `@Transactional` matches JDBC | R2DBC publisher may not join test-managed transaction | Use `TransactionalOperator` or verify reactive test support for your exact version |
| Treating `@Rollback` as proof of R2DBC rollback | JDBC test listener may not manage reactive connections | Check transaction manager and verify database state |
| Creating a publisher without subscribing | SQL never executes, test may give false results | Use `StepVerifier` or an appropriate test subscriber |
| Wrapping the wrong `ConnectionFactory` | Repository uses a connection outside the transaction | Use the same factory for manager and tested operations |
| Running verification query inside the transaction | Observes uncommitted data | Wait for transaction completion, then query in a fresh subscription |
| Swallowing errors inside the transaction | Publisher completes normally and transaction may commit | Let errors escape the boundary or mark rollback-only |
| Calling `subscribe()` inside a service | Side operation runs outside transaction/test lifecycle | Chain publishers with `flatMap`/`then` |
| Seeding with JDBC `@Sql` and reading R2DBC in same transaction | Two connections do not share a transaction | Use R2DBC fixtures or commit setup before reading |
| Asserting error only without checking database | Does not prove data rolled back | Query again by unique key after rollback |
| Sharing test keys across parallel tests | Tests interfere with each other | Generate unique data and clean up cleanly |
| Using mocks to conclude driver rollback works | Does not verify real transactions | Write integration tests with a compatible database/driver |
| Assuming one manager rolls back multiple datasources | Another source may already have committed | Test each local transaction; use outbox/saga for coordination |

## 28. Workflow for Building an R2DBC Rollback Test

A practical workflow:

1. Identify which `ConnectionFactory` the repository, template, and `DatabaseClient` use.
2. Identify the `ReactiveTransactionManager` managing that exact factory.
3. Create a `TransactionalOperator` from that manager or call a proxied service with reactive `@Transactional`.
4. Create test data with unique keys.
5. Chain all writes inside a single publisher; never call `subscribe()` separately.
6. Emit an intentional error after writes or trigger a database failure on a later step.
7. Let the error cross the transaction boundary so the transaction manager rolls back.
8. Use `StepVerifier` to await the terminal signal before proceeding.
9. Run a new query outside the transaction to verify no changes were committed.
10. Write a symmetric commit test confirming the success path still saves data.
11. Run integration tests with the target R2DBC driver/database, especially when relying on constraints, cancellation, or commit behavior.
12. Clean up fixtures with R2DBC and wait for the publisher to finish.

## 29. Practical Guidelines

- Never assume JDBC test transaction rollback applies to R2DBC.
- Distinguish `PlatformTransactionManager` from `ReactiveTransactionManager`.
- Remember that reactive transactions travel via Reactor Context, not thread-local JDBC context.
- Use `TransactionalOperator` to establish explicit transaction boundaries in tests.
- Ensure the operator and repository/`DatabaseClient` use the same `ConnectionFactory`.
- Let errors escape the transactional publisher; do not swallow errors before the transaction boundary.
- Wait for transaction completion with `StepVerifier` before running verification queries.
- Verify data using a fresh subscription outside the transaction.
- Do not treat `@Transactional`, `@Rollback`, `@DataR2dbcTest`, or `@Sql` as automatic proof; check exact version and connection behavior.
- Never call detached `subscribe()` or `block()` in reactive services.
- Use unique test keys, R2DBC fixtures, and awaited cleanup.
- Test both commit and rollback; asserting only an exception is insufficient.
- Use a real database/driver for transaction, constraint, cancellation, and commit behavior.
- With multiple datasources, test each transaction boundary separately; one R2DBC manager does not roll back another source.

## 30. Conclusion

Testing rollback in Spring Data Relational R2DBC must rely on actual reactive transaction boundaries. JDBC tests usually rely on `PlatformTransactionManager` and thread-bound context; R2DBC uses `ReactiveTransactionManager` and Reactor Context. Therefore, you cannot assume `@Transactional` or `@Rollback` on a test automatically wraps publishers subscribed to by `StepVerifier` the way traditional JDBC tests work.

Use `TransactionalOperator` with the repository's `ConnectionFactory`, chain all write operations into a single publisher, let errors escape the transaction boundary, and wait for rollback to complete. Then run a fresh query outside the transaction to verify data was not committed. Combining symmetric commit tests, R2DBC fixtures, integration tests on real drivers/databases, and per-datasource checks ensures tests reflect true reactive semantics rather than JDBC assumptions.
