# Preparing Spring Libraries and a Compatible Database

## 1. Goal: Ready to Run Your First Transaction

For a Spring method using `@Transactional` to actually commit or roll back data, the application needs a **transaction management library**, a **database access tool**, a **JDBC driver**, a **DataSource**, a **transaction manager**, and a **database that supports transactions**. Adding the annotation to the code is only part of the job.

After this lesson, you can:

1. Understand the role of each dependency and choose the right JDBC/JPA stack.
2. Set up a minimal **Spring Boot + JDBC + H2** application to learn transactions without installing a database server.
3. Switch to **PostgreSQL** via profile configuration, verify the connection, schema, and rollback.
4. Recognize dependency/driver/configuration errors and know when a transaction is genuinely applied.

The examples use **Java 17, Spring Boot 3.3.13 (Spring Framework 6.x), and Gradle 8.5**: this is a compatible set of versions, pinned so the examples are reproducible, not a claim that they are the latest. For projects using an internal BOM/convention plugin, keep the project's version management rather than inserting arbitrary plugin versions.

> Practice path: run correctly with H2 first, then enable the PostgreSQL profile. H2 is helpful for demonstrating commit/rollback, but it is not a perfect replica of PostgreSQL in terms of SQL dialect, isolation, locking, or production behavior.

## 2. Component and Responsibility Map

```text
Spring Boot Application
    |
    | @Transactional  (Spring AOP / spring-tx)
    v
TransactionInterceptor -> PlatformTransactionManager
                                |
                                | manages transaction and JDBC Connection
                                v
                          DataSource / HikariCP
                                |
                                | appropriate JDBC driver
                                v
                       H2 or PostgreSQL
                                ^
                                |
                       JdbcTemplate / JDBC
```

| Component | Which question does it answer? | How it is included in this lesson |
| --- | --- | --- |
| `spring-tx` | Who declares, starts, commits, or rolls back the transaction? | Pulled transitively by the JDBC starter |
| `spring-jdbc` | How does Java send SQL and participate in a Spring-managed transaction? | `spring-boot-starter-jdbc` |
| `JdbcTemplate` | Who executes `SELECT/UPDATE` SQL, receives results, and translates JDBC exceptions? | Auto-configured as a bean when Boot configures JDBC |
| `DataSource` / HikariCP | Where do database connections come from? | JDBC starter + `spring.datasource.*` |
| JDBC driver | Who communicates using the database's exact protocol? | `com.h2database:h2` or `org.postgresql:postgresql` |
| Database engine | Who guarantees commit/rollback and data rules? | H2 for learning, PostgreSQL for near-real-world verification |
| Transaction proxy | Where are `@Transactional` calls intercepted? | Spring/Boot auto-configured transaction infrastructure |

For **synchronous JDBC** applications, Spring uses a `PlatformTransactionManager` suitable for `DataSource` (for example, `JdbcTransactionManager`/`DataSourceTransactionManager`). `JdbcTemplate` works with the connection bound to the transaction by Spring. For **JPA**, the transaction manager is suited for JPA/`EntityManagerFactory`, and Hibernate manages the persistence context.

Do not confuse the layers:

- **Spring `@Transactional`** defines business transaction boundaries via a proxy/interceptor.
- **The JDBC driver** only provides the ability to talk to the database; it does not by itself define the transaction boundary of an entire method.
- **The database** is where COMMIT/ROLLBACK is actually applied. In JDBC, `jdbc.update(...)` may have already sent SQL while the transaction has not yet committed.
- **JPA EntityManager** adds an entity tracking/flush layer. This lesson prioritizes JDBC so you can see direct SQL behavior.

### Checking Database Suitability

- The database needs a transaction mechanism; PostgreSQL satisfies this. For MySQL, use a transactional table engine such as InnoDB—do not use MyISAM for rollback examples.
- The JDBC URL and driver must match the same DB type: `jdbc:h2:...` for H2; `jdbc:postgresql://...` for PostgreSQL. `r2dbc:...` URLs are for a different, reactive stack.
- The account needs permissions to connect, create, and manipulate tables needed for the demo; in real environments, grant least privilege and do not store passwords in Git.
- The Spring, Gradle, Java, and driver versions must lie within the compatibility range of the toolchain. Do not mix Spring Boot 2.x dependencies with 3.x.

## 3. Choosing the Minimal Library Set: Spring Boot Starter JDBC

`JdbcTemplate` is an easy-to-observe choice for a first transaction: we write two SQL statements ourselves and verify both roll back when a later step fails. There is no need for `spring-boot-starter-web` or an ORM if HTTP or JPA is not being used yet.

Create a standalone Spring Boot project with Gradle Groovy DSL, Java 17, and the Gradle Wrapper. **`build.gradle`**:

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

    // Both drivers can reside on the classpath together.
    // The profile's JDBC URL selects the actual DB to connect to.
    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`settings.gradle`**:

```groovy
rootProject.name = 'tx-lab'
```

Dependency explanation:

- `spring-boot-starter-jdbc` already brings in Spring JDBC, Spring transaction infrastructure, and HikariCP. There is no need to declare `spring-tx` again just to use `@Transactional`.
- `runtimeOnly` is appropriate because the code compiles against JDBC/Spring JDBC APIs; the JDBC driver is actually needed at runtime. If learning only on H2, you can omit the PostgreSQL driver, and vice versa.
- Spring Boot dependency management selects compatible versions for managed libraries; do not specify separate versions for starters, H2, or the PostgreSQL driver without a reason.
- `io.spring.dependency-management` in this Gradle configuration applies the BOM managed by the Spring Boot plugin. When using a build convention that already provides a version catalog/BOM, follow that project's approach.
- `@Transactional` in the example imports `org.springframework.transaction.annotation.Transactional`.

Verify the environment in the project directory:

```bash
java -version
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

On Windows, use `gradlew.bat` instead of `./gradlew`. Java must be compatible with Spring Boot; Gradle needs to locate a JDK 17 toolchain. `runtimeClasspath` must contain `spring-jdbc`, HikariCP, and the driver you intend to connect with. If dependency resolution fails, resolve it before running business logic: Maven Central/Plugin Portal access, network proxy, incompatible Gradle plugin, or wrong dependency overrides can all be causes.

## 4. Configuring H2 for the First Practice Exercise

Arrange the files as follows:

```text
tx-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/transaction/
    │   ├── TxLabApplication.java
    │   └── TransferService.java
    └── resources/
        ├── application.yml
        ├── application-postgres.yml
        ├── schema.sql
        └── data.sql
```

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: tx-lab
  datasource:
    url: "jdbc:h2:mem:txlab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

`jdbc:h2:mem:txlab` creates a database **in the JVM's memory**; data is not retained when the process exits. `DB_CLOSE_DELAY=-1` keeps the DB alive until the JVM stops even when the last connection closes; it does **not** make H2 persistent like a disk-backed database.

`spring.sql.init.mode=always` runs SQL initialization scripts when the application starts. Spring Boot also supports auto-initializing embedded DBs by default; we set this property explicitly so the demo flow is easy to compare after switching profiles. The driver class is usually inferred from the JDBC URL, so specifying `spring.datasource.driver-class-name` is not mandatory.

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
```

**`src/main/resources/data.sql`**:

```sql
-- Use only on a dedicated practice database: resets data on every boot.
DELETE FROM accounts;
INSERT INTO accounts (id, balance) VALUES (1, 100);
INSERT INTO accounts (id, balance) VALUES (2, 100);
```

Two accounts let us test a transfer of 10 units while the total balance remains 200. The `data.sql` script intentionally deletes data before every run; **do not use this in production or on a database storing data that must be kept**. In real systems, use versioned migrations (Flyway or Liquibase), seed test data independently, and control DB permissions.

### Do You Need `@EnableTransactionManagement` or a Manual `DataSource` Bean?

With **Spring Boot auto-configuration**, a valid `DataSource` together with the JDBC starter is usually enough for Boot to configure `JdbcTemplate` and the appropriate transaction manager; you do not need to manually declare `@Bean DataSource`, create a connection pool, or add `@EnableTransactionManagement` to run this example. In **Spring Framework without Boot**, or when you disable auto-configuration, you must explicitly provide the corresponding infrastructure.

## 5. Executing One Transaction and One Rollback

The following two classes belong to the same `demo.transaction` package. This is **complete Spring Boot application code when combined with the build.gradle, application.yml, and SQL files above**; it is not a standalone Java file that can be run with `javac` because it requires Spring and database dependencies.

**`src/main/java/demo/transaction/TransferService.java`**:

```java
package demo.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        move(fromId, toId, amount);
    }

    @Transactional
    public void transferThenFail(long fromId, long toId, long amount) {
        move(fromId, toId, amount);
        throw new IllegalStateException("simulated failure");
    }

    private void move(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? "
                + "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException(
                "Source missing or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Destination missing");
        }
    }
}
```

**`src/main/java/demo/transaction/TxLabApplication.java`**:

```java
package demo.transaction;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + balances(jdbc));

            try {
                service.transferThenFail(1L, 2L, 10L);
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }

            System.out.println("After rollback: " + balances(jdbc));

            service.transfer(1L, 2L, 10L);
            System.out.println("After commit: " + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Long first = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1", Long.class);
        Long second = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 2", Long.class);
        return first + " / " + second;
    }
}
```

Run on Linux/macOS:

```bash
./gradlew bootRun
```

Run on Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Among the Spring Boot logs, the four `System.out.println` lines appear in order:

```text
Before: 100 / 100
Caught: simulated failure
After rollback: 100 / 100
After commit: 90 / 110
```

**Why is this result trustworthy?**

1. Spring Boot connects to H2, runs `schema.sql` and `data.sql` before `CommandLineRunner` queries the table.
2. `transferThenFail` executes two `UPDATE` statements and then throws `IllegalStateException`. This is an unchecked exception, so by default Spring rolls back the transaction.
3. After the proxy handles the rollback and propagates the exception outward, the runner re-reads the DB in `balances(jdbc)`: the result returns to `100 / 100`.
4. `transfer` completes normally, and the transaction coordinated by the proxy is committed before the call returns; the final read is `90 / 110`.

Important point: the runner is injected with the **Spring-managed `TransferService`**, so the call `service.transfer(...)` goes through the transaction proxy. If you call another `@Transactional` method from inside the same bean (*self-invocation*), standard proxy mode **does not** apply new advice to the internal call. You also should not instantiate the service yourself with `new` outside the container and expect `@Transactional` to work.

In JDBC, `jdbc.update(...)` sends SQL to the DB within the open transaction. **Executed SQL does not mean committed**. When the method ends with an unchecked exception, the transaction manager calls rollback; if each `UPDATE` ran on an independent autocommit connection, the data would not have the atomicity shown in the example.

## 6. Connecting to PostgreSQL with a Dedicated Profile

H2 is useful for getting started, but part of transaction testing needs to be performed on the actual production DB engine. PostgreSQL is suitable for practicing constraints, locking, isolation, and deadlocks in greater depth. The following example switches DBs using **configuration**, without modifying the Java service.

### 6.1. Starting Local PostgreSQL

When Docker is available and port 5432 is not in use:

```bash
docker run -d --name txlab-postgres \
  -e POSTGRES_DB=txlab \
  -e POSTGRES_USER=txlab \
  -e POSTGRES_PASSWORD=local_only \
  -p 5432:5432 postgres:16
```

On Windows PowerShell, you can run it on a single line:

```powershell
docker run -d --name txlab-postgres -e POSTGRES_DB=txlab -e POSTGRES_USER=txlab -e POSTGRES_PASSWORD=local_only -p 5432:5432 postgres:16
```

This password is **for local demo use only**, not a production secret configuration pattern. Check that the DB process is accepting connections:

```bash
docker ps --filter "name=txlab-postgres"
docker exec txlab-postgres pg_isready -U txlab -d txlab
```

The output of `pg_isready` should report `accepting connections`. If the database is installed outside Docker, prepare the `txlab` database, valid user, host, and port accordingly.

### 6.2. Switching Profile and Running

`build.gradle` already has `runtimeOnly 'org.postgresql:postgresql'`. Create **`src/main/resources/application-postgres.yml`**:

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/txlab"
    username: ${DB_USER:txlab}
    password: ${DB_PASSWORD:local_only}
  sql:
    init:
      mode: always
```

Run on Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=postgres'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=postgres"
```

When the `postgres` profile is active, `spring.datasource.url` in the profile file overrides the H2 URL in `application.yml`. Do not rely on Spring Boot guessing the driver; a `jdbc:postgresql://...` URL must have the PostgreSQL driver on the runtime classpath. `schema.sql` and `data.sql` in this lesson use syntax compatible with both H2 and PostgreSQL; with `spring.sql.init.mode=always`, PostgreSQL **also resets practice data on every boot**.

After the app finishes running, inspect the table state in PostgreSQL:

```bash
docker exec txlab-postgres psql -U txlab -d txlab \
  -c "SELECT id, balance FROM accounts ORDER BY id;"
```

The query result corresponds to two rows:

```text
 id | balance
----+---------
  1 |      90
  2 |     110
(2 rows)
```

If another run reads `100 / 100`, check whether the application just restarted and the `data.sql` script reset the data. For production, use migrations and **do not** set `mode=always` with a `data.sql` file containing `DELETE`; disable script initialization after switching to Flyway/Liquibase. Separate accounts, profiles, and secrets per environment to avoid connecting to the wrong DB.

### 6.3. When Can H2 Not Replace PostgreSQL?

| Criterion | H2 in-memory | PostgreSQL |
| --- | --- | --- |
| Running exercises without installing a server | Good | Requires server/container |
| Learning transaction boundaries, basic SQL rollback | Good | Good |
| Data after the JVM process ends | Lost with `mem:` URL | Can be persisted if server/storage is maintained |
| PostgreSQL SQL dialect and data types | Not guaranteed to match | Exact engine |
| Locks, deadlocks, isolation, query planner | Should not generalize results | Should test directly |
| Production deployment | Do not choose H2 in-memory as primary storage | A common production choice |

In particular, "same JDBC API" does not mean two DBs handle SQL, DDL, isolation, or error codes identically. If the real DB is MySQL/SQL Server/Oracle, test on that exact engine.

## 7. What Changes When Moving from JDBC to JPA?

If a lesson or project uses entities, repositories, and Hibernate instead of `JdbcTemplate`, the appropriate starter is **`spring-boot-starter-data-jpa`**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

The JPA starter pulls in Hibernate, Spring Data JPA, Spring ORM, and the necessary JDBC components. With a `DataSource` and typical JPA setup, Spring Boot configures the appropriate JPA transaction manager. **There is no need to add the JDBC starter just to get basic Spring JDBC** because the JPA starter already includes the relevant dependencies; only add another stack when you actually use it.

Key differences to remember:

- `JdbcTemplate` sends SQL when calling `update`; JPA has a `Persistence Context`, dirty checking, and flush, so entity changes may be synchronized later.
- Spring Boot 3.x uses `jakarta.persistence.*`, not `javax.persistence.*` seen in older JPA examples.
- Do not use `spring.jpa.hibernate.ddl-auto=create` or `create-drop` on a real database with data. `ddl-auto=update` also does not replace a versioned migration tool for production.
- Do not enable Hibernate's auto-schema generation alongside SQL initialization/migrations without actively controlling ordering; in the JDBC example in this lesson, Hibernate is not needed.
- If mixing JDBC/JPA or multiple DataSources, determine exactly which transaction manager owns which resource. A regular `@Transactional` does not automatically turn multiple independent DBs into a distributed transaction.

To learn your first transaction, choose **one stack first**: simple JDBC to observe SQL, or JPA once you understand entities and the persistence context.

## 8. Layer-by-Layer Checks When Startup Fails

| Symptom | Possible Cause | Verification Step |
| --- | --- | --- |
| `Failed to configure a DataSource` | Missing URL/embedded DB/driver, wrong profile | Check `spring.datasource.*` and runtime dependencies |
| `Cannot load driver class` or `No suitable driver` | Driver is not on the runtime classpath or URL is incorrect | Check `gradlew dependencies`, H2/PostgreSQL driver |
| `Connection refused` | PostgreSQL is not running, wrong host/port | `docker ps`, `pg_isready`, port 5432 |
| `password authentication failed` | Wrong user/password or out-of-sync secret | Check user and runtime environment |
| `Table "ACCOUNTS" not found` / `relation "accounts" does not exist` | Schema initialization did not run or connected to wrong database | Inspect `schema.sql`, `mode`, active profile, table creation permissions |
| `NoUniqueBeanDefinitionException` for manager | Multiple transaction managers exist and none is explicitly chosen | Review manager beans, specify `@Transactional(transactionManager = "...")` when needed |
| No rollback after error | Method did not go through Spring proxy, exception was caught and swallowed, or did not match rollback rules | Use injected bean, let unchecked exception escape, or declare rollback rules |
| Re-run shows data lost/reverted to initial state | H2 `mem` exited or `data.sql` reset | Confirm demo environment; do not use reset script on real DB |
| H2 works but PostgreSQL fails | Different SQL dialect, schema, constraint, or configuration | Read the SQL exception and test against real PostgreSQL |

### Short Checklist Before Saying "Transactions Are Ready"

1. JDK, Gradle, Spring Boot version, and dependency graph are compatible.
2. Appropriate data access starter is present and driver matches the JDBC URL.
3. DataSource connects to the right database, user/port/schema.
4. Transaction manager is appropriate and explicitly chosen when multiple managers exist.
5. Calls to `@Transactional` actually pass through the Spring-managed proxy.
6. Schema/data are created on the right DB, without accidentally resetting real data.
7. Success commit case and failure rollback case have been verified by **re-reading the database after the method finishes**.

If the application can only connect to the DB and run `UPDATE`, that is still not enough to prove a transaction across the whole business operation. When the first SQL statement has already committed separately via autocommit, an error in the second SQL statement cannot automatically undo the first statement. Testing a failure scenario located **after both UPDATE statements**, like `transferThenFail`, shows whether the transaction manager actually wraps them.

## 9. Preparing Properly for Non-Demo Environments

- **Data and schema:** use version-controlled migrations, separate test seeds, and appropriate backups. Do not run data-deleting startup scripts in production.
- **Credentials:** read from environment/secret manager, use an account with least privilege; do not push real secrets to Git.
- **Connection pool:** keep appropriate pool size/timeouts; avoid opening `DriverManager.getConnection(...)` manually inside services because that connection may not participate in Spring transactions.
- **Transaction boundary:** call through Spring bean proxies; avoid long-running transactions spanning HTTP calls or user-wait operations.
- **Observability:** log SQL/errors purposefully and do not log sensitive data. Turn off overly verbose transaction debugging in production if unnecessary.
- **Test on the right DB:** for isolation, locking, deadlock, constraint, or dialect behavior, use a real PostgreSQL/MySQL engine (Testcontainers can be used in integration tests). H2 is only a starting step.
- **Reactive:** if switching to R2DBC, use a reactive connection factory and `ReactiveTransactionManager`; do not mix thread-bound JDBC mechanisms into a reactive pipeline and expect transactions to propagate automatically.

## 10. Self-Check Questions

1. **Is the `spring-tx` dependency alone enough to connect to PostgreSQL?** No: you need the JDBC layer, driver, DataSource, database server, and corresponding configuration.
2. **Why can't the H2 driver connect to `jdbc:postgresql://...` even though it is present?** The H2 driver speaks the H2 protocol; PostgreSQL requires the PostgreSQL driver.
3. **Why does the example put `@Transactional` on public service methods?** So calls from the runner pass through the Spring transaction proxy; private helpers are only called inside the already-opened transaction.
4. **Why is a new query needed after rollback?** To observe the DB state after the transaction manager has processed the rollback, without confusing sent SQL with committed data.
5. **If H2 runs successfully, can we skip testing PostgreSQL?** No, because dialect/isolation/locking and production errors may differ.
6. **When switching to JPA, does modifying a field on a managed entity necessarily send an UPDATE immediately?** No. JPA/Hibernate may defer SQL until flush; you still need the transaction manager and DB to actually commit.

**Key takeaway:** A trustworthy first transaction requires **the right dependencies + driver + DataSource + transaction manager + transactional database + commit/rollback tests**. Once the environment is solid, you are ready to study propagation policies, isolation, timeouts, rollback rules, and JPA flush in depth.

## Reference Documentation

- Spring Boot 3.3, Java/Gradle requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3, SQL Databases / JDBC / DataSource / JPA: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot, Database Initialization: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
- Spring Framework, Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework, Declarative Transactions and proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Boot Gradle Plugin 3.3.13: https://plugins.gradle.org/plugin/org.springframework.boot/3.3.13
- Dependency Management Gradle Plugin 1.1.7: https://plugins.gradle.org/plugin/io.spring.dependency-management/1.1.7
- PostgreSQL JDBC driver documentation: https://jdbc.postgresql.org/documentation/
