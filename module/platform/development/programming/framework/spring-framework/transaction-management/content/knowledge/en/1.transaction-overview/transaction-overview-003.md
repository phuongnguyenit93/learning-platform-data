# Roles of Spring, the JDBC Driver, and the DBMS in Transactions

When a method in a Spring application executes multiple SQL statements, the key question is: **who decides the transaction scope, who sends requests down to the database, and who actually enforces commit or rollback?** The answer lies across three collaborating layers: Spring manages **transaction boundaries and policies**, the JDBC driver provides **connectivity and protocol-level communication with the database**, and the database management system (DBMS) executes SQL and maintains the **actual transaction state**.

This lesson focuses on transactions with relational databases via JDBC/JPA in blocking Spring applications. Reactive models (R2DBC) and distributed transactions are introduced only to distinguish responsibilities.

## 1. A transaction seen from a business requirement

Suppose we transfer 200 units from wallet A to wallet B:

1. Subtract 200 from A's balance.
2. Add 200 to B's balance.
3. Either both changes are accepted, or both are discarded if one step fails.

If only the first statement is permanently saved, the system becomes inconsistent. Therefore, both operations must run within the **same database transaction**. A transaction creates a boundary for a unit of work, though achieving correctness also requires business validation, data constraints, and an appropriate concurrency strategy.

**Do not equate** the concept of a transaction with the `@Transactional` annotation: the annotation is Spring's declarative way of expressing intent; an actual transaction involves resources and commit/rollback operations inside the database system.

## 2. Responsibility map: what does each layer do?

| Component | Primary responsibility | Not responsible for other layers |
| --- | --- | --- |
| Service / business logic | Chooses the unit of work, operation order, validation conditions, and error handling | Does not create ACID guarantees through Java code alone |
| Spring Transaction Infrastructure | Defines transaction boundary, propagation, isolation, timeout, rollback rules; acquires/binds resources and requests commit/rollback | Does not directly write WAL records, hold DB locks, or execute the SQL engine |
| DataSource and connection pool | Provides, manages the lifecycle of, and reuses JDBC Connections | A pool is not a transaction coordinator; one Connection does not automatically span multiple DBs |
| JDBC API and JDBC driver | Maps Java calls such as prepare/execute/commit/rollback to DBMS connections/protocols and translates results/errors back to Java | Driver does not decide `@Transactional` rollback rules or guarantee ACID on behalf of the DBMS |
| DBMS and storage engine | Executes SQL, enforces constraints, manages locks/MVCC, logging, isolation, commit, and rollback | DBMS does not automatically know Spring-layer business boundaries or undo sent emails/HTTP calls |
| JPA provider, if used | Manages EntityManager/persistence context, dirty checking, and translates object changes into SQL | `flush` does not mean `commit`; JPA still relies on the underlying transaction and DBMS |

Conceptually:

~~~text
HTTP/CLI/scheduler
       |
       v
Spring-managed Service
       |
       v
Spring proxy / TransactionInterceptor
       |
       v
PlatformTransactionManager ---- DataSource / pool
                                   |
                                   v
                             JDBC Connection
                                   |
                              JDBC driver
                                   |
                                   v
                         DBMS: SQL, locks, log,
                         constraints, commit/rollback
~~~

**Distinguish the two paths:** transaction control (begin/commit/rollback) is coordinated by Spring through the transaction manager; CRUD statements are executed by `JdbcTemplate`, plain JDBC, or the JPA provider on the resource bound to that transaction. Both paths must use the exact same resource to participate in a single transaction.

## 3. Spring: manages boundaries, does not replace the database

### 3.1. Abstraction and transaction manager

Spring provides the `PlatformTransactionManager` interface for imperative transactions. Its three core operations are:

~~~java
// API signature excerpt for illustration; not a standalone program.
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

`TransactionDefinition` describes the policy (propagation, isolation, timeout, read-only); `TransactionStatus` reflects transaction state. Depending on the environment, the transaction manager uses different underlying mechanisms:

- **JdbcTransactionManager / DataSourceTransactionManager:** manages a JDBC `DataSource` and JDBC `Connection`, suitable for local JDBC access. `JdbcTransactionManager` adds translation of transaction errors into Spring's data access exception hierarchy.
- **JpaTransactionManager:** integrates JPA transactions through `EntityManager` and the JPA provider; with proper configuration, it can also coordinate JDBC access using the same `DataSource`.
- **JtaTransactionManager:** coordinates with JTA infrastructure when transactional resources capable of participating in global transactions are required; it does not turn arbitrary drivers/DBs or external APIs into XA resources.
- **ReactiveTransactionManager:** used for reactive models such as R2DBC with a context propagation mechanism different from blocking JDBC.

The transaction manager must match the data access technology and resources. Placing `@Transactional` on a service while configuring the wrong manager, using a different `DataSource`, or obtaining a `Connection` outside managed scope can all produce unexpected transaction behavior.

### 3.2. `@Transactional` works through Spring-intercepted calls

In common proxy mode, when external code calls a Spring bean method **through the proxy**, `TransactionInterceptor` reads the `@Transactional` metadata, asks the transaction manager to join or open a transaction according to propagation, invokes the business method, and decides commit/rollback when the method finishes.

~~~java
// Illustrative code in a Spring application with transaction management enabled.
@Service
public class TransferService {
    private final WalletRepository repository;

    public TransferService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        repository.debit(from, amount);
        repository.credit(to, amount);
    }
}
~~~

The snippet above illustrates a **service-level boundary**; it is not a standalone program because it requires a repository, `DataSource`, transaction manager, and Spring configuration. The annotation itself is only metadata: it requires a Spring-managed bean and enabled transaction management (such as `@EnableTransactionManagement` or corresponding Spring Boot auto-configuration).

Common defaults of Spring `@Transactional` are `PROPAGATION_REQUIRED`, `ISOLATION_DEFAULT`, and `readOnly=false`. By default, `RuntimeException` and `Error` cause Spring to roll back, whereas checked `Exception`s do not automatically roll back unless `rollbackFor` or a custom default rollback policy is configured. This rule determines when **Spring requests a rollback upon an escaping exception**; it does not replace DBMS rollback.

**Self-invocation trap:** calling `this.anotherTransactionalMethod()` from another method of the same object normally bypasses the proxy, so the annotation on the called method does not activate a new transaction boundary in proxy mode. Extracting to a separate Spring bean invoked through its proxy or redesigning the transaction boundary is the usual solution.

### 3.3. How are resources bound to a transaction?

With imperative JDBC, `DataSourceTransactionManager`/`JdbcTransactionManager` obtains a JDBC `Connection` from the `DataSource`, configures the necessary state, and binds a `ConnectionHolder` to the current thread's transaction context. `JdbcTemplate` uses `DataSourceUtils` to obtain that exact bound `Connection`; thus, statements within the same transaction can share the same connection.

Upon completion, Spring invokes commit/rollback, restores required connection state, unbinds the resource from the thread, and returns the connection to the pool or closes it according to the `DataSource`. **Closing a pool's logical connection does not mean closing the physical socket.** Drivers and pools may perform additional cleanup depending on implementation.

Never casually call `DriverManager.getConnection(...)` inside a `@Transactional` method and expect the new `Connection` to join the active transaction. Calling `DataSource.getConnection()` directly from custom code can also obtain a separate connection; when low-level JDBC needs to participate in a Spring transaction, use `DataSourceUtils` or Spring's transaction-aware APIs.

## 4. JDBC driver: the bridge between Java and the DBMS

JDBC is Java's standard API contract; a driver is the concrete implementation for PostgreSQL, MySQL, Oracle, H2, SQL Server, etc. The driver performs tasks such as:

1. Opening physical connections, authenticating, and communicating with the server via the corresponding protocol.
2. Sending SQL statements and `PreparedStatement` parameters, and receiving result sets, update counts, or errors.
3. Mapping Java/JDBC data types to DB types and translating server errors into `SQLException` with useful error codes/SQLStates.
4. Translating `Connection.setAutoCommit(false)`, `commit()`, `rollback()`, and `setTransactionIsolation(...)` calls into operations supported by the DBMS/driver.

Drivers may perform buffering, batching, protocol selection, and other optimizations, but they are **not the data storage engine**. A driver reports commit success based on the server response received; durability, locking, and actual rollback are determined by the DBMS and its configuration.

**`DataSource` does not equal driver:** `DataSource` is an abstraction providing JDBC `Connection`s; in production it typically fronts a connection pool like HikariCP, while the pool uses the driver. Spring's `DriverManagerDataSource` is suitable for demos/tests because each request may open a new physical connection; it is not a production connection pool.

**Autocommit:** a new JDBC `Connection` typically operates with `autoCommit=true` by JDBC default, meaning each individual SQL statement is committed according to DB rules. To group multiple statements into a standard JDBC transaction, `autoCommit=false` must be managed explicitly or via a transaction manager. Some DBs have specific transaction/DDL semantics and autocommit behavior; do not assume every SQL statement can be rolled back on every engine.

## 5. DBMS: where the transaction is actually executed

Upon receiving SQL, the DBMS validates syntax/permissions, plans execution, reads/writes data, and enforces constraints. Within a transaction, the engine uses mechanisms such as locks, MVCC, undo/redo logs, or write-ahead logging depending on the product to support:

- **Atomicity:** changes in a transaction succeed together or are rolled back according to engine capabilities.
- **Consistency:** state transitions from valid to valid when constraints and business logic are sound. The DBMS enforces `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK`, etc., though it cannot know every business invariant.
- **Isolation:** governs how concurrent transactions observe or affect each other; supported isolation levels and prevented anomalies vary by DBMS.
- **Durability:** committed data is retained according to the DBMS's durability guarantees and storage configuration.

Commit is the point instructing the DBMS to finalize the transaction. Rollback instructs the DBMS to discard uncommitted changes belonging to that transaction. Spring coordinates **when to call**; the DBMS decides **how to execute**. Never claim that Spring itself locks tables, writes WAL records, or directly guarantees ACID.

A transaction can fail even when Java throws no business error: `UNIQUE`/`CHECK` violations, deadlocks, serialization failures, connection drops, timeouts, resource exhaustion, etc. The DBMS detects and returns errors through the driver; Spring JDBC can translate `SQLException` into `DataAccessException`. For errors occurring during commit, the outcome sometimes needs verification before retrying, especially when the connection drops during acknowledgment.

## 6. Timeline: a money transfer request

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring TX proxy
    participant TM as TransactionManager
    participant JDBC as JDBC driver/Connection
    participant DB as DBMS
    Caller->>Proxy: transfer(A, B, 200)
    Proxy->>TM: getTransaction(REQUIRED)
    TM->>JDBC: acquire Connection, configure transaction
    JDBC->>DB: begin work in transaction
    Proxy->>JDBC: UPDATE wallet A (via JDBC/JPA)
    JDBC->>DB: debit SQL
    DB-->>JDBC: result
    Proxy->>JDBC: UPDATE wallet B (via JDBC/JPA)
    JDBC->>DB: credit SQL
    DB-->>JDBC: result
    alt No rollback-triggering error
        Proxy->>TM: commit
        TM->>JDBC: Connection.commit()
        JDBC->>DB: request COMMIT
    else Rollback-triggering error
        Proxy->>TM: rollback
        TM->>JDBC: Connection.rollback()
        JDBC->>DB: request ROLLBACK
    end
    TM-->>Proxy: release resources
    Proxy-->>Caller: result or exception
~~~

The diagram illustrates **logical semantics**, not a claim that every driver sends an explicit `BEGIN` statement at that exact moment: some DBs begin a transaction upon executing the first SQL statement after disabling autocommit. If `PROPAGATION_REQUIRED` joins an existing transaction, the final commit point belongs to the outer transaction boundary, not necessarily the inner called method.

For example, an error may occur on the second `UPDATE` statement. If both statements go through the exact same transaction and the DBMS supports rollback for that operation, rollback restores balances to their initial state. If the first `UPDATE` ran through an independent autocommit connection, Spring cannot undo that already-committed change.

## 7. Runnable practice: observing rollback and commit

This example uses **Java 17+, Maven, Spring JDBC 6.2.12, and H2 2.3.232** to demonstrate the three layers above. H2 runs in memory, requiring no external server. `DriverManagerDataSource` is for learning only; production systems should configure an appropriate pooled `DataSource`.

Directory structure:

~~~text
transaction-roles-demo/
├── pom.xml
└── src/main/java/demo/TransactionRolesDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-roles-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <configuration>
                    <mainClass>demo.TransactionRolesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TransactionRolesDemo.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionRolesDemo {
    private TransactionRolesDemo() {}

    private static int balance(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?",
                Integer.class, id);
        if (value == null) {
            throw new IllegalStateException("Wallet not found: " + id);
        }
        return value;
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:role_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE wallet (" +
                "id INT PRIMARY KEY, " +
                "balance INT NOT NULL CHECK (balance >= 0))");
        jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 1, 1000);
        jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 2, 500);

        TransactionTemplate tx = new TransactionTemplate(
                new JdbcTransactionManager(dataSource));

        try {
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE wallet SET balance = balance - 200 WHERE id = ?", 1);
                jdbc.update("UPDATE wallet SET balance = balance + 200 WHERE id = ?", 2);
                throw new IllegalStateException("demo rollback");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback: " + expected.getMessage());
        }

        System.out.printf("After rollback: A=%d, B=%d%n",
                balance(jdbc, 1), balance(jdbc, 2));

        tx.executeWithoutResult(status -> {
            jdbc.update("UPDATE wallet SET balance = balance - 200 WHERE id = ?", 1);
            jdbc.update("UPDATE wallet SET balance = balance + 200 WHERE id = ?", 2);
        });

        System.out.printf("After commit: A=%d, B=%d%n",
                balance(jdbc, 1), balance(jdbc, 2));
    }
}
~~~

From the `transaction-roles-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Stdout of the Java program** (excluding Maven or environment logs):

~~~text
Rollback: demo rollback
After rollback: A=1000, B=500
After commit: A=800, B=700
~~~

**Exact explanation of what happens:**

1. `JdbcTemplate` creates the table and two initial rows before opening the demo transactions; those setup statements are independent of the two transactions below.
2. `TransactionTemplate` asks `JdbcTransactionManager` to open a transaction on the `DataSource`. Spring holds the appropriate connection in the transaction context.
3. `JdbcTemplate` retrieves that connection via Spring integration; the H2 driver sends both `UPDATE`s to the H2 DBMS.
4. The `RuntimeException` in the first lambda causes the transaction manager to roll back. H2 discards the two uncommitted changes, so the balances remain 1000 and 500.
5. The second lambda finishes normally; the transaction manager commits, H2 persists both changes, and the balances become 800 and 700.

If you replace the `JdbcTemplate` calls inside the lambda with a manually opened JDBC connection outside Spring's transaction with `autocommit=true`, the outcome can differ. Test this change only in a demo environment to observe the design flaw; never apply it to real systems.

In applications using `@Transactional`, the interceptor handles coordination before/after the method in place of `TransactionTemplate`; the roles of the driver and DBMS remain essentially the same.

## 8. Transaction attributes: who decides, who enforces?

| Attribute | Spring decides | DBMS/driver enforces or constrains |
| --- | --- | --- |
| Transaction boundary | Opens/joins/ends based on propagation and proxy or template calls | Connection and DBMS execute the physical transaction |
| Rollback rules | Which exceptions mark rollback; allows calling `setRollbackOnly()` | DBMS discards changes belonging to the uncommitted transaction |
| Propagation | `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `NESTED`, etc. determine call relationships | `REQUIRES_NEW` typically needs an independent transaction/connection; `NESTED` depends on savepoint and manager support |
| Isolation | Sends the requested isolation level via the transaction definition | Capabilities and semantics of `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, etc. depend on the DBMS |
| Timeout | Sets timeout / propagates to queries if supported by APIs | Driver, statement, and DBMS determine how work is actually interrupted or aborted |
| `readOnly` | Expresses read intent, enables optimizations, and may pass hints down to JDBC | Should not be treated as a strict security/write-prevention barrier across all DBMSs |
| Commit/rollback | Final request based on transaction status and policy | DBMS executes, writes logs, holds/releases locks, and confirms the result |

**Propagation is not isolation.** Propagation answers "how does this call's transaction relate to an existing transaction?"; isolation answers "to what extent can concurrent transactions observe one another?". A `@Transactional` method does not automatically eliminate lost updates, write skew, or all race conditions; you still need properly designed SQL, locks, optimistic locking versions, isolation, and retries.

**Connection granularity:** a local JDBC transaction is tied to a specific connection. Two `DataSource`s pointing to two different DBs do not become one atomic transaction simply by sharing a single annotation. Coordinating multiple resources requires an appropriate mechanism (such as JTA/XA where supported) or an eventual-consistency design like outbox/saga depending on business requirements.

## 9. Common misconceptions and how to verify

### Misconception 1: "Having `@Transactional` means the database automatically rolls back everything"

Incorrect. Spring must actually intercept the call, have a transaction manager, and the operations must participate in the right resource. Catching and swallowing an exception in the service without marking rollback-only can cause Spring to commit. By default, checked `Exception`s may not trigger automatic rollback either; inspect `rollbackFor` and the configured policy.

### Misconception 2: "The driver provides ACID"

The driver is a communication bridge; actual transactions and constraints live in the DBMS/storage engine. Isolation behavior, locking, DDL handling, and durability differ across database engines and configurations.

### Misconception 3: "Two repositories called in one method share the same transaction"

Only true when the repositories use resources coordinated by the active manager. If one repository uses a different `DataSource` or opens its own autocommit connection, the changes may not share a transaction. With JPA, verify the corresponding `EntityManager`/transaction manager and `DataSource`.

### Misconception 4: "JPA `flush()` is the same as `commit()`"

`flush()` pushes pending changes as SQL for the DBMS to process inside the transaction; the transaction can still roll back. Only `commit()` completes the transaction successfully. Conversely, constraint violations can surface at flush or commit depending on the provider and execution path.

### Misconception 5: "Database rollback undoes emails, HTTP calls, and messages"

An ordinary external service call, email send, or message publish does not automatically participate in a local JDBC transaction. When consistency between the database and event emission is needed, consider transactional outbox, idempotent consumers, or an explicitly designed distributed architecture.

### Misconception 6: "`REQUIRES_NEW` is free, and `readOnly` strictly forbids writes"

`REQUIRES_NEW` may require an additional connection while the outer transaction is still holding resources, impacting the pool and risking connection starvation. `readOnly` is primarily a hint/optimization unless the stack/DBMS provides an explicit enforcement mechanism.

### Misconception 7: "If commit reports an error, no record was saved"

A network drop at commit time can leave the client uncertain whether the DBMS committed or not. Query status, use business keys/idempotency keys, and design proper retries instead of blindly re-sending operations.

## 10. Layer-by-layer diagnostic checklist

When troubleshooting "the transaction did not roll back", ask questions in order:

1. **Spring boundary:** Was the method invoked through a proxy/`TransactionTemplate`? Is transaction management enabled? Does the exception type match rollback rules? Did any code catch and return normally?
2. **Transaction manager and resources:** Are the manager and `DataSource` correct? Do `JdbcTemplate`/JPA providers acquire the resource participating in the transaction? Is there a manually opened connection or `@Async`/new thread losing context?
3. **JDBC/driver:** What is the connection's autocommit state? Was SQL sent? Are there SQLState errors, timeouts, socket drops, or pool issues? Does the driver support the requested isolation/savepoint features?
4. **DBMS:** Does the statement target a transactional table/engine? Are there DDL implicit commits, triggers, constraints, deadlocks, or engine-specific isolation settings? Did the DB actually commit or roll back?
5. **System scope:** Beyond the DB, are message brokers, HTTP calls, files, or multiple DBs involved? If so, identify the explicit coordination or compensation mechanism.

To verify in an integration test, seed initial data, perform two operations in one transaction, intentionally fail on the second operation, and then **read back from an independent connection/transaction after the method finishes** to confirm both changes were rolled back. Then run the success case and verify the committed result. This proves actual DBMS behavior far better than merely asserting that an exception was thrown.

## 11. Self-check

**Scenario A.** A `@Transactional` service calls repository A using `JdbcTemplate` and repository B, which manually calls `DriverManager.getConnection(...)` to `UPDATE` the same database. Will repository B reliably roll back together with A?  
**Answer:** No. B's manually created connection may sit outside the Spring-managed transaction, even if it targets the same DB using the same driver.

**Scenario B.** The second `UPDATE` violates a `CHECK` constraint and the driver reports a `SQLException`. Who detects the error, who decides to roll back, and who discards the data?  
**Answer:** The DBMS detects the violation; the driver translates the error to Java; Spring (depending on the transaction manager and rollback rules) requests rollback; the DBMS executes the transaction rollback.

**Scenario C.** Inside a JPA transaction, `flush()` succeeds and then the service throws a `RuntimeException`. Is the data guaranteed to be committed?  
**Answer:** No. `flush` may have sent SQL, but the transaction can still be rolled back when the exception escapes under default policy.

**Scenario D.** There are two independent DBs and a single `@Transactional` on a service. Does Spring automatically guarantee an atomic commit across both?  
**Answer:** No. A local transaction manager does not automatically coordinate two resources. An appropriate architecture/transaction coordinator is required.

## 12. Core takeaways

- **Spring = the coordinator:** defines transaction boundaries and policies, binds resources, and requests commit/rollback.
- **JDBC driver = the technical bridge:** implements the JDBC contract over the DBMS protocol, sends SQL and operates on `Connection`, and returns results/errors.
- **DBMS = where the transaction executes:** reads/writes data, enforces constraints and isolation, and performs commit/rollback.
- **A correct business boundary alone is not enough:** all SQL must participate in the right resources; concurrency, non-DB side effects, and error handling must still be designed.

## References

- [Spring Framework: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring: Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring: Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Java SE 17: java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
