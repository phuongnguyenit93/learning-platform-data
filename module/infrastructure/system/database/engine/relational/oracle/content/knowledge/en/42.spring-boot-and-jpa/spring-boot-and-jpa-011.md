# Read-Only, Isolation, Flush, and Practical Locking Behavior in Oracle

In a Spring Boot application using JPA/Hibernate with Oracle Database, **read-only**, **transaction isolation**, **flush**, and **locking** frequently appear together, yet they control distinct layers. Misunderstanding them can lead to assuming a transaction cannot write data when Oracle still allows DML, or thinking `save()` immediately writes and commits when the SQL is still sitting in the persistence context. A normal read query can see consistent data without locking rows, whereas a `flush()` can emit DML and hold row locks until the transaction ends.

Spring's `@Transactional(readOnly = true)` is primarily a transaction hint enabling optimizations in the transaction manager, JDBC driver, and JPA provider. With Hibernate, Spring Data JPA can set the flush mode to `MANUAL` to skip dirty checking and auto-flushes. This flag is **not automatically equivalent** to Oracle's `SET TRANSACTION READ ONLY`, which is a database-enforced mode establishing a transaction-level consistent snapshot and prohibiting DML.

Oracle defaults to `READ COMMITTED` with statement-level read consistency. Normal `SELECT` statements read committed versions via multiversion concurrency control (MVCC) without locking the rows read. DML and `SELECT ... FOR UPDATE` acquire row locks, which remain held until `COMMIT` or `ROLLBACK`. JPA flushing determines when SQL actually reaches Oracle, which in turn determines when locks start being held.

This lesson belongs to the **Spring Boot and JPA** chapter of Database Engine Relational Oracle. It focuses on Spring transaction management, read-only hints, Oracle isolation levels, persistence context and flushing, optimistic/pessimistic locking, row-lock behavior, lock waits, and investigating blockers in Oracle.

After this lesson, you will be able to:

- Distinguish Spring read-only transactions from Oracle read-only transactions.
- Understand `@Transactional`, propagation, isolation, and rollback rules.
- Know when a method's isolation setting applies versus when an outer transaction governs.
- Distinguish `READ COMMITTED`, `SERIALIZABLE`, and `READ ONLY` in Oracle.
- Understand why Oracle does not support `READ UNCOMMITTED` and `REPEATABLE READ` as separate isolation levels.
- Explain persistence context, dirty checking, flush, and commit.
- Understand the effects of `FlushMode` `AUTO`, `COMMIT`, and Hibernate `MANUAL`.
- Use `flush()`, `clear()`, `refresh()`, and Spring Data `saveAndFlush()` appropriately.
- Distinguish bulk JPQL DML from normal entity state changes.
- Understand MVCC and row-level locking in Oracle.
- Choose optimistic locking with `@Version` or pessimistic locking with `@Lock`.
- Use `SELECT FOR UPDATE`, `NOWAIT`, `WAIT`, and `SKIP LOCKED` in the right scenarios.
- Know when locks are acquired and when locks are released.
- Investigate blocking sessions, TX/TM locks, and `ORA-00054`, `ORA-00060`, and `ORA-08177`.
- Design short transactions with clear boundaries aligned with business consistency.

> **Example scope:** Java examples use Spring Boot 3, Jakarta Persistence (`jakarta.persistence`), and Oracle Database 19c. For Spring Boot 2, replace `jakarta.persistence` with `javax.persistence` and check your exact Spring/Hibernate versions. Certain behaviors such as flush modes, lock timeouts, and generated SQL depend on the JPA provider/dialect; inspect your application's actual SQL.

## 1. Four Conceptual Layers to Distinguish

| Concept | Responsible Layer | Core Question |
| --- | --- | --- |
| Read-only | Spring transaction manager, JDBC driver, JPA provider, or Oracle transaction | Is the transaction optimized for reads or blocked from writes by the database? |
| Isolation | Oracle transaction and Spring transaction manager | Which version of data does a transaction observe? |
| Flush | JPA persistence context/Hibernate | When are in-memory changes sent as SQL to the database? |
| Locking | Oracle Database and JPA lock API | Which transaction holds a row lock, and which must wait? |

These layers interact but do not substitute for one another:

- `readOnly = true` does not automatically create an Oracle transaction-level snapshot.
- Isolation is not synonymous with locking every row read.
- Flush is not commit.
- Commit releases locks, whereas flush does not release locks.
- A normal `SELECT` in Oracle `READ COMMITTED` does not acquire row locks.
- Pessimistic locks can acquire row locks even before the application runs `UPDATE`.

## 2. How Does Spring @Transactional Work?

Spring uses a transaction manager to start, join, commit, or roll back transactions. In Spring Boot JPA, the transaction manager is typically `JpaTransactionManager` paired with a JPA provider like Hibernate.

### 2.1. Default Configuration

If you simply write:

~~~java
@Transactional
public void createOrder() {
    // business logic
}
~~~

Spring `@Transactional` defaults are:

| Attribute | Default |
| --- | --- |
| propagation | REQUIRED |
| isolation | DEFAULT |
| readOnly | false |
| timeout | Transaction system default timeout or unlimited |
| rollback | RuntimeException and Error |

Checked exceptions do not trigger rollback under Spring's default rules. If a business operation must roll back on checked exceptions, specify `rollbackFor`.

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // multi-step import
}
~~~

### 2.2. Place Transaction Boundaries on Services

Place transaction boundaries on service methods representing a business unit of work. Repositories focus on querying and persistence.

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
    public void confirmOrder(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        order.confirm();
        paymentRepository.markReady(orderId);
    }
}
~~~

When both repositories use the same transaction manager and transaction, their changes commit or roll back as one business unit.

### 2.3. @Transactional Relies on Proxies

In default proxy mode, Spring intercepts only calls passing through the proxy. Calling a `@Transactional` method from another method on the same object (self-invocation) does not create a new transaction interception.

~~~java
@Service
public class ImportService {

    public void runImport() {
        saveChunk(); // self-invocation, bypasses proxy
    }

    @Transactional
    public void saveChunk() {
        // may not run with the transaction you expect
    }
}
~~~

Move transactional methods to another bean or call through a Spring proxy. Never rely on an annotation without verifying calls are actually intercepted.

### 2.4. Annotations Do Not Create Transactions on Their Own

`@Transactional` is metadata. The application needs transaction management enabled and an appropriate transaction manager configured. If the annotation is unprocessed, code runs without the expected transaction boundary.

## 3. Propagation and Existing Transactions

Propagation determines whether a method joins an active transaction or starts a new one.

### 3.1. REQUIRED

`REQUIRED` is the default:

- If no transaction exists, Spring starts a new one.
- If a transaction exists, the method joins it.

~~~java
@Transactional
public void placeOrder() {
    reserveInventory();
    createInvoice();
}

@Transactional
public void reserveInventory() {
    // joins placeOrder's transaction
}
~~~

If `reserveInventory()` fails and its exception triggers rollback, `placeOrder()`'s changes can roll back as well.

### 3.2. REQUIRES_NEW

`REQUIRES_NEW` suspends the outer transaction and starts a new physical transaction.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    // independent transaction
}
~~~

This helps when audit records must commit independently, but watch connection pools and lock dependencies. The new transaction may wait for a row lock held by the outer transaction while the outer transaction waits for the inner method to return, causing unnecessary waits or application-level deadlocks.

### 3.3. Isolation on Methods Joining an Outer Transaction

The `isolation` attribute takes effect only when Spring actually begins a new transaction—typically `REQUIRED` or `REQUIRES_NEW` per Spring documentation. When a `REQUIRED` method joins an existing transaction, declaring isolation on the inner method usually does not alter the outer transaction's isolation.

Example:

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outerOperation() {
    innerOperation();
}

@Transactional(isolation = Isolation.SERIALIZABLE)
public void innerOperation() {
    // joins outerOperation's transaction
    // SERIALIZABLE isolation does not upgrade the existing transaction
}
~~~

You can enable `validateExistingTransaction` on the transaction manager to reject isolation/read-only mismatches rather than silently joining an incompatible transaction. Configuration depends on the transaction manager.

### 3.4. Timeouts and Lock Hold Duration

Spring transaction timeouts do not replace Oracle lock timeouts. A transaction can hold row locks throughout processing, including time spent calling external services or waiting on I/O. Keep transactions short and avoid external API calls while holding database locks.

## 4. @Transactional(readOnly = true) in Spring

This configuration is common for read-only service methods:

~~~java
@Transactional(readOnly = true)
public OrderView getOrder(Long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();
    return OrderView.from(order);
}
~~~

### 4.1. Read-Only Is a Hint

Per Spring Data JPA documentation, the read-only flag is passed as a performance optimization hint to the JDBC driver. It is not a check guaranteeing the application executes zero DML. Some databases may reject INSERT/UPDATE in read-only transactions, but you cannot assume every setup enforces that.

With Hibernate, Spring Data JPA sets the flush mode to `MANUAL` inside read-only transactions to skip auto-flushes and dirty checking where applicable. This reduces overhead when reading large object graphs.

### 4.2. What Happens If You Modify Entities in a Read-Only Transaction?

~~~java
@Transactional(readOnly = true)
public void renameCustomer(Long id) {
    Customer customer = customerRepository.findById(id)
        .orElseThrow();

    customer.setName("New name");
}
~~~

Avoid writing code like this. With Hibernate read-only optimizations, changes may not auto-flush to the database. However:

- The Java entity object is mutated in memory.
- Native JDBC or another transaction manager may behave differently.
- Explicit flushes or provider-specific APIs can alter behavior.
- Different setups handle read-only differently.

Never use `readOnly` to protect data. Use database privileges, enforced read-only transaction modes, or proper security controls.

### 4.3. Read-Only Is Not an Isolation Level

`readOnly = true` and `isolation = Isolation.SERIALIZABLE` are independent attributes.

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED
)
public ReportView buildReport() {
    // read data
}
~~~

This asks the Spring transaction manager and provider to treat the work as a read-only transaction hint under `READ COMMITTED`. It does not guarantee multiple `SELECT` statements observe the same Oracle transaction-level snapshot.

### 4.4. Repositories and Services

Spring Data JPA often marks read methods with read-only transaction metadata. However, Spring Data documentation recommends placing transaction boundaries at the service layer whenever consistency across multiple repository calls is required.

### 4.5. Read-Only Does Not Replace Database Privileges

If the application's database account holds `UPDATE` privileges, `readOnly` is not a security boundary. When reporting accounts must never write, grant a database user/role only `SELECT` privileges on the required objects.

## 5. Oracle SET TRANSACTION READ ONLY

Oracle provides a true database-enforced read-only transaction mode.

### 5.1. Syntax

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT SUM(amount)
FROM app_order
WHERE order_date >= DATE '2026-01-01';

SELECT COUNT(*)
FROM app_customer;

COMMIT;
~~~

`SET TRANSACTION READ ONLY` must be the very first SQL statement of the transaction and can only be set once per transaction. If a previous transaction is still open, `COMMIT` or `ROLLBACK` before starting the read-only transaction.

### 5.2. Transaction-Level Snapshot

All queries in a read-only transaction observe changes committed before the transaction began. Subsequent queries continue seeing that same snapshot even as other sessions `INSERT`/`UPDATE`/`DELETE`.

This is ideal for multi-query reports requiring point-in-time consistency.

### 5.3. Oracle Prohibits DML

Inside a read-only transaction, only Oracle-permitted operations such as `SELECT` without `FOR UPDATE` and documented transaction/session commands are allowed. `INSERT`, `UPDATE`, `DELETE`, and `SELECT FOR UPDATE` are rejected.

### 5.4. Does Not Lock Other Sessions' Data

Read-only transactions acquire no row locks for reading. Other sessions can still query and update the same tables. Oracle uses undo to reconstruct the versions needed for the snapshot.

### 5.5. Read-Only Transactions and Connection.setReadOnly

Oracle JDBC 19c supports read-only connections at the JDBC driver level, yet the Oracle server does not treat that as an enforced read-only transaction. `Connection.setReadOnly(true)` is a hint; it is not equivalent to SQL `SET TRANSACTION READ ONLY`.

## 6. Enforcing Read-Only in Spring

If the application requires the database to reject DML, examine the active transaction manager.

### 6.1. Spring DataSourceTransactionManager

Spring's `DataSourceTransactionManager` provides `setEnforceReadOnly(true)`. When enabled, the transaction manager executes `SET TRANSACTION READ ONLY` on the connection for read-only transactions. This is stronger than the JDBC `Connection.setReadOnly(true)` hint.

Conceptual configuration example:

~~~java
@Bean
public DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setEnforceReadOnly(true);
    return manager;
}
~~~

This setup is for the JDBC transaction manager. Do not copy this verbatim into an application using `JpaTransactionManager` without evaluating JPA/connection lifecycle integration.

### 6.2. Spring Data JPA with JpaTransactionManager

With a JPA transaction manager, `@Transactional(readOnly = true)` is typically passed as a hint to Hibernate/JPA. Do not assume Oracle automatically receives `SET TRANSACTION READ ONLY`.

If blocking all DML is mandatory:

- Use a `SELECT`-only database account for read workloads.
- Or design transaction manager/enforcement compatible with the JPA connection lifecycle.
- Inspect actual SQL emitted at transaction start.
- Test `INSERT`/`UPDATE` in a test environment and verify Oracle rejects them.

Never rely on a unit test checking annotations to conclude database enforcement works.

### 6.3. Comparing the Three Mechanisms

| Mechanism | Who Handles It? | Blocks DML in Oracle? |
| --- | --- | --- |
| `@Transactional(readOnly = true)` | Spring/JPA transaction hint | No by default |
| `Connection.setReadOnly(true)` | JDBC driver hint | No on Oracle server |
| `SET TRANSACTION READ ONLY` | Oracle Database | Yes, for the current transaction |

## 7. Oracle Isolation Levels

Oracle offers three key read/transaction modes:

- `READ COMMITTED`.
- `SERIALIZABLE`.
- `READ ONLY`.

Oracle server supports two JDBC transaction isolation levels: `TRANSACTION_READ_COMMITTED` and `TRANSACTION_SERIALIZABLE`. `READ ONLY` is a separate transaction mode, not a JDBC isolation constant in `Connection.TRANSACTION_*`.

### 7.1. READ COMMITTED — Default

Each `SELECT` sees data committed before that statement began.

~~~sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
~~~

This is Oracle's default behavior. One transaction running the same query twice can receive different results if another transaction commits changes in between.

Example:

~~~text
T1: SELECT balance -> 100
T2: UPDATE balance = 150
T2: COMMIT
T1: SELECT balance -> 150
~~~

T1 never reads uncommitted data. The first query reads the snapshot prior to T2's commit; the second query starts after T2's commit and reads the new value.

### 7.2. SERIALIZABLE

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Queries in the transaction observe a consistent snapshot from the start of the transaction, plus changes made by the transaction itself.

`SERIALIZABLE` permits DML, but if the transaction tries to update/delete a row modified and committed by another transaction after the `SERIALIZABLE` transaction began, Oracle raises:

~~~text
ORA-08177: Cannot serialize access for this transaction
~~~

The application must roll back and retry the entire business unit of work per policy. Never retry just the single `UPDATE` statement if earlier business decisions depended on the old snapshot.

### 7.3. READ ONLY

~~~sql
SET TRANSACTION READ ONLY;
~~~

`READ ONLY` shares `SERIALIZABLE`'s transaction-level snapshot visibility while forbidding DML. It fits multi-query reports needing point-in-time consistency within one transaction.

### 7.4. Comparison

| Characteristic | READ COMMITTED | SERIALIZABLE | READ ONLY |
| --- | --- | --- | --- |
| Snapshot | Per statement | Entire transaction | Entire transaction |
| Dirty reads | No | No | No |
| Sees new commits between queries | Yes | No | No |
| DML | Yes | Yes, may raise ORA-08177 | No |
| Row locks from normal SELECT | No | No | No |
| Best for | Default OLTP | Transactions needing stable snapshots plus writes | Multi-query consistent reports |

### 7.5. Oracle Does Not Have READ UNCOMMITTED as a Separate Mode

Oracle does not provide `READ UNCOMMITTED` with dirty-read semantics. Normal reads never observe uncommitted data from other sessions. Never configure `Isolation.READ_UNCOMMITTED` assuming Oracle will allow dirty reads.

### 7.6. Oracle Does Not Provide REPEATABLE READ as a Separate Level

Oracle provides `SERIALIZABLE` and `READ ONLY` for transaction-level read consistency. Do not assume Spring/JDBC `Isolation.REPEATABLE_READ` maps to an independent Oracle isolation mode. Documented Oracle JDBC server isolation levels are `READ_COMMITTED` and `SERIALIZABLE`.

## 8. Using Isolation in Spring Boot

### 8.1. READ COMMITTED

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateOrder() {
    // Oracle default isolation
}
~~~

Typically you can leave `Isolation.DEFAULT` unless overriding the database default.

### 8.2. SERIALIZABLE

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void allocateInventory(Long productId, int quantity) {
    // read and write against transaction snapshot
}
~~~

You must handle `ORA-08177` and implement retries at the transaction/business operation boundary.

### 8.3. READ ONLY Oracle Transactions

Spring's `Isolation` enum has no `READ_ONLY` value. To run an Oracle read-only transaction, execute `SET TRANSACTION READ ONLY` at transaction start or use an enforcing transaction manager mechanism.

Do not write:

~~~java
@Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
public ReportView report() {
    // does not guarantee an Oracle READ ONLY transaction
}
~~~

This is not a portable way to request an Oracle read-only transaction-level snapshot.

### 8.4. Isolation Applies Only When a New Transaction Starts

When a method runs inside an existing `REQUIRED` transaction, isolation declared on the inner method may not apply. If a distinct isolation level is genuinely required, consider `REQUIRES_NEW` while accounting for connections, locks, and independent commits.

## 9. Persistence Context and Dirty Checking

JPA uses a persistence context to track entities during a unit of work.

### 9.1. Managed Entities

~~~java
@Transactional
public void renameCustomer(Long id) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName("New name");
}
~~~

An entity loaded via `EntityManager.find` becomes managed. When attributes change, Hibernate tracks mutations via dirty checking. Calling `repository.save()` again on a managed entity is not mandatory for changes to synchronize.

### 9.2. Dirty Checking

During flush, Hibernate compares managed entity state against its loaded snapshot and emits necessary `INSERT`/`UPDATE`/`DELETE` SQL.

Example:

~~~java
customer.setName("New name");
// UPDATE is not necessarily sent to Oracle yet
~~~

Mutating a Java object does not mean the database has received SQL yet.

### 9.3. Detached Entities

An entity becomes detached when:

- `EntityManager.clear()` is called.
- `EntityManager.close()` is called.
- The entity is explicitly detached.
- The persistence context ends.

Changes on detached entities are not automatically flushed. Merge or reload a managed entity according to the use case.

### 9.4. Persistence Context Is Not a Transaction

The persistence context manages entity state; the transaction manages database work and commit/rollback. They often work together, yet remain distinct:

- A persistence context can exist outside a transaction.
- Flush can occur mid-transaction.
- Commit ends the transaction.
- Clear detaches entities without committing or rolling back the transaction.

## 10. What Is Flush?

Flushing synchronizes pending changes from the persistence context down to the database as SQL.

### 10.1. Flush Does Not Commit

~~~java
entityManager.flush();
~~~

After flush:

- SQL `INSERT`/`UPDATE`/`DELETE` has been sent to Oracle.
- Database constraints are checked.
- Row locks may be acquired.
- The transaction has not committed yet.
- Other transactions still cannot see uncommitted changes.
- The application can still roll back to undo changes.

### 10.2. Commit Usually Triggers Flush

Before committing a JPA transaction, the provider flushes pending changes according to flush semantics. If a constraint violation occurs at flush/commit, the exception surfaces then rather than at the setter or `save()` call.

### 10.3. When Does Hibernate Flush?

Common trigger points:

- Before transaction commit.
- Under `FlushMode.AUTO`, before queries that could be affected by pending changes.
- When the application calls `EntityManager.flush()` explicitly.

Exact flush timing depends on provider and query spaces. Check SQL logs to confirm actual timing.

## 11. Flush Modes

### 11.1. JPA FlushModeType.AUTO

`AUTO` is the standard default. The provider guarantees queries see relevant persistence context changes, flushing prior to queries when needed.

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

### 11.2. JPA FlushModeType.COMMIT

~~~java
entityManager.setFlushMode(FlushModeType.COMMIT);
~~~

`COMMIT` requires flushing before commit. Providers may still flush at other permitted times, so never treat it as an absolute guarantee that zero SQL runs before commit.

### 11.3. Hibernate MANUAL

Hibernate supports `FlushMode.MANUAL`, where the application is responsible for calling flush explicitly. Spring Data JPA can switch Hibernate to this mode when a transaction is marked `readOnly`.

`MANUAL` is Hibernate-specific, not a portable JPA `FlushModeType` value.

### 11.4. Comparison

| Mode | General Behavior |
| --- | --- |
| JPA AUTO | Flushes before commit and before queries when needed for pending changes |
| JPA COMMIT | Flushes before commit; provider may flush at other times |
| Hibernate MANUAL | No automatic flushing; application/provider must request flush |

### 11.5. Read-Only Transactions and MANUAL

When Spring Data JPA/Hibernate sees `@Transactional(readOnly = true)`, Spring can switch the Hibernate session to `MANUAL`. This skips dirty-checking/flush overhead for read workloads.

For read-only services, this is a helpful optimization. If a service accidentally mutates an entity, changes may not flush under normal auto-flush flows. Never use this mechanism as a data-protection barrier.

## 12. save(), saveAndFlush(), flush(), and commit()

Each method has a distinct meaning.

| API | Meaning |
| --- | --- |
| `repository.save(entity)` | Persists or merges entity depending on state; SQL may be deferred |
| `repository.saveAndFlush(entity)` | Saves and triggers persistence context flush |
| `entityManager.flush()` | Sends pending changes to the database |
| transactionManager commit / `connection.commit()` | Commits transaction and releases transaction locks |

### 12.1. save() Does Not Guarantee Immediate SQL

~~~java
orderRepository.save(order);
// SQL may not have run yet if not flushed
~~~

### 12.2. saveAndFlush() Does Not Commit

~~~java
orderRepository.saveAndFlush(order);
// SQL has been flushed, but transaction remains open
~~~

Row locks from flushed DML remain held until commit/rollback.

### 12.3. Why Flush Explicitly?

Explicit flushing is useful to:

- Surface constraint errors early in the transaction.
- Ensure DML runs before an operation needing database state.
- Separate SQL execution timing from commit timing.
- Synchronize pending changes before native SQL or bulk operations when needed.

Do not call `flush()` after every setter. Excessive flushing defeats SQL batching and increases round trips.

### 12.4. Clear After Flush

~~~java
entityManager.flush();
entityManager.clear();
~~~

This is a common batch pattern when processing many entities to bound persistence context memory usage. `clear()` detaches all managed entities. Calling `clear()` before `flush()` discards pending changes without sending them to the database.

## 13. Bulk JPQL DML and Persistence Context

Bulk JPQL `UPDATE`/`DELETE` executes directly in the database, bypassing dirty checking on managed entities.

### 13.1. Bulk Update Example

~~~java
@Modifying
@Query("""
    update Order o
       set o.status = :status
     where o.createdAt < :cutoff
       and o.status = 'PENDING'
    """)
int expirePendingOrders(
    @Param("status") OrderStatus status,
    @Param("cutoff") LocalDateTime cutoff
);
~~~

### 13.2. Bulk DML Does Not Auto-Update Managed Objects

If an `Order` entity is already loaded in the persistence context, the bulk update changes the row in Oracle while the managed Java object retains its stale values.

### 13.3. Automatic Flush and Clear

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Order o
       set o.status = 'EXPIRED'
     where o.status = 'PENDING'
       and o.createdAt < :cutoff
    """)
int expireOrders(@Param("cutoff") LocalDateTime cutoff);
~~~

`flushAutomatically` flushes pending changes before bulk DML. `clearAutomatically` clears the persistence context afterward to prevent reading stale managed state.

Enable `clearAutomatically` only when you understand that all currently managed entities in the persistence context will be detached.

### 13.4. Bulk DML Still Acquires Oracle Locks

Bulk `UPDATE`/`DELETE` is still DML in Oracle. Affected rows are locked per Oracle rules until the transaction ends.

## 14. Oracle MVCC: Normal SELECTs Do Not Lock Rows

Oracle uses multiversion concurrency control and undo to provide read consistency.

### 14.1. Readers Do Not Block Writers

A normal `SELECT` reads committed data matching the statement's snapshot. If another session is updating a row without committing, readers reconstruct the prior committed version using undo.

### 14.2. Writers Do Not Block Normal Readers

An `UPDATE` holding a row lock generally does not stop normal `SELECT` queries from reading that row. `SELECT` sees the committed pre-update version.

### 14.3. Writers Block Writers

If a second transaction attempts to `UPDATE`/`DELETE` the same row locked by the first transaction, the second transaction waits until the first executes `COMMIT` or `ROLLBACK`.

### 14.4. Illustration

~~~text
Session A                         Session B
---------                         ---------
UPDATE account
SET balance = 900
WHERE id = 1;
                                  SELECT balance
                                  FROM account
                                  WHERE id = 1;
                                  -> reads old committed value
                                  UPDATE account
                                  SET balance = 800
                                  WHERE id = 1;
                                  -> waits for A's row lock
COMMIT;
                                  -> proceeds after A commits
~~~

This is fundamental Oracle `READ COMMITTED` behavior.

### 14.5. No Dirty Reads

Oracle does not allow sessions to read uncommitted changes from other sessions under `READ COMMITTED`. Do not try `READ UNCOMMITTED` as a way to reduce lock contention.

## 15. Row Locks and Table Locks in Oracle

Oracle uses multiple lock types to protect data and structure.

### 15.1. DML Row Locks

`INSERT`, `UPDATE`, and `DELETE` acquire row locks on modified rows. Transaction locks stay held until commit or rollback.

### 15.2. TM Table Locks

DML also acquires a table-level DML lock (TM enqueue) in the appropriate mode to protect table structure and DML consistency. A row-exclusive table lock does not lock the whole table exclusively; other transactions can still run DML on non-conflicting rows.

### 15.3. TX Transaction Enqueues

TX enqueues represent transaction and row-level contention. When a session waits for another transaction to release a row lock, the typical wait event is `enq: TX - row lock contention`.

### 15.4. Normal SELECTs

Normal `SELECT` statements do not take row locks and are not blocked by row-level DML locks. DDL, explicit table locks, or special situations can still cause other waits; do not generalize that `SELECT` can never wait.

### 15.5. Locks Persist Until Transaction End

Closing a cursor does not release row locks. Flushing does not release locks. Only commit or rollback ends the transaction and releases its locks.

## 16. SELECT FOR UPDATE

When reading a row and guaranteeing no other transaction modifies it before your application updates it, lock the row with `SELECT FOR UPDATE`.

### 16.1. Syntax

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE;
~~~

Oracle acquires exclusive row locks on the selected rows. Other sessions cannot acquire conflicting locks or modify those rows until the transaction ends.

### 16.2. Locks Are Acquired Before Fetching

When `SELECT FOR UPDATE` opens a cursor, Oracle locks the result-set rows upon cursor open, before fetching individual rows. Thus, a query matching many rows locks all of them upfront even if the application fetches only a subset.

### 16.3. When Are Locks Released?

~~~sql
COMMIT;
-- or
ROLLBACK;
~~~

Closing the `ResultSet`/`Statement` does not release transaction locks.

### 16.4. NOWAIT

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE NOWAIT;
~~~

If a row already has a conflicting lock, Oracle returns an error immediately instead of waiting. The application can report a resource conflict or retry after an appropriate delay.

### 16.5. WAIT n

~~~sql
SELECT account_id, balance
FROM account
WHERE account_id = 100
FOR UPDATE WAIT 5;
~~~

Oracle waits up to the specified seconds to acquire the lock. If the timer expires, the statement returns an error.

### 16.6. SKIP LOCKED

~~~sql
SELECT job_id, status
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` skips rows currently locked by other transactions. It is useful when multiple workers dequeue jobs concurrently without blocking each other on the same rows.

`SKIP LOCKED` does not guarantee business ordering or fairness across workers. Design leases, statuses, attempt counts, and short transactions.

### 16.7. SQL Restrictions

Oracle enforces restrictions on `FOR UPDATE`, such as queries with `DISTINCT`, set operators, `GROUP BY`, aggregate functions, or certain view transformations. When JPA generates `SELECT FOR UPDATE` for a complex query, the SQL may be invalid. Use simple queries directly on the target entity/table and inspect the generated SQL.

## 17. JPA Optimistic Locking with @Version

Optimistic locking fits when write conflicts are rare and holding row locks from read to write is undesirable.

### 17.1. Versioned Entity

~~~java
@Entity
@Table(name = "APP_PRODUCT")
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @Version
    @Column(name = "VERSION_NO")
    private Long version;

    // getters/setters
}
~~~

### 17.2. How It Works

Suppose two transactions read version 4:

~~~text
T1 reads version 4
T2 reads version 4

T1 UPDATE ... WHERE id = 10 AND version_no = 4
T1 increments version to 5 and COMMITs

T2 UPDATE ... WHERE id = 10 AND version_no = 4
T2 updates 0 rows instead of expected 1
T2 receives OptimisticLockException
~~~

The provider emits an `UPDATE` with a version predicate and increments the version. Watch exception timing, because version conflicts may surface at flush or commit.

### 17.3. Optimistic Locking Does Not Lock Rows on SELECT

Optimistic locking does not run `SELECT FOR UPDATE` just to read. It detects conflicts at write time via the version column.

### 17.4. Exception Handling

~~~java
@Transactional
public void changePrice(Long productId, BigDecimal newPrice) {
    Product product = productRepository.findById(productId)
        .orElseThrow();
    product.setPrice(newPrice);
}
~~~

On a version conflict, the transaction must roll back. Ask the user to reload or retry the entire business operation if business rules permit.

### 17.5. Do Not Blindly Retry an Old UPDATE

When a transaction fails with an optimistic lock conflict, the state used for business decisions is already stale. Retries must re-read fresh state and recompute the decision, not just replay the old SQL.

## 18. JPA Pessimistic Locking

Pessimistic locking uses database locks to prevent other transactions from modifying rows while the application processes them.

### 18.1. @Lock(PESSIMISTIC_WRITE)

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

When called in a transaction, the JPA provider requests the corresponding lock. With Oracle/Hibernate, this typically translates to `SELECT ... FOR UPDATE`. Enable SQL logging to verify.

### 18.2. Service Transaction

~~~java
@Transactional
public void withdraw(Long accountId, BigDecimal amount) {
    Account account = accountRepository.findByIdForUpdate(accountId)
        .orElseThrow();

    if (account.getBalance().compareTo(amount) < 0) {
        throw new InsufficientBalanceException();
    }

    account.debit(amount);
}
~~~

The row lock remains held until commit/rollback. Never call remote payment services or wait for user confirmation while holding the lock.

### 18.3. LockModeType

| JPA Lock Mode | Purpose |
| --- | --- |
| `OPTIMISTIC` | Verifies optimistic lock within transaction |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic lock and increments version |
| `PESSIMISTIC_READ` | Requests a pessimistic read lock |
| `PESSIMISTIC_WRITE` | Requests a pessimistic write lock |
| `PESSIMISTIC_FORCE_INCREMENT` | Pessimistic lock and increments version |

Exact generated SQL depends on provider and dialect. Oracle normally uses `SELECT FOR UPDATE` for pessimistic row locking; do not assume `PESSIMISTIC_READ` creates a standalone shared row lock identical to other databases. Inspect the actual SQL.

### 18.4. Lock Timeout Hint

JPA defines a lock timeout hint:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "0"
    )
)
@Query("select a from Account a where a.id = :id")
Optional<Account> findByIdForUpdateNowait(@Param("id") Long id);
~~~

Supported values and translation to `NOWAIT`/`WAIT` depend on the provider. Never assume every JPA provider handles hints identically. When Oracle-specific semantics like `SKIP LOCKED` are needed, native SQL is often clearer.

## 19. JPA and Oracle SKIP LOCKED for Worker Queues

`SKIP LOCKED` suits multiple consumers pulling jobs concurrently.

### 19.1. Native Query

~~~java
@Repository
public interface JobQueueRepository extends JpaRepository<JobQueue, Long> {

    @Query(
        value = """
            SELECT *
            FROM job_queue
            WHERE status = 'READY'
            FOR UPDATE SKIP LOCKED
            """,
        nativeQuery = true
    )
    List<JobQueue> lockReadyJobs();
}
~~~

This illustrates syntax only. Production queries generally add row limits, `ORDER BY`, claim tokens, and processing states matching your Oracle release's SQL grammar.

### 19.2. Short Claim Transactions

A worker should:

1. Open a transaction.
2. Select and lock unlocked ready jobs.
3. Update status to `PROCESSING` and save worker/lease info.
4. Commit to release locks.
5. Execute work outside the transaction whenever possible.
6. Open a second transaction to persist completion or retry state.

Avoid holding `SELECT FOR UPDATE` across external API calls unless required.

### 19.3. SKIP LOCKED Does Not Replace Leases

If a worker crashes after committing `PROCESSING`, the job can get stuck. Implement lease expiration, heartbeats, or recovery sweepers to reclaim overdue jobs.

## 20. Flush and Lock Timing: What Actually Happens?

A common misconception is thinking row locks only appear at commit. In reality, locks are acquired as soon as DML executes, including during Hibernate flushes.

### 20.1. Example

~~~java
@Transactional
public void updateAndRead(Long id) {
    Account account = entityManager.find(Account.class, id);
    account.setBalance(account.getBalance().subtract(new BigDecimal("10")));

    // Here the entity may only be modified in memory.

    entityManager.flush();
    // Hibernate sends UPDATE to Oracle.
    // Oracle acquires row lock and holds it until transaction end.

    // Subsequent work remains inside the transaction.
}
~~~

### 20.2. Lock Duration

~~~text
BEGIN TRANSACTION
      |
      v
Modify managed entity
      |
      v
FLUSH -> UPDATE reaches Oracle
      |
      v
Oracle acquires row lock
      |
      v
More Java work / queries
      |
      v
COMMIT or ROLLBACK
      |
      v
Oracle releases lock
~~~

The span from flush until commit/rollback is how long locks remain held.

### 20.3. Why Are Long Transactions Dangerous?

- Other sessions block waiting on row locks.
- Undo/redo and transaction state stay active longer.
- Connection pool connections stay checked out.
- Deadlocks become more likely when transactions lock rows in inconsistent orders.
- Calling external APIs inside transactions can hold locks for the duration of network timeouts.

### 20.4. Keep Transactions Short

Avoid:

~~~java
@Transactional
public void processOrder(Long id) {
    Order order = orderRepository.findByIdForUpdate(id).orElseThrow();
    paymentGateway.callRemoteService(); // holds lock while waiting on network
    order.markPaid();
}
~~~

Design workflows using state machines/optimistic versioning or split transactions where business rules allow. If a lock must span the flow, enforce timeouts and evaluate load/concurrency.

## 21. Oracle Lock Waits and Common Errors

### 21.1. ORA-00054

`ORA-00054: resource busy and acquire with NOWAIT specified` occurs when `SELECT FOR UPDATE NOWAIT` or a `NOWAIT` lock request hits an already-locked resource.

The application can return a conflict or retry per policy. Never spin `NOWAIT` in a tight loop.

### 21.2. ORA-00060

`ORA-00060: deadlock detected while waiting for resource` occurs when transactions wait on each other in a cycle. Oracle detects the cycle and rolls back one statement to break the deadlock.

Reduce deadlocks by:

- Locking rows in a consistent order across all transactions.
- Keeping transactions short.
- Avoiding locking more rows than necessary.
- Never holding locks across external service calls.
- Handling `ORA-00060` and retrying the entire business unit of work when appropriate.

### 21.3. ORA-08177

`ORA-08177: Cannot serialize access for this transaction` appears under `SERIALIZABLE` when a transaction tries to modify rows changed and committed by another transaction after the serializable snapshot started.

The application typically must roll back and retry the entire transaction against fresh data.

### 21.4. ORA-01555

`ORA-01555: snapshot too old` occurs when a query/transaction needs undo records that were already overwritten. Long-running read-only reports can hit this if undo retention and workload do not align.

Solutions include tuning query runtime, undo sizing/retention, shortening transaction durations, and tuning SQL. Never solve it by locking entire tables for reports.

## 22. Investigating Blockers in Oracle

When a JPA request hangs, find what the session is waiting on and which session is blocking it.

### 22.1. Finding Blocked Sessions

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    event,
    seconds_in_wait,
    blocking_session_status,
    blocking_instance,
    blocking_session,
    row_wait_obj#,
    row_wait_file#,
    row_wait_block#,
    row_wait_row#
FROM v$session
WHERE blocking_session_status = 'VALID'
ORDER BY seconds_in_wait DESC;
~~~

### 22.2. Inspecting the Blocker Session

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    sql_id,
    prev_sql_id,
    event,
    module,
    action,
    logon_time,
    last_call_et
FROM v$session
WHERE sid = :blocking_sid;
~~~

`BLOCKING_SESSION` is the SID of the blocking session. In RAC, check `BLOCKING_INSTANCE` and query `GV$SESSION` on the right instance.

### 22.3. Viewing Objects with DML Locks

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    o.owner,
    o.object_name,
    lo.locked_mode
FROM v$locked_object lo
JOIN v$session s
  ON s.sid = lo.session_id
LEFT JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY s.sid, o.owner, o.object_name;
~~~

`V$LOCKED_OBJECT` displays TM DML locks on objects and their table lock modes. It is not a full list of individual row locks.

### 22.4. Viewing TX/TM Locks

~~~sql
SELECT
    l.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
ORDER BY l.type, l.sid;
~~~

`V$LOCK` shows held locks and waiting lock requests. `TX` typically relates to transaction enqueues; `TM` relates to object DML enqueues.

### 22.5. V$SESSION_BLOCKERS

~~~sql
SELECT
    sid,
    sess_serial#,
    wait_event_text,
    blocker_instance_id,
    blocker_sid,
    blocker_sess_serial#
FROM v$session_blockers;
~~~

This view shows blocked/blocker pairs. If lacking read privileges on dynamic performance views, request appropriate DBA grants or have an admin account run the queries.

### 22.6. RAC and CDB

In RAC, use `GV$SESSION`, `GV$LOCKED_OBJECT`, and `GV$LOCK`, joining on `INST_ID`. In CDBs, filter by `CON_ID` so root and PDB sessions are not mixed.

## 23. Mapping JPA Actions to Oracle Behavior

| Java/JPA Operation | Possible SQL/Database Behavior | Lock Implication |
| --- | --- | --- |
| `findById()` | `SELECT` | Does not acquire normal row locks |
| Mutating field on managed entity | Memory-only change until flush | No DML lock from setter alone |
| `save()` | Persist/merge; SQL may be deferred | Locks acquired when DML actually runs |
| `saveAndFlush()` | Persist/merge followed by flush | DML locks may begin at flush |
| `entityManager.flush()` | Emits pending INSERT/UPDATE/DELETE | Oracle acquires locks per DML |
| `entityManager.clear()` | Detaches managed entities | Does not commit or roll back |
| `@Lock(PESSIMISTIC_WRITE)` | Typically `SELECT FOR UPDATE` on Oracle | Locks selected rows |
| `@Version` update | `UPDATE` with version predicate | Detects conflict at write; no read lock |
| `@Transactional(readOnly=true)` | Hint/optimization per manager/provider | Does not block DML by default in Oracle |
| Oracle `SET TRANSACTION READ ONLY` | Transaction-level snapshot, blocks DML | Acquires no row locks for reads |

## 24. Safe Transaction and Lock Design in Spring Boot

### 24.1. Use Read-Only for Reads

~~~java
@Service
public class ReportService {

    @Transactional(readOnly = true)
    public OrderSummary getSummary(LocalDate from, LocalDate to) {
        return orderRepository.calculateSummary(from, to);
    }
}
~~~

This declares read intent and enables Hibernate optimizations. If multiple `SELECT` statements need one Oracle snapshot, use an appropriate Oracle `READ ONLY` or `SERIALIZABLE` transaction.

### 24.2. Updates with Optimistic Locking

~~~java
@Transactional
public void changeAddress(Long customerId, String address) {
    Customer customer = customerRepository.findById(customerId)
        .orElseThrow();
    customer.setAddress(address);
}
~~~

The entity has `@Version`; if another transaction updates first, Hibernate detects the version conflict at flush/commit.

### 24.3. Updates with Pessimistic Locking

~~~java
@Transactional
public void reserveInventory(Long itemId, int quantity) {
    Inventory item = inventoryRepository.findByIdForUpdate(itemId)
        .orElseThrow();

    if (item.getAvailable() < quantity) {
        throw new InsufficientInventoryException();
    }

    item.reserve(quantity);
}
~~~

Use when rows must be locked before checking and updating. Keep processing inside the transaction short.

### 24.4. Handling Checked Exceptions

~~~java
@Transactional(rollbackFor = Exception.class)
public void settleOrder(Long orderId) throws Exception {
    // steps that must roll back even on checked exceptions
}
~~~

Without a rollback rule, checked exceptions may not trigger Spring's default rollback.

### 24.5. Retrying ORA-08177

Place retries outside the rolled-back transaction boundary—such as retrying a service method that starts a new transaction per attempt. Never retry inside a transaction that already hit a serialization error.

### 24.6. Retrying Lock Waits

For `NOWAIT`/lock timeouts, either return a conflict to the client or retry with backoff and a retry cap. Never continue processing inside a failed transaction.

## 25. Two-Session Lab to Observe Oracle Locks

This lab uses two SQL sessions. Run in a lab schema, never against production tables.

### Step 1 — Create Table

~~~sql
CREATE TABLE account_lock_lab (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 0 NOT NULL
);

INSERT INTO account_lock_lab(account_id, balance, version_no)
VALUES (1, 1000, 0);

COMMIT;
~~~

### Step 2 — Session A Updates Without Committing

~~~sql
UPDATE account_lock_lab
SET balance = 900
WHERE account_id = 1;
~~~

Do not `COMMIT`.

### Step 3 — Session B Runs a Normal SELECT

~~~sql
SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

Session B reads the previously committed value `1000` thanks to read consistency. Normal `SELECT` does not wait on A's row lock.

### Step 4 — Session B Updates the Same Row

~~~sql
UPDATE account_lock_lab
SET balance = 800
WHERE account_id = 1;
~~~

Session B waits for Session A to release its lock.

### Step 5 — Session A COMMITs

~~~sql
COMMIT;
~~~

Session B then proceeds with its `UPDATE` per `READ COMMITTED` rules. Check the final value after B commits.

### Step 6 — Test SELECT FOR UPDATE NOWAIT

Session A:

~~~sql
SELECT *
FROM account_lock_lab
WHERE account_id = 1
FOR UPDATE;
~~~

Session B:

~~~sql
SELECT *
FROM account_lock_lab
WHERE account_id = 1
FOR UPDATE NOWAIT;
~~~

Session B immediately gets an error while A holds the conflicting lock.

### Step 7 — Test SERIALIZABLE

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

Session B updates and commits that row. Then Session A attempts to `UPDATE` the row modified by B. Observe `ORA-08177` under serialization conflict conditions.

### Step 8 — Test READ ONLY

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT balance
FROM account_lock_lab
WHERE account_id = 1;
~~~

From another session, update and commit the row. The next query in the read-only transaction still sees the old snapshot. Try running `UPDATE` inside the read-only transaction to see Oracle reject DML.

## 26. Spring Boot/JPA Lab

### Step 1 — Versioned Entity

~~~java
@Entity
@Table(name = "ACCOUNT_LOCK_LAB")
public class Account {

    @Id
    @Column(name = "ACCOUNT_ID")
    private Long id;

    @Column(name = "BALANCE")
    private BigDecimal balance;

    @Version
    @Column(name = "VERSION_NO")
    private Long version;

    public void debit(BigDecimal amount) {
        this.balance = this.balance.subtract(amount);
    }
}
~~~

### Step 2 — Optimistic/Pessimistic Repository

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findForUpdate(@Param("id") Long id);
}
~~~

### Step 3 — Read-Only Service

~~~java
@Transactional(readOnly = true)
public AccountView getAccount(Long id) {
    Account account = accountRepository.findById(id)
        .orElseThrow();
    return AccountView.from(account);
}
~~~

### Step 4 — Pessimistic Update

~~~java
@Transactional
public void debit(Long id, BigDecimal amount) {
    Account account = accountRepository.findForUpdate(id)
        .orElseThrow();

    if (account.getBalance().compareTo(amount) < 0) {
        throw new InsufficientBalanceException();
    }

    account.debit(amount);
    // SQL UPDATE may flush before commit.
}
~~~

### Step 5 — Observe SQL

Enable Hibernate SQL logging in the lab environment and verify:

- Read-only queries emit no unexpected DML.
- `findForUpdate` generates SQL with `FOR UPDATE`.
- `UPDATE` is sent at flush/commit.
- Locks stay held until transaction end.

Never enable bind-value logging in production if parameters carry sensitive data.

### Step 6 — Test Two Concurrent Requests

1. Request A acquires `PESSIMISTIC_WRITE` and holds its transaction open.
2. Request B calls the same method.
3. Observe B waiting on the lock.
4. A commits.
5. B proceeds or times out per configuration.
6. Repeat with `@Version` to observe `OptimisticLockException` instead of holding locks from read time.

## 27. Troubleshooting by Symptom

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@Transactional(readOnly=true)` still writes | Read-only is only a hint | Use DB privileges or Oracle-enforced read-only |
| Entity modified without `UPDATE` | Hibernate `MANUAL` flush in read-only tx or detached entity | Check transaction metadata, flush mode, and managed state |
| `save()` shows no SQL in logs yet | SQL deferred until flush/commit | Flush only when genuinely needed and verify transaction |
| Other session misses data after `saveAndFlush()` | Flush does not commit | Commit the transaction |
| Query before commit sees new entity in same session | Persistence context/flush semantics | Distinguish in-session visibility from cross-session visibility |
| Other session `SELECT` reads old value | Oracle MVCC reads committed version | Normal behavior before writer commits |
| `UPDATE` hangs waiting | Row locked by another transaction | Inspect `V$SESSION` blockers and transaction owner |
| `ORA-00054` | `NOWAIT` hit conflicting lock | Return conflict or retry with backoff |
| `ORA-00060` | Deadlock | Enforce consistent lock order and shorten transactions |
| `ORA-08177` | Serializable conflict | Roll back and retry entire transaction |
| `ORA-01555` | Undo needed for consistent read overwritten | Optimize queries, runtime, and undo retention |
| Pessimistic lock not working as expected | No active transaction or different provider SQL | Check proxies, transaction manager, and generated SQL |
| Lock persists after `flush()` | Flush does not release locks | Commit or roll back |
| Self-invocation skips transaction | Call bypassed Spring proxy | Split into another bean or use appropriate weaving |
| Inner method's isolation has no effect | Method joined outer transaction | Check propagation and existing transaction |
| Bulk JPQL update leaves stale entity | Bulk DML bypasses persistence context | Flush/clear/refresh per use case |

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| `@Transactional(readOnly=true)` blocks `UPDATE` in Oracle | It is generally a hint/provider optimization, not default DB enforcement |
| `Connection.setReadOnly(true)` equals `SET TRANSACTION READ ONLY` | Oracle JDBC treats it as a hint; server does not enforce read-only this way |
| `READ COMMITTED` holds a snapshot for the whole transaction | Each statement gets its own snapshot |
| Oracle has `READ UNCOMMITTED` and `REPEATABLE READ` like other DBs | Oracle server supports `READ COMMITTED` and `SERIALIZABLE`; `READ ONLY` is a separate mode |
| Normal `SELECT` locks rows it reads | Oracle MVCC lets `SELECT` read consistent versions without row locks |
| `UPDATE` only locks rows on `COMMIT` | Row locks are acquired when DML executes |
| `flush()` is commit | Flush only sends pending SQL to the database |
| `save()` always emits SQL immediately | SQL may be deferred until flush |
| `saveAndFlush()` commits | It does not commit the transaction |
| Closing a cursor releases `SELECT FOR UPDATE` locks | Locks stay held until commit/rollback |
| `@Version` locks rows at read time | Optimistic locking detects conflicts at write time |
| `PESSIMISTIC_WRITE` is just Java metadata | Provider requests a database lock, usually `SELECT FOR UPDATE` |
| `readOnly=true` and `Isolation.SERIALIZABLE` are the same | One is access intent/hint; the other is isolation semantics |
| Method isolation always overrides outer transactions | Joining an existing transaction usually keeps the outer isolation |
| `ORA-08177` is a lock timeout | It is a serialization conflict |
| `V$LOCKED_OBJECT` lists every locked row | It shows TM object/table DML locks; inspect TX/`V$SESSION` for row contention |

## 29. Implementation Checklist

**Transaction Boundaries**

- Is the transaction placed on a service method representing one business operation?
- Does the call pass through a Spring proxy?
- Who owns commit/rollback?
- Do checked exceptions need `rollbackFor`?
- Does the transaction hold connections or locks too long?

**Read-Only**

- Is the method truly read-only?
- Is read-only used as a hint or is database enforcement needed?
- Does the transaction manager support enforcement?
- Is an Oracle transaction-level snapshot needed for reports?
- Does the database user have least-privilege grants?

**Isolation**

- Is Oracle's default `READ COMMITTED` sufficient?
- Is `SERIALIZABLE` needed?
- Are `ORA-08177` handling and retries implemented?
- Is an isolation annotation inadvertently joining an outer transaction?
- Is Spring `REPEATABLE_READ` being confused with Oracle modes?

**Flush**

- What is the active flush mode?
- Does SQL execute at save, query, explicit flush, or commit?
- Is flushing happening too frequently?
- Is `clear()` ever called before `flush()`?
- Does bulk JPQL/native DML leave the persistence context stale?

**Locking**

- Is optimistic or pessimistic locking appropriate?
- Does `PESSIMISTIC_WRITE` hold locks too long?
- Is `NOWAIT`/`WAIT`/`SKIP LOCKED` needed?
- Do transactions lock rows in a consistent order?
- Are blocking sessions and deadlocks monitored?

## 30. Self-Check Questions

1. Does Spring `@Transactional(readOnly=true)` block DML in Oracle by default?
2. How does Spring optimize Hibernate for read-only transactions?
3. When must Oracle `SET TRANSACTION READ ONLY` be called?
4. What snapshot does an Oracle read-only transaction observe?
5. Is `Connection.setReadOnly(true)` equivalent to an Oracle read-only transaction?
6. What is Oracle's default isolation level?
7. At what level does `READ COMMITTED` take snapshots?
8. At what level does `SERIALIZABLE` take snapshots?
9. What does `ORA-08177` mean?
10. Does Oracle support `READ UNCOMMITTED` and `REPEATABLE READ` as distinct JDBC modes?
11. What propagation does `@Transactional` use by default?
12. How does self-invocation affect transactional proxies?
13. Does isolation on an inner `REQUIRED` method always override an outer transaction?
14. Which exception types does Spring roll back by default?
15. What is a persistence context?
16. What does dirty checking do?
17. Does flush commit a transaction?
18. Can flush acquire Oracle row locks?
19. When can Hibernate auto-flush?
20. What does `MANUAL` flush mode mean?
21. How does `save()` differ from `saveAndFlush()`?
22. How does `clear()` affect managed entities?
23. Does a bulk JPQL `UPDATE` update managed entities in memory?
24. Do normal Oracle `SELECT` statements acquire row locks?
25. Why can `SELECT` read a row currently undergoing an uncommitted `UPDATE`?
26. Until when are Oracle DML locks held?
27. When does `SELECT FOR UPDATE` lock rows?
28. How do `NOWAIT`, `WAIT`, and `SKIP LOCKED` differ?
29. How does optimistic locking with `@Version` work?
30. What SQL is `PESSIMISTIC_WRITE` typically translated to on Oracle?
31. What lock type does `V$LOCKED_OBJECT` show?
32. What does wait event `enq: TX - row lock contention` indicate?
33. How do `ORA-00054` and `ORA-00060` differ?
34. Why do long transactions increase lock contention?
35. When should you use an Oracle `READ ONLY` transaction instead of a `readOnly` hint?

**Suggested Answers:**

1. No; `readOnly` is a hint/provider optimization, not default database enforcement.
2. Spring Data JPA can set Hibernate `FlushMode.MANUAL` to skip dirty checking/auto-flush.
3. As the first SQL statement of the transaction.
4. Changes committed before the transaction began.
5. No; Oracle JDBC treats it as a hint, not a server-enforced read-only transaction.
6. `READ COMMITTED`.
7. Per statement.
8. Entire transaction.
9. A serializable transaction hit a conflicting change committed after its snapshot began.
10. No; Oracle server supports `READ COMMITTED` and `SERIALIZABLE`, plus `READ ONLY` transaction mode.
11. `REQUIRED`.
12. Internal calls bypass the proxy, so the annotation may not be intercepted.
13. No; a method joining an outer transaction generally uses the outer transaction's isolation.
14. `RuntimeException` and `Error`, unless rollback rules are configured otherwise.
15. The JPA region managing managed entities and their states.
16. Detects entity changes to generate DML on flush.
17. No.
18. Yes, when DML is actually sent to Oracle.
19. Before commit and before queries potentially affected by pending changes in `AUTO` mode.
20. The provider does not auto-flush normally; the application must trigger flush when needed.
21. `save` persists/merges; `saveAndFlush` also requests a flush; neither commits the transaction.
22. Detaches all currently managed entities.
23. It does not automatically sync managed objects in the persistence context.
24. No.
25. Oracle uses MVCC/undo to reconstruct the committed version.
26. Commit or rollback.
27. When the cursor opens, before fetching rows.
28. `NOWAIT` errors immediately; `WAIT` waits up to `n` seconds; `SKIP LOCKED` skips currently locked rows.
29. A version predicate detects if data was updated by another transaction.
30. Typically `SELECT ... FOR UPDATE`, depending on provider/dialect.
31. TM DML table/object locks and their lock modes.
32. A session waiting for another transaction to release a row-level lock.
33. `ORA-00054` is resource busy with `NOWAIT`; `ORA-00060` is a deadlock.
34. Because locks stay held throughout the transaction, including time waiting outside the database.
35. When multiple report queries require the same Oracle snapshot and DML must be prohibited by the database.

## Spring, JPA, and Oracle References

- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): read-only hint, Hibernate `MANUAL` flush mode, and transaction boundaries.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, isolation, rollback rules, and proxy/self-invocation.
- [Spring Framework — DataSourceTransactionManager.setEnforceReadOnly](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): enforcing read-only via `SET TRANSACTION READ ONLY`.
- [Oracle Database 19c SQL Language Reference — SET TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SET-TRANSACTION.html): `READ ONLY`, `READ COMMITTED`, and `SERIALIZABLE`.
- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): MVCC, read consistency, isolation, and `ORA-08177`.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `FOR UPDATE`, `NOWAIT`, `WAIT`, and `SKIP LOCKED`.
- [Oracle Database 19c SQL Processing for Application Developers](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-processing-for-application-developers.html): locking and read consistency.
- [Oracle Database 19c JDBC Coding Tips](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-coding-tips.html): Oracle JDBC isolation levels and read-only access mode.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): blocking sessions and row wait information.
- [Oracle Database 19c Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): TX/TM locks and lock modes.
- [Oracle Database 19c Database Reference — V$LOCKED_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCKED_OBJECT.html): DML object locks.
- [Oracle Database 19c Database Reference — V$SESSION_BLOCKERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION_BLOCKERS.html): blocked/blocker session pairs.

**Key principle:** Spring `readOnly` is an optimization hint, whereas Oracle `SET TRANSACTION READ ONLY` is the database-enforced mode with a transaction-level snapshot. Oracle defaults to `READ COMMITTED`, giving each statement its own snapshot; `SERIALIZABLE` and `READ ONLY` hold a snapshot for the entire transaction. JPA flush sends DML to Oracle without committing; row locks are acquired upon DML execution and held until commit/rollback. Normal `SELECT`s read via MVCC without locking rows. Use `@Version` for optimistic locking where appropriate, `PESSIMISTIC_WRITE`/`SELECT FOR UPDATE` when real row locks are needed, and always keep transactions short. When contention occurs, investigate blockers via `V$SESSION`, `V$LOCK`, and `V$LOCKED_OBJECT`, and address `ORA-00054`, `ORA-00060`, and `ORA-08177` according to their root causes.
