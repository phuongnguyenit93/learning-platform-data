# NOT_SUPPORTED and Execution While the Outer Transaction Is Suspended in Spring

## 1. The problem: wanting to temporarily run *outside* the current transaction

A Spring application has a business processing method running inside transaction T1. While processing, it calls another function: querying diagnostic information, performing a non-transactional operation, or recording an independent event via JDBC. If you want the called function **not to participate in transaction T1**, you can use:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void doNonTransactionalWork() {
    // Runs without participating in the current physical transaction.
}
```

This is a **signature illustration snippet**, not a standalone Java program.

When the call passes through a **Spring transaction proxy**, the `Propagation.NOT_SUPPORTED` policy means:

> **Does not support running within the current transaction. If a compatible transaction currently exists, Spring suspends it, executes the method within a scope without that physical transaction, and then resumes the outer transaction after the method finishes.**

The crucial distinction is that `NOT_SUPPORTED` **does not create a new transaction**. It is fundamentally different from `REQUIRES_NEW`, which requests opening an independent transaction.

Consider an outer method that writes business data in T1, calls an inner method using `NOT_SUPPORTED` to INSERT into another table via JDBC, and then throws an error:

```text
CheckoutService.checkout()             @Transactional(REQUIRED)
    |
    | T1: INSERT business_record(id=1), uncommitted
    |
    +--> IndependentService.record()    @Transactional(NOT_SUPPORTED)
    |        |
    |        | Spring suspends T1
    |        | No actual T1 transaction here
    |        | JdbcTemplate INSERT independent_record(id=100)
    |        | New connection is auto-commit: INSERT commits individually
    |        | Spring resumes T1
    |        v
    |
    | throw IllegalStateException
    v
ROLLBACK T1

Result after the call:
  business_record       = 0 rows
  independent_record    = 1 row
```

This is **an illustrative scenario with JDBC auto-commit**. It does **not** mean `NOT_SUPPORTED` automatically commits everything the method does: because there is no enclosing Spring transaction, each DB operation may commit on its own, or fail, depending on the data access technology and connection configuration. Section 6 provides a runnable Java 17+ program to prove this result.

### Learning objectives

After this article you will be able to:

1. Explain accurately the meaning of `NOT_SUPPORTED` with and without an outer transaction.
2. Describe the sequence **suspend → run non-transactionally → resume**.
3. Distinguish `NOT_SUPPORTED` from `SUPPORTS`, `NEVER`, `REQUIRED`, and `REQUIRES_NEW`.
4. Understand why a JDBC INSERT inside a `NOT_SUPPORTED` block can **survive even when the outer transaction rolls back**.
5. Understand why `NOT_SUPPORTED` cannot be called an "independent transaction", and why it should not be used to protect multiple write steps that must be atomic.
6. Avoid mistakes with self-invocation, accessing uncommitted outer data, connection/lock contention, wrong transaction managers, and exception handling.
7. Test using **actual database state after the call**, not just by reading the annotation.

## 2. Exact definition of Propagation.NOT_SUPPORTED

In Spring, `org.springframework.transaction.annotation.Propagation.NOT_SUPPORTED` has the semantics **execute non-transactionally; suspend the current transaction if one exists**.

Two situations must be distinguished:

| State when Spring intercepts the call | Behavior of `NOT_SUPPORTED` | After the method completes |
| --- | --- | --- |
| Active current transaction T1 managed by the corresponding manager | Suspends T1's context; runs the body **without participating in T1** | Resumes T1 so the caller can continue |
| No compatible current transaction exists | Runs the body **without creating a new physical transaction** | Returns to caller, with no T1 to resume |

Full syntax:

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void readOrPerformIndependentStep() {
    // ...
}
```

This is a method-level snippet without an enclosing class. Unlike default `@Transactional`, here you **must explicitly specify NOT_SUPPORTED** because the default propagation is `REQUIRED`.

A common misconception is: "Having `@Transactional` means the method definitely runs inside a transaction." That is **false** when propagation is `NOT_SUPPORTED`. Here, the annotation is **an instruction not to use the existing transaction**.

### Conditions for the mechanism to work

- The bean is Spring-managed and the call actually passes through a transaction-aware proxy/advice.
- There is a compatible transaction manager and Spring resolves the `NOT_SUPPORTED` policy.
- If suspending an outer transaction is needed, the transaction manager must support suspension. Not every transaction manager or infrastructure type supports suspension in every configuration.
- When using imperative JDBC/JPA, you must consider **the current thread context and actual resources**. A transaction on another thread is not automatically the current transaction of this method.
- When there are multiple managers/datasources, `NOT_SUPPORTED` does not automatically suspend all transactions belonging to every manager. You must clearly identify **which manager and resource** are being coordinated.

## 3. The "suspend – execute – resume" sequence

Suppose `OuterService` and `IndependentService` are two Spring beans, both using the same JDBC transaction manager, and the initial caller has not opened a transaction:

1. The caller invokes `outerService.execute()` through the Spring proxy.
2. `OuterService.execute()` uses `@Transactional(REQUIRED)`. Since no transaction exists, the manager creates **T1**.
3. Outer runs SQL via `JdbcTemplate`; the SQL participates in T1 and is not yet committed.
4. Outer calls `independentService.doWork()` **through the second Spring proxy**.
5. The interceptor reads the `NOT_SUPPORTED` policy. The manager **suspends** transaction T1 and its associated resources/context.
6. `doWork()` executes **without an active physical transaction T1**.
7. When inner finishes or throws an error, Spring cleans up the non-transactional context and **resumes T1**.
8. Outer continues inside T1. If outer commits, changes in T1 commit; if outer rolls back, changes in T1 roll back.
9. Side effects that occurred **outside T1** are not automatically undone by an outer rollback.

### Sequence diagram

```mermaid
sequenceDiagram
    participant C as Caller
    participant OP as Outer proxy
    participant M as TransactionManager
    participant O as OuterService
    participant IP as Inner proxy
    participant I as IndependentService
    participant DB as Database

    C->>OP: checkout()
    OP->>M: REQUIRED; no transaction yet
    M->>DB: Begin T1
    OP->>O: Execute outer
    O->>DB: INSERT business_record in T1
    O->>IP: record() from another Spring bean
    IP->>M: NOT_SUPPORTED
    M->>M: Suspend T1 / unbind resource context
    IP->>I: Execute inner without T1
    I->>DB: JDBC INSERT with auto-commit (example)
    DB-->>I: Statement committed individually
    I-->>IP: Return
    IP->>M: End non-transactional scope
    M->>M: Resume T1
    IP-->>O: Return
    O--xOP: IllegalStateException
    OP->>M: Rollback T1
    M->>DB: ROLLBACK changes belonging to T1
    OP--xC: Exception
```

The diagram illustrates **JDBC with auto-commit in a non-transactional block**. With JPA, R2DBC, other drivers, or different non-transactional configurations, do not extrapolate identical detailed SQL behavior.

### "Suspend" is not "rollback", "commit", or "close transaction"

When Spring suspends T1:

- T1 is **not yet committed**.
- T1 is **not yet rolled back**.
- T1's uncommitted changes are still typically invisible from other connections at standard isolation levels.
- The connection or resource held by T1 **may still be retained** for resuming later, and locks acquired by T1 typically remain held until T1 ends.
- T1 resumes after inner finishes with its own data/locks, depending on transaction validity.

Do not misunderstand "suspend" as "releasing all connections and locks to do other work". Those held resources are why `NOT_SUPPORTED` should not be overused for long-running tasks while an outer transaction remains open.

## 4. Non-transactional is not the same as a new transaction

This is the central distinction of the topic.

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void methodA() {
    // Does not join the outer transaction,
    // and does not create a new physical transaction.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void methodB() {
    // Requests opening a new, separate physical transaction.
}
```

The two methods above are **not equivalent**, even though in a simple demo a written row may survive an outer rollback in both cases.

| Characteristic | `NOT_SUPPORTED` | `REQUIRES_NEW` |
| --- | --- | --- |
| When caller is in T1 | Suspends T1 | Suspends T1 |
| Does inner have a new actual physical transaction? | **No** | **Yes**, when created successfully |
| Two SQL writes using JDBC auto-commit | May commit **each statement** individually | Usually belong together in T2, can commit/roll back as one unit |
| Inner throws RuntimeException | No physical T2 to roll back | T2 typically rolls back per rollback rules |
| Outer T1 rolls back later | Does not undo side effects already committed outside T1 | Does not undo T2 changes **already committed** |
| Suitable for a sequence of DB writes that must be atomic | **No** | Possible, if business logic requires an independent transaction |
| Additional resources | JDBC outside transaction often needs another connection if T1 still holds one | T2 usually needs a new connection |

**Warning example:** Inside `NOT_SUPPORTED`, a method executes:

```java
jdbc.update("INSERT INTO first_table(id) VALUES (?)", 1L);
jdbc.update("INSERT INTO second_table(id) VALUES (?)", 2L);
```

Without an enclosing transaction and with a JDBC auto-commit connection, the first statement can **commit** before the second statement fails. There is no shared Spring transaction rollback to cancel the first statement. If two operations must succeed together or fail together, **do not use NOT_SUPPORTED** to protect them.

### JDBC auto-commit and JPA differ

With `JdbcTemplate` and a `DataSource` configured with default auto-commit in many applications, a statement outside a transaction is typically **committed by the DB immediately after successful execution**. Each statement may form a brief database transaction on the DB side, but **not a physical transaction opened by Spring to span the whole method**.

With JPA/Hibernate, write operations such as `EntityManager.persist/flush` outside a transaction may be disallowed or throw `TransactionRequiredException`, depending on the API and provider. Therefore, do not claim "NOT_SUPPORTED automatically commits each persist()" as a rule for every technology.

As for calling an HTTP API, sending email, or writing files, those are inherently not side effects that a JDBC transaction manager can roll back. `NOT_SUPPORTED` provides no atomicity guarantee for such side effects.

## 5. Observing "is there a transaction?" properly

Spring provides the API:

```java
TransactionSynchronizationManager.isActualTransactionActive()
```

In the imperative JDBC model of this hands-on exercise, outside T1 it returns `false`, inside outer REQUIRED it returns `true`, and inside the NOT_SUPPORTED method after T1 is suspended it returns `false`.

Visualization:

```text
Before outer:           actualTransactionActive = false
Inside outer REQUIRED:  actualTransactionActive = true
Inside inner NOT_SUPPORTED:
                        actualTransactionActive = false
After inner, in outer:  actualTransactionActive = true
After outer finishes:   actualTransactionActive = false
```

**Do not equate this** with `TransactionSynchronizationManager.isSynchronizationActive()`. Spring has transaction synchronization, scope, and thread-bound resource mechanisms; having a synchronization context is not proof that an **actual physical transaction** is active. Use `isActualTransactionActive()` for the observation goal of this example, and combine it with actual SQL outcomes.

Furthermore, `TransactionAspectSupport.currentTransactionStatus()` should not be assumed to mean "a status object exists only when there is a physical transaction". In transaction advice infrastructure, a `NOT_SUPPORTED` call may have a transaction status for scope management while **owning no actual physical transaction**. Do not take the existence of a status object as proof of physical commit/rollback.

## 6. Runnable Java 17+ example: inner runs outside transaction, outer rolls back

The example uses **Spring Boot, Spring JDBC, in-memory H2, and Java 17+**. Two service beans and two separate tables demonstrate `NOT_SUPPORTED` semantics without row locks on the same row skewing the experiment.

The program has **two scenarios**:

- **Scenario A:** outer INSERTs business record, inner NOT_SUPPORTED INSERTs independent record and returns; outer throws an error, rolling back T1. The business table is empty, while the independent record remains due to auto-commit.
- **Scenario B:** outer INSERTs business record, inner NOT_SUPPORTED INSERTs independent record and throws an error; outer **catches the error inside the transactional method** and finishes normally. The inner record has already auto-committed; outer commits the business record. This proves an exception from inner **does not automatically force T1 to roll back if outer handles it and T1 was not marked rollback-only for another reason**.

### 6.1. Project setup

Create a Maven project from Spring Initializr:

- Java **17** or newer.
- Spring Boot compatible with the chosen Java version.
- Dependencies: **Spring JDBC** (`spring-boot-starter-jdbc`) and **H2 Database**.
- Root package: `com.example.notsupported`.

Keep the Initializr-generated `pom.xml`; the dependencies section should contain:

```xml
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
```

This is only the **dependencies snippet**, not the full `pom.xml`. Spring Web is not needed: the application runs verification logic via `CommandLineRunner`.

File layout:

```text
src/main/
  java/com/example/notsupported/
    NotSupportedApplication.java
    CheckoutService.java
    IndependentService.java
  resources/
    schema.sql
    application.properties
```

### 6.2. Creating the database schema

File `src/main/resources/schema.sql`:

```sql
CREATE TABLE business_record (
    id BIGINT PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);

CREATE TABLE independent_record (
    id BIGINT PRIMARY KEY,
    message VARCHAR(100) NOT NULL
);
```

The two tables have **no foreign key** linking them. This is a decision **for the learning environment**: outer may hold a transaction and row lock; inner on another connection should not need to read or lock outer's uncommitted row.

In a real system, never drop foreign key constraints just to let a NOT_SUPPORTED method run. If the inner record truly must reference an **already committed** outer record, redesign the timing of the write.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:not_supported_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.datasource.hikari.auto-commit=true
```

When using Spring Boot with embedded H2, default SQL initialization typically executes `schema.sql` at startup. `auto-commit=true` is set explicitly for **connections borrowed from the pool outside a transaction** to keep the experiment transparent. When Spring opens T1, the transaction manager can change auto-commit on that connection as needed and restore it upon completion.

A maximum pool size of 4 connections is sufficient for a **single-threaded demo**, where outer still holds one connection and inner needs another. This is not a production pool sizing recommendation.

### 6.3. Inner service: NOT_SUPPORTED and JDBC auto-commit

File `src/main/java/com/example/notsupported/IndependentService.java`:

```java
package com.example.notsupported;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class IndependentService {

    private final JdbcTemplate jdbc;

    public IndependentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void record(long id, boolean fail) {
        boolean active =
                TransactionSynchronizationManager
                        .isActualTransactionActive();

        System.out.println("inner: actualTransactionActive=" + active);

        jdbc.update("""
            INSERT INTO independent_record (id, message)
            VALUES (?, ?)
            """, id, "observed");

        if (fail) {
            throw new IllegalStateException("inner failed");
        }
    }
}
```

**Explanation:**

1. `IndependentService` is an independent Spring bean; when injected and called by `CheckoutService`, its transaction advice can apply.
2. `@Transactional(propagation = NOT_SUPPORTED)` instructs **not to participate in the current physical transaction**.
3. When outer is inside T1, Spring suspends T1; inner's `isActualTransactionActive()` prints `false`.
4. `JdbcTemplate` obtains an appropriate JDBC connection. In this experimental auto-commit configuration, the INSERT into `independent_record` **commits individually** when the SQL succeeds.
5. If `fail=true`, the method throws `IllegalStateException` **after the INSERT has already succeeded**. There is no physical Spring transaction for inner to roll back the auto-committed operation.
6. The error can propagate to outer; outer continues, commits, or rolls back depending on its error handling and T1's state.

Important note: if you switch from `JdbcTemplate` to an access technology that requires a mandatory transaction for writes, this experiment must be redesigned. `NOT_SUPPORTED` does not force such a technology into auto-commit mode.

### 6.4. Outer service: transaction T1 is still restored

File `src/main/java/com/example/notsupported/CheckoutService.java`:

```java
package com.example.notsupported;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class CheckoutService {

    private final JdbcTemplate jdbc;
    private final IndependentService independentService;

    public CheckoutService(
            JdbcTemplate jdbc,
            IndependentService independentService) {
        this.jdbc = jdbc;
        this.independentService = independentService;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void rollbackAfterIndependentWrite() {
        System.out.println(
            "outer: actualTransactionActive=" +
            TransactionSynchronizationManager
                .isActualTransactionActive());

        jdbc.update("""
            INSERT INTO business_record (id, description)
            VALUES (?, ?)
            """, 1L, "pending checkout");

        independentService.record(100L, false);

        System.out.println(
            "outer resumed: actualTransactionActive=" +
            TransactionSynchronizationManager
                .isActualTransactionActive());

        throw new IllegalStateException("outer failed");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void handleInnerFailure() {
        jdbc.update("""
            INSERT INTO business_record (id, description)
            VALUES (?, ?)
            """, 2L, "accepted checkout");

        try {
            independentService.record(101L, true);
        } catch (IllegalStateException ex) {
            System.out.println(
                "outer handled: " + ex.getMessage());
        }

        // Do not rethrow: T1 can commit.
    }
}
```

Key observations:

- Both outer methods have `REQUIRED` and are called from a caller without a transaction, thus creating a separate physical transaction T1 for **each individual call**.
- `independentService.record(...)` is a call **through another bean**, not self-invocation. This is a prerequisite for the NOT_SUPPORTED policy to be enforced.
- In `rollbackAfterIndependentWrite()`, the business SQL joins T1 and has not committed; the inner INSERT is **outside T1** and auto-commits separately. Afterward, T1 is resumed and then rolled back due to the outer error.
- In `handleInnerFailure()`, outer **catches the inner exception**. The NOT_SUPPORTED block has no physical transaction of its own to mark T1 rollback-only. If T1 remains valid, returning normally from outer commits it.

Do not conclude that outer **always** commits just because it caught an exception. SQL inside T1 could fail on its own, or T1 could already have been marked rollback-only. The situation here is controlled: only a deliberate Java error is thrown after the inner JDBC INSERT has already auto-committed.

### 6.5. Entry point and database proof

File `src/main/java/com/example/notsupported/NotSupportedApplication.java`:

```java
package com.example.notsupported;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableTransactionManagement
public class NotSupportedApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotSupportedApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            CheckoutService checkoutService,
            JdbcTemplate jdbc) {
        return args -> {
            System.out.println(
                "caller: actualTransactionActive=" +
                TransactionSynchronizationManager
                    .isActualTransactionActive());

            try {
                checkoutService.rollbackAfterIndependentWrite();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
            printCounts("after outer rollback", jdbc);

            checkoutService.handleInnerFailure();
            printCounts("after handled inner error", jdbc);

            System.out.println(
                "caller ended: actualTransactionActive=" +
                TransactionSynchronizationManager
                    .isActualTransactionActive());
        };
    }

    private static void printCounts(String title, JdbcTemplate jdbc) {
        Integer business = jdbc.queryForObject(
            "SELECT COUNT(*) FROM business_record",
            Integer.class);
        Integer independent = jdbc.queryForObject(
            "SELECT COUNT(*) FROM independent_record",
            Integer.class);

        System.out.printf(
            "%s: business=%d, independent=%d%n",
            title, business, independent);
    }
}
```

The program uses Java 17 text blocks and Spring Boot dependency injection. Inside `CommandLineRunner`, there is no enclosing transaction annotation, so the caller executes **outside T1**.

With the demo configuration, Spring Boot typically auto-configures a transaction manager for a single JDBC datasource. `@EnableTransactionManagement` is stated explicitly to show enabling annotation-driven transaction support. Calls to each service method go through Spring bean proxies.

### 6.6. Running the program

In the directory containing `pom.xml`:

```bash
./mvnw spring-boot:run
```

In Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Aside from Maven and Spring Boot logs, the lines printed by **the program itself** will be:

```text
caller: actualTransactionActive=false
outer: actualTransactionActive=true
inner: actualTransactionActive=false
outer resumed: actualTransactionActive=true
caller caught: outer failed
after outer rollback: business=0, independent=1
inner: actualTransactionActive=false
outer handled: inner failed
after handled inner error: business=1, independent=2
caller ended: actualTransactionActive=false
```

### 6.7. Analyzing each result

**Scenario A — outer rolls back, inner non-transactional write remains**

1. `caller: ... false`: the caller has no physical transaction.
2. `outer: ... true`: `REQUIRED` initializes T1 before the outer body runs.
3. Outer INSERTs `business_record(id=1)` in T1; the record is **uncommitted**.
4. Calls bean `IndependentService.record(100, false)`. The proxy sees NOT_SUPPORTED and **suspends T1**.
5. `inner: ... false`: there is no actual transaction T1 inside inner.
6. JDBC INSERTs `independent_record(id=100)` on an auto-commit connection; the statement is committed outside T1.
7. Inner returns, and the transaction infrastructure **resumes T1**.
8. `outer resumed: ... true`: outer sees an actual transaction again.
9. Outer throws `IllegalStateException("outer failed")`, and outer's interceptor **rolls back T1**.
10. The caller catches the exception **after the proxy has rolled back T1**, then queries the database. Result: `business=0` while `independent=1`.

**Scenario B — inner errors, outer handles and commits**

1. The second outer call creates a new transaction T1' and INSERTs `business_record(id=2)`.
2. Inner `record(101, true)` runs outside T1', INSERTs `independent_record(id=101)` with auto-commit, and then throws `IllegalStateException("inner failed")`.
3. Spring cleans up inner's context, **resumes T1'**, and the exception propagates back into outer's `catch` block.
4. Outer **catches the exception**, does not rethrow, does not mark rollback-only, and returns normally.
5. The outer interceptor **commits T1'**. Now `business_record(id=2)` exists; independent also has id=101.
6. Total result: `business=1` and `independent=2`.

What matters most is not the depth of the call stack, but **which SQL runs in T1, which SQL runs outside T1, and who decides the outcome of T1**.

## 7. Why can a JDBC write outside a transaction survive a rollback?

In the demo, the inner method uses `JdbcTemplate` with a Hikari/JDBC connection in `autoCommit=true` mode. When an `INSERT` succeeds:

- The JDBC driver/database performs a commit for the statement under auto-commit.
- There is no physical Spring transaction T2 enclosing the entire inner method.
- When inner code subsequently throws an exception, Spring cannot roll back auto-committed statements just because the method uses NOT_SUPPORTED.
- When outer rolls back T1, the rollback applies only to T1's connection/transaction, **not to statements already committed on a connection outside T1**.

Do not phrase this as "NOT_SUPPORTED inserts into the DB without any transaction at the DB level". The database may execute each statement in very short transactions auto-committed per connection policy. What Spring guarantees here is **not participating in a Spring-managed physical transaction for this method**.

### If the inner method runs multiple SQL statements

Example:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void writeTwoRows() {
    jdbc.update("INSERT INTO independent_record (id, message) VALUES (?, ?)",
                201L, "first");
    jdbc.update("INSERT INTO independent_record (id, message) VALUES (?, ?)",
                201L, "duplicate key");
}
```

This is an illustrative method snippet assuming the primary key from the schema above.

- The first statement INSERTs id=201 successfully and **can auto-commit immediately**.
- The second statement violates the primary key and throws an error.
- There is no new Spring transaction wrapping both statements to roll back the first statement.
- The database may retain record id=201 even though the method ended with an exception.

With `@Transactional(REQUIRES_NEW)` on the same method and data source, both INSERTs can participate in T2; a runtime error rolls back T2 and no record id=201 remains. That is a major reason **not to use NOT_SUPPORTED in place of REQUIRES_NEW** when you want atomicity across multiple independent write steps.

## 8. Why is NOT_SUPPORTED different from SUPPORTS and NEVER?

These propagation types have similar-sounding names but choose different behaviors:

| Propagation | When outer transaction T1 exists | When no outer transaction exists |
| --- | --- | --- |
| `REQUIRED` | Joins T1 | Creates a new transaction |
| `SUPPORTS` | **Joins T1** | Runs without requiring an actual transaction |
| `NOT_SUPPORTED` | **Suspends T1, runs outside T1** | Runs without requiring an actual transaction |
| `NEVER` | **Throws an error** because it rejects transactions | Runs without requiring an actual transaction |
| `REQUIRES_NEW` | Suspends T1, **creates a new transaction T2** | Creates a new transaction |
| `MANDATORY` | Joins T1 | Throws an error due to missing transaction |

The trickiest points:

- `SUPPORTS` means **join if present**, so the method can execute SQL inside T1 if the caller has a transaction.
- `NOT_SUPPORTED` means **avoid if present**, so the method must run outside T1 even if the caller is in a transaction.
- `NEVER` means **reject if present**, so it is used when an outer transaction is considered a technical contract violation.
- `REQUIRES_NEW` means **always need a new T2**, not "no transaction".

If you want to **read data inside the outer transaction** to share the same snapshot/consistency or see the caller's uncommitted changes, do not choose NOT_SUPPORTED. If the method only performs an operation not needing a transaction, yet should still participate when the caller opened one, consider SUPPORTS while keeping synchronization in mind.

## 9. Accessing outer's uncommitted data: a major limitation

For example, T1 is running:

```sql
INSERT INTO purchase_order (id, status)
VALUES (77, 'PENDING');
```

Outer has not committed yet and immediately calls inner NOT_SUPPORTED to query:

```sql
SELECT status FROM purchase_order WHERE id = 77;
```

Under common isolation levels such as READ COMMITTED, inner running on a different connection/transaction typically **does not see T1's uncommitted row**. Therefore:

- Inner may get `0 rows` or see the state **before T1's update**.
- If inner tries to insert a row with a **foreign key** referencing the new uncommitted data, the DB may wait on a lock, reject it, or time out.
- If inner needs to update the same row currently locked by T1, it may block until T1 finishes; yet T1 is suspended **waiting for inner to return**.
- Do not "work around" this by disabling foreign keys or reading dirty data in production without analyzing invariants.

**Important:** `NOT_SUPPORTED` does not automatically let you see the caller's "latest" data. It usually does the opposite: **detaches from the caller's transaction context**. If the goal is to inspect data just written by T1, do it inside the same T1 or adjust when the read happens.

### Loss of consistency across multiple reads

When inner runs without an enclosing Spring transaction spanning the entire method, two consecutive SELECTs can observe two different committed states if another transaction commits in between, depending on DB/connection and isolation. Do not rely on NOT_SUPPORTED to provide a consistent snapshot across multiple queries.

For stronger snapshot requirements, you need a read-only transaction with appropriate isolation, while remembering that `readOnly=true` alone does not guarantee snapshot isolation or strictly forbid writes.

## 10. Lock and connection pool risks when suspending

Suspending a transaction does not necessarily release resources:

```text
Outer T1:
    holds connection C1
    holds row lock on inventory(id=10)
    |
    +--> inner NOT_SUPPORTED:
            borrows connection C2 (example)
            UPDATE inventory(id=10)
            waits for T1's lock
    |
    Outer waits for inner to return, cannot finish T1.
```

This is a self-blocking situation:

1. T1 holds the lock.
2. Inner needs that lock through a connection not belonging to T1.
3. Outer has yielded the call stack to inner and cannot commit/roll back T1 before inner finishes.
4. Inner waits for the lock to be released, which can lead to a timeout or deadlock depending on the DB.

### Why might an extra connection be needed?

Even though inner **does not create a new transaction**, inner's SQL may still need **a different JDBC connection** because T1's connection is being kept aside to resume later. If the connection pool is too small, inner may have to wait for a free connection.

Concurrent load example:

```text
N concurrent requests, each holding one connection for T1.
Each request calls inner NOT_SUPPORTED that accesses the DB and needs another connection.
If the pool maximum is only N connections, no request can acquire a new connection
for inner; pool starvation and timeouts can occur.
```

The exact number of connections depends on how Spring manages the datasource/transaction manager and the driver. For production applications, measure concurrency, connection hold times, and nested call layers. Do not treat the `4` in the example as a sizing formula.

### Do not use NOT_SUPPORTED just to "avoid holding a transaction during network calls"

If outer T1 was already opened before calling NOT_SUPPORTED, T1 **still exists and typically still holds its connection/locks** while suspended. An inner method waiting 15 seconds on an external API makes outer hold resources even longer. It is better to restructure transaction boundaries: perform slow I/O before opening T1 or after T1 commits, when business logic allows.

## 11. Proxies: internal calls can stop NOT_SUPPORTED from running

Look at this code:

```java
@Service
class ReportService {

    @Transactional
    public void build() {
        jdbc.update("INSERT INTO business_record ...");
        readOutsideTransaction();
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void readOutsideTransaction() {
        // Intended not to use T1.
    }
}
```

This is **illustrative code**, with incomplete SQL and an undeclared `jdbc` field.

In standard Spring AOP **proxy mode**, calling `readOutsideTransaction()` on the same `ReportService` instance does not pass through that method's proxy. Consequences:

- The transaction interceptor **does not apply the NOT_SUPPORTED policy** to the internal call.
- JDBC accesses inside may **continue participating in T1**, completely contradicting the intent to "run outside the transaction".
- When outer rolls back, those changes may roll back together with T1.

This is why the example in Section 6 uses **two Spring bean classes**:

```text
CheckoutService (bean A)
       |
       +-- injected IndependentService (bean B, proxied)
                    |
                    +-- @Transactional(NOT_SUPPORTED)
```

If you want a method to genuinely have a NOT_SUPPORTED boundary, call it through a Spring-managed proxy. Also do not instantiate the bean manually with `new IndependentService(jdbc)` and expect the annotation to work.

### Visibility and `final`

Private methods cannot be advised by standard Spring proxies. With class-based proxies, `final` methods cannot be overridden to intercept. With JDK interface-based proxies, the method must be exposed through the interface. The safe pattern for this topic is a public, non-final service method called by another bean via injection.

## 12. Exceptions from inner: how do they affect the outer transaction?

**NOT_SUPPORTED does not have its own physical transaction to roll back.** However, an exception from inner is still a Java exception that can unwind up the call stack to outer.

Two cases:

### Case A — Outer does not catch the error

```java
@Transactional
public void outer() {
    writeBusiness();          // Belongs to T1.
    innerNotSupported.work();  // Outside T1; may have auto-committed side effects.
    // If work() throws a RuntimeException and it is not caught,
    // the exception escapes through the outer transaction interceptor.
}
```

This is an illustrative snippet. The inner transaction infrastructure **resumes T1 even when the inner call fails**, and then the exception continues propagating through the outer method. Outer's interceptor sees the `RuntimeException` and **rolls back T1 by default**.

Side effects already committed outside T1 **are not rolled back with it**.

### Case B — Outer catches the error and continues

```java
@Transactional
public void outer() {
    writeBusiness(); // Belongs to T1.
    try {
        innerNotSupported.work();
    } catch (IllegalStateException ex) {
        // Business logic allows continuing.
    }
}
```

If T1 has not been marked rollback-only for another reason and outer returns normally, T1 **can commit**. Inner NOT_SUPPORTED has no physical transaction T2 of its own to mark T1 rollback-only.

Do not apply this conclusion mechanically if an error arose from a SQL statement inside T1, or if another interceptor marked rollback-only. Also, checked exceptions under default rollback rules are handled differently when escaping outer; design explicitly if the business logic requires a rollback.

### Two independent failure modes

| Failure | Can outer roll back? | Are inner's commits outside T1 undone by outer? |
| --- | --- | --- |
| Inner throws unchecked exception, outer does not catch | Yes, typically rolls back T1 | **No** |
| Inner throws unchecked exception, outer catches and returns normally | T1 can commit | **No** |
| Outer itself throws RuntimeException after inner succeeds | Yes, rolls back T1 | **No** |
| Inner's second SQL fails after first SQL auto-committed | Depends on whether exception reaches outer and outer's rules | **Not automatically** |
| Database/pool fails to grant connection to inner | Inner may not have written anything; outer handles exception per design | Cannot assume side effects occurred |

Do not equate "exception" with "transaction rollback everywhere". You must determine **which physical transaction exists and which interceptor sees the exception**.

## 13. `readOnly`, `isolation`, and `timeout` attributes in NOT_SUPPORTED

Example:

```java
@Transactional(
    propagation = Propagation.NOT_SUPPORTED,
    readOnly = true,
    timeout = 10
)
public void readReport() {
    // ...
}
```

This is an illustrative annotation. Because NOT_SUPPORTED **does not create a new physical transaction**, do not expect `readOnly=true` to force the database to reject writes, or new timeout/isolation settings to be applied as when a real transaction is opened. Some infrastructure may still create a scope for synchronization and metadata, but that does not change the definition of **executing non-transactionally**.

If you need a read transaction with real snapshot semantics and timeout, consider `REQUIRED` or `REQUIRES_NEW` with appropriate `readOnly`/`isolation`/`timeout` according to business needs. If you just need ordinary reads and want to avoid T1, NOT_SUPPORTED can be an option, provided you understand its consistency limits.

## 14. Multiple transaction managers: what gets suspended?

Suppose the application has:

- `ordersTxManager` managing `ordersDataSource`.
- `analyticsTxManager` managing `analyticsDataSource`.

You write:

```java
@Transactional(
    transactionManager = "analyticsTxManager",
    propagation = Propagation.NOT_SUPPORTED
)
public void readAnalytics() {
    // Queries analyticsDataSource.
}
```

This policy is applied through **analyticsTxManager**. It does not automatically suspend every existing transaction on **ordersTxManager** or every data source in the JVM.

Therefore, when saying "the outer transaction is suspended", check:

1. Which manager does outer use?
2. Which manager does inner NOT_SUPPORTED select?
3. Does the transaction manager find a current transaction for **the resource it manages**?
4. Which datasource does the inner Repository/DAO/`JdbcTemplate` access?

**If the managers differ**, resource contexts and synchronization may interact depending on configuration; do not conclude that an annotation on manager B guarantees all effects of manager A are suspended. For an introductory setup, use the same manager and datasource as in the main example to observe the true nature of propagation.

### Suspension support depends on the manager

Spring documentation notes that actual suspension is not supported out of the box by every transaction manager. For example, JTA may require providing the server's native transaction manager to support suspend/resume. If the environment does not support it, requesting NOT_SUPPORTED with a current transaction may throw an exception.

Do not "fix" this by swallowing the exception and assuming the method will run non-transactionally. Verify the suspend/resume capability of the transaction manager in use.

## 15. When is NOT_SUPPORTED useful and when is it dangerous?

### Potentially reasonable cases

- **Independent secondary queries** where you intentionally do not want to participate in the outer transaction and do not need to read outer's uncommitted data.
- **Operations not needing a transaction**, within well-designed boundaries where atomically committing a sequence of SQL statements is not required.
- **Recording individual diagnostic/experimental logs** via JDBC, when business rules deliberately allow the record to persist if the main operation rolls back, and it is understood that multiple statements share no atomicity.

Even in these cases, you must still weigh locks, pool sizing, and latency while outer T1 is suspended.

### Cases to avoid

- Money transfers or multi-table updates that must **succeed together or fail together**.
- Publishing `OrderCreated` or `PaymentSucceeded` **before the outer transaction commits**; if outer rolls back, the emitted event becomes false.
- Code depending on uncommitted records, row locks, or uncommitted state of T1.
- Reports requiring a **consistent snapshot** across multiple SELECT statements.
- JPA code needing a transaction to flush/persist, moved to NOT_SUPPORTED merely to "make it run faster".
- Long-running blocks causing outer to hold onto transaction resources while waiting.

### Alternatives by goal

| Business goal | Usually better solution |
| --- | --- |
| Multiple DB operations must be atomic with outer | Keep in `REQUIRED` / same transaction |
| A group of DB operations needs its own transaction and its own atomicity | `REQUIRES_NEW`, after analyzing side effects |
| Run non-transactionally even if outer has a transaction | `NOT_SUPPORTED`, with clear trade-offs |
| Run non-transactionally and fail if caller has a transaction | `NEVER` |
| Event must exist only when outer commits | Outbox in the same transaction or after-commit workflow |
| Slow remote I/O | Move outside transaction boundaries if possible, not just suspend |
| Verify transaction presence | `TransactionSynchronizationManager.isActualTransactionActive()` and DB results |

**Choose propagation by business contract**, not out of a desire to "bypass" rollback errors.

## 16. Testing properly: read data after the outer transaction finishes

The best way to test the case in this article:

1. Create an empty test database with two independent tables.
2. Call the outer Spring bean from a caller **with no transaction**.
3. Outer REQUIRED INSERTs a row in T1.
4. Outer calls inner NOT_SUPPORTED through another Spring bean.
5. Inner observes `isActualTransactionActive() == false`, then performs a JDBC INSERT on an auto-commit connection.
6. Outer resumes T1 and throws a runtime exception.
7. Catch the exception in the caller **after the outer transaction interceptor finishes rolling back**.
8. Re-query the DB: outer's row is gone; inner's auto-committed row remains.
9. Repeat the scenario where inner throws an error and outer catches it and finishes; verify outer can commit if not rollback-only.

**A Spring Test pitfall:** if `@Transactional` is placed on the test method itself, the test framework may open a transaction wrapping the entire test and roll it back at the end. Then the "caller has no transaction" state and reading data after commit/rollback will no longer behave as described. Write integration tests for this scenario with calls outside a test transaction, or manage the test transaction explicitly.

Use H2 to learn the concepts, but if production runs PostgreSQL/MySQL, add integration tests with the same database engine (for example Testcontainers), because locking, auto-commit, isolation, and SQL error behavior can differ.

### Expected outcomes table

| Case | Outer T1 | Inner NOT_SUPPORTED | After the call |
| --- | --- | --- | --- |
| A | INSERT then rollback | One auto-committed JDBC INSERT | Outer gone, inner remains |
| B | INSERT then commit | One auto-committed JDBC INSERT | Both remain |
| C | Catch inner error, then commit | Inner INSERT succeeds then throws | Both outer and inner can remain |
| D | Do not catch inner error; outer rolls back | Inner INSERT then throws | Outer gone, committed inner may remain |
| E | Outer holds a lock inner needs | Inner waits for lock | Possible timeout/deadlock |
| F | Inner called via self-invocation, advice bypassed | JDBC joins T1 | Outer rollback may undo both |
| G | Inner uses JPA write requiring transaction | No physical transaction | Possible `TransactionRequiredException` |

What needs verifying is not only `active=false`, but also **where actual changes were committed**.

### Supporting logs

You can enable logging in `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs can help trace suspend/resume and outer commit/rollback. Exact log messages vary by Spring version and transaction manager; do not depend on a specific log string. Reading the DB after the calls remains the primary evidence.

## 17. Common thinking mistakes

**Mistake 1 — NOT_SUPPORTED means committing the outer transaction before running inner.** No. Spring **suspends** T1, it does not commit T1. When inner finishes, T1 is resumed.

**Mistake 2 — Inner has `@Transactional(NOT_SUPPORTED)` so it still has its own transaction.** No. NOT_SUPPORTED actively avoids an actual transaction. If you need a separate transaction T2, see REQUIRES_NEW.

**Mistake 3 — NOT_SUPPORTED rolls back SQL statements when inner throws RuntimeException.** That cannot be assumed. With JDBC auto-commit, succeeded statements can commit individually, and there is no enclosing Spring physical transaction spanning the method.

**Mistake 4 — Because T1 is suspended, connections and row locks are released.** Not necessarily; they are usually still held for T1 to resume. Inner may run short on connections or wait on outer's locks.

**Mistake 5 — NOT_SUPPORTED will see what outer just INSERTed.** No, if outer has not committed and inner uses a different connection/transaction at normal isolation levels.

**Mistake 6 — If a NOT_SUPPORTED block throws an error, outer definitely rolls back.** Only if the exception ultimately causes outer to roll back or T1 is marked rollback-only. Outer can catch the error and continue, as in Scenario B.

**Mistake 7 — Putting `@Transactional` on a method in the same class is enough.** In proxy mode, self-invocation bypasses the called method's advice, so NOT_SUPPORTED is not applied at that boundary.

**Mistake 8 — Having `isSynchronizationActive() == true` means an actual transaction is definitely active.** No. Synchronization scope and actual physical transaction are not the same concept.

**Mistake 9 — NOT_SUPPORTED always makes every persistence library auto-commit.** No. Write behavior outside a transaction depends on JDBC auto-commit, JPA provider, resources, and APIs.

**Mistake 10 — NOT_SUPPORTED makes the application faster by skipping transactions.** There is no speed guarantee; suspend/resume, extra pool usage, locks, and lost atomicity can make the system more complex.

## 18. Self-check exercises

### Question 1 — Active state of outer and inner

An `OuterService.run()` method using `@Transactional(REQUIRED)` is called from a non-transactional controller. Inside, it calls `InnerService.work()` using `@Transactional(NOT_SUPPORTED)` via a proxy. With the same JDBC manager, what are the values of `isActualTransactionActive()` in sequence?

**Answer:** Inside outer it is `true`; inside inner it is `false`; after inner returns and outer resumes it is `true`. After outer completes, the caller again has no transaction.

### Question 2 — An INSERT outside a transaction

Outer INSERTs business id=1 in T1. Inner NOT_SUPPORTED uses an auto-commit JDBC connection to INSERT audit id=100. Then outer throws a runtime exception and T1 rolls back. What can remain?

**Answer:** Business id=1 is rolled back. Audit id=100 can still exist if the inner statement auto-committed successfully, because it did not participate in T1.

### Question 3 — Two INSERTs and the second statement fails

Inner NOT_SUPPORTED uses JDBC auto-commit to INSERT two rows. The first statement succeeds; the second violates a UNIQUE constraint. Can Spring use inner's rollback to revert the first statement?

**Answer:** There is no physical Spring transaction wrapping the whole inner method. The first statement may already have committed. If business logic requires atomicity between the two statements, an appropriate transaction must be used, such as REQUIRES_NEW for an independent scope.

### Question 4 — Comparing NOT_SUPPORTED and REQUIRES_NEW

Both can suspend T1. What is the essential difference?

**Answer:** REQUIRES_NEW requests opening **transaction T2**; NOT_SUPPORTED requests running **without an active current transaction**. REQUIRES_NEW can roll back multiple SQL statements in T2 as one unit; NOT_SUPPORTED creates no T2 to protect statements.

### Question 5 — Inner throws an error, outer catches it

Outer T1 INSERTs a row and calls inner NOT_SUPPORTED. Inner performs an independent INSERT and throws `IllegalStateException`. Outer catches it and returns normally. Must T1 roll back?

**Answer:** No, if T1 is not rollback-only and there is no other error. Outer can commit. The auto-committed inner record is not undone by an outer rollback anyway.

### Question 6 — Self-invocation

Outer calls `this.inner()`, where inner has `@Transactional(NOT_SUPPORTED)`. Why might an inner operation roll back together with outer?

**Answer:** In proxy mode, `this.inner()` bypasses transaction advice, so Spring does not suspend T1. Inner's JDBC calls may continue using T1's connection.

### Question 7 — Reading uncommitted data

Outer T1 INSERTs order 77 without committing yet, then calls NOT_SUPPORTED to SELECT order 77. Is inner guaranteed to see that record?

**Answer:** No. Inner typically uses a connection outside T1, so it does not see uncommitted changes at normal isolation levels.

### Question 8 — Connection pool

The pool has 8 connections, and 8 concurrent requests each hold 1 connection in T1 and then call NOT_SUPPORTED to run a JDBC query. What is the risk?

**Answer:** Inner may need another connection while all connections are held by T1, leading to pool starvation and timeouts. Exact behavior depends on implementation, but you must account for needing extra connections during suspension.

### Question 9 — Needing data that exists only when the order commits

The application writes an `OrderCreated` event inside inner NOT_SUPPORTED before outer commits. Outer fails. Is this design appropriate?

**Answer:** No, if the event is only valid after the order has committed. Store an outbox record in the **same T1** as the order or arrange appropriate after-commit handling, rather than letting the event auto-commit beforehand.

## 19. Checklist for applying in a real system

- [ ] Clearly verified that the **goal** is non-transactional execution, not creating a separate transaction.
- [ ] Accurately understood `Propagation.NOT_SUPPORTED`: suspend existing transaction, then resume.
- [ ] Service method is an entry point called through a Spring-managed proxy, not self-invocation.
- [ ] Transaction manager supports suspend/resume in the infrastructure being used.
- [ ] Identified which manager/resource holds T1; with multiple DataSources, do not assume every transaction is suspended.
- [ ] Non-transactional JDBC/JPA behavior has been verified (auto-commit or `TransactionRequiredException`).
- [ ] No multi-statement SQL atomicity requirement exists inside inner when using NOT_SUPPORTED.
- [ ] Inner does not depend on uncommitted T1 data and does not require locks held by T1.
- [ ] Connection pool/timeouts/concurrency are adequate for suspension while inner acquires another connection.
- [ ] Any independent side effect makes valid business sense if outer rolls back.
- [ ] Checked whether inner exceptions are caught or propagate to outer, and how they affect T1 rollback.
- [ ] Tested against a DB matching production, reading data after commit/rollback.
- [ ] Not using NOT_SUPPORTED as a substitute for outbox/after-commit when an event is only valid after outer commits.

## 20. Conclusion

**`Propagation.NOT_SUPPORTED` = do not run inside the current transaction; if a transaction currently exists, suspend it during method execution and then restore it.** It **does not create a new physical transaction** like `REQUIRES_NEW`.

When a JDBC connection runs with auto-commit in a non-transactional scope, succeeded statements can **commit independently**, so rolling back the outer transaction does not automatically revert them. This is both a property that can be useful for diagnostic data and a risk to business atomicity. Verify proxies, managers, connections, locks, exception flow, and database state to know what the program actually does.

### References

- Spring Framework — `Propagation.NOT_SUPPORTED` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework — `TransactionDefinition.PROPAGATION_NOT_SUPPORTED` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — Declarative Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Boot — SQL Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html
