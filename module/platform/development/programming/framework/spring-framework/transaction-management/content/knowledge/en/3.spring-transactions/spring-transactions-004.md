# TransactionDefinition and Transaction Attributes in Spring Framework

## Learning Objectives

After this lesson, you will be able to: explain how `TransactionDefinition` differs from `TransactionStatus`; use the five attributes propagation, isolation, timeout, read-only, and name; predict the behavior of nested transactions; distinguish `TransactionDefinition` from `TransactionAttribute` and `@Transactional`; configure transactions in Java; and verify commits/rollbacks accurately against a database.

## 1. What Does TransactionDefinition Define?

`org.springframework.transaction.TransactionDefinition` is an interface representing **a request for a transaction**, not an already-started transaction. It answers: if a transaction exists, should we join or create a new one? Which isolation level should be used? What is the timeout? Is it read-only or writable? What is the transaction name?

In the synchronous model, `PlatformTransactionManager` accepts the definition and returns the actual status:

```text
TransactionDefinition (policy/request)
             |
             v
PlatformTransactionManager.getTransaction(definition)
             |
             v
TransactionStatus (status of the specific execution)
             |
             +--> JDBC/JPA operations join the transaction
             |
             +--> commit(status) or rollback(status)
```

`TransactionDefinition` does not hold a JDBC connection, does not provide a commit method, and does not itself decide which exceptions trigger rollback. `TransactionStatus` represents an execution instance; you can query `isNewTransaction()`, `isRollbackOnly()`, `isCompleted()`. The same definition can be reused, whereas each time the manager processes it there is a separate transaction status.

Two ways to use it in an application:

- **Declarative:** place `@Transactional` on a method or class; the Spring transaction interceptor translates the annotation into transaction attributes and manages begin/commit/rollback.
- **Programmatic:** create a `DefaultTransactionDefinition` and pass it to `PlatformTransactionManager.getTransaction(...)`; or configure `TransactionTemplate` so you do not have to manage status manually.

In the reactive model, the attributes have corresponding meanings; however, transaction operations use `ReactiveTransactionManager`/`TransactionalOperator` and Reactor Context. The JDBC examples below are imperative—do not mix `PlatformTransactionManager` with reactive `Mono/Flux`.

## 2. Five Getters and Default Values

| Attribute | `TransactionDefinition` Getter | Default | Meaning |
|---|---|---|---|
| Propagation | `getPropagationBehavior()` | `PROPAGATION_REQUIRED` | How to join/create a transaction |
| Isolation | `getIsolationLevel()` | `ISOLATION_DEFAULT` | How concurrent transactions are isolated |
| Timeout | `getTimeout()` | `TIMEOUT_DEFAULT` (`-1`) | Number of seconds allocated for a new transaction, if supported |
| Read-only | `isReadOnly()` | `false` | Read-only hint for the manager/driver/ORM |
| Name | `getName()` | `null` | Name for logging/monitoring |

`TransactionDefinition.withDefaults()` provides an **unmodifiable** default definition. When customization is needed, use `new DefaultTransactionDefinition()` and the corresponding setters: `setPropagationBehavior`, `setIsolationLevel`, `setTimeout`, `setReadOnly`, `setName`.

`ISOLATION_DEFAULT` does not fixedly mean `READ_COMMITTED`: the data system/driver determines it. `TIMEOUT_DEFAULT` uses the default timeout of the transaction manager/transaction system or no limit if unsupported. Crucially, **the requested value is not identical to the outcome observed at the database**.

## 3. Propagation: Relationship with an Existing Transaction

This attribute controls business boundaries when service A calls service B. Spring supports seven standard behaviors:

| Propagation | When a transaction already exists | When no transaction exists |
|---|---|---|
| `REQUIRED` | Join the current transaction | Start a new transaction |
| `SUPPORTS` | Join | Run without a physical transaction |
| `MANDATORY` | Join | Throw `IllegalTransactionStateException` |
| `REQUIRES_NEW` | Suspend the current transaction, start a separate transaction | Start a new transaction |
| `NOT_SUPPORTED` | Suspend the transaction, run outside a transaction | Run outside a transaction |
| `NEVER` | Throw `IllegalTransactionStateException` | Run outside a transaction |
| `NESTED` | Use a savepoint within the same physical transaction if supported | Behaves like `REQUIRED` |

Full constant names on the interface are `TransactionDefinition.PROPAGATION_REQUIRED`, `TransactionDefinition.PROPAGATION_REQUIRES_NEW`, `TransactionDefinition.PROPAGATION_NESTED`, etc. In `@Transactional`, use the enums `Propagation.REQUIRED`, `Propagation.REQUIRES_NEW`, `Propagation.NESTED`.

### REQUIRED — Default for Most Business Operations

```text
OrderService.placeOrder()        REQUIRED
    |
    +-- StockService.reserve()   REQUIRED
    |
    +-- BillingService.charge()  REQUIRED

      One physical transaction T1
   (multiple logical transaction scopes)
```

If outer has no transaction yet, `placeOrder()` creates T1. Inner `REQUIRED` calls join T1 and thus commit/rollback together. Each call still has its own logical transaction scope. If inner marks rollback-only and outer catches the error and continues, when outer attempts to commit it may receive `UnexpectedRollbackException`: T1 cannot commit once marked for rollback. Trying to "swallow" the exception does not clear the rollback-only marker.

### REQUIRES_NEW — Separate Physical Transaction

```text
Outer T1 is running
  |
  +-- Inner REQUIRES_NEW
        suspend T1
        begin T2
        commit/rollback T2
        resume T1
  |
Outer T1 continues and commits/rolls back
```

T2 makes an independent commit/rollback decision. If T2 has committed and T1 subsequently rolls back, T2's committed changes **are not undone with T1**. Because T1's resources may remain held while acquiring another connection for T2, evaluate connection pool limits, concurrent load, and business consistency. Use only when business logic genuinely requires independence.

### NESTED — Savepoint, Not an Independent Transaction

With JDBC and a transaction manager/driver supporting savepoints, `NESTED` creates a marker inside **the same physical transaction**. When the inner part fails, it can roll back to the savepoint and the outer part can continue. But if outer ultimately rolls back, **all** changes in the same physical transaction roll back. Therefore:

- `REQUIRES_NEW`: two physical transactions, inner commits independently.
- `NESTED`: one physical transaction, local rollback via savepoint.

`NESTED` has support limitations depending on manager/driver, especially not working out of the box with every JPA or R2DBC setup. `SUPPORTS` without a physical transaction can still maintain a transaction synchronization scope depending on manager configuration, so it should not always be treated as identical to a plain call bypassing the manager.

### Do Inner Attributes Apply When REQUIRED Joins Outer?

For example, outer has `@Transactional(readOnly = true, isolation = Isolation.READ_COMMITTED)`, and inner has `@Transactional(propagation = REQUIRED, readOnly = false, isolation = SERIALIZABLE, timeout = 3)`. Inner merely **joins** an already-started transaction, so it cannot reopen the connection to raise isolation or reset the physical transaction's timeout. Under default configuration of managers that support this, different isolation/timeout/read-only requests from inner are typically ignored when joining; the outer transaction's characteristics govern execution.

With managers extending `AbstractPlatformTransactionManager`, you can call `setValidateExistingTransaction(true)` to reject incompatible requests, such as differing isolation or an inner read-write joining an outer read-only transaction. When enabling this, check existing nested services because some previously working flows will start being rejected.

## 4. Isolation: What Data Can a Transaction See?

Typical concurrency phenomena:

- **Dirty read:** T1 sees uncommitted changes from T2; T2 rolls back, meaning the read value was never persisted.
- **Non-repeatable read:** T1 reads the same row twice, and between reads another transaction commits a modification to that row.
- **Phantom read:** T1 runs two queries with the same predicate and the set of matching rows changes because another transaction inserted/deleted/updated rows.

| Isolation | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `DEFAULT` | Per database | Per database | Per database |
| `READ_UNCOMMITTED` | Possible | Possible | Possible |
| `READ_COMMITTED` | Prevented | Possible | Possible |
| `REPEATABLE_READ` | Prevented | Prevented per standard model | Possible per standard model |
| `SERIALIZABLE` | Prevented | Prevented | Prevented |

The full constants are `TransactionDefinition.ISOLATION_DEFAULT`, `ISOLATION_READ_UNCOMMITTED`, `ISOLATION_READ_COMMITTED`, `ISOLATION_REPEATABLE_READ`, and `ISOLATION_SERIALIZABLE`. They correspond to `java.sql.Connection.TRANSACTION_*` levels. Spring passes the request to the driver/manager; the database decides how locking, MVCC, or conflict handling works.

**Understand the table's limits:** engines may prevent additional phenomena beyond the table, omit support for a level, or interpret `REPEATABLE_READ` differently under MVCC. `SERIALIZABLE` may detect conflicts and abort a transaction, requiring the application to retry safely. Isolation does not replace unique constraints, conditional UPDATE operations, version columns, or explicit locking when business logic needs contention control.

Custom isolation only applies when a **new physical transaction** is created. An inner `REQUIRED` joining T1 does not change T1's isolation level. This is especially important when method-level and class-level annotations differ.

## 5. Timeout: Limiting Execution Time

`getTimeout()` is in seconds or `TIMEOUT_DEFAULT = -1`. `setTimeout(10)` or `@Transactional(timeout = 10)` requests a ten-second limit for a **new** transaction, if supported by the transaction manager. You cannot assume an inner `REQUIRED` joining an existing transaction starts an independent timeout for the whole transaction.

With Spring JDBC, the transaction manager and `JdbcTemplate` can apply the remaining time to SQL statements; when checks happen and whether SQL can be canceled depend on the driver/database. A transaction timeout is not the same as a connection pool acquisition timeout, does not automatically interrupt arbitrary CPU code, and does not guarantee stopping an HTTP call at exact second 10. Consider statement/query timeouts, lock timeouts, and request deadlines as needed.

`@Transactional(timeoutString = "10")` is the string-based declaration variant; in a Spring application, resolved configuration values can be used instead of hardcoding. Timeout values may be rejected by an unsupported manager; verify on your actual deployment stack.

## 6. Read-Only: Optimization Hint, Not a Data Locking Mechanism

`setReadOnly(true)`/`@Transactional(readOnly = true)` signals the expectation of read-only data access. With some ORMs/drivers, Spring may reduce flushing/checks, optimize sessions, or pass a read-only flag to the connection/database.

**Do not assume `readOnly=true` blocks all UPDATE/INSERT/DELETE statements.** Some managers ignore the hint, and some databases enforce it partially or fully. If business requirements demand blocking writes, use database permissions, SQL/endpoint controls, and test against the target database.

A report query service is a good fit for `readOnly=true`. Write services use read-write transactions. Once inside an outer read-only transaction, an inner `readOnly=false` method is not guaranteed to alter the already-bound resource.

## 7. Transaction Name, Rollback Rules, and TransactionAttribute

`getName()` is useful for transaction monitoring and logs. In programmatic transactions, call `DefaultTransactionDefinition.setName("reconcile-invoices")`. With Spring declarative transactions, the name is typically the fully qualified class name + dot + intercepted method name; `@Transactional` has no attribute to customize this name.

`TransactionAttribute` extends `TransactionDefinition`, adding semantics for the interceptor, especially **exception-based rollback rules**. Distinguish:

| Setting | API Level | Usage |
|---|---|---|
| `propagation` / `isolation` / `timeout` / `readOnly` / `name` | `TransactionDefinition` | `DefaultTransactionDefinition` / `@Transactional` |
| `rollbackFor` / `noRollbackFor` | Transaction attributes and interceptor | `@Transactional(rollbackFor = IOException.class)` |
| `transactionManager` / `value` | Manager selection for annotation/interceptor | `@Transactional(transactionManager = "billingTx")` |
| `label` | Extended metadata; manager-specific handling | `@Transactional(label = {"batch"})` |

By default with `@Transactional`, unchecked `RuntimeException` and `Error` trigger rollback; checked exceptions normally do not roll back automatically unless rules are declared or the application changed its default policy (Spring 6.2+ allows configuring a default rollback policy). `TransactionDefinition` has no `getRollbackFor()`: if using `PlatformTransactionManager` manually, your code itself calls `commit(status)` or `rollback(status)`.

`@Transactional(transactionManager = "billingTx")` selects the **manager's bean name/qualifier**, not the `getName()` transaction name. `label` adds descriptive labels that a manager may handle specifically; it is not an SQL execution directive.

## 8. Complete Java 17 Example: Observing Attributes and Real Rollback

The standalone runnable example below uses Spring JDBC and in-memory H2. It configures `DefaultTransactionDefinition`, opens transactions via `PlatformTransactionManager`, and verifies commit/rollback with independent queries. This is an **imperative** example requiring no Spring Boot.

### Directory Structure

```text
transaction-definition-demo/
  pom.xml
  src/main/java/demo/TxDefinitionDemo.java
```

**`pom.xml`** (JDK 17+, Maven; dependencies will download if not already cached):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-definition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/TxDefinitionDemo.java`:**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class TxDefinitionDemo {
    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:tx_defs;DB_CLOSE_DELAY=-1", "sa", "");
        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
                "CREATE TABLE accounts (id BIGINT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO accounts VALUES (1, 100), (2, 50)");

        PlatformTransactionManager manager =
                new JdbcTransactionManager(dataSource);

        var definition = new DefaultTransactionDefinition();
        definition.setName("wallet-transfer");
        definition.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        definition.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        definition.setTimeout(10);
        definition.setReadOnly(false);

        System.out.println(
                "definition: required=" +
                (definition.getPropagationBehavior()
                    == TransactionDefinition.PROPAGATION_REQUIRED) +
                ", readCommitted=" +
                (definition.getIsolationLevel()
                    == TransactionDefinition.ISOLATION_READ_COMMITTED) +
                ", timeout=" + definition.getTimeout() +
                ", readOnly=" + definition.isReadOnly());
        System.out.println("initial: " + balances(jdbc));

        transfer(jdbc, manager, definition, 1, 2, 20, false);
        System.out.println("after commit: " + balances(jdbc));

        try {
            transfer(jdbc, manager, definition, 1, 2, 5, true);
        } catch (IllegalStateException e) {
            System.out.println("caught: " + e.getMessage());
        }
        System.out.println("after rollback: " + balances(jdbc));
    }

    private static void transfer(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager,
            TransactionDefinition definition,
            long from, long to, int amount, boolean simulateFailure) {
        TransactionStatus status = manager.getTransaction(definition);
        try {
            int debited = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE id = ? AND balance >= ?",
                    amount, from, amount);
            if (debited != 1) {
                throw new IllegalStateException("debit failed");
            }

            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }

            int credited = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (credited != 1) {
                throw new IllegalStateException("credit failed");
            }
            manager.commit(status);
        } catch (RuntimeException e) {
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw e;
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);
        return a + "," + b;
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxDefinitionDemo
```

**Expected stdout** (excluding environment-specific tool/logging output):

```text
definition: required=true, readCommitted=true, timeout=10, readOnly=false
initial: 100,50
after commit: 80,70
caught: simulated failure
after rollback: 80,70
```

Explanation:

1. Creating `definition` only configures the policy; the transaction **has not started yet**.
2. The first `getTransaction(definition)` opens T1. Subtracting 20 and adding 20 share the connection Spring binds to the transaction; `commit(status)` yields 80,70.
3. Next, T2 is opened, 5 is subtracted, and `IllegalStateException` is intentionally thrown before adding; the catch branch calls `rollback(status)`, so afterward balances remain 80,70.
4. `status.isCompleted()` prevents rolling back again once the status has completed. In real code, commit/rollback exception handling must also be designed carefully; using higher-level abstractions is preferable to reduce lifecycle management errors.

Here `DriverManagerDataSource` is used simply for illustration, not as a connection pool suitable for production. Use the same `DataSource` for `JdbcTransactionManager` and `JdbcTemplate`; if an independent connection is opened using raw APIs, SQL may not join the Spring-managed transaction.

## 9. From TransactionDefinition to @Transactional and TransactionTemplate

In a Spring application with transaction management enabled, corresponding attributes can be declared with annotations. The example below is a **Spring service**, not a standalone `main` program (it requires a Spring context, a `JdbcTemplate` bean, and a transaction manager):

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Integer getBalance(long id) {
        return jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, id);
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = false)
    public void credit(long id, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        int rows = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, id);
        if (rows != 1) {
            throw new IllegalStateException("account not found");
        }
    }
}
```

Class-level `readOnly = true` applies as the default configuration for `getBalance()`; the specific annotation on `credit()` takes precedence over the class-level metadata. However, if `credit()` joins an already read-only outer physical transaction, the new attribute is not guaranteed to change the outer resource.

Invoke the method through the **Spring proxy**. In default proxy mode, `this.credit(...)` within the same class bypasses `credit()`'s own interceptor. In applications using Spring Framework directly, enable `@EnableTransactionManagement` or equivalent configuration; Spring Boot typically auto-configures when valid dependencies/managers are present.

When only a section of code needs a transaction without managing status manually, use `TransactionTemplate`, which extends `DefaultTransactionDefinition`:

```java
// Code snippet in a Spring component that already has manager and JdbcTemplate jdbc.
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
template.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(10);

template.executeWithoutResult(status -> {
    int rows = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            5, 1);
    if (rows != 1) {
        throw new IllegalStateException("account not found");
    }
});
```

`TransactionTemplate` handles begin/commit/rollback around the callback. With unchecked exceptions, an error escaping the callback makes the template roll back. For checked exceptions or business logic wanting rollback without throwing an exception, design explicit handling/`status.setRollbackOnly()`.

## 10. Choosing Appropriate Settings

| Need | Suggestion | What must be verified |
|---|---|---|
| Service writing multiple tables as an atomic unit | `REQUIRED` | Same manager/resource; propagation not broken by async calls |
| Child transaction truly independent of outer | `REQUIRES_NEW` | Connection pool and consequences of outer rollback |
| Must only be called when caller already has a transaction | `MANDATORY` | Clear error if called outside a transaction |
| Partial rollback within a JDBC transaction | `NESTED` | Savepoint and manager/driver support |
| Read-only report queries | `readOnly = true` | How the hint is applied by manager/ORM |
| Prevent dirty reads | `READ_COMMITTED` or higher | Actual database isolation |
| Limit how long resources are held | `timeout = n` | Driver/statement/query timeout |
| Small code block needing its own transaction | `TransactionTemplate` | Callback throws/rolls back properly |

If an application has multiple transaction managers, `@Transactional(transactionManager = "ordersTx")` must select the right bean. Having two JDBC/R2DBC managers or two datasources does not turn those resources into **a distributed atomic transaction**. Each local transaction has its own scope.

## 11. Common Mistakes and Required QA

1. **Assuming inner isolation always wins.** Inner `REQUIRED` may join an old physical transaction and thus not reconfigure isolation.
2. **Confusing `REQUIRES_NEW` with `NESTED`.** One uses a separate transaction; the other typically uses a savepoint inside the existing transaction.
3. **Treating read-only as a database permission.** Use proper access permissions/constraints when writes must truly be blocked.
4. **Treating timeout as automatically killing every thread.** Verify SQL/driver/request timeouts and how timeouts react.
5. **Catching an error and assuming rollback-only was cleared.** Outer may throw `UnexpectedRollbackException` when attempting to commit.
6. **Thinking `rollbackFor` belongs to the `TransactionDefinition` interface.** It belongs to transaction attributes/annotation interceptor, not the five basic getters.
7. **Adding `@Transactional` but calling via `this.method()`.** Self-invocation does not pass through the proxy in default mode.
8. **Forgetting to set the right manager and DataSource.** SQL obtaining connections outside the transaction-bound resource may fail to roll back with the operation.
9. **Testing only the happy path.** Test failures after the first write statement and re-read data after the transaction ends.

Minimum integration checklist: one commit case with correct data; one exception case rolling back all changes; one nested `REQUIRED` case with rollback-only; one `REQUIRES_NEW` independent commit case if used; one `NESTED` case with savepoints if supported; concurrent read/write tests at the chosen isolation; and timeout on a real database. To verify commit, query using a new connection/transaction rather than only checking an old persistence context's cache.

## 12. Self-Check Questions

1. Why can `TransactionDefinition` be reused while `TransactionStatus` is tied to each execution?
2. If inner `REQUIRED` declares `SERIALIZABLE` while outer is `READ_COMMITTED`, what determines the actual isolation?
3. If inner `REQUIRES_NEW` commits and then outer rolls back, is inner's data rolled back?
4. How does `NESTED` differ from `REQUIRES_NEW` in terms of physical transactions and savepoints?
5. Why can't `readOnly = true` replace database permissions?
6. Distinguish `getName()`, `@Transactional(transactionManager = "...")`, and `@Transactional(label = "...")`.
7. When using the manager directly, who decides rollback instead of `rollbackFor`?

## References

- Spring Framework, TransactionDefinition API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework, DefaultTransactionDefinition API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework, Transaction Abstraction: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Spring Framework, Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework, Using @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework, Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
