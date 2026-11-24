# `ISOLATION_DEFAULT` uses the resource's default in Spring Transaction Management

## Learning objectives

After this lesson, you will be able to:

1. Explain accurately what `Isolation.DEFAULT`/`TransactionDefinition.ISOLATION_DEFAULT` means in `@Transactional`.
2. Distinguish **the isolation declared in Spring** from **the effective isolation of the JDBC connection/transaction**.
3. Understand why `DEFAULT` **is not synonymous** with `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, or "no isolation."
4. Trace the source of isolation configuration: database server, JDBC driver/session, connection pool, and transaction manager.
5. Predict behavior when a `REQUIRED` method **joins an existing transaction**, a `REQUIRES_NEW` method opens its own transaction, or a `NESTED` method shares the same physical transaction.
6. Run a **Java 17+, Spring Boot, HikariCP, H2, Spring JDBC** example, observe `Connection.getTransactionIsolation()`, and write tests to verify instead of guessing from annotations.
7. Know when to leave `DEFAULT`, when to specify an explicit isolation level, and how to avoid bugs when switching databases or configuring a connection pool.

**Topic:** the `ISOLATION_DEFAULT` isolation level in Spring Framework transaction management. The focus is not on ranking every isolation level, but on understanding **who determines the effective level when Spring does not specify a dedicated one**.

---

## 1. The single most important takeaway

In Spring:

```java
@Transactional
public void process() {
    // ...
}
```

has the same default isolation as:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void process() {
    // ...
}
```

`Isolation.DEFAULT` **does not ask Spring to enforce a specific isolation level**. Per `TransactionDefinition`, it carries the sentinel value `ISOLATION_DEFAULT = -1`, meaning *use the default isolation level of the underlying transactional resource*.

With **Spring JDBC + `DataSourceTransactionManager`**, when starting a new transaction with `Isolation.DEFAULT`, Spring **does not call `Connection.setTransactionIsolation(...)` to force a specific level**. The transaction uses whatever isolation level **the newly acquired JDBC connection already has**. That connection may have been configured by the DBMS, JDBC driver, pool configuration, or initialization SQL.

This does **not** mean the transaction runs with "no isolation," "no locks," or "always `READ_COMMITTED`." It simply means: **Spring does not override the connection's isolation level for this transaction definition**.

```text
@Transactional(isolation = Isolation.DEFAULT)
                  |
                  v
     Spring TransactionInterceptor
                  |
         New JDBC transaction?
                  |
                  v
   DataSourceTransactionManager acquires Connection
                  |
                  v
  Isolation.DEFAULT => does not force a new JDBC isolation
                  |
                  v
   Transaction uses the Connection's existing isolation
                  |
                  v
   Database executes according to that level's semantics
```

If an application is moved from PostgreSQL to MySQL InnoDB, or if a connection pool's settings change, the exact same `Isolation.DEFAULT` annotation **can** result in a different effective isolation level. To require a consistent level, configure it explicitly at the right layer and verify that the DB supports it.

## 2. `DEFAULT` is a sentinel, not a JDBC isolation level

The enum values in Spring:

```java
import org.springframework.transaction.annotation.Isolation;

Isolation.DEFAULT;
Isolation.READ_UNCOMMITTED;
Isolation.READ_COMMITTED;
Isolation.REPEATABLE_READ;
Isolation.SERIALIZABLE;
```

Value table:

| Spring name | Value | Meaning |
| --- | ---: | --- |
| `Isolation.DEFAULT` | `-1` | **Do not choose a specific isolation**; use the default of the resource/transaction manager |
| `Isolation.READ_UNCOMMITTED` | `1` | Request JDBC level `TRANSACTION_READ_UNCOMMITTED` |
| `Isolation.READ_COMMITTED` | `2` | Request JDBC level `TRANSACTION_READ_COMMITTED` |
| `Isolation.REPEATABLE_READ` | `4` | Request JDBC level `TRANSACTION_REPEATABLE_READ` |
| `Isolation.SERIALIZABLE` | `8` | Request JDBC level `TRANSACTION_SERIALIZABLE` |

The values `1, 2, 4, 8` of the four concrete levels correspond to constants in `java.sql.Connection`. **`-1` is not a JDBC level**, so `connection.setTransactionIsolation(-1)` must never be called.

Related constants:

```java
import java.sql.Connection;
import org.springframework.transaction.TransactionDefinition;

int useResourceDefault = TransactionDefinition.ISOLATION_DEFAULT; // -1
int readCommitted = Connection.TRANSACTION_READ_COMMITTED;       // 2
int repeatableRead = Connection.TRANSACTION_REPEATABLE_READ;     // 4
```

The snippet above only illustrates constant values; a complete runnable program appears in section 8. JDBC also defines `Connection.TRANSACTION_NONE = 0`, meaning the connection/driver does not support transactions—**not equivalent** to `ISOLATION_DEFAULT = -1`.

### Defaults of `@Transactional`

When no attributes are specified:

```java
@Transactional
public void executeBusinessStep() {
    // ...
}
```

Spring interprets this as `Propagation.REQUIRED`, `Isolation.DEFAULT`, `readOnly = false`, default timeout, and default rollback rules. These attributes are **independent**:

- **Propagation**: open a new transaction or join an existing one?
- **Isolation**: if a new physical transaction is opened, which isolation level will it use?
- **Read-only**: a read-only hint/policy, not isolation.
- **Rollback rules**: which exceptions cause the interceptor to roll back, not isolation.

Do not interpret `Isolation.DEFAULT` as "no transaction." Whether a transaction exists depends on propagation, the transaction manager, whether the caller goes through the Spring proxy, and the underlying resource.

## 3. Whose default is "the resource's default"?

In a JDBC setup, a connection's effective level can be influenced by multiple layers:

```text
DBMS / server / database-level settings
             |
             v
JDBC driver / session initialization
             |
             v
DataSource / connection pool (HikariCP, ... )
             |
             v
Connection borrowed from pool
             |
             v
Spring JDBC TransactionManager
   | Isolation.DEFAULT -> keep existing level
   | Isolation.READ_COMMITTED -> request change if needed
             |
             v
Physical transaction executes using that JDBC connection
```

Points to distinguish:

1. **DBMS default**: the default configuration of PostgreSQL, MySQL InnoDB, H2, or another database. It can be changed by an administrator.
2. **JDBC connection/session state**: the driver and initialization statements can set isolation before Spring receives the connection.
3. **Connection pool policy**: a pool such as HikariCP can configure `transactionIsolation` for the connections it manages, **differing from the DB server's initial default**.
4. **Transaction manager override**: if a method requests a specific level when opening a transaction, Spring JDBC can temporarily change the connection's isolation.
5. **Existing transaction**: if a method merely *joins* an outer transaction, the isolation has already been established by the outer transaction; the inner method's annotation does not automatically alter it.

Therefore, answering "`Isolation.DEFAULT` = `READ_COMMITTED`" is **wrong as a general rule**. Some systems happen to exhibit `READ_COMMITTED`, but that is because **the resource is configured that way**, not because `DEFAULT` dictates it.

### Example: common out-of-the-box configurations for three databases

| DBMS/engine | Commonly documented default | What to keep in mind |
| --- | --- | --- |
| PostgreSQL | `READ COMMITTED` | Server/session settings can change it; `READ UNCOMMITTED` is treated equivalently to `READ COMMITTED` |
| MySQL InnoDB | `REPEATABLE READ` | Session/global `transaction_isolation` can differ from the default |
| H2 | `READ COMMITTED` | Demos/tests can change the connection's level via JDBC/pool |

These are **typical unoverridden values**, not a guarantee of the isolation level of every running instance. A datasource pointing to PostgreSQL whose pool sets `TRANSACTION_REPEATABLE_READ` can cause a Spring `DEFAULT` transaction to run at `REPEATABLE_READ`.

Official sources: PostgreSQL `SET TRANSACTION`, MySQL 8.4 InnoDB Transaction Isolation Levels, and H2 Transaction Isolation — URLs are listed at the end of this lesson.

## 4. How does Spring JDBC implement `Isolation.DEFAULT`?

Conceptually, when `DataSourceTransactionManager` begins a new JDBC transaction:

```text
doBegin()
  -> obtain JDBC Connection
  -> read TransactionDefinition.getIsolationLevel()
  -> prepare connection
     if isolation == ISOLATION_DEFAULT:
         DO NOT force Connection.setTransactionIsolation(...)
     if isolation is a specific level and differs from current level:
         record previous level
         Connection.setTransactionIsolation(requestedLevel)
  -> switch to transactional mode (autoCommit=false if needed)
  -> bind Connection to transaction context
```

When the transaction finishes, Spring attempts to restore any connection attributes it changed for that transaction, including the previous isolation level if Spring overrode it. This is especially important when the connection is **returned to the pool** for reuse by other requests.

This is a conceptual description, **not a copy of Spring's source code**. Spring exposes the relevant APIs:

- `TransactionDefinition.getIsolationLevel()` — the value in the transaction definition.
- `DataSourceUtils.prepareConnectionForTransaction(...)` — prepares the JDBC connection.
- `Connection.getTransactionIsolation()` — reads the **effective JDBC level reported by the connection**.
- `Connection.setTransactionIsolation(int)` — asks the connection to switch to a specific JDBC level.
- `DataSourceUtils.resetConnectionAfterTransaction(...)` — restores the prior isolation when needed.

**Important:** Spring can only control what the transaction manager and driver support. A manager that does not support custom isolation may accept `DEFAULT` and reject other requests. Databases may map, restrict, or throw errors for certain isolation levels. Thus, never rely solely on an enum to promise that the DB will prevent a particular anomaly.

## 5. Difference between "do not override" and "force `READ_COMMITTED`"

In the same service, consider two methods:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void processWithResourceDefault() {
    // ...
}

@Transactional(isolation = Isolation.READ_COMMITTED)
public void processWithExplicitReadCommitted() {
    // ...
}
```

Both are snippets, not a standalone Java project. Suppose HikariCP hands out a JDBC connection whose current isolation is `REPEATABLE_READ`:

| Step | With `DEFAULT` | With `READ_COMMITTED` |
| --- | --- | --- |
| Borrow JDBC connection | Has level `REPEATABLE_READ` | Has level `REPEATABLE_READ` |
| Spring checks isolation definition | `-1` | `2` |
| Does Spring change isolation before transaction? | **Does not force change** | May call `setTransactionIsolation(2)` |
| Isolation used during transaction | `REPEATABLE_READ` | `READ_COMMITTED` if driver accepts |
| On completion | No Spring isolation override to undo | Spring attempts to restore previous level `REPEATABLE_READ` |
| Next borrow | Per resource/pool state | Per restored resource/pool state |

An annotation with `DEFAULT` **does not execute a command** to "reset the connection back to the DB's original default." If the connection pool configured a different level, `DEFAULT` continues using that level.

### Why does `DEFAULT` not necessarily match the DBMS default?

For example, H2 defaults to `READ_COMMITTED`, yet configuring HikariCP with:

```yaml
spring:
  datasource:
    hikari:
      transaction-isolation: TRANSACTION_REPEATABLE_READ
```

causes HikariCP to supply connections with `REPEATABLE_READ` isolation (if the driver supports it). A Spring transaction starting with `Isolation.DEFAULT` will **preserve** that connection's isolation. In the same app with that setting removed, new connections fall back to H2/driver's default, namely `READ_COMMITTED`.

This example clarifies the principle of **the actual resource's default**. The pool is part of the resource-provisioning infrastructure, not a new transaction level.

## 6. When a method joins an existing transaction

Spring's isolation attribute is designed to take effect **when starting a new transaction**, typically with `REQUIRED` when no transaction exists or `REQUIRES_NEW` when opening an independent transaction.

Suppose:

```java
@Service
public class OuterService {

    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        inner.inner();
    }
}
```

```java
@Service
public class InnerService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // ...
    }
}
```

These two classes are illustrative snippets inside the same application with transaction management enabled. **If** `OuterService.outer()` is called through the Spring proxy and creates a physical transaction T at `READ_COMMITTED`, the proxied call to `InnerService.inner()` with `REQUIRED` **joins T**. By default, the Spring transaction manager **does not create a new T** and does not change the existing physical transaction's isolation level to `SERIALIZABLE`.

```text
Caller
   |
   v
Outer proxy: BEGIN T with READ_COMMITTED
   |
   v
OuterService.outer()
   |
   v
Inner proxy: REQUIRED -> join T
   |  Method declares SERIALIZABLE
   |  But T already has isolation READ_COMMITTED
   v
InnerService.inner() runs inside T itself (READ_COMMITTED)
   |
   v
Outer proxy: COMMIT/ROLLBACK T
```

**Practical rule:** the isolation of the **outer physical transaction** usually wins when an inner scope joins the same transaction. It is not the case that "inner `SERIALIZABLE` upgrades protection for a small slice of T."

### `validateExistingTransaction`

`AbstractPlatformTransactionManager` has a `validateExistingTransaction` flag:

- **Default is typically `false`**: an inner participant can join an existing transaction even if it declares a different isolation; the physical transaction T keeps the owner's isolation.
- **Set to `true`**: the manager can **reject** joining when the isolation/read-only declared on the inner method is incompatible with the existing transaction, rather than silently accepting a mismatch.

Explicit configuration example:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

This is an **alternative configuration** for the manager bean in section 8's demo, **not a second bean** to add to the same context. With outer requesting `READ_COMMITTED` and inner requesting `SERIALIZABLE`, the manager can throw `IllegalTransactionStateException` when inner tries to join. Enabling validation is helpful when service contracts demand strict consistency, though it changes runtime behavior and must be tested before adopting.

**Another note:** `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` reflects the isolation published by Spring in the transaction context, and can be `null` when the declaration is `DEFAULT`. That value **does not replace** `Connection.getTransactionIsolation()` for verifying the connection's effective level.

## 7. `REQUIRES_NEW` and `NESTED`: do not infer from method names

| Situation | Effective isolation of the inner part |
| --- | --- |
| `REQUIRED`, no prior T, `Isolation.DEFAULT` | New transaction uses the connection/resource's current level |
| `REQUIRED`, existing outer T at `READ_COMMITTED`, inner `DEFAULT` | Uses outer T's `READ_COMMITTED` |
| `REQUIRED`, existing outer T at `READ_COMMITTED`, inner requests `SERIALIZABLE`, default validation off | Usually still uses outer T's `READ_COMMITTED` |
| `REQUIRES_NEW`, inner `Isolation.DEFAULT` | Suspends outer T; new inner transaction uses its own **connection/resource default** |
| `REQUIRES_NEW`, inner requests `SERIALIZABLE` | New inner transaction requests `SERIALIZABLE` if manager/driver support it |
| `NESTED` inside outer T | With JDBC savepoints, uses the **same physical transaction and connection**, so it cannot have its own isolation |
| `SUPPORTS` with no T | Does not open a physical transaction; isolation declaration has no effect as a new transaction |

`REQUIRES_NEW` may require a **separate connection** while outer is still holding its own connection. The pool needs sufficient capacity to avoid waiting or connection exhaustion. `NESTED` uses savepoints when supported by the manager/driver and cannot establish a separate isolation level for the "child transaction" on the same connection.

**Do not change propagation just to force isolation for a piece of code**, unless you truly want to change commit boundaries, commit timing, and atomicity. `REQUIRES_NEW` has its own transaction: inner can commit even if outer subsequently rolls back. That changes business semantics, not just a configuration parameter.

---

## 8. Runnable example with Java 17+, Spring Boot 3.3.5, H2, and HikariCP

The demo uses H2 because it runs in-memory; HikariCP is the connection pool brought in by `spring-boot-starter-jdbc` in standard setups. We **intentionally** configure the pool's isolation to `REPEATABLE_READ` while out-of-the-box H2 typically defaults to `READ_COMMITTED`.

Consequently, if `Isolation.DEFAULT` truly uses the resource's level, the program must observe **`REPEATABLE_READ`** rather than forcing `READ_COMMITTED`.

At the same time, the demo creates a transaction with explicit `READ_COMMITTED`, then tests:

- `REQUIRED` inner declaring `SERIALIZABLE`: **joins outer**, isolation does not change.
- `REQUIRES_NEW` inner declaring `DEFAULT`: **opens a new transaction**, using the new connection's level from the pool.
- Once the `READ_COMMITTED` transaction ends, the next `DEFAULT` call sees the pool resource default again.

### 8.1. Project structure

```text
isolation-default-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/isolation/
    │   │   ├── IsolationProbe.java
    │   │   ├── IsolationOuterService.java
    │   │   └── IsolationDefaultApplication.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/example/isolation/
            └── IsolationDefaultApplicationTest.java
```

This is a **complete project** if you create the exact files below in a Gradle project with a wrapper. No schema is needed because the exercise measures isolation directly on the JDBC connection without creating tables.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'isolation-default-demo'
```

### 8.3. `build.gradle`

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

`spring-boot-starter-jdbc` provides `JdbcTemplate`, JDBC transaction manager infrastructure, and HikariCP. Spring Boot manages Spring Framework/Hikari/H2 versions via dependency management, so avoid mixing mismatched Spring JARs manually.

### 8.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:isolation_default_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
      transaction-isolation: TRANSACTION_REPEATABLE_READ
```

Two key properties:

- `spring.datasource.hikari.transaction-isolation`: the JDBC constant name that **HikariCP** uses to set the baseline isolation of connections in the pool. Here it is `TRANSACTION_REPEATABLE_READ`, **different from H2's server default**.
- `maximum-pool-size: 4`: allows an outer transaction to hold one connection while a `REQUIRES_NEW` inner transaction needs a second connection. The demo is low-load, but the setting highlights the resource requirement.

`DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive until the JVM exits. The demo transactions only read connection metadata without modifying the database, so there are no fixtures to reset.

**Do not confuse:** the `spring.datasource.hikari.transaction-isolation` setting is a **pool** setting. It does not change the value of `Isolation.DEFAULT` in Spring; it changes **the resource isolation level that `DEFAULT` inherits**.

### 8.5. `src/main/java/example/isolation/IsolationProbe.java`

```java
package example.isolation;

import java.sql.Connection;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class IsolationProbe {
    private final JdbcTemplate jdbc;

    public IsolationProbe(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String isolationName(int level) {
        return switch (level) {
            case Connection.TRANSACTION_NONE -> "NONE";
            case Connection.TRANSACTION_READ_UNCOMMITTED ->
                "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED ->
                "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ ->
                "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE ->
                "SERIALIZABLE";
            default -> "UNKNOWN(" + level + ")";
        };
    }

    public String observeConnection() {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) Connection::getTransactionIsolation
        );
        if (level == null) {
            throw new IllegalStateException(
                "JDBC did not return an isolation level"
            );
        }

        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();

        return isolationName(level) + ", active=" + active;
    }

    @Transactional
    public String implicitDefault() {
        return observeConnection();
    }

    @Transactional(isolation = Isolation.DEFAULT)
    public String explicitDefault() {
        return observeConnection();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String explicitReadCommitted() {
        return observeConnection();
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public String requiredRequestSerializable() {
        return observeConnection();
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.DEFAULT
    )
    public String requiresNewResourceDefault() {
        return observeConnection();
    }
}
```

`observeConnection()` calls `JdbcTemplate.execute(ConnectionCallback)` so it retrieves the exact JDBC connection bound by Spring to the transaction when called inside a transactional method. It does **not** call `dataSource.getConnection()` and accidentally borrow a different connection from the pool.

`TransactionSynchronizationManager.isActualTransactionActive()` verifies that the method is inside an imperative Spring transaction. In the demo, the transactional methods are called from outside through the Spring proxy, so `active=true`.

**Important:** `observeConnection()` does not carry its own `@Transactional`. It is a helper called when a transaction is already open; self-invocation to the helper **does not need** new transaction advice. Conversely, `implicitDefault()`, `explicitReadCommitted()`, and `requiredRequestSerializable()` must be **called by another bean through the Spring proxy** for their own metadata to take effect.

### 8.6. `src/main/java/example/isolation/IsolationOuterService.java`

```java
package example.isolation;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IsolationOuterService {
    private final IsolationProbe probe;

    public IsolationOuterService(IsolationProbe probe) {
        this.probe = probe;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String requiredJoinsOuter() {
        return probe.requiredRequestSerializable();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public String newTransactionFromOuter() {
        String inner = probe.requiresNewResourceDefault();
        String resumedOuter = probe.observeConnection();
        return "inner=" + inner + " | outer=" + resumedOuter;
    }
}
```

`requiredJoinsOuter()` creates physical transaction T at `READ_COMMITTED`. The inner method `requiredRequestSerializable()` has `Propagation.REQUIRED` and is called **through another bean**, so the transaction interceptor runs, yet it **joins T**. The default manager does not force T up to `SERIALIZABLE` based on the participant's annotation.

`newTransactionFromOuter()` also starts T at `READ_COMMITTED`, but the inner method has `REQUIRES_NEW`: Spring suspends T, borrows another connection, and opens a new transaction with `DEFAULT`. The new connection comes from the pool with a `REPEATABLE_READ` baseline. Once inner finishes, outer T resumes with its original `READ_COMMITTED` connection. The method returns both levels, clearly showing **two physical transactions** with different isolations in the same call chain.

### 8.7. `src/main/java/example/isolation/IsolationDefaultApplication.java`

```java
package example.isolation;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;

@SpringBootApplication
@EnableTransactionManagement
public class IsolationDefaultApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationDefaultApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    ApplicationRunner printResults(
            IsolationProbe probe,
            IsolationOuterService outer) {
        return args -> {
            System.out.println(
                "Isolation.DEFAULT.value()=" + Isolation.DEFAULT.value()
            );
            System.out.println(
                "Implicit DEFAULT=" + probe.implicitDefault()
            );
            System.out.println(
                "Explicit DEFAULT=" + probe.explicitDefault()
            );
            System.out.println(
                "Explicit READ_COMMITTED=" +
                probe.explicitReadCommitted()
            );
            System.out.println(
                "DEFAULT after override=" + probe.explicitDefault()
            );
            System.out.println(
                "REQUIRED joined=" + outer.requiredJoinsOuter()
            );
            System.out.println(
                "REQUIRES_NEW DEFAULT=" + outer.newTransactionFromOuter()
            );
        };
    }
}
```

The application defines **a single `PlatformTransactionManager`**, using the exact `DataSource` used by `JdbcTemplate`. `@EnableTransactionManagement` enables transaction interception. `ApplicationRunner` receives service beans from the Spring container, so public calls **go through the proxy**, avoiding self-invocation bugs.

`new DataSourceTransactionManager(dataSource)` uses the default `validateExistingTransaction=false`, matching the premise where inner `REQUIRED` specifies an incompatible isolation request yet is allowed to join in the demo.

### 8.8. Running the application

On Linux/macOS:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If the project does not yet have a Gradle wrapper, you can use `gradle bootRun` once a compatible Gradle version is installed, or generate the wrapper with Gradle. Do not invoke `javac`/`java` without the Spring/H2 classpath.

**Lines printed by the application**, excluding Spring Boot/Hikari/Gradle startup logs:

```text
Isolation.DEFAULT.value()=-1
Implicit DEFAULT=REPEATABLE_READ, active=true
Explicit DEFAULT=REPEATABLE_READ, active=true
Explicit READ_COMMITTED=READ_COMMITTED, active=true
DEFAULT after override=REPEATABLE_READ, active=true
REQUIRED joined=READ_COMMITTED, active=true
REQUIRES_NEW DEFAULT=inner=REPEATABLE_READ, active=true | outer=READ_COMMITTED, active=true
```

This is the **expected output based on the code, Hikari configuration, and H2**, not a claim that Gradle was executed in this environment. The isolation values are the names mapped from `Connection.getTransactionIsolation()` in code.

### 8.9. Exact line-by-line explanation

**`Isolation.DEFAULT.value()=-1`:** confirms this is a Spring sentinel, not JDBC `Connection.TRANSACTION_NONE` or a fixed isolation level.

**`Implicit DEFAULT` and `Explicit DEFAULT`:** give the same `REPEATABLE_READ` result because both let the transaction manager use the level of the connection supplied by Hikari. Writing `DEFAULT` explicitly in the annotation or omitting it does not change the result.

**`Explicit READ_COMMITTED`:** because Spring created a new transaction with an explicit request, the manager temporarily switches isolation from the `REPEATABLE_READ` baseline to `READ_COMMITTED` on the connection. The H2 driver supports this level.

**`DEFAULT after override`:** after the explicit method ends, Spring/the connection pool restores the connection state appropriately. A new `DEFAULT` transaction sees the `REPEATABLE_READ` baseline again, rather than having `READ_COMMITTED` "left behind" by the previous request.

**`REQUIRED joined`:** outer opened a `READ_COMMITTED` physical transaction. Inner requested `SERIALIZABLE` but only joined T, so the observed level is `READ_COMMITTED`. This is why you should never assume declaring a higher isolation on a `REQUIRED` method will raise isolation when called from an outer service.

**`REQUIRES_NEW DEFAULT`:** inner received its own transaction and a different connection from the pool, seeing `REPEATABLE_READ`; afterward outer resumed on T with `READ_COMMITTED`. Both levels coexist, but belong to **two different physical transactions**.

## 9. JUnit 5 tests to prevent unintended configuration drift

Create `src/test/java/example/isolation/IsolationDefaultApplicationTest.java`:

```java
package example.isolation;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Isolation;

@SpringBootTest
class IsolationDefaultApplicationTest {
    @Autowired IsolationProbe probe;
    @Autowired IsolationOuterService outer;

    @Test
    void defaultIsSpringSentinelNotAConcreteJdbcLevel() {
        assertEquals(-1, Isolation.DEFAULT.value());
    }

    @Test
    void implicitAndExplicitDefaultsUseConfiguredResource() {
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.implicitDefault()
        );
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.explicitDefault()
        );
    }

    @Test
    void explicitOverrideIsTemporaryForThisTransaction() {
        assertEquals(
            "READ_COMMITTED, active=true",
            probe.explicitReadCommitted()
        );
        assertEquals(
            "REPEATABLE_READ, active=true",
            probe.explicitDefault()
        );
    }

    @Test
    void requiredParticipantKeepsOuterIsolation() {
        assertEquals(
            "READ_COMMITTED, active=true",
            outer.requiredJoinsOuter()
        );
    }

    @Test
    void requiresNewUsesItsOwnResourceDefault() {
        assertEquals(
            "inner=REPEATABLE_READ, active=true | " +
            "outer=READ_COMMITTED, active=true",
            outer.newTransactionFromOuter()
        );
    }
}
```

Run:

```bash
./gradlew test
```

The tests are not annotated with `@Transactional`, so the test framework does not open an enclosing transaction that would skew the question "did this method actually start a new transaction?". `@SpringBootTest` may invoke `ApplicationRunner` when building the context and print the demo lines; that does not affect assertions because each case only reads JDBC connection metadata without modifying data.

**Do not use Mockito to verify effective isolation.** Mocking `JdbcTemplate` or mocking the transaction manager can prove code called an API, but cannot prove what isolation Hikari/driver/database actually provide on a connection. An integration test against a DB/driver representative of production is the right choice.

### What if the `hikari.transaction-isolation` setting is removed?

With H2's default, both `DEFAULT` lines in the demo are expected to become `READ_COMMITTED`, while explicit `READ_COMMITTED` stays `READ_COMMITTED`. The current test **intentionally asserts `REPEATABLE_READ`** to protect the pool configuration contract. If you remove the setting, update the assertions to match the new requirement rather than treating the failing test as Spring choosing the wrong default.

### What if switching to PostgreSQL or MySQL?

Do not update assertions by guesswork. Run an actual integration test against the corresponding database, JDBC driver, pool, permissions, and session settings. Pay special attention to the default level of **connections coming out of the pool**, not just the default written on the DBMS documentation page.

## 10. Do not measure using a connection outside the transaction

A common source of confusion:

```java
@Transactional
public void businessMethod() throws Exception {
    try (Connection other = dataSource.getConnection()) {
        System.out.println(other.getTransactionIsolation());
    }
}
```

This is an illustrative snippet assuming a `DataSource`, not a complete file. If `dataSource` is a pool, `getConnection()` may borrow **a different connection** rather than the connection Spring bound to the current transaction. The result may reflect the pool's baseline, not the effective isolation of the business SQL inside T.

To measure the isolation of **the transactional connection itself** in Spring JDBC, use `JdbcTemplate.execute(ConnectionCallback)` as in the demo code, or follow the `DataSourceUtils.getConnection(dataSource)` contract and remember to release with the matching API:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    int effectiveLevel = connection.getTransactionIsolation();
    System.out.println(effectiveLevel);
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

This is also just a snippet, requiring imports for `DataSource`, `Connection`, `DataSourceUtils`, and a transaction-managed context. Do not call `connection.close()` arbitrarily on a connection bound by Spring if you obtained it through a transaction-aware mechanism without understanding the release rules.

Another useful check is:

```java
Integer declaredLevel = TransactionSynchronizationManager
    .getCurrentTransactionIsolationLevel();
```

However, this value can be `null` when the transaction uses `Isolation.DEFAULT`. `null` does not mean the database is running `TRANSACTION_NONE` or has no isolation. To find the **actual** JDBC isolation, read `Connection.getTransactionIsolation()`.

## 11. Why is the connection pool part of the answer?

A pool does more than reduce connection-creation cost. It can also manage **the default state of every connection**:

- Isolation level.
- `autoCommit`.
- Read-only state.
- Default catalog/schema.
- Initialization SQL or tool/driver-specific session-level settings.

HikariCP has the `transactionIsolation` property, accepting values like `TRANSACTION_READ_COMMITTED` and `TRANSACTION_REPEATABLE_READ`. If the property is **unset**, Hikari normally inherits whatever level the driver/database assigns to the connection. If the property **is set**, connections from the pool can have a baseline different from the DB default.

This clarifies the difference between two statements:

- **"The database server's default is READ_COMMITTED."** This is a server setting/documented default.
- **"The connection Spring uses has REPEATABLE_READ isolation."** This is the state of the JDBC resource **in the application**; it may come from the pool or session settings.

Spring `Isolation.DEFAULT` generally chooses **not to override the second statement**, rather than querying the server for the first statement and forcing the connection back to it.

### State "leaking" across connection uses

If the application manually runs a SQL command changing **session isolation** or calls `Connection.setTransactionIsolation` outside the transaction manager, the pool may detect and reset it via supported APIs, or may **be unaware** of a change performed solely via session-specific SQL. As a result, a connection returned to the pool could carry unexpected state to the next borrower.

Therefore:

1. Choose one clear place to configure baseline isolation (database/session/pool).
2. Prefer `@Transactional(isolation = ...)` for per-transaction overrides so the transaction manager governs its lifecycle.
3. Avoid changing isolation mid-transaction while SQL is executing when the database has restrictions or implicit-commit behavior.
4. Do not assume the pool automatically cleans up every hand-written `SET SESSION ...` statement.
5. Use integration tests to observe the actual level via the transactional connection.

## 12. Which read anomalies does isolation affect? `DEFAULT` does not answer that question

When multiple transactions run concurrently, the DBMS must decide which records statements are permitted to see. The four familiar JDBC isolation levels relate to:

- **Dirty read:** one transaction reads data that another transaction has not committed yet.
- **Non-repeatable read:** the same row is read twice in one transaction and returns different values because another transaction committed.
- **Phantom:** the same query predicate returns a different set of rows after another transaction commits inserted/deleted matching rows.
- **Serialization anomalies:** the outcome of concurrent transactions is not equivalent to any valid serial execution schedule.

Overview table according to classical definitions of isolation levels; specific DBMSs may implement stronger or subtler behavior than some intuitions in the table:

| JDBC level | Dirty read | Non-repeatable read | Phantom per classical definition |
| --- | --- | --- | --- |
| `READ_UNCOMMITTED` | Possible | Possible | Possible |
| `READ_COMMITTED` | No | Possible | Possible |
| `REPEATABLE_READ` | No | No by level definition | Depends on definition/DBMS |
| `SERIALIZABLE` | No | No | No in a true serializability model |

**Do not try to add `DEFAULT` as a row in the table**: `DEFAULT` is not a technical engine level. If `DEFAULT` resolves to `READ_COMMITTED`, analyze read anomalies using that database's `READ_COMMITTED` semantics; if it resolves to `REPEATABLE_READ`, examine that engine's actual `REPEATABLE_READ` semantics.

For example, PostgreSQL uses MVCC and implements `REPEATABLE READ` via snapshot isolation with properties that do not map one-to-one onto classical intuitions about phantoms. MySQL InnoDB has consistent nonlocking reads and locking reads with different mechanics. From a Spring enum alone, you **cannot** deduce all engine details.

### An illustrative read schedule

```text
T1 (DEFAULT -> READ_COMMITTED)     T2
--------------------------------  --------------------------
BEGIN
SELECT price FROM products WHERE id=1  -> 100
                                  BEGIN
                                  UPDATE products SET price=120 WHERE id=1
                                  COMMIT
SELECT price FROM products WHERE id=1  -> may be 120
COMMIT
```

This is a **conceptual example of a non-repeatable read**. The observed value depends on the DBMS, statement type, the connection's actual isolation, and transaction T2. If `DEFAULT` is actually `REPEATABLE_READ`, the same read schedule can return the same value from the same snapshot across both reads, depending on the engine.

**Learning point:** observe or determine the effective isolation first, and only then evaluate concurrency anomalies. Do not write concurrency tests under the assumption that "Spring's default is always READ_COMMITTED."

## 13. Why is leaving `Isolation.DEFAULT` often a good choice?

Many applications have straightforward transactional services:

```java
@Service
public class CatalogService {
    @Transactional(readOnly = true)
    public ProductView load(long id) {
        return repository.load(id);
    }
}
```

This snippet illustrates a service with an application repository/DTO. `@Transactional(readOnly = true)` still leaves the **default isolation**, rather than turning into a different isolation level just because it is read-only.

Keeping `DEFAULT` is usually appropriate when:

- The DBA or platform team has defined a **sensible isolation policy at the DB/pool** for the system's workload.
- Transactions do not require special consistency mechanisms beyond the default.
- The application runs across environments where each environment's resource policy is explicitly managed and tested.
- You want to avoid the cost/constraints of forcing `SERIALIZABLE` unnecessarily.
- You do not want every service method repeating the same isolation level when a unified policy already lives at the datasource layer.

However, `DEFAULT` **does not mean "just let it run and it is safe."** For operations such as placing orders, deducting inventory, allocating sequence numbers, transferring funds, or confirming payments, you still must design invariants, constraints, optimistic locking, conditional `UPDATE`s, retries on serialization errors, and proper concurrency tests. Isolation is only one piece of a consistency strategy.

### When should you declare an explicit level?

When business logic has a clear concurrency requirement and the DB/transaction manager supports it:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void allocateSequence() {
    // ...
}
```

For this request to be applied, the snippet requires the method to be called through the Spring proxy and **start a new physical transaction**. If the method only joins an outer T with weaker isolation, do not assume this annotation automatically upgrades T. You can use validation to catch mismatches, or structure transaction boundaries so the owning method starts T at the right level from the outset.

Even at `SERIALIZABLE`, the DB can detect a serialization conflict and **abort a transaction**; the application needs safe retry and idempotency strategies. Do not interpret a high isolation level as "never hits deadlocks or errors."

## 14. A new transaction, a participant, and an independent transaction

Quick decision table:

| Does caller have T? | Method propagation | Isolation declaration | What Spring JDBC typically does |
| --- | --- | --- | --- |
| No | `REQUIRED` | `DEFAULT` | Starts new T, keeps resource connection isolation |
| No | `REQUIRED` | `READ_COMMITTED` | Starts new T, requests JDBC `READ_COMMITTED` |
| Yes | `REQUIRED` | `DEFAULT` | Joins T, uses T's isolation |
| Yes | `REQUIRED` | `SERIALIZABLE` | By default joins T and does not change isolation; validation can reject mismatch |
| Yes | `REQUIRES_NEW` | `DEFAULT` | Suspends outer T, opens new T using the new connection's resource default |
| Yes | `REQUIRES_NEW` | `READ_COMMITTED` | Opens new T, requests `READ_COMMITTED` |
| Yes | `NESTED` | `DEFAULT` | Uses a savepoint within T (if supported), inherits T's isolation |
| No | `SUPPORTS` | `DEFAULT` | Does not create a physical transaction just for the annotation |

**Read the table from left to right.** If you start from the isolation enum and skip "new transaction or join?", you will easily draw the wrong conclusion.

### Proxy boundaries that can alter the table

In Spring AOP's default proxy mode, `@Transactional` requires calls **through the Spring proxy**. For example:

```java
@Service
public class WrongService {

    public void outer() {
        inner();
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void inner() {
        // ...
    }
}
```

`outer()` calls `this.inner()`, so the internal invocation does not pass back through the bean's proxy. If there is no other enclosing transaction boundary, `inner()` may receive no transaction advice even though the annotation is present. Switching from JDK proxies to CGLIB **does not fix** self-invocation in proxy mode.

Extracting the transactional method to another bean, placing the annotation on the entrypoint the caller actually invokes, or using the programmatic transaction API are clearer choices.

## 15. Verifying in a real environment

Before concluding what `Isolation.DEFAULT` resolves to in production, inspect from **the application's execution path**.

### 15.1. Reading the JDBC connection participating in the transaction

```java
@Transactional
public int currentIsolation(JdbcTemplate jdbc) {
    Integer level = jdbc.execute(
        (ConnectionCallback<Integer>) Connection::getTransactionIsolation
    );
    if (level == null) {
        throw new IllegalStateException("No JDBC isolation reported");
    }
    return level;
}
```

This is a **conceptual snippet**, not a standalone class. The method annotation only works if processed by Spring's transaction infrastructure; imports match the project in section 8. In real service code, injecting `JdbcTemplate` via the constructor is usually better than passing it as an argument.

Most importantly, `JdbcTemplate` obtains **the connection belonging to the current transaction**. If you merely call `dataSource.getConnection()` from another thread or borrow a separate connection, the result may not reflect the transaction under investigation.

### 15.2. Checking session settings in the DBMS

DBMSs provide their own tools. For example:

```sql
-- PostgreSQL: isolation level of the current transaction
SHOW transaction_isolation;
```

```sql
-- MySQL: isolation level of the current session
SELECT @@transaction_isolation;
```

These are syntax for two specific DBMSs; **do not run both blocks verbatim on H2**. They must execute on the exact connection/session serving the transaction you want to inspect; running in a standalone SQL client may only show that client's session level, not the application's connection.

When investigating differences across dev/staging/prod, compare:

1. Database name/version/engine and server configuration.
2. Driver and JDBC URL.
3. HikariCP/pool isolation property and initialization SQL.
4. Specific transaction manager (`DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager`, or another manager).
5. Annotations/propagation and whether the method actually starts a new T or joins T.
6. `Connection.getTransactionIsolation()` **directly inside the transactional method**.
7. Concurrency tests and DBMS-specific query behavior.

### 15.3. Using logging at the right level

In a debugging environment, you can add:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

This is a diagnostic option, **not required** for the demo's stdout. Do not enable TRACE on high-load systems without evaluating log volume and privacy. Transaction manager logs help trace start/participate/commit/rollback, though to know the effective JDBC level you should still read the exact connection or session.

## 16. Common mistakes and fixes

| Claim or symptom | Why it can be wrong | How to handle it |
| --- | --- | --- |
| "`Isolation.DEFAULT` means `READ_COMMITTED`." | DEFAULT is only the `-1` sentinel | Inspect the connection; check DB/pool |
| "`DEFAULT` means no isolation." | It is not `TRANSACTION_NONE` | Distinguish Spring metadata from JDBC level |
| "Spring always resets isolation to the DB default." | With DEFAULT, Spring JDBC usually **does not override the connection** | Check resource state at borrow time |
| "H2 defaults to READ_COMMITTED so the demo must print READ_COMMITTED." | The demo intentionally configures Hikari `REPEATABLE_READ` | Check `spring.datasource.hikari.transaction-isolation` |
| "An inner `SERIALIZABLE` method upgrades outer's isolation." | Inner `REQUIRED` only joins the existing physical T | Set the right boundary or enable validation |
| "An inner `DEFAULT` method in `REQUIRES_NEW` inherits outer's isolation." | `REQUIRES_NEW` creates its own T, usually on a different connection | Read the isolation of the inner connection |
| "Same DB name means same connection." | A connection pool hands out multiple connections/sessions | Use the transaction-bound connection to measure |
| "After an explicit override, the pool keeps that level forever." | Spring/pool manage resetting when the transaction ends | Test `DEFAULT after override` |
| "Reading `TransactionSynchronizationManager` alone tells you the level." | `DEFAULT` can yield `null` for context isolation | Use `Connection.getTransactionIsolation()` |
| "READ_ONLY is synonymous with SERIALIZABLE." | Read-only is a different attribute | Check `isolation` and read-only separately |
| "Raising isolation fixes every lost update." | Still depends on DB, SQL, locking, constraints, and retries | Design invariants and run concurrency tests |
| "All transaction managers support custom isolation." | Some resources/managers do not support it | Check API and driver; `DEFAULT` may be required |
| "You can switch DBs without testing when using DEFAULT." | Resource defaults may differ | Maintain integration/concurrency tests |
| "Annotation present means the interceptor ran." | Self-invocation, `new`, unproxied methods | Verify the Spring bean/proxy call path |
| "Session SQL is always safe mid-transaction." | Some isolation-changing statements have timing/commit constraints | Use the transaction manager and understand the DBMS |

## 17. Scenario exercises

### Scenario A: same code, two datasources

Service:

```java
@Transactional(isolation = Isolation.DEFAULT)
public void report() {
    // ...
}
```

In environment A, resource connections have `READ_COMMITTED` isolation. In environment B, the pool is configured with `REPEATABLE_READ`.

**Question:** Does Spring automatically make both environments behave the same?

**Answer:** No. The same `DEFAULT` metadata only indicates Spring does not apply a specific level; effective isolation can differ per each resource's connections. Test both environments or establish a consistent policy.

### Scenario B: outer `READ_COMMITTED`, inner `SERIALIZABLE`

Outer already started T; inner `REQUIRED` joins the same T; default validation is off.

**Question:** Does inner execute at `SERIALIZABLE`?

**Answer:** Typically no; it runs inside T at `READ_COMMITTED`. If validate-existing-transaction is enabled, the incompatible request can be rejected instead of ignored.

### Scenario C: outer `READ_COMMITTED`, inner `REQUIRES_NEW DEFAULT`

The pool has `TRANSACTION_REPEATABLE_READ`.

**Question:** What is inner's isolation?

**Answer:** If the driver/manager support it and the new connection from the pool has the configured baseline, inner runs at `REPEATABLE_READ`. Outer continues at `READ_COMMITTED` after inner finishes.

### Scenario D: printing `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()`

A new method with `Isolation.DEFAULT` returns `null` from the context API.

**Question:** Does this prove the DB has no isolation?

**Answer:** No. Here `null` can simply mean Spring did not record an isolation override in transaction metadata. You must read `Connection.getTransactionIsolation()`.

### Scenario E: no SQL executed at all

A method starts a new `@Transactional` transaction and reads connection isolation, without any SELECT/UPDATE.

**Question:** Is measuring the isolation level meaningful?

**Answer:** Yes, because it confirms which level the JDBC connection is using, though it **does not yet prove** which concurrency anomalies the DBMS will prevent on real data. To verify transactional behavior, write tests with multiple connections and appropriate SQL.

### Scenario F: moving from H2 tests to MySQL InnoDB production

H2 runs `READ_COMMITTED` by default, MySQL InnoDB typically defaults to `REPEATABLE_READ`, and the service uses `Isolation.DEFAULT`.

**Question:** Can test and production semantics be treated as identical?

**Answer:** No. First inspect the actual pool/session; if isolation differs, concurrent read/lock observations may differ. H2 tests are useful for proving Spring wiring, but do not replace integration tests on the production engine.

## 18. Checklist for choosing and verifying `ISOLATION_DEFAULT`

1. Identify the actual transaction manager and the resource it manages.
2. Understand that `Isolation.DEFAULT` is **`ISOLATION_DEFAULT = -1`**, not a JDBC isolation level.
3. Verify that `@Transactional` runs through the Spring proxy and whether the method actually opens a new physical transaction.
4. If `REQUIRED` joins an existing T, T's isolation is used; do not expect an inner annotation to change isolation.
5. If `REQUIRES_NEW`, check the isolation of the **new connection/resource**, along with connection pool exhaustion risks.
6. If using a pool, check the `transactionIsolation` policy and initialization/session settings, not just the DB default.
7. Measure the effective level with `Connection.getTransactionIsolation()` **on the transaction-bound connection**.
8. Verify that Spring/driver restore isolation after a transaction with explicit isolation ends.
9. If a service has specific consistency requirements, place isolation at the proper outer physical transaction boundary or enable validation to detect mismatches.
10. Do not infer full MVCC/locking/phantom semantics from the isolation level name alone; test on the actual DBMS.
11. Keep business invariants correct with constraints, conditional updates, locks/retries when needed; isolation does not replace all protective layers.
12. Document the expected default isolation per environment; use integration tests to alert when datasource/pool/database configuration changes.

## Official references

- Spring Framework — `@Transactional` settings and default isolation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `TransactionDefinition` API, `ISOLATION_DEFAULT`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — `Isolation` enum: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Isolation.html
- Spring Framework — `DataSourceTransactionManager`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `DataSourceUtils` and JDBC connection preparation: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- HikariCP — Configuration, `transactionIsolation` property: https://github.com/brettwooldridge/HikariCP/wiki/Configuration
- H2 Database — Transaction Isolation: https://h2database.com/html/advanced.html#transaction_isolation
- PostgreSQL — `SET TRANSACTION`, `READ COMMITTED` default: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels, `REPEATABLE READ` default: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html