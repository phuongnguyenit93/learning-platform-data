# Distinguishing isSynchronizationActive from isActualTransactionActive in Spring Transaction Management

## 1. A Situation Where a Transaction Appears to Exist, Yet Does Not

You are debugging a Spring Java service and see:

```java
TransactionSynchronizationManager.isSynchronizationActive() // true
```

You conclude: "There is already a transaction; all SQL is wrapped in commit/rollback." **That conclusion may be wrong.** Under certain Spring configurations, a method using `PROPAGATION_SUPPORTS`, when **there is no outer DB transaction**, still opens a **transaction synchronization scope** to manage resources/callbacks per thread. At that moment:

```text
isSynchronizationActive()    = true
isActualTransactionActive()  = false
```

An `INSERT` executed via JDBC on a connection with `autoCommit=true` can be committed immediately; throwing an exception afterward in `SUPPORTS` **does not cause the database to revert the INSERT**, even though synchronization was active.

Both methods being discussed belong to:

```java
org.springframework.transaction.support.TransactionSynchronizationManager
```

and in Spring's **imperative** transaction model, they are `static` methods that read metadata bound to the **current thread**. They answer **two different questions**, not two ways of asking "is there a transaction or not?"

**Learning objectives:**

1. Distinguish a **transaction synchronization scope** from an **actual resource transaction** (JDBC/JPA).
2. Grasp how Spring manages `TransactionSynchronizationManager`, thread-bound resources, and the callback lifecycle.
3. Understand precisely when the two flags differ: `SUPPORTS` without an owner, `NOT_SUPPORTED` suspending an outer transaction, `REQUIRED`/`REQUIRES_NEW`, and the `SYNCHRONIZATION_ALWAYS` policy.
4. Understand the effect of `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` and `SYNCHRONIZATION_NEVER`.
5. Run a Java 17 + Spring Boot + Spring JDBC + H2 example to observe **true/false flags** and the **real difference in commit/rollback**.
6. Avoid misusing synchronization flags to drive business decisions or emit post-commit side effects.

> **API reading rule:** `isSynchronizationActive()` indicates whether Spring synchronization is open so corresponding callbacks can be registered; `isActualTransactionActive()` indicates whether Spring currently **marks the thread as associated with an actual transaction**. Both are **metadata per thread and transaction manager**, not a direct SQL query asking the database whether a commit is pending.

## 2. The Two APIs and Their Exact Meanings

### 2.1. `isSynchronizationActive()`

Signature:

```java
public static boolean isSynchronizationActive()
```

It returns `true` if Spring transaction synchronization has been activated for the **current thread**, typically via `TransactionSynchronizationManager.initSynchronization()` called by the transaction infrastructure.

Synchronization is the mechanism for registering `TransactionSynchronization` objects to receive notifications such as:

- before committing or completing the scope;
- after commit according to the transaction manager's semantics;
- after completion with committed/rolled-back/unknown status;
- suspend/resume when a transaction scope is suspended.

Resources such as connections or persistence sessions can be managed/bound by Spring within a synchronization scope, even when **no physical backend transaction exists**. Therefore, this flag primarily answers:

**"Can I currently participate in Spring's transaction synchronization mechanism and register a synchronization?"**

It **does not answer**:

- Is there an open JDBC transaction with `autoCommit=false`?
- Will an `UPDATE` that just ran be rolled back, or has it already auto-committed?
- How many connections or resources have been bound?
- Which transaction will be the eventual commit owner?
- Does an `afterCommit` callback necessarily correspond to a database `COMMIT`?

`isSynchronizationActive()` also does not count the number of registered synchronizations. It can be `true` even when the current callback list is empty.

### 2.2. `isActualTransactionActive()`

Signature:

```java
public static boolean isActualTransactionActive()
```

According to the Spring Javadoc, this method distinguishes a **thread associated with an actual transaction** from a **thread that only has a synchronization scope**. In the standard execution path of `AbstractPlatformTransactionManager` with synchronization enabled, the transaction manager sets the marker:

```java
TransactionSynchronizationManager.setActualTransactionActive(
    status.hasTransaction()
);
```

The line above illustrates how the manager attaches metadata when preparing synchronization. You **should not** call the setter to declare a DB transaction yourself in business code; flipping a thread-local boolean does not make a JDBC connection start a transaction.

Typical examples:

- `@Transactional(propagation = REQUIRED)` called through a Spring proxy, with no outer transaction: the manager opens a real JDBC transaction → `actual=true`.
- `PROPAGATION_SUPPORTS` with no outer transaction: does not open a backend transaction → `actual=false`.
- `PROPAGATION_SUPPORTS` joining an outer transaction: an actual transaction already exists → `actual=true`.
- `PROPAGATION_NOT_SUPPORTED` suspending an outer transaction: inside the scope there is no participating backend transaction → `actual=false`.

**Important limitation:** this is a **marker exposed by Spring's transaction infrastructure**, not an automatic check of all transactions managed by non-Spring code or other drivers. If the application calls `Connection.setAutoCommit(false)` manually on a separate connection, both Spring flags may still be `false` even though an external JDBC transaction is open.

### 2.3. Side-by-Side Comparison

| Criterion | `isSynchronizationActive()` | `isActualTransactionActive()` |
| --- | --- | --- |
| Question answered | Is Spring's synchronization scope active? | Does Spring mark an actual transaction as active? |
| Primary subject | Synchronization callback list + resource management | Physical transaction state according to the manager |
| Can be `true` without a backend transaction? | **Yes** | Typically **no** |
| Appropriate check before `registerSynchronization`? | **Yes** | Not sufficient: `actual=true` does not automatically guarantee synchronization is active |
| Is `true` proof that `COMMIT` succeeded/will succeed? | No | **No** |
| Bound to the current thread? | Yes, in imperative Spring | Yes, in imperative Spring |
| Replaces `TransactionStatus`/rollback rules? | No | No |
| Measures the state of an R2DBC reactive transaction via static ThreadLocal? | No | No |

**Memory aid:** "Synchronization is the **tracking/callback registration mechanism**; actual transaction is the **transactional resource scope**." The two concepts often appear together, yet they are **not identical**.

## 3. What Does TransactionSynchronizationManager Attach to the Thread?

In imperative Spring JDBC, `TransactionSynchronizationManager` manages per-thread structures (not global variables shared across all requests):

```text
Current thread
  |
  +-- resources: Map<resource-key, resource-holder>
  |       e.g., DataSource -> ConnectionHolder
  |
  +-- synchronizations: TransactionSynchronization instances
  |       registered when synchronization is active
  |
  +-- transactionName
  +-- currentTransactionReadOnly
  +-- currentTransactionIsolationLevel
  +-- actualTransactionActive
```

Several APIs to distinguish:

| API | Meaning |
| --- | --- |
| `getResource(key)` | Retrieve the resource bound to the key on the thread, if any |
| `hasResource(key)` | Check whether a resource is bound to the key |
| `bindResource(key, resource)` | Bind a resource to the thread; Spring infrastructure is normally responsible |
| `unbindResource(key)` | Unbind a resource; Spring infrastructure is normally responsible |
| `isSynchronizationActive()` | Is there an active synchronization list for the thread? |
| `registerSynchronization(synchronization)` | Register a callback; requires synchronization to be active |
| `getSynchronizations()` | Obtain a snapshot of the callback list; requires synchronization to be active |
| `isActualTransactionActive()` | Thread-level actual transaction marker |
| `getCurrentTransactionName()` | Exposed transaction name, may be `null` |
| `isCurrentTransactionReadOnly()` | Current read-only metadata; does not itself guarantee DB write prohibition |
| `getCurrentTransactionIsolationLevel()` | Explicitly declared isolation level or `null`; not always the actual value the driver uses |

A **bound** connection is not automatically a connection inside a real transaction. In `SUPPORTS` without a backend transaction, Spring can temporarily bind/reuse a JDBC connection for the same synchronization scope to manage its lifecycle, while the connection remains in **auto-commit** mode.

Conversely, a transaction manager can start a real DB transaction **without activating transaction synchronization** if configured that way. Therefore, **do not reason in one direction** that "having resources" or "having synchronization" guarantees a transaction exists, nor should `!isSynchronizationActive()` be used as absolute proof that "no backend transaction exists."

### 3.1. Do Not Call Infrastructure APIs Arbitrarily

`initSynchronization()`, `clearSynchronization()`, `setActualTransactionActive(...)`, `bindResource(...)`, and `unbindResource(...)` are meant primarily for framework/resource management. Business code calling them directly can corrupt cleanup schedules, lose connections, or produce markers that diverge from actual DB state.

Normal business code should use:

- `@Transactional` via a Spring proxy;
- `TransactionTemplate` with the right manager;
- `JdbcTemplate`/Spring Data JPA using Spring-coordinated resources.

Use the `is...Active()` read APIs for **debugging, diagnostics, or resource integration**, not setters to "manually turn on a transaction."

## 4. The Four Boolean Combinations Table: Do Not Over-Infer

| Synchronization | Actual | Common Meaning |
| --- | --- | --- |
| `false` | `false` | Outside any Spring transaction/synchronization scope; could also be disabled synchronization policy or a non-Spring transaction |
| `true` | `false` | **Synchronization exists without a backend transaction**: `SUPPORTS` without outer, `NOT_SUPPORTED` under the default `SYNCHRONIZATION_ALWAYS` mode |
| `true` | `true` | Normal transaction scope via the manager: `REQUIRED`, `REQUIRES_NEW`, or `SUPPORTS` joining an outer transaction |
| `false` | `true` | Not a typical default state of the imperative manager covered in this lab; if encountered, inspect custom managers, markers, suspend/resume, and orchestration flow |

This table is **not an absolute mapping** for every `TransactionManager` implementation. Always specify the transaction manager, synchronization policy, propagation, and whether the call actually passes through Spring's transaction infrastructure.

### 4.1. Why Is `true/false` Completely Valid?

Example:

```text
Caller without a DB transaction
   |
   v
Spring proxy: @Transactional(SUPPORTS)
   |
   +-- Does not create an actual DB transaction
   +-- But the manager uses SYNCHRONIZATION_ALWAYS
   +-- initSynchronization() for the thread
   |
   v
method body:
  isSynchronizationActive()   -> true
  isActualTransactionActive() -> false
   |
   v
method ends, cleanup synchronization
```

This state is **deliberately** designed by Spring to support resource binding and synchronization callbacks in an "empty transaction scope." Do not call it "Spring reporting inaccurately."

### 4.2. Why Does `true/true` Not Yet Guarantee an Immediate Commit?

`SUPPORTS` joining an outer `REQUIRED` can also see `true/true`. When the inner method returns, the physical transaction owned by outer has not yet ended. If outer continues and then rolls back, all SQL in the shared transaction can still be reverted. The two flags do not reveal **who the transaction owner is** or **when the scope will commit**.

## 5. Synchronization Policies of AbstractPlatformTransactionManager

`AbstractPlatformTransactionManager` supports three primary modes, configured via:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS
);
```

Constant names and effects:

| Mode | Synchronization when an actual transaction is active | Synchronization for "empty" SUPPORTS/NOT_SUPPORTED |
| --- | --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Yes | **Yes** |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Yes | **No** |
| `SYNCHRONIZATION_NEVER` | No | No |

`SYNCHRONIZATION_ALWAYS` is the default of `AbstractPlatformTransactionManager` in the traditional Spring 6.x model. "Always" means *activating synchronization even for empty scopes when the manager handles those scopes*; it does **not** mean every thread in the JVM always has `sync=true`.

### 5.1. With ALWAYS (Default): SUPPORTS Can Be true/false

```java
TransactionTemplate supports =
    new TransactionTemplate(transactionManager);

supports.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_SUPPORTS);

supports.executeWithoutResult(status -> {
    System.out.println(
        TransactionSynchronizationManager.isSynchronizationActive()
            + " / " +
        TransactionSynchronizationManager.isActualTransactionActive()
    );
});
```

This is an **illustrative snippet**, requiring a real Spring manager and code running on a thread without an outer transaction. Using a flag-supporting manager with `SYNCHRONIZATION_ALWAYS`, it prints:

```text
true / false
```

If `SUPPORTS` is called inside an outer `REQUIRED`, the typical output is `true / true`. Propagation **together with the outer state** determines the behavior, not the `SUPPORTS` label alone.

### 5.2. With ON_ACTUAL: Reducing "Empty" Synchronization Scopes

Configuration:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager
        .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION
);
```

When `SUPPORTS` has no outer transaction and the manager does not open an actual transaction, synchronization is not created; the typical result becomes:

```text
isSynchronizationActive()   = false
isActualTransactionActive() = false
```

Inside a real `REQUIRED` transaction opened by the manager, synchronization is still enabled and typically `true/true`. This is a **manager policy change** that can affect resource reuse/cleanup and callback-based integrations. Do not change this setting in a large system just to make a log "look more sensible."

### 5.3. With NEVER: An Important Caveat When Interpreting Markers

`SYNCHRONIZATION_NEVER` disables the synchronization mechanism **even when the manager opens an actual resource transaction**. In `AbstractPlatformTransactionManager`'s execution path, exposing the `actualTransactionActive` thread-local marker is typically performed in `prepareSynchronization(...)` **when a new synchronization is initialized**. Consequently, in an isolated execution with `SYNCHRONIZATION_NEVER`, you may observe:

```text
isSynchronizationActive()   = false
isActualTransactionActive() = false
```

**Even though a physical JDBC transaction exists.** This illustrates why `isActualTransactionActive()` remains a **Spring-exposed marker**, not an oracle independent of infrastructure configuration. If business logic strictly needs to know whether a transaction exists, choose the appropriate boundary/API contract rather than checking only two thread-local booleans.

This does not mean `SYNCHRONIZATION_NEVER` disables database transactions itself. It changes synchronization and marker exposure. With custom managers/resources, different behavior may occur; always test in the actual environment.

### 5.4. Do Not Activate Synchronization by Multiple Managers on the Same Thread

Spring Javadoc warns that synchronization is not designed for **multiple distinct transaction managers simultaneously activating the same thread-bound synchronization context**. In systems with multiple DataSources/managers, establish clear boundaries, tracking which manager coordinates the thread and which resource is bound. Do not assume calling `isSynchronizationActive()` tells you whether "manager A turned it on" or "manager B turned it on": the method does not return manager identity.

## 6. How Does Propagation Change the Two Flags?

Assuming `JdbcTransactionManager`/`DataSourceTransactionManager` extending `AbstractPlatformTransactionManager`, synchronization policy `ALWAYS`, real Spring proxy/template application, and a thread with a controlled boundary:

| Running scope | Outer transaction present on entry? | Sync | Actual | Notes |
| --- | --- | --- | --- | --- |
| Code outside any Spring transaction boundary | No | `false` | `false` | Provided the thread was properly cleaned up |
| `REQUIRED` | No | `true` | `true` | Opens a new physical JDBC transaction |
| `REQUIRED` | Yes | `true` | `true` | Joins the existing transaction |
| `REQUIRES_NEW` | Yes or no | `true` | `true` | Opens a new physical transaction, suspending outer if present |
| `SUPPORTS` | **No** | **`true`** | **`false`** | "Empty" scope, no backend transaction |
| `SUPPORTS` | **Yes** | `true` | `true` | Joins the outer actual transaction |
| `NOT_SUPPORTED` | Yes | **`true`** | **`false`** | Suspends outer, empty scope with synchronization |
| `NOT_SUPPORTED` | No | `true` | `false` | Scope without a backend transaction |
| `NEVER` | No | `true` | `false` | May have empty synchronization under ALWAYS |
| `NEVER` | Yes | Does not enter body | Does not enter body | Spring throws an error because propagation forbids an existing transaction |
| `MANDATORY` | No | Does not enter body | Does not enter body | Spring throws an error because an existing transaction is required |
| `MANDATORY` | Yes | `true` | `true` | Joins outer |
| `NESTED` (JDBC savepoint) | Yes | `true` | `true` | Shares physical transaction, nested savepoint |
| `NESTED` | No | `true` | `true` | Typically creates a new actual transaction similar to REQUIRED |

These rows represent **typical scenarios** under `ALWAYS`. Do not treat the table as a universal rule for reactive managers, custom managers, or `ON_ACTUAL`/`NEVER` configurations.

### 6.1. NOT_SUPPORTED: Outer Is Suspended, Not Committed

Suppose:

```text
outer @Transactional(REQUIRED)
  |
  +-- sync=true, actual=true, transaction T is active
  |
  +-- inner @Transactional(NOT_SUPPORTED)
  |      - suspend T and related synchronizations
  |      - sync=true, actual=false (under ALWAYS)
  |      - SQL here does not belong to transaction T
  |
  +-- inner completes
  +-- resume T and original synchronizations
  |
  +-- sync=true, actual=true
  +-- outer eventually commits or rolls back T
```

"NOT_SUPPORTED has no transaction" **does not mean** "synchronization is always false." This is precisely a case where distinguishing the two flags matters.

An `INSERT` executed inside `NOT_SUPPORTED` on an auto-commit connection can be committed **independently** of outer T. If outer rolls back later, the data already committed in the `NOT_SUPPORTED` region is **not automatically reverted**.

### 6.2. SUPPORTS Joining Outer

`SUPPORTS` means:

- A transaction already exists → **join** that transaction.
- No transaction exists yet → **do not create a new backend transaction**.

With `ALWAYS`, synchronization can still be active in the second case. Hence the `SUPPORTS` label by itself is insufficient to infer `actual=false` or `actual=true` without knowing the outer context.

### 6.3. REQUIRES_NEW

`REQUIRES_NEW` has an independent actual transaction within its scope, so inside its body it is normally `true/true`. This does **not** tell you whether outer has committed; outer may still be suspended and later roll back. Distinguish an active actual transaction from **overall atomicity across the entire business flow**.

## 7. Checking Flags at the Right Time and on the Right Thread

### 7.1. Do Not Check Before the Proxy Opens the Transaction

Consider a caller:

```java
System.out.println(
    TransactionSynchronizationManager.isActualTransactionActive()
);
orderService.placeOrder();
```

The `println` runs **before** the call passes through `placeOrder()`'s `@Transactional` proxy, so it can print `false` even though a real transaction exists inside `placeOrder()`.

To debug, log **inside** the method intercepted by Spring or inside the running `TransactionTemplate` callback.

### 7.2. Self-Invocation Can Prevent the Annotation from Applying

```java
@Service
public class ReportService {

    public void run() {
        this.supportsMethod(); // Does not go through the proxy in Spring AOP mode.
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void supportsMethod() {
        // Here, SUPPORTS synchronization is not automatically opened by the annotation
        // if the call is this.supportsMethod() and no other advice applies.
    }
}
```

This is **illustrative code**, requiring imports and a Spring environment. If you want to observe flags created by the annotation, call the method from **another bean through an injected proxy**. `TransactionTemplate` in the section 10 example operates via direct calls on the template, avoiding self-invocation confusion while learning the two flags.

### 7.3. @Async, ExecutorService, and Other Threads

Imperative Spring's `TransactionSynchronizationManager` is **thread-bound**. Creating a new thread does not automatically copy the transaction context:

```java
@Transactional
public void parent() {
    // Thread A: sync=true, actual=true

    executor.execute(() -> {
        // Thread B: does not automatically inherit Thread A's transaction.
        // Both flags may be false if B does not open its own Spring scope.
    });
}
```

Illustrative snippet; `executor` must be provided. If an asynchronous task must write data atomically, open a **separate transaction** on the worker thread via a Spring bean/proxy or appropriate template. Do not crudely copy `ThreadLocal`/resource holders across threads to "pass the transaction", because connections and cleanup require a clear owner.

### 7.4. Reactive TransactionSynchronizationManager Is a Different Type

For Reactor/R2DBC, Spring provides the class:

```java
org.springframework.transaction.reactive.TransactionSynchronizationManager
```

This is a different API from:

```java
org.springframework.transaction.support.TransactionSynchronizationManager
```

Reactive transactions attach to the **Reactor context**, not purely to an imperative `ThreadLocal`. Reading the two static flags of the `support` class inside a reactive pipeline **does not prove** whether an R2DBC transaction is active or inactive.

For reactive transactions, use `ReactiveTransactionManager`/`TransactionalOperator` and the corresponding reactive context management APIs. Do not use blocking `JdbcTemplate` or imperative `TransactionTemplate` and assume they automatically share a transaction context with R2DBC.

## 8. When Should Synchronization Callbacks Be Registered?

### 8.1. Technical Condition for Calling registerSynchronization

Infrastructure/service integration example:

```java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                // Clean up resources/record metrics upon scope completion.
            }
        });
}
```

This is an **illustrative snippet**, not a complete application. `isSynchronizationActive()` is the proper guard to avoid calling `registerSynchronization(...)` when synchronization is inactive. Calling it when false may cause Spring to throw `IllegalStateException`.

However, the callback is registered **for the synchronization scope**, and that scope could be an "empty" `SUPPORTS` or `NOT_SUPPORTED` **without a real DB transaction**. Therefore, choose callbacks consistent with the integration's semantics.

### 8.2. Condition for "A Real DB Transaction Exists"

If an integration specifically needs to avoid registering "after commit" onto an empty scope:

```java
boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
boolean actualTransactionActive =
    TransactionSynchronizationManager.isActualTransactionActive();

if (synchronizationActive && actualTransactionActive) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Example: signal to dispatch work after COMMIT.
                // Avoid performing additional SQL writes in the old transaction here.
            }
        });
}
```

This is a **conditional guard pattern**, not absolute proof that "every manager guarantees a DB COMMIT is pending." For managers extending `AbstractPlatformTransactionManager`, under `ALWAYS`/`ON_ACTUAL` policy, with a real transaction per the marker and no unusual configuration, this distinguishes an empty `SUPPORTS` case from a real transaction.

**Do not check only `actual=true`:** if synchronization is disabled (e.g., `SYNCHRONIZATION_NEVER`), `registerSynchronization` is still invalid. **Do not check only `sync=true`:** it may be an empty scope.

### 8.3. Why Must afterCommit Also Be Understood Correctly?

In `AbstractPlatformTransactionManager`, transaction synchronization callbacks belong to **transaction scope** completion logic. Under `SYNCHRONIZATION_ALWAYS`, an "empty" `SUPPORTS` scope has no backend transaction yet still has a callback lifecycle; depending on the callback/completion path, `afterCommit`/`afterCompletion` can fire when that scope ends "successfully," **with no corresponding physical JDBC COMMIT**.

Consequently, do not treat the execution of an `afterCommit` callback from an empty synchronization scope as proof that data committed to the DB. If you need to guarantee that **an outgoing event corresponds to a committed business record**, evaluate a transactional outbox or an after-commit mechanism bound to a real actual transaction rather than relying solely on the callback name.

### 8.4. afterCompletion Also Does Not Replace Business Rollback Status

`TransactionSynchronization.afterCompletion(int status)` can receive `STATUS_COMMITTED`, `STATUS_ROLLED_BACK`, or `STATUS_UNKNOWN` according to the transaction manager scope. On an empty scope, "completed" does not inherently mean database changes were confirmed or reverted. If you need to return a business outcome, use the service result or a transaction status with a clear contract rather than inferring it from a callback on a scope without a resource transaction.

## 9. Having a Bound Connection Does Not Guarantee a Backend Transaction

Spring JDBC uses `DataSourceUtils` together with `TransactionSynchronizationManager` to acquire and release connections appropriate for the thread.

Example call:

```java
jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM orders",
    Long.class
);
```

When a real transaction exists, `JdbcTemplate` can use the connection already bound to the transaction; the SQL participates in the same commit/rollback scope.

However, under `PROPAGATION_SUPPORTS` **without an actual transaction** and with `SYNCHRONIZATION_ALWAYS`, Spring can still temporarily hold/bind a connection within the synchronization scope for reuse and cleanup. When the connection still has `autoCommit=true` (such as H2's default in the demo), writes are **committed statement by statement** rather than waiting for a physical transaction from the template.

That is why:

- `hasResource(dataSource)` can be `true` while `isActualTransactionActive()` remains `false`;
- `isSynchronizationActive()` does not imply the connection has `autoCommit=false`;
- observing a bound connection or receiving a completion callback **does not prove** that a DB transaction committed/rolled back together with the service.

### 9.1. Do Not Use hasResource as "In Transaction?"

`hasResource(dataSource)` only indicates that Spring has bound a resource under the `dataSource` key on the thread. Whether that resource has a real transaction or is merely managed within a synchronization scope depends on the manager and execution path. If you need to verify DB commit/rollback, test the **data state after the scope finishes**.

### 9.2. Need One Transaction for Multiple SQL Statements to Be Atomic?

Choose `REQUIRED` propagation/a real transaction with the same manager/resource:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void placeOrder() {
    // INSERT order
    // UPDATE inventory
    // INSERT ledger
}
```

Or use `TransactionTemplate` with `PROPAGATION_REQUIRED`. `SUPPORTS` without an outer transaction **does not guarantee multi-statement atomicity**; one SQL statement may already have auto-committed before an exception occurs on the next SQL statement.

## 10. Runnable Java 17 Project: Observing Flags and Verifying Commit/Rollback

The project below uses **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2**. Spring Boot 3.3.x manages the Spring Framework 6.1.x line, which suits imperative infrastructure examples. The goal is to observe the flags **from inside** `TransactionTemplate`, without needing an AOP proxy for the demo.

Three points to prove:

1. `SUPPORTS` without outer: synchronization active, actual transaction inactive.
2. `REQUIRED` has an actual transaction; `NOT_SUPPORTED` suspends it and typically still has empty synchronization.
3. An INSERT inside an empty `SUPPORTS` (H2 auto-commit connection) **is not rolled back by an exception in the empty scope**, whereas an INSERT inside `REQUIRED` is rolled back when the callback throws an exception.

Versions are pinned for reproducibility, **with no claim that these are the latest releases**.

### 10.1. File Structure

```text
transaction-flags-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/
    ├── java/demo/flags/
    │   ├── FlagsApplication.java
    │   └── TxManagerConfig.java
    └── resources/
        └── application.yml
```

You can generate the Gradle Wrapper via Spring Initializr. The code below is a **multi-file project**, not a single-file program runnable with `javac` lacking dependencies.

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-flags-lab'
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
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:flagsdemo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
```

In-memory H2 lives inside the running JVM; each time a new process starts, the database is empty. `DB_CLOSE_DELAY=-1` only keeps the database alive until the JVM exits. The demo explicitly creates the table when the runner starts rather than using `schema.sql`.

### 10.2. Configuring the Manager with SYNCHRONIZATION_ALWAYS

**`src/main/java/demo/flags/TxManagerConfig.java`**

```java
package demo.flags;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;

@Configuration
public class TxManagerConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        manager.setTransactionSynchronization(
            AbstractPlatformTransactionManager
                .SYNCHRONIZATION_ALWAYS);

        return manager;
    }
}
```

Explanation:

- `JdbcTransactionManager` manages JDBC transactions for the exact same `DataSource` used by `JdbcTemplate`.
- `SYNCHRONIZATION_ALWAYS` is the default in the base class; declaring it explicitly ensures the learner **does not rely on assumptions**.
- Spring Boot normally does not auto-create another JDBC transaction manager when an application-provided transaction manager bean is already present.
- The demo uses only one manager and one DataSource, avoiding ambiguity in multi-resource projects.
- Do not use the setter `setActualTransactionActive(true)` to "turn on" a transaction: that must be the transaction manager's job.

### 10.3. Runner: outside, SUPPORTS, REQUIRED, NOT_SUPPORTED, and Join

**`src/main/java/demo/flags/FlagsApplication.java`**

```java
package demo.flags;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class FlagsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlagsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {

        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_flags_lab (" +
                "id INTEGER PRIMARY KEY, " +
                "note VARCHAR(30) NOT NULL)"
            );

            TransactionTemplate required =
                new TransactionTemplate(manager);

            TransactionTemplate supports =
                new TransactionTemplate(manager);
            supports.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_SUPPORTS);

            TransactionTemplate notSupported =
                new TransactionTemplate(manager);
            notSupported.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_NOT_SUPPORTED);

            System.out.println("outside: " + flags());

            try {
                supports.executeWithoutResult(status -> {
                    System.out.println(
                        "SUPPORTS no outer: " + flags());

                    // H2 connection autoCommit=true, no backend tx.
                    jdbc.update(
                        "INSERT INTO tx_flags_lab(id, note) " +
                        "VALUES (1, 'auto-committed')");

                    throw new IllegalStateException(
                        "empty scope failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caught SUPPORTS failure: " + ex.getMessage());
            }

            System.out.println(
                "rows after SUPPORTS error: " + count(jdbc));

            try {
                required.executeWithoutResult(status -> {
                    System.out.println(
                        "REQUIRED outer: " + flags());

                    jdbc.update(
                        "INSERT INTO tx_flags_lab(id, note) " +
                        "VALUES (2, 'rollback-me')");

                    notSupported.executeWithoutResult(inner -> {
                        System.out.println(
                            "NOT_SUPPORTED suspended: " + flags());
                    });

                    System.out.println(
                        "REQUIRED resumed: " + flags());

                    throw new IllegalStateException(
                        "outer transaction failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caught REQUIRED failure: " + ex.getMessage());
            }

            System.out.println(
                "rows after REQUIRED error: " + count(jdbc));

            required.executeWithoutResult(status -> {
                supports.executeWithoutResult(inner -> {
                    System.out.println(
                        "SUPPORTS joined outer: " + flags());
                });
            });

            System.out.println("after all: " + flags());
        };
    }

    private static String flags() {
        return "sync=" +
            TransactionSynchronizationManager.isSynchronizationActive()
            + ", actual=" +
            TransactionSynchronizationManager.isActualTransactionActive();
    }

    private static Long count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_flags_lab",
            Long.class);
    }
}
```

This is compilable Java 17 when assembled with the proper project/dependencies. Because callbacks are passed directly into `TransactionTemplate`, they do not rely on the `demo(...)` method having a `@Transactional` proxy. Even so, `JdbcTemplate` must still use the same DataSource as the manager.

### 10.4. Running and Expected stdout

In the directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Aside from Gradle/Spring Boot logs, the program prints **in exact order**:

```text
outside: sync=false, actual=false
SUPPORTS no outer: sync=true, actual=false
caught SUPPORTS failure: empty scope failed
rows after SUPPORTS error: 1
REQUIRED outer: sync=true, actual=true
NOT_SUPPORTED suspended: sync=true, actual=false
REQUIRED resumed: sync=true, actual=true
caught REQUIRED failure: outer transaction failed
rows after REQUIRED error: 1
SUPPORTS joined outer: sync=true, actual=true
after all: sync=false, actual=false
```

**Stage-by-stage explanation:**

1. The runner executes outside any Spring transaction → `false/false`.
2. `SUPPORTS` with no outer transaction creates an empty synchronization scope under `ALWAYS` → `true/false`. The INSERT for ID 1 is auto-committed by the H2 JDBC connection; the exception in the callback **has no physical transaction to roll back**, so after catching it, one row remains.
3. `REQUIRED` opens an actual transaction → `true/true`. The INSERT for ID 2 remains part of that transaction.
4. `NOT_SUPPORTED` suspends the outer transaction, opening a scope with no backend transaction yet with synchronization under `ALWAYS` → `true/false`.
5. When `NOT_SUPPORTED` completes, Spring restores the outer transaction → `true/true`.
6. Outer deliberately throws an unchecked exception. `TransactionTemplate` rolls back its JDBC transaction; ID 2 disappears, while ID 1 had already committed earlier, so the count remains 1.
7. `SUPPORTS` called **inside** a real `REQUIRED` joins the outer actual transaction → `true/true`.
8. After the scopes end, the manager cleans up thread-bound synchronization/metadata → `false/false`.

**Output assumptions:** assumes manager `SYNCHRONIZATION_ALWAYS`, H2 default auto-commit connections outside an actual transaction, no external test/actor transaction wrapping the runner, normal connection pool operation, and all files kept intact. If you change the manager policy, propagation, or database, you must re-evaluate the output.

### 10.5. The Crucial Difference Proven by the SQL Section

The exercise is not merely about printing booleans. Both blocks **throw `IllegalStateException`**, yet the data outcomes differ:

| Case | Flags inside callback | SQL before error | Result after error |
| --- | --- | --- | --- |
| `SUPPORTS` without outer, `ALWAYS` | `true/false` | INSERT ID 1 | **ID 1 still exists** |
| `REQUIRED` opening a real transaction | `true/true` | INSERT ID 2 | **ID 2 is rolled back** |

Therefore, logging `isSynchronizationActive()=true` alone and declaring "rollback protects the data" is a serious transaction-evaluation error.

## 11. Changing Synchronization Policy: Re-Testing the Flags

If you change only one line in `TxManagerConfig` to:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager
        .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

then the key expectations are:

- `SUPPORTS` **without** outer: `sync=false, actual=false` because synchronization is not opened for empty scopes.
- `NOT_SUPPORTED` when outer is suspended: `sync=false, actual=false` in the scope without a backend transaction.
- `REQUIRED` opening an actual transaction: `sync=true, actual=true`.
- `SUPPORTS` joining an outer with an actual transaction: typically `sync=true, actual=true`.

**The SQL rollback behavior does not magically turn transactional inside `SUPPORTS`** when synchronization for empty scopes is disabled. INSERT ID 1 can still auto-commit; the flag merely makes the difference clearer to see.

If changed to:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_NEVER);
```

synchronization is not opened even for actual transactions. Do not take the default demo's output and alter a few words to claim all managers yield the same flags: in particular, `isActualTransactionActive` is a thread-local marker whose initialization path ties to synchronization, so it can return `false` even when the manager still manages a physical transaction on that very thread. You need to **verify data rollback after failure** or check `TransactionStatus.hasTransaction()` with an appropriate manager/status to distinguish physical transactions.

**Do not alter the synchronization policy on a singleton manager serving real production requests.** If it needs to be changed, configure it at startup, evaluate integrations that rely on resource binding/callbacks, and run tests against the real manager/DB.

## 12. Using TransactionStatus When You Open the Scope Yourself

If code uses `TransactionTemplate`, the callback receives `TransactionStatus`. When asking "does the current scope have a backend transaction recognized by the manager?", the API is:

```java
TransactionTemplate template = new TransactionTemplate(manager);

template.executeWithoutResult(status -> {
    boolean actualScope = status.hasTransaction();
    boolean newScope = status.isNewTransaction();

    System.out.println("hasTransaction=" + actualScope);
    System.out.println("isNewTransaction=" + newScope);
});
```

`hasTransaction()` (present in modern Spring transaction execution APIs, e.g. Spring 6.1) expresses a contract based on **manager status** that is more direct than guessing from a thread's synchronization flag. `isNewTransaction()` has a different meaning: it indicates whether the scope is considered a new transaction, **not** "has an actual transaction" in every implementation. When joining an outer transaction, `hasTransaction()` can be true while `isNewTransaction()` is false.

Still, `TransactionStatus` is not a certificate of DB commit either: the callback is still running, and a transaction can be marked rollback-only or fail at commit time. To prove the business outcome, inspect state after transaction completion.

**Note:** the ownerless `SUPPORTS` example in section 10 can yield `status.hasTransaction()=false` even when `isSynchronizationActive()=true`. This accurately confirms the difference between a **synchronization scope** and a **resource transaction**.

## 13. Using @Transactional with Two Services to Observe Propagation

`TransactionTemplate` is convenient for demonstrating flags, and annotations use the same infrastructure. Example design with two beans:

```java
@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void outer() {
        inner.supports();
        inner.noTransaction();
    }
}

@Service
public class InnerService {

    @Transactional(propagation = Propagation.SUPPORTS)
    public void supports() {
        // When called by outer: typically sync=true, actual=true.
        // When caller has no tx: may be sync=true, actual=false.
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void noTransaction() {
        // Under ALWAYS, sync=true, actual=false if outer is suspended.
    }
}
```

This is **illustrative code**, requiring `@Service`, `@Transactional`, `Propagation` imports, manager configuration, and calls through Spring beans/proxies. Add flag logging inside the method bodies if you want to run verification. Do not drop these two illustrative classes into section 10's demo project and assume the runner will invoke them automatically.

If `outer()` is called via `this.outer()` from the same bean without going through the proxy, transaction advice may not run. In that case, logged flags will not reflect the propagation you thought was executing.

## 14. Why Should You Not Use These Two Booleans for Business Decisions?

### 14.1. "If sync is active, send an afterCommit event" Is Not Enough

A dangerous piece of logic:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    registerAfterCommitNotification();
} else {
    sendNotificationNow();
}
```

In an empty `SUPPORTS` scope under `ALWAYS`, the first branch will be chosen even though **no actual transaction exists**. If the code expects the notification to fire only after a DB commit, the contract is already broken. Even when both flags are `true`, the scope may be joining an outer transaction whose commit happens **after the current method**.

Prefer explicit design:

- Write an outbox record **inside the same actual DB transaction** as the business change.
- Have a publisher process the record after commit, with retries/idempotency.
- Or use transaction-bound events/synchronization properly registered to an actual transaction, with a clear policy for the **no-transaction** case.

### 14.2. "If actual=false, DB operations always autocommit" Is Also Not a Global Rule

`isActualTransactionActive=false` is **Spring's marker** on the current thread. A connection managed manually outside Spring can still have an open transaction; or a manager using `SYNCHRONIZATION_NEVER` prevents the marker from being exposed as usual. Therefore, do not write branching business logic based on the marker to toggle data checks.

### 14.3. "If actual=true, it will definitely commit" Is Also Wrong

An active actual transaction can:

- Be marked rollback-only by an inner scope.
- Hit a constraint violation, deadlock, connection error, or timeout.
- Be rolled back by the outer caller after the child method returns.
- Have an unknown commit outcome if a connection error occurs during completion.

The two booleans represent **point-in-time state**, not a prediction of the transaction's final outcome.

### 14.4. "readOnly=true means an actual transaction exists" Is Not Necessarily True

`TransactionSynchronizationManager.isCurrentTransactionReadOnly()` is metadata of the current scope exposed by Spring. In an empty `SUPPORTS` scope declared read-only, it can still be `true` while `actual=false`; furthermore, read-only metadata **does not guarantee** the database rejects all write SQL statements.

To confirm a resource transaction, do not substitute `isCurrentTransactionReadOnly` or `getCurrentTransactionIsolationLevel() != null` for `isActualTransactionActive`.

## 15. Checklist When Debugging "Transaction Did Not Roll Back"

When SQL still commits even though logs show `sync=true`:

1. **Read both flags**: `sync=?`, `actual=?` **inside** the method/callback of the exact scope.
2. **Verify propagation**: is it `SUPPORTS`/`NOT_SUPPORTED`/`NEVER`? Did a real outer transaction exist when the method started?
3. **Verify synchronization policy**: is the manager using `ALWAYS`, `ON_ACTUAL`, or `NEVER`?
4. **Verify transaction manager bean**: does the right manager manage the DataSource/EntityManager used by the DAO?
5. **Verify proxy boundary**: was the `@Transactional` method called via a Spring proxy, or was it self-invocation/`new Service()`?
6. **Verify thread**: is the DB code running on the same imperative transaction thread? Is `@Async`/`ExecutorService` involved?
7. **Verify connection**: does JDBC use `JdbcTemplate`/`DataSourceUtils` on the right DataSource? Is there a separate non-Spring connection?
8. **Verify exception**: runtime or checked? Was it caught and swallowed inside the method? Does the transaction have appropriate rollback rules?
9. **Verify transaction owner**: is the scope joining an outer transaction or opening its own? Is outer marked rollback-only?
10. **Read data after completion**: do not infer from SQL logs or a marker being true before commit.
11. **Check driver/DB**: autoCommit, isolation, pool behavior, constraints, and commit errors.
12. **Reactive or imperative?** If reactive, use the proper reactive transaction context API.

### Minimal Test Scenarios

| Scenario | Sync / Actual (ALWAYS) | What to Verify |
| --- | --- | --- |
| Outside all scopes | false/false | No leaked thread-local callbacks/resources remain |
| SUPPORTS without outer | **true/false** | JDBC write may autocommit; exception does not roll back DB |
| REQUIRED opening new | true/true | Runtime exception rolls back DB changes in scope |
| SUPPORTS inside REQUIRED | true/true | Joins owner; does not commit independently |
| NOT_SUPPORTED inside REQUIRED | **true/false** | Outer suspends/resumes; SQL in no-tx region falls outside outer's rollback |
| REQUIRED after NOT_SUPPORTED | true/true | Outer state is restored |
| ON_ACTUAL + SUPPORTS without outer | false/false | No empty synchronization remains |
| NEVER + REQUIRED | May be false/false per thread marker | DB transaction may still work; check `status.hasTransaction()` and actual commit/rollback |

**Do not try to "fix" boolean values just to make a test pass.** Fix the transaction boundary, transaction manager, propagation, or resource routing, then verify against a real DB.

## 16. Self-Check Questions

**1. Is `isSynchronizationActive()=true` enough to conclude that a JDBC INSERT is protected by transaction rollback?**

No. `SUPPORTS` without an outer transaction under `SYNCHRONIZATION_ALWAYS` can produce `true/false`, and an INSERT on an auto-commit connection will still be persisted when code throws an error afterward.

**2. Does `isActualTransactionActive()=true` mean the current method will commit itself when it returns?**

No. The method may be joining an outer transaction, or the transaction may roll back or fail to commit. The marker only indicates that Spring has marked the thread as having an actual transaction at the time of inspection.

**3. Can you call `registerSynchronization` when `actual=true` but `synchronization=false`?**

No. The direct technical prerequisite is that synchronization **is active**. To register a callback for an actual transaction, check both flags under the standard manager model and understand the scope.

**4. Why does `@Transactional(SUPPORTS)` sometimes yield `actual=true` and sometimes `false`?**

Because `SUPPORTS` **joins an existing transaction if present**, whereas when there is no outer transaction it does not open a new backend transaction.

**5. Does `NOT_SUPPORTED` inside an outer `REQUIRED` necessarily produce `synchronization=false`?**

No. Under `SYNCHRONIZATION_ALWAYS`, it can create an empty synchronization scope so `sync=true, actual=false` while outer is suspended.

**6. How does switching the mode to `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` affect behavior?**

It does not activate synchronization for empty scopes. `SUPPORTS` without outer typically becomes `false/false`; a real `REQUIRED` typically remains `true/true`.

**7. If the manager is set to `SYNCHRONIZATION_NEVER`, can `actual=false` be used to assert there is no JDBC transaction?**

No. Marker visibility depends on the manager's synchronization initialization path; a backend transaction may still be active even though neither flag shows it.

**8. Do the two flags work the same way inside a reactive R2DBC transaction?**

Do not use the two imperative static flags to infer reactive transactions; the reactive context must be read using the proper reactive API.

**9. Is a connection bound at `getResource(dataSource)` guaranteed to have `autoCommit=false`?**

No. Spring can bind/reuse a connection solely within a synchronization scope when no real backend transaction exists.

**10. If you want all SQL in a service to roll back together, what should you configure?**

Use an actual transaction managed by the right `PlatformTransactionManager`, such as `@Transactional(REQUIRED)` via a proxy or `TransactionTemplate` with `REQUIRED`. Ensure DAOs use the shared resource, exception/rollback rules are right, and test after completion.

## 17. Conclusion

**`isSynchronizationActive()` and `isActualTransactionActive()` are not synonymous.**

- `isSynchronizationActive()`: **is Spring's synchronization/callback mechanism open on the thread?**
- `isActualTransactionActive()`: **is Spring currently marking the thread as associated with an actual resource transaction?**

In the commonly used `SYNCHRONIZATION_ALWAYS` configuration, an ownerless `SUPPORTS` or `NOT_SUPPORTED` can yield **sync=true, actual=false**. That is a valid state. Conversely, when synchronization is disabled, markers may not be exposed the way you expect even though the underlying transaction manager is still managing a backend transaction.

To apply this properly: choose clear transaction boundaries and propagation, use a manager aligned with the DataSource/JPA resource, call through proxies when using `@Transactional`, avoid inferring rollback/commit solely from the two booleans, and **verify data after the transaction ends**. For reactive applications, use Reactor's transaction context instead of the imperative `ThreadLocal`.

## Official Documentation

- Spring Framework 6.1 — `TransactionSynchronizationManager` Javadoc, `isSynchronizationActive` and `isActualTransactionActive`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework 6.1 — `AbstractPlatformTransactionManager` and the `SYNCHRONIZATION_ALWAYS` / `ON_ACTUAL_TRANSACTION` / `NEVER` modes: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework 6.1 — `TransactionStatus`, `hasTransaction`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Programmatic Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — *TransactionSynchronization* lifecycle: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `DataSourceUtils` and thread-bound JDBC connections: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Reactive `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronizationManager.html
- Spring Framework source — `AbstractPlatformTransactionManager`, `prepareSynchronization` and `handleExistingTransaction` branches: https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java
