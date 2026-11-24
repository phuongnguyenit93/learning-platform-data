# Dependency Graph of Transaction Manager, DataSource or ConnectionFactory, and Data Access Code in Spring

## 1. Why Read the Dependency Graph Correctly?

When writing `@Transactional`, what needs checking is not merely that the annotation is present, but **which transaction manager controls the transaction, which resource that manager manages, and whether the data access code obtains the right connection belonging to that transaction**. These three links determine whether a SQL statement commits/rolls back together with other SQL statements.

In Spring Framework, the model must be viewed along **two separate branches**:

- **Imperative/JDBC:** `PlatformTransactionManager`, `javax.sql.DataSource`, JDBC `Connection`, `JdbcTemplate`, or JDBC-based repositories. The transaction context is typically bound to a **thread**.
- **Reactive/R2DBC:** `ReactiveTransactionManager`, `io.r2dbc.spi.ConnectionFactory`, R2DBC `Connection`, `DatabaseClient`, or reactive repositories. The transaction context is bound to the **Reactor subscriber Context**, not relying on JDBC's ThreadLocal.

Additionally, **JPA** is an important imperative branch: `JpaTransactionManager` manages `EntityManagerFactory`/`EntityManager`; underneath, the JPA provider still typically uses a JDBC `DataSource`. JPA is not R2DBC.

Distinguish the components:

| Component | Question it answers | Function |
| --- | --- | --- |
| Transaction boundary (`@Transactional`, `TransactionTemplate`, `TransactionalOperator`) | When does the scope start/end? | Declares or programmatically defines transaction rules |
| Transaction manager | Who begins/joins, commits, rolls back, and synchronizes resources? | Coordinates transactions suited to the storage technology |
| `DataSource` / `ConnectionFactory` / `EntityManagerFactory` | Where are data access resources obtained from? | Factory/pool or abstraction creating resources |
| `JdbcTemplate` / `DatabaseClient` / `EntityManager` / repository | Who executes SQL or persistence operations? | Provides data access APIs for business logic |
| JDBC/R2DBC `Connection` | Through which connection are changes performed? | Physical resource or logical handle managed within the transaction |
| Database | Where does the system ultimately store data? | Executes SQL and confirms/cancels transactions |

**Foundational rule:** a transaction manager does not automatically discover and group every SQL statement in an application. Data access code must use **the exact resource synchronized** with the manager. Having the same database URL or the same SQL statement is not enough to prove two operations belong to the same transaction.

## 2. Overall Graph: Two Parallel Paths

The following two diagrams are **bean wiring and execution flow graphs**; arrows labeled `begin/commit/rollback` indicate transaction control authority, while `acquire connection` arrows indicate the resource access path. They do not imply Spring always sends a SQL `BEGIN` on every method.

### 2.1. JDBC Branch, Synchronous Execution

~~~mermaid
flowchart LR
    A["Caller"] --> B["Spring proxy"]
    B --> C["TransactionInterceptor"]
    C -->|"begin / join / commit / rollback"| M["PlatformTransactionManager<br/>JdbcTransactionManager<br/>or DataSourceTransactionManager"]
    C -->|"call method"| S["Service @Transactional"]
    S --> D["DAO / Repository"]
    D --> J["JdbcTemplate"]
    J --> U["DataSourceUtils"]
    U --> H["Thread-bound Connection"]
    M -->|"acquire and manage"| DS["DataSource"]
    DS --> H
    H --> DB[("Database")]
~~~

View the graph as two branches **meeting at the connection**:

- **Control branch:** proxy → `TransactionInterceptor` → transaction manager → `DataSource` → connection. The manager holds commit or rollback authority.
- **Business branch:** service → DAO → `JdbcTemplate` → `DataSourceUtils` → transaction-bound connection. The DAO executes SQL; it does not decide commit on its own.

`JdbcTransactionManager` inherits `DataSourceTransactionManager`'s mechanism and adds translation of commit/rollback errors into the `DataAccessException` hierarchy in appropriate cases. Both use a `DataSource` for single-resource JDBC transactions. They **do not** automatically manage all databases or all `DataSource`s in the application.

### 2.2. R2DBC Branch, Reactive Execution

~~~mermaid
flowchart LR
    A["Subscriber"] --> B["Publisher from service"]
    B --> C["Transactional advice<br/>or TransactionalOperator"]
    C -->|"begin / join / commit / rollback"| M["ReactiveTransactionManager<br/>R2dbcTransactionManager"]
    C -->|"subscribe business flow"| S["Reactive service"]
    S --> D["Reactive DAO / Repository"]
    D --> J["DatabaseClient"]
    J --> U["ConnectionFactoryUtils"]
    U --> H["Connection bound to<br/>Reactor subscriber Context"]
    M -->|"acquire and manage"| CF["ConnectionFactory"]
    CF --> H
    H --> DB[("Database")]
~~~

In this branch, a method returning `Mono`/`Flux` only **describes** the computation. DB access and transaction initiation normally happen **when the Publisher is subscribed**; the subscriber context is the mechanism allowing operations in the pipeline to reuse the connection managed by `R2dbcTransactionManager`.

Both branches share the pattern "manager manages a factory, data-access code obtains resources through a transaction-aware utility." Structural similarity **does not mean** a JDBC `DataSource` and an R2DBC `ConnectionFactory` share contexts, connections, or commits with each other.

## 3. What Does Each Edge in the JDBC Graph Mean?

### 3.1. Manager and DataSource

`DataSource` (JDBC) is the standard factory for obtaining `java.sql.Connection`; implementations are typically connection pools such as HikariCP. `DataSourceTransactionManager`/`JdbcTransactionManager` receives **one specific `DataSource`** via constructor or setter. The manager uses connections from this source to set up transactions, coordinate isolation/read-only/timeout within supported limits, commit or rollback, and return resources to the pool.

In imperative Spring, `TransactionSynchronizationManager` maintains resource bindings for the **current thread**. With a JDBC manager, a `ConnectionHolder` is bound under a key tied to the transaction's `DataSource`. A DAO using the right `DataSource` can retrieve the already-bound connection instead of borrowing an independent connection.

Correct path:

~~~text
jdbcTxManager ──references──> mainDataSource ──provides──> JDBC Connection
paymentJdbcTemplate ──references──> mainDataSource
paymentJdbcTemplate ──DataSourceUtils──> Transaction-bound Connection
~~~

Suspicious path:

~~~text
jdbcTxManager ──> mainDataSource
paymentJdbcTemplate ──> auditDataSource
~~~

If `mainDataSource` and `auditDataSource` are two separate pools or uncoordinated wrappers, the first manager does not automatically control transactions from the second pool. Even two `DataSource`s pointing to the same database can hand out **two separate connections** with independent commit/rollback.

### 3.2. JdbcTemplate and DataSourceUtils

`JdbcTemplate` uses `DataSourceUtils` internally. `DataSourceUtils.getConnection(dataSource)` prioritizes a connection already bound to the transaction on the current thread; if none exists, it obtains an appropriate connection from `DataSource`. `DataSourceUtils.releaseConnection(connection, dataSource)` knows when **not** to close a connection still belonging to a transaction; the framework normally handles this automatically.

For hand-written plain JDBC wanting to participate in a Spring transaction, the proper way to acquire/release resources is:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Create PreparedStatement, bind parameters, execute SQL.
    // Specific JDBC calls are omitted in this mechanism example.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

This is an **illustrative snippet**, not a standalone program. Calling `dataSource.getConnection()` directly on an ordinary `DataSource` can create a new connection outside the Spring-bound transaction. For legacy libraries forced to call `DataSource.getConnection()`, you can investigate `TransactionAwareDataSourceProxy`; new Spring code should prefer `JdbcTemplate` or `DataSourceUtils`.

### 3.3. Sequence of a JDBC Transaction

1. Caller invokes a method on a **Spring bean proxy**; self-invocation via `this.method()` within the same bean bypasses advice in proxy mode.
2. `TransactionInterceptor` selects `PlatformTransactionManager` and `@Transactional` rules. With `REQUIRED`, if no current transaction exists it creates a new one; if one exists, it joins.
3. The manager acquires a JDBC connection from the corresponding `DataSource`, prepares transaction attributes (e.g., auto-commit), and binds the connection to the thread's transaction context.
4. The service calls the DAO; `JdbcTemplate` retrieves the connection via `DataSourceUtils` and executes SQL on that connection.
5. If the method completes successfully without rollback-only, the manager of **the outermost physical transaction** requests commit; if a rollback rule triggers or rollback-only is set, it rolls back.
6. The manager performs cleanup: runs needed synchronization callbacks, unbinds resources, restores connection state, and returns it to the source. An inner `REQUIRED` scope merely joins the transaction and does not physically commit on its own.

Do not confuse a **singleton bean** like `JdbcTemplate` with a **single connection**: the template is shared across requests/threads; each transaction has its own resource context. Conversely, within a single transaction scope, multiple `JdbcTemplate` calls can use **the same active connection**.

## 4. What Does Each Edge in the R2DBC Graph Mean?

### 4.1. ReactiveTransactionManager and ConnectionFactory

`ConnectionFactory` is the **R2DBC** interface providing publishers that create `io.r2dbc.spi.Connection`. `R2dbcTransactionManager` manages a `ConnectionFactory` and binds the connection to the **subscriber Context**. It can begin/commit/rollback on the R2DBC connection and release resources via the reactive lifecycle.

Spring Framework's `DatabaseClient` is the non-blocking SQL API; operations from the client acquire connections transaction-awarely via `ConnectionFactoryUtils`. This pairs analogously with `JdbcTemplate` + `DataSourceUtils` in the JDBC branch:

| Imperative JDBC | Reactive R2DBC |
| --- | --- |
| `PlatformTransactionManager` | `ReactiveTransactionManager` |
| `JdbcTransactionManager`/`DataSourceTransactionManager` | `R2dbcTransactionManager` |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| `JdbcTemplate` | `org.springframework.r2dbc.core.DatabaseClient` |
| `DataSourceUtils` | `ConnectionFactoryUtils` |
| Thread-bound resource | Reactor subscriber Context-bound resource |
| Logic executes immediately during method call | Publisher normally executes upon subscription |

Calling `connectionFactory.create()` directly in a DAO does not automatically retrieve the Spring-managed connection. When low-level R2DBC operations are needed, use `ConnectionFactoryUtils.getConnection(factory)` and its corresponding release mechanism, or prefer `DatabaseClient`. For third-party R2DBC clients not integrated with Spring, `TransactionAwareConnectionFactoryProxy` exists for suitable cases; this proxy does not turn a JDBC `DataSource` into R2DBC.

### 4.2. Reactive Context Is Not ThreadLocal

A pipeline can switch threads during execution while preserving the subscriber's transaction context. The essential condition is that operations **remain inside the same reactive pipeline/context**, using the right `ConnectionFactory`. There is no "same thread means same transaction" rule for R2DBC; conversely, another thread in imperative JDBC does not automatically inherit a transaction just because it was spawned from a `@Transactional` method.

A reactive method advised by `ReactiveTransactionManager` must return an appropriate reactive type, such as `Mono<Void>` or `Flux<T>`. Do not call `subscribe()` yourself inside a service to run an independent branch and return: that branch can run outside the transaction the caller expects. If nobody subscribes to the returned publisher, reactive work and the transaction usually **do not run** either.

### 4.3. R2DBC Graph with Bean Wiring and a Pipeline

Below is **illustrative configuration and service code in a Spring application that already has a `ConnectionFactory` bean, R2DBC driver, and `wallet` table**. It is not a standalone runnable application because bootstrap and database configuration are omitted:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Configuration
@EnableTransactionManagement
class ReactiveWiring {
    @Bean
    ReactiveTransactionManager r2dbcTx(ConnectionFactory factory) {
        return new R2dbcTransactionManager(factory);
    }

    @Bean
    DatabaseClient databaseClient(ConnectionFactory factory) {
        return DatabaseClient.create(factory);
    }
}

@Service
class ReactiveTransferService {
    private final DatabaseClient db;

    ReactiveTransferService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional(transactionManager = "r2dbcTx")
    public Mono<Void> transfer(int from, int to, long amount) {
        Mono<Void> debit = db.sql(
                "UPDATE wallet SET balance = balance - :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", from)
            .fetch()
            .rowsUpdated()
            .flatMap(n -> n == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException("debit must update one row")));

        Mono<Void> credit = db.sql(
                "UPDATE wallet SET balance = balance + :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", to)
            .fetch()
            .rowsUpdated()
            .flatMap(n -> n == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException("credit must update one row")));

        return debit.then(credit);
    }
}
~~~

Here `r2dbcTx` and `DatabaseClient` receive **the exact same `ConnectionFactory` bean injected by Spring**. Both `UPDATE` statements are chained sequentially via `then`; when the publisher is subscribed through the Spring proxy, they execute inside the reactive transaction. If either debit or credit errors, the default rollback rule for `RuntimeException` requests rollback. The example assumes the driver supports the operations and the `wallet` table has suitable `id` and `balance` columns. In a Spring Boot application, if `DatabaseClient`/manager are already auto-configured, reuse existing beans rather than registering unnecessary duplicates.

## 5. JPA Graph: Manager Linked to EntityManagerFactory

With JPA, `JpaTransactionManager`'s direct target is `EntityManagerFactory`; operations normally go through `EntityManager` or Spring Data JPA repositories, not directly through `JdbcTemplate`:

~~~mermaid
flowchart LR
    A["Caller"] --> P["Transactional proxy"]
    P --> T["JpaTransactionManager"]
    P --> S["Service"]
    S --> R["JPA Repository"]
    R --> E["EntityManager<br/>bound to transaction"]
    T --> F["EntityManagerFactory"]
    F --> E
    F --> DS["JPA provider's DataSource"]
    DS --> C["JDBC Connection"]
    E --> C
    C --> DB[("Database")]
~~~

`EntityManagerFactory` is the factory typically shared across the application; `EntityManager` is a persistence context whose lifecycle and scope align with the transaction, **not a singleton `EntityManager` shared across all threads**. With Spring Data JPA, repositories typically operate through a Spring-managed/synchronized `EntityManager`.

There are cases of **mixing JPA and JDBC** on **the same `DataSource`** within a transaction managed by `JpaTransactionManager`: Spring can allow JDBC code to access the corresponding connection via `DataSourceUtils` if the `JpaDialect`/JPA provider and configuration support it. Do not infer this merely because two beans share the same URL. When an application declares **both `JpaTransactionManager` and `JdbcTransactionManager` for the same DB**, choosing the wrong manager can make the two parts run in separate transactions; explicitly design and verify which manager the entrypoint uses.

JPA `flush()` only synchronizes persistence context changes to the DB; **it is not equivalent to commit**. The purpose of the JPA graph is to point directly to the transaction owner (`JpaTransactionManager` → `EntityManagerFactory`) and the path business code takes to access data (repository → `EntityManager`).

## 6. How to Wire Beans Properly in an Application

An effective way to read configuration is to trace from **service entrypoint** to **manager**, and then from manager and DAO back to **factory**.

| Need | Typically suitable transaction manager | Factory that must match | Commonly used access API |
| --- | --- | --- | --- |
| Pure JDBC, single DB | `JdbcTransactionManager` or `DataSourceTransactionManager` | `DataSource` | `JdbcTemplate`, Spring JDBC repositories |
| JPA (Hibernate or another JPA provider) | `JpaTransactionManager` | `EntityManagerFactory`, with `DataSource` under JPA provider | `EntityManager`, Spring Data JPA |
| Reactive R2DBC, single DB | `R2dbcTransactionManager` | `ConnectionFactory` | `DatabaseClient`, Spring Data R2DBC repositories |
| JTA/XA when coordination infrastructure fits | `JtaTransactionManager` | Transaction coordinator and enlisted resources | JDBC/JPA configured to participate in JTA |

When there is only one manager, `@Transactional` usually resolves the default manager via Spring/Boot configuration. When multiple managers exist, choose by bean name or qualifier:

~~~java
@Transactional(transactionManager = "ordersJdbcTx")
public void saveOrder() { /* JDBC business snippet */ }

@Transactional(transactionManager = "catalogJpaTx")
public void updateCatalog() { /* JPA business snippet */ }

@Transactional(transactionManager = "reportR2dbcTx")
public Mono<Void> refreshReport() {
    return Mono.empty(); // Illustrates reactive return type only.
}
~~~

These three methods are **illustrative signatures**, not a standalone runnable program. `@Transactional("ordersJdbcTx")` selects **one** manager; it does not automatically coordinate all three managers into a distributed transaction. With multiple `DataSource`s, each manager must be wired to the intended `JdbcTemplate`/repositories; the same applies to multiple `ConnectionFactory` beans.

### Minimal JDBC Configuration Example Showing Bean Edges Only

~~~java
@Configuration
@EnableTransactionManagement
class JdbcWiring {
    @Bean
    PlatformTransactionManager ordersJdbcTx(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }
}
~~~

This is an **excerpt**: it assumes an `ordersDataSource` bean exists and `@Configuration`, `@Bean`, `@Qualifier`, `DataSource`, `PlatformTransactionManager`, `JdbcTransactionManager`, and `JdbcTemplate` are imported. It clearly shows the relationship:

~~~text
ordersJdbcTx ─────┐
                  ├──> ordersDataSource
ordersJdbc ───────┘
~~~

**A manager bean and a template bean referencing the same connection source bean** is the right sign structurally. Still, verify that calls pass through the proxy, transactions are activated, and DAOs actually use the right template; correct dependency injection alone is not enough to prove runtime behavior.

## 7. Runnable Example: Verifying Same Connection and Rollback with Spring JDBC

This example uses Java 17+, Spring Boot 3.3.5 (Spring Framework 6.x), Maven, and in-memory H2. Its goal is to verify the **JDBC graph with real data**, rather than reading annotations and guessing. There are exactly three files; no web server, JPA, or R2DBC is needed in this runnable example.

Structure:

~~~text
tx-graph-demo/
├── pom.xml
└── src/main/java/example/txgraph/
    ├── TxGraphApplication.java
    └── TransferService.java
~~~

**File `pom.xml`:**

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
    <artifactId>tx-graph-demo</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
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

**File `src/main/java/example/txgraph/TxGraphApplication.java`:**

~~~java
package example.txgraph;

import java.util.LinkedHashMap;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxGraphApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxGraphApplication.class, args);
    }

    // Manager and JdbcTemplate receive the same Spring Boot DataSource bean.
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfer) {
        return args -> {
            jdbc.execute("CREATE TABLE wallet (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 2, 50);

            System.out.println("Before: " + balances(jdbc));

            try {
                transfer.move(1, 2, 20, true);
            } catch (IllegalStateException ex) {
                System.out.println("Rollback because: " + ex.getMessage());
            }
            System.out.println("After rollback: " + balances(jdbc));

            transfer.move(1, 2, 20, false);
            System.out.println("After commit: " + balances(jdbc));
        };
    }

    private static Map<Integer, Integer> balances(JdbcTemplate jdbc) {
        return jdbc.query("SELECT id, balance FROM wallet ORDER BY id", rs -> {
            Map<Integer, Integer> rows = new LinkedHashMap<>();
            while (rs.next()) {
                rows.put(rs.getInt("id"), rs.getInt("balance"));
            }
            return rows;
        });
    }
}
~~~

**File `src/main/java/example/txgraph/TransferService.java`:**

~~~java
package example.txgraph;

import java.sql.Connection;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;

    public TransferService(DataSource dataSource, JdbcTemplate jdbc) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
    }

    @Transactional
    public void move(int from, int to, int amount, boolean failAfterDebit) {
        Connection first = DataSourceUtils.getConnection(dataSource);
        try {
            Connection second = DataSourceUtils.getConnection(dataSource);
            try {
                System.out.println("Same connection: " + (first == second));
            } finally {
                DataSourceUtils.releaseConnection(second, dataSource);
            }

            int updated = jdbc.update(
                "UPDATE wallet SET balance = balance - ? WHERE id = ? AND balance >= ?",
                amount, from, amount
            );
            if (updated != 1) {
                throw new IllegalStateException("insufficient balance");
            }
            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }
            updated = jdbc.update(
                "UPDATE wallet SET balance = balance + ? WHERE id = ?",
                amount, to
            );
            if (updated != 1) {
                throw new IllegalStateException("destination absent");
            }
        } finally {
            DataSourceUtils.releaseConnection(first, dataSource);
        }
    }
}
~~~

Run in the `tx-graph-demo` directory (requires JDK 17+ and Maven; Maven downloads dependencies if not cached):

~~~bash
mvn spring-boot:run
~~~

Lines printed by the program, **excluding Spring/Hikari startup logs**:

~~~text
Before: {1=100, 2=50}
Same connection: true
Rollback because: simulated failure
After rollback: {1=100, 2=50}
Same connection: true
After commit: {1=80, 2=70}
~~~

Explanation based on the graph:

1. `@SpringBootApplication` creates the Spring context; Boot provides an H2 `DataSource` and a `JdbcTemplate` using that exact source. The `transactionManager` bean is explicitly configured as `JdbcTransactionManager(dataSource)`.
2. `CommandLineRunner` calls `transfer.move(...)` through the **Spring-injected bean**, so transaction advice applies. Calling directly via `new TransferService(...)` would no longer demonstrate proxy transactions.
3. Both calls to `DataSourceUtils.getConnection(dataSource)` inside the same transaction return the same thread-bound connection. Both references are properly released; Spring does not prematurely close a connection still belonging to a transaction.
4. `jdbc.update(...)` goes through `JdbcTemplate` and `DataSourceUtils`, so the UPDATEs join the exact connection controlled by the manager.
5. On the first call, the debit succeeds, then `IllegalStateException` escapes the transactional method. Spring rolls back, keeping both balances unchanged. The `catch` sits **outside the service proxy**, not swallowing the exception before advice sees it.
6. On the next call, both UPDATEs succeed and the method returns normally, so the manager commits. Both balances shift by exactly 20 units.

`first == second` is clear evidence for the connection **`DataSourceUtils` returns in this transaction**, not a comprehensive test for every pool/proxy configuration; another vital verification is that data changes rolled back/committed as expected. Temporarily removing `@Transactional` (only in the temporary demo project) will show why using the same `DataSource` cannot be treated as an automatic transaction guarantee.

## 8. Three Graphs Commonly Miswired

### Case A — Manager and DAO Use Two Different DataSources

~~~text
Service @Transactional -> jdbcTxManager -> dataSourceMain -> connection #1
                  DAO -> jdbcTemplateAudit -> dataSourceAudit -> connection #2
~~~

A transaction of `jdbcTxManager` only manages connections under that manager's responsibility. Connection #2 does not automatically join transaction #1. If statements on #1 roll back while #2 auto-committed, the system can persist half a business operation.

**How to fix:** clearly decide which data belongs in one transaction, and inject the same source into the manager and all participating DAOs. If atomicity across multiple independent resources is genuinely required, design an appropriate transaction coordinator (e.g., JTA/XA where supported), or use outbox/saga per business requirements. Do not solve this by sprinkling `@Transactional` on every method.

### Case B — R2DBC and JDBC Pointing to the Same Database

~~~text
@Transactional with R2dbcTransactionManager
    -> ConnectionFactory -> R2DBC Connection

JdbcTemplate
    -> DataSource -> JDBC Connection
~~~

The two connections belong to **two different drivers/APIs and two different transaction contexts**. `R2dbcTransactionManager` does not control a JDBC `Connection`, and `JdbcTransactionManager` does not control an R2DBC `Connection`. Pointing to the same database host/schema does not make them share a transaction. Mixing blocking and reactive styles also introduces scheduling/execution-thread risks.

**How to fix:** keep work requiring atomicity within the same technology/resource supported by one manager, or design explicit coordination between the two systems; never assume one annotation guarantees atomicity across both.

### Case C — Two Managers of the Same Type, Wrong One Chosen

~~~text
@Transactional("ordersTx") -> ordersTx -> ordersDataSource
orderJdbcTemplate ----------> ordersDataSource

@Transactional("auditTx")  -> auditTx  -> auditDataSource
auditJdbcTemplate ----------> auditDataSource
~~~

This is a completely valid configuration if the business accepts **two independent transactions**. However, when a service calls both DAOs inside one method annotated `@Transactional("ordersTx")`, that single annotation **does not** cause `auditDataSource` to commit together. Even if both managers target the same DB server, you still must check which connections/resources they manage.

When multiple transaction managers exist, inspect `@Transactional(transactionManager = "...")`, bean names/qualifiers, `TransactionManagementConfigurer` (if present), and the actual injected factory beans. A dangerous case is an application starting normally and passing all "happy path" tests, only revealing the desynchronization when a failure occurs between UPDATEs.

## 9. How to Draw/Read the Graph of a Real Module

For each service entrypoint requiring a transaction, follow this order:

1. **Find the boundary:** which method has `@Transactional`, `TransactionTemplate`, or `TransactionalOperator`? Is it called through a proxy/using the operator properly?
2. **Identify the execution model:** does the method return a synchronous value/`void`, or return `Mono`/`Flux`? A `PlatformTransactionManager` serves imperative; a `ReactiveTransactionManager` serves reactive.
3. **Find the actual manager:** which bean name is selected? With multiple managers, how do annotation/qualifier/primary/default resolvers decide?
4. **Find the factory:** which `DataSource`, `ConnectionFactory`, or `EntityManagerFactory` does the manager reference? Is there a wrapper/proxy/routing factory?
5. **Find the access code:** which factory does the repository/template/client for each SQL statement use? Does raw JDBC code use `DataSourceUtils`, or grab a connection directly?
6. **Identify the synchronization context:** in JDBC, are the source and thread properly bound to the resource? In R2DBC, does the pipeline preserve subscriber context without spawning detached subscriptions?
7. **Verify with a failure test:** intentionally fail after the first write statement; after the transaction finishes, read data from another session to confirm both changes commit together or roll back together.

Example verification table for a service with two DAOs:

| Edge to cross-check | Expected condition | Signs requiring investigation |
| --- | --- | --- |
| `Service -> transactionManager` | Manager matches the chosen technology and source | Ambiguity with multiple managers; wrong qualifier |
| `Manager -> factory` | Exact resource source bean | Similar names, multiple pools with the same URL |
| `DAO -> template/client -> factory` | Same source as manager if sharing a transaction | DAO uses a different pool or client |
| `Factory -> connection -> context` | Connection is Spring-synchronized | Raw `getConnection()` or `create()` bypassing helpers |
| `Scope -> completion` | Commit/rollback outcome matches requirements | Swallowed exception, unsubscribed publisher |
| `Cross-resource boundary` | Coordination designed if multi-resource atomicity is needed | Only using one `@Transactional` across multiple pools |

### Observing at Runtime Without Changing Business Logic

For imperative JDBC, you can enable DEBUG logging for `org.springframework.transaction` and `org.springframework.jdbc.datasource` in test environments. Logs usually show transaction creation/joining, connection acquisition/release, and commit/rollback, depending on implementation/version. When debugging manually, `TransactionSynchronizationManager.isActualTransactionActive()` indicates an active transaction context on the thread; it **does not** prove the DAO uses the right `DataSource`. When needed, inspect `TransactionSynchronizationManager.getResource(dataSource)` in a debugger to view the specific source binding; do not turn this internal check into business logic.

For reactive code, trace the pipeline and subscription points, enabling transaction/R2DBC logging in test environments. Do not apply JDBC's `ThreadLocal` inspection to conclude R2DBC has no transaction. Prefer **an integration test failing after the first write step** and verifying DB state; that is more objective than only reading logs.

### Misconceptions to Avoid

- `@Transactional` is metadata: without valid advice/manager or when self-invocation bypasses the proxy, behavior may differ from expectations.
- Both `DataSource` and `ConnectionFactory` create "connections", but belong to two different SPIs; never inject one in place of the other.
- `JdbcTemplate` and `DatabaseClient` are reusable objects, which does not mean a template/client holds one fixed connection for all requests.
- `DataSourceTransactionManager` does not automatically see every pool in the `ApplicationContext`.
- `EntityManagerFactory` differs from `EntityManager`: JPA transactions follow the corresponding persistence context, not simply "JpaTransactionManager pointing directly at JdbcTemplate".
- JPA `flush` or `rowsUpdated()`/`update()` succeeding is not proof the outermost transaction committed.
- `@Transactional(readOnly = true)` is a directive/hint; enforcement depends on manager, driver, and database. Do not use it in place of DB read-only permissions.
- `REQUIRES_NEW` may use an independent connection while the outer transaction is suspended; do not assume the two scopes always share one connection.
- Changes in a database transaction do not automatically undo emails, HTTP calls, or messages sent outside the transactional resource; use an integration pattern like outbox if consistency is required.

## 10. Graph-Reading and Outcome-Prediction Exercises

**Exercise 1 — same DataSource:** A `@Transactional("mainTx")` service calls two DAOs. `mainTx` and both `JdbcTemplate`s use the same `mainDataSource` bean; the method is called through the proxy. The first DAO updates A, the second DAO throws `IllegalStateException` out of the service. Prediction: with default `REQUIRED` propagation, both DAOs participate in one transaction, so both in-transaction changes are rolled back. Confirm with an integration test.

**Exercise 2 — different DataSource:** Keep the same service, except the second DAO uses `auditDataSource` and auto-commits. Prediction: rolling back `mainTx` is not guaranteed to undo changes made via `auditDataSource`. Redraw the graph adding a second connection to see where the transaction splits.

**Exercise 3 — unsubscribed Publisher:** A reactive service returning `Mono<Void>` is annotated `@Transactional("r2dbcTx")`, but the caller discards the return value without subscribing. Prediction: the pipeline does not execute, so DB operations and the reactive transaction do not normally start.

**Exercise 4 — JPA and JDBC:** A JPA repository and a `JdbcTemplate` see the same DB URL. Can you conclude both share a transaction managed by `JpaTransactionManager`? **No**. You must check the provider, `JpaDialect`, `EntityManagerFactory`, `DataSource`, how connections are acquired, and actual behavior during rollback.

## 11. Model Summary

**JDBC model:** `@Transactional` → `TransactionInterceptor` → `JdbcTransactionManager`/`DataSourceTransactionManager` → **`DataSource`** ↔ `DataSourceUtils` ← `JdbcTemplate` ← DAO.

**R2DBC model:** `@Transactional` or `TransactionalOperator` → **`R2dbcTransactionManager` → `ConnectionFactory`** ↔ `ConnectionFactoryUtils` ← `DatabaseClient` ← reactive DAO; bound to **Reactor subscriber Context**.

**JPA model:** `@Transactional` → **`JpaTransactionManager` → `EntityManagerFactory`** ↔ `EntityManager` ← JPA repository; JPA provider uses a JDBC `DataSource` underneath.

A correct transaction graph must answer all three questions: **which factory does the manager manage; which factory does data access code use; and which connection actually undergoes commit/rollback?** Only when all three answers align within a supported transaction manager's boundaries is there basis to trust that data operations will commit or roll back together.

## Official References

- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html).
- Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Controlling JDBC Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html).
- Spring Framework — [Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html).
- Spring Framework — [Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html).
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
