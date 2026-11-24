# Transaction Acquisition, Method Invocation, and Completion Flow

## 1. Goal: Looking Through `@Transactional`

When a Spring bean invokes a method annotated with `@Transactional`, what happens **before the method body runs**, **while the method runs**, and **after the method returns or throws an exception**?

The answer lies in the model **AOP proxy → transaction interceptor → transaction manager → target method → commit/rollback**. `@Transactional` is metadata; the annotation itself is not a `BEGIN` or `COMMIT` statement. Spring reads the metadata to create a transactional invocation wrapping the business call.

This lesson focuses on the **transaction acquisition, method invocation, and completion flow** within the **Proxy mechanism** topic of Spring transaction management. After this lesson, you will be able to:

1. Trace from the caller to the Spring AOP proxy, `TransactionInterceptor`, `TransactionAttribute`, and `PlatformTransactionManager`.
2. Explain when `getTransaction(...)` starts a new physical transaction and when it only joins an existing transaction.
3. Distinguish between **method body return** and **successful transaction commit and the caller receiving the result**.
4. Predict commit, rollback, rollback-only, and the exception type observed by the caller.
5. Distinguish the interceptor's `TransactionInfo` cleanup from JDBC resource release by the transaction manager.
6. Run a Spring JDBC experiment that records a timeline, verifying via database state **after the proxy call completes**.
7. Identify cases where annotations are not intercepted, differences between imperative and reactive paths, and limitations of the standard flow.

The concrete example uses **Java 17+, Spring Boot 3.3.x, Spring JDBC, H2, JUnit 5**. The principles of Spring's transaction abstraction apply more broadly; details of connection acquisition, flushing, timeouts, callbacks, or propagation capabilities may differ among `DataSourceTransactionManager`, `JpaTransactionManager`, JTA, and reactive managers.

## 2. The Big Picture

```text
                    calls bean via reference provided by Spring
Caller / Controller / another bean
                 |
                 v
      Spring AOP transactional proxy
                 |
                 v
          TransactionInterceptor
          | - look up TransactionAttribute
          | - determine transaction manager
          | - request TransactionStatus
          |
          v
   PlatformTransactionManager
          | - getTransaction(definition)
          | - create new / join / suspend / reject
          v
          TransactionStatus
                 |
                 v
          Target service method
                 |
                 +--- JdbcTemplate / Repository ---> Database
                 |
                 +--- normal -------------+
                 |                        |
                 +--- exception ----------+---> apply rollback rule
                                          |
                             commit / rollback via manager
                                          |
                              clean up required resources
                                          |
                                          v
                            Caller receives result / exception
```

This diagram is a **simplified standard imperative flow**. A call through a proxy can pass through many other advice/interceptors before reaching the target. `TransactionInterceptor` is just one advice in that chain. With callback-based transaction managers or reactive publishers, the implementation takes a different branch; do not treat this diagram as the detailed order for every implementation.

### 2.1. Components to Name Accurately

| Component | Responsibility | Common Misconception |
| --- | --- | --- |
| `@Transactional` | Describes propagation, isolation, read-only, timeout, rollback rules, manager qualifier, etc. | The annotation **does not open** a connection by itself |
| Spring AOP proxy | Intercepts calls going **through the proxy**, runs advice around target | `this.method()` normally does not go through the proxy |
| `TransactionAttributeSource` | Finds resolved transaction metadata for method/class | Not the transaction manager |
| `TransactionInterceptor` | Advice entering the transaction flow, calls `invokeWithinTransaction` | Not the database connection |
| `TransactionAspectSupport` | Core engine handling manager selection, scope opening, target invocation, and completion | Internal helpers are not application APIs to call directly |
| `PlatformTransactionManager` | `getTransaction`, `commit`, `rollback` for imperative transactions | `getTransaction` **does not always** create a new physical transaction |
| `TransactionDefinition` | Requests propagation, isolation, timeout, read-only, and name | A request does not mean the DB supports every option |
| `TransactionAttribute` | Extends definition with rollback rules/qualifier/labels | Metadata for a transactional joinpoint |
| `TransactionStatus` | State of the current scope: new transaction, rollback-only, completed, etc. | One status for a scope does not equal a dedicated connection |
| `TransactionSynchronizationManager` | Binds imperative transaction resources and synchronizations to the thread | ThreadLocal does not automatically propagate to new threads |

Related classes generally live in `org.springframework.transaction.*`, with the interceptor in `org.springframework.transaction.interceptor.*`; for JDBC, `DataSourceTransactionManager` is in `org.springframework.jdbc.datasource`.

## 3. Conditions for a Call to Actually Pass Through the Transaction Proxy

In default proxy mode, the main conditions are:

1. **Transaction infrastructure is enabled.** Plain Spring usually uses `@EnableTransactionManagement`; Spring Boot can auto-enable it if transaction auto-configuration and a suitable transaction manager are present.
2. **Bean is managed by Spring.** Instantiating an object with `new MyService()` outside the container and calling a method will have no Spring AOP proxy.
3. **Caller uses the proxy reference.** Inter-bean calls via injection typically qualify. A `this.inner()` call within the same object is not intercepted as a separate proxy call by default.
4. **Method has recognized metadata** and can be intercepted by the proxy. A reliable rule for learners: public service method, not private or final.
5. **The right transaction manager is selected** for the data source/resource. `@Transactional(transactionManager = "ordersManager")` selects by qualifier; Spring does not choose a transaction manager based on the method name.
6. **Imperative or reactive path is matched properly.** The example in this lesson uses `void`-returning methods and `PlatformTransactionManager`.

When one requirement is missing, the method may still run normally—even autocommitting each SQL statement in the database—yet **without the transaction boundary you expected**. Do not conclude an annotation is active just because data was saved.

### 3.1. Self-invocation and initialization timing

```java
@Service
public class PaymentService {
    public void submit() {
        this.saveTransactional(); // Bypasses transactional proxy on internal call.
    }

    @Transactional
    public void saveTransactional() {
        // ...
    }
}
```

This is **illustrative code**; it needs `@Service` and `@Transactional` imports to compile. If only `saveTransactional` carries the annotation, the `submit() → this.saveTransactional()` call in default proxy mode does not automatically open a new transaction for the internal call. Similarly, calling a transactional method from `@PostConstruct` before the proxy is ready is not a reliable testing approach.

The clearest pattern is placing the transaction boundary on a **public method called by another bean through the proxy**. If you need to coordinate individual transactions programmatically, consider `TransactionTemplate`. AspectJ weaving is an alternative to proxy mode when self-invocation must be handled, though it carries its own configuration and operational overhead.

## 4. Phase A — Metadata and Selecting the Transaction Manager

When a caller invokes an eligible method through the proxy:

1. Transaction advice identifies the actual method and target class.
2. `TransactionAttributeSource` resolves information from `@Transactional` on the method/class or from other transaction configuration.
3. `TransactionInterceptor`, via `TransactionAspectSupport.invokeWithinTransaction(...)`, processes this attribute.
4. The framework determines which manager to use based on the `transactionManager()/value()` qualifier or the configured default.
5. For the imperative path, the manager must be compatible with `PlatformTransactionManager`.

**Having no transaction metadata** does not necessarily eliminate all proxies/advice: the same proxy can still run other advice. However, the transaction advice itself will not request a new transaction for that call.

### 4.1. Transaction definition is a request, not an already-occurred event

Example:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false
)
public void updateInventory() {
    // ...
}
```

This metadata requests the corresponding semantics. When the manager joins an existing transaction under `REQUIRED`, the inner scope's isolation, timeout, and read-only attributes may **not be reapplied** because the physical transaction was already opened by the outer scope. Some managers allow enabling `validateExistingTransaction` to detect mismatches. Therefore you must inspect the **actual physical transaction** and manager configuration rather than guessing from annotations alone.

### 4.2. Annotation resolution mechanism

If a class has `@Transactional` and a method has a different `@Transactional`, Spring applies method/class resolution rules; it does not automatically merge all attributes into a "combined" configuration as a reader might expect. When debugging, inspect the `TransactionAttribute` that the infrastructure actually resolved for that method.

With a JDK dynamic proxy, the caller goes through an interface proxy; with a class-based proxy, Spring uses a subclass proxy for interceptable methods. Proxy type does not change the purpose of the transaction interceptor, but it affects interception points and self-invocation limits.

## 5. Phase B — `getTransaction`: Create New or Join?

This is the crux that is often misinterpreted. Calling:

```java
TransactionStatus status =
        transactionManager.getTransaction(definition);
```

**Does not mean** always issuing SQL `BEGIN` or opening a new connection. The manager checks `propagation`, any existing transaction, and resource capabilities to decide the next step.

| Propagation | No existing transaction | Existing transaction present |
| --- | --- | --- |
| `REQUIRED` (default) | Creates a physical transaction | Joins the existing physical transaction |
| `REQUIRES_NEW` | Creates a new physical transaction | Suspends outer transaction; creates an independent physical transaction |
| `SUPPORTS` | Runs without an actual transaction (may still have a synchronization scope depending on manager) | Joins the existing transaction |
| `MANDATORY` | Throws `IllegalTransactionStateException` | Must join the existing transaction |
| `NOT_SUPPORTED` | Runs without an actual transaction | Suspends outer transaction and runs non-transactionally |
| `NEVER` | Runs without a transaction | Throws `IllegalTransactionStateException` |
| `NESTED` | Typically creates a new transaction per manager capability | Typically uses a savepoint inside the current physical transaction, if supported |

For local JDBC transactions, the manager usually obtains a suitable `Connection` from the `DataSource`, configures required transaction settings (such as auto-commit/isolation/read-only per JDBC capability), and manages that connection within the scope. `JdbcTemplate` uses `DataSourceUtils` to obtain the connection bound to the transaction. Do **not** call `dataSource.getConnection()` yourself and use an independent connection if you want to participate in Spring's transaction.

### 5.1. Distinguishing logical and physical transactions

```text
Caller
  |
  v
Outer @Transactional(REQUIRED)  ─┐  logical scope A
  |                              │
  +--> Inner @Transactional     ├── same physical transaction P
       (REQUIRED)              ─┘  logical scope B
  |
  v
Outer finishes -> determines P's outcome
```

Two calls to `getTransaction` can return **two statuses for two logical scopes** while both reference the same physical transaction P. `status.isNewTransaction()` is typically **true** at the outer level and **false** at the inner level. Calling `commit(innerStatus)` does not mean the database just committed all of P; the physical commit only happens at the boundary owning the new transaction when conditions allow.

If the inner scope marks rollback-only due to an error, the outer scope—even if it catches the exception—still cannot commit P as it wishes. When the outer scope attempts to commit, Spring may throw `UnexpectedRollbackException` to inform the caller that the actual outcome was rollback.

### 5.2. `TransactionStatus` is not a "commit receipt"

Useful observations:

- `status.isNewTransaction()` indicates whether this scope created a new transaction or is joining one.
- `status.hasSavepoint()` can reflect a nested savepoint.
- `status.isRollbackOnly()` indicates the status has been marked rollback-only.
- `status.isCompleted()` reflects that the status was completed when the manager finished it.

These properties must be read **at the right phase**. `TransactionStatus` is not proof that the database durably committed; checking data state **after the transaction ends** confirms the outcome the application needs.

## 6. Phase C — Invoking the Target Method

Once the manager finishes `getTransaction`, the transaction advice allows the next interceptor or target method to run. On the standard imperative path:

```text
proxy
  -> resolve metadata / manager
  -> getTransaction(...)
  -> bind TransactionInfo for interceptor (thread context)
  -> invocation.proceedWithInvocation()
       -> target method
            -> DAO/JdbcTemplate -> SQL ...
            -> return value  OR  throw exception
  -> complete transaction based on outcome
```

The pseudo-code below **only explains** the algorithm structure; it is not an application API you should call directly:

```java
TransactionInfo info = createTransactionIfNecessary(...);

try {
    Object result = invocation.proceedWithInvocation();
    // Method-level success; transaction may not be committed yet.
    return result;
} catch (Throwable failure) {
    // Evaluate rollback rule and handle commit/rollback accordingly.
    throw failure;
} finally {
    // Restore the advice's transaction information on the current thread.
}
```

In real Spring source code, the result may undergo extra handling (for example, a `Future` already completed exceptionally under rollback rules) before calling the completion helper. So do not copy this pseudo-code into production as a transaction manager. The goal is to understand **where the target is invoked**.

When the target accesses the DB via Spring JDBC:

- `JdbcTemplate` typically obtains the connection participating in the active transaction.
- An `INSERT/UPDATE` statement may have **executed** before the method returns, yet that does not mean the transaction has committed.
- With JPA, `persist()` may not immediately emit SQL; `flush` and constraint checks can happen later, even at commit time.
- If the method throws an exception before returning, the interceptor must still drive the transaction scope to completion, unless a severe infrastructure failure prevents it.

## 7. Phase D — Method Return and Commit

When the target returns normally, the standard imperative mechanism calls the helper corresponding to `commitTransactionAfterReturning(...)`. That helper forwards the request to:

```java
transactionManager.commit(status);
```

Do not assume `commit(status)` is a driver `Connection.commit()` call in **every case**:

1. If `status` is a `REQUIRED` participating scope, the manager typically completes the logical scope without committing the outer physical transaction.
2. If `status` owns a new transaction, the manager checks rollback-only, runs appropriate synchronization callbacks, and calls commit on the physical transaction when allowed.
3. If rollback-only was set earlier, calling `commit` may end in a rollback and in some cases throw `UnexpectedRollbackException`.
4. Commit can fail due to constraints/flushing/connection or database issues; the caller receives an exception **after the method body has already returned normally**.
5. Transaction lifecycle callbacks can run before/after commit per manager rules; do not assume every callback executes after the thread is completely clear of the transaction.

### 7.1. Three milestones to distinguish

```text
Target service:    return value
                          |
Transaction advice:       v
                    commit(status)
                          |
Transaction manager:      v
                  commit / rollback / error
                          |
Caller:                   v
                sees result or exception
```

**"The method body finished running"**, **"the database commit succeeded"**, and **"the caller received a successful result"** are three distinct events. An error occurring at commit time can make the caller see an exception even though the method body threw nothing.

For example, a JPA repository holds an entity in the persistence context, the method returns, yet the SQL flush at commit violates a unique constraint. The exception can appear **after** the method body, while the transaction advice is completing.

### 7.2. Commit exceptions can make the outcome ambiguous

When a connection drops at the exact moment COMMIT is sent, the application may not know whether the database accepted the transaction. **Do not assume every commit exception means a successful rollback.** For operations sensitive to duplication (creating payments, issuing invoices), use a business key / idempotency key and reconciliation before retrying.

`PlatformTransactionManager.commit(status)` has a contract for handling status completion; after calling commit and hitting an error, do not arbitrarily call `rollback(status)` again to "fix" the outcome.

## 8. Phase E — Exceptions and Rollback Rules

If the target throws an exception through the transaction advice, Spring applies rollback rules. By default in standard `@Transactional` configuration:

- `RuntimeException` and `Error` → rollback.
- Checked `Exception` → **no default rollback**, unless a rollback rule is configured or the transaction is marked rollback-only for another reason.
- `rollbackFor` / `noRollbackFor` can alter the choice.
- When an exception is caught *before escaping through the interceptor*, the interceptor may see the method return normally; however, any rollback-only flag already set is still respected.

| Scenario in a new JDBC transaction | What interceptor typically requests | Expected observation |
| --- | --- | --- |
| Method returns normally | `commit(status)` | Data is persisted if commit succeeds |
| Method throws `IllegalStateException` | `rollback(status)` | Uncommitted changes are discarded |
| Method throws `IOException`, no rollback rule | `commit(status)` then propagate `IOException` | Data may be committed even though caller receives checked exception |
| Method throws `IOException` with `rollbackFor=IOException.class` | `rollback(status)` then propagate exception | Data is discarded if rollback succeeds |
| Method catches runtime exception and returns | Treated as normal return if no rollback-only | Typically commits |
| Inner `REQUIRED` throws runtime exception, outer catches and returns | Inner marks rollback-only; outer attempts commit | Physical rollback; possible `UnexpectedRollbackException` at caller |
| `getTransaction` fails before target | Method body is not invoked | No transaction for that scope to complete via the normal path |

A subtle exception: since Spring Framework 6.1, a `Future`/`CompletableFuture` **already completed exceptionally at the moment the method returns** can cause the transaction to be marked rollback-only if the failure matches rollback rules. `Vavr Try.Failure` also has documented handling in Spring. This is a **special rule based on the return value**; it does not mean an imperative Spring transaction stays open waiting for asynchronous tasks to finish later.

### 8.1. Exceptions outside vs. inside a transactional method

```java
try {
    orderService.placeOrder();
} catch (IllegalStateException ex) {
    // At caller outside proxy: transaction advice already handled completion
    // or threw an exception if completion failed.
}
```

The snippet above is **illustrative**; the `orderService` variable and `placeOrder` method must exist. If `orderService` is a proxy and a transaction scope was opened, the outer `catch` block receives the error **after the advice has already processed the corresponding exit path**. It does not guarantee the database rolled back cleanly: inspect the exception and actual DB state.

Conversely, catching **inside** the transactional method can hide a swallowed runtime exception from the interceptor. With an inner `REQUIRED` scope that already marked rollback-only before the outer method caught the error, the outcome can be completely different.

## 9. Phase F — Cleanup: Two Kinds to Distinguish

In the standard implementation of `TransactionAspectSupport`, there is a `cleanupTransactionInfo(...)` helper used to restore the advice's **TransactionInfo ThreadLocal**. On the imperative path, this helper is called in `finally` around the target invocation; it does not mean the connection/database transaction has committed or closed completely. **Resources** are completed/cleaned up by the transaction manager during commit/rollback handling.

A useful way to describe this:

```text
TransactionInterceptor / TransactionAspectSupport
  - manages call stack and advice's TransactionInfo
  - restores interceptor info in finally
  - asks manager to commit/rollback for the given status

PlatformTransactionManager implementation
  - manages the actual resource transaction
  - completes commit/rollback appropriately
  - triggers synchronization callbacks per lifecycle
  - unbinds resources, restores connection settings,
    releases connection when owning scope finishes
```

**Do not equate these three things:** `TransactionInfo` (the advice's info stack), `TransactionSynchronizationManager` (thread-bound resources/synchronizations), and `TransactionStatus` (state of a logical transaction scope). They are related but have distinct lifecycles and responsibilities.

### 9.1. Why don't callbacks always see a "clean thread"?

`TransactionSynchronization` has `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion`. Actual ordering depends on the manager and lifecycle; resources may still be bound during post-commit callbacks prior to final cleanup. If a post-commit callback needs to **write new data and commit independently**, you must define an explicit transaction boundary, often considering `REQUIRES_NEW` for the separated work. Do not use a single `isActualTransactionActive()` check to conclude you can extend the old transaction after commit.

In this lesson's example, we only record the timeline in a manager wrapper before and after the delegate completes. That is a simple observation technique for learning; production tracing should use properly designed instrumentation/callbacks rather than arbitrarily wrapping every transaction manager.

## 10. One Successful Call and One Failing Call

### 10.1. Success

```text
Caller -> Proxy -> TransactionInterceptor
                     |
                     +--> resolve @Transactional (REQUIRED)
                     +--> TM.getTransaction(...) -> status(new=true)
                     |
                     +--> Target.success()
                     |       INSERT row
                     |       return
                     |
                     +--> TM.commit(status)
                     |       JDBC COMMIT
                     |       cleanup resources
                     |
Caller <- Proxy -----+----- return result
```

Key observation point: the **caller** only receives a normal return after the advice's commit path finishes without error. If the call occurs inside an outer transaction, "normal return" may only complete the **inner logical scope**, while physical commit waits for the outer boundary.

### 10.2. Runtime exception

```text
Caller -> Proxy -> Interceptor
                     |
                     +--> TM.getTransaction(...) -> status(new=true)
                     +--> Target.failRuntime()
                     |       INSERT row
                     |       throw IllegalStateException
                     |
                     +--> rollback rule: true
                     +--> TM.rollback(status)
                     |       JDBC ROLLBACK
                     |       cleanup resources
                     |
Caller <- Proxy -----+----- throw IllegalStateException
```

With an active transaction and successful rollback, the inserted row does not exist when queried after the boundary. If rollback itself fails, an infrastructure exception may replace/mask the original error; inspect the cause chain and data state instead of assuming.

### 10.3. Checked exception without rollback configuration

```text
Caller -> Proxy -> Interceptor -> Target.failChecked()
                                   INSERT row
                                   throw IOException
                     |
                     +--> default rollback rule: false
                     +--> TM.commit(status)
                     |
Caller <- Proxy -----+----- IOException is propagated
```

The exception is still propagated after completion. This is a clear example of why **exception and rollback are not synonymous**.

## 11. Complete Practice: Recording the Timeline of proxy → manager → method

We will write a Spring Boot application using JDBC/H2 and a `PlatformTransactionManager` wrapper to record milestones. The wrapper only **observes** and forwards calls to a real `DataSourceTransactionManager`; it does not perform JDBC commit/rollback itself. Integration tests then verify both the **timeline** and the **data**.

### 11.1. Project layout

```text
tx-proxy-flow/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txflow/
    │   │   ├── TxFlowApplication.java
    │   │   ├── Timeline.java
    │   │   ├── RecordingTransactionManager.java
    │   │   ├── TransactionConfig.java
    │   │   ├── InnerStep.java
    │   │   └── FlowService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txflow/
        └── TransactionFlowIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-proxy-flow'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The example uses Gradle to manage Spring/JUnit/H2 dependencies. If you use Spring Initializr to generate the project, it provides the Gradle Wrapper; if you create these files manually, add the wrapper or use a compatible pre-installed Gradle. Do not invoke `javac` directly without configuring Spring's classpath.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txflow;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

H2 and a single table are chosen to make commit/rollback behavior easy to verify. `code` has a `UNIQUE` constraint; every test clears the table beforehand so it does not depend on data from previous tests.

### 11.2. Application and timeline-recording bean

`src/main/java/com/example/txflow/TxFlowApplication.java`:

```java
package com.example.txflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxFlowApplication.class, args);
    }
}
```

`src/main/java/com/example/txflow/Timeline.java`:

```java
package com.example.txflow;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class Timeline {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }

    public void clear() {
        events.clear();
    }
}
```

`Timeline` is an **experimental utility**. It uses an in-memory list so tests can assert ordering. Do not use an unbounded singleton list for production logging. The experiment assumes tests run sequentially, and each test clears the timeline before starting.

### 11.3. Manager wrapper: observing `getTransaction`, `commit`, `rollback`

`src/main/java/com/example/txflow/RecordingTransactionManager.java`:

```java
package com.example.txflow;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;

public final class RecordingTransactionManager
        implements PlatformTransactionManager {

    private final PlatformTransactionManager delegate;
    private final Timeline timeline;

    public RecordingTransactionManager(
            PlatformTransactionManager delegate,
            Timeline timeline) {
        this.delegate = delegate;
        this.timeline = timeline;
    }

    @Override
    public TransactionStatus getTransaction(TransactionDefinition definition)
            throws TransactionException {
        timeline.record("tm:get");
        TransactionStatus status = delegate.getTransaction(definition);
        timeline.record("tm:new=" + status.isNewTransaction());
        return status;
    }

    @Override
    public void commit(TransactionStatus status) throws TransactionException {
        timeline.record("tm:commit");
        delegate.commit(status);
        timeline.record("tm:commit:return");
    }

    @Override
    public void rollback(TransactionStatus status) throws TransactionException {
        timeline.record("tm:rollback");
        delegate.rollback(status);
        timeline.record("tm:rollback:return");
    }
}
```

Each milestone has a precise meaning:

- `tm:get`: the interceptor **called into** the transaction manager wrapper.
- `tm:new=true/false`: the delegate returned a status, corresponding to a new scope or a participating scope.
- `tm:commit`: there was a **call** to `commit(status)`; does not assert a physical JDBC commit when the status is a participant.
- `tm:commit:return`: the delegate returned normally. If it was the transaction owner with JDBC, the delegate's commit path finished without error.
- `tm:rollback` and `tm:rollback:return`: analogous for `rollback(status)`; when an inner `REQUIRED` is participating, the inner rollback may only **mark rollback-only** rather than rolling back the physical transaction right away.

If the delegate throws an exception, the corresponding `:return` milestone **does not appear**. The absence of the return milestone hints at which step failed, though it is not enough by itself to conclude whether the database committed or not.

### 11.4. Connecting the wrapper to the real JDBC manager

`src/main/java/com/example/txflow/TransactionConfig.java`:

```java
package com.example.txflow;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean("transactionManager")
    public RecordingTransactionManager transactionManager(
            DataSource dataSource,
            Timeline timeline) {
        return new RecordingTransactionManager(
                new DataSourceTransactionManager(dataSource),
                timeline);
    }
}
```

Import `DataSourceTransactionManager` from **`org.springframework.jdbc.datasource`**. This class is the JDBC transaction manager for a `DataSource`. The experiment creates only **one** Spring transaction manager bean named `transactionManager`; Boot still configures the datasource, JdbcTemplate, and H2 schema.

In production code, only add such a wrapper when there is a clear reason and thorough testing. If you need metrics, instrumentation, or lifecycle callbacks, prefer standard integration mechanisms suited to your system rather than wrapping every transaction for measurement.

### 11.5. An inner bean to test `REQUIRED`

`src/main/java/com/example/txflow/InnerStep.java`:

```java
package com.example.txflow;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerStep {
    private final JdbcTemplate jdbc;
    private final Timeline timeline;

    public InnerStep(JdbcTemplate jdbc, Timeline timeline) {
        this.jdbc = jdbc;
        this.timeline = timeline;
    }

    @Transactional // REQUIRED by default
    public void writeThenFail() {
        timeline.record("inner:enter");
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", "inner");
        timeline.record("inner:throw");
        throw new IllegalStateException("Simulated inner failure");
    }
}
```

`InnerStep` is a separate bean so the caller goes through its proxy. `InnerStep.writeThenFail()` throws a runtime exception after inserting; the interceptor for the inner logical scope applies the rollback rule. Because the inner method is called from an outer `REQUIRED` transaction, the manager typically **marks the shared physical transaction rollback-only** rather than completing an independent physical transaction right there.

### 11.6. Main service containing five scenarios

`src/main/java/com/example/txflow/FlowService.java`:

```java
package com.example.txflow;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class FlowService {
    private final JdbcTemplate jdbc;
    private final Timeline timeline;
    private final InnerStep inner;

    public FlowService(
            JdbcTemplate jdbc,
            Timeline timeline,
            InnerStep inner) {
        this.jdbc = jdbc;
        this.timeline = timeline;
        this.inner = inner;
    }

    @Transactional
    public void success() {
        write("ok");
    }

    @Transactional
    public void failRuntime() {
        write("runtime");
        throw new IllegalStateException("Simulated runtime failure");
    }

    @Transactional
    public void failChecked() throws IOException {
        write("checked");
        throw new IOException("Simulated checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void failCheckedRollback() throws IOException {
        write("checked-rollback");
        throw new IOException("Simulated checked failure");
    }

    @Transactional
    public void outerCatchesInner() {
        write("outer");

        try {
            inner.writeThenFail();
        } catch (IllegalStateException expected) {
            timeline.record("outer:caught");
        }

        // Method body returns normally; outer advice still must complete.
    }

    private void write(String code) {
        timeline.record("body:write=" + code);
        timeline.record("body:active=" +
                TransactionSynchronizationManager.isActualTransactionActive());
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
        timeline.record("body:inserted=" + code);
    }
}
```

In all four initial `@Transactional` methods, `write` is a private helper running inside the transaction opened by the public method; the helper **does not need** its own annotation. `TransactionSynchronizationManager.isActualTransactionActive()` proves Spring marks a transaction active on the thread **at the moment of logging**, though a single `true` line alone does not prove future commit.

With `outerCatchesInner`, the caller invokes the `inner` bean through its proxy. Inner fails and marks rollback-only; outer catches it and returns normally at the Java level. When the outer advice tries to commit the shared physical transaction, the manager is not permitted to commit it.

### 11.7. Integration test verifying both timeline and data

`src/test/java/com/example/txflow/TransactionFlowIntegrationTest.java`:

```java
package com.example.txflow;

import java.io.IOException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class TransactionFlowIntegrationTest {
    @Autowired
    private FlowService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private Timeline timeline;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
        timeline.clear();
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalReturnCommitsBeforeCallerGetsResult() {
        service.success();

        assertEquals(1L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=ok",
                "body:active=true",
                "body:inserted=ok",
                "tm:commit",
                "tm:commit:return"
        ), timeline.snapshot());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void runtimeFailureRollsBackBeforeExceptionReachesCaller() {
        assertThrows(IllegalStateException.class,
                service::failRuntime);

        assertEquals(0L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=runtime",
                "body:active=true",
                "body:inserted=runtime",
                "tm:rollback",
                "tm:rollback:return"
        ), timeline.snapshot());
    }

    @Test
    void checkedExceptionCanCommitThenReachCaller() {
        assertThrows(IOException.class,
                service::failChecked);

        assertEquals(1L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=checked",
                "body:active=true",
                "body:inserted=checked",
                "tm:commit",
                "tm:commit:return"
        ), timeline.snapshot());
    }

    @Test
    void rollbackForChangesCompletionDecision() {
        assertThrows(IOException.class,
                service::failCheckedRollback);

        assertEquals(0L, rows());
        assertEquals(List.of(
                "tm:get",
                "tm:new=true",
                "body:write=checked-rollback",
                "body:active=true",
                "body:inserted=checked-rollback",
                "tm:rollback",
                "tm:rollback:return"
        ), timeline.snapshot());
    }

    @Test
    void innerRequiredParticipatesAndMarksRollbackOnly() {
        assertThrows(UnexpectedRollbackException.class,
                service::outerCatchesInner);

        assertEquals(0L, rows());
        List<String> events = timeline.snapshot();

        // Outer creates physical transaction; inner only joins.
        assertEquals(2L, events.stream()
                .filter("tm:get"::equals).count());
        assertTrue(events.contains("tm:new=true"));
        assertTrue(events.contains("tm:new=false"));

        // Inner signals rollback; outer still attempts commit.
        assertTrue(events.contains("tm:rollback"));
        assertTrue(events.contains("tm:rollback:return"));
        assertTrue(events.contains("outer:caught"));
        assertEquals("tm:commit", events.get(events.size() - 1));
    }
}
```

### 11.8. How to run

Place the files at their exact paths, use JDK 17 or newer, Gradle compatible with Spring Boot 3.3.5, and from the directory containing `build.gradle` run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If there is no wrapper yet, generate the Gradle Wrapper with an installed Gradle or run `gradle test` with a compatible version. Spring/JDBC/H2/JUnit are placed on the classpath by Gradle; no separate `javac` command is needed. **Expected result: 5 tests pass.** The tests do not print fixed stdout; the report is at `build/reports/tests/test/index.html`.

| Scenario | Observed manager calls | Data after caller returns |
| --- | --- | --- |
| `success` | `getTransaction → commit` | 1 row |
| `failRuntime` | `getTransaction → rollback` | 0 rows |
| `failChecked` | `getTransaction → commit`, then checked exception reaches caller | 1 row |
| `failCheckedRollback` | `getTransaction → rollback` | 0 rows |
| `outerCatchesInner` | Outer get, inner get (join), inner rollback request, outer commit request raises rollback-only exception | 0 rows |

**Notes on test correctness:**

- The test class is **not** annotated with `@Transactional`. If the test owned a transaction itself, the `REQUIRED` service might merely join the test transaction and the entire test would roll back afterward; you would no longer prove the service's commit boundary.
- `@BeforeEach` clears the table before resetting the timeline. Therefore test data preparation does not leak into the recorded milestones.
- The wrapper timeline shows **manager calls and status**, without directly verifying a JDBC physical commit for participating scopes. Data conclusions rest on querying `rows()` **after the service call finishes**.
- Tests share one application context and in-memory H2 source. If parallel test execution is enabled, data and the timeline recorder must be isolated per test; JUnit 5's default configuration typically runs sequentially.
- There is no claim here that the tests were run on the reader's machine. The table above shows the **expected results from the source code**; if they differ, inspect the actual configured manager, logs, and test report.

## 12. What If the Flow Is Altered?

### 12.1. Errors before the target

If `getTransaction` cannot acquire a connection, the manager cannot start a transaction, or propagation requires an existing transaction that does not exist, an error may be thrown **before the target method runs**. In that case there is no `body:write=...` event in the experiment; do not manually run business logic from `catch` to "compensate" for a transaction that never opened.

### 12.2. Errors at commit and rollback

Errors in `commit`/`rollback` are **post-invocation** errors. They can mask an earlier exception from the method. Distinguish among:

- An exception directly from the target.
- An exception governed by rollback rules and handled by the manager.
- A new exception from the transaction manager when completion fails.
- Whether data actually committed; when the commit outcome is uncertain, **reconcile using a business key**.

Do not assume every transaction error is a `TransactionException`. For example, `JdbcTransactionManager` can translate commit/rollback errors into the `DataAccessException` family; `DataSourceTransactionManager` and other managers handle errors differently. Read the implementation and cause chain of the manager in use.

### 12.3. Multiple data sources or multiple managers

Transaction advice must choose a manager matching the resource used by the repository/JDBC code. A `@Transactional` method only manages the resources participating in that manager; it does not automatically combine email sending, HTTP calls, Kafka publishing, or an independent database into one shared physical transaction. For multi-resource transactions, you need an appropriate pattern such as JTA/XA (when truly needed and supported), transactional outbox, or compensation.

### 12.4. Ordering of other advice

`@Retryable`, `@Async`, caching, metrics, or custom aspects may also be present. **Advice ordering** determines what sits **inside** vs. **outside** the transaction boundary. A retry advice running outside the transaction advice can open a separate transaction per attempt; the reverse order might retry inside a transaction already marked rollback-only, which has very different semantics. Do not guess ordering from annotation placement order: inspect order configuration and the runtime call chain.

### 12.5. Reactive transactions

With `ReactiveTransactionManager`, the transaction is tied to the **Reactor context** and publisher lifecycle, not simply an imperative method call via thread-locals. Subscribing, completion, error, or cancellation of the reactive pipeline are the key transaction milestones. Therefore this lesson's JDBC diagram and integration tests **must not be copied verbatim** for `Mono`/`Flux`.

## 13. Observing and Diagnosing a Real Transaction

When verifying the proxy/manager flow outside the lab, identify the **exact phase** before guessing:

| Symptom | Hypothesis | How to check |
| --- | --- | --- |
| No transaction begin seen | Call bypassed proxy; annotation did not resolve; no matching manager | Inspect injected bean, target method, proxy mode, transaction infrastructure |
| SQL ran but rollback did not undo data | Executed on connection outside Spring transaction; autocommit; resource not on same manager | Check `DataSource`, `JdbcTemplate`/`DataSourceUtils`, manager, and connection |
| Method returned yet caller received exception | Commit/flush or completion callback failed | Check stack trace at transaction boundary; reconcile DB |
| Inner `REQUIRED` error caught yet outer did not commit | Shared transaction marked rollback-only | Check inner advice and `UnexpectedRollbackException` |
| Two `getTransaction` calls yet one physical commit | `REQUIRED` logical scopes sharing one transaction | Observe `isNewTransaction()`, connection, and propagation |
| Test sees data but external DB view does not | Test transaction has not committed or cache/persistence context | Measure after boundary via an independent transaction/connection |
| Timeout on long operation | Isolation/lock/query/statement timeout or deadline-checking infrastructure | Measure DB, pool, thread, and exact timeout point |

You can selectively enable logging in development environments:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Do not write tests relying on fixed log wording: logger names, ordering, and log messages can change across versions/managers. With JPA, add flush/SQL details as needed. Never log secrets, credentials, or personal data in traces.

### 13.1. A timeline-based debugging workflow

1. **Identify caller and target bean:** does the call pass through a Spring proxy?
2. **Determine transactional metadata:** which method/class provides `@Transactional`, and which manager is chosen?
3. **Trace `getTransaction`:** is there already an existing transaction? Does status have `isNewTransaction()`?
4. **Trace into the target:** does SQL use the right `DataSource` and bound resource?
5. **Confirm return/exception from target:** on which line does it happen, and where is any exception caught?
6. **Determine completion decision:** which rollback rule, rollback-only flag, propagation, and callbacks are involved?
7. **Measure completion at the manager:** was `commit(status)` or `rollback(status)` called, and did it return normally?
8. **Re-read data past the transaction boundary:** use an independent connection/context and business key to distinguish commit, rollback, or uncertain outcome.

The four facts "annotation present", "SQL executed", "target returned", and "log shows commit" are **each insufficient on their own** to prove business data was saved properly. Data observed after the transaction and business invariants decide.

## 14. Reasoning Exercises

**Exercise 1.** A controller calls a service bean through its proxy. The method has `@Transactional`, executes an `INSERT`, and returns. After the target returns, what else must happen for the caller to receive a normal result?

*Answer:* The transaction advice still has to execute completion for its scope, typically calling `commit(status)`. If the scope created a new physical transaction, the manager must commit/clean up successfully. If the method merely joined an outer transaction, physical commit waits for the outer boundary.

**Exercise 2.** A `@Transactional(REQUIRED)` method calls another bean annotated with `@Transactional(REQUIRED)`. The wrapper records `getTransaction` twice. Does that guarantee two `Connection.commit()` calls?

*Answer:* No. Two logical scopes can share one physical transaction. The participating inner status has `isNewTransaction() = false`; the physical commit is completed by the outer owner.

**Exercise 3.** A method throws checked `IOException`, has no `rollbackFor`, and has no rollback-only flag. By default, which path does Spring take?

*Answer:* `completeTransactionAfterThrowing(...)` may choose `commit(status)` because the exception does not match default rollback rules, and then still propagate `IOException` to the caller.

**Exercise 4.** Why is `cleanupTransactionInfo(...)` not synonymous with `Connection.close()`?

*Answer:* This helper restores the transaction advice's info on the thread. Completing the physical transaction, unbinding resources, returning the connection to the pool, and restoring connection state belong to the transaction manager.

**Exercise 5.** The target returns normally, yet commit hits a lost connection. Can we say all data rolled back?

*Answer:* No. The commit outcome may be uncertain. Check via business key/idempotency and reconciliation; do not retry blindly.

**Exercise 6.** A `@Transactional` method is called via `this.method()` from the same object with no outer transaction. Is the call guaranteed to enter `TransactionInterceptor`?

*Answer:* No, in default proxy mode. Internal calls bypass the proxy; to get a separate boundary, call through another Spring bean or use an appropriate transaction mechanism.

### Self-assessment criteria

You have mastered the lesson when you can explain in order **proxy → resolve metadata → getTransaction → invoke target → choose completion → commit/rollback → resource cleanup → caller**, accurately predict data state across normal return / runtime exception / checked exception / inner `REQUIRED` branches, and prove your prediction with tests that read data after the transaction.

## Official References

- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — `TransactionAspectSupport` API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
