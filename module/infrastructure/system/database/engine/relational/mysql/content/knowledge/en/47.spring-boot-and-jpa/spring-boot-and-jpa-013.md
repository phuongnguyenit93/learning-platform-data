# Optimistic/Pessimistic Locking, Timeouts, and Exception Translation

When multiple requests concurrently read and update a MySQL row, the application must control how competing transactions interact. **Optimistic locking** detects when one transaction modified data since another transaction read it; **pessimistic locking** locks data while a transaction is processing to prevent concurrent conflicting edits on the same resource. Timeouts bound lock-wait or execution durations, while exception translation converts JDBC/JPA errors into consistent Spring-layer exceptions.

No single locking strategy fits every operation. Optimistic locking typically works best when conflicts are rare and transactions are short. Pessimistic locking helps when contention is frequent or business rules require holding exclusive update rights across a brief processing window. Regardless of choice, the application still needs explicit transaction boundaries, finite timeouts, and recoverable error handling.

This lesson belongs to the **Spring Boot and JPA** chapter of the DATABASE_MYSQL module. The module covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, access control, backups, and relational database operations. Examples use Spring Boot 3, Spring Data JPA, Jakarta Persistence, and MySQL InnoDB; in Spring Boot 2, persistence packages use the javax prefix instead of jakarta.

After this lesson, you will be able to:

- Explain lost updates and the role of a version column.
- Configure optimistic locking with @Version.
- Use LockModeType to request pessimistic locks.
- Set timeouts for transactions, queries, and locks.
- Distinguish deadlocks, lock wait timeouts, and optimistic conflicts.
- Understand exception translation from JPA/Hibernate to Spring DataAccessException.
- Design retries outside failed transactions.
- Inspect lock waits and test concurrency across multiple transactions.

## 1. Concurrency Problem: Lost Update

Suppose account A has a balance of 1,000. Two requests simultaneously read the balance, each intending to deduct 100:

1. Transaction T1 reads 1,000.
2. Transaction T2 also reads 1,000.
3. T1 computes 900 and writes 900.
4. T2 computes 900 and writes 900.
5. Both requests believe they deducted 100, yet the final balance is 900 instead of 800.

This is a lost update: one update overwrites the result of another because both relied on the same stale read.

~~~text
T1                         T2
|                          |
|---- read balance=1000 ---|
|                          |---- read balance=1000
|---- compute 900 ---------|
|                          |---- compute 900
|---- write balance=900 ---|
|                          |---- write balance=900
|                          |
Result: 900, whereas two 100 deductions should yield 800.
~~~

InnoDB provides locking and isolation levels, yet the application must choose an appropriate read/update pattern. Using @Transactional alone does not automatically prevent lost updates. A transaction can span multiple statements, yet if two transactions both read first and write absolute values without checking version or holding locks, results can still be wrong.

## 2. Two Locking Strategies

| Criterion | Optimistic Locking | Pessimistic Locking |
|---|---|---|
| Mechanism | Detects write conflicts using a version or equivalent predicate | Holds locks during the transaction to block competing updates |
| Best suited for | Rare conflicts, read-heavy workloads, short transactions | Frequent contention or operations requiring serialization |
| Uncontended overhead | Low; no locks held from read time | Incurs lock acquisition/retention cost |
| On conflict | One transaction fails and may need to retry | Competing transactions wait or time out |
| Operational risks | Retry storms under sustained contention | Deadlocks, lock waits, holding locks too long |
| Protection scope | Versioned row and version-checked update statement | Rows/ranges locked by the DB per execution plan and isolation level |

Both mechanisms require transactions. Optimistic locking does not mean zero database locks: the UPDATE statement still acquires InnoDB row locks during execution. The difference is that the application does not hold exclusive locks from read time; it verifies the version at write time.

Nor does pessimistic locking replace constraints. Unique keys, foreign keys, CHECK constraints, and conditional UPDATE predicates remain essential to enforce data invariants.

## 3. Optimistic Locking with @Version

Jakarta Persistence supports optimistic locking via a version attribute. The entity declares a field annotated with @Version:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "account", schema = "banking")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public Long getVersion() {
        return version;
    }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new IllegalStateException("Insufficient funds");
        }
        balance = balance.subtract(amount);
    }
}
~~~

With this entity, Hibernate checks the version on update. Conceptually, the SQL looks like:

~~~sql
UPDATE banking.account
SET balance = ?, version = ?
WHERE id = ?
  AND version = ?;
~~~

Suppose the entity was loaded with version = 7. On a successful update, the provider increments version to 8 and updates only if the row still has version = 7. If another transaction updated it first and the current version is 8, the UPDATE affects 0 rows. The provider detects the conflict and throws an optimistic locking exception.

Never assign version manually in business code. The provider manages version on entity insert/update. Use a JPA-supported version type such as int, Integer, long, Long, short, Short, java.sql.Timestamp, or a compatible temporal type per spec/provider. Long is easy to inspect and offers ample range.

### 3.1. Initializing Version in the Schema

DDL can declare the version column:

~~~sql
CREATE TABLE banking.account (
  id BIGINT NOT NULL,
  balance DECIMAL(19,2) NOT NULL,
  version BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

When Hibernate inserts a new entity, the provider initializes version per the mapping. If rows are inserted via SQL outside JPA, ensure version receives a valid initial value. Every non-JPA write path must respect the same version contract to avoid breaking conflict detection.

### 3.2. When Are Conflicts Detected?

Conflicts are typically detected when the provider flushes changes to the database. Flushing can occur:

- When calling EntityManager.flush().
- Before a query that requires persistence context synchronization under the active flush mode.
- At transaction commit.
- Whenever the provider decides to flush.

Consequently, repository.save(entity) returning does not mean the commit succeeded. Failure may appear only at flush or when the transaction commits at the end of the @Transactional method.

You can call flush to detect conflicts earlier in a workflow:

~~~java
account.debit(amount);
entityManager.flush();
~~~

Flush dispatches SQL to the database without committing the transaction. The transaction can still roll back afterward, and other errors can still arise at commit. Never catch an optimistic conflict and continue using the entity or persistence context as if nothing happened.

### 3.3. Handling OptimisticLockException

JPA defines OptimisticLockException. With Spring, it is normally translated into an OptimisticLockingFailureException in Spring's exception hierarchy.

Basic service:

~~~java
@Service
public class AccountService {
    private final AccountRepository accounts;

    public AccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long accountId, BigDecimal amount) {
        Account account = accounts.findById(accountId)
            .orElseThrow(() -> new EntityNotFoundException("Account not found"));

        account.debit(amount);
    }
}
~~~

If two requests simultaneously edit the entity at the same version, one commits first and the other fails at flush/commit. The failed transaction must roll back. If business rules allow, the application can reload fresh state and re-execute the full operation in a new transaction.

Never retry only the final UPDATE with the stale version. Reload the data and recompute business decisions from fresh state.

## 4. Optimistic Locking with Spring Data JPA

The repository can extend standard JpaRepository:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
~~~

Spring Data JPA and the provider manage version automatically during entity updates. Service code does not need explicit version predicates in every statement as long as all writes flow through the entity lifecycle.

Points to watch:

- The entity must be managed in the persistence context when mutated so dirty checking works.
- For detached entities, save typically triggers merge, returning a separate managed instance. Do not keep using the detached instance to infer the new version.
- Never mutate the version field manually.
- Ensure all significant write paths honor the version contract.
- Handle errors at the transaction boundary, not merely around a repository call.

### 4.1. DTOs and Entity Updates

APIs should accept changes via DTOs, load the current entity, and apply only permitted fields. Avoid accepting a raw entity from clients and blindly merging it, because clients might send a stale version, sensitive fields, or immutable attributes.

Example:

~~~java
public record ChangeAccountRequest(
    BigDecimal debitAmount,
    Long expectedVersion
) {}
~~~

You can compare the request's expectedVersion with the loaded entity's version to return a clear business error. However, a Java-level check does not replace the @Version check at flush: another transaction could still commit right after that check. The database version predicate remains the final safeguard.

## 5. Bulk Updates and Native SQL Can Bypass @Version

JPQL bulk updates, Criteria bulk updates, and native SQL do not follow the normal entity lifecycle. They neither increment version automatically like entity dirty checking nor synchronize entities already loaded in the persistence context.

Bulk update example:

~~~java
@Modifying
@Query("""
    update Account a
       set a.balance = a.balance - :amount
     where a.id = :id
       and a.balance >= :amount
    """)
int debitIfEnough(
    @Param("id") Long id,
    @Param("amount") BigDecimal amount
);
~~~

This statement uses an atomic predicate to debit only when funds suffice, without automatically checking @Version. When optimistic version checking is needed in a bulk update, include version in the WHERE clause and increment it explicitly:

~~~java
@Modifying
@Query("""
    update Account a
       set a.balance = a.balance - :amount,
           a.version = a.version + 1
     where a.id = :id
       and a.version = :expectedVersion
       and a.balance >= :amount
    """)
int debitWithVersion(
    @Param("id") Long id,
    @Param("amount") BigDecimal amount,
    @Param("expectedVersion") Long expectedVersion
);
~~~

If the update returns 0, the row might be missing, the version may have changed, or the balance may be insufficient. Distinguish those cases with appropriate queries/logic if the API must report specific error reasons.

After a bulk update, entities of that type already loaded in the persistence context become stale. Use clearAutomatically/flushAutomatically where appropriate, or explicitly flush and clear the EntityManager. Never read entities from a stale persistence context assuming they reflect bulk updates.

## 6. Pessimistic Locking in JPA

Pessimistic locking instructs the database to lock a resource so competing transactions cannot perform conflicting operations until the current transaction ends or a lock timeout occurs.

Jakarta Persistence defines standard lock modes:

| LockModeType | Meaning |
|---|---|
| NONE | No extra JPA lock requested. |
| READ | Equivalent to optimistic read lock in JPA semantics; do not confuse with InnoDB physical shared locks. |
| WRITE | Equivalent to optimistic write lock; typically mapped to a version check. |
| OPTIMISTIC | Requests an optimistic lock for the entity. |
| OPTIMISTIC_FORCE_INCREMENT | Optimistic lock that increments version even without ordinary field changes. |
| PESSIMISTIC_READ | Requests a database read/shared lock if supported by the provider. |
| PESSIMISTIC_WRITE | Requests an exclusive/write lock blocking other transactions from modifying/deleting locked rows. |
| PESSIMISTIC_FORCE_INCREMENT | Pessimistic lock combined with version increment under JPA semantics. |

In JPA applications, use PESSIMISTIC_WRITE for operations that must read and update a row within a brief transaction. With InnoDB, this normally translates to a locking read like SELECT ... FOR UPDATE.

Never hold pessimistic locks while calling external APIs, waiting on users, or running heavy CPU tasks. Locks stay held until transaction commit or rollback, so longer transactions drive higher contention and deadlock risk.

## 7. Using @Lock in Spring Data JPA

Spring Data JPA lets you attach a lock mode to repository methods via @Lock:

~~~java
public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

Services must invoke this method inside a transaction:

~~~java
@Service
public class LockedAccountService {
    private final AccountRepository accounts;

    public LockedAccountService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void debit(Long accountId, BigDecimal amount) {
        Account account = accounts.findByIdForUpdate(accountId)
            .orElseThrow(() -> new EntityNotFoundException("Account not found"));

        account.debit(amount);
    }
}
~~~

Calling a locking query outside a transaction causes incorrect behavior or a provider/database error. Never rely on a @Lock repository method as if it creates a transaction spanning the entire service workflow.

### 7.1. Using EntityManager

You can request a lock when finding an entity:

~~~java
Account account = entityManager.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Or lock an already-managed entity:

~~~java
entityManager.lock(account, LockModeType.PESSIMISTIC_WRITE);
~~~

Both require an active transaction. If the entity is already in the persistence context, the provider may issue a lock statement for the corresponding row; verify emitted SQL and behavior against your provider/version.

### 7.2. Locking Queries with JPQL

~~~java
TypedQuery<Account> query = entityManager.createQuery(
    "select a from Account a where a.id = :id",
    Account.class
);

query.setParameter("id", accountId);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

Account account = query.getSingleResult();
~~~

Locking queries fit when locking a filtered set of entities. Inspect the execution plan and indexes; a broad predicate can lock far more records or index ranges than intended depending on InnoDB's isolation level and access path.

## 8. Row Locking, Indexes, and InnoDB Lock Scope

InnoDB locks records/index records, not merely abstract logical rows as pictured at the ORM layer. For locking reads and updates, lock scope depends on the index used, search predicates, and isolation level.

Under REPEATABLE READ, InnoDB can apply next-key locks (record lock plus gap lock) to prevent phantoms when applicable. A locking query missing a suitable index can scan and lock many more records than expected.

Example:

~~~sql
SELECT *
FROM sales.orders
WHERE customer_id = 42
FOR UPDATE;
~~~

If customer_id lacks an index, the engine scans many rows. Under a locking read, that builds a wide lock footprint, forcing unrelated transactions to wait.

Create an index matching the predicate and verify the plan:

~~~sql
CREATE INDEX idx_orders_customer_id
ON sales.orders(customer_id);

EXPLAIN
SELECT *
FROM sales.orders
WHERE customer_id = 42
FOR UPDATE;
~~~

Indexes do more than speed up queries; they also narrow the set of records accessed and locked. Still, extra indexes add write and storage overhead. Choose indexes to match real workloads.

## 9. Pessimistic Lock Timeout

JPA lets you pass lock timeout hints. In Jakarta Persistence, the standard hint is jakarta.persistence.lock.timeout in milliseconds:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.lock.timeout", 3000
);

Account account = entityManager.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
~~~

Providers may not support or honor this hint identically across all databases and drivers. Verify emitted SQL and actual runtime behavior with integration tests.

With Spring Data JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("select a from Account a where a.id = :id")
Optional<Account> findForUpdate(@Param("id") Long id);
~~~

On Spring Boot 2/older JPA, the hint name is javax.persistence.lock.timeout. Never mix javax and jakarta persistence packages in the same application.

## 10. Three Distinct Types of Timeouts

Applications often need timeouts at multiple layers:

| Timeout | Common Unit | What It Bounds |
|---|---|---|
| @Transactional(timeout = ...) | Seconds | Transaction duration per transaction manager/provider |
| jakarta.persistence.query.timeout | Milliseconds | Query execution time per JPA/provider hint |
| jakarta.persistence.lock.timeout | Milliseconds | Lock acquisition wait time per JPA/provider hint |
| innodb_lock_wait_timeout | Seconds | How long InnoDB waits for a row lock before throwing lock wait timeout |
| JDBC connectTimeout | Milliseconds | Time to establish TCP connection |
| JDBC socketTimeout | Milliseconds | Time waiting to read data from socket |
| Connection pool timeout | Pool-defined | Time waiting to borrow a connection from the pool |

Transaction timeout example:

~~~java
@Transactional(timeout = 10)
public void updateOrder(Long orderId) {
    // Transaction work.
}
~~~

Query timeout example:

~~~java
query.setHint("jakarta.persistence.query.timeout", 5000);
~~~

These limits operate at distinct layers. A transaction timeout does not necessarily abort an already-executing SQL query immediately; nor does a query timeout define lock-wait duration on every provider. Verify support and actual configuration behavior.

### 10.1. innodb_lock_wait_timeout

MySQL exposes the innodb_lock_wait_timeout system variable, in seconds, to bound InnoDB row lock waits. Check it with:

~~~sql
SHOW VARIABLES LIKE 'innodb_lock_wait_timeout';
~~~

This timer does not govern every lock type or SQL activity. Metadata locks (MDL), network timeouts, and query execution follow separate mechanisms.

Never raise innodb_lock_wait_timeout just to mask chronic contention. Identify lock-holding transactions, inspect execution plans, shorten transactions, or standardize update order first.

### 10.2. Lock Timeout vs. Query Timeout

A lock timeout happens when a statement cannot acquire required locks within the allowed window. A query timeout bounds total query execution time. A query can run slowly due to scans, CPU, or I/O without waiting on any lock; conversely, a trivial query can hit a lock timeout when another transaction holds a row lock for too long.

Record the exact timeout type. Never collapse every timeout into a generic "database unavailable" message.

## 11. Deadlocks and Lock Wait Timeouts in MySQL

A deadlock occurs when transactions form a circular lock-wait dependency. Example:

~~~text
Transaction T1                 Transaction T2
----------------              ----------------
Locks row A                    Locks row B
Waits for row B lock           Waits for row A lock
       \                         /
        \--- lock wait cycle ---/
~~~

InnoDB detects deadlocks and chooses one transaction as the victim to roll back. Applications typically observe MySQL error 1213 (Deadlock found when trying to get lock), usually mapped to SQLState class 40001.

A lock wait timeout is typically reported as MySQL error 1205. One transaction waited longer than the configured threshold for a lock, causing its statement to fail.

Key distinctions:

- Deadlock: the database detects a wait cycle and picks a victim; the victim transaction is rolled back.
- Lock wait timeout: a statement waited too long and timed out.
- Optimistic conflict: the version predicate no longer matches, signaling that another transaction modified the row.

### 11.1. MySQL Rollback Behavior on Timeout

In MySQL, innodb_rollback_on_timeout controls rollback scope on lock wait timeouts. When off (the common default), InnoDB rolls back only the timed-out statement; when on, InnoDB rolls back the entire transaction. Check the live configuration:

~~~sql
SHOW VARIABLES LIKE 'innodb_rollback_on_timeout';
~~~

At the Spring layer, if an unchecked exception escapes a @Transactional method, Spring marks the transaction for rollback by default. However, if code catches the exception and continues or swallows it, transaction state can become inconsistent.

Never continue committing a transaction after a lock timeout simply because MySQL may have rolled back only the last statement. Roll back the entire business unit and restart from scratch if business rules permit retries.

## 12. Exception Translation from JPA/Hibernate to Spring

Spring provides exception translation so service layers do not depend directly on raw JDBC error codes or Hibernate-specific exceptions.

Common exception groups:

| Root Error or Scenario | Likely Spring Exception Group | Meaning |
|---|---|---|
| Optimistic version conflict | OptimisticLockingFailureException or JPA equivalent subclass | Entity was modified by another transaction. |
| Failed to acquire pessimistic lock | PessimisticLockingFailureException or CannotAcquireLockException | Lock could not be acquired under current conditions. |
| Deadlock | DataAccessException subclass reflecting concurrency/lock failure | Transaction was chosen as victim or could not proceed. |
| Constraint violation | DataIntegrityViolationException | Violated unique, foreign key, NOT NULL, or other constraint. |
| General database access error | DataAccessException | Data-access failure requiring further classification. |

Exact exception classes depend on Spring version, persistence provider, driver, and where the failure occurs. You might observe jakarta.persistence.OptimisticLockException, org.hibernate.StaleObjectStateException, or a Spring subclass after exception translation runs.

### 12.1. @Repository and Exception Translation

Spring-managed repository beans participate in exception translation. Spring translates persistence/SQL errors into a more uniform DataAccessException hierarchy.

~~~java
@Repository
public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
~~~

Spring Data repositories include this automatically. For custom DAOs using EntityManager/JdbcTemplate, ensure the bean is Spring-managed and uses the proper abstractions so exception translation applies.

Never catch Throwable or generic Exception and map every error to "conflict". Preserve root causes and classify by exception class, cause, SQLState, and vendor code when needed.

### 12.2. Useful Error Logging

When logging concurrency errors, include:

- Entity/table and relevant business keys.
- Operation or request ID.
- Transaction boundary and execution duration.
- Lock mode/isolation level if relevant.
- Exception class, SQLState, and MySQL vendor code.
- Retry attempt count and backoff delay.
- Host/database endpoint used.

Never log passwords, tokens, personal data, or raw SQL containing sensitive literals. Use bind parameters and log query templates or operation IDs.

## 13. @Transactional Rollback Rules

Spring rolls back a transaction by default when a @Transactional method exits via an unchecked exception (RuntimeException or Error). Checked exceptions do not trigger automatic rollback by default.

Example declaring rollback for a checked exception:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void processOrder(Long orderId)
        throws BusinessRuleException {
    // Database operations.
}
~~~

OptimisticLockException and many Spring DataAccessExceptions are unchecked. Allowing them to escape the transaction boundary causes Spring to roll back by default.

### 13.1. Never Catch and Ignore Exceptions

Dangerous example:

~~~java
@Transactional
public void updateAccount(Long id) {
    try {
        // Load and update entity.
    } catch (OptimisticLockingFailureException ex) {
        log.warn("Conflict", ex);
        // Continue processing as if the update succeeded.
    }
}
~~~

After a conflict, the transaction may already be marked rollback-only or the persistence context may no longer be valid to continue. When the method finishes, commit fails with UnexpectedRollbackException or another provider exception.

To retry, let the exception escape the transaction attempt and run the next attempt in a brand-new transaction.

## 14. Retries Must Live Outside the Failed Transaction

A concurrency failure cannot be repaired by re-running statements inside a transaction already marked rollback-only. Every retry needs a fresh transaction and usually reloads entities from the database.

A clear pattern separates a coordinating facade from a bean executing one attempt:

~~~java
@Service
public class TransferFacade {
    private final TransferAttemptService attempts;

    public TransferFacade(TransferAttemptService attempts) {
        this.attempts = attempts;
    }

    // Do not place @Transactional on this coordinator method.
    public void transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                attempts.transferOnce(fromId, toId, amount);
                return;
            } catch (OptimisticLockingFailureException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                pauseBeforeRetry(attempt);
            }
        }
    }

    private void pauseBeforeRetry(int attempt) {
        long delayMillis = Math.min(100L * (1L << (attempt - 1)), 1000L);
        try {
            Thread.sleep(delayMillis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}
~~~

The bean executing a single attempt:

~~~java
@Service
public class TransferAttemptService {
    private final AccountRepository accounts;

    public TransferAttemptService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transferOnce(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Account from = accounts.findById(fromId)
            .orElseThrow(() -> new EntityNotFoundException("Source missing"));

        Account to = accounts.findById(toId)
            .orElseThrow(() -> new EntityNotFoundException("Target missing"));

        from.debit(amount);
        to.credit(amount);
    }
}
~~~

The two classes are separate Spring beans so calls to transferOnce pass through the transactional proxy. Never invoke another @Transactional method on the same object via self-invocation expecting the proxy to open a new transaction.

Once an attempt throws an exception, the proxy rolls back the transaction before returning the exception to the facade. The next attempt starts a fresh transaction and loads fresh entities.

### 14.1. Retryable Errors

Consider retrying:

- OptimisticLockingFailureException when business logic can recompute from fresh state.
- Deadlocks or transient lock errors properly classified.
- Certain transient connection errors, though indeterminate outcomes during commit require special handling.

Never automatically retry:

- SQL syntax errors or missing columns/tables.
- Permission or authentication failures.
- Business rule violations unaffected by reloading state.
- Duplicate key errors indicating the request was already processed or input is invalid.
- Invalid data or permanent constraint violations.

### 14.2. Retries and Idempotency

If a transfer request is resent due to a client timeout, internal retries are not the only safeguard needed against duplicate execution. Use a unique request ID and persist the business outcome inside the same transaction. When the request has already completed, replay the stored result rather than transferring funds twice.

Never sleep/backoff inside a transaction holding pessimistic locks. Roll back and close the transaction first, wait outside any transaction, and only then begin the next attempt.

## 15. Choosing Optimistic or Pessimistic by Business Case

| Use Case | Initial Recommendation | Rationale |
|---|---|---|
| User editing personal profile, rare conflicts | Optimistic | Can prompt user to reload when version changed. |
| Collaborative document editing | Optimistic | Detects stale edits and prompts content merge. |
| Hot-item stock deduction | Atomic conditional UPDATE or pessimistic depending on workload | Must prevent overselling; measure contention. |
| Transferring funds between two accounts | Optimistic or pessimistic with short transactions and consistent lock order | Must update both accounts atomically. |
| Claiming a single unique resource | Pessimistic lock or unique constraint/atomic claim | Must prevent two workers claiming the same resource. |
| Updating order state | Optimistic with version and state-transition predicate | Detects requests acting on stale state. |
| Reading reports | Usually no pessimistic lock needed | Read locks block writers without business benefit. |

For inventory, a conditional UPDATE is often concise:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE product_id = ?
  AND available >= 1;
~~~

If the update count is 1, one unit was reserved. If 0, either the product does not exist or stock is exhausted; a follow-up query may distinguish those two cases. This executes the check and update atomically in the database.

For multi-row, multi-table, or complex read-then-decide workflows, select @Version or pessimistic locks based on contention levels and UX requirements.

## 16. Pessimistic Locks and Lock Ordering

When a transaction must lock multiple rows, acquire locks in a consistent order to reduce deadlock risk.

For example, given two accounts with IDs 10 and 20, ensure every transfer locks the smaller ID before the larger ID:

~~~java
List<Long> ids = Stream.of(fromId, toId)
    .sorted()
    .toList();

List<Account> locked = accounts.findAllByIdForUpdate(ids);
~~~

The repository can define:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select a from Account a where a.id in :ids order by a.id")
List<Account> findAllByIdForUpdate(@Param("ids") Collection<Long> ids);
~~~

Verify actual locking order via SQL and execution plans; an ORDER BY in JPQL does not always guarantee every internal locking detail. When lock order is a critical invariant, acquire locks one by one in explicit order within the same transaction or use verified SQL.

Never assume the database always locks rows in the order of the input collection. Verify against your exact MySQL and Hibernate versions.

## 17. Lock Timeouts, Exceptions, and Transaction State

When a lock timeout or deadlock occurs, treat the current transaction attempt as failed and roll back the entire unit of work before retrying.

JPA distinguishes two scenarios:
- PessimisticLockException indicates a lock error that marks the transaction for rollback under JPA semantics.
- LockTimeoutException indicates a lock acquisition timeout without necessarily marking the transaction rollback-only under the JPA spec.

However, Spring @Transactional rolls back by default whenever an unchecked exception escapes the proxy. If code catches LockTimeoutException inside the method and continues, the transaction may sit in an unpredictable state between provider and database. The safe pattern for write workflows is stopping the attempt, rolling back, and starting a fresh transaction if retrying.

Never try to resume midway through a multi-table update sequence after a locking operation failed.

## 18. Observing Lock Waits on MySQL

When the system slows due to locks, locate the waiting transactions and the lock-holding transactions.

On MySQL 8.0, Performance Schema exposes data lock details:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

Lock wait relationships:

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Inspect InnoDB transactions:

~~~sql
SELECT *
FROM information_schema.innodb_trx;
~~~

And InnoDB status output:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

These tables and commands require appropriate privileges. Output from SHOW ENGINE INNODB STATUS has many sections; focus on LATEST DETECTED DEADLOCK and transactions holding/waiting for locks.

When investigating, record:

- Transaction ID and how long the transaction has been open.
- Thread/connection ID and user.
- Currently executing SQL or prior statement.
- Locked table/index.
- Lock mode and WAITING/GRANTED state.
- Isolation level.
- Application request ID.
- Lock hold duration and number of impacted requests.

Never simply raise timeouts when seeing lock waits. Pinpoint transactions holding locks too long, missing indexes, inconsistent lock ordering, or non-database work inside transactions.

## 19. Testing Optimistic Conflicts

An integration test needs two independent transactions reading the same version and then updating.

Test flow:

1. Create an account with balance 100 and version 0.
2. Transaction A loads the entity.
3. Transaction B loads the same entity.
4. A updates balance and commits; version increments.
5. B mutates the entity from the stale version and attempts to commit.
6. Verify B receives an optimistic locking failure.
7. Read the entity in a fresh transaction and verify balance/version.

Never use a single EntityManager/persistence context for both transactions because it can return the same managed instance and fail to reproduce real contention. Use two separate connections or transaction manager contexts with synchronization barriers to control ordering.

## 20. Testing Pessimistic Locks and Timeouts

Use two transactions:

1. T1 opens a transaction and acquires PESSIMISTIC_WRITE on the account.
2. T1 holds the transaction uncommitted.
3. T2 requests PESSIMISTIC_WRITE on the same row.
4. T2 blocks until T1 commits/rolls back or times out.
5. Record the exception and wait duration.
6. Verify T2 can retry in a new transaction if business rules allow.

Tests must run against production-like MySQL/InnoDB. H2 or mocked databases cannot accurately reproduce MySQL locking behavior, deadlock detection, timeouts, and Hibernate-generated SQL.

## 21. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming @Transactional prevents lost updates | Two transactions can still overwrite based on stale reads | Use @Version, locking reads, or atomic conditional UPDATEs. |
| Omitting @Version on optimistically locked entities | Stale updates go undetected | Add a version column and ensure all write paths honor it. |
| Using bulk updates expecting @Version to run automatically | Version and persistence context go out of sync | Include explicit version predicates/increments or use entity lifecycle. |
| Calling PESSIMISTIC_WRITE outside a transaction | Lock is not held across business logic | Place transaction boundaries at the service layer. |
| Holding locks during HTTP calls | Long transactions, lock waits, and deadlocks | Decouple side effects via outbox or run outside transactions. |
| Catching optimistic exceptions and continuing | Transaction may be rollback-only or context stale | Let errors escape the attempt; retry in a fresh transaction. |
| Retrying inside the same @Transactional method | Retries inside an already-failed transaction | Separate retry orchestration from transactional worker beans. |
| Raising lock timeouts to hide contention | Requests hang longer and retain resources longer | Find blockers, add indexes, and shorten transactions. |
| Varying lock orders across flows | Frequent deadlocks | Enforce a single global lock order. |
| Testing only with H2 | Misses MySQL locking differences | Run integration tests on MySQL/InnoDB. |
| Retrying non-idempotent operations | Duplicate writes or repeated side effects | Use request IDs/unique keys and persist outcomes atomically. |

## 22. Hands-On Exercises

### Exercise 1: Optimistic Locking

Create an Account entity with @Version. Open two independent transactions, load the same account in both, update from both, and commit sequentially. Observe version increment and the stale transaction's exception.

### Exercise 2: Pessimistic Locking

Create a repository method with @Lock(PESSIMISTIC_WRITE). Use two transactions locking the same row, measure wait duration, and experiment with lock timeout settings. Confirm the lock releases on commit/rollback.

### Exercise 3: Bulk Update

Write a JPQL bulk update for a @Version entity. Check whether version increments, then update the query to verify expected version and increment version explicitly. Refresh the persistence context and compare results.

### Exercise 4: Deadlock

Create two transactions updating two rows in opposite orders to induce a deadlock. Record the MySQL error code/SQLState and Spring exception. Refactor to lock in consistent order and re-test.

### Exercise 5: Retrying Outside the Transaction

Separate a coordinating facade from a transactional service. Induce controlled optimistic conflicts and retry up to three times with backoff. Confirm each attempt gets a new transaction/persistence context and does not duplicate work.

### Exercise 6: Multi-Layer Timeouts

Configure distinct transaction, query, and lock timeouts in a test environment. Simulate both a slow query and a lock wait. Observe exception types, trigger times, and rollback states.

## 23. Pre-Production Checklist

- [ ] Entities have @Version wherever stale updates must be detected.
- [ ] Non-JPA write paths audited so they do not break the version contract.
- [ ] Bulk JPQL/native SQL includes version predicates and synchronizes persistence context when needed.
- [ ] Pessimistic locks held only inside short transactions.
- [ ] Repository locking methods called from services with clear transaction boundaries.
- [ ] Indexes support predicates of locking queries.
- [ ] Consistent lock ordering enforced when updating multiple rows.
- [ ] Transaction, query, lock, connection, and pool timeouts clearly distinguished.
- [ ] innodb_lock_wait_timeout and innodb_rollback_on_timeout verified.
- [ ] Exception translation tested against exact Spring/JPA/provider versions.
- [ ] Retries executed outside failed transactions.
- [ ] Retries bounded with backoff and paired with idempotency.
- [ ] Locks never held during external calls or user waits.
- [ ] Monitoring in place for lock waits, deadlocks, transaction age, and pool saturation.
- [ ] Integration tests executed against production-compatible MySQL/InnoDB.
- [ ] Logs capture request ID, SQLState/vendor code, and retry counts without leaking secrets.

Optimistic locking uses version numbers to catch updates built on stale reads; pessimistic locking holds locks inside transactions to coordinate contended access. Timeouts must be configured at the proper layers, while exception translation gives applications consistent error classification. When a transaction fails, roll back the entire attempt and retry in a fresh transaction only when business operations can repeat safely. Test on real MySQL/InnoDB, monitor lock waits and deadlocks, and choose your strategy based on contention levels and business invariants.
