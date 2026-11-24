# READ_UNCOMMITTED and actual support limits in Spring Transaction Management

## 1. Learning objectives

`READ_UNCOMMITTED` is the weakest isolation level among the four common SQL standard levels. Theoretically, it **allows one transaction to read data that another transaction has not yet committed** — the **dirty read** phenomenon. Spring Framework can request this level via `@Transactional(isolation = Isolation.READ_UNCOMMITTED)` or `TransactionDefinition.ISOLATION_READ_UNCOMMITTED`.

However, an annotation **does not guarantee** that the database will permit dirty reads. Whether it applies also depends on the transaction manager, JDBC driver, DBMS/engine, propagation, any existing transaction, the connection used, and the timing of the read.

After this lesson, you will be able to:

1. Understand how dirty reads occur and why the observed data may be rolled back immediately afterward.
2. Distinguish `READ_UNCOMMITTED` from `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` with respect to dirty reads, non-repeatable reads, and phantom reads.
3. Declare isolation in Spring JDBC using `@Transactional`, `TransactionTemplate`, or XML, and know when the configuration takes effect.
4. Inspect `DatabaseMetaData.supportsTransactionIsolationLevel(...)` and `Connection.getTransactionIsolation()` without **mistaking metadata/settings for proof of runtime behavior**.
5. Understand real-world differences: PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED`; Oracle Database does not allow dirty reads; MySQL InnoDB, H2, and SQL Server provide mechanisms according to their product documentation.
6. Run a Java 17+ experiment with a **writer holding an uncommitted transaction** and **two readers using two independent connections/transactions**; then have the writer roll back to prove data was read despite never existing in a committed state.
7. Avoid anti-patterns: reading from the same connection and concluding dirty read; self-invocation bypassing the Spring proxy; putting isolation on an inner `REQUIRED` method while an outer transaction is already open; relying on dirty reads for balance checks, payments, or critical business decisions.

**Scope:** This lesson focuses on **synchronous Spring Framework transaction management with JDBC**, while JPA, JTA, reactive, and other DBMSs are covered in the limitations sections. Do not enable `READ_UNCOMMITTED` for performance without a specific business requirement and concrete measurements.

## 2. What is a dirty read?

Suppose an account/table `price_quote` has a committed price of 100. Two independent transactions run concurrently:

```text
Time               Transaction A (writer)         Transaction B (reader)
---------          ----------------------         ----------------------
T0                 BEGIN                           BEGIN READ_UNCOMMITTED
T1                 UPDATE price = 900
                   (NOT COMMITTED YET)
T2                                                 SELECT price -> 900 (*)
T3                 ROLLBACK
T4                                                 If re-read -> may be 100
T5                 --                              COMMIT/END
```

`(*)` is a **dirty read**: B reads the value 900 written by A while A has not committed yet. A rolls back, so 900 **never became a committed value**. Any business decision made based on 900 can be wrong.

Another example is an uncommitted `INSERT` of record `id=42`. A reader at a level allowing dirty reads can see this record; if the writer rolls back, the reader no longer sees it afterward.

Key distinctions:

- **Read your own writes:** The same transaction/connection writes and reads back its own change. This is normal behavior and **does not prove dirty read**.
- **Dirty read:** A **different** transaction/connection **B** reads uncommitted changes from transaction **A**.
- **Non-repeatable read:** B reads a row once, A **commits** a new value, and B reads the same row again and sees a different value.
- **Phantom read:** B repeats a predicate query and may see a different set of rows because another transaction **committed** matching INSERTs/DELETEs.
- **Dirty write:** Two transactions overwrite each other's uncommitted changes; `READ_UNCOMMITTED` does not imply dirty writes are allowed. Many engines still hold write locks and prevent this.

### Phenomenon matrix under the standard model

| SQL conceptual isolation | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ_UNCOMMITTED` | Possible | Possible | Possible |
| `READ_COMMITTED` | No | Possible | Possible |
| `REPEATABLE_READ` | No | No per standard definition | Possible per standard model |
| `SERIALIZABLE` | No | No | No |

**"Possible" does not mean "guaranteed to appear."** Modern DBMSs have MVCC, snapshots, predicate locking, additional guarantees, or map isolation levels to other semantics. For instance, PostgreSQL does not allow dirty reads even when `READ UNCOMMITTED` is requested. Query types (`SELECT`, locking reads, UPDATE), snapshot isolation, storage engines, and DB configuration can also change behavior. The matrix describes what the model permits, **not a promise across every backend**.

## 3. How does Spring represent READ_UNCOMMITTED?

### 3.1. With annotation

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_UNCOMMITTED, readOnly = true)
public long countRows() {
    return jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM price_quote",
        Long.class);
}
```

This is an **illustrative fragment**, without declaring `jdbcTemplate` or the enclosing class. `Isolation.READ_UNCOMMITTED` tells Spring: when creating a new transaction, ask the transaction manager to set the corresponding isolation level. `readOnly=true` is an optimization/read-intent hint; it does not determine whether dirty reads occur, nor is it always a mechanism that blocks data writes.

`Isolation.DEFAULT` (the default of `@Transactional`) does **not** mean `READ_COMMITTED`. It means **use the default of the underlying database/resource**, which can vary; for instance, MySQL InnoDB defaults to `REPEATABLE_READ`, while PostgreSQL/H2 typically default to `READ_COMMITTED`.

### 3.2. With TransactionTemplate

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setIsolationLevel(TransactionDefinition.ISOLATION_READ_UNCOMMITTED);
template.setReadOnly(true);

Integer count = template.execute(status ->
    jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM price_quote", Integer.class));
```

This is a **fragment**, requiring `transactionManager`/`jdbcTemplate` beans and imports for `TransactionDefinition`/`TransactionTemplate`. `TransactionTemplate` applies isolation when it **actually creates a new transaction**; if `REQUIRED` propagation joins an existing transaction, different annotations/settings on the inner scope do not automatically change outer's isolation.

### 3.3. With XML transaction advice

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" isolation="READ_UNCOMMITTED"
                   read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

This is also a **configuration fragment**, requiring the `tx` namespace, manager bean, and AOP advisor binding the advice to a pointcut. Isolation still flows through the Spring transaction manager and JDBC connection; XML cannot force a DBMS to implement an unsupported feature.

### 3.4. Mapping to JDBC

Spring uses isolation concepts closely aligned with JDBC constants:

| Spring | JDBC `Connection` | JDBC numeric value |
| --- | --- | --- |
| `Isolation.READ_UNCOMMITTED` | `TRANSACTION_READ_UNCOMMITTED` | `1` |
| `Isolation.READ_COMMITTED` | `TRANSACTION_READ_COMMITTED` | `2` |
| `Isolation.REPEATABLE_READ` | `TRANSACTION_REPEATABLE_READ` | `4` |
| `Isolation.SERIALIZABLE` | `TRANSACTION_SERIALIZABLE` | `8` |
| `Isolation.DEFAULT` | Do not force a level; use resource default | Not a concrete JDBC level number |

With `DataSourceTransactionManager`/`JdbcTransactionManager`, when **starting a new JDBC transaction**, Spring may call `Connection.setTransactionIsolation(...)` per metadata. On completion, Spring generally restores the connection attributes it changed so isolation does not "leak" to the next borrower from the pool.

**Limitation:** Setting the level may be rejected by the driver, converted/mapped, or accepted as a setting while the DB still executes different semantics. Therefore `@Transactional(isolation = Isolation.READ_UNCOMMITTED)` is a **request**, not proof that data can actually be dirty-read.

## 4. When does isolation take effect under propagation?

The key is a **new physical transaction**:

```text
Caller without a transaction
    |
    v
@Transactional(isolation = READ_UNCOMMITTED, propagation = REQUIRED)
    |
    +-- Spring opens a new JDBC transaction
    +-- manager requests READ_UNCOMMITTED
    +-- read executes under the level actually applied by DB/driver
    +-- COMMIT/ROLLBACK -> connection returned to pool
```

However, when the caller already has a transaction:

```text
Outer @Transactional(isolation = READ_COMMITTED)
   |
   +-- physical transaction T at READ_COMMITTED
   |
   +-- Inner @Transactional(
   |       isolation = READ_UNCOMMITTED,
   |       propagation = REQUIRED)
   |       -> joins T
   |       -> does not automatically switch T to READ_UNCOMMITTED
   |
   +-- outer completes transaction T
```

| Scope | Is a new level requested? | Conclusion |
| --- | --- | --- |
| `REQUIRED` with no outer transaction | Yes, when creating a physical transaction | Can apply if manager/DB support it |
| `REQUIRED` with outer transaction | Inner only joins existing transaction | Inner's isolation is typically ignored in default lenient mode |
| `REQUIRES_NEW` with outer transaction | Creates a new physical transaction, suspends outer | Can request its own new isolation |
| `NESTED` with outer JDBC transaction | Savepoint on the same physical transaction | Not an independent transaction to change isolation |
| Self-invocation via `this.method()` | Can bypass the proxy | Metadata on inner method is not applied |
| Method runs in a new thread | Does not inherit caller's thread-bound transaction | Must define a new transaction/explicit async design |

Spring provides `AbstractPlatformTransactionManager.setValidateExistingTransaction(true)`. When enabled, an inner `REQUIRED` requesting an isolation **different** from the current transaction can be rejected rather than silently joining. This is a configuration guard, **not** a mechanism to upgrade/downgrade an already-existing transaction's isolation.

Example configuration to detect mismatches, used only if the application genuinely wants strict policy:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    var manager = new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

This is a fragment, not included in section 8's runnable project because the example intentionally observes the default lenient behavior. If a transaction manager bean already exists, do not accidentally create a second manager or alter app-wide configuration just to test one method.

## 5. Practical DBMS-specific limits

### 5.1. PostgreSQL: accepts the level name, but has no dirty reads

Official PostgreSQL documentation explicitly states that **`READ UNCOMMITTED` is treated as `READ COMMITTED`**. That means:

- Do not expect to read uncommitted changes from another transaction merely by requesting this level.
- Even if the JDBC driver accepts the isolation setting call, that does not prove dirty reads occur.
- PostgreSQL uses MVCC; for an ordinary SELECT under `READ COMMITTED`, the statement snapshot sees only appropriate committed data, not uncommitted changes from other transactions.
- If a test is written assuming "READ_UNCOMMITTED must always see the writer's uncommitted row," that test **will be invalid when ported to PostgreSQL**.

Therefore, **do not extrapolate H2/MySQL demo results to PostgreSQL**.

Reference: https://www.postgresql.org/docs/current/transaction-iso.html and https://www.postgresql.org/docs/current/sql-set-transaction.html

### 5.2. MySQL InnoDB: supports READ UNCOMMITTED, but requires the right engine

InnoDB provides all four levels: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`. InnoDB's common default is `REPEATABLE READ`.

InnoDB documentation states that at `READ UNCOMMITTED`, ordinary non-locking `SELECT`s can perform **dirty reads**, meaning observed data may reflect an uncommitted state.

Reasoning caveats:

- Confirm the table uses **InnoDB or an appropriate transactional engine**. A non-transactional engine without rollback makes the "writer rollback" example invalid.
- A `SELECT ... FOR UPDATE`, locking read, or update statement does not necessarily follow simple ordinary non-locking SELECT rules. Do not equate all SQL with a simple dirty-read mental model.
- Behavior can be affected by DB/driver version, connection pool, session isolation, and query form.
- Never use dirty reads as proof that data "exists" for payments, inventory checks, or invoice issuance.

Reference: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html

### 5.3. SQL Server: supports READ UNCOMMITTED, NOLOCK is not harmless

Microsoft documents that `READ UNCOMMITTED` allows reading rows modified but not yet committed by other transactions. The behavior is often compared with the `NOLOCK` table hint in read scenarios.

However:

- Dirty reads can cause reports to see data that vanishes if the writer rolls back.
- Not every query is "lock-free," and `NOLOCK` is not a default cure-all for every blocking issue.
- SQL Server offers alternatives such as `READ_COMMITTED_SNAPSHOT`/`SNAPSHOT` to balance concurrency and consistency differently; they are not equivalent to enabling dirty reads.
- Certain SQL Server platforms/variants have additional rules, so verify **the exact SQL Server engine/edition and configuration**.

Reference: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql

### 5.4. Oracle Database: does not allow dirty reads

Oracle Database documentation states that **`READ UNCOMMITTED` is not an isolation level providing dirty reads**. Oracle implements levels such as `READ COMMITTED`, `SERIALIZABLE`, and read-only transactions per its product semantics; ordinary queries use consistent reads.

- Do not assume `@Transactional(isolation = READ_UNCOMMITTED)` lets Oracle read uncommitted data.
- The JDBC driver may reject or handle the isolation request according to its actual capabilities; verify the behavior and any errors returned.
- Do not attempt to "shortcut" with dirty reads for speed: throughput goals can be met with proper transaction/SQL/index strategies while still reading committed data.

Reference: https://docs.oracle.com/en/database/oracle/oracle-database/21/adfns/sql-processing-for-application-developers.html

### 5.5. H2: a suitable environment to study dirty reads

H2 documents support for `READ UNCOMMITTED` and describes that dirty reads can occur at this level. H2's default level is typically `READ COMMITTED`.

Hence we use **a named in-memory H2 database** to run a controlled experiment:

- Transaction A INSERTs a record but **does not commit yet**.
- Reader B at `READ_UNCOMMITTED` on a **different** JDBC transaction/connection runs SELECT before A finishes.
- Reader C at `READ_COMMITTED` also runs SELECT while A is still open.
- A rolls back.
- C reads again after rollback: the record is gone.

Important: H2 is only a **technical demo**, not a compatibility guarantee for PostgreSQL, Oracle, MySQL, or SQL Server in production.

Reference: https://h2database.com/html/advanced.html and https://h2database.com/html/features.html

### 5.6. Summary table without conflating databases

| DB / engine | READ_UNCOMMITTED and dirty reads | Expectation to verify |
| --- | --- | --- |
| H2 | Supported per H2 docs | With ordinary SELECT and two transactions on different connections, uncommitted rows can be seen |
| MySQL InnoDB | Supported | Test on the same version/engine/driver with real queries |
| SQL Server | Supported | Test per SQL Server edition/options; evaluate `NOLOCK` risks |
| PostgreSQL | `READ UNCOMMITTED` is treated as `READ COMMITTED` | Do not expect dirty reads |
| Oracle Database | Dirty reads not permitted | Do not expect dirty reads; check driver error/mapping |
| Non-transactional engine | Rollback not guaranteed | Do not use to draw transactional isolation conclusions |

This reflects **documented behavior**, not a promise that every query/driver/version reproduces the exact same output as H2. When deploying for real, verify version, engine, schema, transaction mode, and workload.

## 6. Why does JDBC metadata not prove dirty reads?

JDBC provides two useful checks:

```java
try (Connection c = dataSource.getConnection()) {
    boolean advertised = c.getMetaData()
            .supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_READ_UNCOMMITTED);
    int current = c.getTransactionIsolation();
    System.out.println("driver reports support: " + advertised);
    System.out.println("current JDBC level: " + current);
}
```

This is a Java fragment; `DataSource` and imports must be supplied.

Proper interpretation:

- `DatabaseMetaData.supportsTransactionIsolationLevel(int)` returns **what the driver reports supporting** for an isolation level.
- `Connection.getTransactionIsolation()` reflects the JDBC connection's isolation state; value `1` corresponds to `TRANSACTION_READ_UNCOMMITTED`.
- `Connection.setTransactionIsolation(int)` requests changing the isolation level when a new transaction is prepared, subject to manager/driver/backend.

Questions metadata **cannot answer**:

- Will a SELECT see an uncommitted row just written by another connection?
- Does the backend map READ_UNCOMMITTED to READ_COMMITTED?
- Is the current transaction an outer transaction opened before the inner annotation requested a new level?
- Is the SQL running on the exact connection/DB/schema/tenant being tested?
- Did the reader read while the writer was genuinely **uncommitted**, or had the writer already rolled back/committed beforehand?

**Therefore concurrency behavior verification is required.** The reliable method is using two concurrent physical connections, holding the writer open with synchronization, running SELECT while the writer has not finished, then rolling back the writer and checking committed state.

## 7. Designing a proper experiment and control conditions

### 7.1. Two-session timeline

```text
Thread W / Connection W                     Thread Main / Connection R
-------------------------------------       -----------------------------------
@Transactional REQUIRED begin
INSERT id=101, amount=900 (uncommitted)
signal "inserted"
wait("release")

                                            @Transactional READ_UNCOMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              H2 demo: 1 (dirty read)

                                            @Transactional READ_COMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              H2 demo: 0

release writer
throw IllegalStateException
Spring ROLLBACK
                                            @Transactional READ_COMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              0 (no committed row)
```

### 7.2. Conditions for valid conclusions

1. Writer uses `@Transactional` and is called via a Spring proxy, not by manually instantiating the service with `new`.
2. Writer **holds its transaction incomplete** when the reader executes. `CountDownLatch` synchronizes ordering; do not rely on `Thread.sleep(100)` or scheduling luck.
3. Reader is called from a caller with no outer transaction, so `@Transactional(isolation=...)` opens its own transaction and actually applies the isolation.
4. Writer and reader use **the same DB but two connections**. The connection pool must have enough connections for concurrent reading and writing; do not use pool size 1.
5. Tables are created before the experiment starts; avoid implicit DDL commits while the writer holds a transaction.
6. Use an ordinary `SELECT COUNT(*)`, not a locking read, and do not read from JPA's first-level cache.
7. Use a dedicated ID per test to prevent stale data from skewing conclusions.
8. **Re-read after writer rollback** to distinguish dirty reads from committed data.
9. Include timeouts and `finally` blocks to release the writer/`ExecutorService`, avoiding permanent hangs if the reader blocks or the test fails.
10. On DBs other than H2, **do not hardcode** asserting "dirty read = 1" if the vendor intentionally does not support that level; use expected behavior matching the vendor's documentation.

## 8. Runnable Java 17+ Spring Boot project

The example uses Spring Boot **3.5.6**, Spring JDBC, H2, Maven, and JUnit 5. The files are complete enough to create the folder and run; Spring Boot automatically creates the `DataSource` connection pool and `PlatformTransactionManager` for JDBC. No JPA configuration is needed.

### 8.1. Directory structure

```text
read-uncommitted-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── IsolationApplication.java
    │   │   ├── PendingWriteService.java
    │   │   ├── IsolationReadService.java
    │   │   └── OuterIsolationService.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── IsolationIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>read-uncommitted-lab</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

`spring-boot-starter-jdbc` supplies `JdbcTemplate` and JDBC transaction infrastructure; H2 is the in-memory database; `spring-boot-starter-test` includes Spring Test/JUnit 5.

### 8.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:dirty_read_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.main.banner-mode=off
```

**Why is a pool larger than 1 needed?** The writer holds one connection inside its transaction while the main thread needs another connection for the reader. A pool size of `5` prevents deadlocks waiting for connections and enables testing concurrent reads. The H2 URL is **named** `dirty_read_lab` so connections in the same JVM reach the same database, and `DB_CLOSE_DELAY=-1` keeps the database alive in the JVM.

### 8.4. PendingWriteService.java: holding an uncommitted transaction

**`src/main/java/demo/PendingWriteService.java`**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PendingWriteService {
    private final JdbcTemplate jdbc;

    public PendingWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void insertThenRollback(
            long id,
            CountDownLatch inserted,
            CountDownLatch release) {

        jdbc.update(
                "INSERT INTO isolation_probe(id, amount) VALUES (?, ?)",
                id, 900);

        // Signal reader that INSERT has run in transaction W.
        inserted.countDown();

        try {
            // Hold transaction W open until reader finishes reading.
            if (!release.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("writer timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("writer interrupted", ex);
        }

        // Unchecked exception crosses transaction interceptor => rollback.
        throw new IllegalStateException("forced rollback");
    }
}
```

`insertThenRollback` is invoked **on a Spring bean proxy** from an executor thread. The synchronous Spring transaction is opened on the writer's thread, not on the main thread. After `INSERT`, the writer signals and waits; it has not returned from the method yet, so neither commit nor rollback has occurred. When the main thread signals `release`, the method throws an unchecked exception and the Spring interceptor rolls back.

In production, never hold transactions open waiting on network/UI like this demonstration; this is strictly a **test synchronization** with a timeout to reliably reproduce dirty reads.

### 8.5. IsolationReadService.java: separating READ_UNCOMMITTED and READ_COMMITTED

**`src/main/java/demo/IsolationReadService.java`**

```java
package demo;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IsolationReadService {
    private final JdbcTemplate jdbc;

    public IsolationReadService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Observation(int effectiveJdbcLevel, int rows) {}

    @Transactional(
            isolation = Isolation.READ_UNCOMMITTED,
            readOnly = true)
    public Observation readUncommitted(long id) {
        return observe(id);
    }

    @Transactional(
            isolation = Isolation.READ_COMMITTED,
            readOnly = true)
    public Observation readCommitted(long id) {
        return observe(id);
    }

    private Observation observe(long id) {
        Integer jdbcLevel = jdbc.execute(
                (ConnectionCallback<Integer>)
                        Connection::getTransactionIsolation);

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM isolation_probe WHERE id = ?",
                Integer.class, id);

        return new Observation(
                Objects.requireNonNull(jdbcLevel),
                Objects.requireNonNull(rows));
    }
}
```

Both public methods are called through the Spring proxy. When the caller has no outer transaction, each method creates a new transaction under default `REQUIRED` and requests the corresponding JDBC isolation. `JdbcTemplate` acquires the transaction-bound connection; `getTransactionIsolation()` and the SELECT query execute within the same method/transaction. `Observation` records both **the level reported by the JDBC connection** and **the row count observed by the query**.

`Objects.requireNonNull(...)` ensures the demo does not silently turn a `null` into fake data. `Connection.getTransactionIsolation()` alone does not prove vendor semantics; the concurrent read itself is the behavioral test.

### 8.6. OuterIsolationService.java: proving inner REQUIRED does not change level

**`src/main/java/demo/OuterIsolationService.java`**

```java
package demo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterIsolationService {
    private final IsolationReadService reader;

    public OuterIsolationService(IsolationReadService reader) {
        this.reader = reader;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public IsolationReadService.Observation readViaInnerRequired(long id) {
        // Inner requests READ_UNCOMMITTED, but same physical transaction.
        return reader.readUncommitted(id);
    }
}
```

`OuterIsolationService` and `IsolationReadService` are **two separate beans** so the inner call passes through the proxy. With the manager in default lenient mode, outer creates a `READ_COMMITTED` transaction and inner `REQUIRED` joins that transaction. The actual JDBC level remains `READ_COMMITTED`, even though inner's annotation says `READ_UNCOMMITTED`.

When `validateExistingTransaction=true` is enabled, this kind of mismatch can be rejected; the lesson uses the default to verify that **inner does not override outer's isolation**.

### 8.7. IsolationApplication.java: coordinating two connections and printing results

**`src/main/java/demo/IsolationApplication.java`**

```java
package demo;

import java.sql.Connection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            DataSource dataSource,
            JdbcTemplate jdbc,
            PendingWriteService writer,
            IsolationReadService reader,
            OuterIsolationService outer) {

        return args -> {
            // Run DDL before the concurrency transaction demo.
            jdbc.execute("""
                    CREATE TABLE IF NOT EXISTS isolation_probe (
                        id BIGINT PRIMARY KEY,
                        amount INT NOT NULL
                    )
                    """);

            try (Connection connection = dataSource.getConnection()) {
                boolean supported = connection.getMetaData()
                        .supportsTransactionIsolationLevel(
                                Connection.TRANSACTION_READ_UNCOMMITTED);
                System.out.println(
                        "driver reports READ_UNCOMMITTED supported: "
                                + supported);
            }

            CountDownLatch inserted = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            ExecutorService pool = Executors.newSingleThreadExecutor();

            try {
                Future<?> task = pool.submit(() ->
                        writer.insertThenRollback(101L, inserted, release));

                try {
                    if (!inserted.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "writer did not insert");
                    }

                    var dirty = reader.readUncommitted(101L);
                    var clean = reader.readCommitted(101L);

                    System.out.println(
                            "RU effective JDBC level: "
                                    + dirty.effectiveJdbcLevel());
                    System.out.println(
                            "RU while writer open: " + dirty.rows());
                    System.out.println(
                            "RC effective JDBC level: "
                                    + clean.effectiveJdbcLevel());
                    System.out.println(
                            "RC while writer open: " + clean.rows());
                } finally {
                    // Even if reading throws an error, do not leave writer waiting forever.
                    release.countDown();
                }

                boolean rolledBack = false;
                try {
                    task.get(10, TimeUnit.SECONDS);
                } catch (ExecutionException ex) {
                    Throwable failure = ex.getCause();
                    if (!(failure instanceof IllegalStateException)
                            || !"forced rollback".equals(
                                    failure.getMessage())) {
                        throw ex;
                    }
                    rolledBack = true;
                }

                System.out.println(
                        "writer rollback observed: " + rolledBack);

                System.out.println(
                        "RC after writer rollback: "
                                + reader.readCommitted(101L).rows());

                System.out.println(
                        "joined REQUIRED actual JDBC level: "
                                + outer.readViaInnerRequired(101L)
                                       .effectiveJdbcLevel());
            } finally {
                release.countDown();
                pool.shutdownNow();
            }
        };
    }
}
```

This is a runnable `@SpringBootApplication` file together with the remaining files. Several key details:

- `ExecutorService` has a single worker thread for the writer; the main thread executes the reader calls.
- `inserted.await` waits until the writer has executed `INSERT`, not relying on arbitrary sleep durations.
- The writer is still holding its physical transaction when the readers run.
- `READ_UNCOMMITTED` and `READ_COMMITTED` are called **sequentially on the main thread**, yet each has its own connection/transaction distinct from the writer's active connection.
- `release.countDown()` in `finally` releases the writer even if a reader throws an error.
- `Future.get` waits for the writer to finish; the exception from `insertThenRollback` is **expected** so Spring rolls back. Only `IllegalStateException("forced rollback")` is accepted; any other error is rethrown to prevent false positives.
- After the writer rolls back, `readCommitted` checks the **committed** state. If the dirty read saw a row earlier and none remains after rollback, that proves the row was read while uncommitted.
- Finally, the outer method requests `READ_COMMITTED` and calls the inner method wanting `READ_UNCOMMITTED`, verifying that inner `REQUIRED` isolation does not alter outer's level.
- All cases use ID 101 in the demo, with a fresh table and only one writer for this ID.

### 8.8. Run command and expected stdout on H2

Requires Java 17+ and Maven; in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Lines printed by **the program itself** (ignoring Spring/Maven startup logs):

```text
driver reports READ_UNCOMMITTED supported: true
RU effective JDBC level: 1
RU while writer open: 1
RC effective JDBC level: 2
RC while writer open: 0
writer rollback observed: true
RC after writer rollback: 0
joined REQUIRED actual JDBC level: 2
```

Notable observations:

| Observation | Explanation |
| --- | --- |
| `RU while writer open: 1` | H2 reader at `READ_UNCOMMITTED` saw the writer transaction's uncommitted INSERT |
| `RC while writer open: 0` | `READ_COMMITTED` reader did not see the uncommitted INSERT |
| `writer rollback observed: true` | Writer threw the expected exception and Spring rolled back the transaction |
| `RC after writer rollback: 0` | The record was never committed; the dirty-read data was transient |
| `joined REQUIRED actual JDBC level: 2` | Inner reader requested RU but joined outer RC without changing outer's isolation |

**Limit of stdout:** This is the **expected output for H2 and the configured versions/components listed above**. If run on PostgreSQL, do not expect the line `RU while writer open: 1`. On other databases, the driver may error on unsupported isolation or behave differently. Verification must rely on actual execution in your environment rather than "fixing" code to force every vendor to produce dirty reads.

## 9. Integration test verifying both metadata and semantics

Create **`src/test/java/demo/IsolationIntegrationTest.java`**:

```java
package demo;

import java.sql.Connection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class IsolationIntegrationTest {
    @Autowired
    private DataSource dataSource;

    @Autowired
    private PendingWriteService writer;

    @Autowired
    private IsolationReadService reader;

    @Autowired
    private OuterIsolationService outer;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void driverAdvertisesReadUncommitted() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.getMetaData()
                    .supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_READ_UNCOMMITTED));
        }
    }

    @Test
    void readUncommittedCanSeeRowThatLaterRollsBack() throws Exception {
        long id = 1001L;
        CountDownLatch inserted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> task = pool.submit(() ->
                    writer.insertThenRollback(id, inserted, release));

            try {
                assertTrue(inserted.await(10, TimeUnit.SECONDS));

                var dirty = reader.readUncommitted(id);
                var clean = reader.readCommitted(id);

                assertEquals(
                        Connection.TRANSACTION_READ_UNCOMMITTED,
                        dirty.effectiveJdbcLevel());
                assertEquals(
                        Connection.TRANSACTION_READ_COMMITTED,
                        clean.effectiveJdbcLevel());

                assertEquals(1, dirty.rows()); // Expected for H2 lab.
                assertEquals(0, clean.rows());
            } finally {
                release.countDown();
            }

            ExecutionException thrown = assertThrows(
                    ExecutionException.class,
                    () -> task.get(10, TimeUnit.SECONDS));
            assertInstanceOf(
                    IllegalStateException.class, thrown.getCause());
            assertEquals(
                    "forced rollback", thrown.getCause().getMessage());

            assertEquals(0, reader.readCommitted(id).rows());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void innerRequiredCannotChangeIsolationOfExistingOuter() {
        var result = outer.readViaInnerRequired(9999L);
        assertEquals(
                Connection.TRANSACTION_READ_COMMITTED,
                result.effectiveJdbcLevel());
        assertEquals(0, result.rows());
    }
}
```

Run:

```bash
mvn test
```

**Expectation:** all three tests pass on H2 with Spring Boot/JDBC configured as in the project. `@SpringBootTest` builds the application context and runs `CommandLineRunner`, which already created the table and ran the demo with ID 101; the tests use IDs 1001 and 9999 to avoid collisions.

The tests do not use `@Transactional` on the class or methods. Adding it would make Spring TestContext open an enclosing test transaction that `REQUIRED` reader methods join, breaking the condition "two reader transactions opened fresh with their own isolation"—and the isolation test would no longer measure what you think it measures.

### 9.1. Why must the test use real concurrency?

A test that only calls:

```java
jdbc.update("INSERT INTO isolation_probe(id, amount) VALUES (?, ?)",
        55L, 900);

int count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM isolation_probe WHERE id = ?",
        Integer.class, 55L);
```

**Does not prove dirty read.** The statements might be on the same transaction/connection, or the INSERT might have auto-committed before the SELECT. You must hold **an uncommitted writer transaction** on one connection and read from **a second connection** during that window.

### 9.2. What makes a test see 0 even after requesting READ_UNCOMMITTED?

- The backend intentionally prohibits dirty reads, such as PostgreSQL/Oracle.
- The reader did not actually open a new transaction because it joined an outer `REQUIRED`.
- The driver did not apply the level as expected or the wrong manager was selected.
- The writer already rolled back/committed before the read (synchronization bug).
- Two DataSources point to different databases/schemas.
- The query hit a JPA cache or a read replica instead of the primary database.
- The SQL/engine type has different locking/snapshot semantics than assumed.

Do not mechanically change expected from 1 to 0. First determine **why** using metadata, JDBC isolation levels, and actual tests.

## 10. Misconfiguration cases in Spring applications

### 10.1. Looking only at @Transactional and concluding dirty reads are enabled

`@Transactional(isolation=READ_UNCOMMITTED)` is a configuration request. The transaction manager must actually open a new physical transaction, the JDBC driver must accept the setting, the DB must support those semantics, and the SQL must read while the writer is still uncommitted.

### 10.2. Calling a method with `this`, bypassing the proxy

`this.someTransactionalMethod()` inside the same bean in standard proxy mode does not trigger the inner method's transaction advice. The isolation annotation can be ignored. Inject another Spring bean and call through the proxy as shown in the demo.

### 10.3. Inner REQUIRED wants RU while outer is already RC

Inner `REQUIRED` joins the outer transaction. Spring does not change the level of an already-started transaction. If separating physical transactions matters, consider `REQUIRES_NEW`; however, that changes transaction semantics and requires an extra JDBC connection. Do not use `REQUIRES_NEW` merely to "make the annotation take effect" without evaluating business logic.

### 10.4. Treating driver metadata `true` as a guarantee of dirty reads

`supportsTransactionIsolationLevel(...)` is just one piece of information. Check the connection's effective isolation and behavior between **two** concurrent transactions. PostgreSQL is an important example where a level is accepted/mapped yet dirty-read semantics do not exist.

### 10.5. Treating read-only as an isolation level

`readOnly=true` is an optimization hint for the transaction/driver; it does not prevent dirty reads, does not turn READ_UNCOMMITTED into READ_COMMITTED, and is not a barrier blocking all write SQL on every DB. Isolation and read-only are two distinct properties.

### 10.6. Using READ_UNCOMMITTED as a default cure for lock contention

Dirty reads can break business invariants. Even for transient monitoring dashboards, label them "not guaranteed committed." Before lowering isolation, try index/SQL optimization, shortening transaction duration, sizing the connection pool appropriately, or DB-appropriate snapshot/MVCC-based read committed.

### 10.7. Assuming queries at RU never block

DBMSs also use schema locks, metadata locks, row/write locks, locks during joins/ordering/DDL, and other mechanisms. SQL Server `NOLOCK` does not mean "never locks" and is not a cure-all for every blocking scenario.

### 10.8. Setting isolation manually on a pooled connection and forgetting to restore

When using Spring-managed transactions, let the manager set and restore isolation. Manually calling `connection.setTransactionIsolation(...)` on a pooled connection without restoring it can leak state to subsequent requests. In raw JDBC tests, always use a dedicated connection, save the previous setting, and restore it before returning to the pool.

### 10.9. Extrapolating from a mock/in-memory database to production

H2 is convenient for unit/integration demos, but MySQL/PostgreSQL/Oracle/SQL Server have different semantics, SQL dialects, and locking. Run integration tests against the actual production DB/driver—for example via Testcontainers—before enabling a new isolation level.

### 10.10. Basing irreversible actions on uncommitted data

A dirty read can trigger emails, payments, notifications, or changes in external systems. When the writer rolls back, these side effects do not automatically roll back. Never base financial, authorization, inventory, or public-facing state decisions on uncommitted data.

### 10.11. Setting isolation at the JPA layer and assuming it equals JDBC

With `JpaTransactionManager`, the JPA provider and dialect may support or restrict custom isolation. The persistence context has a first-level cache and flush semantics. Do not treat `EntityManager.find` results as a direct SELECT in a fresh JDBC transaction. Test specifically against the provider, JDBC access, and actual manager.

### 10.12. Ignoring the outermost boundary

If a reader joins an outer transaction, an inner query is not enough to prove committed state or changed isolation. If a writer is marked rollback-only or its commit/rollback is not yet finished, wait until the outermost transaction completes before concluding final data state.

## 11. Pre-deployment verification checklist for actual support

- [ ] Identify the exact DBMS, version, storage engine, driver version, and transaction manager implementation.
- [ ] Verify `@Transactional` executes through the proxy, with no self-invocation causing metadata to be skipped.
- [ ] Verify a new transaction is actually created at the reader method, not joining an outer `REQUIRED`.
- [ ] Check `DatabaseMetaData.supportsTransactionIsolationLevel(Connection.TRANSACTION_READ_UNCOMMITTED)`.
- [ ] Read `Connection.getTransactionIsolation()` on **the connection participating in the reader transaction**, not an arbitrary connection from the pool.
- [ ] Check whether the server/driver maps RU to RC (especially PostgreSQL).
- [ ] Use the right JDBC DataSource, database/schema/tenant/primary; avoid read replicas and JPA caching.
- [ ] Create an uncommitted writer transaction held open with a latch; run the reader on a separate connection.
- [ ] Record behavior before writer rollback and compare data after writer rollback.
- [ ] Do not apply hardcoded H2 expectations to other vendors.
- [ ] Evaluate correctness/security/side effects if dirty reads actually occur.
- [ ] Choose an appropriate isolation level and add regression tests running on the production backend.

## 12. Questions and exercises

**Exercise 1.** Transaction A INSERTs a row and has not committed. B on the same connection as A SELECTs and sees the row. Is that a dirty read?

**Answer:** No. That is read-your-own-writes within the same transaction/connection. To demonstrate a dirty read, B must be a different transaction/connection.

**Exercise 2.** Running `@Transactional(isolation = READ_UNCOMMITTED)` on PostgreSQL. Will the reader definitely see uncommitted data?

**Answer:** No. PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED` and does not permit dirty reads.

**Exercise 3.** On H2, an RU reader sees the temporary row, then the writer rolls back and an RC read no longer sees the row. What does the test prove?

**Answer:** The reader read an uncommitted state. The fact that the data disappears after rollback proves temporary data cannot be treated as committed information.

**Exercise 4.** Outer transaction starts at READ_COMMITTED, inner `REQUIRED` declares READ_UNCOMMITTED. Will inner definitely execute at RU?

**Answer:** No. Inner joins the already-open physical transaction and typically uses outer's isolation. Strict mode `validateExistingTransaction=true` can even reject the mismatch.

**Exercise 5.** `supportsTransactionIsolationLevel(...)` returns true. Can you skip the two-connection experiment?

**Answer:** No. Metadata reports driver capability, not whether a specific SELECT actually performs dirty reads under the DB/engine semantics.

**Exercise 6.** Does MySQL InnoDB default to READ_UNCOMMITTED?

**Answer:** No. InnoDB usually defaults to `REPEATABLE_READ`; to test RU you must configure a specific transaction/session and verify the actual driver/engine.

**Exercise 7.** Will Oracle Database allow dirty reads if the Spring annotation is RU?

**Answer:** No. Oracle Database does not provide dirty-read semantics; an annotation cannot force the engine beyond what it supports.

**Exercise 8.** Why does the demo set `spring.datasource.hikari.maximum-pool-size=5`?

**Answer:** The writer holds one connection open. The reader needs another connection concurrently; a pool size of 1 could make the reader simply wait instead of testing concurrency.

**Exercise 9.** Why must the table be created before opening the writer transaction?

**Answer:** DDL on many DBs performs an implicit commit and can alter transaction boundaries. Isolation tests should isolate DML from DDL behavior.

**Exercise 10.** Should RU be enabled to avoid all lock contention for funds transfer logic?

**Answer:** No. It can allow reading data that will roll back and cause wrong decisions. Pick ways to reduce contention that preserve consistency, such as optimizing SQL/indexes/transaction duration or appropriate snapshot/MVCC mechanisms.

## 13. Official references

- Spring Framework — `@Transactional` settings, isolation/propagation, and proxy rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction propagation, `REQUIRED`, and `validateExistingTransaction`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — `TransactionDefinition` Javadoc (ISOLATION_READ_UNCOMMITTED): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — JDBC connections and transaction manager: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- PostgreSQL — `SET TRANSACTION`, READ UNCOMMITTED treated as READ COMMITTED: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 InnoDB — Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- Microsoft SQL Server — `SET TRANSACTION ISOLATION LEVEL`: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql
- Oracle Database — SQL Processing for Application Developers, isolation supported: https://docs.oracle.com/en/database/oracle/oracle-database/21/adfns/sql-processing-for-application-developers.html
- H2 Database — Transaction Isolation: https://h2database.com/html/advanced.html
- JDBC API — `Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- JDBC API — `DatabaseMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html

**Conclusion:** `READ_UNCOMMITTED` is an **isolation level request**, not a guarantee of observing uncommitted data across every database. Verify transaction boundaries, the actual connection, driver metadata, and DBMS behavior. In Spring, only a new physical transaction can receive a new isolation level; inner `REQUIRED` does not change outer's level. Before using it in a real system, test concurrency with **two connections**, wait for the writer to roll back, and verify reads after the transaction ends—while seriously weighing the risk of dirty reads to business decisions.