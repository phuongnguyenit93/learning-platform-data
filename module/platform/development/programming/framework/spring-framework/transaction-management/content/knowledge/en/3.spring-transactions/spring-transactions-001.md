# TransactionManager and Transaction Management Strategies in Spring

A business requirement such as transferring funds, creating an order with line items, or updating inventory may perform multiple write operations. If part succeeds and the rest fails, the application needs to know **which scope must commit or rollback**. In Spring, TransactionManager is the component that coordinates starting, joining, and ending transactions on the appropriate resource. To apply it properly, you need to distinguish **transaction manager types**, **boundary declaration styles**, **propagation strategies**, **isolation**, and **rollback**.

This lesson presents Spring Framework's transaction management model for JDBC, JPA, JTA, and reactive applications, clearly explaining how to choose and configure a TransactionManager for each scenario.

## 1. Where Does TransactionManager Sit in the Spring Model?

Suppose a service handles transferring 50 units from account A to account B. Both SQL statements must commit together or rollback together. The service can be declared as follows:

~~~java
// Illustrative snippet in a Spring application with configured repository and transaction.
@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, int amount) {
        accounts.decrease(fromId, amount);
        accounts.increase(toId, amount);
    }
}
~~~

This snippet **is not a standalone program**: it requires a repository class, DataSource, TransactionManager, and enabled transaction management. Its purpose is to indicate the transaction boundary at the service layer. There is no proof that the two SQL statements share the same transaction if the repository uses independent DataSources or connections.

A diagram of the roles:

~~~text
Caller
  |
  v
Spring-managed service (call goes through transactional proxy)
  |
  v
TransactionInterceptor / TransactionAspectSupport
  |
  v
TransactionManager: open, join, commit, or rollback
  |
  +---- JDBC: DataSource + Connection -> JDBC driver -> DBMS
  |
  +---- JPA : EntityManager + JPA provider -> JDBC -> DBMS
  |
  +---- JTA : transaction coordinator -> enlistable resources
  |
  +---- R2DBC: reactive Connection -> R2DBC driver -> DBMS
~~~

**Spring does not enforce ACID on behalf of the database.** TransactionManager makes coordination decisions within the scope of the resources it manages; the DBMS executes the actual changes, locks, constraints, and commit/rollback. Nor does TransactionManager by default turn an HTTP call, email, or message send into an operation that can rollback together with SQL.

## 2. The Interface Family: TransactionManager, PlatformTransactionManager, and ReactiveTransactionManager

In Spring, **org.springframework.transaction.TransactionManager** is the root marker interface of the abstraction. The two main branches have different semantics:

| Interface | Used for | Transaction binding mechanism | Key operations |
| --- | --- | --- | --- |
| PlatformTransactionManager | Imperative/blocking flows, e.g., JDBC, JPA | Transaction context is typically bound to the current thread | getTransaction, commit, rollback |
| ReactiveTransactionManager | Reactive pipelines, e.g., R2DBC | Reactor Context in the reactive chain | getReactiveTransaction, commit, rollback returning Publisher/Mono |

For PlatformTransactionManager, the typical contract is:

~~~java
// Excerpt of API signatures; not a complete implementation class.
TransactionStatus getTransaction(TransactionDefinition definition);
void commit(TransactionStatus status);
void rollback(TransactionStatus status);
~~~

- **TransactionDefinition** describes the requested policy: propagation, isolation, timeout, read-only, and transaction name.
- **TransactionStatus** indicates whether the transaction is new or participating, whether it has a savepoint, and whether it is completed; business code can also request **setRollbackOnly()**.
- **PlatformTransactionManager** executes the calls through a concrete technology. Implementations typically extend **AbstractPlatformTransactionManager** to share the standard workflow for controlling propagation, synchronization, commit, and rollback.

With ReactiveTransactionManager, transaction operations are bound to the asynchronous processing flow and Publisher subscription; you cannot assume it is propagated via ThreadLocal across every callback. Both types of managers can coexist in the same application, but they cannot automatically substitute for each other.

**Do not choose a manager solely by class name or simply because @Transactional is present.** You must base the choice on the data access technology and the actual resources the service uses.

## 3. Implementations and How to Choose

| Transaction manager | Managed resource | Choose when | Limitations to know |
| --- | --- | --- | --- |
| **JdbcTransactionManager** | A single JDBC DataSource/Connection | JDBC applications, JdbcTemplate, NamedParameterJdbcTemplate | A single local JDBC transaction; does not automatically combine multiple DBs into one atomic transaction |
| **DataSourceTransactionManager** | A single JDBC DataSource/Connection | Need a local JDBC transaction, long-term compatibility with JDBC integration | Does not manage a JPA persistence context or multi-resource transactions |
| **JpaTransactionManager** | EntityManagerFactory and EntityManager | Using JPA/Hibernate over the same persistence unit | Does not automatically coordinate multiple EntityManagerFactories or multiple independent DBs |
| **JtaTransactionManager** | JTA transaction coordinator | Environment has a JTA server/coordinator and suitable global-transaction-capable resources | Requires enlistment/XA configuration; higher operational cost and risk than local transactions |
| **R2dbcTransactionManager** | A single R2DBC ConnectionFactory | Reactive flows reading/writing data with R2DBC | Does not manage blocking JDBC inside a reactive transaction |
| **Custom TransactionManager** | Per implementation contract | Integrating a specialized resource when genuinely needed | Must ensure semantics, synchronization, exceptions, and cleanup yourself |

**JdbcTransactionManager** inherits the mechanism of DataSourceTransactionManager and adds translation of JDBC commit/rollback errors into Spring data access exceptions. For modern pure-JDBC applications, this is usually a good choice. Both use a single DataSource; the actual datasource should be a connection pool in production.

**JpaTransactionManager** manages the JPA transaction lifecycle and persistence context via EntityManager. Under proper configuration, JDBC using the same DataSource can participate in a JPA transaction; this requires proper integration, and you must not assume every JDBC Connection or EntityManager shares the same transaction.

**JtaTransactionManager** is appropriate when the application genuinely needs a transaction coordinator to coordinate multiple JTA/XA-capable resources. It does not automatically make REST APIs, emails, or two ordinary connections into a distributed transaction. For many systems, **local transaction + transactional outbox + idempotent consumer** can be easier to operate than a global XA transaction.

**R2dbcTransactionManager** is appropriate when repositories use R2DBC and return Mono/Flux. For blocking JDBC/JPA, choose PlatformTransactionManager. The two worlds have different context propagation models; do not run JDBC statements inside a reactive chain and expect them to automatically join an R2DBC transaction.

### Quick Decision Matrix

1. **Single database, using JdbcTemplate/JDBC?** Choose JdbcTransactionManager or DataSourceTransactionManager with the right DataSource.
2. **Single JPA persistence unit?** Choose JpaTransactionManager for that EntityManagerFactory.
3. **Multiple resources requiring true atomic commit guarantees?** Evaluate JTA/XA and the capabilities of each resource; if not feasible, explicitly design outbox/saga and eventual consistency.
4. **Pure reactive R2DBC?** Choose R2dbcTransactionManager with the right ConnectionFactory.
5. **Multiple independent datasources?** You can declare multiple managers and specify the right manager for each operation, but **multiple local managers do not create a distributed transaction**.

Spring Boot can auto-configure a TransactionManager based on DataSource, JPA, or R2DBC and existing beans. When an application contains multiple datasources/providers, verify the actual bean selected instead of relying on assumptions about auto-configuration.

## 4. Two Boundary Declaration Strategies: Declarative and Programmatic

### 4.1. Declarative Transactions with @Transactional

When transaction management is enabled, Spring typically uses an AOP proxy. Calls passing through the proxy are handled by **TransactionInterceptor**:

1. Look up the transaction configuration of the method/class, including the manager name if declared.
2. Select the manager and request a transaction matching the propagation.
3. Bind the resource and let the business method execute.
4. If the call completes normally and the transaction is allowed to commit, request commit at the boundary that owns the transaction.
5. If an exception matches a rollback rule or the status is rollback-only, request rollback.
6. Release and restore the resource and transaction context.

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as Spring AOP Proxy
    participant TM as TransactionManager
    participant DB as Transactional Resource
    Caller->>Proxy: Call service method
    Proxy->>TM: getTransaction(definition)
    TM->>DB: Open/join transaction
    Proxy->>DB: Run business logic (JDBC/JPA)
    alt Success, not rollback-only
        Proxy->>TM: commit(status)
        TM->>DB: Commit or wait for outer transaction
    else Matching exception / rollback-only
        Proxy->>TM: rollback(status)
        TM->>DB: Rollback or mark rollback-only
    end
    Proxy-->>Caller: Result or exception
~~~

Configuring a manager for a JDBC application (this is an **illustrative configuration snippet**; an existing DataSource bean is required):

~~~java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Corresponding imports: **org.springframework.context.annotation.Bean**, **Configuration**; **org.springframework.transaction.annotation.EnableTransactionManagement**; **org.springframework.transaction.PlatformTransactionManager**; **org.springframework.jdbc.support.JdbcTransactionManager**; **javax.sql.DataSource**. In a Spring Boot application that auto-configures successfully, you may not need to declare this bean manually.

Using the annotation to describe policy at the service boundary:

~~~java
// Illustrative service snippet; dependencies reside in the Spring application.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = BusinessCheckedException.class,
    timeout = 15
)
public void placeOrder(Command command) throws BusinessCheckedException {
    reserveInventory(command);
    saveOrder(command);
}
~~~

This is not a standalone program: the Command and BusinessCheckedException types and business methods must be defined. The meaning is that for the same service operation, Spring attempts to apply the requested transaction to the appropriate resource. **Isolation.READ_COMMITTED** depends on DBMS support; the timeout duration does not guarantee every driver/DBMS interrupts statements in the same way.

**Proxy caveats:** self-invocations such as this.save() from the same object usually do not pass through the proxy, so the annotation on the save() method does not start a new transaction. Private/final methods or calls outside the proxy mechanism also need to be evaluated according to the proxy mode and Spring version; place transaction boundaries on service methods that can be clearly intercepted by Spring. Imperative transaction contexts do not automatically propagate to new threads created by @Async or an Executor.

### 4.2. Programmatic Transactions with TransactionTemplate

In imperative flows, **TransactionTemplate** accepts a PlatformTransactionManager, wraps callbacks inside a transaction, and automatically performs commit/rollback based on status or exceptions.

~~~java
// Illustrative snippet inside a class already injected with JdbcTemplate and manager.
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
template.executeWithoutResult(status -> {
    jdbcTemplate.update("UPDATE account SET balance = balance - 10 WHERE id = 1");
    if (businessConditionNotMet()) {
        status.setRollbackOnly();
    }
});
~~~

The strength is **not depending on calls through an AOP proxy**, making it easy to control a narrow scope, timeout, or dynamic rollback-only. On the flip side, transaction logic becomes tightly coupled to business code and is easy to overuse if wrapping many small operations. For typical services, @Transactional is usually easier to read.

In reactive flows, the equivalent programmatic option is **TransactionalOperator**; the operator wraps a Publisher and uses a ReactiveTransactionManager. Do not place blocking JDBC code inside the pipeline and treat TransactionalOperator as a transaction manager for JDBC.

### 4.3. Which Approach Should You Choose?

| Criterion | @Transactional | TransactionTemplate / TransactionalOperator |
| --- | --- | --- |
| Separation of business logic and infrastructure | High; policy declared via metadata | Business code is aware of the transaction API |
| Boundary | Method managed by interceptor | Explicitly wrapped callback block or pipeline |
| Requires AOP proxy in imperative | Usually yes in proxy mode | No |
| Changing transaction policy at runtime | Limited by metadata/config | More flexible per callback |
| Readability for CRUD services | Usually simpler | Can involve more boilerplate |
| Application style | Imperative and reactive when using the right manager | TransactionTemplate (imperative), TransactionalOperator (reactive) |

## 5. Propagation: Strategy for Nested Calls

**Propagation** answers: “When a method requires a transaction but an outer call already has a transaction, what will Spring do?” This is a transaction manager policy, not a database lock level.

| Propagation | Existing transaction | No existing transaction | Notes |
| --- | --- | --- | --- |
| **REQUIRED** (default) | Join the current transaction | Create a new one | Suitable for most services |
| **REQUIRES_NEW** | Suspend the outer transaction, create a new independent physical transaction | Create a new one | May require an additional connection; independent commit/rollback |
| **NESTED** | Create a savepoint within the same physical transaction if the manager supports it | Create a new transaction | Partial rollback to savepoint; final commit still belongs to outer |
| **SUPPORTS** | Join if one exists | Run without an active transaction | Must understand read or write behavior without a transaction |
| **MANDATORY** | Join | Throw an error | Requires caller to have already opened a transaction |
| **NOT_SUPPORTED** | Suspend the current transaction | Run outside a transaction | Useful when an independent operation genuinely needs to skip the transaction |
| **NEVER** | Throw an error | Run outside a transaction | Used when running inside a transaction is strictly forbidden |

### 5.1. REQUIRED: Logical Boundaries Sharing One Physical Transaction

Suppose methods outer() and inner() are both REQUIRED. When outer has already created a transaction, inner **joins the same physical transaction** and does not commit on its own when inner returns. Each method has its own logical scope, but they share the final outcome.

If inner determines it must rollback and marks the transaction rollback-only, outer cannot commit even if it completes normally. In a situation where outer tries to commit without knowing inner marked rollback-only, Spring typically throws **UnexpectedRollbackException**. This exception ensures the caller does not mistakenly think the operation committed.

### 5.2. REQUIRES_NEW: Independent Physical Transactions

When outer() already has a transaction and inner() is REQUIRES_NEW, Spring temporarily suspends outer's resources, opens a new transaction for inner, and resumes outer after inner finishes.

~~~text
outer REQUIRED   : [ begin ----------- (suspended) ---------- resume ---- rollback ]
inner REQUIRES_NEW:                    [ begin --- commit ]
Result           : changes in inner can be preserved even if outer rolls back
~~~

Valid use case: writing an independent audit record that product requirements allow saving even when the main operation fails. However, separating audit this way can cause semantic mismatch if the audit must accurately reflect committed business transactions; requirements must be clearly defined.

**Technical cost:** inner usually needs a new connection while outer still holds its connection. If there are N concurrent threads, each needing both outer and inner connections, a pool sized to only N connections can cause threads to wait on each other. Set realistic concurrency limits, connection pool sizing, and timeouts.

### 5.3. NESTED: Same Physical Transaction, with Savepoints

NESTED relies on savepoints when supported by the manager/driver. When inner fails, it can rollback to the savepoint and outer can continue; however, **if outer rolls back, all changes, including the nested part that succeeded, are still lost**.

~~~text
BEGIN outer
  UPDATE A
  SAVEPOINT before_inner
    UPDATE B
  ROLLBACK TO SAVEPOINT before_inner
  UPDATE C
COMMIT outer

DB persists A and C; B is discarded.
~~~

In Spring, DataSourceTransactionManager/JdbcTransactionManager supports appropriate JDBC savepoints. Do not assume NESTED works by default for every JPA provider, Reactive manager, or resource that does not support savepoints.

**How REQUIRES_NEW differs from NESTED:** REQUIRES_NEW has a new physical transaction that can commit independently; NESTED only creates a savepoint within the existing physical transaction. This is the decisive difference when choosing a strategy.

### 5.4. Rules for Choosing Propagation

- Use **REQUIRED** for a business unit that must succeed/fail together, placing the boundary at the service.
- Use **REQUIRES_NEW** only when independent commit behavior is genuinely required; evaluate pool capacity and side effects.
- Use **NESTED** when you want partial rollback within the same transaction and have verified manager/driver savepoint support.
- Use **MANDATORY** when the method makes no sense if the caller does not already have a transaction.
- Use **SUPPORTS/NOT_SUPPORTED/NEVER** for intentional contracts; avoid using them to “fix” rollback bugs without understanding the differences.

## 6. Isolation, Timeout, and readOnly: Resource Control Strategies

### 6.1. Isolation

Propagation resolves **relationships between calls**; isolation resolves **relationships between concurrent transactions**.

| Isolation | General meaning | Risks or caveats |
| --- | --- | --- |
| DEFAULT | Use the database's default level | Need to know what the DBMS is configured with |
| READ_UNCOMMITTED | May allow reading uncommitted data | Some DBMSs promote the level or implement it differently |
| READ_COMMITTED | Avoid reading uncommitted data | Non-repeatable read/phantom may still occur depending on DBMS |
| REPEATABLE_READ | Many DBMSs hold snapshots/locks to prevent non-repeatable reads | Does not automatically eliminate all write skew or anomalies |
| SERIALIZABLE | Attempts to produce results equivalent to serial execution | May require retries on serialization failure, reduces concurrency |

Isolation is enforced by the DBMS. The transaction manager typically requests the setting on the connection or via an equivalent mechanism. **There is no single optimal isolation value for all operations.** Reading a balance and then updating it may require an atomic UPDATE statement, row locking, optimistic locking, or higher isolation depending on invariants.

When a REQUIRED method merely **joins** an existing transaction, an inner method's own isolation declaration usually does not change the isolation of the current physical transaction. You can enable validateExistingTransaction=true on AbstractPlatformTransactionManager so Spring refuses to join on significant mismatches; do not assume the inner annotation always wins.

### 6.2. Timeout

Timeout describes the transaction time limit, though how it is enforced depends on the manager, driver, and DBMS. The timeout may be translated into a transaction deadline or statement timeout via appropriate integration. Do not treat this as “automatically killing every Java thread and canceling every HTTP call” after the exact declared number of seconds.

If a transaction calls a slow network service, holding the connection and locks throughout the wait can reduce throughput. Network operations should usually be separated from the DB transaction boundary, or an appropriate asynchronous architecture should be chosen.

### 6.3. readOnly

readOnly=true is a **hint** for the manager, JDBC connection, JPA provider, and/or DBMS to optimize read operations when supported. It is not an authorization mechanism or an absolute immutability guarantee in every configuration.

A @Transactional(readOnly=true) block can still trigger write commands or exceptions depending on the stack; use a read-only DB account and permission/constraint mechanisms if the requirement is to forbid writes.

## 7. Rollback: Error Handling Strategy and Rollback-Only

By default for @Transactional in standard configurations:

- **RuntimeException** or **Error** escaping the transactional boundary causes Spring to request a rollback.
- **Checked exceptions** do not trigger rollback automatically unless configured with rollbackFor or an equivalent policy.
- If an exception is caught and the method returns normally, the interceptor may treat the call as successful and commit.
- You can explicitly request rollback using TransactionStatus.setRollbackOnly() in a programmatic callback or through the appropriate transaction status API.

Example of controlling checked errors (illustrative snippet in a Spring service):

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public void checkout(Order order) throws PaymentRejectedException {
    reserveStock(order);
    chargeWithinTransactionBoundary(order);
}
~~~

The snippet above is not a standalone program and does not imply that a charge to an external payment gateway can rollback together with the database. If chargeWithinTransactionBoundary calls an external API, separate consistency and compensation design is needed.

**rollbackFor** only controls Spring's decision; it does not turn side effects outside the transaction into ACID operations. **noRollbackFor** can request a commit even when a type of exception is thrown; use it very carefully so as not to leave partial state.

Two levels of rollback to distinguish:

1. **Rollback of a logical transaction scope**: a participating REQUIRED method marks rollback-only; the manager may mark the existing physical transaction to roll back later.
2. **Rollback of a physical transaction**: the transaction owner or coordinator executes rollback at the final boundary; the DBMS discards uncommitted changes belonging to that transaction.

In the case of JPA, remember that EntityManager can flush SQL before commit. **Flush is not the same as commit**, and the transaction can still rollback. Some DB/JPA errors put the transaction into a rollback-only state; do not swallow the error and try to continue as if the transaction were still healthy.

## 8. Selecting Multiple TransactionManagers in the Same Application

An application may access two DBs:

~~~text
billingService  -> billingDataSource -> billingTxManager
reportingService -> reportingDataSource -> reportingTxManager
~~~

Declare manager beans with explicit names and specify them via annotation:

~~~java
// Illustrative configuration snippet; the two DataSources have been declared separately.
@Bean("billingTxManager")
public PlatformTransactionManager billingTxManager(
        @Qualifier("billingDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}

@Bean("reportingTxManager")
public PlatformTransactionManager reportingTxManager(
        @Qualifier("reportingDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

~~~java
// Illustrative snippet; assumes this is a Spring-managed service method.
@Transactional(transactionManager = "billingTxManager")
public void collectPayment(Bill bill) {
    billingRepository.update(bill);
}
~~~

You must import **@Qualifier** from Spring and the corresponding Java/Spring types; these are snippets, not standalone runnable Java files. When multiple managers exist, the default bean or qualifier must be specified explicitly. Using the wrong manager can cause a repository to run outside the intended transaction or create a transaction on a different resource.

**Core caveat:** calling billingTxManager and reportingTxManager sequentially does not guarantee atomicity across two DBs. If DB A commits successfully but DB B fails, local transaction managers cannot rollback the already-committed A. When atomic multi-resource behavior is required, you need a suitable transaction coordinator with enlistable resources or a business consistency approach such as outbox/saga.

## 9. Hands-On Java 17+: Seeing REQUIRED and REQUIRES_NEW Clearly

The standalone runnable example below uses **Spring JDBC + H2 in-memory** and TransactionTemplate. It verifies these scenarios:

1. Outer transaction rolls back, inner REQUIRES_NEW commits independently.
2. Inner REQUIRED marks rollback-only, outer transaction tries to commit and receives UnexpectedRollbackException.
3. A single REQUIRED transaction commits successfully.

Structure:

~~~text
tx-manager-strategies/
├── pom.xml
└── src/main/java/demo/TxManagerStrategiesDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-manager-strategies</artifactId>
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
                    <mainClass>demo.TxManagerStrategiesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TxManagerStrategiesDemo.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionTemplate;

public final class TxManagerStrategiesDemo {
    private TxManagerStrategiesDemo() {}

    private static void show(JdbcTemplate jdbc, String phase) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s: A=%d, B=%d%n", phase, a, b);
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE account (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (2, 200)");

        JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);

        TransactionTemplate required = new TransactionTemplate(manager);
        TransactionTemplate requiresNew = new TransactionTemplate(manager);
        requiresNew.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        show(jdbc, "Initial");

        // A changes in outer but is rolled back; independent inner committed B.
        required.executeWithoutResult(outer -> {
            jdbc.update(
                    "UPDATE account SET balance = balance - 20 WHERE id = 1");
            requiresNew.executeWithoutResult(inner ->
                    jdbc.update(
                            "UPDATE account SET balance = balance + 5 WHERE id = 2"));
            outer.setRollbackOnly();
        });
        show(jdbc, "REQUIRES_NEW + outer rollback");

        // inner REQUIRED joins outer transaction and requests rollback-only.
        try {
            required.executeWithoutResult(outer -> {
                jdbc.update(
                        "UPDATE account SET balance = balance - 10 WHERE id = 1");
                required.executeWithoutResult(inner -> {
                    jdbc.update(
                            "UPDATE account SET balance = balance + 10 WHERE id = 2");
                    inner.setRollbackOnly();
                });
            });
        } catch (UnexpectedRollbackException expected) {
            System.out.println("REQUIRED inner: UnexpectedRollbackException");
        }
        show(jdbc, "After REQUIRED rollback");

        // Two SQL statements in one successful transaction.
        required.executeWithoutResult(status -> {
            jdbc.update(
                    "UPDATE account SET balance = balance - 30 WHERE id = 1");
            jdbc.update(
                    "UPDATE account SET balance = balance + 30 WHERE id = 2");
        });
        show(jdbc, "Committed REQUIRED");
    }
}
~~~

Requires **JDK 17+** and **Maven** installed. In the tx-manager-strategies directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout from the Java program** (excluding Maven's own logs/warnings):

~~~text
Initial: A=100, B=200
REQUIRES_NEW + outer rollback: A=100, B=205
REQUIRED inner: UnexpectedRollbackException
After REQUIRED rollback: A=100, B=205
Committed REQUIRED: A=70, B=235
~~~

**Step-by-step state explanation:**

- **Initial:** H2 has accounts A=100 and B=200. Table creation/seed data commands completed before the example opened any transaction.
- **REQUIRES_NEW:** outer subtracts 20 from A on one connection without committing; inner temporarily suspends outer and adds 5 to B on another transaction connection, then commits. Afterward, outer calls setRollbackOnly, so only A's change is discarded. Hence A=100, B=205.
- **Nested REQUIRED:** inner uses the same physical transaction as outer, adds 10 to B, and marks rollback-only. Outer attempts to commit and receives UnexpectedRollbackException. Both subtracting 10 from A and adding 10 to B are rolled back; balances remain A=100, B=205.
- **REQUIRED commit:** subtracts 30 from A and adds 30 to B in one successful transaction, yielding A=70, B=235.

DriverManagerDataSource creates a new connection when needed, which serves to observe separation between the two physical transactions. In production, use an appropriate connection pool. This example demonstrates propagation within **the same DataSource**; if switching to two datasources, atomicity must be evaluated separately.

### Controlled Extension Exercise

Replace inner REQUIRES_NEW with REQUIRED in the first example while keeping outer rollback-only: what happens to B? Because inner joins the outer transaction, B also rolls back and stays 200. Switch back to REQUIRES_NEW and remove outer.setRollbackOnly(): A becomes 80 and B becomes 205. Verify this yourself by reading the data after the transaction ends.

## 10. Reactive Transactions: Same Idea, Different Context Propagation Mechanism

In a reactive application with R2DBC:

- ReactiveTransactionManager manages reactive transactions via publishers, not relying on a fixed ThreadLocal.
- TransactionalOperator can wrap Mono/Flux so that all reactive operations in the same context join the transaction.
- When a publisher has not been subscribed to, the code inside the pipeline has not run and the transaction has not executed in the usual way.
- Operations that want to participate must share the same reactive transaction context and the right ConnectionFactory/manager.
- @Transactional with a reactive return type uses a reactive transaction manager; for methods returning normal types, use the appropriate PlatformTransactionManager.

Conceptual example (illustrative snippet; requires configured ReactiveTransactionManager and DatabaseClient):

~~~java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Void> updateBoth =
        databaseClient.sql("UPDATE account SET balance = balance - 5 WHERE id = 1")
                .fetch().rowsUpdated()
                .then(databaseClient.sql(
                        "UPDATE account SET balance = balance + 5 WHERE id = 2")
                        .fetch().rowsUpdated())
                .then();

return operator.transactional(updateBoth);
~~~

This is not a standalone class and results depend on the R2DBC driver/DBMS. Do not mix blocking JDBC inside the pipeline above and assume JdbcTemplate will use R2dbcTransactionManager's connection. If you need to combine both mechanisms, design separate boundaries and consistency.

## 11. Strategy Guide by Practical Scenario

### Case A: An Order Placement Writing to Three Tables in the Same DB

**Recommendation:** a single service boundary using REQUIRED; for JDBC choose JdbcTransactionManager, for JPA choose JpaTransactionManager. Repositories must participate in the right transaction. Order creation, line items, and inventory reservation must finish together; constraint violations roll back the whole unit.

**No need** for REQUIRES_NEW on each repository. Splitting every SQL line into its own transaction breaks order atomicity.

### Case B: Saving a Technical Audit Trail Even If Business Logic Fails

**Worth considering:** separate a real service through a Spring proxy and use REQUIRES_NEW for the technical record. You must decide whether this audit means “attempted” or “completed”. If it must accurately reflect committed business state, an after-commit hook or transactional outbox may be more suitable.

### Case C: Trying a Secondary Branch; If It Fails, Continue the Main Branch

**Worth considering:** NESTED with JDBC savepoints when supported; the secondary branch rolls back to the savepoint and outer can continue. If using JPA or an unsupported resource, do not silently assume NESTED always succeeds.

### Case D: Two DBs and a Message Broker

**Analyze first:** which resources can enlist in JTA/XA and what the actual atomicity requirements are. If global transactions are not feasible, use a local transaction to write business state + outbox in the same DB; a publisher emits events afterward and consumers process idempotently. Eventual consistency and retry/duplicate possibilities must be accepted.

### Case E: Heavy Report Reading

**Recommendation:** determine isolation, snapshot consistency, timeout, and readOnly appropriate for the DBMS. Avoid holding transactions too long while exporting reports or calling external services; only use NOT_SUPPORTED when running outside a transaction genuinely meets the desired consistency.

## 12. Configuration Errors and Diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| @Transactional does not rollback | Self-invocation, caught exception, checked exception not in rollback rules | Trace proxy, method boundary, rollbackFor, and escaping exceptions |
| One repository writes and still commits after rollback | Wrong manager used, different DataSource, or JDBC Connection outside transaction | Cross-check manager bean, DataSource, SQL logs, and connection identity |
| UnexpectedRollbackException at outer | Inner REQUIRED marked rollback-only | Inspect stack trace and inner logic; do not catch the exception and assume commit succeeded |
| REQUIRES_NEW hangs waiting | Connection pool exhausted or lock conflict | Check active/waiting connections, thread dump, locks, and pool sizing |
| NESTED reports unsupported | Driver/manager does not support savepoints or unsuitable configuration | Verify transaction manager and JDBC savepoint capability |
| Inner isolation annotation has no effect | Inner merely joins an existing transaction | Identify the physical transaction opening boundary and validateExistingTransaction |
| DB in wrong state after commit | Wrong SQL logic, concurrency anomaly, another transaction, or unclear commit outcome | Integration test against real DB, SQL logs, transaction id, and query from a new connection |
| Reactive @Transactional has no effect | Publisher not subscribed, lost Reactor Context, wrong manager | Check reactive chain, context, return type, and ConnectionFactory |

**Debugging workflow in order:**

1. Identify the exact method entrypoint and transaction boundary (proxy or TransactionTemplate/TransactionalOperator).
2. Identify which PlatformTransactionManager or ReactiveTransactionManager was selected, bean name, and corresponding datasource/provider.
3. Check whether propagation is creating a new transaction or joining; check if rollback-only, suspend, or savepoint occurred.
4. Check actual isolation, readOnly, timeout, and SQL/exceptions returned by the driver or DBMS.
5. After the method finishes, verify data state using an independent connection/transaction instead of only looking at object results in the persistence context.
6. If the transaction involves multiple resources, check consistency, idempotency, and retry mechanisms across the whole system.

### Logging and Testing

In test environments, you can selectively enable TRACE/DEBUG for **org.springframework.transaction** and **org.springframework.jdbc.datasource** to observe creation/joining, suspend/resume, and commit/rollback. Avoid enabling sensitive SQL and parameters outside controlled environments.

A useful integration test invokes the business method **through the Spring bean proxy**, intentionally causes an error on the second operation, and then reads both rows from another transaction to confirm rollback. Then check success and REQUIRED/REQUIRES_NEW cases. When testing real database behavior, use the DBMS matching the application environment; H2 is just a convenient demo and does not fully simulate locking and isolation of every DB.

## 13. Self-Check Questions

**1. Is TransactionManager a JDBC driver or DBMS?**  
No. It is a transaction coordination abstraction. The driver communicates with the DBMS; the DBMS executes the actual commit/rollback and isolation.

**2. Why can an inner REQUIRED marking rollback-only cause outer to receive UnexpectedRollbackException?**  
Because the two logical scopes share one physical transaction. Outer thinks it can commit, but the transaction has been marked for mandatory rollback; Spring reports that the commit did not happen.

**3. Can REQUIRES_NEW commit and then outer rollback afterward?**  
Yes. Inner uses an independent physical transaction. This is intentional behavior, not a nested savepoint.

**4. How does NESTED differ from REQUIRES_NEW?**  
NESTED typically uses a savepoint on the same physical transaction; an outer rollback discards everything. REQUIRES_NEW opens an independent physical transaction and can commit separately.

**5. When should you use JpaTransactionManager instead of JdbcTransactionManager?**  
When business logic uses a JPA EntityManager/persistence unit to manage object changes and flushing, choose the appropriate JPA-integrated manager; JDBC uses a JDBC manager on a DataSource.

**6. With two DataSources, does using @Transactional with one manager guarantee atomicity across both?**  
No. A single local manager does not automatically coordinate atomic commit across two independent resources. Appropriate JTA/XA or an application consistency strategy is needed.

**7. Do readOnly=true and timeout=10 guarantee forbidding all writes and canceling every task at exactly 10 seconds?**  
No. Enforcement depends on the manager, provider, driver, DBMS, and data access API; they do not replace DB permissions and timeouts of external systems.

**8. Why doesn't TransactionalOperator automatically include JdbcTemplate commands in an R2DBC transaction?**  
Because reactive transactions are propagated via Reactor Context through ReactiveTransactionManager, whereas blocking JDBC typically uses a thread-bound Connection managed by PlatformTransactionManager.

## 14. Conclusion and Practical Principles

- **Choose the right manager first:** JDBC → JdbcTransactionManager/DataSourceTransactionManager; JPA → JpaTransactionManager; JTA/XA → JtaTransactionManager; R2DBC → R2dbcTransactionManager.
- **Place boundaries on business units:** @Transactional for services via proxy, or template/operator for flows with programmatic requirements.
- **Propagation determines transaction relationships:** REQUIRED shares the physical transaction, REQUIRES_NEW separates independently, NESTED uses savepoints when supported.
- **Isolation and rollback are policies:** Spring requests, DBMS enforces; rollback rules must account for exceptions that actually escape or rollback-only.
- **A single annotation does not solve distribution:** multiple DBs, APIs, and messages require an appropriate coordinator or an eventual consistency architecture.
- **Verify via DB state after the transaction ends**, while also observing the right manager, connection, propagation, and commit/rollback in logs.

## References

- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring – Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring – Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring – Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
