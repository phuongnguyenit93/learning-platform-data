# Observing Begin, Commit, Rollback, and Connection Release Logs in Spring

A method annotated with **@Transactional** running without errors is not enough to prove data committed properly. When learning your first transaction in Spring, you need to see **when a transaction is created or joined, whether it ends with commit or rollback, and where the JDBC Connection is returned**. Combining Spring logs with re-reading data from the database helps distinguish the behavior of the transaction manager, JDBC driver, DBMS, and connection pool.

Lesson objectives:

- Enable the right loggers to see the JDBC transaction lifecycle in Spring.
- Read the signs of **begin -> SQL execution -> commit/rollback -> cleanup/release** without confusing log messages with durable DB results.
- Run both a success scenario and an intentional error scenario with Java 17+, Spring JDBC, H2, and a connection pool.
- Understand why **releasing a connection does not necessarily mean closing the physical connection**, and how to recognize leaks or long-running transactions.
- Handle commonly misunderstood cases: methods bypassing the proxy, transactions joining an outer transaction, caught exceptions, checked exceptions, and connections outside Spring's scope.

The primary scope is **imperative JDBC transactions** coordinated by JdbcTransactionManager/DataSourceTransactionManager. When using JPA/JTA or R2DBC, the phase concepts are similar, though specific loggers and resources may differ.

## 1. What Actually Happens Behind a @Transactional Call?

For example, a service transfers 10 units from A to B. When two UPDATEs belong to one JDBC transaction, the system expects:

- No error: the DBMS accepts **both** changes at commit.
- Rollback-triggering error: the DBMS cancels **both** uncommitted changes.
- Whether commit or rollback, Spring **cleans up the transaction context and releases borrowed resources**.

Typical path:

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring TransactionInterceptor
    participant TM as JdbcTransactionManager
    participant Pool as DataSource / Connection Pool
    participant DB as JDBC Driver / DBMS
    Caller->>Proxy: Call service method
    Proxy->>TM: getTransaction(definition)
    TM->>Pool: Acquire JDBC Connection
    Pool-->>TM: Connection
    TM->>TM: Bind Connection to transaction context
    TM->>DB: Configure Connection (usually autoCommit=false)
    Proxy->>DB: Execute SQL via JdbcTemplate
    alt Success
        Proxy->>TM: commit
        TM->>DB: Connection.commit()
    else Error requiring rollback
        Proxy->>TM: rollback
        TM->>DB: Connection.rollback()
    end
    TM->>TM: Restore and clear transaction binding
    TM->>Pool: release Connection
    Pool-->>TM: Return to pool or close per DataSource
    Proxy-->>Caller: Result / exception
~~~

The diagram depicts **the logic of a newly opened local JDBC transaction**. It does not claim every driver sends an explicit SQL BEGIN command. With many JDBC drivers/DBMSs, Spring switches the connection to **autoCommit=false**, and the DBMS starts the actual transaction per its own rules when an operation executes.

Specifically, **@Transactional does not control the JDBC Connection directly**. TransactionInterceptor asks the TransactionManager; the manager coordinates with the DataSource; the JDBC driver talks to the DBMS. If a method only joins an existing transaction (PROPAGATION_REQUIRED), that method normally **does not create or end a new physical transaction**.

## 2. Enabling Logs in the Right Places

Spring does not necessarily log transactions at INFO. With Spring Boot using JDBC, start with DEBUG on narrow packages, and raise TRACE on the interceptor when you truly need to trace calls.

**application.yml** in a Spring Boot application:

~~~yaml
logging:
  level:
    org.springframework.transaction.interceptor: TRACE
    org.springframework.jdbc.support: DEBUG
    org.springframework.jdbc.datasource: DEBUG
    com.zaxxer.hikari: INFO
~~~

Equivalent in **application.properties**:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=INFO
~~~

Do not configure both files; pick the configuration format used by your application. For **DataSourceTransactionManager**, the logger is usually in **org.springframework.jdbc.datasource**; for **JdbcTransactionManager**, the subclass logger is in **org.springframework.jdbc.support**. Enabling both helps trace when you are unsure which manager is active. **org.springframework.transaction.interceptor** shows transaction advice around method calls.

If using **JpaTransactionManager**, also enable **org.springframework.orm.jpa** at DEBUG; with Hibernate you can add SQL/flush logs as needed. For R2DBC, use the corresponding Spring R2DBC and driver loggers, and do not expect the JDBC wording shown below. JDBC logs also do not guarantee every statement is printed: transaction manager loggers mainly record **transaction lifecycle**, not every SQL query or bind value.

When running a Java application without Spring Boot, settings in application.yml alone will not be read automatically. The standalone example in section 5 configures **SLF4J SimpleLogger via Java system properties** so Boot is not required.

**Considerations in real environments:** DEBUG/TRACE under heavy traffic generates large log volumes. Enable only temporarily in permitted environments; avoid logging SQL parameter values, identifiers, tokens, and sensitive data. When using Logback, Log4j2, or another logging framework, configure it accordingly instead of SimpleLogger.

## 3. Log Reading Table: What Does Each Line Prove?

| Common log signature | Component | Primary meaning | What you must NOT conclude from that line alone |
| --- | --- | --- | --- |
| **Creating new transaction with name [...]** | TransactionManager | Spring decides to open a new transaction | That DBMS logged SQL BEGIN or already committed |
| **Acquired Connection [...] for JDBC transaction** | DataSourceTransactionManager/JdbcTransactionManager | A JDBC Connection was obtained for the transaction | That a brand-new physical socket was created |
| **Switching JDBC Connection [...] to manual commit** | JDBC transaction manager | Manager requested disabling autocommit | That DBMS already started executing SQL |
| **Getting transaction for [...]** | TransactionInterceptor at TRACE | Advice is managing the intercepted call | That new resources were allocated if a transaction already existed |
| **Participating in existing transaction** | TransactionManager | Call joins the current transaction | That the inner method will commit on its own when returning |
| **Initiating transaction commit** | TransactionManager | Spring enters the commit process | That commit definitely succeeded |
| **Committing JDBC transaction on Connection [...]** | JDBC transaction manager | Spring is about to call or calling Connection.commit() | That DBMS confirmed success if a subsequent log shows an error |
| **Initiating transaction rollback** | TransactionManager | Spring begins the rollback branch | That all non-DB side effects were undone |
| **Rolling back JDBC transaction on Connection [...]** | JDBC transaction manager | Spring requested Connection.rollback() | That data on other connections was also rolled back |
| **Releasing JDBC Connection [...] after transaction** | JDBC transaction manager | Cleanup is releasing the connection held by the manager | That the physical connection was closed |
| **Returning JDBC Connection to DataSource** | DataSourceUtils, depending on log config | Spring completes handing back the connection | That the pool reduced its physical connection count |
| **HikariPool ... Shutdown completed** | HikariCP | The entire pool is closing/closed | That this log appears after every normal transaction |

Wording, categories, and log levels can vary by **Spring version, transaction manager, logging framework, and DataSource**. The signatures in the table are patterns to recognize, not a requirement that every run prints every single line. For method names, connection IDs, threads, timestamps, or interleaving across loggers, verify against actual output.

**Most common misconception:** the word **begin** in a business question does not mean you must see literal **BEGIN TRANSACTION** text. In local JDBC transactions, meaningful indicators are usually **Creating new transaction**, **Acquired Connection**, and **Switching ... to manual commit**.

## 4. Separating Transaction Control Phases from SQL Execution

### Phase 1: Opening a Transaction

For a new JDBC transaction, Spring reads @Transactional metadata, picks the transaction manager, obtains a connection from the DataSource, prepares isolation/read-only if needed, switches autoCommit when appropriate, and binds the resource to the current thread's context.

- The manager may skip calling setAutoCommit(false) if the connection already has autoCommit=false.
- **LazyConnectionDataSourceProxy** can defer acquiring a physical connection until the first SQL statement; a transaction executing no SQL might not need to borrow a real connection.
- A transaction created by the transaction manager does not necessarily correspond to a visible BEGIN SQL statement in SQL logs.

### Phase 2: Running Business Code and SQL

JdbcTemplate uses the **DataSourceUtils** mechanism to obtain the exact connection bound to the transaction. Multiple JDBC operations in the same transaction use the same appropriate resource. If you manually call DriverManager.getConnection(...) or use another DataSource, that separate connection may not join the service's transaction.

### Phase 3A: Commit

When a method finishes normally without being marked rollback-only, advice asks the manager to commit at the transaction-owning boundary. The manager calls **Connection.commit()**, and the driver sends the request to the DBMS; the DBMS validates, persists changes, and responds. Because errors can occur during commit, **an "Initiating transaction commit" log does not by itself prove commit succeeded**.

### Phase 3B: Rollback

When an exception matching rollback rules escapes the boundary, or the transaction is already rollback-only, advice requests rollback. The manager calls **Connection.rollback()**, and the DBMS cancels uncommitted changes belonging to that transaction. Other transactions or an already-sent external HTTP request/email do not roll back automatically.

### Phase 4: Cleanup and Release

After finishing, the manager restores connection states it changed when necessary, unbinds from the thread, completes transaction synchronizations, and releases the connection. With pools like HikariCP, **close() on the wrapper** normally means **returning the logical connection to the pool**, where the physical connection can continue to be reused.

**Releasing after commit and releasing after rollback are both normal.** Never classify a transaction as succeeded or failed solely from the release line. Check the preceding commit/rollback lines and re-read DB state.

## 5. Running a Java 17+ App Observing Both Commit and Rollback

The following example uses **Spring Framework 6.2.12, H2 2.3.232, HikariCP 5.1.0, and SLF4J Simple 2.0.17**. It creates a real Spring application context, enables transaction proxies, calls a service via a Spring bean, runs one successful transaction, and runs one transaction intentionally throwing a RuntimeException. Data is checked after each case.

**Structure:**

~~~text
tx-log-demo/
├── pom.xml
└── src/main/java/demo/TxLogDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-log-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
            <version>2.0.17</version>
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
                    <mainClass>demo.TxLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TxLogDemo.java:**

~~~java
package demo;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class TxLogDemo {
    private TxLogDemo() {}

    public static void main(String[] args) {
        // Must be set before application loggers are initialized.
        System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", "warn");
        System.setProperty("org.slf4j.simpleLogger.showDateTime", "false");
        System.setProperty("org.slf4j.simpleLogger.showThreadName", "true");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.jdbc.support",
                "debug");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.jdbc.datasource",
                "debug");
        System.setProperty(
                "org.slf4j.simpleLogger.log.org.springframework.transaction.interceptor",
                "trace");

        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            DataSource dataSource = context.getBean(DataSource.class);
            TransferService service = context.getBean(TransferService.class);

            jdbc.execute("CREATE TABLE account (" +
                    "id INT PRIMARY KEY, balance INT NOT NULL CHECK (balance >= 0))");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 100);
            printBalances(jdbc, "INITIAL");

            System.out.println("=== COMMIT ===");
            service.successfulTransfer(); // Call through Spring proxy
            printBalances(jdbc, "AFTER COMMIT");
            System.out.println("after commit: resourceBound=" +
                    TransactionSynchronizationManager.hasResource(dataSource));

            System.out.println("=== ROLLBACK ===");
            try {
                service.failedTransfer();  // Call through Spring proxy
            } catch (IllegalStateException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
            printBalances(jdbc, "AFTER ROLLBACK");
            System.out.println("after rollback: resourceBound=" +
                    TransactionSynchronizationManager.hasResource(dataSource));
        }
        // context.close() closes HikariDataSource/pool at program end.
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?", Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?", Integer.class, 2);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean(destroyMethod = "close")
        public HikariDataSource dataSource() {
            HikariConfig config = new HikariConfig();
            config.setJdbcUrl("jdbc:h2:mem:tx_log_demo;DB_CLOSE_DELAY=-1");
            config.setUsername("sa");
            config.setPassword("");
            config.setPoolName("tx-log-pool");
            config.setMinimumIdle(1);
            config.setMaximumPoolSize(3);
            return new HikariDataSource(config);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbcTemplate) {
            return new TransferService(jdbcTemplate);
        }
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void successfulTransfer() {
            System.out.println("inside commit: active=" +
                    TransactionSynchronizationManager.isActualTransactionActive());
            jdbc.update(
                    "UPDATE account SET balance = balance - 10 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 10 WHERE id = 2");
        }

        @Transactional
        public void failedTransfer() {
            System.out.println("inside rollback: active=" +
                    TransactionSynchronizationManager.isActualTransactionActive());
            jdbc.update(
                    "UPDATE account SET balance = balance - 20 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 20 WHERE id = 2");
            throw new IllegalStateException("simulated error");
        }
    }
}
~~~

**Points to verify in the code:**

1. **@EnableTransactionManagement(proxyTargetClass = true)** enables the interceptor and forces class-based proxies, ensuring calls retrieving the TransferService bean by class type are intercepted. TransferService has public, non-final methods.
2. **transactionManager** is a JdbcTransactionManager bean using **the exact HikariDataSource** used by JdbcTemplate.
3. **@Transactional** on both methods executes via the Spring proxy, without internal this.method() calls.
4. **TransactionSynchronizationManager.isActualTransactionActive()** observes the context inside the method.
5. **TransactionSynchronizationManager.hasResource(dataSource)** checks whether a resource remains bound to the thread **after** the transactional method ends. A value of false does not mean the pool has closed.
6. **IllegalStateException** is a RuntimeException: by default Spring requests rollback when this exception escapes a transactional method.
7. Both UPDATEs use the same transaction-bound resource. H2 performs commit/rollback; Spring only coordinates when to call via the driver.

**Test run** on a machine with JDK 17+ and Maven:

~~~bash
cd tx-log-demo
mvn -q compile exec:java
~~~

**Lines intentionally printed by the program's System.out.println/printf** (excluding DEBUG/TRACE emitted by loggers or Maven's own output):

~~~text
INITIAL: A=100, B=100
=== COMMIT ===
inside commit: active=true
AFTER COMMIT: A=90, B=110
after commit: resourceBound=false
=== ROLLBACK ===
inside rollback: active=true
caught: simulated error
AFTER ROLLBACK: A=90, B=110
after rollback: resourceBound=false
~~~

SLF4J SimpleLogger by default may print DEBUG/TRACE to **stderr**, so the terminal displays them interleaved with stdout. Do not use interleaving order between the two streams as absolute ordering proof; read **logger names, thread names, and transaction milestones**.

Note: the dependency set and example target Java 17+/Spring 6.2; for projects with Spring Boot, prefer dependency versions managed by Boot's BOM rather than hardcoding versions from the example.

## 6. Interpreting Actual Logs Phase by Phase

The section below shows **sample observable DEBUG/TRACE lines**, omitting timestamps, thread names, connection hashes/IDs, and non-decisive lines. Exact log contents depend on version and configuration.

### 6.1. Commit Case

~~~text
Creating new transaction with name [demo.TxLogDemo$TransferService.successfulTransfer]
Acquired Connection [...] for JDBC transaction
Switching JDBC Connection [...] to manual commit
Getting transaction for [demo.TxLogDemo$TransferService.successfulTransfer]
... application executes UPDATE A and UPDATE B ...
Completing transaction for [demo.TxLogDemo$TransferService.successfulTransfer]
Initiating transaction commit
Committing JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

**How to read it:**

- **Creating new transaction:** Spring is opening a local physical transaction because the service is the transactional entry point.
- **Acquired Connection:** the manager borrowed a JDBC Connection from HikariDataSource.
- **manual commit:** Spring switches to boundary-controlled commits instead of auto-committing each statement. This is the **common mechanism**, not proof that SQL BEGIN was sent.
- **Getting transaction / Completing transaction:** method interception trace. These lines do not replace DBMS logs.
- **Initiating commit / Committing JDBC transaction:** Spring instructs the driver to execute commit. If commit reports an error, investigate actual DB state—never claim success from the "Initiating" line alone.
- **Releasing JDBC Connection:** Spring releases the connection it borrowed. HikariCP may keep the **physical connection** open to serve the next request.

The business result **AFTER COMMIT: A=90, B=110** is re-read from JdbcTemplate after the method completes; this is better evidence than merely seeing the word "commit" in logs.

### 6.2. Rollback Case

~~~text
Creating new transaction with name [demo.TxLogDemo$TransferService.failedTransfer]
Acquired Connection [...] for JDBC transaction
Switching JDBC Connection [...] to manual commit
Getting transaction for [demo.TxLogDemo$TransferService.failedTransfer]
... application executes UPDATE A and UPDATE B ...
Completing transaction for [...] after exception: java.lang.IllegalStateException
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

The failedTransfer() method ran both UPDATEs and then threw RuntimeException. The proxy saw the exception escape the method and chose rollback per default rules. H2 canceled both uncommitted updates; the result **AFTER ROLLBACK: A=90, B=110** equals the state before failedTransfer().

**Do not infer "success" just because you saw both UPDATEs.** Both statements may have executed successfully inside the transaction yet were rolled back afterward.

### 6.3. Why Might You See "begin" Without Immediate Rollback or Commit?

If **REQUIRED** propagation joins an already-existing transaction, the log may say **Participating in existing transaction**. When the inner method finishes, the inner logical scope ends, yet the **physical transaction** only commits/rolls back at the outer method boundary. Counting @Transactional calls and comparing against physical COMMIT counts often yields different numbers.

When using **REQUIRES_NEW**, the manager temporarily suspends the outer transaction and opens a new transaction; logs show an independent commit/rollback branch followed by resuming the outer resource. When using **NESTED** via supported savepoints, logs and behavior differ from REQUIRES_NEW: rolling back a branch to a savepoint still belongs to the outer physical transaction.

## 7. What Does Releasing a JDBC Connection Mean?

This is the core takeaway when reading transaction-end logs.

| Event | Meaning |
| --- | --- |
| Spring **unbinds** resource | ConnectionHolder is no longer attached to the current thread/transaction context |
| Spring **resets** connection state | Restores states changed when opening the transaction, such as autocommit, isolation, read-only when applicable |
| Spring calls **DataSourceUtils.releaseConnection** | Hands back the connection acquired by the manager |
| Hikari proxy connection **close()** | Returns the logical lease to the pool; does not necessarily close the socket/physical connection |
| Pool actively closes physical connection | Occurs when the connection reaches max lifetime, fails validation, is evicted, or the pool shuts down per policy |
| DBMS closes session | Server-level event, cannot be inferred solely from Spring's release log |

In the example, inside the method it logs **active=true**, and after the method **resourceBound=false**. This shows the transaction context was cleaned from the thread. It **does not prove the Hikari pool was shut down**; in fact, the pool remains alive until the application context closes.

HikariCP can expose metrics observing **active connections**, **idle connections**, **pending threads**, and **total connections**. In Spring Boot apps with Micrometer/Actuator, corresponding metrics help distinguish "connections currently borrowed" from "connections still open in the pool." Having idle > 0 after release is usually completely normal.

**Do not manually call connection.close() inside a @Transactional method** when the connection is Spring-managed; use JdbcTemplate or DataSourceUtils properly. If you manually open a DriverManager connection, the developer must manage and close it; it does not join Spring's transaction automatically.

### Physical Connection Boundaries

A logical JDBC Connection may be wrapped in a pool proxy. Representation strings in logs like HikariProxyConnection@... can vary between borrows and are **not durable business transaction identifiers**. To correlate logs for one request, use a trace ID/correlation ID and proper transaction name; do not use object hashes as transaction IDs in system design.

### When Release Does Not Mean Clean Transaction Completion

If Connection.commit() or rollback() throws SQLException, Spring still runs a cleanup branch attempting to release resources. Hence you can see a release log **even after a commit error occurred**. Analysts must check the root exception and DB data rather than interpreting release as commit confirmation.

If logs show active or pending connections climbing continuously, it is not necessarily a leak: it could be long transactions, SQL waiting on locks, an undersized pool, or the application holding connections outside transactions. Combine transaction duration, thread dumps, DB locks, and pool metrics to tell them apart.

## 8. Reading the Right Log Sources in Real Applications

### Transaction Manager Logs

Spring's TransactionManager is the right place to find begin, commit, rollback, and release. Verify the **actual manager** used by the bean:

- **JdbcTransactionManager / DataSourceTransactionManager**: the JDBC patterns shown in this lesson.
- **JpaTransactionManager**: may show logs opening/closing EntityManager, starting JPA transactions, flush, commit/rollback; do not insist it must contain "Switching JDBC Connection."
- **JtaTransactionManager**: state and commit via a JTA coordinator, potentially spanning multiple resources.
- **R2dbcTransactionManager**: reactive transactions based on Reactor Context and R2DBC connections; do not apply the ThreadLocal JDBC model to reactive callbacks.

### TransactionInterceptor Logs

Interceptor TRACE shows **which methods were intercepted by Spring**. If a method is self-invoked within the same bean in proxy mode, sometimes there will be no new interceptor log for that method. That is a sign to check **self-invocation** and proxies.

If a method is not called through a Spring bean, or transaction management has not been enabled, do not expect transaction logs just because @Transactional appears in source code.

### Connection Pool Logs

HikariCP logs pool startup, shutdown, validation, timeouts, and certain pool operations depending on log level. **HikariPool - Shutdown** only appears when the pool actually closes or the application exits, not after each successful @Transactional call. Do not turn on full Hikari DEBUG in production just to verify a transaction committed.

### Driver/DBMS Logs

Some DBMSs have transaction IDs, backend PIDs, slow query logs, statement logs, or dedicated audit logs. These help verify on the server side, yet require proper DBA configuration. **SQL logs only show statements sent/executed; they do not by themselves show the final commit outcome.**

## 9. Observing Caught Exceptions or Rollback-Only Cases

Example method:

~~~java
// Snippet: inside a Spring-managed service with a configured repository.
@Transactional
public void saveAndCatch() {
    try {
        repository.writeA();
        repository.writeBThatThrows();
    } catch (IllegalArgumentException ex) {
        applicationLogger.warn("Error occurred yet method still returns normally", ex);
    }
}
~~~

If an exception is caught and the method returns normally, the outer interceptor may **commit**, unless the transaction was already marked rollback-only by a resource or another transactional scope. Therefore, reading logs must go hand in hand with checking **which exceptions actually escape across the transaction boundary**.

Spring @Transactional rolls back by default on **RuntimeException** and **Error**; checked exceptions normally do not roll back automatically without rollbackFor or an equivalent policy. Example:

~~~java
// Snippet: PaymentCheckedException is an application checked exception.
@Transactional(rollbackFor = PaymentCheckedException.class)
public void saveWithCheckedFailure() throws PaymentCheckedException {
    repository.writeA();
    throw new PaymentCheckedException("rejected");
}
~~~

This is an **illustrative snippet, not a standalone program**. With rollbackFor configured as above, an escaping checked exception causes Spring to request rollback.

When an inner REQUIRED scope marks rollback-only yet the outer tries to commit, Spring may throw **UnexpectedRollbackException**. Preceding logs may show one scope marking rollback-only, while physical rollback occurs at the outer scope. Looking only at the end and ignoring the nested transaction context makes the cause hard to understand.

## 10. Transaction Names, Threads, and Correlation to Avoid Mixing Requests

When multiple requests run concurrently, transaction logs from different threads can interleave. Include appropriate fields in the log format:

- Timestamp with timezone and sufficient resolution to compare ordering.
- Logger name, log level, thread name.
- Correlation/trace ID attached at request entry, propagated across compatible components.
- Operation name or service method; avoid embedding emails, account numbers, or sensitive data directly into transaction names.

A practical approach when using Spring Boot + Micrometer Tracing is adding **traceId/spanId** to the log pattern per current logging configuration. When not using tracing, you can use MDC to attach a request correlation ID, yet you must **clear MDC when the request/worker thread finishes**, or stale information may be reused.

For @Async, task schedulers, and Executors, thread-bound imperative transactions **do not propagate automatically to new threads**. Thread names/correlation IDs are very helpful for catching bugs where two operations were assumed to share a transaction when in fact they did not.

## 11. How to Verify Results Instead of Trusting Logs Alone

A meaningful transaction test must verify **committed state**:

1. Initialize A=100, B=100 in a completed transaction.
2. Call the service via the Spring bean proxy to successfully execute A-=10, B+=10.
3. Once the method returns, re-read using a different connection/transaction; expect A=90, B=110.
4. Call the failure branch intentionally updating A-=20, B+=20 then throwing RuntimeException.
5. Once the exception escapes the proxy and rollback completes, re-read using an independent connection/transaction; expect still A=90, B=110.
6. Compare commit/rollback and release log timings against those results.

In the simple example, the queries after each call run **outside the service transaction**, so they can verify accepted state after the transaction finishes. With JPA, avoid merely reading an entity still sitting in an old persistence context; use an independent reading context/transaction to verify durability.

**Note on tests:** if an integration test is annotated @Transactional and the test framework rolls back automatically at the end, checks inside the test may see its own uncommitted data. To test actual commit, create an appropriate test boundary or use TestTransaction/REQUIRES_NEW in a controlled manner.

## 12. Troubleshooting: Missing or Unexpected Logs

| Symptom | Possibilities to Investigate | Verification Action |
| --- | --- | --- |
| No Creating new transaction | Wrong logger, method bypassed proxy, different manager, or joining an existing transaction | Verify @EnableTransactionManagement/Boot config, bean proxy, logger packages, propagation |
| Getting transaction seen yet no JDBC Connection | Using JPA/R2DBC/JTA, LazyConnectionDataSourceProxy, or no SQL executed | Identify actual manager/DataSource and whether any query ran |
| COMMIT seen yet data does not match expectations | Querying wrong DB/schema, SQL updated 0 rows, another transaction, reading from cache, race condition | Check update count, datasource, readback on independent connection, and DB logs |
| ROLLBACK seen yet a change still persists | SQL ran on non-transactional connection, different DB, operation committed earlier | Check JDBC Connection and manager use same DataSource, manual connections, @Async |
| RELEASE seen yet pool still holds many connections | Pool reuses physical connections, not necessarily a leak | Check active/idle/pending, pool config, and wait times |
| Pool timeout or connections held too long | Long transaction, SQL waiting on locks, network calls in transaction, small pool | Measure transaction duration, DB locks, thread dumps, pool metrics |
| Commit log appears before exception | Error occurred after commit, in afterCommit callback, or in another operation | Identify scope throwing error; check DB data and stack trace |
| Outer hits UnexpectedRollbackException | Inner REQUIRED marked rollback-only | Inspect earlier logs, propagation, caught exceptions |
| No UPDATE seen in transaction logs | Transaction manager logger is not an SQL logger | Enable appropriate JDBC/ORM logger and guard sensitive data |
| Same connection number appears in two transactions | Pool reuses physical connections | Distinguish each borrow/lease from transaction boundaries |

**Diagnostic priority order:** (1) right method goes through proxy, (2) right transaction manager and DataSource, (3) right propagation, (4) right begin/commit/rollback logs, (5) right cleanup/release, (6) right DB state after completion, (7) pool metrics and DB server when needed.

## 13. Avoid Breaking Transactions Just to Add Observability

- Never call **Connection.commit()** or **Connection.rollback()** manually on a Spring-managed connection to "see logs clearly"; that breaks the manager's transaction contract.
- Never keep a transaction open just to observe; SQL waiting on locks or long HTTP calls can hold connections too long.
- Never print raw SQL with sensitive information without log access controls.
- Never treat a RELEASE message as a "business operation succeeded" signal.
- Never leave global DEBUG/TRACE enabled long-term; select appropriate loggers, time windows, and environments.
- Never assume every Spring app uses JdbcTransactionManager: confirm JPA, JTA, JDBC, or R2DBC before interpreting log wording.
- Never interpret **closing a logical connection = physical close** when using a pool.

## 14. Self-Check Exercises

**Exercise A — Commit:** After a successful @Transactional call, you see "Initiating transaction commit" and "Releasing JDBC Connection". What must you check to confirm the DB actually saved the data?  
**Answer:** Verify no commit error/exception occurred and re-read state using an independent connection/transaction after the method finishes. Those two log lines only reflect coordination and cleanup steps.

**Exercise B — Rollback:** A service updates two tables then throws RuntimeException, and logs show "Rolling back JDBC transaction". Yet one row still changed. Which layer should you investigate first?  
**Answer:** Check whether all operations used the same transaction manager/DataSource/transaction-bound connection, whether any connection was opened manually or requests ran on another thread, then check the engine/DB and prior commit timing.

**Exercise C — Connection:** The log "Releasing JDBC Connection" appears after commit, yet Hikari still has idle connections. Is this a connection leak?  
**Answer:** No. The connection was returned to the pool for reuse. A leak is only suspected when active/borrowed connections are not returned, pending threads keep climbing, or the pool warns after its configured threshold.

**Exercise D — BEGIN:** Why is there no SQL BEGIN statement in the logs even though @Transactional is working?  
**Answer:** A local JDBC transaction is usually controlled via Connection.setAutoCommit(false); the DBMS/driver may not display BEGIN as a standalone SQL statement. Check transaction manager logs, connection behavior, and commit/rollback outcomes.

**Exercise E — Nested scope:** Inner REQUIRED returns normally yet only the outer commits. Why is there no physical COMMIT after the inner method?  
**Answer:** Inner joined the existing transaction. Final decision and commit belong to the outer transaction owner.

**Exercise F — Proxy:** Calling this.inner() with @Transactional shows no interceptor log for inner. What is wrong?  
**Answer:** Self-invocation normally bypasses the Spring AOP proxy in proxy mode, so inner's @Transactional metadata may not be applied. Call through another Spring bean/proxy or redesign the boundary.

## 15. Checklist for Observing Your First Transaction

- [ ] Configure the right transaction manager and interceptor loggers at DEBUG/TRACE in a learning environment.
- [ ] Confirm the method is invoked through a Spring-managed proxy or an appropriate transaction template.
- [ ] Confirm **Creating new transaction** or **Participating in existing transaction** per propagation.
- [ ] For local JDBC, identify the borrowed connection and controlled autocommit.
- [ ] Observe the success **commit** branch and error **rollback** branch separately.
- [ ] Confirm **release connection** after both branches, understanding logical vs. physical connections.
- [ ] Re-read data after the transaction ends to verify actual state.
- [ ] Match correlation IDs, loggers, and threads if multiple requests run concurrently.
- [ ] Turn off unnecessary verbose logging levels when finishing the debugging session.

**Key takeaway:** Spring logs tell you *who is coordinating the transaction and in which phase*. DBMS outcomes prove the final data state; release logs prove the cleanup path, not commit. With connection pools, physical connections staying open after being returned to the pool is normal behavior.

## References

- [Spring Framework — Understanding the Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Example of Declarative Transaction Implementation (transaction log)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [HikariCP — Configuration and Pool Lifecycle](https://github.com/brettwooldridge/HikariCP)
