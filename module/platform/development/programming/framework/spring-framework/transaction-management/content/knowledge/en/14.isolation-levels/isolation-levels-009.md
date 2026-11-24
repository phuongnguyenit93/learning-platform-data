# Isolation of participating calls vs. new transactions in Spring Transaction Management

## 1. Core question: does declaring SERIALIZABLE on an inner method change outer?

Suppose a Spring service has already opened a transaction with `READ_COMMITTED` isolation. Inside that transaction, the service calls a method on another bean:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void processCriticalStep() {
    // Execute JDBC/ORM here.
}
~~~

Will the inner method run at `SERIALIZABLE` because its annotation requests a stronger level? **Not necessarily — in the scenario of joining an existing transaction, Spring by default ignores the isolation declared specifically on the inner method.** Inner's `PROPAGATION_REQUIRED` joins **the same physical transaction** already opened by outer. An already-active physical transaction does not automatically switch its isolation level merely because a new logical scope begins.

Conversely, if that method itself **opens a new physical transaction** (because no prior transaction existed with `REQUIRED`, or intentionally via `REQUIRES_NEW`), Spring gets the chance to configure isolation on the connection/resource before executing SQL. When the manager/driver/database support it, the new isolation can actually be applied.

These are two distinct rules:

1. **Metadata resolution**: Spring reads the method's `@Transactional(isolation = ...)` according to where the annotation applies.
2. **Applying isolation to the resource**: an isolation declaration normally takes effect only when **a new physical transaction starts**, with no authority to rewrite an existing transaction owned by another scope.

In short, **an inner method having its own annotation does not mean the inner method has its own physical transaction**.

This lesson covers: what isolation is, how Spring handles `REQUIRED`/`REQUIRES_NEW`/`NESTED`, when the manager rejects mismatches via `validateExistingTransaction`, how to observe **actual isolation on the JDBC connection**, and how to design tests that avoid false conclusions.

## 2. Isolation belongs to a physical transaction, not an isolated Java block

A **transaction isolation level** defines how operations inside one transaction observe or interact with operations from other transactions, within the DB/driver's capabilities. Levels in Spring's `Isolation` map to corresponding JDBC constants:

| Spring `Isolation` | JDBC constant | General meaning |
| --- | --- | --- |
| `DEFAULT` | Default of the transaction/database system | Does not force a specific level from the annotation |
| `READ_UNCOMMITTED` | `Connection.TRANSACTION_READ_UNCOMMITTED` | On systems truly supporting it, may see uncommitted data from other transactions |
| `READ_COMMITTED` | `Connection.TRANSACTION_READ_COMMITTED` | Prevents dirty reads; non-repeatable read/phantom handling depends on the engine |
| `REPEATABLE_READ` | `Connection.TRANSACTION_REPEATABLE_READ` | Aims for stability when re-reading rows, per DB semantics |
| `SERIALIZABLE` | `Connection.TRANSACTION_SERIALIZABLE` | Strongest isolation level in the standard model, equivalent to some serial execution order when properly enforced |

**Key caveats about isolation levels:**

- `Isolation.DEFAULT` **does not equal** `READ_COMMITTED` across all databases. It instructs the manager to let the resource choose its default. H2/PostgreSQL often start at READ_COMMITTED, yet you must verify the running system.
- A driver/database may **not support** a requested isolation level, or may have MVCC/semantics differing from simplified textbook descriptions. Never infer from a Spring enum that all concurrency phenomena vanish.
- Isolation does not replace UNIQUE constraints, proper locking, retries on serialization failures, or business invariant design.
- Spring `@Transactional` defaults to `Isolation.DEFAULT`. Specify `SERIALIZABLE` only when justified by consistency needs; do not treat it as "the safest setting for every call."

In Spring JDBC, the transaction manager typically calls `Connection.setTransactionIsolation(...)` when starting a new transaction if isolation differs from `DEFAULT`; it also attempts to restore connection state before returning it to the pool after the transaction. This setting call must fit the driver/DB contract. Transactions opened via JPA, JTA, or R2DBC may manage isolation differently, and not every manager supports every level.

## 3. Logical transaction scope vs. physical transaction: where misunderstandings begin

Spring distinguishes:

- **Logical scope**: each method passing through declarative transaction advice receives a transaction definition/status for that invocation (for example, outer `@Transactional` and inner `@Transactional` on two Spring beans).
- **Physical transaction**: the actual transaction on the resource, such as a JDBC connection/DB transaction with begin, commit, or rollback.

With `PROPAGATION_REQUIRED`, if no transaction exists, the logical scope creates a new physical transaction; if one already exists, the logical scope **joins** the existing physical transaction. Multiple logical scopes can share one physical transaction.

~~~mermaid
flowchart TD
    A["Client -> OuterService proxy"] --> B["Outer @Transactional<br/>isolation=READ_COMMITTED"]
    B --> C["Physical transaction T1<br/>JDBC Connection C1<br/>READ_COMMITTED"]
    C --> D{"Inner via proxy<br/>propagation?"}
    D -->|"REQUIRED: join"| E["Inner logical scope<br/>declares SERIALIZABLE"]
    E --> F["Still uses T1 and C1<br/>effective isolation READ_COMMITTED<br/>if validate=false"]
    D -->|"REQUIRES_NEW"| G["Suspend T1 and C1"]
    G --> H["Begin physical transaction T2<br/>Connection C2<br/>SERIALIZABLE if supported"]
    H --> I["Commit/rollback T2<br/>resume T1 on C1"]
    F --> J["Outer commits/rolls back T1"]
    I --> J
~~~

The diagram assumes a `DataSource`/`JdbcTransactionManager`, that outer already uses a JDBC connection, and that inner's annotation **is actually intercepted**. If outer has a different isolation, the physical transaction's value follows outer when inner joins. If there is no outer transaction, inner's `REQUIRED` opens a new transaction itself and there is no "join" branch.

### 3.1. Same method, two different call paths

~~~java
@Service
class RiskService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void assess() {
        // ...
    }
}
~~~

Assuming `assess()` is called through the Spring proxy:

- **Caller outside any transaction:** `REQUIRED` creates a new T2; when supported by the manager, it requests `SERIALIZABLE` for T2.
- **Caller already in T1 READ_COMMITTED:** `REQUIRED` joins T1; T1's isolation typically remains `READ_COMMITTED`, even though the method defines `SERIALIZABLE`.
- **Caller already in T1 SERIALIZABLE:** `REQUIRED` joins T1; no isolation change is needed since it is already at that level, though not because inner created a new physical transaction.
- **Caller in T1 with DEFAULT isolation:** you must know the actual JDBC connection level, and strict validation semantics can depend on the isolation metadata Spring recorded for T1; do not equate "DEFAULT" with a specific JDBC constant.

The design question is not merely "what isolation did inner write?", but **"does that call join an existing transaction or actually create a new transaction?"**.

## 4. PROPAGATION_REQUIRED: joins by default and ignores inner isolation

This is a common situation in the service layer:

~~~java
@Service
class CheckoutService {
    private final FraudService fraud;

    CheckoutService(FraudService fraud) {
        this.fraud = fraud;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void checkout() {
        // T1 is created here when no outer transaction exists.
        fraud.checkAndUpdate();
    }
}

@Service
class FraudService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void checkAndUpdate() {
        // Joins T1 instead of opening T2.
    }
}
~~~

This is an illustrative structural example omitting database code and imports. When a caller invokes `checkout()` through the proxy, T1 is created with requested isolation `READ_COMMITTED`. `FraudService` is **a different bean**, so `checkAndUpdate()` passes through the proxy and the manager sees inner's own annotation. However, `REQUIRED` propagation decides to **join T1**. In the default (lenient) mode of managers based on `AbstractPlatformTransactionManager`, inner's `SERIALIZABLE` isolation **does not upgrade** T1 from `READ_COMMITTED` to a new level.

Spring's own transaction propagation documentation notes that a participating transaction inherits the outer's attributes by default, **ignoring** the inner's own isolation level, timeout, and read-only flag unless incompatibility checking is enabled. Thus separate two conclusions:

1. **Inner's annotation was read**: the transaction interceptor chose `REQUIRED` propagation.
2. **Inner's isolation was not applied as a connection change**: because no new physical transaction began.

If a critical operation must enforce strong isolation, merely annotating an inner method called inside T1 is insufficient. Either ensure **the transaction-owning entrypoint** declares the required isolation, or design an independent physical transaction with `REQUIRES_NEW` after evaluating consistency and resources.

## 5. PROPAGATION_REQUIRES_NEW: starts a different physical transaction, applies its own isolation

Configuration:

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void checkAndUpdateIndependently() {
    // ...
}
~~~

When an outer T1 exists at `READ_COMMITTED`, this method **does not join T1**. Spring suspends T1 and opens a new T2; with a supporting JDBC manager and driver, T2 gets `SERIALIZABLE` isolation on its connection. After T2 commits/rolls back, Spring releases T2's connection and resumes T1. T1 continues with its own `READ_COMMITTED`.

| Moment | Outer T1 | Inner T2 | Active SQL isolation |
| --- | --- | --- | --- |
| Outer starts | Active | None yet | READ_COMMITTED |
| Inner `REQUIRES_NEW` starts | Suspended, holds resources | Active | SERIALIZABLE |
| Inner returns/throws | Still suspended | Commits/rolls back | SERIALIZABLE for T2 until completion |
| Outer resumes | Active | Completed | READ_COMMITTED |
| Outer finishes | Commits/rolls back | Completed | T1 no longer exists |

**Especially important:** `REQUIRES_NEW` also changes **atomicity**. A successful inner commit is **not** undone by a later outer rollback. If inner reads data outer just modified but **has not committed**, T2 normally **does not see** those uncommitted changes under isolations preventing dirty reads; T2 can also block waiting on a lock held by T1 while T1 waits for T2 — a lock dependency cycle even when the pool has plenty of connections. Never use `REQUIRES_NEW` merely to "force SERIALIZABLE" if business rules require outer and inner work to commit/roll back together.

With a connection pool such as HikariCP, outer may keep holding C1 while T2 needs to borrow C2. Many concurrent requests can cause pool exhaustion. Choosing a separate isolation level must go hand in hand with connection pool and row-lock capacity planning.

## 6. Isolation.DEFAULT: DB default differs from outer's Spring metadata

`@Transactional` defaults isolation to `Isolation.DEFAULT`. In typical usage:

~~~java
@Transactional
public void writeDefault() {
    // Physical transaction isolation comes from DB/pool/driver default,
    // and cannot be inferred directly from this annotation.
}
~~~

When Spring does not request a specific isolation, the JDBC connection may sit at the pool/database default, such as `READ_COMMITTED` in common H2 setups. However:

- `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` reflects **the isolation level declared by Spring on the transaction context**, which can be `null` if the transaction uses `Isolation.DEFAULT`; it is **not necessarily** the actual JDBC isolation.
- `Connection.getTransactionIsolation()`, called on **the connection bound to the transaction**, observes the real JDBC isolation at inspection time.
- A pooled connection must be properly managed/restored; if code outside transactions alters isolation without resetting it, behavior can diverge from expectations.

**Easy-to-confuse case:** Outer declares `Isolation.DEFAULT` (Spring metadata states no specific level) while the actual connection is `READ_COMMITTED`. Inner `REQUIRED` declares `SERIALIZABLE`; lenient mode joins and keeps using the actual `READ_COMMITTED` connection. Strict validation can compare inner's request against the current isolation metadata known to the manager, rather than comparing developer intent against the driver in some ad-hoc way. When you need to verify mismatches unambiguously, declare outer's level **explicitly** and use connection-level tests.

### Is DEFAULT "safe enough"?

There is no universal answer. Every DB has its own default isolation and concurrency semantics. Appropriate isolation depends on the anomalies to prevent, workload, lock contention, retry policy, and transaction duration. Never hardcode the assumption "DEFAULT = SERIALIZABLE" or "DEFAULT = READ_COMMITTED" across multiple databases.

## 7. Strict checking with validateExistingTransaction

Spring supports **`setValidateExistingTransaction(true)`** on transaction managers inheriting from `AbstractPlatformTransactionManager`, such as `JdbcTransactionManager` and `DataSourceTransactionManager`.

When enabled:

- If inner tries to join an existing transaction while requesting an isolation level **different** from what Spring recorded for the outer transaction, the manager can **reject** joining with `IllegalTransactionStateException`, instead of silently ignoring inner's declaration.
- This mechanism also helps catch a read-write inner attempting to join a read-only outer transaction, depending on manager and metadata.
- It **does not turn `REQUIRED` into `REQUIRES_NEW`**: mismatches error out rather than creating a replacement independent transaction.
- If inner does not request a specific isolation (`Isolation.DEFAULT`), that is not a request to "upgrade/pin isolation," so it does not trigger a mismatch merely because the physical DB level has a concrete value.
- Not all transaction managers support custom isolation equally; when a manager does not support it, verify the resource's actual capabilities.

Typical bean configuration:

~~~java
@Bean
JdbcTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
~~~

This snippet belongs in a `@Configuration`/Spring Boot application class with appropriate imports; `DataSource` must be the DAO's resource. It is a **manager-wide policy**, not per-method. Enabling strict validation can turn flows that previously "ran with silently ignored attributes" into **fail-fast errors**; test all callers participating in transactions.

### Note on the API name

The Java setter name is **`setValidateExistingTransaction`** (singular "Transaction"). Documentation occasionally writes "validate existing transactions" as descriptive prose; when writing code, use the exact method name and a manager type that provides it.

### Why is strict validation useful?

Suppose payment logic requires all SQL deciding final state to execute at a specified isolation. If a caller opens a weaker transaction and invokes a critical `@Transactional(isolation=SERIALIZABLE)` method with `REQUIRED`, default configuration **does not upgrade** the outer transaction. If that would be a consistency bug, strict mode surfaces the error **right at the join point** instead of letting the system assume it ran at the desired isolation.

However, strict mode does not solve "only inner needs different isolation while still joining the same physical transaction"; those two desires conflict at the resource semantics level. Choose T1's isolation from the start or intentionally split out T2.

## 8. Runnable Java 17+ example: observing real isolation on the JDBC Connection

This CLI example uses **Java 17**, **Spring Boot 3.3.5 (Spring Framework 6.1.x)**, `spring-boot-starter-jdbc`, in-memory H2, Maven, and two separate Spring services. No HTTP server or external DB is needed.

The program runs **three scenarios**:

1. **Lenient + REQUIRED join:** Outer opens a `READ_COMMITTED` transaction, inner requests `SERIALIZABLE` yet joins the same physical transaction; inner inspects the JDBC connection and sees `READ_COMMITTED`.
2. **REQUIRES_NEW:** Outer opens `READ_COMMITTED`, inner opens an independent `SERIALIZABLE` physical transaction; back in outer, `READ_COMMITTED` is seen again.
3. **Strict validation:** Manager enables `validateExistingTransaction=true`, inner `REQUIRED` requests `SERIALIZABLE` while outer is `READ_COMMITTED`; the manager throws `IllegalTransactionStateException` as soon as inner attempts to join.

To observe accurately, the program calls `JdbcTemplate.execute(ConnectionCallback<T>)` to obtain **the current transaction's connection** and read `Connection.getTransactionIsolation()`. Do not deduce isolation levels solely by reading annotations or logs.

### 8.1. File structure

~~~text
isolation-join-demo/
├── pom.xml
└── src/main/java/example/isolation/
    ├── IsolationDemoApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

The package-private utility class `IsolationProbe` is placed **in the same file** `IsolationDemoApplication.java`, because Java allows one public top-level class alongside package-private top-level classes in a file. Thus the project only needs **four files**.

### 8.2. pom.xml

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
    <artifactId>isolation-join-demo</artifactId>
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

### 8.3. src/main/java/example/isolation/IsolationDemoApplication.java

~~~java
package example.isolation;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class IsolationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
        manager.setValidateExistingTransaction(false);
        return manager;
    }

    @Bean
    CommandLineRunner demo(OuterService outer, JdbcTransactionManager manager) {
        return args -> {
            System.out.println("LENIENT_MODE");
            outer.joinScenario();
            outer.independentScenario();

            // Only flip this flag in a single-threaded CLI app for illustration.
            // NOT recommended to mutate transaction manager config in running production.
            manager.setValidateExistingTransaction(true);
            System.out.println("STRICT_MODE");
            try {
                outer.joinScenario();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "STRICT_REJECTED=" + ex.getClass().getSimpleName()
                );
            }
        };
    }
}

// Package-private utility class in the same file as the public class above.
final class IsolationProbe {
    private IsolationProbe() {
    }

    static String actual(JdbcTemplate jdbc) {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );
        if (level == null) {
            throw new IllegalStateException("No JDBC isolation level");
        }
        return switch (level) {
            case Connection.TRANSACTION_READ_UNCOMMITTED -> "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ -> "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "OTHER(" + level + ")";
        };
    }
}
~~~

Note that importing `ConnectionCallback` from `org.springframework.jdbc.core` provides the callback where `JdbcTemplate` supplies the connection bound to the Spring transaction. Do not call `dataSource.getConnection()` directly and forget to close it: that may be a different connection, making the measurement meaningless for the active transaction.

### 8.4. src/main/java/example/isolation/OuterService.java

~~~java
package example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void joinScenario() {
        System.out.println(
            "OUTER_JOIN_BEFORE=" + IsolationProbe.actual(jdbc)
        );
        // Different bean -> passes through InnerService's transaction proxy.
        inner.joinSerializable();
        System.out.println(
            "OUTER_JOIN_AFTER=" + IsolationProbe.actual(jdbc)
        );
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void independentScenario() {
        System.out.println(
            "OUTER_NEW_BEFORE=" + IsolationProbe.actual(jdbc)
        );
        inner.newSerializable();
        System.out.println(
            "OUTER_NEW_AFTER=" + IsolationProbe.actual(jdbc)
        );
    }
}
~~~

### 8.5. src/main/java/example/isolation/InnerService.java

~~~java
package example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void joinSerializable() {
        System.out.println(
            "INNER_REQUIRED_ACTUAL=" + IsolationProbe.actual(jdbc)
        );
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void newSerializable() {
        System.out.println(
            "INNER_NEW_ACTUAL=" + IsolationProbe.actual(jdbc)
        );
    }
}
~~~

### 8.6. Run and compare output

From the directory containing `pom.xml` (JDK 17+ and Maven; dependencies may download on first run):

~~~bash
mvn -q spring-boot:run
~~~

Lines **printed by the program itself** in order, excluding Spring Boot/HikariCP startup logs:

~~~text
LENIENT_MODE
OUTER_JOIN_BEFORE=READ_COMMITTED
INNER_REQUIRED_ACTUAL=READ_COMMITTED
OUTER_JOIN_AFTER=READ_COMMITTED
OUTER_NEW_BEFORE=READ_COMMITTED
INNER_NEW_ACTUAL=SERIALIZABLE
OUTER_NEW_AFTER=READ_COMMITTED
STRICT_MODE
OUTER_JOIN_BEFORE=READ_COMMITTED
STRICT_REJECTED=IllegalTransactionStateException
~~~

**Step-by-step explanation:**

1. `LENIENT_MODE`: manager has `setValidateExistingTransaction(false)`.
2. `OUTER_JOIN_BEFORE=READ_COMMITTED`: outer proxy begins a new T1, and Spring requests READ_COMMITTED isolation on T1's JDBC connection.
3. `INNER_REQUIRED_ACTUAL=READ_COMMITTED`: although the inner method declares SERIALIZABLE, it joins T1 via `REQUIRED`. In lenient mode, the manager ignores inner's requested isolation; the JDBC connection stays READ_COMMITTED.
4. `OUTER_JOIN_AFTER=READ_COMMITTED`: T1's isolation did not change during the join. The outer transaction finishes at the end of the method.
5. `OUTER_NEW_BEFORE=READ_COMMITTED`: a new T1 is created for the second call.
6. `INNER_NEW_ACTUAL=SERIALIZABLE`: `REQUIRES_NEW` suspends T1, opens physical transaction T2, and requests SERIALIZABLE on T2's connection. H2 supports this level.
7. `OUTER_NEW_AFTER=READ_COMMITTED`: T2 completed and T1 resumed with its original isolation.
8. `STRICT_MODE`: the demo enables `setValidateExistingTransaction(true)` **after the previous methods returned**; do not do this mid-flight in a production request with concurrent transactions.
9. Outer starts T1 READ_COMMITTED and prints `OUTER_JOIN_BEFORE=READ_COMMITTED`.
10. Inner `REQUIRED` requests SERIALIZABLE; strict validation detects the mismatch and **rejects joining before entering the body of `joinSerializable()`**. The caller outside the outer proxy catches `IllegalTransactionStateException` after the outer interceptor rolls back. Hence **there is no second `INNER_REQUIRED_ACTUAL` line** in the strict case.

The demo shows not only annotation metadata, but the **current JDBC isolation** returned from the right transaction's connection. It is not a test of concurrency anomalies such as phantom reads; write a separate concurrent multi-connection test to prove specific read/write phenomena.

## 9. Prediction matrix when the caller has or lacks an outer transaction

Assuming the Spring JDBC manager supports the requested isolation level, the call **passes through the proxy**, and no enclosing transaction exists beyond what is stated:

| Current transaction | Inner annotation | Physical transaction | Expected inner isolation (lenient) | Under strict validation |
| --- | --- | --- | --- | --- |
| None | `REQUIRED, SERIALIZABLE` | Inner creates new T | SERIALIZABLE | Same result if driver supports it |
| Existing T1 READ_COMMITTED | `REQUIRED, SERIALIZABLE` | Joins T1 | READ_COMMITTED (per T1) | Rejects mismatch |
| Existing T1 SERIALIZABLE | `REQUIRED, SERIALIZABLE` | Joins T1 | SERIALIZABLE | Allows join if metadata matches |
| Existing T1 READ_COMMITTED | `REQUIRED, DEFAULT` | Joins T1 | READ_COMMITTED | Does not demand new isolation |
| Existing T1 READ_COMMITTED | `REQUIRES_NEW, SERIALIZABLE` | Suspends T1, creates T2 | SERIALIZABLE on T2 | Creates T2; not validated as a T1 join |
| None | `REQUIRES_NEW, SERIALIZABLE` | Creates new T2 | SERIALIZABLE | Same result if supported |
| Existing T1 READ_COMMITTED | `NESTED, SERIALIZABLE` | May create a JDBC savepoint in T1 | Does not upgrade T1 to SERIALIZABLE | Not a way to establish new isolation |
| Existing T1 READ_COMMITTED | `SUPPORTS, SERIALIZABLE` | Joins if present | T1 stays READ_COMMITTED | Do not use SUPPORTS to request new isolation |

**Note on `NESTED`:** behavior also depends on manager/driver support; a savepoint does not create a new physical transaction. `SUPPORTS` with custom isolation is not designed to force isolation on a new physical transaction. Per `@Transactional` Javadoc, isolation and timeouts primarily apply when a new transaction is started with `REQUIRED` or `REQUIRES_NEW`.

## 10. Annotation isolation, Spring context isolation, connection isolation

There are three distinct layers of information:

1. **Requested definition:** `@Transactional(isolation = Isolation.SERIALIZABLE)` — what the author asks for at the transaction boundary.
2. **Spring transaction context:** `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` — **declared** isolation info Spring attaches to the current transaction context; may be `null` for `DEFAULT`.
3. **Actual JDBC connection:** `Connection.getTransactionIsolation()` from the transaction-aware connection used by `JdbcTemplate` — the isolation level the driver reports as active.

In the lenient example, inner's definition requests SERIALIZABLE, yet the physical connection inside inner returns READ_COMMITTED. Reading annotation code without inspecting context/connection can lead to wrong conclusions.

~~~java
// Snippet inside an imperative method with Spring transaction advice applied:
Integer springDeclared =
    TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();

// Obtain the exact connection bound to the transaction via JdbcTemplate.
Integer jdbcActual = jdbc.execute(
    (ConnectionCallback<Integer>) c -> c.getTransactionIsolation()
);
~~~

Required imports in the snippet: `org.springframework.transaction.support.TransactionSynchronizationManager`, `org.springframework.jdbc.core.ConnectionCallback`, `org.springframework.jdbc.core.JdbcTemplate`. This is an **illustrative snippet**, not a standalone runnable class. Do not instantiate `new JdbcTemplate(new HikariDataSource(...))` to probe a completely different source; use the exact `DataSource` bean managed by the manager.

**A trap:** Calling `DataSource.getConnection()` directly can borrow another connection from the pool (unbound to the transaction) and observe its default isolation. Then logging "inner is READ_COMMITTED" does not prove inner SQL on `JdbcTemplate` runs at that level. To measure accurately, go through Spring's transaction-aware API; `JdbcTemplate` uses `DataSourceUtils` under the hood.

## 11. What happens if the isolation level is not supported by the database?

A declared level is not magic. You may encounter:

- Driver/database **does not support** a JDBC isolation level: `Connection.setTransactionIsolation(...)` may reject it, or the DB may exhibit driver-specific behavior.
- Transaction manager does not support custom isolation: it may throw `InvalidIsolationLevelException` or an equivalent exception.
- A database using snapshot isolation/MVCC has semantics differing from the simplified ANSI SQL table; the same name `REPEATABLE_READ` or `SERIALIZABLE` does not guarantee identical locking strategies.
- Serialization failures/lock timeouts occur when the DB enforces strong isolation; applications must define proper retries, **never** assuming strong isolation never fails.
- Transaction timeout, read-only, and isolation are all transaction attributes with distinct support and enforcement. One attribute being accepted by a manager does not prove the others are enforced identically.

When designing across multiple databases, test against real DBs (PostgreSQL, MySQL/InnoDB, SQL Server, Oracle...) instead of relying solely on H2. The H2 demo above only proves **Spring selects the connection's isolation level** across three scenarios; it does not prove an entire production anomaly matrix.

## 12. Be cautious with REQUIRES_NEW and business consistency

Suppose outer T1 reads customer info and updates `account.balance`, and then inner `REQUIRES_NEW` SERIALIZABLE checks a credit limit. T2 is a different physical transaction, so it **does not inherit T1's uncommitted writes** and may observe a different DB snapshot/state. If T2 needs to check values outer has not committed yet, the result may not match the author's expectation. T2 can also block on a lock held by T1 while T1 waits on T2 — a dependency cycle even when the pool has enough connections.

This is why you should **never reach for REQUIRES_NEW automatically just to get another isolation level**. Ask in order:

1. Does the business invariant require all steps to be atomic together?
2. Can the stronger isolation level be placed on **the outer transaction owner** from the outset?
3. Will splitting inner into an independent transaction introduce unwanted partial commits?
4. Is there uncommitted outer data that inner needs to see?
5. Could cross-transaction lock dependencies or connection pool contention arise?
6. Can a fresh command/entrypoint be designed to open with `SERIALIZABLE` instead of calling inside the current T1?

If the whole workflow must be atomic and requires strong isolation, choose **one physical transaction owning all operations** at the right isolation from the beginning, rather than stitching together two independent transactions with unintended consistency consequences.

## 13. Role of proxies and internal calls

In default `@EnableTransactionManagement` proxy mode, `@Transactional` is advised only when calls go **through the Spring proxy**. Calling `this.inner()` within the same target object does not invoke a new transaction interceptor for inner.

~~~java
@Service
class OneBean {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        this.inner(); // Does not go through inner proxy.
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // Inner's annotation does not open T2 when invoked via this.inner().
    }
}
~~~

This is **illustrative code**. If the caller goes through `outer()`'s proxy, inner still runs inside outer's `READ_COMMITTED` T1, though not because inner's `REQUIRES_NEW` ran. **Do not treat "unchanged isolation" as sole proof of a REQUIRED join**; it can also happen because self-invocation bypassed transaction advice.

To establish proper transaction boundaries, extract inner into another bean invoked via the Spring proxy, or use `TransactionTemplate`/programmatic transactions where appropriate. Verify with integration tests checking committed/rolled-back data and connection isolation, not merely inspecting annotations in source code.

## 14. TransactionTemplate also obeys physical transaction isolation rules

With Spring's programmatic API, the same rules apply. Illustrative snippet:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE
);
template.executeWithoutResult(status -> {
    // When the manager joins an existing T1,
    // SERIALIZABLE in this definition does not upgrade T1.
});
~~~

Changing propagation to `PROPAGATION_REQUIRES_NEW` lets the callback open a new physical transaction and apply the requested isolation, within manager/DB limits. The programmatic style does **not** change the join-versus-new rule; it only removes the need for a proxy call around the callback.

`TransactionTemplate` fits well when explicit boundaries are needed inside the same component, while still requiring attention to the transaction manager, exceptions, retries, and pool resources. It is not a tool to "force an isolation level onto an already-running transaction."

## 15. Common configuration mistakes

| Misconception or error | Reality |
| --- | --- |
| "Inner `REQUIRED` declares SERIALIZABLE so all of T1 upgrades to SERIALIZABLE." | Default lenient managers normally ignore inner isolation when joining T1. |
| "Any method annotation creates a new physical transaction." | `REQUIRED` joins an existing physical transaction. |
| "`Isolation.DEFAULT` is always READ_COMMITTED." | Uses the DB/connection/manager default, which varies by environment. |
| "`REQUIRES_NEW` only changes isolation while committing together with outer." | It creates an independent physical transaction and changes atomicity. |
| "Enabling `validateExistingTransaction=true` automatically creates a new transaction on mismatch." | No. It typically rejects the join with an exception. |
| "Strict validation inspects actual isolation on every JDBC connection in every manager." | It relies on transaction metadata/manager rules; do not treat it as a comprehensive JDBC diagnostic. |
| "Inner `NESTED` can set SERIALIZABLE independently of outer." | A JDBC savepoint lives in the same physical transaction, not a separate T2. |
| "Changing isolation by calling `Connection.setTransactionIsolation` mid-transaction is safe." | Can break consistency/driver contracts and pool state; never change arbitrarily mid-transaction. |
| "H2 supporting SERIALIZABLE means PostgreSQL/MySQL share the same anomaly behavior." | Drivers/DBs have distinct semantics; test on the target engine. |
| "`TransactionSynchronizationManager` returning null means the JDBC connection has no isolation." | `null` usually means no explicit isolation level in Spring metadata, not that the connection lacks JDBC isolation. |
| "Self-calls still get inner's @Transactional advice." | Proxy mode typically skips advice on `this.inner()` calls. |
| "Raising isolation is a universal fix for every race condition." | You still need proper transaction scope, constraints, locking/retries, and concurrent tests. |

## 16. Debugging: a method requests SERIALIZABLE yet SQL still runs at READ_COMMITTED

Check in order:

1. **Who is the actual caller?** Is an outer `@Transactional` or test transaction already open? If so, what is that physical transaction's isolation?
2. **What is inner's propagation?** `REQUIRED` joins, `REQUIRES_NEW` creates an independent transaction, `NESTED` uses savepoints when supported.
3. **Did the call go through a proxy?** Is another Spring-injected bean invoked, or is it `this` self-invocation? Instances created with `new` receive no transaction advice.
4. **Which manager was selected?** Are there multiple `PlatformTransactionManager`/`DataSource` beans? `@Transactional(transactionManager="...")` must point to the manager owning the SQL's resource.
5. **Which metadata applies?** Method annotations override class annotations; do not assume class attributes are partially merged into method annotations.
6. **Is strict validation enabled?** If `setValidateExistingTransaction(true)` is set and a mismatch exists, an error should fire on join; otherwise re-check manager/proxy.
7. **Measure isolation on the real connection.** Use `JdbcTemplate.execute(ConnectionCallback)` or an equivalent transaction-aware API; never borrow a separate connection to inspect.
8. **Is the outcome driver-dependent?** Does the DB support the requested level, upgrade/downgrade it, use MVCC, or raise lock/serialization failures?
9. **Does the test have an outer transaction?** A `@Transactional` test method managed by Spring TestContext can unexpectedly turn a `REQUIRED` service method into a participating scope.
10. **Is another inner resource involved?** A repository using a different datasource/manager may actually run in a different physical transaction—do not infer from matching database names.

Diagnostic logging you can enable:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Use logging to confirm begin/join/suspend and the manager, but do not treat a "participating in existing transaction" log line as a substitute for `getTransactionIsolation()` on the exact JDBC connection. In production, control log levels to avoid overhead and sensitive output.

## 17. Scenario exercises and answers

### Exercise 1. Inner REQUIRED upgrading isolation?

Outer opens T1 `READ_COMMITTED`. An inner bean has `@Transactional(propagation=REQUIRED, isolation=SERIALIZABLE)`. Default lenient manager. Inner reads the JDBC connection. Expected isolation?

**Answer:** `READ_COMMITTED` from T1, because inner joins the same physical transaction. Inner's `SERIALIZABLE` metadata is not re-applied to T1.

### Exercise 2. What if there is no outer transaction?

Same inner method `REQUIRED`/`SERIALIZABLE`, but the caller has no transaction. Expected isolation?

**Answer:** Inner creates a new physical transaction; if supported by manager/driver, it configures `SERIALIZABLE` for that transaction.

### Exercise 3. Enabling validateExistingTransaction?

Keep Exercise 1, enable strict validation on `JdbcTransactionManager`. What changes?

**Answer:** The manager detects inner requesting SERIALIZABLE inside a T1 recorded by Spring as READ_COMMITTED and rejects the join with `IllegalTransactionStateException`; it does not automatically create T2.

### Exercise 4. Changing inner to REQUIRES_NEW?

Outer T1 `READ_COMMITTED` calls inner `REQUIRES_NEW`/`SERIALIZABLE`. Isolation while inner runs, and after returning to outer?

**Answer:** While inner T2 runs, `SERIALIZABLE` if supported; once T2 completes and T1 resumes, outer continues at `READ_COMMITTED`. Inner commits/rolls back independently.

### Exercise 5. Inner on the same bean called via this.inner()?

Outer `@Transactional(READ_COMMITTED)` calls `this.inner()`; inner is annotated `REQUIRES_NEW`/`SERIALIZABLE`. Is T2 created?

**Answer:** In default proxy mode, **no** T2 is created by inner's annotation. The call bypasses inner's advice; its body executes inside outer's T1.

### Exercise 6. DEFAULT and null metadata?

Outer `@Transactional` specifies no isolation, using a JDBC connection currently at `READ_COMMITTED`. What can `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` return?

**Answer:** It can return `null` because Spring metadata is `Isolation.DEFAULT`, while `Connection.getTransactionIsolation()` on T1's connection returns `READ_COMMITTED`. Do not confuse declared isolation with effective isolation.

### Exercise 7. Does strong isolation prevent every lost update?

Two transactions read the same value, compute a new value, and update. Is putting `SERIALIZABLE` on a `REQUIRED` helper inside an outer READ_COMMITTED transaction enough?

**Answer:** No; the helper joins outer and does not raise the isolation level. Even when the physical transaction runs SERIALIZABLE, the system still needs serialization-failure/retry handling and proper constraints/SQL. Test concurrency on the real DB.

### Exercise 8. Consistency issue when using REQUIRES_NEW?

Outer T1 modifies a row without committing yet; inner T2 SERIALIZABLE needs to read that exact row to make a decision. Is inner guaranteed to see outer's uncommitted change?

**Answer:** No. T2 is an independent transaction; under isolations preventing dirty reads, it does not see that uncommitted write and may block on T1's lock. Choose propagation based on invariants, not merely desired isolation.

## 18. Pre-implementation checklist

- [ ] Clearly identify **the physical transaction owner** and the propagation of each logical scope.
- [ ] If a method requires its own isolation, verify whether it **opens a new transaction** or **joins**.
- [ ] Never assume an inner annotation upgrades outer's isolation level.
- [ ] Verify `Isolation.DEFAULT` against the actual database/driver rather than hardcoding.
- [ ] Choose `validateExistingTransaction(true)` if you want mismatches detected, and test its impact on existing flows.
- [ ] Ensure calls to inner pass through the right Spring proxy without self-invocation.
- [ ] For `REQUIRES_NEW`, evaluate independent commit/rollback, JDBC connection pool sizing, and row locks.
- [ ] Measure `Connection.getTransactionIsolation()` on the transaction-aware connection.
- [ ] Test on a production-like DB with concurrent workloads and a retry strategy.
- [ ] Avoid reading results from an unintended Spring TestContext outer transaction.

## 19. Conclusion

**Isolation is a property of a physical transaction.** `@Transactional(isolation=SERIALIZABLE)` on a `REQUIRED` method is only **a metadata request**. When the method **joins** outer's `READ_COMMITTED` physical transaction, Spring by default does not switch that connection/transaction to SERIALIZABLE. You can enable `setValidateExistingTransaction(true)` to **reject mismatches** rather than silently ignoring them.

For a dedicated isolation level to take effect, the method must **own a new physical transaction**: `REQUIRED` when no current transaction exists, or `REQUIRES_NEW` when separating from outer is appropriate. Yet an independent transaction also changes atomicity, visibility, resource locks, and connection pool demand. Therefore choose isolation and propagation together according to consistency requirements, and verify on real JDBC connections and in the target database environment.

## Official references

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transactions, `REQUIRED` joining and ignoring inner isolation, strict `validateExistingTransaction`, `REQUIRES_NEW` with independent physical transactions.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default `Isolation.DEFAULT` and propagation.
- [Spring Framework 6.1 — Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): isolation primarily applies to newly started `REQUIRED`/`REQUIRES_NEW` transactions.
- [Spring Framework — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `setValidateExistingTransaction` and validating participating scopes.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, transaction-aware JDBC connection usage.
- [Java SE 17 — java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `getTransactionIsolation()`, JDBC transaction isolation constants.
