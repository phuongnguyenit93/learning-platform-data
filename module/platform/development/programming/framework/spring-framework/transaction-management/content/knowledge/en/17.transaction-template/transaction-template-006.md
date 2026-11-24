# Declaring `propagation`, `isolation`, `readOnly`, and `timeout` with `TransactionTemplate`

## Objectives

`TransactionTemplate` is Spring Framework's **programmatic** transaction management API, designed for imperative flows. This lesson focuses on how to **accurately declare the four transaction properties** and understand the conditions under which they actually take effect.

After this lesson, you can:

1. Create a `TransactionTemplate` from a `PlatformTransactionManager` and configure `setPropagationBehavior`, `setIsolationLevel`, `setReadOnly`, and `setTimeout`.
2. Recognize the defaults: `REQUIRED`, `DEFAULT`, `readOnly=false`, `TIMEOUT_DEFAULT=-1`.
3. Distinguish the values declared on the template from the **physical transaction** state when the callback runs.
4. Predict the behavior of `REQUIRED` when joining an existing transaction, `REQUIRES_NEW` when an independent transaction is needed, `NESTED` with savepoints, and the remaining propagation behaviors.
5. Know that `isolation`, `readOnly`, and `timeout` are meaningful primarily **when a new physical transaction starts**, and depend on the transaction manager/driver/DBMS.
6. Safely apply the same `TransactionTemplate` across multiple callbacks without mutating configuration at runtime.
7. Run a **Java 17+ / Spring Boot 3.3.5 / Spring JDBC / H2** project, observe isolation and read-only on a real connection, verify commit/rollback, and write JUnit 5 tests.
8. Distinguish exception handling and `status.setRollbackOnly()` inside a callback from the rollback rules of the `@Transactional` annotation.

**Focus:** declaring **all four properties** with `TransactionTemplate`; propagation, JDBC isolation, timeout, and AOP topics are explained just enough to understand configuration and practical limits.

---

## 1. Why Use `TransactionTemplate`?

In Spring there are two common styles:

**Declarative** — placing `@Transactional` on a method so a Spring AOP proxy creates the transaction boundary:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true,
    timeout = 15
)
public Report calculateReport() {
    // ...
}
```

**Programmatic** — explicitly wrapping **a specific block of code** with `TransactionTemplate.execute(...)`:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
template.setReadOnly(true);
template.setTimeout(15);

Report report = template.execute(status -> calculateReport());
```

The two snippets above **only illustrate the API**, assuming `transactionManager`, `Report`, and `calculateReport()` already exist. The full runnable program is in section 10.

`TransactionTemplate` is suitable when you need to:

- Place a transaction around **a small block** within a long method rather than around the entire method.
- Choose dedicated propagation/isolation for each orchestrated operation.
- Return a result from the callback or mark rollback-only based on business conditions.
- Avoid depending on whether an internal method call goes back through a Spring AOP proxy.
- Organize multiple clearly bounded units of work directly within an imperative Java flow.

It **does not** make a transaction independent of underlying resources or automatically protect against all JDBC issues. `TransactionTemplate` only coordinates the provided `PlatformTransactionManager`, so the final effective behavior depends on the **manager, datasource, driver, DBMS, and existing transaction**.

### Three Objects with Different Roles

| Object | Role |
| --- | --- |
| `PlatformTransactionManager` | Actually begins, commits, rolls back, suspends/resumes the appropriate transaction |
| `TransactionTemplate` | Holds the transaction definition and wraps a callback by calling the manager |
| `TransactionStatus` | Represents the currently executing transaction scope: `isNewTransaction()`, `isRollbackOnly()`, `setRollbackOnly()`... |

`TransactionTemplate` **is not** a database connection. Nor does it **automatically create a transaction** when the constructor runs. The manager is only asked to create/join a transaction when `execute()` or `executeWithoutResult()` is called.

## 2. The Four Properties and Default Values

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_DEFAULT);
tx.setReadOnly(false);
tx.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
```

The four setter lines above merely repeat the standard defaults; writing them is optional. `TransactionDefinition.TIMEOUT_DEFAULT = -1` indicates using the infrastructure's default timeout (or no timeout when unsupported), **not always -1 seconds**.

| Property | Setter | Default | Meaning |
| --- | --- | --- | --- |
| Propagation | `setPropagationBehavior(int)` | `PROPAGATION_REQUIRED` (`0`) | Starts a transaction when none exists; joins a suitable existing transaction |
| Isolation | `setIsolationLevel(int)` | `ISOLATION_DEFAULT` (`-1`) | Does not request a specific isolation level; uses resource default |
| Read-only | `setReadOnly(boolean)` | `false` | Read/write transaction by default; `true` is an infrastructure-dependent hint/optimization |
| Timeout | `setTimeout(int)` | `TIMEOUT_DEFAULT` (`-1`) | Uses the default timeout of the transaction manager/resource |
 
Default properties **do not depend on the constructor taking the manager** or how the template is injected as a bean. If different characteristics are desired, configure them before the template is shared.

### Configuring All Four Properties

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class TemplateFactory {

    public static TransactionTemplate newReportTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(true);
        tx.setTimeout(15); // unit: seconds
        tx.setName("report.read");
        return tx;
    }
}
```

This is a **Java 17 class that compiles when Spring Transaction is on the classpath**, though it needs a real manager and caller to execute callbacks. `setName` is an optional extra property, useful for diagnostics, not one of the four primary properties.

The next snippet uses the template:

```java
TransactionTemplate readTx = TemplateFactory.newReportTemplate(manager);
String result = readTx.execute(status -> readFromRepository());
```

The callback can return any value matching generic `T`; `execute()` returns that value when the transaction finishes validly. If transaction commit fails, `execute()` may **throw an exception instead of returning the result**.

## 3. Declaring with Constant Integers or Constant Names?

`TransactionTemplate` inherits configuration from `DefaultTransactionDefinition`, so there are two ways to express it.

### `int` Constants

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_REPEATABLE_READ
);
tx.setReadOnly(true);
tx.setTimeout(30);
```

### `String` Constant Names

```java
tx.setPropagationBehaviorName("PROPAGATION_REQUIRES_NEW");
tx.setIsolationLevelName("ISOLATION_REPEATABLE_READ");
tx.setReadOnly(true);
tx.setTimeout(30);
```

Both approaches express the same configuration intent. Incorrect names will be rejected by Spring validation; do not pass arbitrary values like `"REQUIRES_NEW"` when this API expects the constant name `"PROPAGATION_REQUIRES_NEW"`.

When using annotations, the API uses **enums**:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true,
    timeout = 30
)
```

When using `TransactionTemplate`, setters accept **`int`/constant names**, not the `Propagation` or `Isolation` enums directly. If you want to use enums for consistent expression, you can pass `.value()` when supported by the API version, though `TransactionDefinition` constants are clear and easy to look up in documentation.

## 4. `setPropagationBehavior`: Deciding the Relationship with an Existing Transaction

This property takes effect **before** considering the other three properties, because whether a callback starts a new transaction depends on propagation.

### 4.1. `PROPAGATION_REQUIRED` (default)

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
```

- **No existing transaction:** the manager creates a new physical transaction.
- **Compatible transaction already exists:** the callback joins that physical transaction without creating a new one.
- If the callback is a participant, the template's own isolation/read-only/timeout **do not automatically override** transaction characteristics already established by the owner under default manager configuration.
- If the participant encounters an error leading to rollback-only, the entire shared transaction may become uncommittable; the owner may receive `UnexpectedRollbackException` when attempting to commit.

`REQUIRED` fits steps that need shared atomicity: if one required step fails, the entire unit of work rolls back.

### 4.2. `PROPAGATION_REQUIRES_NEW`

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
```

- Opens a **separate physical transaction** for the callback.
- If an outer transaction already exists, the manager suspends the outer context before opening the inner one, then resumes outer after inner finishes.
- New isolation/read-only/timeout on the template have the chance to be applied to this independent transaction.
- Inner can commit even if outer later rolls back; conversely, inner rolling back does not automatically roll back outer.
- With JDBC, a **second connection** may be needed while outer still holds its connection; the connection pool must be large enough.

Do not use `REQUIRES_NEW` merely to make a SQL query faster. It changes **atomicity** and the commit order of business steps.

### 4.3. `PROPAGATION_NESTED`

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NESTED
);
```

- When the manager and JDBC driver support savepoints, an inner callback can create a savepoint within the **same physical transaction**.
- Rolling back inner can revert to the savepoint while outer continues the transaction.
- When there is no outer transaction, `NESTED` usually starts a new transaction just like `REQUIRED`.
- `NESTED` does not create an independent isolation/timeout/read-only policy for an already existing physical transaction.
- Do not assume JPA/JTA or every driver supports nested transactions.

It fits when business rules allow **discarding an optional piece of data** while still committing the preceding/following parts, but requires testing on the actual transaction manager.

### 4.4. Other Propagations

| Constant | When an outer transaction exists | When no outer transaction exists |
| --- | --- | --- |
| `PROPAGATION_SUPPORTS` | Joins transaction if compatible | Runs without a new physical transaction |
| `PROPAGATION_MANDATORY` | Must join | Throws error due to missing transaction |
| `PROPAGATION_NOT_SUPPORTED` | Suspends transaction and runs without a transaction | Runs without a transaction |
| `PROPAGATION_NEVER` | Throws error when a transaction exists | Runs without a transaction |
| `PROPAGATION_REQUIRED` | Joins | Creates transaction |
| `PROPAGATION_REQUIRES_NEW` | Suspends and creates a new transaction | Creates transaction |
| `PROPAGATION_NESTED` | Uses savepoint if supported | Creates transaction |

`NOT_SUPPORTED`/`SUPPORTS` do not guarantee every "non-transactional" JDBC statement immediately uses the same JDBC connection; transaction synchronization and resource binding have manager-dependent details. However, **they do not open a new physical transaction just to apply isolation/readOnly/timeout**.

**Rule to remember:** propagation decides "create/join/suspend/no transaction" before you can reason about the remaining properties.

## 5. `setIsolationLevel`: Isolation Level of the Physical Transaction

```java
tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
```

Spring constants:

| Constant | Value | Notes |
| --- | ---: | --- |
| `ISOLATION_DEFAULT` | `-1` | Use the existing/default isolation of the resource |
| `ISOLATION_READ_UNCOMMITTED` | `1` | May be promoted/mapped by the database to a stronger level |
| `ISOLATION_READ_COMMITTED` | `2` | Does not read uncommitted data per supported semantics |
| `ISOLATION_REPEATABLE_READ` | `4` | Repeatable read capability depends on the DBMS |
| `ISOLATION_SERIALIZABLE` | `8` | Highest isolation level in the standard JDBC enum |

The four concrete levels correspond to `java.sql.Connection.TRANSACTION_*`. `ISOLATION_DEFAULT=-1` **is not** a JDBC isolation level; Spring treats it as **no override requested**.

### When Does Isolation Apply?

Suppose an outer callback has started a JDBC transaction T at `READ_COMMITTED`:

```java
TransactionTemplate outer = new TransactionTemplate(manager);
outer.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
outer.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);

TransactionTemplate inner = new TransactionTemplate(manager);
inner.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
inner.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE
);

outer.execute(outerStatus -> {
    inner.execute(innerStatus -> {
        // Still joins existing T; usually READ_COMMITTED.
        return null;
    });
    return null;
});
```

Even though `inner` declares `SERIALIZABLE`, it uses `REQUIRED` and thus **joins T**. With default managers, a participant's own isolation does not upgrade the isolation of T's connection. To get independent isolation, you must create a genuinely new transaction **and** accept the atomicity difference; or request the right isolation directly on the outer transaction owner.

### Detecting Mismatches with `validateExistingTransaction`

`AbstractPlatformTransactionManager` supports configuring:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

If this manager is used and an inner `REQUIRED` requests an isolation incompatible with existing T, it can reject joining with `IllegalTransactionStateException`. Do not enable this flag without testing call chains that rely on joining despite differing inner declarations.

### Actual Isolation Depends on the Resource

For instance, H2 defaults typically to `READ_COMMITTED`, PostgreSQL also typically defaults to `READ_COMMITTED`, while MySQL InnoDB typically uses `REPEATABLE_READ`. However, the connection pool/driver/session can change it. To know the physical isolation in a JDBC transaction, measure **the exact connection bound by Spring**:

```java
Integer actual = jdbcTemplate.execute(
    (ConnectionCallback<Integer>) Connection::getTransactionIsolation
);
```

This is a snippet requiring full imports/beans as in the demo. Do not borrow another connection from the pool and treat it as the current transaction's isolation.

## 6. `setReadOnly`: A Hint for the Manager/Driver/Database

```java
tx.setReadOnly(true);
```

With `DataSourceTransactionManager`, Spring may call JDBC `Connection.setReadOnly(true)` when starting a new transaction. The driver/DBMS may use this hint to optimize, treat it as policy, or **ignore it**.

**There is no universal guarantee** that `tx.setReadOnly(true)` causes every `INSERT`, `UPDATE`, `DELETE` to fail:

- H2's `JdbcConnection.setReadOnly(true)` on a writable in-memory DB may be ignored; `Connection.isReadOnly()` still returns `false`.
- A database with a SQL-level read-only transaction mechanism may reject DML when that mode is enabled.
- With `JpaTransactionManager`/Hibernate, the read-only flag can affect flush mode and dirty checking.
- With a custom manager, this value may only be used as metadata or a routing hint.
- `readOnly=true` **does not replace `SELECT`-only permissions on the database user**.

To observe Spring context:

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

To observe the JDBC driver:

```java
Boolean jdbcReadOnly = jdbcTemplate.execute(
    (ConnectionCallback<Boolean>) Connection::isReadOnly
);
```

The two values **can differ**. `springReadOnly=true` means Spring is publishing the transaction as read-only, not proving the database blocks writes.

### When `REQUIRED` Joins an Already Open Transaction

If outer T is read-write and an inner template sets `readOnly=true` while using `REQUIRED`, inner **usually inherits T's policy**. The Spring flag in the inner context can still be `false`. Conversely, an inner `readOnly=false` joining a read-only outer does not automatically open a writable physical transaction.

In the demo, we intentionally create a `REQUIRED` template declaring `readOnly=true` and call it inside a read-write outer transaction. The resulting Spring flag inside inner remains `false`, making this principle clear.

### Want the Database to Actually Forbid Writes?

With Spring JDBC and a suitable DBMS, `DataSourceTransactionManager#setEnforceReadOnly(true)` can issue **`SET TRANSACTION READ ONLY`** when starting a new transaction. SQL support depends on the DBMS, session settings, and driver. In production, if the goal is **security**, use restricted DB privileges or a read-only account/replica, not just a hint on the template.

This lesson's example program uses H2 and **does not enable SQL enforce read-only**, as it focuses on configuring the four properties and their actual effect.

## 7. `setTimeout`: Seconds, Defaults, and Practical Limits

```java
tx.setTimeout(15); // 15 seconds
```

`TransactionTemplate#setTimeout(int)` takes a number of seconds. Default:

```java
tx.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT); // -1
```

`-1` means **use the default timeout decided by the manager/resource or none**. It does not install a Java timer that automatically halts all code at the exact instant.

### Where Does Timeout Apply?

- **New transaction:** the manager can establish a corresponding deadline.
- **`REQUIRED` joining an existing transaction:** the inner template's timeout setting **does not reset the deadline** of outer T.
- **`REQUIRES_NEW`:** the new transaction can use its own timeout.
- **`NESTED` on the same T:** a savepoint does not create a physical transaction with an independent deadline.
- **Propagations running without T:** timeout does not turn a non-transactional callback into a new transaction.

`DataSourceTransactionManager` and `JdbcTemplate` can coordinate **transaction timeout with JDBC statement timeout**. `JdbcTemplate` uses the transaction context to set the remaining timeout on `Statement`s when appropriate. The JDBC driver/DBMS decides the ability to interrupt a running query, and a CPU-bound Java operation or `Thread.sleep()` is not guaranteed to be interrupted at the exact expiration second.

### Clear-Intent Timeout Example

```java
TransactionTemplate shortTx = new TransactionTemplate(manager);
shortTx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
shortTx.setTimeout(3);
shortTx.executeWithoutResult(status -> performDatabaseWork());
```

This is a snippet needing `manager` and `performDatabaseWork()` from the application. In tests, do not assert that a `Thread.sleep(3001)` **definitely** throws an exception: transaction timeout is not wall-clock Java thread cancellation. If real verification is needed, run an integration test with a DBMS, driver, a query that can be timed out, and an appropriate deadline; do not rely on test machine latency.

### Timeout Does Not Replace Network Timeouts or SLAs

- `HikariCP.connectionTimeout` limits **wait time for a connection from the pool**, which is distinct from transaction timeout.
- JDBC `Statement.setQueryTimeout()` limits **processing time of a single statement**, with driver-dependent enforcement.
- HTTP client timeout limits a network request, which is not synonymous with DB rollback.
- Transaction timeout limits transaction duration per the transaction manager/resource and its enforcement mechanism.

To prevent transactions from holding connections/locks too long, combine query timeouts, network timeouts, queue limits, retry logic, scoped transaction boundaries, and observability.

## 8. Standard Configuration Pattern: One Template per Policy

Because `TransactionTemplate` holds properties mutable via setters, it is best configured **once** during bean/constructor initialization.

```java
@Configuration
class TransactionPolicyConfiguration {

    @Bean("readerTx")
    TransactionTemplate readerTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(true);
        tx.setTimeout(10);
        return tx;
    }

    @Bean("auditTx")
    TransactionTemplate auditTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_DEFAULT
        );
        tx.setReadOnly(false);
        tx.setTimeout(5);
        return tx;
    }
}
```

This is an **illustrative configuration snippet**; it needs Spring imports and a suitable manager. Do not copy this snippet into the project in section 10 because that project already defines its own beans.

The two beans have different policies:

- `readerTx`: read-only transaction only when newly opened; if joining a writable outer T, the inner policy does not necessarily have independent effect.
- `auditTx`: independent new transaction, read-write; it **can commit even if the outer caller rolls back**, a characteristic that business rules must permit.

**Do not use one singleton template and change setters per request:**

```java
// Anti-pattern: avoid doing this when the template is shared.
sharedTx.setReadOnly(request.isReadOnly());
sharedTx.setTimeout(request.timeoutSeconds());
sharedTx.execute(status -> doWork(request));
```

If two threads run concurrently, thread A can alter the configuration that thread B thinks it is using. **`TransactionTemplate` is thread-safe when executing callbacks with a stable configuration**, yet setters mutate configuration state; it is not "an independent definition per call".

Solution: define **multiple preconfigured templates**, or construct a new instance (where truly necessary) for a genuinely dynamic policy. The latter approach should be paired with validation because timeout/isolation directly from requests can become a performance and consistency risk.

### Creating a Template from `DefaultTransactionDefinition`?

`TransactionTemplate` itself extends `DefaultTransactionDefinition`, so calling setters directly as above is valid and concise. `TransactionTemplate` does not have a universal constructor accepting arbitrary `TransactionDefinition`s and copying every property under some imagined callback style; read the exact Javadoc for your Spring version if using another overload.

## 9. Callbacks, Results, and Rollback Policy

When running:

```java
String orderId = tx.execute(status -> {
    insertOrder();
    insertOrderLines();
    return "ORDER-100";
});
```

`execute()` obtains an appropriate transaction status, runs the callback, and commits/rolls back according to the outcome. The callback can inspect:

```java
boolean newPhysicalTx = status.isNewTransaction();
boolean markedRollback = status.isRollbackOnly();
```

### Returning a Normal Result

```java
Result result = tx.execute(status -> {
    writeTwoRecords();
    return Result.ok();
});
```

This is a snippet assuming `Result` and `writeTwoRecords()` are defined in the application. Normal `return` usually leads to **commit** if a new transaction is owned, not marked rollback-only, and no manager/DB error occurs.

### Throwing an Unchecked Exception to Roll Back

```java
tx.executeWithoutResult(status -> {
    writeFirstRecord();
    throw new IllegalStateException("Cannot finish operation");
});
```

With a new transaction, Spring `TransactionTemplate` handles unchecked exceptions/Errors by rolling back and rethrowing. If code outside the callback catches the exception **after `execute()`**, the transaction manager has already had the chance to roll back before the catch.

### Proactively Calling `status.setRollbackOnly()`

```java
Result result = tx.execute(status -> {
    writeFirstRecord();

    if (!businessRuleSatisfied()) {
        status.setRollbackOnly();
        return Result.rejected();
    }

    writeSecondRecord();
    return Result.accepted();
});
```

This approach is useful when the contract requires **returning a failure Result** instead of throwing an exception. With a new transaction owned by the template, it rolls back before returning the result. If the template joins an enclosing transaction, the rollback-only flag can propagate to the shared transaction; the outer caller may receive `UnexpectedRollbackException` when trying to commit.

### Checked Exceptions Inside Callbacks

The `TransactionCallback<T>.doInTransaction(TransactionStatus)` interface **does not declare `throws IOException`**. Therefore, you cannot write `throw new IOException(...)` directly inside an `execute(...)` lambda without catching/wrapping under Java checked exception rules.

```java
try {
    return tx.execute(status -> {
        try {
            return readFromExternalSource(); // may throw IOException
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    });
} catch (java.io.UncheckedIOException ex) {
    // Callback threw an unchecked exception through TransactionTemplate.
    throw ex;
}
```

This is a snippet assuming `readFromExternalSource()` and `tx` exist. You can use `status.setRollbackOnly()` and return a failure result if you want to handle the checked exception **inside** the callback.

Important distinction: do not copy `@Transactional`'s default **"checked exceptions do not roll back"** rule verbatim onto callbacks and extrapolate. You must consider **what errors can escape `TransactionCallback`**, how you wrap them, and how `TransactionTemplate.execute` dispatches exceptions. `TransactionTemplate` has no `rollbackFor` attribute like the annotation; the callback code itself controls conversion or rollback-only.

## 10. Runnable Project: Declaring All Four Properties, Observing Real Effect

### 10.1. Experiment Objectives

The project consists of **five preconfigured templates**, focusing on the four properties:

1. `defaultTx`: no properties set; verifies defaults.
2. `outerTx`: `REQUIRED`, `READ_COMMITTED`, `readOnly=false`, `timeout=15`.
3. `joinTx`: `REQUIRED`, `SERIALIZABLE`, `readOnly=true`, `timeout=2`, called from an open `outerTx`.
4. `separateTx`: `REQUIRES_NEW`, `SERIALIZABLE`, `readOnly=true`, `timeout=4`.
5. `queryTx`: `REQUIRED`, `DEFAULT`, `readOnly=true`, `timeout=8`, called with no active transaction.

H2 is connected via HikariCP; the pool is configured with **baseline `REPEATABLE_READ`** to show that `ISOLATION_DEFAULT` picks up the connection/resource's isolation rather than automatically choosing `READ_COMMITTED`. When `outerTx` requests `READ_COMMITTED`, the Spring JDBC manager temporarily changes the isolation of the connection belonging to the new transaction, then restores it afterward.

We will demonstrate with custom log lines:

- `joinTx` **does not** alter the isolation, read-only flag, or timeout of the existing outer physical transaction.
- `separateTx` uses a new transaction so its `SERIALIZABLE` isolation request and separate Spring read-only flag have a chance to apply.
- H2 may ignore JDBC `setReadOnly(true)`, hence `springRO=true` while `jdbcRO=false`.
- `TransactionTemplate.execute()` throwing an exception rolls back; `setRollbackOnly()` can roll back while still returning a meaningful `Result`.

**Note on timeout:** the demo prints the template's **configured** timeout value and passes timeout to the manager, without attempting to write a flaky wall-clock test. Do not claim that running in under 2/4/15 seconds proves the driver's enforced timeout mechanism.

### 10.2. Project Structure

```text
transaction-template-properties/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/template/
    │   │   ├── TemplateConfig.java
    │   │   ├── TemplateScenarioService.java
    │   │   └── TransactionTemplateDemoApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/template/
        └── TransactionTemplateDemoTest.java
```

Create a Java 17+ Gradle project from Spring Initializr (Spring Boot 3.3.5), with the wrapper. Add the files with exact names and packages. No web server or external database connection is needed.

### 10.3. `settings.gradle`

```groovy
rootProject.name = 'transaction-template-properties'
```

### 10.4. `build.gradle`

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

`spring-boot-starter-jdbc` provides Spring transaction APIs, `JdbcTemplate`, and HikariCP. H2 is used as the in-memory DB. Do not add `spring-boot-starter-web` just to run a transaction demo.

### 10.5. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:template_properties;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
      transaction-isolation: TRANSACTION_REPEATABLE_READ
  sql:
    init:
      mode: always
```

The pool baseline is `TRANSACTION_REPEATABLE_READ`. Configuring `maximum-pool-size=4` lets `REQUIRES_NEW` borrow an additional connection while outer still holds one connection. With a pool of size one, nested `REQUIRES_NEW` inside a JDBC transaction can **wait for a connection** and hit pool timeout regardless of remaining transaction timeout.

### 10.6. `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

Creates a table to observe actual commits/rollbacks. No initial data is inserted; each scenario runs `DELETE FROM tx_events` **outside** its transaction to reset the fixture. Unique IDs per scenario and valid SQL isolate transaction behavior from DB constraint errors.

### 10.7. `src/main/java/example/template/TemplateConfig.java`

```java
package example.template;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
public class TemplateConfig {

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new DataSourceTransactionManager(source);
    }

    @Bean("defaultTx")
    TransactionTemplate defaultTx(PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }

    @Bean("outerTx")
    TransactionTemplate outerTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(false);
        tx.setTimeout(15);
        tx.setName("demo.outer");
        return tx;
    }

    @Bean("joinTx")
    TransactionTemplate joinTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_SERIALIZABLE
        );
        tx.setReadOnly(true);
        tx.setTimeout(2);
        tx.setName("demo.participant");
        return tx;
    }

    @Bean("separateTx")
    TransactionTemplate separateTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_SERIALIZABLE
        );
        tx.setReadOnly(true);
        tx.setTimeout(4);
        tx.setName("demo.independent");
        return tx;
    }

    @Bean("queryTx")
    TransactionTemplate queryTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_DEFAULT
        );
        tx.setReadOnly(true);
        tx.setTimeout(8);
        tx.setName("demo.query");
        return tx;
    }
}
```

Each template holds **one stable policy**, injected and reused by Spring. The `Qualifier` import is unused in this configuration file (Java allows unused imports); it will be used in the service. There is a single JDBC transaction manager using the exact `DataSource` used by `JdbcTemplate`. Do not declare any additional managers in the project.

The values on `joinTx` are **the transaction definition's requests**, not proof that isolation or read-only changed when it joined T. That is what we verify next.

### 10.8. `src/main/java/example/template/TemplateScenarioService.java`

```java
package example.template;

import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TemplateScenarioService {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate outer;
    private final TransactionTemplate joined;
    private final TransactionTemplate separate;
    private final TransactionTemplate query;

    public TemplateScenarioService(
            JdbcTemplate jdbc,
            @Qualifier("outerTx") TransactionTemplate outer,
            @Qualifier("joinTx") TransactionTemplate joined,
            @Qualifier("separateTx") TransactionTemplate separate,
            @Qualifier("queryTx") TransactionTemplate query) {
        this.jdbc = jdbc;
        this.outer = outer;
        this.joined = joined;
        this.separate = separate;
        this.query = query;
    }

    private static String isolationName(int level) {
        return switch (level) {
            case Connection.TRANSACTION_NONE -> "NONE";
            case Connection.TRANSACTION_READ_UNCOMMITTED ->
                "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ ->
                "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "UNKNOWN(" + level + ")";
        };
    }

    private String flags(TransactionStatus status) {
        Integer isolation = jdbc.execute(
            (ConnectionCallback<Integer>) Connection::getTransactionIsolation
        );
        Boolean jdbcReadOnly = jdbc.execute(
            (ConnectionCallback<Boolean>) Connection::isReadOnly
        );

        if (isolation == null || jdbcReadOnly == null) {
            throw new IllegalStateException("No JDBC transaction metadata");
        }

        boolean springReadOnly = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        return "new=" + status.isNewTransaction()
            + " isolation=" + isolationName(isolation)
            + " springRO=" + springReadOnly
            + " jdbcRO=" + jdbcReadOnly;
    }

    private void insert(int id, String eventName) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, eventName
        );
    }

    private String rows() {
        List<String> values = jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, index) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
        return values.toString();
    }

    public List<String> runScopes() {
        jdbc.update("DELETE FROM tx_events");

        List<String> trace = new ArrayList<>();

        outer.execute(outerStatus -> {
            insert(1, "outer");
            trace.add("OUTER " + flags(outerStatus));

            joined.execute(innerStatus -> {
                insert(2, "joined");
                trace.add("JOINED " + flags(innerStatus));
                return null;
            });

            separate.execute(innerStatus -> {
                trace.add("SEPARATE " + flags(innerStatus));
                return null;
            });

            trace.add("RESUMED " + flags(outerStatus));
            return null;
        });

        trace.add("ROWS=" + rows());
        return trace;
    }

    public String runQuery() {
        return query.execute(this::flags);
    }

    public String runExceptionRollback() {
        jdbc.update("DELETE FROM tx_events");
        String signal = "completed";

        try {
            outer.execute(outerStatus -> {
                insert(10, "before-error");

                joined.execute(innerStatus -> {
                    insert(11, "joined-before-error");
                    return null;
                });

                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            signal = ex.getMessage();
        }

        return "signal=" + signal + " rows=" + rows();
    }

    public String runManualRollback() {
        jdbc.update("DELETE FROM tx_events");

        String result = outer.execute(status -> {
            insert(20, "temporary");
            status.setRollbackOnly();
            return "REJECTED";
        });

        return "result=" + result + " rows=" + rows();
    }
}
```

**Code analysis:**

- `flags(status)` uses `JdbcTemplate.execute(ConnectionCallback)` to measure **the JDBC connection bound to the transaction**. If you manually pull an arbitrary connection from the pool, you may measure the wrong connection.
- `status.isNewTransaction()` distinguishes a callback creating a new physical transaction from a joining `REQUIRED` callback. This is not a count of JDBC connections across every manager, yet it is accurate in this JDBC demo.
- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` reads Spring's metadata of the running transaction.
- H2's `Connection.isReadOnly()` on a writable database can return `false` even when the transaction definition is read-only, because the driver ignores the hint.
- `runScopes()` creates an outer transaction, then runs `joined` and `separate` via **the `execute()` API itself**, without needing Spring AOP to intercept `runScopes()`.
- `runQuery()` runs outside any other transaction, so `queryTx` creates a new T at `DEFAULT` isolation from the pool's `REPEATABLE_READ` baseline.
- `runExceptionRollback()` throws `IllegalStateException` **out of the outer callback**; the template rolls back all of T. `joined` returning successfully earlier does not create an independent commit.
- `runManualRollback()` sets rollback-only on `outerStatus` and returns `"REJECTED"`; the manager rolls back T instead of committing.

`ArrayList trace` is a local variable of a single invocation and callbacks execute **synchronously**, creating no background tasks; appending strings to the list inside callbacks is valid. Template beans can still be used concurrently by multiple threads because their configurations do not change.

### 10.9. `src/main/java/example/template/TransactionTemplateDemoApplication.java`

```java
package example.template;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionTemplateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionTemplateDemoApplication.class, args);
    }

    private static void showConfig(
            String name, TransactionTemplate template) {
        System.out.println(
            "CONFIG " + name
            + "=" + template.getPropagationBehavior()
            + "/" + template.getIsolationLevel()
            + "/" + template.isReadOnly()
            + "/" + template.getTimeout()
        );
    }

    @Bean
    ApplicationRunner demonstrate(
            TemplateScenarioService service,
            @Qualifier("defaultTx") TransactionTemplate defaultTx,
            @Qualifier("outerTx") TransactionTemplate outerTx,
            @Qualifier("joinTx") TransactionTemplate joinTx,
            @Qualifier("separateTx") TransactionTemplate separateTx,
            @Qualifier("queryTx") TransactionTemplate queryTx) {
        return args -> {
            showConfig("default", defaultTx);
            showConfig("outer", outerTx);
            showConfig("joined", joinTx);
            showConfig("separate", separateTx);
            showConfig("query", queryTx);

            for (String line : service.runScopes()) {
                System.out.println(line);
            }

            System.out.println("QUERY " + service.runQuery());
            System.out.println("ROLLBACK " +
                service.runExceptionRollback());
            System.out.println("MANUAL " +
                service.runManualRollback());
        };
    }
}
```

`@SpringBootApplication` scans the same package and picks up `TemplateConfig` and `TemplateScenarioService`. The templates are not Spring AOP proxies; they are Spring bean objects holding transaction definition configurations. Spring Boot creates `JdbcTemplate` and the H2 datasource via the JDBC starter.

`@EnableTransactionManagement` is not required just for `TransactionTemplate.execute()` to run, because it calls `PlatformTransactionManager` directly. If the project also uses `@Transactional`, Spring Boot configures transaction infrastructure according to its auto-configuration conditions.

### 10.10. How to Run

In the project where the Gradle wrapper was created:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If there is no wrapper yet, use `gradle bootRun` with a compatible Gradle version or generate the wrapper. Do not invoke `javac`/`java` directly without Spring Boot/JDBC/Hikari/H2 JARs on the classpath.

### 10.11. Expected Stdout

Ignore Spring Boot/Gradle startup logs. Lines printed by the application itself:

```text
CONFIG default=0/-1/false/-1
CONFIG outer=0/2/false/15
CONFIG joined=0/8/true/2
CONFIG separate=3/8/true/4
CONFIG query=0/-1/true/8
OUTER new=true isolation=READ_COMMITTED springRO=false jdbcRO=false
JOINED new=false isolation=READ_COMMITTED springRO=false jdbcRO=false
SEPARATE new=true isolation=SERIALIZABLE springRO=true jdbcRO=false
RESUMED new=true isolation=READ_COMMITTED springRO=false jdbcRO=false
ROWS=[1:outer, 2:joined]
QUERY new=true isolation=REPEATABLE_READ springRO=true jdbcRO=false
ROLLBACK signal=boom rows=[]
MANUAL result=REJECTED rows=[]
```

This is the **expected result derived from the code and configuration**, not a claim that the project was compiled/run in the current environment.

### 10.12. Interpreting Stdout per Property

**`CONFIG ...`:** four values in order `propagation/isolation/readOnly/timeout`. Constants: `REQUIRED=0`, `REQUIRES_NEW=3`, `DEFAULT isolation=-1`, `READ_COMMITTED=2`, `SERIALIZABLE=8`. `TIMEOUT_DEFAULT=-1` does not mean a negative timeout at the DB, but rather the "use default" sentinel.

**`OUTER`:** `outerTx` owns a new physical transaction; isolation is set to `READ_COMMITTED`. Spring read-only flag is `false` and H2 JDBC read-only flag is `false`.

**`JOINED`:** although `joinTx` **declares** `SERIALIZABLE` isolation, `readOnly=true`, and 2-second timeout, `REQUIRED` sees the outer T and joins T. Status is `new=false`, connection isolation remains `READ_COMMITTED`, and Spring read-only remains `false`. **The 2-second timeout does not change outer's deadline either**, even though that is not directly shown by those two flags.

**`SEPARATE`:** `REQUIRES_NEW` starts another physical transaction. The connection inside the callback receives `SERIALIZABLE` isolation; Spring publishes read-only `true`. Yet H2's `JdbcConnection.isReadOnly()` may return `false` because read-only is only an ignored hint.

**`RESUMED`:** after the `separate` callback finishes, the outer transaction resumes with `READ_COMMITTED` isolation and read-only flag `false`, without the new transaction's metadata "leaking" into it.

**`ROWS`:** both INSERTs from outer and joined belong to the same physical T, so committing outer leaves both rows present. The `separate` callback writes no data.

**`QUERY`:** when there is no outer T, `queryTx` with `DEFAULT` isolation starts a new T. Hikari's `REPEATABLE_READ` baseline is preserved; Spring read-only metadata is `true`, while H2's JDBC read-only flag stays `false`.

**`ROLLBACK`:** `IllegalStateException` escapes the outer callback after two INSERTs; Spring rolls back all of T and the caller catches the exception after `execute()`. No rows remain.

**`MANUAL`:** the callback returns `"REJECTED"` while setting `status.setRollbackOnly()`; the new transaction rolls back without needing to throw an exception. This is a transparent return-result pattern; never return `"SUCCESS"` after marking rollback-only.

## 11. JUnit 5: Verifying Configuration and Behavior Instead of Guessing from Annotations

Create `src/test/java/example/template/TransactionTemplateDemoTest.java`:

```java
package example.template;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class TransactionTemplateDemoTest {

    @Autowired TemplateScenarioService service;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("defaultTx")
    TransactionTemplate defaultTx;

    @Autowired
    @Qualifier("outerTx")
    TransactionTemplate outerTx;

    @Autowired
    @Qualifier("joinTx")
    TransactionTemplate joinTx;

    @Autowired
    @Qualifier("separateTx")
    TransactionTemplate separateTx;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    @Test
    void defaultConfigurationMatchesTransactionDefinition() {
        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRED,
            defaultTx.getPropagationBehavior()
        );
        assertEquals(
            TransactionDefinition.ISOLATION_DEFAULT,
            defaultTx.getIsolationLevel()
        );
        assertEquals(false, defaultTx.isReadOnly());
        assertEquals(
            TransactionDefinition.TIMEOUT_DEFAULT,
            defaultTx.getTimeout()
        );
    }

    @Test
    void configurationHoldsFourDeclaredProperties() {
        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRED,
            outerTx.getPropagationBehavior()
        );
        assertEquals(
            TransactionDefinition.ISOLATION_READ_COMMITTED,
            outerTx.getIsolationLevel()
        );
        assertEquals(false, outerTx.isReadOnly());
        assertEquals(15, outerTx.getTimeout());

        assertEquals(
            TransactionDefinition.ISOLATION_SERIALIZABLE,
            joinTx.getIsolationLevel()
        );
        assertEquals(true, joinTx.isReadOnly());
        assertEquals(2, joinTx.getTimeout());

        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW,
            separateTx.getPropagationBehavior()
        );
        assertEquals(true, separateTx.isReadOnly());
        assertEquals(4, separateTx.getTimeout());
    }

    @Test
    void participantInheritsEffectiveOuterCharacteristics() {
        assertEquals(
            List.of(
                "OUTER new=true isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "JOINED new=false isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "SEPARATE new=true isolation=SERIALIZABLE " +
                    "springRO=true jdbcRO=false",
                "RESUMED new=true isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "ROWS=[1:outer, 2:joined]"
            ),
            service.runScopes()
        );
    }

    @Test
    void resourceDefaultAndReadOnlyAreSeparatelyObservable() {
        assertEquals(
            "new=true isolation=REPEATABLE_READ " +
                "springRO=true jdbcRO=false",
            service.runQuery()
        );
    }

    @Test
    void uncheckedExceptionRollsBackPhysicalTransaction() {
        assertEquals(
            "signal=boom rows=[]",
            service.runExceptionRollback()
        );
    }

    @Test
    void statusSetRollbackOnlyReturnsFailureWithoutCommit() {
        assertEquals(
            "result=REJECTED rows=[]",
            service.runManualRollback()
        );
    }
}
```

Run:

```bash
./gradlew test
```

The tests **do not place `@Transactional`** on the test class or methods. If the test framework creates a transaction itself, `outerTx`'s `REQUIRED` can join the test's T, making both `isNewTransaction()` and commit/rollback conclusions deviate from the lesson's goal.

`@SpringBootTest` may run `ApplicationRunner` during context startup; `@BeforeEach` clears the table before each test for an independent fixture. If running tests in parallel against the same H2 database, isolate schemas/fixtures to avoid races.

**Scope of proof:** tests on H2 prove wiring/config and JDBC/H2 behavior. When moving to PostgreSQL/MySQL/JPA, re-test effective isolation, JDBC read-only flags, and timeouts on that exact stack.

## 12. Advanced Configuration: Timeout, Validation, and Transaction Manager Defaults

### 12.1. Manager Default Timeout Is Not Template Timeout

`TransactionTemplate` can hold:

```java
template.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
```

At runtime, the manager may have a configured default timeout, or the backend may not support timeouts. Conversely, if the template sets `15`, that is a timeout **request** for a new transaction managed by the manager, not a guarantee of a deadline enforced by interrupting every Java statement.

When SLAs are required, network/CPU/query steps must be measured and bounded separately; transaction timeout is only one piece.

### 12.2. Isolation/readOnly Mismatch on a Participant

If `joinTx` uses `REQUIRED` with `SERIALIZABLE` and `readOnly=true` while outer T is at `READ_COMMITTED` and `readOnly=false`, the **default** manager can allow joining and ignore incompatible inner declarations. This does not break code by itself, yet it can violate assumptions made by the callback author.

You can enable:

```java
manager.setValidateExistingTransaction(true);
```

Then the manager can throw `IllegalTransactionStateException` when isolation is incompatible. For read-only, validation is typically especially useful for a **read-write request joining a read-only outer**, rather than treating every read-only participant inside a writable outer as invalid. Read the manager's actual contract instead of assuming it checks all `readOnly` combinations by the same rule.

### 12.3. Choosing the Right Manager for the Resource

- **Spring JDBC:** `DataSourceTransactionManager` or `JdbcTransactionManager` suits JDBC transactions on a managed datasource.
- **Spring Data JPA/Hibernate:** typically uses `JpaTransactionManager`; do not arbitrarily pair another JDBC manager with JPA repositories without understanding connection/`EntityManager` sharing.
- **JTA/multiple resources:** requires a manager supporting resource coordination; a local JDBC transaction does not turn into a distributed atomic transaction by itself.
- **Reactive R2DBC:** use `ReactiveTransactionManager` and `TransactionalOperator`; do not use imperative `TransactionTemplate` to create transaction context on a reactive subscription.

In this example, **one** `DataSourceTransactionManager` and **one** `JdbcTemplate` share one `DataSource`, so join/suspend/resume have clear meaning.

## 13. `@Transactional` vs. `TransactionTemplate`

| Criterion | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Configuration | Annotation with `Propagation`, `Isolation` enums | Setters with `TransactionDefinition` constants |
| Boundary | Method advised by Spring AOP/AspectJ | Code block inside the `execute()` callback |
| Proxy mode dependency | Can be bypassed by self-invocation | Callback is called directly, no proxy needed to start T |
| Returning results | Return from annotated method | Callback return value passed through `execute()` |
| Exception-based rollback | Configurable `rollbackFor`/`noRollbackFor` rules | `execute` handles unchecked/Error; can call `setRollbackOnly()` |
| Checked exceptions | Annotated method can declare `throws` | Callback interface does not allow throwing checked exceptions directly |
| Configuring multiple policies | Multiple annotations/methods | Multiple preconfigured template instances |
| Relationship to DB | Depends on manager/resource | **Also depends on manager/resource** |
| Reactive | Has dedicated rules with reactive transaction manager | Use `TransactionalOperator` for reactive |

An application can combine both approaches when there is a clear reason. However, avoid randomly nesting an outer `@Transactional` with differing template propagations and then being surprised when `REQUIRES_NEW` commits independently or `REQUIRED` marks the shared transaction rollback-only.

## 14. Common Mistakes

| Symptom / Misconception | Cause | Fix |
| --- | --- | --- |
| `setPropagationBehavior(Propagation.REQUIRES_NEW)` fails to compile | Setter accepts `int`, not enum | Use `TransactionDefinition.PROPAGATION_REQUIRES_NEW` |
| Setting `setIsolationLevel(-1)` thinking it means READ_UNCOMMITTED | `-1` means DEFAULT, not a JDBC level | Use explicit constants and check resource |
| `joinTx` configured `SERIALIZABLE` yet runs `READ_COMMITTED` | `REQUIRED` joined outer T | Set isolation on outer owner or enable validation |
| `joinTx.setReadOnly(true)` yet Spring context stays false | Callback joined read-write outer T | Set policy on transaction owner; do not treat flag as separate mode |
| `REQUIRES_NEW` breaks atomicity of the entire workflow | Inner creates/commits an independent physical transaction | Use only when business rules allow it |
| `setTimeout(2)` on inner does not limit outer | Outer already has its own deadline | Set timeout on the boundary owning T |
| `Thread.sleep` over 2 seconds does not throw immediately | Timeout does not automatically interrupt Java threads | Test on real JDBC statements and DBMS |
| `readOnly=true` yet SQL still writes | JDBC hint may be ignored by driver | Use DB enforcement/permissions when writes must be forbidden |
| H2 test passes yet production behaves differently | Driver/DB isolation/timeout differ | Integration-test on production-like DB |
| Changing template setters per HTTP request | Shared configuration state, race condition | Create immutable-after-setup policy beans or separate templates |
| Callback called `setRollbackOnly()` yet caller believes it committed | Callback returned success violating contract | Return a clear failure result |
| Throwing checked `IOException` directly inside lambda | `TransactionCallback` does not declare checked throws | Catch/wrap or rollback-only |
| Transaction "does not run" despite having a template bean | Only constructed template, never called `execute()` | Put transactional code inside callback |
| Callback uses a different JDBC connection | Obtained connection outside transaction binding | Use `JdbcTemplate`/`DataSourceUtils` with matching manager |
| `UnexpectedRollbackException` when outer commits | Inner `REQUIRED` participant marked shared T rollback-only | Trace rollback scope, preserve invariants |
| `NESTED` does not work | Manager/driver does not support savepoints | Verify capability; do not assume |
| Using `TransactionTemplate` across `CompletableFuture` expecting same T | Imperative transactions are typically bound to thread/resource context | Open separate transaction where task runs or redesign |
| Overlapping `@Transactional` and templates are hard to follow | Physical transaction owner is unclear | Draw call tree/propagation and inspect status |
| Query is not canceled right at timeout | Driver/statement timeout does not guarantee instant cancellation | Combine query/network timeouts, metrics, retries |

## 15. Practical Design Patterns

### Pattern A — Reading Data with a Query Policy

```java
public List<CustomerView> findCustomers() {
    return readerTx.execute(status -> repository.findAllViews());
}
```

Sample snippet assuming `readerTx`, `repository`, and `CustomerView` beans exist. The template's `readOnly=true` expresses intent; optimization/enforcement effectiveness depends on the backend. If the method is called inside an outer T, the chosen propagation decides whether outer characteristics are inherited.

### Pattern B — All-or-Nothing Write Across Two Tables

```java
public Receipt placeOrder(CreateOrder command) {
    return writeTx.execute(status -> {
        Long id = orders.insert(command);
        ledger.insertDebit(id, command.total());
        return new Receipt(id);
    });
}
```

This is an architectural snippet without repositories/types defined. Both operations require the same manager/resource and physical transaction. If one step throws a runtime exception, the manager rolls back the required scope.

### Pattern C — Short Timeout for an Independent Unit

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
isolated.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
isolated.setReadOnly(false);
isolated.setTimeout(5);
```

Use only when the unit is genuinely **allowed to commit independently**. Configuration good for this case may be wrong for order atomicity.

### Pattern D — Returning Intentional Failure

```java
OperationResult result = tx.execute(status -> {
    debitAccount();

    if (!canCreditDestination()) {
        status.setRollbackOnly();
        return OperationResult.failure("No destination");
    }

    creditAccount();
    return OperationResult.success();
});
```

Snippet assuming domain types/helpers exist. Calling `setRollbackOnly()` must pair with a **failure result**; do not report success when the DB rolled back. Verify data after the transaction to confirm.

## 16. Self-Check Exercises

1. What propagation does a template have if no setter is called? **`PROPAGATION_REQUIRED`**.
2. Is `ISOLATION_DEFAULT=-1` a JDBC isolation level? **No**; it is Spring's sentinel to use the resource default.
3. What unit does `setTimeout(20)` use? **Seconds**, for new transactions if supported by the manager.
4. Does `setReadOnly(true)` guarantee every DB rejects `UPDATE`? **No**, it depends on the manager/driver/DBMS.
5. Inner `REQUIRED` sets `SERIALIZABLE` while outer T is already at `READ_COMMITTED`, with default validation off—what happens? **Inner usually joins outer at `READ_COMMITTED`**.
6. Can an inner `REQUIRES_NEW` commit even if outer rolls back? **Yes**, because of independent physical transactions.
7. Does `NESTED` inside T always open a separate connection? **No**; when supported, it usually uses a JDBC savepoint within the same physical T.
8. Does a 2-second timeout on an inner `REQUIRED` reset a 15-second deadline on outer? **Not by default**; inner does not own physical T.
9. Why should you not call setters on a singleton template per request? **Shared configuration can be mutated concurrently across threads**.
10. Can `status.setRollbackOnly()` on a callback owning T return a normal result? **Yes**; T rolls back and the callback should return a transparent failure state.
11. Why does throwing `new IOException()` directly from an `execute` lambda fail to compile? **The callback does not declare checked exceptions**.
12. What should you call to verify actual isolation? **`Connection.getTransactionIsolation()` on the exact connection participating in the transaction**.
13. Must `@Transactional` and `TransactionTemplate` use two different transaction managers? **No**; both can use the same `PlatformTransactionManager`.
14. For a read-only transaction in JPA, should you assume JDBC template manager behavior directly? **Do not assume blindly**; pick the right JPA transaction manager/provider and test.
15. Why does a test checking `getTimeout()==4` not prove a query aborts at second 4? **That only checks the template setting, not deadline/driver execution**.

## 17. Checklist Before Taking `TransactionTemplate` to Production

1. Identify the exact **single manager/resource** for the unit of work, especially when both JDBC and JPA or multiple datasources exist.
2. Choose propagation per invariant: shared transaction, independent, savepoint, or no T?
3. Verify whether the template **actually starts a new T** on the current call path before trusting that isolation/readOnly/timeout will apply individually.
4. Set an explicit isolation level if business logic needs the corresponding consistency/locking, rather than relying on `DEFAULT` and guessing.
5. Understand `readOnly=true` is a stack-dependent hint/optimization/enforcement; for security requirements, use DB permissions and test.
6. Set reasonable timeouts on transaction owners, coordinating statement timeouts, connection pool timeouts, network timeouts, and error handling.
7. Never mutate setters after a template is shared; create **separate templates per policy**.
8. Test `REQUIRED` joining an outer transaction and `REQUIRES_NEW` opening an independent T; spot unexpected commits/rollbacks.
9. Use `status.setRollbackOnly()` when needed, and return accurate failure results.
10. Keep code inside callbacks short and retryable/idempotent per business requirements.
11. Never launch async/background operations expecting them to stay inside the imperative transaction of an already returned callback.
12. When executing real SQL updates, inspect the DB after the **outermost transaction boundary**, not just updated row counts inside the callback.
13. Write integration tests on a production-like DBMS and transaction manager; do not extrapolate timeout/locking conclusions from H2.
14. Provide observability on transaction manager, propagation, deadlines, and commit/rollback errors.
15. When upgrading drivers/Spring Boot/databases, re-run tests because resource-dependent properties may behave differently.

## References

- Spring Framework — **Programmatic Transaction Management / TransactionTemplate**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — **Transaction Propagation** (physical vs. logical transactions, `REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **`TransactionTemplate` Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — **`DefaultTransactionDefinition` setters/getters**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework — **`TransactionDefinition` constants**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — **`TransactionStatus` interface**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — **`DataSourceTransactionManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — **Declarative `@Transactional` settings**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- HikariCP — **Connection pool configuration (`transactionIsolation`)**: https://github.com/brettwooldridge/HikariCP/wiki/Configuration
- H2 — **JDBC `JdbcConnection` read-only behavior**: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html