# TransactionInterceptor Wrapping Business Calls in Spring

> **Spring Framework — Transaction Management → Proxy mechanism.** This lesson explains the exact path of a `@Transactional` call in Spring: from the proxy object, through `TransactionInterceptor` and `TransactionManager`, to the business code, and back out to commit or roll back. The goal is to understand *when* a transaction is created, *who* ends the transaction, and *why* calls that look similar can have different rollback outcomes.

## 1. The Big Picture

When a Spring bean is configured for declarative transactions, Spring typically does not insert `beginTransaction()` and `commit()` into the developer-written method body. In **proxy mode** (the default mode), Spring creates an **AOP proxy** to intercept calls going through that bean. The proxy has a chain of advice/interceptors; one link in the chain for transactions is `org.springframework.transaction.interceptor.TransactionInterceptor`.

Key components:

| Component | Role |
| --- | --- |
| **Caller** | A controller, another service, a scheduled task, or code calling a Spring bean. |
| **AOP proxy** | The outer object typically returned by the injector; receives the call before the target. |
| **Transaction advisor / pointcut** | Determines which methods need transaction advice applied based on metadata. |
| **TransactionAttributeSource** | Provides the `TransactionAttribute` of the method/class (for example, from `@Transactional`), including propagation, isolation, rollback rules, read-only, timeout, and manager qualifier. |
| **TransactionInterceptor** | A `MethodInterceptor` that executes transaction advice around the method invocation. |
| **TransactionManager** | Performs acquiring/joining, committing/rolling back, and releasing/suspending transaction resources. Imperative: `PlatformTransactionManager`; reactive: `ReactiveTransactionManager`. |
| **Target method** | The Java method written by the developer; performs business logic with JDBC/JPA or an appropriate resource. |
| **Resource** | JDBC `Connection`, JPA `EntityManager`, R2DBC `Connection`, etc. that actually participates in the transaction. |

Path diagram (illustrating an imperative transaction, call through a proxy):

```text
Caller
  |
  | 1. call injected Spring bean
  v
AOP PROXY
  |
  | select matching advice for method
  v
TransactionInterceptor
  |
  | 2. read TransactionAttribute (from @Transactional, etc.)
  | 3. select suitable PlatformTransactionManager
  | 4. begin or join transaction
  |    (may bind resource to thread)
  |
  | 5. invocation.proceed()
  v
TARGET METHOD / business logic
  |
  | JDBC / JPA / repository / another service ...
  |
  +---------------------------+
                              |
             return / throw exception
                              |
                              v
TransactionInterceptor
  |
  | 6a. normal completion   --> request COMMIT
  | 6b. exception           --> decide ROLLBACK or COMMIT
  |     per rollback rules and transaction state
  | 7. cleanup / restore context
  v
AOP PROXY --> Caller
        (return result or throw exception)
```

**Key takeaway:** `TransactionInterceptor` runs *around the business call*, typically managing the transaction **before entering the target** and **after the target exits**. Code inside the target does not have to call `commit()` itself when managed by Spring; the transaction manager decides commit/rollback.

This is a logical model, not a line-by-line diagram of Spring's source code. In practice there may be multiple advisors (logging, security, retry, metrics, etc.), and their ordering can affect which advice runs inside or outside the transaction.

## 2. What Causes a Call to Be Intercepted?

### Both metadata and runtime infrastructure are required

`@Transactional` by itself is **metadata**. To turn the annotation into runtime behavior, an imperative Spring application typically needs:

1. A Spring bean containing a method defined as transactional.
2. Transaction management enabled via `@EnableTransactionManagement`, XML `<tx:annotation-driven/>`, or the corresponding auto-configuration.
3. A suitable `TransactionManager` (for example `JdbcTransactionManager` for JDBC, `JpaTransactionManager` for JPA).
4. A caller invoking **through the Spring proxy** rather than instantiating the target directly with `new` or calling internally via `this.method()`.
5. Data access operations that actually participate in the resource managed by the manager.

JDBC configuration example (fragment, not runnable standalone because `DataSource` is not declared):

```java
@Configuration
@EnableTransactionManagement
public class TxConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Requires importing `org.springframework.context.annotation.*`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.jdbc.support.JdbcTransactionManager`, and `javax.sql.DataSource`. `@EnableTransactionManagement` registers the infrastructure to detect transactional metadata, create advisors/proxies, and apply `TransactionInterceptor` when a method is called through a proxy.

If a method **has no transaction metadata** (directly or from an applicable class/interface), transaction advice does not orchestrate it merely because the method uses SQL. If a bean is already proxied by another advice, the mere presence of a proxy is also not enough to prove that a transaction is active for the method in question.

### Where can `@Transactional` be placed?

Placing it on a **public service method** is usually easiest to read and most consistent. The annotation can be placed on a class or a method; more specific method-level metadata takes precedence when resolution occurs. Spring also supports interface-level annotations in suitable proxy modes, though Spring documentation recommends placing the annotation on the concrete class/method to avoid differences between proxies and AspectJ weaving.

In Spring Framework 6+, class-based proxies can intercept certain `protected` or package-visible methods from external calls; interface-based proxies require public methods belonging to the proxied interface. **Private methods do not become transactional entry points in proxy mode.** Do not assume all non-public methods are intercepted under the same rules: that depends on the proxy type and version/configuration.

## 3. Inside `TransactionInterceptor`: Step-by-Step Flow

### Step 1 — Receive `MethodInvocation`

`TransactionInterceptor` implements AOP Alliance `MethodInterceptor`. When Spring AOP calls `invoke(MethodInvocation)`, the interceptor has information about the method, target class, and the `proceed()` callback to forward the call to the next advice or to the target.

Do not confuse `MethodInvocation` here with an HTTP request. A web request can call multiple service methods; each intercepted service method is a separate AOP boundary, and propagation decides whether they use one or multiple physical transactions.

### Step 2 — Determine transaction attributes

`TransactionInterceptor` inherits its logic from `TransactionAspectSupport`. The infrastructure uses `TransactionAttributeSource` to look up metadata for the method/class, for example:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    readOnly = false,
    rollbackFor = IOException.class
)
public void importFile() throws IOException {
    // Business method.
}
```

This is a **fragment**: it needs imports and a Spring context. The attributes tell the interceptor the business intent. They are **not** the transaction manager and **do not by themselves guarantee** that resources have joined the transaction.

If a method is proxied but has no corresponding transaction attributes, calling it does not imply starting a transaction merely because it sits on a proxy.

### Step 3 — Resolve the manager and transaction boundary

For imperative code, Spring needs a `PlatformTransactionManager` such as `JdbcTransactionManager`, `DataSourceTransactionManager`, or `JpaTransactionManager`. When multiple managers exist, the `@Transactional(transactionManager = "ordersTx")` qualifier or a default configuration helps select the right bean.

The manager is asked to start or join a transaction according to propagation:

- `REQUIRED` (default): if a suitable transaction already exists, join it; otherwise, start a new one.
- `REQUIRES_NEW`: start an independent physical transaction, potentially suspending the outer transaction.
- `NESTED`: may use a savepoint depending on the manager/resource.
- `SUPPORTS`: may execute without an actual transaction if none exists.

**Passing through the interceptor does not mean a new physical `BEGIN` every time.** If an inner method uses `REQUIRED` and a matching transaction already exists, the manager may only open a **logical scope** participating in the running physical transaction.

Two-method example:

```java
@Transactional
public void createInvoice() {
    invoiceRepository.save(...);
    taxService.calculateAndSave(...); // another service bean, same manager
}

@Transactional
public void calculateAndSave(...) {
    // Default REQUIRED: typically joins createInvoice()'s transaction.
}
```

The `...` placeholders represent application data and methods; this is not standalone runnable code. With the same manager and properly participating resources, a single physical commit at the outer level can confirm both operations.

### Step 4 — Invoke the business method

After setting up the transaction context, the interceptor calls `invocation.proceed()`. The call continues through any remaining advice and finally enters the target method. The business method uses repositories/DAOs/JdbcTemplate as usual.

With imperative JDBC, Spring typically binds the resource to the thread via `TransactionSynchronizationManager`. `JdbcTemplate` obtains the transaction-participating JDBC connection from the same `DataSource` via `DataSourceUtils`. Thus multiple `jdbcTemplate.update(...)` calls can share the same transaction without the target method having to manage `setAutoCommit(false)` itself.

**The interceptor does not turn every SQL call from any datasource into a single transaction:** a connection opened manually via `DriverManager` or from a different datasource may sit outside the managed transaction. With JPA, the `EntityManagerFactory` must match; with R2DBC, the `ConnectionFactory` and reactive context must match.

### Step 5 — Receive the result or exception from the target

There are two fundamental branches:

- **Target returns normally:** the interceptor asks the manager to complete toward a commit. The manager may still roll back if the physical transaction was already marked rollback-only, or the commit may fail due to a DB/driver error.
- **Target throws an exception:** the interceptor evaluates the exception against rollback rules, then asks the manager to roll back or commit per configuration. The exception is typically propagated to the caller (possibly accompanied by another exception raised while completing the transaction).

With `@Transactional` defaults in common configurations, **`RuntimeException` and `Error` trigger rollback; checked exceptions do not trigger rollback by default**. You can specify `rollbackFor` or `noRollbackFor`. This rule is also affected by transactions already marked rollback-only and resource errors: you cannot guarantee "checked exceptions always commit".

### Step 6 — Cleanup and context restoration

After commit/rollback or error handling, the infrastructure cleans up transaction status/resources according to the manager's responsibility. If an inner method joined an outer one, Spring must restore the calling scope's transaction information rather than arbitrarily committing or closing the outer physical transaction. Once the proxy returns control, the caller sees the result or exception based on how the transaction actually completed.

**Do not think "once the method returns, the transaction cannot fail".** `commit()` executes in the advice layer after the method body has computed its return value; if commit fails or the transaction is rollback-only, the caller can receive an exception even though the target reached the `return` statement.

## 4. Pseudocode to Understand "Wrapping", Not Original Spring Source

The snippet below models the *idea* of imperative transaction advice. This is **pseudocode**, not the actual method signatures or source code of `TransactionInterceptor`, and is not meant to compile:

```text
attr = transactionAttributeSource.resolve(invokedMethod, targetClass)
manager = resolveTransactionManager(attr)
status = manager.getTransaction(attr)  // create or join depending on propagation

try {
    value = invocation.proceed()       // run remaining advice and business logic
    manager.commit(status)            // may roll back if rollback-only
    return value
} catch (Throwable error) {
    if (attr.rollbackOn(error)) {
        manager.rollback(status)
    } else {
        manager.commit(status)
    }
    throw error
} finally {
    restoreTransactionContext()
}
```

**Warning on simplification:** Real Spring also handles branches without transaction attributes, transaction synchronization, method identification, multiple propagation modes, rollback-only, commit/rollback errors, special return types, and reactive flows. Therefore you cannot deduce everything precisely from pseudocode, especially the exception-throwing order when `manager.commit()` itself fails. The goal of the pseudocode is to clarify the **sequence begin → proceed → commit/rollback → cleanup**.

An easy way to remember it is:

```text
BEFORE: TransactionInterceptor determines the transaction boundary
AROUND: invocation.proceed() passes the call into the business method
AFTER : TransactionInterceptor inspects the result/exception and ends the scope
```

What is "wrapped" here is a **method invocation through a proxy**, not every line of code running in the same HTTP request, not newly spawned threads, and not internal calls within the object.

## 5. Runnable Java 17+ Example: Observing Proxy, Transaction, and Rollback

The example uses Spring Framework 6.2.x, Spring JDBC, H2 in-memory database, Java 17+, and Maven. Two service beans have `@Transactional`:

- `OrderService.place(...)` writes an order.
- `AuditService.record(...)` writes an audit record in the **same datasource**.
- When an `IllegalStateException` is intentionally thrown after both operations, the interceptor handles rollback; neither the order nor the audit record from the failing call remains.
- When the method completes normally, the interceptor commits; both records from the successful call persist.
- Prints `AopUtils.isAopProxy(...)` to confirm the retrieved bean is an AOP proxy and `TransactionSynchronizationManager` to check whether a transaction is active inside the method.

The project requires neither Spring Boot nor a database server.

### 5.1. Create the project structure

```text
transaction-interceptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionInterceptorDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-interceptor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TransactionInterceptorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Contents of `TransactionInterceptorDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionInterceptorDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:tx_interceptor;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc, AuditService audit) {
            return new OrderService(jdbc, audit);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void record(int orderId) {
            System.out.println(
                    "audit.txActive="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "INSERT INTO audit_events (order_id, description) "
                    + "VALUES (?, ?)",
                    orderId, "order placed");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService audit;

        public OrderService(JdbcTemplate jdbc, AuditService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void place(int id, boolean failAfterAudit) {
            System.out.println(
                    "order.txActive="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "INSERT INTO orders (id, description) VALUES (?, ?)",
                    id, "sample order");

            // Calls another Spring bean so the audit proxy is traversed.
            // Default Propagation.REQUIRED => joins the current transaction.
            audit.record(id);

            if (failAfterAudit) {
                throw new IllegalStateException("simulated failure");
            }
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // DDL runs before business operations in the experiment.
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        order_id INT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            OrderService orders = context.getBean(OrderService.class);
            AuditService audit = context.getBean(AuditService.class);

            System.out.println(
                    "orderProxy=" + AopUtils.isAopProxy(orders));
            System.out.println(
                    "auditProxy=" + AopUtils.isAopProxy(audit));

            // First pass: both INSERTs succeed => commit.
            orders.place(1, false);

            // Second pass: both INSERTs run, then an exception is thrown
            // => interceptor rolls back the second pass's transaction.
            try {
                orders.place(2, true);
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }

            Integer orderCount = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class);
            Integer auditCount = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_events", Integer.class);

            System.out.println("orders=" + orderCount);
            System.out.println("auditEvents=" + auditCount);
        }
    }
}
```

### 5.3. Compile and run

Requires JDK 17+ and Maven; on first run Internet access is needed for Maven to download dependencies. In the `transaction-interceptor-demo` directory, run:

```bash
mvn -q clean compile exec:java
```

Lines **printed by the program itself**, excluding environment-dependent logs:

```text
orderProxy=true
auditProxy=true
order.txActive=true
audit.txActive=true
order.txActive=true
audit.txActive=true
caught=simulated failure
orders=1
auditEvents=1
```

Step-by-step explanation:

1. `@EnableTransactionManagement` causes Spring to create proxies for the two service classes with transactional methods. They declare no business interface, so Spring can use class-based proxies.
2. When `orders.place(1, false)` is called, the call enters the `OrderService` proxy. The interceptor reads the default transaction metadata and asks `JdbcTransactionManager` to start JDBC transaction T1. Inside the method, `isActualTransactionActive()` is `true`.
3. `audit.record(1)` goes through the `AuditService` proxy. Due to default `REQUIRED` and the same manager/datasource, the inner method joins T1 and does not perform a separate physical commit when `record` finishes.
4. `place(1,false)` returns normally, and the outer interceptor requests a commit. Both records from T1 persist.
5. `place(2,true)` opens T2. Both INSERTs occur, but the method throws `IllegalStateException`. The outer interceptor sees the exception under the default rollback rules and requests rolling back T2.
6. `main` catches the exception after it passes back through the proxy. T2 has been rolled back; T1 from the previous call already committed and is unaffected.
7. The two `SELECT COUNT(*)` queries at the end use another connection outside the completed transaction, so they see exactly one order and one audit record.

The lesson from this example is that **when the transaction ends is determined at the interceptor layer**, while the business method body only performs data operations.

> **Observation limitation:** `AopUtils.isAopProxy(...) == true` confirms the bean has an AOP proxy, but by itself this does not prove that *the method in question* definitely has transaction advice. Combining checks on the target method, transaction manager/resource, and rollback tests provides complete evidence.

### 5.4. Optional experiment

After running the original version, you can change the second call's argument from `orders.place(2, true)` to `orders.place(2, false)` and rerun on a fresh JVM. Both passes then complete normally: the `orders` and `auditEvents` counts are both 2; the `caught=...` line does not appear. Comparing the success branch and error branch shows that the commit/rollback decision does not live in the two SQL statements inside the business method.

In production, you should add integration tests for SQL errors, timeouts, rollback-only, and multi-table updates; do not rely solely on `isActualTransactionActive()`.

## 6. Why Self-Invocation Makes Calls "Escape" the Interceptor

This is the most common mistake when misunderstanding transaction proxies.

```java
@Service
public class ReportService {

    public void generate() {
        saveReport();  // equivalent to this.saveReport()
    }

    @Transactional
    public void saveReport() {
        // Write data requiring a transaction.
    }
}
```

The code snippet is a **fragment** (needs `@Service`, `@Transactional` imports, and persistence logic). Suppose a caller invokes `reportService.generate()` from the Spring context:

- The caller goes through the proxy to `generate()`, but `generate()` has no transaction metadata.
- Inside the target, `this.saveReport()` **does not go back through the proxy**. Therefore `saveReport`'s interceptor is not invoked, and the annotation on `saveReport` does not activate a new transaction by itself.
- If `generate()` already has a transaction (for example via a class-level or outer-method annotation), `saveReport` can still use the **existing** transaction, but **`saveReport`'s own attributes** such as `REQUIRES_NEW` or `rollbackFor` will not be applied by the interceptor to the internal call.

That is why checking `TransactionSynchronizationManager.isActualTransactionActive()` inside a method may not be sufficient to conclude that *that method's own* annotation was intercepted. The transaction may have come from an outer method.

### Recommended fix: move the boundary to another bean

```java
@Service
class ReportWriter {
    @Transactional
    public void saveReport() {
        // Data operations.
    }
}

@Service
class ReportFacade {
    private final ReportWriter writer;

    ReportFacade(ReportWriter writer) {
        this.writer = writer;
    }

    public void generate() {
        writer.saveReport(); // called through the ReportWriter bean proxy
    }
}
```

This snippet is a fragment. `writer` must be a Spring-provided bean; do not call `new ReportWriter()` yourself. Besides extracting a bean, you can use `TransactionTemplate` to define the boundary programmatically. Using `AopContext.currentProxy()` and enabling `exposeProxy` is a specialized technique that couples code to AOP and is harder to maintain, so it should not be the default choice.

### When does AspectJ mode differ from proxy mode?

`@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` combined with weaving configuration and `spring-aspects` can apply transaction advice at the bytecode level instead of relying on the caller going through a proxy; thus self-invocation can also be handled. This is a separate mode that requires proper compile-time or load-time weaving and does not happen automatically just by adding the annotation to source code.

This lesson focuses on **proxy mode**, which is the standard mode.

## 7. JDK Proxy, Class-Based Proxy, and Method Visibility

Spring AOP has two common proxy families:

| Type | When suitable | Things to watch out for |
| --- | --- | --- |
| **JDK dynamic proxy** | Bean is proxied through an interface. | Callers usually work against the interface; only public interface methods are proxied. Do not retrieve the bean by casting to the implementation class if the proxy does not implement that class. |
| **Class-based proxy (CGLIB)** | Bean has no business interface or configuration requests a class proxy. | The proxy is a subclass; final classes or final methods cannot be subclassed/overridden to intercept with this mechanism. Visibility also depends on version/configuration. |

`@EnableTransactionManagement(proxyTargetClass = true)` requests class-based proxies for proxy mode configuration. When `proxyTargetClass=false`, Spring can use JDK dynamic proxies for beans with interfaces and class-based proxies for beans without interfaces; this default does not mean Spring always creates a JDK proxy.

Interface-based example:

```java
public interface PaymentService {
    void pay(long orderId);
}

@Service
public class PaymentServiceImpl implements PaymentService {
    @Override
    @Transactional
    public void pay(long orderId) {
        // ...
    }
}
```

This is a fragment: when Spring uses a JDK proxy, callers should inject `PaymentService`. `getBean(PaymentServiceImpl.class)` may fail to find the bean by the desired class or fail to cast because the proxy object only implements the interface.

**Choosing public methods and placing `@Transactional` on concrete service methods** is a readable convention that remains stable across proxy configurations. Do not rely on intercepting private/final methods or calls from constructors/`@PostConstruct`, because the proxy may not be ready yet and those mechanisms do not go through normal interception.

## 8. Exceptions Passing Through TransactionInterceptor: Understanding Rollback Decisions

### Default rollback for unchecked exceptions

```java
@Transactional
public void createCustomer() {
    jdbc.update("INSERT INTO customers ...");
    throw new IllegalArgumentException("invalid");
}
```

Illustrative fragment, SQL intentionally incomplete; do not run verbatim. When `IllegalArgumentException` exits the method through the proxy, default rollback rules request a rollback.

### Checked exceptions require declaration when rollback is desired

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders(Path file) throws IOException {
    // Read file and write to database.
    // An IOException escaping the method will request a rollback.
}
```

Fragment: needs `java.io.IOException`, `java.nio.file.Path` imports, and actual implementation. Without `rollbackFor`, checked exceptions are normally **not** included in default rollback rules; the interceptor may request a commit even though a checked exception was thrown. However, if a resource or inner scope already marked the transaction rollback-only, the physical transaction still rolls back.

### Catching an exception and returning normally

```java
@Transactional
public void process() {
    jdbc.update("INSERT INTO items ...");
    try {
        performNextStep();
    } catch (RuntimeException ignored) {
        // Exception swallowed: interceptor only sees the method return normally.
    }
}
```

Illustrative fragment. If subsequent steps fail but the exception does not escape the proxy invocation, the interceptor cannot use that exception to apply a rollback rule. If the resource has not marked itself rollback-only, the method returns normally and the transaction may commit. Choose a clear strategy: rethrow the exception, define appropriate rollback rules, or mark rollback-only via Spring's API when truly needed.

### Rollback-only and `UnexpectedRollbackException`

Two `REQUIRED` methods can create **two logical scopes** on one physical transaction. If the inner method marks the transaction rollback-only, yet the outer method catches the error and tries to return normally, the outer interceptor may call commit, but the manager forces a rollback and throws `UnexpectedRollbackException`. Reason: the caller must not mistakenly think the transaction committed.

```text
T1 (outer @Transactional)
  |
  +-- inner @Transactional REQUIRED
  |     +-- error => marks T1 rollback-only
  |
  +-- outer catches error and returns
  |
  +-- outer interceptor calls commit(T1)
  |     +-- T1 is rolled back
  |     +-- throws UnexpectedRollbackException
```

Do not fix this by catching and ignoring `UnexpectedRollbackException`. Review the business logic: if the inner operation should roll back independently, consider `REQUIRES_NEW` where appropriate (and remember that the inner's committed result will not automatically roll back with the outer), or split the boundaries differently.

## 9. Things Outside the Default "Wrapping" Scope

### Calls to another thread

An imperative transaction managed by `PlatformTransactionManager` is usually bound to the execution thread. Spawning a new thread via `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, or running an `@Async` task does not automatically carry the transaction context across.

```java
@Transactional
public void placeOrder() {
    CompletableFuture.runAsync(() -> {
        // Runs on another thread:
        // does not automatically join the calling thread's imperative transaction.
    });
}
```

Illustrative fragment. In particular, if the async task writes to the same application's database, it may use an independent connection and transaction. Do not infer "because the code is inside the braces of a `@Transactional` method, it always rolls back together".

### Reactive `Publisher`

`TransactionInterceptor` now supports both imperative and reactive paths. With reactive return types such as Reactor `Mono`/`Flux` and a `ReactiveTransactionManager`, the transaction is attached to the subscription's **Reactor Context**, not simply "started before the Java method body constructs the `Mono` and committed immediately when the method returns the `Mono`".

Visualization:

```text
caller invokes proxy method returning Mono
       |
       v
TransactionInterceptor detects reactive return type
       |
       v
builds transaction-aware Publisher
       |
       v
when subscribed and reactive pipeline runs:
    begin/join reactive transaction
    -> R2DBC operations in the same context
    -> complete/error/cancel per reactive semantics
    -> corresponding commit/rollback/cleanup
```

Spring documentation clearly distinguishes `PlatformTransactionManager` for imperative methods (including `void`) and `ReactiveTransactionManager` for reactive transactions. Do not choose `R2dbcTransactionManager` for an imperative JDBC method just because the method has `@Transactional`. For reactive cancel signals, check the exact semantics of your Spring version and reactive source instead of assuming "cancel is equivalent to normal return".

### External side effects

TransactionInterceptor only coordinates **resources managed by the manager**. If the method has already called an HTTP API, sent an email, written a file, or sent a message to a broker that does not participate in the same transaction coordinator, rolling back the database **does not automatically undo the side effect**. For multiple resources requiring atomicity, look at JTA/XA when suitable infrastructure is available; otherwise use outbox, saga, idempotency, and compensation as required by the system.

### AOP advice ordering

If there are additional `@Around` logging, security, retry, or caching advisors, advisor ordering determines which logic is wrapped inside the transaction. For example, a logging advice **outside** the transaction advice can measure commit time as well; if **inside**, it may stop measuring when the business method returns before the transaction manager commits.

You can configure the order for transaction advice via `@EnableTransactionManagement(order = ...)` and use `@Order` for other aspects. **Do not guess** the order solely from the order of annotations written on a method. When debugging commit or retry issues, inspect the actual order, because a retry outside the transaction usually has different semantics from a retry occurring inside a transaction already marked rollback-only.

## 10. How to Observe and Debug TransactionInterceptor

### Enable logging on the right namespaces

In a Spring Boot application, you can try the following settings in `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Actual logs and formatting vary by Spring version, manager, and logging backend. Do not write tests that depend on an *exact* log line. The plain Spring example in section 5 does not automatically read `application.properties` the way Spring Boot does.

### Diagnosing from outside the proxy

In an integration test or code with access to `ApplicationContext`:

```java
Object bean = applicationContext.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(bean));
```

This is a **fragment**: requires an existing `applicationContext` variable and `OrderService` class. If the proxy is a JDK proxy, use the interface type when retrieving the bean; if class-based proxy, you can use the concrete class.

When you need to inspect advisors on a Spring AOP proxy, you can use:

```java
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getAdvice().getClass().getName());
    }
}
```

This fragment can help show which advice is `TransactionInterceptor`, but a bean having an advisor does not mean every method is matched by the advice; you must verify method/pointcut metadata. Spring may create proxies that do not permit inspection this way in certain configurations.

### Observing state inside an imperative method

```java
boolean txActive =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

These are diagnostic APIs for imperative transactions. `isolation == null` may simply mean Spring did not set an explicit isolation level; **it does not mean the database has no isolation**. To know the actual JDBC isolation, query `Connection.getTransactionIsolation()` on the connection participating in the transaction.

In a JDBC service, also cross-check the `DataSource` bean of `JdbcTemplate` and the manager; in JPA, cross-check `EntityManagerFactory`. `txActive=true` can come from an outer transaction, so a single flag does not prove the call in question went through the interceptor.

### Troubleshooting checklist in order

1. **Did the caller get the bean from Spring?** Using `new MyService()` bypasses the Spring AOP proxy.
2. **Call through proxy or self-invocation?** `this.inner()` does not apply the inner method's transaction advice.
3. **Is the infrastructure enabled in the right context?** `@EnableTransactionManagement`/auto-configuration must see the service beans.
4. **Does the method have transaction metadata and can the proxy intercept it?** Check visibility, final methods/classes, interface/class-based proxies.
5. **Is the `TransactionManager` the right one?** A `@Transactional` bean using datasource A with a manager for B will not automatically roll back A.
6. **Which advisors are in the call chain?** Logging, retry, and async advice can affect boundaries.
7. **Does the method let exceptions escape through the proxy?** If caught inside the target, the interceptor may see a normal return.
8. **Are the rollback rules right?** Checked/unchecked exceptions, `rollbackFor`, `noRollbackFor`.
9. **Does inner join outer or open separately?** `REQUIRED`, `REQUIRES_NEW`, and `NESTED` behave differently.
10. **Have you run a real rollback test?** Perform writes to two tables, intentionally trigger an error on a later step, and read the data after the transaction.

## 11. Comparison Table of Easily Confused Calls

| Call | Passes through proxy advice for that method? | Transactional consequence |
| --- | --- | --- |
| Bean A calls public `@Transactional` on Spring-injected bean B | Typically **yes** | Interceptor applies B's attributes; manager begins/joins and commits/rolls back the scope. |
| Caller invokes `@Transactional` method directly on bean B's proxy | **Yes** when pointcut/visibility match | Transaction advice applies to that method. |
| Inside target B calling `this.otherTransactionalMethod()` | **No** for the inner method in proxy mode | No new boundary from the inner annotation; may still run in the outer transaction. |
| `new B().save()` instead of the Spring bean | **No** | No Spring transaction advice. |
| Calling a `private` method with `@Transactional` | **No** in Spring proxy mode | The method's own annotation does not create a transaction. |
| `@Transactional` on a `final` class with class-based proxy | Cannot use subclass proxy to intercept | Must redesign interface/proxy or use appropriate configuration. |
| Proxied method where DAO opens a different JDBC connection outside the manager | May **have a proxy**, but DAO does not participate in the resource | That SQL is not automatically inside the manager's transaction. |
| Inner `REQUIRED` intercepted inside an outer transaction | **Yes** | Has an inner logical scope but usually shares the physical transaction. |
| Inner `REQUIRES_NEW` intercepted through a Spring proxy | **Yes** | Suspends outer and starts a new transaction if supported by the manager. |
| Reactive method returning `Mono` with a reactive manager | **Yes**, reactive path | Transaction is bound to subscription/reactive context; thread-bound JDBC model does not apply. |

Phrases like "typically" and "may" preserve genuinely important conditions: Spring mode, runtime configuration, resource participation, and manager type. You cannot conclude every case solely from the annotation name.

## 12. Self-Check

**Question 1.** Why doesn't a `@Transactional` method need to call `connection.commit()`?

Because the proxy/`TransactionInterceptor` asks `TransactionManager` to coordinate the transaction before and after the method invocation. Business code performs data operations through resources managed by the manager; the manager is responsible for commit/rollback.

**Question 2.** Does `@Transactional` on an inner method always create a new transaction?

No. Default `REQUIRED` joins an existing transaction. If both outer and inner go through proxies, the inner method is typically a logical scope inside the same physical transaction; the final commit sits at the outer level.

**Question 3.** If the outer method catches a `RuntimeException` from the inner method and returns normally, will it always commit?

No. The inner method may have marked the shared transaction rollback-only; the outer interceptor may receive `UnexpectedRollbackException` when attempting to commit.

**Question 4.** Is `this.save()` different from calling `writer.save()` through an injected Spring bean?

Yes. In proxy mode, `this.save()` bypasses the inner method's proxy. `writer.save()` enters the `writer` bean's proxy if Spring-injected and the method is eligible.

**Question 5.** Does `AopUtils.isAopProxy(bean) == true` prove all methods are transactional?

No. Knowing a bean has an AOP proxy is just one observation step. You must know which methods the advisor/pointcut matches and whether resources participate in the transaction.

**Question 6.** Why can a method with a `return` statement still cause the caller to receive a transaction error?

Because the transaction advice performs the commit after the method body returns. The commit may fail, or the manager may roll back due to rollback-only.

**Question 7.** Why doesn't `@Transactional` cover a `CompletableFuture.runAsync(...)` just because it is created inside the method?

Because the imperative transaction context is thread-bound; it does not automatically propagate to new threads. To have a transaction in another task, you must design a separate boundary and avoid assuming shared rollback.

**Question 8.** Is a method returning `Mono` committed right after constructing the `Mono` object?

You should not think of it that way. With a reactive manager, the transaction is tied to subscription and execution of the reactive pipeline in the Reactor Context.

## 13. Code Review Checklist

- [ ] The business method belongs to a Spring bean and is called through its proxy.
- [ ] `@EnableTransactionManagement` or Spring Boot transaction auto-configuration has activated the infrastructure.
- [ ] Method/class transaction attributes resolve properly.
- [ ] Proxy type and method visibility/final modifiers allow interception.
- [ ] `TransactionManager` is appropriate and aligned with `DataSource`/`EntityManagerFactory`/`ConnectionFactory`.
- [ ] No unintended self-invocation bypassing an inner method's annotation.
- [ ] Propagation matches intent: join existing, new transaction, or nested savepoint.
- [ ] Exceptions meant to trigger rollback actually escape the boundary or mark rollback-only.
- [ ] Advice ordering with logging/retry/async is understood if they coexist.
- [ ] Reactive methods and imperative methods use the right transaction infrastructure.
- [ ] Integration tests exist proving both commit and rollback on real data.

## Official References

1. [Spring Framework — Understanding the Spring Framework's Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxy, advisor, `TransactionInterceptor`, and invocation lifecycle.
2. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): enabling annotation-driven transactions, proxy vs AspectJ, visibility, and self-invocation.
3. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and rollback-only.
4. [Spring Framework — `TransactionInterceptor` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionInterceptor.html): `MethodInterceptor`/`invoke` and transaction advice.
5. [Spring Framework — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html): transaction handling around methods and cleanup.
6. [Spring Framework — Controlling JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager` and how JDBC participates in Spring transactions.
7. [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` and `TransactionalOperator` when direct programmatic boundaries are needed.
