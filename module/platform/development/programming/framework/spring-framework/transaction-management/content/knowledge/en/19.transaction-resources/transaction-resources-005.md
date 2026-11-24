# Suspending, Resuming, and Cleaning Up Transaction-Bound Resources in Spring Framework

## Objectives

In Spring transaction management, a transaction is not just `BEGIN` and `COMMIT`. The framework must also **bind resources to the execution context**, **suspend/resume** them when switching to another transaction, and **clean up** after commit or rollback.

This article helps you:

1. Distinguish physical transaction, logical transaction scope, JDBC connection, and `ConnectionHolder`.
2. Understand how `TransactionSynchronizationManager` manages resource bindings, metadata, and synchronizations per thread in the imperative model.
3. Explain how `PROPAGATION_REQUIRES_NEW` and `NOT_SUPPORTED` suspend outer resources and then restore the exact outer context.
4. Explain why `REQUIRED` typically shares the connection and `NESTED` typically uses a savepoint, **without** needing to suspend outer like `REQUIRES_NEW`.
5. Distinguish `TransactionSynchronization.suspend()/resume()` from `beforeCommit`, `beforeCompletion`, `afterCommit`, and `afterCompletion`.
6. Monitor connection pools, cleanup after both commit and rollback, resource leak risks, and surprises when JDBC auto-commits outside a transaction.
7. Run a **Java 17+, Spring Boot 3.3.5, Spring JDBC, H2** example with JUnit 5 tests verifying exact callback ordering and actually committed data.

**Scope:** imperative JDBC transactions via `DataSourceTransactionManager`. Some details do not apply directly to JPA/JTA or reactive transactions.

---

## 1. What Are "Transaction-Bound Resources"?

In Spring JDBC, `JdbcTemplate` normally does not take a connection parameter on every method. Instead, Spring provides a **transaction-bound connection** appropriate for the current thread and managed `DataSource`.

```text
Application thread
     |
     v
TransactionSynchronizationManager
     |
     +-- DataSource A -> ConnectionHolder -> JDBC Connection C1
     +-- metadata: name, readOnly, isolation, actual transaction
     +-- registered TransactionSynchronization callbacks
     |
     v
JdbcTemplate -> DataSourceUtils
     |
     +-- accesses the exact connection C1 bound to the transaction
     v
Database transaction T1
```

| Component | Responsibility |
| --- | --- |
| `DataSource` | Supplies JDBC connections, possibly via HikariCP |
| `Connection` | Database working connection where the physical JDBC transaction is managed |
| `ConnectionHolder` | Spring holder retaining the connection and some transaction-related state |
| `TransactionSynchronizationManager` | Manages resources and synchronizations bound to the current thread |
| `DataSourceUtils` | Acquires/releases connections respecting transaction-bound resources |
| `JdbcTemplate` | Uses Spring-managed connections to execute SQL |
| `PlatformTransactionManager` | Coordinates begin, commit, rollback; specifically, the JDBC manager handles suspend/resume/cleanup |
| `TransactionSynchronization` | Callback for coordinating resources across the transaction lifecycle |

**Distinguish three layers:** `ThreadLocal` holds the binding, `ConnectionHolder` references the connection, and the **physical transaction** is the database's actual transaction state. Binding an object to a thread **does not automatically create** a transaction; a transaction manager must still start and complete the actual transaction.

Example:

```java
@Transactional
public void createOrder() {
    orderRepository.insert();
    inventoryRepository.decrease();
    ledgerRepository.append();
}
```

This is a business snippet requiring real repositories. If all three repositories use the same Spring-managed JDBC datasource/transaction manager, the statements can use the same transaction-bound connection. If one repository opens an unmanaged connection on its own, atomicity can be lost.

## 2. Observing the Thread-Bound Context Properly

API used in imperative Spring:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;
```

Calls:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean syncActive =
    TransactionSynchronizationManager.isSynchronizationActive();

boolean bound =
    TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
    TransactionSynchronizationManager.getResource(dataSource);
```

`resource` is typically a `ConnectionHolder` in Spring JDBC, **not** a `java.sql.Connection` directly.

Common pitfall: `isActualTransactionActive()` differs from `isSynchronizationActive()`.

- **Actual transaction active:** Spring context is associated with a real resource transaction.
- **Synchronization active:** a callback/resource synchronization mechanism is active; in certain cases, it remains active **without an actual transaction**, such as some `SUPPORTS`/`NOT_SUPPORTED` branches.
- **Resource bound:** a resource exists under the key you checked. Having a bound resource also does not by itself prove a physical transaction exists.

Therefore:

> `isSynchronizationActive() == true` is not enough to assert that SQL is executing inside a physical transaction.

When determining a scope's state, inspect **propagation**, actual transaction, resource binding, and the transaction manager in use.

**Do not manually call** `TransactionSynchronizationManager.bindResource(dataSource, ...)`, `unbindResource(dataSource)`, `clearSynchronization()`, or `clear()` on connections/holders owned by the transaction manager. Doing so can break the link to resources awaiting commit/rollback.

## 3. Lifecycle of a Typical JDBC Transaction

`DataSourceTransactionManager` is a concrete implementation of `PlatformTransactionManager` for local JDBC transactions. When an outer `@Transactional(REQUIRED)` is called through a proxy and no suitable transaction exists yet:

```text
Caller -> Spring proxy
    |
    v
TransactionInterceptor
    |
    v
DataSourceTransactionManager
    |
    +-- acquire JDBC Connection C1
    +-- prepare isolation/read-only/timeout when supported
    +-- set autoCommit=false if needed
    +-- bind ConnectionHolder(C1) under DataSource key
    +-- publish metadata/synchronizations
    |
    v
Business method -> JdbcTemplate -> C1
    |
    +-- method returns: attempt commit
    |       or
    +-- exception matches rollback rule: rollback
    |
    v
TransactionSynchronization callbacks
    |
    v
cleanup:
    - unbind the transaction's holder
    - restore modified connection state
    - release connection to pool
    - clear corresponding transaction/synchronization context
    |
    v
Caller receives result
```

This is a **functional description**, without promising the exact order of every internal method shown in the diagram. Importantly, `afterCommit` and `afterCompletion` can run **while some resources are still bound**; do not assume the connection has already been completely released the moment the callback starts.

`DataSourceTransactionManager` is responsible for cleanup on successful commit, rollback, or when transaction operations fail per manager rules. Business code should let the framework coordinate resources rather than closing connections or clearing `ThreadLocal` manually.

### What About Inner `REQUIRED`?

```java
@Transactional(propagation = Propagation.REQUIRED)
public void outer() {
    innerService.inner();
}
```

If `inner()` is advised via another Spring bean and also uses `REQUIRED`, it **joins** physical T1 on C1 without suspending to open a new physical transaction. Successful completion of inner **does not commit** C1 separately. If inner marks rollback-only, outer's commit can still fail with `UnexpectedRollbackException`.

## 4. Suspend and Resume: Hiding the Outer Context Without Ending the Outer Transaction

When outer transaction T1 is active and inner uses `REQUIRES_NEW`, Spring must give inner an **independent physical transaction**:

```text
Outer T1 / C1
  |
  +-- INSERT A on C1, uncommitted
  |
  +-- SUSPEND outer
  |      - save and temporarily unbind outer resource binding
  |      - suspend outer synchronizations
  |      - preserve metadata/context for restoration
  |      - T1 remains open, C1 is usually still held
  |
  +-- BEGIN inner T2 / C2
  |      - bind Holder(C2)
  |      - INSERT B on C2
  |      - COMMIT or ROLLBACK T2
  |      - cleanup inner resources
  |
  +-- RESUME outer
  |      - rebind Holder(C1)
  |      - restore outer synchronizations and metadata
  |
  +-- INSERT C on C1
  |
  +-- COMMIT or ROLLBACK T1
  +-- cleanup outer
```

**Suspend is not COMMIT/ROLLBACK.** T1 remains open in the database; uncommitted data A and locks or snapshots may still exist while inner runs. **Resume does not create a new T1:** it restores the previous transaction/resource context.

For local JDBC, `DataSourceTransactionManager` provides `doSuspend(...)` and `doResume(...)` hooks to unbind/bind resources. At the general level, `AbstractPlatformTransactionManager` coordinates transaction synchronizations, suspended resources, and metadata.

**Connection pool consequence:** outer C1 may still hold onto a connection while inner T2 needs C2. Under many concurrent requests, the pool must have capacity for inner transactions. Spring notes that the pool needs at least one more connection than the number of concurrent threads for one level of nested `REQUIRES_NEW`, and in practice may need more depending on workloads.

## 5. `NOT_SUPPORTED`: Suspend Outer Without Opening a New Transaction

If inner has:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void runWithoutTransaction() {
    // JDBC work in a scope without a Spring-managed physical transaction.
}
```

Spring suspends the outer transaction when needed, yet **does not open a new physical transaction** just to run inner. If `JdbcTemplate.update()` uses a new connection with `autoCommit=true`, the SQL statement can **commit independently** as soon as the statement completes.

```text
T1 on C1: INSERT outer-1 (uncommitted)
    |
    +-- suspend T1
    +-- NOT_SUPPORTED:
    |      INSERT external-2 using another connection / auto-commit
    |      external-2 already committed (with autoCommit=true)
    +-- resume T1
    |
    +-- ROLLBACK T1
```

Result: `outer-1` is rolled back, while `external-2` remains.

**Condition to state clearly:** the durability of a statement outside a transaction depends on the datasource, connection/auto-commit setting, SQL, and database. `NOT_SUPPORTED` does not promise that everything auto-commits in every environment.

In `NOT_SUPPORTED`, `isActualTransactionActive()` is `false`; however, transaction synchronization **can** be active, and `JdbcTemplate` can bind a connection for nontransactional synchronization **after performing JDBC access**. Therefore, do not write an assertion such as "after any SQL statement in `NOT_SUPPORTED`, `hasResource(dataSource)` must always be false."

## 6. Propagation Decides Whether to Suspend, Join, or Use a Savepoint

| Inner propagation | When outer T1 is active | Suspend resource? | Inner's physical transaction |
| --- | --- | --- | --- |
| `REQUIRED` | Joins T1 | Normally no | Same T1 |
| `REQUIRES_NEW` | Suspends T1 | Yes | Independent T2 |
| `NOT_SUPPORTED` | Suspends T1 | Yes | Does not open a new transaction |
| `NESTED` | Creates a savepoint in T1 if supported | No, under JDBC savepoint model | Same T1 |
| `SUPPORTS` | Joins T1 | Normally no | Same T1 |
| `MANDATORY` | Requires T1 | No | Same T1 |
| `NEVER` | Forbids T1 | No; throws error | Does not run inner when T1 exists |

`NESTED` is **not** the same as `REQUIRES_NEW`: rolling back to a savepoint can undo part of T1's changes, yet nested success **does not commit independently**. With `REQUIRES_NEW`, inner has its own transaction that can commit even if outer rolls back.

`NOT_SUPPORTED` is **not** equivalent to `readOnly=true`: it only requests execution without a current physical transaction. Code can still send `UPDATE`/`INSERT`.

## 7. How Does Spring Coordinate the Lifecycle?

`AbstractPlatformTransactionManager` determines propagation, whether a transaction already exists, whether to create a new one or join, whether suspend/resume is needed, and decides commit/rollback. Concrete managers such as JDBC `DataSourceTransactionManager` provide implementation hooks for specific resources.

| Hook | Purpose |
| --- | --- |
| `doBegin(...)` | Begin a physical transaction |
| `doSuspend(...)` | Temporarily unbind the current transaction's resource |
| `doResume(...)` | Restore a suspended resource |
| `doCommit(...)` | Commit the actual transaction |
| `doRollback(...)` | Roll back the actual transaction |
| `doSetRollbackOnly(...)` | Mark a shared transaction as unable to commit |
| `doCleanupAfterCompletion(...)` | Clean up resources after completion |

A transaction manager **does not necessarily** support suspension: the base implementation can throw `TransactionSuspensionNotSupportedException`. JTA, JPA, or custom manager configurations/implementations must be verified specifically; do not extrapolate from JDBC code to every resource type.

### Why Not Suspend the Connection Yourself?

Spring must temporarily unbind **both resource bindings and synchronizations/metadata**, and then restore them in a consistent state—even if inner throws an exception. Calling `TransactionSynchronizationManager.unbindResource(dataSource)` in a business service only removes a single binding; it does not fulfill the entire suspend/resume contract.

A common bug is holding onto an old connection, switching threads manually, or binding another connection under the same key and expecting Spring to sort it out. The result can be SQL using the wrong transaction, duplicate binding errors, missing rollbacks, or pool leaks.

## 8. `TransactionSynchronization`: Callbacks and Ordering

Spring provides:

```java
import org.springframework.transaction.support.TransactionSynchronization;
```

Important callbacks:

| Callback | Execution Point | Meaning |
| --- | --- | --- |
| `suspend()` | When outer synchronizations are suspended | Custom resource synchronization can unbind its own resource |
| `resume()` | When outer context is restored | Can rebind the custom resource |
| `beforeCommit(boolean readOnly)` | Before commit attempt | Flush/check; **does not guarantee commit will succeed** |
| `beforeCompletion()` | Before completion, on both commit and rollback | Clean up resources that must be released prior to completion |
| `afterCommit()` | After successful commit | Post-commit tasks, with the caveat that resources may still be bound |
| `afterCompletion(int status)` | After commit/rollback/unknown status is known | Cleanup and outcome tracking |

`TransactionSynchronization` defines `STATUS_COMMITTED`, `STATUS_ROLLED_BACK`, and `STATUS_UNKNOWN`.

Normal commit path:

```text
business method returns
  -> beforeCommit
  -> beforeCompletion
  -> physical commit
  -> afterCommit
  -> afterCompletion(COMMITTED)
  -> complete resource/context cleanup
```

Normal rollback path:

```text
business method throws unchecked exception
  -> beforeCompletion
  -> physical rollback
  -> afterCompletion(ROLLED_BACK)
  -> complete resource/context cleanup
```

`afterCommit()` and `beforeCommit()` are **not** callbacks on the normal rollback path. `beforeCommit()` does not prove the commit has completed.

### Registering a Synchronization

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                System.out.println("Completed: " + status);
            }
        }
    );
}
```

The above is a snippet, not a standalone class. When there is no active synchronization, do not skip the condition and call `registerSynchronization(...)`. Spring's infrastructure handles activating/stopping synchronizations.

**Important warning:** according to the Spring Javadoc, `afterCommit()` and `afterCompletion(...)` can run while transactional resources **are still accessible and bound**, even though physical commit/rollback has finished. Database work inside the callback may appear to "join the old transaction" **with no further commit coming**. If you genuinely need to write to the DB inside a callback, use a **new transaction**, such as calling a `@Transactional(propagation = REQUIRES_NEW)` bean. If you need to ensure cross-system events are not lost when the process crashes right after commit, consider a **transactional outbox**.

---

## 9. Runnable Project: Spring Boot 3.3.5 + JDBC/H2 Tracking Resource Suspend/Resume

### 9.1. Scenarios

The demo has two independent scenarios:

**A. Outer rolls back, inner keeps its independent commit**

- Outer T1 INSERTs id 1.
- Inner `REQUIRES_NEW` T2 INSERTs id 2 and commits.
- Inner `NOT_SUPPORTED` INSERTs id 3 via an auto-commit connection.
- Outer T1 INSERTs id 4 and then throws `IllegalStateException`; T1 rolls back.
- Final DB contains only **2 and 3**.

**B. Inner rolls back, outer still commits**

- Outer T1 INSERTs id 10.
- Inner `REQUIRES_NEW` T2 INSERTs id 11 and then throws `IllegalStateException`; T2 rolls back.
- Outer catches the error after the inner proxy, INSERTs id 12, and commits.
- Final DB contains **10 and 12**, without 11.

Throughout, outer synchronization logs `suspend`, `resume`, `beforeCompletion`, `afterCompletion`; in case B, `beforeCommit` and `afterCommit` also appear.

### 9.2. Structure

```text
resource-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/lifecycle/
    │   │   ├── InnerScopeService.java
    │   │   ├── OuterScopeService.java
    │   │   ├── ScenarioRunner.java
    │   │   └── ResourceLifecycleApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/lifecycle/
        └── ResourceLifecycleTest.java
```

Uses Java 17+, Gradle with Spring Boot 3.3.5. Generate the Gradle wrapper via Spring Initializr or an installed Gradle. No web server is needed.

### 9.3. `settings.gradle`

```groovy
rootProject.name = 'resource-lifecycle-demo'
```

### 9.4. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

### 9.5. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:resource_lifecycle;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
  sql:
    init:
      mode: always
```

A 4-connection pool allows outer to hold C1 while inner `REQUIRES_NEW` or `NOT_SUPPORTED` SQL borrows another connection. The demo assumes the pool/driver's default JDBC auto-commit for SQL running outside a physical transaction.

### 9.6. `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
```

Each scenario resets the table before opening the outer transaction. The INSERTs use distinct IDs so they do not contend on the same primary key.

### 9.7. `src/main/java/example/lifecycle/InnerScopeService.java`

```java
package example.lifecycle;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerScopeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public InnerScopeService(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void commitNew(List<String> trace, Object outerHolder) {
        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();
        Object innerHolder = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "NEW active=" + active
            + " differentHolder=" + (innerHolder != outerHolder)
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            2, "new-committed"
        );
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void nonTransactional(List<String> trace, Object outerHolder) {
        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();
        Object visible = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "NOT_SUPPORTED active=" + active
            + " outerHidden=" + (visible == null)
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            3, "non-transactional"
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failNew(List<String> trace) {
        trace.add(
            "NEW_FAIL active="
            + TransactionSynchronizationManager.isActualTransactionActive()
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            11, "inner-rolled-back"
        );
        throw new IllegalStateException("inner rejected");
    }
}
```

`outerHolder` is passed to compare **object identity** of the resource holder in the demo; it is not a connection ID for production logic.

`nonTransactional` checks the binding **before JDBC access**. After `jdbc.update`, Spring may temporarily bind a connection under the synchronization policy even though **there is no physical transaction** in scope; that is why we do not print `hasResource` after the SQL statement and falsely infer that `NOT_SUPPORTED` opened T.

### 9.8. `src/main/java/example/lifecycle/OuterScopeService.java`

```java
package example.lifecycle;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OuterScopeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final InnerScopeService inner;

    public OuterScopeService(
            JdbcTemplate jdbc, DataSource dataSource,
            InnerScopeService inner) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.inner = inner;
    }

    private static String completionName(int status) {
        return switch (status) {
            case TransactionSynchronization.STATUS_COMMITTED -> "COMMITTED";
            case TransactionSynchronization.STATUS_ROLLED_BACK -> "ROLLED_BACK";
            default -> "UNKNOWN";
        };
    }

    private static void registerTrace(List<String> trace) {
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void suspend() {
                    trace.add("SYNC suspend");
                }
                @Override
                public void resume() {
                    trace.add("SYNC resume");
                }
                @Override
                public void beforeCommit(boolean readOnly) {
                    trace.add("SYNC beforeCommit");
                }
                @Override
                public void beforeCompletion() {
                    trace.add("SYNC beforeCompletion");
                }
                @Override
                public void afterCommit() {
                    trace.add("SYNC afterCommit");
                }
                @Override
                public void afterCompletion(int status) {
                    trace.add(
                        "SYNC afterCompletion=" + completionName(status)
                    );
                }
            }
        );
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            id, description
        );
    }

    @Transactional
    public void rollbackOuter(List<String> trace) {
        Object outerHolder = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "OUTER active="
            + TransactionSynchronizationManager.isActualTransactionActive()
            + " bound=" + (outerHolder != null)
        );

        registerTrace(trace);
        insert(1, "outer-before");

        inner.commitNew(trace, outerHolder);
        trace.add(
            "RESUMED after NEW="
            + (TransactionSynchronizationManager.getResource(dataSource)
               == outerHolder)
        );

        inner.nonTransactional(trace, outerHolder);
        trace.add(
            "RESUMED after NOT_SUPPORTED="
            + (TransactionSynchronizationManager.getResource(dataSource)
               == outerHolder)
        );

        insert(4, "outer-after");
        throw new IllegalStateException("outer rejected");
    }

    @Transactional
    public void commitOuter(List<String> trace) {
        trace.add(
            "OUTER active="
            + TransactionSynchronizationManager.isActualTransactionActive()
        );

        registerTrace(trace);
        insert(10, "outer-before");

        try {
            inner.failNew(trace);
        } catch (IllegalStateException ex) {
            trace.add("OUTER caughtInner=" + ex.getMessage());
        }

        insert(12, "outer-after");
    }
}
```

`registerTrace()` runs inside the already-opened outer transaction so synchronization is active. `suspend`/`resume` only record the trace; they do **not** manually unbind the JDBC holder. The framework handles the holder via `DataSourceTransactionManager`.

In case A, `beforeCompletion` and `afterCompletion(ROLLED_BACK)` callbacks fire, with **no** `afterCommit`. In case B, before/after commit callbacks fire and the completion status is `COMMITTED`.

### 9.9. `src/main/java/example/lifecycle/ScenarioRunner.java`

```java
package example.lifecycle;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ScenarioRunner {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final OuterScopeService outer;

    public ScenarioRunner(
            JdbcTemplate jdbc, DataSource dataSource,
            OuterScopeService outer) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.outer = outer;
    }

    private void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    private String persistedRows() {
        List<String> rows = jdbc.query(
            "SELECT id, description FROM tx_events ORDER BY id",
            (rs, index) ->
                rs.getInt("id") + ":" + rs.getString("description")
        );
        return rows.toString();
    }

    private boolean contextClean() {
        return !TransactionSynchronizationManager
                .isActualTransactionActive()
            && !TransactionSynchronizationManager
                .isSynchronizationActive()
            && !TransactionSynchronizationManager
                .hasResource(dataSource);
    }

    public List<String> scenarioA() {
        reset();
        List<String> trace = new ArrayList<>();

        try {
            outer.rollbackOuter(trace);
        } catch (IllegalStateException ex) {
            trace.add("A caught=" + ex.getMessage());
        }

        trace.add("A rows=" + persistedRows());
        trace.add("A cleanup=" + contextClean());
        return trace;
    }

    public List<String> scenarioB() {
        reset();
        List<String> trace = new ArrayList<>();

        outer.commitOuter(trace);
        trace.add("B rows=" + persistedRows());
        trace.add("B cleanup=" + contextClean());
        return trace;
    }
}
```

The runner is called **outside a transaction**, so `reset()` and `persistedRows()` do not join outer T1. DB results are read only after the transaction proxy has committed/rolled back.

`contextClean()` verifies that no actual transaction, active synchronization, or bound datasource resource remains on the thread. It is a useful lifecycle check; pool metrics are still needed to detect connection leaks in real systems.

### 9.10. `src/main/java/example/lifecycle/ResourceLifecycleApplication.java`

```java
package example.lifecycle;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ResourceLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceLifecycleApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    ApplicationRunner demonstrate(ScenarioRunner scenarios) {
        return args -> {
            scenarios.scenarioA().forEach(System.out::println);
            scenarios.scenarioB().forEach(System.out::println);
        };
    }
}
```

There is one JDBC transaction manager sharing the same `DataSource` with `JdbcTemplate`; `@EnableTransactionManagement` enables transaction advice. Calls `ScenarioRunner -> OuterScopeService -> InnerScopeService` all go through Spring bean proxies, avoiding self-invocation.

### 9.11. Running and Expected stdout

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ignoring startup logs, the program is expected to print:

```text
OUTER active=true bound=true
SYNC suspend
NEW active=true differentHolder=true
SYNC resume
RESUMED after NEW=true
SYNC suspend
NOT_SUPPORTED active=false outerHidden=true
SYNC resume
RESUMED after NOT_SUPPORTED=true
SYNC beforeCompletion
SYNC afterCompletion=ROLLED_BACK
A caught=outer rejected
A rows=[2:new-committed, 3:non-transactional]
A cleanup=true
OUTER active=true
SYNC suspend
NEW_FAIL active=true
SYNC resume
OUTER caughtInner=inner rejected
SYNC beforeCommit
SYNC beforeCompletion
SYNC afterCommit
SYNC afterCompletion=COMMITTED
B rows=[10:outer-before, 12:outer-after]
B cleanup=true
```

This is the **expected stdout based on source and configuration**, not a claim that the code was executed on the machine where the documentation was written.

Explanation:

- `SYNC suspend`/`SYNC resume` appear around `REQUIRES_NEW`, `NOT_SUPPORTED`, and the failing inner call because outer synchronizations are suspended and then restored.
- `differentHolder=true` means inner bound a new holder rather than using outer's holder.
- `NOT_SUPPORTED active=false` confirms there is no Spring-managed physical transaction inside that callback.
- `RESUMED ...=true` confirms the exact outer holder was rebound.
- When outer rolls back, **inner's committed id 2** and the auto-committed SQL id 3 remain.
- When inner T2 rolls back yet outer catches the error after the inner proxy, outer T1 can still commit id 10 and id 12.
- `cleanup=true` confirms the thread context was cleaned up after the outer boundary.

## 10. JUnit 5 Tests Verifying Resource Lifecycle

File `src/test/java/example/lifecycle/ResourceLifecycleTest.java`:

```java
package example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootTest
class ResourceLifecycleTest {
    @Autowired ScenarioRunner scenarios;
    @Autowired DataSource dataSource;

    @Test
    void outerRollbackLeavesIndependentWrites() {
        assertEquals(
            List.of(
                "OUTER active=true bound=true",
                "SYNC suspend",
                "NEW active=true differentHolder=true",
                "SYNC resume",
                "RESUMED after NEW=true",
                "SYNC suspend",
                "NOT_SUPPORTED active=false outerHidden=true",
                "SYNC resume",
                "RESUMED after NOT_SUPPORTED=true",
                "SYNC beforeCompletion",
                "SYNC afterCompletion=ROLLED_BACK",
                "A caught=outer rejected",
                "A rows=[2:new-committed, 3:non-transactional]",
                "A cleanup=true"
            ),
            scenarios.scenarioA()
        );
    }

    @Test
    void innerRollbackDoesNotForceOuterRollback() {
        assertEquals(
            List.of(
                "OUTER active=true",
                "SYNC suspend",
                "NEW_FAIL active=true",
                "SYNC resume",
                "OUTER caughtInner=inner rejected",
                "SYNC beforeCommit",
                "SYNC beforeCompletion",
                "SYNC afterCommit",
                "SYNC afterCompletion=COMMITTED",
                "B rows=[10:outer-before, 12:outer-after]",
                "B cleanup=true"
            ),
            scenarios.scenarioB()
        );
    }

    @Test
    void noTransactionResourcesRemainAfterBoundary() {
        scenarios.scenarioB();

        assertFalse(
            TransactionSynchronizationManager.isActualTransactionActive()
        );
        assertFalse(
            TransactionSynchronizationManager.isSynchronizationActive()
        );
        assertFalse(
            TransactionSynchronizationManager.hasResource(dataSource)
        );
    }
}
```

Run:

```bash
./gradlew test
```

Do not put `@Transactional` on the test class/method: a transaction opened by the test framework could make the outer method join **the test's transaction** and completely alter the behavior of `REQUIRES_NEW`, `NOT_SUPPORTED`, and final commit/rollback.

`@SpringBootTest` may invoke `ApplicationRunner` when building the context. Each scenario executes `DELETE` on the fixture before running, so assertions are independent of startup output. Do not run multiple tests sharing the same H2 table in parallel without isolating the database/fixture. Pure Mockito cannot prove resource suspend/resume or persisted rows after physical commit.

## 11. Custom Resource Binding: Only for the Infrastructure Layer

Most applications do not need `bindResource`/`unbindResource`. However, a **resource management integration** can bind a self-managed object under a dedicated key and use synchronizations:

```java
private static final Object CUSTOM_KEY = new Object();

void bindCustomResource(Object holder) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("No active synchronization");
    }

    TransactionSynchronizationManager.bindResource(CUSTOM_KEY, holder);

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void suspend() {
                TransactionSynchronizationManager.unbindResource(CUSTOM_KEY);
            }
            @Override
            public void resume() {
                TransactionSynchronizationManager.bindResource(
                    CUSTOM_KEY, holder
                );
            }
            @Override
            public void afterCompletion(int status) {
                TransactionSynchronizationManager
                    .unbindResourceIfPossible(CUSTOM_KEY);
            }
        }
    );
}
```

This is an **architectural snippet, not a standalone Java class**, and still requires resource-closing policy, error handling, nested scopes, and real key ownership. It must not be copied blindly into production.

Meaning: a custom resource must be **temporarily unbound on suspend**, **rebound on resume**, and **cleaned up after transaction completion**. Never use this code to manipulate the `DataSource` key of a `ConnectionHolder` owned by the Spring manager. As of Spring 6.1, a resource key should have only one valid binding; duplicate binding normally throws `IllegalStateException`.

## 12. Dangerous Mistake in `afterCommit()` and `afterCompletion()`

```java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            auditRepository.insertAuditEntry();
        }
    }
);
```

This snippet **does not guarantee** that `insertAuditEntry()` will receive a new commit. Per the Spring Javadoc, the transaction has already committed, yet some resources **may still be bound** during callbacks. JDBC code inside the callback may see the old connection and appear to join the old transaction **with no subsequent commit**.

If you want to actually write to the DB after commit, call **another Spring bean** with a `@Transactional(propagation = REQUIRES_NEW)` method to create a new transaction, or use a `TransactionTemplate` configured with `PROPAGATION_REQUIRES_NEW` in the right place. Do not call `this.innerRequiresNew()` via self-invocation and expect proxy advice to run.

When events/messages must not be lost if the process crashes right after database commit, sending straight to a broker inside `afterCommit()` still has a failure gap. A **transactional outbox** with retries/idempotency is a more consistent solution.

## 13. Cleanup and Connection Pools

With a connection pool like HikariCP, `release` usually means **returning the connection proxy to the pool**, not necessarily closing the physical TCP socket immediately.

After physical completion, the JDBC manager is typically responsible for unbinding the holder, restoring auto-commit/isolation/read-only if changed, releasing the connection, and clearing transaction-specific context. Spring runs cleanup along appropriate success/failure paths; hence application code should not arbitrarily `close` transaction-bound connections.

Three situations to distinguish:

| Symptom | What to Investigate |
| --- | --- |
| Pool runs out of connections | Outer T stays open while suspended, inner `REQUIRES_NEW` needs C2; transaction is too long |
| Thread carries old resources across requests | Custom binding failed to unbind after completion or code mutated `ThreadLocal` manually |
| Leak detection logs warnings | Connection genuinely was not returned to the pool **or** a transaction held the connection too long |

Prevention: use `JdbcTemplate`, keep transactions short, avoid blocking network calls inside T, audit `REQUIRES_NEW` nesting depth, pool capacity, and connection metrics instead of increasing max pool size indefinitely.

## 14. Synchronization with Other Threads and Reactive Contexts

In imperative JDBC, `TransactionSynchronizationManager` is **thread-bound**. `@Async`, `Executor`, or `CompletableFuture` running on another thread **do not automatically inherit** the calling thread's transaction holder:

```java
@Transactional
public void perform(Executor executor) {
    saveToDatabase();
    executor.execute(() -> sendMessage());
}
```

This illustrative snippet does not guarantee the task shares the transaction or rolls back if outer fails. Do not copy `getResourceMap()` to another thread: connections/holders may not be thread-safe, and the manager's lifecycle will be broken.

Reactive (`ReactiveTransactionManager`/R2DBC) uses the subscription/Reactive Context rather than the same implicit JDBC thread-local semantics. Do not apply this technique directly to reactive flows.

## 15. Suspend/Resume Debugging Checklist

1. Identify where the outer physical transaction starts and whether it goes through a proxy.
2. Check `PlatformTransactionManager`, `DataSource`, and the JDBC connection pool.
3. Determine inner propagation: `REQUIRED`, `REQUIRES_NEW`, `NOT_SUPPORTED`, `NESTED`.
4. If `REQUIRES_NEW`, does outer suspend and inner acquire a new connection? Does the pool have enough connections?
5. If `NOT_SUPPORTED`, does the code execute auto-commit SQL outside a transaction?
6. If `NESTED`, does the driver/manager support savepoints instead of a new transaction?
7. Trace `TransactionSynchronization.suspend()/resume()` to distinguish the outer context from the inner context.
8. Read `isActualTransactionActive()` and `getResource(dataSource)` at the right moment; do not confuse with `isSynchronizationActive()`.
9. Do not look only at SQL "having executed": check data after the **outermost transaction boundary**.
10. Track `beforeCompletion`/`afterCompletion` and the transaction outcome.
11. Verify the thread context is clean after the method; cross-check pool metrics to detect leaks.
12. Avoid mutating `TransactionSynchronizationManager` manually in business services.
13. If an unexpected rollback occurs, check whether an inner `REQUIRED` marked rollback-only.
14. If DB writes are needed from `afterCommit`, route through a genuinely new transaction.
15. When switching from JDBC to JPA/JTA/reactive, re-verify all resource/lifecycle assumptions.

Logging can be enabled in a debug environment:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

Enable only temporarily when needed; do not print resource maps or connection secrets to production logs.

## 16. Self-Check Questions

1. Does `suspend` commit the outer transaction? **No**; outer usually remains open in the DB.
2. Does `resume` create a new outer transaction? **No**; it restores the previous context/resource.
3. Can `REQUIRES_NEW` commit even if outer rolls back? **Yes**, because of its independent physical transaction.
4. Does `NOT_SUPPORTED` open a new physical transaction? **No**.
5. If JDBC auto-commits under `NOT_SUPPORTED`, does an outer rollback delete the committed inner INSERT? **No**.
6. Does an inner `REQUIRED` open C2 when outer already has C1? **Normally no**; it joins C1/T1.
7. What does `NESTED` use for partial rollback? **A savepoint within the same physical transaction** when supported.
8. Does `isSynchronizationActive()` guarantee an actual transaction exists? **No**.
9. What does `getResource(dataSource)` return? **The resource bound under the key**, which for JDBC is typically `ConnectionHolder`.
10. Does `beforeCommit` mean the commit has already succeeded? **No**.
11. Can `afterCompletion` run before resources are completely cleaned up? **Yes**.
12. To write an audit record inside `afterCommit`, what should you create? **A genuinely new transaction** if business requirements allow.
13. Why can `REQUIRES_NEW` easily cause pool starvation? **Outer C1 remains held while inner C2 is needed**.
14. Should you call `unbindResource(dataSource)` yourself in a service? **No**; the manager owns that resource.
15. Does an imperative transaction context automatically propagate to another async thread? **No**.
16. Does `afterCompletion(STATUS_ROLLED_BACK)` mean "no side effects outside the DB"? **No**; the transaction manager only manages the resources belonging to its transaction.

## 17. Official References

- Spring Framework — **Transaction Propagation**, `REQUIRED`, `REQUIRES_NEW`, `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Declarative Transaction Implementation**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **TransactionSynchronizationManager** (imperative): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — **TransactionSynchronization** (`suspend`, `resume`, `afterCompletion`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — **AbstractPlatformTransactionManager** lifecycle: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — **DataSourceTransactionManager**, suspend/resume/cleanup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — **DataSourceUtils**, JDBC resource binding: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — **Transaction-bound Events** and `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html