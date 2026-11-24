# `readOnly` Is a Hint Whose Effect Depends on the Transaction Manager, JDBC Driver, and Database

## Learning Objectives

After this lesson, you will be able to:

1. Explain what `@Transactional(readOnly = true)` actually declares in the Spring Framework.
2. Distinguish between **Spring transaction metadata**, JDBC `Connection.setReadOnly(true)`, Hibernate/JPA optimizations, and **actual write rules enforced by the database**.
3. Understand why `readOnly = true` is **not a universal ban on `INSERT`, `UPDATE`, or `DELETE`**; behavior depends on the manager, driver, connection, and DBMS.
4. Know how to configure a stronger read-only policy on supported databases, such as `DataSourceTransactionManager#setEnforceReadOnly(true)`, and the limitations of this approach.
5. Predict what happens when a `REQUIRED` method joins a transaction whose read-only flag differs from its own annotation.
6. Run an example with **Java 17+, Spring Boot 3.3.5, Spring JDBC, and H2** to observe the Spring flag, JDBC connection state, `UPDATE`, commit, and rollback.
7. Design safe query services, avoiding confusion between read-only and database permissions, isolation levels, timeouts, or routing to read replicas.

**Main theme:** `readOnly` is **a transaction hint** that the infrastructure layer can use to optimize or enforce constraints, **not a guarantee that every DBMS will block write operations**.

---

## 1. The Short and Accurate Answer

Consider this service:

```java
@Service
public class ProductQueryService {

    @Transactional(readOnly = true)
    public ProductView load(long productId) {
        return repository.findView(productId);
    }
}
```

This is an illustrative snippet; `ProductView`, `repository`, and domain imports belong to a real application. When Spring AOP intercepts a call to `load()` from another bean, the transaction definition carries `readOnly=true`. That means **"this transaction is expected to be primarily read-only"**.

What **can happen**:

- The Spring transaction infrastructure publishes the **read-only flag** to code participating in the transaction.
- A JDBC transaction manager may call `Connection.setReadOnly(true)` on the connection before the transaction to **hint to the driver/DBMS to optimize**.
- A JPA/Hibernate transaction manager may adjust the ORM's **flush mode** or dirty checking mechanism to reduce overhead when only reading.
- If **additionally configured** and supported by the DBMS, the manager may send SQL such as `SET TRANSACTION READ ONLY` so the DBMS **rejects certain data-modifying operations**.
- The read-only flag can be used in an **application-designed routing** mechanism, such as selecting a read replica when starting an eligible transaction.

What **must not be inferred automatically**:

- `readOnly=true` **is not by default equivalent to a SELECT-only database permission**.
- It **does not** cause all `jdbc.update(...)` calls to fail on every DBMS.
- It **does not** force Spring to automatically roll back any transaction that executed an `UPDATE`.
- It **does not** guarantee that queries use a replica or run faster.
- It **does not** turn a method running inside an existing read-write transaction into an independent physical read-only transaction.
- It **does not** replace transaction isolation, rollback rules, timeouts, security, or access control.

The accurate answer to **"Is an `UPDATE` inside `@Transactional(readOnly=true)` blocked?"** is: **it depends on the transaction manager, JDBC driver, DBMS, how read-only is configured, and whether the method actually opens a new transaction**.

## 2. Do Not Confuse the Four Layers of Read-Only

Four layers use the term "read-only" but do not share the same technical contract.

| Layer | Flag or API | What It Expresses | Does It Guarantee Blocking All Writes? |
| --- | --- | --- | --- |
| Spring transaction definition | `@Transactional(readOnly = true)` | The method's intent regarding the transaction | **No** |
| Spring thread-bound transaction context | `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | The current transaction flag published by Spring | **No** |
| JDBC connection | `Connection.setReadOnly(true)`, `isReadOnly()` | A hint/mode handled by the driver and DBMS | **Not universally** |
| DBMS transaction / access permissions | SQL read-only transaction, `GRANT`/`REVOKE` permissions, read-only replica | Policies and mechanisms enforced by the engine | **Depends on policy, SQL command, DBMS, and actual permissions** |

In applications using JPA/Hibernate there is another layer: **persistence context behavior**, such as flush mode or dirty checking. Hibernate may skip certain entity synchronization work in a read-only transaction, but it does not turn the Spring annotation into a "write-blocking firewall" for every `nativeQuery`, `JdbcTemplate`, or direct SQL statement.

### An Example of the Difference

```text
Spring @Transactional(readOnly=true)
             |
             +--> Thread transaction metadata: readOnly = true
             |
             +--> DataSourceTransactionManager
                       |
                       +--> JDBC Connection.setReadOnly(true)
                                 |
                                 +--> Driver/DBMS may optimize or ignore
                       |
                       +--> SQL UPDATE may still be executed
                                 |
                                 +--> Some DBMSs accept it
                                 +--> Some DBMSs/modes reject it
```

Someone reading a Spring log showing `"readOnly=true"` only knows the **declaration/transaction context**. From that alone, one cannot accurately conclude what `Connection.isReadOnly()` returns, whether the database is in an SQL read-only transaction, or whether an `UPDATE` statement was blocked.

## 3. What Is the Default of `@Transactional`?

In the Spring Framework, if `readOnly` is omitted, `@Transactional` defaults to:

```java
@Transactional(readOnly = false)
public void updateSomething() {
    // ...
}
```

Similarly, `@Transactional` with no arguments uses `REQUIRED` propagation, `DEFAULT` isolation, the read-write flag, and default rollback rules. Those attributes are **different dimensions**.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT,
    readOnly = true,
    timeout = 30
)
public Report readReport() {
    // ...
}
```

The snippet above declares four aspects:

- `REQUIRED`: creates a transaction if none exists, or joins a compatible existing transaction.
- `DEFAULT`: does not request a specific JDBC isolation level different from the resource default.
- `readOnly=true`: signals **read-only** intent; the infrastructure decides how to handle it.
- `timeout=30`: requests a timeout for a new transaction, if supported by the transaction manager. A timeout does not turn read-only into "write-prohibited".

**Do not infer that `readOnly=true` automatically raises isolation to `SERIALIZABLE`.** The two attributes have separate purposes. A read-only transaction can run at `READ_COMMITTED` or `REPEATABLE_READ` depending on the resource.

## 4. Spring JDBC: `Connection.setReadOnly(true)` Is a Hint

With `DataSourceTransactionManager`, when starting a **new JDBC transaction** whose definition has `readOnly=true`, Spring typically prepares the connection via `DataSourceUtils.prepareConnectionForTransaction(...)` and calls `Connection.setReadOnly(true)` before executing the transaction. At the end of the transaction, Spring attempts to **restore the connection state** when needed to avoid affecting the next borrower of the connection from the pool.

The JDBC API describes `Connection.setReadOnly(boolean)` as a **hint to the driver** so the database can optimize; actual behavior **is not guaranteed to be identical** across all drivers. Some drivers/DBMSs may reject write statements; others only use the flag for optimization, or ignore it.

### H2 Is a Clear Counterexample

According to H2's `JdbcConnection` Javadoc:

- `setReadOnly(boolean)` accepts the parameter but **ignores the value** when the database is opened in normal writable mode.
- `isReadOnly()` reflects whether the database itself was actually opened in read-only mode.
- H2 documentation clearly states: the JDBC read-only hint **does not by itself forbid writes**.

Therefore, in a default in-memory H2 database, a Spring `@Transactional(readOnly=true)` transaction can have:

```text
Spring transaction context: readOnly = true
JDBC connection: Connection.isReadOnly() = false
Database: UPDATE still succeeds
```

This is **not** Spring "forgetting the annotation"; it is the specific behavior of the JDBC driver/DBMS. The complete example in section 8 will demonstrate this state and check the data after commit.

### Note on `Connection.isReadOnly()`

This value is reported by the JDBC driver. With H2, it reflects **database-level read-only**, not Spring metadata. With other drivers, semantics may differ. Therefore:

- Use `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` to observe the **Spring transaction flag**.
- Use `Connection.isReadOnly()` to observe the **JDBC driver's read-only status**.
- Use **a safe SQL test in a test environment** to know whether the DBMS actually blocks write operations.

Do not perform destructive write tests in production just to verify a flag; use a test schema, transaction rollback, and a user with restricted privileges.

## 5. Transaction Managers Can Implement Read-Only Differently

### 5.1. `DataSourceTransactionManager` and `JdbcTransactionManager`

For JDBC, `DataSourceTransactionManager` uses Spring-managed connections; `JdbcTransactionManager` extends that approach and adds JDBC exception translation on certain commit/rollback paths.

In a common configuration:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

`@Transactional(readOnly=true)` is translated into the JDBC hint `Connection.setReadOnly(true)` when starting a new transaction. By default, **you should not treat this flag as a mandatory DML-blocking mechanism**.

### 5.2. `DataSourceTransactionManager#setEnforceReadOnly(true)`

Spring JDBC has a **stronger** configuration:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);

    manager.setEnforceReadOnly(true);
    return manager;
}
```

**This is an alternative configuration option**, not to be used at the same time as the `@Bean transactionManager` in the H2 program in section 8. For DBMSs that understand the corresponding syntax, Spring can send SQL **`SET TRANSACTION READ ONLY`** for a new transaction declared as read-only.

According to the Spring Javadoc, this approach is suitable for DBMSs such as **PostgreSQL, Oracle, and MySQL** in supported versions/configurations. It goes beyond the **JDBC hint** and can instruct the database to actually **reject DML within the transaction**.

However:

- Enable it only if the DBMS/driver and transaction execution path support **the exact syntax, timing, and semantics**.
- It can cause transaction initialization errors if the database does not understand the SQL being sent.
- When a method merely joins an existing transaction, you cannot assume it is allowed to switch that physical transaction to a new read-only one.
- You must test **on the target DBMS**, verifying that `INSERT`/`UPDATE` statements are rejected as expected and rolling back modified data.
- **Do not enable this configuration in the H2 demo below.** The demo's goal is to observe H2 ignoring the JDBC hint, not to try an SQL enforcement syntax not proven suitable for H2.

This is a **database transaction policy**, not a substitute for secure DB user permissions. If the security requirement is "the account must not modify data", use restricted DB privileges or a read-only database replica.

### 5.3. `JpaTransactionManager` and Hibernate

With JPA/Hibernate, Spring Data JPA notes that `readOnly=true` can lead to **optimizations in the JPA provider**, such as setting the Hibernate flush mode to `MANUAL` to avoid unnecessary dirty checking/auto-flushing in read-only transactions.

Example:

```java
@Service
public class CatalogQueryService {
    private final ProductRepository repository;

    public CatalogQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Product> findAvailable() {
        return repository.findByAvailableTrue();
    }
}
```

This is a Spring Data JPA snippet; the domain types and JPA dependencies are not declared in the JDBC demo project. With Hibernate, specific optimizations also depend on the version and how Spring configures the Session/EntityManager. Do not equate "Hibernate does not auto-flush certain entities" with "every native SQL write will be rejected by the database".

Some misconceptions to avoid:

- `@Transactional(readOnly=true)` does not automatically prevent the application from calling `repository.save(...)` at the Java API level.
- Flush mode/dirty checking can change, so you **should not** rely on `save` or mutating an entity and ending the transaction having the same behavior across every configuration.
- Native SQL, `JdbcTemplate`, stored procedures, and other components can go through different execution paths.
- If you need a guarantee of no writes, you must apply **DB-level read-only transactions or data permissions** appropriate to your actual stack, and test them.

**Spring Data JPA repositories:** CRUD methods implemented by `SimpleJpaRepository` have inherited transaction configuration; read operations are typically configured read-only, while modifying operations are read-write. Declared query methods do not automatically receive every transactional configuration. The transaction at the **service boundary** is usually more important than annotations on individual repository methods, because it determines the final physical transaction.

### 5.4. `JtaTransactionManager` and Other Managers

JTA, reactive, and custom transaction managers have their own capabilities. A manager may receive `TransactionDefinition.isReadOnly()` yet **not translate that flag into JDBC `Connection.setReadOnly(true)` or SQL enforcement**. Do not deduce that an annotation with the same parameters produces the same database behavior on every platform.

With `ReactiveTransactionManager`, the transaction context is propagated along the reactive pipeline rather than relying on the same thread-local JDBC connection as this example. The H2/JDBC exercise in section 8 demonstrates **imperative JDBC behavior**; applying it to R2DBC requires verifying the specific driver and transaction manager separately.

## 6. What If the DB Still Allows `UPDATE` Inside Read-Only?

Example service:

```java
@Transactional(readOnly = true)
public void updateByAccident() {
    jdbcTemplate.update(
        "UPDATE inventory SET quantity = quantity + 1 WHERE id = ?",
        1L
    );
}
```

This is only an illustrative snippet. The consequence depends on the DBMS:

- With writable H2 JDBC where `setReadOnly` is ignored, the `UPDATE` can succeed and the transaction **commits** normally.
- With a PostgreSQL transaction actually set to **`READ ONLY`** at the SQL layer, prohibited data-modifying operations can be rejected by the DB.
- With a database user having only `SELECT`, `UPDATE` is rejected due to **database permissions**, regardless of the Spring flag.
- With JPA/Hibernate, certain entity changes might not auto-flush due to read-only optimizations, but this does not mean all forms of writing are blocked.

**Conclusion:** `readOnly=true` does not automatically **roll back** a transaction when it contains a valid `UPDATE`. If the DB allows the SQL and the method returns normally, Spring can commit.

### When the Method Throws an Exception

`readOnly=true` does not change default rollback rules:

```java
@Transactional(readOnly = true)
public void writeThenFail() {
    jdbcTemplate.update(
        "UPDATE inventory SET quantity = quantity + 10 WHERE id = 1"
    );
    throw new IllegalStateException("Business failure");
}
```

In a new JDBC transaction, if the `UPDATE` succeeded but `IllegalStateException` escapes through the interceptor, Spring by default **rolls back**. This is a consequence of **rollback rules**, not of `readOnly=true` prohibiting writes.

Therefore, distinguish three questions: **Does the DB accept the statement? Does the transaction interceptor decide to roll back? Is the caller already in another transaction?**

## 7. `REQUIRED` Inherits the Existing Transaction; Read-Only Is Not Applied Per Method

A frequent source of bugs is that **the inner method's annotation does not necessarily become the new mode for the physical transaction**.

Suppose:

```java
@Service
public class ReportFacade {
    private final ReportRepository reports;

    public ReportFacade(ReportRepository reports) {
        this.reports = reports;
    }

    @Transactional(readOnly = true)
    public Report run() {
        return reports.buildReportAndMaybeUpdate();
    }
}
```

In another bean:

```java
@Service
public class ReportRepository {

    @Transactional(readOnly = false)
    public Report buildReportAndMaybeUpdate() {
        // ...
    }
}
```

The two snippets are illustrative only, not standalone runnable Java classes. When `run()` creates transaction T with `readOnly=true`, the inner method using the default `REQUIRED` **joins T**. It does not open a new read-write transaction merely because of `readOnly=false`.

If the DB/driver does not enforce read-only, the write statement in the inner method can still execute. If the DB already enforced read-only for T, the inner method usually **cannot** break that policy solely via `readOnly=false`.

### The Reverse Case

If the outer method has `@Transactional` read-write, and the inner has `@Transactional(readOnly=true)` and `REQUIRED`, the inner also **joins the outer transaction**. Do not expect Spring to always temporarily enable read-only just for a sub-segment of the same physical T.

```text
Caller
  |
  v
Outer @Transactional(readOnly=false) -> BEGIN read-write T
  |
  v
Inner @Transactional(readOnly=true), REQUIRED -> join T
  |
  v
SQL uses physical transaction T
  |
  v
Outer -> COMMIT/ROLLBACK T
```

Normally, resource/connection policies are set **when T begins**, not "mode-switched" every time Java invokes another method.

### `validateExistingTransaction=true`

`AbstractPlatformTransactionManager` has an option:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);

manager.setValidateExistingTransaction(true);
```

This is an alternative configuration snippet. When validation is enabled, the manager can **reject a read-write method joining a transaction already marked read-only by Spring**, instead of silently letting it run inside T. For example, an outer read-only with an inner `REQUIRED` read-write can throw `IllegalTransactionStateException` when joining T.

Important:

- This is a **guardrail in the transaction infrastructure**, not a comprehensive database permission policy.
- It does not prove that every statement emitted from **the read-only method itself** will be blocked.
- It is not enabled by default in all applications; changing the flag can alter the behavior of nested services.
- Verifying whether the infrastructure supports validation and the exception path requires testing in a real system.

### `REQUIRES_NEW` and `NESTED`

| Inner Method | When Outer Already Has T | Effective Read-Only |
| --- | --- | --- |
| `REQUIRED`, `readOnly=false` | Joins T | Usually uses T's policy; does not open a new transaction |
| `REQUIRED`, `readOnly=true` | Joins T | Usually uses T's policy |
| `REQUIRES_NEW`, `readOnly=false` | Suspends T, opens new transaction | Policy of the new transaction/connection |
| `REQUIRES_NEW`, `readOnly=true` | Opens independent new transaction | Manager has the opportunity to apply read-only hint/enforcement to the new transaction |
| `NESTED`, `readOnly=true` | With JDBC, creates a savepoint within the same T | No independent read-only connection/physical transaction |

Choosing `REQUIRES_NEW` solely to "turn on read-write inside a read-only outer" is a major change to atomicity: the inner transaction can commit independently even if the outer rolls back. You must consider business semantics and connection pooling, not just the read-only flag.

---

## 8. Runnable Demo: H2 Ignores the JDBC Read-Only Hint While Spring Still Manages Transactions

This example is designed to prove **three independent facts**:

1. The Spring transaction context knows `readOnly=true`.
2. H2 `JdbcConnection.setReadOnly(true)` **does not turn a writable database's connection into a read-only database**.
3. On H2, an `UPDATE` inside a read-only method **can commit** when the method completes normally, or **roll back** when an unchecked exception escapes.

In addition, a read-only outer service calls a `REQUIRED` read-write inner service through **another Spring bean**, showing that the inner flag does not automatically change the outer's transaction policy.

### 8.1. Project Structure

```text
read-only-hint-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/readonly/
    │   │   ├── WriteService.java
    │   │   ├── ReadOnlyService.java
    │   │   └── ReadOnlyHintApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/
        └── java/example/readonly/
            └── ReadOnlyHintApplicationTest.java
```

Use Gradle with JDK 17+ and Spring Boot 3.3.5. You can generate the structure with Spring Initializr (Java 17, Spring Web not needed, JDBC and H2) and replace the files listed below. The program is a CLI and does not run a web server.

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'read-only-hint-demo'
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

We use **Spring JDBC**, not Hibernate, in the demo. This avoids ORM flush modes affecting the result. H2 is an in-memory test database. Using JDBC here does not mean conclusions about H2 also hold for PostgreSQL/MySQL/Oracle.

### 8.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:read_only_hint_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

`setEnforceReadOnly(true)` is not configured on the transaction manager. This is intentional: we are demonstrating that **the JDBC hint does not guarantee write blocking**. `DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive until the JVM exits. Each scenario resets the quantity back to the initial value so observations do not accumulate.

### 8.5. `src/main/resources/schema.sql`

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    quantity BIGINT NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory (id, quantity) VALUES (1, 100);
```

The schema has only one row. After each method, the caller reads data **outside the service transaction** to check the final `quantity`. Looking only at the row count returned by `jdbc.update(...)` mid-transaction does not prove that a commit took place.

### 8.6. `src/main/java/example/readonly/WriteService.java`

```java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;

    public WriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = false
    )
    public boolean incrementRequired() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 5 WHERE id = 1"
        );
        return TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();
    }
}
```

This method **declares read-write**. If the caller has no transaction, it opens a read-write transaction and the Spring current transaction flag is `false`. If the method is called through the bean proxy inside an outer transaction that is **already read-only**, `REQUIRED` joins the outer T; the inner method's `readOnly=false` **does not automatically override** T's flag/resource policy.

`WriteService` is separated into its own Spring bean so `ReadOnlyService` calls it **through the transaction proxy**, avoiding self-invocation issues.

### 8.7. `src/main/java/example/readonly/ReadOnlyService.java`

```java
package example.readonly;

import java.sql.Connection;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReadOnlyService {
    private final JdbcTemplate jdbc;
    private final WriteService writer;

    public ReadOnlyService(JdbcTemplate jdbc, WriteService writer) {
        this.jdbc = jdbc;
        this.writer = writer;
    }

    private String flags() {
        Boolean jdbcReadOnly = jdbc.execute(
            (ConnectionCallback<Boolean>) Connection::isReadOnly
        );
        if (jdbcReadOnly == null) {
            throw new IllegalStateException(
                "JDBC connection returned no read-only status"
            );
        }

        boolean springReadOnly = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();

        return "spring=" + springReadOnly +
               ", jdbc=" + jdbcReadOnly +
               ", active=" + active;
    }

    @Transactional(readOnly = true)
    public String observe() {
        return flags();
    }

    @Transactional(readOnly = true)
    public String updateDespiteHint() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 10 " +
            "WHERE id = 1"
        );
        return flags();
    }

    @Transactional(readOnly = true)
    public void updateThenFail() {
        jdbc.update(
            "UPDATE inventory SET quantity = quantity + 20 " +
            "WHERE id = 1"
        );
        throw new IllegalStateException("demonstration rollback");
    }

    @Transactional(readOnly = true)
    public String outerReadOnlyCallsRequiredWriter() {
        boolean outerFlag = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        boolean innerFlag = writer.incrementRequired();

        return "outer=" + outerFlag + ", inner=" + innerFlag;
    }
}
```

**Crucial detail for measuring the right connection:** `flags()` uses `JdbcTemplate.execute(ConnectionCallback)`. `JdbcTemplate` obtains the connection via `DataSourceUtils`, so when a JDBC transaction is active, it operates on the **connection already bound by Spring to the transaction**. If you manually open a second connection from `DataSource`, the result may describe a different session.

`flags()` does not need its own `@Transactional` because it is called from public methods where the proxy has already created the transaction. `updateDespiteHint()` and `updateThenFail()` are deliberately placed in the query service to illustrate **a design flaw to avoid**, not a recommendation for applications to regularly write inside read-only methods.

### 8.8. `src/main/java/example/readonly/ReadOnlyHintApplication.java`

```java
package example.readonly;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ReadOnlyHintApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReadOnlyHintApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE inventory SET quantity = 100 WHERE id = 1");
    }

    private static long quantity(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
            "SELECT quantity FROM inventory WHERE id = 1",
            Long.class
        );
        if (value == null) {
            throw new IllegalStateException("Inventory row missing");
        }
        return value;
    }

    @Bean
    ApplicationRunner demo(
            ReadOnlyService reader,
            WriteService writer,
            JdbcTemplate jdbc) {
        return args -> {
            reset(jdbc);
            System.out.println(
                "probe | " + reader.observe() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "write in readOnly | " + reader.updateDespiteHint() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            try {
                reader.updateThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("expected exception | " + ex.getMessage());
            }
            System.out.println(
                "after rollback | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "REQUIRED joined | " +
                reader.outerReadOnlyCallsRequiredWriter() +
                " | quantity=" + quantity(jdbc)
            );

            reset(jdbc);
            System.out.println(
                "standalone writer | spring=" +
                writer.incrementRequired() +
                " | quantity=" + quantity(jdbc)
            );
        };
    }
}
```

`@EnableTransactionManagement` enables Spring declarative transaction handling; a `PlatformTransactionManager` bean uses the same H2 `DataSource` that `JdbcTemplate` uses. `ApplicationRunner` is injected with **Spring bean proxies** and invokes through them, rather than doing `new ReadOnlyService(...)`.

`reset()` runs from `ApplicationRunner` **outside** the service transaction and resets quantity to 100 before each case. Because all demo methods finish before `quantity(jdbc)` is called, the printed quantity is the **post-commit/rollback state**.

### 8.9. Running the Project

On macOS/Linux, if the project has a Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you just created the files without a wrapper, you can run `gradle bootRun` with a compatible installed Gradle or generate the wrapper with Gradle. The program cannot run standalone with `javac`/`java` without Spring and H2 on the classpath.

**Lines printed by the program**, ignoring Boot/Gradle startup logs, are expected to be:

```text
probe | spring=true, jdbc=false, active=true | quantity=100
write in readOnly | spring=true, jdbc=false, active=true | quantity=110
expected exception | demonstration rollback
after rollback | quantity=100
REQUIRED joined | outer=true, inner=true | quantity=105
standalone writer | spring=false | quantity=105
```

These lines are **results inferred from the code, Spring JDBC, and documented H2 driver behavior**; they are not a claim that the project was compiled/run in this environment.

### 8.10. Interpreting Each Result

**`probe`:** Spring created a transaction with `readOnly=true`, so `TransactionSynchronizationManager` reports `spring=true` and `active=true`. However, H2 `Connection.isReadOnly()` returns `false` when the database is writable; `Connection.setReadOnly(true)` is a hint ignored by H2. No write SQL ran, so quantity remains 100.

**`write in readOnly`:** `@Transactional(readOnly=true)` still has `spring=true`. `JdbcTemplate` runs a valid `UPDATE` on writable H2 and the method returns normally; the transaction manager commits. Quantity increases from 100 to **110**. This directly illustrates that **the read-only hint is not a mandatory write-blocking mechanism**.

**`expected exception`/`after rollback`:** In another read-only transaction, `UPDATE +20` is accepted by H2, but the method throws `IllegalStateException`. Because an unchecked exception escapes through the transaction interceptor, Spring rolls back by default, so quantity returns to **100**. Read-only does not cancel rollback rules.

**`REQUIRED joined`:** `outerReadOnlyCallsRequiredWriter()` creates read-only transaction T; `WriteService.incrementRequired()` has `REQUIRED` and `readOnly=false` yet joins **the same T**. The current flag seen by the inner method remains `true`, because the transaction policy belongs to the already opened physical scope. H2 does not block the SQL, so quantity increases to **105**. This is why code should not rely on a single repository method's annotation to switch transaction mode for the entire call chain.

**`standalone writer`:** With no outer transaction, `WriteService.incrementRequired()` creates a **new read-write** transaction. The Spring context returns `false`, the update succeeds, and quantity is **105**.

### 8.11. Why Doesn't the Demo Print `Connection.isReadOnly()=true`?

An easy intuition to fall into is "Spring calls `setReadOnly(true)`, so `isReadOnly()` must return `true`". With a JDBC driver, the hint can be ignored. H2 Javadoc confirms `setReadOnly` is ignored and `isReadOnly()` returns the database-level state. This is precisely why H2 is used as an example of **the difference between intention and enforcement**.

If you replace H2 with another database, **do not copy the stdout results blindly**. The driver may reflect `isReadOnly=true`, enforce a read-only transaction, or reject writes. You must observe the specific manager, driver, and DBMS.

## 9. JUnit 5 Testing: Do Not Assert Only a Single Flag

Create `src/test/java/example/readonly/ReadOnlyHintApplicationTest.java`:

```java
package example.readonly;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class ReadOnlyHintApplicationTest {
    @Autowired ReadOnlyService reader;
    @Autowired WriteService writer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE inventory SET quantity = 100 WHERE id = 1");
    }

    private long quantity() {
        Long value = jdbc.queryForObject(
            "SELECT quantity FROM inventory WHERE id = 1",
            Long.class
        );
        if (value == null) {
            throw new IllegalStateException("Inventory row missing");
        }
        return value;
    }

    @Test
    void springReadOnlyMetadataDiffersFromH2JdbcState() {
        assertEquals(
            "spring=true, jdbc=false, active=true",
            reader.observe()
        );
        assertEquals(100L, quantity());
    }

    @Test
    void jdbcReadOnlyHintDoesNotPreventH2Write() {
        assertEquals(
            "spring=true, jdbc=false, active=true",
            reader.updateDespiteHint()
        );
        assertEquals(110L, quantity());
    }

    @Test
    void uncheckedExceptionStillRollsBackReadOnlyTransaction() {
        assertThrows(
            IllegalStateException.class,
            reader::updateThenFail
        );
        assertEquals(100L, quantity());
    }

    @Test
    void participatingRequiredMethodUsesOuterReadOnlyPolicy() {
        assertEquals(
            "outer=true, inner=true",
            reader.outerReadOnlyCallsRequiredWriter()
        );
        assertEquals(105L, quantity());
    }

    @Test
    void standaloneWriterStartsReadWriteTransaction() {
        assertFalse(writer.incrementRequired());
        assertEquals(105L, quantity());
    }
}
```

Run:

```bash
./gradlew test
```

**Test design explanation:**

- The test class is not annotated with `@Transactional` because a transaction opened by the test framework could cause the service to **join the test transaction instead of starting a new one**, invalidating the read-only/commit checks.
- `@BeforeEach` resets quantity so cases are independent. `@SpringBootTest` may run `ApplicationRunner` during context startup; resetting before each test ensures the fixture remains accurate.
- Assertions check the **Spring flag**, **JDBC status**, and **post-transaction-boundary data**. Simply doing `assertTrue(isCurrentTransactionReadOnly())` is not enough to claim the DB forbids writes.
- If switching DB/driver, expected tests must be adjusted to the contract actually needed: on a database with enforcement, tests should assert that write operations are rejected and data is unchanged, rather than asserting H2 accepts them.
- Do not run test fixtures sharing one H2 schema concurrently on multiple threads without data isolation, because this test's `@BeforeEach` could affect another test.

## 10. `readOnly` Is Not a Security Policy

Suppose the goal is **an analytics application that must never modify production data**. Configuring only:

```java
@Transactional(readOnly = true)
public List<ReportRow> analyze() {
    // ...
}
```

is **insufficient** to protect data, because an SQL statement from code, a native query, migration, stored procedure, or another endpoint could pass through a connection/transaction where writes are not prohibited.

Measures at the **right layer**:

- **Database privileges:** grant the application user only the necessary read permissions, revoking `INSERT`, `UPDATE`, `DELETE`, DDL, and other dangerous privileges per the DBMS.
- **Dedicated read-only endpoint / replica:** connections actually go to a database with a read-only policy when architecture permits.
- **DB-level read-only transactions:** use the DBMS's SQL/session mechanism and test that statements are rejected.
- **Application architecture:** separate query services and command services, avoiding mixing write operations into read code.
- **Observability and tests:** monitor actual SQL, and test to verify the DB rejects writes using the deployed user/connection.

`@Transactional(readOnly=true)` still has value: it communicates intent to the infrastructure, enables optimizations on supported stacks, and serves as design documentation. However, it **must not be used as the sole security barrier**.

### Read Replicas and Routing

Some applications have an `AbstractRoutingDataSource` based on `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` to choose a read datasource. **This is an additional configuration built by the application/team**, not default `@Transactional` behavior.

You must carefully check **when the JDBC connection is acquired**: if the connection is obtained before the read-only flag is set, or if routing uses an unsuitable connection cache/proxy, routing may not behave as expected. `LazyConnectionDataSourceProxy` and sound routing design can help in some architectures, but must be tested with real connections.

Reading a replica also has **replication lag**, so a query right after a write might not yet see the new data. `readOnly=true` does not solve replica consistency.

## 11. `readOnly` Is Not `timeout`, Even Though Both Are in Transaction Configuration

Both are attributes on `@Transactional`:

```java
@Transactional(readOnly = true, timeout = 5)
public Report readReport() {
    // ...
}
```

Different meanings:

| Attribute | Purpose | Does It Block `UPDATE` by Default? |
| --- | --- | --- |
| `readOnly=true` | Describes a transaction expected to be read-only, which may be optimized/enforced by the appropriate layer | Not universally |
| `timeout=5` | Requests a transaction time limit, depending on manager/driver/statement | No |
| `isolation=...` | Requests an isolation level for a new transaction | No |
| `rollbackFor=...` | Rollback rule when an exception passes through the interceptor | No |

`timeout` is not a guarantee that every SQL statement is cut off after exactly 5 seconds in every DB. Spring can coordinate the transaction timeout with JDBC statements via `JdbcTemplate`, but query cancellation and timely rollback depend on the driver/DBMS/manager.

On the other hand, when `timeout` or `readOnly` is declared on a method that **only joins an existing physical transaction** with `REQUIRED`, do not infer that they create an independent timeout/mode for the inner segment. Place important policies at the **boundary that owns the transaction**.

## 12. JPA/Hibernate: Read-Only Optimizations Do Not Mean Database Enforcement

Compare the two paths:

```text
Spring JDBC:
@Transactional(readOnly=true)
  -> DataSourceTransactionManager
  -> Connection.setReadOnly(true) hint
  -> JDBC SQL/driver/DBMS
```

```text
Spring Data JPA / Hibernate:
@Transactional(readOnly=true)
  -> JpaTransactionManager / JPA dialect
  -> Hibernate Session / flush mode / persistence context optimizations
  -> JDBC connection / database
```

Details to understand:

1. **Hibernate flush mode:** with a read-only transaction, Spring Data JPA may set flush mode `MANUAL` so Hibernate does not need to flush/dirty-check like a normal write transaction. This is an optimization, not a permission check.
2. **Managed entities:** changing a Java object inside the persistence context will not necessarily be synchronized to the DB the same way as in a read-write transaction. However, there is no basis to claim "all `save`, `flush`, and native DML calls are always blocked" from the flag alone.
3. **Spring Data JPA method configuration:** read queries can be marked read-only; depending on method/annotation, update queries use `@Modifying` and an explicit read-write transaction. A service-level transaction can override or wrap repository calls.
4. **JPA provider behavior:** `readOnly` information may not have the same meaning across Hibernate, EclipseLink, or other providers.
5. **Database-level enforcement:** if the technical requirement is for the DB to reject DML, configure appropriate transactions or DB accounts rather than relying solely on the ORM skipping flush.

With an application containing both Hibernate and direct JDBC access, a read-only transaction might limit ORM flushing while a native `JdbcTemplate.update(...)` still goes down to the DB. That is why **end-to-end tests on the real stack** are necessary.

## 13. Measuring Read-Only at the Right Boundary

### Spring Transaction Metadata

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

These two variables describe the **Spring thread-bound transaction context** in the imperative model. They are not a check that SQL has been write-blocked by the DB. The same method with `readOnly=true` called via self-invocation or outside a Spring bean may lack transaction advice, leading to unexpected results.

### JDBC Driver Status

```java
Boolean driverReadOnly = jdbcTemplate.execute(
    (ConnectionCallback<Boolean>) Connection::isReadOnly
);
```

You should only inspect the connection coordinated by the transaction manager. `JdbcTemplate` inside a Spring JDBC transaction obtains the connection participating in that transaction. Manually borrowing a new connection from the pool may only measure a different session.

### DBMS Transaction State

On some DBMSs you can query the session/transaction setting with engine-specific SQL:

```sql
-- PostgreSQL: check read-only transaction state of the current connection
SHOW transaction_read_only;
```

The statement above **is for PostgreSQL**, and does not run on H2. Other DBMSs use different syntax/metadata. It must be executed inside the exact physical transaction/connection under investigation; running another SQL client does not prove the application's transaction state.

### Safe Write Testing

In a database-specific integration test:

1. Start a `readOnly=true` transaction through the Spring proxy.
2. Attempt an `UPDATE` on a test table containing no real data.
3. Observe whether the database succeeds or errors.
4. End the transaction according to the test's purpose.
5. Re-read the data after the boundary, from an independent connection when appropriate.
6. Verify the transaction manager, driver version, DB role, and SQL read-only configuration.

If the test requires that **writes must be rejected**, a default H2 run will **not satisfy the requirement**, because H2 does not enforce based on the `setReadOnly(true)` hint.

## 14. Situations That Easily Produce Surprising Results

### 14.1. Self-Invocation Prevents `readOnly` From Taking Effect on the Expected Method

```java
@Service
public class ReportService {
    public void outer() {
        inner();
    }

    @Transactional(readOnly = true)
    public void inner() {
        // ...
    }
}
```

In normal Spring AOP **proxy mode**, `outer()` calls `inner()` via `this`, without going back through the transaction proxy. Therefore `@Transactional(readOnly=true)` on `inner()` **does not automatically activate a new transaction/read-only hint**. Move the boundary to the method called externally through the proxy, or extract `inner` into another bean.

### 14.2. An Inner `REQUIRES_NEW` Reading Inside a Writing Outer

With `REQUIRES_NEW`, Spring opens a separate physical transaction for the inner method; it can receive a read-only hint independently of the outer. However, this transaction typically needs a **different connection** and may read data **excluding the outer's uncommitted changes**, depending on isolation and the DB. Do not pick `REQUIRES_NEW(readOnly=true)` just hoping for faster queries without evaluating consistency and pool capacity.

### 14.3. Connection Pool and Reused State

The JDBC transaction manager typically tries to restore `Connection.setReadOnly(false)` after finishing a hinted read-only transaction. Pools also have mechanisms to manage connection state. However, manual `SET SESSION...` SQL or database session-specific flags may require special handling; do not blindly trust the pool to recognize every change made outside the JDBC API.

Therefore, do not change read-only state with arbitrary session SQL commands inside services without understanding the reset policy. Connection state leakage between requests can cause hard-to-reproduce write errors.

### 14.4. DDL, Stored Procedures, and Operations Outside the DB

Even when a read-only database transaction blocks most DML, statement types, DDL, temporary tables, functions, and side effects can have DBMS-specific rules. Outside the DB, sending HTTP requests, message broker messages, emails, or writing files **is not prevented by the JDBC read-only flag**. A query method with out-of-database side effects must still be designed carefully.

### 14.5. Reading Data Does Not Mean a Transaction Is Cheap or Lock-Free

A long read-only transaction can still hold a connection, snapshot, MVCC retention, and certain resources/locks depending on the DBMS. Enabling read-only does not automatically solve long-running transactions, connection pool starvation, or unindexed queries. Effectiveness depends on ORM optimizations, driver, and database.

## 15. When Should You Use `@Transactional(readOnly=true)`?

### Recommended When

- Public service methods performing a clearly bounded unit of data reading.
- Spring Data JPA repositories/services using Hibernate, where read-only can help reduce dirty checking and flushing.
- Applications with proper transaction routing and clear read-pool/replica policies.
- You need to express read-only intent consistently and test that the service does not unexpectedly modify data.
- DB-level enforcement/permissions exist if the requirement is truly **no writes allowed**.

### Do Not Rely Solely on This Flag When

- You want a security barrier against DB write operations.
- There are direct SQL writes, native queries, stored procedures, or out-of-DB side effects.
- You expect a small readOnly method inside a read-write outer to automatically switch the physical transaction mode.
- You test with H2 and extrapolate production PostgreSQL/MySQL enforcement results.
- You need time limits/lock prevention/serializability — those require other configurations and tools.
- You want to automatically route datasources to a read replica without routing infrastructure.

## 16. Common Pitfalls and Solutions Table

| Symptom / Conclusion | Common Cause | How to Handle |
| --- | --- | --- |
| `@Transactional(readOnly=true)` is present yet `UPDATE` still commits | Driver/DBMS treats `setReadOnly` as a hint; H2 ignores it | Do not use the flag as a write barrier; use DB policies/permissions |
| Spring flag is true, `Connection.isReadOnly()` is false | JDBC driver reports state differently from Spring metadata | Check driver docs and actual SQL behavior |
| `@Transactional(readOnly=true)` used and Hibernate does not save modified entities | Flush mode/dirty-check optimization | Move write logic to a read-write transaction with a clear service boundary |
| `Connection.isReadOnly()` is true yet SQL behavior is still suspect | JDBC mode and DBMS semantics differ | Test safe DML on the target DB and inspect SQL errors |
| Inner method declares read-write yet runs inside read-only outer | Inner `REQUIRED` joins physical T | Set proper boundaries; check propagation/validation |
| `REQUIRES_NEW(readOnly=false)` fixes the error yet outer rolls back | Inner commits independently | Re-evaluate atomicity before changing propagation |
| SQL `SET TRANSACTION READ ONLY` fails on H2/unfamiliar DB | Enforcement enabled with unsupported SQL | Do not enable blindly; test the specific DBMS |
| Repository `save` in a read-only service gives inconsistent results | ORM flush/dirty-check and manager/driver differences | Do not mix read/write inside a read-only boundary |
| Annotation has no effect | Self-invocation, bean created with `new`, method not advised | Call through Spring proxy and test properly |
| Query method uses readOnly yet still consumes heavy resources | Unoptimized query, long transaction, index/lock | Optimize SQL and keep transactions short |
| DB replica returns stale data | Replication lag, routing timing | Establish a consistency policy |
| JPA readOnly flag behaves differently from JDBC | Different manager/provider translation | Test on the actual stack |
| Tests only assert Spring metadata | Metadata does not prove DB behavior | Check DML outcomes and post-transaction state |
| App assumes readOnly equals timeout | Two independent attributes | Configure timeouts and query timeouts separately |
| DB account has full write privileges | `readOnly=true` does not grant/revoke permissions | Use least-privilege DB credentials |

## 17. Self-Check Questions

1. Does `@Transactional(readOnly=true)` **always** cause the database to reject `UPDATE`? **No**. The manager/driver/DBMS determines the level of enforcement.
2. What does H2 `JdbcConnection.setReadOnly(true)` typically do on a writable database? **Ignores the hint**, without turning the database read-only.
3. What does `TransactionSynchronizationManager.isCurrentTransactionReadOnly()==true` prove? **The Spring transaction context is publishing readOnly=true**, not that the DB prohibits DML.
4. Is `Connection.isReadOnly()==false` in H2 under Spring `readOnly=true` an annotation bug? **No**, because the two APIs have different roles and H2 only reports database-level read-only.
5. If an `UPDATE` succeeds in a read-only transaction and the method returns normally, can it commit? **Yes**, when the DB/driver allows it and the transaction is not rollback-only.
6. What if that method throws an unchecked exception through the interceptor? **Spring rolls back by default**, even though readOnly is true.
7. What can `DataSourceTransactionManager#setEnforceReadOnly(true)` be used for? **Stronger enforcement via an SQL read-only transaction** on compatible DBMSs, which must be tested separately.
8. How can Hibernate use this flag? **Adjusting flush mode/dirty checking or the Session**, which is an optimization rather than a universal DML prohibition.
9. Does a `REQUIRED(readOnly=false)` method joining a `readOnly=true` outer automatically open a new read-write transaction? **No**. It joins the outer T, unless propagation/manager dictates otherwise.
10. If an application only needs to read and must strictly never write to the DB, what should you rely on? **Minimal database privileges and/or genuine read-only database/transaction enforcement**.
11. Is `readOnly` the same as `timeout` or `isolation`? **No**, they are different dimensions of transaction metadata.
12. Why are H2 results insufficient to guarantee production PostgreSQL behavior? **JDBC drivers, SQL enforcement, permissions, and DB semantics differ**.

## 18. Production Design and Testing Checklist

1. Ensure the transaction boundary sits at a **public Spring service method called through a proxy**.
2. Choose `readOnly=true` for genuine read operations; do not attempt to write data and rely on the hint for error control.
3. Verify how the actual `PlatformTransactionManager`/JPA provider handles readOnly.
4. Check connections supplied by the datasource/pool, JDBC driver, and DBMS, especially read-only session state.
5. With JDBC, distinguish the **Spring thread flag** from `Connection.isReadOnly()` and true SQL read-only policies.
6. With Hibernate, inspect flush mode, dirty checking, and native/modifying queries inside read-only transactions.
7. If the DB must reject writes, deploy DB privileges or supported read-only transaction enforcement and test on the target DBMS.
8. Evaluate `REQUIRED` joining and outer transactions before relying on an inner method's flag.
9. Do not substitute `REQUIRES_NEW` merely to bypass a read-only flag when business logic requires shared atomicity.
10. Write integration tests observing DB values **after** transaction commit/rollback; do not check only annotations.
11. Do not infer automatic replica routing from `readOnly=true`; verify routing timing and replica consistency.
12. Evaluate query timeouts, DB locks, MVCC retention, and connection pooling separately from read-only optimization.
13. When changing DB/driver/Hibernate/Spring, re-run readOnly/DB-level enforcement tests; this is an environment-dependent property.
14. Maintain the **least privilege** principle for database users, because a transaction hint is not a security boundary.

## Official References

- Spring Framework — `@Transactional` settings (`readOnly`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `DataSourceTransactionManager` Javadoc, `setEnforceReadOnly`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `DataSourceUtils` Javadoc, prepare/reset connection: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `TransactionDefinition` (`isReadOnly`) Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Data JPA — Transactionality, readOnly and Hibernate flush optimization: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- H2 Database — `JdbcConnection` Javadoc, `setReadOnly` ignored: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html
- JDBC — Java SE `Connection.setReadOnly`, hint and invocation timing: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- PostgreSQL — Transaction Characteristics, `READ ONLY`/`READ WRITE`: https://www.postgresql.org/docs/current/sql-set-transaction.html