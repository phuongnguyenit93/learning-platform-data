# Comparing All Seven Propagations Across Two Input States in Spring Framework

## 1. Two inputs determine propagation behavior

In Spring Framework, `Propagation` specifies what **the method being called** should do with an already existing transaction. There are seven options: `REQUIRED`, `SUPPORTS`, `MANDATORY`, `REQUIRES_NEW`, `NOT_SUPPORTED`, `NEVER`, and `NESTED`.

To compare accurately, always examine **two states right before entering the transaction interceptor**:

- **A — NO actual transaction yet:** the caller is not participating in a physical transaction managed by the corresponding transaction manager.
- **B — AN actual transaction ALREADY exists:** the caller already has an active transaction; for example, an outer service method declared `@Transactional(REQUIRED)`.

"Having an active transaction" does not simply mean having an annotation in source code or `TransactionSynchronizationManager.isSynchronizationActive() == true`: synchronization can be active in an empty transaction scope without opening a real DB transaction.

This article helps predict all **14 combinations (7 propagations × 2 input states)**, distinguish logical/physical transactions, suspend/resume, savepoints, rollback-only, connection pool costs, and common mistakes. The example runs with Java 17+, Spring Framework, JDBC, and H2.

## 2. Matrix of 7 propagations × 2 input states

| Propagation | **A — NO transaction yet** | **B — Outer transaction ALREADY exists** |
| --- | --- | --- |
| `REQUIRED` *(default)* | Creates a **new physical transaction**. | **Joins outer transaction**; does not open a separate physical transaction. |
| `SUPPORTS` | Runs **without an actual transaction**; may have a synchronization scope. | **Joins outer transaction**. |
| `MANDATORY` | **Throws `IllegalTransactionStateException`** before entering the method body. | **Joins outer transaction**. |
| `REQUIRES_NEW` | Creates a **new transaction**. | **Suspends outer**, creates an **independent physical transaction**, completes it, then resumes outer. |
| `NOT_SUPPORTED` | Runs **outside any transaction**. | **Suspends outer**, runs outside any transaction, then resumes outer. |
| `NEVER` | Runs **outside any transaction**. | **Throws `IllegalTransactionStateException`**, does not suspend automatically. |
| `NESTED` | Acts like `REQUIRED`: **creates a new transaction**. | **Savepoint inside the same physical transaction**, if manager and driver support it; otherwise may throw an error. |

This is the behavior table of **Spring transaction advice when the call actually passes through a proxy**. It is not a guarantee that every transaction manager supports savepoints, suspension, or that every Java method is intercepted.

### Memory aid

~~~text
A. NO TRANSACTION YET:
REQUIRED      -> NEW
SUPPORTS      -> NO ACTUAL TRANSACTION
MANDATORY     -> ERROR
REQUIRES_NEW  -> NEW
NOT_SUPPORTED -> NO ACTUAL TRANSACTION
NEVER         -> NO ACTUAL TRANSACTION
NESTED        -> NEW (like REQUIRED)

B. TRANSACTION ALREADY EXISTS:
REQUIRED      -> JOIN
SUPPORTS      -> JOIN
MANDATORY     -> JOIN
REQUIRES_NEW  -> SUSPEND; NEW INDEPENDENT TX; RESUME
NOT_SUPPORTED -> SUSPEND; NO ACTUAL TX; RESUME
NEVER         -> ERROR
NESTED        -> SAVEPOINT (if supported)
~~~

## 3. How do logical scope and physical transaction differ?

A **logical transaction scope** is the transaction scope declared on a method. A **physical transaction** is the actual transaction on the connection/data resource that ultimately commits or rolls back.

When **inner REQUIRED** is called from outer REQUIRED:

~~~text
Outer @Transactional(REQUIRED)      [logical OUTER]
  |
  '-- Inner @Transactional(REQUIRED) [logical INNER]
               |
               '-- SAME physical transaction TX-A

Finally: TX-A COMMITs or ROLLBACKs once.
~~~

Inner completing normally does not mean TX-A has committed. If inner marked rollback-only, outer—even if it catches the exception and tries to commit—may receive `UnexpectedRollbackException`.

With **inner REQUIRES_NEW**, Spring separates two physical transactions:

~~~text
Outer TX-A is active
  |
  +-- SUSPEND TX-A (holds outer resources)
  +-- BEGIN TX-B for @Transactional(REQUIRES_NEW)
  +-- COMMIT/ROLLBACK TX-B independently
  +-- RESUME TX-A
  |
  '-- TX-A continues then COMMITs/ROLLBACKs later
~~~

If TX-B commits and TX-A rolls back, TX-B's data can still survive. TX-B rolling back does not automatically propagate rollback-only state to TX-A, though an exception from TX-B **escaping the outer method** can cause the outer interceptor to choose rollback.

With **inner NESTED** using a JDBC savepoint:

~~~text
Outer physical TX-A
  UPDATE A
  SAVEPOINT S1
  inner UPDATE B
  if inner errors: ROLLBACK TO S1
  outer UPDATE C
TX-A COMMITs or ROLLBACKs at the end
~~~

`NESTED` has no new physical transaction. If outer rolls back at the end, **A, B, and C can all be reverted**, even if inner completed normally.

## 4. REQUIRED, SUPPORTS, MANDATORY — the group that can join a transaction

### `REQUIRED` — create if missing, join if present

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public void saveOrder() {
    // Write changes that need to stay within one transaction.
}
~~~

On input A, `REQUIRED` opens a transaction, and when the proxied method finishes normally, the transaction interceptor attempts to commit. On input B, it **does not** create a new physical transaction, instead sharing the outer transaction. This is the default choice for business use cases needing atomicity.

Easy to forget: an inner `REQUIRED` joining outer can decide rollback-only when encountering an unchecked exception. Inner's own `isolation`, `timeout`, or `readOnly` attributes **do not automatically alter** the physical transaction already opened by outer; manager configuration exists to reject mismatches.

### `SUPPORTS` — follow a transaction if one is active

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public Report readReport() {
    // Join if a transaction exists; otherwise still run.
}
~~~

On input A, `SUPPORTS` **does not open an actual transaction**. On managers using `SYNCHRONIZATION_ALWAYS`, a synchronization scope can still be active to coordinate resources. SQL on an auto-commit JDBC connection may commit immediately, so do not use SUPPORTS when multiple SQL statements must roll back together.

On input B, SUPPORTS **joins the outer transaction**. The same method may read inside a transaction or outside a transaction depending on the caller; evaluate actual consistency and locking behavior.

### `MANDATORY` — requires an existing transaction

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void writeAsPartOfExistingUseCase() {
    // Caller must open a transaction beforehand.
}
~~~

A → `IllegalTransactionStateException`, method body is not invoked. B → joins outer. Unlike `REQUIRED`, `MANDATORY` **does not auto-heal a missing transaction**. It is useful for a strong contract: this helper must only be called from a use case that already has a transaction.

The Java snippets in this section are **attribute examples** placed inside a Spring-managed service, not complete programs; the full runnable demo is in Section 8.

## 5. REQUIRES_NEW, NOT_SUPPORTED — the group that changes outer's boundary

### `REQUIRES_NEW` — independent physical transaction

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditAttempt() {
    // Audit can commit even if outer business transaction rolls back.
}
~~~

A → creates a new transaction. B → suspends outer, creates **another physical transaction**, finishes inner, and resumes outer. Inner can choose its own isolation/timeout/read-only; inner rollback does not automatically roll back outer.

**The price to pay:** with JDBC, outer usually holds Connection A while inner needs Connection B. If many concurrent requests hold outer connections and wait for inner, a small pool can be exhausted or deadlock while issuing connections. Spring recommends sizing the pool sufficiently for concurrent threads. Inner also does not automatically see uncommitted rows written by outer.

`REQUIRES_NEW` fits **independent attempt logging**, but should not emit an "order committed" event in inner before knowing outer's commit outcome.

### `NOT_SUPPORTED` — run outside any transaction

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void executeOutsideTransaction() {
    // Do not participate in caller's existing transaction.
}
~~~

A → runs without an actual transaction. B → suspends outer, runs without an actual transaction, then resumes outer.

**Difference:** `REQUIRES_NEW` has a new transaction with commit/rollback; `NOT_SUPPORTED` **has no inner physical transaction**. If inner uses JDBC auto-commit, SQL statements can persist even if outer rolls back later.

## 6. NEVER and MANDATORY — two opposite contracts

| Propagation | Mandatory condition on caller | Violation behavior |
| --- | --- | --- |
| `MANDATORY` | Must **have** an actual transaction | None → exception |
| `NEVER` | Must **not have** an actual transaction | Exists → exception |

~~~java
@Transactional(propagation = Propagation.NEVER)
public void mustRunWithoutTransaction() {
    // Run outside a transaction; throw error if caller has a transaction.
}
~~~

A → runs without a transaction. B → throws `IllegalTransactionStateException` before the target executes. `NEVER` **does not automatically suspend** like `NOT_SUPPORTED`.

An outer transactional method can catch the exception from a `NEVER` violation. If the exception is caught inside outer, do not automatically assume the outer transaction was marked rollback-only just because the NEVER method was rejected. Check rollback rules at the outer boundary and any other errors.

## 7. NESTED — one name, two execution modes depending on input

~~~java
@Transactional(propagation = Propagation.NESTED)
public void saveOptionalStep() {
    // Outer exists -> savepoint; no outer -> create a new transaction.
}
~~~

**Input A:** `NESTED` behaves like `REQUIRED`: creates a new transaction; with no outer transaction, there is no nested savepoint.

**Input B:** with a supporting manager, Spring creates a **savepoint within the same physical transaction**. Inner rollback reverts the work after the savepoint, and outer can catch the error and continue committing the remainder.

Support limitations to remember:

- `DataSourceTransactionManager`/`JdbcTransactionManager` together with a JDBC driver supporting savepoints is the fitting case. The demo enables `nestedTransactionAllowed=true`.
- `JpaTransactionManager` has limitations regarding the persistence context; do not assume every entity operation rolls back cleanly like a JDBC savepoint.
- Some JTA/transaction managers do not support nested transactions and may throw `NestedTransactionNotSupportedException` or another error.
- An eventual outer rollback still discards nested changes that completed normally; `NESTED` is **not** `REQUIRES_NEW`.

Do not replace `NESTED` with `REQUIRES_NEW` just to silence an exception: they have different commit/rollback semantics and resource usage.

## 8. Runnable example: all 14 cases and savepoint rollback

Environment: **Java 17+, Spring Framework 6.2.5, Spring JDBC, H2 2.2.224, Maven**. No Spring Boot. Inner calls go through a Spring bean proxy, not self-invocation.

Three fields printed in each method:

- `actual`: `TransactionSynchronizationManager.isActualTransactionActive()`.
- `hasTx`: `TransactionAspectSupport.currentTransactionStatus().hasTransaction()`.
- `savepoint`: `TransactionAspectSupport.currentTransactionStatus().hasSavepoint()`.

These booleans describe **current state**, not confirmed commit. Both `REQUIRED` joining outer and `REQUIRES_NEW` opening an independent transaction print `actual=true`. To distinguish two physical transactions, you must examine the propagation and boundaries accurately.

### 8.1. Structure

~~~text
spring-propagation-matrix/
  pom.xml
  src/main/java/demo/PropagationMatrixDemo.java
~~~

### 8.2. Create `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-propagation-matrix</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Create `src/main/java/demo/PropagationMatrixDemo.java`

~~~java
package demo;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class PropagationMatrixDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            InnerSteps inner = context.getBean(InnerSteps.class);
            OuterSteps outer = context.getBean(OuterSteps.class);

            jdbc.execute("CREATE TABLE marker (id INT PRIMARY KEY, note VARCHAR(40))");

            System.out.println("=== WITHOUT OUTER TRANSACTION ===");
            callAll("NONE", inner);

            System.out.println("=== WITH OUTER TRANSACTION ===");
            outer.callAllInsideTransaction();

            outer.testNestedSavepoint();
            List<Integer> ids = jdbc.queryForList(
                    "SELECT id FROM marker ORDER BY id", Integer.class);
            System.out.println("AFTER_NESTED_IDS=" + ids);
        }
    }

    static void callAll(String input, InnerSteps inner) {
        run(input, "REQUIRED", () -> inner.required(input));
        run(input, "SUPPORTS", () -> inner.supports(input));
        run(input, "MANDATORY", () -> inner.mandatory(input));
        run(input, "REQUIRES_NEW", () -> inner.requiresNew(input));
        run(input, "NOT_SUPPORTED", () -> inner.notSupported(input));
        run(input, "NEVER", () -> inner.never(input));
        run(input, "NESTED", () -> inner.nested(input));
    }

    private static void run(String input, String name, Runnable action) {
        try {
            action.run();
        } catch (IllegalTransactionStateException ex) {
            System.out.println(input + "/" + name
                    + " ERROR=IllegalTransactionStateException");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:propagation_matrix;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            var tm = new JdbcTransactionManager(ds);
            tm.setNestedTransactionAllowed(true);
            tm.setTransactionSynchronization(
                    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
            return tm;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public InnerSteps innerSteps(JdbcTemplate jdbc) {
            return new InnerSteps(jdbc);
        }

        @Bean
        public OuterSteps outerSteps(InnerSteps inner, JdbcTemplate jdbc) {
            return new OuterSteps(inner, jdbc);
        }
    }

    public static class InnerSteps {
        private final JdbcTemplate jdbc;

        public InnerSteps(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void show(String input, String propagation) {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();
            System.out.printf("%s/%s actual=%s hasTx=%s savepoint=%s%n",
                    input, propagation,
                    TransactionSynchronizationManager.isActualTransactionActive(),
                    status.hasTransaction(),
                    status.hasSavepoint());
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void required(String input) {
            show(input, "REQUIRED");
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supports(String input) {
            show(input, "SUPPORTS");
        }

        @Transactional(propagation = Propagation.MANDATORY)
        public void mandatory(String input) {
            show(input, "MANDATORY");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNew(String input) {
            show(input, "REQUIRES_NEW");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void notSupported(String input) {
            show(input, "NOT_SUPPORTED");
        }

        @Transactional(propagation = Propagation.NEVER)
        public void never(String input) {
            show(input, "NEVER");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nested(String input) {
            show(input, "NESTED");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedWriteAndFail() {
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    11, "nested-to-rollback");
            throw new IllegalStateException("nested failed");
        }
    }

    public static class OuterSteps {
        private final InnerSteps inner;
        private final JdbcTemplate jdbc;

        public OuterSteps(InnerSteps inner, JdbcTemplate jdbc) {
            this.inner = inner;
            this.jdbc = jdbc;
        }

        @Transactional
        public void callAllInsideTransaction() {
            PropagationMatrixDemo.callAll("EXISTING", inner);
        }

        @Transactional
        public void testNestedSavepoint() {
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    10, "outer-before");
            try {
                inner.nestedWriteAndFail();
            } catch (IllegalStateException ex) {
                System.out.println("NESTED_FAILURE=" + ex.getMessage());
            }
            jdbc.update("INSERT INTO marker (id, note) VALUES (?, ?)",
                    12, "outer-after");
        }
    }
}
~~~

Spring creates `InnerSteps` and `OuterSteps` via `@Bean`. `main` retrieves the services from the context; outer calls a **separate inner bean** so the transaction proxy handles propagation. `@EnableTransactionManagement` enables the annotation infrastructure. The JDBC manager is configured to allow nested savepoints.

### 8.4. Run command and stdout

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.PropagationMatrixDemo
~~~

The program's `System.out` lines (ignoring Maven/Spring logs):

~~~text
=== WITHOUT OUTER TRANSACTION ===
NONE/REQUIRED actual=true hasTx=true savepoint=false
NONE/SUPPORTS actual=false hasTx=false savepoint=false
NONE/MANDATORY ERROR=IllegalTransactionStateException
NONE/REQUIRES_NEW actual=true hasTx=true savepoint=false
NONE/NOT_SUPPORTED actual=false hasTx=false savepoint=false
NONE/NEVER actual=false hasTx=false savepoint=false
NONE/NESTED actual=true hasTx=true savepoint=false
=== WITH OUTER TRANSACTION ===
EXISTING/REQUIRED actual=true hasTx=true savepoint=false
EXISTING/SUPPORTS actual=true hasTx=true savepoint=false
EXISTING/MANDATORY actual=true hasTx=true savepoint=false
EXISTING/REQUIRES_NEW actual=true hasTx=true savepoint=false
EXISTING/NOT_SUPPORTED actual=false hasTx=false savepoint=false
EXISTING/NEVER ERROR=IllegalTransactionStateException
EXISTING/NESTED actual=true hasTx=true savepoint=true
NESTED_FAILURE=nested failed
AFTER_NESTED_IDS=[10, 12]
~~~

**Interpretation:**

1. `NONE`: REQUIRED/REQUIRES_NEW/NESTED open a transaction; MANDATORY throws an error; SUPPORTS/NOT_SUPPORTED/NEVER run without an actual transaction.
2. `EXISTING`: REQUIRED/SUPPORTS/MANDATORY join; REQUIRES_NEW opens an independent transaction yet still prints `actual=true`; NOT_SUPPORTED suspends outer so `actual=false`; NEVER throws an error.
3. NESTED without outer is a new transaction, `savepoint=false`; with outer it is a savepoint, `savepoint=true`.
4. The final test case creates row 10 before the savepoint, row 11 inside nested then throws an error, and row 12 after outer catches the error. Nested rolls back to the savepoint removing row 11, and outer commits rows 10 and 12. Hence `AFTER_NESTED_IDS=[10, 12]`.

The results are **expected under the Java 17/Spring 6.2.5/H2 setup**. Other transaction managers or drivers lacking savepoint support may throw errors; do not assume identical output verbatim across every JPA/JTA stack.

## 9. How exceptions and rollback are handled

The matrix tells you **how the scope is established**. If inner throws a `RuntimeException` under input B, the outcome depends on propagation:

| Inner propagation when outer exists | When outer catches the exception | Key consequence to remember |
| --- | --- | --- |
| `REQUIRED` | Inner interceptor may mark shared TX rollback-only | Outer may hit `UnexpectedRollbackException` on commit. |
| `SUPPORTS` | Because it joined outer, rollback rules can affect shared TX | No longer non-transactional. |
| `MANDATORY` | Joins outer; rollback rules apply to the existing transaction | Does not commit independently. |
| `REQUIRES_NEW` | Inner rolls back independently, outer can continue if allowed | Inner rollback-only does not automatically transfer to outer. |
| `NOT_SUPPORTED` | No inner physical transaction to roll back | Auto-committed SQL may not be reverted. |
| `NEVER` | Propagation check error can be caught by outer | NEVER's method body did not run. |
| `NESTED` | Inner rolls back to savepoint, outer can continue | Requires a manager supporting savepoints. |

If the exception is caught **right inside the annotated method** and not rethrown, the interceptor typically never sees the exception to trigger rollback. By default `RuntimeException`/`Error` cause Spring to roll back; checked exceptions usually do not, unless `rollbackFor` or global rollback rules change that.

An inner `REQUIRED` returning normally does not mean commit is finished. `NESTED` releasing a savepoint also does not mean physical commit. Even after the target method returns, the transaction interceptor can still fail during flush/commit.

## 10. Pool, locking, visibility, and manager support

**REQUIRES_NEW:** outer may still hold a JDBC connection/locks while inner needs a new connection. The pool gets exhausted when many concurrent threads hold outer connections and simultaneously wait for inner; size the pool for concurrency/nested depth and configure timeouts. Inner does not automatically see rows newly written but uncommitted by outer, and inner touching a row locked by outer can block/deadlock.

**NOT_SUPPORTED:** there is no inner transaction; suspending outer does not mean outer's locks are released. Inner may use another connection to run auto-committed SQL. A subsequent outer rollback cannot undo changes inner already committed.

**NESTED:** JDBC savepoints use the same physical transaction, usually the same connection. No new independent transaction is created; an eventual outer rollback still reverts nested work.

**Actual managers:** `JdbcTransactionManager` and H2 in the demo support JDBC savepoints. `JpaTransactionManager` and `JtaTransactionManager` have different restrictions/options for nested/suspend; some combinations can throw exceptions. With multiple transaction managers, "having a transaction" must be evaluated per selected manager/resource, not inferred from a single general thread-local flag.

## 11. Common mistakes

| Mistake | Explanation / how to fix |
| --- | --- |
| Thinking `REQUIRED` always opens a new transaction | If outer exists it joins, and does not commit separately. |
| Using `SUPPORTS` for multiple SQL statements requiring synchronized rollback | Without outer, no actual transaction is opened. |
| Assuming `MANDATORY` creates a transaction when missing | It throws `IllegalTransactionStateException`. |
| Assuming `NEVER` suspends automatically | It throws an error when a transaction exists; `NOT_SUPPORTED` suspends. |
| Using `REQUIRES_NEW` instead of `NESTED` without understanding the difference | One is a separate physical tx, the other is a savepoint in a shared physical tx. |
| Catching an unchecked exception and expecting outer `REQUIRED` to commit for sure | The shared tx may already be marked rollback-only. |
| Forgetting the connection pool when using `REQUIRES_NEW` | Inner may need an extra connection while outer still holds one. |
| Calling `this.inner()` and expecting inner `@Transactional` to take effect | Self-invocation bypasses proxy mode. Extract to another bean or use `TransactionTemplate`. |
| Equating active synchronization with an active actual transaction | Empty `SUPPORTS` can enable synchronization without creating a physical tx. |
| Reading status inside the method and claiming commit succeeded | Must observe after the outer boundary or via an appropriate transaction callback. |

### Proxy issue: INCORRECT example

~~~java
@Service
class WrongService {
    @Transactional
    public void outer() {
        inner(); // this.inner(), bypasses transaction proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Does not automatically get a REQUIRES_NEW boundary on the internal call above.
    }
}
~~~

This is **anti-pattern illustrative code**, not standalone source. In default proxy mode, for propagation to apply, call through a Spring proxy—such as a separate service bean like in the demo.

## 12. Checklist for choosing propagation

- Want to **create a transaction if none exists** and **join if one exists** → `REQUIRED`.
- Want to be able to run **inside or outside** a transaction without opening a new one → `SUPPORTS`.
- Want to **require the caller to have already opened a transaction** → `MANDATORY`.
- Want an **independent transaction** to commit/roll back separately → `REQUIRES_NEW`; weigh pool and atomicity.
- Want to **temporarily suspend the outer transaction to run non-transactionally** → `NOT_SUPPORTED`.
- Want to **fail when the caller already has a transaction** → `NEVER`.
- Want **partial savepoint rollback inside the same outer transaction** → `NESTED`, when the manager supports it.

There is no single optimal choice for every system. Set propagation according to desired commit/rollback semantics, verify manager capabilities, and then write integration tests proving DB state after the transaction **actually finishes**.

## 13. Self-check exercises

**Question 1.** No outer exists; `MANDATORY` is called. Result?

**Answer:** Throws `IllegalTransactionStateException` before the body runs.

**Question 2.** Outer exists; `NEVER` is called. Does Spring suspend outer and run the body?

**Answer:** No. `NEVER` rejects it; `NOT_SUPPORTED` is what suspends and runs outside the transaction.

**Question 3.** No outer exists; `NESTED` is called on a supporting JDBC manager. Does it use a nested savepoint?

**Answer:** Not needed; it creates a new physical transaction like `REQUIRED`.

**Question 4.** Outer exists; inner `REQUIRES_NEW` commits an audit row, and outer rolls back later. Can the audit row still exist?

**Answer:** Yes. Inner is a separate physical transaction and is not automatically undone by an outer rollback.

**Question 5.** Inner `NESTED` writes B and throws an unchecked exception; outer catches it and commits A. Can A remain and B be gone?

**Answer:** Yes, when savepoints are supported. The H2 example keeps IDs 10 and 12 and reverts 11.

**Question 6.** Inner `REQUIRED` marks rollback-only; outer catches the exception and returns. Is outer guaranteed to commit?

**Answer:** No; it may encounter `UnexpectedRollbackException` at final commit.

**Question 7.** `SUPPORTS` without outer has `isSynchronizationActive()` true. Is there an actual transaction?

**Answer:** Not necessarily. A synchronization scope is not a physical transaction.

**Question 8.** `NOT_SUPPORTED` writes auto-commit data while outer is suspended, then outer rolls back. Is inner's data lost?

**Answer:** Not necessarily; auto-committed SQL can still remain.

**Question 9.** When no transaction exists, `REQUIRED` and `REQUIRES_NEW` both open a new one. Are they the same when outer exists?

**Answer:** No. REQUIRED joins, whereas REQUIRES_NEW opens a new independent physical transaction.

## Key takeaways

**Input A:** `REQUIRED`, `REQUIRES_NEW`, and `NESTED` open a transaction; `SUPPORTS`, `NOT_SUPPORTED`, and `NEVER` run without an actual transaction; `MANDATORY` throws an error.

**Input B:** `REQUIRED`, `SUPPORTS`, and `MANDATORY` join; `REQUIRES_NEW` suspends + independent transaction; `NOT_SUPPORTED` suspends + runs outside; `NEVER` throws an error; `NESTED` uses a savepoint when supported.

**Key point:** physical transaction differs from logical scope. You need a Spring proxy, the right transaction manager, driver support, and end-to-end commit/rollback testing; an annotation or `isActualTransactionActive()==true` alone does not guarantee that a transaction committed.

## Official references

1. Spring Framework — [`Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/transaction/annotation/Propagation.html): definitions of all seven values.
2. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transactions, REQUIRED/REQUIRES_NEW/NESTED.
3. Spring Framework — [`TransactionDefinition` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/TransactionDefinition.html): transaction semantics.
4. Spring Framework — [`AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): policies and savepoints.
5. Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC nested support.
6. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxies and self-invocation.
