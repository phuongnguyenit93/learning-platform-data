# Declarative vs. Programmatic Transaction Management in Spring Framework

## 1. Goals and context

After this lesson, you will be able to: define the transaction boundary for a use case; implement declarative transactions using `@Transactional`; implement programmatic transactions via `TransactionTemplate` or `PlatformTransactionManager`; explain commit/rollback, propagation, and the role of proxies/AOP; and choose the right approach based on business requirements.

Suppose we transfer 20 currency units from account A to B. The system must ensure **debiting A and crediting B either both succeed, or neither takes effect**. If crediting B fails after debiting A, the transaction must roll back. A transaction guarantees atomicity for data resources **actually managed within that transaction**; HTTP calls, sending emails, or publishing messages to external systems are not automatically rolled back by the annotation.

Spring supports two ways to specify where a transaction starts and ends:

- **Declarative:** describes transaction policy on a method/class, typically using `@Transactional`. Spring AOP and the transaction interceptor apply the policy when the method is called through a proxy.
- **Programmatic:** directly wraps the processing block in `TransactionTemplate` or calls `PlatformTransactionManager` for explicit scope control. Useful when the transaction spans only a short block, boundaries depend on branching logic, or explicit orchestration is required.

Both rely on a transaction manager; they differ in **how the boundary is expressed**, not in using two different storage mechanisms.

## 2. Spring's transaction infrastructure

| Component | Role |
| --- | --- |
| `PlatformTransactionManager` | Coordinates get-transaction/commit/rollback in synchronous JDBC/JPA execution flows. |
| `ReactiveTransactionManager` | Coordinates transactions for reactive pipelines, binding to context rather than ThreadLocal. |
| `TransactionDefinition` | Policy: propagation, isolation, timeout, read-only. |
| `TransactionStatus` | Transaction state; can mark `setRollbackOnly()`. |
| `TransactionInterceptor` | AOP advice enforcing declarative transaction policy around a method call. |
| `TransactionTemplate` | Callback API hiding repetitive begin/commit/rollback boilerplate. |

Depending on the technology, the transaction manager may be `JdbcTransactionManager`/`DataSourceTransactionManager` for JDBC, `JpaTransactionManager` for JPA, or another implementation. Having an appropriate manager bean and ensuring data access operations participate in the right transactional resource are essential prerequisites. Never assume two datasources or a database plus an external API are covered by a single local transaction.

Synchronous cycle when a caller invokes a transactional service:

```text
Caller
  -> Boundary (@Transactional proxy or TransactionTemplate)
     -> Select transaction manager
     -> Open new transaction or join existing transaction
     -> Data operation A; data operation B
     -> Success: commit if the boundary owns the transaction
     -> Error per rollback rule / rollback-only: roll back
  -> Return result or throw exception to caller
```

## 3. Declarative management with `@Transactional`

### 3.1. Declaration and proxy mechanism

In Java, the annotation is typically placed on a service bean representing a business unit of work. This example uses an `accounts(id, balance)` table, a `JdbcTemplate`, and a configured transaction manager; full imports are shown:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("Destination not found");
        }
    }
}
```

This is an **illustrative class**, not a standalone application; section 6 contains a complete runnable project. When `transfer` is invoked **through the Spring bean proxy**, `TransactionInterceptor` selects the transaction manager, starts or joins a transaction, invokes the body, and decides completion. If the credit statement fails with a `RuntimeException`, the debit from A is rolled back. Place the transaction boundary at the business entry point (service/use case), rather than splitting small operations into separate transactions.

In plain Spring Framework, enable annotation-driven transaction management via `@EnableTransactionManagement` on `@Configuration` or `<tx:annotation-driven/>` in XML. Spring Boot normally auto-configures this when compatible managers/dependencies are present. The annotation itself is merely **metadata**: instantiating objects manually with `new` or lacking transaction infrastructure renders the annotation ineffective.

**Declarative transactions can also be configured in XML**, such as `<tx:advice>` combined with an AOP pointcut matching method names. When Java code can be annotated directly, `@Transactional` is usually easier to read; XML is helpful when source code cannot be edited or externalized class policies are desired.

### 3.2. Key attributes

| Attribute | Meaning / common default |
| --- | --- |
| `propagation` | `REQUIRED`: join current transaction or open a new one if none exists. |
| `isolation` | `DEFAULT`, decided by the database/manager. |
| `readOnly` | `false`; `true` is normally an **optimization hint**, not a strict write-prohibition mechanism. |
| `timeout` | Uses timeout in seconds if supported by the manager; defaults to the transaction system. |
| `rollbackFor`, `noRollbackFor` | Adds exceptions that should/should not trigger rollback. |
| `transactionManager` | Selects a specific manager bean when multiple managers exist. |

Example of deliberate policy configuration on a method in a Spring bean:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    rollbackFor = IOException.class
)
public void importOrders() throws IOException {
    // JDBC/JPA statements belonging to a single use case.
}
```

The snippet above is an **illustrative method**, requiring imports for `java.io.IOException` and `org.springframework.transaction.annotation.Transactional`, `Propagation`, `Isolation`. Declarations of isolation/timeout/read-only on an inner `REQUIRED` scope do not automatically alter a transaction already created by an outer scope; the transaction manager and database also determine actual support.

**Default rollback behavior of `@Transactional`:** unchecked `RuntimeException` and `Error` trigger rollback; checked `Exception`s (e.g., `IOException`) do not trigger rollback by default unless specified. Use `rollbackFor` to be explicit. Since Spring Framework 6.2, a global default rollback policy option is available, so check project configuration when predicting behavior.

A common mistake is swallowing exceptions:

```java
@Transactional
public void wrongPattern() {
    try {
        writeData();
    } catch (RuntimeException ex) {
        logError(ex);
    }
}
```

`writeData` and `logError` here are **illustrative functions**. When the exception is caught and the method returns normally, the interceptor may commit changes if the transaction was not marked rollback-only. Let errors propagate to the boundary, configure `rollbackFor` appropriately, or when there is a clear business reason call `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` inside an active transaction. Never report success when a mandatory operation failed to complete.

### 3.3. Proxy limitations to remember

The default mode uses a Spring AOP proxy, intercepting only **external calls passing through the proxy**. If `this.inner()` calls another method on the same instance, `@Transactional` on `inner()` is not triggered:

```java
@Service
public class OrderService {
    public void placeOrder() {
        saveOrder(); // self-invocation: bypasses @Transactional on saveOrder.
    }

    @Transactional
    public void saveOrder() {
        // Data persistence operations.
    }
}
```

This is an **illustrative class**, without a persistence implementation. Fix it by placing the boundary on `placeOrder()`, or moving `saveOrder()` into another Spring service bean and calling through that bean. AspectJ weaving can handle self-invocation, though it requires separate configuration.

Additionally:

- Prefer `public` methods on concrete Spring-managed beans invoked through a proxy. Whether `private`/`final` or non-public methods are intercepted depends on proxy type and Spring version; do not assume they behave like public methods.
- Class-level annotations set defaults for matching methods; more specific method-level annotations take higher precedence.
- Imperative transactions are typically bound to the **current thread**. `@Async`, new threads, or `CompletableFuture` do not automatically inherit the caller's transaction.
- Do not rely on `@Transactional` inside `@PostConstruct` before proxy initialization is complete.
- Transactions do not automatically undo HTTP calls, sent emails, or side effects on external systems. For those tasks, consider transactional outbox/saga/compensation.

## 4. Programmatic transaction management

### 4.1. `TransactionTemplate`: preferred choice for imperative code

`TransactionTemplate` takes a `PlatformTransactionManager` and accepts a callback. The template manages begin, commit/rollback, and resource cleanup; business code focuses solely on the operations inside the transaction:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class InventoryWriter {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public InventoryWriter(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    public void reserve(long productId, int quantity) {
        template.executeWithoutResult(status -> {
            int updated = jdbc.update(
                "UPDATE inventory SET available = available - ? " +
                "WHERE id = ? AND available >= ?",
                quantity, productId, quantity
            );
            if (updated != 1) {
                status.setRollbackOnly();
            }
        });
    }
}
```

This is an **illustrative class**, requiring an `inventory` table and manager/JDBC beans. `status.setRollbackOnly()` requests rollback even when the callback returns normally. Real business logic should return a result or throw an exception so the caller knows the reservation failed; never assume callback completion guarantees the work was committed.

Use `template.execute(status -> { ...; return result; })` when returning a value. When the callback throws an unchecked exception, the template rolls back and rethrows the exception (barring other rollback/cleanup issues). When handling checked exceptions, translate them into intentional exceptions, handle them inside the callback, or mark rollback-only; do not assume the callback signature permits arbitrary `throws IOException`.

The template can be configured before use via `setPropagationBehavior(Propagation.REQUIRES_NEW.value())`, `setIsolationLevel(...)`, `setReadOnly(true)`, and `setTimeout(...)`. If multiple concurrent calls share the same instance, fix the configuration at initialization rather than mutating it between callbacks.

### 4.2. Calling `PlatformTransactionManager` directly

This lower-level approach gives direct control over the transaction lifecycle. This Java 17+ snippet uses Spring transaction dependencies, and the caller-supplied `Runnable` holds the work to run:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class ManualUnitOfWork {
    private final PlatformTransactionManager manager;

    public ManualUnitOfWork(PlatformTransactionManager manager) {
        this.manager = manager;
    }

    public void run(Runnable work) {
        TransactionStatus status =
            manager.getTransaction(new DefaultTransactionDefinition());

        try {
            work.run();
            manager.commit(status);
        } catch (RuntimeException | Error ex) {
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw ex;
        }
    }
}
```

`getTransaction` may join an existing transaction according to propagation, so `commit(status)` does not always mean an immediate physical commit. On the error path, avoid rolling back an already-completed status and rethrow the error so the caller can handle it. Prefer `TransactionTemplate` in most cases to reduce boilerplate and error-prone paths.

### 4.3. Reactive: `TransactionalOperator`

With R2DBC or reactive pipelines, use `ReactiveTransactionManager`/`TransactionalOperator`; do not wrap a `Mono` in `TransactionTemplate` and expect reactive SQL to finish inside the callback:

```java
// Illustration in a reactive service with a ReactiveTransactionManager:
TransactionalOperator operator = TransactionalOperator.create(reactiveManager);
Mono<Void> move = debit(accountA, amount).then(credit(accountB, amount));
return operator.transactional(move);
```

`debit`, `credit`, and `reactiveManager` are **illustrative** variables/methods; imports for `reactor.core.publisher.Mono` and `org.springframework.transaction.reactive.TransactionalOperator` are required. Reactive transactions use **Reactor Context**, requiring operations to stay in the same reactive pipeline.

## 5. Propagation, isolation, and rollback-only

| Propagation | When the caller already has a transaction |
| --- | --- |
| `REQUIRED` (default) | Participates in the same physical transaction; inner rollback-only affects outer. |
| `REQUIRES_NEW` | Suspends outer and starts an **independent** physical transaction. |
| `NESTED` | Typically creates a savepoint within the same JDBC transaction, depending on manager/resource. |
| `SUPPORTS` | Participates if present; otherwise runs non-transactionally. |
| `MANDATORY` | Requires an active transaction; throws an exception if none exists. |
| `NOT_SUPPORTED` | Suspends any existing transaction to run non-transactionally. |
| `NEVER` | Throws an exception if a transaction is currently active. |

**Logical versus physical transaction:** With two `REQUIRED` scopes invoked through proxies, each scope can independently decide rollback-only while sharing one physical transaction. If the inner scope marks rollback-only and the outer scope still attempts to commit, Spring may throw `UnexpectedRollbackException` so the caller is not misled into thinking the transaction committed successfully. `REQUIRES_NEW` is independent, but often requires an extra connection while the outer still holds its connection: too small a pool can cause connection waits or exhaustion. `NESTED` is not equivalent to `REQUIRES_NEW` because it usually relies on savepoints on the same connection.

Isolation (`READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, ...) controls how transactions observe concurrent changes per DB semantics and does not replace locking/optimistic locking design. `readOnly=true` is a provider optimization hint, not a guarantee against writes. Timeouts take effect only as supported by the manager and resource.

## 6. Standalone demo with Java 17+, Maven, Spring Boot, and H2

The following example uses **Spring Boot 3.5.16**, `spring-boot-starter-jdbc`, and in-memory H2. The program creates 2 accounts and tests success and failure with both transaction approaches; H2 lets us inspect post-rollback balances without installing a database.

Create the files:

```text
transaction-demo/
  pom.xml
  src/main/java/example/TxDemoApplication.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>transaction-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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

`src/main/java/example/TxDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE accounts (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 2, 100);

            System.out.println("Start: " + balances(jdbc));

            try {
                transfer.declarative(1, 2, 20, true);
            } catch (IllegalStateException expected) {
                // Continue demo after intentional failure.
            }
            System.out.println("Declarative failure: " + balances(jdbc));

            transfer.declarative(1, 2, 20, false);
            System.out.println("Declarative success: " + balances(jdbc));

            try {
                transfer.programmatic(1, 2, 10, true);
            } catch (IllegalStateException expected) {
                // Continue demo after intentional failure.
            }
            System.out.println("Programmatic failure: " + balances(jdbc));

            transfer.programmatic(1, 2, 10, false);
            System.out.println("Programmatic success: " + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?", Integer.class, 2
        );
        return a + " / " + b;
    }
}

@Service
class TransferService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    TransferService(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    @Transactional
    public void declarative(int from, int to, int amount, boolean fail) {
        transferSteps(from, to, amount, fail);
    }

    public void programmatic(int from, int to, int amount, boolean fail) {
        template.executeWithoutResult(
            status -> transferSteps(from, to, amount, fail)
        );
    }

    private void transferSteps(int from, int to, int amount, boolean fail) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Cannot debit source");
        }

        if (fail) {
            throw new IllegalStateException("Simulated failure after debit");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("Cannot credit destination");
        }
    }
}
```

From the `transaction-demo` directory, using JDK 17+ and Maven 3.9+:

```bash
java -version
mvn -version
mvn -q spring-boot:run
```

The lines printed by `CommandLineRunner`, aside from Spring logs, are:

```text
Start: 100 / 100
Declarative failure: 100 / 100
Declarative success: 80 / 120
Programmatic failure: 80 / 120
Programmatic success: 70 / 130
```

Both intentional errors thrown right after the debit step roll back, leaving balances unchanged. Both successful runs transfer 20 and 10 respectively; the total is always 200. `@Transactional` works because the runner calls the injected `TransferService` bean through its Spring proxy; `TransactionTemplate` manages the callback's scope directly. Real production code still requires concurrency controls, idempotency, and testing against the target database; H2 only illustrates the transaction boundary.

## 7. Choosing an implementation and verifying results

| Problem | Usually appropriate approach |
| --- | --- |
| Service use case where the transaction spans the entire method | `@Transactional`: expresses policy clearly with minimal boilerplate. |
| Only a small block needs a transaction or has special branching | `TransactionTemplate`: boundary right at the callback site. |
| Need an independent transaction nested inside a workflow | `REQUIRES_NEW` via another service proxy or a template configured with propagation; consider connection pool sizing. |
| Need direct begin/commit/rollback decisions inside specialized algorithms | `PlatformTransactionManager` directly, while carefully handling all error paths. |
| R2DBC/Reactive pipelines | `TransactionalOperator` or `@Transactional` with `ReactiveTransactionManager`. |

Practical QA checklist: call the service **through a bean**; verify the right manager and datasource; deliberately inject a failure at the **second step** and confirm the first step rolls back; test checked exceptions; test inner `REQUIRED` rollback-only; check for self-invocation; avoid network calls inside long transactions; verify with integration tests on the target database. If a test places `@Transactional` on the test method itself, remember Spring Test typically rolls back the test transaction, which differs from verifying the service's actual boundary.

**Self-check:** What happens if `@Transactional` and `TransactionTemplate` are removed from the demo? Why does `this.save()` not trigger `save`'s interceptor? Why can an inner `REQUIRED` scope marking rollback-only cause the outer scope to throw `UnexpectedRollbackException`? When should you genuinely use `REQUIRES_NEW` instead of `NESTED`?

## 8. Official Spring documentation

- [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
