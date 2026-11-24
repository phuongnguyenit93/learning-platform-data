# Designing a two-connection experiment to observe transaction isolation phenomena

## 1. Why are two connections needed?

When learning `@Transactional(isolation = ...)` in Spring, reading the definitions of `READ_COMMITTED`, `REPEATABLE_READ`, or `SERIALIZABLE` is not enough to picture **when one transaction can see another transaction's changes**.

A good experimental program must simulate **two independent sessions against the database**:

- **Connection A** represents transaction T1 reading, holding a snapshot, or computing business decisions.
- **Connection B** represents transaction T2 modifying data and explicitly executing `COMMIT` or `ROLLBACK`.
- The program **precisely controls the ordering** of A/B statements rather than relying on `Thread.sleep(...)` or hoping a race condition occurs.
- After each experiment, data is **reset to a known state** so results do not depend on the previous experiment.
- Results are explained based on **the actual DBMS and isolation level**. The SQL standard defines minimum guarantees, not that every DBMS produces the exact same phenomena.

This lesson designs a lab for the **Transaction isolation** topic in Spring Framework transaction management. The main hands-on part uses **two truly distinct JDBC `Connection`s**, Java 17+, Spring Boot, and PostgreSQL.

> **Core rule:** you cannot observe dirty reads, non-repeatable reads, phantom reads, or other concurrency anomalies by running all statements sequentially on **a single transaction/connection**. At least two transactions with a controlled interleaving are required.

### Expected outcomes after this lesson

You will be able to:

1. Write a clear schedule of operations for two connections A/B: who `BEGIN`s, who reads, who writes, who `COMMIT/ROLLBACK`s, and who reads the second time.
2. Distinguish **dirty read**, **non-repeatable read**, **phantom read**, **lost update** from unsafe read-modify-write, and **serialization anomaly**.
3. Run Java 17+ with **two JDBC connections** and observe reproducible quantitative outcomes.
4. Know **why PostgreSQL does not allow dirty reads even when requesting `READ_UNCOMMITTED`**, and why PostgreSQL `REPEATABLE_READ` also prevents phantom reads.
5. Connect the measurements to Spring's `@Transactional(isolation = ...)`, propagation, and transaction manager.
6. Avoid wrong conclusions caused by auto-commit, late snapshot initialization, accidentally reusing the same connection, lock waits, or tests already wrapped in an outer transaction.

## 2. Definitions of phenomena to observe

### 2.1. Dirty read — reading uncommitted data

T2 updates a balance from 100 to 200 **without committing yet**. T1 reads 200. Then T2 rolls back, returning the true data to 100.

```text
Initial state: balance = 100

B / T2: BEGIN
B / T2: UPDATE balance = 200       (not COMMITTED yet)
A / T1: SELECT balance              (if 200 seen => dirty read)
B / T2: ROLLBACK
A / T1: SELECT balance              (may see 100 again)
```

A DBMS may **not support dirty reads** even if its SQL API accepts `READ_UNCOMMITTED` isolation. PostgreSQL is an important example: requesting `READ_UNCOMMITTED` is handled with guarantees equivalent to `READ_COMMITTED`, so the PostgreSQL experiment must see **100**, not 200.

To demonstrate a real dirty read, pick a DBMS and configuration that permits it—such as MySQL/InnoDB at `READ UNCOMMITTED`—and verify on that version. **Never use dirty reads in financial processing or business operations requiring consistency**.

### 2.2. Non-repeatable read — same row, two values

T1 reads the same row twice inside **the same transaction**. Between the two reads, T2 updates that row and **commits**:

```text
Initially: balance = 100

A / T1: BEGIN
A / T1: SELECT balance  -> 100
B / T2: BEGIN
B / T2: UPDATE balance = 120
B / T2: COMMIT
A / T1: SELECT balance  -> 120 (READ_COMMITTED in PostgreSQL)
A / T1: ROLLBACK
```

The phenomenon is **a row already read changing its value between two reads**. Compare:

- PostgreSQL `READ_COMMITTED`: the second SELECT normally sees 120 because each statement gets a fresh snapshot.
- PostgreSQL `REPEATABLE_READ`: the second SELECT still sees 100, because transaction T1 keeps reading the snapshot pinned at the first statement.

### 2.3. Phantom read — same condition, changing row set

T1 re-executes a filtered predicate query:

```sql
SELECT COUNT(*) FROM lab_items WHERE category = 'READY';
```

T2 inserts a new record with `category='READY'` and commits between T1's two SELECTs:

```text
Initially: READY has 1 row

A / T1: SELECT COUNT(*) WHERE category='READY' -> 1
B / T2: INSERT new READY row
B / T2: COMMIT
A / T1: SELECT COUNT(*) WHERE category='READY' -> 2 (phantom)
```

Unlike a non-repeatable read, here **the set of rows matching the condition changes**, not merely the value of an already-read row. `COUNT(*)` is convenient to observe, though do not equate the count itself with the essence of the phenomenon: it represents the changed result set.

PostgreSQL `READ_COMMITTED` permits phantom reads; PostgreSQL `REPEATABLE_READ` **prevents phantom reads**, even though the SQL standard allows phantoms at REPEATABLE READ as a minimum guarantee.

### 2.4. Lost update — overwriting a result from a stale read

Two transactions read the same `balance=100`. T2 computes `100+20=120` and commits. T1 then takes its **previously read** value to compute `100+10=110` and UPDATEs the balance with constant 110, overwriting T2's new value.

```text
A: READ balance -> 100
B: READ balance -> 100
B: UPDATE balance = 120; COMMIT
A: UPDATE balance = 110; COMMIT

Final: balance = 110
Expected if both +20 and +10 accumulate: balance = 130
```

This is a **lost update from unsafe client read–modify–write**. It can appear in PostgreSQL `READ_COMMITTED` when an application reads an old value into Java and later sends `UPDATE balance = ?` from the precomputed value.

**Risk mitigation:** an SQL statement `UPDATE lab_account SET balance = balance + ? WHERE id = ?` computing from the DB's current value, optimistic locking with a version column, pessimistic locking, or appropriate transactions/isolation. Do not treat every form of lost update as a single standard phenomenon with identical definitions/modes across all DBMSs.

### 2.5. Serialization anomaly / write skew — advanced level

Two transactions both check a global condition—such as "at least one doctor must remain on call"—and then each updates **a different row**. If both read the state before the other commits, each thinks another doctor remains and leaves duty. In the end, nobody is on call.

PostgreSQL `REPEATABLE_READ` can allow this write skew because snapshots do not guarantee histories equivalent to serial execution in every case. PostgreSQL `SERIALIZABLE` detects a non-serializable schedule and **aborts one transaction with SQLSTATE `40001`**. The application must retry **the entire transaction** on serialization failure.

The main lesson first fixes the four simple measurements; at the end there is an extra two-window SQL schedule for write skew/serializable.

## 3. Comparison table: SQL standard and PostgreSQL

| Isolation | Dirty read (PG) | Non-repeatable read (PG) | Phantom read (PG) | Serialization anomaly |
| --- | --- | --- | --- | --- |
| `READ_UNCOMMITTED` | No | Possible | Possible | Possible |
| `READ_COMMITTED` | No | Possible | Possible | Possible |
| `REPEATABLE_READ` | No | No | **No** | Possible |
| `SERIALIZABLE` | No | No | No | Does not let both transactions commit in a non-serializable schedule; may return error `40001` |

This table is specifically about **PostgreSQL**; do not use it to predict SQL Server, Oracle, MySQL, or H2 without reading the corresponding DBMS documentation.

Two easy-to-remember exceptions:

1. PostgreSQL executes `READ_UNCOMMITTED` just like `READ_COMMITTED`, so it does not read uncommitted data.
2. PostgreSQL `REPEATABLE_READ` is stronger than the standard's minimum guarantee regarding phantom reads, because it is snapshot-based.

### When is the snapshot actually taken?

Under PostgreSQL `READ_COMMITTED`, each ordinary `SELECT` statement sees a snapshot as of when the statement starts. Two different SELECTs in the same T1 can see different values when T2 commits in between.

Under PostgreSQL `REPEATABLE_READ`, the transaction's snapshot is fixed on **the first execution of a non-transaction-control statement**, not necessarily at the Java line `setAutoCommit(false)`. Therefore, to run the experiment properly:

- Have A execute its **first SELECT** to establish the snapshot;
- Only then have B modify and commit;
- Finally have A execute its second SELECT inside **the same transaction A**.

If you let B commit **before A's first SELECT**, you cannot use that result to prove whether repeatable read preserves a snapshot.

## 4. Designing a two-connection schedule scientifically

### 4.1. Conventions

- **A** = reader or first transaction.
- **B** = writer or second transaction.
- **T1/T2** = two independent physical transactions.
- **R1/R2** = A's first/second read.
- **W2** = B's write operation.
- **C2** = B's `COMMIT`.
- **X2** = B's `ROLLBACK`.
- **S0** = database state reset and committed before each experiment.

For experiments completely controllable by statement order, **two Java threads are not required**: one Java program can hold two `Connection`s open simultaneously and interleave A/B statements according to a fixed schedule. The database still sees **two concurrent unfinished transactions**, even though one Java thread alternates between them.

### 4.2. Four core experiment schedules

| Phenomenon | Mandatory schedule | What to read? | What can be concluded |
| --- | --- | --- | --- |
| Dirty read | S0 → B BEGIN → B uncommitted UPDATE → A SELECT → B ROLLBACK | Value A sees while B is uncommitted | Whether uncommitted value is visible |
| Non-repeatable read | S0 → A BEGIN/R1 → B BEGIN/W2/C2 → A R2 | A's two SELECTs of the same row | Whether a row's value changed within T1 |
| Phantom read | S0 → A BEGIN/R1 (predicate) → B INSERT/C2 → A R2 (same predicate) | A's two row sets / COUNTs | Whether the result set changed |
| Lost update | S0 → A reads old → B reads old → B UPDATE/C2 → A UPDATE from old value/C1 | Final value of a row | Whether one update was overwritten by a stale write |

To compare isolation levels, **keep the operation schedule and data identical**, changing only the relevant connection's isolation; if you change multiple things at once, you cannot tell which factor changed the result.

### 4.3. Variables to control

1. **DBMS/version:** use actual PostgreSQL in the main experiment.
2. **Two physical connections:** do not create two Java variables pointing to the same `Connection`.
3. **Auto-commit:** set `setAutoCommit(false)` on A/B before the test schedule so connections hold transactions across statements.
4. **Isolation:** call `setTransactionIsolation(...)` before the connection's transaction begins.
5. **Initial state:** reset the DB using a separate connection so the reset **finishes committing** before A/B begin.
6. **A/B ordering:** do not rely on thread delays; explicitly control who commits/rolls back before who reads the second time.
7. **Comparative reads:** same SQL, same predicate, on **the same connection A and same T1**.
8. **Cleanup:** close `ResultSet`/`Statement`; end T1/T2 with commit or rollback on every path; then close both connections.
9. **Side effects:** avoid unnecessary row locks, triggers, application caches, background jobs, or reused test data.
10. **Output:** print exact numbers and the isolation used to explain why an anomaly was or was not observed.

### 4.4. Why not wrap a test method with @Transactional and then open "two connections"?

When the goal is **manually controlling two physical JDBC transactions**, putting `@Transactional` on the coordinating method itself can interfere: Spring may bind a transaction to the thread or you may accidentally use `JdbcTemplate`/a repository joining an existing transaction.

The experiment below intentionally uses `DataSource.getConnection()` to acquire **two separate JDBC connections**, controls `autoCommit/commit/rollback` **directly**, and does not annotate `CommandLineRunner` with `@Transactional`. This isolates the "isolation level" variable cleanly for the lab.

In real business applications, you can use `@Transactional(isolation = ...)` and Spring's transaction manager to govern transactions; section 10 explains how to map the results back.

## 5. Reproducible lab environment

### 5.1. Test PostgreSQL instance

Requires Docker running. Create a PostgreSQL 16 database **strictly for local lab use**:

```bash
docker run --name spring-isolation-lab \
  -e POSTGRES_DB=isolation_lab \
  -e POSTGRES_USER=lab \
  -e POSTGRES_PASSWORD=lab \
  -p 55432:5432 \
  -d postgres:16
```

The command above uses Bash syntax. On Windows PowerShell, write it on **a single line**:

```powershell
docker run --name spring-isolation-lab -e POSTGRES_DB=isolation_lab -e POSTGRES_USER=lab -e POSTGRES_PASSWORD=lab -p 55432:5432 -d postgres:16
```

Verify the container is ready:

```bash
docker exec spring-isolation-lab pg_isready -U lab -d isolation_lab
```

If the container name or port already exists, pick another name/port and adjust the JDBC URL. Avoid using these demo credentials outside a learning machine. The lesson drops/recreates **tables prefixed with `lab_`** in the test database, so **never point it at a database with real data**.

### 5.2. Java 17+ Spring Boot project

Create a Maven project from Spring Initializr with:

- Java 17+; Spring Boot 3.x matching the JDK.
- Dependencies **Spring JDBC** / `spring-boot-starter-jdbc` and **PostgreSQL Driver**.
- Package: `com.example.isolationlab`.

Keep the full `pom.xml` generated by Initializr, including Spring Boot parent, version, and Maven plugin. The corresponding dependencies section:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

This is only **the dependencies section**, not the entire POM. Spring Boot dependency management provides compatible versions for the chosen Boot release.

File structure:

```text
src/main/
  java/com/example/isolationlab/
    IsolationLabApplication.java
  resources/
    application.properties
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:postgresql://localhost:55432/isolation_lab
spring.datasource.username=lab
spring.datasource.password=lab
spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.auto-commit=true
logging.level.root=WARN
```

A pool size of 5 is plenty for a synchronously controlled lab where A and B hold two connections at once. This is not a production sizing setting; when an application runs many concurrent transactions, size capacity for the workload.

## 6. Complete Java 17+ program with two JDBC connections

Single file `src/main/java/com/example/isolationlab/IsolationLabApplication.java`:

```java
package com.example.isolationlab;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class IsolationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }

    @Bean
    CommandLineRunner lab(DataSource dataSource) {
        return args -> {
            initialize(dataSource);
            verifyConnections(dataSource);

            dirtyRead(dataSource);
            nonRepeatableRead(
                dataSource, Connection.TRANSACTION_READ_COMMITTED,
                "READ_COMMITTED");
            nonRepeatableRead(
                dataSource, Connection.TRANSACTION_REPEATABLE_READ,
                "REPEATABLE_READ");

            phantomRead(
                dataSource, Connection.TRANSACTION_READ_COMMITTED,
                "READ_COMMITTED");
            phantomRead(
                dataSource, Connection.TRANSACTION_REPEATABLE_READ,
                "REPEATABLE_READ");

            lostUpdate(dataSource);
            atomicIncrement(dataSource);
        };
    }

    private static void initialize(DataSource ds) throws SQLException {
        // Run ONLY on dedicated LAB DB: DDL drops test tables.
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.execute("DROP TABLE IF EXISTS lab_items");
            s.execute("DROP TABLE IF EXISTS lab_account");

            s.execute("""
                CREATE TABLE lab_account (
                    id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL
                )
                """);
            s.execute("""
                INSERT INTO lab_account(id, balance) VALUES (1, 100)
                """);

            s.execute("""
                CREATE TABLE lab_items (
                    id INTEGER PRIMARY KEY,
                    category VARCHAR(20) NOT NULL
                )
                """);
            s.execute("""
                INSERT INTO lab_items(id, category) VALUES (1, 'READY')
                """);
        }
    }

    private static void verifyConnections(DataSource ds)
            throws SQLException {
        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            int pidA = number(a, "SELECT pg_backend_pid()");
            int pidB = number(b, "SELECT pg_backend_pid()");

            System.out.println(
                "[lab] distinct-backends=" + (pidA != pidB));
        }
    }

    private static void dirtyRead(DataSource ds) throws SQLException {
        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            // A is reader, B is writer.
            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_UNCOMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            setBalance(b, 200);    // B has not committed.
            int seen = balance(a); // PostgreSQL does not read dirty value.

            b.rollback();          // Discard B's uncommitted change.
            int afterRollback = balance(a);

            a.rollback();

            System.out.printf(
                "[lab] dirty READ_UNCOMMITTED (PostgreSQL): "
                    + "seen=%d, afterRollback=%d%n",
                seen, afterRollback);
        }
    }

    private static void nonRepeatableRead(
            DataSource ds, int isolation, String label)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(isolation);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            // The first SELECT establishes A's snapshot.
            int first = balance(a);

            setBalance(b, 120);
            b.commit();            // B commits between the two SELECTs.

            int second = balance(a); // Same query, same A/T1.
            a.rollback();

            System.out.printf(
                "[lab] non-repeatable %s: first=%d, second=%d%n",
                label, first, second);
        }
    }

    private static void phantomRead(
            DataSource ds, int isolation, String label)
            throws SQLException {

        resetItems(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(isolation);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            int first = countReady(a);

            try (PreparedStatement p = b.prepareStatement("""
                    INSERT INTO lab_items(id, category)
                    VALUES (?, ?)
                    """)) {
                p.setInt(1, 2);
                p.setString(2, "READY");
                p.executeUpdate();
            }
            b.commit();             // Add committed phantom row.

            int second = countReady(a);
            a.rollback();

            System.out.printf(
                "[lab] phantom %s: first=%d, second=%d%n",
                label, first, second);
        }
    }

    private static void lostUpdate(DataSource ds)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            int firstA = balance(a); // A remembers 100 in Java.
            int firstB = balance(b); // B also remembers 100.

            setBalance(b, firstB + 20); // Writes 120.
            b.commit();

            // Writes from stale value 100+10, overwriting 120.
            setBalance(a, firstA + 10);
            a.commit();

            int finalBalance = freshBalance(ds);
            System.out.printf(
                "[lab] lost-update READ_COMMITTED: "
                    + "firstA=%d, firstB=%d, final=%d%n",
                firstA, firstB, finalBalance);
        }
    }

    private static void atomicIncrement(DataSource ds)
            throws SQLException {

        resetAccount(ds);

        try (Connection a = ds.getConnection();
             Connection b = ds.getConnection()) {

            a.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            b.setTransactionIsolation(
                Connection.TRANSACTION_READ_COMMITTED);
            a.setAutoCommit(false);
            b.setAutoCommit(false);

            // Both can read 100, yet DO NOT use
            // the old value as the write parameter.
            balance(a);
            balance(b);

            addToBalance(b, 20);
            b.commit();
            addToBalance(a, 10);
            a.commit();
        }

        System.out.println(
            "[lab] atomic-increment READ_COMMITTED: final="
                + freshBalance(ds));
    }

    private static void resetAccount(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.executeUpdate(
                "UPDATE lab_account SET balance = 100 WHERE id = 1");
        }
    }

    private static void resetItems(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection();
             Statement s = c.createStatement()) {
            s.executeUpdate("DELETE FROM lab_items");
            s.executeUpdate("""
                INSERT INTO lab_items(id, category)
                VALUES (1, 'READY')
                """);
        }
    }

    private static void setBalance(Connection c, int value)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement("""
                UPDATE lab_account SET balance = ? WHERE id = 1
                """)) {
            p.setInt(1, value);
            p.executeUpdate();
        }
    }

    private static void addToBalance(Connection c, int increment)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement("""
                UPDATE lab_account
                SET balance = balance + ?
                WHERE id = 1
                """)) {
            p.setInt(1, increment);
            p.executeUpdate();
        }
    }

    private static int freshBalance(DataSource ds)
            throws SQLException {
        try (Connection c = ds.getConnection()) {
            return balance(c);
        }
    }

    private static int balance(Connection c) throws SQLException {
        return number(
            c, "SELECT balance FROM lab_account WHERE id = 1");
    }

    private static int countReady(Connection c)
            throws SQLException {
        return number(c, """
            SELECT COUNT(*) FROM lab_items
            WHERE category = 'READY'
            """);
    }

    private static int number(Connection c, String sql)
            throws SQLException {
        try (Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(sql)) {
            if (!rs.next()) {
                throw new SQLException(
                    "Query did not return a row: " + sql);
            }
            return rs.getInt(1);
        }
    }
}
```

### 6.1. Why does this code satisfy "two connections"?

Each measurement opens:

```java
try (Connection a = ds.getConnection();
     Connection b = ds.getConnection()) {
    // Schedule coordinating two transactions.
}
```

Two connections are acquired simultaneously and held until the end of the measurement. `verifyConnections(...)` uses PostgreSQL's `pg_backend_pid()` function to confirm **two distinct backend sessions** exist in the demo.

Both A and B call `setAutoCommit(false)` so they do not auto-commit after each statement. The application itself decides when B commits/rolls back and when A re-reads.

Data-reset operations run on a separate reset connection **before** A/B start the next experiment. They auto-commit per pool settings. Thus:

- Non-repeatable read always starts from `balance=100`.
- Phantom read always starts from **one** `READY` row.
- Lost update and atomic increment both start from `balance=100`.

The program does not use `Thread.sleep`; it does not wait for "just the right moment" to succeed.

### 6.2. Run command

Make sure the PostgreSQL container is ready. In the directory containing `pom.xml`:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

If Spring Initializr did not generate a Maven Wrapper, install Maven and run `mvn spring-boot:run`.

### 6.3. Expected printed output

Besides Spring/Maven logs, the program prints these lines:

```text
[lab] distinct-backends=true
[lab] dirty READ_UNCOMMITTED (PostgreSQL): seen=100, afterRollback=100
[lab] non-repeatable READ_COMMITTED: first=100, second=120
[lab] non-repeatable REPEATABLE_READ: first=100, second=100
[lab] phantom READ_COMMITTED: first=1, second=2
[lab] phantom REPEATABLE_READ: first=1, second=1
[lab] lost-update READ_COMMITTED: firstA=100, firstB=100, final=110
[lab] atomic-increment READ_COMMITTED: final=130
```

These numbers are based on **PostgreSQL with JDBC, the schema, and the code's operation schedule**, not a claim for every DBMS. If triggers, different data, or code/isolation changes exist, re-analyze accordingly.

### 6.4. Reading the result of each measurement

**`distinct-backends=true`:** the two concurrent `Connection`s have different backend process IDs. This rules out the mistake of holding two Java variables that actually operate on the same connection/transaction.

**Dirty read:** B writes uncommitted 200; A requests `READ_UNCOMMITTED`, yet PostgreSQL treats it as `READ_COMMITTED`. A still sees 100; after B rolls back, A still sees 100. This is **proof the phenomenon is prevented**, not that "the dirty read test didn't run."

**Non-repeatable, READ_COMMITTED:** A sees 100 first; B commits 120; A sees 120 on the second read. Two reads of the same row inside the same T1 return two different values.

**Non-repeatable, REPEATABLE_READ:** A sees 100 both times even though B committed 120. A retains its old snapshot; to see 120 under a new snapshot, T1 must end and a new transaction must open.

**Phantom, READ_COMMITTED:** first `COUNT READY=1`; B inserts another READY row and commits; A counts 2.

**Phantom, REPEATABLE_READ:** A still counts 1 because PostgreSQL uses a consistent transaction snapshot. This **does not contradict the SQL standard**: the standard permits a DB to provide stronger guarantees than the minimum.

**Lost update:** A and B both read 100; B writes 120 first; A sends 110 computed from stale data in Java. Final result is 110, losing B's +20 effect.

**Atomic increment:** A and B can still read the old value, yet `UPDATE balance = balance + ?` does not use the client's cached copy of 100. B adds 20, then A adds 10 to the current value, resulting in 130.

### 6.5. Why does the code not use two threads?

Because the immediate goal is **reproducibility of the phenomenon**, not a throughput benchmark. Two database transactions can coexist even when Java sends commands alternately on one thread:

```text
Java thread       Connection A / T1      Connection B / T2
    |                    |                       |
    |--- SELECT -------->|                       |
    |                    |                       |
    |--- UPDATE --------------------------------->|
    |--- COMMIT --------------------------------->|
    |                    |                       |
    |--- SELECT -------->|                       |
    v                    v                       v
```

When you need to test blocking, deadlocks, lock-wait timeouts, or real races, use two threads with `CountDownLatch` or two `psql` sessions, with timeouts and cleanup. Never use `sleep` as the sole synchronization condition, because faster/slower machines produce different schedules.

## 7. Manual design via two psql windows

The Java program is the automated approach. For visual instruction, using **two SQL terminals** is also helpful because learners see exactly which statement runs on each connection.

Open terminal A:

```bash
docker exec -it spring-isolation-lab psql -U lab -d isolation_lab
```

Open terminal B with **a second identical command**:

```bash
docker exec -it spring-isolation-lab psql -U lab -d isolation_lab
```

Each terminal opens a separate PostgreSQL session. You can run:

```sql
SELECT pg_backend_pid();
SHOW transaction_isolation;
```

To observe non-repeatable read on schedule:

**Terminal A — run first:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM lab_account WHERE id = 1;
```

**Terminal B — run after A's SELECT:**

```sql
BEGIN;
UPDATE lab_account SET balance = 120 WHERE id = 1;
COMMIT;
```

**Terminal A — run again:**

```sql
SELECT balance FROM lab_account WHERE id = 1;
ROLLBACK;
```

If your starting state is no longer 100, reset `lab_account` back to 100 **outside any open transaction** before starting. To compare REPEATABLE READ, reset data again and replace `BEGIN ISOLATION LEVEL READ COMMITTED` in A with `BEGIN ISOLATION LEVEL REPEATABLE READ`, keeping the rest of the schedule identical.

### Result log sheet

| Test ID | DBMS/version | Isolation A | A read 1 | B's action | B ends | A read 2 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NR-1 | PostgreSQL 16 | READ COMMITTED | 100 | UPDATE 120 | COMMIT | 120 | Non-repeatable |
| NR-2 | PostgreSQL 16 | REPEATABLE READ | 100 | UPDATE 120 | COMMIT | 100 | Stable snapshot |
| PH-1 | PostgreSQL 16 | READ COMMITTED | COUNT=1 | INSERT READY | COMMIT | COUNT=2 | Phantom |
| PH-2 | PostgreSQL 16 | REPEATABLE READ | COUNT=1 | INSERT READY | COMMIT | COUNT=1 | Phantom prevented |
| DR-1 | PostgreSQL 16 | READ UNCOMMITTED | 100 | UPDATE 200 | Uncommitted → ROLLBACK | 100 | No dirty read |
| LU-1 | PostgreSQL 16 | READ COMMITTED | 100 | B writes 120, commits | COMMIT | A stale-writes 110 | Lost update |

These rows are **expected templates** for the exact schedule, not results you have already run in your own environment. When running yourself, record actual transaction IDs, logs, and SQLSTATE if results differ.

## 8. Why might some experiments fail to show the phenomenon?

### 8.1. B commits too early

If in a non-repeatable or phantom experiment you let B commit **before A's first read**, A under REPEATABLE_READ may acquire a snapshot already seeing the new data, so both reads return the same value. That is not proof that the phenomenon is prevented under READ_COMMITTED; you altered the schedule.

**Fix:** always enforce a checkpoint `A.R1 done` before letting B commit, and only then run `A.R2`.

### 8.2. A has auto-commit enabled

If A has `autoCommit=true`, each SELECT finishes in its own transaction. Then the measurement "two reads inside the same T1" no longer holds, even if the two SELECTs return different values.

**Fix:** call `setAutoCommit(false)` before the first SELECT and only `commit/rollback` A after the second SELECT.

### 8.3. Reusing the same connection

If A and B are just two variables pointing to the same connection, A's SELECT can see that connection's own uncommitted changes. That is **read-your-own-writes**, not a dirty read between two transactions.

**Fix:** open two connections simultaneously and verify session identity; in PostgreSQL, use `pg_backend_pid()`.

### 8.4. The DBMS prevents the phenomenon

You cannot force PostgreSQL to produce a dirty read by requesting `READ_UNCOMMITTED`: PostgreSQL behaves like READ_COMMITTED. Nor can you use PostgreSQL REPEATABLE_READ to "prove phantoms never happen at that level in any system," because PostgreSQL blocks phantoms.

**Fix:** distinguish **phenomena permitted by the standard** from **phenomena exhibited by a specific DBMS**, and state the DBMS explicitly in conclusions.

### 8.5. The test runs inside a Spring transaction

If a test has `@Transactional` on the test method or calls through a transactional service, JDBC/repository calls may reuse the thread-bound connection from the outer transaction. Then code that looks like multiple transactions is actually coordinated differently by the transaction manager.

**Fix:** for manual labs, run inside an entry point **without a transaction** and acquire two JDBC connections directly; for Spring annotation tests, wire two Spring beans/proxies and proper thread orchestration.

### 8.6. Reading ORM cache instead of DB data

JPA/Hibernate has a first-level persistence context; calling `EntityManager.find(...)` twice can return the cached managed entity even if the database at READ_COMMITTED already holds a new value.

**Fix:** to observe pure database isolation, use direct JDBC SELECTs as in this lesson. When testing an ORM, use `clear/refresh` deliberately and note persistence-context behavior rather than mistaking cache behavior for an isolation-level property.

### 8.7. Lock contention causes the test to hang

A bad schedule might have B try to UPDATE a row locked by A or make T2 wait for T1 to commit while Java is waiting on T2. The program then blocks instead of printing output.

**Fix:** in pure read tests, use plain SELECTs **without FOR UPDATE**; let writer B commit before the re-read, and do not make B wait on a lock A has not released. For locks and deadlocks, build a separate experiment with timeouts and multiple threads.

### 8.8. Not resetting data between measurements

If the previous phantom test inserted READY id=2, the next test starts with altered input data. You may see an initial COUNT=2 instead of 1 and draw the wrong conclusion.

**Fix:** run and commit a dedicated reset function **before opening A/B**, like `resetItems(...)` in the code.

## 9. Observing a real dirty read on another DBMS

In PostgreSQL, section 6's dirty read experiment must print `seen=100`. If a training goal strictly requires **observing uncommitted 200**, run a separate lab on a DBMS with a real `READ UNCOMMITTED` mechanism.

Illustrative sequence **for MySQL/InnoDB** assuming table `lab_account(id,balance)` already exists with row `(1,100)`:

**Session A — reader:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;
-- Pause here and let B UPDATE before running the query below.
SELECT balance FROM lab_account WHERE id = 1;
```

**Session B — writer:**

```sql
START TRANSACTION;
UPDATE lab_account SET balance = 200 WHERE id = 1;
-- Not COMMITTED yet: keep transaction B open.
```

Return to session A and run SELECT again inside A's transaction. In a configuration supporting dirty reads, A **may** see uncommitted 200.

Then in session B:

```sql
ROLLBACK;
```

Then in A:

```sql
SELECT balance FROM lab_account WHERE id = 1;
ROLLBACK;
```

A can see 100 again after B rolls back. This **demo depends on MySQL/InnoDB and version settings**; verify it yourself. In production, `READ_UNCOMMITTED` should never be chosen merely because an anomaly is "interesting" to observe.

Important: if application-side caching is active, SELECT no longer carries the same semantics; use raw connections/SQL to observe transaction isolation.

## 10. Connecting to Spring @Transactional(isolation = ...)

Spring declares transaction isolation on service methods:

```java
@Service
public class AccountReadService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void inspectAccount() {
        // JDBC/JPA statements using the right DataSource/manager
        // for this transaction will be governed by its isolation level.
    }
}
```

This is an **illustrative snippet**, requiring imports for `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.transaction.annotation.Propagation`, `org.springframework.transaction.annotation.Isolation`, plus a DAO implementation.

### Conditions for the isolation attribute to take effect

1. The call must pass through a **Spring transaction proxy** or corresponding transactional interception mechanism. `this.inspectAccount()` inside the same bean in proxy mode can bypass the interceptor.
2. `PlatformTransactionManager` must manage the exact datasource/connection used by the SQL statements.
3. The `isolation` attribute of `@Transactional` primarily applies to **a newly created transaction** under propagations such as `REQUIRED` when no transaction exists and `REQUIRES_NEW`. If the method merely **joins an existing outer transaction**, a local isolation declaration normally **does not alter the outer transaction's isolation**.
4. With multiple managers, specify `@Transactional(transactionManager="...")` to avoid targeting the wrong resource.
5. The DBMS may enforce stronger guarantees than the standard's minimum. For example, annotating `Isolation.READ_UNCOMMITTED` on PostgreSQL does not make PostgreSQL return dirty reads.

### Manual JDBC in the lab vs. Spring annotations

| Manual JDBC experiment | Declarative Spring application |
| --- | --- |
| `dataSource.getConnection()` twice | Spring beans/transaction manager choose the appropriate connection |
| `a.setTransactionIsolation(...)` before transaction | `@Transactional(isolation = ...)` declares policy |
| `a.setAutoCommit(false)` | Manager starts the transaction |
| `a.commit() / a.rollback()` | Interceptor + manager commit/roll back based on outcome and rollback rules |
| Orchestrate R1 → W2 → C2 → R2 in Java | Must orchestrate two transactions/proxies to achieve the same schedule |
| Inspect JDBC state directly | Typically combine JDBC tests, DB state, logging, and transaction metadata |

**Do not mix arbitrarily:** inside a method already managed by `@Transactional`, manually calling `commit()` on a connection obtained via Spring or changing isolation mid-transaction can break Spring's contract. The lab uses **manual connections intentionally outside any transactional method**, not as a production DAO pattern.

### If you want to test with real @Transactional

A test architecture can include:

- A non-transactional `Coordinator` driving the test schedule.
- Two worker Spring beans with `@Transactional(propagation = REQUIRES_NEW, isolation = ...)` methods.
- Barriers/locks allowing **both workers to hold open transactions simultaneously**, typically requiring two threads because each annotated method auto-commits on return.
- `CountDownLatch` to ensure A runs its first SELECT before B UPDATEs/COMMITs, and only then A runs its second SELECT.

Be careful: if method A returns after its first SELECT, transaction A has **already ended**, so the later SELECT is no longer in the same transaction. To demonstrate a non-repeatable read, both R1 and R2 must sit **inside the same transactional call A** while B gets a chance to commit in between. That is why single-threaded manual two-connection JDBC testing is easier for beginners to reproduce.

## 11. Advanced exercise: write skew and SERIALIZABLE

This is a **self-directed exercise using two PostgreSQL terminals**, not part of section 6's program stdout. Its goal is showing that "no dirty/non-repeatable/phantom reads" is still **not enough to prove a schedule is serializable**.

### 11.1. Initial data

Use a terminal with no open transaction:

```sql
DROP TABLE IF EXISTS lab_doctors;

CREATE TABLE lab_doctors (
    id INTEGER PRIMARY KEY,
    on_call BOOLEAN NOT NULL
);

INSERT INTO lab_doctors(id, on_call)
VALUES (1, TRUE), (2, TRUE);
```

Business invariant: **at least one doctor must be on call**.

### 11.2. Two sessions at REPEATABLE READ

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM lab_doctors WHERE on_call = TRUE;
-- Result: 2. Keep transaction A open.
```

**Session B (before A UPDATEs):**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM lab_doctors WHERE on_call = TRUE;
-- Result: 2. Keep transaction B open.
```

After **both SELECTs have returned 2**:

**Session A:**

```sql
UPDATE lab_doctors SET on_call = FALSE WHERE id = 1;
```

**Session B:**

```sql
UPDATE lab_doctors SET on_call = FALSE WHERE id = 2;
```

The two transactions modify **two different rows**, so PostgreSQL REPEATABLE READ can let both finish:

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
COMMIT;
```

Verify in a session outside the transactions:

```sql
SELECT COUNT(*) AS remaining_on_call
FROM lab_doctors WHERE on_call = TRUE;
```

**The result can be 0**, violating the "at least one on call" invariant. This is **write skew / serialization anomaly**: T1 and T2 each decided on a valid individual snapshot, yet the combined result is not equivalent to any serial execution respecting the check.

### 11.3. Re-trying with SERIALIZABLE

Reset the table:

```sql
UPDATE lab_doctors SET on_call = TRUE;
```

Re-open both transactions with:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

Run **the same schedule**: both SELECT COUNT see 2, each transaction UPDATEs a different row, then both try to COMMIT.

In PostgreSQL, the engine can detect a serializability conflict and **one transaction fails to commit**, usually reporting SQLSTATE `40001` with a serialization failure message. Never hardcode that A or B specifically will fail; the choice can depend on execution timing and conflict detection order.

After rolling back/cleaning up the failed transaction, normally **at least one doctor remains on call** from the committed changes. The application must have a strategy to **retry the entire transaction** that hit serialization failure, including the read checking the invariant, not merely retrying the final UPDATE.

### 11.4. Limits of the example

- This demonstrates an invariant across **two different rows**; using `REPEATABLE_READ` does not lose data in every problem.
- With constraints/locks or a different design protecting the invariant, results can differ.
- Serializable in PostgreSQL **does not guarantee every transaction commits**; it guarantees transactions that **commit successfully** produce an outcome equivalent to some serial order, and may force others to abort/retry.
- When switching to MySQL or SQL Server, snapshot/locking/serializable behavior differs and must be checked in vendor docs.

## 12. Lost update: how to test and how to fix properly

The lab overwrote a value by saving the stale copy in Java:

```java
int aSeen = balance(a);  // 100
int bSeen = balance(b);  // 100

setBalance(b, bSeen + 20); // UPDATE balance = 120
b.commit();

setBalance(a, aSeen + 10); // UPDATE balance = 110
a.commit();
```

This is **an excerpt from the full program**, not a standalone runnable file. The danger lies not in the arithmetic addition itself, but in **overwriting using a stale value**.

### 12.1. Atomic update

```sql
UPDATE lab_account
SET balance = balance + 10
WHERE id = 1;
```

The increment executes on the database side against the current state/lock when the UPDATE runs. In the demo schedule, B adds 20 and commits, then A adds 10 → 130, not 110.

Do not assume an atomic SQL UPDATE solves **every** business condition; if "balance must never go negative" is required, you may also need `WHERE balance >= :amount` and to check the updated row count or add a constraint.

### 12.2. Optimistic locking

Add a `version` column, then write:

```sql
UPDATE lab_account
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?;
```

If A read an old version and B just committed incrementing the version, A's UPDATE affects **0 rows**. The application can detect the conflict and retry **the entire business logic** instead of silently overwriting.

In JPA, `@Version` can be used on suitable entity mappings; you still must handle `OptimisticLockException` and decide whether to retry or fail.

### 12.3. Pessimistic locking and transaction isolation

`SELECT ... FOR UPDATE` can lock rows so two transactions do not concurrently edit from a stale value, at the cost of lock waits and deadlock risk if multiple rows are accessed out of order.

Raising isolation to `SERIALIZABLE` can prevent certain invalid schedules via blocking or aborts depending on the database. Never replace proper concurrency-control design with "just crank isolation to the maximum" without measuring performance and implementing retries.

## 13. Diagnostic questions before drawing conclusions

### Why does PostgreSQL READ_UNCOMMITTED still print 100?

Because PostgreSQL handles that requested level identically to READ_COMMITTED: it does not expose uncommitted data from other transactions. That outcome is not a "broken lab," it is **a documented trait of the DBMS implementation**.

### Why does REPEATABLE_READ still see changes made by T1 itself?

Because a consistent snapshot does not forbid a transaction from seeing **its own changes**. The non-repeatable read experiment here intentionally has **B** modify data while A only SELECTs; if A issues its own UPDATE between R1 and R2, you are measuring read-your-own-writes rather than an anomaly from another transaction.

### Why must both `Connection`s be open at the same time?

To keep transaction A open while B works. If you close A and reopen it before the second SELECT, you no longer have a single transaction A spanning the schedule. With a connection pool, holding both objects open simultaneously also prevents confusion from the pool reusing the same physical connection over time.

### Must transaction B finish before the second SELECT?

For non-repeatable read and phantom experiments at READ_COMMITTED, B must **COMMIT** so A can observe committed changes. If B has not committed, you accidentally shift the experiment into dirty reads or lock visibility—a different test.

### Why did the program work on the first run and fail with duplicate key on the second?

Perhaps you edited the code and removed the reset, or connected to a database containing prior data. The demo's `initialize()` runs `DROP TABLE IF EXISTS lab_*` and recreates the data; verify the exact JDBC URL and ensure the DB is strictly for lab use.

### Why does changing A's isolation after the first SELECT fail to produce the expected result?

Changing isolation **mid-transaction while active** is usually restricted or will not give the old transaction a new snapshot. In the lab, `setTransactionIsolation(...)` is called before `setAutoCommit(false)` and before the first SELECT. To test a new level, **end the current transaction, reset data, and start a fresh transaction**.

### Why can an UPDATE wait?

Because isolation and the lock manager enforce contention control. An ordinary SELECT in PostgreSQL MVCC does not lock rows like `FOR UPDATE`; however, two UPDATEs on the same row, foreign keys, or constraints can require locks. The experiment chooses a schedule avoiding unnecessary waits to isolate the observed variable.

## 14. Criteria checklist for a sound test

A complete lab report should include:

- [ ] Exact **DBMS/version** (PostgreSQL 16 for the main example).
- [ ] Proof that A and B are **two distinct connections**, e.g., `pg_backend_pid()`.
- [ ] Confirmation that `autoCommit=false` for A/B and isolation was set before the transaction.
- [ ] Recorded **initial data S0** and reset before each experiment.
- [ ] Explicit statement ordering for A and B, especially **R1 before B COMMIT, R2 after B COMMIT**.
- [ ] Assurance that R1/R2 ran on **the same connection/transaction A**.
- [ ] Ending A/B with commit or rollback; no connections/transactions left dangling open.
- [ ] Concrete expected output compared against actual numbers.
- [ ] Distinction between anomalies **permitted** by the standard and anomalies **exhibited** by the DBMS.
- [ ] For lost update, comparing final result against expected correct value (110 vs. 130), not merely printing a number.
- [ ] For SERIALIZABLE, handling SQLSTATE `40001` and retrying the entire business transaction when appropriate.
- [ ] When translating to Spring `@Transactional`, verifying proxies, transaction manager, propagation, and where new transactions begin.
- [ ] Not relying on `Thread.sleep` or ORM caches as sole evidence of isolation level.

### Experiment report template

```text
Name: Phantom read
DBMS: PostgreSQL 16
Isolation A: READ COMMITTED
Isolation B: READ COMMITTED
Initial data: READY count = 1
A.R1: SELECT COUNT(*) ... = 1
B.W2: INSERT READY id=2
B.C2: COMMIT succeeded
A.R2: SELECT COUNT(*) ... = 2
A.X1: ROLLBACK (merely ends the read transaction)
Conclusion: PostgreSQL READ COMMITTED allows phantom under this schedule.
Comparison: same schedule with REPEATABLE READ gives 1 -> 1.
```

If results differ, submit **the SQL schedule, auto-commit state, actual isolation, and DBMS** before concluding the code/framework is broken.

## 15. Practice exercises

**Exercise 1.** A opens a READ_COMMITTED transaction and reads balance=100. B UPDATEs balance=150 but **has not committed**. A reads a second time. Does this qualify as a non-repeatable read?

**Answer:** No. Non-repeatable read as defined here requires B's change to be **committed before the re-read**. If A saw 150 while B was uncommitted, that would be a dirty read; PostgreSQL READ_COMMITTED prevents that.

**Exercise 2.** A opens REPEATABLE_READ, but B commits its update **before A executes its first SELECT**. A reads 150 in both SELECTs. Does this prove repeatable read prevents non-repeatable reads?

**Answer:** Not according to the intended verification schedule. A's snapshot was established after B committed, so both reads see 150. You must run A.R1 before B.C2 and then A.R2 for a valid comparison.

**Exercise 3.** Why did PostgreSQL `REPEATABLE_READ` in the demo show no phantoms, even though some SQL textbook tables mark phantoms as "possible"?

**Answer:** The standard table describes minimum guarantees; PostgreSQL implements REPEATABLE_READ with consistent snapshots that are stronger with respect to phantom reads.

**Exercise 4.** Are two Java threads strictly required to construct dirty/non-repeatable/phantom schedules?

**Answer:** No, if two JDBC connections are open simultaneously and one thread sequences statements and commits in order. Two threads or two terminals are needed when measuring real waits/races or when worker transaction code cannot be paused by a single-threaded orchestrator.

**Exercise 5.** In lost update, A reads 100, B adds 20 and commits, and A sends `UPDATE balance=110`. Why does final=110 not mean the DB "added wrong"?

**Answer:** The DB faithfully executed the UPDATE with **the constant 110** supplied by the application. The bug lies in the client's stale read–modify–write, not the database's arithmetic.

**Exercise 6.** A Spring service has `@Transactional(isolation = Isolation.SERIALIZABLE, propagation = REQUIRED)` while joining a caller's transaction already opened at READ_COMMITTED. Will the method automatically upgrade the outer transaction to SERIALIZABLE?

**Answer:** No. In standard Spring transaction management, the isolation annotation of a method joining an existing transaction does not alter the already-open physical transaction. Inspect propagation, transaction manager, and validate-existing-transaction policy.

**Exercise 7.** Two doctors at REPEATABLE_READ both see 2 on call, then each marks a different row off call; both commit. Is this a non-repeatable read?

**Answer:** No. Each read a stable snapshot, yet the combined outcome breaks the invariant. This is write skew / a serialization anomaly, showing why REPEATABLE_READ is not equivalent to SERIALIZABLE in PostgreSQL.

**Exercise 8.** A `@Transactional` integration test calls method A SELECT, then method B UPDATE, then A SELECT again. Why is it hard to know whether two transactions existed?

**Answer:** The calls may have joined **the same transaction opened by the test/caller**, especially when sharing the same transaction manager and `REQUIRED` propagation. Design two explicit physical transactions, two connections, and a clear commit schedule.

## 16. Conclusion

**Good isolation experiment design is two-connection schedule design**, not just changing an annotation value:

1. Reset committed data.
2. Start T1/T2 on two separate physical connections.
3. Set isolation levels before starting.
4. Let A read first, B write and commit/roll back at the exact step, and A re-read on **the same T1**.
5. Close the transactions and compare outcomes per **the actual DBMS**.
6. For write problems, verify **final state and invariants**, not only SELECT values.

In PostgreSQL: `READ_COMMITTED` can exhibit non-repeatable/phantom reads; `REPEATABLE_READ` uses a stable snapshot and prevents both in this experiment; `READ_UNCOMMITTED` produces no dirty reads; `SERIALIZABLE` can raise error 40001 to block non-serializable schedules. When translating this knowledge to Spring `@Transactional`, verify that a **new transaction is opened**, proxies apply the policy, and repositories actually use the managed resource.

### Official documentation

- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/16/transaction-iso.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/16/explicit-locking.html
- PostgreSQL — Handling Serialization Failures: https://www.postgresql.org/docs/16/mvcc-serialization-failure-handling.html
- Spring Framework — `@Transactional` settings, isolation and propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Javadoc — `Isolation` enum: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Isolation.html
- Java SE JDBC — `Connection.setTransactionIsolation(int)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
