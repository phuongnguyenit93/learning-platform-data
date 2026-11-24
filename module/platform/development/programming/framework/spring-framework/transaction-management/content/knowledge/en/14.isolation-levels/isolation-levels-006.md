# REPEATABLE_READ and MVCC implementation differences in Spring Transaction Management

## 1. Goal and short answer

In Spring Framework, you can request the **`Isolation.REPEATABLE_READ`** isolation level for a transaction. Its minimum meaning under the SQL isolation model is: when a transaction re-reads **the same row it already read**, it must not unexpectedly see a different version committed by a concurrent transaction. However, running that SQL statement on **PostgreSQL, MySQL/InnoDB, SQL Server, Oracle, or H2** can produce different behaviors regarding snapshots, phantom reads, locking reads, write conflicts, and resource overhead.

This Knowledge lesson explains:

- Dirty reads, non-repeatable reads, phantom reads, and serialization anomalies, especially the difference between **re-reading the same row** and **re-reading the same predicate result set**.
- **MVCC — Multi-Version Concurrency Control**: multiple row versions, transaction snapshots/read views, read-your-own-writes, old-version retention, and write conflict checks.
- Practical differences among PostgreSQL `REPEATABLE READ`, InnoDB `REPEATABLE READ`, SQL Server `REPEATABLE READ`, Oracle, and H2.
- Configuring `@Transactional(isolation = Isolation.REPEATABLE_READ)` in Spring and what the annotation does **not** guarantee.
- A runnable Java 17 + Spring JDBC + H2 demo to test read consistency with two separate transactions, plus exercises/SQL timelines to verify behavior on real databases.
- Common mistakes regarding write skew, read-modify-write, locking reads, JPA first-level cache, long-running transactions, and retry policies.

**Core rule:** an isolation level name describes **a set of guarantees and a request API**, not a single mandatory concurrency control algorithm across all databases. "REPEATABLE_READ" is **not synonymous** with "all behavior is always snapshot isolation," **not synonymous** with "no phantoms in every DBMS," and **not synonymous** with "serializable guarantee."

## 2. First: transactions and four types of anomalies

A **transaction** is a unit of DB work that is committed or rolled back. An isolation level defines how much concurrent transactions can observe or affect one another. Consider two transactions **T1** and **T2** running on two independent database connections.

| Phenomenon | Illustration | SQL minimum for REPEATABLE_READ |
|---|---|---|
| **Dirty read** | T1 reads a value T2 just wrote while T2 **has not committed**, then T2 rolls back | Must not occur |
| **Non-repeatable read** | T1 reads row A = 100; T2 updates A = 120 and commits; T1 re-reads row A and sees 120 | **Must not occur** |
| **Phantom read** | T1 runs `SELECT ... WHERE amount >= 100` returning 3 rows; T2 inserts a matching row and commits; T1 re-runs the query and sees 4 rows | **May be permitted** at REPEATABLE READ's minimum |
| **Serialization anomaly** | Multiple transactions commit successfully yet the combined outcome is not equivalent to any serial execution order | **Can occur** at REPEATABLE READ |

Here "permitted" **does not mean it must occur**. A database is allowed to provide stronger protection than the SQL minimum. This is why the same `REPEATABLE_READ` level prevents phantoms in PostgreSQL while not preventing phantoms in SQL Server/H2.

### 2.1. Non-repeatable read: same row, different value

```text
T1 (READ COMMITTED)                T2
---------------------------------  ----------------------------
BEGIN
SELECT balance WHERE id=1 -> 100
                                   BEGIN
                                   UPDATE balance=120 WHERE id=1
                                   COMMIT
SELECT balance WHERE id=1 -> 120
COMMIT
```

T1 reads the same row twice and gets different results because visibility/snapshot updated before the second read. In many databases, `REPEATABLE_READ` prevents this: it may read an older version via MVCC, or hold read locks to prevent T2 from updating until T1 completes.

### 2.2. Phantom read: same predicate, different set of rows

```text
T1                                   T2
-----------------------------------  ----------------------------
BEGIN
SELECT COUNT(*) FROM orders
WHERE amount >= 100 -> 3
                                     INSERT orders(amount=150)
                                     COMMIT
SELECT COUNT(*) FROM orders
WHERE amount >= 100 -> 4  (phantom)
COMMIT
```

The example above is **one possible schedule** at an isolation level allowing phantoms, not a fixed output across all databases. In PostgreSQL REPEATABLE READ, a single consistent snapshot prevents T1 from seeing rows newly committed by T2; in standard SQL Server REPEATABLE READ, shared locks on rows already read do not necessarily lock the entire **value range** to block new rows from appearing.

### 2.3. Serialization anomaly: stable reads yet broken business invariant

Suppose two doctors are on call; the business rule is **at least one doctor must remain on call**:

```text
doctors:
(Alice, on_call=true)
(Bob,   on_call=true)

T1                                T2
--------------------------------  --------------------------------
BEGIN REPEATABLE READ             BEGIN REPEATABLE READ
COUNT(on_call=true) -> 2          COUNT(on_call=true) -> 2
UPDATE Alice SET on_call=false    UPDATE Bob SET on_call=false
COMMIT                            COMMIT

Result: nobody is on call.
```

When two transactions update **two different rows** based on a shared snapshot, a system using snapshot isolation can let both commit: **write skew**. Each transaction reads a valid snapshot, yet the combined result violates the cross-row constraint. PostgreSQL REPEATABLE READ **can** encounter this case; `SERIALIZABLE` (with error handling/retry) or appropriate locks/constraints help protect the invariant. In lock-based databases, the execution schedule and outcome can differ.

**Takeaway:** seeing the same value across two SELECTs is **not enough** to conclude that multi-operation logic is serializable.

## 3. How does MVCC work?

**MVCC (Multi-Version Concurrency Control)** allows a database to retain multiple logical versions of a row so transactions read an appropriate snapshot. Implementations differ: for instance, PostgreSQL stores multiple tuple versions and applies visibility rules; InnoDB uses undo information/read views; SQL Server has row-versioning infrastructure and specific isolation options.

```text
Account row id=1:

Version V1: balance=100  -- committed before T1's snapshot
Version V2: balance=120  -- committed by T2 after T1's snapshot

T1 reads via old snapshot  ───────────> sees V1 (100)
T3 opens new snapshot      ───────────> can see V2 (120)
```

Properties to understand independently:

1. **Read view/snapshot:** the DB decides which transaction/statement sees which versions. A snapshot can be fixed **per statement** or **per transaction**, depending on engine and isolation.
2. **Read your own writes:** a transaction usually sees changes it just made itself, even if its snapshot references an earlier point in time. Thus "fixed snapshot" **does not mean** every SELECT returns immutable values regardless of T1's own UPDATEs.
3. **Visibility vs. locking:** a plain SELECT using a consistent snapshot may not lock the rows it reads; `UPDATE`/`DELETE`/`SELECT FOR UPDATE` statements have their own locking and version-selection logic.
4. **Garbage collection/version retention:** the DB cannot immediately clean up old records if an open transaction/snapshot might still need to read them. PostgreSQL has VACUUM/old tuples, InnoDB has undo/purge, and SQL Server has a version store. Very long read transactions can increase storage pressure.
5. **MVCC does not eliminate write locks:** concurrent transactions updating the same row still need locking/conflict mechanisms. Waiting, errors, and retries differ across engines.
6. **Isolation is not an application cache:** older data is served by DB visibility rules, not necessarily Hibernate's cache or Java objects held in RAM.

### 3.1. When is a snapshot created?

Saying "snapshot at BEGIN" is shorthand and **inaccurate for many engines**.

- **PostgreSQL REPEATABLE READ:** the snapshot is pinned when the transaction executes its first query or data-modifying statement, not necessarily at `BEGIN`. Subsequent statements read that same snapshot (plus the transaction's own changes).
- **InnoDB REPEATABLE READ:** for **consistent nonlocking SELECTs**, the read view is established on **the first consistent read** in the transaction, unless special syntax/conditions such as `START TRANSACTION WITH CONSISTENT SNAPSHOT` are used. Subsequent consistent reads use that read view.
- **MVCC-based READ COMMITTED:** typically chooses a new snapshot for each statement, so the same SELECT statement can return data T2 committed between two calls.
- **Standard SQL Server REPEATABLE READ:** primarily holds **shared locks** until the end of the transaction, rather than necessarily maintaining a transaction-wide MVCC snapshot.

Therefore, **the timing of the first SELECT and the type of SELECT** can determine experiment results, especially when comparing PostgreSQL with InnoDB.

## 4. Comparison table: one isolation name, multiple implementations

This summary table describes the primary behavior of common configurations and does not replace the documentation for your exact running version/engine.

| Database | How is `REPEATABLE READ` typically implemented? | Can two plain SELECTs see T2's committed update? | Phantoms in repeated ordinary queries | Key takeaway |
|---|---|---|---|---|
| **PostgreSQL** | Transaction snapshot/MVCC; implements snapshot isolation | No, after the snapshot is pinned | **No** for snapshot reads | Still allows serialization anomalies/write skew; some update conflicts error and require retry |
| **MySQL InnoDB** | Consistent nonlocking reads using a fixed read view from the first read | No for plain consistent SELECTs sharing the read view | Plain consistent SELECTs typically **do not see new phantoms** | Locking reads and DML see newer state using record/gap/next-key locks; do not naively mix semantics |
| **SQL Server** | `REPEATABLE READ` based on shared locks held until end of transaction | Not under normal semantics; T2 may have to wait | **Possible** because key ranges are not protected | `SNAPSHOT` is **a different isolation**; `RCSI` is a mode of READ COMMITTED |
| **Oracle Database** | Does not support a standalone level named `REPEATABLE READ` | No corresponding level for direct comparison | Use READ COMMITTED/SERIALIZABLE per requirements | Oracle uses MVCC; choices are READ COMMITTED, SERIALIZABLE, READ ONLY |
| **H2** | H2 MVCC engine; dedicated REPEATABLE READ level | Non-repeatable reads do not occur | **Phantoms** can occur | H2 has a separate `SNAPSHOT` level; H2 tests do not prove PostgreSQL's phantom policy |

**Do not conflate:** PostgreSQL REPEATABLE READ ≈ snapshot isolation in many practical respects, yet PostgreSQL REPEATABLE READ ≠ SQL Server REPEATABLE READ; InnoDB REPEATABLE READ has two different read models depending on statement type; H2 REPEATABLE READ differs from H2 SNAPSHOT.

## 5. PostgreSQL: stable snapshot, no phantoms, yet write skew remains

PostgreSQL defaults to **READ COMMITTED**. When switching to `REPEATABLE READ`:

1. Reads after the initial snapshot see the same set of changes committed before the snapshot, plus T1's own changes.
2. T2 can commit UPDATEs/INSERTs while T1 is reading its older snapshot; T1 does not see those changes in subsequent SELECTs.
3. PostgreSQL guarantees **no phantom reads** at REPEATABLE READ — stronger than the SQL standard table's minimum.
4. Concurrent transactions can still produce **serialization anomalies**, notably write skew across different rows.
5. If T1 tries to UPDATE/DELETE/lock a row modified by another transaction after T1's snapshot, PostgreSQL may wait and then report a **serialization failure** rather than updating based on the old version. You must roll back and retry **the entire transaction**, not just retry a single statement on a failed transaction.

### 5.1. Two-session PostgreSQL example

Assume the table already exists:

```sql
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);
INSERT INTO accounts(id, balance) VALUES (1, 100);
```

Run on two independent connections. *Session 1*:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM accounts WHERE id=1;  -- 100, establishes snapshot
-- While session 1 remains open, run session 2:
-- UPDATE accounts SET balance=120 WHERE id=1; COMMIT;
SELECT balance FROM accounts WHERE id=1;  -- still 100
COMMIT;
```

*Session 2*, executed between session 1's two SELECTs:

```sql
BEGIN;
UPDATE accounts SET balance=120 WHERE id=1;
COMMIT;
```

If session 1 only reads, PostgreSQL returns **100 then 100**; a subsequent new transaction will see 120. If session 1 attempts to UPDATE this row after session 2 commits, it can receive SQLSTATE **`40001`** with a serialization error; the application must retry from the transaction boundary.

### 5.2. Predicate phantom counterexample

Once T1's snapshot is pinned:

```sql
SELECT COUNT(*) FROM accounts WHERE balance >= 100;
```

T2 inserts a matching row and commits. When T1 re-runs the same query, it **does not** see the new row in its snapshot. That is "no phantoms" under PostgreSQL REPEATABLE READ, **not** a promise made by every database bearing the REPEATABLE READ label.

### 5.3. Why is SERIALIZABLE needed for multi-row invariants?

In the two-doctor problem, if both transactions read the old snapshot and UPDATE *different* rows, PostgreSQL REPEATABLE READ can let both commit, leaving nobody on call. PostgreSQL `SERIALIZABLE` uses Serializable Snapshot Isolation (SSI), detects non-serializable dependency chains, and rolls back one transaction with error `40001`; the application must retry the entire transaction.

Do not raise isolation to SERIALIZABLE blindly: know the invariant, conflict rate, retry/idempotency policy, transaction management cost, and throughput impact. A unique constraint, properly locked check logic, or data redesign is sometimes more appropriate.

## 6. MySQL InnoDB: consistent reads and locking/current reads are not the same

InnoDB defaults to **REPEATABLE READ** (in typical configurations). A common source of bugs is that **not every statement in the same transaction reads the same way**.

### 6.1. Consistent nonlocking SELECT

An ordinary `SELECT` (without `FOR UPDATE`/`FOR SHARE`) is normally a **consistent nonlocking read**. Under REPEATABLE READ:

- The first consistent read establishes the transaction's read view.
- Subsequent consistent reads reuse that read view and see data committed before the read view, plus T1's own changes.
- New rows committed by T2 after the read view **do not appear** in T1's plain consistent SELECTs — so phantoms of the "repeated SELECT sees new rows" variety normally do not appear here.

Under READ COMMITTED, InnoDB creates a fresh read view for **each consistent read**, so non-repeatable and phantom reads can occur.

**Surprising detail:** InnoDB lets a transaction see changes **it made itself**. Thus after an `UPDATE` by T1, a SELECT can combine newly modified versions of T1's rows with older versions of other rows; the combined view might not match any single external state of the database.

### 6.2. Locking reads, UPDATE, and DELETE

```sql
-- A plain consistent read:
SELECT balance FROM accounts WHERE id = 1;

-- A locking read:
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;

-- A DML statement:
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
```

These statements **do not share the same visibility/locking semantics**. `SELECT ... FOR UPDATE`, `FOR SHARE`, `UPDATE`, and `DELETE` use locking/current-read mechanisms operating on newer state and may have to wait for other transactions to finish. InnoDB uses **record locks**, **gap locks**, and **next-key locks** depending on the predicate and accessed index.

- A lookup via a unique index with a matching unique condition may lock only the record.
- Range scans/non-unique conditions may lock value gaps to block inserts into the range (next-key/gap locking), depending on query plan, index, and isolation.
- Missing a suitable index can widen lock scope and reduce throughput.
- Never conclude "plain SELECT is stable so UPDATE also touches only rows visible in the old snapshot."

**Surprising case documented by InnoDB:** T1's plain predicate SELECT does not see a new row inserted by T2 after the read view, yet executing `UPDATE ... WHERE same_predicate` in T1 can affect that new row via current/locking read semantics. After that UPDATE, a subsequent plain SELECT can even see the row just updated by T1 itself. This differs from how PostgreSQL REPEATABLE READ handles update conflicts on rows modified after the snapshot.

### 6.3. When are phantoms "prevented"?

Do not assert **"InnoDB REPEATABLE READ is completely phantom-free in every situation."** A more accurate statement:

- For **plain consistent reads** sharing the same read view, T1 does not see T2's new inserts.
- For **locking reads/range scans**, InnoDB can use next-key/gap locks to block inserts into the locked range, depending on index, condition, and statement.
- Mixing consistent SELECTs with locking SELECTs or DML can expose **different versions** between the two read styles, invalidating assumptions about a single "snapshot."

MySQL documentation advises against casually mixing locking statements with nonlocking SELECTs under REPEATABLE READ; if logic truly requires serializable schedules, consider SERIALIZABLE or explicit locking design.

## 7. SQL Server: REPEATABLE READ holds shared locks; SNAPSHOT is a separate level

SQL Server best illustrates why you cannot equate **REPEATABLE_READ = MVCC snapshot**.

In SQL Server, traditional `REPEATABLE READ` holds **shared read locks** on rows read until the end of the transaction, preventing other transactions from modifying those specific rows while T1 holds the locks. However, it **does not lock entire predicate ranges**, so another transaction can still insert new matching rows and cause **phantoms**.

```text
T1 REPEATABLE READ:
  SELECT ... WHERE id = 1     -- holds S lock on row id=1
  ...
T2 UPDATE id=1               -- may have to wait for T1 to finish

T2 INSERT id=99 within range:
  -- may succeed if not blocked by other locks

T1 SELECT COUNT(*) WHERE id > 50
  -- may encounter a phantom
```

SQL Server has row-versioning mechanisms, yet **the isolation option names differ**:

- **READ_COMMITTED_SNAPSHOT (RCSI)** is a **database-level** option causing `READ COMMITTED` to use **per-statement** snapshots; it **does not turn REPEATABLE READ into snapshot isolation**.
- **SNAPSHOT isolation** is **a separate isolation level** using row versions to provide transaction-level snapshots. `ALLOW_SNAPSHOT_ISOLATION` must be enabled on the database and SNAPSHOT selected appropriately at the session/transaction level.
- **SERIALIZABLE** uses range locks to protect predicates from phantoms under SQL Server semantics.

Check the edition/version/optimized-locking options and the actually configured transaction isolation rather than inferring from Java annotations.

**Limit of the Spring enum:** `Isolation.REPEATABLE_READ` maps to JDBC `TRANSACTION_REPEATABLE_READ`; it is **not synonymous** with enabling SQL Server `SNAPSHOT` (a SQL Server-specific level). Do not assume changing the enum to REPEATABLE_READ gives you transaction-wide row versioning in SQL Server.

## 8. Oracle and H2: two more reasons not to overgeneralize

### 8.1. Oracle Database

Oracle uses multiversion read consistency, yet **does not provide a standalone isolation level named REPEATABLE READ** among its supported levels like PostgreSQL/MySQL. Common modes include:

- **READ COMMITTED (default):** each query reads data committed as of the time the statement starts.
- **SERIALIZABLE:** transaction-level consistent view with conflict checking and errors when needed (e.g., `ORA-08177`); should not be equated directly with PostgreSQL's SSI mechanism.
- **READ ONLY transaction:** useful for a consistent snapshot across a series of read queries.

Therefore, `@Transactional(isolation = Isolation.REPEATABLE_READ)` may not be accepted by the Oracle driver/manager. Do not silently fall back to `SERIALIZABLE` without evaluating correctness, error/retry handling, and cost.

### 8.2. H2 in-memory

H2 provides `READ_COMMITTED`, `REPEATABLE_READ`, `SNAPSHOT`, `SERIALIZABLE` (and READ_UNCOMMITTED). Per H2 documentation:

- `REPEATABLE_READ` prevents dirty and non-repeatable reads, while **phantom reads can still occur**.
- `SNAPSHOT` prevents phantoms as well for read views per H2 semantics.
- H2's `SERIALIZABLE` level carries documented caveats regarding guaranteeing serial equivalence in transactions with writes.

Thus H2 is a good learning environment for observing **row re-reads** under isolation levels, but **not an accurate simulator of PostgreSQL/InnoDB/SQL Server** for phantoms, locking, conflicts, DDL, or performance. Run integration tests on your actual production database.

## 9. How does Spring Framework pass isolation to the database?

With Spring JDBC and a local transaction manager:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public Report readReport() {
    // JDBC/repository queries inside a Spring-managed transaction.
    // Snippet only: Report and repository are application-provided.
    return repository.loadReport();
}
```

The snippet above **does not compile standalone** since `Report` and `repository` are placeholders. When this method **starts a new physical transaction**, the Spring transaction manager can call JDBC `Connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ)` before SQL statements run. The JDBC driver/database then determines the actual semantics. Spring **does not implement MVCC in Java** and does not snapshot DB data itself.

### 9.1. Isolation only takes effect when truly opening a new transaction

This is a very common Spring design mistake:

```java
@Service
class OuterService {
    private final ReportService reports;

    OuterService(ReportService reports) {
        this.reports = reports;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        reports.readRepeatably();
    }
}

@Service
class ReportService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.REPEATABLE_READ
    )
    public void readRepeatably() {
        // Joins outer's READ_COMMITTED transaction.
        // REPEATABLE_READ on inner does not alter the physical transaction!
    }
}
```

These are **two illustrative classes** excluding imports/runner. With `REQUIRED`, if outer already has a transaction, inner **joins the outer transaction**; inner's isolation setting normally **does not replace** the already-open physical transaction's isolation. `AbstractPlatformTransactionManager.validateExistingTransaction` defaults to **false** (relatively lenient). If set to `true`, Spring can detect incompatible isolation/read-only requests when joining and reject them rather than ignoring them.

If you genuinely need a read transaction with its own isolation, consider **separating services and using `REQUIRES_NEW`** with its trade-offs: outer is suspended, inner acquires a separate connection/transaction, outer's locks/resources stay held, and commit/rollback divergence can occur. Never use `REQUIRES_NEW` merely to "work around" proper transaction boundary design.

### 9.2. Proxies and self-invocation

```java
@Service
class WrongService {
    public void report() {
        this.loadStableSnapshot();
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void loadStableSnapshot() {
        // Calling this.loadStableSnapshot() does not go through the proxy.
    }
}
```

This is an illustrative snippet: in Spring proxy mode, same-instance calls via `this` bypass the transaction interceptor. `@Transactional` may **fail to open a transaction**, so the isolation level is not applied. Prefer calling another service method through a Spring-managed proxy or using `TransactionTemplate` to declare boundaries explicitly.

### 9.3. `Isolation.DEFAULT` is not READ_COMMITTED

`Isolation.DEFAULT` means using **the database/connection's default level**, not a Spring default of READ_COMMITTED. Engines differ: PostgreSQL defaults to READ COMMITTED, InnoDB defaults to REPEATABLE READ, Oracle defaults to READ COMMITTED, H2 defaults to READ COMMITTED; SQL Server also has database options like RCSI. Do not guess what a DBA configured from the enum name.

### 9.4. Read-only does not automatically raise isolation

`@Transactional(readOnly = true)` can act as a hint/optimization or set read-only on the connection/session depending on manager/driver. It **does not create a stable snapshot, does not turn READ_COMMITTED into REPEATABLE_READ, and does not replace SERIALIZABLE**. Likewise, entities held in Hibernate's first-level cache do not prove the database is repeating queries under REPEATABLE_READ; inspect the actual SQL.

## 10. Runnable Java 17 demo: READ_COMMITTED sees update, REPEATABLE_READ does not

The experiment uses **Spring JDBC**, **TransactionTemplate**, and **H2**. To create two independent physical transactions in deterministic order without relying on thread timing, the code opens T1 and then uses `PROPAGATION_REQUIRES_NEW` to run T2 on a separate connection:

1. T1 reads `balance=100`.
2. T2 updates the same row to 125 and commits.
3. T1 reads the same row again before T1 commits.
4. Compare T1 under READ_COMMITTED vs. T1 under REPEATABLE_READ.

T1 **only reads**, avoiding holding a write lock on that row that would block T2's update. H2 allows non-repeatable reads at READ_COMMITTED and prevents them at REPEATABLE_READ, fitting the observation goal. The demo **does not claim** every DB produces phantoms identically to H2.

### 10.1. Project structure

```text
spring-repeatable-read-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── isolation/
                        └── Main.java
```

### 10.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-repeatable-read-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-jdbc` brings in Spring transaction infrastructure, and `h2` is the in-memory database. Spring 6.2.19 targets Java 17+ and is pinned for reproducibility; production projects should manage dependencies with a maintained and tested BOM/version.

### 10.3. `src/main/java/com/example/isolation/Main.java`

```java
package com.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static int readBalance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1",
            Integer.class
        );
    }

    private static void runCase(
            String name,
            int isolation,
            JdbcTemplate jdbc,
            JdbcTransactionManager manager) {

        // Reset between the two scenarios, outside the transactions being demonstrated.
        jdbc.update("UPDATE accounts SET balance = 100 WHERE id = 1");

        // T1 gets a physical transaction and the chosen isolation.
        TransactionTemplate outer = new TransactionTemplate(manager);
        outer.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
        outer.setIsolationLevel(isolation);

        // T2 has an independent transaction/connection, suspending T1 while it runs.
        TransactionTemplate writer = new TransactionTemplate(manager);
        writer.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );

        System.out.println("=== " + name + " ===");

        outer.executeWithoutResult(t1 -> {
            int first = readBalance(jdbc);
            System.out.println("T1 first=" + first);

            writer.executeWithoutResult(t2 -> {
                jdbc.update(
                    "UPDATE accounts SET balance = 125 WHERE id = 1"
                );
                System.out.println("T2 updated=125");
            }); // T2 commits, T1 is resumed.

            int second = readBalance(jdbc);
            System.out.println("T1 second=" + second);
        }); // T1 commits.

        System.out.println("after completion=" + readBalance(jdbc));
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
            "jdbc:h2:mem:repeatable_demo;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE accounts (" +
            "id INT PRIMARY KEY, " +
            "balance INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO accounts(id, balance) VALUES (1, 100)"
        );

        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        runCase(
            "READ_COMMITTED",
            TransactionDefinition.ISOLATION_READ_COMMITTED,
            jdbc,
            manager
        );

        runCase(
            "REPEATABLE_READ",
            TransactionDefinition.ISOLATION_REPEATABLE_READ,
            jdbc,
            manager
        );
    }
}
```

**Reading the code:**

- `runCase` uses a single `JdbcTransactionManager` and datasource; `JdbcTemplate` acquires the exact connection currently bound to each segment's transaction.
- `TransactionTemplate` sets the isolation of **a new physical transaction** without needing an AOP proxy. T1 is the outer transaction; T2 uses `PROPAGATION_REQUIRES_NEW` so it runs in a new physical transaction and then resumes T1.
- `DriverManagerDataSource` opens connections on demand and **is not a pool**; fine for a demo, whereas production should use a proper pool. Because T1 has not written or locked the row, T2 can update independently to observe read consistency.
- Each scenario resets balance to 100 **after the previous transaction finishes**. Never draw conclusions about a new transaction from leftover numbers of a prior run.
- `readBalance` runs direct JDBC SQL through the template, avoiding confusion with Hibernate's first-level cache.

### 10.4. Run and expected output

Install JDK 17+ and Maven. In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.isolation.Main
```

Lines printed by the program itself on H2 for this example:

```text
=== READ_COMMITTED ===
T1 first=100
T2 updated=125
T1 second=125
after completion=125
=== REPEATABLE_READ ===
T1 first=100
T2 updated=125
T1 second=100
after completion=125
```

**Explaining the difference:**

- Under `READ_COMMITTED`, T1's two SELECTs can see different snapshots. T2 committed before the second SELECT, so T1 sees 125.
- Under `REPEATABLE_READ`, T1 does not experience a non-repeatable read on the same row: both reads return 100. T2 **still committed successfully**; once T1 closes, a new transaction sees 125.
- That T1 still sees 100 **does not mean T2 failed to commit** or that the database rolled T2 back. It is **T1's visibility**.
- This output **only illustrates non-repeatable reads**; it does not prove phantoms or write skew are prevented in H2 or other DBs.

This demo code compiles with the declared dependencies; this describes expected behavior under H2 semantics, while actual execution requires JDK/Maven and downloaded libraries. On a different database, you may encounter blocking, update conflicts, SQL dialect differences, or different snapshot-pinning points: test against that database rather than tweaking expectations by ignoring exceptions.

## 11. Two SQL timelines to verify phantoms and read modes on real engines

### 11.1. PostgreSQL: two predicate counts on the same snapshot

Prepare data **before** opening T1:

```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    amount INTEGER NOT NULL
);
INSERT INTO invoices(id, amount)
VALUES (1, 120), (2, 90);
```

Connection T1:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM invoices WHERE amount >= 100; -- 1
-- Pause here for connection T2 to insert and COMMIT.
SELECT COUNT(*) FROM invoices WHERE amount >= 100; -- still 1
COMMIT;
```

Connection T2, run between T1's two queries:

```sql
BEGIN;
INSERT INTO invoices(id, amount) VALUES (3, 150);
COMMIT;
```

With no other data modifications and the exact schedule above, T1 in PostgreSQL RR still counts **1**. After T1 commits and a subsequent transaction reads, the count is **2**. Observing a stable snapshot does not mean a constraint prevented T2 from inserting; it simply means T1 does not see the new version.

### 11.2. InnoDB: distinguishing plain SELECT from SELECT FOR UPDATE

In an InnoDB transaction at `REPEATABLE READ`:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE id = 1;
-- T2 updates the same id=1 then COMMITs.
SELECT balance FROM accounts WHERE id = 1;
-- Plain consistent SELECT usually still sees the old snapshot version.

SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- Locking/current read; result cannot be inferred solely from the plain
-- SELECT's read view. Also depends on locks and concurrent changes.
COMMIT;
```

This is an **illustrative timeline to run on MySQL/InnoDB with an actual accounts table**, not a standalone program with a fixed output for `FOR UPDATE`. Rather than claiming a locking read "always sees 125," consider which transaction holds locks, commit timing, conditions/indexes, and whether the statement waits or hits a deadlock/timeout.

**Do not take results from H2 and assume they are PostgreSQL's or InnoDB's phantom policy.**

## 12. Limits that REPEATABLE_READ does not solve by itself

### 12.1. Write skew and multi-row invariants

To prevent two doctors from both leaving a shift, place the business invariant in a transaction capable of preventing serialization anomalies, or use appropriate constraints/locks. For example, PostgreSQL `SERIALIZABLE` can abort a transaction due to an invalid read/write dependency; the application must retry the whole transaction under a bounded policy.

Do not merely read COUNT and trust that RR guarantees "nobody else changed anything": a count stable within a snapshot **does not mean** other transactions cannot simultaneously make decisions on a similar snapshot.

### 12.2. Lost updates and optimistic locking

A problematic pattern:

```text
T1 reads balance=100
T2 reads balance=100
T1 computes 100+10 then UPDATEs balance=110
T2 computes 100+20 then UPDATEs balance=120
```

The final result may lose one update, though **whether it happens** depends on engine/isolation and how the UPDATE is written. PostgreSQL RR may raise a serialization failure when two transactions contend on the same row; SQL Server locking may block/deadlock; InnoDB has its own locking/current-read semantics. Never assert one universal outcome for every DB.

Common solutions to evaluate:

- Atomic updates in SQL `UPDATE accounts SET balance=balance+10 WHERE id=?` instead of unguarded read-compute-write.
- JPA/Hibernate `@Version` for optimistic locking where appropriate.
- `SELECT ... FOR UPDATE` / pessimistic locking with appropriate indexes and transaction boundaries.
- On serialization/deadlock/optimistic conflict errors, retry **the entire idempotent business unit**, without repeating irreversible side effects.

### 12.3. Long-running transactions and version retention

A reporting read running for minutes on an old snapshot can prevent the DB from reclaiming obsolete row versions, increasing undo/version storage, WAL/retention/cleanup pressure depending on the engine. Long transactions also hold connections and can hold locks if they perform writes/locking reads.

Shrink transaction scope, paginate with data-appropriate strategies, monitor transaction/snapshot age, timeouts, and pool usage. If you simply need a consistent report, consider an appropriate database snapshot/export/analytics mechanism instead of keeping an OLTP transaction open for too long.

### 12.4. Application caches can skew measurements

A second JPA `EntityManager.find(...)` call can return **the same Java instance** from the first-level cache without issuing a second SQL query. Reading "100, 100" then **does not prove** database isolation is REPEATABLE_READ. Conversely, a JPQL query may trigger a flush/DB hit or return data differently than expected.

To verify real isolation, use JDBC queries or design explicit JPA tests with deliberate flush/clear/refresh, checking SQL logs, connections, and transaction boundaries. Never call `clear()` indiscriminately in production just to "force correctness."

### 12.5. Multiple datasources or different threads

A local JDBC transaction binds a single datasource's connection to the **current thread**. Calling an async task or using another datasource/transaction manager means those SQL statements may **not share the same transaction/snapshot**. `@Transactional` on service A does not automatically open a distributed transaction across multiple databases.

Similarly, reactive transactions use the Reactor context and their own managers. Do not use `ThreadLocal` or imperative `TransactionSynchronizationManager.isActualTransactionActive()` to draw direct conclusions about reactive transactions.

## 13. Diagnostics: why does REPEATABLE_READ appear not to work?

| Observation | Possible cause | How to verify |
|---|---|---|
| Method has `@Transactional(REPEATABLE_READ)` yet queries still see new values | Self-invocation, method bypassed proxy; no transaction opened | Check calls go through Spring bean/proxy, check transaction manager logs |
| Inner declares RR while outer is READ_COMMITTED | `REQUIRED` joined the outer physical transaction | Check propagation/boundaries; inspect actual isolation; use strict validation if appropriate |
| Two JPA `find()` calls return identical values | First-level cache; two real SELECTs were not issued | Enable SQL logging or test with JDBC |
| Plain SELECT is stable yet UPDATE/locking SELECT sees newer state | InnoDB separates consistent reads from current/locking reads | Inspect SQL type, indexes, read view, and locks |
| Range query sees phantoms at RR | Valid on SQL Server/H2, as the SQL standard allows it | Check engine/isolation rather than assuming PostgreSQL behavior |
| Heavy blocking under RR | Lock-based implementation or queries using locking reads | Inspect wait events, locks, transaction duration, and query plan |
| RR throws serialization failure | PostgreSQL/engine detected an update conflict | Roll back and retry transaction from start (with backoff/idempotency) |
| Spring reports unsupported isolation | Database/driver lacks the requested isolation (e.g., Oracle RR) | Check JDBC/transaction manager capabilities; choose suitable strategy |
| READ_COMMITTED yet queries stay stable across reads | T2 hasn't committed; cache hit; no data changed; test synchronization bug | Use two physical transactions and explicit barrier/timeline |
| `Isolation.DEFAULT` assumed to equal READ_COMMITTED | DB defaults differ and can be configured by administrators | Check `Connection.getTransactionIsolation()` and server/session settings |

### 13.1. Checking JDBC isolation directly inside a transaction

With JDBC, use a connection obtained through a **Spring-aware API** so you do not accidentally inspect a brand-new connection outside the transaction:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;
import java.sql.Connection;

public static int currentJdbcIsolation(DataSource ds) {
    Connection conn = DataSourceUtils.getConnection(ds);
    try {
        return conn.getTransactionIsolation();
    } catch (java.sql.SQLException ex) {
        throw new IllegalStateException("Cannot inspect isolation", ex);
    } finally {
        DataSourceUtils.releaseConnection(conn, ds);
    }
}
```

This is an **illustrative utility method**, requiring a valid `DataSource` and invocation inside an active transaction. `Connection.getTransactionIsolation()` reports **the current JDBC level**, which cannot by itself prove whether the engine uses PostgreSQL-like snapshots or SQL Server locking. `DataSourceUtils.releaseConnection()` will not prematurely close a connection properly bound to a Spring transaction.

Additional inspection SQL (dialect-specific):

```sql
-- PostgreSQL
SHOW transaction_isolation;

-- MySQL/InnoDB
SELECT @@transaction_isolation;

-- SQL Server: current level can be checked with DBCC USEROPTIONS
DBCC USEROPTIONS;
```

These statements apply only to their respective DBMSs; do not copy them to H2/Oracle without adjusting dialects. Check state **inside** the method intercepted by Spring, not solely at application startup.

### 13.2. Testing concurrent transactions properly

A good test uses **two physical transactions/connections** with synchronization points enforcing the schedule:

1. T1 opens with the isolation level under test.
2. T1 executes its **first SELECT**, pinning the snapshot if the engine does so.
3. T2 opens, UPDATEs or INSERTs an independent row, and **COMMITs before** T1 reads the second time.
4. T1 repeats **the same SELECT** or **the same predicate** and records the result.
5. T1 finishes; open a new T3 to verify the committed state in the DB.
6. Also test locking reads, UPDATE conflicts, write skew, rollback/retry, and lock/wait metrics on a **compatible production-like DB**.

Never use `Thread.sleep(...)` as an ordering guarantee; if using multiple threads, synchronize with `CountDownLatch`/barriers, cap timeouts, and ensure `finally` cleanup. Section 10's demo uses `REQUIRES_NEW` to create a synchronous T2 in a separate physical transaction to avoid unstable timing; on a lock-based DB, that exact T1-read → T2-update schedule may block, which is an important result to observe rather than forcing H2-like output.

## 14. Choosing an isolation level for business requirements

**When a reporting flow needs consistent reads:** REPEATABLE_READ on an MVCC engine supporting transaction snapshots can help. However, for reports spanning multiple tables and predicates, understand the engine's guarantees and consider READ ONLY/SNAPSHOT/analytics transactions.

**When multi-row invariants must hold:** a stable snapshot may not be enough (write skew). Use SERIALIZABLE with retries, or appropriate constraints/locking, backed by concurrent tests.

**Under high-contention read-write workloads:** REPEATABLE_READ is not automatically faster than READ_COMMITTED. Snapshot/version retention, row/gap locks, update conflicts, and retries can reduce throughput. Measure on representative queries, indexes, and load.

**When code runs across multiple databases:** do not rely on the enum name assuming uniform semantics. Encode isolation assumptions in per-database integration tests. When migrating PostgreSQL ↔ MySQL ↔ SQL Server ↔ Oracle, review all assumptions about phantoms, locking reads, retries, and snapshot timing.

## 15. Self-check questions

1. **Does REPEATABLE_READ guarantee no phantoms on every DB?** — No. SQL allows phantoms as a minimum; PostgreSQL prevents phantoms, while SQL Server/H2 can allow them.
2. **Is PostgreSQL REPEATABLE READ equivalent to SERIALIZABLE?** — No. Write skew/serialization anomalies can still occur.
3. **Where do two plain SELECTs in the same InnoDB RR transaction get their snapshot?** — Normally from the read view of the first consistent read.
4. **Does `SELECT ... FOR UPDATE` in InnoDB have the same visibility as a plain SELECT?** — Not necessarily; it is a locking/current read with its own locking rules.
5. **Does SQL Server REPEATABLE READ automatically enable SNAPSHOT isolation?** — No. SNAPSHOT is a separate isolation level, and RCSI is an option for READ COMMITTED.
6. **Does `@Transactional(isolation = REPEATABLE_READ)` on an inner REQUIRED method upgrade an outer READ_COMMITTED transaction?** — Typically no, because inner joins the outer physical transaction.
7. **Why do two `EntityManager.find()` calls returning the same data not prove RR?** — Both reads may have been served from the first-level cache.
8. **If a PostgreSQL RR transaction gets SQLSTATE 40001, what should be retried?** — Roll back and retry **the entire transaction**, with bounds/idempotency, not just a single SQL statement on the failed transaction.
9. **Why can holding a snapshot transaction open too long consume resources?** — The database must retain older row versions/undo/history along with associated connections/locks for older readers.
10. **Does `Isolation.DEFAULT` in Spring default to READ_COMMITTED?** — No; it uses the database/connection's default, which varies across engines.

## Official references

- PostgreSQL — Transaction Isolation (REPEATABLE READ and snapshot isolation, phantoms, serialization anomalies): https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — `SET TRANSACTION` and when isolation takes effect: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
- MySQL 8.4 — Locking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- SQL Server — Transaction Locking and Row Versioning Guide: https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide
- Oracle Database — Data Concurrency and Consistency: https://docs.oracle.com/en/database/oracle/oracle-database/18/cncpt/data-concurrency-and-consistency.html
- H2 Database — Transaction Isolation and MVCC: https://h2database.github.io/html/advanced.html#transaction_isolation
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `AbstractPlatformTransactionManager` and `validateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — `JdbcTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
