# Testing Transactions, Rollback, and Implicit DDL Commits

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Testing  
> **Objective:** Understand transaction boundaries in Oracle; test `COMMIT`, `ROLLBACK`, `SAVEPOINT`, and mid-transaction failures; master implicit commits before/after DDL; distinguish rollbackable DML from DDL such as `TRUNCATE`/`ALTER`/`DROP`; test transactions via Spring Boot/JPA/JDBC; recognize the impact of sequences, autonomous transactions, and external side effects; build isolated, repeatable tests that do not pollute shared databases.

## 1. Why test transactions explicitly?

A feature may return HTTP 200 or a repository method may throw no exceptions, yet data ends up wrong because the transaction boundary is not what the developer assumed.

Common scenarios:

- A service updates two tables; the second step fails, yet the first step already committed.
- A Spring method has `@Transactional`, but an internal self-invocation bypasses the proxy so no transaction opens as expected.
- JPA modified an entity in memory, but SQL has not been sent to the database because no flush occurred.
- Native SQL or a stored procedure updates a table while an already-loaded entity retains stale data in the persistence context.
- DDL executes in the middle of a DML transaction and Oracle automatically commits the open transaction.
- A Spring test annotated with `@Transactional` expects everything to roll back at the end of the test, yet a `CREATE TABLE` statement committed preceding fixture data.
- A sequence incremented even though the inserting transaction rolled back.
- A procedure writes audit logs using an autonomous transaction, so the audit record persists even when the business transaction rolls back.
- HTTP calls or file writes cannot be undone by an Oracle `ROLLBACK`.

Transaction testing must verify data state across each commit/rollback boundary, not just inspect return values.

## 2. Transactions in Oracle

A transaction is a logical unit of work comprising one or more data changes. Oracle guarantees that DML changes within a transaction commit together or roll back according to transaction semantics.

Example:

~~~sql
UPDATE accounts
   SET balance = balance - 100
 WHERE account_id = 10;

UPDATE accounts
   SET balance = balance + 100
 WHERE account_id = 20;

COMMIT;
~~~

Both `UPDATE`s belong to the same transaction. If the second step fails and the application rolls back the entire transaction, the first step's change is also undone.

### 2.1. COMMIT

`COMMIT` ends the current transaction and makes its changes durable per Oracle's commit mechanism.

~~~sql
UPDATE orders
   SET status = 'PAID'
 WHERE order_id = 1001;

COMMIT;
~~~

After `COMMIT`, a subsequent `ROLLBACK` cannot undo the committed `UPDATE`.

### 2.2. ROLLBACK

`ROLLBACK` discards uncommitted changes in the current transaction:

~~~sql
UPDATE orders
   SET status = 'CANCELLED'
 WHERE order_id = 1001;

ROLLBACK;
~~~

The database reverts to its pre-transaction state for those transactional changes.

`ROLLBACK` does not reverse everything the application performed. It does not undo sent emails, processed HTTP requests, written files, issued sequence `NEXTVAL`s, or committed autonomous transactions.

### 2.3. SAVEPOINT

`SAVEPOINT` sets a marker within a transaction to allow partial rollback:

~~~sql
UPDATE inventory
   SET reserved_qty = reserved_qty + 1
 WHERE product_id = 501;

SAVEPOINT after_reserve;

UPDATE orders
   SET status = 'READY'
 WHERE order_id = 1001;

ROLLBACK TO after_reserve;

COMMIT;
~~~

In this example, the `inventory` update is kept; the `orders` update is rolled back to the savepoint; `COMMIT` ends the transaction with the remaining changes.

`SAVEPOINT` does not create an independent transaction. It is merely a marker inside the current transaction.

### 2.4. SAVEPOINTs are cleared when a transaction commits

`COMMIT` ends the transaction and clears savepoints. DDL triggers an implicit commit, which also breaks the current savepoint boundary.

Do not design a workflow relying on a `SAVEPOINT` and then execute DDL expecting to roll back to that savepoint afterward.

## 3. DML and DDL have different transaction semantics

DML modifies data inside tables:

- `INSERT`
- `UPDATE`
- `DELETE`
- `MERGE`
- Certain other DML operations per SQL semantics

DDL modifies database structures or metadata:

- `CREATE TABLE`
- `ALTER TABLE`
- `DROP TABLE`
- `CREATE INDEX`
- `TRUNCATE TABLE`
- `CREATE`/`ALTER`/`DROP VIEW`
- `CREATE`/`ALTER`/`DROP PROCEDURE` or `PACKAGE`
- `GRANT` and `REVOKE`
- Many other object management statements

In Oracle, DDL has implicit commit rules. This is especially important when writing migrations, stored procedures, and integration tests.

### 3.1. Oracle's implicit commit rule

For a syntactically valid DDL statement, Oracle executes an implicit `COMMIT` before running the DDL. Once the DDL succeeds, Oracle executes a commit after the statement.

Consequences:

1. Uncommitted DML prior to DDL is committed before the DDL executes.
2. Successful DDL is finalized as an atomic operation.
3. `ROLLBACK` after DDL cannot undo DML committed before the DDL or successful DDL.
4. Savepoints from the prior transaction are no longer usable after the commit.
5. If DDL fails, do not assume preceding DML can still roll back; the pre-DDL commit already occurred.

This rule differs from some other databases. Do not carry transaction assumptions from PostgreSQL, SQL Server, or H2 over to Oracle without testing.

### 3.2. Example of DDL committing prior DML

Suppose table `TX_PROBE` already exists:

~~~sql
DELETE FROM tx_probe;
COMMIT;

INSERT INTO tx_probe(id, note)
VALUES (1, 'DML before DDL');

CREATE TABLE ddl_probe (
    id NUMBER PRIMARY KEY
);

ROLLBACK;

SELECT id, note
FROM tx_probe
WHERE id = 1;
~~~

The result still contains row `ID = 1`. The `INSERT` was committed before `CREATE TABLE` ran. The trailing `ROLLBACK` cannot restore the old transaction boundary.

The successful `CREATE TABLE` was also committed. Therefore, `DDL_PROBE` persists after `ROLLBACK`.

### 3.3. Failed DDL can still commit prior DML

Suppose there is uncommitted DML followed by a syntactically valid DDL statement that fails at execution time—for instance, because an object name already exists or privileges are missing.

Oracle already executed the implicit commit before running the DDL. Hence preceding DML may already be committed even though the DDL failed.

This is why you should never use DDL as a speculative check inside a business transaction. To check schema/objects, query metadata or run DDL in a dedicated test schema.

### 3.4. DDL inside PL/SQL still has this effect

DDL cannot be written directly as static SQL inside a normal PL/SQL block; dynamic SQL is typically used:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE runtime_probe (id NUMBER)';
END;
/
~~~

Wrapping DDL inside `EXECUTE IMMEDIATE` does not turn it into transactional DML. DDL implicit commit rules still apply.

A procedure containing DDL can unexpectedly commit the caller's transaction. Never call such a procedure inside a business transaction requiring atomicity without clearly designing boundaries.

## 4. DELETE, TRUNCATE, and DROP are not the same

All three statements can remove data from a table, yet their semantics differ:

| Statement | Category | Can deleted data be rolled back? | Meaning |
|---|---|---:|---|
| `DELETE` | DML | Yes, before `COMMIT` | Deletes rows matching a predicate or all rows |
| `TRUNCATE TABLE` | DDL | No | Removes all rows via a DDL operation |
| `DROP TABLE` | DDL | Not via normal `ROLLBACK` | Removes the object/table from the schema |

### 4.1. DELETE can be rolled back

~~~sql
DELETE FROM staging_orders
WHERE batch_id = 9001;

ROLLBACK;
~~~

Rows removed by `DELETE` are restored when rolling back the transaction prior to commit.

### 4.2. TRUNCATE cannot be rolled back

~~~sql
TRUNCATE TABLE staging_orders;
~~~

`TRUNCATE` is DDL in Oracle. It triggers an implicit commit and data cannot be recovered via normal `ROLLBACK`.

If deletion must be rollbackable, use `DELETE` or design appropriate partition maintenance/recovery. `TRUNCATE` is generally faster and generates less redo/undo than `DELETE` for clearing entire tables, but transaction impacts must be understood.

### 4.3. DROP TABLE is not DELETE

`DROP TABLE` removes the object. `ROLLBACK` cannot restore a dropped table. Oracle may support Flashback Drop via the recycle bin under appropriate conditions, but that is a separate recovery mechanism, not transaction rollback.

Never use `DROP`/`CREATE` to reset data in a test running inside a transaction expecting Spring to roll everything back automatically.

## 5. Testing transactions with plain SQL

Before testing through frameworks, verify database behavior using a probe table in a lab schema.

~~~sql
CREATE TABLE tx_probe (
    id      NUMBER PRIMARY KEY,
    note    VARCHAR2(100)
);
~~~

Create the table once before tests. Do not recreate the table inside a transaction that a test intends to roll back.

### 5.1. Testing commit

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (10, 'commit case');

COMMIT;

SELECT *
FROM tx_probe
WHERE id = 10;
~~~

The row must persist after the session ends.

### 5.2. Testing rollback

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (11, 'rollback case');

ROLLBACK;

SELECT *
FROM tx_probe
WHERE id = 11;
~~~

No row with `ID = 11` exists.

### 5.3. Testing savepoint

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (12, 'before savepoint');

SAVEPOINT s1;

INSERT INTO tx_probe(id, note)
VALUES (13, 'after savepoint');

ROLLBACK TO s1;

COMMIT;

SELECT id
FROM tx_probe
WHERE id IN (12, 13)
ORDER BY id;
~~~

Only row `ID = 12` exists.

### 5.4. Testing implicit commit

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (14, 'before DDL');

CREATE TABLE tx_ddl_probe (
    id NUMBER
);

ROLLBACK;

SELECT *
FROM tx_probe
WHERE id = 14;
~~~

Row `ID = 14` still exists because the `INSERT` committed before the DDL. Table `TX_DDL_PROBE` also exists after `ROLLBACK`.

Run these examples in a lab schema. Dropping the probe table is DDL and commits the current transaction; clean up in a separate step after confirming no other tests use the object.

## 6. Transaction boundaries in Spring Boot

Spring manages transactions via `PlatformTransactionManager`, typically `JpaTransactionManager` for JPA or `DataSourceTransactionManager`/`JdbcTransactionManager` for JDBC.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;

    public OrderService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
    }

    @Transactional
    public void payOrder(long orderId) {
        OrderEntity order = orderRepository.findById(orderId)
            .orElseThrow();

        order.markPaid();

        paymentRepository.save(
            PaymentEntity.forOrder(orderId)
        );
    }
}
~~~

If the method completes normally, the Spring transaction interceptor commits. If the method throws an exception matching rollback rules, the transaction rolls back.

### 6.1. Default rollback rules

Under Spring's standard defaults:

- `RuntimeException`: rolls back.
- `Error`: rolls back.
- Checked exception: does not automatically roll back unless configured via rollback rules.

For example, if a business method throws a checked exception and must roll back:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // Database changes.
}
~~~

`noRollbackFor` can be configured for certain exceptions, but weigh carefully because callers may receive an error while the database has already committed.

Never assume every exception automatically triggers rollback.

### 6.2. Propagation REQUIRED

`REQUIRED` is the default propagation. The method joins an existing transaction or creates a new one if none exists.

~~~java
@Transactional
public void processOrder() {
    updateOrder();
    createPayment();
}
~~~

If `updateOrder` and `createPayment` share the same transaction manager/context, they commit or roll back together.

### 6.3. REQUIRES_NEW

`REQUIRES_NEW` suspends the current transaction and starts a new independent transaction:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    auditRepository.save(...);
}
~~~

A `REQUIRES_NEW` transaction can commit independently. If the outer transaction rolls back, the committed audit record persists.

This may be intentional for audit/telemetry, but never use it for business data that must roll back alongside the parent transaction.

### 6.4. NESTED and savepoints

`NESTED` propagation can use savepoints if supported by the transaction manager and resource. Do not assume `JpaTransactionManager` supports nested transactions exactly as an application expects.

If savepoints are needed, verify the transaction manager, JDBC connection, and driver. Test rolling back to a savepoint on real Oracle.

## 7. Cases where @Transactional does not behave as expected

### 7.1. Self-invocation

Spring proxies normally apply `@Transactional` when a method is invoked through the proxy. Calling another transactional method from within the same object may bypass the proxy:

~~~java
@Service
public class ImportService {

    public void runImport() {
        saveBatch(); // self-invocation, may bypass proxy
    }

    @Transactional
    public void saveBatch() {
        // Expected transaction may not be created.
    }
}
~~~

Extract transactional methods to another bean or invoke through the proxy using a clean architecture. Do not rely on annotations if the actual call path bypasses the transaction interceptor.

### 7.2. Thread boundaries

Transaction context is normally bound to a thread. When using `@Async`, an executor, or spawning new threads, transactions do not automatically propagate across threads.

~~~java
@Transactional
public void process() {
    executor.execute(() -> repository.save(...));
}
~~~

The `save` call on the other thread may run in its own transaction or auto-commit depending on configuration. Design workers with their own transaction boundaries and pass IDs/data rather than passing an active `EntityManager`/`Connection`.

### 7.3. Method visibility and proxy mode

How Spring handles method annotations depends on proxy mode, interface/class proxying, and version. Public service methods invoked from another bean are the most predictable pattern.

Verify the actual transaction manager and proxy configuration. Do not rely on annotations placed on private helper methods as if every call were intercepted.

### 7.4. Multiple transaction managers

An application may have multiple `DataSource`s or transaction managers. `@Transactional` must specify the right manager when multiple managers exist:

~~~java
@Transactional(transactionManager = "oracleTransactionManager")
public void updateOracleData() {
    // Oracle work.
}
~~~

If JPA repositories use an Oracle `DataSource` while raw JDBC code acquires connections from another `DataSource`, the two sets of changes are not in the same transaction.

## 8. Testing @Transactional in Spring Test

Spring Test supports test-managed transactions. A test method annotated with `@Transactional` is typically rolled back after the test completes.

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrderInsideTestTransaction() {
        repository.save(new OrderEntity(...));

        assertTrue(repository.findById(...).isPresent());
    }
}
~~~

After the test, Spring rolls back the test-managed transaction by default. This is a convenient way to isolate DML fixtures.

However, there is a critical exception: Oracle DDL causes an implicit commit. If a test runs `CREATE TABLE` or `TRUNCATE` inside the transaction, prior DML fixtures may have committed and will not be rolled back by the test.

### 8.1. @Rollback and @Commit

~~~java
@Test
@Transactional
@Rollback
void rollbackByDefault() {
    // Changes rolled back after test.
}
~~~

~~~java
@Test
@Transactional
@Commit
void commitTestChanges() {
    // Changes committed after test.
}
~~~

`@Commit` instructs Spring not to roll back when the test finishes. Use it only when data must persist after the method and a clear cleanup plan exists.

### 8.2. Tests without test-managed transactions

Some integration tests must verify real transaction boundaries. You can place `@Transactional(propagation = NOT_SUPPORTED)` on the test so the entire method is not wrapped in a test transaction, then use `TransactionTemplate` or service-level transactions.

This lets you verify state after transactions have genuinely committed/rolled back rather than inspecting within the same persistence context.

### 8.3. @BeforeEach and @AfterEach

Spring Test lifecycle methods typically execute inside the test-managed transaction when the test method is transactional. Use `@BeforeTransaction` and `@AfterTransaction` when actions must run outside the test transaction.

Do not run fixture-creating DDL in `@BeforeEach` expecting post-test rollback to clean it up. DDL can commit the transaction.

### 8.4. Preemptive timeouts

Some test frameworks enforce preemptive timeouts by executing the test body on a separate thread. Since Spring transaction context is thread-bound, the test body may run outside the transaction opened by Spring Test.

When using timeouts, understand how the framework executes them and verify thread/transaction binding. Never let test rollback create false confidence.

## 9. Flush is not commit

The JPA persistence context can buffer changes in memory before sending SQL to the database.

~~~java
OrderEntity order = entityManager.find(OrderEntity.class, orderId);
order.setStatus("PAID");

entityManager.flush();
~~~

`flush()` synchronizes pending changes to the database within the current transaction. It does not commit the transaction.

After flush:

- SQL has been sent to the database.
- Constraints and triggers may have executed.
- The transaction can still roll back.
- Locks may still be held.
- Changes are not yet durable or visible to other transactions until commit per isolation semantics.

### 9.1. Why do tests need flush?

If a test only calls `repository.save()` and asserts on in-memory objects, it may never actually test SQL/database behavior.

To test constraints or SQL mappings:

~~~java
repository.save(entity);
entityManager.flush();
~~~

You can then clear the persistence context and re-query to prove data was genuinely persisted:

~~~java
entityManager.clear();
OrderEntity reloaded = repository.findById(id).orElseThrow();
~~~

`flush` surfaces DML errors early. `clear` detaches managed entities so subsequent queries fetch fresh state from the database.

### 9.2. Errors can occur at flush or commit

Standard constraints usually fail when SQL is flushed. `DEFERRABLE` constraints set to deferred mode may only be checked at `COMMIT`.

Therefore, a test that only flushes may not verify full commit behavior.

In Oracle, constraints can be declared deferrable and switched to deferred inside a transaction:

~~~sql
SET CONSTRAINTS ALL DEFERRED;
~~~

Only constraints declared `DEFERRABLE` can delay validation this way. Tests must commit to verify that deferred constraint errors actually trigger.

## 10. Testing real rollback with TransactionTemplate

To prove data does not exist after rollback, query from another transaction after the first transaction ends.

Example:

~~~java
@SpringBootTest
class TransactionRollbackTest {

    @Autowired
    TransactionTemplate transactionTemplate;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackInsertedRow() {
        long id = 900001L;

        transactionTemplate.executeWithoutResult(status -> {
            jdbcTemplate.update(
                "insert into tx_probe(id, note) values (?, ?)",
                id,
                "rollback-test"
            );

            status.setRollbackOnly();
        });

        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from tx_probe where id = ?",
            Integer.class,
            id
        );

        assertEquals(0, count);
    }
}
~~~

This test must run outside another test-managed transaction so `TransactionTemplate` creates and completes an independent transaction. Use `@Transactional(propagation = NOT_SUPPORTED)` on the test class/method if necessary.

Table `TX_PROBE` must be created prior to the test via migrations or schema setup outside the tested transaction.

### 10.1. Testing commit

~~~java
transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "insert into tx_probe(id, note) values (?, ?)",
        id,
        "commit-test"
    );
});

Integer count = jdbcTemplate.queryForObject(
    "select count(*) from tx_probe where id = ?",
    Integer.class,
    id
);

assertEquals(1, count);
~~~

Do not call `setRollbackOnly`. When the callback completes normally, `TransactionTemplate` commits per configuration.

### 10.2. Testing exception rollback

~~~java
assertThrows(IllegalStateException.class, () ->
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into tx_probe(id, note) values (?, ?)",
            id,
            "exception-test"
        );

        throw new IllegalStateException("force rollback");
    })
);
~~~

Then query in a separate transaction to verify the row does not exist.

### 10.3. Testing checked exceptions

Spring defaults to not rolling back on checked exceptions under standard rules. Check the annotation:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importBatch() throws Exception {
    repository.save(...);
    throw new Exception("import failed");
}
~~~

Tests must verify that checked exceptions actually roll back per configured rules—not merely assert that the exception was thrown.

## 11. Testing implicit commit with real Oracle

This test is especially important because H2 or mocks may not reflect Oracle DDL semantics accurately.

Prepare beforehand:

~~~sql
CREATE TABLE tx_ddl_probe (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

Test in a dedicated lab schema:

~~~java
@Test
void oracleDdlCommitsPendingDml() {
    long id = 900101L;

    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into tx_ddl_probe(id, note) values (?, ?)",
            id,
            "dml-before-ddl"
        );

        jdbcTemplate.execute(
            "create table ddl_commit_marker (id number)"
        );

        status.setRollbackOnly();
    });

    Integer count = jdbcTemplate.queryForObject(
        "select count(*) from tx_ddl_probe where id = ?",
        Integer.class,
        id
    );

    assertEquals(1, count);
}
~~~

Expected result on Oracle: the inserted row persists because `CREATE TABLE` implicitly committed the transaction before the DDL. `setRollbackOnly` cannot undo a commit that already occurred in the database.

This test must run in an isolated schema/database because it creates a real object. Afterward, clean up the row via DML in a separate transaction and drop the marker table in a dedicated cleanup step. `DROP TABLE` is also DDL and triggers an implicit commit.

### 11.1. Why can't Spring prevent implicit commit?

The Spring transaction manager manages transactions over the JDBC/JPA connection. However, Oracle enforces implicit commit rules inside the database engine upon receiving DDL.

Spring cannot turn DDL into transactional DML. The transaction manager may still believe a transaction is open while the database has already committed it.

Consequently, when DDL runs inside a Spring transaction:

- Pending DML may have already committed.
- Successful DDL is committed.
- Subsequent DML may belong to a new transaction on the same session.
- When Spring finishes the transaction, rollback only affects the remaining transaction portion, never undoing what DDL already committed.

This is a mismatch between application transaction abstractions and Oracle DDL semantics.

### 11.2. Do not use H2 as proof of Oracle DDL behavior

H2 has an Oracle compatibility mode, but it is not Oracle Database. DDL transaction semantics, PL/SQL, data dictionary, sequences, locking, and driver behavior can all differ.

Implicit commit tests must run on an Oracle version close to production. H2 remains useful for certain unit tests, but never replaces integration tests for Oracle semantics.

## 12. Testing TRUNCATE and DELETE

A test can demonstrate the difference:

~~~sql
-- Prepare data before test.
INSERT INTO tx_probe(id, note) VALUES (20, 'keep');
COMMIT;

-- DELETE can roll back.
DELETE FROM tx_probe WHERE id = 20;
ROLLBACK;

SELECT COUNT(*) FROM tx_probe WHERE id = 20;
-- Expected: 1

-- TRUNCATE is DDL, cannot roll back.
TRUNCATE TABLE tx_probe;

ROLLBACK;

SELECT COUNT(*) FROM tx_probe WHERE id = 20;
-- Expected: 0
~~~

Never run `TRUNCATE` on a shared fixture table. It affects all tests/sessions and cannot be undone by transaction rollback.

To reset test tables:

- Use a dedicated test schema.
- Use temporary tables or data tagged with test keys.
- Use scoped `DELETE` by test identifier when rollback is needed.
- Recreate schemas/containers between test suites if supported by the environment.
- Place DDL setup/teardown outside business transactions.

## 13. DDL in Flyway and Liquibase

Database migrations typically contain DDL such as `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, and constraint changes.

In Oracle, implicit DDL commits mean a migration containing DDL cannot be treated as a single transaction fully reversible via normal `ROLLBACK`.

### 13.1. Flyway

Flyway manages migration versions and ordering. Transaction behavior depends on the database and statement type; Oracle DDL auto-commits even if the tool attempts to wrap migrations in a transaction.

Therefore:

- Never assume a failed DDL migration rolls back all preceding changes.
- Design small migrations whose before/after state is easy to inspect.
- Use idempotent/guarded operations where appropriate.
- If a migration stops mid-way, follow a runbook to repair the schema and update version state per process.
- Never blindly re-run scripts with non-idempotent DDL before determining which statements succeeded.

### 13.2. Liquibase

Liquibase offers a `runInTransaction` attribute on changesets. However, `runInTransaction` cannot disable Oracle's implicit DDL commit.

A changeset containing multiple DDL statements can partially complete before failing. Even if the migration tool marks the state as failed, the database may already contain newly created objects.

Split changesets into small steps and design recovery/forward-fix plans. Inspect `DATABASECHANGELOG` alongside the data dictionary to determine actual state.

### 13.3. Do not treat migration rollbacks like data rollbacks

A migration tool's rollback script is typically a new set of DDL/DML statements intended to return the schema to an equivalent prior shape. It is not an Oracle transaction rollback.

A `DROP`/`ALTER` rollback also commits and can destroy new data written after the migration. Maintain backups, compatibility strategies, and forward-fix plans.

## 14. Sequences and non-transactional side effects

### 14.1. Sequences do not roll back

Example:

~~~sql
CREATE SEQUENCE order_seq START WITH 1;

SELECT order_seq.NEXTVAL FROM dual;
-- Returns 1

ROLLBACK;

SELECT order_seq.NEXTVAL FROM dual;
-- Returns a later value, not 1
~~~

Sequences are designed for concurrent value generation, not gap-free guarantees. An issued `NEXTVAL` is not returned when a transaction rolls back.

Caching, instance restarts, and RAC can widen gaps further. Do not write tests assuming gap-free sequences.

Oracle identity columns are also backed by sequence mechanisms and can have gaps. Never treat contiguous IDs as proof of transaction commits.

### 14.2. Autonomous transactions

PL/SQL can declare an autonomous transaction:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit(
    p_message IN VARCHAR2
)
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

An autonomous transaction is independent of the caller's transaction. If the business transaction rolls back, the committed audit record persists.

This is useful for audit/diagnostic records that must survive failed operations. However, clearly distinguish whether the audit logs an attempt, an error, or a committed business event; do not let audit records mislead readers into thinking the business operation succeeded.

An autonomous routine must end its own transaction with `COMMIT` or `ROLLBACK`; otherwise errors occur when the routine exits.

### 14.3. External side effects

Oracle `ROLLBACK` cannot undo:

- HTTP requests already processed by a remote service.
- Emails already sent.
- Files already written to a filesystem.
- Messages already published to a broker.
- Charges already processed by a payment gateway.
- Independent commits in another database.

For workflows with external side effects, use outbox patterns, idempotency keys, sagas/compensation, or appropriate distributed transaction patterns. Never place HTTP calls mid-database transaction assuming rollback reverses remote effects.

## 15. Testing transactions with native queries and stored procedures

A stored procedure executing in the same database session can participate in the caller's transaction, provided the procedure does not issue `COMMIT`/`ROLLBACK` itself and is not an autonomous transaction.

Procedure example:

~~~sql
CREATE OR REPLACE PROCEDURE update_order_status(
    p_order_id IN NUMBER,
    p_status   IN VARCHAR2
)
IS
BEGIN
    UPDATE orders
       SET status = p_status
     WHERE order_id = p_order_id;
END;
/
~~~

If Spring calls the procedure inside the same transaction, the caller can roll back the `UPDATE`.

However, if the procedure contains:

~~~sql
COMMIT;
~~~

then the caller's transaction is committed. A `ROLLBACK` from Spring cannot undo that commit.

### 15.1. Testing a procedure that joins the transaction

1. Start a transaction.
2. Call the procedure to update data.
3. Read state within the transaction.
4. Mark for rollback.
5. End the transaction.
6. Query from a new transaction.
7. Confirm data reverted to its initial state.

### 15.2. Testing a procedure containing COMMIT

Create a dedicated test procedure containing `COMMIT`. Invoke it inside `TransactionTemplate` and mark rollback. Query in a new transaction to demonstrate that changes committed by the procedure persisted.

Never use self-committing procedures for business operations requiring atomicity with other repository methods.

### 15.3. Native DML

Native update/delete queries also participate in the current transaction when sharing the same connection/context. However, the persistence context can become stale.

~~~java
entityManager.flush();

entityManager.createNativeQuery(
    "update orders set status = 'CLOSED' where order_id = :id"
).setParameter("id", orderId)
 .executeUpdate();

entityManager.clear();
~~~

After `clear`, subsequent queries load state from the database. Flush beforehand to push pending entity changes prior to native DML; clear afterward to avoid retaining stale managed objects.

## 16. Testing constraints and errors at commit time

Not all errors appear immediately when calling `save()`.

### 16.1. Immediate constraints

Standard constraints are typically checked as statements execute/flush:

- `PRIMARY KEY`.
- `UNIQUE`.
- `NOT NULL`.
- `FOREIGN KEY`.
- `CHECK`.

For example, duplicate keys raise `ORA-00001`. Foreign key violations raise `ORA-02291` or `ORA-02292`.

In JPA tests, call `flush` to surface errors at the expected point:

~~~java
entityManager.persist(entity);
assertThrows(PersistenceException.class, entityManager::flush);
~~~

Exact exception types may be wrapped by Spring/Hibernate. Assert on root cause or vendor error codes when needed.

### 16.2. Deferred constraints

Oracle allows `DEFERRABLE` constraints to be validated at the end of a transaction when deferred.

~~~sql
ALTER TABLE child_orders
ADD CONSTRAINT child_orders_parent_fk
FOREIGN KEY (parent_id)
REFERENCES parent_orders(parent_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Inside a transaction:

~~~sql
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO child_orders(child_id, parent_id)
VALUES (1, 999);

-- May not error at this statement.
COMMIT;
-- Constraint is validated at commit.
~~~

Tests that only flush may miss deferred errors. You must test an actual commit.

Not all constraints can be made `DEFERRABLE`; inspect DDL and data dictionary metadata.

## 17. Testing concurrency and locking

Transaction tests are not just single-session commit/rollback checks. Test two competing transactions whenever business logic relies on locking.

### 17.1. SELECT FOR UPDATE

Oracle locks rows acquired by `SELECT FOR UPDATE` until `COMMIT` or `ROLLBACK`.

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 10
FOR UPDATE;
~~~

Concurrency tests should use two separate connections/sessions:

1. Transaction A runs `SELECT FOR UPDATE`.
2. Transaction B attempts to update the same row.
3. B blocks or receives an error depending on timeout/locking clauses.
4. A commits or rolls back.
5. B proceeds or fails as expected.

Never share one JDBC `Connection` for both transactions; doing so will not simulate independent concurrency.

### 17.2. NOWAIT and WAIT

~~~sql
SELECT *
FROM accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

`NOWAIT` does not wait if the row is already locked; it can raise `ORA-00054`.

`WAIT n` waits up to `n` seconds per Oracle syntax. Test both success and lock contention paths.

### 17.3. Deadlocks

If two transactions lock resources in opposite order, Oracle can detect a deadlock and raise `ORA-00060`.

Test deadlocks in a lab using two sessions and synchronization barriers—never arbitrary `sleep`s to guess timing. Applications must handle aborted transactions and retry only when the operation is safe to retry.

### 17.4. Optimistic locking

JPA `@Version` detects lost updates during entity-managed updates. Test two transactions reading the same version: the first commits, the second attempts to update and receives an optimistic locking failure.

If native SQL or stored procedures modify data, they must also maintain the version column when the application relies on optimistic locking.

## 18. Isolation levels and snapshots

Oracle defaults to `READ COMMITTED`. Each `SELECT` normally reads a consistent snapshot as of the start of that statement, rather than a fixed snapshot for the entire transaction.

### 18.1. READ COMMITTED

A single transaction can run the same `SELECT` twice and observe different results if another transaction commits in between.

Tests must verify whether that behavior satisfies business requirements.

### 18.2. SERIALIZABLE

`SERIALIZABLE` provides transaction-level consistency per Oracle semantics, though concurrent write conflicts can trigger `ORA-08177: can't serialize access for this transaction`.

Applications must retry the entire transaction when appropriate. Never retry only the final `UPDATE` statement, because the transaction snapshot and prior decisions may be stale.

### 18.3. Isolation in Spring

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void processOrder() {
    // Work in the current transaction.
}
~~~

Isolation settings may only take effect when a new transaction starts; if the method joins an existing transaction, behavior depends on the transaction manager. Verify propagation and the actual database session.

## 19. Test fixtures and schema lifecycle

A good test starts from a deterministic data state and finishes without polluting other tests.

### 19.1. Separating test schemas

Recommendations:

- Dedicated schema for integration tests.
- Migration setup executed before the test suite.
- Seed data with isolated IDs/keys.
- DML tests using rollback or ID-scoped cleanup.
- DDL setup/teardown run outside test transactions.
- Never run `TRUNCATE`/`DROP` on a schema shared by multiple workers.
- Each parallel test has an independent namespace or schema.

### 19.2. Using Testcontainers or an Oracle test database

H2 can be helpful for simple repository logic, but cannot replace Oracle when testing:

- Implicit DDL commits.
- PL/SQL packages.
- Oracle sequence/identity behavior.
- `REF CURSOR`s.
- Oracle data types.
- Locking and isolation.
- Optimizer hints.
- Data dictionary views.
- Oracle JDBC driver behavior.

Use an Oracle container/image compatible with licensing and CI environments, or an organization-provisioned test database. Pin image/database versions close to production.

### 19.3. Parallel tests

If multiple tests share a schema:

- DDL tests commit their own session's transaction, and DDL on shared objects can cause locks or disrupt other tests' data.
- `TRUNCATE`/`DROP` can wipe objects/data actively used by other tests.
- Shared sequences do not guarantee contiguous IDs.
- Broad predicate cleanups can delete another test's data.

Prefer schema/database isolation or isolated object/data namespaces.

## 20. Testing DDL migrations

Migration tests must verify the schema before and after, not just tool status.

Migration example:

~~~sql
ALTER TABLE orders ADD source_system VARCHAR2(30);

CREATE INDEX idx_orders_source
ON orders(source_system);
~~~

DDL statements commit independently per Oracle semantics. If the second statement fails, the column from the first statement may still exist.

### 20.1. Testing migration failures

1. Build the schema at the pre-migration version.
2. Run the migration in a test Oracle database.
3. Intentionally trigger a failure at a step in the migration test.
4. Inspect which objects were created/altered.
5. Inspect migration tool state.
6. Build a forward-fix or cleanup script.
7. Re-run from the actual state without assuming the database rolled back cleanly.

Never intentionally break a migration in production to test behavior.

### 20.2. Expand-contract

For schema changes with live applications running:

1. Expand: add compatible columns/tables/indexes.
2. Deploy application versions able to read/write both old and new schemas.
3. Backfill data in resumable batches.
4. Switch traffic/logic to the new schema.
5. Contract: drop old columns/objects in a later release once no consumers remain.

This reduces the need for immediate DDL rollbacks. Once DDL has committed, forward-compatible migrations are generally safer than trying to revert structures and data.

## 21. Testing rollback with multiple side effects

A business transaction may span:

- DML in Oracle.
- REST API calls.
- Sending emails.
- Publishing messages.
- Writing files.
- Writing audit logs via autonomous transactions.

Oracle rollback only undoes transactional DML within that same transaction.

### 21.1. Example coordination bug

~~~text
BEGIN DATABASE TRANSACTION
    UPDATE ORDERS
    INSERT PAYMENT
    CALL EXTERNAL PAYMENT API
    API succeeds
    INSERT fails
ROLLBACK DATABASE
~~~

The database rolls back `ORDERS` and `PAYMENT`, yet the payment gateway already charged the card. The system becomes inconsistent between database and external service.

### 21.2. Outbox pattern

Write business changes and outbox events inside the same transaction:

~~~text
Transaction:
    UPDATE ORDERS
    INSERT OUTBOX_EVENT
    COMMIT

Worker:
    Read pending event
    Call remote service with idempotency key
    Mark event delivered
~~~

If the worker crashes after the remote service succeeds but before marking delivered, the event may be re-sent. Remote services must be idempotent or consumers must deduplicate.

### 21.3. Saga/compensation

Some distributed workflows use compensation instead of cross-system rollback. For instance, if payment succeeded but fulfillment fails, invoke a refund operation per business contract.

Compensation is a new business action, not a rollback of the original transaction. It can also fail and requires retries/monitoring.

## 22. Common bugs and how to verify

| Symptom | Possible cause | How to check |
|---|---|---|
| `@Transactional` test leaves data behind | Implicit DDL commit, `@Commit`, `REQUIRES_NEW`, or procedure `COMMIT` | Inspect SQL/transaction boundaries and DDL |
| DML before `CREATE TABLE` does not roll back | Oracle commits before DDL | Separate DDL from test transactions |
| `DELETE` rolls back but `TRUNCATE` does not | `DELETE` is DML, `TRUNCATE` is DDL | Check statement type |
| Spring does not roll back checked exceptions | Default rollback rules | `rollbackFor` or exception design |
| `@Transactional` has no effect | Self-invocation/proxy/thread boundary | Inspect call path and transaction manager |
| `repository.save` shows no SQL | JPA has not flushed | Call `flush` in tests |
| Entity holds stale data after procedure | Stale persistence context | `refresh`/`clear` and re-query |
| Procedure commit breaks atomicity | `COMMIT` inside PL/SQL | Review procedure source |
| Sequence has gaps after rollback | Sequences are non-transactional | Do not assert contiguous IDs |
| Audit persists after rollback | Autonomous transaction | Check `PRAGMA AUTONOMOUS_TRANSACTION` |
| External payment persists after rollback | Off-DB side effect | Outbox/idempotency/compensation |
| Deferred constraint fails only at the end | Validated at `COMMIT` | Test real commit |
| `ORA-00060` | Deadlock | Analyze lock order and transactions |
| `ORA-08177` | Serializable conflict | Retry full transaction when safe |
| `ORA-00054` | `NOWAIT`/resource busy | Check session holding the lock |
| Passes H2 but fails Oracle | Dialect/transaction semantics differences | Oracle integration tests |

## 23. Runbook for investigating transactions that fail to roll back

### Step 1 — Define expected state

Record:

- Database and schema.
- Request/test ID.
- Expected transaction boundary.
- Modified tables/objects.
- Step where the exception occurred.
- Actual data after the method returns.

### Step 2 — Identify the commit source

Look for:

- `COMMIT` inside PL/SQL packages/procedures.
- DDL run directly or via `EXECUTE IMMEDIATE`.
- `TRUNCATE`, `CREATE`, `ALTER`, `DROP`, `GRANT`, `REVOKE`.
- Spring `@Commit` or `@Rollback(false)`.
- `REQUIRES_NEW`.
- Autonomous transactions.
- JDBC connection auto-commit.
- Mismatched transaction managers/`DataSource`s.
- Async/thread boundaries.

### Step 3 — Inspect the persistence context

- Was the entity loaded before native DML?
- Were pending changes flushed?
- Was `clear`/`refresh` called after a procedure?
- Did the test query in the same persistence context or a fresh transaction?
- Were entities detached after rollback?

### Step 4 — Inspect the database

Use a new session or independent connection to query data. Never rely solely on re-reading entities in the same persistence context.

If DDL is suspected, check object metadata and DML row state in the test schema.

### Step 5 — Fix

- Separate DDL from business transactions.
- Remove unnecessary `COMMIT`s from procedures.
- Align transaction managers/`DataSource`s.
- Add `rollbackFor` where needed.
- Fix proxy/self-invocation or thread boundaries.
- Use outbox for external side effects.
- Add real Oracle tests.

## 24. Checklist for testing transactions and DDL

### Basic transactions

- [ ] Committed DML persists after transaction.
- [ ] Rolled-back DML does not persist after transaction.
- [ ] `SAVEPOINT` rolls back the right subset of changes.
- [ ] Runtime exceptions roll back per contract.
- [ ] Checked exceptions have explicit rollback rules.
- [ ] Procedures do not commit unintentionally.
- [ ] `REQUIRES_NEW` tested independently.

### Oracle DDL

- [ ] Tested that DDL commits pending DML prior to DDL.
- [ ] Tested that successful DDL persists after rollback.
- [ ] Tested that failed DDL does not guarantee preceding DML can still roll back.
- [ ] Tested `TRUNCATE` differs from `DELETE`.
- [ ] Tested dynamic DDL via `EXECUTE IMMEDIATE`.
- [ ] Avoided running DDL inside test-managed transactions when expecting full rollback.
- [ ] Tested migration failures on Oracle.

### Spring/JPA

- [ ] `@Transactional` passes through proxy.
- [ ] Transactions are not lost across threads/async boundaries.
- [ ] `DataSource` and transaction manager match.
- [ ] `flush` used when verifying SQL/constraints.
- [ ] `clear`/`refresh` handles stale persistence context.
- [ ] Bulk DML accounts for auditing/versioning/callbacks.
- [ ] Rollback tests verified from a fresh transaction.

### Oracle-specific side effects

- [ ] Sequence gaps accepted.
- [ ] Autonomous transactions reviewed.
- [ ] Deferred constraints verified at commit.
- [ ] Locking/deadlocks/concurrency tested.
- [ ] External side effects covered by idempotency/outbox/compensation.

## 25. Key takeaways

- DML such as `INSERT`/`UPDATE`/`DELETE` can roll back prior to `COMMIT`; `COMMIT` ends the transaction and makes changes durable.
- `SAVEPOINT` allows partial rollback within the same transaction; it does not create an independent transaction.
- Oracle executes an implicit `COMMIT` before syntactically valid DDL and commits after successful DDL.
- Uncommitted DML prior to `CREATE`/`ALTER`/`DROP`/`TRUNCATE` can commit before DDL executes; subsequent `ROLLBACK` cannot undo it.
- Failed DDL does not mean preceding DML can still roll back; the pre-DDL implicit commit may already have happened.
- `TRUNCATE` is DDL and does not roll back like `DELETE`.
- DDL inside `EXECUTE IMMEDIATE` retains implicit commit semantics.
- Spring `@Transactional` cannot suppress implicit commits performed by Oracle.
- Spring rolls back `RuntimeException`/`Error` by default; checked exceptions need explicit rollback rules to roll back.
- Self-invocation, async/thread boundaries, and multiple transaction managers can keep transactions from working as expected.
- JPA `flush` sends SQL to the database without committing; constraints may fail at flush or commit depending on constraint type.
- Native DML/stored procedures can make managed entities stale; use `flush`, `clear`, or `refresh` intentionally.
- Self-committing procedures break atomicity with outer JPA/JDBC transactions.
- `REQUIRES_NEW` and autonomous transactions commit independently; outer rollbacks do not undo them.
- Sequence `NEXTVAL` is non-transactional; rollback does not return issued numbers.
- HTTP, email, files, and message brokers do not roll back with Oracle; use outbox, idempotency, or compensation.
- DDL migrations on Oracle need forward-fix/recovery plans; never assume migration tools can roll back DDL.
- Tests for implicit commits, PL/SQL, locking, sequences, and migrations must run on real Oracle or a compatible Oracle environment, not solely H2.
- Verify rollbacks from a new transaction/connection; objects in a persistence context are not proof of database commit or rollback.

### Reference Oracle, Spring, and JPA documentation

- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html) — Transactions, commits, rollbacks, savepoints, and consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — DDL, DML, `TRUNCATE`, transaction control, and constraint syntax.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — Dynamic SQL, autonomous transactions, and stored program behavior.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — `@Transactional`, propagation, rollback rules, and transaction managers.
- [Spring Framework Reference — Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html) — Test-managed transactions, rollback, and commit behavior.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — Persistence context, flush, bulk operations, locking, and transaction semantics.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/testing/index.html) — Integration testing and database test setup.
- [Flyway Documentation](https://documentation.red-gate.com/flyway) and [Liquibase Documentation](https://docs.liquibase.com/) — Migration execution and recovery practices.

Oracle DDL semantics are database-specific and differ from transactional DDL behavior in other engines. Confirm the deployed Oracle release, Spring transaction manager, JPA provider, and JDBC driver; run DDL/rollback integration tests in an isolated Oracle schema before relying on test rollbacks or migration rollbacks in production.
