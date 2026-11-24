# Distinguishing the Read-Only Hint from Write-Blocking Mechanisms in Spring Transaction Management

## 1. The Most Important Answer

`@Transactional(readOnly = true)` in Spring **is first and foremost a declaration of transaction intent**: this unit of work is expected to be read-only, and the transaction infrastructure may use that information to optimize execution. It is **not a security rule or a default SQL filter provided by Spring**. Some DBMSs or JDBC drivers will indeed reject `INSERT`, `UPDATE`, and `DELETE` inside a transaction marked read-only; other systems treat it purely as a hint and still allow writes.

Therefore, you must distinguish at least four questions:

1. **Does Spring record the transaction as read-only?** This can be checked using `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` while inside the transaction.
2. **Does the JDBC driver receive the read-only hint?** A Spring JDBC transaction manager may call `Connection.setReadOnly(true)` when creating a new transaction. Per JDBC, this is a *hint*, and the driver/database has the right to handle it differently.
3. **Does the ORM optimize read operations?** A JPA provider like Hibernate may adjust the flush mode and entity management behavior to reduce unnecessary work.
4. **Is there an actual write-blocking mechanism?** You must verify the DB transaction mode (for example `SET TRANSACTION READ ONLY` on engines that support it), DB user privileges, or other control policies; even these mechanisms have their own scope and limits.

A sound design does not state: "Because it is marked `readOnly=true`, there is definitely no way to UPDATE the database." Instead, determine whether you **want read optimization** or **require a write-prohibition guarantee**, choose the appropriate mechanism, and verify it against the production database.

## 2. Why Is There Confusion Around the Word "Read-Only"?

In a Spring application, "read-only" can refer to several different layers:

| Layer | Manifestation | Does It Guarantee Blocking All Writes? |
|---|---|---|
| **Business method intent** | `@Transactional(readOnly=true)` | **No**. This is metadata intended for the infrastructure |
| **Spring transaction context** | `TransactionDefinition.isReadOnly()` / `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | **No**. The status flag does not parse or filter SQL statements |
| **JDBC connection** | `Connection.setReadOnly(true)` | **Not guaranteed across all drivers**; some drivers/environments enforce read-only, others ignore it |
| **ORM / Hibernate** | Changes flush mode, optimizes dirty checking for queries | **Not a security barrier**; behavior depends on the provider and how SQL is emitted |
| **DB read-only transaction mode** | `SET TRANSACTION READ ONLY` / `BEGIN READ ONLY` on supported DBs | **Can block data-modifying operations within the DB mode's scope**, though restrictions/allowed SQL vary by DB |
| **Database account privileges** | Account has only `SELECT`, no DML privileges on protected objects | **A stronger access-control measure**, provided GRANTs/roles/ownership are configured properly |
| **Application-level policy** | Guard rejecting write commands in a read-only flow | Blocks **code paths going through the guard**, not other SQL paths bypassing the guard |

Three terms easily conflated are **hint**, **optimization**, and **enforcement**:

- **Hint**: input information for another component, but not a mandatory contract requiring that component to reject writes.
- **Optimization**: reduces operation cost (for example, less flushing/dirty checking) without necessarily changing execution permissions.
- **Enforcement**: an actual checkpoint that rejects write commands when a condition is violated; you need to know whether that checkpoint lives in the application, driver, transaction mode, or database authorization.

**Do not call Hibernate optimizations "the DB guarantees no writes".** Conversely, do not say every database ignores read-only either: some drivers/DBs genuinely block write statements in a read-only transaction.

## 3. How Does Spring Handle `@Transactional(readOnly=true)`?

Example declaring intent on a read service:

```java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;

    public InvoiceQueryService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceView findInvoice(long id) {
        return repository.findViewById(id);
    }
}
```

This code is **illustrative only**, requiring `InvoiceRepository`/`InvoiceView` classes and appropriate imports. When an external call passes through the Spring transaction proxy, the interceptor reads the `TransactionAttribute` containing propagation, isolation, timeout, and the **readOnly flag**. When a new physical transaction needs to start, the transaction manager has the opportunity to pass read-only down to the underlying resource.

With common local JDBC transaction managers (`DataSourceTransactionManager` or subclass `JdbcTransactionManager`), a simplified lifecycle is:

```text
Caller
  |
  v
Spring transaction proxy
  |
  +-- read TransactionAttribute: readOnly=true
  |
  +-- start new physical transaction (if needed)
  |      |
  |      +-- acquire JDBC Connection
  |      +-- prepare connection, may call setReadOnly(true)
  |      +-- set isolation/autoCommit, bind connection to thread
  |      +-- depending on config: execute explicit SQL enforcement
  |
  +-- run business method
  |      |
  |      +-- SELECT / [may still attempt INSERT, UPDATE...]
  |
  +-- commit or roll back per transaction rules
  +-- cleanup/reset connection after completion
```

Spring **does not by default wrap `JdbcTemplate.update()` in an if-block catching every write operation when read-only metadata is true**. `JdbcTemplate` still sends SQL down to the connection; whether it succeeds depends on the entire infrastructure chain.

### 3.1. What Is JDBC `Connection.setReadOnly(true)` Actually?

JDBC defines `setReadOnly(boolean)` as a **hint** so the driver/database can optimize and/or apply corresponding behavior. There is no uniform guarantee that `setReadOnly(true)` forces all DBMSs to reject all DML.

Specifically, **H2**'s `JdbcConnection.setReadOnly(boolean)` API documents that this parameter **is ignored**: a Spring transaction marked read-only can still write to a regular H2 table when no other enforcement mechanism is present.

In other environments, such as PostgreSQL JDBC, the driver has options and read-only mode management logic that can create a genuinely write-restricted transaction. Thus, you must neither extrapolate from H2 that the JDBC hint is **always** ineffective, nor use a write-blocking driver to claim the annotation itself is a security control.

### 3.2. Spring Metadata Is Not `Connection.isReadOnly()`

The two values can differ:

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

// To read the connection state: obtain the bound connection
// via DataSourceUtils, do not casually open a new connection from the pool.
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    boolean jdbcReadOnly = connection.isReadOnly();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

This is a **snippet** used inside a method with an injected `dataSource`; it requires importing `Connection`, `DataSourceUtils`, and the appropriate JDBC exceptions. `springReadOnly` is Spring's **active metadata**; `jdbcReadOnly` is what the JDBC driver reports on the connection. The value of `isReadOnly()` also **does not verify all DML permissions**. A driver may return `false` even when Spring metadata is `true` (H2), or the driver/DB may block writes due to other configuration.

To verify **enforcement**, run an integration test that deliberately attempts a write operation on a non-sensitive test table and then checks the error and DB state; do not look at a single boolean alone.

## 4. Read-Only in JPA/Hibernate Is an Optimization, Not a General SQL Rule

A service using Spring Data JPA typically declares:

```java
@Transactional(readOnly = true)
public List<CustomerDto> listCustomers() {
    return customerRepository.findAll()
        .stream()
        .map(CustomerDto::fromEntity)
        .toList();
}
```

This is a snippet, not a standalone runnable class. With modern Hibernate integration, Spring can switch the flush mode to **`MANUAL`** in a read-only transaction to reduce auto-flush/dirty checking work; exact behavior also depends on version and provider configuration. This is an **optimization**. It is not the same as a general SQL rejection rule generated by Spring.

Cases to distinguish:

- **Modifying a property of a managed entity**: under read-only/flush optimization, Hibernate may not automatically emit an `UPDATE` to the DB when the transaction commits. If you do not see SQL, the cause may be flushing/dirty checking rather than the DB blocking writes.
- **`EntityManager.createNativeQuery("UPDATE ...").executeUpdate()`** or `JdbcTemplate.update(...)`: these are different DML execution paths. They **may** go down to JDBC/DB and succeed or be rejected according to transaction mode/driver/permissions.
- **`repository.save(entity)`** inside an outer read-only transaction: calling this method does not by itself guarantee a write to the DB; persist/merge/flush operations and the transaction context determine whether SQL runs and commits. Do not rely on "`save` ran without error" to conclude the write succeeded.
- **`@Modifying`** on a Spring Data JPA query marks a data-modifying query. It **does not by itself turn a caller's read-only physical transaction into read-write**. You normally need an appropriate write transaction and properly configured transaction boundaries.
- A provider, flush mode, JDBC driver, or database may actively block certain operations; you cannot deduce all cases from the annotation alone.

The **Spring Data JPA — Transactionality** documentation explicitly states that the read-only flag **does not perform checks** to ensure you do not trigger modifying queries; it is a hint that can help the provider optimize. This point is more important than any single observation from a unit test.

## 5. Runnable Java 17 Example: H2 Writes Successfully Even Though the Transaction Is Marked Read-Only

The demo's goal is to distinguish **metadata** from **enforcing write blocking** using real DB results. H2 is chosen because its JDBC driver publicly ignores `Connection.setReadOnly(boolean)`. The program uses Spring JDBC and `TransactionTemplate` so it does not depend on whether `@Transactional` self-invocation passes through a proxy.

We execute three consecutive scenarios:

1. **HINT_ONLY**: `TransactionTemplate.setReadOnly(true)`, print Spring metadata, call `INSERT`. With H2, the INSERT commits successfully.
2. **APPLICATION_GUARD**: also `readOnly=true`, but the application actively throws an exception **before** calling INSERT. No new row is added; that is due to the guard in code, **not H2 enforcing the JDBC hint**.
3. **READ_WRITE**: normal transaction, the guard allows writing, and INSERT succeeds.

The demo intentionally does not enable `setEnforceReadOnly(true)` because that mechanism issues **DB-specific SQL** that should not be assumed for H2. The lesson covers DB enforcement separately in the next section.

### 5.1. Project Structure

```text
spring-readonly-hint-demo/
├── pom.xml
└── src/main/java/com/example/readonly/Main.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-readonly-hint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring JDBC includes the transaction infrastructure and `JdbcTemplate`. H2 is an in-memory database; the program does not need Spring Boot, a container, or a server. `DriverManagerDataSource` is simple and is not a connection pool for production use. JDK 17+ is compatible with Spring Framework 6.2.

### 5.3. `src/main/java/com/example/readonly/Main.java`

```java
package com.example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static boolean springReadOnly() {
        return TransactionSynchronizationManager
                .isCurrentTransactionReadOnly();
    }

    // This is an APPLICATION-WRITTEN guard, not a Spring mechanism
    // that automatically checks every SQL statement.
    private static void requireWritable() {
        if (springReadOnly()) {
            throw new IllegalStateException("application blocked write");
        }
    }

    private static int count(JdbcTemplate jdbc) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM read_only_events",
                Integer.class
        );
        return value;
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:readonly_hint;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
                "CREATE TABLE read_only_events (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                "detail VARCHAR(80) NOT NULL)"
        );

        JdbcTransactionManager manager = new JdbcTransactionManager(ds);

        TransactionTemplate readOnly = new TransactionTemplate(manager);
        readOnly.setReadOnly(true);

        TransactionTemplate readWrite = new TransactionTemplate(manager);

        System.out.println("=== HINT_ONLY ===");
        readOnly.executeWithoutResult(status -> {
            System.out.println("springReadOnly=" + springReadOnly());
            jdbc.update(
                    "INSERT INTO read_only_events(detail) VALUES (?)",
                    "written despite hint"
            );
            System.out.println("writeInReadOnly=SUCCEEDED");
        });
        System.out.println("rows=" + count(jdbc));

        System.out.println("=== APPLICATION_GUARD ===");
        try {
            readOnly.executeWithoutResult(status -> {
                System.out.println("springReadOnly=" + springReadOnly());
                requireWritable(); // Throws error before the INSERT statement.
                jdbc.update(
                        "INSERT INTO read_only_events(detail) VALUES (?)",
                        "guard should prevent this"
                );
            });
        } catch (IllegalStateException ex) {
            System.out.println("guard=" + ex.getMessage());
        }
        System.out.println("rows=" + count(jdbc));

        System.out.println("=== READ_WRITE ===");
        readWrite.executeWithoutResult(status -> {
            System.out.println("springReadOnly=" + springReadOnly());
            requireWritable();
            jdbc.update(
                    "INSERT INTO read_only_events(detail) VALUES (?)",
                    "regular write"
            );
        });
        System.out.println("rows=" + count(jdbc));
    }
}
```

**Why is this a valid test?**

- Both `TransactionTemplate` instances use the same `JdbcTransactionManager` and the same datasource. `executeWithoutResult` opens a new transaction when there is no outer transaction.
- `isCurrentTransactionReadOnly()` shows the **metadata Spring receives**; it is not a write-permission condition of H2.
- H2 `Connection.setReadOnly(true)` is documented in its JDBC docs as **ignoring the readOnly parameter**. Because there is no other enforcement, `JdbcTemplate.update` still executes INSERT and the transaction commits.
- The `requireWritable()` guard prevents calling INSERT **on the controlled code path**. Another method that forgets to call the guard can still write; this is not an authorization mechanism.
- When the guard throws an unchecked exception, `TransactionTemplate` rolls back that transaction; no INSERT ran in this branch.
- `readWrite` leaves the default `readOnly=false`, so the guard permits it. Both records (from the hint branch and the write branch) end up in H2.

### 5.4. Running and Expected stdout

Install JDK 17+ and Maven, and from the `spring-readonly-hint-demo` directory run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.readonly.Main
```

The lines printed **by the program itself**; extra Maven or logging output depending on the environment is not listed:

```text
=== HINT_ONLY ===
springReadOnly=true
writeInReadOnly=SUCCEEDED
rows=1
=== APPLICATION_GUARD ===
springReadOnly=true
guard=application blocked write
rows=1
=== READ_WRITE ===
springReadOnly=false
rows=2
```

**Correct interpretation:** In the **specific H2 environment of the demo**, Spring readOnly metadata is true yet the INSERT statement still succeeds. The second branch rejects the write thanks to **an application-written check**, not the database. That output **does not mean** every database always accepts write SQL under `@Transactional(readOnly=true)`; for instance, PostgreSQL or another JDBC driver may enforce a real read-only mode.

If you replace H2 with a production database, keep the intent of the test but **do not hardcode expected stdout**: you need to evaluate the transaction manager, JDBC driver, DB session mode, and connection permissions.

## 6. Database Transaction-Level Write-Blocking Mechanisms

If business logic requires **the database to actually reject DML** within a transaction, you need to choose an enforcement mechanism backed by the DB. An example with PostgreSQL (regular table, not a temporary table) is:

```sql
BEGIN;
SET TRANSACTION READ ONLY;

SELECT current_setting('transaction_read_only');  -- 'on'

-- Example existing permanent table in the schema:
INSERT INTO invoices(id, amount) VALUES (1001, 50);
-- PostgreSQL reports ERROR: cannot execute INSERT in a read-only transaction

ROLLBACK;
```

This is **illustrative SQL running on PostgreSQL when the `invoices` table already exists**. PostgreSQL will reject disallowed DML statements inside a read-only transaction. After an SQL error, the transaction can enter a failed state and require `ROLLBACK`. **Do not confuse** this mechanism with `Connection.setReadOnly(true)` acting purely as a hint in every JDBC driver.

### 6.1. Using `setEnforceReadOnly(true)` with Spring JDBC

`DataSourceTransactionManager` supports configuring `setEnforceReadOnly(true)`. When the transaction definition is read-only and a **new physical transaction** starts, the manager can run the SQL:

```sql
SET TRANSACTION READ ONLY
```

Spring Javadoc states that this SQL is understood by **Oracle, MySQL, and PostgreSQL**; exact behavior/strictness depends on the engine. This is a **stronger option than the JDBC hint**, but **not universal across all DBs**. Some drivers or DBs do not support this SQL syntax; enabling enforcement on the H2 demo is not a safe default.

One way to configure Spring JDBC once **DB support is confirmed**:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcTxConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        JdbcTransactionManager manager = new JdbcTransactionManager(ds);
        manager.setEnforceReadOnly(true);
        return manager;
    }
}
```

The code above is a **configuration class**; you must provide a `DataSource` bean, driver, credentials, and suitable repositories in the application. With this manager and a Spring `@Transactional(readOnly=true)` call through a proxy **that opens a new physical transaction**, Spring can instruct the DB to enter read-only transaction mode; a prohibited INSERT statement will fail **directly at the database**.

**Three limitations to remember:**

1. `setEnforceReadOnly(true)` belongs to **`DataSourceTransactionManager` and subclasses** such as `JdbcTransactionManager`. Do not assume a setting with the same name/meaning automatically exists for `JpaTransactionManager`, `JtaTransactionManager`, or all reactive managers.
2. The degree of "write prohibition" depends on SQL/DB: PostgreSQL read-only transactions have nuances regarding temporary tables and allowed command types; it is not a sandbox against every side effect or every SQL behavior.
3. If `REQUIRED` **joins an existing physical transaction**, the inner part generally does not re-run `SET TRANSACTION READ ONLY` to override the caller's transaction. Wanting a new boundary with its own read-only mode requires designing appropriate propagation and evaluating the trade-offs.

### 6.2. `Connection.setReadOnly` May Still Be Strongly Enforced by the Driver

You should not make a rule saying "PostgreSQL will only ever block writes if `setEnforceReadOnly(true)` is enabled". A JDBC driver may rely on `Connection.setReadOnly(true)` to initialize a DB transaction in read-only mode or have its own configuration. Therefore, **a specific manager + driver default** may already block writes without Spring's SQL enforcement.

What holds true across every system is: **the Spring annotation does not promise a write-prohibition guarantee independent of the driver/database**. To know whether enforcement is in place, you must check the **actual behavior** of the driver/version/database in use.

### 6.3. Do Not Use Read-Only Transactions in Place of Access Permissions

Even a true DB read-only transaction mode applies **per transaction/session**, depending on syntax and lifecycle. In a large application, another method can open its own read-write transaction, a job can use another account, or another system can query the DB directly.

If the goal is **protecting data from modification by an actor/service**, separate database permissions and least privilege are needed, not just annotations. This is especially important when separating query services and command services.

## 7. DB Permissions: A More Practical Write-Blocking Barrier

In PostgreSQL, an example of principles for a read-only user/role's privileges:

```sql
-- Run these administrative operations using a role with appropriate privileges.
CREATE ROLE app_reader LOGIN PASSWORD 'replace-with-secure-secret';

-- Example for a specific table:
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON TABLE public.invoices TO app_reader;

-- Do not grant INSERT, UPDATE, DELETE, or TRUNCATE to app_reader.
-- Also inspect inherited privileges from other roles, PUBLIC, and
-- privileges on views/functions/other schemas that the service may use.
```

This is **policy-illustrating SQL**, not a complete production provisioning script. A role can receive indirect privileges from group roles, `PUBLIC` grants, object ownership, or functions with special privileges; you must audit accurately on the system. Do not store sample passwords in source code. For new tables or other schemas, matching GRANT policies and default privileges are needed.

**Distinguishing goals:**

- **Read-only transaction mode:** applies per transaction to commands forbidden by the DB in that mode.
- **Read-only account/role:** applies by object access permissions and principal privileges, even if code forgets `readOnly=true`.
- **App-level guard:** checks business intent before SQL, giving early feedback without replacing DB permissions.

Use **defense in depth** when strong protection is required: a least-privilege query account, verified read-only transactions, clear query/command separation in the application, and tests deliberately probing unexpected write paths.

## 8. `REQUIRED` and Transaction Joining Can Cause the Hint to Be Misunderstood

Consider two Spring services:

```java
@Service
class OuterService {
    private final ReaderService reader;

    OuterService(ReaderService reader) {
        this.reader = reader;
    }

    @Transactional(readOnly = false)
    public void updateAndRead() {
        // Outer has already opened a read-write physical transaction.
        reader.list();   // Inner REQUIRED joins the outer transaction.
    }
}

@Service
class ReaderService {
    @Transactional(readOnly = true)
    public void list() {
        // No new physical transaction if joining outer.
        // Inner's flag does not automatically turn the outer transaction read-only.
    }
}
```

Both classes are **illustrative snippets** without imports/configuration. When both use `REQUIRED` (the default) and the same transaction manager/resource, the inner joins the outer. The outer's existing **physical transaction** dictates the JDBC/DB state; the inner's `readOnly=true` declaration **does not automatically create a write ban**.

Reversing the situation:

```java
@Transactional(readOnly = true)
public void outerQuery() {
    writerService.performWrite(); // Inner REQUIRED defaults to readOnly=false.
}
```

If `writerService.performWrite()` only joins the outer's read-only physical transaction, it generally **does not automatically re-enable read-write**. Result:

- Hint-only H2 in the demo may still allow writes.
- A DB with read-only transaction enforcement may reject DML.
- Spring may detect some mismatches if `AbstractPlatformTransactionManager.setValidateExistingTransaction(true)` is configured; this policy is for **validating joining transactions**, not a global SQL firewall.

Do not assume that an inner method declaring `@Transactional(readOnly=false)` will "unlock" an outer read-only transaction.

### 8.1. To Be Independent on `readOnly`, a Real Boundary Is Needed

An inner `@Transactional(propagation = REQUIRES_NEW, readOnly = true)` can suspend the outer and open a **separate physical transaction**, using its own read-only configuration. In return, Spring needs an independent transaction/resource; the outer may still hold connections/locks while the inner runs, and the inner's commit/rollback outcome is not atomically tied to the outer.

Use this only when a new transaction is needed by business requirements, not as a default patch for an unclear transaction-splitting model.

### 8.2. Self-Invocation Makes the Annotation Ineffective

```java
@Service
class BrokenService {
    public void entry() {
        this.queryOnly(); // Bypasses the transaction proxy in proxy mode.
    }

    @Transactional(readOnly = true)
    public void queryOnly() {
        // Cannot assume a new read-only transaction was opened.
    }
}
```

This is a snippet. With Spring AOP proxy mode, the `this.queryOnly()` call does not go through the proxy's interceptor; `@Transactional` may not be applied. Therefore, a test that simply calls the method directly on `new BrokenService()` is even more meaningless for verifying DB read-only. Use a Spring-managed service, call through the proxy, or use `TransactionTemplate`.

## 9. Distinguishing from Timeout, Isolation, Rollback, and "Auto-Rollback on INSERT"

`@Transactional` has multiple independent attributes:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    propagation = Propagation.REQUIRED
)
public Report loadReport() {
    // Illustrative code in a service with a suitable repository and Report.
    return repository.fetch();
}
```

- **`readOnly=true`:** read intent, which may affect driver/ORM/DB enforcement.
- **`isolation=...`:** visibility and concurrency rules between transactions.
- **`timeout=5`:** time limit per transaction manager/resource; timeout handling depends on infrastructure.
- **`propagation=REQUIRED`:** joins an existing transaction or opens a new one.

**Read-only does not mean a short timeout, does not guarantee a consistent snapshot across the whole transaction, and is not a separate rollback rule.** If the DB blocks an INSERT, SQL normally throws an error; that exception can trigger a rollback according to transaction policy. It is not that Spring silently "rolls back only the INSERT statement" and commits the rest. Moreover, a transaction with readOnly metadata does not automatically trigger an exception when `JdbcTemplate.update()` is called in all environments.

`readOnly=true` also does not mean `autoCommit=true`. Spring can still create a read-only physical transaction and commit/roll it back like a normal transaction; the commit mechanism does not automatically cause every SQL statement to be prohibited.

## 10. Out-of-Database Side Effects and Missed Write Paths

Even a database transaction marked read-only **does not manage all resources in the application**. A query method can still cause side effects:

- Writing to a Redis cache or updating a counter in cache.
- Sending an HTTP request that modifies data in another system.
- Publishing a message to a broker, publishing a domain event, or triggering an email.
- Writing files, calling a stateful API, updating a search index.
- Spawning an `@Async` task/new thread with its own transaction.
- Calling a second datasource managed by a different transaction manager.
- Invoking a database function/procedure with special privileges or semantics.

Blocking JDBC writes on datasource A **does not automatically block** those side effects. If "read-only" is a **cross-system business or security contract**, you must clearly define which actions are permitted, separate roles/credentials, and have dedicated controls for each system.

**Do not treat a `find...` method name or readOnly annotation as proof of no side effects.** Inspect both the call graph and the code actually executed.

## 11. When Should Each Layer of Protection Be Used?

| Goal | Preferred Mechanism | Verification |
|---|---|---|
| Optimize read-only queries | `@Transactional(readOnly=true)`, provider settings, short transaction boundaries | Profiling, SQL logs, flush mode, query plan |
| Pass read-only intent to JDBC | `TransactionTemplate.setReadOnly(true)` or annotation via proxy | Spring metadata and transaction manager logs |
| DB must reject DML **within this transaction** | DB-supported read-only transaction mode, optionally `setEnforceReadOnly(true)` with compatible JDBC manager | Integration test deliberately running INSERT/UPDATE/DELETE, verify rollback |
| An application/service **must not write** to specific tables | Dedicated DB account with SELECT privilege and without corresponding write/ownership privileges | Audit role grants and verify write SQL is rejected even without readOnly annotation |
| Prevent write bugs from code accidentally calling commands | Application guard, CQRS boundary, behavioral tests | Test across all code paths; DB privileges still protect bypass paths |
| Protect a multi-SELECT consistent report | Choose isolation/snapshot fitting the DB and business logic, optionally read-only transaction | Concurrent integration tests of read data and snapshot point |
| Avoid transactions hanging too long | Reasonable timeout, query timeout, and measuring transaction duration | Runtime metrics, timeout tests, connection pool metrics |

No single read-only checkbox satisfies all of the goals above.

## 12. Proper Test Design: Proving Hint vs. Enforcement

A good test should separate three hypotheses:

**Hypothesis A — metadata only:**

- Open a read-only transaction through Spring.
- Check `TransactionSynchronizationManager.isCurrentTransactionReadOnly() == true`.
- Valid conclusion: **Spring knows the intent**. You cannot yet conclude the DB will reject DML.

**Hypothesis B — DB enforcement:**

- Open a **new** read-only transaction with the exact production driver/transaction manager/configuration.
- Execute an INSERT into a test table to which the DB account normally has write permission.
- If the DB rejects due to read-only transaction mode, verify **the DB error**, the transaction outcome, and the data after rollback.
- Also run a normal read-write test with the same credentials to distinguish an error **caused by read-only mode** from an error **caused by missing table privileges**.

**Hypothesis C — DB authorization:**

- Use the service's read-only credentials.
- Attempt an INSERT inside a **read-write transaction** or normal session.
- If the DB rejects due to permissions, verify that the authorization barrier works **independently of** the readOnly annotation.
- Check inherited roles, privileges on schemas/views/functions, and other execution paths.

### 12.1. Why Are Unit Tests with Mocks Not Enough?

Mocking `JdbcTemplate` or a repository only shows whether code called a write method. It does not verify whether the driver ignores `Connection.setReadOnly`, whether the database runs `SET TRANSACTION READ ONLY`, whether Hibernate flushes, or whether credentials have DML privileges.

For a **write-prohibition guarantee**, integration tests with the exact database engine/version are mandatory. H2 is useful as a counterexample showing **hints do not automatically block writes**, not as proof that production PostgreSQL or MySQL configurations behave identically.

### 12.2. A Required Integration Test Checklist

1. A service call **through the Spring proxy** (if using declarative transactions).
2. A **new physical** transaction, or a separate test checking when an inner method joins an outer transaction.
3. The same JDBC datasource/manager as the data you want to protect.
4. Explicit INSERT, UPDATE, and DELETE on a test table; check each type per DB.
5. Verify the thrown error and transaction state after the error; do not just check that Java code does not throw an exception.
6. After completion, open another transaction to confirm **no unintended data changes**.
7. Repeat tests for direct JDBC SQL, JPA entity updates, native queries, and stored procedures if the application uses those paths.
8. Verify actual database username/roles and driver configuration, not just `application.yml`.
9. With a production connection pool, verify readOnly/isolation state is reset properly when connections return to the pool after transactions.
10. If you suspect read-only is only a hint, run a control case with an actual read-write transaction to pinpoint the source of any error.

## 13. Common Pitfalls and Diagnostics

| Symptom | Possible Explanation | Verification / Fix |
|---|---|---|
| `@Transactional(readOnly=true)` is set yet INSERT still succeeds | Driver/database treats JDBC readOnly as a hint, e.g., H2; or annotation not applied | Check proxy, manager, datasource, DB mode, and permissions |
| Hibernate entity property changes yet DB is not updated | Flush mode/dirty-check optimization may skip auto-flush | Enable SQL logging, inspect flush mode, do not mistake for SQL enforcement |
| Native UPDATE rejected by DB inside readOnly transaction | Driver/DB is enforcing read-only transaction mode | Read SQLSTATE/error code, check DB mode and manager config |
| Inner `readOnly=true` method has no effect | `REQUIRED` joins an outer that is already read-write | Place transaction boundaries properly; understand joining; write tests |
| Inner `readOnly=false` method still cannot write | Joining the outer's read-only transaction | Do not try to "turn on write" via inner annotation; redesign the boundary |
| Spring readOnly flag is set yet connection `isReadOnly()` is false | Driver does not apply hint or reports a different state, e.g., H2 | Test real SQL, do not rely on one boolean |
| Enabling `setEnforceReadOnly(true)` causes a syntax error | DB does not support `SET TRANSACTION READ ONLY` in the manager's syntax | Check DB dialect, docs, custom config, or use permissions |
| Read-only account can still write through a function/view | Role/ownership/SECURITY DEFINER or special inherited privileges | Audit permissions across the database, not just `GRANT SELECT` on one table |
| `@Transactional(readOnly=true)` does not block Redis/email | Outside the scope of the database transaction | Separate side-effect policies, suitable outbox/roles |
| Read-only report still reads changed data between two queries | Read-only **does not** automatically change isolation/snapshot level | Choose suitable isolation, test concurrent snapshots |
| A read request saturates the pool | Read-only can still hold connections, snapshots, or locks depending on DB | Shorten transaction duration, measure pooling/slow queries |
| Test passes on H2, fails on PostgreSQL | Driver/database enforces read-only differently from H2 | Use integration tests against the production DB |
| Marked query method readOnly yet self-invocation creates no transaction | Call did not go through Spring proxy | Call bean through proxy or use `TransactionTemplate` |
| Manually toggling `setReadOnly` on a connection borrowed from the pool | Interfering with state outside transaction manager; hard to reset | Let Spring manage lifecycle and reset, do not manipulate arbitrarily |

## 14. Self-Check Questions

1. **Does `@Transactional(readOnly=true)` automatically parse every SQL statement and forbid INSERT?** — No. It is a transaction attribute/hint; enforcement depends on underlying layers.
2. **Why did the H2 demo have `springReadOnly=true` yet INSERT still succeeded?** — H2 documents that JDBC `setReadOnly(true)` ignores the parameter; Spring metadata remains true.
3. **Is Hibernate MANUAL flush mode a SELECT-only database permission?** — No. It is an ORM optimization/behavior, not a DB permission.
4. **Can a DB block INSERT even when Spring only calls `setReadOnly(true)`?** — Yes, it can. The driver may translate the hint into an actual read-only transaction; test on the specific driver.
5. **What does `setEnforceReadOnly(true)` do with DataSourceTransactionManager?** — In compatible DBs, the manager issues `SET TRANSACTION READ ONLY` when opening a new read-only physical transaction.
6. **Does enabling `setEnforceReadOnly(true)` work for all DBs/transaction managers?** — No; there are syntax and manager-type limitations.
7. **Does an inner `REQUIRED(readOnly=true)` inside an outer `REQUIRED(readOnly=false)` escalate write-blocking privileges?** — No; the inner normally joins the outer transaction.
8. **How do you ensure a query service does not write to the DB even if an annotation is forgotten?** — Use a DB credential without the required write privileges and audit privileges, combined with app guards where appropriate.
9. **Does a read-only transaction block HTTP POST or Redis SET from a Java method?** — No; those are different resources and require separate policies.
10. **Does merely observing `Connection.isReadOnly()==true` prove all write commands are blocked?** — Not yet. You need DML integration tests and verification of actual permissions/mode.

## 15. Technical Decision Summary

- **Query optimization only:** use `@Transactional(readOnly=true)`, measure with query/flush metrics; do not rely on the annotation for security control.
- **Need to reject DML within a transaction:** choose a read-only transaction mode supported by the DB; with Spring JDBC consider `setEnforceReadOnly(true)`, checking the specific driver/database.
- **Need to prevent unintended writes from a service/query actor:** use a read-only DB account with least privilege; annotations and guards are supplementary layers.
- **Need to protect all side effects of a business flow:** define business boundaries, isolate external resources, and test each execution path; a JDBC readOnly flag cannot solve everything.
- **Need correctness in Spring AOP:** verify calls go through the proxy, check propagation and whether a physical transaction is truly new; isolation/readOnly/timeout on an inner method do not automatically override an active outer transaction.

**Conclusion:** `readOnly=true` is a declaration **very valuable for semantics and performance optimization**, yet "read-only **hint**" and "**write prohibited**" are two different claims. Only call it "write-blocked" once you have clearly identified **which component rejects writes, within what scope, and have verified the error against real data/driver/database**.

## 16. References

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — Transactionality (read-only is a hint, Hibernate MANUAL flush): https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Framework — `DataSourceTransactionManager`, `setEnforceReadOnly`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `AbstractPlatformTransactionManager`, `validateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- H2 JDBC `JdbcConnection.setReadOnly` — readOnly parameter ignored: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html
- Java JDBC `Connection.setReadOnly` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html#setReadOnly(boolean)
- PostgreSQL — `SET TRANSACTION` and READ ONLY mode: https://www.postgresql.org/docs/current/sql-set-transaction.html
- PostgreSQL — Database Roles and Privileges: https://www.postgresql.org/docs/current/user-manag.html
