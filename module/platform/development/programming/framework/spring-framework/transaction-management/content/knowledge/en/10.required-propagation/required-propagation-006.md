# Why Catching an Exception in the Outer Method Does Not Guarantee Commit

## 1. Direct Answer

In Spring, when two methods both use `@Transactional(propagation = Propagation.REQUIRED)` and the **outer** method calls the **inner** method through a Spring proxy, they typically create **two logical transaction scopes** while participating in **one physical transaction**.

If the inner method throws an exception matching a rollback rule, the **inner method's** transaction interceptor can mark the **shared physical transaction** as **rollback-only**. The outer method may `catch` that exception and return normally, yet **`catch` only handles Java control flow; it does not clear the rollback-only marker**. When the outer method's interceptor calls `commit`, the transaction manager detects that commit is no longer allowed and performs a rollback. The outside caller typically receives `UnexpectedRollbackException`.

```text
Caller
  |
  v
Outer proxy: @Transactional(REQUIRED)
  |  getTransaction(): creates physical transaction T
  |
  v
Outer method
  |  INSERT "outer"
  |
  +---> Inner proxy: @Transactional(REQUIRED)
  |       |  getTransaction(): joins T, does not create another physical transaction
  |       v
  |     Inner method
  |       |  INSERT "inner"
  |       |  throw IllegalStateException
  |       v
  |     Inner interceptor: rollback rule matches
  |       -> marks T rollback-only
  |       -> rethrows IllegalStateException
  |
  |  catch (IllegalStateException) -> Java exception handled
  |  INSERT "after"
  |  returns normally
  v
Outer interceptor: commit(T)
  |  T is rollback-only -> ROLLBACK all INSERTs of T
  |  throw UnexpectedRollbackException
  v
Caller receives exception, DB has no "outer", "inner", "after"
```

**Remember three points:** (1) `REQUIRED` joins an existing transaction; (2) rollback-only is transaction state, not an exception variable being caught; (3) **method body returning** does not mean **transaction committing**.

This covers the topic **REQUIRED → Why catching an exception in the outer method does not guarantee commit**. The goal of this lesson is to predict outcomes at the transaction boundary, understand when `UnexpectedRollbackException` occurs, and write integration tests that verify against real data rather than inferring from logs or `catch`.

The examples use Java 17+, Spring Boot 3.3.5/Spring Framework 6.1.x, Spring JDBC, H2, and JUnit 5. The explanation of `REQUIRED` applies to the imperative transaction model; differences for JPA/JTA, reactive transactions, databases, and manager configurations are noted where needed.

## 2. Two Layers of Scope: Logical Scope and Physical Transaction

### 2.1. What is a logical transaction scope?

Each method handled by the Spring transaction interceptor has a **logical transaction scope** corresponding to that transactional invocation. The scope carries `@Transactional` metadata, a `TransactionStatus`, and Spring-level rollback/commit decisions.

Example:

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        inner.inner();  // Another bean -> goes through inner's proxy.
    }
}

@Service
class InnerService {
    @Transactional
    public void inner() {
        // ...
    }
}
```

This snippet illustrates the structure; to compile standalone it needs Spring imports and the full bean/config setup in section 7. In default proxy mode, if the caller invokes `outer()` via its proxy and `inner` is an injected proxy, Spring creates an outer logical scope for `outer()` and an inner logical scope for `inner()`.

### 2.2. What is a physical transaction?

A **physical transaction** is the actual resource transaction: for example, a JDBC `Connection` with auto-commit disabled coordinated by the manager until commit/rollback. With the default `REQUIRED`:

- No existing transaction: creates a new physical transaction.
- Compatible existing transaction: joins that physical transaction.

```text
Logical scope A: Outer @Transactional(REQUIRED) ────────────────┐
  starts physical T                                             │
                                                                ├── T
Logical scope B: Inner @Transactional(REQUIRED) ────────┐      │
  joins same physical T; no independent COMMIT          ┘      │
                                                               │
Outer completion owns final physical COMMIT/ROLLBACK ────────────┘
```

Both scopes can have their own rollback rules, yet changes from both are saved or discarded together in T. Once T is marked rollback-only, the outer scope **cannot** make T commit merely by returning normally or catching an exception.

### 2.3. What does `TransactionStatus` tell us?

Inside a transactional method intercepted by Spring, the API:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
boolean createdByThisScope = status.isNewTransaction();
```

The value of `isNewTransaction()` is normally `true` in outer when it opens T, and `false` in inner `REQUIRED` when joining T. The snippet above is explanatory; it requires importing `TransactionStatus` and `TransactionAspectSupport` in an application. `TransactionStatus` is the logical status of the invocation; **it is not a "commit receipt"**.

| Call | Propagation | Does T exist before the call? | Physical transaction | Typical `isNewTransaction()` |
| --- | --- | --- | --- | --- |
| Caller → Outer | `REQUIRED` | No | Newly created T | `true` |
| Outer → Inner | `REQUIRED` | T exists | Joins same T | `false` |
| Caller → Inner directly | `REQUIRED` | No | A new T | `true` |
| Outer → Inner | `REQUIRES_NEW` | T exists | Suspends T, opens independent T2 | `true` for T2 |
| Outer → Inner | `NESTED` | T exists | Usually uses a savepoint within T (JDBC supported) | Does not create independent T2 |

Savepoint/suspend details depend on the transaction manager. `JpaTransactionManager` and `JtaTransactionManager` do not by default provide the same nested savepoint semantics as `DataSourceTransactionManager` for JDBC.

## 3. Complete Sequence of Events When Outer Catches Inner's Exception

Consider this common scenario:

```java
@Transactional // REQUIRED
public void outer() {
    repository.insert("outer");

    try {
        innerService.inner(); // Another bean, goes through proxy
    } catch (IllegalStateException ex) {
        log.warn("Handled error from inner step", ex);
    }

    repository.insert("after");
} // normal return at the Java level
```

And inner:

```java
@Transactional // REQUIRED
public void inner() {
    repository.insert("inner");
    throw new IllegalStateException("inner failed");
}
```

These two snippets are **illustrative**; the variables `repository`, `innerService`, and `log` must be supplied by the application, with a full example in section 7.

### Step 1 — caller enters through outer proxy

Spring's `TransactionInterceptor` looks up the `TransactionAttribute` for `outer()` and calls `PlatformTransactionManager.getTransaction(...)`. Because no transaction exists yet, the manager creates T and binds the connection/resource to the thread's transaction context under the imperative mechanism. The body of `outer()` is invoked with T active.

### Step 2 — outer writes data within T

`repository.insert("outer")` uses a resource participating in T, such as `JdbcTemplate` with the same `DataSource`. The statement may have executed and SQL queries **on T's own connection** can see the data, yet it has not committed. Reading from an independent connection before commit may not see the data depending on isolation level.

### Step 3 — outer calls inner through proxy

`innerService` is a Spring-injected bean. The call goes through inner's proxy. With `Propagation.REQUIRED`, the manager recognizes that T is active and returns a status for inner's logical scope, **without** opening physical transaction T2.

### Step 4 — inner throws a runtime exception

Inner writes `"inner"` and throws `IllegalStateException`. Under Spring's default rollback rules, a runtime exception requires rollback. The inner transaction interceptor is **where the exception is observed before outer catches it**. In a participating `REQUIRED` scope on a typical manager, `rollback(innerStatus)` does not roll back an independent transaction; it **marks T rollback-only**.

### Step 5 — the exception is propagated into outer's body

The inner interceptor forwards `IllegalStateException` to the caller in the outer method. Outer's `catch` handles the Java exception. Java continues executing code after the `catch` block (such as `insert("after")`). However, the rollback-only marker on T remains.

### Step 6 — outer method returns

At the business-code level, `outer()` can return without any remaining exception. That only indicates **the method body ended normally**. The outer transaction interceptor still has to complete its status via the transaction manager.

### Step 7 — outer commit is rejected

Outer's interceptor attempts `commit(outerStatus)`. The manager checks T and sees it is **globally rollback-only**, so it executes rollback instead of a physical commit. Spring throws `UnexpectedRollbackException` so the caller is not given a false success signal.

### Step 8 — caller receives the exception after the method body has returned

The origin of `UnexpectedRollbackException` is normally at the **outermost transaction boundary**, meaning after `outer()` has exited its method body and is inside AOP completion logic. Therefore, a `catch` block **inside the outer method** usually cannot catch this exception itself. Only the caller invoking **through the proxy** observes it.

**Note:** This is the outcome under standard `DataSourceTransactionManager`/`JdbcTransactionManager` configuration and default rollback rules. Options such as `setGlobalRollbackOnParticipationFailure`, `setFailEarlyOnGlobalRollbackOnly`, savepoints, or other managers can alter how rollback-only is marked or when errors are reported. Do not apply this model mechanically to every transaction implementation.

## 4. Why Doesn't `catch` Clear Rollback-Only?

### 4.1. `catch` and the transaction manager store two different kinds of state

```text
Timeline                                      Java State        State of T
--------------------------------------------------------------------------------
Inner throws IllegalStateException            exception         still active
Inner interceptor processes rollback rule     exception         rollback-only
Outer catches IllegalStateException           normal            rollback-only
Outer returns                                 normal            rollback-only
Manager attempts commit                       normal            rollback-only
Manager rolls back + throws UnexpectedRollback new exception    finished
```

Java's `catch` only consumes the exception object and redirects control flow; Spring has no default rule saying "once an exception is caught, the transaction recovers to a committable state".

Marking rollback-only is a **decision already executed by the transaction infrastructure**. It can be triggered by an inner interceptor, `TransactionStatus.setRollbackOnly()`, the ORM, the driver, or the transaction coordinator. "Clearing" such a mark is generally unsupported by transaction managers; trying to continue writing can leave the transaction invalid or cause errors to surface later.

### 4.2. **Where** the exception is caught matters

Compare two cases:

**Case A: the error is caught completely inside outer before the transaction interceptor sees it.**

```java
@Transactional
public void outerCatchesLocalError() {
    repository.insert("outer");
    try {
        throw new IllegalStateException("handled locally");
    } catch (IllegalStateException expected) {
        // The interceptor wrapping outer has not seen this exception.
    }
    repository.insert("after");
}
```

If nobody else marked T rollback-only and the resource is still healthy, outer can commit. Having `catch(RuntimeException)` does not automatically cause a rollback.

**Case B: inner is a method with its own interceptor sharing T.**

```java
@Transactional
public void outerCatchesInnerError() {
    repository.insert("outer");
    try {
        innerService.writeThenFail();
    } catch (IllegalStateException expected) {
        // Inner's interceptor already saw the exception
        // before outer caught it.
    }
    repository.insert("after");
}
```

If the inner interceptor requests rollback, the manager marks T rollback-only. Outer catching it does not return T to a committable state.

The essence is **which transactional boundary the exception passed through before being caught**, not merely the exception class or whether `catch` appears in source code.

### 4.3. What if inner catches the exception itself before returning?

```java
@Transactional
public void innerHandlesItsOwnProblem() {
    try {
        throw new IllegalStateException("handled inside inner");
    } catch (IllegalStateException expected) {
        // Does not throw the exception through inner's interceptor.
    }
}
```

If no other code marks rollback-only and the database/ORM remain in a valid state, inner's interceptor sees only a normal return. Outer can commit. However, catching and ignoring errors like this can violate business contracts; **do not** use it as a way to "dodge rollback" for serious failures.

### 4.4. Rollback-only can occur even when no exception escapes

Inner can explicitly call:

```java
@Transactional
public void innerSignalsRollback() {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

This API marks **inner's local status**. When inner `REQUIRED` participates in T, completion processing of inner's scope can translate this signal into rollback-only on T. Outer can still return normally yet ultimately hit `UnexpectedRollbackException` when trying to commit T.

Conversely, **outer setting rollback-only on its own owner status** and returning can result in a **silent rollback** (without throwing `UnexpectedRollbackException` to the caller) when the manager recognizes local rollback-only as an intentional rollback decision. Therefore, **"caller receives UnexpectedRollbackException" is not a mandatory indicator of every rollback-only**.

## 5. What Exactly Does `UnexpectedRollbackException` Report?

`org.springframework.transaction.UnexpectedRollbackException` is a runtime exception in the `TransactionException` hierarchy. It is used when an invocation attempts to commit yet the actual outcome had to be rollback due to state that boundary did not intentionally decide on its own.

It should not be misunderstood as:

- "The last SQL statement definitely failed."
- "Spring called `rollback` twice on the same physical transaction."
- "The outer method threw this exact exception at its `return` line."
- "Catching exceptions in outer is always wrong."
- "Every transaction manager throws it at the exact same moment."
- "We need to retry commit once more to recover."

In the typical `REQUIRED` case, the exception states that **the caller must not assume the outer call committed successfully**. Outer's database transaction was rolled back because a participating scope earlier marked it rollback-only.

### 5.1. Timing of throwing the exception

With `AbstractPlatformTransactionManager`, the default is `failEarlyOnGlobalRollbackOnly = false`: global rollback-only state is normally reported at the **outermost transaction boundary**. If `setFailEarlyOnGlobalRollbackOnly(true)` is enabled, the exception can be raised earlier when the manager detects the global rollback-only flag at a subsequent inner boundary.

The invariant remains unchanged: **a globally rollback-only physical transaction must not be committed**. Changing when the error is reported is not a method for recovering a transaction.

### 5.2. `globalRollbackOnParticipationFailure` and why it should not be disabled lightly

`AbstractPlatformTransactionManager` has a `setGlobalRollbackOnParticipationFailure(boolean)` option, defaulting to `true`. When a **participating transaction** fails and the interceptor requests rollback, the manager can mark the global transaction rollback-only. Turning off this option is an advanced semantic change and **does not guarantee** you can keep committing after a resource/ORM error.

For example, PostgreSQL can place a database transaction into an aborted state after a SQL error, and a Hibernate `Session` may no longer be safe to continue after a persistence failure. Even if the manager does not proactively mark rollback-only, the underlying resource may still forbid commit. Therefore, do not use this setting as a "trick so outer can catch errors and commit" without thoroughly understanding database/ORM state and running integration tests.

### 5.3. Checking "new" status and rollback-only

The `TransactionAspectSupport.currentTransactionStatus()` API is meaningful only within an active Spring transactional interceptor context. Calling it outside that context can throw `NoTransactionException`. In the right context, `isNewTransaction()` helps distinguish the owner from a participant, while `isRollbackOnly()` helps check whether the current status has been marked rollback-only.

Do not treat `isRollbackOnly()` as an API that can "reset" a transaction. Moreover, at certain points, a rollback-only flag may live in the global transaction object/resource and not appear as expected when looking at a different status alone; testing behavior at the boundary matters more than logging a single variable.

## 6. Scenario Matrix: When Does Catch Still Commit, and When Not?

Assume a single `DataSourceTransactionManager` and a JDBC database supporting transactions. Methods are called **through Spring proxies**, except for the self-invocation row.

| Scenario | Inner scope | What happens before outer catch/return | Typical outcome |
| --- | --- | --- | --- |
| Inner `REQUIRED` throws `RuntimeException` via proxy | Same physical T | Inner interceptor marks T rollback-only | Outer tries to commit → rollback and `UnexpectedRollbackException` |
| Inner `REQUIRED` throws checked `IOException`, traditional default rule | Same T | Inner interceptor does not request rollback solely for a checked exception | Outer catches → can commit T |
| Inner `REQUIRED` throws checked `IOException`, with `rollbackFor=IOException.class` | Same T | Inner interceptor marks T rollback-only | Outer catching still fails to commit; typically `UnexpectedRollbackException` |
| Inner `REQUIRED` returns normally yet calls `setRollbackOnly()` | Same T | Inner completion makes T rollback-only | Outer return still encounters rollback at the boundary |
| Outer `catch`es a `RuntimeException` thrown **directly inside outer's body** | Only outer scope | No other interceptor marked rollback-only | Can commit T |
| Outer calls `setRollbackOnly()` itself and returns | Only outer owner | Outer intentionally decides rollback | Typically rolls back **without** `UnexpectedRollbackException` |
| Outer calls inner via `this.inner()` instead of proxy | No separate inner logical scope | Inner `@Transactional` is not intercepted on internal call | Can commit if outer catches and T is not rollback-only |
| Inner `REQUIRES_NEW` throws runtime exception | Independent physical T2 | T2 rolls back, outer's T remains separate | Outer catching can commit T |
| Inner `NESTED` throws runtime exception (JDBC savepoint supported) | Savepoint within T | Rolls back to savepoint, T can continue | Outer catching can commit the rest of T |
| Outer throws an uncaught runtime exception | Outer owner | Outer interceptor requests rollback | Rolls back T; caller sees original exception if rollback succeeds |

**Conditions for "can commit":** no rollback-only from other causes, manager/resource healthy, commit succeeds, and the transaction actually covers the operations. Rollback/commit rules alone do not guarantee the physical outcome.

### 6.1. How do checked exceptions differ in this problem?

Under traditional rollback defaults, Spring rolls back on `RuntimeException` and `Error`, **and does not roll back on checked `Exception` by default**. In Spring Framework 6.2, an application can **explicitly** configure `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` so checked exceptions also roll back under the new fallback. That change is opt-in; upgrading versions does not automatically change all defaults.

Therefore, when analyzing "outer catches inner's exception", ask **what inner's actual rollback rule is**, not just whether the exception was caught by outer. The hands-on exercise uses Boot 3.3.5/Spring 6.1.x, so traditional defaults apply.

### 6.2. Do not use `noRollbackFor` to "clear" another scope's rollback-only

```java
@Transactional(noRollbackFor = IllegalStateException.class)
public void outer() {
    try {
        innerService.writeThenFail();
    } catch (IllegalStateException ignored) {
        // ...
    }
}
```

This is an illustrative snippet. Outer's `noRollbackFor` only governs if **outer's interceptor sees** a matching exception at outer's boundary. It does not clear the rollback-only marker created earlier by inner's interceptor. To change inner's decision, examine the business contract and the right rollback rule/propagation **on inner**.

### 6.3. Why are repository failures even riskier than pure Java errors?

A `DataIntegrityViolationException` from a unique constraint, an `OptimisticLockingFailureException`, or an ORM flush failure can put the transaction resource into a state where it cannot validly continue. Even if outer catches the exception, the DB or persistence context may be unrecoverable. Do not rely on catching exceptions to run further SQL statements in the same transaction expecting a commit.

When recovery from a failed step is needed, determine whether **savepoints/`NESTED`** are viable for your stack, whether you must split into **`REQUIRES_NEW`** (independent transaction), or whether to redesign the workflow.

## 7. Runnable Hands-On Project: Verifying with H2 and JUnit

This section provides a minimal complete project. The goal is to **reproduce accurately** the phenomenon: outer catches a Java exception yet the caller still receives `UnexpectedRollbackException` and the database retains no records from T.

We also verify control cases: checked exception under defaults, explicit `rollbackFor`, explicit rollback-only, `REQUIRES_NEW`, `NESTED`, and self-invocation. These tests do not place a transaction on the test method itself, avoiding masking real service commits/rollbacks.

### 7.1. Project structure

```text
required-rollback-only/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/required/
    │   │   ├── RequiredApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── EventStore.java
    │   │   ├── InnerRequiredService.java
    │   │   ├── IndependentService.java
    │   │   ├── OuterService.java
    │   │   └── SelfInvocationService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/required/
        └── RequiredRollbackIntegrationTest.java
```

Use **JDK 17+** and a Gradle version compatible with Spring Boot 3.3.5. When generating a project via Spring Initializr, the Gradle Wrapper is usually included. If creating files manually, install Gradle or generate the wrapper. Because Spring is an external dependency outside the JDK, you cannot run `javac` directly on the classes below without providing the classpath.

`settings.gradle`:

```groovy
rootProject.name = 'required-rollback-only'
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

Note that Boot 3.3.5 uses Spring Framework 6.1.x, so Spring 6.2's global `ALL_EXCEPTIONS` is **not** enabled in this lesson. We want default checked-exception behavior for a clear comparison.

### 7.2. Database and transaction manager

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:required_demo;DB_CLOSE_DELAY=-1
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

`src/main/java/com/example/required/RequiredApplication.java`:

```java
package com.example.required;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequiredApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredApplication.class, args);
    }
}
```

`src/main/java/com/example/required/TransactionConfig.java`:

```java
package com.example.required;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        // Important defaults for this example:
        // globalRollbackOnParticipationFailure = true
        // failEarlyOnGlobalRollbackOnly = false
        return manager;
    }
}
```

This configuration chooses a single **local JDBC transaction manager**, convenient for observing one physical transaction on H2. `DataSourceTransactionManager` supports JDBC savepoints for `NESTED` if the driver/database supports them. No `TransactionTemplate` or JTA coordinator is needed.

### 7.3. Repository: writing and reading after the transaction

`src/main/java/com/example/required/EventStore.java`:

```java
package com.example.required;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String code) {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
    }

    public List<String> allCodes() {
        return jdbc.queryForList(
                "SELECT code FROM tx_events ORDER BY code", String.class);
    }

    public void deleteAll() {
        jdbc.update("DELETE FROM tx_events");
    }
}
```

The `allCodes()` method has no `@Transactional`; when called **after the service has returned or thrown an exception to the test**, it reads the finalized data state of the service transaction rather than observing uncommitted INSERTs inside T. In the H2 example, each test clears the table beforehand and runs sequentially.

### 7.4. Inner REQUIRED: multiple ways to make a transaction rollback-only

`src/main/java/com/example/required/InnerRequiredService.java`:

```java
package com.example.required;

import java.io.IOException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerRequiredService {
    private final EventStore store;

    public InnerRequiredService(EventStore store) {
        this.store = store;
    }

    @Transactional // REQUIRED by default
    public void insertThenRuntimeFailure() {
        store.insert("inner");
        throw new IllegalStateException("inner REQUIRED failed");
    }

    @Transactional
    public void insertThenCheckedFailure() throws IOException {
        store.insert("inner");
        throw new IOException("checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void insertThenConfiguredCheckedFailure() throws IOException {
        store.insert("inner");
        throw new IOException("checked failure with rollback rule");
    }

    @Transactional
    public void markRollbackOnly() {
        store.insert("inner");
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }

    @Transactional
    public void insertSuccess() {
        store.insert("inner");
    }

    @Transactional
    public boolean isCurrentScopeNew() {
        return TransactionAspectSupport.currentTransactionStatus()
                .isNewTransaction();
    }
}
```

**Note on `markRollbackOnly()`:** it throws no exception. Yet when called from outer `REQUIRED` through a proxy, inner's status is a participating status; `setRollbackOnly()` in inner causes the transaction manager to propagate the rollback-only marker to the shared physical transaction during inner completion handling.

**Note on `isCurrentScopeNew()`:** calling this method directly from a test via its proxy, when no transaction exists, typically returns `true`. Calling it **inside** an outer transaction via inner's proxy typically returns `false`. Both values come from the same `@Transactional(REQUIRED)`, differing only in participation conditions.

### 7.5. Independent transaction and savepoint for comparison

`src/main/java/com/example/required/IndependentService.java`:

```java
package com.example.required;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentService {
    private final EventStore store;

    public IndependentService(EventStore store) {
        this.store = store;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void newTransactionThenFail() {
        store.insert("isolated");
        throw new IllegalStateException("REQUIRES_NEW failed");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedSavepointThenFail() {
        store.insert("nested");
        throw new IllegalStateException("NESTED failed");
    }
}
```

These two methods are intentionally separated from `REQUIRED` for contrast:

- `REQUIRES_NEW`: suspends outer T and uses an independent transaction T2. An exception rolls back T2; outer T **does not automatically** roll back merely because T2 failed if outer catches the exception. Requires a separate connection; the connection pool must be large enough.
- `NESTED`: with `DataSourceTransactionManager` and H2 in the example, creates a savepoint within T. Inner rolls back to the savepoint, and outer's changes before the savepoint can still commit if the manager/resource allow it. It **does not** create an independent physical transaction like `REQUIRES_NEW`.

Do not switch every inner method to `REQUIRES_NEW` just to dodge `UnexpectedRollbackException`: doing so changes atomicity and can cause pool starvation when outer holds a connection and inner needs another. `NESTED` requires savepoint support; it is not a portable option across all JPA/JTA managers.

### 7.6. Outer service: the main focus of the lesson

`src/main/java/com/example/required/OuterService.java`:

```java
package com.example.required;

import java.io.IOException;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final EventStore store;
    private final InnerRequiredService inner;
    private final IndependentService independent;

    public OuterService(EventStore store,
                        InnerRequiredService inner,
                        IndependentService independent) {
        this.store = store;
        this.inner = inner;
        this.independent = independent;
    }

    @Transactional
    public void catchesInnerRuntime() {
        store.insert("outer");
        try {
            inner.insertThenRuntimeFailure();
        } catch (IllegalStateException expected) {
            // Caught the Java exception, yet inner interceptor already marked T rollback-only.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesInnerChecked() {
        store.insert("outer");
        try {
            inner.insertThenCheckedFailure();
        } catch (IOException expected) {
            // Spring 6.1 default: checked IOException does not trigger rollback.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesConfiguredChecked() {
        store.insert("outer");
        try {
            inner.insertThenConfiguredCheckedFailure();
        } catch (IOException expected) {
            // rollbackFor on inner already marked T rollback-only.
        }
        store.insert("after");
    }

    @Transactional
    public void innerMarksRollbackOnly() {
        store.insert("outer");
        inner.markRollbackOnly(); // No exception thrown here.
        store.insert("after");
    }

    @Transactional
    public void catchesLocalJavaError() {
        store.insert("outer");
        try {
            throw new IllegalStateException("local Java error");
        } catch (IllegalStateException expected) {
            // No inner transactional boundary requested rollback.
        }
        store.insert("after");
    }

    @Transactional
    public void ownerMarksRollbackOnly() {
        store.insert("outer");
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }

    @Transactional
    public void catchesIndependentFailure() {
        store.insert("outer");
        try {
            independent.newTransactionThenFail();
        } catch (IllegalStateException expected) {
            // T2 rolled back independently; outer T can still commit.
        }
        store.insert("after");
    }

    @Transactional
    public void catchesNestedFailure() {
        store.insert("outer");
        try {
            independent.nestedSavepointThenFail();
        } catch (IllegalStateException expected) {
            // Savepoint rolled back; the rest of T can still commit.
        }
        store.insert("after");
    }

    @Transactional
    public void allRequiredStepsSucceed() {
        store.insert("outer");
        inner.insertSuccess();
        store.insert("after");
    }

    @Transactional
    public boolean innerJoinedExistingTransaction() {
        return inner.isCurrentScopeNew(); // false: inner joined existing T.
    }

    @Transactional
    public void uncaughtRuntimeFailure() {
        store.insert("outer");
        throw new IllegalStateException("unhandled outer exception");
    }
}
```

Note the two most important methods:

- `catchesInnerRuntime()` finishes **normally in Java**, yet the outer proxy must still complete T. Because inner made T rollback-only, the caller outside the proxy receives `UnexpectedRollbackException`.
- `ownerMarksRollbackOnly()` explicitly calls `setRollbackOnly()` on **outer's status** and returns. The manager treats this as the owner's rollback decision; the caller may **not** receive `UnexpectedRollbackException`. Do not write logic relying solely on whether an exception is thrown.

### 7.7. Self-invocation: same object, unlike an inner proxy

`src/main/java/com/example/required/SelfInvocationService.java`:

```java
package com.example.required;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SelfInvocationService {
    private final EventStore store;

    public SelfInvocationService(EventStore store) {
        this.store = store;
    }

    @Transactional
    public void outerCallsThisAndCatches() {
        store.insert("outer");
        try {
            this.annotatedInnerThrows();
        } catch (IllegalStateException expected) {
            // this.inner(): does not go through a separate inner proxy.
        }
        store.insert("after");
    }

    @Transactional
    public void annotatedInnerThrows() {
        store.insert("self-inner");
        throw new IllegalStateException("self invocation failure");
    }
}
```

`outerCallsThisAndCatches()` still has an outer transaction because the test invokes it through a Spring proxy. Yet `this.annotatedInnerThrows()` is an internal call on the target object, **not intercepted by the transaction interceptor as a separate inner scope** in default proxy mode. The exception is caught inside the outer body, so even though inner's SQL executed inside outer T, no inner interceptor marked T rollback-only. The control outcome is that **all three rows can be committed**.

This point is easily misunderstood: self-invocation does not mean SQL inside the inner method automatically runs outside the outer transaction. If the outer transaction is already active on the same thread/resource, SQL still participates in T; it is simply that the inner method's annotation creates no additional transaction boundary.

### 7.8. Integration tests: observing after the proxy finishes

`src/test/java/com/example/required/RequiredRollbackIntegrationTest.java`:

```java
package com.example.required;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class RequiredRollbackIntegrationTest {
    @Autowired
    private EventStore store;

    @Autowired
    private OuterService outer;

    @Autowired
    private InnerRequiredService inner;

    @Autowired
    private SelfInvocationService self;

    @BeforeEach
    void reset() {
        store.deleteAll();
    }

    @Test
    void catchingInnerRuntimeCannotSaveSharedTransaction() {
        assertThrows(UnexpectedRollbackException.class,
                outer::catchesInnerRuntime);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void catchingCheckedWithoutRollbackRuleCanCommit() {
        outer.catchesInnerChecked();

        assertEquals(List.of("after", "inner", "outer"),
                store.allCodes());
    }

    @Test
    void explicitRollbackForMakesCheckedFailurePoisonSharedTransaction() {
        assertThrows(UnexpectedRollbackException.class,
                outer::catchesConfiguredChecked);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void innerCanMarkRollbackOnlyWithoutThrowing() {
        assertThrows(UnexpectedRollbackException.class,
                outer::innerMarksRollbackOnly);

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void catchingOnlyLocalJavaExceptionCanStillCommit() {
        outer.catchesLocalJavaError();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void ownerRollbackOnlyMayRollbackWithoutUnexpectedException() {
        outer.ownerMarksRollbackOnly();

        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void requiresNewFailureDoesNotAutomaticallyPoisonOuterTransaction() {
        outer.catchesIndependentFailure();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void nestedSavepointCanPreserveOuterWork() {
        outer.catchesNestedFailure();

        assertEquals(List.of("after", "outer"), store.allCodes());
    }

    @Test
    void successfulRequiredScopesCommitTogether() {
        outer.allRequiredStepsSucceed();

        assertEquals(List.of("after", "inner", "outer"),
                store.allCodes());
    }

    @Test
    void selfInvocationIsNotAnInnerProxyBoundary() {
        self.outerCallsThisAndCatches();

        assertEquals(List.of("after", "outer", "self-inner"),
                store.allCodes());
    }

    @Test
    void directRequiredCallCreatesANewTransactionScope() {
        assertTrue(inner.isCurrentScopeNew());
        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void innerRequiredJoinsExistingPhysicalTransaction() {
        assertFalse(outer.innerJoinedExistingTransaction());
        assertEquals(List.of(), store.allCodes());
    }

    @Test
    void unhandledOuterRuntimeExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                outer::uncaughtRuntimeFailure);

        assertEquals(List.of(), store.allCodes());
    }
}
```

**There are 13 independent tests**. Each test:

1. Clears the table before starting.
2. Invokes a Spring-managed service through its proxy.
3. Waits for the service's transaction to complete (or an exception to escape to the test).
4. Reads data via `EventStore.allCodes()` to measure the outcome.

**Do not** place `@Transactional` on this test class or these test methods. If a test opens its own transaction and rolls back at the end, `REQUIRED` services would join the test's transaction, and "commit" tests would no longer measure physical commits at the service boundary.

### 7.9. Running the project

In the directory containing `build.gradle`, if the Gradle Wrapper is present:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project was created manually without a wrapper, use a compatible installed Gradle to generate the wrapper or run `gradle test`. The code depends on Spring/JUnit/H2; use Gradle rather than plain `javac`.

**Expected outcome:** 13 JUnit tests pass with JDK 17+ and a valid environment/dependencies; there is no fixed-order stdout because JUnit does not guarantee test order. The test report is at `build/reports/tests/test/index.html`. This document does not claim the test suite was executed on your machine; row counts and exception types are **expected from the code and Spring JDBC semantics**.

| Test | Caller observes | Data after boundary |
| --- | --- | --- |
| Catch inner runtime `REQUIRED` | `UnexpectedRollbackException` | `[]` |
| Catch inner checked (no `rollbackFor`) | No error at outer caller | `[after, inner, outer]` |
| Catch inner checked with `rollbackFor` | `UnexpectedRollbackException` | `[]` |
| Inner sets rollback-only manually | `UnexpectedRollbackException` | `[]` |
| Catch Java error only inside outer | Returns normally | `[after, outer]` |
| Outer sets local rollback-only itself | May return normally | `[]` |
| Inner `REQUIRES_NEW` fails | Outer returns normally | `[after, outer]` |
| Inner `NESTED` rolls back savepoint | Outer returns normally | `[after, outer]` |
| Inner `REQUIRED` succeeds | Returns normally | `[after, inner, outer]` |
| Self-invocation caught | Returns normally | `[after, outer, self-inner]` |
| Direct inner `REQUIRED` | `isNewTransaction() = true` | `[]` |
| Inner `REQUIRED` joins outer | `isNewTransaction() = false` | `[]` |
| Uncaught outer runtime exception | `IllegalStateException` | `[]` |

**A note on the `REQUIRES_NEW` test:** transaction T2 needs an independent connection while outer T holds a connection. Use a pool with at least two available connections; in production, size the connection pool according to nesting depth. If the database blocks T2's operation due to locks on rows outer just wrote, tests may need separate fixture data. H2 with distinct keys and the sample configuration was chosen to minimize that likelihood.

## 8. Debugging `UnexpectedRollbackException` in a Real Application

### 8.1. Identify inner transactional boundaries before looking at `catch`

Do not start by deleting `catch` or changing exception classes. Trace:

1. **Which caller invokes outer through a proxy?** If outer is called via `this.outer()` or on a non-Spring-managed object, transaction advice may not run.
2. **Which physical transaction does outer have?** Does `REQUIRED` open a new one or join a broader caller's transaction?
3. **Is inner really called through a Spring proxy?** If so, inner's own interceptor handles the exception.
4. **Which exception escaped through inner's interceptor?** `RuntimeException`, `Error`, or a checked exception with `rollbackFor`?
5. **Who set rollback-only?** Inner interceptor, `TransactionStatus.setRollbackOnly()`, ORM/database, or another participating scope?
6. **Is there a stack trace starting at outer's commit?** `UnexpectedRollbackException` usually surfaces when the manager reports an unexpected rollback.
7. **What remains in the database at the end?** Read back with an independent transaction/connection after the outer boundary to verify.
8. **Which manager is in use?** `DataSourceTransactionManager`, `JpaTransactionManager`, JTA, or a custom manager have different semantics.

### 8.2. Selectively enable logging

In Spring Boot you can temporarily enable:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.orm.jpa=DEBUG
```

Enable the ORM/JPA logger only if the application actually uses JPA. Logger names/lines vary by version and manager, so **do not** write tests that depend on fixed log strings. Logs can show an inner scope joining an existing transaction and the manager marking rollback-only, yet only observing **after the boundary** reveals the actual data outcome.

Do not log sensitive data, credentials, or full SQL parameters in production. On busy systems, DEBUG/TRACE can add overhead and generate huge logs.

### 8.3. When an error occurs at commit time

Errors at the outer boundary are not always `UnexpectedRollbackException`. They can be JPA flush failures, constraint violations, locks, timeouts, dropped connections, or transaction manager failures. When commit fails, data can be in an **indeterminate** state if the connection drops at the exact moment the database receives commit.

For payments, orders, or invoicing, never blindly retry a transaction just because the caller received an exception. Use a business key or idempotency key to reconcile state before retrying. A "commit failed" log line does not by itself prove rollback succeeded.

## 9. Business Design When You Need to "Try a Secondary Step and Ignore Errors"

In practice, outer catching inner is not always wrong. The mistake is **believing that catch will recover a physical transaction that is already rollback-only**. There are at least four design approaches, with distinct semantics.

### 9.1. Keep `REQUIRED` to preserve atomicity

If outer and inner must **succeed together or fail together** (for example, inventory deduction and order recording must not diverge), keep `REQUIRED` and **do not try to swallow errors**. Let the exception propagate to the caller or change the API to return an appropriate business result after the entire transaction rolls back.

```java
@Transactional
public void placeOrder() {
    reserveInventory();
    chargePaymentRecord();
    // Unrecoverable error -> fail the whole operation.
}
```

This illustration assumes the methods use proper transaction-bound resources. Do not assume external HTTP/payment-gateway calls will automatically roll back along with the JDBC transaction.

### 9.2. Use `REQUIRES_NEW` for a truly independent step

If a secondary step must be independent—such as saving an audit record when the primary operation fails—you can consider another bean using `REQUIRES_NEW`. However, this design has consequences:

- Inner T2 can commit even if outer T rolls back, or vice versa.
- Outer holds resources while T2 needs another connection.
- An independent audit event does not automatically guarantee consistency with the main transaction if a system failure occurs.
- For events/messages requiring durability, a transactional outbox is usually more appropriate than an HTTP call inside a transaction.

Use it only when this independence genuinely matches business requirements, and test both branches.

### 9.3. Use `NESTED` when partial rollback via savepoint is needed

With JDBC and a manager supporting savepoints, `PROPAGATION_NESTED` lets inner roll back changes made after the savepoint within **the same physical transaction**, allowing outer to continue. It fits workflows that permit skipping a substep while committing valid prior work.

**Limitation:** not every database/transaction manager supports nested savepoints; Hibernate/JPA contexts and side effects outside the database do not automatically "rewind to a savepoint" in the same way. Test against the real resource.

### 9.4. Avoid using exceptions to represent normal branches

If inner detects "soft quota reached" or "no coupon available", it can return a business value instead of throwing a runtime exception that causes the transaction interceptor to decide on rollback:

```java
public enum CouponResult {
    APPLIED,
    NOT_ELIGIBLE
}
```

This is a standalone Java enum usable in a service. For example, the service can return `CouponResult.NOT_ELIGIBLE` for an expected branch, while real infrastructure failures still throw exceptions. However, do not turn exceptions into return values just to "make Spring commit" when transactional invariants no longer hold; there must be clear business criteria.

## 10. Counterexample Scenarios to Remember

### 10.1. Outer catches an error yet inner uses `noRollbackFor`

```java
@Transactional(noRollbackFor = ValidationWarning.class)
public void inner() {
    throw new ValidationWarning();
}
```

Here `ValidationWarning` is a **hypothetical** runtime exception defined by the application; the snippet is not standalone. If inner's rule **does not require rollback** and the resource still permits continuing, outer catching it and committing can succeed. This shows that **catching the exception** is not the sole factor; the **actual rollback rule at the boundary that saw the exception** is what matters.

### 10.2. Inner throws a checked exception, yet global ALL_EXCEPTIONS is enabled

In Spring Framework 6.2+, the optional configuration `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` causes checked exceptions without special rules to trigger rollback by default too. When upgrading from the old default to the new mode, an outer method that used to catch checked `IOException` and commit can shift to `UnexpectedRollbackException`. Do not apply the conclusion "checked exceptions never roll back" regardless of actual configuration.

### 10.3. Outer also joins a broader caller's transaction

If controller → facade `@Transactional` → outer `@Transactional(REQUIRED)` → inner `@Transactional(REQUIRED)`, then outer is no longer the owner of the physical transaction. It is merely another participating logical scope. Rollback-only may be detected and reported at the **outermost boundary of the facade**, not necessarily immediately when outer returns. Thus when debugging, find the **ultimate transaction owner**, not just a method named "outer".

### 10.4. Outer catches `UnexpectedRollbackException` **after** calling an independent inner

If an inner `REQUIRES_NEW` becomes rollback-only and throws `UnexpectedRollbackException` upon T2's completion, outer can catch that exception **inside its body** because T2 finished at the inner proxy. This differs from `UnexpectedRollbackException` raised by **outer's own commit** after outer's body returns: a `catch` inside the body cannot catch a completion exception thrown by its own boundary.

### 10.5. Method returns normally yet outcome remains uncertain

Even without rollback-only, commit can fail in the infrastructure. Therefore "outer caught it and returned so it definitely committed" is wrong for **two independent reasons**:

- Under `REQUIRED`, T may already be rollback-only due to an inner scope.
- The transaction can fail during physical commit even when the method body throws no exception.

That is why callers must distinguish **returning from the method body** from **the proxy returning normally after completion**.

## 11. Checklist for Verifying a Production Bug

Suppose an application returns `UnexpectedRollbackException` even though logs say "Handled inner exception". Follow this order:

1. Identify an **operation ID** to correlate against the database rather than relying on random data.
2. Inspect the **original stack trace** of the inner failure; find where the first exception escaped through a transaction interceptor.
3. Verify whether outer and inner are different Spring-managed beans and whether the call goes **through a proxy**.
4. Read `@Transactional` on both: `propagation`, `rollbackFor`, `noRollbackFor`, `transactionManager`, isolation, timeout.
5. Check the actual transaction manager and database; do they share the same `DataSource`/resource?
6. Identify which scope has `isNewTransaction() = true`; check whether inner joined physical T.
7. Check whether the **rollback-only** flag came from an exception rule, `setRollbackOnly()`, or a resource error.
8. Read data after the boundary using an **independent connection**, checking business keys and business invariants.
9. Choose the design explicitly: atomic `REQUIRED`, independent transaction `REQUIRES_NEW`, JDBC savepoint `NESTED`, or return-value branching.
10. Write regression tests for **both the exception the caller observes and the committed/rolled-back data**.
11. If changing propagation or timeout, check connection pool, locks, throughput, and failure modes in a production-like environment.
12. For indeterminate commit failures, stop non-idempotent retries and reconcile first.

### Which test provides the strongest evidence?

A test that only writes:

```java
assertThrows(UnexpectedRollbackException.class, service::run);
```

is insufficient if the business requirement involves data. Add:

```java
assertEquals(List.of(), eventStore.allCodes());
```

Only when the test runs **outside a test-managed transaction** and reads from an independent transaction/connection after the service boundary does it verify the real effect. Conversely, a test that only checks zero rows without asserting the exception can miss the fact that the caller was misinformed about the commit outcome.

## 12. Self-Check Questions

**1. Outer `REQUIRED` calls inner `REQUIRED`, inner throws `IllegalStateException`, outer catches and returns. By default, why does outer usually hit `UnexpectedRollbackException`?**

Because the inner interceptor saw the runtime exception and marked the **shared physical transaction** rollback-only. Outer's catch does not clear the marker; outer's commit is rolled back, so the caller is notified of an unexpected rollback.

**2. Is `isNewTransaction()` on inner `REQUIRED` always `false`?**

No. When inner is called directly and no transaction exists, inner can create a new T and return `true`. When joining T opened by outer, the value is normally `false`.

**3. What if an exception is thrown and caught completely inside the outer method, and nobody marked rollback-only?**

Outer's interceptor may see a normal return and commit T. `catch` does not cause rollback on its own, nor does it guarantee commit on its own.

**4. Can we call `setRollbackOnly(false)` to restore T?**

No. The `TransactionStatus.setRollbackOnly()` API marks rollback-only; there is no corresponding "clear rollback-only and commit" contract. Change the boundary/design instead of trying to reverse the state of a potentially failed resource.

**5. Inner `REQUIRES_NEW` rolls back, outer `REQUIRED` catches it. Is outer guaranteed to commit?**

You cannot say "guaranteed". Inner T2 rolls back independently and does not mark outer T rollback-only by default, yet outer can still encounter other errors or fail at commit. If T is healthy, outer **can** commit.

**6. How does inner `NESTED` differ from `REQUIRES_NEW`?**

`NESTED` typically uses a savepoint within the **same** physical T when supported by a JDBC manager, whereas `REQUIRES_NEW` creates an independent physical T2 and suspends outer T. They differ completely in semantics and resource requirements.

**7. Outer calls `this.inner()`, and both methods have `@Transactional`. Why might the result differ from calling a separate inner bean?**

Self-invocation bypasses the proxy for the inner method in default proxy mode. There is no separate inner transaction advice handling the exception; if the exception is caught by outer and T is not rollback-only, outer can commit.

**8. Can the caller receive `UnexpectedRollbackException` even though the outer method already returned from its body?**

Yes. The exception can be thrown from the transaction interceptor **after** the body returns, during transaction completion. A `catch` inside the body cannot catch an exception thrown by the completion of that very boundary.

**9. Is the best way to verify just reading "rollback-only" logs or running integration tests?**

Integration tests calling through proxies and checking **both the exception and post-boundary data**. Logs help diagnose causes, yet do not accurately prove business outcomes.

**10. What needs fixing in business code: the exception type, the `catch` location, or the transaction boundary?**

It depends on the invariant. First determine whether outer and inner must be atomic together. If yes, keep `REQUIRED` and let failures be reported properly. If a step is genuinely allowed to be independent, design `REQUIRES_NEW`/`NESTED` or return values with matching tests. Do not change propagation merely to hide exceptions.

## Official Documentation

- [Spring Framework — Transaction Propagation: Understanding PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — `UnexpectedRollbackException` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/UnexpectedRollbackException.html)
- [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — `TransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
