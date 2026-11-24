# Verifying REQUIRES_NEW vs. REQUIRED with Real Data

## 1. Central Question

Two methods both write to the database and are both marked `@Transactional` by Spring, yet their **commit/rollback outcomes differ** depending on whether the inner method uses `Propagation.REQUIRED` or `Propagation.REQUIRES_NEW`. What makes them differ, and how can we prove it with **committed data**, rather than guessing from annotation names?

- **`REQUIRED`**: if outer already has a suitable physical transaction, inner **joins that transaction**. An error forcing inner to roll back can cause the entire shared transaction to roll back. Nor does inner succeeding commit independently ahead of outer.
- **`REQUIRES_NEW`**: inner always requests an **independent physical transaction**, suspending outer's existing transaction while inner runs. Inner can commit/roll back independently; inner's committed result **is not automatically undone** when outer later rolls back.

Keep this side-by-side comparison in mind:

```text
A. REQUIRED
Outer transaction T1: [INSERT outer] -> Inner REQUIRED [INSERT inner] -> Outer error
                                  \____________ shared T1 ____________/
T1 rolls back -> NEITHER outer nor inner record remains.

B. REQUIRES_NEW
Outer transaction T2: [INSERT outer] -- suspend --+             +-- resume -- Outer error
                                                  |             |
Inner REQUIRES_NEW:                       T3 [INSERT inner] -> COMMIT T3
Outer T2 rolls back -> outer is gone, T3's inner record STILL REMAINS.
```

This lesson belongs to **REQUIRES_NEW** in Spring Framework — transaction management; its direct topic is **"Verifying this choice against REQUIRED with real data"**. The goal is not merely defining the two propagation modes, but building an experiment with input data, SQL statements, exceptions at different boundaries, expected output, and result explanations.

After this lesson, you will be able to:

1. Distinguish logical transaction scope from physical transaction, and understand `REQUIRES_NEW` suspend/resume semantics.
2. Predict DB outcomes when **outer rolls back after inner succeeds**, or **inner rolls back while outer catches the error**.
3. Build a **Java 17+, Spring Boot, Spring JDBC, H2** application and run all scenarios across multiple service beans so proxies are genuinely used.
4. Read the table of surviving rows after transactions complete and explain why `REQUIRED` and `REQUIRES_NEW` produce different results.
5. Know when to use an independent transaction, when it breaks business atomicity, and its connection pool and lock costs.
6. Test reliably in real systems without being misled by test `@Transactional`, self-invocation, or queries inside uncommitted transactions.

## 2. Two Transaction Concepts to Keep Separate

### 2.1. Logical Transaction Scope

Each time execution passes through transaction advice for a `@Transactional` method, Spring can establish a **logical scope**. That scope holds transaction attributes, rollback rules, and state used when the method returns or throws an exception.

When outer calls inner through the **Spring proxy of another bean**, there are typically two logical scopes: an outer scope for outer and an inner scope for inner. **The number of logical scopes does not determine the number of physical transactions.**

### 2.2. Physical Transaction

A physical transaction is the actual transaction coordinated by the DB/transaction manager over a connection, with concrete commit/rollback. In this JDBC demo, one `DataSourceTransactionManager` works with one H2 `DataSource`.

- With `REQUIRED`, two logical scopes typically map to **one physical transaction** on the same managed connection.
- With `REQUIRES_NEW`, inner opens a **new physical transaction**; Spring suspends outer's resource context and restores it after inner completes.
- An inner `REQUIRES_NEW` is not a savepoint of outer. Once inner commits, outer rolling back afterward **cannot undo that commit**.
- A new transaction is only truly independent for the matching manager/resources; emails, HTTP calls, Kafka, or other databases are not automatically covered by a local manager.

Diagram:

```text
REQUIRED
caller
  |
outer proxy -> BEGIN T_outer
  |  outer INSERT
  +--> inner proxy REQUIRED -> join T_outer
  |        inner INSERT / exception
  +<-- inner returns
  |  outer returns / exception
outer proxy -> COMMIT or ROLLBACK T_outer

REQUIRES_NEW
caller
  |
outer proxy -> BEGIN T_outer
  |  outer INSERT (uncommitted)
  +--> inner proxy REQUIRES_NEW
  |       suspend T_outer
  |       BEGIN T_inner on separate resource
  |       inner INSERT
  |       COMMIT or ROLLBACK T_inner
  |       resume T_outer
  +<-- inner returns / exception
  |  outer returns / exception
outer proxy -> COMMIT or ROLLBACK T_outer
```

**This is why you cannot look solely at whether a method has `@Transactional` to infer atomicity.** You must determine the propagation, whether the caller already has a transaction, whether the method is intercepted, which manager is used, and which scope handles errors.

## 3. Pre-Run Hypothesis Table

We place INSERTs on **distinct IDs** to avoid lock or unique-constraint conflicts on the same record. Scenarios are named A through F:

| Scenario | Inner propagation | What happens? | Final outer row | Final inner row |
| --- | --- | --- | --- | --- |
| **A** | `REQUIRED` | Inner INSERT succeeds; outer throws runtime exception | 0 | 0 |
| **B** | `REQUIRES_NEW` | Inner INSERT, commits; outer throws runtime exception | 0 | **1** |
| **C** | `REQUIRED` | Inner INSERT then throws runtime exception; outer **catches and returns** | 0 | 0 |
| **D** | `REQUIRES_NEW` | Inner INSERT then throws runtime exception; outer **catches and returns** | **1** | 0 |
| **E** | `REQUIRES_NEW` | Both inner and outer succeed | **1** | **1** |
| **F** | `REQUIRED` and `REQUIRES_NEW` called directly without outer | Each method opens its own transaction when none exists | Not applicable | 1 per method |

**The single most important reason to verify C and D:** a runtime exception from an inner `REQUIRED` can mark the **shared transaction rollback-only**, even if outer catches it and returns. With `REQUIRES_NEW`, the exception rolls back the **separate inner transaction**; if outer catches it and does not fail on its own, outer can still commit.

The outcomes above assume default Spring transaction manager behavior: rollback on `RuntimeException` and `Error`; `REQUIRED` joining the same transaction; `REQUIRES_NEW` creating a separate transaction; no non-DB side effects; and no other resource errors. The demo proves each row with SQL queries after the transactional methods finish.

## 4. Why Can "Outer Rollback After Inner Commit" Happen?

With `REQUIRES_NEW`, the transaction manager must:

1. Detect that outer's transaction T is already active.
2. **Suspend** outer's state/resources T from the current thread context. T is not committed or rolled back just by being suspended.
3. Begin transaction T2 for inner; in JDBC, typically using a **different connection** from the same pool.
4. Run inner, committing or rolling back T2 according to inner's outcome.
5. Clean up T2's context and **resume** outer's T.
6. Let outer continue; only when outer finishes is its own T resolved.

Because T2 is an independent physical transaction, if T2 has committed and T later rolls back, T2's rows persist. **There is no mechanism to "merge" an independent transaction back into outer at outer commit time.**

By contrast, `REQUIRED` only opens an inner **logical scope** joining T. Inner returning normally performs no new physical commit; T can be rolled back in full by outer.

In tests, if you query a row while transaction T is still active, you may see uncommitted data written by T itself (*read your writes*). "Seeing it" does not prove the data was committed. We will query from the runner after the proxy returns to verify the **final DB state**.

## 5. Runnable Sample Project: Java 17, Spring Boot, JDBC, and H2

This project uses **Spring Boot 3.3.13**, Spring JDBC, and in-memory H2. Spring Boot manages the `DataSource`; we explicitly declare a `DataSourceTransactionManager` and enable `@Transactional` processing. To avoid manually instantiating objects outside the container, both outer service and inner service are injected Spring beans.

This is a complete Gradle project for the demo, requiring no HTTP server or external services. Versions are pinned to reproduce behavior reliably, not as a claim they are optimal for production at all times.

### 5.1. Directory Structure

```text
compare-propagation/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/example/propagation/
        │   ├── PropagationApplication.java
        │   ├── OuterService.java
        │   └── InnerService.java
        └── resources/
            ├── application.properties
            └── schema.sql
```

All Java classes belong to package `example.propagation`, within the application's component-scan scope.

**`settings.gradle`**

```groovy
rootProject.name = 'compare-propagation'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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

`spring-boot-starter-jdbc` supplies JDBC, `JdbcTemplate`, and Spring transaction support. `spring-boot-starter-aop` ensures the AOP infrastructure needed for proxies. H2 runs in memory, so every clean launch is an isolated experiment.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:propagation_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
spring.main.web-application-type=none
```

**Why `maximum-pool-size=5`?** Outer `REQUIRES_NEW` generally holds T_outer's connection while inner needs another connection to run T_inner. A pool with only 1 connection could make inner wait until timeout and prevent the demo from running as expected. Five connections suffice for a **single sequential runner demo**; in production, size according to real concurrency rather than treating 5 as a universal rule.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

Each case uses its own ID for verification via `SELECT COUNT(*)`. Avoid updating the same record in outer and inner so the demo does not accidentally turn into a row-lock contention test. H2 transactions let us observe commit/rollback differences, while pool sizing lets inner request another connection.

### 5.2. InnerService — Two Propagation Modes and Two Failure Modes

**`src/main/java/example/propagation/InnerService.java`**

```java
package example.propagation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredInsert(int id) {
        printStatus("inner REQUIRED");
        insert(id, "required-ok");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewInsert(int id) {
        printStatus("inner REQUIRES_NEW");
        insert(id, "new-ok");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredInsertAndFail(int id) {
        printStatus("inner REQUIRED_FAIL");
        insert(id, "required-fail");
        throw new IllegalStateException("inner-fail");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewInsertAndFail(int id) {
        printStatus("inner REQUIRES_NEW_FAIL");
        insert(id, "new-fail");
        throw new IllegalStateException("inner-fail");
    }

    private void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static void printStatus(String label) {
        boolean newTx = TransactionAspectSupport
            .currentTransactionStatus()
            .isNewTransaction();
        System.out.println(label + " newTx=" + newTx);
    }
}
```

Four public methods serve as transaction entry points; all are non-final and on a Spring bean. `printStatus` is invoked **inside** an invocation advised with transactions. In the demo:

- Inner `REQUIRED` called by outer when T_outer already exists: `isNewTransaction() == false`.
- Inner `REQUIRES_NEW` called by outer: `isNewTransaction() == true` because it opens its own physical transaction.
- When the runner calls `inner.requiredInsert(...)` directly with no outer transaction, even `REQUIRED` yields `isNewTransaction() == true`.

**Do not mistake `isNewTransaction()` for a DB transaction ID.** It reports whether Spring's logical-scope transaction status owns a new transaction. The decisive proof of independence is the data remaining when outer rolls back after inner committed.

Both `*AndFail` methods always INSERT first and then throw unchecked `IllegalStateException`. Spring's default rollback rule handles exceptions passing through the transaction interceptor. If the exception were thrown **before** the INSERT, a count of 0 would not prove rollback; placing INSERT first is intentional.

### 5.3. OuterService — Creating Four Behavioral Pairs to Compare

**`src/main/java/example/propagation/OuterService.java`**

```java
package example.propagation;

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

    // A: inner REQUIRED joins T_outer.
    // Outer fails after inner succeeds -> both roll back.
    @Transactional
    public void requiredThenOuterFails() {
        insert(11, "outer-A");
        inner.requiredInsert(12);
        throw new IllegalStateException("outer-fail");
    }

    // B: REQUIRES_NEW commits independently before outer fails.
    @Transactional
    public void requiresNewThenOuterFails() {
        insert(21, "outer-B");
        inner.requiresNewInsert(22);
        throw new IllegalStateException("outer-fail");
    }

    // C: inner REQUIRED fails -> shared transaction becomes rollback-only.
    // Outer catches the error and returns, yet outer commit still fails.
    @Transactional
    public void requiredFailureCaught() {
        insert(31, "outer-C");
        try {
            inner.requiredInsertAndFail(32);
        } catch (IllegalStateException ex) {
            System.out.println("C inner caught=" + ex.getMessage());
        }
        System.out.println("C outer finished body");
    }

    // D: inner REQUIRES_NEW fails; only the inner transaction rolls back.
    // Outer caught it and did not fail on its own -> outer transaction commits.
    @Transactional
    public void requiresNewFailureCaught() {
        insert(41, "outer-D");
        try {
            inner.requiresNewInsertAndFail(42);
        } catch (IllegalStateException ex) {
            System.out.println("D inner caught=" + ex.getMessage());
        }
    }

    // E: both outer and inner NEW succeed.
    @Transactional
    public void bothCommit() {
        insert(51, "outer-E");
        inner.requiresNewInsert(52);
    }

    private void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, label
        );
    }
}
```

**Explaining the structure so proxies work:**

- `OuterService` is called by the runner from another bean through a Spring AOP proxy; `@Transactional` defaults to `REQUIRED`, so each outer call starts a physical transaction when the runner has no active T.
- `inner` is an `InnerService` bean constructor-injected into outer. Calls to `inner.method()` pass through the **proxy of another bean**, so the transaction interceptor actually applies `REQUIRED` or `REQUIRES_NEW`.
- `insert` is a private helper running inside the transaction already opened by the public method; it needs no `@Transactional` of its own.
- Do not instantiate `new InnerService(jdbc)` or call `this.requiresNewInsert(...)` in the same bean and expect propagation to switch. Self-invocation in proxy mode bypasses advice on the inner method.
- All INSERTs use the same `JdbcTemplate`, meaning the same `DataSource` and transaction manager, yet the transaction connection differs whenever inner requests `REQUIRES_NEW`.

### 5.4. Application — Running and Reading Data After Transactions End

**`src/main/java/example/propagation/PropagationApplication.java`**

```java
package example.propagation;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class PropagationApplication {
    public static void main(String[] args) {
        SpringApplication.run(PropagationApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner verify(
            OuterService outer, InnerService inner, JdbcTemplate jdbc) {
        return args -> {
            // A — inner REQUIRED success, outer rollback.
            try {
                outer.requiredThenOuterFails();
            } catch (IllegalStateException ex) {
                System.out.println("A caught=" + ex.getMessage());
            }
            showCounts(jdbc, "A", 11, 12);

            // B — inner REQUIRES_NEW commits, outer rolls back.
            try {
                outer.requiresNewThenOuterFails();
            } catch (IllegalStateException ex) {
                System.out.println("B caught=" + ex.getMessage());
            }
            showCounts(jdbc, "B", 21, 22);

            // C — inner REQUIRED rolls back, outer catches exception.
            try {
                outer.requiredFailureCaught();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "C caught=" + ex.getClass().getSimpleName());
            }
            showCounts(jdbc, "C", 31, 32);

            // D — inner REQUIRES_NEW rolls back; outer commits.
            outer.requiresNewFailureCaught();
            showCounts(jdbc, "D", 41, 42);

            // E — both transaction scopes commit.
            outer.bothCommit();
            showCounts(jdbc, "E", 51, 52);

            // F — no outer transaction, both modes start a new one.
            inner.requiredInsert(61);
            inner.requiresNewInsert(62);
            showCounts(jdbc, "F", 61, 62);
        };
    }

    private static void showCounts(
            JdbcTemplate jdbc, String label, int outerId, int innerId) {
        int first = count(jdbc, outerId);
        int second = count(jdbc, innerId);
        System.out.println(
            label + " rows first=" + first + " second=" + second);
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id = ?",
            Integer.class, id
        );
        return result;
    }
}
```

`@SpringBootApplication` scans `OuterService` and `InnerService` in the same package. `@EnableTransactionManagement` enables annotation-driven proxy transactions; Spring Boot auto-configures this in many setups, yet declaring it explicitly clarifies the learning boundary. `transactionManager` is the bean used by transaction advice, coordinating the same `DataSource` as `JdbcTemplate`.

Most importantly: `CommandLineRunner` **is not marked `@Transactional`**. `showCounts` runs **after the outer/inner call has returned or thrown an exception through the proxy**, so the DB has already been instructed to commit or roll back. Never draw conclusions from query values while an outer transaction is still open.

### 5.5. How to Run

Requires JDK 17+, compatible Gradle 8.x, and network access on first run to fetch dependencies. In the `compare-propagation` directory:

```bash
gradle bootRun
```

If a compatible Gradle Wrapper is present, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Do not use `javac` with a plain JDK classpath because the program depends on Spring and H2; Gradle fetches dependencies, compiles, and runs the application.

Each launch starts a fresh in-memory H2 instance; if re-running inside the same JVM or changing configuration to persist the database, make sure to clear test tables/records to avoid primary-key collisions. In the demo, 12 distinct ID values prevent collisions across scenarios.

### 5.6. Expected Stdout, in Exact Order

Ignoring Gradle, Spring Boot, Hikari, and startup logs, the lines printed by `System.out.println` (on a fresh run with a clean DB) are:

```text
inner REQUIRED newTx=false
A caught=outer-fail
A rows first=0 second=0
inner REQUIRES_NEW newTx=true
B caught=outer-fail
B rows first=0 second=1
inner REQUIRED_FAIL newTx=false
C inner caught=inner-fail
C outer finished body
C caught=UnexpectedRollbackException
C rows first=0 second=0
inner REQUIRES_NEW_FAIL newTx=true
D inner caught=inner-fail
D rows first=1 second=0
inner REQUIRES_NEW newTx=true
E rows first=1 second=1
inner REQUIRED newTx=true
inner REQUIRES_NEW newTx=true
F rows first=1 second=1
```

This is the **expected output** derived from the code and standard `DataSourceTransactionManager` behavior, not copied from a single run log. When preconditions are met, the count lines serve as evidence of committed/rolled-back state. If results differ, check the diagnostics section: proxies, manager, resources, connection pool, runner transaction, or an uncleaned database.

## 6. Interpreting Each Verification Case with Real Data

### 6.1. A — REQUIRED Inner Succeeds, Outer Rolls Back: Both Lost

`outer.requiredThenOuterFails()`:

1. Outer opens T_A and INSERTs id 11.
2. Inner `REQUIRED` sees T_A already exists, **joins T_A**, prints `newTx=false`, and INSERTs id 12.
3. Inner returns, completing only its logical scope — id 12 is **not committed yet**.
4. Outer throws `IllegalStateException` out through its interceptor, and Spring rolls back T_A.
5. Runner catches the exception and queries id 11, 12 after rollback: **0 and 0**.

In practice, this is the desired outcome when "creating an order" and "updating inventory" must succeed together. Any step failing within the same unit of work cancels the entire transaction.

**What this proves:** `REQUIRED` does not isolate inner's result into an independent commit; it **depends on the outcome of outer's physical transaction**.

### 6.2. B — REQUIRES_NEW Inner Commits, Outer Rolls Back: Inner Data Persists

`outer.requiresNewThenOuterFails()`:

1. Outer opens T_B and INSERTs id 21, **uncommitted**.
2. Inner `REQUIRES_NEW` suspends T_B, acquires a new resource/connection, opens T_B2, and prints `newTx=true`.
3. Inner INSERTs id 22 in T_B2 and returns normally. Spring **commits T_B2**; id 22 is durable.
4. Outer resumes T_B and throws `IllegalStateException`. Spring rolls back T_B; id 21 vanishes.
5. Runner queries: **id 21 = 0, id 22 = 1**.

**What this proves:** outer rollback cannot "override" an already-committed inner transaction. This is the clearest verification of `REQUIRES_NEW`'s independent commit ability. It is not "REQUIRED that runs early"; it is a genuinely separate physical transaction.

An important business question: after an order fails, is it valid for the inner record to remain? For an independent audit log, perhaps **yes**. For deducting inventory on a failed order, many systems would treat that as a **consistency bug** without compensation.

### 6.3. C — REQUIRED Inner Fails, Outer Catches: Rollback-Only Breaks Outer Commit

`outer.requiredFailureCaught()`:

1. Outer opens T_C and INSERTs id 31.
2. Inner `REQUIRED` joins T_C, INSERTs id 32, and throws `IllegalStateException`.
3. The inner transaction interceptor catches the runtime exception and marks the shared transaction **rollback-only** by default.
4. Outer `catch` handles the exception and prints `C outer finished body`; outer's Java code finished normally.
5. Outer's transaction interceptor attempts to commit T_C, detects rollback-only, rolls back, and throws `UnexpectedRollbackException`.
6. Runner catches `UnexpectedRollbackException`; both id 31 and 32 are **0**.

**What this proves:** with `REQUIRED`, inner's rollback rule can affect outer's entire physical transaction. A `catch` in outer **does not clear the rollback-only flag**. Spring throws `UnexpectedRollbackException` so the caller does not mistakenly believe outer committed when it actually rolled back.

This is standard `AbstractPlatformTransactionManager` behavior for participating transactions. If an application changes manager flags, uses different exception rules, or fails to proxy inner, outcomes can differ; that is why tests must verify the real environment.

### 6.4. D — REQUIRES_NEW Inner Fails, Outer Catches: Outer Commits

`outer.requiresNewFailureCaught()`:

1. Outer opens T_D and INSERTs id 41.
2. Inner suspends T_D, opens an independent T_D2, and INSERTs id 42.
3. Inner throws `IllegalStateException`. The transaction interceptor rolls back T_D2; id 42 is gone.
4. Spring resumes T_D and rethrows the exception to outer. Outer catches it and returns normally.
5. T_D is not marked rollback-only merely because inner T_D2 rolled back; outer can commit id 41.
6. Runner queries: **id 41 = 1, id 42 = 0**.

**What this proves:** inner `REQUIRES_NEW` rolling back **does not automatically propagate** a rollback-only flag to outer's physical transaction. However, if outer **does not catch the exception**, the runtime exception escapes outer's interceptor, and **outer still rolls back under outer's own rollback rule**. `REQUIRES_NEW` does not immunize outer against unhandled exceptions propagating outward.

### 6.5. E — Both Succeed: Both Records Persist, Yet Not One Transaction

`outer.bothCommit()` INSERTs id 51, inner `REQUIRES_NEW` INSERTs/commits id 52, and outer then commits id 51. The **1/1** result looks identical to a successful `REQUIRED` unit of work.

Yet **identical final state does not prove identical atomicity**. Only by deliberately introducing failures at different boundaries (A–D) do we see the crucial difference: REQUIRES_NEW can leave **partial success** when one transaction fails.

### 6.6. F — No Outer Transaction: Both Create a New Transaction

The runner calls `inner.requiredInsert(61)` and `inner.requiresNewInsert(62)` directly when no outer transaction exists. Both print `newTx=true` and commit their rows; count **1/1**.

Thus, testing `REQUIRED` and `REQUIRES_NEW` only without an outer transaction can tempt you into concluding "they are the same". **The distinction only manifests when an existing transaction is active** and scopes/outcomes diverge.

## 7. Cross-Reference Matrix: Who Fails, Who Catches, What Remains in DB?

A short decision map:

| Outer | Inner | Inner propagation | Does outer catch inner exception? | Typical outcome |
| --- | --- | --- | --- | --- |
| Throws RuntimeException after inner succeeds | Success | REQUIRED | Irrelevant | Both outer and inner roll back |
| Throws RuntimeException after inner succeeds | Success | REQUIRES_NEW | Irrelevant | Inner already committed; outer rolls back |
| Returns normally | RuntimeException | REQUIRED | Yes | Shared transaction rollback-only; outer typically hits `UnexpectedRollbackException` |
| Returns normally | RuntimeException | REQUIRES_NEW | Yes | Inner rolls back, outer can commit |
| Returns normally | RuntimeException | REQUIRES_NEW | **No** | Exception escapes outer proxy, so outer can also roll back |
| Returns normally | Success | REQUIRED | Not applicable | One physical transaction commits together |
| Returns normally | Success | REQUIRES_NEW | Not applicable | Two physical transactions commit independently |
| No outer transaction | Success | Either mode | Not applicable | The mode creates its own physical transaction |

The subtlety in the row **inner REQUIRES_NEW fails while outer does not catch**: the two transactions are manager-independent, yet outer can still roll back via **Java exception propagation**. Physical transaction independence does not mean program control-flow independence.

## 8. Measuring DB Outcomes Properly: "Real Data", Not Just Active Flags

### 8.1. Why Is `isNewTransaction()` Not Enough?

`TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` indicates whether the current invocation owns a new transaction or joined an existing one. However, this flag:

- Is not a database-issued transaction ID.
- Does not prove the SQL committed.
- Does not confirm operations on other systems participated.
- Can be misleading if called outside a transaction-advised method or under another manager/transaction scope.

In this lesson, the flag serves to **explain the mechanism**, while actual results rest on `SELECT COUNT(*)` **after outer/inner finish**.

### 8.2. Querying While Outer Is Still Active Can Mislead You

An outer transaction usually sees rows it just wrote even before committing. If you query on the same connection inside outer, the count may be 1; a subsequent rollback makes the true result 0.

That is why the demo places `showCounts` in a non-transactional runner **after returning or catching an exception from the proxy**. Reading at that moment distinguishes committed data from rolled-back data in every scenario.

### 8.3. Distinguish SQL Errors, Business Exceptions, and Commit Exceptions

A JDBC exception mid-transaction typically triggers rollback because `DataAccessException` is unchecked. However, an exception occurring **after inner has committed** does not undo the inner transaction. When a commit ACK is lost and the outcome is uncertain, never infer from an exception alone that the DB definitely rolled back; query business state, use idempotency keys, and reconcile where critical.

### 8.4. Verifying Real Isolation Can Be Harder Than the Demo

H2 lets you open a new transaction on another connection, yet if the inner transaction tries to read an uncommitted record outer just INSERTed, it **usually cannot see** that change under common isolation levels. There is no magic snapshot bypassing transaction isolation. If inner updates the same row locked by outer, inner may block or time out because outer is suspended without releasing locks. That is why the demo **intentionally uses independent IDs**, so our measurement isolates propagation.

In production, database isolation, locking, constraints, and timeouts can introduce additional outcomes. When expanding tests, always state the isolation level and which resources are locked.

## 9. Situations Where REQUIRES_NEW Can Be the Wrong Choice

### 9.1. Deducting Inventory and Outer Later Fails

Order example:

```java
@Transactional
public void placeOrder() {
    orders.insertPending();
    inventory.reserveIndependently(); // @Transactional(REQUIRES_NEW)
    chargeCard();
    throw new IllegalStateException("checkout failed");
}
```

This is illustrative code lacking dependencies/implementation. If `reserveIndependently` commits inventory in inner T2, outer's DB transaction rollback does not revert inventory. Even if `chargeCard` is an external non-DB call, Spring's transaction does not automatically refund payments either.

If the business invariant requires inventory and order to succeed together in **one database**, having inner `REQUIRED` join outer's transaction is likely better. Across distributed systems, use workflows and compensation; do not use `REQUIRES_NEW` as a substitute for consistency guarantees.

### 9.2. Independent Audit Logging Can Be a Valid Use Case

Another case:

```java
@Transactional
public void createOrder() {
    try {
        persistOrder();
        // Business failure...
        throw new IllegalStateException("cannot create");
    } finally {
        auditService.recordAttempt();
    }
}
```

If `auditService.recordAttempt()` is proxy-intercepted with `REQUIRES_NEW`, it **can commit its event log separately** even when the order transaction rolls back. This can be the **intended design** when failed attempts must be recorded.

Still, the snippet is illustrative without an implementation; clarify ordering, audit error handling, external logging, connection pools, and constraints. If the audit method throws an exception, it can mask the primary exception; design logging and failure handling carefully.

Independent auditing does not automatically make Kafka/email delivery reliable. To emit events tied to DB commits, consider a transactional outbox; to persist failed attempts reliably, design and test the independent transaction or dedicated audit store separately.

### 9.3. Partial Commit Outcomes Are Not a Spring Bug

Some view "outer rolled back yet inner still has a record" as a transaction bug. In fact, that **is precisely `REQUIRES_NEW` semantics**: each scope has its own physical transaction and commits/rolls back on its own. If the business cannot tolerate partial success, the chosen propagation or transaction boundary is wrong.

When designing, ask: "If the final step fails, is it still valid for the inner step's changes to stay durable?" If **no**, `REQUIRES_NEW` is usually inappropriate for that step.

## 10. Connection Pools and Locks: Costs That May Stay Hidden in Demos

### 10.1. Outer Still Holds Resources While Suspended

In JDBC transactions, outer has usually acquired a connection and may hold locks. When inner `REQUIRES_NEW` begins, it needs an extra connection. If N threads each hold an outer connection and wait for an inner connection while the pool size is only N, none can obtain a new connection. The result can be **pool starvation** or a deadlock-like wait, followed by timeouts.

Spring recommends sizing the pool larger than the number of concurrent threads that can hold outer transactions, by at least one connection under appropriate assumptions; in practice, plan capacity for nesting depth and overall workload.

The demo uses:

```properties
spring.datasource.hikari.maximum-pool-size=5
```

Size 5 merely gives **a single sequential runner** at least two connections. It **does not** prove a production-safe configuration. With 20 concurrent requests, a pool of 5 can fail even when the single-threaded demo always passes.

### 10.2. REQUIRES_NEW Does Not Release Locks Held by Outer

Suspending the outer transaction **does not commit or roll back outer**, so it does not automatically release outer's locks. An inner call updating the same record locked by outer can wait on the very outer connection suspended on the same thread. This anti-pattern easily produces puzzling timeouts.

Use separate IDs in tests so propagation tests do not turn into lock-contention tests. When designing real transactions, analyze SQL ordering and which rows/tables each scope touches.

### 10.3. Inner's Isolation/Timeout/ReadOnly Are Its Own

Because `REQUIRES_NEW` truly opens another physical transaction, inner can declare its own isolation, timeout, and read-only settings:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    readOnly = true
)
public ReportView loadSnapshot() {
    return repository.loadSnapshot();
}
```

This is an illustrative API snippet omitting `ReportView` and the repository. When inner `REQUIRED` joins an outer transaction, outer's physical attributes usually stay unchanged; setting read-only/timeout/isolation on inner does not alter the already-open physical transaction (and with `validateExistingTransaction` enabled, the manager may reject mismatches).

Do not treat `readOnly=true` as a security control blocking every INSERT on every database. It may be an optimization hint or enforced differently across managers and drivers.

## 11. Why Not Replace REQUIRES_NEW with NESTED?

`Propagation.NESTED` typically relies on **savepoints** inside **one physical transaction** when using a supporting JDBC manager. It does not create an independent transaction like `REQUIRES_NEW`.

| Criterion | REQUIRED | REQUIRES_NEW | NESTED (when supported) |
| --- | --- | --- | --- |
| Physical transaction when outer has T | Same T | New, independent T2 | Same T, adds savepoint |
| Inner commits separately before outer | No | **Yes** | No, completes scope/savepoint only |
| Outer rollback after inner succeeds | Reverts inner | Does not revert committed T2 | Reverts inner |
| Inner fails, outer wants to continue | May mark T rollback-only | Inner rolls back T2, outer can continue | Can roll back to savepoint and continue |
| Needs a new connection for inner | Usually no | Usually yes | Usually no |
| Support | Transaction-capable managers | Managers supporting suspend/new | Managers/drivers supporting savepoints |

If the requirement is for inner to roll back locally while **outer still commits the entire physical transaction at the end**, `NESTED` may be worth exploring when resources support it, rather than `REQUIRES_NEW` causing independent commits. Do not assume JPA/R2DBC/all drivers support savepoints the same way JDBC does.

## 12. Exception Propagation: Independent Transactions, Not Independent Java Call Stacks

Something many overlook: `REQUIRES_NEW` separates physical transactions, yet methods still call each other in Java. If inner throws a runtime exception and outer **does not catch** it:

```java
@Transactional
public void outer() {
    saveOuter();
    inner.requiresNewInsertAndFail(99); // Throws IllegalStateException.
    // Code below does not execute.
}
```

This is an illustrative code fragment lacking dependencies/implementation. In this case:

1. Inner T2 is rolled back by inner's transaction interceptor.
2. Spring resumes T_outer and rethrows `IllegalStateException`.
3. The exception continues out through outer's transaction interceptor.
4. Outer rolls back T_outer under the default rule for `RuntimeException`.

**Both transactions can roll back** despite being physically independent, because the exception crossed both transaction scopes. This does not contradict `REQUIRES_NEW`; outer rolls back because its own unhandled exception escaped.

Scenario D in the demo catches the exception in outer, allowing outer to return normally. There, only inner T2 rolls back while outer T commits. Always state explicitly **who catches the exception where** when describing outcomes, instead of writing "a `REQUIRES_NEW` failure never affects outer"—that statement is too sweeping.

### 12.1. Checked Exceptions and Rollback Rules

By default, Spring rolls back on `RuntimeException` or `Error`; checked `IOException` usually does not trigger rollback without an extra rule. If inner `REQUIRES_NEW` INSERTs and throws checked `IOException`:

- Without `rollbackFor`: Spring may **commit** inner T2 and throw the checked exception up to outer.
- With `@Transactional(rollbackFor = IOException.class)`: inner can roll back T2.
- Outer may catch or rethrow; if it rethrows the checked exception, outer's rollback depends on **outer's** rollback rules, not automatically following inner.

The main experiment uses `IllegalStateException` because it triggers default rollback, avoiding mixing exception-rule variables into propagation variables. In advanced tests, test checked exceptions too so policies are crystal clear.

### 12.2. Once Inner Commits, Outer Errors Do Not Undo Inner

A T2 `afterCommit` event, a callback, or a subsequent failure in outer does not undo a durable T2. If a commit ACK from the DB is lost and it is unknown whether the transaction committed, query by business keys, use idempotency, and reconcile; do not treat an exception alone as proof of rollback.

## 13. Setting Up Proxies Properly So Propagation Executes

### 13.1. Call Through Another Injected Bean

`@Transactional` only takes effect when the transaction infrastructure actually intercepts the call. In default Spring AOP proxy mode:

```java
@Service
class TransferService {
    public void transfer() {
        this.logIndependently();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logIndependently() {
        // Write data...
    }
}
```

This is illustrative code. `this.logIndependently()` directly invokes the target method on the same bean, **bypassing the proxy** for that method. Thus `REQUIRES_NEW` on inner does not create a new physical transaction. If the outer caller has a transaction, inner code may simply run inside it; if there is no transaction, it may run outside any Spring transaction.

Experiments A–F in this lesson use **two beans**, `OuterService` and `InnerService`, so both transaction interceptors get to run. Putting all methods in one class and calling `this.inner()` means you **are no longer comparing propagations** as requested.

### 13.2. Methods Must Be Interceptable

Class-based proxies generally cannot intercept `private` or `final` methods as required. Use public non-final methods as transaction entry points. When relying on JDK proxies, interfaces and injection types matter too. Inside `@PostConstruct`/constructors, do not assume proxying is ready. AspectJ mode uses a different weaving mechanism, not the behavior demonstrated here.

### 13.3. Use the Right Manager and DataSource

A `@Transactional(REQUIRES_NEW)` pointing to database A's manager does not turn operations using an unmanaged connection on database B into an independent transaction on B. Check which resources your repository/EntityManager/JDBC actually uses. The example uses **one manager** and one DataSource for a single-variable comparison.

In multi-resource workflows, independent local transactions can cause partial commits across systems. Design proper Sagas/outboxes/compensation or distributed transactions; `REQUIRES_NEW` does not turn itself into an XA transaction.

### 13.4. @Async and Reactive Are Different Contexts

Standard imperative transactions are thread-bound. Calling `@Async`/Executors does not automatically carry outer's transaction context onto the new thread; an inner `REQUIRES_NEW` on another thread does not share the same suspend/resume semantics as synchronous proxied calls in the demo. For reactive transactions, context is managed via Reactor Context and `ReactiveTransactionManager`; test against reactive pipelines instead of copying thread-bound JDBC conclusions verbatim.

## 14. Writing Integration Tests That Detect Real Differences

### 14.1. Do Not Assert Only Exceptions

A test like:

```java
assertThrows(IllegalStateException.class,
    () -> outer.requiresNewThenOuterFails());
```

is not enough. Both `REQUIRED` and `REQUIRES_NEW` can make outer throw that exact exception. **The difference lies in the data after outer rolls back**, so add:

```java
assertEquals(0, count(21)); // Outer rolled back.
assertEquals(1, count(22)); // Inner REQUIRES_NEW committed.
```

Both snippets are illustrative JUnit syntax, **not standalone runnable test files**, since JUnit, context setup, and `count` helper are omitted. The demo project in Section 5 is a self-contained program with full SQL readbacks.

To test `REQUIRED`, substitute IDs 11 and 12: **both counts must equal 0**.

### 14.2. Do Not Let Test `@Transactional` Mask Results

Spring TestContext can automatically open a transaction around a `@Transactional` test method and roll it back at the end of the test. If the test calls a `REQUIRED` service, it can **join the test's transaction**, making commit/rollback timing and `isNewTransaction()` differ from production.

Use integration tests without an outer test transaction, or explicitly end the test transaction via `TestTransaction` before reading state. Verification SQL queries must execute **after the boundary you are measuring has finished**, ideally in a separate appropriate transaction.

### 14.3. Isolate from Unintended Pre-Existing Transactions

If a controller, filter, scheduled job, or runner is configured with an outer transaction, a `REQUIRED` method can join that transaction, while `REQUIRES_NEW` suspends it and opens a new one. Before drawing conclusions from tests, identify the source of any active physical transaction.

### 14.4. Verify Rollback-Only at the Right Place

With `REQUIRED`, an inner scope encountering a `RuntimeException` through the transaction interceptor can mark the shared physical transaction rollback-only. Outer catching and returning will typically produce `UnexpectedRollbackException` **at outer's commit boundary**. Tests must catch the exception outside the proxy and verify both rows vanished.

With `REQUIRES_NEW`, the inner rollback is handled inside its own transaction. Outer catching and returning can still commit outer's record; test D confirms this with count 1/0.

## 15. Diagnosing Numbers That Do Not Match Expected Output

| Symptom | Possible cause | Check to perform |
| --- | --- | --- |
| B yields `0/0` instead of `0/1` | Inner `REQUIRES_NEW` not intercepted, or wrong manager/resource | Check proxy call, new-transaction logs, manager bean |
| A yields `0/1` instead of `0/0` | Inner did not truly join transaction; ran on separate manager/connection | Check `DataSource` and connection resources |
| C does not throw `UnexpectedRollbackException` | Inner advice did not run, error swallowed in inner, rollback rules changed | Check `newTx`, exceptions, and transaction manager policy |
| D yields `0/0` instead of `1/0` | Outer did not catch, outer marked itself rollback-only, or commit failure | Check exception path outside proxy and DB state |
| App hangs at `REQUIRES_NEW` | Pool out of connections or inner waits on outer's lock | Check Hikari active/idle/waiting, locks, and timeouts |
| Output `1/1` in every case | Test never actually rolled back; exception thrown before/caught inside; wrong DB read | Print logs, read via SQL after method, verify IDs |
| `newTx` is always `true` | No outer transaction or outer method bypassed proxy | Check caller, outer's proxy, manager name |
| `newTx` is always `false` | Inner `REQUIRES_NEW` not intercepted or wrong transaction context | Check self-invocation and bean injection |
| SQL reports unique constraint violation | Stale IDs from prior run or altered schema/data lifecycle | Reset in-memory DB, use unique IDs |
| Counts vary across runs | Dirty DB, active test/runner transaction, or concurrent operations | Isolate data and scopes, avoid shared fixtures |

Enable extra logging in `application.properties` while investigating:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

This is an **optional debug configuration**, not required to observe the expected `System.out.println` output. Logs help spot the manager creating new transactions, suspending/resuming, committing, or rolling back. Never substitute a log line for SQL readbacks, and never log sensitive payloads.

## 16. Checklist for Choosing REQUIRED vs. REQUIRES_NEW

Before accepting `REQUIRES_NEW`, answer:

1. Are inner's changes **allowed to survive** when outer rolls back? If not, `REQUIRED` is usually more suitable on the same DB.
2. If inner fails, should outer continue and commit? If yes, design catch/recovery and consistency; `REQUIRES_NEW` is one option, and `NESTED` is also worth evaluating where savepoints are supported.
3. If inner committed yet outer failed, do you have **reconciliation/compensation** to avoid orphaned data?
4. Is inner truly called through a Spring proxy? Does it use the right manager/connection?
5. Does the pool have enough connections for outer and inner active together under concurrent load? Does inner lock rows outer still holds?
6. Have inner's isolation, timeout, read-only, and exception rollback rules been tested?
7. Are there non-transactional side effects (HTTP, email, event broker) outside DB rollback coverage?
8. Do tests prove SQL state **after commit/rollback**, rather than asserting only exceptions or uncommitted reads?

**Decision rule:** choose propagation by **business durability and atomicity requirements**. Never pick `REQUIRES_NEW` merely to silence an `UnexpectedRollbackException`; that can turn a loud failure into a silent partial commit.

## 17. Self-Check Exercises and Answers

**Q1.** Outer opened T, and inner `REQUIRED` INSERTed successfully and returned. Outer throws `IllegalStateException`. Does the inner row remain after outer rolls back?

**A:** No, assuming the same manager/resources and an actual rollback. Inner only joined T and had no separate physical commit.

**Q2.** Change inner to `REQUIRES_NEW`; it INSERTs/commits and outer then throws an exception. Does the inner row remain?

**A:** Yes, provided inner's commit actually succeeded. T_inner is independent; outer rollback does not undo it.

**Q3.** Inner `REQUIRED` throws a RuntimeException, and outer catches it and returns normally. Is the caller guaranteed success?

**A:** No. The inner scope may have marked the shared transaction rollback-only; outer attempting to commit can receive `UnexpectedRollbackException`.

**Q4.** Inner `REQUIRES_NEW` throws a RuntimeException, and outer catches it and returns. Is the outer row guaranteed to roll back?

**A:** No. The separate inner transaction rolls back, and outer can commit if there are no other errors or rollback-only flags. Demo D gives outer 1, inner 0.

**Q5.** If outer does not catch the exception from inner `REQUIRES_NEW`, is outer immune from rollback?

**A:** No. The runtime exception continues through outer's transaction interceptor and can cause outer itself to roll back. "Independent transaction" does not erase exceptions from the Java call stack.

**Q6.** With no outer transaction, is the difference between `REQUIRED` and `REQUIRES_NEW` easy to see via row counts?

**A:** No. Both create a transaction and commit. Test with an active outer transaction.

**Q7.** With a pool of only 1 connection, outer starts T and calls inner `REQUIRES_NEW`. What problem can happen?

**A:** Outer holds the connection while suspended; inner needs another connection and can wait until timeout. Pool sizing, locks, and concurrency are critical factors with `REQUIRES_NEW`.

**Q8.** Both `NESTED` and `REQUIRES_NEW` can let inner roll back while outer continues; do they share the same physical semantics?

**A:** No. `NESTED` can use a savepoint inside one physical transaction; a final outer rollback still undoes the inner work. `REQUIRES_NEW` creates a separate physical transaction, so a committed inner can survive outer rollback.

**Q9.** How do you prove `REQUIRES_NEW` beyond an `isNewTransaction=true` flag?

**A:** Have inner INSERT succeed and outer roll back, then query the DB **after the outer transaction ends**. If the inner row persists, that proves independent commit under controlled test conditions.

## 18. References

- Spring Framework — Transaction Propagation, comparing `PROPAGATION_REQUIRED`, `PROPAGATION_REQUIRES_NEW`, and `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion from the data:** experiments **A = 0/0** and **B = 0/1** show that outer rollback reverts an inner `REQUIRED` yet does not revert a committed inner `REQUIRES_NEW`. Experiments **C = 0/0 with UnexpectedRollbackException** and **D = 1/0** show that inner rollback under `REQUIRED` can prevent the shared transaction from committing, whereas `REQUIRES_NEW` lets outer continue after handling the exception. Choosing between them is a **business-consistency decision**, not merely an annotation parameter.