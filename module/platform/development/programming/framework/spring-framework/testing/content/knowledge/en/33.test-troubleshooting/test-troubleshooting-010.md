# Transaction Rollbacks Hiding Flush Errors or Leaked Test Data

Spring Test typically runs a `@Transactional` test method inside its own transaction and rolls that transaction back when the test finishes. This mechanism prevents test-created data from persisting after the test. However, rolling back can also cause a test to miss behaviors that only occur when SQL is flushed or the transaction is committed. In addition, some database operations may execute outside the transaction managed by Spring Test and leave data behind even after the test finishes.

Two distinct problems must be separated:

- **Masked flush errors:** the test modifies entities inside the persistence context without pushing SQL to the database. The test ends and rolls back, so constraints or SQL errors were never actually executed.
- **Leaked data:** a data write runs in an independent transaction, on another thread, in a request to a real server, or in a committed transaction. The test's rollback cannot undo that operation.

To test persistence reliably, you must understand the transaction lifecycle, when JPA flushes, the thread-bound scope of transactions, and which operations execute outside the test transaction.

## 1. How Do Spring Test Transactions Work?

The Spring TestContext Framework supports transaction management for tests via `TransactionalTestExecutionListener`. When a test class or test method is annotated with `@Transactional`, Spring starts a test-managed transaction before running the test method and rolls it back by default once the test completes.

Example:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void savesCustomer() {
        customerRepository.save(new Customer("alice@example.test"));

        assertThat(customerRepository.findByEmail("alice@example.test"))
                .isPresent();
    }
}
```

`@DataJpaTest` is configured to run inside a transaction and roll back after each test method by default. Data created inside this transaction generally does not remain after the test ends.

With tests using `@SpringBootTest`, test transactions are not enabled automatically merely by using that annotation. Annotate the class or method with `@Transactional` if you want Spring Test to manage a transaction for the test.

### Transaction Lifecycle

For a typical transactional test, the general sequence is:

```text
Spring Test starts test-managed transaction
                  |
                  v
             @BeforeEach
                  |
                  v
              @Test
                  |
                  v
              @AfterEach
                  |
                  v
         Rollback transaction
                  |
                  v
      @AfterTransaction callback
```

`@BeforeTransaction` runs before the test-managed transaction starts; `@AfterTransaction` runs after the transaction has ended. These two callbacks are useful when you need to prepare or inspect data outside the test's transaction.

By default, `@Rollback` is `true`. You can use `@Commit` or `@Rollback(false)` to request a commit instead of a rollback, though in that case the test must have an explicit data cleanup strategy.

## 2. Flush Is Not the Same as Commit

JPA maintains a persistence context to track entities. When calling `persist`, `merge`, or Spring Data JPA's `save`, changes may be recorded only in the persistence context without immediately sending SQL to the database.

**Flush** synchronizes pending changes in the persistence context down to the database by executing the required SQL statements. **Commit** ends the transaction and makes the changes committed according to the transaction manager/database.

The two operations are related yet not identical:

| Operation | What happens | Is data committed? |
| --- | --- | --- |
| `repository.save(entity)` | Puts the entity into managed/saved state per repository behavior; SQL may not have run yet | No |
| `entityManager.flush()` | Sends pending changes down to the database | No, the transaction can still roll back |
| `repository.saveAndFlush(entity)` | Saves and then requests a flush | No, the transaction can still roll back |
| Transaction commit | Completes the transaction in the database | Yes, if the commit succeeds |
| Transaction rollback | Undoes uncommitted transactional changes | No |

Therefore, a test can call `save()` successfully, pass assertions on the in-memory object, and then roll back the transaction without ever sending an INSERT statement to the database.

### Why Can Database Errors Be Masked?

Suppose the `email` column has a unique constraint. A test creates two customers with the same email but only calls `save()` without flushing. Depending on the provider and flush timing, the INSERT statement may not run inside the test body. If the transaction rolls back before committing, the unique constraint may never be checked.

Example of an insufficiently strict test:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void duplicateEmailIsRejected() {
        repository.save(new Customer("same@example.test"));
        repository.save(new Customer("same@example.test"));

        // Test ends and the transaction rolls back.
        // Without flushing, the database may never have executed the INSERT.
    }
}
```

The test above lacks an assertion proving the constraint was enforced. It can pass even though the database would reject the data when the transaction actually flushes or commits.

## 3. Using Flush to Force the Database to Execute SQL in Tests

When the goal is to verify constraints, mappings, or SQL statements, flush at the appropriate point so failures surface immediately inside the test.

Entity example:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

Test verifying the unique constraint:

```java
@DataJpaTest
class CustomerRepositoryConstraintTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmailWhenChangesAreFlushed() {
        repository.saveAndFlush(new Customer("same@example.test"));

        assertThatThrownBy(() ->
                repository.saveAndFlush(new Customer("same@example.test")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
```

`saveAndFlush` instructs Spring Data JPA to synchronize changes to the database. When the unique constraint is checked immediately upon executing INSERT, the test observes the failure on the second call. The exact exception type can depend on the JPA provider and Spring's exception translation; `DataIntegrityViolationException` is common when translated by Spring Data/Spring ORM.

You can use `EntityManager.flush()` when the test operates through the entity manager:

```java
entityManager.persist(new Customer("same@example.test"));
entityManager.flush();

entityManager.persist(new Customer("same@example.test"));

assertThatThrownBy(entityManager::flush)
        .isInstanceOf(PersistenceException.class);
```

In the second example, the exception type may be a JPA provider exception or a Spring-translated exception depending on how it is invoked and where it is caught. When asserting exact types, base assertions on the actual exception thrown by the provider/database under test.

### Flushing Does Not Commit the Transaction

After `flush()` succeeds, the data still belongs to the current transaction. If the test ends with a rollback, transactional INSERT/UPDATE/DELETE statements are still undone. This is desirable: the test can verify SQL and constraints without leaving data behind after the test.

## 4. Using Flush and Clear to Avoid Assertions Reading Only from Memory

A test may read an entity back from the persistence context instead of actually querying the database. If the entity remains managed in the first-level cache, calling `findById` can return the exact same object without issuing a SELECT.

When you want to verify that data was written and can be reloaded from the database, flush and then clear the persistence context before reading:

```java
@DataJpaTest
class CustomerRepositoryPersistenceTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void reloadsCustomerAfterFlushAndClear() {
        Customer saved = repository.save(new Customer("alice@example.test"));

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = repository.findById(saved.getId()).orElseThrow();

        assertThat(reloaded.getEmail()).isEqualTo("alice@example.test");
    }
}
```

`flush()` pushes changes to the database. `clear()` detaches entities from the current persistence context. When calling `findById`, JPA must load the entity again, so the test verifies the state stored in the database rather than inspecting the old object still sitting in memory.

`TestEntityManager` is a utility provided by Spring Boot for JPA test slices. In Spring/JPA tests not using Boot, inject an `EntityManager` as appropriate.

You do not need `clear()` in every test. Use it when the goal is to verify reloading data or prevent the persistence context from masking query errors.

## 5. When JPA May Flush Automatically

Beyond calling `flush()` directly, a JPA provider may flush automatically in certain situations depending on `FlushMode` and the operation type.

With the commonly defaulted `FlushModeType.AUTO`, the provider must ensure changes affecting a query's result are synchronized before executing that query. Consequently, running a query can cause a constraint error to surface even when the code did not explicitly call `flush()`.

Common flush points include:

- Calling `EntityManager.flush()`.
- Calling `JpaRepository.flush()` or `saveAndFlush()`.
- Before executing a query when the flush mode requires synchronizing relevant changes.
- When a transaction commits, the provider typically flushes pending changes prior to committing.

Exact timing can depend on the provider, flush mode, query type, and database. Do not write tests assuming every `save()` call emits SQL immediately.

## 6. Are Constraints Checked at Flush Time or Commit Time?

Many constraints such as `NOT NULL`, standard unique constraints, or non-deferred foreign keys are checked by the database when the corresponding SQL statement executes. Flushing is usually enough to catch failures.

Some databases support deferred constraints, which are checked at transaction commit time. With these constraints, flushing can succeed even though the transaction later fails on commit.

This means:

- If you want to verify SQL emission and immediate constraints, flushing is sufficient.
- If you want to verify behavior that only occurs at commit, you need a test that actually commits the transaction.
- Default rollback tests cannot prove commit success or failure.

For example, PostgreSQL supports constraints declared `DEFERRABLE`, which can be checked at commit time. Tests using H2 or another database may not reproduce the same behavior; use the real database engine when features depend on dialect.

## 7. Testing Commit Behavior Intentionally

If you need to verify transaction commit behavior, you can use `@Commit` or `@Rollback(false)`:

```java
@DataJpaTest
class CommittedCustomerTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    @Commit
    void commitsCustomer() {
        repository.save(new Customer("committed@example.test"));
    }
}
```

This test tells Spring to commit the transaction instead of rolling back. However, the data can persist after the test and affect subsequent runs. Use this approach only when commit is the behavior under test and cleanup is explicitly handled.

Another option is controlling the test-managed transaction with `TestTransaction`:

```java
@DataJpaTest
class TransactionBoundaryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void commitsAtAnExplicitPoint() {
        repository.save(new Customer("commit-check@example.test"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
    }
}
```

`TestTransaction.flagForCommit()` marks the current transaction to commit; `end()` terminates the transaction and performs commit or rollback according to the flag. `TestTransaction` can start a new transaction with `start()` if the test needs to continue operating in another transaction. Remember that an actual commit can leave data in the database after the test.

### Inspecting State After the Transaction

If you need to confirm data is gone after rollback, query from an independent transaction after the test transaction has ended. You cannot prove rollback simply by reading inside the same transaction before it finishes.

Spring Test provides `@AfterTransaction` to run checks after the test-managed transaction completes:

```java
@DataJpaTest
class RollbackVerificationTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void writesTemporaryRecordInsideTestTransaction() {
        jdbcTemplate.update(
                "insert into audit_note(message) values (?)",
                "temporary");

        assertThat(jdbcTemplate.queryForObject(
                "select count(*) from audit_note where message = ?",
                Integer.class,
                "temporary")).isEqualTo(1);
    }

    @AfterTransaction
    void verifiesRollbackRemovedRecord() {
        Integer count = jdbcTemplate.queryForObject(
                "select count(*) from audit_note where message = ?",
                Integer.class,
                "temporary");

        assertThat(count).isZero();
    }
}
```

The example assumes the `audit_note` table already exists in the test database. `@AfterTransaction` runs outside the test transaction, so the query observes post-rollback state. In real applications, use a unique data key so the test does not touch data from other tests.

## 8. Cases Where Test Rollback Cannot Clean Up Data

A transaction rollback only undoes operations belonging to the transaction it rolls back. It does not automatically undo every database change performed while the test ran.

### `Propagation.REQUIRES_NEW`

A method invoked through a Spring transaction proxy with `Propagation.REQUIRES_NEW` runs in a new transaction. The outer transaction is suspended; the new transaction can commit independently. Afterward, even if the outer test transaction rolls back, data committed by the inner transaction remains.

Example:

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String message) {
        auditRepository.save(new AuditEntry(message));
    }
}
```

If a test calls `auditService.record(...)` while the test-managed transaction is open, Spring opens an independent transaction for `record`. Once that transaction commits, rolling back the test transaction does not delete the audit record.

Note: `REQUIRES_NEW` only works via proxy interception when the call passes through a Spring bean proxy. Self-invoking another method on the same object typically bypasses the proxy and may not apply propagation as expected.

### Test Code Running on Another Thread

Spring transactions are typically bound to the current thread. The following mechanisms can execute code on another thread:

- `@Async` or `TaskExecutor`.
- `CompletableFuture` or custom executors.
- Servlet container threads when a test sends HTTP requests to an embedded server.
- JUnit's `assertTimeoutPreemptively`, which runs the executable in a separate thread so it can interrupt on timeout.

The test's transaction does not automatically propagate to another thread. If the new thread performs writes, it may run in its own transaction or auto-commit depending on configuration. Thus, the test can finish and roll back while data from the secondary thread persists.

#### Beware of `assertTimeoutPreemptively`

Example prone to data leaks:

```java
@Test
@Transactional
void mayWriteOutsideTestManagedTransaction() {
    assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
        repository.save(new Customer("timeout@example.test"));
    });
}
```

JUnit executes the executable on a different thread. The Spring-managed test transaction is bound to the original test thread, so repository operations inside the preemptive timeout thread may not participate in that transaction. If the operation commits, post-test rollback cannot clean up the data.

If you need a timeout on a transactional test, prefer non-preemptive `assertTimeout(...)` when suitable; it runs the code on the same thread and reports overtime after completion. If you genuinely need task cancellation, design separate transaction management and cleanup for the worker thread.

### Requests to an Embedded Server

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the test sends HTTP requests to a running server. The controller handles requests on a server thread, not the thread holding the test transaction. Hence, the client-side test transaction does not wrap the transaction used by the controller.

A POST request can commit data inside the server's transaction. When the test method ends, Spring rolls back the test thread's transaction, yet data committed on the server remains.

For tests against a real HTTP server, create unique data, clean up explicitly, or use a dedicated database/container for the test. Do not rely on `@Transactional` on the test method to automatically roll back operations performed by server requests.

## 9. Leaked Data from `@Commit`, `@Rollback(false)`, and Independent Transactions

The following approaches intentionally alter default rollback behavior:

```java
@Test
@Commit
void persistsData() {
    // Transaction will commit.
}

@Test
@Rollback(false)
void alsoPersistsData() {
    // Transaction does not roll back.
}
```

These are valid choices when a test must verify commits or inspect data from another transaction. However, if used without cleanup, data persists and can make subsequent test runs fail due to unique keys, row counts, or stale state.

Data can also persist due to:

- An independent transaction that committed, such as `REQUIRES_NEW`.
- Test setup running outside the transaction, such as code in `@BeforeTransaction` writing data.
- SQL scripts or migrations executing in an isolated transaction mode.
- Async tasks writing data on another thread.
- Requests to an embedded server committing their own transactions.
- Database sequences or non-transactional objects whose state does not roll back normally.

Do not assume every database change will roll back simply because the test class has `@Transactional`.

## 10. Database Sequences and Non-Transactional Side Effects

Database rollback does not necessarily restore everything to its byte-for-byte initial state.

For instance, many databases use sequences or identity generators whose counters do not roll back with transactions. A test that inserts and rolls back can still advance the next generated ID. Tests should not assume auto-generated IDs always start at 1 or have no gaps.

Non-transactional side effects also do not roll back:

- Sending emails or HTTP requests.
- Publishing messages to a broker once received and committed by the broker.
- Writing files or object storage.
- Emitting events to external systems.
- Updating caches or search indices outside the database transaction.

If you need to test these side effects, use fakes/mocks in unit tests or integration environments capable of resetting state. For message brokers/databases requiring consistency, test transactional messaging or outbox mechanisms separately; database test rollback cannot recall a message already delivered to an independent broker.

## 11. Strategies for Cleaning Up Leaked Data

When a test genuinely needs to commit or runs across independent threads/transactions, manage data proactively.

### Use Unique Data Per Test

Generate unique emails, order numbers, or correlation keys so tests do not collide. Retain created IDs and delete those exact records.

### Clean Up Data in an Independent Transaction

You can use `@AfterTransaction` to delete committed data after the test transaction ends. If cleanup runs in a new transaction, ensure that transaction commits successfully.

### Use `@Sql` for Setup/Cleanup

Spring Test supports `@Sql` to run scripts before or after tests. When a script must run in an independent transaction, configure `transactionMode = ISOLATED`:

```java
@Test
@Sql(scripts = "/sql/cleanup-audit.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void verifiesCommittedAuditRecord() {
    // Execute test.
}
```

`ISOLATED` executes the script in its own transaction and commits that transaction. Keep cleanup scripts narrowly scoped to test-specific keys; avoid `DELETE` or `TRUNCATE` across whole tables when sharing a database with other tests.

### Use a Dedicated Database or Schema

For integration tests that write data independently, a dedicated database or schema per test suite or worker reduces collisions. Testcontainers can spin up a dedicated database for the suite. When multiple tests run in parallel, still use unique data or schemas at the appropriate scope.

### Do Not Use `@DirtiesContext` as a Substitute for Database Cleanup

`@DirtiesContext` closes/evicts the application context from the cache; it does not guarantee deleting committed records in a shared database. Use it for irrecoverably mutated context state, not for cleaning persistence data.

## 12. How to Verify That a Test Actually Rolls Back

To prove data was rolled back, observe from an independent transaction after the test transaction ends.

A practical procedure:

1. Create a record with a unique key inside the test transaction.
2. Flush to ensure the INSERT was sent to the database.
3. Assert the record exists inside the current transaction.
4. End the transaction via default rollback or `TestTransaction.flagForRollback()` and `end()`.
5. Open a new transaction or query outside the test transaction.
6. Assert the record is gone.

Example with `@AfterTransaction`:

```java
@DataJpaTest
class RollbackBehaviorTest {

    private static final String TEST_EMAIL = "rollback-check@example.test";

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsInsideTransactionBeforeRollback() {
        repository.save(new Customer(TEST_EMAIL));
        entityManager.flush();

        assertThat(repository.findByEmail(TEST_EMAIL)).isPresent();
    }

    @AfterTransaction
    void verifiesRecordWasRolledBack() {
        assertThat(repository.findByEmail(TEST_EMAIL)).isEmpty();
    }
}
```

The example assumes the repository has `findByEmail` and the database schema is prepared. Queries inside `@AfterTransaction` run after the test transaction ends; Spring Data may open an appropriate read transaction or run under the test infrastructure's current transaction config. If a repository method requires an explicit transaction, use `TransactionTemplate` to open a new read transaction.

## 13. Diagnostic Workflow for Flush Errors and Data Leaks

When a database test passes yet you suspect constraints were untested or data persists after the test, proceed in order:

1. Check whether the test has `@Transactional` directly, via the class, or from a test slice.
2. Check whether the test transaction commits or rolls back; inspect `@Commit`, `@Rollback(false)`, and `TestTransaction`.
3. Look for `save`, `persist`, and `merge` calls that were never flushed.
4. Add `flush()`/`saveAndFlush()` wherever SQL and constraints must be verified.
5. When verifying data reloaded from the database, flush and then `clear()` the persistence context.
6. If a failure only happens at commit, write a committing test with cleanup using a database supporting that constraint.
7. Look for `REQUIRES_NEW`, `NOT_SUPPORTED`, or operations executing outside transactions.
8. Look for secondary threads: `@Async`, executors, futures, preemptive timeouts, and requests to a real server.
9. Check non-transactional side effects and sequences/identities.
10. Use `@AfterTransaction` or an independent transaction to inspect data after the test ends.
11. If committed data must be preserved during a test, clean up by test-owned ID/key or use a dedicated database/schema.

## 14. Common Errors and Resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Duplicate key test passes despite violating unique constraint | Not flushed, so SQL never ran | Use `saveAndFlush()` or `EntityManager.flush()` |
| Re-reading entity still succeeds even without database data | Persistence context returns managed instance | Flush then `clear()` before re-reading |
| Test rolls back yet record still exists | Independent transaction committed or code ran on another thread | Check `REQUIRES_NEW`, async, server threads, preemptive timeout |
| Re-running test fails with unique key error | Committed data from a previous run | Use unique IDs and clean up after the test |
| `@SpringBootTest(RANDOM_PORT)` test leaves data behind | Requests run in separate server transactions | Explicit cleanup or dedicated database |
| Auto-generated IDs keep incrementing despite rollback | Sequences/identities do not roll back with transactions | Do not assert contiguous IDs or reset sequences in a dedicated test DB |
| `@DirtiesContext` used yet data remains | Context cache is not database cleanup | Clean the database via scripts or proper transactions |
| Async test writes data after rollback | Worker thread executes outside the test transaction | Await task completion, manage transactions, and clean up separately |

## 15. Conclusion

Spring Test rollbacks isolate data only when operations actually participate in the test-managed transaction. JPA can defer SQL until flush or commit, so tests must call `flush()`/`saveAndFlush()` when verifying constraints and database errors. Flushing sends SQL to the database without committing; the transaction can still roll back afterward.

Data can still leak if operations commit inside `REQUIRES_NEW`, execute on another thread, go through an embedded server, use preemptive timeouts, or produce side effects outside the database transaction. Identify exact transaction boundaries, observe data after the transaction ends, and clean up by unique data keys. Do not rely on default rollbacks to hide unexecuted SQL or undo changes outside the transaction managed by Spring Test.
