# Evaluating Correctness Before Lowering Isolation Levels

> **Topic:** Spring Framework — Transaction Management. **Group:** Locking and Concurrency. **Goal:** establish an evidence-based process to answer the question: *can a transaction's isolation level be lowered while still preserving every business invariant?* This lesson focuses on correctness, contention schedules, Spring `@Transactional`, locking, and atomic conditional updates, without equating good throughput numbers with valid data. The hands-on example uses Java 17, Spring Boot 3.5.7, Maven, Spring JDBC, and H2.

## 1. Why is lowering an isolation level a business change?

When multiple transactions read and write concurrently, each transaction can observe a different slice of system state. The *transaction isolation level* lets the database constrain which execution schedules are allowed. Lowering isolation can improve throughput, reduce lock waits, or lower snapshot maintenance costs, yet it can also permit schedules where **every transaction commits successfully while the overall state violates business rules**.

For example: a slot has **one** spot, yet two requests both run `SELECT COUNT(*) = 0` and create two bookings with different IDs. That is a business correctness failure, even with no dirty reads and no Java exceptions at all.

Before deciding to change `SERIALIZABLE` down to `READ_COMMITTED`, determine:

1. **Which invariants must always hold?** At most one booking per slot, non-negative stock, an idempotency key taking effect at most once, at least one staff member on duty, total debits equal total credits.
2. **At what point must the invariant hold?** After every database commit, after a multi-commit workflow, or temporarily relaxed within a contractually permitted eventual-consistency window?
3. **Which reads govern writes?** Especially `SELECT COUNT`, `EXISTS`, `SELECT balance` followed by `if(...) UPDATE/INSERT`.
4. **Can other transactions modify the same row, different rows tied to the same rule, or rows that do not yet exist?**
5. **Where does the current protection live?** Isolation, database constraints, locks, optimistic versions, atomic SQL updates, queues, or a transaction coordinator?
6. **Have worst-case schedules been tested on the real database?** Or only a single sequential request?

**Rule:** correctness of the **committed** state is the first acceptance criterion. Performance is evaluated only afterward.

## 2. Anomaly identification table at weaker isolation levels

| Phenomenon | Illustrative schedule | Why does it matter? |
| --- | --- | --- |
| **Dirty read** | A reads B's update **before B commits**, then B rolls back | A can make decisions based on data that was never committed. |
| **Non-repeatable read** | A SELECTs row X; B updates+commits; A re-SELECTs X and sees the new value | One transaction has two inconsistent observations of the same row. |
| **Phantom read** | A COUNTs by predicate; B INSERTs a matching row+commits; A re-COUNTs and sees more rows | Rules over row sets/ranges can shift mid-transaction. |
| **Lost update** | A/B both read an old value, then overwrite with values computed separately in Java | One update disappears from the final value. |
| **Write skew** | A/B both read an aggregate condition, yet each updates **different** rows | Two successful commits break a multi-row invariant. |
| **Serialization anomaly** | No serial execution order produces the same outcome as the committed transactions | Concurrent transactions can be "individually valid" yet "jointly wrong." |

### 2.1. Standard named isolation levels

| Isolation | Protection orientation | What to check before lowering |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Very weak; on supporting engines can allow dirty reads | Do not use for sensitive business decisions just to reduce blocking; some engines silently elevate behavior to READ_COMMITTED. |
| `READ_COMMITTED` | Prevents dirty reads from other transactions | Non-repeatable reads, phantom reads, check-then-act, and races can still occur. |
| `REPEATABLE_READ` | Prevents re-reading the same row and seeing newly committed values as a baseline guarantee | Does not promise serializability; snapshot isolation can suffer write skew. |
| `SERIALIZABLE` | Targets equivalence to a serial transaction execution order | Can produce serialization/deadlock conflicts; application must roll back and retry properly. |

This is a **conceptual** table, not a universal implementation guarantee across all DBs. PostgreSQL `REPEATABLE READ` also prevents phantom reads under the usual definition yet can still experience write skew; MySQL/InnoDB `REPEATABLE READ` has different gap/next-key locking; SQL Server `READ COMMITTED` has two distinct mechanisms depending on `READ_COMMITTED_SNAPSHOT` ON/OFF; Oracle maps JDBC levels differently. Always consult the exact DB version documentation before deciding.

### 2.2. Stable snapshots still do not guarantee serializability

Suppose a transaction reads a consistent snapshot throughout its lifetime. That keeps reads consistent **within the transaction**, yet two transactions can both read a snapshot showing "both doctors are on duty," and each takes a different doctor off duty. Because they update different rows, there is no direct write-write conflict; the final state leaves nobody on duty.

Thus **snapshot consistency ≠ serializable correctness**. When an invariant spans multiple rows or predicates, check **read/write dependencies** as well, not merely "does SELECT twice return the same result."

## 3. Turning invariants into verifiable conditions

A requirement stating "consistent data" is too vague for an acceptance test. Write exact conditions before changing isolation.

| ID | Invariant | Post-commit check |
| --- | --- | --- |
| B-01 | Each slot has at most one active booking | No slot has more than one `CONFIRMED` booking. |
| B-02 | Inventory is non-negative | `available >= 0` for every SKU. |
| B-03 | No double charge for the same request | Each `idempotency_key` produces at most one effective charge. |
| B-04 | Accounting journal balances | Total debits equal total credits per journal/currency per accounting rules. |
| B-05 | At least one doctor on duty per shift | Every shift retains at least one row with `on_duty=true`. |
| B-06 | Bookings do not exceed capacity | `confirmed_count(slot) <= capacity(slot)` on every commit. |

Also document the invariant's **scope**: one database, multiple schemas, multiple services, or external systems. `@Transactional` on one JDBC manager does not roll back HTTP payments or separate databases together.

### 3.1. "Safe at lower isolation" is a conditional conclusion

Isolation can be lowered if **every schedule permitted by the new level still preserves invariants** thanks to other mechanisms:

- `UNIQUE(slot_key)` genuinely expresses "at most one booking per slot."
- `CHECK(available >= 0)` plus atomic conditional DML prevents negative inventory.
- `version`/optimistic locking forces one of two stale writers to retry or fail.
- A representative row for the aggregate is locked before deciding.
- SERIALIZABLE is retained specifically for transactions with hard-to-guard multi-row invariants.

Never treat "we haven't seen bugs on staging yet" as sufficient proof if adversarial concurrent schedules were never reproduced.

## 4. Write skew scenario: both doctors leaving shift

Suppose:

```sql
CREATE TABLE on_call (
    doctor_id INT PRIMARY KEY,
    shift_id INT NOT NULL,
    on_duty BOOLEAN NOT NULL
);
INSERT INTO on_call VALUES (1, 99, TRUE), (2, 99, TRUE);
```

Rule: **every shift must have at least one doctor on duty**.

```text
T1 (A)                              T2 (B)
BEGIN                               BEGIN
SELECT COUNT(*) = 2
                                    SELECT COUNT(*) = 2
UPDATE doctor_id=1 SET on_duty=FALSE
                                    UPDATE doctor_id=2 SET on_duty=FALSE
COMMIT                              COMMIT

Result: COUNT(on_duty=true, shift=99) = 0.
```

The two transactions do not write to the same `doctor_id`. A `UNIQUE(doctor_id)` does not enforce "at least one doctor exists." This is **write skew**, classic proof of why multi-row invariants must be checked before substituting snapshot isolation for serializable.

Intentional solutions:

1. Keep `SERIALIZABLE` for leave-shift operations, retrying the **entire transaction** when the DB reports a serialization failure.
2. Create a `shift` row as a lock/coordination point, requiring **every** schedule-changing operation to lock that row before counting and updating.
3. Maintain a counter/version on the `shift` aggregate with an atomic conditional update, ensuring it never drops to 0 and all writers obey the protocol.
4. Build an engine-appropriate constraint/trigger that is genuinely concurrency-safe. A simple `CHECK` on each `doctor` row cannot enforce a multi-row condition on its own.
5. If all operations are serialized by shift key in an application queue, still define failover/replay and any write paths outside the queue.

**Insufficient:** merely adding `@Transactional` or setting `readOnly` on the counting step.

## 5. Check-then-insert scenario: two bookings for one spot

A slot `SLOT-A` has capacity=1. Two `READ_COMMITTED` transactions:

```text
T1: SELECT COUNT(*) WHERE slot_key='SLOT-A' -> 0
T2: SELECT COUNT(*) WHERE slot_key='SLOT-A' -> 0
T1: INSERT booking_id=1, slot_key='SLOT-A'
T2: INSERT booking_id=2, slot_key='SLOT-A'
T1: COMMIT
T2: COMMIT

Result: 2 bookings for 1 slot.
```

Here `PRIMARY KEY(booking_id)` does not conflict because IDs differ. `SELECT COUNT(*)` does not reserve exclusive rights to insert into an empty slot across all databases/isolations. Without a schema constraint matching the invariant, both transactions can commit.

For the rule **at most one booking per slot**, you can add:

```sql
CREATE TABLE bookings (
    booking_id INT PRIMARY KEY,
    slot_key VARCHAR(40) NOT NULL,
    CONSTRAINT uq_booking_slot UNIQUE (slot_key)
);
```

Now the DB **forbids** two committed rows from sharing the same `slot_key`. One attempt will be rejected on concurrency conflict even if both previously read `COUNT=0`. `UNIQUE` is the **correctness line independent of prior Java reads**.

**Important:** if a slot has capacity=5, `UNIQUE(slot_key)` would be wrong for business rules; use a capacity/counter design, locking, or a different constraint. If bookings have canceled/confirmed states, define "effective booking" precisely before choosing a filtered unique constraint/index.

## 6. Evaluation methodology: seven steps

### Step 1 — Inventory transaction boundaries

List all service methods, entry points, `@Transactional` annotations, propagation modes, `transactionManager`s, databases, pools, and callable APIs. Distinguish transactions **actually opened** from annotations merely present in source. In Spring proxy mode, beans instantiated with `new`, `private/final` methods, or `this.inner()` self-invocations may not be intercepted as expected.

### Step 2 — Map read sets and write sets

For each transaction:

- Which keys/rows, ranges, and predicates are read?
- Which read values drive write decisions?
- Which rows are inserted/updated/deleted?
- Can two requests update the same row? Can they update **two different rows** tied to the same invariant?
- Are there conditions on **nonexistent rows**, such as "no booking exists for this slot"?
- Are there other writers such as batch jobs, admin scripts, other services, or migrations?

Disjoint write sets **do not** prove safety: write skew is specifically when two transactions write to different rows while sharing a dependency on a read condition.

### Step 3 — Construct adversarial schedules

For every `SELECT → if → INSERT/UPDATE` pattern, create two transactions and force them to:

1. Both read the initial state.
2. Both pass the `if` check.
3. Both execute mutations on the same row, different rows, or a predicate range.
4. Both try committing, one failing, one rolling back, and one retrying.
5. Read data **after both finish** from a fresh connection/transaction.
6. Verify invariants, not just HTTP status/exceptions.

Use `CountDownLatch` or `CyclicBarrier` to reproduce races deterministically, rather than `Thread.sleep` hoping timing lines up.

### Step 4 — Identify protection mechanisms

For each invariant, select and prove **one** or more mechanisms:

- `UNIQUE`, `CHECK`, foreign keys, filtered/partial unique indexes.
- Atomic `UPDATE ... SET x=x+1 WHERE x<limit`, checking affected rows.
- `@Version`/optimistic locking, handling version conflicts.
- `SELECT FOR UPDATE`/row locking following a shared lock protocol.
- SERIALIZABLE with proper transaction-level retries.
- An aggregate row/counter, queue, or engine-appropriate advisory lock.

### Step 5 — Compare correctness at old vs. new levels

Run the exact same tests at both old and new isolation levels using the real database, driver, schema, indexes, and manager. If the new level permits invariant violations without a compensating mechanism, **do not approve**. If no bug surfaces, explain **why the constraint/atomic DML/lock** preserves correctness, rather than merely citing run counts.

### Step 6 — Benchmark after correctness passes

Keep workload, concurrency, connection pool, indexes, and dataset comparable. Measure p50/p95/p99, throughput of **valid transactions**, retry/deadlock/conflict rates, pool waits, lock waits, and version/undo pressure. If throughput rises while invalid bookings increase, the change failed.

### Step 7 — Canary and rollback plan

Roll out to clearly scoped endpoints/transactions; monitor business invariants; define rollout halt criteria. Reverting isolation back to a stronger level **does not auto-fix already-committed bad data**: reconciliation/compensation is required.

## 7. Ways to maintain correctness under READ_COMMITTED

### 7.1. Atomic updates avoid stale reads

Code vulnerable to lost updates:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void addPoints(long id, int delta) {
    int current = jdbc.queryForObject(
        "SELECT points FROM wallets WHERE id = ?",
        Integer.class, id
    );
    jdbc.update(
        "UPDATE wallets SET points = ? WHERE id = ?",
        current + delta, id
    );
}
```

This is a **snippet**, with `jdbc` being an injected `JdbcTemplate`. If two requests both read 100 and then write 110 and 120, one addition can be lost due to stale application values.

Better approach when simply adding points:

```java
int affected = jdbc.update(
    "UPDATE wallets SET points = points + ? WHERE id = ?",
    delta, id
);
if (affected != 1) {
    throw new IllegalStateException("Wallet not found");
}
```

SQL updates using the row value at DML execution time under the DB's concurrency control. For a single row, this is usually simpler than read-modify-write in Java; still check overflow, constraints, and driver/engine behavior.

### 7.2. Atomic conditional decrement and CHECK

```java
int updated = jdbc.update(
    "UPDATE stock " +
    "SET available = available - ? " +
    "WHERE sku = ? AND available >= ?",
    quantity, sku, quantity
);
if (updated != 1) {
    throw new IllegalStateException("Insufficient stock");
}
```

Snippet where `quantity` must be positive and `sku` validated. If both requests try to claim more than remaining stock, the DB evaluates the update condition on the row properly. Adding `CHECK (available >= 0)` provides an extra layer of defense. Index `sku` and check affected rows; never return success when `0` rows updated.

### 7.3. Optimistic locking with version

```sql
UPDATE wallet
SET balance = 110,
    version = version + 1
WHERE id = 42
  AND version = 7;
```

If another transaction already updated version from 7 to 8, the conditional UPDATE updates zero rows. Java must check the affected-row count:

```java
int count = jdbc.update(
    "UPDATE wallet SET balance=?, version=version+1 " +
    "WHERE id=? AND version=?",
    nextBalance, id, oldVersion
);
if (count == 0) {
    throw new IllegalStateException("Stale wallet version");
}
```

Snippet. With JPA, `@Version` mapping provides optimistic locking where supported by the provider; all writers must respect the version protocol. Retries must **read fresh state and re-run the entire decision**, not just resend the UPDATE with `oldVersion`.

### 7.4. Pessimistic locking on a representative row

For multi-spot capacity, you can maintain an always-existing `slot_capacity(id,capacity,used)` row and lock it before checking/deciding:

```sql
BEGIN;

SELECT capacity, used
FROM slot_capacity
WHERE id = 10
FOR UPDATE;

-- Only when used < capacity:
UPDATE slot_capacity
SET used = used + 1
WHERE id = 10;

INSERT INTO bookings(booking_id, slot_id)
VALUES (101, 10);

COMMIT;
```

This is a **scenario**; exact syntax/lock semantics vary by engine. Every writer must lock the **same row** before updating; if `SELECT FOR UPDATE` returns 0 rows, do not assume a gap was locked across all databases. On SQL Server, use properly designed lock hints instead of copying PostgreSQL's `FOR UPDATE`.

### 7.5. Serializable for multi-row invariants

When multi-row conditions are hard to express as constraints/aggregate locks, keeping `SERIALIZABLE` is easier to reason about. Serialization failures (e.g., PostgreSQL SQLSTATE `40001`) can occur and require bounded retries. Never swallow exceptions and return success, nor retry inside a transaction already marked rollback-only.

**No safeguard works if only one of several write paths follows it.** A batch import or admin script can break invariants if it bypasses locking/versioning protocols. Direct DB constraints help close this gap.

## 8. Spring Framework: where does the isolation level apply?

Example:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void placeOrder() {
    // When the call goes through the proxy and opens a new transaction,
    // the manager asks the database to use READ_COMMITTED.
}
```

**Technical notes:**

- `@Transactional` is metadata, not an MVCC/lock engine written in Java.
- Default propagation is `REQUIRED`. If no transaction exists, the method can open a new one with `READ_COMMITTED`. If inner `REQUIRED` joins an outer already opened as `SERIALIZABLE`, the **existing physical transaction's** isolation typically stays `SERIALIZABLE`.
- `REQUIRES_NEW` creates a new physical transaction that can apply its own isolation, yet alters commit/rollback boundaries and typically needs an extra JDBC connection; do not use it merely as a way to "lower isolation for inner" while ignoring side effects.
- `Isolation.DEFAULT` means the datasource/database default, not `READ_COMMITTED` on every engine.
- The bean must be Spring-managed and calls must go through the proxy in proxy mode; `this.method()` self-invocation bypasses inner advice.
- One transaction manager governs only its own resources; multiple datasources do not automatically yield distributed ACID.
- `readOnly=true` is only metadata/a hint and does not automatically provide a transaction-level consistent snapshot.

### 8.1. Inner annotation does not lower outer's level

```java
@Service
class OuterService {
    private final InnerService inner;
    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void outer() {
        inner.run();
    }
}

@Service
class InnerService {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void run() {
        // REQUIRED: joins the outer physical transaction.
    }
}
```

This is a **snippet**, needing `@Service` and transaction annotation imports. Under the same manager/resource, `run()` joins T1 rather than starting a new `READ_COMMITTED` transaction. If a benchmark only changes the inner annotation, it may **not have changed physical isolation at all**.

Some transaction managers have `setValidateExistingTransaction(true)` to **reject** isolation mismatches instead of silently joining. It does not change T1 into a different isolation.

### 8.2. Checking the actual JDBC connection

Inside a Spring-managed transaction, you can inspect:

```java
Connection c = DataSourceUtils.getConnection(dataSource);
try {
    int isolation = c.getTransactionIsolation();
    System.out.println("actual-jdbc-isolation=" + isolation);
} finally {
    DataSourceUtils.releaseConnection(c, dataSource);
}
```

Snippet; import `java.sql.Connection` and `org.springframework.jdbc.datasource.DataSourceUtils`, with `dataSource` being the manager's datasource. `Connection.TRANSACTION_READ_COMMITTED=2`, `TRANSACTION_REPEATABLE_READ=4`, `TRANSACTION_SERIALIZABLE=8`. Never manually commit/rollback/close a connection participating in a Spring transaction.

The JDBC isolation code **does not reflect every database option**: for SQL Server you must check `READ_COMMITTED_SNAPSHOT` ON/OFF; MySQL has session-level isolation and consistent-read behavior; replication routing also affects visibility.

## 9. Implementation differences across DBMSs

### PostgreSQL

- `READ COMMITTED` is usually default; each plain `SELECT` sees a snapshot as of that statement.
- `REPEATABLE READ` has a stable snapshot and prevents phantoms per PostgreSQL's implementation, yet can still suffer write skew/serialization anomalies.
- `SERIALIZABLE` uses Serializable Snapshot Isolation and can abort a transaction to prevent non-serializable outcomes; apps must retry the entire transaction on `40001`.
- `READ UNCOMMITTED` behaves like READ COMMITTED in PostgreSQL, not a dirty-read mode as the standard name implies.
- `UPDATE/DELETE/SELECT FOR UPDATE` acquire row locks and can re-evaluate conditions on newer row versions per engine rules, rather than behaving purely like plain SELECTs.

Docs: https://www.postgresql.org/docs/current/transaction-iso.html and https://www.postgresql.org/docs/current/applevel-consistency.html.

### MySQL / InnoDB

- InnoDB's default is typically `REPEATABLE READ`; consistent nonlocking SELECTs within a transaction use the read view established at the first consistent read.
- `READ COMMITTED` creates a fresh read view for each consistent read, with differences in gap/record locking for locking reads and DML.
- `SELECT ... FOR UPDATE` is not equivalent to a plain consistent SELECT, and range/next-key locking depends on indexes, predicates, and isolation.
- When lowering from RR to RC, check phantom inserts, `IF NOT EXISTS`, gap locks, batch jobs, and replication/binlog format requirements.

Docs: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html.

### Microsoft SQL Server

- `READ COMMITTED` with `READ_COMMITTED_SNAPSHOT=OFF` normally uses shared locks; when ON, it uses row-versioned statement-level snapshots for normal reads.
- RCSI differs from `SNAPSHOT` isolation (transaction-level snapshot). `REPEATABLE READ` uses stronger read locks yet lacks key-range locking like SERIALIZABLE.
- Lowering isolation can allow phantom/predicate races; toggling RCSI is a database option, not just a Spring annotation.
- `WITH (NOLOCK)` can cause dirty reads and must not be treated as a "safer and faster" tool.

Check RCSI:

```sql
SELECT name, is_read_committed_snapshot_on,
       snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
```

Docs: https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide.

### Oracle Database

Oracle supports `READ COMMITTED` with statement-level read consistency via SCN/undo, alongside `SERIALIZABLE` and read-only transaction modes. Never assume all four JDBC enum levels behave like PostgreSQL/MySQL. Under `SERIALIZABLE` contention, Oracle can raise `ORA-08177`. Queries under READ COMMITTED can observe different committed snapshots across statements.

Docs: https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html.

### H2

H2 supports `READ_COMMITTED` and can reproduce the `SELECT COUNT→INSERT` race. It suits learning transaction isolation and testing constraint mechanisms, yet does not replace locking/index/MVCC semantics of production databases. Before approving changes, run integration tests on the exact production DB/driver/version.

## 10. Runnable project: READ_COMMITTED + race + UNIQUE

**Goal:** run two concurrent transactions through the Spring proxy. Both read the booking count for `SLOT-A` as 0 and then both INSERT. The table without UNIQUE receives **two** bookings; the table with `UNIQUE(slot_key)` retains only **one** booking after commit. Do not use `Thread.sleep`; use `CyclicBarrier` to guarantee both transactions finish the pre-check before either INSERTs.

### Structure

```text
isolation-correctness-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/correctness/
    │   ├── CorrectnessApplication.java
    │   └── BookingService.java
    └── resources/application.properties
```

### 10.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>vn.example</groupId>
    <artifactId>isolation-correctness-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.2. src/main/resources/application.properties

```properties
spring.datasource.url=jdbc:h2:mem:isolation_correctness;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
```

Two threads require at least two physical JDBC connections. `DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive across connections in the same JVM.

### 10.3. src/main/java/vn/example/correctness/BookingService.java

```java
package vn.example.correctness;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
    private final JdbcTemplate jdbc;

    public BookingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void book(String caseName, int bookingId, CyclicBarrier gate) {
        String table = switch (caseName) {
            case "unsafe" -> "bookings_unsafe";
            case "safe" -> "bookings_safe";
            default -> throw new IllegalArgumentException("Unknown case");
        };

        int existing = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table + " WHERE slot_key = ?",
            Integer.class, "SLOT-A"
        );

        if (existing != 0) {
            throw new IllegalStateException("Slot already occupied");
        }

        try {
            gate.await(10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at barrier", e);
        } catch (BrokenBarrierException | TimeoutException e) {
            throw new IllegalStateException("Barrier failed", e);
        }

        jdbc.update(
            "INSERT INTO " + table +
            " (booking_id, slot_key) VALUES (?, ?)",
            bookingId, "SLOT-A"
        );
    }
}
```

**Explanation:**

- Only two fixed table names can be chosen in `switch`; never concatenate arbitrary SQL identifiers from input.
- A transaction starts when the caller invokes the public method on the Spring-managed proxy.
- Both transactions observe `COUNT=0` because `CyclicBarrier` sits **after SELECT, before INSERT**.
- `READ_COMMITTED` prevents dirty reads, yet does not make check-then-insert atomic.
- On the safe table, `UNIQUE(slot_key)` enforces the invariant at write/commit time regardless of both requests previously seeing the slot empty.
- Barrier errors are unchecked exceptions, ensuring the transaction rolls back if the test stalls or is interrupted.

### 10.4. src/main/java/vn/example/correctness/CorrectnessApplication.java

```java
package vn.example.correctness;

import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class CorrectnessApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrectnessApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner run(JdbcTemplate jdbc, BookingService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE bookings_unsafe (" +
                "booking_id INT PRIMARY KEY, " +
                "slot_key VARCHAR(40) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE bookings_safe (" +
                "booking_id INT PRIMARY KEY, " +
                "slot_key VARCHAR(40) NOT NULL, " +
                "CONSTRAINT uq_safe_slot UNIQUE(slot_key))"
            );

            int unsafe = race(jdbc, service, "unsafe", 1, 2);
            int safe = race(jdbc, service, "safe", 11, 12);

            System.out.println("without_constraint=" + unsafe);
            System.out.println("with_unique_constraint=" + safe);
        };
    }

    private static int race(
            JdbcTemplate jdbc, BookingService service,
            String caseName, int idA, int idB
    ) throws Exception {
        CyclicBarrier gate = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> a = pool.submit(
                () -> attempt(service, caseName, idA, gate)
            );
            Future<Boolean> b = pool.submit(
                () -> attempt(service, caseName, idB, gate)
            );

            boolean committedA = a.get(20, TimeUnit.SECONDS);
            boolean committedB = b.get(20, TimeUnit.SECONDS);

            String table = switch (caseName) {
                case "unsafe" -> "bookings_unsafe";
                case "safe" -> "bookings_safe";
                default -> throw new IllegalArgumentException("Unknown case");
            };
            int rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table +
                " WHERE slot_key = ?",
                Integer.class, "SLOT-A"
            );

            if ("unsafe".equals(caseName)) {
                if (!committedA || !committedB || rows != 2) {
                    throw new AssertionError("Unexpected unsafe result");
                }
            } else {
                if (committedA == committedB || rows != 1) {
                    throw new AssertionError("Unexpected safe result");
                }
            }
            return rows;
        } finally {
            pool.shutdownNow();
        }
    }

    private static boolean attempt(
            BookingService service, String caseName,
            int bookingId, CyclicBarrier gate
    ) {
        try {
            service.book(caseName, bookingId, gate);
            return true; // Proxy method returned after commit.
        } catch (DuplicateKeyException expected) {
            return false; // Database rejected the duplicate slot.
        }
    }
}
```

**Why is this example verifiable?**

1. Both tables and constraints are created **before** service transactions; no mid-transaction DDL muddies rollback measurement.
2. `@EnableTransactionManagement(proxyTargetClass = true)` with `@Service` and injection ensures the runner invokes `BookingService` through the Spring proxy.
3. The two executor threads have separate transaction contexts/DB connections; no imperative transaction is shared across threads.
4. `CyclicBarrier` forces both SELECTs to finish before INSERTs, creating an adversarial schedule.
5. Both booking IDs in each case differ, so the unsafe table only has an ID PK constraint, leaving the slot unprotected.
6. On the safe table, the unique index rejects one operation; the demo treats only `DuplicateKeyException` as expected. On a timeout, deadlock, or other exception, `Future.get` fails instead of printing a false pass.
7. `Future.get` waits for both service calls to finish; proxy calls return after commit/rollback. Counting in the runner observes **committed state**.

### 10.5. Run and stdout

Inside `isolation-correctness-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/isolation-correctness-demo-1.0.0.jar
```

With Java 17, Spring Boot 3.5.7, H2, and the config above, the two lines explicitly printed by the application are:

```text
without_constraint=2
with_unique_constraint=1
```

Spring Boot/HikariCP may emit additional startup logs. If a different DB/driver/isolation causes one transaction to wait or fail with a different lock error than expected, **do not** alter expectations to mask the failure; investigate, since the goal is understanding scheduling and safeguards, not forcing "green" output.

### 10.6. Limitations of the demo

The example proves only one invariant—"one booking per slot"—using `UNIQUE(slot_key)`. It does **not** prove:

- All multi-row invariants are solved by UNIQUE.
- H2 completely mirrors PostgreSQL/Oracle/MySQL/SQL Server.
- `READ_COMMITTED` yields higher throughput under every workload.
- Every concurrency failure is a duplicate key; deadlocks, lock timeouts, optimistic conflicts, and serialization failures can occur.
- A single H2 run suffices to approve a production migration.

If capacity > 1, a different schema and invariant are needed; if there is a `CANCELLED` status, "effective booking" must be defined and an appropriate constraint designed.

## 11. Testing properly on a production-like database

### 11.1. Schedule testing

With production-version PostgreSQL/MySQL/SQL Server/Oracle, use Testcontainers or staging:

1. Create baseline data and constraints matching production.
2. Open **two separate physical transactions** on different connections.
3. Synchronize after SELECT, before mutation; avoid uncontrolled `Thread.sleep`.
4. Test both committing, one rolling back, one timing out, and one transaction retrying.
5. Verify invariants after commit from a fresh connection.
6. Test updating the same row, two different rows, and a predicate range when no rows exist.
7. Verify `SET TRANSACTION`/`@Transactional` actually affects the new transaction's level rather than being masked by an outer `REQUIRED`.

### 11.2. Testing invariants, not just API status

For example, with bookings:

```sql
SELECT slot_key, COUNT(*) AS total
FROM bookings
GROUP BY slot_key
HAVING COUNT(*) > 1;
```

Any row returned indicates a slot violating the invariant **if the schema defines every row in the table as an effective booking**. If statuses exist, count only statuses participating in the constraint.

For inventory: `SELECT sku FROM stock WHERE available < 0`. For shifts: join against the `shift` table and on-call group so you do not miss a shift **with zero rows left**. For journals: sum debits/credits per currency and committed status. Never rely solely on request logs.

### 11.3. Stress tests and deterministic tests complement each other

Stress tests with thousands of requests uncover unknown races, yet "0 errors" across 100,000 requests does not prove a rare bad schedule cannot exist. Deterministic barrier tests deliberately force conflicts at exact business points; stress tests then measure behavior under realistic load.

### 11.4. Spring TestContext can skew assumptions

If a test method itself has `@Transactional`, Spring TestContext may start a **test-managed transaction** and roll back at the end of the test. `REQUIRED` services can join the test transaction instead of opening independent ones. That obscures boundaries, isolation, and committed state.

To test concurrent commits, prefer tests not wrapped by an outer test transaction, or manage test transactions intentionally. Count rows after both service calls have finished.

## 12. Retries, exceptions, and idempotency

**Under SERIALIZABLE** or when using optimistic locking, a valid transaction can be **rejected** to protect invariants. Applications must treat this as a concurrency-control outcome rather than assuming every failure is a bug.

Appropriate retry workflow:

```text
Begin new transaction
    -> read fresh state
    -> revalidate invariant/business rules
    -> attempt write
    -> commit
If known retryable conflict:
    -> rollback fully
    -> bounded backoff
    -> begin another NEW transaction
Else:
    -> report the business/infrastructure failure
```

Do not retry only the old `UPDATE` using a stale snapshot. Never reuse a transaction already marked rollback-only to retry.

In Spring, retry logic should sit **outside** the `@Transactional` boundary, or have an accurately configured and tested aspect order so each attempt genuinely receives a new transaction. Classify exceptions per transaction manager/driver: `CannotSerializeTransactionException`, `OptimisticLockingFailureException`, deadlock/lock timeout, or engine SQLSTATEs can surface differently.

### Idempotency outside the database

If an HTTP payment succeeded yet the local database transaction rolled back, retrying can double-charge. Even with `SERIALIZABLE`, `@Transactional` **does not** roll back remote side effects. Use idempotency keys, transactional outbox/sagas, or reconciliation design. Never pick an isolation level assuming every step in a distributed workflow shares one physical transaction.

## 13. Benchmarking after correctness passes

| Scope | Metrics to measure | Warning signs to investigate |
| --- | --- | --- |
| API performance | p50/p95/p99 latency; throughput of business-valid requests | p99 rises due to lock waits/retries even as median drops. |
| DB contention | Lock waits, deadlocks, serialization/optimistic conflicts | Changing level spikes or shifts conflict patterns unexpectedly. |
| JDBC pool | Active, idle, pending connections; acquisition latency | Long transactions or `REQUIRES_NEW` exhaust the pool. |
| MVCC | Undo/version store pressure; transaction age; cleanup lag | Transactions hold snapshots long or scan widely. |
| Correctness | Post-commit invariant violations, duplicate bookings, negative stock | **Any** violation must block rollout. |
| Retries | Attempts per success, exhausted retries, final error rate | SQL throughput rises while completed business operations fall. |

Keep dataset, concurrency, schema/indexes, DB/driver, pool, load distribution, and query patterns comparable across runs. Test read-heavy, write-heavy, and **hot key contention** workloads. Measure "valid business transactions completed per second" rather than merely "SQL statements per second."

## 14. Reducing blocking before lowering isolation

Before changing isolation, prioritize:

- Optimizing indexes and predicates to shrink scanned/locked rows and ranges.
- Shortening transactions: never hold connections/locks during HTTP calls or slow computations.
- Turning check-then-act into atomic conditional DML.
- Using constraints so the DB enforces invariants regardless of caller.
- Separating dashboard/report reads from write transactions while defining explicit eventual-consistency SLAs.
- Using representative rows/aggregate versions when invariants span multiple rows.
- Ensuring every writer follows the same lock ordering and protocol.
- Mitigating hot-row contention with suitable partitioning/queuing.
- Tuning pool/backpressure/retry policies after observing real bottlenecks.

If only certain reports tolerate seeing newer data between SELECTs, consider a lighter isolation **solely** on a dedicated read-only transaction for that path, rather than weakening sensitive money-transfer/booking operations. Keep in mind `readOnly=true` does not create a stable snapshot and is not a security boundary.

## 15. Deployment and rollback procedure

**Before changing**, document:

- Transaction boundaries, current isolation, DB/driver/manager, config value sources.
- Invariants and business owners.
- Tested concurrent schedules, all write paths, and protecting constraints/locks.
- Baseline correctness/performance results.
- Anomaly monitoring and data remediation plan if the change fails.

**During canary**:

1. Apply the new isolation to a clearly bounded scope; do not change the database global default without approval.
2. Verify transactions actually run at the intended isolation; do not rely only on source annotations.
3. Measure invariant violations, conflicts/retries, and latency.
4. Enforce rollout halt thresholds, config rollback, and reconciliation plans.
5. Record sufficient evidence for review/investigation.

**After rollback:** reverting to stronger isolation **does not automatically fix** duplicate bookings or corrupt ledger entries committed earlier. Reconciliation/compensation and consistency checks are required.

## 16. Common analysis pitfalls

| Wrong assumption | Correction |
| --- | --- |
| "READ_COMMITTED has no dirty reads, so data is always consistent." | Dirty read is only one phenomenon; non-repeatable, phantom, and read-check-write races remain. |
| "Two transactions updating two different rows is safe." | Write skew can break invariants spanning multiple rows. |
| "REPEATABLE_READ is always serializable." | No; engine-dependent, snapshot isolation permits write skew. |
| "Having @Transactional on the transaction is enough." | Must verify proxies, propagation, manager, and database constraints. |
| "Inner isolation=READ_COMMITTED definitely lowers outer." | Inner `REQUIRED` usually joins outer; physical transaction isolation does not change. |
| "SELECT FOR UPDATE returning no rows locks an empty slot." | Not guaranteed across all engines/isolations; use a representative row or tested unique/range-lock mechanism. |
| "Zero errors in a stress test means zero races." | Not hitting a bad schedule is not proof of safety. |
| "If an exception occurs, no transaction commits." | Exception propagation, rollback rules, and `REQUIRES_NEW` can leave committed side effects differently than expected. |
| "Reverting isolation fixes the data." | Does not fix committed corruption; reconciliation is needed. |
| "H2 behaves identically to the production DB." | H2 is for learning; lock/MVCC/index semantics differ from production engines. |

## 17. Decision checklist

- [ ] Business invariants and post-commit correctness scope are written as verifiable checks.
- [ ] Transaction boundaries, read sets, write sets, and all write paths are mapped.
- [ ] Same row, different rows, predicate ranges, and nonexistent-row cases have been tested.
- [ ] Dirty reads/non-repeatable reads/phantom reads, lost updates, and write skew were simulated where relevant.
- [ ] Engine/version specifics are understood: PostgreSQL, MySQL InnoDB, SQL Server RCSI, Oracle.
- [ ] **Effective** isolation was verified on new JDBC transactions and Spring propagation.
- [ ] Invariants are protected by constraints, atomic DML, optimistic versions, locking protocols, or SERIALIZABLE with retries.
- [ ] Tests exist with two real transactions/physical connections, barriers/latches, and committed-state assertions.
- [ ] Tested on the production DB/driver/schema, not just H2.
- [ ] Retryable exceptions are classified, bounded, and operations are idempotent.
- [ ] Metrics exist for throughput of **valid transactions**, p95/p99, lock waits, deadlocks, pool waits, and retry rates.
- [ ] Canary, business invariant monitoring, rollback plan, and committed-corruption remediation exist.
- [ ] Global isolation is not altered based solely on a single-threaded benchmark.

## 18. Self-check questions

**1.** Two `READ_COMMITTED` requests both read `COUNT=0` and INSERT two bookings with different IDs. Why can overbooking occur?

**Answer:** Because the check and the write are separate statements; both transactions can read the same valid state before either commits. Without a unique/atomic protocol, both writes succeed.

**2.** Does `UNIQUE(slot_key)` help when each slot has one spot?

**Answer:** Yes, if the true invariant is one committed row per `slot_key`. The DB rejects the second duplicate key; duplicates must be handled per business contract.

**3.** If capacity=5, is `UNIQUE(slot_key)` right?

**Answer:** No. You need a counter/atomic conditional update model or appropriate locking and constraints.

**4.** Why is the same snapshot in `REPEATABLE_READ` not enough to stop two doctors from both going off duty?

**Answer:** The two transactions update two different rows based on a shared condition; write skew can occur if the engine does not force one transaction to fail.

**5.** Why measure the actual JDBC isolation level instead of just checking the inner method annotation?

**Answer:** Because inner `REQUIRED` may be joining an outer transaction at a different level; the inner annotation does not reset isolation.

**6.** Should you retry a SQL `UPDATE` with the old `oldVersion` after an optimistic conflict?

**Answer:** No. You must start a new transaction, re-read data, re-check business rules, and only then write; with bounded retries.

**7.** Does 100,000 error-free runs prove there is no race?

**Answer:** No. You need deterministic concurrency schedules and reasoning about constraints/lock semantics; stress tests only provide supplemental evidence.

**8.** If an invalid booking has already committed, can rolling back the isolation config fix it?

**Answer:** No. Reconciliation/compensation and auditing of corrupted data are required.

## Official References

1. [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation and isolation when starting a new transaction.
2. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical scopes, `REQUIRED`, and `REQUIRES_NEW`.
3. [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): read committed, repeatable read, and serializable anomalies.
4. [PostgreSQL — Application-Level Data Consistency Checks](https://www.postgresql.org/docs/current/applevel-consistency.html): preserving invariants via serializable transactions or explicit locking.
5. [MySQL 8.4 — InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html): consistent reads, gap/next-key locks, and default level.
6. [Microsoft SQL Server — Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide): lock-based reads, RCSI, and serializable.
7. [Oracle — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): statement read consistency, serializable, SCN.
8. [H2 Database — Advanced](https://h2database.github.io/html/advanced.html): JDBC transaction isolation in the lab environment.

**Conclusion:** lowering an isolation level **widens the set of concurrent schedules permitted to commit**. Do so only when invariants are defined, races are reproduced, constraints/locks/atomic updates/optimistic versions or serializable alternatives are proven sound, and results are verified on the corresponding production database. **Correctness first — performance second.**
