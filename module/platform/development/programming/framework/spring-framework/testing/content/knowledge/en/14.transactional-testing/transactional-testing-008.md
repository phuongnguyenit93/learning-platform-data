# @BeforeTransaction and @AfterTransaction outside the transaction

In Spring testing with transactions, many test methods run inside a **test-managed transaction**. By default, Spring usually rolls back this transaction after the test ends so test data does not affect the next test. However, there are behaviors that can only be checked before the transaction starts or after the transaction has committed/rolled back.

The Spring TestContext Framework provides two specialized callbacks:

- **@BeforeTransaction:** runs before the test-managed transaction starts.
- **@AfterTransaction:** runs after the test-managed transaction has ended, whether the transaction committed or rolled back.

These two callbacks help prepare baseline data outside the test's transaction, inspect actual state after the transaction completes, and verify behaviors that depend on commit/rollback boundaries. They do not mean every operation inside the callback is strictly non-transactional. They only sit outside the transaction managed by Spring TestContext for the test method; a service or repository invoked inside the callback can still open its own transaction.

## 1. What is a test-managed transaction?

The Spring TestContext Framework can manage a transaction for a test method when the test is configured with @Transactional and an appropriate transaction manager exists. This management is typically performed by **TransactionalTestExecutionListener**.

Example:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class AccountRepositoryTests {

    @Autowired
    AccountRepository accountRepository;

    @Test
    void creates_account() {
        accountRepository.save(new Account("A-100"));

        assertThat(accountRepository.findById("A-100"))
            .isPresent();
    }
}
~~~

In a typical configuration, the test method runs inside a transaction started by Spring Test. When the test completes, the transaction is rolled back by default. Consequently, the record created during the test does not exist after the test finishes.

This is a **test-managed transaction**. Distinguish it from:

- **Application-managed transaction:** a transaction started by application code using TransactionTemplate, PlatformTransactionManager, or an equivalent mechanism.
- **Spring-managed transaction in the application:** a transaction opened when calling a bean through an @Transactional proxy.
- **External system transaction:** a transaction or side effect performed by another database, broker, or service.

@BeforeTransaction and @AfterTransaction sit on either side of the test-managed transaction. They do not automatically manage every other transaction in the application.

### 1.1. Transactions are rolled back by default

For a test method with @Transactional, Spring Test normally rolls back the transaction after the test completes. The outcome can be changed using:

- @Commit: requests committing the test-managed transaction.
- @Rollback(false): requests a commit instead of a rollback.
- @Rollback: explicitly declares rollback behavior, defaulting to true.

Example:

~~~java
@Test
@Commit
void commits_created_account() {
    accountRepository.save(new Account("A-200"));
}
~~~

When a transaction is committed, data can persist after the test and affect subsequent tests if not cleaned up. This is a suitable case for using @AfterTransaction to verify post-commit state and then clean up according to the test's strategy.

## 2. How do @BeforeTransaction and @AfterTransaction work?

The two annotations belong to the package:

~~~java
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.AfterTransaction;
~~~

TransactionalTestExecutionListener invokes annotated methods at the points corresponding to the test-managed transaction.

General flow:

~~~text
Prepare test instance and inject dependencies
                 |
                 v
       @BeforeTransaction
   (outside the test transaction)
                 |
                 v
     Spring starts test transaction
                 |
                 v
       JUnit @BeforeEach
                 |
                 v
           @Test method
                 |
                 v
        JUnit @AfterEach
                 |
                 v
    Commit or roll back transaction
                 |
                 v
        @AfterTransaction
    (after the test transaction)
                 |
                 v
            Test finishes
~~~

The diagram shows the general sequence in a test with a Spring-managed transaction. JUnit and Spring callbacks have their own lifecycles; the point to remember is that @BeforeTransaction runs before the test-managed transaction begins, while @AfterTransaction runs after that transaction completes.

### 2.1. Only runs when the test has a test-managed transaction

@BeforeTransaction and @AfterTransaction are not replacement callbacks for @BeforeEach and @AfterEach. They are invoked when the test method runs inside a test-managed transaction.

If the test lacks @Transactional on the method or class, or if configuration causes the test not to participate in a test-managed transaction, these two callbacks are not invoked under the usual mechanism.

Example:

~~~java
@SpringJUnitConfig(TestConfig.class)
class NonTransactionalTests {

    @BeforeTransaction
    void beforeTransaction() {
        // Not called merely because the method has this annotation.
    }

    @Test
    void runs_without_test_managed_transaction() {
        // ...
    }
}
~~~

In the case above, the test does not declare @Transactional, so there is no test-managed transaction for the callbacks to precede or follow.

### 2.2. Callbacks run on the prepared test instance

The callbacks can use dependencies that Spring has injected into the test instance, such as JdbcTemplate, repositories, or transaction managers. Thus, they can be used to prepare and inspect database state.

Callback methods normally take no parameters and are declared as methods on the test class. They can be inherited from a superclass according to Spring TestContext's method discovery rules.

## 3. @BeforeTransaction: preparing state before the transaction

@BeforeTransaction is called immediately before Spring starts the test-managed transaction. It is suitable for:

- Creating baseline data that the test transaction must not roll back.
- Confirming the database is in its initial state.
- Setting up an out-of-transaction state required for the test.
- Recording data or counts before the test performs operations.
- Preparing a precondition that must exist before the service begins a transaction.

Example:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class OrderTransactionTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void prepare_baseline_data() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );

        jdbcTemplate.update(
            """
            insert into customers(customer_id, customer_name)
            values (?, ?)
            """,
            reference,
            "Transaction test customer"
        );
    }

    @Test
    void creates_order_for_existing_customer() {
        // Test runs inside a test-managed transaction.
    }
}
~~~

Operations inside the callback sit outside the test-managed transaction. Therefore, if the callback writes data using an autocommit connection or through a repository/service that opens its own transaction, the baseline data may already be committed before the test method starts.

Do not assume every JDBC operation outside a test-managed transaction automatically commits under every configuration. The outcome also depends on the connection, DataSource, transaction manager, and how collaborators manage transactions. If determinism is needed, use an explicit transaction boundary or a repository/service API with known semantics.

### 3.1. Data created in @BeforeTransaction is not rolled back with the test transaction

This is a key point when using the callback to seed data. The test-managed transaction starts after the callback, so operations completed in the callback do not belong to that transaction.

Example:

~~~java
@BeforeTransaction
void insert_customer() {
    customerRepository.save(new Customer("C-1"));
}

@Test
void updates_customer() {
    Customer customer = customerRepository.findById("C-1").orElseThrow();
    customer.rename("Updated");
}
~~~

If the save in @BeforeTransaction is executed by a repository with its own transaction and commits, record C-1 still exists after the test transaction rolls back. The name change inside the test transaction will roll back by default.

If you do not want the baseline data to persist long-term, clean up in @AfterTransaction or use uniquely identified data and clean up with an appropriate strategy.

### 3.2. Using @BeforeTransaction to record initial state

The callback can also read state before the transaction:

~~~java
private long ordersBefore;

@BeforeTransaction
void capture_initial_order_count() {
    ordersBefore = jdbcTemplate.queryForObject(
        "select count(*) from orders",
        Long.class
    );
}
~~~

The test method can create or update data. After the transaction, @AfterTransaction compares state to verify commit/rollback. This approach is useful when needing to check the transaction's impact on a table or aggregate.

However, if the test suite runs in parallel or other tests concurrently write to the table, whole-table counts can change due to unrelated activity. Using a unique business key per test is usually more reliable.

## 4. @AfterTransaction: checking after commit or rollback

@AfterTransaction is called after the test-managed transaction has ended. This is the right point to check what remains in the database after the transaction has committed or rolled back.

Use cases:

- Confirming data disappeared after default rollback.
- Confirming data exists after @Commit or @Rollback(false).
- Checking state that is only observable after the transaction completes.
- Cleaning up data created outside the test-managed transaction.
- Verifying a REQUIRES_NEW operation that committed independently.

### 4.1. Verifying default rollback

The following example creates a record inside the test transaction and checks that it is gone after Spring rolls back:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class RollbackVerificationTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void clean_previous_data() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }

    @Test
    void inserted_order_is_visible_inside_test_transaction() {
        jdbcTemplate.update(
            """
            insert into orders(order_id, external_reference, status)
            values (?, ?, ?)
            """,
            UUID.randomUUID().toString(),
            reference,
            "CREATED"
        );

        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isEqualTo(1);
    }

    @AfterTransaction
    void verifies_rollback() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isZero();
    }
}
~~~

Inside the test method, the record is visible because it is in the current transaction. After the method ends, Spring rolls back the transaction. @AfterTransaction re-reads the database after the rollback and confirms the record is gone.

The example assumes JdbcTemplate uses the same DataSource governed by the transaction manager. Because the callback runs outside the test-managed transaction, the post-rollback query observes state outside the ended transaction.

### 4.2. Verifying data after commit

If the test uses @Commit, @AfterTransaction can inspect the committed data:

~~~java
@SpringJUnitConfig(JdbcTestConfig.class)
@Transactional
class CommitVerificationTests {

    @Autowired
    JdbcTemplate jdbcTemplate;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void remove_old_record() {
        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }

    @Test
    @Commit
    void commits_order() {
        jdbcTemplate.update(
            """
            insert into orders(order_id, external_reference, status)
            values (?, ?, ?)
            """,
            UUID.randomUUID().toString(),
            reference,
            "CREATED"
        );
    }

    @AfterTransaction
    void verifies_committed_order_and_cleans_up() {
        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from orders where external_reference = ?",
            Integer.class,
            reference
        );

        assertThat(count).isEqualTo(1);

        jdbcTemplate.update(
            "delete from orders where external_reference = ?",
            reference
        );
    }
}
~~~

The test verifies the record exists after commit and then deletes it so it does not affect other tests. Cleanup occurs outside the test-managed transaction, so understand the cleanup operation's transaction and ensure it actually persists.

If the assertion in @AfterTransaction fails before cleanup runs, data can be left behind. For critical tests, you can use cleanup in a finally block or an appropriately designed independent cleanup mechanism.

## 5. Distinguishing from @BeforeEach and @AfterEach

JUnit Jupiter provides @BeforeEach and @AfterEach for each test method's lifecycle. When a test has its transaction managed by Spring, these callbacks usually run inside the test-managed transaction.

| Callback | Timing relative to test-managed transaction | Typical purpose |
| --- | --- | --- |
| @BeforeTransaction | Before the transaction starts | Seed data outside the transaction, check baseline |
| @BeforeEach | After the transaction has started | Prepare data belonging to the test's transaction |
| @Test | Inside the transaction | Execute behavior under test |
| @AfterEach | Before the transaction ends | Assertions or cleanup inside the transaction |
| @AfterTransaction | After commit/rollback | Verify final state outside the transaction |

Do not replace @BeforeEach with @BeforeTransaction just to make setup run earlier. The two callbacks have different semantics with respect to rollback.

### 5.1. When to use @BeforeEach?

Use @BeforeEach if the setup data should belong to the test transaction and roll back with the test. For instance, creating an entity to test a repository within the same transaction.

### 5.2. When to use @BeforeTransaction?

Use @BeforeTransaction if data must exist before the test transaction begins, or the test needs to check database state before the transaction is opened.

### 5.3. When to use @AfterEach?

Use @AfterEach for operations that must run before the test transaction completes, such as checking data currently inside the transaction. If the test transaction rolls back afterward, those assertions do not prove the data was committed.

### 5.4. When to use @AfterTransaction?

Use @AfterTransaction when you need to know the outcome after Spring has committed or rolled back the test transaction. This is the right place to verify durable database state after the transaction.

## 6. Interaction with @Transactional, @Commit, and @Rollback

The two callbacks only make sense when a test-managed transaction exists. Therefore, it is necessary to understand how transaction annotations decide when a transaction is opened and closed.

### 6.1. @Transactional at the class level

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class TransactionalRepositoryTests {

    @BeforeTransaction
    void before() {
    }

    @Test
    void first_test() {
    }

    @Test
    void second_test() {
    }

    @AfterTransaction
    void after() {
    }
}
~~~

When class-level @Transactional configuration applies to test methods, each test method gets its own test-managed transaction. The pre/post-transaction callbacks are invoked for each test method that has a transaction.

### 6.2. @Transactional at the method level

~~~java
@SpringJUnitConfig(TestConfig.class)
class MixedTransactionTests {

    @Test
    @Transactional
    void runs_with_test_transaction() {
    }

    @Test
    void runs_without_test_transaction() {
    }
}
~~~

In this example, only the method annotated with @Transactional requests a test-managed transaction. Do not expect @BeforeTransaction or @AfterTransaction to run for the method without a transaction.

### 6.3. @Commit

@Commit asks Spring to commit the test-managed transaction after the test method. @AfterTransaction is called after the commit completes, so it can read the persisted data.

### 6.4. @Rollback

@Rollback defaults to true. When a test does not declare @Commit or @Rollback(false), Spring usually rolls back the transaction after the test. @AfterTransaction can confirm that changes belonging to that transaction are gone.

### 6.5. @Rollback(false)

~~~java
@Test
@Transactional
@Rollback(false)
void persists_changes() {
    // ...
}
~~~

@Rollback(false) has a similar effect to requesting a commit in the context of a test-managed transaction. Be careful with persisted data and always have appropriate cleanup.

### 6.6. Propagation that does not create a test transaction

If the test transaction configuration uses propagation such as NOT_SUPPORTED or NEVER in a way supported by Spring TestContext, the test may not run inside a test-managed transaction. When there is no managed transaction for the test, transaction callbacks have no start/end point to execute around.

Inspect the actual @Transactional configuration, selected transaction manager, and TransactionalTestExecutionListener logs rather than relying solely on the annotation appearing on the class.

## 7. Application-opened transactions inside callbacks

The name @BeforeTransaction can lead readers to think the callback has no transaction whatsoever. Its exact meaning is that the callback runs outside the **test-managed transaction**.

If the callback invokes a service bean through a Spring proxy and the service has @Transactional, the service can still open its own transaction:

~~~java
@Service
class CustomerSetupService {

    private final CustomerRepository repository;

    CustomerSetupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createCustomer(String id) {
        repository.save(new Customer(id));
    }
}
~~~

Test:

~~~java
@BeforeTransaction
void create_customer_before_test_transaction() {
    customerSetupService.createCustomer("C-100");
}
~~~

The call through the proxy can open and commit its own transaction before the test-managed transaction starts. Data C-100 can therefore be visible to the test.

This differs from calling an @Transactional method directly on the same object via self-invocation. If one method in a class calls another method in the same class, the internal call usually does not go through the Spring proxy, so transaction advice may not be applied.

### 7.1. Using TransactionTemplate to create a clear boundary

If a callback needs to write data in its own transaction, TransactionTemplate can make the intent explicit:

~~~java
@Autowired
TransactionTemplate transactionTemplate;

@BeforeTransaction
void prepare_data_in_own_transaction() {
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into customers(customer_id) values (?)",
            "C-200"
        );
    });
}
~~~

Because the callback runs outside the test-managed transaction, TransactionTemplate can open a separate transaction under the configured transaction manager. When the callback completes successfully, that separate transaction commits under the appropriate default propagation.

Only use this approach when the test truly needs a separate transaction. For simple fixtures, a repository with clear transaction semantics or suitable JDBC operations may be enough.

### 7.2. REQUIRES_NEW in application code

A service can use REQUIRES_NEW propagation to write data in a transaction independent of the test transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(AuditRecord record) {
    auditRepository.save(record);
}
~~~

When the service is called through a proxy from a test method that has a transaction, the new transaction can commit independently. Rolling back the outer test transaction does not automatically roll back the already-committed REQUIRES_NEW transaction.

@AfterTransaction is very useful for confirming that the audit record still exists after the outer test transaction rolls back. This is meaningful business behavior, though the test needs an appropriate database and transaction manager setup.

## 8. Example: verifying REQUIRES_NEW does not roll back with the test

Suppose a service writes audits in a separate transaction:

~~~java
@Service
class AuditService {

    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String reference) {
        repository.save(new AuditRecord(reference));
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(TestConfig.class)
@Transactional
class RequiresNewTransactionTests {

    @Autowired
    AuditService auditService;

    @Autowired
    AuditRepository auditRepository;

    private final String reference = UUID.randomUUID().toString();

    @BeforeTransaction
    void remove_old_audit() {
        auditRepository.deleteByReference(reference);
    }

    @Test
    void records_audit_in_independent_transaction() {
        auditService.record(reference);

        assertThat(auditRepository.findByReference(reference))
            .isPresent();
    }

    @AfterTransaction
    void audit_record_survives_outer_rollback() {
        assertThat(auditRepository.findByReference(reference))
            .isPresent();

        auditRepository.deleteByReference(reference);
    }
}
~~~

This example assumes AuditRepository has the illustrative methods and deleteByReference performs cleanup using an appropriate transaction. In the test method, the REQUIRES_NEW call commits the audit record independently. When the outer test transaction rolls back, the record remains; @AfterTransaction confirms this.

This is also an example showing that default rollback does not mean all data generated during the test is reverted. Transaction propagation creates independent boundaries that must be verified separately.

## 9. Combining with JPA and the persistence context

When using JPA, distinguish database state from state residing in the persistence context.

Inside a test-managed transaction:

- Entities may be managed in the persistence context.
- A query may return an entity from the first-level cache.
- Flushing pushes changes to the database within the transaction, but is not synonymous with committing.
- Rollback reverts database changes belonging to that transaction.
- After the transaction, a new EntityManager or an out-of-transaction repository query will observe the committed/rolled-back state.

### 9.1. Why is @AfterTransaction useful with JPA?

If a test just calls findById right after save in the same transaction, the entity may be returned from the persistence context. That does not prove the data committed.

@AfterTransaction runs after the test transaction ends, so it can inspect the outcome through a new persistence operation. For clearer proof, you can use a repository or JdbcTemplate configured against the same database.

Example:

~~~java
@AfterTransaction
void verifies_entity_is_not_persisted_after_rollback() {
    assertThat(orderRepository.findByExternalReference(reference))
        .isEmpty();
}
~~~

There is no need to call EntityManager.clear() in a post-transaction callback merely to avoid the first-level cache of an already-ended transaction. However, if the test uses another manually opened persistence context or transaction, verify clearly whether it is holding stale state.

### 9.2. Flush is not commit

In JPA tests, you can call entityManager.flush() to force SQL to be sent to the database and catch constraint violations early. Yet flush still takes place inside the current transaction. If the test transaction rolls back afterward, the data is not committed.

If the goal is to verify a commit, use @Commit or @Rollback(false), and verify inside @AfterTransaction. Do not treat flush as proof that the transaction has completed.

## 10. Combining with SQL scripts

Spring TestContext supports @Sql to run SQL scripts before or after a test method. @Sql can be combined with test transactions, though you must understand the script's execution phase and transaction mode.

If @Sql runs inside the test transaction, changes may roll back with the test. If the script is configured to run outside the test transaction or uses its own transaction mode, data may persist after the test.

@BeforeTransaction and @AfterTransaction fit when Java logic is needed to prepare or inspect data on either side of the test-managed transaction. @Sql fits when fixture data is naturally expressed as SQL scripts.

Do not use both mechanisms to create and delete the same data without a clear reason. Choose an easy-to-follow fixture strategy and ensure cleanup runs even when assertions fail.

## 11. Tests running without a transaction or transaction manager

The two transaction callbacks are not general-purpose tools for every test:

- If a test method does not run in a test-managed transaction, the callbacks are not invoked.
- If Spring cannot find the transaction manager required by @Transactional configuration, context or test setup can fail.
- If a test only uses plain Java objects, Spring transaction lifecycles are unnecessary.
- If a test checks HTTP requests through a real server, the test thread's transaction does not automatically wrap the transaction on the server thread.

With real HTTP tests using @SpringBootTest(webEnvironment = RANDOM_PORT), requests are handled on a server thread. The transaction opened by TestContext on the test-invoking thread does not automatically wrap database operations inside the request. Therefore, @BeforeTransaction and @AfterTransaction stand before/after the test method's test-managed transaction, not directly before/after the server request's transaction.

If you need to inspect the request's transaction, observe data after the HTTP request finishes using a new transaction or suitable repository operation. Do not infer that the client thread's test-managed transaction will roll back data committed by the server.

## 12. Common pitfalls

### Using @BeforeTransaction but forgetting @Transactional

Without a test-managed transaction, the callbacks are not invoked. Confirm that the test method or class has a transaction managed by Spring Test.

### Thinking data seeded in @BeforeTransaction rolls back automatically

The callback runs before the test transaction. Data written and committed in the callback can survive after the test. Clean up explicitly or use isolated fixtures.

### Using @AfterEach to confirm commit

@AfterEach runs before the test-managed transaction completes. It does not prove data was committed. Use @AfterTransaction when needing to verify post-commit/rollback state.

### Thinking @AfterTransaction always sees committed data

By default, test-managed transactions usually roll back. Only when using @Commit or @Rollback(false) is data belonging to the transaction committed.

### Thinking every operation in callbacks autocommits

Callbacks sit outside the test-managed transaction, yet services/repositories can open their own transactions. JDBC connections are also affected by DataSource configuration. Identify the actual transaction boundary.

### Using @AfterTransaction to delete data, only for cleanup to roll back

If cleanup calls a service or repository that joins another active transaction, the outcome depends on propagation. Ensure cleanup commits or use an independent cleanup mechanism.

### Checking only the entity in the same persistence context

The entity may still reside in the first-level cache. To confirm commit/rollback, read after the transaction using an appropriate new operation.

### Overlooking REQUIRES_NEW

Independent transactions can commit even if the outer test transaction rolls back. If business logic has REQUIRES_NEW, verify that side effect after the test transaction ends.

### Using callbacks to verify all non-database side effects

@AfterTransaction only defines the timing after the test-managed transaction. It does not automatically roll back messages, emails, HTTP requests, or files. Those side effects need test doubles or separate cleanup.

## 13. Practical workflow

**Step 1 – Determine whether the test has a test-managed transaction.** Check @Transactional on the method or class, the transaction manager, and propagation configuration.

**Step 2 – Identify state to prepare.** If data must exist before the test transaction starts, consider @BeforeTransaction. If data should roll back with the test, use @BeforeEach or setup inside the test method.

**Step 3 – Determine the transaction outcome.** Will the test roll back by default, commit with @Commit, or use @Rollback(false)?

**Step 4 – Choose assertion points.** Check in-transaction data in the test method; check post-commit/rollback state in @AfterTransaction.

**Step 5 – Account for application-opened transactions.** Check whether @Transactional on services, REQUIRES_NEW propagation, or TransactionTemplate creates independent transactions.

**Step 6 – Prepare isolated data.** Use unique business keys to prevent parallel tests or stale data from skewing results.

**Step 7 – Design cleanup.** Clean up committed or out-of-transaction seeded data with operations that have clear transaction semantics.

**Step 8 – Verify the right persistence boundary.** With JPA, distinguish flush, persistence context, and commit. With real HTTP servers, distinguish the test thread's transaction from the server thread's.

**Step 9 – Run the test standalone and in the suite.** Ensure callbacks run properly, data does not leak, and results do not depend on execution order.

## 14. Callback selection table

| Goal | Appropriate callback or mechanism |
| --- | --- |
| Seed data that exists before the test transaction | @BeforeTransaction |
| Check baseline before the transaction starts | @BeforeTransaction |
| Create fixtures that roll back with the test | @BeforeEach or test method |
| Check state while inside the transaction | Test method or @AfterEach |
| Verify data rolled back | @AfterTransaction |
| Verify data committed | @Commit combined with @AfterTransaction |
| Verify REQUIRES_NEW side effects | @AfterTransaction |
| Clean up committed data | @AfterTransaction or an appropriate cleanup mechanism |
| Test behavior without a test-managed transaction | Standard test lifecycle, without relying on these two callbacks |

## 15. Principles for safe usage

- Understand @BeforeTransaction and @AfterTransaction according to the test-managed transaction boundary.
- Only expect the callbacks to run when the test method has a transaction managed by Spring Test.
- Use @BeforeTransaction for state that must exist before the test transaction begins.
- Use @AfterTransaction to verify results after commit or rollback.
- Remember that rollback is the default; use @Commit or @Rollback(false) when testing commit.
- Do not assume callbacks cannot open another transaction.
- Distinguish the test's transaction from transactions opened by services/repositories themselves.
- Use uniquely identified data and cleanup for data created outside the test transaction.
- With JPA, distinguish flush, persistence context, and commit.
- With real HTTP servers, do not assume the test thread's transaction wraps the server thread.
- Do not use context cleanup as a substitute for database or external side-effect cleanup.

## Conclusion

@BeforeTransaction and @AfterTransaction help test behaviors on both sides of a test-managed transaction in Spring TestContext. The pre-transaction callback fits preparing or inspecting baseline state; the post-transaction callback fits verifying whether data committed or rolled back and checking effects executed in independent transactions.

The key is understanding the exact scope: both callbacks sit outside the transaction managed by Spring Test for the test method, yet code invoked inside the callbacks can still open its own transactions. Combining them properly with @Transactional, @Commit, @Rollback, repositories, and transaction managers lets tests verify commit/rollback boundaries, avoid confusing persistence context state with durable data, and keep test data independent.
