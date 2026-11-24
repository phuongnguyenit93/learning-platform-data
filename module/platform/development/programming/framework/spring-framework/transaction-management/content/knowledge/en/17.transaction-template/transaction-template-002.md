# Creating TransactionTemplate from PlatformTransactionManager in Spring Framework

> **Spring Framework — Transaction Management → TransactionTemplate.** This lesson presents the complete process of creating and configuring `org.springframework.transaction.support.TransactionTemplate` from an `org.springframework.transaction.PlatformTransactionManager`, running business blocks via callbacks, reading `TransactionStatus`, controlling commit/rollback, managing multiple configurations, and choosing the right transaction manager. The focus is on **actual lifecycle and wiring**: a template does not connect to a database by itself; it coordinates transactions through the manager we provide.

## 1. Learning Objectives

After studying this lesson, you can:

1. Clearly state the relationship among `DataSource`, `PlatformTransactionManager`, `TransactionTemplate`, `JdbcTemplate`, and `TransactionStatus`.
2. Create a `TransactionTemplate` using the constructor taking a `PlatformTransactionManager`; know two alternatives: the constructor also taking a `TransactionDefinition`, and the no-arg constructor plus `setTransactionManager(...)`.
3. Set the transaction definition including propagation, isolation, timeout, read-only, and transaction name, while understanding the limits when the scope joins an outer transaction.
4. Inject a template into a Spring bean via constructor injection or define the template as a reusable `@Bean`.
5. Use `execute(TransactionCallback<T>)` to return a value, `executeWithoutResult(Consumer<TransactionStatus>)` for non-returning operations, and `status.setRollbackOnly()` when business logic intentionally requests a rollback.
6. Understand exception handling: runtime exceptions/errors escaping the callback lead to rollback, while checked exceptions must be handled inside the callback according to Java type rules.
7. Distinguish using the template in imperative code from AOP proxy-based `@Transactional` and from `TransactionalOperator` for reactive flows.
8. Verify behavior through a runnable **Java 17+, Maven, Spring JDBC, and H2** example: commit, rollback by exception, rollback-only with normal return, and independent `REQUIRES_NEW` commit.

## 2. One Core Sentence to Remember

`TransactionTemplate` is **the coordinator of a transaction scope via a callback**, whereas `PlatformTransactionManager` is **the component that actually controls begin, commit, rollback, and resource binding**.

Model:

```text
               Application / Spring Bean
                        |
                        v
         TransactionTemplate.execute(callback)
                        |
                 configured with
                        |
                        v
             PlatformTransactionManager
               /       |          \
              /        |           \
   getTransaction   commit      rollback
              \        |           /
               \       |          /
                physical transaction
                        |
                JDBC Connection / JPA
                        |
                Spring-aware data access
                  e.g. JdbcTemplate
```

This statement:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
```

**Does not start a transaction yet**. It only creates a template object bound to the manager. A transaction is requested when calling:

```java
Integer result = template.execute(status -> {
    // Code that needs to run inside the transaction.
    return 42;
});
```

When the callback finishes or throws an exception, the template asks the manager to complete the transaction appropriately. With the default `REQUIRED` propagation, if an outer transaction exists, the callback **joins** that physical transaction rather than creating/committing an independent physical transaction of its own.

## 3. Classes and Roles

| Component | Primary role | What it does not do |
| --- | --- | --- |
| `PlatformTransactionManager` | Imperative API with `getTransaction(definition)`, `commit(status)`, `rollback(status)`; implementations execute on the corresponding resource | Does not automatically "guess" the datasource of every JDBC operation in the application |
| `JdbcTransactionManager` | A Spring JDBC implementation controlling transactions on a `DataSource`; commonly used for Spring JDBC | Does not turn multiple different datasources into a distributed atomic transaction |
| `JpaTransactionManager` | Coordinates transactions via JPA `EntityManagerFactory` and related resources | Does not independently control arbitrary databases outside the configured JPA resources |
| `TransactionTemplate` | Receives a manager, holds a transaction definition, creates a callback boundary, and handles lifecycle/exceptions | Does not replace the database manager and does not require an AOP proxy for `execute` itself to run |
| `TransactionDefinition` | Contract for propagation, isolation, timeout, read-only, and name | Does not hold transaction data or decide SQL results |
| `TransactionStatus` | State of the scope currently being processed; supports `setRollbackOnly()`, `isRollbackOnly()`, `isNewTransaction()` | Does not represent a single global transaction across all threads |
| `JdbcTemplate` | Executes SQL through Spring JDBC/resource synchronization | Does not automatically open/commit a single transaction for a whole group of SQL statements when a boundary is missing |
| `TransactionOperations` | Interface for `execute(...)`, `executeWithoutResult(...)`, useful as a contract/injection seam | Does not expose all configuration setters of `TransactionTemplate` |

**Important package names:**

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.DefaultTransactionDefinition;
```

The above is a group of imports, not a standalone program.

### 3.1. Why Is JdbcTemplate Alone Not Enough?

A standalone `JdbcTemplate` can run SQL with autocommit when there is no active transaction. If the business logic needs **two statements to succeed or fail together**, there must be a transaction boundary:

```java
return transactionTemplate.execute(status -> {
    jdbc.update("UPDATE ...");  // part 1
    jdbc.update("INSERT ...");  // part 2
    return "done";
});
```

This is a fragment; the SQL must be replaced with real tables. If the manager coordinates the exact `DataSource` used by `JdbcTemplate`, both calls participate in the Spring-bound transaction. If the manager and `JdbcTemplate` use **two unrelated datasources**, you must not assume the two SQL statements roll back together just because they sit inside the lambda.

## 4. Three Ways to Instantiate TransactionTemplate

### 4.1. Common Recommended Approach: Constructor Taking Manager

```java
PlatformTransactionManager manager = /* Spring-injected manager */;
TransactionTemplate template = new TransactionTemplate(manager);
```

These two lines are an illustrative fragment of dependency injection, not a verbatim compilable Java declaration due to the comment at the manager assignment. In an actual Spring bean:

```java
@Service
public class PaymentService {
    private final TransactionTemplate tx;

    public PaymentService(PlatformTransactionManager manager) {
        this.tx = new TransactionTemplate(manager);
    }

    public void markPaid() {
        tx.executeWithoutResult(status -> {
            // SQL / repository operations...
        });
    }
}
```

This is a class fragment: it needs imports, data access logic, and the corresponding manager bean. Constructor injection ensures the service receives the manager configured by the Spring container. `@Transactional` is not needed on `markPaid()` because the `tx.executeWithoutResult(...)` call itself opens a programmatic boundary.

### 4.2. Constructor Taking Manager and TransactionDefinition

When a specific configuration set needs to be reused:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
def.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15); // seconds
def.setName("independent-audit");

TransactionTemplate auditTx =
        new TransactionTemplate(manager, def);
```

This fragment assumes `manager` has already been provided. The constructor copies the initial settings from `TransactionDefinition`; the template can still be configured further before use.

**Do not confuse:** `REQUIRES_NEW` can **suspend** the outer transaction and create an independent physical transaction; it is not a "safer" option by default. If the audit must commit together with the order, `REQUIRED` is the appropriate semantics.

### 4.3. No-Argument Constructor + Setter

```java
TransactionTemplate tx = new TransactionTemplate();
tx.setTransactionManager(manager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
```

This approach is valid, especially when the container configures properties after constructing the bean. However, a template without a manager is **not ready** to run `execute`. When managed by Spring as a bean, `afterPropertiesSet()` validates that the manager is present.

For directly written Java code, using the constructor taking a manager is usually more readable and reduces the risk of forgetting the setter. **Do not choose the no-arg constructor just to avoid dependency injection.**

### 4.4. One Semantics, Multiple Ways of Wiring

All three approaches create an **imperative TransactionTemplate**. They do not decide where the SQL/transaction resource lives; that depends on the manager. A template can be a private field of a service or a bean shared across multiple services. When there are multiple transaction definitions, bean names should be clear to avoid picking the wrong one.

## 5. Using a Spring Bean to Share TransactionTemplate

Instead of having each service create its own template, you can define a bean:

```java
@Configuration(proxyBeanMethods = false)
public class TransactionConfig {

    @Bean
    public TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {

        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);

        return template;
    }
}
```

This is a Spring configuration fragment: it needs imports and an existing `PlatformTransactionManager` bean for the right resource. Spring automatically passes the manager into the factory method. Then the service:

```java
@Service
public class OrderService {
    private final TransactionTemplate tx;

    public OrderService(TransactionTemplate tx) {
        this.tx = tx;
    }

    public void submit() {
        tx.executeWithoutResult(status -> {
            // Write order and stock in the same transaction.
        });
    }
}
```

Fragment. **You do not need to create a new `PlatformTransactionManager` for every service**. The manager is typically a singleton bean configured alongside the datasource/entity manager factory. The template can also be reused.

### 5.1. Multiple TransactionTemplate Beans

When a service needs two semantics:

```java
@Bean("orderTx")
TransactionTemplate orderTx(PlatformTransactionManager manager) {
    TransactionTemplate t = new TransactionTemplate(manager);
    t.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
    return t;
}

@Bean("auditTx")
TransactionTemplate auditTx(PlatformTransactionManager manager) {
    TransactionTemplate t = new TransactionTemplate(manager);
    t.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    return t;
}
```

Fragments need to be placed in `@Configuration`. When injecting:

```java
public OrderService(
        @Qualifier("orderTx") TransactionTemplate orderTx,
        @Qualifier("auditTx") TransactionTemplate auditTx) {
    this.orderTx = orderTx;
    this.auditTx = auditTx;
}
```

If there are multiple beans of type `TransactionTemplate` without `@Qualifier`, `@Primary`, or suitable resolution rules, the container may report ambiguity. Do not randomly pick whichever template happens to inject; **different propagation leads to different data outcomes**.

### 5.2. Is a Shared Template Safe When Multiple Threads Call execute?

According to Spring documentation, `TransactionTemplate` instances are **thread-safe for sharing** because they do not hold per-call conversational transaction state. Actual transaction state is managed by the manager and resource synchronization per execution context.

However, the template **has mutable configuration state** via setters. Therefore:

- Configure the fields once during bean initialization.
- Do not call `template.setPropagationBehavior(...)` or `template.setIsolationLevel(...)` per HTTP request on a shared singleton template.
- If you have two transaction settings, create **two differently configured template objects**; give the beans understandable names.
- Do not store `TransactionStatus` from a callback for use on another thread or after the callback finishes.

Example **to avoid**:

```java
public void run(boolean independent) {
    // Dangerous if tx is a singleton used by multiple requests:
    tx.setPropagationBehavior(
            independent
                ? TransactionDefinition.PROPAGATION_REQUIRES_NEW
                : TransactionDefinition.PROPAGATION_REQUIRED);

    tx.executeWithoutResult(status -> {
        // Another request can modify tx's config concurrently.
    });
}
```

This is an anti-pattern fragment. Using two immutable-after-setup template references `requiredTx` and `independentTx` is clearer and easier to test.

## 6. Defaults Inherited by the Single-Parameter Constructor

`TransactionTemplate` extends `DefaultTransactionDefinition`. Common defaults when no further configuration is added:

| Setting | Default | Meaning |
| --- | --- | --- |
| `propagationBehavior` | `PROPAGATION_REQUIRED` | If a transaction already exists, join it; otherwise create a new transaction |
| `isolationLevel` | `ISOLATION_DEFAULT` | Use the default isolation of the DB/resource |
| `timeout` | `TIMEOUT_DEFAULT` | Use the default timeout of the transaction manager/resource |
| `readOnly` | `false` | Do not declare read-only on the transaction definition |
| `name` | `null` | No dedicated name set for the transaction definition |

How to print and inspect programmatically:

```java
System.out.println(
        template.getPropagationBehavior()
                == TransactionDefinition.PROPAGATION_REQUIRED);
System.out.println(
        template.getIsolationLevel()
                == TransactionDefinition.ISOLATION_DEFAULT);
System.out.println(
        template.getTimeout()
                == TransactionDefinition.TIMEOUT_DEFAULT);
System.out.println(!template.isReadOnly());
```

If a template is newly created from the single-parameter constructor and unconfigured, these lines are typically all `true`. This is a fragment requiring a valid `template` variable and imports.

**Isolation.DEFAULT does not mean READ_COMMITTED on every database.** `TIMEOUT_DEFAULT` does not mean the transaction lives forever and does not automatically replace database/HTTP/query timeouts. `readOnly=true` is normally a hint/optimization, not an absolute write barrier across all managers.

## 7. Customizing Propagation, Isolation, Timeout, Read-Only, and Name

The setters on the template are the `DefaultTransactionDefinition` API:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(20);      // 20 seconds, depending on manager/resource
tx.setReadOnly(false);
tx.setName("orders.create");
```

This is a fragment assuming `manager` exists. Some configurations have setter variants by name:

```java
tx.setPropagationBehaviorName("PROPAGATION_REQUIRES_NEW");
tx.setIsolationLevelName("ISOLATION_SERIALIZABLE");
```

The string constants must match the exact names accepted by `DefaultTransactionDefinition`; do not arbitrarily pass enum names like `"REQUIRES_NEW"` when the method expects constant names.

### 7.1. When Joining an Existing Transaction, Inner Config Does Not Automatically Upgrade Isolation

Suppose an outer `@Transactional(isolation=READ_COMMITTED)` has opened physical T1. Inside, `TransactionTemplate` is called with `PROPAGATION_REQUIRED` and `ISOLATION_SERIALIZABLE`.

The template still asks the manager to join T1; the manager normally does not create a second physical isolation level within the same T1. With managers using default lenient handling, the inner isolation **does not automatically upgrade T1**. If `validateExistingTransaction=true` is enabled and the configuration is incompatible, the manager can throw `IllegalTransactionStateException`.

If a separate transaction with its own isolation is truly needed, `REQUIRES_NEW` can open T2, but that changes atomicity/visibility and adds connections/locks. **Do not change propagation just to avoid an isolation mismatch** if business data must commit/rollback together.

### 7.2. Read-Only and Rollback Rules

`tx.setReadOnly(true)` is a transaction-definition hint. Depending on the manager/DB, it may adjust connection mode or provider optimizations. Do not rely on it in place of database permissions to forbid updates.

`TransactionTemplate` **does not have attributes** `rollbackFor` / `noRollbackFor` like `@Transactional`. Under the imperative callback interface, a `RuntimeException` or `Error` escaping the callback is handled by the template with a rollback. For checked exceptions, the callback method does not declare `throws Exception`, so you must catch/wrap/mark rollback and decide how to propagate errors intentionally. See section 9.

### 7.3. Transaction Name for Observing Logs

`tx.setName("orders.create")` attaches a name to the transaction definition. It is useful in diagnostics/tracing, especially when a method uses programmatic boundaries. The name is descriptive only and does not alter durability/isolation.

## 8. Using execute(TransactionCallback<T>)

`execute` is the core method of `TransactionTemplate`:

```java
String receipt = tx.execute(status -> {
    jdbc.update(
            "INSERT INTO receipts(id, label) VALUES (?, ?)",
            7, "paid");

    return "receipt-7";
});
```

This is a fragment requiring `tx` and `jdbc` variables and the `receipts` table. The callback runs inside a transaction according to the configured definition.

- The callback receives `TransactionStatus`; it can check `isRollbackOnly()`, `isNewTransaction()`, or call `setRollbackOnly()`.
- The callback's `return` value is returned to the caller from `execute` if the transaction completes appropriately.
- Having no `return` means a void callback must be used or `null` returned.
- If the callback throws an unchecked exception, the template asks for rollback of the appropriate transaction scope and propagates the exception to the caller.
- If the database commit fails after the callback, the caller can still receive a transaction exception instead of a normal value. Do not log "committed" **before `execute` returns successfully**.

### 8.1. Callback Can Return a Number, DTO, or Query Result

```java
int insertedId = tx.execute(status -> {
    jdbc.update("INSERT INTO items(id, label) VALUES(10, 'new')");
    return 10;
});
```

Fragment. Note that `execute` returns generic `T`, which is nullable per its contract; if the callback returns `null`, unboxing to `int` will fail. In real code, choose a non-null value or check explicitly.

### 8.2. Callback Runs at the Exact Boundary, Independent of Self-Invocation

Because `tx.execute(...)` is called directly, this approach **does not need a Spring AOP proxy** for the callback block itself. One method in the same class calling another method of its own can still use the template in its body. Unlike:

```java
this.otherMethodAnnotatedTransactional(); // Can bypass AOP advice.
```

However, the transaction manager and datasource still need to be configured properly; not depending on AOP does not mean the template can create a transaction from any unrelated `DataSource`.

## 9. executeWithoutResult and Proactive Rollback-Only

### 9.1. No Return Needed: executeWithoutResult

`TransactionOperations` has the convenience method `executeWithoutResult(Consumer<TransactionStatus>)`:

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE orders SET status = 'PAID' WHERE id = ?", 17);
    jdbc.update("INSERT INTO outbox(event_id) VALUES(?)", 1001);
});
```

Fragment requiring real schema. When the callback returns normally and no rollback is requested, the manager takes the commit path (if the scope is the owner); if a `RuntimeException`/`Error` occurs, the transaction scope is rolled back according to manager semantics.

If participating in a physical transaction opened by an outer scope, the callback **does not commit** the physical transaction immediately upon exit; commit completion is decided by the owner of the physical transaction.

### 9.2. setRollbackOnly() — Allowed to Return Normally While Data Rolls Back

```java
String outcome = tx.execute(status -> {
    jdbc.update("INSERT INTO reservations(id) VALUES(99)");

    if (businessRuleRejected()) {
        status.setRollbackOnly();
        return "rejected";
    }

    return "accepted";
});
```

Fragment, requiring `businessRuleRejected()` and the `reservations` table. When the callback sets local rollback-only on the root transaction status, the manager can roll back and `execute` **still returns** the string `"rejected"`. That is not proof that the data committed. Business results must be distinguished from data state.

**Important point:** `status.setRollbackOnly()` only marks the transaction status of the current scope. It does not trigger an immediate physical rollback on the exact line it is called. The manager processes that flag when the scope completes.

### 9.3. Catching Exceptions Inside the Callback: Do Not Swallow Errors and Accidentally Commit

Wrong example:

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE accounts SET balance = balance - 100 WHERE id=1");
    try {
        chargeExternalGateway();
    } catch (RuntimeException ignored) {
        // Without marking rollback-only, the callback returns normally.
    }
});
```

This is an anti-pattern fragment. If the exception is caught **inside** the callback without calling `status.setRollbackOnly()`, the template no longer sees that exception escape. If the database has not already marked itself rollback-only, the transaction may commit the debit even though the gateway failed.

Intentional handling:

```java
tx.executeWithoutResult(status -> {
    try {
        performAllRequiredOperations();
    } catch (RecoverableBusinessException ex) {
        status.setRollbackOnly();
        // Business response is handled by the caller, without pretending commit.
    }
});
```

This is a fragment requiring corresponding exception and operation definitions. If you want the caller to know about the error, consider rethrowing an unchecked domain exception rather than swallowing it. When the operation has already produced external side effects, DB rollback does not automatically undo external actions either; idempotency/outbox/saga are needed as appropriate.

### 9.4. RuntimeException, Error, and Checked Exception

`TransactionTemplate.execute(...)` handles `RuntimeException` and `Error` escaping the callback by rolling back, then rethrows the error; if the manager fails while processing rollback, a transaction exception may replace or supplement the original information.

The callback API does not declare checked exceptions, so the following code **does not compile** when `readFile()` declares `throws IOException` without a catch:

```java
tx.execute(status -> {
    readFile();   // Suppose it throws IOException: must be handled here.
    return null;
});
```

This is a **fragment intentionally illustrating a compile error**, not a runnable program snippet. Valid approach:

```java
tx.executeWithoutResult(status -> {
    try {
        readFile();
        jdbc.update("INSERT INTO imports(id) VALUES(1)");
    } catch (IOException ex) {
        throw new UncheckedIOException("File import failed", ex);
    }
});
```

This is a fragment requiring imports `java.io.IOException`, `java.io.UncheckedIOException`, and real variables/methods. `UncheckedIOException` extends `RuntimeException`; the template will catch the exception escaping the callback and roll back. When a checked exception represents a normal business condition, you can call `status.setRollbackOnly()` and return an explicit result instead of always wrapping.

**Do not mechanically apply** `@Transactional(rollbackFor = Exception.class)` thinking to templates; that annotation attribute is a different declarative mechanism. With programmatic callbacks, exception/rollback handling is written in code.

## 10. When an Outer @Transactional Exists

Example where outer already has `@Transactional(REQUIRED)` and inner uses default template `REQUIRED`:

```java
@Service
public class OuterService {
    private final TransactionTemplate tx;

    public OuterService(PlatformTransactionManager manager) {
        this.tx = new TransactionTemplate(manager); // REQUIRED default
    }

    @Transactional
    public void placeOrder() {
        tx.executeWithoutResult(status -> {
            // Runs inside the outer's physical transaction
            // if using the right manager/resource.
        });
    }
}
```

Class fragment requiring imports and business code. In the typical scenario:

1. Outer's `@Transactional` advice opens physical transaction T1.
2. `tx.executeWithoutResult` requests a `REQUIRED` transaction via the same manager.
3. The template creates a logical scope joining T1, without opening physical T2.
4. Normal callback completion does not mean T1 commits immediately.
5. When the outer method returns, the outer interceptor decides whether to commit/rollback T1.

If the callback marks rollback-only or throws an unchecked exception leading to a participating rollback, **physical T1 can be marked global rollback-only**. Outer can receive `UnexpectedRollbackException` when trying to commit even if it caught the inner exception. Do not fix this with `REQUIRES_NEW` unless the business accepts an independent commit.

### 10.1. When an Independent Commit Is Intentionally Needed

```java
TransactionTemplate auditTx = new TransactionTemplate(manager);
auditTx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
```

When running `auditTx.execute(...)` inside an outer transaction, Spring suspends context T1 and starts physical T2 (when supported by the manager). Inner T2 can commit right away; T1 remains open and may roll back later. This is appropriate semantics for an **attempt audit** that must be saved even if outer fails, not for an audit claiming the order committed before the order actually commits.

**Resource risk:** outer may still hold a JDBC connection and row locks while inner requests a new connection. Pool exhaustion or lock waits can occur. T2 also cannot automatically see uncommitted inserts from T1; avoid foreign keys or predicates depending on that data.

## 11. One Manager Bean, Multiple Templates: Clear Naming Conventions

An application can configure:

```text
ordersDataSource
     |
     v
ordersTransactionManager  (JdbcTransactionManager)
     |
     +-- requiredOrderTx       (PROPAGATION_REQUIRED)
     |
     +-- independentAuditTx    (PROPAGATION_REQUIRES_NEW)

auditDataSource
     |
     v
auditTransactionManager   (JdbcTransactionManager)
     |
     +-- externalAuditTx      (another manager/DB)
```

There are two **independent** axes:

- **Manager** selects which resource/transaction system is coordinated.
- **Template definition** selects propagation/isolation/timeout/read-only for that manager's transactions.

If two templates share the same manager with `REQUIRED` and `REQUIRES_NEW`, they still share the **same datasource**, while creating different scopes. If two managers coordinate two datasources, changing propagation on one manager does not make the two databases synchronize commits automatically.

### 11.1. @Qualifier When There Are Multiple Managers

```java
@Bean("ordersTxTemplate")
TransactionTemplate ordersTxTemplate(
        @Qualifier("ordersTransactionManager")
        PlatformTransactionManager ordersManager) {
    return new TransactionTemplate(ordersManager);
}

@Bean("auditTxTemplate")
TransactionTemplate auditTxTemplate(
        @Qualifier("auditTransactionManager")
        PlatformTransactionManager auditManager) {
    return new TransactionTemplate(auditManager);
}
```

Fragments require Spring `@Configuration`, imports, and corresponding manager beans. Use `@Qualifier` on both **manager** and template injection when needed. Do not rely on Java variable names to assume the right manager is selected at runtime.

If two resources must commit atomically, an appropriate distributed transaction design or saga/outbox/idempotency is needed. A `TransactionTemplate` cannot turn two independent local transaction managers into a global atomic transaction.

### 11.2. Do Not Create a New Manager from an Arbitrary Datasource on Every Call

```java
// Per-request configuration anti-pattern:
PlatformTransactionManager m =
        new JdbcTransactionManager(new SomeDataSource());
TransactionTemplate tx = new TransactionTemplate(m);
```

This is a fragment illustrating **a design to avoid** (`SomeDataSource` is not a real type). It easily bypasses the application's existing resources/configuration and creates the wrong manager/pool.

Normally, declare one official transaction manager bean and inject it; if you need different `TransactionTemplate` settings, create separate template beans.

## 12. Runnable Exercise: Spring 6.2.8 + JDBC + H2 + Maven + Java 17

We will build a small console application **without depending on Spring Boot**, using programmatic transaction boundaries. `@EnableTransactionManagement` is not needed because `@Transactional` is not used to demarcate transactions in the demo.

**Scenarios:**

1. `TransactionTemplate` bean `requiredTemplate` with default `REQUIRED` commits an insert and returns a result.
2. Callback throws `IllegalStateException`; template rolls back and propagates the exception to the caller.
3. Callback calls `status.setRollbackOnly()` while returning a normal string; SQL changes still roll back.
4. Outer `REQUIRED` writes an order and calls a `REQUIRES_NEW` template to write an audit into a **different** table, then outer rolls back itself; the inner's committed audit still persists.
5. After each scenario, use `JdbcTemplate` outside the transaction to query row counts, verifying the transaction actually committed/rolled back.

### 12.1. Directory Structure

```text
transaction-template-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionTemplateDemo.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-template-demo</artifactId>
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
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TransactionTemplateDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. src/main/java/dev/learning/TransactionTemplateDemo.java

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionTemplateDemo {

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:transaction_template;DB_CLOSE_DELAY=-1");
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

        // Approach 1: create TransactionTemplate directly from manager in @Bean.
        @Bean("requiredTemplate")
        TransactionTemplate requiredTemplate(
                PlatformTransactionManager manager) {
            TransactionTemplate template =
                    new TransactionTemplate(manager);

            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);
            template.setIsolationLevel(
                    TransactionDefinition.ISOLATION_READ_COMMITTED);
            template.setName("demo.required");
            return template;
        }

        // Approach 2: constructor with manager + TransactionDefinition.
        @Bean("auditTemplate")
        TransactionTemplate auditTemplate(
                PlatformTransactionManager manager) {
            DefaultTransactionDefinition definition =
                    new DefaultTransactionDefinition();

            definition.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            definition.setName("demo.independent-audit");

            return new TransactionTemplate(manager, definition);
        }

        @Bean
        OrderOperations orderOperations(
                JdbcTemplate jdbc,
                @Qualifier("requiredTemplate")
                TransactionTemplate required,
                @Qualifier("auditTemplate")
                TransactionTemplate audit) {
            return new OrderOperations(jdbc, required, audit);
        }
    }

    public static class OrderOperations {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate required;
        private final TransactionTemplate audit;

        public OrderOperations(
                JdbcTemplate jdbc,
                TransactionTemplate required,
                TransactionTemplate audit) {
            this.jdbc = jdbc;
            this.required = required;
            this.audit = audit;
        }

        // execute returns a value produced by the callback.
        public int commitAndCount() {
            Integer count = required.execute(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    1, "committed");

                return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders",
                    Integer.class);
            });
            return count;
        }

        // RuntimeException escapes callback => template rolls back.
        public void failAndRollback() {
            required.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    2, "should rollback");

                throw new IllegalStateException("simulated failure");
            });
        }

        // Can return a normal result even when requesting rollback.
        public String markRollbackAndReturn() {
            return required.execute(status -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    3, "rolled back by status");

                status.setRollbackOnly();
                return "business rejected";
            });
        }

        // T2 commits audit independently; T1 is rolled back by outer's decision.
        public void auditPersistsAfterOuterRollback() {
            required.executeWithoutResult(outer -> {
                jdbc.update(
                    "INSERT INTO orders(id, label) VALUES(?, ?)",
                    4, "outer should rollback");

                audit.executeWithoutResult(inner -> {
                    jdbc.update(
                        "INSERT INTO audits(id, label) VALUES(?, ?)",
                        40, "attempt recorded");
                });

                outer.setRollbackOnly();
            });
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    private static void showCounts(
            JdbcTemplate jdbc, String phase) {
        System.out.println(
                phase
                + " orders=" + count(jdbc, "orders")
                + " audits=" + count(jdbc, "audits"));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        label VARCHAR(100) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audits (
                        id INT PRIMARY KEY,
                        label VARCHAR(100) NOT NULL
                    )
                    """);

            OrderOperations operations =
                    context.getBean(OrderOperations.class);

            System.out.println(
                    "commit.insideCount="
                    + operations.commitAndCount());
            showCounts(jdbc, "afterCommit");

            try {
                operations.failAndRollback();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "failure.message=" + ex.getMessage());
            }
            showCounts(jdbc, "afterFailure");

            System.out.println(
                    "explicit.result="
                    + operations.markRollbackAndReturn());
            showCounts(jdbc, "afterExplicit");

            operations.auditPersistsAfterOuterRollback();
            showCounts(jdbc, "afterIndependent");
        }
    }
}
```

### 12.4. Compiling and Running

Requires JDK 17+ and Maven 3.x. In the `transaction-template-demo` directory, the first Maven run needs access to the dependency repository:

```bash
mvn -q clean compile exec:java
```

Lines printed by **the program itself** in the expected order, excluding Maven/Spring logs:

```text
commit.insideCount=1
afterCommit orders=1 audits=0
failure.message=simulated failure
afterFailure orders=1 audits=0
explicit.result=business rejected
afterExplicit orders=1 audits=0
afterIndependent orders=1 audits=1
```

### 12.5. Interpreting Each Scenario

**Scenario 1 — commit with return value.** `commitAndCount()` calls `required.execute`. The callback inserts order ID=1 and then queries the count in the same transaction, returning `1`. The template asks the manager to commit T1 when the callback returns normally. After the method finishes, an external query shows there is one order and no audits yet.

**Scenario 2 — rollback due to unchecked exception.** The callback inserts ID=2 and throws `IllegalStateException`. The template catches it to request rollback of T2 and rethrows the error. The caller receives `simulated failure`; a subsequent query shows only order ID=1 remains.

**Scenario 3 — rollback-only with normal return.** The callback inserts ID=3, calls `status.setRollbackOnly()`, and returns `"business rejected"`. The template sees rollback-only and the manager completes the scope with a rollback. The caller still gets the result string, but the order count does not increase. This proves **a result is not synonymous with committed**.

**Scenario 4 — two templates with two semantics.** Outer uses `requiredTemplate` to open T4 and insert order ID=4, then `auditTemplate` uses `REQUIRES_NEW` to open T5 on another connection, writes to the `audits` table, and commits. Outer marks rollback-only and ultimately rolls back order ID=4. Audit ID=40 remains. The two tables **have no foreign key** between them to avoid the inner transaction depending on an uncommitted row from outer.

**JDBC mechanism:** Spring's `JdbcTransactionManager` and `JdbcTemplate` are configured with the same `DataSource` bean, so `JdbcTemplate` accesses the connection bound to the transaction context properly. The demo uses H2's simple `JdbcDataSource` to supply multiple physical connections; that is not a production connection pool. In production, proper pool sizing is needed, especially with nested `REQUIRES_NEW`.

**Verification scope:** Output is derived from the stated Spring/H2 semantics, not from running Maven in the lesson environment. To confirm directly, run the project in JDK/Maven and compare stdout and queries.

### 12.6. Modifying the Example Yourself to See the Manager-Template Relationship

**Try A — change `auditTemplate` propagation to `REQUIRED`.** When audit runs under outer T4, it joins the same physical transaction. When outer rolls back, audit ID=40 also rolls back. The final output will be `afterIndependent orders=1 audits=0`. This shows **the template definition**, not the method name `audit`, decides independent commits.

**Try B — remove `status.setRollbackOnly()` in `markRollbackAndReturn`.** Order ID=3 will be committed. The caller still receives the same string `"business rejected"`, so this is a business mismatch if users expect data not to be written when rejected.

**Try C — use `new TransactionTemplate()` and forget `setTransactionManager(...)`.** When the template is managed as a bean, initialization validation can fail; when used directly without setting a manager, it cannot execute `execute`. This is why using the constructor taking a manager is recommended.

**Try D — change the manager bean to one using a different datasource.** `JdbcTemplate` does not automatically participate in a transaction on a different datasource. Querying after commit/rollback can reveal statements executing outside the intended scope. In practice, you must ensure the manager, datasource, and data access layer are aligned.

**Try E — give `auditTemplate` its own isolation.** Because audit uses `REQUIRES_NEW`, T5 can receive the new isolation per manager/DB support. If changed to `REQUIRED` joining T4, the inner isolation declaration does not automatically upgrade T4's isolation.

## 13. Example of Per-Service Configuration Without a Shared Template Bean

When only one service needs a template with dedicated settings, creating it directly in the constructor remains a valid approach:

```java
@Service
public final class InvoiceService {
    private final TransactionTemplate invoiceTx;
    private final JdbcTemplate jdbc;

    public InvoiceService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.jdbc = jdbc;

        TransactionTemplate template =
                new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setTimeout(10);
        template.setName("invoice.close");

        this.invoiceTx = template;
    }

    public int closeInvoice(long id) {
        return invoiceTx.execute(status -> jdbc.update(
                "UPDATE invoices SET closed = TRUE WHERE id = ? "
                + "AND closed = FALSE",
                id));
    }
}
```

This is a **Spring service fragment**, requiring imports, schema, and a manager bean. `jdbc.update(...)` returns the affected row count; if the result is 0, the invoice does not exist or is already closed. In real business logic, you must clearly decide whether 0 rows is idempotent success or failure. Even if `execute` returns 0, the transaction can still commit normally; **a successful commit does not mean the business update succeeded**.

**Do not create a new template after every request if the settings do not change**; initializing once in the constructor or as a Spring `@Bean` is simple and sufficiently safe.

## 14. Creating a Template from a Shared TransactionDefinition

You can separate transaction settings from instantiation code:

```java
DefaultTransactionDefinition settings =
        new DefaultTransactionDefinition();
settings.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
settings.setReadOnly(true);
settings.setTimeout(5);
settings.setName("report.read");

TransactionTemplate reportTx =
        new TransactionTemplate(manager, settings);
```

Fragment. This approach fits when multiple templates need mostly identical settings but different managers/resources. However, do not reuse **the same mutable definition object** expecting all templates to pick up later changes automatically: the constructor is documented as taking/copying initial defaults; treat settings and templates as initialization-time configuration.

If you only want a variable for `execute` operations without exposing setters to the consuming service, you can expose the `TransactionOperations` interface:

```java
@Bean("reportTransactions")
TransactionOperations reportTransactions(
        PlatformTransactionManager manager) {
    TransactionTemplate template = new TransactionTemplate(manager);
    template.setReadOnly(true);
    return template;
}
```

Fragment requires importing `org.springframework.transaction.support.TransactionOperations`. Clients inject `@Qualifier("reportTransactions") TransactionOperations tx`. This narrows the client API and is useful for testing, but **do not mistake the interface for a new manager**; it is still the same implementation/template.

## 15. TransactionTemplate vs. @Transactional: Choosing at the Right Time

| Question | `TransactionTemplate` | `@Transactional` |
| --- | --- | --- |
| How the boundary is placed | Code directly calls `execute(callback)` | AOP advice when the method is called through a proxy/aspect |
| Needs a Spring proxy for the boundary itself? | No; explicit method call | Usually yes in proxy mode |
| Operating on part of a method | Easy to wrap a specific block of code | Normally applies around the intercepted method |
| Configuring propagation/isolation | Template setters or definition | Annotation attributes |
| Exception-based rollback | RuntimeException/Error escaping callback => rollback; use `setRollbackOnly` manually | Rollback rules configurable via `rollbackFor`/`noRollbackFor` |
| Code coupling | Depends on Spring transaction APIs | Annotation-based, less imperative boilerplate |
| Testability | Can inject `TransactionOperations`/mock or fake and verify DB | Tested through Spring context/proxy and transaction infrastructure |
| When an outer transaction exists | Depends on template propagation | Depends on annotation propagation |
| Reactive | Use `TransactionalOperator` instead of imperative template for Reactor flows | Reactive annotations have corresponding manager/context semantics |

You do not have to pick one for the entire application. You can use `@Transactional` in many use cases and use `TransactionTemplate` for special sections where you want an explicit boundary. However, avoid overlapping both mechanisms unintentionally because it becomes easy to misunderstand commit timing.

### 15.1. Isolating a Small Transaction Section Inside a Large Method

```java
public ProcessResult process(Request request) {
    NormalizedInput input = validateOutsideTransaction(request);

    return tx.execute(status -> {
        // Only the atomic DB portion has a transaction.
        return persistAtomically(input);
    });
}
```

Fragment. Performing validation/CPU-heavy work before the transaction can reduce connection/lock hold times. However, **do not** move checks with race-sensitive invariants outside without revalidating under a transaction/lock: "reading inventory then deciding" before the transaction can still go stale.

### 15.2. Do Not Use @Transactional on a Method Called via this Just to Compensate for Dropping Template

In default proxy mode:

```java
public void entry() {
    this.write(); // Does not go through transactional proxy.
}

@Transactional
public void write() {
    // ...
}
```

Anti-pattern fragment. If a direct boundary is needed, a `tx.execute(...)` call does not suffer from self-invocation bypass for the callback itself. Or move the boundary into another Spring bean and call it through an injected proxy.

### 15.3. Do Not Mix Imperative and Reactive APIs

`TransactionTemplate` works with `PlatformTransactionManager` and imperative/thread-bound transaction management. For non-blocking R2DBC/WebFlux, Spring recommends `TransactionalOperator` with `ReactiveTransactionManager`, which uses the Reactor context. Do not put `TransactionTemplate` inside a `Mono` and assume subsequent queries running on different threads remain in the original JDBC transaction context.

## 16. Common Configuration Mistakes

### 16.1. "No transaction manager configured"

Cause: using the no-arg constructor without setting a manager, or the Spring container has not injected the manager. Fix: inject `PlatformTransactionManager` and use `new TransactionTemplate(manager)`, or configure the bean property properly. A transaction cannot be created from just a class name.

### 16.2. Multiple PlatformTransactionManager Beans

If there are `ordersTransactionManager` and `billingTransactionManager`, injection by type can be ambiguous. Select the right manager using `@Qualifier`, give beans clear names, and test the resource managed by each manager. Do not just mark one manager `@Primary` and expect it to fit every datasource.

### 16.3. Transaction Manager Does Not Match JdbcTemplate Datasource

For example, `JdbcTransactionManager(dsA)` but `JdbcTemplate(dsB)`. Calling the template may open a transaction on A, while SQL executes on B outside that transaction. As a result, a template rollback does not undo data on B. You must configure the manager and datasource/data access layer as a matching pair.

### 16.4. Changing Propagation on a Singleton Template at Runtime

Configuration setters hold mutable state. If multiple concurrent HTTP requests share one instance and take turns calling `setPropagationBehavior` before `execute`, semantic races can happen: request A expects `REQUIRED` while request B changed it to `REQUIRES_NEW`. Use two statically configured templates.

### 16.5. Returning Success Despite setRollbackOnly

If a callback calls `status.setRollbackOnly()` and returns `"ok"`, the template can return `"ok"` after the intentional rollback. The caller must distinguish business results from transaction outcomes. Do not report "saved" simply because the method did not throw an exception.

### 16.6. Swallowing Exceptions Inside the Callback

If an exception is caught before escaping the callback without setting rollback-only, the manager may commit earlier writes. Exception translation/DB failures may still prevent the resource from committing; do not use catch-and-ignore as a transaction strategy.

### 16.7. Taking TransactionStatus Outside the Callback

`TransactionStatus` is bound to the active scope. Do not store it in a field or async task to call `setRollbackOnly()` after the callback has finished; the status may already be completed, and the transaction context does not automatically follow a new thread.

### 16.8. Trying to Fix a Rollback-Only Transaction Using REQUIRES_NEW

An inner `REQUIRED` can mark a shared physical transaction rollback-only; outer tries to commit and gets `UnexpectedRollbackException`. Switching inner to `REQUIRES_NEW` just to avoid the exception can cause inner to commit independently and break invariants. Identify which data must roll back together.

### 16.9. Forgetting Pool Sizing When Using REQUIRES_NEW

The outer transaction still holds a connection/locks while inner requests a new connection. If the pool is too small, multiple concurrent requests holding outer connections and waiting for inner can suffer connection timeouts. If inner touches a row locked by outer, lock waits still happen even when the pool is large enough.

### 16.10. Assuming readOnly=true Guarantees Consistent SELECTs

`readOnly` is a hint; isolation and query semantics determine snapshot/visibility. If a report needs consistency across multiple SELECTs, set the transaction boundary, isolation, and snapshot requirements according to your DBMS.

### 16.11. Assuming Template Timeout Limits HTTP Calls Inside the Callback

`TransactionTemplate.setTimeout(10)` is a transaction definition sent to the manager, not a timer that automatically aborts every HTTP/file/network operation. Dedicated timeouts are needed for clients/database statements and the application.

## 17. Testing Configuration Properties

### 17.1. Simple Configuration Unit Test

When you only need to verify the template is configured with the manager and defaults:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(true);

assert tx.getTransactionManager() == manager;
assert tx.getPropagationBehavior()
        == TransactionDefinition.PROPAGATION_REQUIRES_NEW;
assert tx.getIsolationLevel()
        == TransactionDefinition.ISOLATION_READ_COMMITTED;
assert tx.getTimeout() == 15;
assert tx.isReadOnly();
```

This is a **Java fragment** with an assumed `manager`, using the `assert` keyword (which only runs when assertions `-ea` are enabled). In real JUnit tests, use `Assertions.assertSame`/`assertEquals` and inject actual beans when testing configuration.

**Unit-testing setters does not prove an actual DB commit.** Integration tests are needed.

### 17.2. Integration-Testing Transaction Outcomes

Checklist:

| Scenario | Action | Post-boundary observation |
| --- | --- | --- |
| Normal return | Callback inserts + returns | Row exists |
| Runtime exception | Callback inserts + throws | Row does not exist, caller receives exception |
| Explicit rollback-only | Callback inserts + setRollbackOnly + returns | Row does not exist even though caller receives return value |
| Joined REQUIRED | Outer T1 active, inner template REQUIRED writes | Inner does not physically commit by itself; outer rollback pulls inner with it |
| REQUIRES_NEW | Outer T1 writes, inner template T2 writes independently, outer rolls back | Only T2 remains, if there is no FK/lock dependency |
| Wrong manager | Manager dsA, JdbcTemplate dsB | Test detects rollback does not protect B as expected |
| Two template configs | Clearly named Required and RequiresNew beans | No settings mutation happens between requests |
| Checked exception | Callback catches checked exception, wraps or marks | Rollback/response matches design |
| Isolation mismatch | Outer READ_COMMITTED, inner REQUIRED SERIALIZABLE | Do not expect automatic isolation upgrade; validate manager if needed |

With Spring TestContext, a test method annotated with `@Transactional` is usually rolled back at the end of the test and can **mask** the service's committed data. To test actual template commits, avoid accidentally wrapping the whole test in a test-managed transaction, or use `TestTransaction` intentionally.

### 17.3. Testing with Two Managers

If you want to ensure orders and audit connect to the right DBs:

- Create two datasources/test schemas or two differently named H2 databases.
- Create `ordersTransactionManager` and `auditTransactionManager`.
- Create templates injected via `@Qualifier`.
- Execute a transaction on each side.
- Query independently from each datasource after commit/rollback.
- Verify that a rollback on DB A **does not automatically** roll back DB B if these are two local managers with no shared coordination.

If business rules require atomic synchronization across two DBs, this test will expose that two templates alone are insufficient. In that case, a solution such as distributed transactions or saga/outbox is needed, not arbitrarily changing propagation.

## 18. A Standard Design Flow for a Spring Project

### Step 1 — Configure DataSource and Manager

```text
DataSource for the right database
       |
       v
PlatformTransactionManager bean
       |
       v
TransactionTemplate bean(s)
       |
       v
Service constructor injection
       |
       v
transactionTemplate.execute(callback)
```

When using Spring Boot, Boot can auto-configure `DataSource` and the transaction manager according to the appropriate starters/configuration. Before creating new ones manually, identify the beans Boot already provides. Avoid accidentally having two managers causing ambiguous injection.

### Step 2 — Express Business Semantics Clearly in Template Names

Names such as `orderRequiredTx`, `auditIndependentTx`, and `reportReadOnlyTx` are better than generic names `tx1`/`tx2`. In code reviews, seeing which template is used matters because two templates can determine whether data survives an outer rollback.

### Step 3 — Keep Callbacks Short, Focused on the DB Atomic Unit

Do not hold a transaction across HTTP calls, queue waits, or long CPU processing unless necessary. Prolonged transactions hold connections/locks longer and increase contention.

### Step 4 — Handle Rollbacks According to Business Results

If a business rejection can be treated as a normal outcome, `status.setRollbackOnly()` and returning a clear domain result is valid; if a serious error occurs, rethrow an unchecked exception so the caller knows. Do not swallow errors and report success.

### Step 5 — Protect Concurrent Invariants

The template **does not automatically replace** optimistic versioning, atomic update predicates, database constraints, or pessimistic locks. If two transactions compete for inventory, a well-bounded `execute` can still contain a flawed read-modify-write. Combine proper isolation/locking/constraints and retry in a new transaction when needed.

### Step 6 — Observe Results After the Boundary

Logs/counters/metrics before the callback ends do not prove a database commit. When integrating external effects, ensure events are sent under post-commit/outbox policies, avoiding sending early before an outer rollback.

## 19. Q&A Knowledge Check

**Question 1.** Does `new TransactionTemplate(manager)` open a JDBC transaction immediately?

No. The constructor only creates/configures the template. A transaction is requested when `execute(...)` or `executeWithoutResult(...)` is called.

**Question 2.** Can you use the template without `@EnableTransactionManagement`?

Yes, for programmatic `TransactionTemplate`. `@EnableTransactionManagement` primarily enables annotation-driven transaction advice. The template calls the manager directly and does not need an AOP proxy for the callback itself.

**Question 3.** Does `TransactionTemplate` automatically know which database to commit?

No. It receives a `PlatformTransactionManager`; the manager is configured for the actual resource. If the manager uses dsA while SQL uses dsB, the desired semantics are not guaranteed.

**Question 4.** When a callback returns a normal value but calls `status.setRollbackOnly()`, what is the result?

For a root transaction scope, the manager normally rolls back, while `execute` can still return a normal value. A return value does not prove a commit.

**Question 5.** Can a single singleton `TransactionTemplate` be shared across multiple threads?

Yes according to Spring documentation, when **the configuration is fixed**. Do not mutate propagation/isolation/timeout settings while requests are calling execute.

**Question 6.** Why should you use two templates when there are two propagation modes?

Because the template holds mutable configuration, and the semantics differ. Two preconfigured `REQUIRED`/`REQUIRES_NEW` instances avoid races and help code reviews spot independent commits.

**Question 7.** How do `execute(...)` and `executeWithoutResult(...)` differ?

`execute` takes a `TransactionCallback<T>` that can return a value of type `T`. `executeWithoutResult` is convenient for void callbacks; both use the template's transaction boundary.

**Question 8.** Does a checked `IOException` pass straight out of the callback and trigger `rollbackFor`?

Not under the annotation `rollbackFor` model, because `TransactionTemplate` does not have that attribute. The Java callback does not declare checked exceptions, so you must catch and wrap unchecked or call `setRollbackOnly()`, then handle business logic intentionally.

**Question 9.** If outer `@Transactional` and inner template are both `REQUIRED`, does inner commit on its own when the callback returns?

No if inner is joining outer's physical transaction T1. The manager only completes the logical scope; physical commit belongs to the outer owner.

**Question 10.** If inner `REQUIRES_NEW` commits and then outer rolls back, does inner remain?

It can remain, because T2 is independent. That should only be used when business semantics accept the inner data existing independently.

**Question 11.** When there are two `PlatformTransactionManager` beans, how do you fix injection?

Use `@Qualifier` or clear resolution configuration to select the right manager for the corresponding datasource/provider; name the template beans and test effects on a real DB.

**Question 12.** Should you create a new transaction template inside every lambda?

Not needed when settings do not change. Using a preconfigured shared field/bean is simpler, easier to test, and avoids creating mutable settings per call.

**Question 13.** Does `readOnly=true` on a template guarantee writes are impossible in every database?

No. This is usually a hint/setting interpreted by the manager/resource as supported. To strictly forbid writes, appropriate database permissions/constraints are needed.

**Question 14.** When do you use `TransactionalOperator` instead of the template?

When the flow is truly reactive (Reactor/R2DBC) with `ReactiveTransactionManager`. `TransactionTemplate` is for imperative `PlatformTransactionManager`.

**Question 15.** If a callback fails after sending an email, does a DB rollback recall the email?

No. The transaction manager only coordinates the resources it manages; external side effects need appropriate outbox/idempotency/compensation.

## 20. Final Pre-Application Checklist

- [ ] `PlatformTransactionManager` is a Spring bean matching the right datasource/entity manager factory.
- [ ] `TransactionTemplate` is created with a valid manager, usually via constructor injection.
- [ ] The purpose of each template bean is clear via names indicating `REQUIRED`/`REQUIRES_NEW` or read-only.
- [ ] Setters on a shared template run only at initialization, never mutated between requests.
- [ ] Separate templates exist when propagation/isolation/timeout semantics differ.
- [ ] Code calls `execute(...)` or `executeWithoutResult(...)`, not assuming the constructor opens a transaction.
- [ ] Spring data-access operations use the right resource, e.g., the same `DataSource` for `JdbcTransactionManager` and `JdbcTemplate`.
- [ ] Callbacks wrap only the necessary atomic DB work, avoiding holding transactions across slow HTTP/CPU.
- [ ] Checked/unchecked exceptions are handled properly; failures are not swallowed leading to partial commits.
- [ ] `status.setRollbackOnly()` is used intentionally and return values do not falsely report a commit.
- [ ] Inner `REQUIRED` is not misunderstood as committing independently.
- [ ] `REQUIRES_NEW` is chosen only when business rules accept an independent commit and pool/locks can support it.
- [ ] Isolation/read-only/timeout suit the manager and DB, without relying on another annotation to alter an existing physical transaction.
- [ ] Tests verify data commit/rollback after the boundary has actually completed.
- [ ] If multiple managers exist, qualifiers and tests are used to prevent transactions wrapping the wrong DB.

## 21. Conclusion

**The simplest way to create it**:

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.executeWithoutResult(status -> {
    // Database operations needing a transaction.
});
```

However, writing correct production code requires understanding:

- `PlatformTransactionManager` determines the actual transaction resources, while `TransactionTemplate` only holds the definition and coordinates the callback.
- `execute` creates a **scope according to propagation**, not always a new physical transaction.
- A template can be shared if **its configuration is fixed**; different settings require different instances.
- `RuntimeException`/`Error` escaping the callback normally rolls back; explicit `setRollbackOnly()` can roll back even if the callback returns normally.
- `REQUIRED` and `REQUIRES_NEW` are two different semantics regarding whether data can survive an outer rollback; do not swap them arbitrarily just to silence an exception.
- Spring JDBC data access must share the same resource as the transaction manager; with the wrong manager bean, a syntactically valid template still will not produce the expected atomicity.
- For reactive transactions, use `TransactionalOperator` rather than simulating JDBC thread-bound behavior.

## Official Documentation

1. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): guide to constructor injection, `execute`, `setRollbackOnly`, settings, and thread-safety of `TransactionTemplate`.
2. [Spring Framework 6.2 — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): constructors, `setTransactionManager`, `afterPropertiesSet`, and callbacks.
3. [Spring Framework 6.2 — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html): `execute` and `executeWithoutResult`.
4. [Spring Framework 6.2 — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): imperative manager contract.
5. [Spring Framework 6.2 — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html): propagation, isolation, timeout, read-only, and name setters.
6. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, and nested scopes.
7. [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): datasource, `DataSourceUtils`, and JDBC resource synchronization.
8. [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): differences between annotation/AOP boundaries and programmatic management.
