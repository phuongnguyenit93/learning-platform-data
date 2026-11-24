# Relationship Between AOP, Data Access, and Resource Management in Spring Transaction Management

## 1. The big picture

In a business operation such as transferring money, placing an order, or updating inventory, multiple data operations must be treated as **one unit of work**: either all required changes are committed, or they are rolled back according to transaction policy. In Spring, three mechanisms collaborate to make this happen:

1. **AOP (Aspect-Oriented Programming)** determines *when* a method call must be wrapped with transaction logic. With the common declarative approach, Spring creates a proxy and attaches `TransactionInterceptor` to eligible invocations.
2. **Transaction management** determines *which transaction* to begin/join/end. `PlatformTransactionManager` coordinates the transaction and the state of involved resources; the storage system itself performs the physical commit/rollback.
3. **Data access and resource management** execute SQL/JPA operations and use the exact resource participating in the transaction, such as a JDBC `Connection` or JPA `EntityManager`. Spring acquires, binds, reuses, and releases these resources according to the lifecycle.

The three layers have distinct responsibilities. The `@Transactional` annotation **does not execute SQL, create connections, or guarantee atomicity on its own**. It supplies metadata so the transaction infrastructure, typically via AOP, establishes a transaction boundary; actual data mutations are still carried out by the DAO/repository and the database.

| Component | Primary responsibility | Typical example |
| --- | --- | --- |
| AOP proxy + `TransactionInterceptor` | Intercepts calls through the proxy, reads `@Transactional` metadata, wraps the method with advice | Calling `orderService.placeOrder()` |
| `PlatformTransactionManager` | Decides begin/join, commit/rollback; coordinates transaction and resource state | `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager` |
| Data access layer | Executes queries/updates, translates exceptions, works through appropriate APIs | `JdbcTemplate`, Spring Data JPA repository |
| Actual resource | Holds physical transaction state and applies commit/rollback | JDBC `Connection`, JPA `EntityManager` with transaction backend, DB transaction |
| Resource synchronization infrastructure | Binds resources to the execution context and cleans them up on completion | `TransactionSynchronizationManager`, `DataSourceUtils` |

> The scope of this lesson is the **relationship** between these layers. Topics such as isolation, advanced propagation, distributed transactions, and performance tuning are introduced only as needed to understand how the layers interact.

## 2. Path of a `@Transactional` call

Suppose an HTTP controller calls a Spring bean named `transferService`; this bean has a `transfer()` method annotated with `@Transactional`. With typical imperative transactions, the conceptual path is:

```text
Controller / caller
       |
       v
Spring AOP proxy of TransferService
       |
       v
TransactionInterceptor (reads @Transactional)
       |
       v
PlatformTransactionManager
       |-- resolves existing transaction / creates new transaction
       |-- prepares and binds required resources
       |
       v
TransferService.transfer()  <-- actual business method
       |
       +--> AccountRepository.debit()
       |            |
       |            +--> JdbcTemplate / JPA
       |
       +--> AccountRepository.credit()
                    |
                    +--> same compatible transaction context
       |
       v
Method returns or throws exception
       |
       v
TransactionInterceptor / TransactionManager
       |-- commit if succeeded and transaction is committable
       |-- roll back / mark rollback-only if rules require
       +-- clear synchronizations and resources, return connection to pool
```

Step-by-step explanation:

1. **The caller obtains the bean from the Spring container.** When transaction configuration is active, the caller normally interacts with a proxy rather than directly invoking an instance created manually with `new`.
2. **The proxy enters the interceptor.** The interceptor reads transaction attributes applicable to the method, such as `propagation`, `readOnly`, `isolation`, `timeout`, and rollback rules.
3. **The transaction manager determines scope.** With default `Propagation.REQUIRED`, it joins the existing transaction if one exists; otherwise it starts a new transaction. Not every `@Transactional` method creates a separate physical transaction.
4. **Resource management infrastructure.** With typical JDBC, the transaction manager works with a connection from the `DataSource`, sets required transaction attributes, and binds the connection to the execution thread. The exact moment a connection is acquired can depend on configuration and lazy acquisition mechanisms.
5. **Business code invokes data-access APIs.** `JdbcTemplate` or repositories use a resource compatible with the current transaction. Multiple SQL statements within the same scope can share one JDBC connection and one physical transaction.
6. **When the method exits, the interceptor decides the outcome per transaction scope.** If this scope owns the physical transaction and is eligible to commit, the manager commits; if rollback is required, the manager rolls back. A scope participating in a caller's transaction may only mark rollback-only so the outer transaction decides completion.
7. **Spring cleans up state.** Synchronization callbacks run according to the lifecycle; resources are unbound from context and connections are released. With connection pools, "closing" on the application side normally means **returning the connection to the pool**, not tearing down the physical socket to the DB.

**Key takeaway:** AOP sits at the method-call boundary; the transaction manager sits at the transaction boundary; data-access APIs and resources ensure each data operation actually participates in that transaction.

## 3. Why use AOP instead of writing `commit()` in every service?

Without declarative support, a manual JDBC operation must acquire a `Connection`, disable auto-commit, run multiple statements, call `commit()` or `rollback()`, then restore state and release the connection. Repeating this logic across services clutters code, risks missed cleanup, and makes policy changes hard to apply consistently.

AOP separates **cross-cutting infrastructure logic** from **business logic**:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.items());
    }
}
```

The snippet above is **illustrative code**, assuming `Order`, both repositories, and their methods are defined. It describes a business boundary: if both repositories use resources compatible with the **same transaction manager**, and an error triggers transaction rollback, both saving the order and reserving inventory roll back in the DB transaction. AOP does not need to intercept each SQL statement individually; it wraps the *entire* `placeOrder` call.

Spring AOP can use JDK dynamic proxies (interface-based) or class-based proxies. In default `proxy` mode, only calls **passing through the proxy** are intercepted by advice. Interception capabilities depend on method/class modifiers and proxy type; the cleanest, most reliable convention is placing `@Transactional` on **public methods of Spring-managed service beans**, called from another bean or external caller.

`@Transactional` is only metadata. Active transaction management infrastructure is required, such as `@EnableTransactionManagement` in plain Spring applications or appropriate auto-configuration in Spring Boot, along with a properly selected transaction manager.

## 4. How does data access share a transaction?

### 4.1 JDBC: `DataSource`, `Connection`, `JdbcTemplate`

In a typical imperative JDBC flow:

- `DataSource` is the source of connections, typically backed by a pool. A `DataSource` is **not synonymous** with a transaction.
- A JDBC `Connection` is the object tied to the physical transaction for that database. Statements executed through this connection can belong to the same transaction.
- `DataSourceTransactionManager` (or the appropriate JDBC variant) manages local JDBC transactions for a `DataSource`; `JdbcTransactionManager` adds Spring-style exception translation for commit/rollback failures.
- `TransactionSynchronizationManager` manages thread-bound state and resources at the infrastructure layer. For imperative transactions, a connection holder can be bound keyed by `DataSource`.
- `JdbcTemplate` delegates to `DataSourceUtils` to acquire/release connections according to Spring context. Thus multiple `jdbc.update(...)` calls within the same Spring-managed transaction can share a connection without business code manually passing a `Connection`.
- `JdbcTemplate` also manages short-lived resources like `Statement` and `ResultSet`; that is **distinct** from ending the transaction or returning the connection held by the transaction.

Example within a transactional service call:

```java
@Transactional
public void renameAndActivate(long id, String name) {
    jdbcTemplate.update("UPDATE account SET display_name = ? WHERE id = ?", name, id);
    jdbcTemplate.update("UPDATE account SET active = TRUE WHERE id = ?", id);
}
```

This is an **illustrative method**, assuming `jdbcTemplate` and the `account` table exist. If they use the same `DataSource`/manager and the connection participates in the transaction, both `UPDATE`s belong to the same local JDBC transaction. Running both statements outside a transaction scope normally offers no atomicity guarantee across both statements; many JDBC configurations default to auto-commit per statement.

When plain JDBC must be used inside a Spring transaction, respect the connection binding mechanism:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE account SET active = TRUE WHERE id = ?")) {
    statement.setLong(1, id);
    statement.executeUpdate();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

This is also an **illustrative snippet** requiring `dataSource`/`id` variables, JDBC imports, and execution context. Do not call `connection.commit()` or `connection.rollback()` inside DAO code when Spring coordinates the transaction. `releaseConnection` avoids closing a connection held by an active transaction; when no transaction is active, it releases it appropriately. Usually you should prefer `JdbcTemplate` to avoid managing these details.

Calling `dataSource.getConnection()` directly from arbitrary code may obtain a separate connection that does not automatically join the thread-bound Spring connection (unless using a transaction-aware adapter such as `TransactionAwareDataSourceProxy`). That is a common cause of the bug "annotated with `@Transactional`, yet one operation still commits on its own."

### 4.2 JPA/Hibernate: `EntityManager` and persistence context

When using JPA, `JpaTransactionManager` manages local JPA transactions and the participation of the `EntityManager`/persistence context. `@PersistenceContext` and Spring Data JPA repositories provide transaction-aware access to the `EntityManager` without forcing services to open/close it manually. Hibernate `Session` is the underlying implementation layer when Hibernate serves as the JPA provider.

Two concepts must be kept distinct:

- **`flush`** synchronizes pending changes in the persistence context as SQL operations sent to the database; it is **not synonymous** with commit.
- **`commit`** completes the transaction successfully according to the transaction manager/database mechanism. Flushed SQL can still be rolled back if the transaction has not committed.

Do not assume that having a single `DataSource` automatically makes every JDBC API, JPA API, and non-Spring tool share the same transaction. Coordinating JDBC and JPA depends on configuring `JpaTransactionManager`, a unified `DataSource`, and acquiring connections through compatible mechanisms. When multiple databases or multiple transaction managers exist, clearly establish which resource belongs to which transaction.

### 4.3 Resource mapping table

| Technology | Common access API | Common manager | Context / resource |
| --- | --- | --- | --- |
| JDBC | `JdbcTemplate`, Spring JDBC repository | `JdbcTransactionManager` / `DataSourceTransactionManager` | JDBC `Connection` bound to `DataSource` |
| JPA/Hibernate | Spring Data JPA, `EntityManager` | `JpaTransactionManager` | JPA transaction, `EntityManager` / persistence context |
| Multiple resources with coordinator | Environment/JTA APIs | `JtaTransactionManager` | Transaction managed by JTA coordinator; requires corresponding infrastructure |
| Reactive R2DBC | `DatabaseClient`, reactive repository | `R2dbcTransactionManager` | Reactive `Connection`, state via Reactor Context |

**Do not confuse Spring's `Resource` interface** (an abstraction for classpath/file/URL access) with a "transactional resource." Reading/writing files via `Resource` does not automatically become an operation that rolls back with the DB.

## 5. Complete example: two JDBC statements committing or rolling back together

This small example uses **Java 17**, **Spring Boot 3.3.5**, **Spring JDBC**, and in-memory H2. Spring Boot auto-configures `DataSource`, `JdbcTemplate`, and the appropriate JDBC transaction manager in this single-database setup. It can run standalone with Maven 3.9+ and JDK 17+.

Create two files following this layout:

```text
transaction-demo/
├── pom.xml
└── src/main/java/example/TxDemoApplication.java
```

File `pom.xml`:

```xml
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
    <artifactId>transaction-demo</artifactId>
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

File `src/main/java/example/TxDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class TxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService service) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE accounts (
                        id VARCHAR(20) PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO accounts(id, balance) VALUES (?, ?)", "A", 100);
            jdbc.update("INSERT INTO accounts(id, balance) VALUES (?, ?)", "B", 50);

            try {
                service.transfer("A", "B", 30, true);
            } catch (IllegalStateException expected) {
                System.out.println("Rolled back after simulated failure");
            }
            printBalances(jdbc, "After failure");

            service.transfer("A", "B", 30, false);
            printBalances(jdbc, "Success");
        };
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?", Integer.class, "A");
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?", Integer.class, "B");
        System.out.println(label + ": A=" + a + ", B=" + b);
    }

    @Service
    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(String from, String to, int amount, boolean failAfterDebit) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int updated = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                    amount, from);
            if (updated != 1) {
                throw new IllegalArgumentException("source account not found");
            }

            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }

            updated = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (updated != 1) {
                throw new IllegalArgumentException("destination account not found");
            }
        }
    }
}
```

Run from the `transaction-demo` directory:

```bash
mvn -q spring-boot:run
```

In the output (aside from environment-dependent startup messages), the program prints these exact lines:

```text
Rolled back after simulated failure
After failure: A=100, B=50
Success: A=70, B=80
```

Why?

1. The two initial `INSERT` statements seed test data. The `TransferService` object is a **Spring bean** injected into `CommandLineRunner`; calling `service.transfer(...)` goes through the proxy.
2. The first call debits `30` from A, then throws `IllegalStateException` before crediting B. `TransactionInterceptor` sees the unchecked exception escape the method and requests rollback: balances remain `100` and `50`.
3. The second call executes both debit and credit and returns normally: the transaction manager commits; balances become `70` and `80`.
4. Both `jdbc.update` calls inside one `transfer` share the Spring-managed JDBC transaction. The service never creates a `Connection` or calls `commit()` itself.

**Intentional limitations of the demo:** no balance-sufficiency check, concurrency control, or locking policy is included; do not use directly as production transfer code. The goal is to observe the boundary between AOP, data access, and transaction resources.

## 6. Where is `@Transactional` placed, and how do operations participate?

Place transaction boundaries at the **service/use-case** layer when multiple steps form one business unit. Repositories focus on data access and should not need to know orchestration logic for the entire business operation.

```text
PlaceOrderService.placeOrder()  @Transactional(REQUIRED)
    |-- OrderRepository.save(order)
    |-- InventoryRepository.reserve(items)
    +-- PaymentRecordRepository.save(record)
           \--> DB operations sharing compatible manager/resource
```

If all repositories join the same active transaction, rolling back that transaction cancels all their uncommitted changes. If a repository uses another resource, another manager, or an independently opened connection, **shared atomicity does not happen automatically**.

A repository method also annotated with `@Transactional(REQUIRED)` does not necessarily open a second physical transaction; when invoked inside a transactional service, it typically **joins** the active transaction. `REQUIRES_NEW` is different: it requests an independent transaction, potentially acquiring an extra connection while the outer transaction still holds its resource.

Key `@Transactional` attributes to understand in this relationship:

| Attribute | Meaning at the AOP/transaction boundary | Resource considerations |
| --- | --- | --- |
| `propagation=REQUIRED` (default) | Joins current transaction or starts a new one | Multiple logical scopes can share one physical transaction |
| `propagation=REQUIRES_NEW` | Suspends outer transaction and uses a new physical transaction | May require an additional connection; small pools can be exhausted |
| `propagation=NESTED` | Nested scope via savepoint when supported by manager and DB | Typically tied to JDBC savepoints; not an independent transaction |
| `readOnly=true` | Expresses read-only intent / optimization hint to manager and provider | Not a strict barrier blocking all writes across every DB |
| `isolation`, `timeout` | Requests isolation/timeout for a new transaction per actual support | Does not alter isolation of an already-joined transaction |
| `rollbackFor` | Adds exception types that trigger rollback | Useful for checked exceptions |
| `transactionManager` | Explicitly specifies which manager to use when multiple exist | Wrong manager may fail to manage the DAO's resource |

With `REQUIRED`, if an inner call marks the transaction **rollback-only** and the outer caller still attempts to commit, Spring may throw `UnexpectedRollbackException`. This prevents the caller from mistakenly believing writes were committed.

## 7. Boundaries that AOP does not cross automatically

### 7.1 Self-invocation within the same bean

```java
@Service
class BillingService {
    public void checkout() {
        charge(); // this.charge(): does not go back through the Spring proxy
    }

    @Transactional
    public void charge() {
        // database operations
    }
}
```

This is an **illustrative** snippet, not a standalone runnable program. If the caller only invokes `checkout()` through the proxy, the annotation on `charge()` is **not applied by the interceptor for this internal call**. Typical fixes are moving `charge()` to another Spring bean and calling through it, placing the transaction boundary on `checkout()`, or using `TransactionTemplate` when programmatic control is needed.

Subtle detail to remember: if `checkout()` is already running inside another transaction, the internal call can still execute **within the existing transaction**, yet `charge()`'s own `@Transactional` attributes are not applied independently via self-invocation.

### 7.2 Bypassing the Spring proxy or non-interceptable targets

- `new TransferService(...)` creates an unmanaged object: annotations on that instance do not activate Spring AOP.
- Private methods are not proxy entry points for applying transactions like public service methods. Final classes/methods also have limitations with class-based proxies because they cannot be subclassed/overridden accordingly.
- `@PostConstruct`, direct calls inside constructors, or early initialization code are not places to rely on transaction proxies being ready.
- Imperative transaction state is typically bound to the **current thread**. Spawning a new thread, running `@Async`, or switching execution contexts does not automatically carry an existing JDBC transaction to the new thread.
- In reactive pipelines, `ReactiveTransactionManager` uses **Reactor Context**, not thread-bound JDBC rules; operations must stay in the same reactive chain/appropriate context. Reactive return types require a compatible manager configuration rather than extrapolating from imperative JDBC examples.

### 7.3 Caught exceptions, exception types, and rollback

Under default `@Transactional` settings, `RuntimeException` and `Error` trigger rollback; **checked exceptions** do not automatically roll back unless explicitly configured. `JdbcTemplate` typically translates DB access failures into `DataAccessException` (unchecked), so most SQL errors trigger the default rule.

```java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // checked IOException escaping the method also requests DB rollback
}
```

This is an illustrative snippet; `IOException` requires importing `java.io.IOException`. Configuring `rollbackFor` governs **DB rollback rules**; it does not automatically undo actions that already occurred outside the DB (such as file writes).

If a service **swallows an exception** and returns normally, the interceptor may view the scope as successful and commit, unless the transaction was already marked rollback-only or another rollback condition occurred. Conversely, an inner scope marked rollback-only can cause the outer commit to fail even if the caller caught the exception.

## 8. What does "resource management" include, and what does it exclude?

A JDBC transaction involves several distinct lifecycles:

| Object | Who is typically responsible? | When does it end? |
| --- | --- | --- |
| Transaction scope | `TransactionInterceptor` + `PlatformTransactionManager` | When the call/transaction scope finishes per propagation |
| Transaction-bound JDBC `Connection` | Transaction manager + binding/release infrastructure | When the transaction finishes and the connection is released |
| `PreparedStatement`, `ResultSet` | `JdbcTemplate` or DAO `try-with-resources` | When the corresponding SQL operation finishes |
| Physical connection in pool | Connection pool / datasource implementation | Reused; physically closed per pool policy |
| Transaction-bound JPA `EntityManager` | JPA transaction infrastructure | Per transaction/persistence context lifecycle |
| Unenlisted files, HTTP calls, emails, messages | Separate libraries/systems | Do **not** roll back with a local DB transaction |

Example: `@Transactional` wraps inserting into `orders` and then sending an email. If sending the email succeeds while the DB transaction rolls back, the email is **not "unsent."** Likewise, writing a file to disk, calling a REST API, or publishing a message does not automatically join a local JDBC transaction.

When reliable post-commit effects are required, consider **transactional outbox** (saving an event record in the same DB transaction and sending afterward) or an event listener in the right phase such as `@TransactionalEventListener(phase = AFTER_COMMIT)`. Post-commit callbacks do not replace outbox retry/durable delivery mechanisms when high reliability is needed.

With multiple databases or resources needing atomic commit, a single local `DataSourceTransactionManager` does not turn them into a distributed transaction; an appropriate strategy is required (JTA/XA when conditions allow, or saga/outbox/compensation depending on the problem). That limit belongs to **resources and transaction systems**, not to a missing AOP annotation.

## 9. How to investigate when a transaction "has no effect"

Trace the call path from outside in, instead of merely staring at `@Transactional`:

1. **Right bean and proxy?** Was the service created/injected by Spring? Does the call go from caller through the proxy or via `this.method()`? Are any classes/methods unproxiable?
2. **Are interceptor and manager active?** Is transaction management enabled? Is there a compatible `PlatformTransactionManager` or `ReactiveTransactionManager`? When multiple managers exist, does the annotation pick the right one?
3. **Does the DAO acquire the right resource?** Does `JdbcTemplate` share the manager's `DataSource`? Does plain JDBC use `DataSourceUtils` or a suitable adapter? Does the JPA repository belong to the right persistence unit/manager?
4. **Is the transaction scope right?** Did `REQUIRED` join an outer transaction? Did `REQUIRES_NEW` open an independent transaction? Is there async/thread switching or a different reactive context?
5. **Did rollback rules actually trigger?** Which exception exited the method? Was it caught and swallowed? Is a checked exception missing `rollbackFor`? Did a scope mark rollback-only?
6. **Observe post-commit/rollback state.** Use an integration test with a real DB/H2, intentionally raise an error between two operations, and read values back from another transaction or after the transaction finishes. Never treat seeing SQL logs as proof of commit.

You can selectively enable logging in test/lab environments to inspect begin/join/commit/rollback and JDBC activity; for example, `logging.level.org.springframework.transaction=TRACE` and `logging.level.org.springframework.jdbc.datasource=DEBUG` in Spring Boot. Avoid overly verbose logging in production as it consumes resources and risks exposing sensitive data.

In imperative code, `TransactionSynchronizationManager.isActualTransactionActive()` is useful for **diagnostics** to check whether the current execution has a real Spring transaction active. It does not prove a DAO is using the right `Connection` or that an external system can roll back; do not couple everyday business logic to this internal API.

A misleading test pitfall: `@Transactional` on a **test method** managed by Spring Test can open a transaction and roll it back at the end of the test, differing from normal application service calls. Always inspect the real business transaction boundary when verifying commit capability.

## 10. Self-check

**Scenario A.** A `@Transactional` service calls two JDBC repositories sharing the same `DataSource` and `JdbcTemplate`. The second statement throws an uncaught `DataAccessException`. What happens to the first statement's data?

**Explanation:** if the service was invoked through the proxy, the transaction is truly active, and both repositories share the same transaction, the unchecked exception causes rollback by default; uncommitted changes from the first statement do not exist after rollback. If the service bypassed the proxy or the DAOs used independent connections, you cannot assume that outcome.

**Scenario B.** `placeOrder()` calls `this.saveOrder()`, which has `@Transactional(REQUIRES_NEW)`. Is a new transaction guaranteed to be created?

**Explanation:** no. In proxy mode, self-invocation is not intercepted by advice on `saveOrder()`; that method's `REQUIRES_NEW` attribute is not applied. Extract to another bean or change the transaction boundary.

**Scenario C.** Two SQL statements succeed and then JPA calls `flush()`. Can we conclude they are committed?

**Explanation:** no. `flush()` and commit are two distinct milestones; the transaction can still roll back after a flush.

**Scenario D.** Inside a DB transaction, a service sends an email and then throws an exception. Is the email rolled back together with the DB?

**Explanation:** no. A sent email is an external side effect outside the local DB transaction; a separate coordination mechanism is required.

## 11. Mental model to remember

- **AOP:** "*Where* do we intercept calls to establish a transaction boundary?"
- **Transaction manager:** "Which transaction is active, should it commit or roll back, and which resources belong to it?"
- **Data access:** "Which resources does the DAO/repository use to perform data work and join the right transaction?"
- **Resource management:** "How is the Connection/EntityManager acquired, bound to context, reused, cleaned up, and released on time?"
- **Database/resource manager:** "Who actually guarantees atomic commit/rollback for changes inside the physical transaction?"

Remember the path: **caller → Spring proxy/AOP → transaction interceptor/manager → service → data-access API → DB resource → manager commit/rollback and cleanup**. Understanding this full path explains both working behavior and most "annotated but didn't roll back" bugs.

## Official references for deeper reading

- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)