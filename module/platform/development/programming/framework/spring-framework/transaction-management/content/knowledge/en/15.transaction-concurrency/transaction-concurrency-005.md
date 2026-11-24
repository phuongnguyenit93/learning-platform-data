# Atomic Update Operations Instead of Unprotected Read-Then-Write

## 1. The problem: valid statements, wrong results under concurrent requests

In a Spring application handling concurrent requests, a very familiar code pattern is **reading a value, computing in Java, and writing it back**:

```java
int current = jdbc.queryForObject(
    "SELECT total FROM counters WHERE id = ?",
    Integer.class, 1);

int next = current + 10;

jdbc.update(
    "UPDATE counters SET total = ? WHERE id = ?",
    next, 1);
```

With a single request, the code looks reasonable. Yet when two transactions read the same initial value before either writes back, both can compute the same result and overwrite each other's changes. This is a classic example of a **lost update** when implementing *read–modify–write* without concurrency control.

An appropriate alternative for a simple addition:

```sql
UPDATE counters
SET total = total + 10
WHERE id = 1;
```

This is a **single atomic update SQL statement on the database side**: the addition uses the row value currently being updated by the database, rather than relying on the stale `current` copy read earlier in the application. In PostgreSQL under `READ COMMITTED`, writers updating the same row are coordinated by row locking; the later writer may wait for the earlier writer and proceed with the updated row version.

A business condition like "only deduct inventory if enough remains" also needs to put the **check condition** into the `UPDATE` itself:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5;
```

Then **check the number of rows actually updated** to know whether the request succeeded. Never infer success merely because SQL did not throw an exception.

Lesson objectives:

1. Clearly trace execution schedules causing lost updates even when code has `@Transactional`.
2. Distinguish **atomic SQL statements**, **multi-step transactions**, **business conditions**, and **idempotency**.
3. Use `JdbcTemplate.update(...)` and row counts to implement counter increments, stock deductions, and guarded balance debits.
4. Understand PostgreSQL `READ COMMITTED` lock waiting and `WHERE` re-evaluation.
5. Run a Java 17 + Spring Boot + PostgreSQL example with **two concurrent requests**: the unsafe way yields 110, the atomic way yields 120, and only one of two reservation requests is accepted.
6. Recognize when optimistic locking, `SELECT ... FOR UPDATE`, constraints, or stronger isolation are needed instead of a single `UPDATE`.

> **Core principle:** When business logic can be expressed as a transformation on the current row, prefer letting the **database both check and update**. Avoid pulling mutable values out of the database, computing an absolute value, and overwriting without a guard.

## 2. How does a lost update form?

Suppose `counters(id=1, total=100)`. Both transactions T1 and T2 want to add 10.

### 2.1. Unsafe pattern

```text
Time           T1                                      T2
-----------    -------------------------------------   --------------------------------
t0             committed total = 100
t1             BEGIN
t2                                                     BEGIN
t3             SELECT total -> 100
t4                                                     SELECT total -> 100
t5             Java computes next = 110
t6                                                     Java computes next = 110
t7             UPDATE SET total=110 WHERE id=1
t8             COMMIT
t9                                                     UPDATE SET total=110 WHERE id=1
t10                                                    COMMIT
t11            Final value = 110
```

Both requests executed `UPDATE` successfully and might both return HTTP 200, yet the final value only increased by **10 instead of 20**.

**Root flaw:** T2 does not ensure that `current=100` is still the valid value when T2 writes. The database can lock and serialize the two **UPDATE statements**, but that lock **cannot fix the stale literal 110 passed in by the application**.

A bare `@Transactional` does not solve this:

```java
@Transactional
public void addTen() {
    int current = jdbc.queryForObject(
        "SELECT total FROM counters WHERE id=1",
        Integer.class);

    jdbc.update(
        "UPDATE counters SET total=? WHERE id=1",
        current + 10);
}
```

`@Transactional` creates a transaction boundary; it does not by default turn two SQL statements and a Java computation in between into an indivisible update relative to another transaction. In PostgreSQL `READ COMMITTED`, the timeline above can readily happen.

### 2.2. Why don't tests always catch the bug?

If the second request reads **after the first request has committed**, it may see 110 and write 120. The right outcome happens due to a **favorable execution schedule**, not safe code.

Thus, a test spawning two threads with `sleep(100)` can miss the lost update. To demonstrate it reliably, you must synchronize so that **both read 100 before either is allowed to write**. The runnable example in Section 8 uses `CyclicBarrier` for that exact purpose.

### 2.3. Lost update vs. non-repeatable read

- **Non-repeatable read:** a transaction reads the same row twice and sees a different value because another transaction committed.
- **Lost update:** an update overwrites the result of a previous update due to using a stale value or lacking conflict detection.

The two concurrency phenomena are related but distinct. Even if the application only SELECTs **once**, writing a value computed from a stale snapshot can still cause a lost update. One fix is moving the logic into SQL; another is using optimistic version checks or locking read-for-write.

## 3. What does atomic update mean in this case?

For a single row:

```sql
UPDATE counters
SET total = total + 10
WHERE id = 1;
```

The database reads the target row's value, evaluates `total + 10`, and modifies the row as **a single SQL update statement** within its transaction/concurrency mechanics. Two concurrent statements on the same row must be coordinated so they do not silently overwrite just because both previously read an old value from Java.

In PostgreSQL under `READ COMMITTED`:

1. T1 locks the target row and executes `total = total + 10`.
2. T2 wanting to update the same row may have to **wait for T1 to finish**.
3. If T1 commits, T2 processes the updated version of the row and **re-evaluates the `WHERE` condition**.
4. If it still matches, T2 applies the transformation against the updated row value; e.g., 110 + 10 = 120.
5. If T1 rolls back, T2 can proceed based on the remaining valid state.

This is a PostgreSQL characteristic documented under transaction isolation for `UPDATE` in `READ COMMITTED`. Do not infer from it that every database and isolation level behaves identically; PostgreSQL `REPEATABLE READ`/`SERIALIZABLE` may raise a serialization error on update contention instead of silently continuing.

### 3.1. Right and wrong ways to increment a counter

| Pattern | Correctness when multiple writers increment one row |
| --- | --- |
| `SELECT total` → Java `total + 10` → `UPDATE SET total=?` | **Dangerous:** can overwrite another writer's calculation |
| `UPDATE SET total=total+10 WHERE id=?` | Increment inside one statement, suitable for simple single-row counters |
| `SELECT ... FOR UPDATE` → Java compute → `UPDATE` in same transaction | Can be correct if the read lock is held until write/commit, though longer and risks holding locks too long |
| `UPDATE ... WHERE version=?` and check row count | Optimistic compare-and-swap; on conflict must retry/reject |
| `synchronized` in one JVM then read/write | Does not protect across multiple JVMs/instances, batch jobs, or other apps writing to the same DB |

**Note:** "atomic UPDATE" here refers to the guarantee of **that specific SQL update**, not that an entire workflow including emails, APIs, and external payments is a single atomic transaction.

### 3.2. Checking the updated row count

Even a proper statement like `UPDATE counters SET total=total+10 WHERE id=?` can update **0 rows** if the ID does not exist. With a unique primary key ID, expect:

- `1` row updated: the target row was processed.
- `0` rows updated: no matching row; for conditional statements, possibly insufficient stock/failed condition.
- `>1` rows: contradicts the "single unique ID" assumption; inspect SQL/schema or treat as an error.

`JdbcTemplate.update(...)` returns the affected row count, not the column's value after updating. You must **check the result** rather than ignoring it.

## 4. Putting business conditions inside the UPDATE itself

A simple counter increment needs no complex conditions. However, balance deduction, stock reservation, or quota enforcement requires **writing only when the current state satisfies a predicate**.

### 4.1. Wrong way: check once, write later

Suppose inventory has 7 units; two customers each order 5:

```text
T1: SELECT stock -> 7; Java: 7 >= 5, allow order
T2: SELECT stock -> 7; Java: 7 >= 5, allow order
T1: UPDATE inventory SET stock=2 WHERE id=1; COMMIT
T2: UPDATE inventory SET stock=2 WHERE id=1; COMMIT
```

Both requests are told they succeeded; total promised units are **10** even though initial stock was only **7**. The final stock `2` looks non-negative at a glance, yet the system **oversold**.

Another flawed variant:

```java
int stock = readStock();
if (stock >= requested) {
    jdbc.update(
        "UPDATE inventory SET stock = stock - ? WHERE id = ?",
        requested, itemId);
}
```

Even though the `UPDATE` inside the `if` uses an atomic subtraction, **the "enough stock" decision was still made from a stale SELECT result**. Two requests can both pass the `if` and then subtract, driving stock negative or hitting a constraint error. An atomic transformation **is not enough** if the business predicate is separated from the statement itself.

### 4.2. Right way: a conditional UPDATE

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1
  AND stock >= 5;
```

Two concurrent requests on an inventory row with stock=7 cannot both succeed merely by seeing the old snapshot 7 in Java:

- Request processed first: reduces 7 → 2, updated row count = 1.
- Remaining request: after the row is updated, `stock >= 5` is no longer true; updated row count = 0 in PostgreSQL `READ COMMITTED`.
- Result: **exactly one request is accepted**, stock left = 2.

The `stock >= ?` condition sits **inside the same statement** as `stock = stock - ?`. That is the core point. Checking the condition first and then updating in a separate SQL statement is not equivalent.

### 4.3. Combining with database constraints

PostgreSQL schema example:

```sql
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
```

`CHECK (stock >= 0)` is an extra guardrail: other writers cannot push stock negative and still commit under normal design. It **does not replace** the conditional UPDATE: with only the constraint, one of two requests might receive a SQL exception instead of an "out of stock" business result, and seeing non-negative stock does not prove another allocation flow did not oversell.

Combine:

1. **Atomic conditional UPDATE** to decide success/failure at write time.
2. **DB constraint** to block invalid state even across other code paths.
3. **Updated row count** to reflect the business outcome.
4. **A broader transaction** if orders or ledger entries must also be written alongside the stock change.

### 4.4. Do not let negative/zero inputs invert the meaning

If `requested=-5`, `stock = stock - requested` actually **increases** inventory. If `requested=0`, it may return row count 1 with no meaningful change. Validate inputs:

```java
if (requested <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive");
}
```

Similarly for debit amounts: require positive values, choose precise monetary types such as `DECIMAL/NUMERIC` and `BigDecimal`, and do not use `double` for money requiring exactness.

## 5. Three SQL patterns worth knowing

### 5.1. Counter / count / quantity increment and decrement

```sql
UPDATE counters
SET total = total + 1
WHERE id = :id;
```

The SQL above illustrates a **named parameter**, requiring `NamedParameterJdbcTemplate` or a SQL client supporting named parameters; plain `JdbcTemplate` uses `?` placeholders. This is the right pattern when incrementing a counter based on its current value.

For a non-negative conditional decrement:

```sql
UPDATE counters
SET total = total - :decrement
WHERE id = :id
  AND total >= :decrement;
```

Check the row count and validate `decrement > 0`.

### 5.2. Debit if balance is sufficient

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
```

Include `CHECK (balance >= 0)` if negative balances are forbidden, enforce exact numeric types, and use idempotency/ledgers when handling potentially retried requests.

Do not use:

```text
balance = SELECT ...
if (balance >= amount) {
    UPDATE accounts SET balance = balance - amount
}
```

because the `if` lies outside the statement, unless proper locks are held on the row in the same transaction. Even a balance-safe statement **does not automatically guarantee an entire money transfer operation**; see the multi-row section.

### 5.3. Compare-and-swap / optimistic version check

When a change cannot be expressed as simple arithmetic, you can require the record **still be at the exact version** the client read:

```sql
UPDATE accounts
SET display_name = :newName,
    version = version + 1
WHERE id = :accountId
  AND version = :expectedVersion;
```

If 1 row is updated, the change is accepted. If 0 rows, there may be a conflict because another writer incremented the version, or the ID does not exist; you must **retry with fresh data or report a conflict**, never silently return success.

Essential condition: **every code path modifying the record must respect the version mechanism** (or have a compatible strategy). If one writer runs `UPDATE accounts SET ... WHERE id=?` without incrementing version, optimistic locking elsewhere may miss that change.

Spring Data JPA supports `@Version` for optimistic locking on managed entities; manual SQL compare-and-swap is the equivalent pattern at the row-count level. Do not confuse `@Version` and `UPDATE SET total=total+1` as the same tool; each solves a different kind of update.

## 6. Using `JdbcTemplate.update` properly

Spring JDBC provides the API:

```java
int affected = jdbc.update(
    "UPDATE inventory " +
    "SET stock = stock - ? " +
    "WHERE id = ? AND stock >= ?",
    requested, productId, requested);
```

`affected` is the number of rows the JDBC driver reports were updated. Assuming `id` is the primary key and there are no unusual triggers in the example:

```java
public boolean reserveStock(
        JdbcTemplate jdbc,
        int productId,
        int requested) {

    if (requested <= 0) {
        throw new IllegalArgumentException(
            "Quantity must be positive");
    }

    int affected = jdbc.update(
        "UPDATE inventory SET stock = stock - ? " +
        "WHERE id = ? AND stock >= ?",
        requested, productId, requested);

    if (affected == 1) {
        return true;
    }
    if (affected == 0) {
        return false;
    }
    throw new IllegalStateException(
        "More than one row updated: " + affected);
}
```

This is an **illustrative Java method**; place it in a class, import `JdbcTemplate`, and ensure the proper DataSource. Section 8 contains a complete Spring Boot project.

**`false` here means no row was deducted.** It can happen because:

- The ID does not exist.
- The row exists but stock is insufficient.
- Another predicate failed.

A follow-up SELECT after failure can help craft a more detailed message, but **never use a subsequent SELECT to overturn an `affected==0` decision**. State may keep changing due to other requests. If distinguishing missing ID from insufficient stock with strict guarantees is required, design the model/API and transaction control accordingly.

### 6.1. Prepared parameters, never concatenate SQL from input

Right:

```java
jdbc.update(
    "UPDATE inventory SET stock=stock-? " +
    "WHERE id=? AND stock>=?",
    qty, id, qty);
```

Wrong:

```java
String sql = "UPDATE inventory SET stock=stock-" + qty
    + " WHERE id=" + id;
```

Even when a demo uses integers, build the habit of prepared parameters to avoid SQL injection on other input paths, keep types clear, and ease testing.

### 6.2. `@Transactional` is still needed for multi-SQL operations

A single `UPDATE` is typically executed atomically by the database at the statement level even when the application runs in autocommit mode. Yet if business logic needs **deduct stock + create order + write ledger** as one commit/rollback unit, a transaction spanning those SQL statements is needed:

```java
@Transactional
public void createOrder(int productId, int quantity) {
    int changed = jdbc.update(
        "UPDATE inventory SET stock=stock-? " +
        "WHERE id=? AND stock>=?",
        quantity, productId, quantity);

    if (changed != 1) {
        throw new InsufficientStockException(
            "Stock not available");
    }

    jdbc.update(
        "INSERT INTO orders(product_id, quantity) VALUES (?, ?)",
        productId, quantity);
}
```

This is an **illustrative snippet**, needing `InsufficientStockException extends RuntimeException` and an `orders` table. If the INSERT fails after deducting stock, default rollback for runtime exceptions undoes the stock UPDATE too when both SQL statements belong to the real transaction.

Do not treat `@Transactional` as a "charm" against stale reads: the `UPDATE` condition itself is what prevents overselling in the case above.

## 7. How the database protects conditional UPDATEs under contention

### 7.1. PostgreSQL READ COMMITTED

Suppose stock is 7, and T1 and T2 both send:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5;
```

Under PostgreSQL `READ COMMITTED`, the `UPDATE` locates matching rows; if another writer is modifying the same row, it can **wait** for that writer to commit or roll back. When the first writer commits, PostgreSQL proceeds with the new row version and **re-evaluates `WHERE`** on the target row. Because 2 is no longer >= 5, the second statement updates 0 rows.

This makes keeping **both the condition and the mutation in the same statement** crucial. If T2 used:

```sql
UPDATE inventory
SET stock = 2
WHERE id = 1;
```

even after waiting for the lock, it would still set literal 2 from its stale calculation. The row lock coordinates DB access, but does not know the meaning of "order 5 items" and cannot turn a stale literal into a valid subtraction.

### 7.2. Do not assume identical behavior across all isolation levels

Under PostgreSQL `REPEATABLE READ` or `SERIALIZABLE`, a concurrent update can cause one transaction to abort with a serialization error instead of succeeding with row count 0 as in the `READ COMMITTED` scenario. Production code must have a retry policy or return an appropriate error when the DB reports a conflict; **never claim row count alone always suffices to distinguish all outcomes**.

In MySQL InnoDB, locking/current reads, transaction isolation, and unique/foreign key constraints have their own rules. Conditional UPDATEs are also useful there, but must be tested on the exact engine/level/version. Do not use H2 output as absolute proof for PostgreSQL or MySQL.

### 7.3. Locks are held only up to the appropriate transaction boundary

To avoid deadlocks and preserve throughput:

- Keep transactions short; **do not make long HTTP/email calls** while holding row locks unless required by design and thoroughly evaluated.
- Have appropriate indexes/primary keys for `WHERE id=?` to avoid wide scans that enlarge contention scope.
- When multiple rows must be updated, use a stable lock order and bounded retries for deadlock/serialization errors.
- Define clear business rules for 0 updated rows: out of stock, conflict, or not found.

## 8. Runnable example: unsafe vs. atomic vs. conditional reservation

This lab intentionally uses **PostgreSQL** to verify the database's own `READ COMMITTED` behavior rather than relying on in-memory simulation. A **Java 17 + Spring Boot 3.3.13 + Spring JDBC + PostgreSQL 16** project is provided with complete source code and run commands. Versions are pinned for reproducibility, **not necessarily the latest releases**.

### 8.1. Project structure

```text
atomic-update-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/atomic/
    │   ├── AtomicUpdateApplication.java
    │   └── AtomicOperations.java
    └── resources/
        └── application.yml
```

Use the project's Gradle Wrapper generated by Spring Initializr/Gradle, compatible with Java 17 and Spring Boot 3.3. This is a **multi-file project**; individual Java files cannot be run solely with `javac` without the Spring classpath.

**`settings.gradle`**

```groovy
rootProject.name = 'atomic-update-lab'
```

**`build.gradle`**

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

The Spring Boot JDBC starter provides `JdbcTemplate`, transaction infrastructure, and a connection pool (typically HikariCP). The PostgreSQL JDBC driver is a runtime dependency; Boot manages starter/driver versions in this configuration.

### 8.2. Lab-only database

You can spin up a PostgreSQL container with Docker (port 55434 must be free):

```bash
docker run -d --name atomic-lab-pg \
  -e POSTGRES_DB=atomiclab \
  -e POSTGRES_USER=atomiclab \
  -e POSTGRES_PASSWORD=local_only \
  -p 55434:5432 postgres:16
```

On Windows PowerShell, use a single line:

```powershell
docker run -d --name atomic-lab-pg -e POSTGRES_DB=atomiclab -e POSTGRES_USER=atomiclab -e POSTGRES_PASSWORD=local_only -p 55434:5432 postgres:16
```

Check that the database is ready:

```bash
docker exec atomic-lab-pg pg_isready -U atomiclab -d atomiclab
```

Password `local_only` is a **demo password**; do not reuse it in production. Do not expose the lab PostgreSQL on untrusted networks; if needed, bind only to localhost and configure security per environment.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:postgresql://localhost:55434/atomiclab"
    username: ${DB_USER:atomiclab}
    password: ${DB_PASSWORD:local_only}
    hikari:
      maximum-pool-size: 5
```

A pool of 5 connections is enough for **two concurrent transactions** to hold connections during the experiment. Do not use pool size=1 when both tasks open transactions and wait for each other at a barrier, because the second worker may fail to acquire a connection while the first waits until timeout.

### 8.3. Service with three methods

**`src/main/java/demo/atomic/AtomicOperations.java`**

```java
package demo.atomic;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AtomicOperations {
    private final JdbcTemplate jdbc;

    public AtomicOperations(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Intentionally wrong to demonstrate lost updates under concurrency.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void unsafeAddTen(CyclicBarrier bothRead) {
        int current = jdbc.queryForObject(
            "SELECT total FROM counters WHERE id=1",
            Integer.class
        );

        // Both transactions must read 100 before writing back.
        waitUntilBothRead(bothRead);

        jdbc.update(
            "UPDATE counters SET total=? WHERE id=1",
            current + 10
        );
    }

    // Correct for simple increment: uses the current value in the DB.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public int atomicAddTen() {
        return jdbc.update(
            "UPDATE counters SET total=total+10 WHERE id=1"
        );
    }

    // Both checks and updates stock in the same statement.
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public boolean reserveFive() {
        int changed = jdbc.update(
            "UPDATE inventory " +
            "SET stock=stock-5 " +
            "WHERE id=1 AND stock>=5"
        );

        if (changed == 0) {
            return false;
        }
        if (changed == 1) {
            return true;
        }
        throw new IllegalStateException(
            "Unexpected updated row count: " + changed);
    }

    private static void waitUntilBothRead(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted during demo", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException(
                "Failed to coordinate concurrent reads", ex);
        }
    }
}
```

Explanation:

- `unsafeAddTen` reads `current` **into Java**, synchronizes both readers via a barrier, and then writes a **literal** `current+10`; unsafe, yet needed for the comparison experiment.
- `atomicAddTen` performs the addition directly inside one `UPDATE` statement. The returned `int` is the **updated row count**, not `total`; with existing ID 1, 1 is expected.
- `reserveFive` puts `stock>=5` inside `WHERE` and relies on the row count, without a prior SELECT. The true/false result represents whether the reservation succeeded or failed.
- Each public method is invoked through the bean proxy from the coordinator, so `@Transactional` takes effect. `waitUntilBothRead` is a static helper and needs no annotation.
- The barrier **serves only to reproduce the schedule**, not as a technique for production request handling.

### 8.4. Runner to initialize data and invoke two workers

**`src/main/java/demo/atomic/AtomicUpdateApplication.java`**

```java
package demo.atomic;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
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
public class AtomicUpdateApplication {

    public static void main(String[] args) {
        SpringApplication.run(AtomicUpdateApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            AtomicOperations operations) {

        return args -> {
            // Run ONLY on a LAB database.
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS counters (" +
                "id INTEGER PRIMARY KEY, " +
                "total INTEGER NOT NULL)"
            );

            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS inventory (" +
                "id INTEGER PRIMARY KEY, " +
                "stock INTEGER NOT NULL CHECK (stock >= 0))"
            );

            jdbc.execute("TRUNCATE TABLE counters, inventory");

            jdbc.update(
                "INSERT INTO counters(id, total) VALUES (1, 100)"
            );
            jdbc.update(
                "INSERT INTO inventory(id, stock) VALUES (1, 7)"
            );

            ExecutorService workers = Executors.newFixedThreadPool(2);

            try {
                // A. Two transactions both SELECT 100 then write back 110.
                CyclicBarrier bothRead = new CyclicBarrier(2);

                Future<?> unsafe1 =
                    workers.submit(() ->
                        operations.unsafeAddTen(bothRead));
                Future<?> unsafe2 =
                    workers.submit(() ->
                        operations.unsafeAddTen(bothRead));

                unsafe1.get(30, TimeUnit.SECONDS);
                unsafe2.get(30, TimeUnit.SECONDS);

                System.out.println(
                    "Unsafe final total: " + total(jdbc));

                // B. Reset total, both requests use atomic UPDATE.
                jdbc.update(
                    "UPDATE counters SET total=100 WHERE id=1"
                );

                CountDownLatch startAtomic = new CountDownLatch(1);

                Future<Integer> atomic1 = workers.submit(() -> {
                    startAtomic.await();
                    return operations.atomicAddTen();
                });
                Future<Integer> atomic2 = workers.submit(() -> {
                    startAtomic.await();
                    return operations.atomicAddTen();
                });

                startAtomic.countDown();

                if (atomic1.get(30, TimeUnit.SECONDS) != 1
                        || atomic2.get(30, TimeUnit.SECONDS) != 1) {
                    throw new IllegalStateException(
                        "Counter row was not updated");
                }

                System.out.println(
                    "Atomic final total: " + total(jdbc));

                // C. Both requests ask for 5 when initial stock is only 7.
                CountDownLatch startReserve = new CountDownLatch(1);

                Future<Boolean> reserve1 = workers.submit(() -> {
                    startReserve.await();
                    return operations.reserveFive();
                });
                Future<Boolean> reserve2 = workers.submit(() -> {
                    startReserve.await();
                    return operations.reserveFive();
                });

                startReserve.countDown();

                boolean ok1 = reserve1.get(30, TimeUnit.SECONDS);
                boolean ok2 = reserve2.get(30, TimeUnit.SECONDS);

                int accepted = (ok1 ? 1 : 0) + (ok2 ? 1 : 0);

                System.out.println(
                    "Accepted reservations: " + accepted);
                System.out.println(
                    "Remaining stock: " + stock(jdbc));
            } finally {
                workers.shutdownNow();
            }
        };
    }

    private static int total(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT total FROM counters WHERE id=1",
            Integer.class
        );
    }

    private static int stock(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT stock FROM inventory WHERE id=1",
            Integer.class
        );
    }
}
```

QA points for the runner:

- `CREATE TABLE IF NOT EXISTS` and `TRUNCATE` touch only the **two demo tables**, yet `TRUNCATE` deletes existing rows; use a dedicated lab database and never point to production by mistake.
- There is no `@Transactional` on the runner. Both tasks call `operations` through the **Spring proxy** from separate threads; each call opens its own transaction at `READ_COMMITTED`.
- Once both `unsafe` futures complete, both corresponding transactions have finished through the proxy before `total` is read.
- `CyclicBarrier(2)` forces both tasks to retrieve `100` before writes occur, reproducing the lost-update schedule deterministically.
- `CountDownLatch` aligns the timing of the two atomic/reserve tasks, though SQL correctness **does not depend on thread speed**.
- Data reset statements run **after previous tasks have finished**, never mutating data mid-flight while an earlier transaction is still running.

### 8.5. Running the program and stdout

With Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

After Gradle/Spring Boot logs, the program prints these exact four lines **when the database is running, there are no other writers, no timeouts occur, and code/config match the above**:

```text
Unsafe final total: 110
Atomic final total: 120
Accepted reservations: 1
Remaining stock: 2
```

Explanation:

1. **Unsafe 110:** both SELECT 100, compute `100+10=110`, and write literal 110; only one increment is reflected.
2. **Atomic 120:** reset to 100, two `UPDATE total=total+10` statements update the same row; 1 row each time, ending at 120.
3. **Accepted 1:** starting from stock=7, the first request deducts 5 down to 2; the remaining request fails `stock>=5` and gets row count 0.
4. **Stock 2:** the system accepts only the amount actually available; no overselling.

The unsafe part is designed to **demonstrate the bug**; do not copy it to production. If the database is at a different isolation level (e.g., PostgreSQL `REPEATABLE READ`) or has other triggers/constraints, one of the transactions might abort instead of completing the schedule above; that is why the example explicitly sets `READ_COMMITTED` and uses a dedicated lab DB.

## 9. Hands-on verification with two psql windows

You do not need Java to observe the database's locking mechanism. Open two separate `psql` terminals/sessions against a PostgreSQL sandbox. Initialize when no transactions are open:

```sql
CREATE TABLE IF NOT EXISTS manual_stock (
    id INTEGER PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

TRUNCATE TABLE manual_stock;
INSERT INTO manual_stock(id, stock) VALUES (1, 7);
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE manual_stock
SET stock=stock-5
WHERE id=1 AND stock>=5;
-- UPDATE 1

-- Do not COMMIT yet; keep the session in an open transaction state.
```

**Session B (started while A has not committed):**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

UPDATE manual_stock
SET stock=stock-5
WHERE id=1 AND stock>=5;
-- May WAIT for Session A's row lock.
```

**Session A:**

```sql
COMMIT;
```

**Session B continues:**

```text
UPDATE 0
```

B executes:

```sql
COMMIT;
SELECT stock FROM manual_stock WHERE id=1;
-- 2
```

This is the typical timeline when A commits first: B waits and then re-checks `stock>=5` on the new version; seeing stock=2, it updates nothing. If A **ROLLS BACK** instead of committing, B can proceed from stock=7 and update 1 row; the outcome depends on timing/the prior transaction's conclusion, never deducting twice based on a stale snapshot when stock is insufficient.

**Do not** run this lab on a real DB shared with other applications. `TRUNCATE` deletes all rows in the demo table.

## 10. UPDATE ... RETURNING: updating and fetching the new value together

PostgreSQL supports `RETURNING` on `UPDATE`:

```sql
UPDATE inventory
SET stock = stock - 5
WHERE id = 1 AND stock >= 5
RETURNING id, stock;
```

If stock is sufficient, the statement returns one row containing the ID and the **post-update** stock. If no row meets the condition, it returns **zero rows**. This avoids a separate `SELECT` after UPDATE just to read the new stock, which could otherwise observe a newer change from another request before the application reads it.

In Spring JDBC, a query with `RETURNING` is SQL that produces a **result set**. You can use `JdbcTemplate.query(...)`:

```java
List<Integer> remaining = jdbc.query(
    "UPDATE inventory " +
    "SET stock = stock - ? " +
    "WHERE id = ? AND stock >= ? " +
    "RETURNING stock",
    (rs, rowNum) -> rs.getInt("stock"),
    requested, productId, requested
);

if (remaining.isEmpty()) {
    // No rows matched the condition.
} else if (remaining.size() == 1) {
    int newStock = remaining.get(0);
    // Updated, holding the exact post-update stock of this statement.
} else {
    throw new IllegalStateException("Expected one inventory row");
}
```

This is an **illustrative Java snippet**; it needs `import java.util.List`, variables `jdbc`, `requested`, `productId`, and an appropriate transaction manager. The PostgreSQL JDBC driver must support `RETURNING` in the usual way; do not copy this SQL verbatim to every dialect without verifying.

Do not write:

```java
int affected = jdbc.update(
    "UPDATE inventory ... RETURNING stock");
```

expecting `affected` to be the **new stock**. `JdbcTemplate.update` is designed to return an **update count**, whereas `RETURNING` returns data rows and normally uses a query API. Using `queryForObject` on 0 rows can throw `EmptyResultDataAccessException`; `query` returning an empty list is easier to handle as a condition failure.

## 11. Optimistic locking: when reading, complex computing, and then writing are needed

Not all logic fits neatly into `SET total=total+1`. You may need to read multiple fields, apply business rules in Java, and update the whole aggregate.

Optimistic locking pattern with version:

1. Read the row along with `version=5`.
2. Compute the new state in Java.
3. Send:

```sql
UPDATE customer_profiles
SET display_name = ?,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = ?
  AND version = ?;
```

4. If row count is 1: updated against the right version.
5. If row count is 0: the row was deleted or modified concurrently; do not overwrite with stale data. Reload and **decide to retry or return HTTP 409 Conflict** per API contract.

### 11.1. Compare-and-swap with old value

If the schema has no version column but a column can serve as a guard, you can write:

```sql
UPDATE settings
SET current_value = :newValue
WHERE id = :id
  AND current_value = :expectedValue;
```

Similar to CAS: write only if the value is still what was just read. However, if the value changed **A → B → A** between the two points (*ABA problem*), comparing the old value may miss the intermediate change. A monotonically increasing version is usually preferable when **every modification** must be detected.

### 11.2. Do not retry infinitely

When an optimistic update returns 0 rows due to conflict, retries must:

- Bound attempts and consider backoff.
- Re-read state and **recompute business logic**, not just repeat stale literals.
- Keep external side effects (email, payments, events) outside retried attempts, or use idempotency/outbox.
- Distinguish not found, version conflict, and business rejection.

For APIs with high write rates on a single "hot row," continuous retries can add extra load. Sometimes a direct `UPDATE SET x=x+?` suits simple counter increments better than optimistic versioning.

## 12. When is `SELECT ... FOR UPDATE` appropriate?

Another way to protect complex read-modify-write logic is to **lock the row before reading**, then write within the **same transaction**:

```java
@Transactional
public void changeAccountComplexly(long accountId) {
    AccountSnapshot account = jdbc.queryForObject(
        "SELECT id, balance, status FROM accounts " +
        "WHERE id=? FOR UPDATE",
        (rs, rowNum) -> new AccountSnapshot(
            rs.getLong("id"),
            rs.getBigDecimal("balance"),
            rs.getString("status")),
        accountId
    );

    // Compute business logic using values read under the lock.
    // Execute UPDATE in the same transaction/connection.
}
```

This is **illustrative code**, needing the `AccountSnapshot` record/class and actual UPDATE. `SELECT ... FOR UPDATE` in PostgreSQL can acquire a row lock and make other writers wait; the lock is held per the transaction boundary. Without an enclosing transaction, an autocommit connection can release the lock right after SELECT, leaving the subsequent Java computation unprotected.

Comparing choices:

| Requirement | Usually preferred option |
| --- | --- |
| Increment a counter | `UPDATE SET counter=counter+?` |
| Deduct stock if sufficient | `UPDATE ... SET stock=stock-? WHERE stock>=?` |
| Edit only if client still holds latest version | `UPDATE ... WHERE id=? AND version=?` or JPA `@Version` |
| Evaluate complex rules needing consistent row state | `SELECT ... FOR UPDATE` in a short transaction, or optimistic version |
| Enforce invariant across multiple rows | Constraints, suitable locking, `SERIALIZABLE` with retry, or schema redesign; a single row lock may not suffice |

If `SELECT` returns **no rows**, `FOR UPDATE` does not automatically lock every "gap" needed to block a future INSERT on every engine. For overlapping bookings/predicate-based limits, consider unique/exclusion constraints or a dedicated serialization strategy.

## 13. Not every business change fits in one SQL statement

### 13.1. Transferring money between two accounts

A guarded debit statement preventing negative balance:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :fromId
  AND balance >= :amount;
```

Yet a transfer also needs to **credit the destination account** and possibly insert a ledger entry. To prevent "debited but not credited," a shared transaction is needed:

```text
BEGIN transaction
  UPDATE source SET balance=balance-amount
    WHERE id=source AND balance>=amount
  assert affected=1, otherwise rollback
  UPDATE destination SET balance=balance+amount
    WHERE id=destination
  assert affected=1, otherwise rollback
  INSERT transfer_ledger(...)
COMMIT transaction
```

That is **pseudocode**, not a single SQL command. Use `@Transactional` at the service boundary through a Spring proxy so debit, credit, and ledger commit/roll back together. You must verify destination account existence, limits, request identity, lock ordering, and exact currency handling.

### 13.2. Multi-row invariants

For example: "no more than 100 OPEN orders" is an invariant over a **result set**. Two requests can both see COUNT=99 and both INSERT; an atomic update on an individual order row **cannot** enforce the total invariant.

Capacity can be moved into **a quota row** updated via conditional decrement/claim; or use constraints, locking, or serializable isolation. The choice must fit the schema and contention profile.

### 13.3. Do not equate database atomicity with external side effects

Sending emails, calling payment providers, publishing to Kafka, or writing external files do not automatically participate in JDBC transactions. A transaction rollback does not recall an already-completed API call. With retries, the risk of duplicated side effects grows even larger. Use transactional outbox, idempotency, after-commit processing, or compensation depending on business needs.

## 14. Spring Data JPA: bulk updates and persistence context

If the project uses Spring Data JPA, a conditional update can be expressed in JPQL:

```java
public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Inventory i
        set i.stock = i.stock - :quantity
        where i.id = :id and i.stock >= :quantity
        """)
    int reserve(
        @Param("id") Long id,
        @Param("quantity") int quantity
    );
}
```

This is an **illustrative snippet**, requiring an `Inventory` entity with `stock` and `id` fields, Spring Data JPA imports, and a proper transaction boundary. The `int` return is the updated row count; the service must check it. `@Modifying` indicates this is a modifying query, not a substitute for business `@Transactional`. JPQL does not match the exact SQL syntax of every dialect.

**Major warning:** bulk JPQL updates go straight to the database and do not automatically update `Inventory` objects already loaded in `EntityManager`. `clearAutomatically=true` can evict managed state from the persistence context; if unflushed changes remain, you risk losing those changes. `flushAutomatically=true` also affects SQL ordering. Choose these options per your actual architecture; do not enable them blindly while pending managed changes exist.

Another approach is loading the entity and using `@Version` so Hibernate/JPA performs optimistic locking. This works well when entity-level semantics and Java-computed values are desired. However, you must handle `OptimisticLockException` and retries/responses; do not assume `@Version` automatically fixes bulk updates or writers outside JPA.

### 14.1. Cached data and read-after-write

Inside a transaction with a JPA persistence context, after a bulk update, an already-loaded entity can still hold the stale `stock` field in RAM. Never rely on that field as the answer to "how much stock remains" unless properly synchronized/updated. Use SQL `RETURNING` or re-query in the right context, managing refresh/clear deliberately. In the main JDBC lesson, `JdbcTemplate` has no first-level entity cache like JPA.

## 15. Atomic does not mean idempotent

A statement:

```sql
UPDATE inventory SET stock=stock-5
WHERE id=1 AND stock>=5;
```

is atomic regarding the check-and-deduct on the row, yet **if the same request is submitted twice**, each submission is its own valid request and can deduct twice if enough stock remains.

Example:

- Client sends a request reserving 2 items; server deducts stock and commits.
- The HTTP response is lost due to a network blip.
- Client retries the identical payload.
- Server executes it again unless it recognizes this as the **same business request**.

An idempotency key (e.g., unique `request_id`), ledger, or processed-transaction record is needed. A design flow:

1. Each operation carries a unique `request_id` and identifies the user/client.
2. In the same transaction, attempt to register `request_id` in a table with a **UNIQUE constraint**.
3. If the key was already processed, return the previously recorded result per policy, **without deducting stock again**.
4. If the key is new, execute the guarded UPDATE, record the outcome status, and commit together.

This requires additional table/state design and handling contention on the same key; `@Transactional` + unique constraint help synchronize, and cannot be replaced by an in-memory Java boolean on one app instance. **Atomic updates protect the consistency of a single execution; idempotency protects against processing the same business intent twice.**

## 16. Transaction isolation and concurrency errors do not vanish automatically

### 16.1. READ COMMITTED

In PostgreSQL `READ COMMITTED`, a row-level UPDATE with a simple predicate is a suitable model for guarded increments/decrements. Within a transaction containing multiple SELECT/UPDATE statements across different rows, each statement has its own snapshot/coordination; do not assume an entire multi-row invariant is automatically protected by one update.

### 16.2. REPEATABLE READ / SERIALIZABLE

At stronger isolation levels, PostgreSQL can reject a contending update with a **serialization failure (SQLSTATE 40001)**. You must retry the **entire transaction** with fresh data, rather than merely re-running the SQL statement inside the errored transaction. `SERIALIZABLE` prevents complex anomalies by aborting certain conflicting transactions.

**Do not** interpret atomic updates as "deadlocks/serialization exceptions can never happen." Correctness under conflict may require failing the transaction and retrying.

### 16.3. Deadlocks when updating multiple rows

Two transfers touching accounts A and B while locking in opposite order can deadlock. Mitigations:

- Update/lock IDs in a consistent order whenever possible.
- Keep transactions short.
- Ensure proper indexes.
- Bounded retries for appropriate deadlock/serialization errors.
- Never ignore exceptions and return success.

### 16.4. Checking read-only and proxies

`@Transactional(readOnly=true)` is a read hint/policy; it does not make an `UPDATE` atomic or authorize writes. Write methods need an appropriate transaction policy. Methods receive advice only when invoked through a Spring-managed proxy in standard proxy mode; self-invocation `this.method()` can bypass a new transaction boundary.

A single `UPDATE` is still handled by the DB per actual transaction/autocommit mode, yet additional SQL statements may not share the same atomic unit if Spring advice does not trigger as intended.

## 17. Performance, hotspots, and data types

### 17.1. High-contention rows

If every request increments a single counter, one hot row becomes a contention point; atomic SQL **preserves correctness**, not infinite throughput. Under heavy load, consider:

- Counter sharding / striped counters if business allows eventual consistency aggregation.
- Appending events to a separate table and aggregating later.
- Batch updates or queue architectures when accuracy requirements differ.
- Measuring transaction latency, lock waits, and deadlocks under realistic load.

Switching from `SELECT + UPDATE` to one SQL statement usually reduces round trips, though one hot row must still coordinate multiple writers.

### 17.2. Integer bounds and monetary types

- For counters that may grow large, use `BIGINT` in the DB and Java `long`; still guard against overflow.
- For money, prefer `NUMERIC/DECIMAL` and Java `BigDecimal`, enforcing decimal scale.
- For stock, enforce `stock >= 0` and validate `requested > 0`; if totals can be large, use `BIGINT` where appropriate.
- Do not assume atomic updates prevent invalid inputs or overflow.

### 17.3. Row counts and business messages

For instance, a reservation returning row count 0 signals **deduction is not permitted under current conditions**. The application can return HTTP 409 Conflict, 422 Unprocessable Content, or an out-of-stock message per API contract. Distinguish technical errors (DB down/timeout/deadlock) from business condition failures (insufficient stock). Do not interpret every SQL exception as "out of stock."

## 18. Concurrency testing process

A reliable test must actively control the execution schedule rather than relying on random request volume.

### 18.1. Minimum scenarios

| Scenario | Expected outcome |
| --- | --- |
| Two workers both read 100 then `SET total=110` | Lost update: final 110 |
| Two workers both `SET total=total+10` | Final 120 |
| Stock 7, two workers both request 5 via guarded UPDATE | Exactly 1 succeeds; stock=2 |
| Stock 3, request 5 | 0 rows updated; stock=3 |
| Stock 7, request 0 or negative | Input validated, no update |
| 0 returned on optimistic version UPDATE | Report conflict/reload, do not return success |
| Guarded UPDATE succeeds then another INSERT fails in same transaction | Full rollback per policy; stock restored to pre-operation value |
| Same request_id retried | Not deducted twice if idempotency is implemented |

### 18.2. Measuring the right outcome

1. Use a production-like database and two truly separate transactions/connections.
2. Invoke services through the Spring-managed proxy, not raw `new` or self-invocation.
3. Synchronize read/write timing with `CyclicBarrier`/`CountDownLatch` to reproduce races; do not use `Thread.sleep` as proof.
4. Set timeouts to guard tests, without relying on timeouts to enforce ordering.
5. Check **row counts** and read data **after worker transactions finish**.
6. Separate `READ COMMITTED` tests from other isolation tests so identical behavior is not assumed.
7. Test conflict/0-row cases as well, not just the happy path.
8. If a test has an outer `@Transactional`, understand the test transaction may roll back at the end or cause same-thread calls to join the test transaction. Do not treat it as observing a real commit.
9. When using Spring Data JPA, eliminate persistence-context cache effects if the goal is observing DB values right after commit.

### 18.3. Do not merely count SQL statements

An application can use just **one UPDATE** and still be wrong if:

- `WHERE` omits a business condition.
- `SET` uses a literal computed from a stale value.
- A 0 row count is not checked.
- The right row is updated, or rather the wrong tenant/account is written due to missing `tenant_id=?`.
- Requests are duplicated without idempotency.
- The business operation truly requires multi-table atomicity while only one statement is guarded.
- Deadlock/serialization errors are ignored.
- DB constraints and versioning are not applied uniformly across all write paths.

Thus, the unit of evaluation is not merely the count of SQL statements, but the **predicate, transformation, transaction boundary, and business outcome**.

## 19. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "With `@Transactional`, SELECT → Java compute → UPDATE is automatically safe" | No; transactions still run concurrently, and read values can go stale |
| "Because the database has row locks, `SET total=110` will become 120" | Row locks do not know the `+10` math done in Java; the literal stays 110 |
| "`UPDATE stock=stock-?` always prevents overselling" | Only when `stock>=?` is checked in the same statement or equivalent protection exists |
| "A `SELECT` before UPDATE is enough to verify stock" | The SELECT result can become invalid once another writer commits |
| "SQL throwing no error means the update succeeded" | `UPDATE 0` can be a valid outcome; you must check the row count |
| "`JdbcTemplate.update` returns the new balance" | It returns the number of rows the driver reports were updated |
| "Atomic equals idempotent" | Resending the same request can trigger another deduction; a request key/ledger is needed |
| "One atomic statement protects email and APIs too" | Local DB transactions do not undo external side effects |
| "REPEATABLE_READ/SERIALIZABLE makes every update succeed automatically" | Deadlocks/serialization failures can happen and must be handled |
| "`@Version` automatically protects all bulk JPQL updates" | Bulk updates do not automatically use entity-level version semantics unless written in the query |
| "`synchronized` suffices in a multi-server application" | Only protects threads sharing the same JVM/monitor |
| "Re-reading right after UPDATE yields the value guaranteed by RETURNING" | A separate SELECT can see another transaction's newer commit; use `RETURNING` if you need the statement's own value |

## 20. Self-check questions

**1. Two requests both read total 100, each computes 110, and writes `SET total=110`. Why can the final value be 110?**

Because both updates use the same stale literal computed in Java; one update overwrites the result the other request wrote. This is a lost update.

**2. How does switching to `SET total=total+10` help?**

The addition runs inside the statement at the DB, based on the row value updated by the database. Under PostgreSQL `READ COMMITTED`, two successful increments on one row bring the total from 100 to 120.

**3. A request checks `stock >= 5` via SELECT and then runs `UPDATE stock=stock-5`. Is it safe?**

Not yet. Another writer can reduce stock after SELECT and before UPDATE. Put `stock>=5` into the UPDATE's `WHERE` clause and check the row count.

**4. Why is `UPDATE 0` not necessarily a SQL error?**

Because zero rows matching a predicate is a valid UPDATE outcome. In guarded reservations, it indicates a business condition failure, not a statement syntax error.

**5. If both a source account and a destination account must change, is one guarded UPDATE enough?**

No. You need a transaction wrapping the related steps under the same manager/resource, row-count checks on each operation, rollback on failure, and idempotency protection for the transfer request.

**6. How should you handle a version check returning 0 rows?**

Treat it as a conflict/not found per contract; load fresh data and recompute, or return an error. Never silently overwrite with stale Java values.

**7. Should `REQUIRES_NEW` be used just to "be sure" each update is atomic?**

No. It creates an independent physical transaction, changing the atomicity of multi-step operations. A guarded UPDATE rarely needs its own `REQUIRES_NEW`; choose propagation per the required transaction boundary.

**8. Two requests with the same ID deduct 2 items twice; each command is atomic and stock suffices. Is deducting only once guaranteed?**

No. Atomicity is not idempotency. You must recognize the duplicate `request_id` and reject or return the prior result instead of re-processing.

**9. What is the advantage of `UPDATE ... RETURNING stock`?**

It returns the new stock from **the exact statement that performed the update**, avoiding a separate SELECT that could see subsequent concurrent changes. This is PostgreSQL syntax; use a suitable query API to read the result set.

## 21. Summary

When multiple transactions can write to the same data, **unprotected read–modify–write** produces lost updates and decisions made on stale state. `@Transactional` is a transaction management mechanism, **not** an automatic check that Java values just read are still fresh at write time.

Choose the tool to fit the problem:

- **Counter:** `UPDATE SET total=total+?`.
- **Conditional stock/quota/balance:** `UPDATE ... SET x=x-? WHERE x>=?`, validate input, and check row count.
- **Complex state from snapshot:** optimistic version/CAS or `SELECT FOR UPDATE` in an appropriate transaction.
- **Multiple tables / broad invariants:** transaction boundaries, constraints/locking/serializable, and controlled retries.
- **Potentially retried requests:** idempotency keys/ledgers, not just atomic SQL.

The key lesson is not "write less SQL," but **combining mutable conditions and writes into one database-coordinated operation**, then turning the updated row count/exception into an explicit business decision. Verify with two real transactions and deterministic schedules rather than trusting single-threaded tests as sufficient.

## Official References

- PostgreSQL — Transaction Isolation, `READ COMMITTED`, and `UPDATE` waiting/rechecking `WHERE`: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — `UPDATE`, row counts, and matching conditions: https://www.postgresql.org/docs/current/sql-update.html
- PostgreSQL — `RETURNING` for `UPDATE`: https://www.postgresql.org/docs/current/dml-returning.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Framework — Declarative Transaction Management and `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework API — `JdbcTemplate`, update returns update count: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Data JPA — Query Methods and modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA — Locking: https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
