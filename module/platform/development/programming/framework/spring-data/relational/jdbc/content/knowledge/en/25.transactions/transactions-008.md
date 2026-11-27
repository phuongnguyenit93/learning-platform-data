# Isolation, readOnly, timeout, and Driver-Dependent Limits

In Spring Data JDBC, transaction attributes are typically configured using the @Transactional annotation. Beyond propagation, the annotation allows choosing an isolation level, marking a transaction read-only, and setting a timeout. These attributes are applied by the transaction manager, JDBC connection, driver, and database. The same declaration can have different effects depending on the database or when a method joins an existing transaction.

## 1. Role of the Transaction Manager and JDBC Connection

Spring uses PlatformTransactionManager to coordinate transactions. In a Spring Data JDBC application, the transaction manager is typically configured around a DataSource, such as JdbcTransactionManager or DataSourceTransactionManager.

When a transaction begins, the transaction manager acquires a JDBC Connection, configures isolation/read-only settings, and starts the transaction. Spring Data JDBC repositories and JdbcTemplate can participate in the transaction together if they share the same DataSource and transaction manager.

~~~mermaid
flowchart TD
    A[Service method with @Transactional] --> B[Spring transaction interceptor]
    B --> C[PlatformTransactionManager]
    C --> D[JDBC Connection from DataSource]
    D --> E[Configure isolation / readOnly / timeout]
    E --> F[Execute SQL via Repository or JdbcTemplate]
    F --> G[(Database)]
    G --> H[Commit or rollback]
~~~

The annotation describes the application's intent. The transaction manager translates that intent into connection/transaction settings; the JDBC driver translates JDBC calls into behavior supported by the database. You cannot look at the annotation alone and conclude the database is guaranteed to enforce a given isolation level or timeout identically everywhere.

## 2. Declaring @Transactional

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    isolation = Isolation.READ_COMMITTED,
    timeout = 5
)
public void updateCustomer(Long id, String name) {
    // Read and update the aggregate inside a transaction with a 5-second timeout.
}
~~~

Commonly used attributes:

| Attribute | Purpose |
|---|---|
| propagation | Join an existing transaction or create a new one |
| isolation | Isolation level for a new transaction |
| readOnly | Hint indicating a read-only transaction |
| timeout | Transaction time limit as supported by the transaction manager |
| rollbackFor / noRollbackFor | Customize exception types that trigger rollback |

The isolation, readOnly, and timeout attributes must be understood in relation to propagation. When a method joins an existing transaction, the outer physical transaction usually determines these settings.

## 3. What Is an Isolation Level?

Isolation describes the degree to which one transaction observes concurrent modifications made by other transactions. The isolation level affects which anomalies can occur when multiple transactions read/write the same data.

Three anomalies commonly used in explanations:

- **Dirty read**: a transaction reads uncommitted data from another transaction. The writing transaction may roll back later, meaning the read data never actually became committed data.
- **Non-repeatable read**: the same row is read twice within a transaction and returns different values because another transaction committed an update between the two reads.
- **Phantom read**: the same query condition is executed twice, and the set of matching rows changes because another transaction inserted, deleted, or modified rows so they begin or stop matching the condition.

General table according to SQL standard isolation definitions:

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| READ_UNCOMMITTED | Possible | Possible | Possible |
| READ_COMMITTED | No | Possible | Possible |
| REPEATABLE_READ | No | No | Possible per SQL standard model |
| SERIALIZABLE | No | No | No per SQL standard model |

This is a conceptual description per the standard, not an absolute prediction for every engine. Databases may use MVCC, snapshot isolation, predicate locks, or proprietary mechanisms. Some engines enforce stronger guarantees than requested; others map isolation levels to different behaviors. Check database documentation and test with two concurrent connections/transactions when verification is needed.

## 4. The Isolation Enum in Spring

Spring provides values in the Isolation enum:

~~~java
import org.springframework.transaction.annotation.Isolation;

Isolation.DEFAULT;
Isolation.READ_UNCOMMITTED;
Isolation.READ_COMMITTED;
Isolation.REPEATABLE_READ;
Isolation.SERIALIZABLE;
~~~

Meanings:

- **DEFAULT**: uses the default isolation of the transaction manager/database. This is the default value of @Transactional.
- **READ_UNCOMMITTED**: loosest read level per the SQL standard model; can read uncommitted data if supported by the database.
- **READ_COMMITTED**: reads only committed data; a later read can observe new commits from other transactions.
- **REPEATABLE_READ**: guarantees rows already read do not change on re-read under the standard definition; phantom behavior may still depend on the engine.
- **SERIALIZABLE**: requests outcomes equivalent to serial execution of transactions; can increase locking, retries, or serialization failures.

Example:

~~~java
@Transactional(isolation = Isolation.REPEATABLE_READ)
public OrderSummary calculateSummary(Long customerId) {
    // Reads inside the transaction need a higher isolation level.
}
~~~

Do not choose SERIALIZABLE by default for every method. Higher isolation levels can increase contention, blocking, deadlocks, or serialization failures. Choose the lowest level that still satisfies the use case's invariants and database behavior.

## 5. DEFAULT Uses the Database's Isolation Level

If isolation is omitted:

~~~java
@Transactional
public void processOrder(Long orderId) {
    // ...
}
~~~

Spring uses Isolation.DEFAULT. The transaction manager does not request a different isolation level; the connection/database applies its default.

Defaults differ across database engines and can change via database configuration. Do not assume every application runs under READ_COMMITTED or REPEATABLE_READ.

You can inspect JDBC metadata:

~~~java
try (Connection connection = dataSource.getConnection()) {
    int level = connection.getTransactionIsolation();
}
~~~

In real application code, the snippet above is only for API illustration; connections must be closed properly, and you should avoid acquiring an independent connection to infer the isolation of a currently running transaction. JDBC DatabaseMetaData also offers supportsTransactionIsolationLevel to see which levels the driver reports supporting.

## 6. Drivers and Databases Can Constrain Isolation

JDBC defines isolation levels, but actual capabilities depend on the driver and database:

- The driver might not support a specific level.
- The database might map a requested level to a stronger or engine-specific behavior.
- Some engines disallow changing isolation once a transaction has started.
- Some databases use MVCC/snapshots rather than relying purely on locks.
- Isolation may be configured at the database, connection, or transaction level.
- Some concurrency bugs appear only under concurrent load and are hard to catch in sequential tests.

You can check support via DatabaseMetaData:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    boolean supportsRepeatableRead =
            metadata.supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_REPEATABLE_READ);

    int currentIsolation = connection.getTransactionIsolation();
}
~~~

Metadata results are information reported by the driver; confirm with DBMS documentation and integration tests. If a driver does not support the requested isolation level, the transaction manager may throw an error while configuring the connection or the database may apply its own behavior.

## 7. Why Can a Participating Method's Isolation Be Ignored?

Suppose service A opens a READ_COMMITTED transaction and calls service B:

~~~java
@Service
public class CheckoutService {
    private final InventoryService inventory;

    public CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void checkout() {
        inventory.reserveStock();
    }
}

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserveStock() {
        // ...
    }
}
~~~

The default propagation of @Transactional is REQUIRED. When reserveStock is called while checkout already has an active transaction, it joins the existing transaction. No new physical transaction is created just because the inner method requests SERIALIZABLE. The outer transaction's isolation level remains in effect.

Similarly, timeout or readOnly declared on a method joining an existing transaction usually does not alter the timeout or read-only setting of the already-started transaction.

If the inner method needs its own physical transaction configuration, REQUIRES_NEW can create a new transaction; however, it carries consequences for connections, commit/rollback, and consistency. Use it only when independence is truly required.

You can enable strict checking of existing transactions via validateExistingTransaction on the transaction manager to detect incompatible isolation/read-only settings instead of silently joining with the outer configuration. Specific configuration APIs depend on the transaction manager.

## 14. Choosing Isolation Based on Business Invariants

Do not pick an isolation level simply because a higher-sounding name feels safer. Start from the anomalies that the business cannot tolerate.

| Need | What to protect | Direction to consider |
|---|---|---|
| Reading committed data is sufficient | No dirty reads | READ_COMMITTED is a common starting point |
| Re-reading the same row must remain stable | Avoid non-repeatable reads | REPEATABLE_READ or appropriate snapshot mechanism |
| Checking a condition over a set of rows and avoiding phantoms | Result set must stay consistent per requirement | SERIALIZABLE or dedicated locking/constraints/query strategy |
| Read-only report with no writes | Read intent and potential optimizations | readOnly=true |
| Task must finish within a time limit | Limit transaction/statement duration | timeout paired with appropriate statement/query and network timeouts |

For example, when checking remaining available slots: if two transactions both read available = 1, both decide to reserve, and then write, merely raising isolation may not be the only or optimal solution. You can use an atomic conditional update:

~~~sql
UPDATE event_slots
SET available = available - 1
WHERE id = :id
  AND available > 0;
~~~

Then check the update count. Database constraints, locks, or optimistic locking can protect invariants more explicitly depending on the model. Isolation is one part of concurrency design, not a replacement for all data constraints.

## 15. Locking, Deadlocks, and Serialization Failures

Higher isolation levels can cause the database to hold locks longer or perform stricter conflict checks. Possible outcomes include:

- Transactions wait on locks and exceed timeouts.
- Deadlocks cause the database to pick one transaction as a victim.
- Serializable transactions are rejected at commit because they cannot be serialized cleanly.
- The application receives data access exceptions and must roll back/retry.

Retries must be deliberate. Only retry errors known to be transient, bound the number of attempts, apply backoff, and ensure the use case is safe to rerun. Do not retry every exception; sending emails, charging payments, or calling external services does not roll back automatically with the database transaction.

## 16. Transaction Manager Limitations

Spring's transaction abstraction allows configuring isolation, readOnly, and timeout, but actual effectiveness depends on the transaction manager:

- **JdbcTransactionManager/DataSourceTransactionManager** manages JDBC transactions for a single DataSource.
- **JtaTransactionManager** coordinates JTA transactions and has different semantics/capabilities.
- **Custom transaction managers** may support some attributes while ignoring or handling others differently.

With Spring Data JDBC, ensure the transaction manager governs the exact DataSource used by the repositories. If multiple transaction managers exist, specify the bean via @Transactional's transactionManager attribute when needed.

Do not set isolation/timeout on one transaction manager and then run JDBC against a DataSource not managed by that manager. Statements may then execute outside the transaction the application assumes is active.

## 17. Driver/Database Limits and How to Test Them

A practical verification process:

1. Identify the database engine and version.
2. Identify the JDBC driver and version.
3. Identify the configured transaction manager.
4. Check default isolation and levels reported as supported by the driver.
5. Run integration tests with two independent connections to observe the anomaly you want to control.
6. Enable SQL/transaction logging in development to verify transaction boundaries.
7. Test timeout using a controlled long-running query in a test database.
8. Verify data state after commit/rollback.

You can inspect metadata:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());

    System.out.println(
            metadata.supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_SERIALIZABLE)
    );
}
~~~

Metadata is an initial signal. To confirm behavior, run integration tests against the exact production database/driver or Testcontainers using the same engine and a matching version. H2 can be helpful for fast tests, but it does not prove all semantics of PostgreSQL, MySQL, SQL Server, Oracle, or other databases.

## 18. Common Mistakes When Configuring @Transactional

| Symptom | Common cause | Fix |
|---|---|---|
| Isolation declared as SERIALIZABLE, yet behavior differs | Method joined outer transaction via REQUIRED | Check which method actually starts the physical transaction |
| Timeout on inner method has no effect | Method joined outer transaction that already has a different timeout | Place timeout on the transaction-starting boundary or use suitable propagation |
| DML still executes in a readOnly transaction | Driver/database treats readOnly as a hint | Use DB permissions if writes must be blocked |
| DML rejected when readOnly=true | Database enforces read-only transaction mode | Remove readOnly from write use cases |
| Timeout does not stop HTTP calls | Transaction timeout is not an HTTP client timeout | Configure dedicated timeouts on the HTTP client |
| Query does not stop on time | Driver/statement does not enforce the expected query timeout | Use JdbcTemplate, statement timeout, or appropriate DB timeout |
| Isolation unsupported | Driver/database restricts that isolation level | Check DatabaseMetaData and DBMS documentation |
| Transaction does not cover both repository and JdbcTemplate | Different DataSource/transaction manager or manually opened connection | Share the same DataSource and Spring transaction-aware access |
| @Transactional does not run on internal method call | Self-invocation bypasses proxy | Call via Spring bean/proxy or reorganize service |
| SERIALIZABLE causes deadlocks/serialization failures | Contention or long-lived transactions | Narrow transaction scope, add controlled retries, re-evaluate isolation |
| Repeated reads still see different data | Database semantics differ from assumptions or transaction actually ended | Check engine, isolation, and transaction boundaries |

## 19. Notes on Proxies and @Transactional Placement

In Spring's default proxy configuration, @Transactional applies when calls pass through the Spring bean proxy. Calling another transactional method via this.method() inside the same object generally bypasses the proxy, so the annotation on the called method may not apply as expected.

Example not to rely on self-invocation:

~~~java
@Service
public class ReportService {
    public void generate() {
        loadSnapshot(); // Internal call, bypasses proxy.
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void loadSnapshot() {
        // ...
    }
}
~~~

You can move the transactional method to a separate service bean and inject it into ReportService. Calls through the bean proxy then trigger the transaction interceptor properly.

In addition, Spring's default rollback rules generally roll back on RuntimeException and Error, and do not automatically roll back on all checked exceptions. If a use case requires rollback for checked exceptions, configure rollbackFor accordingly. Timeout/isolation settings do not alter these rollback rules.

## 20. Example Read-Reporting Service with Isolation and Timeout

~~~java
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReportService {
    private final OrderRepository orders;

    public OrderReportService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true,
        timeout = 10
    )
    public List<OrderSummary> loadReport(LocalDate from, LocalDate to) {
        return orders.findSummariesCreatedBetween(
                from.atStartOfDay(),
                to.plusDays(1).atStartOfDay(),
                Sort.by(Sort.Order.asc("createdAt"))
        );
    }
}
~~~

This example expresses clear intent: a read-only report wanting stable reads within the transaction and a time limit. Confirm that the database/driver supports REPEATABLE_READ with the desired semantics and that the repository query genuinely runs inside this transaction. If this method is called inside an outer transaction, the outer configuration may dictate the effective isolation and timeout.

## 21. Lab Exercise: Observing isolation, readOnly, and timeout

Use a test database and two independent connections. Create the table:

~~~sql
CREATE TABLE account_balance (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO account_balance(id, balance) VALUES (1, 100.00);
~~~

Practice across isolation levels:

1. Transaction A reads balance.
2. Transaction B updates balance to 150 and commits.
3. Transaction A reads the same row again.
4. Observe the difference between READ_COMMITTED and REPEATABLE_READ on your database.
5. Have Transaction B update without committing yet; check whether Transaction A can read uncommitted data at levels supported by the driver/database.
6. With readOnly=true, test an UPDATE statement in the test database to see whether the system treats it merely as a hint or rejects DML.
7. With a short timeout, run a query with a controlled wait time and observe the exception/rollback.
8. Call a REQUIRED method inside a transaction with a different isolation level to confirm which setting is preserved.
9. Inspect JDBC metadata and record the database/driver versions alongside your findings.

Do not rely on H2 as sole proof if production runs a different DBMS. Isolation and timeout behavior must be verified on the target engine.

## 22. Key Principles to Remember

- @Transactional expresses intent; the transaction manager, JDBC driver, and database determine how it is actually applied.
- Isolation.DEFAULT uses the database/transaction manager default.
- READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ, and SERIALIZABLE provide increasing anomaly protection in the SQL standard model; DBMS implementations may vary.
- Isolation is configured only when starting a physical transaction; a REQUIRED method joining an existing transaction normally uses the outer transaction's isolation.
- readOnly is a transaction hint/attribute, not an authorization mechanism or a guarantee that all DML is blocked.
- timeout is normally specified in seconds and depends on the transaction manager/driver; it is not a hard deadline for arbitrary code or HTTP calls.
- When joining an existing transaction, isolation, readOnly, and timeout declared on the inner method normally do not modify the outer transaction.
- JdbcTemplate can integrate transaction timeouts via Spring JDBC; JDBC code managing Statement directly must verify query timeouts explicitly.
- Higher isolation can increase blocking, deadlocks, and serialization failures; retries must be bounded and safe.
- Share the same DataSource/transaction manager so repositories and JDBC templates join the same transaction.
- Verify behavior against the real database and JDBC driver using integration tests, not merely by reading annotations or testing on H2.

In Spring Data JDBC, isolation, readOnly, and timeout are requests at the transaction boundary. Choose them according to use-case invariants and requirements, place them on the method that actually starts the transaction, and verify them on the running transaction manager, driver, and database. That avoids the false expectation that a single annotation forces every database to behave identically or aborts any kind of work after a fixed number of seconds.


## 8. readOnly: Hint for Read-Only Transactions

Declaration:

~~~java
@Transactional(readOnly = true)
public List<CustomerSummary> searchCustomers(String city) {
    return customerRepository.findSummariesByCity(city);
}
~~~

readOnly indicates that the use case intends only to read data. The transaction manager can pass this hint down to the JDBC Connection via setReadOnly(true), or apply specific optimizations if supported by the persistence technology.

In Spring Data JDBC, it is useful for expressing intent and letting the driver/database optimize read paths where supported.

### readOnly Is Not an Authorization Mechanism

Do not treat readOnly=true as a security barrier guaranteeing writes are impossible:

- Some drivers treat read-only as a hint and do not block DML.
- Some databases enforce a read-only transaction mode and reject write statements.
- The transaction manager may ignore the hint if unsupported.
- Raw SQL remains subject to rules enforced by the database and connection.

If you need to guarantee a user only has read privileges, use appropriate database users/permissions and application authorization. Do not rely on the annotation's readOnly attribute as a security control.

### Do Not Mark Write Use Cases as readOnly

The following example is contradictory:

~~~java
@Transactional(readOnly = true)
public void renameCustomer(Long id, String name) {
    Customer current = customers.findById(id).orElseThrow();
    customers.save(current.rename(name));
}
~~~

The outcome depends on the transaction manager and database. Some systems reject the write; others may still execute it. Declare readOnly=true for read-only transactions, and use standard read-write transactions for updating use cases.

## 9. How Can readOnly Affect the Connection?

With a JDBC transaction manager, Spring can invoke Connection.setReadOnly(true) before beginning the transaction. The driver may forward the hint to the database to optimize execution or enforce restrictions.

Not all drivers behave alike:

- Some accept it without significant optimization.
- Some use read-only as a signal for an appropriate access path in certain setups.
- Some databases reject write statements inside a read-only transaction.
- Some systems treat it purely as advisory metadata.

Do not assume readOnly automatically routes queries to a read replica. DataSource routing is a separate configuration; ensure your transaction manager, connection routing, and consistency requirements are designed cohesively.

## 10. timeout: Transaction Time Limit

Declare timeout in seconds:

~~~java
@Transactional(timeout = 5)
public void processPayment(Long paymentId) {
    // JDBC operations inside the transaction.
}
~~~

timeout=5 requests a 5-second deadline for the transaction as supported by the transaction manager. The value is normally in seconds, not milliseconds.

If timeout is omitted, the transaction uses the transaction manager's default timeout (typically no specific timeout unless the manager is configured otherwise).

Timeout should not be mistaken for a hard circuit breaker for all Java code:

- It does not necessarily interrupt a long-running CPU computation that does not interact with the transaction.
- It does not automatically set timeouts for external HTTP calls or RPCs.
- It does not guarantee a database statement stops immediately if the driver does not support or enforce query timeouts.
- It does not replace connection pool, socket, or HTTP client timeouts.

## 11. How Is Timeout Applied to JDBC Statements?

Spring JDBC can apply the transaction timeout to a Statement via DataSourceUtils and JdbcTemplate support. Therefore, statements executed through JdbcTemplate within the transaction can receive the appropriate query timeout.

~~~java
@Transactional(timeout = 3)
public int updateStatus(Long id) {
    return jdbcTemplate.update(
            "UPDATE orders SET status = ? WHERE id = ?",
            "PROCESSING",
            id
    );
}
~~~

For JDBC code that manages Statement/Connection manually, do not assume Spring's timeout is applied automatically if the code bypasses Spring's helpers/transaction-aware APIs. Check statement timeouts explicitly or use JdbcTemplate to leverage built-in integration.

Additionally, transaction timeout and database query timeout are related but distinct concepts. The database may have its own statement timeout; the connection pool has a connection acquisition timeout; the socket/driver has a network timeout. Configure each layer appropriately.

## 12. timeout and an Already-Existing Transaction

Suppose an outer method opens a transaction with a 30-second timeout, and then calls an inner method with a 2-second timeout and REQUIRED propagation. The inner method joins the existing transaction; the 2-second timeout normally does not change the outer physical transaction's deadline.

~~~java
@Service
public class ImportService {
    private final CustomerImportWriter writer;

    public ImportService(CustomerImportWriter writer) {
        this.writer = writer;
    }

    @Transactional(timeout = 30)
    public void importBatch() {
        writer.writeRows();
    }
}

@Service
public class CustomerImportWriter {
    @Transactional(timeout = 2)
    public void writeRows() {
        // Joins existing transaction via REQUIRED.
    }
}
~~~

If the inner method needs an independent transaction with its own timeout, REQUIRES_NEW can be considered. Then the outer transaction is suspended and the new transaction gets its own timeout; however, it can also commit independently and requires an extra connection. Do not choose REQUIRES_NEW solely to enforce a shorter timeout if the business requires the whole batch to roll back together.

## 13. Combining isolation, readOnly, and timeout

Multiple attributes can be configured on the same method:

~~~java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true,
    timeout = 10
)
public Report loadConsistentReport(LocalDate from, LocalDate to) {
    // Read data within a read-only transaction.
}
~~~

Meaning:

- Requests REPEATABLE_READ isolation for a new transaction.
- Marks the transaction read-only.
- Requests a 10-second timeout.
- Read operations through repositories/JDBC participate in the transaction if they use the same DataSource and transaction manager.

However, if the method is called inside an existing transaction with REQUIRED, the isolation, readOnly, and timeout attributes declared on this method usually do not override the outer transaction's configuration. Always identify which method actually starts the physical transaction.



