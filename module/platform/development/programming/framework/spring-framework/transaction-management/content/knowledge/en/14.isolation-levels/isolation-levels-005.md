# READ_COMMITTED and data snapshots across database systems

> **Module:** Spring Framework — Transaction Management. **Parent topic:** Isolation levels. This lesson focuses on how `READ_COMMITTED` controls visible data and the difference between **statement-level MVCC snapshots** and **lock-based reads** in PostgreSQL, Oracle Database, MySQL/InnoDB, Microsoft SQL Server, and H2. The Spring section covers `@Transactional(isolation = Isolation.READ_COMMITTED)`, transaction boundaries, datasource/drivers, and a runnable Java 17 project demonstrating non-repeatable reads.

## 1. What does READ_COMMITTED guarantee?

**READ_COMMITTED** is a transaction isolation level in JDBC and SQL. Its core promise: a read at this level **does not retrieve uncommitted changes being modified by another transaction** (*dirty read*). However, between **two SQL statements** of the same transaction, another transaction can commit changes. Therefore, re-reading the same row may return a new value (*non-repeatable read*), and repeating a predicate query may encounter new rows (*phantom read*).

Key distinctions to keep clear:

- **Isolation level** describes which read/write phenomena are permitted or prevented by the database's contract.
- **Read view / snapshot** describes how a specific database determines which data versions a statement sees.
- **MVCC** (Multi-Version Concurrency Control) is the technique of keeping multiple record versions to support consistent reads without always forcing readers to wait for writers.
- **Locks** are mechanisms for controlling concurrent reads/writes via resource locking, which can make readers wait for writers or vice versa.

**Do not equate "READ_COMMITTED" with "the entire transaction uses one fixed snapshot."** In PostgreSQL, Oracle, and MySQL/InnoDB consistent reads at READ COMMITTED, separate reads typically create/receive **a new snapshot per statement/consistent read**. SQL Server even has **two READ COMMITTED implementations** depending on the `READ_COMMITTED_SNAPSHOT` database option.

## 2. Two-session model: transactions A and B

Suppose a table holds a balance:

```sql
CREATE TABLE account_balance (
    id INT PRIMARY KEY,
    balance INT NOT NULL
);

INSERT INTO account_balance (id, balance)
VALUES (1, 100);
```

A controlled schedule:

```text
Time            Transaction A (READ COMMITTED)          Transaction B
---------------------------------------------------------------------------
t0              BEGIN
t1              SELECT balance WHERE id=1 -> 100
t2                                                       BEGIN
t3                                                       UPDATE -> 150
t4                                                       not COMMITTED yet
t5              Cannot read uncommitted value 150
                (may see 100 or have to wait,
                 depending on DB/read type)
t6                                                       COMMIT
t7              SELECT balance WHERE id=1 -> 150
t8              COMMIT
```

Both `SELECT`s by A happen **inside the same transaction A**, yet the first returns `100` and the second returns `150`. There is no dirty read: the new value is seen **only after B committed**.

The `100 → 150` change is a **non-repeatable read**. `READ_COMMITTED` permits this phenomenon. It does not mean A "read wrong data": A is reading **two different committed states** at two points in time.

### A note on timing

In a database with statement-level snapshots such as PostgreSQL, if B commits **after a long-running SELECT has already started**, that SELECT continues to see the state matching the snapshot at the moment the statement began (plus A's own changes). **The next SELECT** after B commits can see the new version. Do not interpret "READ_COMMITTED" to mean a running SELECT scan will switch rows mid-scan to newer versions.

With **SQL Server READ COMMITTED using shared locks**, you cannot assume every SELECT has a point-in-time consistent snapshot across the statement. The corresponding section explains the exact difference.

## 3. Dirty read, non-repeatable read, and phantom read

| Phenomenon | Practical definition | READ_COMMITTED |
| --- | --- | --- |
| **Dirty read** | A reads a value written by B while B **has not committed**; B may roll back | **Prevented** in normal operation |
| **Non-repeatable read** | A reads the same row twice; B commits a change in between | **Possible** |
| **Phantom read** | A re-runs a predicate query; B commits INSERT/DELETE/UPDATE changing the result set | **Possible** |
| **Transaction-wide consistent snapshot** | All ordinary SELECTs of A see the same state at one point in A's lifetime | **Not guaranteed by READ_COMMITTED** |
| **Serialization** | Outcome is equivalent to running transactions sequentially in a valid order | **Not guaranteed by READ_COMMITTED** |

Phantom read illustration:

```sql
-- Transaction A, read 1
SELECT COUNT(*) FROM orders WHERE status = 'NEW';
-- 2

-- Transaction B adds a NEW order then COMMITs.

-- Transaction A, read 2
SELECT COUNT(*) FROM orders WHERE status = 'NEW';
-- 3
```

The statements above represent **a two-session scenario**, not a script run sequentially in one session. `READ_COMMITTED` allows A to see the count change. In practice, figures also depend on query execution, locking hints, commit timing, and the transaction manager.

### Why does this matter for a Java service?

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void processReport() {
    int countBefore = repository.countOpenOrders();
    // Another service can commit a change at this moment.
    int countAfter = repository.countOpenOrders();
}
```

This is an **excerpt** (the repository is application-defined). `countBefore != countAfter` is not a Spring bug. Isolation is enforced by the database for queries; the annotation **does not turn two SELECT statements into a single fixed snapshot for the entire method**.

## 4. What does "statement-level snapshot" mean?

A **statement-level snapshot** can be understood as a *read view* established for **a single SQL statement**, reflecting transactions committed before that snapshot point (plus relevant changes made by the current transaction itself). When executing another SQL statement under READ COMMITTED, the database can issue a **new snapshot**.

```text
Transaction A:  BEGIN ------------------------------------------------ COMMIT
                  | SELECT #1 |                | SELECT #2 |
Snapshot A1:       ^ data at S1                  ^
Transaction B:              UPDATE ---- COMMIT
Snapshot A2:                                  ^ data at S2

S1: id=1 -> 100
S2: id=1 -> 150
```

With an MVCC implementation, the database retains enough version information to **reconstruct** the snapshot's data. A running SQL statement can avoid reading "half before / half after" across multiple concurrent commits. This is **statement-level read consistency**, weaker than a transaction-level snapshot.

Keep three exceptions/limits in mind when speaking generally across DBMSs:

1. **Locking reads and DML** (`SELECT ... FOR UPDATE`, `UPDATE`, `DELETE`) do not necessarily follow the same versioning rules as plain consistent `SELECT`. They must resolve update conflicts against current row state.
2. **Read your own writes**: a transaction generally sees rows it just INSERTed/UPDATEd even before committing, even though the statement snapshot only shows committed data from other transactions.
3. **Lock-based READ COMMITTED** in SQL Server is not a statement-level snapshot; it prevents dirty reads with shared locks, yet changes can occur during a scan.

Therefore, "READ_COMMITTED always snapshots per statement" is accurate only if **the engine and read type are explicitly specified**.

## 5. PostgreSQL: a new snapshot at the start of each statement

In PostgreSQL, `READ COMMITTED` is the default isolation level for ordinary transactions. PostgreSQL 18 documentation states that a plain `SELECT` at this level sees only data committed by other transactions **before the SELECT began**. Each new statement can receive a new snapshot.

Example using two `psql` windows.

### 5.1. One-time setup

```sql
DROP TABLE IF EXISTS account_balance;
CREATE TABLE account_balance (
    id INT PRIMARY KEY,
    balance INT NOT NULL
);
INSERT INTO account_balance(id, balance) VALUES (1, 100);
```

This is a learning example on a dedicated database. Do not run `DROP TABLE` on a schema containing real data.

### 5.2. Session A

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_balance
WHERE id = 1;
-- 100

-- Pause here, switch to session B to UPDATE and COMMIT.

SELECT balance
FROM account_balance
WHERE id = 1;
-- 150

COMMIT;
```

### 5.3. Session B

After A finishes its first SELECT:

```sql
BEGIN;
UPDATE account_balance
SET balance = 150
WHERE id = 1;
COMMIT;
```

**Key point:** transaction A has not ended, yet A's second SELECT receives a new statement snapshot and sees B's commit.

### 5.4. Effect on UPDATE and SELECT FOR UPDATE

PostgreSQL has **more nuanced concurrent-update rules** than plain SELECT. An `UPDATE`/`DELETE`/`SELECT FOR UPDATE` may wait for a transaction that already modified the row to finish, and then **re-evaluate its condition** against the new row version if that transaction commits. Thus you cannot take the "snapshot at statement start" rule of plain `SELECT` and assume all DML only affects data visible in that initial snapshot.

For example:

```sql
UPDATE account_balance
SET balance = balance + 10
WHERE id = 1;
```

When concurrent updates hit the same row, PostgreSQL coordinates row locks and reprocesses for consistency. An in-SQL addition against the current value differs in safety from the pattern of "reading the value into Java and overwriting balance with a constant" across competing transactions.

**Sources:** [PostgreSQL 18 — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html) and [SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html).

## 6. Oracle Database: statement-level read consistency based on SCN/undo

Oracle Database uses **multiversion read consistency**. Under `READ COMMITTED`, Oracle determines a consistency point tied to an **SCN** (*System Change Number*) when the SQL statement is opened/started. If the database already contains newer changes past that point, Oracle uses **undo** to reconstruct the appropriate version for the SELECT.

```text
SELECT A opens at SCN=1000
  -> reads committed state as of SCN 1000
Another transaction commits at SCN=1001
  -> already-open SELECT A does not "jump" to 1001
SELECT B opens later at SCN=1002
  -> can see changes committed at 1001
```

Because each SQL statement typically has its own point in time under READ COMMITTED:

- **Dirty reads do not occur** in normal queries: A does not see B's uncommitted changes.
- **Non-repeatable reads can occur** between two SELECT statements.
- **Phantoms can occur** between two executions of a predicate query.
- A long-running SELECT may need older undo to preserve read consistency; undo-resource errors can occur if required versions are no longer retained.

### Oracle does not equate SERIALIZABLE with READ COMMITTED

In `SERIALIZABLE` mode or an eligible read-only transaction, Oracle uses a **transaction-level** snapshot instead of giving every SELECT a new read view as in READ COMMITTED. Never compare solely by isolation level name while ignoring each engine's implementation traits.

### Usage guidance on Oracle

- When a screen/report runs multiple SELECTs that must reflect the same point in time, do not assume READ COMMITTED guarantees that just because each individual SELECT is consistent.
- If a stable point-in-time view is required for a report, consider an appropriate transaction mode, read-only transaction, Flashback Query/SCN, or consolidating into a single SQL statement if business logic allows; verify suitability with your Oracle version and undo resources.
- Avoid keeping transactions open across HTTP/queue waits, as snapshot/lock and database resource costs can increase.

**Source:** [Oracle Database 19c — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html).

## 7. MySQL/InnoDB: each consistent read gets a fresh read view at READ COMMITTED

MySQL **InnoDB** uses MVCC for **consistent nonlocking reads**: an ordinary `SELECT` does not lock rows and instead reads the appropriate data version.

Core distinctions:

- **`READ COMMITTED`:** each consistent read creates/uses its own **fresh snapshot**, even within the same transaction.
- **`REPEATABLE READ`:** this is **InnoDB**'s default isolation in standard MySQL configurations; consistent reads in a transaction share the snapshot established by **the transaction's first consistent read**.
- **Locking reads** (`SELECT ... FOR UPDATE` or `FOR SHARE`) and DML (`UPDATE`/`DELETE`) have different locking/visibility handling from plain consistent `SELECT`. Do not apply the "SELECT snapshot" rule to conclude how DML behaves.
- InnoDB lets a transaction see changes it made itself, even while uncommitted.

### 7.1. Difference between READ COMMITTED and REPEATABLE READ

```text
MySQL InnoDB, READ COMMITTED

T1: BEGIN
T1: SELECT row 7 -> 100        snapshot R1
T2: UPDATE row 7 -> 150; COMMIT
T1: SELECT row 7 -> 150        snapshot R2 (new)
T1: COMMIT

MySQL InnoDB, REPEATABLE READ (consistent nonlocking SELECT)

T1: BEGIN
T1: SELECT row 7 -> 100        snapshot R1 established
T2: UPDATE row 7 -> 150; COMMIT
T1: SELECT row 7 -> 100        still uses read view R1
T1: COMMIT
```

These are two **idealized scenarios** for plain `SELECT`, not general descriptions for locking reads or transactions with their own updates.

### 7.2. Observation syntax

```sql
-- Check which isolation level the MySQL session is using:
SELECT @@transaction_isolation;

-- Set for the next transaction in the session:
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;
SELECT balance FROM account_balance WHERE id = 1;
-- Have another session UPDATE+COMMIT.
SELECT balance FROM account_balance WHERE id = 1;
COMMIT;
```

Depending on version/permissions, `SET TRANSACTION` must be executed **before the transaction starts**. Verify the actual configuration; do not assume the database defaults to READ COMMITTED — **MySQL InnoDB typically defaults to REPEATABLE READ**.

### 7.3. Why is SELECT FOR UPDATE not equivalent to ordinary SELECT?

`SELECT ... FOR UPDATE` acquires locks on qualifying rows, can wait on other transactions, and accesses current state to support updates. It is **not accurately described** by the "one snapshot per plain SELECT" rule above. In InnoDB, index usage, range predicates, gap/next-key locking, and isolation level affect locking behavior; under READ COMMITTED, gap locking for searches/index scans is largely disabled, except in specific cases such as foreign-key or duplicate-key checks.

```sql
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE id = 1
FOR UPDATE;

UPDATE account_balance
SET balance = balance - 10
WHERE id = 1;

COMMIT;
```

This is a **locked read-to-write** pattern, distinct from plain `SELECT` reporting queries. Do not slap `FOR UPDATE` onto every query "to be safer": it can increase contention/deadlocks and hurt throughput.

**Sources:** [MySQL 8.4 — InnoDB Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html) and [Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html).

## 8. SQL Server: READ COMMITTED can be lock-based or row-versioned

Microsoft SQL Server distinguishes two **execution modes** of `READ COMMITTED` depending on the database option `READ_COMMITTED_SNAPSHOT` (abbreviated **RCSI**).

### 8.1. RCSI OFF: lock-based READ COMMITTED

When `READ_COMMITTED_SNAPSHOT = OFF` (default on many on-premises SQL Server installations), READ COMMITTED uses **shared locks** to avoid reading rows modified but not yet committed by another writer. Row/page shared locks can be released as the statement scans; hence **there is no MVCC-style consistent point-in-time snapshot across the entire statement**.

Possible consequences:

- A reader must **wait** for a writer to commit/roll back before reading rows locked by the writer.
- Readers and writers can block one another depending on lock granularity and query execution.
- A scan can be affected by concurrent changes during traversal, such as missing/double reads in certain scan situations.
- Two separate SELECT statements can naturally see different committed values.

`READ COMMITTED` still prevents **dirty reads**; however, do not interpret "prevents dirty reads" as "a SELECT is always a snapshot at statement start."

### 8.2. RCSI ON: statement-level row-versioned snapshot

When `READ_COMMITTED_SNAPSHOT = ON`, SQL Server uses **row versions** to provide **statement-level read consistency** for READ COMMITTED. A SELECT statement normally sees committed data as of the moment the statement began, while still seeing its own transaction's writes.

```text
RCSI ON:
  SELECT #1 starts -> reads snapshot S1
  Writer COMMIT
  SELECT #2 starts -> reads snapshot S2

Two SELECTs in the same transaction can still differ.
```

**RCSI is not synonymous with the SNAPSHOT isolation level.** SQL Server has a separate isolation level named `SNAPSHOT`, which uses a transaction-level snapshot when `ALLOW_SNAPSHOT_ISOLATION` is enabled and the session requests that level. A database with RCSI enabled can still have READ COMMITTED transactions that see a **fresh snapshot per statement**.

### 8.3. Checking actual configuration

```sql
SELECT name, is_read_committed_snapshot_on,
       snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
```

`is_read_committed_snapshot_on = 1` means RCSI is ON for the current database. `snapshot_isolation_state_desc` relates to the availability of `SNAPSHOT` isolation, **not** a substitute column for RCSI.

An administrator can enable RCSI through a database configuration change process, for example:

```sql
-- Illustrative admin command: evaluate system impact before using.
ALTER DATABASE YourDatabase SET READ_COMMITTED_SNAPSHOT ON;
```

**Do not run in production just to test a lesson**: this change affects read/locking behavior and row version store resources, and may require connection conditions and admin privileges. On Azure SQL Database, RCSI is typically **ON by default**; on SQL Server and Azure SQL Managed Instance, the common default is **OFF**. Always inspect `sys.databases` instead of guessing from the environment.

### 8.4. RCSI does not mean "all locks vanish"

Even though RCSI removes row/page shared locks on data being read by plain reads, there are still:

- Schema stability locks and locks required for metadata/DDL.
- Locks for writes, DML, constraints, and locking hints such as `UPDLOCK`/`HOLDLOCK`.
- Potential update conflicts, deadlocks, and lock waits in specific situations.
- Storage/maintenance overhead for row versions and tempdb/persistent version store depending on configuration/version.

Do not recommend `WITH (NOLOCK)` to "create a snapshot": `NOLOCK` corresponds to read-uncommitted-style hints and can cause **dirty reads** and severe anomalies. If the goal is reducing reader/writer blocking without reading uncommitted data, evaluate RCSI, index/query patterns, and SQL Server version.

**Sources:** [Microsoft Learn — Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide) and [SET TRANSACTION ISOLATION LEVEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql).

## 9. H2: for controlled hands-on practice, not a substitute for every database

H2 supports `READ COMMITTED` and documents it as its default isolation, with **no dirty reads** but potential **non-repeatable/phantom reads**. H2 uses MVCC for many operations; when connection A reads and connection B has uncommitted changes, A sees the appropriate committed version plus its own changes.

Section 12's example uses H2 to verify **two SELECT statements in the same transaction receiving two different values** after another writer commits. That phenomenon is permitted by READ COMMITTED and H2 reproduces it; do not treat that as proof that H2 matches PostgreSQL/Oracle/InnoDB/SQL Server in locking, undo, gap locks, or snapshot strategy.

Notable points:

- H2 DDL can auto-commit transactions. **Create tables and seed data before** starting test transactions, rather than creating tables mid-demo to test rollback.
- H2 also supports other isolation levels, though their exact semantics and strength do not necessarily match PostgreSQL or Oracle. H2's documentation includes implementation caveats for `SERIALIZABLE`.
- Connection pool, JDBC version, and test harness also affect behavior; use H2 to **learn**, then run integration tests against the production database/driver to verify business correctness.

**Source:** [H2 — Advanced: Transaction Isolation](https://h2database.com/html/advanced.html).

## 10. Summary table: "Which snapshot does READ_COMMITTED see?"

| Database / mode | What does READ COMMITTED use for plain SELECT? | Snapshot / read-view timing | Mandatory takeaway |
| --- | --- | --- | --- |
| **PostgreSQL** | MVCC | New snapshot when **each command starts** | Next SELECT can see new commits; UPDATE/SELECT FOR UPDATE has recheck/lock semantics. |
| **Oracle Database** | MVCC/read consistency with undo/SCN | **Statement** point in READ COMMITTED | Each statement is consistent; the next statement gets a new point. |
| **MySQL InnoDB** | MVCC consistent nonlocking read | New read view on **each consistent read** under READ COMMITTED | InnoDB default is usually REPEATABLE READ; locking reads and DML follow different rules. |
| **SQL Server RCSI ON** | Row versioning | Snapshot **at the start of each statement** | `READ_COMMITTED_SNAPSHOT=ON` differs from `SNAPSHOT` isolation. |
| **SQL Server RCSI OFF** | Shared locks | **No guaranteed point-in-time statement MVCC snapshot** | Prevents dirty reads, but readers/writers can block and scans may not be point-in-time consistent. |
| **H2** | MVCC per H2 engine | RC behavior allows reading new commits between statements | Use for RC demos; do not equate all engine details with production. |

This table describes **plain reads** in a READ COMMITTED transaction. Once locking reads, stored procedures, DDL, UDFs, database hints, mixed DML, or driver/connection-specific configurations are added, exact rules can vary.

### Two layers of questions to ask when reading code

1. **"What isolation level does my transaction currently have?"** In Spring/JDBC, check the annotation, transaction manager, JDBC connection, and actual database default.
2. **"How does the database engine implement that level?"** Check PostgreSQL/Oracle/InnoDB/SQL Server RCSI and the SQL statement type.

Answering only question 1 while ignoring question 2 leads to wrong conclusions about blocking and statement consistency.

## 11. Spring Framework: `@Transactional(isolation = READ_COMMITTED)`

In Spring, use:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void calculateAccountStatus() {
    // SQL statements via JdbcTemplate/repository.
}
```

`Isolation.READ_COMMITTED` maps to the corresponding transaction isolation on the transaction resource/manager (for JDBC, `Connection.TRANSACTION_READ_COMMITTED`). However:

1. Spring **does not build MVCC snapshots itself**. The database engine decides statement visibility and locking strategy.
2. The annotation must actually be applied by the transaction interceptor — e.g., the caller invokes a **Spring-managed bean through its proxy** in proxy mode, not `new Service()` or `this.method()`.
3. Isolation is configured for **a new transaction** started by the method (`REQUIRED` when none exists, or `REQUIRES_NEW`). When a method merely **joins** an existing transaction, an isolation declaration on the inner method **does not automatically change** the outer physical transaction's isolation.
4. `Isolation.DEFAULT` is the annotation default: it uses the default isolation level of the underlying data source/database. PostgreSQL usually defaults to READ COMMITTED, MySQL InnoDB usually defaults to REPEATABLE READ, and SQL Server defaults to READ COMMITTED while RCSI can be ON or OFF.
5. A transaction manager, driver, or database may **not support** a specific isolation level, or may throw an exception when setting it. Never treat the enum name as a guarantee of identical consistency semantics across engines.
6. With multiple datasources/transaction managers, you must know which manager/resource an annotation targets; a single annotation does not establish a single snapshot across multiple databases.

### 11.1. `REQUIRED` joining an existing transaction

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void outer() {
        inner.readCommittedMethod();
    }
}

@Service
class InnerService {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void readCommittedMethod() {
        // Default REQUIRED, joins existing outer transaction.
    }
}
```

This is an **excerpt**, requiring imports for `@Service`, `@Transactional`, and `Isolation`. With the same transaction manager/resource, inner `REQUIRED` **joins outer's physical transaction**; it normally does not downgrade T1's isolation from REPEATABLE_READ to READ_COMMITTED. Some managers support `setValidateExistingTransaction(true)` to **reject** isolation mismatches instead of silently reusing the current isolation.

If you need an independent transaction with its own READ_COMMITTED isolation:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED
)
public void independentRead() {
    // New transaction, new isolation per manager and DB.
}
```

Requires importing `Propagation`. `REQUIRES_NEW` creates a separate physical transaction, can use a separate connection, and commits/rolls back independently, so **do not use it merely to "force isolation"** if the business work must be atomic with outer.

### 11.2. JDBC and DataSource

With `JdbcTransactionManager`/`DataSourceTransactionManager`, Spring obtains a connection from the `DataSource`, applies the requested isolation when beginning an eligible transaction, and attempts to restore connection state when the transaction ends.

```text
Caller -> Spring proxy -> transaction manager
                           |
                           +--> DataSource/Connection
                                setTransactionIsolation(READ_COMMITTED)
                                BEGIN/autoCommit=false
                           |
                           +--> JdbcTemplate uses bound connection
                           |
                           +--> COMMIT or ROLLBACK
                           |
                           +--> reset connection state / return to pool
```

This is a conceptual diagram, not the exact log sequence of every JDBC driver. If code directly opens `dataSource.getConnection()` bypassing transaction-aware mechanisms and runs SQL, that query may use **a different connection** outside the Spring transaction bound to the thread. Prefer `JdbcTemplate`, integrated repositories/frameworks, or `DataSourceUtils` for low-level JDBC.

### 11.3. `readOnly=true` does not create a transaction-level snapshot

```java
@Transactional(
    isolation = Isolation.READ_COMMITTED,
    readOnly = true
)
public Report readReport() {
    // ...
}
```

This is an illustrative signature; `Report` is an application type. `readOnly=true` is metadata/a hint that can affect optimizations and connection/resource settings, yet **does not automatically raise isolation** or "freeze" a snapshot for the whole transaction. Two SELECTs in the report can still see different committed data at READ COMMITTED.

If a multi-query report must be consistent as of one point in time, specify the required consistency, check database features, and select an appropriate isolation level. Never add `readOnly=true` and expect a fixed snapshot.

### 11.4. Self-invocation and test infrastructure

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readInIsolation() { }

public void callLocal() {
    readInIsolation(); // self-invocation, bypasses Spring proxy mode.
}
```

This is an excerpt. If `callLocal()` is not intercepted and there is no enclosing transaction, the `READ_COMMITTED` annotation on `readInIsolation()` **has no effect** via this call. If a test method has `@Transactional` opened by Spring TestContext, the service may join **the test-managed transaction**, causing the isolation test to measure the wrong boundary.

## 12. Runnable Java 17 project: two transactions and two snapshots

**Goal:** prove that a Spring method with `@Transactional(isolation = READ_COMMITTED)` can run **two SELECTs** on the same row and receive **two different values** because another transaction committed between the two SELECTs.

To make the result deterministic, the code **does not use `Thread.sleep` to guess timing**. It uses `CountDownLatch` and two executor threads, enforcing the schedule:

1. Reader transaction T1 starts, reads `balance = 100`, signals that the first read completed.
2. Writer transaction T2 waits for the signal, updates balance to 150, commits, then signals that the commit finished.
3. Reader T1 **is still open** and after seeing T2 committed, reads again: `balance = 150`.
4. The runner waits for both to finish and reads the DB again: `final = 150`.

**These are two independent transactions on two threads**, not another thread "sharing" T1. Imperative Spring transactions bind to the thread context; each bean method is invoked through its proxy on its own thread.

### 12.1. Project tree

```text
read-committed-snapshot-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/isolation/
    │   ├── IsolationApplication.java
    │   ├── ReaderService.java
    │   └── WriterService.java
    └── resources/
        └── application.properties
```

Requires **JDK 17 or newer**; Maven 3.9+ is suitable. No standalone H2 server installation is needed.

### 12.2. `pom.xml`

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
    <artifactId>read-committed-snapshot-demo</artifactId>
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

The Spring JDBC starter brings in `JdbcTemplate`, HikariCP, and Spring transaction infrastructure. The transaction manager bean is explicitly defined in the main application so nothing is left to guesswork from auto-configuration.

### 12.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:read_committed_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Reader T1 and writer T2 need two physical connections simultaneously.
spring.datasource.hikari.maximum-pool-size=3
```

`DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive in the JVM when pooled connections are returned. A pool of 3 connections lets the two threads acquire independent connections without contending on connection checkout. This is a demo setting, not a production sizing rule.

### 12.4. `src/main/java/vn/example/isolation/ReaderService.java`

```java
package vn.example.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReaderService {

    private final JdbcTemplate jdbc;

    public ReaderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        isolation = Isolation.READ_COMMITTED,
        readOnly = true
    )
    public String readTwice(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted
    ) throws InterruptedException {

        int first = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE id = 1",
            Integer.class
        );

        firstReadDone.countDown();

        if (!writerCommitted.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Writer did not commit within 10 seconds"
            );
        }

        int second = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE id = 1",
            Integer.class
        );

        return "reader.first=" + first
            + "\nreader.second=" + second;
    }
}
```

**Explanation:**

- `@Transactional` on a public method of a Spring-managed bean, called via the proxy, starts **one T1** covering both `SELECT`s.
- `Isolation.READ_COMMITTED` requests a READ COMMITTED JDBC transaction.
- `readOnly=true` expresses that T1 is read-only; **it does not turn T1 into a fixed-snapshot transaction**.
- `firstReadDone.countDown()` signals that T1 has fetched the first value.
- `writerCommitted.await(...)` waits for the writer to **finish committing** before T1 runs the second `SELECT`. The 10-second limit is only a **test coordination** timeout, not a transaction timeout.
- Both `SELECT`s run inside the same method/T1, so the value difference comes from isolation/commit visibility, not from the reader starting a new T1.

The method declares checked `InterruptedException` so the Java example compiles cleanly; in normal execution no interrupt occurs. If interrupted during test coordination, error handling must follow appropriate rollback/cleanup policy; here the reader performs no DML so the demonstration does not depend on checked-exception rollback rules.

### 12.5. `src/main/java/vn/example/isolation/WriterService.java`

```java
package vn.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriterService {

    private final JdbcTemplate jdbc;

    public WriterService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void addFifty() {
        jdbc.update(
            "UPDATE account_balance SET balance = balance + 50 " +
            "WHERE id = 1"
        );
    }
}
```

The writer runs in **T2 on another thread**, intercepted by the Spring proxy, and commits when `addFifty()` returns normally. `UPDATE balance = balance + 50` performs the increment directly in SQL, avoiding the problem of overwriting with a stale value precomputed in Java.

### 12.6. `src/main/java/vn/example/isolation/IsolationApplication.java`

```java
package vn.example.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc,
            ReaderService readerService,
            WriterService writerService
    ) {
        return args -> {
            // DDL and sample data are created BEFORE the two transactions.
            jdbc.execute(
                "CREATE TABLE account_balance (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO account_balance(id, balance) VALUES (1, 100)"
            );

            CountDownLatch firstReadDone = new CountDownLatch(1);
            CountDownLatch writerCommitted = new CountDownLatch(1);
            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<String> reader = pool.submit(
                    () -> readerService.readTwice(
                        firstReadDone, writerCommitted
                    )
                );

                Future<?> writer = pool.submit(() -> {
                    if (!firstReadDone.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Reader did not read within 10 seconds"
                        );
                    }

                    // Returning from the proxy method means T2's commit is done.
                    writerService.addFifty();
                    writerCommitted.countDown();
                    return null;
                });

                writer.get(15, TimeUnit.SECONDS);
                System.out.println(reader.get(15, TimeUnit.SECONDS));

                int committed = jdbc.queryForObject(
                    "SELECT balance FROM account_balance WHERE id = 1",
                    Integer.class
                );
                System.out.println("final=" + committed);
            } finally {
                // If writer errors, do not leave reader waiting indefinitely.
                writerCommitted.countDown();
                pool.shutdownNow();
            }
        };
    }
}
```

**Why does this code verify properly?**

1. `CommandLineRunner` has no enclosing transaction wrapping the whole run; the service methods define the transaction boundaries.
2. `@EnableTransactionManagement(proxyTargetClass=true)` and constructor injection ensure the Spring-managed service methods are invoked via proxies.
3. T1 and T2 run on **two different threads**, each with its own JDBC transaction context.
4. `writerService.addFifty()` only returns after the Spring transaction interceptor completes committing T2, and only then calls `writerCommitted.countDown()`. Thus the reader's second read cannot run before the writer's commit under normal scheduling.
5. `reader.readTwice(...)` is **one method call**, i.e., one T1 spanning both SELECTs—not two separate transactions.
6. H2 READ COMMITTED can see the new committed version on the second read, matching the specification and H2 documentation.
7. Output is printed **in a deterministic order** after the main thread awaits `Future`s, independent of thread log interleaving.

If either thread fails, `Future.get` surfaces the exception; the code does not print a fake "success" result. Latches have timeouts to reduce the chance of the test hanging indefinitely; this is not a pattern for production code, but makes for a readable concurrency test.

### 12.7. Build and run

```bash
java -version
mvn -version
mvn -q package
java -jar target/read-committed-snapshot-demo-1.0.0.jar
```

**Lines explicitly printed by the example code** when run correctly on Java 17, Spring Boot 3.5.7, H2, and the configuration above:

```text
reader.first=100
reader.second=150
final=150
```

Spring Boot and HikariCP may print additional startup/shutdown logs. The three lines above represent the expected business output of the program, excluding framework logs.

### 12.8. Why is the second value 150?

- Reader T1 starts first; `SELECT #1` reads `100`.
- Writer T2 only runs its update after receiving the latch confirming the first read.
- Writer updates the value to `150` and **commits** before releasing the latch for the reader.
- Reader T1 is still open at READ_COMMITTED, so `SELECT #2` reads newly committed data and can observe `150`.
- There is no dirty read, because `150` is only visible to the reader **after T2 commits**.
- This behavior is a **non-repeatable read permitted by READ_COMMITTED**, not Spring creating a new snapshot in Java; H2/JDBC implements the read-view decision.

### 12.9. What if we change to REPEATABLE_READ?

If you change ReaderService's annotation to:

```java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public String readTwice(...) {
    // Signature snippet only; keep the previous method body.
}
```

This is a **signature snippet**; the ellipsis `...` is not standalone Java code. Do not generalize the result across all databases: PostgreSQL, InnoDB, H2, and SQL Server have different isolation implementations and limits. To compare, rebuild and run against the specific database, keep the schedule fixed, and confirm JDBC driver support.

In PostgreSQL and InnoDB plain consistent reads at REPEATABLE READ, two ordinary SELECTs tend to use a transaction-consistent snapshot; in SQL Server, `REPEATABLE READ` can use locks rather than a transaction-level MVCC snapshot. **The level name alone is not enough to conclude the mechanism**.

## 13. READ_COMMITTED and the lost update problem

A common mistake is seeing that READ_COMMITTED has no dirty reads and concluding "all updates are safe."

Suppose two requests both read `balance=100`:

```text
T1 SELECT balance -> 100
T2 SELECT balance -> 100
T1 computes 100 + 10 = 110
T2 computes 100 + 20 = 120
T1 UPDATE balance = 110; COMMIT
T2 UPDATE balance = 120; COMMIT
Result is 120, instead of 130 if both additions should accumulate.
```

This is a **read-modify-write scenario with a value computed in the application**. The database may lock rows/wait and has specific conflict-handling differences, yet the pattern of overwriting with a stale value risks a **lost update** without extra protection.

Countermeasures depending on requirements:

- Fold the math into one atomic DML statement: `UPDATE account_balance SET balance = balance + 10 WHERE id = 1`. The DB enforces appropriate row-update locking/concurrency.
- **Optimistic locking** with a version column: `UPDATE ... SET balance=?, version=version+1 WHERE id=? AND version=?`, checking the affected row count; if 0, perform bounded retries or report conflict.
- **Pessimistic locking** with `SELECT ... FOR UPDATE` on engines that support it and when critical sections must serialize.
- Choose stronger isolation such as transaction-level snapshot or SERIALIZABLE **when suited to the business semantics** and after testing real conflicts/retries. Note that each engine defines/implements these slightly differently.

`READ_COMMITTED` does not replace database constraints, unique keys, optimistic versions, or race-condition handling.

## 14. Multiple queries in the same service can return business-inconsistent data

Consider a revenue example:

```text
T1, READ_COMMITTED:
  SELECT SUM(amount) FROM invoices WHERE status='PAID'   -> 1,000
T2:
  updates/inserts invoice then COMMIT
T1:
  SELECT COUNT(*) FROM invoices WHERE status='PAID'      -> 12
```

Both numbers may be accurate at **two different moments**. If combined into an average ratio, the report can produce a "composite view" that never existed intact at any single point in time.

Solutions depending on business needs:

1. **Single SQL statement:** when computing SUM/COUNT over the same dataset in **one statement** on an engine with statement snapshots, both aggregates see one coherent point in time. For example:
   `SELECT COUNT(*), SUM(amount) FROM invoices WHERE status='PAID'`.
2. **Transaction-level stable read:** choose the DB's appropriate mechanism so queries share one snapshot when required.
3. **Materialized/read model:** maintain summary tables/projections with a consistent update policy.
4. **Define eventual consistency:** if a dashboard tolerates minor skew, document the SLA/staleness instead of demanding a global snapshot on every report.

In particular, under **SQL Server RCSI OFF**, combining into one SQL statement does not yet guarantee an MVCC point-in-time snapshot; you must verify consistency requirements and design queries/isolation accordingly.

## 15. Two-session test scenarios for production databases

Before changing isolation in a real system, test in a dedicated/staging database with minimal data and two clearly identified connections.

### Test A — no dirty reads

1. T1 at READ_COMMITTED reads `value=100`.
2. T2 UPDATEs to `150` but **does not commit yet**.
3. T1 runs SELECT while T2 is uncommitted:
   - With MVCC plain reads, T1 can see `100`.
   - With SQL Server locking READ COMMITTED, T1 may **block** waiting for T2.
4. T2 ROLLBACKs; T1 must never receive `150` as a "committed value" from T2.

**Do not assert that every engine returns immediately while a writer is uncommitted**: the goal is preventing dirty reads, not mandating nonblocking reads.

### Test B — non-repeatable read

1. T1 READ_COMMITTED SELECTs id=1, records `100`.
2. T2 UPDATEs id=1 to `150` and COMMITs.
3. T1 SELECTs id=1 again, records `150` if the engine/read type exhibits that behavior.
4. Confirm the second read began **after** T2's COMMIT.
5. T1 COMMITs; inspect the actual isolation and transaction boundary, not just the SQL string.

### Test C — phantom read

1. T1 runs SELECT COUNT on a fixed predicate.
2. T2 INSERTs a matching row and COMMITs.
3. T1 runs SELECT COUNT again; if the count increases, that is a phantom.
4. Check indexes, locking hints, or actual isolation if the result blocks or differs from expectations.

### Test D — consistency of a long-running SELECT

1. Create a dataset large enough for a controlled SQL scan.
2. Start T1's query; have T2 commit changes while T1 is mid-read.
3. Compare results across PostgreSQL/Oracle/InnoDB consistent reads, SQL Server RCSI ON, and RCSI OFF.
4. Avoid inferring consistency from a single run — query plans, index scans, locks, and commit timing alter results.
5. On SQL Server RCSI OFF, test **the absence of an MVCC statement snapshot**, so a targeted test model is needed to observe possible missing/double reads without expecting them to reproduce on every run.

### Test E — Spring test boundary

Place transaction boundaries on public service beans. Invoke through the Spring proxy; avoid placing `@Transactional` on the outer test method, which causes the service to join a different transaction. Read/write via the same transaction manager/DataSource. Use a two-thread latch and real database as in the demo to control the schedule, rather than inserting `Thread.sleep` and hoping the race aligns.

## 16. Configuration and operations checklist for READ_COMMITTED

- [ ] Verified the **actual JDBC connection isolation level**, not inferred from framework names.
- [ ] Distinguished `Isolation.DEFAULT` from `Isolation.READ_COMMITTED`.
- [ ] In Spring, `@Transactional` takes effect through the proxy and **starts a new transaction** when setting isolation.
- [ ] Inner `REQUIRED` does not automatically alter an existing outer transaction's isolation.
- [ ] Identified the DB engine/version: PostgreSQL, Oracle, MySQL/InnoDB, SQL Server, or H2.
- [ ] On SQL Server, checked `sys.databases.is_read_committed_snapshot_on`; RCSI ON/OFF changes read behavior.
- [ ] On MySQL, distinguished consistent `SELECT` from locking reads and verified the session default is typically REPEATABLE READ.
- [ ] On PostgreSQL, distinguished plain SELECT snapshots from concurrent-update rechecks in UPDATE/DELETE/FOR UPDATE.
- [ ] On Oracle, understood SCN/undo statement consistency and undo sizing for long queries.
- [ ] Did not confuse a **statement-level snapshot** with a fixed **transaction-wide** snapshot.
- [ ] Evaluated whether non-repeatable reads and phantom reads can break business logic or multi-query reports.
- [ ] Used constraints/optimistic locking/row locking/atomic DML to prevent stale writes when required.
- [ ] Did not use `NOLOCK` as a mechanism for consistent snapshots.
- [ ] Tested database/queries/driver in an appropriate environment rather than assuming H2 represents every engine.
- [ ] Implemented bounded retries when transactions hit deadlocks, serialization failures, or update conflicts at the chosen isolation/DB.
- [ ] Accounted for connection pools, long-running transactions, version/undo stores, and transaction timeouts.

## 17. Self-check questions

**Question 1.** Two SELECTs inside a Spring transaction with `@Transactional(isolation=READ_COMMITTED)` see `100` and then `150` after another transaction commits. Is isolation broken?

**Answer:** No. `READ_COMMITTED` permits non-repeatable reads. On databases using fresh statement snapshots/consistent reads, this is normal behavior.

**Question 2.** Does `READ_COMMITTED` guarantee the whole transaction sees one snapshot?

**Answer:** No. It prevents dirty reads, yet does not guarantee a transaction-level snapshot.

**Question 3.** Are PostgreSQL READ COMMITTED and SQL Server RCSI OFF implemented the same way?

**Answer:** No. PostgreSQL plain SELECT uses per-statement MVCC snapshots; SQL Server RCSI OFF uses shared locks and **does not promise a point-in-time MVCC statement snapshot**.

**Question 4.** How does SQL Server RCSI ON differ from SNAPSHOT isolation?

**Answer:** RCSI ON under READ COMMITTED provides row-versioned **statement-level** snapshots; the separate `SNAPSHOT` isolation targets **transaction-level** snapshots and requires its own options/configuration.

**Question 5.** How do MySQL InnoDB plain SELECTs differ between REPEATABLE READ and READ COMMITTED?

**Answer:** READ COMMITTED uses a fresh read view for each consistent read; REPEATABLE READ uses the read view established by the transaction's first consistent read for subsequent consistent reads, with exceptions for locking reads and the transaction's own writes.

**Question 6.** In Spring, does an inner `@Transactional(isolation=READ_COMMITTED)` automatically switch an outer T1 running at REPEATABLE_READ to READ_COMMITTED?

**Answer:** No, if inner simply joins T1 under default `REQUIRED`. Isolation is a property of the physical transaction when it is started.

**Question 7.** Does setting `readOnly=true` under READ_COMMITTED make all SELECTs in the same transaction see a single snapshot?

**Answer:** That is not a Spring guarantee. You need the appropriate isolation/database transaction mode if the business operation genuinely requires transaction-level consistency.

**Question 8.** On SQL Server, queries are blocking under READ COMMITTED. Should you add `NOLOCK` to every query?

**Answer:** No. `NOLOCK` can read uncommitted data and cause anomalies. First evaluate RCSI, indexes/query plans, lock contention, and consistency requirements.

**Question 9.** A report reads total revenue and order count in two SELECTs while data changes between them. Should both results be expected from the same point in time?

**Answer:** Not when using READ COMMITTED alone. On engines with statement snapshots, you can combine them into one SQL query or use transaction-level consistent reads as needed.

## Official sources for verification

1. **PostgreSQL 18** — [Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html), [SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html): per-statement snapshot at READ COMMITTED, non-repeatable reads, UPDATE recheck.
2. **Oracle Database** — [Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): SCN, undo, statement-level read consistency.
3. **MySQL InnoDB 8.4** — [Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html), [Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html): fresh read view at READ COMMITTED, default REPEATABLE READ, and locking reads.
4. **Microsoft SQL Server** — [Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide), [SET TRANSACTION ISOLATION LEVEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql): RCSI ON/OFF, shared locks, statement vs. transaction snapshots.
5. **H2 Database** — [Advanced: Transaction Isolation](https://h2database.com/html/advanced.html): READ COMMITTED and MVCC used in the hands-on lab.
6. **Spring Framework** — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html), [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): isolation metadata, transaction proxies, REQUIRED vs. REQUIRES_NEW.

**Conclusion:** `READ_COMMITTED` prevents **dirty reads** while typically still allowing data seen between statements of the **same transaction** to change when other transactions commit. "A fresh snapshot per statement" describes PostgreSQL, Oracle, InnoDB consistent reads at READ COMMITTED, and SQL Server with **RCSI ON**; SQL Server with **RCSI OFF** prevents dirty reads primarily via locks rather than per-statement MVCC snapshots. In Spring, `Isolation.READ_COMMITTED` is a request sent to the **transaction manager and database** when starting an eligible transaction, not a snapshot algorithm implemented in Java.
