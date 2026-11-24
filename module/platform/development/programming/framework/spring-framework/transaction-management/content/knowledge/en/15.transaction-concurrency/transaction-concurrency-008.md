# Lock Scope, Indexes, and Impact on Concurrent Load

## 1. Why can a single SQL statement slow down many requests?

Suppose a Spring Framework application concurrently processes many requests updating orders, inventory, or balances. One request holds a lock on a record that another request wants to modify. The second request may have to **wait for the lock**, hit a **lock timeout**, become a deadlock victim, or proceed only after the first transaction finishes.

The impact of locking on concurrency depends on **three interconnected factors**:

1. **Lock footprint:** which rows, index records, index ranges, or objects does the SQL operation actually lock?
2. **Data access path:** how do `WHERE`, `JOIN`, `ORDER BY`, and the **index/query plan** make the database locate the right rows—scanning many or few?
3. **Lock hold time / transaction lifetime:** when is the lock acquired, and is it only released when the transaction commits/rolls back or via another mechanism? During that time, how many transactions need conflicting locks?

A good index can help locate rows quickly, reduce scanning, and sometimes **narrow index-record/gap locks**; yet a single hot row can still cause contention even when queried by primary key. Conversely, a transaction holding locks too long due to an HTTP call inside `@Transactional` can force every related request to wait even with an optimized query.

**Spring defines transaction boundaries, not every row/gap lock.** Specific lock modes are determined by the DBMS, storage engine, isolation, query plan, and SQL statement. Never apply a blanket claim like "missing an index locks the whole table" to every DB.

### Lesson objectives

- Distinguish result set, scan range, lock footprint, and transaction duration.
- Understand row/record locks, relation/table locks, intention locks, gap/next-key locks, MVCC, and locking reads.
- Analyze the effects of primary key indexes, composite indexes, range predicates, non-sargable predicates, and optimizer plans.
- Know why the same `SELECT ... FOR UPDATE` statement can have different impacts on PostgreSQL, MySQL/InnoDB, and H2.
- Run a **Java 17+, Spring Boot, Spring JDBC, H2** example with two overlapping physical transactions: an inner transaction trying to modify the same locked row times out, while an inner transaction modifying a different row commits.
- Read data after transactions finish to prove the outcome, rather than looking only at exceptions.
- Diagnose lock waits, deadlocks, and connection pool starvation, and optimize concurrent load while preserving business invariants.

This lesson belongs to the **Locking and Concurrency** group in the **Spring Framework — transaction-management** module, directly covering **"Lock Scope, Indexes, and Impact on Concurrent Load"**.

## 2. Four concepts that must not be equated

### 2.1. Result set — rows the SQL actually selects/updates

`SELECT ... WHERE id = 101` may return one row. `UPDATE ... WHERE tenant_id = 42` may update thousands of rows. This is the logical output of the SQL condition, and does not itself tell you which locks the engine placed.

### 2.2. Scan range — data the engine must inspect to find results

If a query filters by `id` as a primary key, a B-tree index usually navigates quickly to one row. If filtering on a column without a suitable index, the optimizer may scan many records even when only a few match.

**Scanning many rows does not automatically mean locking every scanned row.** On certain InnoDB locking scans, the index scan range significantly affects record/gap locks. PostgreSQL has different semantics: with top-level `SELECT ... FOR UPDATE`, locked rows relate to the selected rows, rather than a rule that "every scanned row gets locked."

### 2.3. Lock footprint — objects actually locked

Lock footprint comprises **object**, **lock type**, **mode**, **acquisition time**, and **release time**. A database may hold both row locks and coordinating table-level locks.

| Concept | General effect | Caveat |
| --- | --- | --- |
| Row/record lock | Prevents conflicting writes/locking reads on a row | Not all DBs have identical modes |
| Table/relation lock | Coordinates operations on a relation, DDL, DML | Having a table-level lock does not mean an exclusive full-table lock |
| Intention lock | Coordinates multi-granularity locks in DBs like InnoDB | Does not necessarily block ordinary reads |
| Gap lock | Protects a gap in index order | Can block INSERTs even when no row exists in the gap |
| Next-key lock | Combines record lock and gap lock, commonly discussed in InnoDB | Depends on isolation and search condition |
| Predicate/serialization tracking | Supports higher isolation or conflict detection | Does not always appear as a row lock |
| Advisory lock | Application explicitly locks on an agreed key | Not automatically created by `@Transactional` |

### 2.4. Lock hold time — held until the transaction ends

With typical row locks inside a physical transaction, **commit or rollback** is the critical point releasing locks, not when a Java helper method returns.

Example:

```text
BEGIN T
  UPDATE inventory id=10       <- starts holding row lock
  validate remaining steps
  2-second HTTP call
  INSERT order_history
COMMIT T                       <- row lock is released
```

If another request needs to update `inventory id=10` while T is open, it may wait. That the initial UPDATE took only 2 ms matters far less than when T releases the lock.

## 3. MVCC: "reading" does not necessarily mean "waiting for a write lock"

Many modern databases use **Multi-Version Concurrency Control (MVCC)**. An ordinary read query can read a committed snapshot without waiting for a row lock held by another transaction; an `UPDATE`, `DELETE`, or `SELECT ... FOR UPDATE` on that same row may have to wait.

Example on PostgreSQL under common MVCC conditions:

```sql
-- Session A
BEGIN;
UPDATE inventory SET quantity = quantity - 1 WHERE id = 10;
-- Not COMMITted yet.

-- Session B, different connection:
SELECT quantity FROM inventory WHERE id = 10;
-- Can read the previously committed version without waiting for UPDATE row lock.

-- Session C, different connection:
UPDATE inventory SET quantity = quantity - 1 WHERE id = 10;
-- May have to wait for session A to finish.
```

These are **three separate sessions placed together for explanation**, not run sequentially as one script. The exact value Session B reads depends on isolation and snapshot; it does not see A's uncommitted data merely because B and A both use Spring.

Never write absolute rules like "SELECT always locks rows" or "SELECT never takes locks": many DBs take relation locks for coordination, and SQL queries can use `FOR SHARE`, `FOR UPDATE`, or higher isolation.

## 4. Primary keys, unique indexes, and update scope

Suppose we have a table:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

An update targeting the right item:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 501 AND quantity >= 1;
```

This formulation serves two purposes:

- `id = 501` locates the row via the primary key, usually highly selective.
- `quantity >= 1` keeps the business rule "do not deduct when out of stock" inside the **same UPDATE statement**, avoiding "read then unconditional update," which is prone to lost updates under high concurrency.

In Spring JDBC:

```java
int affected = jdbc.update(
    "UPDATE inventory SET quantity = quantity - 1 " +
    "WHERE id = ? AND quantity >= 1",
    inventoryId
);
if (affected != 1) {
    throw new IllegalStateException("Not found or out of stock");
}
```

This is an **illustrative Java snippet**, not a standalone runnable class; `jdbc` and `inventoryId` must be supplied by the service. If an order requires multiple atomic write steps, the method still needs an appropriate transaction boundary.

**However, an index does not let two transactions modify the same row 501 in parallel without contention.** When both need a write lock on the same row, they must serialize, wait, or handle conflicts. This is a *hot row*.

## 5. Composite indexes and range queries

Suppose a job picks orders ready for processing:

```sql
SELECT id
FROM orders
WHERE tenant_id = 42
  AND status = 'READY'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE;
```

A candidate composite index:

```sql
CREATE INDEX idx_orders_tenant_status_time
ON orders(tenant_id, status, created_at, id);
```

Equality filters `tenant_id` + `status` along with ORDER BY can fit this index. On large tables, the query plan can quickly find top-priority rows instead of scanning and sorting vast amounts of data. Yet you must verify with `EXPLAIN` on real data:

- The optimizer **may choose Seq Scan** on small tables even if an index exists.
- A low-cardinality column or skewed distribution can make an index poorly selective.
- `LIMIT 20` is no guarantee that strictly 20 rows/index entries are accessed in every execution plan.
- `FOR UPDATE` still locks rows per database semantics. An index does not turn a locking read into a lock-free read.
- `OFFSET` can cause reading/skipping many rows; in PostgreSQL, a top-level locking clause may also lock rows skipped by OFFSET.

### 5.1. Single-column indexes do not always replace composite indexes

An index only on `tenant_id` may return many rows without filtering `status`; an index only on `created_at` does not necessarily help the tenant/status filter. Composite indexes require considering prefix order, equality/range predicates, selectivity, and ORDER BY per DBMS.

Do not pick index columns by the intuition "always put the highest-cardinality column first." Workloads consist of many different queries; an order optimal for one query may be poor for another.

### 5.2. Sargability: writing index-friendly WHERE clauses

Example:

```sql
-- Can prevent using a standard B-tree index range seek:
WHERE DATE(updated_at) = DATE '2026-10-30'

-- Range form is usually friendlier to an index on updated_at:
WHERE updated_at >= TIMESTAMP '2026-10-30 00:00:00'
  AND updated_at < TIMESTAMP '2026-10-31 00:00:00'
```

This is a **condition-illustrating SQL snippet**. Verify data types/time zones before substituting so semantics stay identical. Some DBs support expression/functional indexes, so the first form **does not always** force a scan.

Other patterns to inspect: mismatched casts, `LIKE '%keyword'` with ordinary B-trees, functions wrapped around columns in WHERE, broad OR conditions, and JOINs lacking indexes on join keys. Never conclude a query is slow due to a missing index without checking the plan.

### 5.3. Indexes have costs

Every new index can add maintenance work to INSERT/DELETE or UPDATEs touching indexed columns. It increases disk/memory overhead and can introduce new write hotspots. Add indexes only when query performance, lock waits, or scan costs are proven to improve meaningfully; prefer removing redundant indexes when safe.

## 6. PostgreSQL vs. MySQL/InnoDB: differences that must be stated explicitly

### 6.1. PostgreSQL: row locks generally apply to selected rows

PostgreSQL `SELECT ... FOR UPDATE` locks rows per the query, preventing conflicting `UPDATE`/`DELETE`/locking reads on those exact rows until the transaction ends. PostgreSQL also uses relation-level lock modes to coordinate table access.

**Do not infer that a `Seq Scan` locks every scanned row.** A query filtering down to a few rows may read many pages due to a missing index, yet which rows it locks depends on SQL semantics. Per PostgreSQL documentation, for a top-level locking clause, locked rows correspond to returned rows, with specific rules for `JOIN`/`LIMIT`/`OFFSET` and rows modified mid-query.

Under higher isolation like `SERIALIZABLE`, PostgreSQL also tracks conflicts and can raise serialization errors; do not force reasoning solely in terms of simple row locks.

### 6.2. InnoDB: index ranges can dictate record/gap lock scope

In InnoDB, locking reads, `UPDATE`, and `DELETE` typically lock the **scanned index records** per the execution plan; under `REPEATABLE READ` (InnoDB's common default), the engine may use **next-key locks**: record locks + gap locks on the interval preceding the record.

Difference:

```sql
-- Primary key equality: very narrow search scope.
SELECT id FROM inventory WHERE id = 501 FOR UPDATE;

-- Range predicate: may scan an index range.
SELECT id FROM inventory
WHERE tenant_id = 42 AND sku >= 'A'
FOR UPDATE;
```

In InnoDB under suitable conditions, searching via a **unique index with a unique search condition** typically locks only the found index record without a preceding gap lock; a range search can take next-key locks across the index range, blocking INSERTs into those gaps as well. Without a suitable index, a locking scan can lock a great many entries.

However, under `READ COMMITTED`, InnoDB changes gap/record locking behavior: gap locks for many searches/index scans are reduced or disabled, except in cases like foreign-key or duplicate-key checks. Exact locking still depends on the optimizer plan and specific SQL. Do not apply this rule verbatim to PostgreSQL or H2.

### 6.3. Why is "indexes narrow locks" a conditional statement?

| Characteristic | PostgreSQL | MySQL/InnoDB |
| --- | --- | --- |
| Exact row lookup via unique index | Usually faster than a large scan | Can reduce scanned index records and lock range |
| Wide scan due to missing index | Can increase query duration and transaction hold time | Can increase both scan work and record/gap locks of locking statements |
| Locking range scan | Row locking per PostgreSQL semantics; not identical to full scan | Next-key/gap locking can be significant, depending on isolation |
| Index exists yet all requests edit same hot row | Still contends | Still contends |
| Optimizer skips the index | Scan work can remain high | Locking scan can remain wide |
| Ordinary SELECT under MVCC | Not the same as `FOR UPDATE` | Consistent read also differs from locking read |

When making an official conclusion for a system, record the **DB engine, version, isolation, SQL statement, indexes, and EXPLAIN**. Never rely solely on `@Transactional` annotations or an H2 simulation.

## 7. Runnable Java 17+ demo: same row waits, different row can commit

To understand transaction-level locking, we build a **Spring Boot 3.3.13 + Spring JDBC + in-memory H2** application where an outer transaction updates row `id=1`. While outer has not committed, two `REQUIRES_NEW` inner transactions sequentially:

1. Try to UPDATE the **same row id=1** — needing the lock outer still holds, H2 raises a lock timeout.
2. UPDATE **row id=2** — no contention with row id=1, and can commit independently.

Outer then throws `IllegalStateException`, so Spring rolls back the change to row 1; row 2, committed by the other transaction, remains. The demo has **two overlapping physical transactions** even though the Java calls run sequentially on one thread: `REQUIRES_NEW` suspends outer, borrows another connection, and opens a new transaction; suspending outer does not release outer's DB locks.

This is a **row contention** experiment on H2, **not** a verification of InnoDB next-key/gap locks or PostgreSQL's row-lock implementation.

### 7.1. Project structure

```text
lock-footprint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/locks/
    │   ├── LockApplication.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'lock-footprint-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:footprint;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=300
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.sql.init.mode=always
```

H2 `LOCK_TIMEOUT=300` sets the lock wait timeout in milliseconds solely to keep the example fast. A pool of 4 connections suffices for a demo with **one sequential call stack** where outer holds one connection and inner needs its own; it is not a recommended production configuration.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE item (
    id INT PRIMARY KEY,
    qty INT NOT NULL
);

INSERT INTO item(id, qty) VALUES (1, 10);
INSERT INTO item(id, qty) VALUES (2, 10);
```

`id` is an indexed primary key. The two rows have no foreign keys/triggers affecting one another; updating id=2 succeeds to prove it does not have to wait for id=1's row lock under the demo conditions.

### 7.2. InnerService — `REQUIRES_NEW` transactions

**`src/main/java/demo/locks/InnerService.java`**

```java
package demo.locks;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void sameRow() {
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            1
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void otherRow() {
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            2
        );
    }
}
```

Each public non-final method gets the transaction interceptor applied when outer invokes it through the injected Spring bean. `REQUIRES_NEW` creates a separate physical transaction; if outer is active, its resource context is temporarily suspended, not committed.

### 7.3. OuterService — hold lock, try contention, and roll back

**`src/main/java/demo/locks/OuterService.java`**

```java
package demo.locks;

import java.sql.SQLException;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void compete() {
        // Outer T1 modifies id=1 and holds the row lock until T1 finishes.
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            1
        );

        boolean timedOut = false;
        try {
            // New T2 needs the same row that T1 is locking.
            inner.sameRow();
        } catch (DataAccessException ex) {
            if (!isH2Timeout(ex)) {
                throw ex;
            }
            timedOut = true;
        }

        if (!timedOut) {
            throw new IllegalStateException(
                "Expected lock timeout on row 1");
        }
        System.out.println("sameRowLockTimeout=true");

        // New T3 modifies row 2 and can commit independently.
        inner.otherRow();

        // Transaction T1 rolls back; already-committed T3 is not undone.
        throw new IllegalStateException("outer rolled back");
    }

    private static boolean isH2Timeout(Throwable error) {
        Throwable t = error;
        while (t != null) {
            if (t instanceof SQLException sql
                    && sql.getErrorCode() == 50200) {
                return true;
            }
            t = t.getCause();
        }
        return false;
    }
}
```

H2 uses vendor code `50200` for lock timeouts. The code verifies the exact expected lock-wait error; if the root cause differs, it rethrows rather than reporting a false pass. Different databases have different SQLStates/vendor codes, so **do not** use `50200` as a generic Spring retry rule.

**Mechanism:** T1 holds the write lock on row 1. `REQUIRES_NEW` T2 opens another connection and tries to UPDATE row 1; it must wait for T1, yet T1 is suspended and cannot release its lock until T2 returns. H2 raises a lock timeout and T2 rolls back. New T3 UPDATEs row 2, has no contention on row 1, and commits. Outer finally throws a runtime exception, rolling back T1 on row 1.

### 7.4. LockApplication — read DB after the transaction boundary

**`src/main/java/demo/locks/LockApplication.java`**

```java
package demo.locks;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class LockApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner verify(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            try {
                outer.compete();
            } catch (IllegalStateException ex) {
                System.out.println("outerFailure=" + ex.getMessage());
            }

            Integer q1 = jdbc.queryForObject(
                "SELECT qty FROM item WHERE id=1", Integer.class
            );
            Integer q2 = jdbc.queryForObject(
                "SELECT qty FROM item WHERE id=2", Integer.class
            );
            System.out.println(
                "afterRollback id1=" + q1 + " id2=" + q2);
        };
    }
}
```

`@EnableTransactionManagement` enables Spring AOP transaction infrastructure. `OuterService` calls **another bean** `InnerService` via injection so `REQUIRES_NEW` is not bypassed by self-invocation. `transactionManager` and `JdbcTemplate` share the same `DataSource`. The runner has no `@Transactional`, so it reads the DB **after all transactions on the call stack have completed**.

Do not put `@Transactional` on the runner, as that changes the experiment's preconditions. In production, nesting independent transactions underneath an outer row lock can cause pool starvation/self-contention; this example creates that scenario intentionally for learning.

### 7.5. Run command and expected output

Requires JDK 17+ and a compatible Gradle 8.x. In the `lock-footprint-demo` directory:

```bash
gradle bootRun
```

If the project has a wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). Do not compile Java files with only a bare JDK classpath because of Spring/H2 dependencies.

Ignoring Spring, Gradle, and Hikari logs, expected `System.out.println` lines:

```text
sameRowLockTimeout=true
outerFailure=outer rolled back
afterRollback id1=10 id2=11
```

Interpretation table:

| Step | Row 1 | Row 2 | Why? |
| --- | --- | --- | --- |
| Initial `schema.sql` | 10 | 10 | Original values |
| T1 UPDATEs id1, uncommitted | 11 in T1 | 10 | T1 holds write lock on id1 |
| T2 tries UPDATE id1 | T2 times out | 10 | Same row locked by T1 |
| T3 UPDATEs id2 | T1 uncommitted | **11 committed** | Different row, new transaction |
| T1 throws exception and rolls back | **10** | **11** | Rolling back T1 does not undo committed T3 |

This is **expected stdout per the code**, not output from an executed build. On H2 under this configuration, the result demonstrates *row-level contention + release timing*; do not use it to infer that PostgreSQL or InnoDB has identical gap-lock semantics.

## 8. Verifying on PostgreSQL with two or three SQL sessions

Run on a dedicated test database, not production tables. **Multiple connections** are required because we keep transaction A open while B and C operate.

### 8.1. Prepare test data

```sql
CREATE TABLE lock_lab (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    qty INT NOT NULL
);

INSERT INTO lock_lab(id, tenant_id, status, qty)
VALUES (1, 42, 'READY', 10),
       (2, 42, 'READY', 10),
       (3, 99, 'READY', 10);

CREATE INDEX idx_lab_tenant_status_time
ON lock_lab(tenant_id, status, created_at, id);
```

### 8.2. Session A — hold lock on row 1

```sql
BEGIN;
SELECT id FROM lock_lab WHERE id = 1 FOR UPDATE;
-- Keep transaction open so another connection can contend.
```

### 8.3. Session B — request the same row

```sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
UPDATE lock_lab SET qty = qty + 1 WHERE id = 1;
-- May fail with lock timeout because session A holds row 1.
ROLLBACK;
```

Once PostgreSQL reports an error inside a transaction, `ROLLBACK` is required to leave the aborted state. The commands in these sections are **for separate sessions**, not to be pasted into a single connection expecting contention.

### 8.4. Session C — independent row 2

```sql
BEGIN;
UPDATE lock_lab SET qty = qty + 1 WHERE id = 2;
COMMIT;
```

Session C can normally commit row 2 while A holds row 1, provided no other constraint/lock intervenes. Finish by returning to A and running `ROLLBACK`:

```sql
ROLLBACK;
```

Then use another connection to read back:

```sql
SELECT id, qty
FROM lock_lab
WHERE id IN (1, 2)
ORDER BY id;
```

Under the described test conditions, `id=1` remains 10 and `id=2` is 11.

### 8.5. EXPLAIN to see which index is actually chosen

```sql
EXPLAIN
SELECT id
FROM lock_lab
WHERE tenant_id = 42 AND status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

Default `EXPLAIN` returns the estimated plan. On a small demo table, the optimizer may choose `Seq Scan` even with an index; that is insufficient to conclude the index is useless on a million-row table.

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the SQL statement**. With `FOR UPDATE`, it can acquire row locks; with `UPDATE/DELETE`, it actually mutates data unless rolled back inside a controlled test transaction. Never run `EXPLAIN ANALYZE` on write statements in production without controlling side effects.

To evaluate indexes, create a representative dataset, update statistics, and compare estimated/actual rows, buffers, scan methods, and lock waits under realistic concurrency.

## 9. Observing lock waits on PostgreSQL/InnoDB

### 9.1. PostgreSQL

An observation query you can use:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    now() - xact_start AS tx_age,
    LEFT(query, 120) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY xact_start NULLS LAST;
```

Visibility into all sessions depends on PostgreSQL roles. Query text may contain sensitive data; use only in controlled monitoring environments.

An important gotcha: **PostgreSQL row-level locks usually do not appear as individual `tuple` rows in `pg_locks`**, because row lock info is stored on disk. A session waiting on a row lock may appear as waiting on the holder's **transaction ID**. Hence "no row lock seen in `pg_locks`" does not prove zero contention.

Combine `pg_blocking_pids`, wait events, transaction age, query plans, `pg_locks`, and application traces instead of checking only one view.

### 9.2. MySQL/InnoDB

Monitoring sources:

- `performance_schema.data_locks`: InnoDB lock info when supported and permitted.
- `performance_schema.data_lock_waits`: contending waiters/blockers.
- `SHOW ENGINE INNODB STATUS`: transaction/deadlock info.

Example on MySQL 8.x:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_NAME = 'orders';
```

Fields can represent record/gap locks, indexes, and lock status; output depends on version and settings. Protect sensitive metadata; do not make absolute inferences from one `LOCK_DATA` column while ignoring the index range.

### 9.3. Spring logs do not replace DB evidence

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Logs show which methods were intercepted and when Spring opened/committed/rolled back physical transactions. However, they **cannot list all index records locked by the DB**. Proper diagnosis requires combining SQL plans, DB wait/blocking views, and application metrics.

## 10. Transaction propagation, isolation, and locking in Spring

### 10.1. REQUIRED and release timing

If `OrderService.placeOrder()` opens T and calls `InventoryService.reserve()` with `@Transactional(REQUIRED)` via proxy, inner joins T. Inner returning **does not commit independently** and usually does not release row locks belonging to T. Outer continues processing until commit/rollback, so lock duration can exceed the inner method's runtime.

### 10.2. REQUIRES_NEW does not automatically solve contention

`REQUIRES_NEW` suspends outer and creates a separate physical transaction. Yet suspended outer **does not release row locks**, and inner may wait for locks held by outer. Meanwhile inner needs another connection; when many concurrent requests each hold an outer connection and wait for an inner connection, the pool can starve.

Changing inner to `REQUIRES_NEW` is valid only when business logic permits inner to commit/roll back independently. Do not use it as a "trick" to boost throughput and inadvertently break atomicity.

### 10.3. NESTED and savepoints

`Propagation.NESTED` can use a savepoint inside the same physical transaction if the JDBC manager/driver supports it. It is not the same as `REQUIRES_NEW`. Rolling back to a savepoint can undo changes in the nested scope; whether locks release and exact rules depend on the DBMS. A subsequent outer rollback still discards the entire physical transaction.

### 10.4. Isolation changes lock behavior per DBMS

`@Transactional(isolation = Isolation.READ_COMMITTED)` can request an isolation level for a **new** transaction when supported by the manager. An inner `REQUIRED` joining an outer transaction normally does not override the existing physical isolation. `SERIALIZABLE` strengthens anomaly guarantees but can trigger serialization errors/retries or different contention patterns.

Caution: lowering isolation solely to take fewer locks while ignoring lost updates/phantoms can violate business invariants. Choose isolation, SQL, and locking strategies by testing on the real DB.

### 10.5. Timeouts at different layers

- Database lock timeout: time waiting for a lock before the DB errors; H2 uses `LOCK_TIMEOUT`, PostgreSQL has `lock_timeout`, InnoDB has `innodb_lock_wait_timeout`.
- Statement timeout: bounds execution time of one query.
- Spring transaction timeout: applied at the transaction manager when conditions allow.
- Hikari connection acquisition timeout: time waiting to borrow a connection, **not a lock wait**.
- HTTP timeout: time waiting on upstream, which can hold transactions/locks needlessly if called inside T.

Do not classify every timeout as a deadlock, and do not retry infinitely when the cause is a hot row or pool exhaustion.

## 11. Appropriate optimization strategies

### 11.1. Shorten transactions first

Move non-DB validation, serialization, CPU-heavy computation, and network calls **outside the segment holding DB row locks** whenever business rules permit. Never arbitrarily "split transactions" when atomicity is needed: use intermediate states, idempotency, and outbox/compensation if workflows span external systems.

### 11.2. Narrow rows and ranges with sound predicates

Use primary/unique keys when updating one entity; add tenant predicates for multi-tenant safety when needed. For batches, use precise WHERE clauses and `LIMIT`/chunking per DB syntax, managing partial-completion semantics. Add indexes based on execution plans, not guesswork.

### 11.3. Lock in a stable order

Deadlocks can occur:

```text
T1 locks account A, waits for B
T2 locks account B, waits for A
                     ↓
                 deadlock
```

For transfers, lock accounts in a stable ID order when permitted to reduce wait cycles. Do not promise zero deadlocks overall, since FKs, triggers, and other locks remain. Retrying deadlock victims must be bounded and idempotent.

### 11.4. Optimistic locking when contention is rare

Example:

```sql
UPDATE account
SET balance = :balance,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Zero updated rows indicates a conflict or missing row. In JPA you can use `@Version`; the application must handle conflicts/retries/responses explicitly. On a hot row, optimistic retries can be very expensive; "no read lock" does not always mean faster.

### 11.5. Pessimistic locking when serialization is needed

Use `SELECT ... FOR UPDATE`, JPA `LockModeType.PESSIMISTIC_WRITE`, or atomic UPDATE statements. Acquire locks inside a physical transaction and hold them only as long as necessary. Consider timeouts and lock scope; never acquire pessimistic locks and wait on slow external gateways.

### 11.6. Distribute hot rows when feasible

A single account/counter modified on every request will contend despite fast primary-key lookups. You can design sharded counters, event accumulation, keying by business queues, or batched writes. Yet you must prove correctness when merging data; changing hot-row design is not solely a performance change.

## 12. Proper concurrent load testing

The H2 demo intentionally creates 2 overlapping physical transactions for clarity, not benchmarking. On a production-like DB, test:

| Test | Change one variable | What to measure? |
| --- | --- | --- |
| Same id | Two writers contending on the same row | Waits, timeouts, serialization |
| Two different ids | No shared constraint | Parallel progress capability |
| With/without composite index | Keep SQL, dataset, isolation constant | Plan, scanned rows, lock waits |
| READ COMMITTED vs REPEATABLE READ | Change isolation on test DB | Gap/next-key/predicate behavior |
| Short vs long transaction | Increase processing time between UPDATE and COMMIT | Lock hold time, pool waits, P95/P99 |
| Hot row vs distributed IDs | Vary business key distribution | Throughput and contention |
| Inner REQUIRES_NEW touching outer's row | Hold outer lock | Self-contention and pool needs |
| Retry with idempotency | Simulate lock timeout/deadlock | No duplicated side effects |

Record P50/P95/P99 latency, successful throughput, error rate, retry count, DB CPU/IO, active/waiting connections, and lock-wait duration. Faster average queries while P99 spikes on a hot row is not yet a proper optimization.

### 12.1. Auto-rolling-back Spring tests can mislead

Spring TestContext can open a transaction around `@Transactional` test methods and roll back at the end. Then `REQUIRED` services join the test's transaction; commit/rollback timing and lock lifetimes differ from the real API. To verify properly, use integration tests not wrapped by an accidental outer test transaction; call the real service through the proxy and read back after the physical transaction ends.

### 12.2. Self-invocation loses expected propagation

In Spring proxy mode, `this.innerMethod()` inside the same bean bypasses inner's transaction advice. To test `REQUIRES_NEW`, call another bean injected via Spring proxy. Do not use self-invocation and conclude `REQUIRES_NEW` has no effect.

### 12.3. Do not confuse read-your-writes with commit

A transaction can read rows it just UPDATEd even before committing. Tests should read from outside the transaction after commit/rollback to prove durable state, rather than asserting data inside the lock-holding method itself.

## 13. Checklist for investigating API slowness due to locks

When seeing timeouts or high P99, collect:

1. Exact DB engine/version, transaction isolation, and actual manager/resources.
2. Full SQL (with sensitive data redacted), WHERE/JOIN clauses, and parameters reducing selectivity.
3. Existing indexes, `EXPLAIN`, and estimated/actual rows; is the query using an index or scanning widely?
4. Are there hot rows, range locking, gap locking, or FK/trigger conflicts?
5. Waiter/blocker sessions, transaction ages, lock modes, and awaited row/index objects.
6. Which Spring code opens `@Transactional`, makes slow HTTP calls inside T, or has `REQUIRED`/`REQUIRES_NEW`/self-invocation?
7. Connection pool active/waiting counts; are transactions holding connections too long?
8. Exact timeouts/SQLStates/vendor codes; are there infinite or non-idempotent retries?
9. Do business invariants permit batching, optimistic locking, or separate transactions?
10. After changes, are throughput/latency/lock waits and business data correctness verified together?

## 14. Self-check questions

**Question 1.** Why can an UPDATE by primary key still have lock contention?

**Answer:** An index lowers lookup cost; it does not let two transactions write conflicting changes to the same row without coordination; one transaction may have to wait for the other to finish.

**Question 2.** Does a missing index mean PostgreSQL locks every scanned row?

**Answer:** No. Scan range and lock footprint are two different concepts. PostgreSQL row-locking semantics differ from InnoDB; examine the statement, plan, and isolation.

**Question 3.** Why can a locking range scan on InnoDB block an INSERT into a gap with no returned rows?

**Answer:** Under conditions such as REPEATABLE READ, next-key/gap locks can protect the scanned index interval.

**Question 4.** Can an inner `REQUIRES_NEW` wait on the exact row outer is locking?

**Answer:** Yes. Suspending outer does not release locks; the new inner transaction uses another connection and waits on the lock until timeout, as in the demo.

**Question 5.** Why shouldn't `EXPLAIN ANALYZE` be run carelessly with UPDATE on real data?

**Answer:** Because it executes the statement. You need a test environment or a controlled transaction/rollback.

**Question 6.** The right index exists, yet P99 latency remains high. What should you inspect?

**Answer:** Hot rows, transaction duration, lock waits, DB pool occupancy, remote calls inside transactions, and retry bursts.

**Question 7.** When is `FOR UPDATE SKIP LOCKED` appropriate?

**Answer:** Queue workers with claim/lease/retry mechanisms that accept temporarily skipping locked rows; inappropriate for reports needing to inspect all data.

**Question 8.** Why should tests read the DB after the transaction ends?

**Answer:** A transaction can observe its own uncommitted changes. Only after commit/rollback do you know whether data is durable or rolled back.

## 15. Official References

- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Transactional Annotations: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL — SELECT locking clauses: https://www.postgresql.org/docs/current/sql-select.html
- PostgreSQL — `pg_locks`: https://www.postgresql.org/docs/current/view-pg-locks.html
- MySQL 8.4 — InnoDB Locking: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html
- MySQL 8.4 — InnoDB Locks Set by Different Statements: https://dev.mysql.com/doc/refman/8.4/en/innodb-locks-set.html
- MySQL 8.4 — Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- H2 — Advanced (MVCC / lock timeout): https://h2database.github.io/html/advanced.html
- H2 — Commands (`FOR UPDATE` and `SET LOCK_TIMEOUT`): https://h2database.github.io/html/commands.html

**Remember:** lock footprint depends on SQL/indexes and the DB engine; lock hold time depends on actual transaction boundaries. To increase concurrent load safely, **inspect query plans, lock waits, and DB state**, shorten transactions sensibly, narrow scan ranges where helpful, and avoid opening `REQUIRES_NEW` on rows outer still locks.