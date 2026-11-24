# Local and Global Rollback-Only State in Spring Transaction Management

> **Spring Framework — Transaction Management → Transaction Scope.** Why does an outer method that never called `setRollbackOnly()`, and even caught every exception from an inner method, still fail to commit in the end? The answer lies in the difference between **local rollback-only on the `TransactionStatus` of a logical transaction scope** and **global rollback-only on the physical transaction shared by multiple scopes**.

## 1. Core summary

Spring distinguishes two important layers of state:

- **Local rollback-only**: a flag attached to **a single `TransactionStatus` object** for the current transaction boundary. With `AbstractTransactionStatus`, when the application calls `status.setRollbackOnly()`, `status.isLocalRollbackOnly()` returns `true`.
- **Global rollback-only**: the state where the **underlying physical/resource transaction** has been marked rollback-only. `DefaultTransactionStatus` can read this state through the transaction object, typically a `SmartTransactionObject` and its resource holders/coordinator.
- **Effective rollback-only**: `TransactionStatus.isRollbackOnly()` on `AbstractTransactionStatus` evaluates to `true` if **either local or global** is true.

A mnemonic formula for the common status implementation:

```text
effectiveRollbackOnly = localRollbackOnly || globalRollbackOnly
```

**Do not conflate the three flags.** The following state can exist:

```text
outer.localRollbackOnly  = false
outer.globalRollbackOnly = true
outer.isRollbackOnly()    = true
```

That means **outer did not proactively request a rollback**, yet the physical transaction it coordinates was marked rollback-only by an inner scope, transaction coordinator, or resource. When outer tries to commit, Spring typically has to roll back and report `UnexpectedRollbackException` to the caller.

> **Explanation scope:** The `isLocalRollbackOnly()` / `isGlobalRollbackOnly()` APIs below belong to the `AbstractTransactionStatus`/`DefaultTransactionStatus` implementation classes, not mandatory methods on every `TransactionStatus` implementation. Most examples use imperative `PlatformTransactionManager` and `PROPAGATION_REQUIRED`; reactive transactions have a different context mechanism.

## 2. Foundation: a logical scope is not a physical transaction

A `@Transactional` method intercepted by Spring creates a **logical transaction scope**. That does not mean there is always a new physical transaction. With `Propagation.REQUIRED` (the default), Spring **joins** an existing transaction if the resource/manager permits; only if none exists does it create a new physical transaction.

```text
Client
  |
  +-- OrderService.outer() @Transactional(REQUIRED)
  |        |
  |        +-- logical scope OUTER: TransactionStatus A
  |        |       local flag A
  |        |
  |        +-- AuditService.inner() @Transactional(REQUIRED)
  |                |
  |                +-- logical scope INNER: TransactionStatus B
  |                        local flag B
  |
  +-------------------------+
                            |
                            v
               ONE PHYSICAL TRANSACTION T1
                 global rollback-only state
                 JDBC Connection / JPA resource
```

When inner is `REQUIRED` and uses the same manager/datasource, the two logical scopes A and B can point to the same T1. Each scope has the right to request rollback according to its own rules, yet **physical commit for T1 cannot happen if T1 has already been marked rollback-only**.

Do not interpret "local" here as a single-database local transaction (as opposed to a distributed transaction). In this topic, **local = flag on one `TransactionStatus`/logical scope**, and **global = flag on the shared underlying transaction**. A `JdbcTransactionManager` coordinating one JDBC datasource still has both local and global rollback-only concepts. "Global" here **does not necessarily** refer to XA/JTA or multiple databases.

### Two types of state at different layers

| Question | Flag/object that answers | Meaning |
| --- | --- | --- |
| Did the current scope **itself** request rollback? | `AbstractTransactionStatus.isLocalRollbackOnly()` | Only the local flag on the current `TransactionStatus`. |
| Has the underlying transaction been marked uncommittable? | `DefaultTransactionStatus.isGlobalRollbackOnly()` | Checks rollback-only of the corresponding transaction object if supported. |
| Is there any rollback-only signal **regardless of source**? | `TransactionStatus.isRollbackOnly()` | Combined state; typically local OR global. |
| Did the scope start a new physical transaction? | `TransactionStatus.isNewTransaction()` | `true` if the manager considers the scope's transaction new. |
| Is the scope holding a savepoint? | `TransactionStatus.hasSavepoint()` | Can relate to `NESTED`, not a global rollback-only signal. |
| Has the transaction scope completed? | `TransactionStatus.isCompleted()` | Scope has committed or rolled back; does not tell the commit outcome of another transaction. |

`isNewTransaction() == false` **does not mean "no transaction"**. It can be a `REQUIRED` scope participating in an outer transaction. On Spring versions supporting `TransactionExecution`, `TransactionStatus.hasTransaction()` can distinguish whether an actual transaction exists, and can be compared with `TransactionSynchronizationManager.isActualTransactionActive()` where appropriate.

## 3. How Spring stores the two flags

### 3.1. Local flag on `AbstractTransactionStatus`

`AbstractTransactionStatus` implements the basic operations:

```java
// Real method names; this snippet only illustrates calling the API.
org.springframework.transaction.TransactionStatus status =
        org.springframework.transaction.interceptor.TransactionAspectSupport
                .currentTransactionStatus();

status.setRollbackOnly();          // Set flag on the current scope.
boolean effective = status.isRollbackOnly();
```

The fragment above must run **inside a method managed by the Spring transaction aspect**; calling it outside such a method can throw `NoTransactionException`. In `AbstractTransactionStatus`, `setRollbackOnly()` sets the local flag. After that call, even if the underlying resource has not yet recorded the global flag, `isRollbackOnly()` is still true.

You can inspect the details on a matching implementation:

```java
var status =
        org.springframework.transaction.interceptor.TransactionAspectSupport
                .currentTransactionStatus();

if (status instanceof
        org.springframework.transaction.support.AbstractTransactionStatus s) {
    System.out.println("local=" + s.isLocalRollbackOnly());
    System.out.println("global=" + s.isGlobalRollbackOnly());
    System.out.println("effective=" + s.isRollbackOnly());
}
```

This is a **diagnostic fragment**. The `instanceof` guard prevents treating an implementation detail as the public contract of every `TransactionStatus`.

### 3.2. Global flag on the underlying transaction

`DefaultTransactionStatus` checks global rollback-only via the underlying transaction object if that object implements `SmartTransactionObject`. With a JDBC transaction manager, the transaction object can reflect the state of `ConnectionHolder`. With a JTA coordinator, the marked-for-rollback state can come from the system's transaction manager; with JPA, the provider/resource can contribute to deciding whether the transaction can still commit.

This has two consequences:

1. A scope whose local flag is `false` can still see a global flag of `true` if **another scope** made the underlying transaction rollback-only.
2. Not every resource reports global rollback-only in the same way or at the exact same moment. Cases where a database transaction is aborted due to an SQL error can cause commit to fail even when the global flag diagnostic API has not yet fully reflected the database's condition.

Do not claim that `isGlobalRollbackOnly()==false` guarantees commit will succeed. Constraint violations, deadlocks, timeouts, network failures, or commit failures can still happen next.

### 3.3. Common truth table

| Local | Global | `isRollbackOnly()` | Meaning in the current scope |
| --- | --- | --- | --- |
| `false` | `false` | `false` | No rollback-only request seen yet; **not** a guarantee of commit. |
| `true` | `false` | `true` | This scope itself requested rollback, though the underlying transaction may not yet be marked global at the moment of observation. |
| `false` | `true` | `true` | The current scope did not request rollback itself; the shared transaction was already marked uncommittable. |
| `true` | `true` | `true` | Both the current scope and the shared transaction are rollback-only. |

This table is based on `AbstractTransactionStatus`'s contract; always inspect the manager/provider when diagnosing implementations outside this hierarchy.

## 4. Scenario A — Outer sets local rollback-only itself

A `@Transactional` method opens a new physical transaction and calls `setRollbackOnly()` on **its own** `TransactionStatus`:

```text
outer @Transactional REQUIRED
  |
  +-- begin physical T1
  +-- INSERT order
  +-- currentTransactionStatus().setRollbackOnly()
  |        outer.local = true
  |        outer.global may still be false at this moment
  +-- outer returns NORMALLY
  |
  +-- TransactionInterceptor calls manager.commit(outerStatus)
          |
          +-- manager sees local rollback-only
          +-- processes T1 rollback
          +-- normally does NOT throw UnexpectedRollbackException
              merely because outer marked local itself
```

`commit(...)` in the manager API is the normal completion path after a method returns; the manager still checks the status and switches to rollback. This is **not** "commit data and then roll it back", but rather the manager choosing to complete via rollback because it sees the local flag.

With `AbstractPlatformTransactionManager`, when **the scope that initiated the transaction marks rollback-only itself**, rollback is an outcome actively requested by that scope. The method's caller can receive a normal return value unless the rollback operation itself or other steps fail. Therefore:

**A method returning normally does not prove the transaction committed.**

Example fragment:

```java
@Transactional
public boolean reserve() {
    jdbcTemplate.update(
        "INSERT INTO reservations(id) VALUES (1)");
    TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
    return false;
}
```

It can return `false` normally while the insert is rolled back. In production design, there should be a clear business signal to the caller rather than letting the caller mistakenly think the data was written.

## 5. Scenario B — Inner `REQUIRED` sets local, outer sees global

This is the most important example of **local and global differing**.

Suppose there are two Spring beans, methods are called through Spring proxies, sharing the same `JdbcTransactionManager` and datasource:

```java
@Service
class InnerService {
    @Transactional // default REQUIRED
    public void validateAndWrite() {
        // Write some data.
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void placeOrder() {
        // Write other data.
        inner.validateAndWrite();
        // Method may keep running, seeing no exception here.
    }
}
```

This is a **fragment**: it requires imports, persistence logic, and a real Spring context. Main flow:

1. Outer starts physical transaction T1, with `TransactionStatus OUTER` and local flag false.
2. Inner `REQUIRED` is intercepted, joins T1, and gets its **own `TransactionStatus INNER`**, initially with local flag false.
3. Inner calls `currentTransactionStatus().setRollbackOnly()`. At that point, **inner.local=true**, while outer.local remains false.
4. Inner returns normally; the interceptor completes inner's logical scope. For a *participating* `REQUIRED` scope, inner's rollback-only request is propagated to the underlying transaction by marking **global rollback-only on T1**.
5. Outer continues executing: **outer.local=false yet outer.global=true**, so `outer.isRollbackOnly()==true`.
6. Outer returns normally; outer's interceptor/manager attempts to complete the transaction. T1 cannot commit. Under standard policy, Spring rolls back T1 and reports `UnexpectedRollbackException` to outer's caller.

Timeline:

```text
Time             OUTER local    INNER local    T1 global      Outcome
-----------      -----------    -----------    ---------      ------------------
New T1           false          (none yet)     false          Can commit
Enter inner      false          false          false          Same T1
Inner sets flag  false          true           false (*)      Inner effective=true
Inner ends       false          (done)         true           T1 can only roll back
Outer continues  false          (done)         true           Outer effective=true
Outer commit     false          (done)         true           Rollback + UE
```

(*) The state immediately after inner's `setRollbackOnly()` call reflects the typical behavior of `DefaultTransactionStatus` and `JdbcTransactionManager`. Depending on the manager/provider, the underlying transaction may be marked at a different point; do not treat the exact timing of updating the internal flag as a general API contract.

**Subtle point:** this behavior happens even when inner **throws no exception**. `setRollbackOnly()` alone is enough to prevent outer from committing once the inner scope completes its participation in the transaction.

### Why does outer receive `UnexpectedRollbackException`?

From Spring's perspective, outer **did not proactively** decide to roll back in its own scope; it reached the commit boundary expecting to commit. Yet the physical transaction had already been marked rollback-only by another scope. If Spring returned silently as though commit succeeded, the caller could easily misread the outcome. `UnexpectedRollbackException` clearly reports the condition "the transaction was rolled back when the caller requested commit".

Typically that exception appears at the **outermost transaction boundary**, after `placeOrder()`'s body has finished. Thus a `try/catch` *inside the outer method body itself* cannot catch an `UnexpectedRollbackException` that is only generated **after the method returns** at the outer interceptor. To handle this outcome, the caller outside outer's proxy is the proper place to catch the exception.

## 6. Scenario C — Inner throws an exception and outer catches it

Not only manual `setRollbackOnly()` calls; `@Transactional`'s rollback rules can also cause the **inner interceptor to mark the shared transaction rollback-only**.

```java
@Service
class InnerService {
    @Transactional // REQUIRED
    public void charge() {
        throw new IllegalStateException("charge failed");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional // REQUIRED
    public void submit() {
        try {
            inner.charge();
        } catch (IllegalStateException ex) {
            // Catch inner's exception.
        }
        // Outer returns normally, yet T1 may already be global rollback-only.
    }
}
```

The classes above are illustrative only, not a standalone program. In a manager based on `AbstractPlatformTransactionManager` with the default `globalRollbackOnParticipationFailure=true`, an inner `REQUIRED` scope that fails and triggers rollback due to an unchecked exception causes T1 to be **marked global rollback-only**. Outer catching the exception **does not clear** that state.

Timeline:

```text
outer T1: INSERT A
   |
   +-- inner REQUIRED: INSERT B
   |       |
   |       +-- throw RuntimeException
   |       +-- TransactionInterceptor applies rollback rule
   |       +-- participating rollback => mark T1 global rollback-only
   |
   +-- outer catch RuntimeException
   +-- outer continues or returns
   |
   +-- manager attempts to commit T1
           |
           +-- rollback T1 (A and B)
           +-- UnexpectedRollbackException at outer boundary
```

Changing `globalRollbackOnParticipationFailure=false` can alter **how the manager handles participating rollback from an exception**, but it does not automatically make the system safe: the provider/DB might not be able to continue after a data-access failure. In particular, it **does not** nullify a manual `setRollbackOnly()` request by inner; see section 9.

### When the exception is caught before leaving inner

Suppose inner catches a `RuntimeException` itself, returns normally, and does **not** call `setRollbackOnly()`. In that case inner's transaction interceptor sees no escaping exception, so it cannot apply a rollback rule based on the swallowed exception. If the resource has not already turned rollback-only on its own, the transaction can commit.

Therefore the question is not simply "did an exception occur somewhere?" but rather:

- Did the exception **escape the intercepted scope**?
- What do that scope's rollback rules dictate?
- Did the code call `setRollbackOnly()`?
- Did the underlying resource already mark rollback-only itself?

## 7. `TransactionStatus`, `TransactionAspectSupport`, and diagnostic APIs

### 7.1. Reading the current scope's status

Inside an imperative `@Transactional` method passing through Spring transaction advice:

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

status.setRollbackOnly();
System.out.println(status.isRollbackOnly());
```

This fragment must not be placed directly in a class body; it is code inside a method. The `currentTransactionStatus()` API returns the **status of the locally declared transaction boundary**, not a single thread-wide singleton status. While the inner method runs, it sees **inner's** status; after inner completes and execution returns to outer, the same call sees **outer's** status.

If called from code without a suitable TransactionAspectSupport-managed scope, it can throw `NoTransactionException`. Do not use this method as a global transaction lookup API from arbitrary threads or background tasks.

### 7.2. Reading local/global separately if the implementation supports it

Standard `TransactionStatus` exposes `isRollbackOnly()`, while `isLocalRollbackOnly()` and `isGlobalRollbackOnly()` are not required on the interface. In `DefaultTransactionStatus` cases:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

if (status instanceof AbstractTransactionStatus s) {
    boolean local = s.isLocalRollbackOnly();
    boolean global = s.isGlobalRollbackOnly();
    boolean effective = s.isRollbackOnly();

    System.out.printf(
        "local=%s, global=%s, effective=%s%n",
        local, global, effective
    );
}
```

The fragment requires imports for `org.springframework.transaction.TransactionStatus`, `org.springframework.transaction.interceptor.TransactionAspectSupport`, and `org.springframework.transaction.support.AbstractTransactionStatus`. When writing code portable across transaction managers/implementations, prefer `TransactionStatus.isRollbackOnly()`; treat the two detailed flags as diagnostic info.

### 7.3. `TransactionSynchronizationManager` does not replace `TransactionStatus`

`TransactionSynchronizationManager.isActualTransactionActive()` tells whether Spring considers an **actual imperative transaction** active on the current thread. It **does not** directly indicate whether that transaction can still commit or is already rollback-only.

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

The fragment requires importing `org.springframework.transaction.support.TransactionSynchronizationManager`. `readOnly` and `isolation` are transaction characteristics, **not** rollback-only flags. The situation `active=true` and `globalRollbackOnly=true` is completely possible: the transaction is still scope-active yet no longer committable.

### 7.4. Thread-local vs. reactive context

The examples show `TransactionAspectSupport.currentTransactionStatus()` on the **imperative** path. With reactive transactions (`ReactiveTransactionManager`), the transaction context is attached to the Reactor `Context`/subscription, not necessarily the same thread-local model. Do not copy thread-bound diagnostic calls into a reactive pipeline and interpret them as global R2DBC state. When switching to a new thread or `@Async`, the imperative transaction context does not automatically carry over either.

## 8. How does Spring decide rollback/commit at a boundary?

The following describes the **conceptual logic** of an `AbstractPlatformTransactionManager`; it is not complete Spring source code:

```text
complete(status):

  if status has localRollbackOnly:
      process rollback for this scope
      (if new transaction => roll back physical transaction)
      (if participating REQUIRED => mark global rollback-only)
      (if NESTED/savepoint => can roll back to savepoint)

  else if underlying transaction already has globalRollbackOnly:
      cannot confirm normal physical commit
      roll back / report unexpected situation per manager semantics

  else:
      execute appropriate commit/completion path

  clean up status, resources, synchronizations
```

Saying "local=true => rollback" does not mean every case throws an exception. When the **outer scope calls `setRollbackOnly()` itself**, rolling back is a decision requested by that scope. When **outer has local=false but global=true**, rolling back when outer requests commit is unexpected and normally produces `UnexpectedRollbackException`.

**Implementation exceptions:** `JtaTransactionManager` and certain managers have their own coordination semantics, including how a coordinator handles a commit request when global rollback-only is set. Do not turn pseudocode into an exact algorithm for every manager.

### Why can calling `manager.commit(status)` still roll back?

The API name `commit(TransactionStatus)` expresses a request to **complete the transaction via the commit path if permitted**. The manager checks rollback-only and can switch to rollback. Even without rollback-only, commit can still fail due to a database error. Therefore, never log "committed" before the commit call actually succeeds.

### Distinguishing `isCompleted()` from rollback-only

`status.isCompleted()` only reports that the scope has finished. Both a scope completed by rollback and one completed by commit have completed=true. Conversely, an outer scope may not be completed yet while global rollback-only is already true; code in outer can keep executing until commit/rollback is called at the boundary.

## 9. Two manager configuration flags that are easily misunderstood

In managers extending `AbstractPlatformTransactionManager`, there are two directly related options. Neither option is an attribute of `@Transactional`; both are **transaction manager configurations**.

### 9.1. `globalRollbackOnParticipationFailure`

The default in `AbstractPlatformTransactionManager` is **`true`**.

- When a scope **participating** in an outer transaction (`REQUIRED`) fails and Spring invokes `rollback(participatingStatus)` per rollback rules, the manager typically marks the physical transaction **global rollback-only**.
- If set to `false`, the manager can let the scope that initiated the outer transaction decide rollback/commit itself after catching inner's exception.
- However, a resource that encountered an error may no longer genuinely be able to commit; a Hibernate/JPA session or database connection may already be considered tainted by the provider/driver.
- **Most importantly:** this option only governs *participating rollback handled by the manager after a failure*. A scope **directly calling `TransactionStatus.setRollbackOnly()`** must still result in the appropriate global rollback outcome when that scope completes; do not use this flag to "cancel" such an explicit request.

Configuration example (fragment in `@Configuration`):

```java
@Bean
JdbcTransactionManager transactionManager(DataSource ds) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(ds);
    manager.setGlobalRollbackOnParticipationFailure(true);
    return manager;
}
```

The default is already true; this snippet mainly clarifies how to set the option and does not need to be added when there are no special requirements.

**Turning this flag off just to make `UnexpectedRollbackException` disappear is not recommended.** When data requires atomicity, handling errors at the right transaction boundary and letting the transaction roll back is the safer approach.

### 9.2. `failEarlyOnGlobalRollbackOnly`

The default is **`false`**.

- If a transaction has already become global rollback-only, Spring usually reports `UnexpectedRollbackException` only at the **outermost transaction boundary** when the caller still attempts to commit.
- When set to `true`, the manager can **report earlier** at an inner boundary when it detects global rollback-only.
- The flag changes **when the notification is raised**, not whether a rollback-only transaction becomes committable.

```java
@Bean
JdbcTransactionManager transactionManager(DataSource ds) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(ds);
    manager.setFailEarlyOnGlobalRollbackOnly(true);
    return manager;
}
```

This is an **illustrative configuration**, not something to enable just to "fix rollbacks". Exact early/late exception placement depends on the flow and manager; integration tests are needed if code catches errors layer by layer.

### 9.3. Comparison table

| Setting | Default | Primary effect | What it cannot do |
| --- | --- | --- | --- |
| `globalRollbackOnParticipationFailure` | `true` | Whether participating rollback after failure marks the shared transaction rollback-only | Cannot erase explicit `setRollbackOnly()` or repair a broken DB resource. |
| `failEarlyOnGlobalRollbackOnly` | `false` | Decides whether unexpected rollback is reported at the outermost boundary or potentially earlier | Cannot allow committing a global rollback-only transaction. |
| `validateExistingTransaction` | `false` commonly | Checks isolation/read-only mismatches when joining a transaction | Cannot clear rollback-only. |

## 10. Propagation comparison: when does inner's rollback-only affect outer?

| Inner propagation | Relationship to outer | If inner rolls back or sets rollback-only | Can outer still commit? |
| --- | --- | --- | --- |
| `REQUIRED` | Usually **same physical transaction** | Participating scope can make the shared transaction global rollback-only | Usually **cannot** commit once global rollback-only is set. |
| `REQUIRES_NEW` | **Independent** physical transaction; outer is suspended | Separate inner transaction rolls back | Outer **can** commit if inner's exception is handled properly and outer is not marked rollback-only. |
| `NESTED` with savepoint | **One physical transaction**; inner gets a savepoint | Can roll back operations after the savepoint without poisoning the whole transaction | Outer can continue, if supported by resource/manager and transaction is not global rollback-only for another reason. |
| `SUPPORTS` | Joins if present; if absent there may be no actual transaction | Depends on current transaction and manager state | Do not infer a physical transaction exists from the annotation alone. |
| `NOT_SUPPORTED` | Suspends outer transaction | Operations do not automatically belong to outer's transaction | There is no local inner transaction to roll back the way `REQUIRED` does. |

**`REQUIRES_NEW` is not a nested savepoint.** It requires its own transaction/connection, and an inner commit can survive even if outer rolls back. `NESTED` usually relies on JDBC savepoints: rolling back the inner portion can preserve outer, though support is not guaranteed across every JPA provider or transaction manager.

### `NESTED` and the statement "explicit setRollbackOnly always marks global"

This must be phrased accurately: with **participating `REQUIRED`**, explicit `setRollbackOnly()` in inner makes the shared transaction uncommittable when the inner scope completes. With **`NESTED` actually executed using a savepoint**, the manager can roll inner back to the savepoint instead of marking the entire physical transaction global rollback-only. Do not conflate the two propagation modes.

### When there is no actual transaction

With `SUPPORTS` finding no active transaction, a transaction interceptor may still create a scope/synchronization depending on configuration, yet there is no database physical transaction to roll back. Do not call `status.setRollbackOnly()` in a flow without an actual transaction and claim prior auto-committed SQL operations were undone.

## 11. Standalone Java 17+ example: measuring local, global, and effective flags

This example uses Spring Framework **6.2.8**, Spring JDBC, in-memory H2, Maven, and JDK 17+. Three scenarios run sequentially on the same datasource, with **each call starting a new transaction**:

1. **Outer sets local flag itself:** local=true, global may still be false inside the method; when the method returns, the transaction rolls back **without an unexpected rollback exception**.
2. **Inner `REQUIRED` sets local flag itself:** inner.local=true; when inner finishes, outer.local=false yet outer.global=true; when outer tries to commit it receives `UnexpectedRollbackException`.
3. **Inner `REQUIRED` throws a runtime exception, outer catches it:** inner interceptor handles participating rollback, marking the shared transaction global rollback-only; outer still receives `UnexpectedRollbackException` when trying to commit.

All three scenarios write to the H2 table and then roll back; after each run, the remaining row count is 0.

### 11.1. Project structure

```text
rollback-only-flags-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RollbackOnlyFlagsDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>rollback-only-flags-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RollbackOnlyFlagsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 11.2. Code `src/main/java/dev/learning/RollbackOnlyFlagsDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.AbstractTransactionStatus;

public final class RollbackOnlyFlagsDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:rollback_flags;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        OuterService outerService(JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }
    }

    // Used only in the JDBC demo with DefaultTransactionStatus;
    // general application code should prefer status.isRollbackOnly().
    private static void show(String label) {
        TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

        if (!(status instanceof AbstractTransactionStatus details)) {
            throw new IllegalStateException(
                    "Expected AbstractTransactionStatus");
        }

        System.out.println(
                label
                + " local=" + details.isLocalRollbackOnly()
                + " global=" + details.isGlobalRollbackOnly()
                + " effective=" + details.isRollbackOnly()
                + " new=" + status.isNewTransaction());
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void markRollbackOnly() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    3, "inner marked");

            show("case2.inner.before");
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            show("case2.inner.after");
        }

        @Transactional
        public void failWithException() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    5, "inner threw");

            throw new IllegalStateException("inner failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void markOwnRollbackOnly() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    1, "outer local");

            show("case1.before");
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            show("case1.after");
        }

        @Transactional
        public void outerCallsInnerMark() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    2, "outer calling inner");

            show("case2.outer.before");
            inner.markRollbackOnly();
            show("case2.outer.after");
        }

        @Transactional
        public void outerCatchesInnerException() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    4, "outer catches");

            try {
                inner.failWithException();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "case3.innerCaught=" + expected.getMessage());
            }

            show("case3.outer.afterCatch");
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM events", Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE events (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            // Obtain the Spring bean proxy, do not manually new OuterService.
            OuterService outer = context.getBean(OuterService.class);

            // Case 1: root scope marks itself => intentional rollback.
            outer.markOwnRollbackOnly();
            System.out.println("case1.rows=" + count(jdbc));

            // Case 2: participating inner marks => global rollback-only.
            try {
                outer.outerCallsInnerMark();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "case2.exception="
                        + ex.getClass().getSimpleName());
            }
            System.out.println("case2.rows=" + count(jdbc));

            // Case 3: inner unchecked exception, caught by outer.
            try {
                outer.outerCatchesInnerException();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "case3.exception="
                        + ex.getClass().getSimpleName());
            }
            System.out.println("case3.rows=" + count(jdbc));
        }
    }
}
```

### 11.3. Compile and run

Requires JDK 17+ and Maven. In the `rollback-only-flags-demo` directory:

```bash
mvn -q clean compile exec:java
```

The first run requires Internet access to download dependencies. Lines **printed by the program itself**, excluding Maven messages or environment logs:

```text
case1.before local=false global=false effective=false new=true
case1.after local=true global=false effective=true new=true
case1.rows=0
case2.outer.before local=false global=false effective=false new=true
case2.inner.before local=false global=false effective=false new=false
case2.inner.after local=true global=false effective=true new=false
case2.outer.after local=false global=true effective=true new=true
case2.exception=UnexpectedRollbackException
case2.rows=0
case3.innerCaught=inner failed
case3.outer.afterCatch local=false global=true effective=true new=true
case3.exception=UnexpectedRollbackException
case3.rows=0
```

**Why does it produce these results?**

- **Case 1:** Outer creates a new transaction (`new=true`) and sets its own local flag. Before the method ends, the resource's global flag can still be false. When the method returns, the transaction manager sees the local flag and rolls back; the caller does not receive unexpected rollback merely from this self-requested rollback decision.
- **Case 2:** The inner `REQUIRED` method sees an active outer transaction, so `new=false`. When inner directly calls `setRollbackOnly()`, the local flag of **inner's status** becomes true. After the inner scope finishes, the transaction manager marks the shared JDBC transaction rollback-only; outer's status **does not turn local=true**, yet global=true. Outer commit is impossible, and the caller receives `UnexpectedRollbackException`.
- **Case 3:** Inner throws an unchecked exception. Inner's interceptor triggers a participating rollback under default rollback rules; the manager sets the global flag on the shared transaction. Outer catching the exception does not restore committability. When the outer method finishes, outer's interceptor detects global rollback-only and reports `UnexpectedRollbackException`.
- All three runs wrote data before rolling back, yet `SELECT COUNT(*)` after the transactions ended returned 0 in every case. The IDs are intentionally distinct to make rows easy to tell apart if you experiment with modifying the code.

**Verification note:** These are the expected results with the dependency versions and JDBC configuration above, deduced from Spring semantics. Internal Spring/driver logging may add extra lines depending on configuration. Run in an environment with JDK/Maven to verify empirically.

### 11.4. Small variations to experiment with

**Experiment A — Remove `setRollbackOnly()` in case 1.** When the method finishes normally with no other errors, row ID=1 commits; `case1.rows` becomes 1. This confirms the rollback in case 1 was caused by the local flag itself.

**Experiment B — Remove inner's `setRollbackOnly()` in case 2.** Both inserts in case 2 complete normally and commit together in outer's transaction. Both survive because `REQUIRED` shares the same physical transaction.

**Experiment C — Change inner to `REQUIRES_NEW`.** Inner gets its own physical transaction; if inner marks itself rollback-only, only that transaction rolls back. Outer can commit if all other conditions permit. Ensure the connection pool has extra connections when running concurrently; with a minimal H2 datasource, this is only a learning model.

**Experiment D — Enable `failEarlyOnGlobalRollbackOnly=true`.** Add another participating boundary after the global flag is marked and observe where the exception can arrive earlier. Simply toggling the flag does not guarantee an exception moves to a specific point if the flow lacks a subsequent boundary to detect it.

**Experiment E — Change `globalRollbackOnParticipationFailure=false` and run case 3.** When the resource remains healthy and there is no other cause of rollback-only, a participating exception rollback may not poison the entire transaction. However, case 2 using explicit `setRollbackOnly()` will not be "saved" by this flag. **Do not adopt an experiment as production config merely to swallow transaction errors.**

## 12. Common misconceptions

### 12.1. "Outer did not call `setRollbackOnly()`, so it can still commit"

False. `outer.local=false` does not mean `outer.global=false`. If inner made the shared transaction rollback-only or the resource marked itself rollback-only, outer cannot physically commit merely by keeping its local flag false.

### 12.2. "Catching the exception in outer clears global rollback-only"

False. Catching only controls Java control flow. It does not invoke any API to restore the transaction. A physical transaction already marked rollback-only has no general "undo setRollbackOnly" mechanism in Spring.

### 12.3. "`isActualTransactionActive()==true` means the transaction is still healthy"

False. A transaction can **still be active** in terms of scope and resource binding, yet already be global rollback-only. Checking active is not checking committable.

### 12.4. "`TransactionStatus.isRollbackOnly()` only returns the flag set by this method itself"

False for `AbstractTransactionStatus`: the effective flag combines local and global. If you need to know the **origin** of the flag in a supporting manager, inspect the two detailed flags on the appropriate implementation.

### 12.5. "Global rollback-only means there is a distributed transaction across multiple DBs"

False in this context. Even a single local JDBC connection with multiple `REQUIRED` logical scopes has a global rollback-only state on the shared physical transaction.

### 12.6. "Inner returned normally, so outer will never see an exception"

False. Inner can return normally after `setRollbackOnly()`; outer still receives `UnexpectedRollbackException` when the interceptor completes the transaction. This error can occur **after** the `return` line in outer's business method.

### 12.7. "`globalRollbackOnParticipationFailure=false` lets every transaction commit"

False. That flag only alters global marking for one kind of participating rollback; explicit local `setRollbackOnly`, database timeouts, transaction coordinators, and resource failures can still prevent commit.

### 12.8. "`NESTED` is the same as `REQUIRES_NEW`"

False. `NESTED` usually uses a savepoint on the **same physical transaction**; `REQUIRES_NEW` opens an independent physical transaction. Rollback/commit outcomes and connection costs differ.

### 12.9. "Calling `this.inner()` directly also creates an inner logical scope"

In default Spring proxy mode, **self-invocation** bypasses the proxy for the inner method, so inner's advice/transaction attributes are not applied on that call. If outer has a transaction, code inside inner can still run on outer's transaction; however, it does not create a separate inner `TransactionStatus`.

### 12.10. "Any exception always marks global rollback-only"

Incorrect. Rollback rules determine which exceptions require rollback; defaults roll back on `RuntimeException` and `Error`, while checked exceptions normally do not trigger rollback automatically. An exception caught **inside** the method before reaching the proxy may not trigger the rule. On the other hand, the database/provider can mark a transaction uncommittable itself after a resource error. These causes must be distinguished.

## 13. Testing reliably

A unit test that only verifies `setRollbackOnly()` was called does not prove data actually rolled back. Integration tests against a transaction manager and datasource are needed:

| Test | What to observe |
| --- | --- |
| Root outer sets local itself | Method can return normally, yet writes are rolled back. |
| Inner `REQUIRED` explicit `setRollbackOnly` | Inner local turns true; after inner ends outer sees global true and outer commit is rejected. |
| Inner `REQUIRED` throws unchecked, outer catches | Shared transaction does not commit; `UnexpectedRollbackException` can occur at outer boundary. |
| Inner `REQUIRES_NEW` rolls back | Outer can commit independently if not marked rollback-only and error is handled properly. |
| Inner `NESTED` rollback-to-savepoint | If supported by manager and driver, rolls back inner part while keeping outer part. |
| Inner checked exception without `rollbackFor` | Verify actual rule and resource state; do not assume global rollback-only always happens. |
| Self-invocation `this.inner()` | Inner's annotation does not create an intercepted scope like a cross-bean call. |
| Database constraint / timeout | Observe actual exception/physical rollback; do not trust status flags alone right before commit. |

### Note on Spring TestContext

A `@Transactional` test method may be rolled back by Spring TestContext at the end of the test. This can **mask** the difference between "the service rolled back on its own" and "the test framework rolled back after the test". For tests asserting service commit/rollback, deliberately design transaction boundaries and when data is queried, or use `TestTransaction` to control the test-managed transaction.

### Diagnostic logging

In a Spring Boot application, you can enable log levels in `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Depending on the Spring version, implementation, and logging backend, log output varies. Do not write integration tests that depend on a fixed log message. When debugging, combine logs with local/global state and an independent data read after the transaction.

## 14. Checklist for debugging rollback-only errors

1. **Identify the outermost boundary**: which method actually opens the physical transaction? Does the caller go through a Spring proxy?
2. **Identify inner scopes**: are `REQUIRED` methods participating in the same transaction manager and datasource?
3. **Check rollback rules**: which runtime/checked exceptions actually escape the interceptor? Are there `rollbackFor` / `noRollbackFor` rules?
4. **Look for explicit `setRollbackOnly()`**: is it called on outer or inner status? Is it placed along a handled error branch?
5. **Distinguish the two flags**: where appropriate for diagnostics, log `isLocalRollbackOnly`, `isGlobalRollbackOnly`, and `isRollbackOnly`.
6. **Check resource failures**: has the database itself entered an uncommittable state independently of Spring status flags?
7. **Inspect manager settings**: what values are set for `globalRollbackOnParticipationFailure` and `failEarlyOnGlobalRollbackOnly`?
8. **Account for propagation**: is there genuinely `REQUIRES_NEW`/`NESTED`, or just one shared `REQUIRED` transaction?
9. **Do not mask exceptions**: catch errors to respond cleanly to business callers, but never pretend a transaction committed.
10. **Test after the boundary**: read data after the transaction ends and verify actual commit/rollback.

## 15. Self-check questions

**Question 1.** Why is outer.local=false while outer.isRollbackOnly()=true?

*Answer:* Because the underlying transaction is already global rollback-only; in `AbstractTransactionStatus`, effective rollback-only is local OR global.

**Question 2.** Is calling `setRollbackOnly()` in inner `REQUIRED` the same as calling it in the outer scope?

*Answer:* Both can cause the physical transaction to roll back, yet **which status has local=true** and **how the caller receives `UnexpectedRollbackException`** differ. Inner sets local on its own scope; when the participating scope finishes, the manager can propagate that state to global. Outer trying to commit did not actively choose rollback, so it normally sees unexpected rollback.

**Question 3.** If outer catches an unchecked exception from inner, can it still commit?

*Answer:* Usually no with default `AbstractPlatformTransactionManager` and inner `REQUIRED` triggering participating rollback: the shared transaction's global flag is normally true. Catching the exception does not clear the flag. Other cases require checking manager flags and resources.

**Question 4.** Does `globalRollbackOnParticipationFailure=false` disable inner's explicit `setRollbackOnly()`?

*Answer:* No. That flag controls participating rollback after failure; explicit `setRollbackOnly()` still leads to the appropriate rollback outcome when the scope completes.

**Question 5.** If inner must roll back separately while outer still needs to commit, what solutions should be considered?

*Answer:* Consider `REQUIRES_NEW` for an independent physical transaction or `NESTED`/savepoint if supported by the manager and resource. The two options have different semantics; evaluate business requirements and connection/locking costs.

**Question 6.** Can you guarantee commit will succeed when local=false and global=false?

*Answer:* No. That is only the observable rollback-only state; commit can still fail due to database constraints, concurrent updates, timeouts, network, or driver errors.

**Question 7.** Why does `UnexpectedRollbackException` usually appear after outer's method body returns?

*Answer:* `TransactionInterceptor` completes the transaction **after** the business method call. If outer returns normally while the physical transaction is global rollback-only, the manager can roll back and throw the exception at the outer proxy boundary.

## 16. Conclusion

- **Local rollback-only** reflects a rollback request for *one logical transaction scope* via `TransactionStatus`.
- **Global rollback-only** reflects that the shared underlying transaction has been marked uncommittable. Do not confuse it with distributed/XA transactions.
- **Effective `isRollbackOnly()`** in `AbstractTransactionStatus` indicates whether local or global is true.
- **`REQUIRED` transaction participation** explains why inner local rollback-only can make outer global rollback-only even when outer never called `setRollbackOnly()`.
- **`UnexpectedRollbackException`** protects callers from mistakenly concluding outer committed when inner silently made the shared transaction rollback-only.
- **`REQUIRES_NEW` and `NESTED`** change rollback boundaries with different semantics; manager flags only alter handling or notification timing, without repairing a broken transaction.
- **Proper verification** requires distinguishing status state, interceptor/manager flow, and the actual data remaining after commit/rollback.

## Official references

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical scopes, physical transaction, rollback-only in `REQUIRED`, `REQUIRES_NEW`, and `NESTED`.
2. [Spring Framework 6.2 — `AbstractTransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractTransactionStatus.html): `setRollbackOnly`, `isLocalRollbackOnly`, `isGlobalRollbackOnly`, and `isRollbackOnly`.
3. [Spring Framework 6.2 — `DefaultTransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionStatus.html): reading global rollback-only from the transaction object.
4. [Spring Framework 6.2 — `SmartTransactionObject` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/SmartTransactionObject.html): resource/coordinator providing internal rollback-only marker.
5. [Spring Framework 6.2 — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `globalRollbackOnParticipationFailure`, `failEarlyOnGlobalRollbackOnly`, and handling of participating transactions.
6. [Spring Framework 6.2 — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html): `currentTransactionStatus()` and status of the locally declared boundary.
7. [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules and setting rollback-only programmatically.
8. [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): `TransactionStatus` and `PlatformTransactionManager`.
