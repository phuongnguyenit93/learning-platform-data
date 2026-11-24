# `setEnforceReadOnly` in Spring Framework's `DataSourceTransactionManager`

## 1. The Problem: Does `readOnly=true` Actually Prohibit Writes?

When seeing `@Transactional(readOnly = true)`, many assume Spring will block all `INSERT`, `UPDATE`, or `DELETE` statements inside the method. That inference is not true for every JDBC driver and database.

In Spring JDBC there are two levels of handling to distinguish:

1. **JDBC hint**: When starting a new transaction declared as read-only, Spring prepares the connection by calling `Connection.setReadOnly(true)` when appropriate. Per the JDBC contract, this is a hint for the driver/database to optimize or apply read-only mode; a driver may support or ignore it, so you must not claim it always forbids writes.
2. **Enforced database transaction mode**: When `DataSourceTransactionManager.setEnforceReadOnly(true)` is configured, Spring executes `SET TRANSACTION READ ONLY` on the connection **when starting a new physical transaction defined with `readOnly=true`**. Databases that support this command will enforce read-only transaction rules at the SQL level.

The `enforceReadOnly` flag of `DataSourceTransactionManager` **defaults to false**. That does not mean every driver is guaranteed to allow UPDATE: some JDBC drivers proactively turn `Connection.setReadOnly(true)` into SQL read-only mode. For example, pgJDBC with default `readOnlyMode=transaction` can open `BEGIN READ ONLY`. Therefore, you should inspect the actual database state rather than looking at a single flag.

This lesson focuses on the `setEnforceReadOnly` API itself, when it takes effect, what it does not guarantee, the difference between a new transaction and a joined transaction, along with a Java 17+ example running against PostgreSQL to observe SQL read-only mode.

## 2. The API Belongs to the Manager, Not the Annotation

The setter lives on the class:

~~~java
org.springframework.jdbc.datasource.DataSourceTransactionManager
~~~

`JdbcTransactionManager` is a subclass of `DataSourceTransactionManager`, so it also has this API. Configuring a simple manager:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
class TxConfiguration {
    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        DataSourceTransactionManager tx = new DataSourceTransactionManager(ds);
        tx.setEnforceReadOnly(true);
        return tx;
    }
}
~~~

The example is only a configuration class; the full application needs a `DataSource` and infrastructure managing `@Transactional`. Enable the flag **once at startup**, and do not toggle it while production requests are running. With multiple transaction managers, ensure the service uses the **exact manager bean** that has the flag enabled. Creating a new `DataSourceTransactionManager` outside the Spring context or enabling the flag on a manager that does not manage the DAO's JDBC connection will not have the intended effect.

`@Transactional(readOnly=true)` is the **transaction definition** supplied by the transaction advice; `setEnforceReadOnly(true)` is **how the transaction manager translates that definition into a database operation**. Both configurations must be present at the right boundary to take effect.

### An Equivalent Option When Using `JdbcTransactionManager`

~~~java
@Bean
org.springframework.jdbc.support.JdbcTransactionManager transactionManager(
        DataSource ds) {
    var manager = new org.springframework.jdbc.support.JdbcTransactionManager(ds);
    manager.setEnforceReadOnly(true);
    return manager;
}
~~~

This is an **alternative option** to the `DataSourceTransactionManager` bean above; **do not declare both simultaneously** under the same bean name. `JdbcTransactionManager` provides better JDBC error translation during commit/rollback in corresponding cases, while the `setEnforceReadOnly` mechanism is inherited.

## 3. Exactly When Does Spring Issue `SET TRANSACTION READ ONLY`?

`DataSourceTransactionManager` has a protected hook `prepareTransactionalConnection(Connection, TransactionDefinition)`. In the default implementation, the hook executes:

~~~sql
SET TRANSACTION READ ONLY;
~~~

when **both conditions** are true:

- The manager has `enforceReadOnly=true`.
- `TransactionDefinition.isReadOnly()` of the **newly started** transaction is true.

Typical JDBC flow:

1. The caller invokes the transactional method **through the Spring AOP proxy**.
2. `TransactionInterceptor` decides whether to open a new transaction or join an existing one.
3. If opening a new transaction, `DataSourceTransactionManager` obtains a JDBC connection from the `DataSource`, prepares the read-only hint and isolation if needed, and handles auto-commit.
4. The manager calls `prepareTransactionalConnection`; if the conditions are met, the `SET TRANSACTION READ ONLY` statement is issued **before the method's business SQL**.
5. `JdbcTemplate` uses the transaction-bound connection to run SELECT/UPDATE.
6. The manager commits/rolls back, cleans up the transaction context, restores necessary connection state, and returns the connection to the pool.

Along this path, the transaction manager **does not issue a SET command for each SELECT** and does not create a new transaction for every method merely because the method has the annotation.

~~~mermaid
flowchart TD
    A["Caller invokes bean via Spring proxy"] --> B["TransactionInterceptor reads @Transactional"]
    B --> C{"Existing physical transaction?"}
    C -->|"No; REQUIRED or REQUIRES_NEW creates new"| D["DataSourceTransactionManager starts new T"]
    C -->|"Yes; REQUIRED joins"| J["Reuse current physical transaction"]
    D --> E["Connection.setReadOnly(true) if readOnly"]
    E --> F{"Both enforceReadOnly and definition.readOnly true?"}
    F -->|"Yes"| G["SET TRANSACTION READ ONLY"]
    F -->|"No"| H["No explicit SQL SET from hook"]
    G --> I["Execute method over T's JDBC connection"]
    H --> I
    J --> K["No new T started; does not automatically SET read-only"]
    K --> I
~~~

### Placing SET in the Right Transaction

`SET TRANSACTION READ ONLY` is a property of the **physical transaction**, not the entire application. In PostgreSQL, transaction characteristics must be set before query/DML statements advance the transaction. The Spring manager handles this at the **begin hook** to satisfy that requirement. Do not arbitrarily issue the command in the middle of a service method that has already executed SQL and expect the DB to allow changing the access mode.

## 4. Comparing the JDBC Read-Only Hint and Database-Enforced Read-Only

| Question | `Connection.setReadOnly(true)` | `SET TRANSACTION READ ONLY` |
| --- | --- | --- |
| Who receives the request? | JDBC driver, which may pass it to the DB | Database SQL engine |
| Can it be just a hint? | Yes | If the statement is supported by the DB and succeeds, the access mode is applied |
| Does it prohibit writing to regular tables? | Not guaranteed across all drivers | PostgreSQL and compatible DBs block many disallowed DML/DDL statements |
| Does it affect the entire connection pool? | No; only the associated connection/transaction | No; only the physical transaction on which SET is executed |
| Is it security authorization? | No | No, roles/privileges are still required |
| Does it change transaction isolation? | Not by default | Not by default: READ ONLY is different from SERIALIZABLE |
| Does it apply to an inner REQUIRED join? | Does not start a new connection for inner | Does not run a new begin hook |

On PostgreSQL, a read-only transaction prohibits `INSERT`, `UPDATE`, `DELETE`, and `MERGE` on non-temporary tables as well as many DDL commands. PostgreSQL has certain exceptions for temporary tables; read-only mode **does not guarantee zero bytes are written to disk**, nor does it prevent HTTP, Kafka, or file side effects invoked by Java. Therefore, read-only is a **database transaction access mode**, not a general-purpose security system.

According to Spring Javadoc, DBs such as Oracle, MySQL, and PostgreSQL understand the `SET TRANSACTION READ ONLY` concept; exact semantics, versions, dialects, drivers, and snapshot characteristics vary. For example, Oracle has distinct read consistency for read-only transactions. Do not assume this statement works identically on every engine.

## 5. Watch Out for pgJDBC: Flag False Yet the Database Can Still Be Read-Only

The PostgreSQL JDBC driver has a `readOnlyMode` property:

| pgJDBC `readOnlyMode` | Main Behavior |
| --- | --- |
| `ignore` | `Connection.setReadOnly(true)` does not automatically change server-side transaction access mode |
| `transaction` (common default) | When the connection is read-only and auto-commit is false, the driver can start `BEGIN READ ONLY` |
| `always` | In addition to transaction behavior, may set the session read-only when auto-commit is true per driver semantics |

Consequently, on PostgreSQL with `readOnlyMode=transaction`, you may observe a read-only DB **even when `DataSourceTransactionManager.setEnforceReadOnly(false)`**. That is not necessarily a Spring bug or a sign the flag is broken: the driver already translated the JDBC hint into SQL at another layer.

The hands-on example in this lesson **intentionally** uses the URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:55432/readonly_demo?readOnlyMode=ignore
~~~

Solely to separate the difference between **a hint not enforced by the driver** and **explicit SQL SET issued by the manager**. `readOnlyMode=ignore` is **not** a recommended production setting; using it can reduce existing protection if the manager does not enable enforcement and a read-only method accidentally writes data.

Read all three signals correctly:

- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`: Does the Spring context declare read-only?
- `Connection.isReadOnly()`: What does the JDBC driver report for the hint flag?
- `SHOW transaction_read_only` on PostgreSQL: What transaction access mode does the **server** currently have?

Only one of the three signals, especially the Spring flag, is **not enough** to claim the database definitely blocks UPDATEs.

## 6. Propagation: A New Transaction Differs from an Inner Join

Even when the manager has `setEnforceReadOnly(true)`, effectiveness depends on propagation:

| Scope | Physical Transaction | Issue SQL SET for This Scope? |
| --- | --- | --- |
| `@Transactional(readOnly=true)`, no outer transaction | Creates new | Yes, if using the right manager/DB |
| `@Transactional(readOnly=false)`, no outer transaction | Creates new | No |
| `@Transactional` without readOnly | Creates new, default readOnly=false | No |
| `REQUIRES_NEW, readOnly=true` inside read-write outer | Suspends outer, creates independent inner | Yes for inner |
| `REQUIRED, readOnly=true` joining read-write outer | Reuses outer transaction | Does not issue a new SQL SET from inner annotation |
| `REQUIRED, readOnly=false` joining read-only outer | Reuses outer transaction | Inner does not automatically turn off outer's read-only mode |
| `NESTED` via savepoint when supported | No independent physical transaction | Does not use the hook like opening a new transaction |
| `SUPPORTS` without a physical transaction | Opens no physical transaction | No |
| Self-invocation `this.inner()` in proxy mode | Bypasses inner's transaction advice | Inner annotation does not automatically issue SET |

### Example of `REQUIRED` Joining

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(readOnly = false)
    public void outer() {
        inner.readSomething();
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = true
    )
    public void readSomething() {
        // Outer's transaction remains read-write by default.
    }
}
~~~

This is an illustrative structural snippet; imports and database beans must be added if run standalone. The call must go **through the `InnerService` bean proxy** for the manager to process the inner metadata. Even so, `REQUIRED` joins the same transaction already opened by outer, so `setEnforceReadOnly(true)` **does not elevate** outer from read-write to read-only.

### `validateExistingTransaction` Differs from `enforceReadOnly`

`setValidateExistingTransaction(true)` is a **different** setting on transaction managers based on `AbstractPlatformTransactionManager`. It requests compatibility checks on the transaction definition when **joining an existing transaction**. It does not turn `REQUIRED` into a new transaction and does not replace the `SET TRANSACTION READ ONLY` hook.

For example, when an inner **read-write** joins an outer **read-only**, strict validation can reject it because the inner's definition is incompatible with the outer transaction. However, you must not claim the validator checks **symmetrically** in every case: Spring's logic checks in specific directions; an inner read-only joining an outer read-write normally still joins without being forced into read-only. To make the inner independent, use `REQUIRES_NEW` and accept the commit/rollback semantic changes.

## 7. `@Transactional` Configuration at Class/Method Level and Choosing the Right Manager

If a class has `@Transactional(readOnly=true)` yet a method specifies `@Transactional`, the method annotation typically takes precedence. A bare annotation has `readOnly=false` by default, so it is not enforced just because the class set `readOnly=true`.

~~~java
@Transactional(readOnly = true)
class SearchService {
    public void list() {
        // No method-level annotation: takes the class policy.
    }

    @Transactional
    public void refreshCacheTable() {
        // Method annotation wins, readOnly defaults to false.
    }
}
~~~

This is illustrative code. **Spring does not merge missing individual attributes** between the method annotation and the class annotation. A method failing to have UPDATE blocked by the DB may happen because the class policy was overridden, the transaction bypassed the proxy, or the wrong manager/datasource was used — not solely because of the enforce flag.

In a multi-datasource application, specify the manager name explicitly when needed, such as `@Transactional(transactionManager="reportingTx", readOnly=true)`. Configuring `setEnforceReadOnly(true)` on `reportingTx` does not automatically affect `ordersTx`. Ensure `JdbcTemplate` also uses the exact source managed by the manager; if connections are obtained directly from another datasource, SQL may execute outside the enforced transaction.

## 8. Practical Java 17+ Demo with Spring Boot, PostgreSQL, and Docker Compose

This demo verifies the manager's behavior directly on PostgreSQL, **without using H2 to assume dialect compatibility**. Tooling: Java 17+, Maven, Docker Compose, Spring Boot **3.3.5** (Spring Framework 6.1.x), pgJDBC, PostgreSQL **16**.

Scenarios:

1. JDBC hint with `enforceReadOnly=false` and driver `readOnlyMode=ignore`: Spring sees `readOnly=true`, the server still reports `off`, UPDATE +1 succeeds.
2. Enable `enforceReadOnly=true` outside any transaction: the server reports `on`, UPDATE on a regular table is rejected and rolled back; data is unchanged.
3. SELECT inside a read-only transaction still succeeds, while a read-write method is allowed to UPDATE.
4. Inner `REQUIRED, readOnly=true` joins outer read-write; server remains `off`.
5. Inner `REQUIRES_NEW, readOnly=true` opens an independent transaction: server is `on` inside, then returns to `off` in outer.

**In production, do not mutate flags on the manager while concurrent requests are running.** Here, the CLI program runs sequentially and only flips the flag between calls to make the effect easy to see.

### 8.1. Project Structure

~~~text
enforce-readonly-demo/
├── compose.yaml
├── pom.xml
└── src/main/
    ├── resources/application.properties
    └── java/example/readonly/
        ├── ReadOnlyDemoApplication.java
        ├── ReadOnlyService.java
        └── OuterService.java
~~~

The `demo` passwords and localhost port are for a local sandbox only.

### 8.2. `compose.yaml`

~~~yaml
services:
  pg:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: readonly_demo
      POSTGRES_USER: demo
      POSTGRES_PASSWORD: demo
    ports:
      - "127.0.0.1:55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U demo -d readonly_demo"]
      interval: 2s
      timeout: 3s
      retries: 30
~~~

### 8.3. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>enforce-readonly-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.4. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:postgresql://localhost:55432/readonly_demo?readOnlyMode=ignore
spring.datasource.username=demo
spring.datasource.password=demo
spring.datasource.hikari.maximum-pool-size=5
~~~

`readOnlyMode=ignore` is only intended to isolate the effect of Spring's SQL hook; with default pgJDBC, the JDBC hint alone can create a server read-only transaction.

### 8.5. `src/main/java/example/readonly/ReadOnlyDemoApplication.java`

~~~java
package example.readonly;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ReadOnlyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadOnlyDemoApplication.class, args);
    }

    @Bean
    DataSourceTransactionManager transactionManager(DataSource ds) {
        var manager = new DataSourceTransactionManager(ds);
        manager.setEnforceReadOnly(false);
        return manager;
    }

    @Bean
    CommandLineRunner run(
            JdbcTemplate jdbc,
            DataSourceTransactionManager manager,
            ReadOnlyService service,
            OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS public.tx_counter "
                + "(id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update("DELETE FROM public.tx_counter");
            jdbc.update(
                "INSERT INTO public.tx_counter (id, amount) VALUES (?, ?)",
                1, 100
            );
            System.out.println("START=" + amount(jdbc));

            manager.setEnforceReadOnly(false);
            service.attemptWrite("HINT");
            System.out.println("AFTER_HINT=" + amount(jdbc));

            manager.setEnforceReadOnly(true);
            try {
                service.attemptWrite("ENFORCED");
            } catch (DataAccessException ex) {
                System.out.println("ENFORCED_UPDATE_REJECTED=true");
            }
            System.out.println("AFTER_ENFORCED=" + amount(jdbc));

            service.queryReadOnly();
            service.writeNormally();
            System.out.println("AFTER_WRITE=" + amount(jdbc));

            outer.joinReadOnly();
            outer.newReadOnly();
            System.out.println("END=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM public.tx_counter WHERE id = ?",
            Integer.class, 1
        );
    }
}
~~~

### 8.6. `src/main/java/example/readonly/ReadOnlyService.java`

~~~java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReadOnlyService {
    private final JdbcTemplate jdbc;

    public ReadOnlyService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public void attemptWrite(String label) {
        System.out.println(
            label + "_SPRING_READ_ONLY="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
        System.out.println(label + "_DB_READ_ONLY=" + mode());
        jdbc.update(
            "UPDATE public.tx_counter SET amount = amount + 1 WHERE id = 1"
        );
    }

    @Transactional(readOnly = true)
    public void queryReadOnly() {
        System.out.println("READ_ONLY_DB=" + mode());
        Integer amount = jdbc.queryForObject(
            "SELECT amount FROM public.tx_counter WHERE id = 1",
            Integer.class
        );
        System.out.println("READ_ONLY_SELECT=" + amount);
    }

    @Transactional(readOnly = false)
    public void writeNormally() {
        System.out.println("WRITE_DB=" + mode());
        jdbc.update(
            "UPDATE public.tx_counter SET amount = amount + 10 WHERE id = 1"
        );
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRED
    )
    public void reportJoined() {
        System.out.println("JOIN_DB=" + mode());
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRES_NEW
    )
    public void reportNew() {
        System.out.println("NEW_DB=" + mode());
    }

    private String mode() {
        return jdbc.queryForObject(
            "SHOW transaction_read_only", String.class
        );
    }
}
~~~

### 8.7. `src/main/java/example/readonly/OuterService.java`

~~~java
package example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final ReadOnlyService inner;

    public OuterService(JdbcTemplate jdbc, ReadOnlyService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(readOnly = false)
    public void joinReadOnly() {
        System.out.println("OUTER_JOIN_BEFORE=" + mode());
        inner.reportJoined();
        System.out.println("OUTER_JOIN_AFTER=" + mode());
    }

    @Transactional(readOnly = false)
    public void newReadOnly() {
        System.out.println("OUTER_NEW_BEFORE=" + mode());
        inner.reportNew();
        System.out.println("OUTER_NEW_AFTER=" + mode());
    }

    private String mode() {
        return jdbc.queryForObject(
            "SHOW transaction_read_only", String.class
        );
    }
}
~~~

### 8.8. Running and Checking Results

From the directory containing `pom.xml`:

~~~bash
docker compose up -d
docker compose exec -T pg pg_isready -U demo -d readonly_demo
mvn -q spring-boot:run
~~~

If `pg_isready` has not yet reported server ready, only run Maven after PostgreSQL is ready. Output **counting only the lines printed by the application itself** (excluding Spring Boot/HikariCP logs):

~~~text
START=100
HINT_SPRING_READ_ONLY=true
HINT_DB_READ_ONLY=off
AFTER_HINT=101
ENFORCED_SPRING_READ_ONLY=true
ENFORCED_DB_READ_ONLY=on
ENFORCED_UPDATE_REJECTED=true
AFTER_ENFORCED=101
READ_ONLY_DB=on
READ_ONLY_SELECT=101
WRITE_DB=off
AFTER_WRITE=111
OUTER_JOIN_BEFORE=off
JOIN_DB=off
OUTER_JOIN_AFTER=off
OUTER_NEW_BEFORE=off
NEW_DB=on
OUTER_NEW_AFTER=off
END=111
~~~

**Explanation of the key milestones:**

- `HINT_SPRING_READ_ONLY=true`: Spring context receives the read-only definition.
- `HINT_DB_READ_ONLY=off`: driver `readOnlyMode=ignore` does not enforce the hint, manager flag false does not send SET, so the server transaction is read-write.
- `AFTER_HINT=101`: update +1 succeeds, illustrating that the read-only annotation alone **is not** a guarantee that SQL is rejected when the driver ignores the hint.
- `ENFORCED_DB_READ_ONLY=on`: flag true causes the Spring manager to issue SET before business SQL.
- `ENFORCED_UPDATE_REJECTED=true`: PostgreSQL rejects the UPDATE on the regular table, `JdbcTemplate` translates `SQLException` into `DataAccessException`; the exception passes through the service proxy, the transaction rolls back, and the caller catches it outside the boundary.
- `AFTER_ENFORCED=101`: data is unchanged after the error.
- `READ_ONLY_SELECT=101`: a read-only transaction can still read.
- `WRITE_DB=off`, `AFTER_WRITE=111`: manager flag true does not prohibit transactions declared read-write.
- `JOIN_DB=off`: inner `REQUIRED` joins outer read-write; there is no new physical transaction to run SET.
- `NEW_DB=on`: inner `REQUIRES_NEW` creates its own read-only transaction while outer is temporarily suspended; afterward `OUTER_NEW_AFTER` returns to `off`.
- `END=111`: the join/new check steps do not modify data.

The example is based on PostgreSQL 16, pgJDBC `readOnlyMode=ignore`, a single manager, and Spring-injected beans. If you change the DB, driver property, propagation, or other config, **do not assume stdout remains the same**. Run the demo only on a sandbox database because the runner executes `DELETE FROM public.tx_counter` to reset data.

Clean up the lab container when finished:

~~~bash
docker compose down
~~~

## 9. Why Not Use H2 to Prove SQL Enforcement of the Flag?

H2 is often useful for Spring JDBC unit/integration tests, yet H2 does not necessarily support the same `SET TRANSACTION READ ONLY` syntax and semantics as PostgreSQL. H2 documentation notes that `Connection.setReadOnly` may be only a hint; its standard SQL command catalog does not have the same `SET TRANSACTION READ ONLY` command as PostgreSQL.

If you enable `setEnforceReadOnly(true)` in the default manager and the driver/DB does not accept that statement, an error can occur **right when starting the transaction**, before the method runs. That is an **SQL dialect difference** error, not a successful "read-only UPDATE rejected". For projects using H2 for tests and PostgreSQL in production, separate them:

- Unit tests of service logic can leave explicit enforcement disabled if H2 does not support the statement.
- Integration tests verifying actual enforcement must run against real PostgreSQL (e.g., Testcontainers) or a production-like DB.
- If a DB needs a custom statement, you can customize `prepareTransactionalConnection` in a controlled way.
- Do not infer transaction manager behavior solely from H2 tests succeeding in hint mode.

## 10. Customizing `prepareTransactionalConnection` When SQL Dialects Differ

Spring allows subclassing `DataSourceTransactionManager` and overriding the hook:

~~~java
@Override
protected void prepareTransactionalConnection(
        Connection con, TransactionDefinition definition) throws SQLException {
    // Issue SQL only if definition.isReadOnly()
    // and the DB has been verified to support the corresponding syntax.
}
~~~

This is a **hook excerpt**, requiring imports `java.sql.Connection`, `java.sql.SQLException`, and `TransactionDefinition`. Not every database uses the exact `SET TRANSACTION READ ONLY` command. If overriding:

- The hook runs **when a new physical transaction begins**, not every time an inner `REQUIRED` joins.
- Use `try (Statement st = con.createStatement()) { ... }` when executing SQL.
- Do not manually call `con.commit()`, `con.rollback()`, or `con.close()` inside the hook.
- If calling `super.prepareTransactionalConnection(...)` while also issuing a custom statement, avoid issuing SQL twice or in the wrong order.
- The access mode command must be executed at the exact **moment the DB permits changing transaction characteristics**, usually before the first business SQL.
- SQL errors from the hook can cause transaction begin to fail; do not swallow errors and proceed with a read-write transaction that the caller thinks is enforced.

This is an advanced extension point. If there is no special dialect requirement, it is better to use the default implementation with a Spring-supported DB and write integration tests.

## 11. Read-Only Differs from Isolation, Timeout, and Write Privileges

A service may declare:

~~~java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    propagation = Propagation.REQUIRED
)
public void produceReport() {
    // Illustrative excerpt.
}
~~~

Each attribute serves a different purpose:

| Attribute | Role |
| --- | --- |
| `readOnly=true` | Suggests a read-only transaction; with the enforce flag, the right manager can issue SQL READ ONLY |
| `isolation=READ_COMMITTED` | Visibility rules between concurrent transactions, not read-only |
| `timeout=10` | Transaction deadline supported by the manager/platform, not a DML ban |
| `propagation=REQUIRED` | Joins an existing physical transaction or creates a new one if none exists |

`READ ONLY` is not equivalent to `SERIALIZABLE`, and `setEnforceReadOnly` does not guarantee faster SQL or automatically restrict every query. A read-only transaction can still need locks, be blocked by another transaction, or hit a timeout. Depending on the DB, certain read-only optimizations may help, but they must be measured.

**Security:** `SET TRANSACTION READ ONLY` does not replace DB roles/privileges. An application whose DB user has UPDATE privileges can use a read-write transaction in another request. If a read-only account is required, design database roles with appropriate privileges; the read-only flag is only an additional operational defense layer.

**Outside the database:** read-only does not prevent calling HTTP endpoints, emitting Kafka events, sending emails, or writing files from the same method. Out-of-transaction side effects can still happen even if the SQL transaction is rolled back.

## 12. When the Flag Is Enabled Yet UPDATE Still Succeeds: Debugging Checklist

1. **Is it the right manager?** Is the service using the `DataSourceTransactionManager` or `JdbcTransactionManager` with the flag enabled, or actually running `JpaTransactionManager`/another bean?
2. **Which annotation is in effect?** A method annotation can override the class policy; a bare `@Transactional` defaults to `readOnly=false`.
3. **Did the invocation go through a proxy?** `this.inner()` in proxy mode typically does not trigger the inner transaction interceptor.
4. **Is there a new physical transaction?** An inner `REQUIRED` joining an outer read-write does not re-run SET.
5. **Does the manager manage the right `DataSource`?** Do the DAO/`JdbcTemplate` use the same source? Are connections acquired directly outside Spring transaction awareness?
6. **Did the driver already turn the hint into SQL?** With default pgJDBC `readOnlyMode=transaction`, the server may be in read-only even when the flag is false.
7. **Does the database understand the statement?** Check logs from `prepareTransactionalConnection` and syntax/dialect errors at begin.
8. **Are you measuring the Spring flag or the DB mode?** Use `SHOW transaction_read_only` for PostgreSQL, not just `isCurrentTransactionReadOnly()`.
9. **Which table type and SQL?** PostgreSQL has exceptions for temporary tables; test UPDATE against a regular table to see the read-only restriction.
10. **Is there an outer test transaction?** `@Transactional` on a test method can create a physical transaction before the service is called, causing the service to join instead of creating a new one.
11. **Was an exception caught?** A DB error can put the transaction into an aborted/rollback-only state, so after catching do not assume you can commit.
12. **Is read-only mode being misused as a security policy?** Check DB permissions and other access paths.

You can enable controlled logging in a test environment:

~~~properties
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.core.JdbcTemplate=DEBUG
~~~

Logs help verify the proxy/manager and begin hook, but **reading the server mode is more direct evidence** of enforcement.

## 13. Common Thinking Traps

| Misconception | Reality |
| --- | --- |
| "`readOnly=true` always forbids DML" | Per JDBC, the read-only hint may not be enforced |
| "Flag false means PostgreSQL definitely allows UPDATE" | pgJDBC can automatically `BEGIN READ ONLY` |
| "Flag true applies to every manager/DB" | This is a setter on specific JDBC managers, requiring a supported dialect |
| "Inner REQUIRED readOnly=true turns outer read-write into read-only" | Joining a physical transaction does not run a new begin hook |
| "`REQUIRES_NEW` only changes read-only without changing atomicity" | The inner is an independent physical transaction |
| "`setValidateExistingTransaction(true)` also enforces SQL" | It checks compatibility when joining, rather than issuing `SET TRANSACTION READ ONLY` instead |
| "H2 running the JDBC hint means it supports PostgreSQL's SET" | The JDBC API and SQL dialect are two different layers |
| "Spring context readOnly=true proves the DB is read-only" | Spring metadata and server access mode can differ |
| "Read-only is authorization" | Database user privileges still must be designed separately |
| "No DML means no side effects" | Java can still send HTTP/messages, modify caches, or write files |
| "Enabling the flag is only a performance optimization" | It can alter behavior of accidental write flows and cause errors on unsupported DBs |
| "Raising isolation replaces the flag" | Isolation and access mode are two different properties |

## 14. Exercises with Answers

**Exercise 1.** A `@Transactional(readOnly=true)` method opens a new transaction with a manager that has `setEnforceReadOnly(true)`. The PostgreSQL DB supports SQL SET. What happens before the service SELECT?

**Answer:** The manager issues `SET TRANSACTION READ ONLY` in the begin hook for that transaction; SELECT runs under server read-only mode.

**Exercise 2.** Inner `REQUIRED` `readOnly=true` joins outer `readOnly=false`. The manager enables enforcement. Does it block UPDATE in the inner?

**Answer:** Not automatically blocked by this flag: the inner does not open a new physical transaction. If the DB/resource has another mechanism, the result must be measured separately; in the PostgreSQL model with a read-write outer, the inner's SET is not issued.

**Exercise 3.** Change the inner to `REQUIRES_NEW` `readOnly=true`, with the outer still read-write. Result?

**Answer:** The outer suspends, the inner opens a new transaction and gets SET READ ONLY if the DB supports it; when the inner finishes, the outer resumes read-write. The inner has independent commit/rollback.

**Exercise 4.** With default pgJDBC, the Spring flag is false yet an UPDATE inside `readOnly=true` is rejected by PostgreSQL. Is Spring secretly setting the flag to true?

**Answer:** Not necessarily. The driver can turn `Connection.setReadOnly(true)` into `BEGIN READ ONLY`. You must check `readOnlyMode` and SQL logs/server state.

**Exercise 5.** The flag is set to true, yet the annotated method bypasses the Spring proxy due to `this.method()`. What needs to be checked?

**Answer:** The self-called method's transaction advice may not run at all. You need a proxy boundary or appropriate programmatic `TransactionTemplate` to create the transaction.

**Exercise 6.** A test on H2 fails with a syntax error at begin; does that test prove DML is blocked?

**Answer:** No. The manager may fail to initialize the transaction because H2 does not understand the dialect SQL. Use a real production-like DB or a controlled custom hook.

**Exercise 7.** Server read-only rejects UPDATE, yet the service already sent an email before that. Does rolling back the transaction recall the email?

**Answer:** No. Enforcement only constrains the database transaction; side effects must be designed separately.

## 15. Conclusion and Official Documentation

`setEnforceReadOnly(true)` is an **SQL-layer enforcement** mechanism for **new JDBC transactions with `readOnly=true`** managed by `DataSourceTransactionManager`. It makes the intent of `@Transactional(readOnly=true)` more concrete via `SET TRANSACTION READ ONLY`, though its effect depends on the database, driver, propagation, proxy invocation, and manager choice.

Do not confuse it with the JDBC hint `Connection.setReadOnly(true)`, isolation, timeout, `setValidateExistingTransaction`, or database permissions. Some PostgreSQL drivers **already enforce from the hint** even when the flag is false. To verify reliably, compare server mode on the exact connection/physical transaction, deliberately attempt an UPDATE on a regular table, read data after the proxy completes, and use a compatible DB.

References:

- [Spring Framework — DataSourceTransactionManager Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): `setEnforceReadOnly` and `prepareTransactionalConnection`.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): REQUIRED vs REQUIRES_NEW and physical transactions.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): readOnly, proxy, and default metadata.
- [PostgreSQL — SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): read-only access mode and restricted commands.
- [pgJDBC — Initializing the Driver](https://jdbc.postgresql.org/documentation/use/): `readOnlyMode=ignore`, `transaction`, `always`.
- [Java 17 — java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `setReadOnly` is a hint.
- [H2 — SQL Commands](https://h2database.com/html/commands.html): SQL syntax supported by H2.
