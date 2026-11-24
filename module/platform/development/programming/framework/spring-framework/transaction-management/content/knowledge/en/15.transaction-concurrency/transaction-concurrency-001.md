# Distinguishing Propagation, Isolation, and Locking Strategies in Spring Transaction Management

> **Spring Framework — Transaction Management → Locking and Concurrency.** A transaction can be configured with the right `propagation` and still suffer from lost updates, write skew, deadlocks, or lock waits. Conversely, raising `isolation` or adding `SELECT ... FOR UPDATE` does not fix a bug where a transaction was unintentionally split by `REQUIRES_NEW`. The three concepts—**propagation**, **isolation**, and **locking/concurrency control strategies**—answer three different kinds of questions. This lesson clearly distinguishes their responsibilities, relationships, and safe combinations in Spring Framework, JDBC/JPA, and relational databases.

## 1. Three questions, three independent design axes

**Propagation** answers:

> When a transactional method calls another method, does the inner method **join the existing transaction**, **open a new transaction**, **create a savepoint**, or **run outside a transaction**?

**Isolation** answers:

> Within a physical transaction, how can queries **observe concurrently modified data**, and which anomalies does the database management system prevent?

**Locking / concurrency control strategy** answers:

> When multiple transactions read or modify data concurrently, how do we **prevent overwrites, enforce business invariants, and coordinate access**: SQL atomic update, optimistic version check, row lock, advisory lock, unique constraint, or serializable retry?

Quick positioning table:

| Axis | API Example | Directly Controls | Does Not Automatically Guarantee |
| --- | --- | --- | --- |
| **Propagation** | `@Transactional(propagation = Propagation.REQUIRED)` | Relationship between inner/outer logical scopes and physical transactions | Does not automatically prevent lost update, phantom, deadlock, or check business invariants |
| **Isolation** | `@Transactional(isolation = Isolation.READ_COMMITTED)` | Level of concurrent data visibility allowed and anomalies prevented by DB per isolation contract | Does not automatically create an independent transaction, nor prove all business races are handled |
| **Locking / concurrency strategy** | `SELECT ... FOR UPDATE`, `@Version`, conditional `UPDATE` | Who may modify which record, when to wait/conflict, and how conflicts are detected | Does not replace transaction boundaries or make two databases commit atomically |
| **Rollback rules** *(related axis)* | `rollbackFor`, `noRollbackFor` | Which exceptions request rolling back a transaction scope | Not propagation, isolation, or lock mode |

A proper choice usually combines all three axes, for example:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED
)
public void reserveStock(long productId, int amount) {
    // Use an atomic conditional UPDATE so inventory cannot go negative.
}
```

The snippet above is a **fragment**, not a standalone runnable method. It states that the use case has an appropriate transaction and wants `READ_COMMITTED` isolation if a new transaction is created. The **non-negative inventory invariant** must still be protected by a SQL condition or an appropriate locking/constraint strategy; the annotation does not inject that condition automatically.

## 2. Intuitive example: three different requirements on the same transaction

Suppose a service reserves orders and receives two concurrent requests:

```text
Request A                              Request B
---------                              ---------
begin transaction T1                  begin transaction T2
read stock=1                           read stock=1
check stock >= 1                       check stock >= 1
write stock=0                          write stock=0
commit T1                              commit T2
```

If both rely on a **read first, then write the computed value** model, the business logic risks overselling or overwriting results. Both methods can be `@Transactional(REQUIRED)` and still hit a race: each request has its own transaction because there is no shared caller transaction spanning **across the two requests**.

- Changing `REQUIRED` to `REQUIRES_NEW` for each request **does not help**: there are still two competing transactions.
- Setting a stronger isolation level may change the snapshot, conflict detection, or force rollback/retry; **exact behavior depends on the DBMS**.
- Executing an **atomic conditional UPDATE** checking that sufficient stock remains is usually more direct: the database checks the condition and modifies the data as a single statement, bounding the race for this invariant.
- If the business operation spans multiple rows/complex conditions, appropriate locks or serializable transactions + retry must be coordinated.

Example protecting inventory with a single SQL statement:

```sql
UPDATE inventory
SET available = available - :amount,
    version = version + 1
WHERE id = :productId
  AND available >= :amount;
```

This is a **SQL fragment** using named parameters (for example `NamedParameterJdbcTemplate`), and cannot be executed verbatim directly in every SQL client. If affected rows = 1, inventory was deducted; if = 0, the product does not exist or the quantity is insufficient. You must check the affected row count and translate it into a business result, rather than assuming the statement succeeded.

**Distinction:** propagation determines which transaction contains the UPDATE, isolation affects visibility and contention with other transactions, while the `available >= :amount` condition is the **specific guard** for the "do not deduct more than available" invariant.

## 3. Propagation: choosing the physical transaction, not isolation or locking

In Spring, `@Transactional` has a default propagation of `Propagation.REQUIRED`.

### 3.1. `REQUIRED`: usually the same physical transaction

```text
OrderService.place()    @Transactional(REQUIRED) --> physical T1
   |
   +-- InventoryService.reserve() @Transactional(REQUIRED)
           |
           +-- different logical scope
           +-- typically JOINS physical T1
```

The two logical scopes still have their own rollback rules and rollback-only status; however, when sharing the same physical transaction, the inner scope cannot commit its data independently of the outer scope. If the inner scope marks the transaction rollback-only, the outer scope may receive `UnexpectedRollbackException` when attempting to commit.

**What does not change:** T1 still contends with transactions T2/T3 from other requests. `REQUIRED` does not impose a row lock before every SELECT, nor does it guarantee serializable execution.

### 3.2. `REQUIRES_NEW`: an independent transaction does not mean avoiding concurrency

```text
Outer @Transactional(REQUIRED) --> T1 holds Connection A, may hold locks
   |
   +-- Inner @Transactional(REQUIRES_NEW)
            |
            +-- suspend context T1
            +-- open physical T2 on Connection B
            +-- commit/rollback T2 independently
   |
   +-- resume T1
```

The inner method has its own physical transaction and can specify its own isolation; however, **T1 does not automatically release locks just because it is suspended**. If T2 needs a row locked by T1, T2 may wait on the lock held by T1 itself. If the connection pool has no Connection B left, T2 may block while borrowing a connection. Raising isolation in T2 does not solve either of those issues.

`REQUIRES_NEW` can **increase** the risk of lock conflicts and connection starvation within a call chain, especially when the inner method reads/writes data that the outer method has not yet committed.

### 3.3. `NESTED`: savepoint, not a different isolation level

When the JDBC transaction manager and resource support savepoints, `Propagation.NESTED` allows the inner method to create a savepoint within the **same physical transaction**. Rolling back the inner scope can restore state to the savepoint and let the outer scope continue. It does not create a new physical snapshot/isolation level for the inner scope.

```text
T1 (READ_COMMITTED)
  +-- update A
  +-- SAVEPOINT s1
  +-- update B
  +-- ROLLBACK TO s1  => update B is undone
  +-- update C
  +-- COMMIT T1       => updates A and C are committed
```

This is a semantics diagram. Savepoints do not replace transaction isolation; not every JPA transaction manager/provider supports nested transactions in this manner. When outer T1 rolls back, all remaining changes in T1 are discarded.

### 3.4. `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`

These levels primarily define the contract regarding the **presence of a transaction**, and must not be misunderstood as an isolation or lock policy:

| Propagation | When caller has a transaction | When caller has no transaction | Concurrency-related point |
| --- | --- | --- | --- |
| `SUPPORTS` | May join | Can run without a physical transaction | Does not automatically provide a consistent snapshot when there is no transaction |
| `MANDATORY` | Must join | Throws `IllegalTransactionStateException` | Enforces that the operation runs within a caller boundary |
| `NOT_SUPPORTED` | Suspends the manager's transaction and runs outside | Runs outside a transaction | Multiple SQL statements may auto-commit individually; no grouped atomicity |
| `NEVER` | Throws an exception | Runs outside a transaction | Forbids the caller from having a transaction; does not make the operation thread-safe |

In short: **do not choose propagation to "eliminate" lost updates**. Choose propagation according to business boundaries: which work must commit/roll back together, which is independent, and which requires a caller-owned transaction.

## 4. Isolation: visibility and concurrency anomalies in a physical transaction

Spring's `Isolation` has the values: `DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`. They are mapped by JDBC/the transaction manager to the database isolation level if supported.

| Isolation | General Meaning | Important Notes |
| --- | --- | --- |
| `DEFAULT` *(Spring default)* | Keeps the underlying DB/resource default isolation level | Does **not** mean "no isolation"; DB defaults vary |
| `READ_UNCOMMITTED` | SQL standard allows dirty reads | Many DBMSs do not support true dirty reads or map it to a stronger level |
| `READ_COMMITTED` | A statement does not read uncommitted data from other transactions | Non-repeatable read/phantom/logic races can still occur |
| `REPEATABLE_READ` | Stronger guarantee for repeatedly reading a row per the standard contract | Phantom, snapshot, and write-conflict behavior varies by DBMS |
| `SERIALIZABLE` | Outcome of committed transactions is equivalent to a serial execution order | May produce serialization failures/deadlocks requiring full transaction retry; does not mean "no error checking needed" |

Isolation levels in the SQL standard define **bounds on anomalies that may occur**, while databases may provide stronger guarantees. For example, PostgreSQL treats `READ UNCOMMITTED` equivalently to `READ COMMITTED` and implements `REPEATABLE READ` with stronger characteristics regarding phantom reads than the standard SQL example table.

### 4.1. Dirty read

`T1` writes `balance=5` without committing yet. If `T2` reads that value and then T1 rolls back, T2 has read data that **was never committed**.

```text
T1: UPDATE balance=5 --- wait --- ROLLBACK
T2:                SELECT balance -> 5 (dirty read)
```

In DBMSs that support dirty reads, `READ_UNCOMMITTED` may allow this; `READ_COMMITTED` must not allow dirty reads by contract. However, you should not reason solely from the annotation if using a different DB/manager or if queries run outside a transaction.

### 4.2. Non-repeatable read

T1 reads a row twice; between those two reads, T2 commits a change. T1 may observe two different values.

```text
T1: SELECT price -> 100
T2: UPDATE price=110; COMMIT
T1: SELECT price -> 110
```

`READ_COMMITTED` may allow this, because each statement only needs to see data committed at the time of that statement. Some use cases require a more stable snapshot or row locking.

### 4.3. Phantom read

T1 runs the same predicate twice; T2 inserts/deletes rows matching the predicate in between. The number/set of rows may change.

```text
T1: SELECT COUNT(*) FROM bookings WHERE room_id=7 -> 2
T2: INSERT INTO bookings(room_id, ...) VALUES(7, ...); COMMIT
T1: SELECT COUNT(*) FROM bookings WHERE room_id=7 -> 3
```

`REPEATABLE_READ` in the SQL standard does not necessarily prevent all phantoms; MVCC implementations and range/predicate locks may prevent or handle them differently. PostgreSQL `REPEATABLE READ` does not allow phantom reads as described in its official documentation, though that conclusion should not be generalized to every DBMS.

### 4.4. Lost update

Two transactions read the same value and then both compute a new value in application code:

```text
Initial stock=10

T1: SELECT stock -> 10
T2: SELECT stock -> 10
T1: UPDATE stock=8; COMMIT
T2: UPDATE stock=9; COMMIT
Result=9 (T1's change is lost)
```

This is a **risk** of unprotected read-modify-write. Exactly which transaction blocks/aborts, and whether this outcome can occur, depends on isolation/DBMS/query shape. In particular, some DBMSs at stronger isolation levels have conflict detection. Do not treat this timeline as inevitable behavior for every `READ_COMMITTED` implementation.

There are several ways to handle it: atomic `UPDATE stock=stock-... WHERE...`, optimistic version, pessimistic lock, or serializable retry depending on the invariant.

### 4.5. Write skew

Two transactions read a set of rows and then write to **different rows**, violating a global invariant even though no two UPDATEs touch the same row.

For example, two on-call doctors: the rule is that at least one doctor must always be on-call. Both T1 and T2 see "the other one is still on-call," and each sets themselves off-call; the final state has nobody on-call.

Checking `@Version` only on the row **each side modifies** may fail to catch write skew because the two writes are on different rows. The invariant must be designed with a constraint/materialized lock, transactional locking of a shared guard row, serializable transaction + retry, or an appropriate coordinator mechanism.

**Note:** stronger isolation does not replace articulating the invariant. To know whether to lock rows or a predicate, you must understand all rows and conditions that govern the business rule.

## 5. When does Spring apply isolation?

A common configuration mistake: **isolation is set for a new physical transaction**, rather than automatically upgrading the isolation of an already-existing transaction when an inner `REQUIRED` method joins.

Example:

```java
@Service
class OuterService {
    private final InnerService inner;

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void outer() {
        inner.inner();  // Cross-bean call via Spring proxy.
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // Usually still runs inside outer's physical T1 READ_COMMITTED.
    }
}
```

This is a fragment: it needs constructors/imports and beans. With `AbstractPlatformTransactionManager`'s default lenient behavior, inner `REQUIRED` joins T1 and the inner's local isolation declaration is typically **ignored**. It does not secretly create a `SERIALIZABLE` snapshot just for a few inner SQL statements.

### 5.1. `validateExistingTransaction` to avoid silently ignoring mismatches

If you want to **detect configuration mistakes** when an inner method requests a different isolation from the outer transaction:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager tx = new JdbcTransactionManager(dataSource);
    tx.setValidateExistingTransaction(true);
    return tx;
}
```

Fragment in a Spring `@Configuration`. When a method joins T1 and declares an incompatible isolation, the manager can throw `IllegalTransactionStateException` instead of running under the outer isolation. This setting also checks matching read-only mismatches.

**Do not fix a mismatch by blindly changing inner to `REQUIRES_NEW`** if the business operation must be atomic with the outer transaction. `REQUIRES_NEW` creates a separate transaction, completely changing commit/rollback outcomes. The proper fix is to set the isolation at the transaction owner, or design the boundary to match the requirement.

### 5.2. With REQUIRES_NEW, the inner method can set its own isolation

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void independentStep() {
    // T2 actually has a new boundary and requests SERIALIZABLE.
}
```

Fragment. Because there is an independent T2, the new isolation can be applied as supported by the manager/driver. However, also because of T2, uncommitted data from T1 **is not automatically visible** from T2; an insert with a foreign key referencing a new row in T1 may fail or block.

### 5.3. With NESTED, there is no second physical isolation

If the inner method uses a savepoint inside T1, it must follow the isolation already established for T1; a savepoint is not a tool for changing isolation mid-transaction. When two genuinely different isolation levels are needed, you must evaluate whether splitting the physical transaction fits the invariant and resource usage.

### 5.4. DEFAULT does not mean READ_COMMITTED

`Isolation.DEFAULT` requests using the underlying transaction system's default. PostgreSQL typically defaults to `READ COMMITTED`; other DBMSs/connections may use different levels. Even when Spring's `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` returns `null`, the physical JDBC connection still has an isolation level. To verify the actual setting, query `Connection.getTransactionIsolation()` on the **connection participating in the transaction** or read the database transaction settings.

## 6. Locking: a different object from isolation

**Pessimistic locking**: acquires a lock to prevent/serialize competing operations before or during modification, usually via `SELECT ... FOR UPDATE` or JPA `LockModeType.PESSIMISTIC_WRITE`. If another transaction holds an incompatible lock, the caller may have to wait, time out, or be marked a deadlock victim by the DB.

**Optimistic locking**: does not hold an exclusive lock throughout the read phase; when writing, checks the expected version/condition. If data has changed, detects the conflict and rejects or retries with a fresh snapshot. JPA supports `@Version`, and JDBC can use `WHERE version = ?`.

**Atomic conditional write**: avoids the read-modify-write pattern in the application by using a guarded statement: `UPDATE ... WHERE available >= amount`, checking affected rows. This can be the simplest option for a local single-row invariant.

**Database constraints**: `UNIQUE`, `CHECK`, and `FOREIGN KEY` are enforced by the engine, preventing invariant violations even when multiple requests or services write concurrently. However, constraints cannot express all multi-row invariants.

**Serializable + retry**: lets the DBMS control the transaction schedule under serializable semantics. The application must handle serialization failures by retrying the **entire transaction from the beginning**, not just re-running a single SQL statement inside an aborted transaction.

There is no single optimal strategy for every workload. Evaluate write contention rate, transaction duration, data size, latency, correctness, and DB/driver capabilities.

## 7. Comparing optimistic and pessimistic locking by business decision

| Criterion | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| When conflict is detected | Usually at update/flush/commit when version mismatches | When trying to acquire the lock beforehand or during write |
| Holds row lock across read / user think time? | Typically does not hold long read locks | Can hold locks in the physical transaction until commit/rollback |
| Result on conflict | Updates 0 rows, `OptimisticLockException` or equivalent; requires reload/retry/response | Lock wait, timeout, deadlock detection, or fail-fast per DB syntax |
| Suitable when | Low contention, web forms, read-heavy, long user think time | High contention, write ordering must be coordinated, must read data and decide under lock |
| Risks | Retry storms, stale data, version does not cover multi-row invariants | Lock waits, deadlocks, reduced throughput, connections held longer |
| Relation to propagation | Still needs a transaction boundary for writes; does not alter REQUIRED/REQUIRES_NEW | Lock is owned by the physical transaction; not released when Spring suspends outer |
| Relation to isolation | Isolation can cause conflicts to surface earlier/later and change visibility | Isolation/DB engine affects lock types, lock compatibility, and query behavior |

Common ground: **locking does not eliminate the need to design transaction scope**. If a method invokes JPA `@Lock` without an actual transaction where the lock must be held, protection semantics may not meet intent; if a lock is acquired in T1, it only applies to operations executed within T1 under DB rules.

## 8. Pessimistic locking in JDBC: SELECT ... FOR UPDATE

In a Spring JDBC service:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void transfer(long fromId, long toId, long amount) {
    // Fragment: table/column names and validation checks must match the schema.
    Long current = jdbc.queryForObject(
        "SELECT balance FROM accounts WHERE id = ? FOR UPDATE",
        Long.class,
        fromId
    );

    if (current == null || current < amount) {
        throw new IllegalArgumentException("insufficient balance");
    }

    jdbc.update(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        amount, fromId
    );
    jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        amount, toId
    );
}
```

This is an **illustrative fragment**, not a standalone application. The code only locks the source row in the example; a real transfer should determine all rows that need locking, a **fixed lock ordering** (for example by account id), validation, and concurrency strategy. Do not consider it complete merely because it has `FOR UPDATE`.

When `SELECT ... FOR UPDATE` is supported by the DB and has an appropriate transaction, the row lock is typically held until the physical transaction completes. If another T2 needs an incompatible lock, it may wait.

### 8.1. What do NOWAIT and SKIP LOCKED actually change?

Some DBMSs support variants:

```sql
SELECT id FROM work_items
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
```

This is **DB-specific SQL**, particularly useful when multiple workers claim jobs from a queue. `SKIP LOCKED` lets workers skip rows currently locked instead of blocking, but the result is an **incomplete view at read time**. Do not use it to guarantee "no backlog jobs remain" in business logic requiring a full scan.

`NOWAIT` typically requests an immediate error if the lock cannot be acquired rather than waiting, though exact syntax and support vary across DBMSs. Do not conclude that any Spring `Propagation` automatically enables `NOWAIT` or `SKIP LOCKED`.

### 8.2. Do not hold locks across slow operations

```java
@Transactional
public void badExample() {
    lockCustomerRow();
    callExternalApi();  // HTTP may take several seconds.
    updateCustomer();
}
```

This fragment extends lock and connection hold times. Under high concurrency, other requests will queue up or time out. If an HTTP API response is needed before a write decision, consider moving it outside the boundary or using an optimistic version to revalidate before commit.

## 9. Optimistic locking with a version column

### 9.1. JDBC pattern

A table with `version`:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    available INT NOT NULL,
    version INT NOT NULL
);
```

Read a snapshot:

```sql
SELECT available, version
FROM inventory
WHERE id = 42;
```

When writing, use the read version as a condition:

```sql
UPDATE inventory
SET available = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :previousVersion;
```

If affected rows = 0, the data may have changed or the row may not exist. Never treat 0 updated rows as success; the application should report a conflict, perform bounded reload/retry, or return HTTP 409 depending on the use case.

**Caution:** a single-row version check alone does not protect invariants spanning multiple rows. You must also prevent other write paths from bypassing the version check or overwriting `version` with a stale value.

### 9.2. JPA `@Version`

With Jakarta Persistence, you can declare:

```java
@Entity
class Product {
    @Id
    private Long id;

    @Version
    private long version;

    private int available;
}
```

This is a **JPA fragment**, needing `jakarta.persistence.*` imports, constructors, accessors, and proper mappings. The provider uses the version to detect stale updates on managed entities, usually throwing `OptimisticLockException` or a Spring-translated exception at flush/commit.

**Note:** bulk JPQL updates or native SQL updates may not automatically participate in `@Version` like normal entity operations; version handling/where clauses must be designed accordingly. When an exception from JPA marks the transaction rollback-only, do not retry within the same failed transaction.

### 9.3. Spring Data JPA `@Lock` vs. `@Version`

A repository query can request a pessimistic lock:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findByIdForUpdate(@Param("id") Long id);
}
```

This is a **fragment** needing `org.springframework.data.jpa.repository.*`, `jakarta.persistence.LockModeType`, and `org.springframework.data.repository.query.Param`. It will not compile with only the Spring JDBC demo below; Spring Data JPA/JPA entities are required.

`@Lock` selects the JPA lock mode for a query; `@Version` is optimistic version metadata on the entity. Neither is `propagation`, and neither automatically creates a transaction boundary across all repository call paths.

## 10. Atomic conditional UPDATE: often less complex than both lock types

If the invariant is "non-negative quantity," an UPDATE with a condition-checking predicate can be a very effective measure:

```java
@Transactional
public void reserveStock(long productId, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    int updated = jdbc.update("""
        UPDATE inventory
        SET available = available - ?,
            version = version + 1
        WHERE id = ? AND available >= ?
        """, amount, productId, amount);

    if (updated != 1) {
        throw new IllegalStateException("insufficient stock");
    }
}
```

The fragment needs a `JdbcTemplate jdbc` field and an intercepted Spring bean. The SQL is a **read-modify-write inside the database engine**, rather than Java read -> compute -> blind update. With proper transaction/DB support, concurrent updates must coordinate writes to the same row; the predicate is evaluated according to database statement semantics. Under H2/PostgreSQL `READ_COMMITTED`, this pattern typically prevents overselling below zero for **a single row**.

Do not generalize this conclusion to multi-row invariants (for example "at most 100 bookings across multiple partitions"): you need additional unique/check constraints, a guard row, locks, or a serializable transaction.

**Do not forget the affected row count.** When row count = 0, the code must intentionally handle out-of-stock or a race; if silently ignored, the business logic might report success without deducting inventory.

## 11. When propagation and isolation appear together in a call chain

Consider three methods:

```java
// Create T1 if none exists, requesting READ_COMMITTED.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED
)
public void placeOrder() {
    inventoryService.reserve();       // Separate REQUIRED + SERIALIZABLE declaration
    auditService.recordIndependent(); // REQUIRES_NEW + SERIALIZABLE
}
```

This is a fragment, assuming the two services are injected Spring-managed beans. Tracing the outcome:

```text
placeOrder(): REQUIRED + READ_COMMITTED
     |
     +--> physical T1: READ_COMMITTED
     |
     +--> inventory.reserve(): REQUIRED + SERIALIZABLE
     |       +-- joins T1
     |       +-- effective isolation remains T1 (READ_COMMITTED)
     |           unless manager validateExistingTransaction detects mismatch
     |
     +--> audit.recordIndependent(): REQUIRES_NEW + SERIALIZABLE
             +-- new physical T2: requests SERIALIZABLE
             +-- T1 still exists and may hold locks/connection
             +-- T2 commits/rollbacks independently
```

Table:

| Inner method | Outer T1 present? | Physical transaction | Typical effective isolation | What must not be inferred |
| --- | --- | --- | --- | --- |
| `REQUIRED, isolation=SERIALIZABLE` | Yes, T1 READ_COMMITTED | Joins T1 | Outer's `READ_COMMITTED` (if manager is lenient) | Does not automatically upgrade inner to SERIALIZABLE |
| `REQUIRES_NEW, isolation=SERIALIZABLE` | Yes | Opens T2 | `SERIALIZABLE` if supported | Does not mean T2 sees uncommitted T1 or needs no extra connection |
| `NESTED` | Yes | Same T1/savepoint | Same isolation as T1 | No new snapshot isolation |
| `REQUIRED, isolation=SERIALIZABLE` | No | Opens new | `SERIALIZABLE` if supported | Does not automatically lock rows before reading unless SQL requests it |
| `SUPPORTS` | No | May have no physical transaction | Per nontransactional/default resource behavior | No snapshot transaction contract |
| `NOT_SUPPORTED` | Yes | Does not join T1; T1 suspended | Outside the manager's transaction | Does not guarantee atomicity across SQL statements |

In particular, `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` reflects the isolation Spring has set on the transaction context; `null` when no value was explicitly declared by Spring **does not mean the DB is at isolation "NONE"**. With JDBC, you can query the physical connection when needed.

## 12. Java 17+ runnable demo: proving isolation of REQUIRED and REQUIRES_NEW

The complete example below uses:

- JDK 17+ and Maven.
- Spring Framework 6.2.8, Spring JDBC, and H2 2.3.232.
- `JdbcTransactionManager` managing a datasource.
- `@EnableTransactionManagement` to activate proxy transaction advice.
- `TransactionSynchronizationManager` to **print the isolation context** inside the scopes.
- **Atomic conditional update** and **optimistic version check** to illustrate two overwrite-prevention strategies independent of propagation.

### 12.1. Create the directory structure

```text
propagation-isolation-lock-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── PropagationIsolationLockDemo.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>propagation-isolation-lock-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <version>3.5.0</version>
                <artifactId>exec-maven-plugin</artifactId>
                <configuration>
                    <mainClass>dev.learning.PropagationIsolationLockDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. `src/main/java/dev/learning/PropagationIsolationLockDemo.java`

```java
package dev.learning;

import java.sql.Connection;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class PropagationIsolationLockDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:iso_lock;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            // Default lenient: joining REQUIRED uses outer's isolation.
            return new JdbcTransactionManager(ds);
        }

        @Bean
        InventoryService inventoryService(JdbcTemplate jdbc) {
            return new InventoryService(jdbc);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(AuditService audit) {
            return new OrderService(audit);
        }
    }

    private record Stock(int available, int version) {}

    private static String isolationName() {
        Integer level =
                TransactionSynchronizationManager
                        .getCurrentTransactionIsolationLevel();

        if (level == null) {
            return "DEFAULT_OR_UNSPECIFIED";
        }

        return switch (level) {
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_READ_UNCOMMITTED -> "READ_UNCOMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ -> "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "OTHER";
        };
    }

    public static class InventoryService {
        private final JdbcTemplate jdbc;

        public InventoryService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Propagation chooses the boundary. SQL guard protects the invariant.
        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED
        )
        public void reserve(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }

            int changed = jdbc.update("""
                UPDATE inventory
                SET available = available - ?,
                    version = version + 1
                WHERE id = 1 AND available >= ?
                """, amount, amount);

            if (changed != 1) {
                throw new IllegalStateException("insufficient stock");
            }

            System.out.println(
                    "reserve.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
        }

        // Simplified optimistic locking: match version right at write time.
        @Transactional(propagation = Propagation.REQUIRED)
        public boolean reserveIfVersion(
                int expectedVersion, int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }

            int changed = jdbc.update("""
                UPDATE inventory
                SET available = available - ?,
                    version = version + 1
                WHERE id = 1
                  AND version = ?
                  AND available >= ?
                """, amount, expectedVersion, amount);

            return changed == 1;
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Only creates a new logical scope; joins T1 READ_COMMITTED.
        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE
        )
        public void joined() {
            System.out.println(
                    "joined.isolation=" + isolationName());
        }

        // A new physical transaction T2 with its own isolation.
        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            isolation = Isolation.SERIALIZABLE
        )
        public void independent() {
            System.out.println(
                    "new.isolation=" + isolationName());
            jdbc.update("""
                INSERT INTO audit_events(id, detail) VALUES(1, 'T2 committed')
                """);
        }
    }

    public static class OrderService {
        private final AuditService audit;

        public OrderService(AuditService audit) {
            this.audit = audit;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED
        )
        public void demonstrateIsolation() {
            System.out.println(
                    "outer.isolation=" + isolationName());

            // Call across another bean so the Spring proxy intercepts each method.
            audit.joined();
            audit.independent();

            System.out.println(
                    "outer.after.isolation=" + isolationName());
        }
    }

    private static Stock stock(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT available, version FROM inventory WHERE id = 1",
                (rs, rowNum) -> new Stock(
                        rs.getInt("available"),
                        rs.getInt("version")));
    }

    private static void showStock(
            String label, JdbcTemplate jdbc) {
        Stock value = stock(jdbc);
        System.out.printf(
                "%s.qty=%d version=%d%n",
                label, value.available(), value.version());
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                CREATE TABLE inventory (
                    id INT PRIMARY KEY,
                    available INT NOT NULL,
                    version INT NOT NULL
                )
                """);
            jdbc.execute(
                    "INSERT INTO inventory(id, available, version) "
                    + "VALUES(1, 10, 0)");

            jdbc.execute("""
                CREATE TABLE audit_events (
                    id INT PRIMARY KEY,
                    detail VARCHAR(80) NOT NULL
                )
                """);

            InventoryService inventory =
                    context.getBean(InventoryService.class);

            inventory.reserve(3);
            showStock("afterReserve", jdbc);

            try {
                inventory.reserve(10);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "reserve.failure=" + expected.getMessage());
            }
            showStock("afterRejected", jdbc);

            System.out.println(
                    "optimistic.stale="
                    + inventory.reserveIfVersion(0, 1));

            System.out.println(
                    "optimistic.fresh="
                    + inventory.reserveIfVersion(1, 1));
            showStock("afterOptimistic", jdbc);

            context.getBean(OrderService.class)
                    .demonstrateIsolation();

            Integer audits = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_events",
                    Integer.class);
            System.out.println("audit.count=" + audits);
        }
    }
}
```

### 12.4. Compile and run

Requires JDK 17+, Maven, and Internet access on the first run to download dependencies. Inside the `propagation-isolation-lock-demo` directory:

```bash
mvn -q clean compile exec:java
```

Lines **printed by the program itself** in the expected order, ignoring Maven or Spring logs:

```text
reserve.active=true
afterReserve.qty=7 version=1
reserve.failure=insufficient stock
afterRejected.qty=7 version=1
optimistic.stale=false
optimistic.fresh=true
afterOptimistic.qty=6 version=2
outer.isolation=READ_COMMITTED
joined.isolation=READ_COMMITTED
new.isolation=SERIALIZABLE
outer.after.isolation=READ_COMMITTED
audit.count=1
```

### 12.5. Why does this output demonstrate all three axes?

**Propagation:** `inventory.reserve` runs a `REQUIRED` transaction; `audit.joined` is intercepted in T1 and joins physical T1 even though its annotation declares `SERIALIZABLE`; `audit.independent` starts T2 thanks to `REQUIRES_NEW` and uses its own transaction isolation.

**Isolation:** `outer` declares `READ_COMMITTED` for T1, so `joined.isolation=READ_COMMITTED`. The inner `REQUIRED` **does not upgrade** T1 to SERIALIZABLE. `REQUIRES_NEW` creates T2, so `new.isolation=SERIALIZABLE` when supported by H2/JDBC manager. When T2 finishes, outer resumes with T1's isolation context: `READ_COMMITTED`.

**Concurrency strategy:** `reserve(3)` decreases from 10 to 7 via an atomic SQL UPDATE with a predicate guard. `reserve(10)` updates no rows and throws a business exception; state remains 7. `reserveIfVersion(0,1)` is a stale version check (current version is 1) so it returns false. `reserveIfVersion(1,1)` updates the row, quantity drops to 6, and version increments to 2.

**Known limitation:** The demo runs sequentially, so it illustrates the correctness of conditional update and version predicate, but **does not prove throughput/lock waits under multiple threads**. To verify concurrency behavior, you must run integration tests with at least two transactions on different connections. The stdout lines above are inferred from the stated APIs and H2/Spring configuration; actual empirical output should be verified with Maven in an environment with a JDK.

### 12.6. Self-study experiments

**Experiment A — Enable `validateExistingTransaction=true` in the manager.** With outer T1 `READ_COMMITTED` calling `audit.joined` requesting `SERIALIZABLE`, the manager checks the mismatch. The call may throw `IllegalTransactionStateException` before entering the body of `joined`. This result shows that an inner isolation requirement does not automatically upgrade an existing physical T1.

**Experiment B — Change `audit.joined` from `REQUIRED` to `REQUIRES_NEW`.** When an outer T1 already exists, the method is allowed to create T2 with its own isolation. However, it is now **no longer in the same atomic unit** as outer and may require an extra connection; this is a change in semantics, not an unconditional mismatch fix.

**Experiment C — Remove `AND available >= ?` in `reserve`.** With amount=10 after available=7, it can update available to -3 because the guard was removed. `@Transactional(REQUIRED, isolation=READ_COMMITTED)` by itself does not enforce the non-negative inventory invariant.

**Experiment D — Remove the version predicate in `reserveIfVersion`.** A stale client no longer detects concurrent modifications; the update can overwrite another change. This also proves `@Transactional` is not synonymous with optimistic locking.

**Experiment E — Use a real concurrency test.** Have two threads borrow two JDBC connections, synchronize the read moment with `CountDownLatch`, and try updating the same row using the version predicate. Ensure the test has a timeout so it cannot hang; the exact outcome depends on DB locking/isolation, but **two writes using the same expected version must never both succeed** when `UPDATE ... WHERE version=?` is properly implemented on a single row.

## 13. Isolation differs from locking when REQUIRES_NEW is blocked

An antipattern in a service:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    jdbc.update(
        "UPDATE accounts SET balance = balance - 5 WHERE id = 1"
    ); // T1 holds row lock.

    auditService.writeNewTransaction(); // T2 accesses the same row.
}

@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void writeNewTransaction() {
    jdbc.update(
        "UPDATE accounts SET audited = TRUE WHERE id = 1"
    );
}
```

This is a **fragment**, and for the inner method to be intercepted it must reside on another bean injected via a Spring proxy. If T1 holds an exclusive lock on row `id=1`, T2 has a different connection and may block waiting for the lock. T2's `SERIALIZABLE` does not let it "pass through" T1's lock. T1 is suspended at the Spring layer and cannot commit before inner returns, so a lock timeout or resource-wait deadlock easily occurs.

Fixes must be based on the business requirement:

- Must the two updates be atomic together? Use a single `REQUIRED` physical transaction, considering the same set of locks.
- Must audit commit separately even if outer rolls back? Do not let inner touch data that outer has locked/not committed; write an independent event to a lock-unrelated table or design an appropriate outbox/saga.
- Is outer holding locks too long? Shorten the transaction; move HTTP/CPU work outside the boundary.
- Database deadlocks across multiple requests? Establish a consistent lock order, lock timeouts, and retry the entire transaction when the DB reports a retryable failure.
- Pool exhausted because inner needs a new connection? Size the pool for peak active outer/inner connections and factor in concurrency; do not merely raise `connectionTimeout`.

**Raising isolation does not replace changing lock topology**, and enlarging the pool does not make T1's row lock disappear.

## 14. JPA persistence context makes issues harder to observe

When using `JpaTransactionManager`, a transaction is typically bound to an `EntityManager`/persistence context. Unflushed entity changes, or changes that were flushed but **not yet committed**, are not necessarily visible to another transaction. If T2 of `REQUIRES_NEW` tries to read an entity just created by T1:

- T2 may not see the row.
- If touching a foreign key/index, T2 may wait or fail.
- If using a lock mode, lock acquisition belongs to T2's separate transaction/resource.
- When T2 commits and T1 resumes, T1's persistence context may still hold entities with stale data, requiring an appropriate refresh/clear strategy when business logic relies on the new data.

`Isolation.SERIALIZABLE` does not make two persistence contexts share uncommitted state. `REQUIRES_NEW` changes the physical transaction scope; it does not automatically synchronize caches between JPA contexts.

In JPA, `@Version` is usually convenient for optimistic locking. `@Lock(LockModeType.PESSIMISTIC_WRITE)` is appropriate when intentionally acquiring a DB lock. You must check provider/DB support, flush timing, and exception translation.

## 15. Locking strategies for common use cases

| Use case | Invariant / Contention | Usually appropriate transaction boundary | Reference isolation / locking strategy |
| --- | --- | --- | --- |
| Deduct stock for one product row | Non-negative, no oversell | `REQUIRED` for the whole order placement | Atomic `UPDATE ... WHERE available >= ?`, check affected rows; or row lock/`@Version` |
| Transfer money between two accounts | Total balance consistent; no half-committed transfer | One `REQUIRED` outer, helpers may be `MANDATORY` | Lock both accounts in the same order, update in the same transaction, constraints, and controlled retry |
| User edits form and saves minutes later | Do not overwrite another user's changes | A short transaction at save time | `@Version`/version predicate; report conflict and ask to merge |
| Worker claims an unprocessed job | No two workers receive the same job | Each claim in a short transaction | `FOR UPDATE SKIP LOCKED` if DB supports it, or atomic claim update; lease + idempotency |
| Book room/time without overlap | No overlap | `REQUIRED` for booking write | Unique/exclusion constraint, guard row, or serializable with retry; locking a single booking row may not suffice |
| Record audit for a failed attempt | Audit persists when outer rolls back | Consider a genuinely independent `REQUIRES_NEW` | Avoid locks/foreign keys to uncommitted outer, pool sizing, idempotency |
| Write event for a committed order | Event must not claim an order that rolled back | Outbox written in `REQUIRED` with the order | DB transaction + post-commit outbox publisher; avoid separate early-committing event |
| Aggregate report with multiple SELECTs | Need consistent snapshot across queries? | Appropriate read boundary | DBMS isolation/snapshot, avoid long locks; `readOnly` does not replace isolation |
| Update invariant across multiple rows | No write skew | `REQUIRED` for the whole use case | Serializable + retry, shared guard lock, or constraint/materialized invariant |
| Import allowing skipped error groups | Partial group rollback while overall job is atomic | `NESTED`/savepoint if supported | Outer isolation remains unchanged; savepoint is not a lock mode |

Note that "usually appropriate" is not a mandatory rule: for each DBMS, transaction manager, workload, and business policy, integration tests are needed to confirm the choice.

## 16. Process for choosing the right design: ask in order

### Step 1 — define invariants and data ownership

Explicitly write down which data **must commit/roll back together**, which data can be independent, and what **must never happen** under concurrent requests.

For example:

> "Two bookings for the same room in the same time range must never be confirmed; recording attempt history may persist even if the booking fails."

The first sentence is a concurrency invariant; the second is transaction independence. **Two solutions** may be required rather than a single annotation.

### Step 2 — choose the transaction owner and propagation

- Updates for one use case must be all-or-nothing: outer `REQUIRED`; helpers join, optionally `MANDATORY` to enforce a caller.
- Inner genuinely needs to commit independently: consider `REQUIRES_NEW`, verify data visibility and resource budget.
- Want partial rollback inside the same transaction: `NESTED` with savepoint when supported by the manager.
- Operation is valid without a transaction: consider `SUPPORTS` or `NOT_SUPPORTED` per contract, not to dodge errors.
- Forbid caller from having a transaction: `NEVER` expresses an architectural constraint.

Do not decide propagation based on the exception type that just appeared before understanding the root cause.

### Step 3 — choose consistency/isolation requirements

If a single atomic conditional update statement satisfies the invariant, an isolation level like `READ_COMMITTED` may suffice for that part; with multiple statements and cross-row invariants, examine snapshot semantics, locking, and serializable anomalies.

**Do not start with "set the entire application to SERIALIZABLE just to be safe."** Higher isolation has trade-offs in conflicts, serialization failures, lock contention, latency, and retries. Exact consequences depend on the DBMS.

### Step 4 — choose concurrency control

- Atomic SQL predicate/constraint for simple invariants.
- Optimistic version when conflicts are rare and stale clients should be detected.
- Pessimistic row locking when a "read, decide, write" sequence must be protected under high contention.
- Serializable + transaction-level retry for invariants difficult to guard with a single lock/constraint.
- Combine multiple mechanisms when business invariants require it: transaction + version + unique constraint.

### Step 5 — account for resources and deadlocks

When using pessimistic locks, limit physical transaction length, avoid HTTP inside transactions, and acquire locks in a consistent order. When using `REQUIRES_NEW`, check the connection pool because outer still holds resources; determine whether T2 needs rows T1 is locking.

### Step 6 — test failures, concurrency, and retries

Tests should not only run a single successful request. Cases should include:

- Two requests reading the same version and trying to write.
- Two requests concurrently deducting stock near 0.
- Two transactions updating rows in opposite order to verify deadlock handling.
- Inner `REQUIRES_NEW` reading a row that outer just inserted but has not committed.
- Outer `REQUIRED READ_COMMITTED` calling inner `REQUIRED SERIALIZABLE`.
- Testing `validateExistingTransaction=true` to detect mismatches.
- Checking data **after** physical commit/rollback using an independent query.

**If the test method itself is `@Transactional` in Spring TestContext**, it may wrap an outer transaction and roll back at the end of the test, altering the behavior of the code under test. Design test boundaries clearly and use `TestTransaction` when needed.

## 17. Lock duration, timeout, and retry: do not mix up errors

| Problem | Typical Symptom | Proper Handling |
| --- | --- | --- |
| Pool exhaustion | Waiting at `DataSource.getConnection()`/Hikari borrow; active=max; pending rising | Shorten outer scope, reduce nested REQUIRES_NEW, size pool for workload, backpressure |
| DB lock wait | Already has connection, but SQL is waiting for row/range lock | Inspect DB blocking sessions, reduce lock hold time, lock order, lock timeout, redesign T1/T2 |
| Deadlock | DB detects wait cycle and rolls back one transaction | Retry the **entire transaction** safely and idempotently, consistent lock order |
| Serialization failure | DB aborts a transaction to preserve SERIALIZABLE | Retry transaction from the start with bounded backoff, do not retry only a statement inside an aborted tx |
| Optimistic conflict | Version check updates 0 rows/`OptimisticLockException` | Reload/reconcile/retry per business rules, do not return fake success |
| Unique constraint violation | `UNIQUE`/constraint blocks duplicate | Return appropriate business error or use idempotent upsert with proper DB-specific semantics |
| Unexpected rollback | Participating scope marked shared tx rollback-only | Fix rollback handling/boundary; do not blindly change propagation |
| Isolation mismatch | Inner REQUIRED wants different isolation from outer | Fix transaction owner, use `validateExistingTransaction` to fail-fast if needed |

`@Transactional(timeout=...)` and DB statement/lock timeouts, pool connection timeouts, and HTTP request timeouts are limits at **different layers**. Do not raise the same number and assume lock waits are fixed. Timeouts prevent hanging indefinitely; invariants still need to be protected.

### Where to place retries

For optimistic conflicts or serialization failures, retry logic should be placed **outside the failed transaction** so each attempt creates a new transaction context. General flow example:

```text
retry attempt 1
   -> begin T1
   -> read/validate/update
   -> conflict/serialization failure
   -> rollback T1
retry attempt 2
   -> begin new T2
   -> re-read fresh state
   -> validate/update
   -> commit T2
```

Do not retry using the same `EntityManager` or `TransactionStatus` that is already rollback-only. Idempotency is required so repeating the operation does not execute external side effects twice.

## 18. Code review checklist

- [ ] Business invariants are explicitly stated: atomicity, uniqueness, stock, balance, booking overlap, snapshot consistency.
- [ ] Propagation is chosen by **transaction ownership and independent commit**, not to mask an existing bug.
- [ ] Inner `REQUIRED` joins outer on the proper manager/resource; do not assume declaring `isolation` on inner changes T1's isolation.
- [ ] If fail-fast mismatch detection is needed, `validateExistingTransaction` has been considered.
- [ ] `REQUIRES_NEW` has been evaluated for pool usage, row locks, foreign keys, uncommitted visibility, and commit independence.
- [ ] `NESTED` is only used when savepoints are supported, and not treated as an independent transaction.
- [ ] Isolation is chosen for the actual database in use, not solely from generic ANSI tables.
- [ ] For read-modify-write, an appropriate atomic predicate, optimistic version, or pessimistic lock is present.
- [ ] For multi-row invariants, write skew, unique/exclusion constraints, serializable transactions, and retries are checked.
- [ ] `@Version` is not inadvertently bypassed by bulk/native updates.
- [ ] Lock order is fixed to reduce deadlocks; transactions hold locks briefly.
- [ ] Do not assume `readOnly=true` forbids all writes or replaces concurrency control.
- [ ] Rollback rules match checked/unchecked exceptions and the transaction boundary is actually intercepted.
- [ ] Integration tests exist with multiple connections/threads and verify data after commit/rollback.
- [ ] Concurrency errors are retried with bounds on a **new transaction**, without continuing a failed transaction.

## 19. Self-check questions

**Question 1.** Do two methods both annotated `@Transactional(REQUIRED)` reliably prevent lost updates when two HTTP requests run concurrently?

No. Scopes in the same call stack can share a physical transaction, but each HTTP request usually has a separate transaction. Concurrent requests still need SQL guards, versions, locks, or appropriate isolation.

**Question 2.** Does an inner `@Transactional(REQUIRED, isolation=SERIALIZABLE)` called under an outer `READ_COMMITTED` automatically upgrade isolation to SERIALIZABLE?

Usually no. When joining an existing physical transaction, the outer isolation governs. You can enable `validateExistingTransaction=true` to report mismatches instead of silently ignoring the inner isolation setting.

**Question 3.** Does `REQUIRES_NEW` make T2 bypass locks held by the suspended T1?

No. T1 can still hold row locks and a connection; T2 is a separate transaction and must obey DB locking rules. If touching the same row, T2 may lock-wait or time out.

**Question 4.** Does `SERIALIZABLE` mean a transaction can never fail due to concurrency?

No. The DBMS may abort a transaction due to a serialization failure or deadlock to preserve a serializable outcome. The application must retry the entire transaction inside a new boundary when the error is retryable.

**Question 5.** Does a method using `@Version` need `@Transactional`?

Entity writes should be placed inside an appropriate transaction. `@Version` checks for stale data/optimistic conflicts, but does not choose commit boundaries or automatically create transactions for every call.

**Question 6.** How does `SELECT ... FOR UPDATE` differ from `@Transactional(isolation=REPEATABLE_READ)`?

`FOR UPDATE` requests a database lock per SQL/DB semantics on the selected rows; isolation is the data visibility level and anomaly guarantee for the physical transaction. A transaction can have a given isolation level without using explicit pessimistic row locks for SELECTs.

**Question 7.** When should you choose `NESTED` instead of `REQUIRES_NEW`?

When you need rollback-to-savepoint for the inner scope while staying in the same physical transaction, and the manager supports it. If inner data must commit independently and survive when outer rolls back, `NESTED` is insufficient.

**Question 8.** Why is `UPDATE inventory SET available=available-1 WHERE available>=1` better than "SELECT then UPDATE the computed value"?

A guarded SQL UPDATE is evaluated by the engine in a single statement, avoiding the gap between the application reading the quantity and writing a value based on a stale snapshot. You must still check affected rows and rely on SQL/DB correctness.

**Question 9.** If an invariant spans multiple rows and two transactions modify two different rows, does per-row `@Version` always prevent write skew?

No. The two transactions may not conflict on the same row version. You need a mechanism protecting the global invariant: an appropriate guard row/constraint or serializable + retry.

**Question 10.** Does `Isolation.DEFAULT` mean `READ_COMMITTED` in every DB?

No. It uses the database/resource's default isolation. Verify the DB/connection configuration; do not assume PostgreSQL's default applies to MySQL, H2, or other systems.

## 20. Conclusion

**Do not substitute these three layers for one another:**

1. **Propagation** determines the **scope/relationship of physical transactions**: join, split a new one, savepoint, or run outside.
2. **Isolation** determines **how a transaction sees and contends with concurrent data**; actual effective isolation must be verified on the DBMS and the boundary that opened the transaction.
3. **Locking / concurrency control strategies** determine how to **protect specific invariants** against concurrent writes: atomic SQL predicates, version checks, pessimistic locks, constraints, or serializable retry.

A sound architecture usually **chooses the transaction owner and propagation first**, sets isolation with justification, then selects suitable guards/locking per invariant, and finally verifies with concurrent integration tests. Do not expect a single annotation to solve all data consistency concerns on its own.

## Official References

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` sharing a physical transaction, independent `REQUIRES_NEW`, `NESTED` savepoints, and pool warnings.
2. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default propagation/isolation, isolation applying to new transactions, proxy/self-invocation, and attributes.
3. [Spring Framework — `Isolation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Isolation.html): `DEFAULT` and the four JDBC isolation levels.
4. [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `validateExistingTransaction` and propagation handling.
5. [Spring Framework — JDBC `JdbcTransactionManager`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): JDBC transaction manager and resource handling.
6. [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): `@Lock` and JPA lock modes on repository query methods.
7. [Jakarta Persistence — `Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic version metadata and conflict-detecting updates.
8. [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): ANSI anomalies, MVCC, and PostgreSQL differences for `READ_UNCOMMITTED`/`REPEATABLE_READ`/`SERIALIZABLE`.
9. [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks, deadlocks, and lock acquisition semantics.
10. [PostgreSQL — `SELECT`](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `NOWAIT`, and `SKIP LOCKED` under DB-specific SQL semantics.
