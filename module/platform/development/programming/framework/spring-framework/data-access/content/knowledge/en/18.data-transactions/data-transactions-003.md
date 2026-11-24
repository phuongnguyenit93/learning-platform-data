# `@Transactional` and `TransactionTemplate` in Spring: Boundaries, Commit, and Rollback

A business operation may require multiple SQL statements yet must produce **a single consistent outcome**. For example, transferring 10 units from account A to account B: if debiting A succeeds and crediting B fails, the system must not persist a state where only A was debited. A **transaction** groups related operations into a single unit of commit or rollback according to the capabilities of the database and transaction manager.

In Spring Framework Data Access, the two common ways to control transactions are:

- **`@Transactional`**: declares transaction rules on a method/class; Spring's transaction interceptor/proxy handles opening, joining, committing, or rolling back.
- **`TransactionTemplate`**: uses a Java API calling `execute(...)` or `executeWithoutResult(...)`, placing the transaction boundary directly around the callback.

Both approaches can use the same `PlatformTransactionManager` and the same `DataSource`, but they differ in where configuration lives, how proxy invocation works, and how flexible they are when handling discrete blocks of work.

This article focuses on **imperative transactions** with Spring JDBC and relational databases. Reactive transactions use a different model, distinguished at the end.

## 1. What Is a Transaction and Why Is a Clear Boundary Needed?

Consider account A with a balance of 100 and account B with a balance of 100. A transfer of 10 has two steps:

~~~sql
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
UPDATE accounts SET balance = balance + 10 WHERE id = 2;
~~~

If both are in the same transaction and both steps succeed, after commit the result is A=90, B=110. If the second step encounters an error causing the transaction to roll back, the result remains A=100, B=100. Without an enclosing transaction, each SQL statement may be committed individually under auto-commit mode, risking saving only the first step.

The **ACID** properties commonly used to describe transactions:

| Property | Practical Meaning |
| --- | --- |
| Atomicity | Changes within the transaction scope are committed together or rolled back per DB capabilities; "half-completed business work" is not allowed after rollback. |
| Consistency | The transaction must satisfy consistency constraints; **business rules still have to be coded and checked**, annotations do not create them automatically. |
| Isolation | How concurrent transactions see or affect one another depends on isolation levels, locks, and database mechanisms. |
| Durability | After a successful commit, the DB is responsible for ensuring durability according to its storage mechanism. |

**A transaction does not by itself guarantee a completely correct transfer business operation:** you also need to check affected row counts, whether the balance is sufficient, duplicate-transfer protection, concurrency handling, and appropriate isolation/locking levels. The following examples prioritize demonstrating commit/rollback across two SQL statements rather than a complete banking system.

### Participating Components in Spring JDBC

~~~text
Client -> Spring-managed service
             |
             +-- @Transactional via proxy
             |         or
             +-- TransactionTemplate.execute(...)
                         |
                         v
              PlatformTransactionManager
                         |
                         v
               DataSource / JDBC Connection
                         |
                JdbcTemplate, Repository
                         |
                      Database
~~~

- `PlatformTransactionManager` is Spring's imperative transaction management contract; implementations for JDBC can be `DataSourceTransactionManager` or `JdbcTransactionManager`.
- `DataSource` supplies connections. `JdbcTemplate` obtains connections through Spring infrastructure, thereby participating in the transaction bound to the current thread on the same resource.
- `TransactionDefinition` describes propagation, isolation, timeout, and read-only; `TransactionStatus` allows marking rollback-only and inspecting status within the provided scope.
- When Spring Boot configures an appropriate `DataSource` and transaction manager, most applications use declarative or programmatic transactions without manually writing `connection.setAutoCommit(false)` and `commit()/rollback()`.

**Key condition:** operations must actually use resources managed by **the same transaction manager**. A `DriverManager.getConnection(...)` opened manually outside Spring's `DataSource` does not automatically participate in the service's transaction.

## 2. `@Transactional`: Declaring Transaction Boundaries

Example of a service-layer method:

~~~java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount) {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, fromId);

        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId);
    }
}
~~~

This is an **illustrative Spring class snippet**, requiring imports for `@Service`, `@Transactional`, `JdbcTemplate`, and appropriate beans/DataSource; a full runnable example appears in section 5. The Spring transaction interceptor wraps transaction logic **around valid method calls through the proxy**:

1. Another bean calls `transfer(...)` through the Spring proxy.
2. The transaction interceptor selects `PlatformTransactionManager` and opens a transaction if none exists, or joins the current transaction according to propagation.
3. `JdbcTemplate` executes the two SQL statements on the connection participating in that transaction.
4. If the method completes normally and the transaction is not marked rollback-only, Spring requests a commit at the corresponding boundary.
5. If an exception matching the rollback rules escapes the method, Spring requests a rollback or marks the participating transaction as rollback-only.

**`@Transactional` is metadata; the annotation by itself does not open a transaction on an object instantiated manually with `new`.** A Spring-managed bean, enabled transaction management infrastructure (`@EnableTransactionManagement` or appropriate Spring Boot auto-configuration), and a corresponding transaction manager are required.

### Important Default Rules

Under standard Spring defaults:

| Attribute | Default |
| --- | --- |
| Propagation | `Propagation.REQUIRED` |
| Isolation | `Isolation.DEFAULT` (per database/transaction manager) |
| Read-only | `false` |
| Timeout | Transaction manager default, or unlimited if unsupported by the system |
| Rollback | On `RuntimeException` and `Error`; **checked exceptions** normally do not trigger rollback by default |

Note: a project may configure a global rollback policy different from the default. Do not infer behavior solely from the annotation if custom transaction configuration exists.

`REQUIRED` means: **create a new transaction if no suitable one exists; otherwise join the existing one**. Therefore, every `@Transactional` does not equate to "always having an independent physical transaction."

### Opting In to Rollback for Checked Exceptions

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public void importDocument() throws java.io.IOException {
    // Multiple database and I/O operations...
}
~~~

This is only a **signature/illustration**, not a standalone runnable program. With `rollbackFor`, if `IOException` escapes the method through the transaction interceptor, Spring also chooses rollback. There is also `noRollbackFor` to customize exceptions that do not cause rollback. Rollback rules affect **how the transaction manager behaves**, and do not automatically undo an I/O change on the filesystem or an HTTP call.

## 3. `TransactionTemplate`: Controlling Transactions via Callbacks

`TransactionTemplate` belongs to `org.springframework.transaction.support`. It accepts a `PlatformTransactionManager`, creates/joins a transaction per configuration, and then invokes an application-provided callback.

~~~java
@Service
public class TransferWithTemplate {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public TransferWithTemplate(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    public void transfer(int fromId, int toId, int amount) {
        template.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, fromId);
            jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);
        });
    }
}
~~~

This is an **illustrative** Spring class; it requires importing `Service`, `JdbcTemplate`, `PlatformTransactionManager`, and `TransactionTemplate`. Whenever execution enters `executeWithoutResult`, the transaction is controlled through the template right at that point. There are two main APIs:

- `template.execute(status -> result)` when you want to return a value of type `T`.
- `template.executeWithoutResult(status -> { ... })` when the callback does not need to return a result.

When the callback finishes normally, the template executes commit logic at its boundary; when the callback throws an unchecked exception or the transaction is marked rollback-only, the system executes the appropriate rollback logic.

### Proactive Rollback Without Throwing an Exception

~~~java
template.executeWithoutResult(status -> {
    int affected = jdbc.update(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        amount, fromId);

    if (affected != 1) {
        status.setRollbackOnly();
        return;
    }

    jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        amount, toId);
});
~~~

The snippet above only runs in a method where `template`, `jdbc`, `amount`, `fromId`, and `toId` are declared. `status.setRollbackOnly()` signals that the transaction **must not be committed**. The `return` statement here only exits the `void` callback; the template handles the rollback-only flag. No exception automatically notifies the caller of a business failure: if the caller needs to know about the failure, return an explicit status or throw an appropriate exception.

**Do not treat `TransactionTemplate` as a separate connection**: it also uses the transaction manager; in Spring JDBC, `JdbcTemplate` joins that transaction when sharing the same `DataSource`. If executed inside an outer transaction with `REQUIRED` propagation, rollback-only inside the callback can affect **the entire outer transaction**.

### Customizing Template Configuration

~~~java
TransactionTemplate readTemplate = new TransactionTemplate(manager);
readTemplate.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
readTemplate.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
readTemplate.setTimeout(15);
readTemplate.setReadOnly(true);
~~~

The snippet above uses `PlatformTransactionManager manager` and requires importing `TransactionDefinition` and `TransactionTemplate`. `TransactionTemplate` holds **configuration state**, so it should be configured **once before shared use**; avoid mutating timeout, isolation, or propagation on the same instance used concurrently by multiple threads. Use separate instances when different transaction policies are needed. `readOnly` is a hint/signal and not an absolute write-blocking mechanism across all databases.

## 4. Direct Comparison of the Two APIs

| Aspect | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Style | Declarative: configured via annotation | Programmatic: callback invoked in Java |
| Transaction boundary | Usually wraps a Spring-intercepted method | Exact scope of the `execute` callback |
| Proxy dependency | **Yes** in default proxy mode; self-invocation is a trap | **No** proxy needed for `template.execute` itself to manage |
| Rollback rules | Annotation, configured rollback rules, exception escaping method | Exceptions and `TransactionStatus.setRollbackOnly()` inside callback |
| Returning results | Method returns value per normal signature | `execute(status -> T)` returns callback result |
| Adjusting configuration | Attributes of `@Transactional` | Set on `TransactionTemplate` before calling |
| When more readable | Most service methods having one enclosing transaction | Small sections needing a transaction, multiple scoped blocks, proactive rollback |
| Coupling to Spring | Annotation on business class | Direct reference to `TransactionTemplate` and `TransactionStatus` |
| Technical overhead | Proxy/interceptor, requires understanding bean calls | Callback and template setup code, requires understanding nested scopes |
| JDBC resource | Same manager/DataSource when properly configured | Same manager/DataSource when properly configured |

The two choices **are not mutually exclusive**: an application can use `@Transactional` for most services and `TransactionTemplate` in spots requiring specialized boundaries. However, when a `TransactionTemplate(REQUIRED)` executes inside a `@Transactional(REQUIRED)` method, those are normally **logical scopes participating in one physical transaction**, not two independent commits.

## 5. Runnable Spring Boot + Java 17 Example: Verifying Both Transaction Styles

The following example runs standalone in a small Maven project and requires no database server because it uses **in-memory H2**. It demonstrates:

1. Transferring 10 successfully using `@Transactional`.
2. Throwing `IllegalStateException` after debiting using `@Transactional`: rollback, balances unchanged.
3. Transferring 20 successfully using `TransactionTemplate`.
4. Throwing an error after debiting using `TransactionTemplate`: rollback.
5. Calling `TransactionStatus.setRollbackOnly()` in the template: rollback even though the callback finishes normally.

Prerequisites: **JDK 17+**, Maven 3.9+, and internet access or a Maven cache containing the dependencies on the first run. This guide uses Spring Boot **3.3.5** as an illustrative baseline (based on Spring Framework 6.x); new applications should choose a project-supported Boot version and check Java compatibility.

Create the directory tree:

~~~text
transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── tx/
                    ├── TxDemoApplication.java
                    └── TransferService.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
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
~~~

**File `src/main/java/demo/tx/TransferService.java`:**

~~~java
package demo.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public TransferService(
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(transactionManager);
    }

    // Public method called from another bean through a Spring proxy.
    @Transactional
    public void annotatedTransfer(int amount, boolean failAfterDebit) {
        transferSteps(amount, failAfterDebit);
    }

    // TransactionTemplate starts/joins a transaction at execute().
    public void templateTransfer(int amount, boolean failAfterDebit) {
        template.executeWithoutResult(status ->
                transferSteps(amount, failAfterDebit));
    }

    // Explicit rollback without throwing an exception.
    public void templateRollbackOnly(int amount) {
        template.executeWithoutResult(status -> {
            debit(amount);
            status.setRollbackOnly();
        });
    }

    // Private helper running INSIDE the transaction of the method above.
    private void transferSteps(int amount, boolean failAfterDebit) {
        debit(amount);

        if (failAfterDebit) {
            throw new IllegalStateException("simulated failure");
        }

        int credited = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, 2);
        if (credited != 1) {
            throw new IllegalStateException("credit did not update one row");
        }
    }

    private void debit(int amount) {
        int debited = jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, 1);
        if (debited != 1) {
            throw new IllegalStateException("debit did not update one row");
        }
    }
}
~~~

**File `src/main/java/demo/tx/TxDemoApplication.java`:**

~~~java
package demo.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxDemoApplication implements CommandLineRunner {
    private final JdbcTemplate jdbc;
    private final TransferService transferService;

    public TxDemoApplication(
            JdbcTemplate jdbc,
            TransferService transferService) {
        this.jdbc = jdbc;
        this.transferService = transferService;
    }

    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        // Fresh table/data on in-memory H2.
        jdbc.execute("""
            CREATE TABLE accounts (
                id INT PRIMARY KEY,
                balance INT NOT NULL
            )
            """);
        jdbc.update("INSERT INTO accounts(id, balance) VALUES(?, ?)", 1, 100);
        jdbc.update("INSERT INTO accounts(id, balance) VALUES(?, ?)", 2, 100);
        System.out.println("start=" + balances());

        transferService.annotatedTransfer(10, false);
        System.out.println("annotated_success=" + balances());

        try {
            transferService.annotatedTransfer(5, true);
        } catch (IllegalStateException ex) {
            System.out.println("annotated_error=" + ex.getMessage());
        }
        System.out.println("annotated_rollback=" + balances());

        transferService.templateTransfer(20, false);
        System.out.println("template_success=" + balances());

        try {
            transferService.templateTransfer(7, true);
        } catch (IllegalStateException ex) {
            System.out.println("template_error=" + ex.getMessage());
        }
        System.out.println("template_rollback=" + balances());

        transferService.templateRollbackOnly(4);
        System.out.println("rollback_only=" + balances());
    }

    private String balances() {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 2);
        return a + "," + b;
    }
}
~~~

**Run from the `transaction-demo/` directory:**

~~~bash
mvn -q spring-boot:run
~~~

The **lines printed by the program itself** (excluding Spring Boot and Maven startup/status logs):

~~~text
start=100,100
annotated_success=90,110
annotated_error=simulated failure
annotated_rollback=90,110
template_success=70,130
template_error=simulated failure
template_rollback=70,130
rollback_only=70,130
~~~

### Exact Breakdown of the Output

- Initially A=100, B=100.
- `annotatedTransfer(10, false)` debits 10 and credits 10; the method returns normally, the transaction commits, resulting in 90,110.
- `annotatedTransfer(5, true)` debits A and then throws `IllegalStateException` **before** crediting B. Because an unchecked exception escapes the method through the proxy, the transaction rolls back; both balances remain 90,110.
- `templateTransfer(20, false)` creates a transaction via `TransactionTemplate` and commits both updates; balances become 70,130.
- `templateTransfer(7, true)` throws an error inside the callback; the template rolls back, balances remain 70,130.
- `templateRollbackOnly(4)` executes one `UPDATE` yet calls `status.setRollbackOnly()` before the callback finishes. There is no exception, yet it still rolls back, so balances remain 70,130.

**Why does the example call methods from `TxDemoApplication` into `TransferService`?** The two classes are two distinct Spring beans: calls to `annotatedTransfer` go through the transactional proxy. If `TransferService` called `this.annotatedTransfer(...)` on itself, the proxy rules could be bypassed. The `transferSteps` method is a private helper that needs no annotation because it already executes inside the transaction established by the public method.

**Why does H2 automatically have a transaction manager?** Spring Boot with `spring-boot-starter-jdbc` and H2 on the classpath can auto-configure a `DataSource`, `JdbcTemplate`, and a `PlatformTransactionManager` for JDBC. `@EnableTransactionManagement` is written explicitly to illustrate enabling declarative transactions. In Boot applications with appropriate auto-configuration, adding this annotation manually is usually unnecessary.

**Business limitations of the example:** monetary amounts are symbolic integers, with no sufficient-funds check, no concurrency locking, and no idempotency. For real money, use `BigDecimal`/decimal types and add appropriate business constraints and concurrency controls.

## 6. Exceptions, Commit, and Rollback: Understanding Each Case Properly

### 6.1. `@Transactional` Does Not Roll Back for Every `Exception` by Default

Under default configuration:

| What happens inside the method | Typical outcome when transaction is Spring-managed |
| --- | --- |
| Method completes normally, not rollback-only | Commits at the scope responsible for committing |
| `RuntimeException` escapes method | Rolls back / marks rollback-only |
| `Error` escapes method | Rolls back / marks rollback-only |
| Checked exception such as `IOException` escapes method | By default **does not** request rollback, unless configured with `rollbackFor` or a global rule |
| Method **catches and swallows** exception then returns | Interceptor may treat the method as successful; it does not automatically know an error was caught |
| Code explicitly marks transaction rollback-only | Transaction is not committed, even when the method returns normally |

A very common mistake:

~~~java
@Transactional
public void saveBoth() {
    jdbc.update("INSERT INTO first_table ...");
    try {
        jdbc.update("INSERT INTO second_table ...");
    } catch (RuntimeException ex) {
        logger.warn("Second insert failed", ex);
        // Neither rethrown nor marked rollback-only.
    }
}
~~~

This is **non-runnable illustrative code**: the SQL is abbreviated and `jdbc`/`logger` are undeclared. If the error was caught and did not cause the transaction to be marked rollback-only at a deeper layer, Spring may attempt to commit the first part. With JDBC errors, the database may also have placed the resource/transaction into an uncommittable state; do not rely on catching an exception to guarantee you can continue. Business logic must explicitly decide to **rethrow the error**, configure `rollbackFor`, or mark rollback-only when appropriate.

If you need to decide rollback manually inside a `@Transactional` method, you can use:

~~~java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

This is an **API tied to a transaction currently managed by the proxy/interceptor**; if there is no matching transaction aspect in the call stack, `currentTransactionStatus()` is not a safe option. Usually it is better to let the right exception propagate out or use `TransactionTemplate` when explicit rollback-handling code is needed.

### 6.2. `TransactionTemplate` with Exceptions and Rollback-Only

~~~java
String result = template.execute(status -> {
    boolean ok = validateInput();
    if (!ok) {
        status.setRollbackOnly();
        return "REJECTED";
    }

    updateDatabase();
    return "DONE";
});
~~~

This is a code snippet inside a class that already has `template` and `validateInput()`/`updateDatabase()` methods; it is not a standalone program. `"REJECTED"` can be returned **while the transaction rolls back**. Therefore, do not infer that "the callback returned a value" means "it committed."

If the callback throws a `RuntimeException`, the template rolls back via the error path. If the callback needs to call an API throwing a checked exception, the callback interface does not declare arbitrary checked exceptions; the application can wrap the exception as unchecked or handle it and call `setRollbackOnly()` per a clear contract. Do not silently drop errors that callers need to know about.

### 6.3. Rollback-Only from an Inner Scope and `UnexpectedRollbackException`

Suppose an outer method has `@Transactional(REQUIRED)` and calls an inner method also configured with `REQUIRED`. If the inner method marks the transaction rollback-only, **the two logical scopes may be sharing a single physical transaction**. The outer method catching the error and returning normally does not mean the transaction can commit. When the outer scope attempts to commit, Spring may throw `UnexpectedRollbackException` to report that a rollback occurred instead of the expected commit.

This is intentional behavior designed to avoid falsely reporting success to the caller. If you want the inner portion to commit or roll back **independently**, consider `REQUIRES_NEW` with its own resource/connection, or structure the workflow differently; do not simply catch the exception and assume the outer scope can commit.

## 7. Propagation: Which Scope Actually Creates a Transaction?

**Propagation** defines how a scope handles an existing transaction.

| Mode | When no transaction exists | When a transaction already exists | Key takeaway |
| --- | --- | --- | --- |
| `REQUIRED` | Creates a new one | Joins the current transaction | Default and suitable for most services |
| `REQUIRES_NEW` | Creates a new one | Suspends outer scope, uses an independent physical transaction | Inner can commit/roll back independently; may require an extra connection |
| `NESTED` | Typically creates a transaction like `REQUIRED` | Uses a savepoint in the same physical transaction if supported by transaction manager/DB | Can roll back the inner scope to the savepoint |
| `SUPPORTS` | Runs without a transaction | Joins the current transaction | Does not guarantee atomicity when called standalone |
| `MANDATORY` | Throws an error | Joins the current transaction | Used when the contract requires the caller to already have a transaction |
| `NOT_SUPPORTED` | Runs without a transaction | Suspends the current transaction | Suitable for some work that does not need a transaction |
| `NEVER` | Runs without a transaction | Throws an error | Expresses a constraint that no transaction may be active |

Declarative example:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit() {
    // JDBC work intended to commit/roll back independently.
}
~~~

This snippet requires importing `Propagation` and being called **through a Spring proxy**, for instance from another bean. `REQUIRES_NEW` should not be used mechanically to write audits for every operation: the inner transaction can commit even when the outer one rolls back, and it usually needs an additional connection while the outer transaction still holds a connection. Connection pool sizing must account for that situation.

Same idea with the programmatic API:

~~~java
TransactionTemplate auditTemplate = new TransactionTemplate(manager);
auditTemplate.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

auditTemplate.executeWithoutResult(status -> {
    // An independent block subject to configuration and manager capabilities.
});
~~~

`NESTED` typically relies on JDBC savepoints and is not a universal mechanism across all transaction managers or DBs; in Spring JDBC, check `DataSourceTransactionManager`/`JdbcTransactionManager` and driver savepoint support. If the manager does not support it, it may throw an exception rather than silently creating the kind of transaction you expected.

**Isolation, timeout, and read-only on an inner `REQUIRED` scope joining an outer transaction normally cannot effectively override the characteristics of the already-existing physical transaction.** When different rules are needed, understand how the transaction manager handles or rejects conflicting settings.

## 8. Where Do Isolation, Read-Only, and Timeout Apply?

A more explicit annotation:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true,
    timeout = 20)
public CustomerReport loadReport() {
    // Query data, return materialized DTO.
}
~~~

This is an illustrative signature; it requires importing `Propagation`, `Isolation`, `Transactional` and defining `CustomerReport`. Main attributes:

- **`isolation`**: requests the isolation level when a physical transaction is created; the meaning of dirty reads, non-repeatable reads, and phantom reads still depends on the database and MVCC/locking mechanics. An isolation level placed on an inner method joining an existing transaction does not automatically upgrade the outer transaction's isolation.
- **`readOnly`**: an optimization hint / read-only intent; drivers, ORMs, DBs, and managers may handle it differently. It is not a firewall blocking every `UPDATE` statement.
- **`timeout`**: maximum transaction duration as supported by the transaction manager. Timeout does not mean immediately aborting every blocking I/O query or HTTP call; add appropriate query/network timeouts as well.
- **`rollbackFor`, `noRollbackFor`**: customize exception conditions that trigger rollback.

Place the annotation on a **service method** enclosing a complete business operation; underlying SQL repositories participate in the transaction through Spring. An excessively long transaction covering file uploads, external API calls, and waiting for user confirmation increases lock duration and holds connections long. If a process needs multiple steps that cannot fit inside a short DB transaction, design an appropriate state machine, outbox, retry/idempotency, or saga.

## 9. Proxy Traps and How to Structure Code

### 9.1. Self-Invocation: Calling a `@Transactional` Method from the Same Object

~~~java
@Service
public class InvoiceService {
    public void runJob() {
        this.saveInvoice(); // Does not go through saveInvoice()'s proxy.
    }

    @Transactional
    public void saveInvoice() {
        // JDBC inserts
    }
}
~~~

This is an illustrative class. In **default proxy mode**, only calls **entering the bean through the proxy** are intercepted. `this.saveInvoice()` is an internal call, so the annotation on `saveInvoice()` **does not create a transaction** at that point. If `runJob()` was already called inside a transaction created at another layer, JDBC may still participate in the existing transaction; the trap is that **the inner method's annotation is not additionally applied**.

Usually the clearest design is to move the transactional method into another `@Service` and call it via Spring injection; or place `@Transactional` directly on the appropriate entry point. For a block of logic needing an exact boundary inside a method, `TransactionTemplate` is also a good option. Avoid calling via `AopContext.currentProxy()` when the code can be structured more cleanly.

### 9.2. Methods Not Intercepted by the Proxy

- Objects created with `new` instead of being Spring beans: annotations may not be processed.
- `private` methods do not become transactional entry points in proxy mode; visibility constraints and proxy styles must be checked.
- `final` methods or `final` classes can prevent class-based proxies from overriding/intercepting; interface-based proxies have their own constraints.
- Calling an annotated method during initialization, such as `@PostConstruct`, is not a reliable point to expect the transaction proxy to already be active.
- `@Transactional` on an `@Async` method or a new thread does not automatically propagate a thread-bound transaction from the caller to the executor.
- In environments with multiple transaction managers, select the right manager via qualifier/annotation and ensure repositories use the corresponding resource.

### 9.3. Why Doesn't `TransactionTemplate` Suffer from This Self-Invocation Trap?

Because opening the transaction is an explicit Java call:

~~~java
public void doWork() {
    template.executeWithoutResult(status -> updateRows());
}
~~~

Even if `doWork()` is called from the same object, `template.executeWithoutResult(...)` still runs. That **does not** mean it automatically fixes a misconfigured `DataSource` or creates an independent new transaction; propagation and the manager still decide that.

## 10. Transactions Only Cover Properly Managed Resources

A DB transaction does not automatically roll back:

- Emails already sent via SMTP, or HTTP requests already processed externally.
- Files already written/renamed on the filesystem.
- Messages already published to a messaging system that does not participate in the same transaction mechanism.
- Another database if there are only two independent `DataSourceTransactionManager` instances.
- Asynchronous work executing on another thread without its own proper transaction.

If you need to write to a database and reliably emit an event, you can use a **transactional outbox**: write business data and an outbox record in the same DB transaction, then have another component publish and retry with idempotency. For true distributed transactions, you must configure an appropriate coordination mechanism (such as JTA when infrastructure supports it); `@Transactional` on a service does not automatically turn multiple sources into one distributed transaction.

### Reactive Differs from Imperative

`@Transactional` can be used in reactive code **when using `ReactiveTransactionManager` and methods returning appropriate reactive types**. In that case, the transaction context is attached to the **Reactor context** rather than `PlatformTransactionManager`'s ThreadLocal. Spring recommends `TransactionalOperator` for programmatic reactive transactions.

With `JdbcTemplate`, blocking JDBC, and `PlatformTransactionManager`, `TransactionTemplate` is the appropriate programmatic tool. Do not mix arbitrary async `Mono/Flux` calls inside a JDBC callback and assume the transaction continues across different threads.

## 11. Which API Should You Choose?

Choose **`@Transactional`** when:

- The service method clearly represents a business operation that must commit/roll back together.
- Callers invoke the bean through Spring and rollback/propagation rules can be declared concisely via annotation.
- You want to keep business code minimally dependent on `TransactionStatus` and transaction infrastructure.

Choose **`TransactionTemplate`** when:

- You want the transaction to wrap only **a small section** amid other processing.
- You need `status.setRollbackOnly()` based on business decisions inside the callback.
- A single method needs multiple separate transactions or different settings where splitting beans/annotations would be less clear.
- You need boundary control directly in Java code without relying on a proxy at a self-invocation call site.

Whichever API you choose, the general design rule is **short transactions, clear boundaries, all critical SQL sharing the same resource/manager, explicit row-count and error checks, and integration tests proving real rollback**.

## 12. Testing Easy-to-Get-Wrong Scenarios

| Test Case | Expectation |
| --- | --- |
| Two SQL statements succeed inside `@Transactional` | Both are committed |
| Second SQL throws `RuntimeException` | First SQL rolls back, initial data unchanged |
| Method throws checked exception without `rollbackFor` | Verify default/actual configured policy; may still commit if transaction remains valid |
| Method has `rollbackFor` and exception escapes | Rolls back when matching the rule |
| Exception is caught and method returns normally | Check whether rollback-only was set; avoid assuming it always rolls back |
| `TransactionTemplate` callback throws unchecked exception | Rolls back and exception propagates to caller |
| Callback calls `setRollbackOnly()` and returns | Rolls back even without throwing an error |
| Inner `REQUIRED` marks rollback-only | Outer must not falsely report commit success; may receive `UnexpectedRollbackException` |
| Inner `REQUIRES_NEW` | Inner separates transaction; observe commit/rollback and connection pool impact |
| `this.methodAnnotated()` | Inner method annotation is not automatically intercepted by proxy |
| Two different `DataSource` beans | Verify which resource actually participates in the manager |
| Async/reactive threads | Test transaction propagation per the actual model, without expecting automatic ThreadLocal transfer |

For integration tests, **do not accidentally wrap the entire test in `@Transactional` and roll back at the end of the test** if the goal is to verify how the service commits/rolls back independently: the test's transaction can cause SQL statements to join a single test-managed transaction, masking the service's actual behavior. Choose an appropriate test setup or run calls outside a test transaction, then query the database state to verify.

In production, monitor active connection counts, pool wait times, transaction duration, deadlocks, lock timeouts, retry rates, and `UnexpectedRollbackException` errors. Avoid retrying an entire business operation after an error without proper idempotency.

## 13. Self-Check Questions

1. **A `@Transactional` method executes two SQL statements, and throws `IllegalStateException` after the first. What happens?** If called through the proxy, using the right transaction manager and default rollback rules, both changes in the transaction are rolled back; the first statement does not commit on its own.
2. **Does `@Transactional` on a `private` method called from a public method on the same bean create a transaction?** You cannot rely on that annotation in proxy mode. Place the boundary on the public entry point or structure a separate bean.
3. **`TransactionTemplate.executeWithoutResult` calls `status.setRollbackOnly()` without throwing an exception; the callback returns. Does it commit?** No, the transaction is marked rollback-only.
4. **Is an inner `@Transactional(REQUIRED)` a different physical transaction from an outer `REQUIRED`?** Usually no; both participate in the same physical transaction.
5. **Why can `REQUIRES_NEW` exhaust the connection pool?** The outer transaction holds its resource/connection while the inner one requires a new transaction/connection.
6. **A service sends an email and then rolls back the database. Is the email automatically retracted?** No; email is a side effect outside the database transaction.
7. **When do you choose `TransactionalOperator`?** When using reactive transactions, `ReactiveTransactionManager`, and reactive pipelines, rather than blocking JDBC callbacks.

## 14. Official Documentation

- Spring Framework, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework, *Programmatic Transaction Management* and `TransactionTemplate`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework, *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework, *Understanding the Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- JavaDoc, `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html