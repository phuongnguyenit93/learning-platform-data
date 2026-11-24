# SUPPORTS and Resource Synchronization Without a Physical Transaction

## 1. The problem and key message

In Spring Framework, `Propagation.SUPPORTS` has a short description:

> If a compatible transaction currently exists, join that transaction; if not, execute without a physical transaction.

However, that sentence **does not describe all** of Spring's behavior. With transaction managers that support *transaction synchronization*, a `@Transactional(propagation = Propagation.SUPPORTS)` call **can activate a resource synchronization scope** even when **there is no physical transaction** in the database.

Therefore, it is completely possible to observe at the same time:

```text
TransactionSynchronizationManager.isSynchronizationActive() = true
TransactionSynchronizationManager.isActualTransactionActive() = false
```

These two values **do not contradict each other**. They answer two different questions:

- **Synchronization active?** Is Spring managing a scope so that resources/synchronization callbacks can be registered, reused, and cleaned up for the scope?
- **Actual transaction active?** Is there an existing physical transaction that Spring considers active?

The most important consequence: **reusing the same JDBC Connection does not mean the SQL statements belong to a database transaction that can roll back together**. With a standard auto-commit H2/Hikari configuration, two INSERT statements in a SUPPORTS scope without a physical transaction can commit **individually at execution time**, and an exception at the end of the method will not undo them.

### After this lesson, what will you be able to do?

1. Distinguish `SUPPORTS` from `REQUIRED`, `NOT_SUPPORTED`, and `MANDATORY` depending on the outer transaction state.
2. Distinguish **logical synchronization scope**, **resource binding/reuse**, and **physical transaction**.
3. Understand the roles of `AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS`, `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION`, and `SYNCHRONIZATION_NEVER`.
4. Explain how `DataSourceUtils`, `JdbcTemplate`, and `TransactionSynchronizationManager` coordinate to share a connection within a thread.
5. Run a **Java 17+, Spring Boot, Spring JDBC, and H2** demo showing that `SUPPORTS` without a physical transaction still has synchronization and shares the connection, yet does not roll back auto-committed data.
6. Compare with the case where inner `SUPPORTS` joins an outer `REQUIRED` transaction: a real physical transaction exists and the INSERTs roll back together.
7. Design tests and monitoring that avoid mistaking `isSynchronizationActive()`, `isCurrentTransactionReadOnly()`, or reading back data as proof of commit/rollback.

This article belongs to the **Other Propagation** section of the **Spring Framework — transaction management** module, focusing directly on **"SUPPORTS and resource synchronization without a physical transaction"**.

## 2. SUPPORTS is not a "lighter" REQUIRED in terms of rollback

Suppose a service has:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void doWork() {
    // Data access...
}
```

When the service is intercepted by a Spring proxy, `SUPPORTS` behavior depends on the outer context:

| Context before calling | What SUPPORTS does | Physical transaction? | What to remember |
| --- | --- | --- | --- |
| Existing transaction T on compatible manager | **Joins T** | Yes, uses existing T | INSERT/UPDATE in T can commit/roll back together |
| No transaction T, synchronization mode is `ALWAYS` | Runs without T, but can open a synchronization scope | **No** | Resources can be shared in scope; no physical rollback for auto-committed SQL |
| No T, synchronization mode is `ON_ACTUAL_TRANSACTION` | Runs without T and opens no new synchronization scope | **No** | No promise of thread-bound resource sharing from SUPPORTS scope |
| No T, synchronization mode is `NEVER` | Opens no synchronization scope from that manager | **No** | Do not assume `DataSourceUtils` will bind a connection |
| Calling method directly via `this.method()` in proxy mode | Method annotation is not applied separately by interceptor | Depends on whether outer already has T | Do not conclude anything from the annotation alone |

With `REQUIRED`, if no transaction exists, Spring **must open a new physical transaction** per manager capability. With `SUPPORTS`, if no transaction exists, it **does not require a physical transaction**. This is the core difference in atomicity guarantees.

What surprises developers is that synchronization configuration can make `SUPPORTS` **behave differently from a plain non-transactional Java call** in how it *scopes resources*. It can retain and reuse the same connection/session and register callbacks, even though the SQL statements do not sit under a shared `BEGIN...COMMIT/ROLLBACK`.

### 2.1. When does SUPPORTS "join T"?

Example:

```java
@Service
public class ReportService {
    @Transactional(propagation = Propagation.SUPPORTS)
    public void calculate() {
        // JDBC/JPA queries...
    }
}

@Service
public class OrderService {
    private final ReportService reports;

    public OrderService(ReportService reports) {
        this.reports = reports;
    }

    @Transactional
    public void placeOrder() {
        // Write order.
        reports.calculate(); // SUPPORTS joins T opened by placeOrder.
    }
}
```

These two classes are **architectural illustrations** without DB implementations. If both methods are called through proxies and use the same transaction manager/resource, `calculate()` executes inside the existing transaction T. `SUPPORTS` **does not create an independent transaction** and does not commit on its own when `calculate()` returns.

If a caller invokes `reportService.calculate()` directly from a runner without a transaction, behavior differs: **there is no physical transaction** for that method, even though synchronization may still be active.

## 3. Three layers to distinguish: metadata, synchronization, physical transaction

To avoid confusion, split this into three concepts:

### 3.1. Transaction metadata

`@Transactional(propagation = SUPPORTS)` is a declaration. `TransactionInterceptor` reads the metadata to ask `PlatformTransactionManager` how to handle it.

The annotation does **not** by itself switch a JDBC connection to `autoCommit=false`, bind resources, or create a proxy. The Spring bean must be managed and the invocation must pass through the corresponding advice (or proper weaving mechanism).

### 3.2. Transaction synchronization

Spring has a synchronization management mechanism for thread-bound imperative transactions. `TransactionSynchronizationManager` can hold:

- Keyed resources, such as a `ConnectionHolder` bound to a `DataSource`.
- A list of registered `TransactionSynchronization` callbacks.
- Transaction scope information, such as name, read-only hint, or isolation metadata.
- The synchronization active flag and the actual transaction active flag.

**A synchronization scope is a coordination/lifecycle mechanism**, not a database transaction in the ACID sense. A manager can open synchronization for an "empty transaction" of `SUPPORTS` with no backend transaction.

### 3.3. Physical transaction

A true physical transaction manages atomicity on the database connection (or corresponding entity manager/transaction coordinator). With `DataSourceTransactionManager`, a new JDBC transaction typically switches the connection to `autoCommit=false`, binds the resource to the thread, and finally invokes commit/rollback.

When there is no physical transaction and the connection has `autoCommit=true`, each SQL statement typically commits under driver/DB auto-commit semantics. An exception at the end of the method **cannot make Spring roll back SQL statements that the database already committed earlier**.

### 3.4. API observation table

| API/observation | What does it tell you? | What does it NOT prove? |
| --- | --- | --- |
| `TransactionSynchronizationManager.isSynchronizationActive()` | A synchronization scope is currently active | Does not prove a DB transaction is active |
| `TransactionSynchronizationManager.isActualTransactionActive()` | Spring marked an actual transaction active | Does not guarantee every external resource participates |
| `TransactionSynchronizationManager.hasResource(dataSource)` | A resource is bound for key `DataSource` | Does not prove the resource disabled auto-commit |
| `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` | Whether the advice invocation opened a new transaction | Not a DB transaction ID, not usable outside advice |
| `Connection.getAutoCommit()` | Auto-commit mode on the retrieved connection | Says nothing about commits on other connections |
| `SELECT COUNT(*)` after the boundary ends | Observed data state in DB | Must ensure querying the right DB/schema without concurrency interference |

For instance, "`sync=true`, `actual=false`, `bound=true`, `autoCommit=true`" shows a **synchronization scope reusing a connection outside a physical transaction**, not a rollback-capable transaction.

## 4. Why can SUPPORTS share a JDBC Connection when there is no T?

Spring JDBC typically goes through `DataSourceUtils.getConnection(DataSource)` to obtain a connection. `JdbcTemplate` also uses connection access compatible with the transaction infrastructure.

When synchronization is active and code requests a connection:

1. `DataSourceUtils` checks `TransactionSynchronizationManager` to see if a `ConnectionHolder` is already bound for the `DataSource`.
2. If none is bound yet, it obtains a connection from the pool/driver.
3. If an appropriate synchronization scope exists, it can **register a synchronization for cleanup** and bind the holder to the thread.
4. Subsequent JDBC operations using the same `DataSource`/`DataSourceUtils` within the scope can receive **that exact bound connection**.
5. When the scope finishes, Spring runs cleanup/closing or returns the connection to the pool per the corresponding lifecycle.

When physical transaction T exists, this shared connection is typically configured with `autoCommit=false` by the manager, and the manager commits/rolls back T.

When **T does not exist**, the connection can still be held and reused because of synchronization, yet it may still keep `autoCommit=true`. **Same connection ≠ same commit boundary**.

Diagram:

```text
SUPPORTS, no T, SYNCHRONIZATION_ALWAYS manager

Service A via proxy
    |
    +-- Spring opens synchronization scope (no BEGIN T)
    |
    +-- DataSourceUtils.getConnection(ds)
    |      +-- acquires Connection C from pool
    |      +-- binds C to thread, registers cleanup
    |
    +-- JdbcTemplate INSERT id=1 via C  [autoCommit=true]
    |      +-- DB commits this SQL statement
    |
    +-- Service B SUPPORTS via proxy
    |      +-- DataSourceUtils.getConnection(ds) -> still C
    |      +-- JdbcTemplate INSERT id=2 via C  [autoCommit=true]
    |      +-- DB commits second SQL statement
    |
    +-- Service A throws RuntimeException
    |
    +-- Spring cleans up synchronization scope
    |      [NO physical transaction to roll back]
    |
Caller catches exception
    |
    +-- SELECT COUNT(id=1 or 2) -> both records still exist
```

**Warning:** this diagram shows the behavior of **the H2/Hikari demo with auto-commit=true**. With a special DataSource or a connection configured with different auto-commit behavior, things can differ and require dedicated testing; do not extrapolate blindly from the propagation name.

### 4.1. Why is keeping the same Connection useful?

Resource synchronization is useful for *lifecycle* consistency, for example:

- Multiple data access layers in the same call can use the same connection/session.
- Reduces repeated resource acquisition/release within a scope when managed properly by the framework.
- Ensures organized resource cleanup at the boundary.
- Libraries can attach synchronization callbacks for resource lifecycles.

However, without a physical transaction, **there is no promise of ACID atomicity**. Sharing a connection can keep session state consistent, but may also cause the connection to be held longer, especially when a query method takes a long time.

### 4.2. `DataSourceUtils` is not the same as calling `dataSource.getConnection()` directly

In Spring JDBC, `DataSourceUtils.getConnection(ds)` and `DataSourceUtils.releaseConnection(conn, ds)` are the public APIs compatible with thread-bound resources. Inside a synchronization scope, `releaseConnection` may **not immediately close** a bound connection: the framework retains it for reuse and cleans it up when the scope ends.

If you call `dataSource.getConnection()` directly, close it manually, or toggle auto-commit improperly, you can bypass Spring's mechanism or break the resource lifecycle. In normal business code, use `JdbcTemplate`, repositories, or transaction-aware abstractions instead of managing connections manually; the demo below touches the connection solely for **controlled observation**.

### 4.3. Resource binding happens on the imperative thread

`TransactionSynchronizationManager` uses thread-bound context for the imperative model. If execution switches to `@Async`, a custom thread, or another executor, the original thread's context **does not automatically transfer**. Reactive Spring uses a different mechanism based on Reactor context; do not directly apply the `ThreadLocal` analogy from the JDBC demo to R2DBC.

## 5. The three synchronization modes of a transaction manager

`AbstractPlatformTransactionManager` defines the following transaction synchronization activation levels:

| Mode | No physical transaction when SUPPORTS | Active actual transaction |
| --- | --- | --- |
| `SYNCHRONIZATION_ALWAYS` | **Can activate a synchronization scope**, even for an "empty" transaction | Activates synchronization |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Does not activate new synchronization solely for SUPPORTS | Activates synchronization when T exists |
| `SYNCHRONIZATION_NEVER` | Does not activate | Manager never activates synchronization even when T exists |

By default in `AbstractPlatformTransactionManager`, the synchronization mode is **ALWAYS**. However, the framework has multiple transaction manager types, so inspect the actual configuration instead of assuming every environment is identical.

Java configuration example:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);

manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);
```

This is a **configuration fragment**; it requires imports/bean wiring and a `DataSource`; the demo below includes a complete bean using this exact configuration.

### 5.1. ALWAYS: synchronization even without T

With `SUPPORTS` and no actual transaction:

```text
isActualTransactionActive() = false
isSynchronizationActive()   = true
```

After `DataSourceUtils.getConnection` acquires a connection, the manager/utility can bind the holder to the synchronization scope; `JdbcTemplate` calls in layers on the same thread can reuse that connection.

A `TransactionSynchronization` callback invoked by the lifecycle **should not be interpreted as proof that a physical DB commit occurred**. In an "empty" synchronization scope, there is no physical `doCommit` affecting auto-committed SQL statements. Therefore, do not use the sync flag or a standalone callback as an "after-commit" business guarantee.

### 5.2. ON_ACTUAL_TRANSACTION: synchronization only when T exists

With this configuration:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

if a `SUPPORTS` method has no outer physical transaction, it does not create a new synchronization scope:

```text
isActualTransactionActive() = false
isSynchronizationActive()   = false
```

Without synchronization, `DataSourceUtils.getConnection()` generally does not bind a connection for the entire scope the way ALWAYS does. You should not predict that two separate JDBC calls will receive the same Java connection object. Yet **lacking synchronization does not turn on a transaction either**: SQL with `autoCommit=true` can still commit individually, just like in the SUPPORTS demo below.

`ON_ACTUAL_TRANSACTION` is especially worth considering if your architecture **nests a REQUIRED/REQUIRES_NEW call inside SUPPORTS** and runs into synchronization conflicts. Spring's Javadoc warns to be careful when nesting those propagations inside a SUPPORTS scope without a physical transaction; test manager/resource compatibility. This is a configuration option **at the transaction manager level**, not a direct attribute on `@Transactional`.

### 5.3. NEVER: never activate synchronization

`SYNCHRONIZATION_NEVER` disables the manager's activation of synchronization even when an actual transaction exists. This is a specialized configuration for specific integration needs; it **does not mean disabling physical transactions**. Do not enable it just to change a `syncActive` indicator without understanding the JDBC/ORM and resource-handling infrastructure.

### 5.4. An environment with multiple managers

Spring warns that multiple transaction managers cannot **simultaneously own thread-bound synchronization**. If you use a JDBC manager, JPA manager, JMS manager, or JTA manager in the same call chain, determine who owns synchronization, which resources are bound, and which manager each annotation selects. One manager enabling `SYNCHRONIZATION_ALWAYS` **does not turn multiple databases into a distributed transaction**.

## 6. Complete hands-on project: two INSERTs, same connection, two different rollback outcomes

We build a Java 17+ program using **Spring Boot 3.3.13, Spring JDBC, Spring AOP, and in-memory H2**. There are two directly comparable scenarios:

- **Case S — SUPPORTS without a physical transaction:** both outer and inner methods use SUPPORTS; synchronization is active, same JDBC connection, auto-commit=true; both INSERTs remain in the DB even though the outer method throws `IllegalStateException`.
- **Case R — outer REQUIRED, inner SUPPORTS:** outer opens a physical transaction; inner SUPPORTS joins T, uses the same connection now set to auto-commit=false; outer throws `IllegalStateException`; both INSERTs are rolled back.

The experiment keeps inner's work identical (one INSERT statement) while changing **outer's transaction context**, isolating the variable "whether a physical transaction already exists".

### 6.1. Project files

```text
supports-sync-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/learning/supports/
    │   ├── SupportsApplication.java
    │   ├── SupportsFacade.java
    │   └── SupportsWorker.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

No HTTP controller is needed; `CommandLineRunner` runs both experiments sequentially on startup.

**`settings.gradle`**

```groovy
rootProject.name = 'supports-sync-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'learning'
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

Compatible with Gradle 8.x and JDK 17 or newer. The dependencies add Spring transaction infrastructure, JDBC, AOP, and the embedded database; do not compile with plain `javac` without the Spring/H2 classpath.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:supports_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.auto-commit=true
spring.sql.init.mode=always
spring.main.web-application-type=none
spring.main.banner-mode=off
```

The line `spring.datasource.hikari.auto-commit=true` makes the experimental condition **explicit**. Hikari/DataSource provides auto-commit connections for operations **without a physical transaction**; `DataSourceTransactionManager` handles turning off auto-commit when opening a new physical transaction. Do not treat this auto-commit setting as a universal recommendation for all systems; it simply makes the contrast clear.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE demo_event (
    id INT PRIMARY KEY,
    description VARCHAR(80) NOT NULL
);
```

Each case uses distinct IDs (1,2 and 3,4). Since the table starts empty, `COUNT(*)` after the scope clearly shows commit vs. rollback. In-memory H2 creates a fresh database on each normal JVM startup, provided no old process keeps that database alive.

### 6.2. SupportsWorker: inner SUPPORTS receives the already bound connection

**`src/main/java/learning/supports/SupportsWorker.java`**

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsWorker {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;

    public SupportsWorker(DataSource dataSource, JdbcTemplate jdbc) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void write(int id, Connection parentConnection)
            throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            boolean physical =
                TransactionSynchronizationManager
                    .isActualTransactionActive();
            boolean sync =
                TransactionSynchronizationManager
                    .isSynchronizationActive();
            boolean bound =
                TransactionSynchronizationManager.hasResource(dataSource);
            boolean sameConnection = connection == parentConnection;

            System.out.println(
                "worker physical=" + physical +
                " sync=" + sync +
                " bound=" + bound +
                " sameConnection=" + sameConnection +
                " autoCommit=" + connection.getAutoCommit());

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                id, "written-by-worker"
            );
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

Code notes:

- `SupportsWorker` is a Spring-managed bean; `write` is public, non-final, and annotated with `SUPPORTS`.
- The outer call uses **another injected bean**, so it passes through a separate proxy and transaction interceptor.
- `DataSourceUtils.getConnection` retrieves the connection for the thread-bound context. Comparing `connection == parentConnection` is a valid test **in this demo environment** because both classes use **the exact same DataSource object** on the same thread.
- `hasResource(dataSource)` indicates whether a holder is bound under the DataSource key after calling `getConnection`.
- `releaseConnection` is called in `finally`; if the connection belongs to a Spring-managed scope, it is cleaned up according to its lifecycle rather than being closed prematurely by business code.
- `JdbcTemplate` connects in a Spring-compatible way, so the INSERT uses the bound connection.

**We do not call `Connection.close()` directly** inside inner and do not manually change auto-commit; doing so would break the transaction manager's resource management. Holding a JDBC connection reference here is solely for observation in this lesson, not the standard way to write business services.

### 6.3. SupportsFacade: changing outer context without changing inner

**`src/main/java/learning/supports/SupportsFacade.java`**

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsFacade {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;
    private final SupportsWorker worker;

    public SupportsFacade(
            DataSource dataSource, JdbcTemplate jdbc,
            SupportsWorker worker) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
        this.worker = worker;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void noPhysicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("support", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "support-outer"
            );
            worker.write(2, connection);

            throw new IllegalStateException("no-physical");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void physicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("required", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                3, "required-outer"
            );
            worker.write(4, connection);

            throw new IllegalStateException("physical-failure");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    private static void printStatus(
            String label, Connection connection) throws SQLException {
        boolean physical =
            TransactionSynchronizationManager
                .isActualTransactionActive();
        boolean sync =
            TransactionSynchronizationManager
                .isSynchronizationActive();
        boolean bound =
            TransactionSynchronizationManager
                .hasResource(DataSourceForLogHolder.key());
    }
}
```

The `printStatus` section at the end is replaced by the complete implementation immediately below, so no nonexistent variable/method is used. The **complete Java file uses a single implementation**:

```java
package learning.supports;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SupportsFacade {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;
    private final SupportsWorker worker;

    public SupportsFacade(
            DataSource dataSource, JdbcTemplate jdbc,
            SupportsWorker worker) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
        this.worker = worker;
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void noPhysicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("support", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                1, "support-outer"
            );
            worker.write(2, connection);

            throw new IllegalStateException("no-physical");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void physicalTransaction() throws SQLException {
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            printStatus("required", connection);

            jdbc.update(
                "INSERT INTO demo_event(id, description) VALUES (?, ?)",
                3, "required-outer"
            );
            worker.write(4, connection);

            throw new IllegalStateException("physical-failure");
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    private void printStatus(
            String label, Connection connection) throws SQLException {
        boolean physical =
            TransactionSynchronizationManager
                .isActualTransactionActive();
        boolean sync =
            TransactionSynchronizationManager
                .isSynchronizationActive();
        boolean bound =
            TransactionSynchronizationManager.hasResource(dataSource);

        System.out.println(
            label + " physical=" + physical +
            " sync=" + sync +
            " bound=" + bound +
            " autoCommit=" + connection.getAutoCommit());
    }
}
```

**Only create `SupportsFacade.java` from the second Java block**; the first block was an intermediate structural explanation that has now been completed. Do not put both into the same file. Making `printStatus` an instance method allows it to access the `dataSource` field to check the exact resource key.

The two methods differ only in outer's propagation. In both, inner is always `@Transactional(SUPPORTS)` and writes an identical INSERT. This lets us **verify the exact cause of the rollback difference**: whether or not a physical transaction was opened by outer.

### 6.4. SupportsApplication: enabling transaction advice and running SQL readback

**`src/main/java/learning/supports/SupportsApplication.java`**

```java
package learning.supports;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class SupportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupportsApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);

        manager.setTransactionSynchronization(
            AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS);

        return manager;
    }

    @Bean
    CommandLineRunner demo(SupportsFacade facade, JdbcTemplate jdbc) {
        return args -> {
            try {
                facade.noPhysicalTransaction();
            } catch (IllegalStateException ex) {
                System.out.println("support caught=" + ex.getMessage());
            }
            System.out.println("support rows=" + count(jdbc, 1, 2));

            try {
                facade.physicalTransaction();
            } catch (IllegalStateException ex) {
                System.out.println("required caught=" + ex.getMessage());
            }
            System.out.println("required rows=" + count(jdbc, 3, 4));
        };
    }

    private static int count(JdbcTemplate jdbc, int firstId, int lastId) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event WHERE id BETWEEN ? AND ?",
            Integer.class,
            firstId,
            lastId
        );
        return result;
    }
}
```

**Configuration explanation:**

- `@SpringBootApplication` scans `SupportsFacade` and `SupportsWorker` in the same package; Spring creates the beans rather than business code using `new`.
- `@EnableTransactionManagement(proxyTargetClass = true)` gives us class-based proxies suitable for classes that do not implement an interface.
- `transactionManager` is a **single bean** of `DataSourceTransactionManager` bound to the exact `DataSource` used by `JdbcTemplate`.
- `setTransactionSynchronization(SYNCHRONIZATION_ALWAYS)` ensures the SUPPORTS experiment without a backend transaction still opens a synchronization scope, without relying on implicit defaults.
- `CommandLineRunner` does **not** carry `@Transactional`, so the two tests run independently. Counts are executed only after the facade method has returned or its exception has propagated out of the proxy.
- `count(jdbc,1,2)` and `count(jdbc,3,4)` check disjoint IDs to avoid accidentally reading rows from the previous case.

The Java code in all three files shares the same package, and public class names match file names. `SQLException` from the facade methods can propagate out to the runner; `CommandLineRunner.run` declares `throws Exception`, so the lambda in `@Bean` compiles cleanly. Under normal demo conditions, no `SQLException` occurs, so only the deliberate `IllegalStateException` is caught.

### 6.5. Running the project

From the `supports-sync-demo` directory, with JDK 17+ and a compatible Gradle 8.x:

```bash
gradle bootRun
```

If you generated a compatible Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Spring/H2 dependencies must be downloaded into the Gradle cache (requires network on first run); do not run plain `javac SupportsApplication.java` since the libraries will be missing.

When running, ignore logs from Gradle, Hikari, and Spring Boot. The lines printed by the program in order are:

```text
support physical=false sync=true bound=true autoCommit=true
worker physical=false sync=true bound=true sameConnection=true autoCommit=true
support caught=no-physical
support rows=2
required physical=true sync=true bound=true autoCommit=false
worker physical=true sync=true bound=true sameConnection=true autoCommit=false
required caught=physical-failure
required rows=0
```

Main interpretation table:

| Measurement | SUPPORTS without T | Outer REQUIRED + inner SUPPORTS |
| --- | --- | --- |
| `isActualTransactionActive()` | `false` | `true` |
| `isSynchronizationActive()` | `true` | `true` |
| `hasResource(dataSource)` after `getConnection` | `true` | `true` |
| `worker` receives outer's exact connection object | `true` | `true` |
| `Connection.getAutoCommit()` | `true` | `false` |
| Two INSERTs then RuntimeException escapes facade proxy | No T to roll back; SQL auto-committed | Physical transaction rolls back both INSERTs |
| SQL count after method ends | `2` | `0` |

**The most important result is not `sameConnection=true`; it is that both have `sameConnection=true`, yet `rows=2` in one case and `rows=0` in the other.** It proves that binding/sharing a connection for synchronization **does not** automatically create a physical transaction or an atomic rollback guarantee.

## 7. Stepping through the SUPPORTS experiment in detail

### 7.1. SUPPORTS without a physical transaction

When the runner calls `facade.noPhysicalTransaction()`:

1. There is no transaction from the caller; `SUPPORTS` **does not open a new JDBC transaction**.
2. With `SYNCHRONIZATION_ALWAYS`, the interceptor/manager initializes a synchronization scope. We observe `physical=false, sync=true`.
3. `DataSourceUtils.getConnection(dataSource)` acquires an H2 connection with `autoCommit=true` and binds it to the thread. `hasResource(dataSource)` becomes true.
4. `JdbcTemplate` INSERTs `id=1` through the bound connection. H2 commits that statement under auto-commit.
5. `worker.write(2,connection)` passes through the proxy with SUPPORTS; there is no physical transaction, yet it inherits the synchronization scope, retrieves the same connection, and INSERTs `id=2`. The second statement also auto-commits.
6. Facade throws `IllegalStateException`. The transaction interceptor catches the runtime error, but **has no physical transaction to roll back**. It cleans up synchronization/resources.
7. The runner catches the exception and reads the DB: both `id=1` and `id=2` **still exist**, `support rows=2`.

Thus, a runtime exception in a `@Transactional(SUPPORTS)` method **does not mean data rolls back**. Rollback rules can only undo an actual physical transaction being managed; if every INSERT already auto-committed, throwing an error at the end of the method is too late to cancel them.

### 7.2. Outer REQUIRED, inner SUPPORTS

Next, the runner calls `facade.physicalTransaction()`:

1. There is no transaction from the caller, so `REQUIRED` creates physical transaction T; `DataSourceTransactionManager` uses a connection with `autoCommit=false`.
2. Facade INSERTs `id=3` **without committing**.
3. `worker.write(4,connection)` goes through the proxy; `SUPPORTS` sees T already exists and **joins T**. Worker receives the same connection, and its INSERT `id=4` also belongs to T.
4. Facade throws `IllegalStateException` escaping through the outer proxy. Spring evaluates default rollback rules for RuntimeException and requests rolling back T.
5. Both INSERTs in T are rolled back.
6. The runner reads after the transaction: `required rows=0`.

In this case, **inner SUPPORTS really is inside a physical transaction**, but because **outer created it**, not because SUPPORTS started T on its own.

### 7.3. Why not check the count while still inside the scope?

If you called `SELECT COUNT(*)` inside the facade before throwing the exception, JDBC transaction T could read `id=3` and `id=4` that it just wrote (*read-your-writes*). That **does not prove commit**. After rollback, the DB no longer has those two records.

Conversely, in the SUPPORTS case without T, auto-commit makes the records durable even before the exception. Placing the readback in the runner **after the facade proxy finishes** gives both cases reliable comparative evidence.

### 7.4. Why not rely on Throwable alone?

Both facade methods throw the same `IllegalStateException` type, both are caught by the caller, and both use Spring transaction advice. Looking at the exception class alone, you **cannot** distinguish the database outcomes.

It is the physical transaction boundary (present or absent) that determines whether the exception makes Spring roll back the SQL statements. The `2 vs 0` result is the observed data outcome of the demo under its designed conditions.

## 8. Try replacing SYNCHRONIZATION_ALWAYS with ON_ACTUAL_TRANSACTION

To explore synchronization's role, create a separate copy of the demo project or modify **only the manager configuration**:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

This is a change **in the demo project**, not to be applied arbitrarily in production. For a SUPPORTS method without a physical transaction:

- `isActualTransactionActive()` remains `false`.
- `isSynchronizationActive()` becomes `false`, because the manager does not create a synchronization scope for an "empty" transaction.
- `DataSourceUtils` does not automatically retain a shared connection based on SUPPORTS's synchronization scope; `sameConnection` may no longer be true and depends on pool/driver/resource acquisition.
- `autoCommit=true` may still remain per the demo's Hikari configuration; the INSERTs are not wrapped by a physical T.
- The exception at the end of the method still does not undo the two auto-committed INSERTs; `support rows` can still be 2 under the demo preconditions.
- In the `REQUIRED` case, a physical transaction is created so synchronization stays active, the SUPPORTS worker still joins T, and both roll back together.

**Do not prescribe `sameConnection=false` as a guaranteed output for the alternative configuration.** We cannot guarantee which connection object a specific pool hands out on every call. The point of this change is to observe **whether a synchronization scope is created**, not to force the pool to return different object instances.

If an application has multiple transaction layers or nests `REQUIRED` inside `SUPPORTS`, Spring's Javadoc recommends considering synchronization-only-on-actual-transaction to avoid certain runtime conflicts. Test the specific scenario on the manager in use.

## 9. SUPPORTS can be "non-transactional" yet still have synchronization callbacks

When synchronization is active, framework code can register a `TransactionSynchronization` for resource lifecycle or callbacks. However, for `SUPPORTS` without a backend transaction:

- Do not infer from a registered callback that a DB `BEGIN` occurred.
- Do not infer from a callback named "afterCommit" that the manager just committed a physical transaction. Synchronization scope lifecycle and physical transaction must be distinguished.
- Do not rely on a callback to emit an event **only when a record truly commits** while running under an "empty" synchronization scope without verifying manager semantics.
- If business logic needs an event after DB commit, verify there is an actual transaction, use the callback in the proper context, or design an outbox/transactional event properly.

Registering callbacks for resource cleanup is an infrastructure capability, not an ACID guarantee. When writing shared libraries, checking `isSynchronizationActive()` alone is insufficient to decide whether DB changes can roll back; check `isActualTransactionActive()` and the manager/resource in use.

## 10. `readOnly`, `timeout`, and `isolation` in SUPPORTS

### 10.1. `readOnly` does not replace a physical transaction

Example:

```java
@Transactional(
    propagation = Propagation.SUPPORTS,
    readOnly = true
)
public List<OrderView> findOrders() {
    return repository.findOrders();
}
```

This is an illustrative fragment, missing the repository and domain types. With an **already existing** physical transaction, SUPPORTS joins it and typically uses the outer transaction's characteristics; `readOnly` declared on inner does not automatically alter the already opened DB transaction's state (a manager can validate mismatches depending on configuration).

If **no physical transaction exists**, Spring can record **read-only metadata in the synchronization scope**, but that does not prove the JDBC connection was placed into a read-only DB transaction. Typically, read-only is a hint/optimization or enforcement dependent on driver, manager, and DB. Do not use a boolean on `TransactionSynchronizationManager` as a security barrier forbidding INSERTs.

### 10.2. `timeout`/`isolation` take effect when the manager opens T

`@Transactional`'s `isolation` and `timeout` typically apply to **a new physical transaction**, especially with `REQUIRED` or `REQUIRES_NEW`. SUPPORTS does not create T when none exists, so you cannot arbitrarily expect a transaction timeout or isolation level to be applied by the DB.

If SUPPORTS joins an outer T, the isolation/timeout established by outer's physical transaction usually remains in force; inner does not switch isolation on a connection already managed by the manager. With `validateExistingTransaction=true`, a manager can detect isolation/read-only mismatches and reject participation instead of silently ignoring them.

### 10.3. Do not use SUPPORTS just to "reduce locking"

A SELECT without a physical transaction is still subject to the DB's own isolation/auto-commit behavior; not every query is lock-free or immune to concurrency anomalies. A synchronization scope can also keep a connection held until the end of the method, putting pressure on the pool even without a long T. Measure query duration, connection lifetime, and data consistency on your specific DB.

If a use case needs a consistent snapshot across multiple queries, read-only `REQUIRED` with appropriate isolation may be a better choice than SUPPORTS. If only a single standalone query is needed, SUPPORTS or no annotation may suffice depending on infrastructure and codebase conventions.

## 11. SUPPORTS vs. REQUIRED, NOT_SUPPORTED, MANDATORY, and NEVER

| Propagation | When outer already has T | When outer has no T | Key distinction |
| --- | --- | --- | --- |
| `SUPPORTS` | Joins T | Creates no physical T; may create synchronization scope | Flexible to caller; atomicity depends on caller |
| `REQUIRED` | Joins T | Creates new physical T | Guarantees a transaction in intercepted calls |
| `REQUIRES_NEW` | Suspends outer and creates new T2 | Creates new physical T | Can commit/roll back independently |
| `NOT_SUPPORTED` | Suspends T and runs without physical T | Runs without physical T | Actively **avoids** participating in outer transaction |
| `MANDATORY` | Joins T | Throws error if T is missing | Forces caller to supply a transaction |
| `NEVER` | Throws error if T exists | Runs without physical T | Actively rejects any transaction |

**Do not equate SUPPORTS and NOT_SUPPORTED.** When outer has T, SUPPORTS **joins T**, whereas NOT_SUPPORTED **suspends T**. They are not "the same just because neither opens a new transaction".

**Do not equate SUPPORTS and MANDATORY.** SUPPORTS still runs when no physical T exists; MANDATORY actively throws an error to protect the use case's precondition.

**Do not equate SUPPORTS and "no annotation".** In `SYNCHRONIZATION_ALWAYS` mode, SUPPORTS can open a synchronization scope even when there is no DB transaction. A Java method completely unintercepted by transaction advice generally does not create a similar scope on its own, unless another caller/infrastructure opened it.

## 12. Nesting propagations: where SUPPORTS is easily misunderstood

### 12.1. Outer REQUIRED calling inner SUPPORTS

This is the **safest pattern to reason about**: outer created T, inner joins T; if outer rolls back, inner's SQL inside the same T also rolls back. Case R in the demo confirms this with data.

SUPPORTS is not limited to JDBC; with JPA it can also join a compatible transaction through the manager, though resource/session behavior must be checked for the respective manager/ORM.

### 12.2. Outer SUPPORTS without T calling inner REQUIRED

Architectural example:

```java
@Transactional(propagation = Propagation.SUPPORTS)
public void orchestrate() {
    readSomeData();
    writeService.writeTransactionally(); // REQUIRED on another bean
}
```

This is illustrative code. When outer has no T yet has activated synchronization, inner `REQUIRED` trying to open a physical transaction can cause **complex interactions with already bound resources**; Spring's Javadoc warns to use SUPPORTS carefully when nesting REQUIRED or REQUIRES_NEW and suggests synchronization-only-on-actual-transaction mode when necessary.

Do not describe this case simply as "REQUIRED definitely creates T and everything is fine" when a resource already exists from the SUPPORTS scope. It is better to **place the transaction boundary directly on the write use case**, clearly separate reading and writing, or configure/test the synchronization mode appropriate for the manager in use.

### 12.3. Outer SUPPORTS without T calling inner REQUIRES_NEW

An inner `REQUIRES_NEW` can open its own physical T, but if outer currently has an "empty" synchronization scope holding a connection, suspending/resuming synchronization and connection lifecycles must be handled properly by the manager. Pool connection demand can increase. If inner commits and outer continues executing non-transactional SQL statements, **there is no shared atomicity** between them.

### 12.4. Self-invocation does not create separate advice

In proxy mode, `@Transactional` is metadata applied only when calls pass through a Spring proxy. Calling `this.innerSupports()` within the same bean means the inner method **gets no separate transaction advisor invocation**, even if it continues using an active outer transaction/synchronization.

To verify two-scope semantics, use **two separate Spring beans** like `SupportsFacade` and `SupportsWorker`. Do not use `new SupportsWorker(...)` and assume the annotation will open a synchronization scope.

## 13. When is SUPPORTS valuable in real designs?

### 13.1. Read services called in both contexts

A query service might be called from both an existing transactional use case and a standalone endpoint:

```text
HTTP endpoint -> ReportService.findSummary() [SUPPORTS, no T]
Order workflow [REQUIRED T] -> ReportService.findSummary() [SUPPORTS, joins T]
```

When the caller has T, the report service reads inside the same transaction and can see the caller's uncommitted updates. When the caller has no T, the report does not open a new physical transaction on its own. This can be an intentional choice for simple queries.

However, if the two environments require very different consistency levels, sharing a single SUPPORTS contract can make behavior hard to predict. Document the preconditions clearly or separate standalone query APIs from queries serving business transactions.

### 13.2. Resource sharing within a request/service scope

Some applications want multiple JDBC/Hibernate operations within a scope to reuse resources without forcing every query into a physical transaction. With `SYNCHRONIZATION_ALWAYS`, SUPPORTS can support that resource lifecycle.

In return, the resource may be held until the end of the scope, impacting pool usage and latency. Measure actual resources; do not treat resource sharing as a free benefit.

### 13.3. Distinguishing ability to proceed from atomicity

SUPPORTS can allow a method to "use a transaction if the caller has one". It does not mean partial failure of internal operations is acceptable. If the business logic **cannot tolerate partial writes**, do not let a multi-step write method run under SUPPORTS without an outer transaction.

In particular, do not put SUPPORTS on an order-creation method writing multiple tables assuming "it has `@Transactional` so it rolls back". If the steps must commit together, use `REQUIRED` at the proper boundary and test rollback from the real caller.

## 14. Common mistakes and how to diagnose them

### Mistake 1 — Seeing `syncActive=true` and concluding a DB transaction is active

Wrong: `isSynchronizationActive()` measures the synchronization scope; with SUPPORTS without T, it can still be true. Check `isActualTransactionActive()` and the real connection/manager.

### Mistake 2 — Seeing the same JDBC Connection and trusting two INSERTs will roll back together

Wrong: when the connection has `autoCommit=true`, each INSERT can commit individually. The demo's `SUPPORTS` test showed the same connection yet `rows=2` after a RuntimeException.

### Mistake 3 — Asserting only the exception without checking the DB

An `IllegalStateException` is thrown in both the SUPPORTS and REQUIRED cases, yet the remaining data is completely different. Query SQL **after the method has finished** to evaluate accurately.

### Mistake 4 — Putting `@Transactional(SUPPORTS)` on a multi-step write method needing atomicity

If the caller has no T, SUPPORTS does not create T on its own. Place `REQUIRED` on the use case boundary, or mark methods that must be called inside T with `MANDATORY`.

### Mistake 5 — Using raw `dataSource.getConnection` or closing improperly

This can create connections outside thread-bound resources and break synchronization; use `JdbcTemplate`/`DataSourceUtils` or proper data access infrastructure and release resources properly.

### Mistake 6 — Treating `readOnly=true` as a guarantee the DB is in a read-only transaction

Read-only metadata in a synchronization scope does not guarantee a physical transaction exists. Check the manager/driver/DB and actual data permissions.

### Mistake 7 — Spawning threads inside SUPPORTS

A new thread does not automatically inherit the current thread's transaction synchronization in imperative Spring. `syncActive` and resource reuse behavior can change.

### Mistake 8 — Changing synchronization mode without testing libraries relying on resource binding

`SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` prevents SUPPORTS without T from creating a synchronization scope. Libraries relying on holders/callbacks may behave differently. Test end-to-end flows.

### Mistake 9 — Assuming SUPPORTS and NOT_SUPPORTED are equivalent

When an outer transaction exists, SUPPORTS joins while NOT_SUPPORTED suspends. This affects SQL visibility, rollback, and resource handling.

### Mistake 10 — Testing only inside a `@Transactional` test method

The test's transaction may already be active, making every SUPPORTS call look like it "always has T" and hiding the risky production case **with no physical transaction**. Verify the path with no outer T as well.

## 15. How to test properly without false positives

A good test for SUPPORTS should separate two questions:

**Question 1: Does synchronization/resource sharing take place?**

- Call a `@Transactional(SUPPORTS)` method with no outer transaction.
- Print `isSynchronizationActive()` and `isActualTransactionActive()`.
- Acquire the connection via `DataSourceUtils` in the facade, pass the reference to the worker, and compare with the connection the worker retrieves from the same DataSource.
- Check `getAutoCommit()` to know the experiment's DB condition.
- Switch manager mode from ALWAYS to ON_ACTUAL_TRANSACTION and observe the difference in synchronization.

**Question 2: Can the SQL changes roll back?**

- Within the same flow, INSERT records in two different classes and then throw RuntimeException **after the INSERTs**.
- Catch the exception **in the caller outside the proxy**.
- Query the DB again after the scope finishes; with SUPPORTS without T and `autoCommit=true`, the records still exist.
- Switch outer to REQUIRED while keeping the SUPPORTS worker unchanged; after the exception, records belonging to T are rolled back.
- Do not rely only on `assertThrows` or logs; assert DB state.

### 15.1. The Spring TestContext trap

If a test method has `@Transactional`, Spring TestContext can open a transaction and roll it back at the end of the test. Then SUPPORTS **joins the test's transaction**, and the test no longer represents a production call without T.

To test the "no physical transaction" case, use a test method **without `@Transactional`**, call the Spring bean through its proxy, and verify data after the method throws an exception. If you need to test multiple scopes, use `TestTransaction` carefully to start/end appropriate transactions.

### 15.2. Testing the same database with different resource keys?

`TransactionSynchronizationManager.hasResource(dataSource)` uses the specific `DataSource` object instance as the resource key. If code A uses a different DataSource proxy wrapper or beans are configured with mismatched keys as recognized by the framework, binding/reuse may not behave as expected. The demo deliberately injects the exact same `DataSource` into all three classes.

### 15.3. Testing concurrent/long-running scopes too

A synchronization scope can hold a connection for an extended time even without a physical transaction. If a SUPPORTS method calls a network API and then continues querying, its connection may be held while waiting. Under concurrent requests, monitor Hikari active/idle/waiting counts, timeouts, and data access boundaries to avoid pool starvation.

## 16. Logging and observability in a running system

You can temporarily enable logs to inspect Spring's transaction interceptor and JDBC manager:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.jdbc.datasource.DataSourceUtils=DEBUG
```

This is an **optional debug configuration fragment**. You do not need to add these lines to the demo's `application.properties` to reproduce the `System.out` output above.

When reading logs, distinguish:

- "Creating new transaction" on the manager when outer REQUIRED actually starts physical T.
- "Participating in existing transaction" when SUPPORTS is called inside an existing T.
- A SUPPORTS scope without T may only activate synchronization, which is not equivalent to a DB BEGIN.
- Resource binding/cleanup is lifecycle; it does not prove commit.
- If a DB error occurs, verify the post-method SQL outcome — especially on commit/network errors where the outcome is uncertain.

Do not enable SQL logging containing sensitive data in production just to inspect propagation. Use scoped tracing and lower log levels once verified.

## 17. Checklist before choosing SUPPORTS

Answer these questions:

1. Is this method **read-only**, or can it perform multiple write steps requiring atomicity?
2. When called from a standalone endpoint, **is there an existing physical transaction**?
3. Should it only join if the caller has a transaction? If a transaction is needed in all cases, `REQUIRED` may fit better.
4. Which synchronization mode does the transaction manager use: ALWAYS, ON_ACTUAL_TRANSACTION, or NEVER?
5. Do all data accesses use the same `DataSource`/`EntityManagerFactory` and resource management infrastructure?
6. Does the service need to share a connection/session in a scope without T? How long will the resource be held?
7. Is anyone assuming a runtime exception will roll back auto-committed write steps?
8. Is there a call chain nesting REQUIRED or REQUIRES_NEW inside SUPPORTS? Have resource synchronization conflicts been tested?
9. Are `@Async`, other threads, or non-DB resources used where the transaction context does not propagate automatically?
10. Do tests **read DB state after the boundary**, both with and without an outer transaction, rather than checking only exceptions?

**Rule:** `SUPPORTS` is a *"join if present"* policy, not *"always has a transaction, just lighter"*. Synchronization manages resource scope; only a physical transaction provides atomic rollback/commit of the DB operations within that scope.

## 18. Self-check questions

**Question 1.** `@Transactional(SUPPORTS)` is called with no outer T, yet `isSynchronizationActive()==true`. Does that prove a physical transaction started?

**Answer:** No. With `SYNCHRONIZATION_ALWAYS`, Spring can open synchronization for an "empty" SUPPORTS scope while `isActualTransactionActive()==false`.

**Question 2.** Two SUPPORTS services share the same JDBC Connection. If `IllegalStateException` is thrown at the end of the method, are both INSERTs guaranteed to roll back?

**Answer:** No. Without a physical T and with connection `autoCommit=true`, each INSERT can commit individually. Connection identity does not equal transaction atomicity.

**Question 3.** Inner SUPPORTS is called by outer REQUIRED through a Spring proxy with the same DataSource. Does inner have a physical transaction?

**Answer:** It **joins the physical transaction opened by outer**, without creating its own T. An outer rollback can revert inner's SQL inside T.

**Question 4.** Switching the transaction manager from ALWAYS to ON_ACTUAL_TRANSACTION, what will `syncActive` be for SUPPORTS without T?

**Answer:** Spring does not open a new synchronization scope solely for SUPPORTS, so `syncActive=false` in a standalone call. Actual transaction remains false.

**Question 5.** What does `hasResource(dataSource)==true` indicate?

**Answer:** Spring has bound a resource to the current thread under the DataSource key. It does **not** prove the JDBC connection has `autoCommit=false` or that the DB has a physical transaction.

**Question 6.** Are SUPPORTS and NOT_SUPPORTED the same when outer REQUIRED has opened T?

**Answer:** No. SUPPORTS joins T; NOT_SUPPORTED actively suspends T and runs without a physical transaction.

**Question 7.** When should REQUIRED be preferred over SUPPORTS?

**Answer:** When the use case must guarantee a physical transaction for multiple write steps to commit/roll back together, even when the initial caller has no transaction.

**Question 8.** Why should you not test SUPPORTS solely inside a `@Transactional` test method?

**Answer:** Because the test already supplies an outer transaction. SUPPORTS will join the test's T, hiding the production case where it is called standalone without T.

**Question 9.** If a library registers a synchronization callback during SUPPORTS without T, can that callback be treated as proof of DB commit?

**Answer:** No. It may only be lifecycle synchronization scope; you must check the actual transaction and actual DB commit.

## 19. Official Spring references

- `Propagation.SUPPORTS` Javadoc (including synchronization scope notes): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- `AbstractPlatformTransactionManager` Javadoc (SYNCHRONIZATION_ALWAYS, ON_ACTUAL_TRANSACTION, NEVER): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- `DataSourceUtils` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html

**Conclusion:** `SUPPORTS` does not open a physical transaction when none exists, yet **can** open a synchronization scope, bind, and reuse a JDBC Connection. Observing `sync=true, physical=false, sameConnection=true, autoCommit=true` while INSERTed data **survives an exception** demonstrates the difference between **resource synchronization** and **a rollback-capable physical transaction**. When outer `REQUIRED` opens T, the exact same inner `SUPPORTS` joins T and SQL statements can roll back together; therefore transaction boundaries must be designed around business requirements, not merely annotations or synchronization flags.