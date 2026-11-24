# Dirty read, non-repeatable read, and phantom read in Spring Transaction Management

## 1. Why can the same SELECT statement return different results?

When two or more transactions run concurrently, **reading data** does not depend only on whether the SQL is written correctly. The result also depends on when another transaction modifies or commits data, the *isolation level* of the reading transaction, and the database's implementation mechanisms (MVCC, locking, snapshots).

Three foundational phenomena to distinguish:

- **Dirty read:** reading **uncommitted** data from another transaction; that data may later be rolled back.
- **Non-repeatable read:** reading **the same row** twice within one transaction and receiving different values because another transaction committed an update or delete to that row between the two reads.
- **Phantom read:** re-executing **the same predicate query** and seeing **the matching set of rows change** because another transaction committed inserts, deletes, or updates affecting matching rows.

These phenomena alter business decisions: checking inventory then calculating charges, counting open orders, verifying credit limits then recording a transaction, and so on. Simply adding `@Transactional` without **understanding isolation** does not guarantee that all reads inside a method observe the same database state.

This lesson helps you:

1. Draw timelines for the three anomalies yourself, identifying **who has not committed, who has committed, and which query re-reads**.
2. Understand the minimum guarantees of SQL isolation levels and why the theoretical table **differs** from actual behavior in PostgreSQL/MySQL.
3. Configure `@Transactional(isolation = ...)` in Spring and know the limits of propagation, proxies, and connections.
4. Run a **Java 17 + Spring Boot + PostgreSQL** example using two transactions coordinated with `CountDownLatch` to observe non-repeatable read/phantom at `READ_COMMITTED`, and stability at PostgreSQL `REPEATABLE_READ`.
5. Avoid misconceptions about dirty reads, MVCC, `readOnly`, commits, locks, and `SERIALIZABLE`.

> **Boundary:** These are phenomena caused by **concurrency between transactions**. Re-reading a row after the current transaction's own `UPDATE` statement may show the new value; that is the transaction seeing **its own writes**, not a non-repeatable read caused by another transaction.

## 2. Key terminology to know first

| Term | Meaning in this lesson |
| --- | --- |
| Transaction T1/T2 | Two SQL units of work that can run concurrently on different connections |
| `BEGIN` | Starts a transaction (or establishes its starting boundary, depending on the DB/driver) |
| `COMMIT` | Asks the database to persist the transaction's remaining changes |
| `ROLLBACK` | Discards the transaction's uncommitted changes |
| Isolation level | Rules governing visibility of data state and conflict handling when transactions run concurrently |
| Snapshot | A logical point-in-time view of which data versions a query or transaction is allowed to read |
| MVCC | Multi-Version Concurrency Control: storing/reading multiple versions to support concurrency |
| Locking read | A read that requests an appropriate lock, such as `SELECT ... FOR UPDATE` in some DBs |
| Predicate | A condition defining a set of rows, for example `WHERE status = 'OPEN'` |
| Serialization anomaly | An outcome where multiple committed transactions are not equivalent to **any** serial execution order |

**Isolation does not mean "locking the entire database."** In PostgreSQL/MySQL InnoDB, much of the read behavior is implemented using MVCC; higher isolation does not necessarily turn every SELECT into a lock that blocks every writer. `SERIALIZABLE` may detect conflicts and abort a transaction rather than making all transactions run sequentially in wall-clock time.

## 3. Dirty read: seeing someone else's uncommitted data

Suppose account ID 1 has a committed balance of **100**.

### 3.1. Timeline

```text
Time          T1 (writer)                            T2 (reader)
---------     -----------------------------------    --------------------------
t0            (DB currently has balance=100)
t1            BEGIN
t2            UPDATE account SET balance=900
              WHERE id=1
              -- 900 NOT COMMITTED YET
t3                                                   BEGIN (READ UNCOMMITTED)
t4                                                   SELECT balance ... -> 900 (*)
t5            ROLLBACK
              -- DB returns to 100
t6                                                   T2 already used value 900
t7                                                   COMMIT/ROLLBACK T2
```

The `(*)` mark only happens if **the database and isolation level actually allow reading dirty values**. T2 has already used the value 900 that was never committed; if it uses it to decide on a transfer or credit limit, that decision rests on an unpersisted state.

**The core of a dirty read:** T2 reads **before T1 commits**. If T1 has already committed and T2 reads again and sees 900, that is **not** a dirty read, even though the value differs from before.

### 3.2. Why T1's rollback does not "undo" decisions T2 already made

`ROLLBACK` reverts T1's uncommitted SQL changes, but it does not automatically retract data that T2 already copied into Java variables, caches, HTTP responses, events, or logs. A fee calculation based on 900 may have already been sent out before T1 rolled back. Thus, reading dirty values makes applications prone to incorrect business behavior even when the database ultimately keeps the balance at 100.

### 3.3. Can PostgreSQL be used to reproduce a dirty read?

**No.** Modern PostgreSQL accepts a request for `READ UNCOMMITTED` but executes it as `READ COMMITTED`. T2 will **not** see T1's uncommitted data; in the timeline above, a normal SELECT by T2 returns 100 rather than 900.

Therefore, a test that "enables `Isolation.READ_UNCOMMITTED` in Spring + PostgreSQL and sees no dirty read" **is not proof that Spring ignored the annotation**; this is PostgreSQL's semantics.

If you need to test the dirty read phenomenon, use a DB that actually supports it, such as **MySQL InnoDB** with `READ UNCOMMITTED` and two connections/sessions. This level should not be used for decisions that require trustworthy data.

### 3.4. Dirty read vs. dirty write

- **Dirty read:** T2 **reads** T1's uncommitted change.
- **Dirty write:** T2 **overwrites** T1's uncommitted change before T1 finishes, which is a different situation and is typically blocked by the DB using locks.

Do not take "a transaction gets blocked on UPDATE" as proof that dirty reads are necessarily allowed or blocked. Reads and writes can have different concurrency policies.

## 4. Non-repeatable read: same row, two different committed values

Scenario: T1 reads the balance for ID 1 as 100. While T1 **is still open**, T2 updates the balance to 200 and **commits**. T1 reads **the exact same row** again and gets 200.

### 4.1. Standard timeline

```text
Time          T1 (reader)                              T2 (writer)
---------     -------------------------------------    ------------------------
t0            (balance=100 already committed)
t1            BEGIN ISOLATION LEVEL READ COMMITTED
t2            SELECT balance WHERE id=1 -> 100
t3                                                     BEGIN
t4                                                     UPDATE ... balance=200
t5                                                     COMMIT
t6            SELECT balance WHERE id=1 -> 200
t7            COMMIT
```

T1 has not finished yet, but **two identical SELECT statements** return different results because **another transaction committed** in between. This is a non-repeatable read.

Identifying conditions:

1. There are at least two reads of the same identifiable data (for example, the same `WHERE id=1`) within **one transaction T1**.
2. T2 commits the change between the two reads.
3. T1 sees a different version when reading again.

If T1 commits after the first SELECT and then opens a different transaction to read again, those are **two independent transactions**, not a non-repeatable read inside a single transaction.

### 4.2. Business impact

A flow:

```text
T1: read balance = 100
T1: check sufficient funds to spend 80
T2: subtract 50 and commit, balance = 50
T1: read balance again = 50
```

If T1 calculates based on the first read of 100 and still writes under the old assumption, business logic errors or lost updates can occur depending on how the SQL and locking are written. **Non-repeatable read and lost update are two distinct phenomena**; raising isolation does not replace atomic SQL updates, optimistic locking/version checks, or appropriate conflict-handling mechanisms.

### 4.3. READ_COMMITTED in PostgreSQL

In PostgreSQL, each statement under `READ COMMITTED` uses a snapshot that sees changes committed **before the statement began**, along with the transaction's own writes. After T2 commits, **a new SELECT statement** in T1 can see the value 200. However, if T2 has not committed when the second SELECT begins, that SELECT continues to see the previously committed value.

Do not interpret "READ_COMMITTED" as "all SELECTs in the same transaction read a single snapshot." It only prevents reading uncommitted data from other transactions; non-repeatable reads and phantoms can still occur.

## 5. Phantom read: same condition, different set of rows

Suppose the `orders` table currently has **1** order in the `OPEN` state.

T1 needs to count the open orders:

```sql
SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
```

While T1 has not finished, T2 creates another `OPEN` order and commits:

```sql
INSERT INTO orders(id, status) VALUES (2, 'OPEN');
```

T1 runs the SELECT statement again with the same condition.

### 5.1. Timeline

```text
Time          T1 (predicate reader)                    T2 (inserter)
---------     -------------------------------------    ------------------------
t0            (id=1, status='OPEN' already committed)
t1            BEGIN ISOLATION LEVEL READ COMMITTED
t2            COUNT(*) WHERE status='OPEN' -> 1
t3                                                     BEGIN
t4                                                     INSERT (id=2,'OPEN')
t5                                                     COMMIT
t6            COUNT(*) WHERE status='OPEN' -> 2
t7            COMMIT
```

T1 **did not change the WHERE condition**, yet the result set changed because another transaction committed an added row that matches the condition. That new row is commonly called a **phantom row**.

A clearer way to observe this than `COUNT(*)` is executing twice:

```sql
SELECT id FROM orders WHERE status='OPEN' ORDER BY id;
```

The first execution returns `[1]`, and the second returns `[1, 2]` within the same T1. If a row is deleted or transitions to a state that no longer matches the predicate, the set can also shrink.

### 5.2. Distinguishing from non-repeatable read

| Question | Non-repeatable read | Phantom read |
| --- | --- | --- |
| What is being re-read? | **An already identified row** (specific ID) | **A predicate query** returning a set of rows |
| Typical change from T2 | `UPDATE account SET balance=200 WHERE id=1` | `INSERT order(status='OPEN')`; or DELETE/UPDATE changing the matching set |
| Easily observed result | `balance: 100 → 200` | `COUNT(*) 1 → 2`, or the list of IDs changes |
| Illustrative query | `SELECT balance WHERE id=1` | `SELECT id WHERE status='OPEN'` |
| Key characteristic | The value of an existing row changed between two reads | The set of rows matching the predicate changed |

A predicate query can also witness the values of existing rows changing; in that case, the phenomena may overlap in observation. To study and test the two types separately, use **an identified row for non-repeatable** and **a newly inserted row for phantom**, as in the examples above.

### 5.3. Why are phantoms dangerous?

Operations such as "ensure no more than 10 open orders," "no overlapping bookings in the same time slot," or "no unpaid invoices" typically rely on **results matching a condition**, not just reading a single ID. If you check and insert based on an assumption without suitable constraints/locking/serialization, two transactions can each observe a valid set of rows and then both write, creating a business invariant violation.

This is where you need to evaluate **database constraints**, transaction isolation, row/range/predicate locking, or optimistic concurrency. Do not assume simply switching to `REPEATABLE_READ` is always enough to prevent all **write skew** or guarantee invariants across all DBs.

## 6. Isolation table by **SQL standard minimum guarantees**

The four isolation level names and three phenomena can be summarized as follows:

| SQL isolation level | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | **Possible** | **Possible** | **Possible** |
| `READ COMMITTED` | **No** | **Possible** | **Possible** |
| `REPEATABLE READ` | **No** | **No** | **Possible per standard** |
| `SERIALIZABLE` | **No** | **No** | **No** |

**Reading the table properly:** "Possible" means **the standard permits the phenomenon**, not that every DB must produce it or that every test run will reproduce it. A DB is allowed to **provide stronger guarantees than the minimum**. Beyond these three phenomena, there are write skew, serialization anomalies, and other lock/read interactions; the table above **is not a proof** that all business logic is serializable.

A way to remember:

- `READ UNCOMMITTED`: permitted to see uncommitted values if the DB implements this level as specified.
- `READ COMMITTED`: eliminates dirty reads, though two separate SELECT statements can see newer committed versions.
- `REPEATABLE READ`: stable when re-reading rows already read, but **the SQL standard permits** phantoms; DB behavior may be stricter.
- `SERIALIZABLE`: successfully committed transactions must be equivalent to a valid serial execution order; the DB may block, wait, or abort transactions on conflict.

In Spring, `Isolation.READ_COMMITTED` and similar enum values are **requests sent to the transaction manager/driver**; the actually supported level and behavior depend on the database.

## 7. **Actual** behavior of PostgreSQL and MySQL InnoDB

### 7.1. PostgreSQL: READ_UNCOMMITTED is treated as READ_COMMITTED

PostgreSQL accepts four level names when requested, but actually implements three distinct levels:

| Requested level in PostgreSQL | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` (handled as `READ COMMITTED`) | No | Possible | Possible |
| `READ COMMITTED` | No | Possible | Possible |
| `REPEATABLE READ` | No | No | **No** |
| `SERIALIZABLE` | No | No | No; additionally prevents serialization anomalies |

Specifically, PostgreSQL `REPEATABLE READ` relies on the snapshot of **the first non-transaction-control statement** in the transaction. Subsequent plain SELECT statements see that same snapshot (plus changes made by the transaction itself), so **phantoms committed by other transactions do not appear** for the kind of reads shown in this lesson.

This **does not contradict** the standard table: the standard only specifies minimum requirements; PostgreSQL is allowed to be stronger. Even so, PostgreSQL's `REPEATABLE READ` **can still exhibit serialization anomalies** such as write skew. When all committed transactions must be equivalent to serial execution, consider `SERIALIZABLE` and be prepared to handle `serialization_failure`/retries.

PostgreSQL's default level is `READ COMMITTED`. In Spring, `Isolation.DEFAULT` typically means using the default of the DB/transaction manager—**it does not default to SERIALIZABLE or REPEATABLE_READ**.

### 7.2. MySQL InnoDB: snapshot reads and locking reads are not the same

InnoDB's default is typically `REPEATABLE READ`. For **plain consistent SELECT** (non-locking reads), reads within the same transaction use the snapshot established by the first consistent read; phantoms caused by another transaction's inserts typically **do not appear in that plain SELECT sequence**.

However, `SELECT ... FOR UPDATE`/`FOR SHARE`, `UPDATE`, and `DELETE` are operations with different locking and/or current-read semantics. InnoDB uses **next-key locks/gap locks** in range-locking cases at `REPEATABLE READ` to restrict inserts that would cause phantoms within the locked range. If you mix consistent non-locking reads with locking reads/DML in the same transaction, you may observe data states that do not belong to the same logical snapshot.

Therefore, you cannot look at the standard table and flatly assert "MySQL REPEATABLE READ always sees phantoms," nor the opposite—"every MySQL REPEATABLE READ query behaves identically and cannot have other concurrency issues." You must analyze **the SELECT type, indexes, predicates, locks, and MySQL version**.

### 7.3. Summary of differences

| Comparison point | PostgreSQL | MySQL InnoDB |
| --- | --- | --- |
| Common default level | `READ COMMITTED` | `REPEATABLE READ` |
| `READ UNCOMMITTED` | Treated as `READ COMMITTED` | Actually supports `READ UNCOMMITTED` |
| `REPEATABLE READ`, plain SELECT | Stable transaction snapshot; no phantoms from T2 | Snapshot from first consistent read; typically no phantoms from T2 |
| Locking / locking read | Depends on isolation and statement; may wait/differ in snapshot | Next-key/gap locks are important in range locking |
| `SERIALIZABLE` | Conflict detection mechanism; may abort with SQLSTATE `40001` | Distinct locking/serialization semantics; may block/timeout/deadlock |

Do not replace testing on the production database engine with conclusions drawn solely from Spring's `Isolation` enum name or results on H2.

## 8. Hands-on practice with two psql windows on PostgreSQL

The following steps are for a **dedicated practice database** and **two separate connections/sessions**. Do not run data-reset statements in an environment with data that must be preserved.

Assuming PostgreSQL is running, open **Session A** and **Session B** (two separate terminals/psql windows). Run the setup **once when neither session has an open transaction**:

```sql
CREATE TABLE IF NOT EXISTS isolation_accounts (
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS isolation_orders (
    id INTEGER PRIMARY KEY,
    state VARCHAR(12) NOT NULL
);

TRUNCATE TABLE isolation_accounts, isolation_orders;

INSERT INTO isolation_accounts(id, balance) VALUES (1, 100);
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

This is **PostgreSQL** SQL for a sandbox lab; `TRUNCATE` deletes all rows in the two specified tables. For databases with foreign keys, truncate order and rules differ; do not run arbitrarily on a database in use.

### 8.1. Non-repeatable read at READ COMMITTED

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM isolation_accounts WHERE id = 1;
-- 100
```

Keep A open. **Session B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 200 WHERE id = 1;
COMMIT;
```

Return to **Session A:**

```sql
SELECT balance FROM isolation_accounts WHERE id = 1;
-- 200
COMMIT;
```

A read the same ID 1 twice in the same transaction, yielding 100 and then 200. The essential condition is that B commits **between the two SELECTs**.

### 8.2. Phantom read at READ COMMITTED

Before the test, reset the orders table in **a session with no open transaction**:

```sql
TRUNCATE TABLE isolation_orders;
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT id FROM isolation_orders
WHERE state = 'OPEN' ORDER BY id;
-- id = 1
```

**Session B:**

```sql
BEGIN;
INSERT INTO isolation_orders(id, state) VALUES (2, 'OPEN');
COMMIT;
```

**Session A:**

```sql
SELECT id FROM isolation_orders
WHERE state = 'OPEN' ORDER BY id;
-- id = 1, 2
COMMIT;
```

A sees a **new row matching the same WHERE clause**, illustrating a phantom read. You can replace the SELECT with `COUNT(*)` to observe 1 then 2.

### 8.3. REPEATABLE READ preserves the old snapshot

Reset the data before starting:

```sql
TRUNCATE TABLE isolation_accounts, isolation_orders;
INSERT INTO isolation_accounts(id, balance) VALUES (1, 100);
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM isolation_accounts WHERE id = 1;
-- 100
SELECT COUNT(*) FROM isolation_orders WHERE state = 'OPEN';
-- 1
```

**Session B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 200 WHERE id = 1;
INSERT INTO isolation_orders(id, state) VALUES (2, 'OPEN');
COMMIT;
```

**Session A continues:**

```sql
SELECT balance FROM isolation_accounts WHERE id = 1;
-- Still 100
SELECT COUNT(*) FROM isolation_orders WHERE state = 'OPEN';
-- Still 1
COMMIT;
```

After A commits and **starts a new query/transaction**, you can see `balance=200`, `COUNT=2`. PostgreSQL `REPEATABLE READ` does not mean the entire database is frozen: B **actually committed**, but A's snapshot does not advance to read the version B just committed.

### 8.4. Trying READ UNCOMMITTED on PostgreSQL

Reset balance to 100 and use two sessions:

**B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 900 WHERE id = 1;
-- Not COMMITTED/ROLLED BACK yet.
```

**A:**

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT balance FROM isolation_accounts WHERE id = 1;
-- PostgreSQL returns the committed value prior to B's UPDATE, e.g., 100.
COMMIT;
```

**B:**

```sql
ROLLBACK;
```

This exercise intentionally demonstrates **no dirty read in PostgreSQL**, not a successful dirty read example. To reproduce a real dirty read, you need a database engine with different semantics.

## 9. Configuring Spring `@Transactional(isolation = ...)`

In Spring, the `org.springframework.transaction.annotation.Isolation` enum includes:

```java
Isolation.DEFAULT
Isolation.READ_UNCOMMITTED
Isolation.READ_COMMITTED
Isolation.REPEATABLE_READ
Isolation.SERIALIZABLE
```

Service configuration example:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountQueryService {

    @Transactional(
        isolation = Isolation.READ_COMMITTED,
        readOnly = true
    )
    public void readLatestCommittedValues() {
        // JdbcTemplate or JPA queries inside this transaction.
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void readConsistentSnapshot() {
        // Reads against the same snapshot, depending on DB implementation.
    }
}
```

This is an **illustrative snippet**, not a standalone program; to run it, you must declare beans and data access code. `isolation` is applied when **a new physical transaction is created**, depending on the transaction manager and driver/database.

### 9.1. What is `Isolation.DEFAULT`?

Default `@Transactional`:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT
)
```

`DEFAULT` does not mean automatically picking `READ_COMMITTED` or `SERIALIZABLE` for every DB. It requests the default isolation of the underlying resource/transaction manager. PostgreSQL usually defaults to `READ_COMMITTED`; InnoDB usually defaults to `REPEATABLE READ`.

In projects requiring consistent behavior across multiple engines, consider explicitly declaring important levels at service boundaries and testing against the actual DB. You must still verify that the DB supports the requested level, because `@Transactional` **cannot force a driver/DB that does not support that behavior**.

### 9.2. A transaction in outer, inner requests a different level

```java
@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        inner.inner();
    }
}

@Service
public class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // ...
    }
}
```

With `REQUIRED`, inner typically **joins the existing transaction**, so no new physical SERIALIZABLE transaction is opened just because of inner's annotation. By default, Spring may allow it to join using outer's isolation. If you want to reject incompatible isolation configurations, with an appropriate manager you can enable `setValidateExistingTransaction(true)` to **detect mismatches**.

`REQUIRES_NEW` opens a separate transaction and can apply a new isolation level, but it changes commit/rollback boundaries, the number of connections needed, and atomicity. Do not use it merely to paper over a service design flaw.

### 9.3. Proxy, thread, and transaction manager

- In Spring AOP proxy mode, calls must go **through the Spring-managed proxy** for `@Transactional` advice to trigger. `this.someTransactionalMethod()` inside the same bean generally does not create new transaction advice.
- With imperative JDBC, transactions are bound to the thread; an `ExecutorService`/`new Thread` inside a method does not automatically carry the calling thread's transaction to the new thread. In the Java example below, **each thread calls a Spring-managed service method**, getting its own transaction.
- There must be a `PlatformTransactionManager` for the corresponding `DataSource` or JPA/EntityManager. An annotation does not create a transaction without the underlying infrastructure.
- `@Transactional(readOnly=true)` is distinct from `isolation=...`: read-only is a transaction hint/setting, **not** a guarantee that the snapshot is always fixed or that write SQL will be rejected on every driver.
- With JPA/Hibernate, the persistence context/first-level cache can mask a non-repeatable read on **the same managed entity** even when the database is at READ_COMMITTED; to test **database semantics**, use JDBC or actively manage flush/clear/refresh and understand the queries issued.
- Methods marked transactional have their own rollback rules when returning or throwing exceptions; isolation does not mean "roll back on exception" or vice versa.

## 10. Runnable Java 17 example: two explicitly synchronized transactions

We will write a small Spring Boot project using **PostgreSQL**, rather than choosing H2 to guess PostgreSQL behavior. The exercise runs **twice** on the same sandbox database, sequentially with `READ_COMMITTED` and `REPEATABLE_READ`.

Each scenario run:

1. Resets the two demo tables to account balance=100, one OPEN order.
2. The reader thread starts a transaction, reads the account balance and the count of OPEN orders, then signals that the first read is done.
3. The coordinator thread calls the writer service; the writer performs UPDATE balance=200 and INSERT order OPEN in a **separate** transaction, committing when the proxy method returns.
4. The coordinator signals that the writer has committed; the reader proceeds to read again **within the original transaction**.
5. Prints both pairs of values. With PostgreSQL RC: `100→200` and `1→2`. With RR: `100→100` and `1→1`.

Instead of `Thread.sleep(500)` (which does not guarantee ordering), we use `CountDownLatch` so it does not depend on CPU speed. The demo assumes nothing else is modifying those two tables in a dedicated local database.

### 10.1. File structure

```text
isolation-anomalies-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/isolation/
    │   ├── IsolationApplication.java
    │   ├── ReaderService.java
    │   └── WriterService.java
    └── resources/
        └── application.yml
```

**`settings.gradle`:**

```groovy
rootProject.name = 'isolation-anomalies-lab'
```

**`build.gradle`:** Fixed versions **Java 17 + Spring Boot 3.3.13** so the example is reproducible; this does not imply it is the latest release.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot automatically manages the versions of the JDBC starter, HikariCP, and PostgreSQL driver via dependency management; there is no need to declare `spring-tx` manually. We use `JdbcTemplate` to read DB values directly without being cached by a JPA persistence context.

### 10.2. Preparing a dedicated PostgreSQL instance for the demo

If Docker is available and port 55432 on your machine is unused:

```bash
docker run -d --name isolation-lab-pg \
  -e POSTGRES_DB=isolab \
  -e POSTGRES_USER=isolab \
  -e POSTGRES_PASSWORD=local_only \
  -p 55432:5432 postgres:16
```

In PowerShell you can enter it on one line:

```powershell
docker run -d --name isolation-lab-pg -e POSTGRES_DB=isolab -e POSTGRES_USER=isolab -e POSTGRES_PASSWORD=local_only -p 55432:5432 postgres:16
```

Check the server:

```bash
docker exec isolation-lab-pg pg_isready -U isolab -d isolab
```

This password is **for local practice only**, not for production use. The example container does not mount a persistent volume; removing the container can lose data, which is fine for a lab but not for real data.

**`src/main/resources/application.yml`:**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:postgresql://localhost:55432/isolab"
    username: ${DB_USER:isolab}
    password: ${DB_PASSWORD:local_only}
    hikari:
      maximum-pool-size: 5
```

A pool size of 5 is sufficient for at least two connections running concurrently in the demo. Adjust host/port/user/password for your environment if not using Docker. Do not hardcode production credentials in YAML.

### 10.3. ReaderService: reading twice within the **same transaction**

**`src/main/java/demo/isolation/ReaderService.java`:**

```java
package demo.isolation;

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

    public record Observation(
        int firstBalance,
        long firstOpenOrders,
        int secondBalance,
        long secondOpenOrders
    ) {}

    @Transactional(isolation = Isolation.READ_COMMITTED, readOnly = true)
    public Observation readCommitted(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {
        return observe(firstReadDone, writerCommitted);
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
    public Observation repeatableRead(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {
        return observe(firstReadDone, writerCommitted);
    }

    private Observation observe(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {

        int firstBalance = jdbc.queryForObject(
            "SELECT balance FROM iso_accounts WHERE id = 1",
            Integer.class
        );
        long firstCount = jdbc.queryForObject(
            "SELECT COUNT(*) FROM iso_orders WHERE state = 'OPEN'",
            Long.class
        );

        // Reader has established snapshot / completed the first read.
        firstReadDone.countDown();

        try {
            if (!writerCommitted.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Writer timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Reader interrupted", ex);
        }

        int secondBalance = jdbc.queryForObject(
            "SELECT balance FROM iso_accounts WHERE id = 1",
            Integer.class
        );
        long secondCount = jdbc.queryForObject(
            "SELECT COUNT(*) FROM iso_orders WHERE state = 'OPEN'",
            Long.class
        );

        return new Observation(
            firstBalance, firstCount, secondBalance, secondCount
        );
    }
}
```

`observe(...)` is a private helper **called from two public methods after the Spring proxy has opened the transaction**. Do not annotate the helper with `@Transactional` and do not self-invoke a public transactional method from the same bean. The transaction holds the connection/snapshot throughout the time the reader waits for the writer's signal.

`queryForObject(..., Integer.class)` reads the `INTEGER` column, while PostgreSQL `COUNT(*)` returns `BIGINT`, so `Long.class` is used. Values are non-null thanks to the table/record initialization in the runner.

### 10.4. WriterService: concurrent modification and commit

**`src/main/java/demo/isolation/WriterService.java`:**

```java
package demo.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriterService {
    private final JdbcTemplate jdbc;

    public WriterService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void publishChange() {
        jdbc.update(
            "UPDATE iso_accounts SET balance = 200 WHERE id = 1"
        );
        jdbc.update(
            "INSERT INTO iso_orders (id, state) VALUES (2, 'OPEN')"
        );
    }
}
```

`publishChange()` writes both the UPDATE and the INSERT in one transaction; with the default PostgreSQL configuration here, the writer runs at `READ_COMMITTED`. The coordinator calls the method on **a Spring-managed bean from another thread**; the writer transaction commits when the proxy call returns normally.

If the writer fails before commit, the scenario premise is not met; the program should fail with an error rather than printing output as if the writer committed successfully.

### 10.5. Application: running the scenario twice and printing results

**`src/main/java/demo/isolation/IsolationApplication.java`:**

```java
package demo.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            ReaderService reader,
            WriterService writer,
            JdbcTemplate jdbc) {

        return args -> {
            // ONLY on a dedicated database used for practice.
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS iso_accounts ("
                + "id INTEGER PRIMARY KEY, balance INTEGER NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS iso_orders ("
                + "id INTEGER PRIMARY KEY, state VARCHAR(12) NOT NULL)"
            );

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                scenario(
                    "READ_COMMITTED", false, reader, writer, jdbc, pool
                );
                scenario(
                    "REPEATABLE_READ", true, reader, writer, jdbc, pool
                );
            } finally {
                pool.shutdownNow();
            }
        };
    }

    private static void scenario(
            String label,
            boolean repeatable,
            ReaderService reader,
            WriterService writer,
            JdbcTemplate jdbc,
            ExecutorService pool) throws Exception {

        // Reset before creating reader/writer transactions.
        jdbc.execute("TRUNCATE TABLE iso_orders, iso_accounts");
        jdbc.update(
            "INSERT INTO iso_accounts(id, balance) VALUES (1, 100)"
        );
        jdbc.update(
            "INSERT INTO iso_orders(id, state) VALUES (1, 'OPEN')"
        );

        CountDownLatch firstReadDone = new CountDownLatch(1);
        CountDownLatch writerCommitted = new CountDownLatch(1);

        Future<ReaderService.Observation> future =
            pool.submit(() -> repeatable
                ? reader.repeatableRead(firstReadDone, writerCommitted)
                : reader.readCommitted(firstReadDone, writerCommitted)
            );

        try {
            if (!firstReadDone.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Reader timed out");
            }
            // Wait for reader to finish reading before executing writer transaction.
            writer.publishChange();
        } finally {
            // Released AFTER the writer proxy call finishes.
            // If writer fails, the exception still propagates; does not report success.
            writerCommitted.countDown();
        }

        ReaderService.Observation observation =
            future.get(30, TimeUnit.SECONDS);

        System.out.println(label + ": " + observation);
    }
}
```

**Run only on a practice database**: the runner executes `TRUNCATE TABLE iso_orders, iso_accounts` at the start of each scenario, deleting demo records. Do not run on a production schema containing data to keep.

How races are avoided:

- The reader starts **its own transaction** via the proxy on a pool thread.
- The reader only calls `countDown(firstReadDone)` after **both initial SELECTs**.
- The coordinator waits for the signal and then calls the writer; the writer opens and commits **a separate transaction**.
- Only **after the writer proxy returns** does the coordinator release `writerCommitted` so the reader can execute the next two SELECTs.
- Does not rely on `sleep` or arbitrary thread scheduling order.

If the reader cannot get a connection or the DB is slow, the 30-second timeout throws an exception instead of pretending to have a result. In high-load environments you can increase the wait limit; the timeout is only a safeguard for the demo scenario, not what determines isolation.

### 10.6. Run commands and stdout

Create a project with Gradle Wrapper (for example from Spring Initializr), and in the project directory run:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

With PostgreSQL ready, no external writers in the demo database, and the classes/config exactly as above, the two lines printed by the program are:

```text
READ_COMMITTED: Observation[firstBalance=100, firstOpenOrders=1, secondBalance=200, secondOpenOrders=2]
REPEATABLE_READ: Observation[firstBalance=100, firstOpenOrders=1, secondBalance=100, secondOpenOrders=1]
```

Startup and Gradle logs may also appear. The `Observation[...]` name and field names come from Java 17's `record Observation`; that is the record's default `toString()` output.

**Analysis:**

- `READ_COMMITTED`: the account SELECT after the writer commits sees 200 instead of 100 → **non-repeatable read**. The same `state='OPEN'` predicate counts 2 instead of 1 → **phantom read**.
- PostgreSQL `REPEATABLE_READ`: the two SELECTs after the writer commits still see the old snapshot: account=100 and count=1. The writer has committed changes in the DB, yet the current reader does not see them.
- There is no dirty read example here because PostgreSQL does not allow dirty reads even when `READ_UNCOMMITTED` is requested.

The data and transaction conditions are explicitly encoded; this is not proof that every SQL statement or every DB will produce identical output.

### 10.7. Observing after the reader finishes

After the `REPEATABLE_READ` scenario, a **new** transaction/query running:

```sql
SELECT balance FROM iso_accounts WHERE id=1;
SELECT COUNT(*) FROM iso_orders WHERE state='OPEN';
```

will see 200 and 2 if there are no other writers. That the reader still sees 100/1 in its own snapshot **does not** prevent the writer from committing, does not mean data was "lost," and does not mean the entire system is frozen.

## 11. Why use a transaction on another thread instead of "passing" the reader's transaction?

In imperative Spring JDBC, `@Transactional` binds the connection/transaction context to **the current execution thread** via Spring's infrastructure. If inside a transactional method you simply spawn `new Thread(...)` and run JDBC code, the new thread **does not automatically inherit** the old thread's transaction.

The example above intentionally needs **two independent transactions running concurrently** to observe anomalies:

```text
Main/Coordinator Thread
   |
   +-- submit readerService.readCommitted(...) to pool thread
   |       -> Spring proxy opens transaction T1, holds connection #1
   |
   +-- call writerService.publishChange(...) on main thread
   |       -> Spring proxy opens transaction T2, connection #2
   |       -> COMMIT T2
   |
   +-- signal latch for T1 to continue reading
           -> T1 reads again on connection #1, then finishes
```

Splitting threads here is a **tool to reproduce concurrency in a controlled way**, not a recommendation to split a single business transaction across multiple threads. When real async processing is needed, each task must have properly designed transaction boundaries and idempotency.

If you try to reproduce this by calling two methods on **the same thread** when both use `Propagation.REQUIRED`, the second method may **join the same physical transaction** instead of creating an independent transaction. In that case you will not create the situation where T1 reads while T2 in another transaction updates and commits as shown in the timeline.

## 12. Does READ_COMMITTED guarantee every business operation is accurate?

No. `READ_COMMITTED` prevents dirty reads, but non-repeatable/phantom reads can break assumptions:

```text
T1: COUNT(booking WHERE room=101 AND overlaps(slot)) -> 0
T2: COUNT(booking WHERE room=101 AND overlaps(slot)) -> 0
T1: INSERT booking for room=101/slot
T2: INSERT booking for room=101/slot
T1/T2: COMMIT
```

If the DB has no constraint or locking to prevent overlapping schedules and neither INSERT conflicts on an existing lock, both transactions can insert conflicting bookings. This issue is a **race/invariant violation** tied to a predicate, not merely two SELECT statements returning different numbers.

Countermeasures (depending on DB and requirements):

1. **Database constraint**: unique index, exclusion constraint, or rules enforcing the invariant; this is often the most important last line of defense.
2. **Conditional atomic SQL update/insert**: avoid separate read-then-write cycles when an atomic expression is possible.
3. **Optimistic locking/versioning**: detect concurrent updates of the same entity/row and retry appropriately.
4. **Explicit locking**: `SELECT ... FOR UPDATE` for existing rows and engine-appropriate range/predicate locks. For a query returning **zero rows**, simply using `FOR UPDATE` on an empty set often **cannot lock "the gap" as intended** on every DB.
5. **SERIALIZABLE**: prevents non-serializable commit schedules using the DB's strategy; requires **retrying the entire transaction** when the DB aborts an execution.

Do not claim "choosing REPEATABLE_READ will definitely solve every booking overlap"; PostgreSQL RR can still experience write skew if two transactions read the same snapshot and then write different rows.

## 13. SERIALIZABLE: stronger, but does not mean "no error handling needed"

In Spring:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void reserveResource() {
    // Read invariant, then write data depending on the invariant.
}
```

In PostgreSQL, a serializable transaction may be rejected with SQLSTATE **40001** if committing all concurrent transactions would create a schedule not equivalent to any serial execution. This is a **mechanism to guarantee correctness**: the DB rejects certain executions rather than necessarily blocking all queries until another transaction finishes.

Key points:

- A `@Transactional` failure with a serialization error does not mean the database is "broken" or that business logic should commit anyway. **That transaction has failed** and needs to be considered for retry.
- Retries, if used, must be **a new transaction** re-reading the input conditions, typically placed **outside the transaction proxy** of each attempt. Do not just retry the final `INSERT` statement inside the already-aborted transaction.
- Retries should have a **bounded attempt count**, appropriate backoff, and distinguish retryable errors from non-retryable data/constraint errors.
- External side effects (sending email/HTTP) inside an attempt may be repeated on retry; consider outbox/after-commit patterns and idempotency.
- `SERIALIZABLE` carries cost and DB-dependent semantics; it is not mandatory for every report or every read transaction.

A read-only transaction that performs no writes can also have snapshot/serialization considerations in the DB; do not assume only writers need concurrency error handling.

## 14. Common misconceptions about JPA/Hibernate and Spring Data JPA

### 14.1. A managed entity may be cached in the persistence context

Calling `EntityManager.find(Account.class, 1L)` twice in the same persistence context typically returns **the same managed entity**, without necessarily sending two SELECT statements to the DB. Therefore, a test that "reads twice, unchanged" in Spring Data JPA **does not prove** the database prevented a non-repeatable read.

If you need to verify isolation at the DB level:

- Use JDBC directly as in the example.
- Or understand how JPA flush/clear/refresh, entity state, query cache, and actual database queries behave.
- Avoid calling `EntityManager.clear()` casually in business code because it can affect state pending flush; it is a testing tool that requires care.

### 14.2. Flush is not commit

In JPA, `entityManager.flush()` can send SQL before the transaction commits. Another transaction at `READ_COMMITTED` still **cannot read dirty state** just because flush ran; it must wait for the data to be committed to see the new version as permitted by its isolation level. After a flush, the current transaction can still roll back.

### 14.3. Repository methods and outer transactions

If an outer service has already opened a transaction and calls a repository with a different transaction declaration, it usually **joins the outer transaction**. Isolation on the repository does not automatically create a new physical transaction. Choose isolation at **the service boundary owning the business operation** and verify which manager is actually used.

### 14.4. readOnly does not mean repeatable read

Two separate attributes:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED
)
```

A read-only transaction at RC can still see non-repeatable/phantom reads caused by another transaction committing between two SELECTs. Do not infer from the word "readOnly" that the snapshot is fixed.

## 15. Guide to testing and diagnosing unexpected results

| Symptom | Common cause | Verification step |
| --- | --- | --- |
| Expecting dirty read in PostgreSQL but always seeing committed data | PostgreSQL `READ_UNCOMMITTED` is treated as RC | Read DB documentation; do not force incorrect expectations |
| T1 does not see a newly committed UPDATE at RC | T2 had not committed before the second SELECT started; or test is not actually using the same DB / separate connections | Use latches, log boundaries, confirm commit timing |
| T1 sees changing data despite expecting RR | No actual transaction between the two SELECTs; new transaction opened; or using a different DB | Check proxy, isolation, connection, `@Transactional` |
| JPA test shows unchanged entity at RC | Persistence context returns the same managed entity without querying DB a second time | Enable SQL logging/test with JDBC, manage EntityManager explicitly |
| Inner `@Transactional(isolation=SERIALIZABLE)` does not raise level | `REQUIRED` joins the outer transaction | Set level at the outer owner or enable validation |
| Test using `Thread.sleep` gives flaky results | Non-deterministic scheduling | Use CountDownLatch / explicitly coordinate commit before reread |
| Test class itself has `@Transactional` | Test framework opens a transaction and may roll back at test end | Separate the test transaction from reader/writer; read DB after commit |
| Connection pool too small, program hangs | Reader holds a connection while writer needs a second connection | Ensure sufficient pool size and timeouts; avoid holding long transactions in production |
| SERIALIZABLE reports SQLSTATE `40001` | DB detected a serialization conflict | Retry the entire transaction with a bounded policy |
| SQL query changes, unclear if phantom or non-repeatable | Mixing row-by-ID query with predicate query | Separate the two cases as in the examples |

### Checklist before concluding that isolation is working

1. **Right DB and engine**: PostgreSQL/MySQL InnoDB/H2 cannot be assumed identical.
2. **Real transaction**: `PlatformTransactionManager` is present, right DataSource, call goes through proxy.
3. **Two independent connections/transactions**: writer must not join reader's transaction.
4. **Event ordering**: first SELECT → writer UPDATE/INSERT → writer COMMIT → second SELECT.
5. **Invariant queries**: same ID for non-repeatable, same predicate for phantom.
6. **Not reading JPA cache instead of DB**: confirm SELECT actually executes.
7. **Isolation applied at transaction owner**: not only on an inner method joining outer.
8. **Clean and deterministic test data**: no third writer, reset only in sandbox database.
9. **Post-transaction observation**: distinguish data in T1's snapshot from committed data visible to a new transaction.

## 16. Self-check exercises

**Exercise 1 — Identify the phenomenon**

```text
T1: BEGIN
T1: SELECT balance WHERE id=1 -> 100
T2: BEGIN
T2: UPDATE balance=80 WHERE id=1
T2: COMMIT
T1: SELECT balance WHERE id=1 -> 80
T1: COMMIT
```

**Answer:** non-repeatable read if the database/isolation level allows T1 to see 80. Not a dirty read because T2 committed before the second read.

**Exercise 2 — Uncommitted data**

```text
T2: UPDATE balance=900 (not committed yet)
T1: SELECT balance -> 900
T2: ROLLBACK
```

**Answer:** dirty read, if the database actually allows it. PostgreSQL does not produce this timeline outcome under any supported isolation level.

**Exercise 3 — Result set changed**

```text
T1: SELECT id FROM orders WHERE state='OPEN' -> [1]
T2: INSERT (2,'OPEN'); COMMIT
T1: SELECT id FROM orders WHERE state='OPEN' -> [1,2]
```

**Answer:** phantom read because the set of rows matching `WHERE` changed between two queries in the same T1.

**Exercise 4 — Why does PostgreSQL REPEATABLE_READ not produce phantoms even though the SQL standard table marks it "Possible"?**

**Answer:** the SQL standard only states **minimum** guarantees; PostgreSQL uses a stable transaction snapshot at RR, giving a stronger guarantee, though other serialization anomalies can still occur.

**Exercise 5 — To guarantee no two overlapping bookings, is choosing REPEATABLE_READ alone enough?**

**Answer:** not necessarily. You need DB-appropriate constraints/locking/serializable and conflict handling; RR can still have write skew, and plain snapshot reads do not automatically protect all predicate invariants.

**Exercise 6 — Why is `@Transactional(readOnly=true)` not enough to prevent phantoms in PostgreSQL RC?**

**Answer:** read-only and isolation are two different attributes. T1 at RC can receive a new snapshot on the next SELECT even though T1 does not write data itself.

**Exercise 7 — An inner method declares SERIALIZABLE and is called from an outer REQUIRED/READ_COMMITTED method. Does it automatically create a physical SERIALIZABLE transaction?**

**Answer:** no. Inner typically joins outer and uses the existing isolation; you need to choose the right transaction boundary or intentional `REQUIRES_NEW`, along with mismatch validation when needed.

## 17. Conclusion

The three anomalies are easy to remember by **commit status and what is re-read**:

- **Dirty read:** reading **uncommitted** data from T2.
- **Non-repeatable read:** re-reading **the same row** and seeing a different value after T2 **commits**.
- **Phantom read:** re-running **the same search condition** and seeing **a different set of rows** after T2 **commits**.

The SQL standard table describes which phenomena are **permitted or prohibited** at each isolation level; **databases are allowed to provide stronger protection**. PostgreSQL `READ_UNCOMMITTED` behaves like `READ_COMMITTED`, and `REPEATABLE_READ` prevents phantoms in snapshot reads as well. Spring's `@Transactional(isolation = ...)` only asks the manager/driver to apply a level when opening an eligible transaction; propagation, proxies, database semantics, caching, and actual concurrency determine the outcome.

**To apply safely:** choose isolation at the transaction owner, add DB constraints for invariants, test with two real transactions and deterministic execution order, read the documentation for your exact database, and prepare to handle concurrency conflicts when using `SERIALIZABLE`.

## Official sources for reference

- PostgreSQL — Transaction Isolation and anomaly table: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — SET TRANSACTION, snapshots, and READ UNCOMMITTED: https://www.postgresql.org/docs/current/sql-set-transaction.html
- Spring Framework — TransactionDefinition, isolation constants: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — Using `@Transactional`, isolation/propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation and proxy/thread: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction Propagation, existing transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
