# Distinguishing Active Transaction from Resource Synchronization in Spring Framework

## 1. Core question

In Spring Transaction Management, two things are very easy to conflate:

1. **Is an actual transaction currently active?** That is, whether the current thread is bound by the Spring transaction manager to an *actual transaction* of a resource, such as a JDBC transaction that can be committed/rolled back.
2. **Is a resource synchronization mechanism currently active?** That is, whether Spring has opened a *transaction synchronization scope* for the thread to manage resource binding, Connection/Session sharing, and invoking `TransactionSynchronization` callbacks.

These two states are related, yet **not equivalent**. A `@Transactional(propagation = Propagation.SUPPORTS)` call with no outer transaction can have **active synchronization** even though there is **no physical JDBC transaction at all**. This is the most important case for understanding the topic accurately.

Spring provides two separate checks on `org.springframework.transaction.support.TransactionSynchronizationManager` (for the imperative flow):

```java
boolean synchronizationActive =
        TransactionSynchronizationManager.isSynchronizationActive();

boolean actualTransactionActive =
        TransactionSynchronizationManager.isActualTransactionActive();
```

**Accurate interpretation:**

- `isSynchronizationActive()` indicates that the **synchronization** infrastructure has been activated on the thread; when true, resource-management code can register synchronization callbacks.
- `isActualTransactionActive()` indicates that Spring marks this thread as associated with an **actual transaction**, rather than synchronization alone.
- Neither check by itself confirms that **the transaction committed successfully**; they are status signals *at the time of the call*, not a commit receipt.

Article scope: Spring Framework imperative transaction management with JDBC/JPA per thread, Spring AOP proxies, and `PlatformTransactionManager`. Reactive transactions have a different context mechanism, noted at the end.

## 2. Distinguishing three things: transaction, synchronization, and resource binding

To avoid misinterpreting the two booleans, clearly separate **three concepts**.

### 2.1. Actual transaction: commit/rollback boundary

An actual transaction has a resource lifecycle: begin, perform operations, and finally commit or roll back. With `JdbcTransactionManager`, Spring uses a JDBC connection, typically setting `autoCommit` to `false` in a new transaction and issuing `commit()` or `rollback()` as needed.

`@Transactional` with `Propagation.REQUIRED` and **no outer transaction** typically opens a new actual transaction. If `REQUIRED` joins an outer transaction, it does not create a separate physical transaction, yet still runs inside the existing actual transaction.

### 2.2. Transaction synchronization: synchronization scope

Synchronization is per-thread Spring-managed infrastructure that can serve to:

- Register `TransactionSynchronization` and callbacks such as `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion`.
- Bind resources like a JDBC `ConnectionHolder` or ORM `SessionHolder` to the thread and share them within a scope.
- Unbind/rebind resources when suspending/resuming a transaction.
- Close, release resources, and clean up state when the scope ends.

**Synchronization does not necessarily accompany an actual transaction.** A transaction manager like `AbstractPlatformTransactionManager` defaults to the `SYNCHRONIZATION_ALWAYS` policy, which enables synchronization even in an **empty transaction scope** of `SUPPORTS` when no physical transaction exists.

The phrase "transaction synchronization" here means **Spring's mechanism for managing resources and callbacks**; it does not mean distributed transactions, data syncing between two systems, or DB locks.

### 2.3. Resource binding: a resource is bound to the thread

`TransactionSynchronizationManager.hasResource(key)` asks whether a resource is bound to a key such as a `DataSource`. That is a third state, independent of whether synchronization is active or an actual transaction exists.

```java
boolean resourceBound =
        TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
        TransactionSynchronizationManager.getResource(dataSource);
```

This is an illustrative API snippet, assuming `dataSource` is provided. `hasResource(dataSource) == true` can occur when:

- The transaction manager started a JDBC transaction and bound a connection holder.
- A `SUPPORTS` scope **without an actual transaction** still had `DataSourceUtils` open a connection and bind the resource because synchronization was active.
- Another resource management infrastructure bound a holder with its own lifecycle.

Therefore, **having a bound resource does not prove a DB transaction is open**. Conversely, active synchronization does not require a resource to have been acquired right at the start of the scope.

## 3. Key state table

With `JdbcTransactionManager` or `DataSourceTransactionManager` using the default `SYNCHRONIZATION_ALWAYS` policy:

| Context when observed | `isSynchronizationActive()` | `isActualTransactionActive()` | Is there a DB transaction managed by Spring? |
| --- | --- | --- | --- |
| Outside all Spring transactional scopes | `false` | `false` | None from the observed context |
| `@Transactional(REQUIRED)` creates a new transaction | `true` | `true` | Yes |
| `@Transactional(SUPPORTS)` when caller has no transaction | `true` | `false` | **No**, even though synchronization exists |
| `@Transactional(SUPPORTS)` joining an outer `REQUIRED` transaction | `true` | `true` | Yes, uses outer transaction |
| `NOT_SUPPORTED` suspending an actual transaction | Depends on policy/manager; may be `true` | `false` inside the suspended scope | No physical transaction participating in that scope |

This table is for **one specific configuration**, not a universal law across all frameworks. When the transaction manager is configured with `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`, a `SUPPORTS` call without an actual transaction **will not** create synchronization. The `SYNCHRONIZATION_NEVER` policy disables synchronization infrastructure altogether. In custom configurations or transactions managed outside Spring, thread-local flags may not reflect the full underlying connection state.

**Never infer that `synchronizationActive == true` means `commit` or `rollback` will occur in the DB.** This is the most common mistake in this topic.

## 4. Why does `PROPAGATION_SUPPORTS` still enable synchronization?

`Propagation.SUPPORTS` means: *if a transaction exists, join it; if not, run without a physical transaction*. However, "running without a physical transaction" does not require "having no resource synchronization infrastructure".

Flow when **no outer transaction exists** and the policy is `SYNCHRONIZATION_ALWAYS`:

```text
Caller without a transaction
  |
  v
Spring proxy for @Transactional(SUPPORTS) method
  |-- Does not create a new physical transaction
  |-- Opens synchronization scope for the thread
  |     isSynchronizationActive()  = true
  |     isActualTransactionActive() = false
  |
  |-- Method runs
  |     |-- May acquire JDBC Connection via DataSourceUtils
  |     |-- Connection can be bound, reused, and cleaned up with the scope
  |     '-- SQL on autoCommit=true Connection may commit immediately
  |
  |-- Completes logical/empty scope, runs appropriate synchronization/cleanup
  '-- Returns control to caller
```

**Conclusion:** "resource synchronization" describes coordinating connection/callback lifecycles per thread; it **does not create atomicity/rollback** across multiple SQL statements when there is no corresponding DB transaction.

When `SUPPORTS` is called inside a `REQUIRED` that already has an outer transaction, it joins that actual transaction. The exact same `SUPPORTS` method can see `actual=false` in the first case and `actual=true` in the second case.

## 5. Runnable example with Java 17+, Spring Framework, and H2

The example below deliberately checks **all three states**: synchronization, actual transaction, and bound resource. It also shows how the exact same unchecked exception rolls back SQL in `REQUIRED` yet **cannot roll back auto-committed SQL** in `SUPPORTS` without a transaction.

Requirements: Java 17+, Maven, Spring Framework **6.2.5**, H2 **2.2.224**. No Spring Boot or database server needed.

Structure:

```text
transaction-state-demo/
  pom.xml
  src/main/java/demo/TransactionStateDemo.java
```

### 5.1. Create `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>transaction-state-demo</artifactId>
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
```

This is a Java SE application using a plain Spring container, without Spring Boot auto-configuration. `DriverManagerDataSource` is suitable for illustration; production should use an appropriate connection pool.

### 5.2. Create `src/main/java/demo/TransactionStateDemo.java`

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionStateDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            ProbeService probe = context.getBean(ProbeService.class);
            CallerService caller = context.getBean(CallerService.class);

            jdbc.execute("CREATE TABLE log_entry "
                    + "(id INT PRIMARY KEY, label VARCHAR(30))");

            state("OUTSIDE", dataSource);
            probe.supportsInspect("SUPPORTS_NO_TX");
            state("AFTER_SUPPORTS", dataSource);

            probe.requiredInsert(1, false);
            System.out.println("AFTER_REQUIRED_ROWS=" + count(jdbc));

            try {
                probe.supportsInsertThenFail(2);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_SUPPORTS=" + ex.getMessage());
            }
            System.out.println("AFTER_SUPPORTS_FAILURE_ROWS=" + count(jdbc));

            try {
                probe.requiredInsert(3, true);
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_REQUIRED=" + ex.getMessage());
            }
            System.out.println("AFTER_REQUIRED_FAILURE_ROWS=" + count(jdbc));

            caller.requiredCallsSupports();
            state("AFTER_OUTER", dataSource);
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM log_entry", Integer.class);
    }

    static void state(String label, DataSource dataSource) {
        System.out.printf("%s sync=%s actual=%s bound=%s%n",
                label,
                TransactionSynchronizationManager.isSynchronizationActive(),
                TransactionSynchronizationManager.isActualTransactionActive(),
                TransactionSynchronizationManager.hasResource(dataSource));
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:sync_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            var manager = new JdbcTransactionManager(dataSource);
            manager.setTransactionSynchronization(
                    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
            return manager;
        }

        @Bean
        ProbeService probeService(DataSource dataSource, JdbcTemplate jdbc) {
            return new ProbeService(dataSource, jdbc);
        }

        @Bean
        CallerService callerService(ProbeService probe, DataSource dataSource) {
            return new CallerService(probe, dataSource);
        }
    }

    public static class ProbeService {
        private final DataSource dataSource;
        private final JdbcTemplate jdbc;

        public ProbeService(DataSource dataSource, JdbcTemplate jdbc) {
            this.dataSource = dataSource;
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supportsInspect(String label) {
            state(label + "_BEFORE", dataSource);

            Connection connection = DataSourceUtils.getConnection(dataSource);
            try {
                state(label + "_AFTER", dataSource);
                System.out.println(label + "_AUTOCOMMIT="
                        + connection.getAutoCommit());
            } catch (SQLException ex) {
                throw new IllegalStateException("Cannot inspect connection", ex);
            } finally {
                DataSourceUtils.releaseConnection(connection, dataSource);
            }
        }

        @Transactional
        public void requiredInsert(int id, boolean failAfterInsert) {
            state("REQUIRED_INSERT", dataSource);
            jdbc.update(
                    "INSERT INTO log_entry (id, label) VALUES (?, ?)",
                    id, "required");
            if (failAfterInsert) {
                throw new IllegalStateException("required failure");
            }
        }

        @Transactional(propagation = Propagation.SUPPORTS)
        public void supportsInsertThenFail(int id) {
            state("SUPPORTS_WRITE", dataSource);
            jdbc.update(
                    "INSERT INTO log_entry (id, label) VALUES (?, ?)",
                    id, "supports");
            throw new IllegalStateException("supports failure");
        }
    }

    public static class CallerService {
        private final ProbeService probe;
        private final DataSource dataSource;

        public CallerService(ProbeService probe, DataSource dataSource) {
            this.probe = probe;
            this.dataSource = dataSource;
        }

        @Transactional
        public void requiredCallsSupports() {
            state("OUTER_REQUIRED", dataSource);
            probe.supportsInspect("SUPPORTS_JOINED");
            state("OUTER_AFTER_SUPPORTS", dataSource);
        }
    }
}
```

**Why is this code intercepted by Spring?** Both `ProbeService` and `CallerService` are beans created via `@Bean`. `main` retrieves the beans via `context.getBean(...)`, and `CallerService` calls into another bean. The `@Transactional` methods are `public`, so calls go through Spring proxies; there is no `this.method()` self-invocation.

**Why must `DataSourceUtils` be used in `supportsInspect`?** It checks for a resource already bound to the thread; if synchronization is active, it can acquire and **bind the connection** even when no actual transaction is active. Afterward `releaseConnection` coordinates with Spring cleanup rather than prematurely closing a connection used by an outer transaction.

`SYNCHRONIZATION_ALWAYS` is written explicitly to make the experiment's condition clear. This is also the default of `AbstractPlatformTransactionManager` in standard setups.

### 5.3. Run and output

In the `transaction-state-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionStateDemo
```

`System.out` lines from the program, ignoring Maven/Spring logs:

```text
OUTSIDE sync=false actual=false bound=false
SUPPORTS_NO_TX_BEFORE sync=true actual=false bound=false
SUPPORTS_NO_TX_AFTER sync=true actual=false bound=true
SUPPORTS_NO_TX_AUTOCOMMIT=true
AFTER_SUPPORTS sync=false actual=false bound=false
REQUIRED_INSERT sync=true actual=true bound=true
AFTER_REQUIRED_ROWS=1
SUPPORTS_WRITE sync=true actual=false bound=false
CAUGHT_SUPPORTS=supports failure
AFTER_SUPPORTS_FAILURE_ROWS=2
REQUIRED_INSERT sync=true actual=true bound=true
CAUGHT_REQUIRED=required failure
AFTER_REQUIRED_FAILURE_ROWS=2
OUTER_REQUIRED sync=true actual=true bound=true
SUPPORTS_JOINED_BEFORE sync=true actual=true bound=true
SUPPORTS_JOINED_AFTER sync=true actual=true bound=true
SUPPORTS_JOINED_AUTOCOMMIT=false
OUTER_AFTER_SUPPORTS sync=true actual=true bound=true
AFTER_OUTER sync=false actual=false bound=false
```

### 5.4. Explaining each group of results

**Group A — outside any transaction:** `OUTSIDE` and `AFTER_SUPPORTS` both have all three flags false. Spring cleaned up the thread-bound synchronization and connection after the scope ended.

**Group B — `SUPPORTS` without an actual transaction:** right at method entry, `sync=true`, `actual=false`, and `bound=false`. After `DataSourceUtils.getConnection`, `bound=true` even though `actual` remains false. The new H2 connection has `autoCommit=true`; resource synchronization does not automatically make the connection a JDBC transaction capable of rolling back multiple SQL statements.

**Group C — `REQUIRED`:** `sync=true`, `actual=true`, `bound=true` before `JdbcTemplate` runs, because the transaction manager already opened and bound a JDBC connection. The first insert commits, so the row count is 1.

**Group D — failure in `SUPPORTS` without a transaction:** `supportsInsertThenFail` sends `INSERT` on an auto-commit connection, then throws a runtime exception. Spring can handle ending the logical transaction scope, yet **there is no physical transaction to roll back the auto-committed SQL**. The row count still increases to 2. This proves `synchronization=true` **does not guarantee atomicity**.

**Group E — failure in `REQUIRED`:** `requiredInsert(3, true)` throws a runtime exception inside an actual JDBC transaction. The interceptor rolls back, so the row count stays 2. The fact that both methods throw `IllegalStateException` yet yield different DB outcomes comes from **whether or not a physical transaction exists**.

**Group F — `SUPPORTS` joining outer `REQUIRED`:** `CallerService.requiredCallsSupports()` opens a transaction first, then calls `supportsInspect` through the bean proxy. Inside SUPPORTS, `sync=true`, `actual=true`, `bound=true`, and the JDBC connection has `autoCommit=false`. Same SUPPORTS annotation, yet this time it uses the outer transaction. After the outer method finishes, all flags return to false.

**Reproducibility note:** The `autoCommit` values above belong to the H2 driver and how the Spring JDBC manager configures connections in the demo. Other pool/driver/transaction manager configurations may show different states; always verify with your project's actual manager.

## 6. How `TransactionSynchronizationManager` manages resources

In imperative Spring, `TransactionSynchronizationManager` uses **thread-locals** to hold:

- A map of resource key → resource holder (for example `DataSource` → `ConnectionHolder`).
- The set of `TransactionSynchronization` callbacks registered while synchronization is active.
- Certain metadata published by the manager, including transaction name, read-only status, isolation, and the actual-transaction flag.

APIs to remember:

| API | What question does it answer? |
| --- | --- |
| `isSynchronizationActive()` | Is there a synchronization scope to register callbacks? |
| `isActualTransactionActive()` | Is the current thread marked by Spring as tied to an actual transaction? |
| `hasResource(dataSource)` | Is there a resource holder bound to the `dataSource` key on this thread? |
| `getResource(dataSource)` | Retrieves the holder bound for the corresponding key; may be null if none |
| `getResourceMap()` | Snapshot of currently bound resources, useful for debugging (not commit proof) |
| `getSynchronizations()` | Snapshot of registered callbacks; call only when synchronization is active |
| `registerSynchronization(callback)` | Registers a callback on the current scope; valid only when synchronization is active |
| `isCurrentTransactionReadOnly()` | Reads read-only metadata published by the manager; does not prove DB forbids writes |
| `getCurrentTransactionIsolationLevel()` | Reads isolation metadata published by Spring; not necessarily every native DB state |

**Do not directly call** `initSynchronization()`, `clearSynchronization()`, `bindResource()`, `unbindResource()`, or `setActualTransactionActive()` in normal business services. Those are low-level APIs intended for transaction managers, resource managers, and integration infrastructure. Mutating flags manually or accidentally unbinding another party's holder can corrupt lifecycles, leak connections, or lose transaction context.

### Why is `getResource` insufficient to conclude commit/rollback?

A `ConnectionHolder` can be bound when synchronization is active so the same thread reuses a connection. **Binding** only indicates that Spring is managing the resource's lifecycle; it does not tell whether the connection has `autoCommit=false` or is participating in any transaction. To determine rollback capability, inspect the transaction manager, propagation, connection type, and outermost boundary.

In addition, `hasResource(dataSource)` can be false **before the method touches the DB**, even when synchronization is already active; the demo printed `SUPPORTS_NO_TX_BEFORE bound=false`. Resources are often bound **lazily** when a call actually acquires a connection.

## 7. Configuring the transaction manager's synchronization policy

`AbstractPlatformTransactionManager` has three modes worth knowing:

| Policy | Behavior |
| --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Opens synchronization even for "empty" scopes like `SUPPORTS` with no transaction; **default** |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Opens synchronization only for scopes with an actual transaction, skipping empty SUPPORTS |
| `SYNCHRONIZATION_NEVER` | Never activates synchronization infrastructure through this manager |

Example when intentionally wanting synchronization only with an actual transaction:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setTransactionSynchronization(
        AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

This is a **configuration illustration snippet**, not a standalone program. When changing the policy on the transaction manager **in a copy of the demo**, `@Transactional(SUPPORTS)` without an outer transaction will have `sync=false`; `DataSourceUtils` then will not bind a connection solely due to a synchronization scope.

**Do not arbitrarily change the policy just to make the two booleans always equal.** Some libraries/infrastructure rely on resource synchronization to coordinate connection lifecycles. Check the impact across the project's repositories and transaction callbacks.

Moreover, `SYNCHRONIZATION_NEVER` can make thread-local metadata published by the manager behave differently even while the manager still processes a real transaction. Hence those two APIs are **signals inside Spring's thread context**, not a protocol for directly inspecting the physical state of arbitrary DB connections outside Spring's ecosystem.

## 8. Are `TransactionSynchronization` callbacks proof of commit?

Code might want to register a task at the end of a transaction:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()
        && TransactionSynchronizationManager.isActualTransactionActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    // Runs after successful commit of the corresponding transaction.
                }
            });
}
```

This is **illustrative code** inside a Spring-managed service; imports for `TransactionSynchronization` and `TransactionSynchronizationManager` are required. Checking both to be true is a **cautious guard** when business logic requires an actual transaction before registering an after-commit callback. In the `SUPPORTS` example without an actual transaction, the second condition is false; do not assume a DB commit exists merely because `registerSynchronization` can be invoked.

Key points:

1. `registerSynchronization(...)` only requires synchronization to be **active** to be API-valid. It does not require a simultaneous physical transaction.
2. With an empty synchronization scope, callback handling depends on the transaction manager; **do not treat the callback name `afterCommit` as proof that a real DB commit always happened**. Choose an appropriate actual transaction boundary before registering work that requires durability.
3. `afterCommit` of an **actual transaction** runs once the manager has performed a successful commit via its mechanism; however, that callback does not guarantee external systems (email, queue, HTTP) received the data.
4. New DB operations performed inside `afterCommit` can sometimes still see a resource bound to the thread; if you need to write in an independent transaction, place that logic in another service with `Propagation.REQUIRES_NEW`.
5. To send events/notifications **reliably** across application crashes after DB commit, consider a **transactional outbox**: write the business record and outbox row in the same actual transaction, and have a worker dispatch with idempotency.

You can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` at the application layer, while still understanding whether event publication is tied to a real transaction/synchronization and handling non-transactional cases per Spring semantics.

## 9. `SUPPORTS`, `NOT_SUPPORTED`, and suspended transactions

Three situations need to be distinguished:

**Situation A: `SUPPORTS` without an outer transaction.** With `SYNCHRONIZATION_ALWAYS`, synchronization is active while actual=false. SQL statements may auto-commit; business code requiring atomicity should not rely on SUPPORTS in this situation.

**Situation B: `SUPPORTS` with an outer transaction.** The child method joins outer's actual transaction. That also means **the child method returning is not the final commit**; outer may roll back afterward.

**Situation C: `NOT_SUPPORTED` called while a transaction is active.** The transaction manager attempts to suspend the transaction and its associated resources/synchronizations; the `NOT_SUPPORTED` block does not participate in the suspended actual transaction. Depending on manager policy, an "empty" synchronization scope may be created during the NOT_SUPPORTED block. When it finishes, the outer transaction is resumed. Do not use a single `isSynchronizationActive()` reading to conclude the outer transaction was lost or committed.

Other propagations also need context: `REQUIRES_NEW` opens an independent physical transaction; `NESTED` typically uses a savepoint on the same physical transaction; `MANDATORY` requires an existing transaction. The topic of this article remains distinguishing **thread synchronization** from **actual transaction**, not turning a flag table into a substitute for full propagation semantics.

## 10. When to check each state in code?

| Need | Appropriate check | What not to infer |
| --- | --- | --- |
| Integration code needing to register a synchronization callback | `isSynchronizationActive()` before `registerSynchronization` | Being allowed to register a callback means a DB transaction exists |
| Executing a task only when Spring reports an actual transaction | `isActualTransactionActive()` on the same thread | The transaction has already committed or is guaranteed to commit |
| Checking if a JDBC resource is bound | `hasResource(dataSource)` / `getResource(dataSource)` | Bound connection means `autoCommit=false` |
| Verifying final commit | Observe after outer transaction or use an appropriate after-commit hook | `save()`, `flush()`, or mid-method booleans are sufficient |
| Confirming business rollback | Integration test writing SQL then throwing an exception, inspecting DB after scope | `isSynchronizationActive() == true` is enough to roll back |
| Processing data on a new thread, `@Async` | Define an explicit transaction boundary on the executing thread | Thread-local Spring transaction automatically transfers to worker thread |
| Reactive transactions | Use `org.springframework.transaction.reactive.TransactionSynchronizationManager`, Reactor context, and a reactive transaction manager | Directly using static thread-local imperative APIs in a reactive pipeline |

**Design tip:** when the goal is *ensuring atomicity*, design clear transaction boundaries with `@Transactional(REQUIRED)`/`REQUIRES_NEW` per business requirements. Do not use logic like `if (isSynchronizationActive())` to decide "a safe transaction is active", because that check does not distinguish `SUPPORTS` without a physical transaction.

## 11. Common errors and how to fix them

| Mistake | What is wrong? | How to fix |
| --- | --- | --- |
| Treating `isSynchronizationActive() == true` as having a DB transaction | Synchronization can be active in empty `SUPPORTS` | Check `isActualTransactionActive()` and transaction boundaries |
| Treating `hasResource(dataSource) == true` as SQL being rollbackable | Holders can also bind in scopes without an actual transaction | Check manager, connection, and propagation; write rollback tests |
| `SUPPORTS` throws a runtime exception, expecting auto-committed SQL to roll back | No physical transaction exists to undo already committed SQL | Use `REQUIRED` when business logic requires atomicity |
| Treating `isActualTransactionActive() == true` as a successful commit | It only reports a transaction is **currently** active | Verify after the boundary, via callbacks, and via DB state |
| Manually binding/unbinding resources in services | Can corrupt holders managed by the transaction manager | Use `JdbcTemplate`/`DataSourceUtils`/standard transaction APIs |
| Calling `dataSource.getConnection()` directly while expecting Spring JDBC management like `DataSourceUtils` | Direct connections may not join the thread-bound transaction | Use `JdbcTemplate` or `DataSourceUtils` for JDBC work |
| Calling `getSynchronizations()` when sync=false | Can throw `IllegalStateException` | Check `isSynchronizationActive()` first |
| Calling `this.supportsMethod()` and reasoning from the annotation | In proxy mode, internal calls typically bypass the child method's transaction interceptor | Call through a Spring bean/proxy |
| Calling `@Async` and expecting the two flags to remain set | Thread-locals do not automatically propagate | Create an appropriate boundary on the worker thread |
| Reading metadata inside a `@Transactional` Spring test and treating it as commit | TestContext normally rolls back test transactions | Write lifecycle-accurate commit/rollback tests, using `TestTransaction` when needed |
| Relying on these flags in JTA/reactive or transactions managed outside Spring | Thread-bound flags do not replace native transaction APIs | Check the right manager/runtime and context |

## 12. Self-check exercises

**Question 1.** A `@Transactional(SUPPORTS)` service is called from a controller with no transaction; `isSynchronizationActive() == true` and `isActualTransactionActive() == false`. Is that a contradiction?

**Answer:** No. Under the default `SYNCHRONIZATION_ALWAYS` policy, Spring can open an "empty" synchronization scope without opening an actual transaction.

**Question 2.** In that `SUPPORTS` scope, `DataSourceUtils.getConnection(...)` flips `hasResource(dataSource)` from false to true. Can we conclude `autoCommit=false`?

**Answer:** No. In the H2 example, the connection still has `autoCommit=true`. Binding only serves thread-level lifecycle/resource reuse.

**Question 3.** Two services both throw `IllegalStateException` after `JdbcTemplate.update`. Service A uses `SUPPORTS` with no outer tx; service B uses `REQUIRED` creating a new tx. Will both roll back SQL?

**Answer:** Not by default. With H2 auto-commit, A may have committed the SQL immediately and cannot roll back; B rolls back the change within the physical transaction.

**Question 4.** Why does `isActualTransactionActive() == true` inside a child `REQUIRED` method not guarantee the row exists after the child method returns?

**Answer:** The child method may be participating in an outer transaction; outer can roll back later. The boolean only reflects current state, not the final outcome.

**Question 5.** If `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` is set, will a `SUPPORTS` call without an outer tx still have `sync=true`?

**Answer:** Not under that policy. The manager only initializes synchronization when there is a corresponding actual transaction.

**Question 6.** Seeing a `ConnectionHolder` in `getResourceMap()`, is an inserted row guaranteed to be committed successfully?

**Answer:** No. Resource binding and transaction commit are two different concepts; you must observe after the actual transaction boundary and inspect DB state.

## Remember

- **`isSynchronizationActive()` asks about synchronization infrastructure; `isActualTransactionActive()` asks about an actual transaction published by Spring on the thread.**
- **`SUPPORTS` + no outer transaction + `SYNCHRONIZATION_ALWAYS`** is the classic example of `sync=true, actual=false`.
- Resource `bound=true` can appear solely because synchronization is active, even without a rollbackable DB transaction.
- `REQUIRED` typically has an actual transaction; `SUPPORTS` joining an outer transaction also has an actual transaction.
- Neither boolean **proves commit**, and neither replaces transaction boundaries or integration tests.
- In imperative Spring, the states above are tied to the **thread**. Reactive transactions use the **Reactor context** and separate APIs.

## Official reference documentation

1. Spring Framework — [`TransactionSynchronizationManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): distinguishing `isSynchronizationActive` and `isActualTransactionActive`.
2. Spring Framework — [`AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): the three transaction synchronization policies.
3. Spring Framework — [`DataSourceUtils` Javadoc](https://www.springframework.org/spring/docs/6.2.5/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): acquiring and binding JDBC connections when synchronization is active.
4. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical vs. logical transaction logic.
5. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): using transaction manager and transaction template.
6. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): lifecycle and callback timing.
