# Transaction Boundaries Spanning Multiple Repository Operations in Spring Framework

## 1. Why Must a Business Operation Span Multiple Repositories?

Suppose a business operation that **transfers 100 currency units** from account A to account B needs to perform three operations:

1. `AccountRepository` deducts 100 from A.
2. `AccountRepository` adds 100 to B.
3. `AuditRepository` records a transfer history entry.

Each repository is responsible for data access, but **all three operations together form a single business operation**. If step 1 succeeds while step 2 or 3 fails, the data will be inconsistent. The business rule is that **either all three changes are committed together, or all of them are rolled back**.

This is the meaning of a **transaction boundary spanning multiple repository operations**: Spring starts a transaction before executing the sequence of operations in a service so that the repositories participate in the same physical transaction, then commits when all succeed or rolls back when an error matching the rollback rules occurs.

Conceptual diagram:

~~~text
Controller / Job / Message Handler
               |
               v
     TransferService.transfer()  <-- @Transactional, starts the boundary
        |         |        |
        v         v        v
   AccountRepo  AccountRepo AuditRepo
   debit(A)     credit(B)   record(...)
        \         |        /
         \        |       /
          +--- same transaction ---+
                       |
             completed?  +-- error matching rollback rule --> ROLLBACK
                 |
               COMMIT
~~~

**Key takeaway:** a transaction is usually the boundary of **a use case at the service/application layer**, not necessarily matching the boundary of a single repository, a single SQL statement, or an HTTP request. A repository can provide multiple independent data methods; the service knows which methods must complete together.

## 2. What Does a Transaction Guarantee?

With a transactional database supporting ACID, the general scope aims to achieve:

- **Atomicity:** changes within a transaction either all commit or all roll back.
- **Consistency:** database constraints and application-checked invariants must be maintained; a transaction does not write business rules for you automatically.
- **Isolation:** concurrent transactions are observed according to the database's isolation level; it is not serializable by default.
- **Durability:** the database guarantees committed data according to its storage mechanism and configuration.

A transaction **does not by itself** make balance checks, inventory checks, or uniqueness checks correct under all concurrent scenarios. You may still need database constraints, conditional updates, optimistic/pessimistic locking, or an appropriate isolation level.

### Wrong Case: Each Repository Commits Independently

~~~java
// Illustrates a design without a shared transaction at the service layer.
public void transfer(long from, long to, int amount) {
    accountRepository.debit(from, amount);   // may commit first
    accountRepository.credit(to, amount);    // fails here
    auditRepository.record(from, to, amount);
}
~~~

If the calls execute independently outside a shared transaction with auto-commit (or each repository opens its own independent transaction), the debit step may already be permanently saved before the credit step fails. Placing `@Transactional` on a **Spring-managed service method** is the common way for JDBC operations against the same database to participate in one transaction.

### Right Case: One Use Case, One Transaction

~~~java
// Illustrated inside a Spring-managed service bean.
@Transactional
public void transfer(long from, long to, int amount) {
    accountRepository.debit(from, amount);
    accountRepository.credit(to, amount);
    auditRepository.record(from, to, amount);
}
~~~

In Spring's imperative transaction management, when a call goes **through a Spring proxy**, an appropriate `PlatformTransactionManager` opens or joins a transaction; repositories using the same resource source participate together, even when the repositories themselves **do not have `@Transactional`**. The annotation does not require all repositories to inherit from a base class or call a single shared repository method.

## 3. Conditions for Multiple Repositories to Actually Share One Transaction

Merely adding an annotation to the source code **is not enough**. You need to verify all of these conditions simultaneously:

1. **The service is a Spring bean** and the method call goes through the transactional proxy (`@EnableTransactionManagement` configured, or Spring Boot configures transactions appropriately).
2. **A `PlatformTransactionManager` matching the resource is present**, such as `DataSourceTransactionManager`/`JdbcTransactionManager` for JDBC on a `DataSource`, or `JpaTransactionManager` for a JPA persistence unit.
3. **The repositories participate in the resource managed by the transaction manager**. With `JdbcTemplate`, they should use the same `DataSource` associated with the transaction manager; `JdbcTemplate` obtains connections via Spring's infrastructure and thus participates in the thread-bound transaction.
4. **The operations execute within the corresponding transaction context**, usually on the same thread for imperative JDBC/JPA. A task that switches to a new thread does not automatically inherit the calling thread's transaction.
5. **Propagation allows participation**: the default `REQUIRED` joins an existing transaction; `REQUIRES_NEW` intentionally opens a separate transaction; `NOT_SUPPORTED` suspends the transaction.

For example: a `@Transactional` service and two repositories using two `JdbcTemplate` instances created from the same `DataSource` can still share a transaction. Conversely, if one repository directly calls `DriverManager.getConnection(...)`, creates a separate connection source, or uses a different manager without coordination, the "roll back everything" promise can fail.

**One data source does not mean every system in the use case is atomically transactional.** Databases, HTTP APIs, email, the file system, Redis, and message brokers usually have separate commit boundaries; section 11 explains how to coordinate them.

## 4. How Spring Opens, Binds, and Ends a Transaction

With `@Transactional` and the default `Propagation.REQUIRED`:

1. The client calls the **proxy** of `TransferService.transfer(...)`.
2. `TransactionInterceptor` looks up the metadata of `@Transactional`.
3. `PlatformTransactionManager` starts a transaction if none exists, or joins an active transaction.
4. The method body calls the repositories; in JDBC, `DataSourceTransactionManager` manages/binds the connection to the thread, and Spring JDBC obtains the appropriate connection via `DataSourceUtils`.
5. Method returns normally: the interceptor requests a commit (if it owns the actual physical transaction).
6. Method throws an exception matching a rollback rule: the interceptor rolls back or marks the shared transaction as **rollback-only**; the exception continues propagating to the caller.

Example timeline:

~~~text
t0: caller --> transactional proxy
t1: BEGIN TRANSACTION
t2: UPDATE account SET balance = balance - 100 ...
t3: UPDATE account SET balance = balance + 100 ...
t4: INSERT INTO transfer_audit ...
t5: COMMIT   (or ROLLBACK on error)
t6: return to caller
~~~

Multiple repositories **do not necessarily cause multiple BEGIN/COMMIT cycles**. With the same resource and `REQUIRED`, they share one physical transaction, even though there may be multiple logical transaction scopes when inner methods are also annotated with `@Transactional`.

A normal method calling three repositories inside a `@Transactional` service has only **one** outer boundary. There is no need to manually open additional transactions inside each repository.

## 5. Standalone Java 17+ Example: Money Transfer Across Two Repositories

This hands-on example runs without Spring Boot: it creates an in-memory H2 database, registers Spring beans using Java configuration, enables transactions, creates tables, performs a successful transfer, and then simulates a failure **after all three repository writes have executed**. When the error occurs, Spring rolls back all three changes from the second call.

Project structure:

~~~text
spring-multi-repository-transaction/
├── pom.xml
└── src/main/java/demo/TransferDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-multi-repository-transaction</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <version>3.14.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <version>3.5.1</version>
                <artifactId>exec-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/TransferDemo.java`**

~~~java
package demo;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TransferDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE account (
                        id BIGINT PRIMARY KEY,
                        balance INTEGER NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE transfer_audit (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        from_id BIGINT NOT NULL,
                        to_id BIGINT NOT NULL,
                        amount INTEGER NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)",
                    1L, 500);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)",
                    2L, 200);

            // Retrieve the bean from the context to go through the transactional proxy.
            TransferService service = context.getBean(TransferService.class);

            service.transfer(1L, 2L, 100, false);
            System.out.println("afterSuccess=" + balances(jdbc));
            System.out.println("auditAfterSuccess=" + auditCount(jdbc));

            try {
                service.transfer(1L, 2L, 50, true);
            } catch (IllegalStateException expected) {
                System.out.println("failedOperationRolledBack=true");
            }

            System.out.println("afterRollback=" + balances(jdbc));
            System.out.println("auditAfterRollback=" + auditCount(jdbc));
        }
    }

    private static java.util.List<Integer> balances(JdbcTemplate jdbc) {
        return jdbc.queryForList(
                "SELECT balance FROM account ORDER BY id", Integer.class);
    }

    private static Integer auditCount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM transfer_audit", Integer.class);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:transfer_example;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public AccountRepository accountRepository(JdbcTemplate jdbc) {
            return new AccountRepository(jdbc);
        }

        @Bean
        public AuditRepository auditRepository(JdbcTemplate jdbc) {
            return new AuditRepository(jdbc);
        }

        @Bean
        public TransferService transferService(
                AccountRepository accounts, AuditRepository audits) {
            return new TransferService(accounts, audits);
        }
    }

    public static class AccountRepository {
        private final JdbcTemplate jdbc;

        public AccountRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void debit(long accountId, int amount) {
            int count = jdbc.update("""
                    UPDATE account
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """, amount, accountId, amount);

            if (count != 1) {
                throw new IllegalStateException(
                        "Account does not exist or has insufficient funds");
            }
        }

        public void credit(long accountId, int amount) {
            int count = jdbc.update("""
                    UPDATE account
                    SET balance = balance + ?
                    WHERE id = ?
                    """, amount, accountId);

            if (count != 1) {
                throw new IllegalStateException("Target account not found");
            }
        }
    }

    public static class AuditRepository {
        private final JdbcTemplate jdbc;

        public AuditRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void record(long from, long to, int amount) {
            jdbc.update("""
                    INSERT INTO transfer_audit (from_id, to_id, amount)
                    VALUES (?, ?, ?)
                    """, from, to, amount);
        }
    }

    public static class TransferService {
        private final AccountRepository accounts;
        private final AuditRepository audits;

        public TransferService(
                AccountRepository accounts, AuditRepository audits) {
            this.accounts = accounts;
            this.audits = audits;
        }

        @Transactional
        public void transfer(
                long from, long to, int amount, boolean failAfterWriting) {
            if (amount <= 0 || from == to) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            accounts.debit(from, amount);
            accounts.credit(to, amount);
            audits.record(from, to, amount);

            if (failAfterWriting) {
                throw new IllegalStateException("Simulated business failure");
            }
        }
    }
}
~~~

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.TransferDemo"
~~~

**Expected output for a fresh in-memory H2 database:**

~~~text
afterSuccess=[400, 300]
auditAfterSuccess=1
failedOperationRolledBack=true
afterRollback=[400, 300]
auditAfterRollback=1
~~~

### Explanation of Each Call's Result

**Call 1, success:**

- Account 1: `500 - 100 = 400`.
- Account 2: `200 + 100 = 300`.
- One audit row is inserted.
- The service returns normally, and the transaction manager commits all three changes.

**Call 2, intentional failure:**

- In the second transaction, the code attempts to debit 50 more, credit 50 more, and insert another audit row.
- Finally, the code throws `IllegalStateException` — a `RuntimeException` that satisfies the default rollback rule.
- Spring rolls back **both** the account updates and the audit insert from the second call. Therefore, the balances remain `[400, 300]` and the audit row count remains `1`.
- The `catch` block in `main` is **outside** the service proxy, after Spring has already handled the rollback. Catching the exception there does not re-commit the failed transaction.

The example intentionally omits `@Transactional` on the two repositories: they are registered as Spring beans and use the same `JdbcTemplate` backed by the same `DataSource`, so they automatically use the connection bound by the manager for the active transaction. If `@Transactional` is removed from the service, individual operations may auto-commit; in that case, the rollback test will no longer preserve the balances as shown above.

**Limitations of the example:** this simple simulation on H2 demonstrates how repositories combine and roll back. In a real financial system, you must also handle balance overflow, isolation/locking, idempotency, retries, immutable audit trails, and other constraints.

## 6. Where Should `@Transactional` Be Placed?

Typically, choose a **public method of the application/service layer** representing a cohesive business operation:

~~~java
// A business method where repositories are collaborating components.
@Transactional
public OrderId placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.create(command);
    inventoryRepository.reserve(command.items());
    paymentRecordRepository.recordPending(order.id());
    return order.id();
}
~~~

This is an **architectural sketch**: the types/methods are assumed to already exist in the application, not a standalone Java file. With appropriate data constraints, the transaction covers order creation, inventory reservation, and recording the payment status in the same database. **It does not by itself cover an actual payment charge at an external payment gateway.**

### Boundary Too Small

If each repository method has its own `@Transactional` and the service has no enclosing transaction:

~~~text
placeOrder() without a shared transaction
  -> orderRepository.create()      : BEGIN, COMMIT
  -> inventoryRepository.reserve() : BEGIN, ROLLBACK (error)
  -> paymentRecordRepository...    : does not run
~~~

The result may be that the order is already saved while the inventory was not reserved. An independent transaction per repository **does not replace** a service-layer transaction.

### Boundary Too Large

You do not necessarily want to place `@Transactional` on an entire controller or keep a transaction open throughout:

- Calling an HTTP API that takes several seconds.
- Waiting for user input or reading large files.
- Sending emails or performing long CPU processing.
- Waiting for message broker acknowledgments.

Long-running transactions hold connections/locks, reducing throughput and increasing the risk of deadlocks, timeouts, or connection pool exhaustion. Group **only the data access that truly needs to be atomic**, and move external side effects to an appropriate post-commit mechanism or outbox.

### One Service Calling Multiple Services

A transaction can span multiple services/repositories if the outer service method has a transaction and synchronous calls enter Spring beans using the same transaction manager with `REQUIRED`. There is no rule that "a transaction may only cross one service layer." What matters is propagation, resources, and how the proxy is invoked.

## 7. Rollback: Exceptions, Catch Blocks, and Tricky Cases

### Default Rules

With Spring's `@Transactional`, by default:

- A `RuntimeException` or `Error` escaping the transactional method → rollback.
- A **checked exception** (e.g., `IOException`) escaping → **does not** trigger rollback by default, unless configured with an appropriate rule.
- When the method returns normally → the framework attempts to commit, unless the transaction has already been marked rollback-only or fails during commit.

Use explicit rules for business checked exceptions:

~~~java
// Illustrated inside a Spring-managed service.
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    repository.savePartOne();
    repository.savePartTwo();
    remoteFileReader.readRequiredData(); // may throw IOException
}
~~~

This snippet is not a standalone runnable program; the repository and reader are assumed components. Consider reading/validating the file **before** starting the transaction to avoid holding the transaction open during slow I/O. `rollbackFor` illustrates the rollback mechanism when a checked exception must remain within the scope.

### Catching and Swallowing an Exception Inside a Transaction

~~~java
@Transactional
public void process() {
    repository.saveA();
    try {
        repository.saveB();
    } catch (IllegalStateException ex) {
        // Swallow the error and exit the method normally:
        // the transaction may commit A if not marked rollback-only.
    }
}
~~~

If the error is simply a business exception thrown on your own and no inner transaction marked rollback-only, Spring sees the method return normally and may commit `saveA()`. If the error came from an inner `@Transactional(REQUIRED)` that already marked the shared transaction rollback-only, the outer scope still cannot commit; when the outer scope attempts to commit, Spring may throw `UnexpectedRollbackException`.

The safe approach: **let the exception propagate out** when you want to roll back everything; or rethrow it after handling; or if there is a reason to return a result while still rolling back, explicitly mark rollback-only via the transaction infrastructure. Do not assume `catch` will cause the DB to roll back or "clear the error" of the transaction.

### `setRollbackOnly()` When Truly Needed

~~~java
// Illustrative snippet for use only inside an active Spring-managed transaction.
org.springframework.transaction.interceptor.TransactionAspectSupport
        .currentTransactionStatus()
        .setRollbackOnly();
~~~

This approach couples your logic to Spring; use it intentionally only when you cannot let an exception escape. Redesigning the error-return flow is usually easier to read.

### Checked Exceptions and Spring Framework 6.2

Since Spring 6.2, you can change the default rollback behavior more broadly via `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` when an application chooses to use that rule. Do not assume every project has it enabled. For examples and foundational knowledge, the default remains rolling back on `RuntimeException`/`Error`; use `rollbackFor` on the method when specific behavior independent of global configuration is needed.

## 8. Propagation Determines the Real Boundary

When a method already inside a transaction calls another method that also has `@Transactional`, the `propagation` attribute determines whether the inner method joins or separates from the transaction:

| Propagation | Behavior when an outer transaction already exists | Impact on multi-repository use cases |
|---|---|---|
| `REQUIRED` (default) | Joins the same **physical transaction**, creating its own logical scope | Default choice for a business operation needing shared rollback |
| `REQUIRES_NEW` | Suspends the outer transaction, opens a **new physical transaction** | Inner can commit independently, breaking all-or-nothing if misused |
| `NESTED` | Uses a savepoint within the **same** physical transaction when supported by manager/driver | Can roll back a portion to a savepoint and let the outer continue |
| `SUPPORTS` | Joins if a transaction exists; runs without a transaction otherwise | Easily lacks guarantees if the caller forgets to open a transaction |
| `MANDATORY` | Requires an existing transaction, throws an error if none exists | Useful when a service must only be called inside a transactional workflow |
| `NOT_SUPPORTED` | Suspends the active transaction, executes without a transaction | Unsuitable for write steps that must roll back with the rest |
| `NEVER` | Throws an error if a transaction exists | Used for logic that must always run outside a transaction |

### `REQUIRED`: Multiple Logical Scopes, One Physical Transaction

~~~text
Service.placeOrder()  @Transactional(REQUIRED) --> BEGIN
  RepoA.save()        @Transactional(REQUIRED) --> JOIN
  RepoB.reserve()     @Transactional(REQUIRED) --> JOIN
Service finishes normally                      --> COMMIT once
~~~

Even if `RepoB.reserve()` has its own annotation, with `REQUIRED` it typically joins the current transaction. Separate isolation/timeout/readOnly attributes on the joining method may not alter the active outer transaction; the actual values are determined by the scope that created the transaction. You can configure the manager to validate attribute conflicts.

### `REQUIRES_NEW`: Independent Transaction

If `AuditService.record()` carries `@Transactional(propagation = Propagation.REQUIRES_NEW)` and is called **through another bean's proxy**, the audit entry can commit independently even if the transfer transaction later rolls back. This only makes sense when the business requirement **genuinely wants** the audit record to persist independently (for example, certain error logs), and does not want the audit to roll back together with the transfer.

`REQUIRES_NEW` usually requires a second connection while the outer transaction's connection is still held. With a small connection pool or high load, overuse can cause pool exhaustion, lock contention, or deadlocks. You must also understand that the independent transaction does not see uncommitted data from the outer transaction, depending on isolation.

### `NESTED`: Savepoint, Not an Independent Transaction

With JDBC and `DataSourceTransactionManager` supporting savepoints, `NESTED` can roll back partially to a savepoint; the outer physical transaction still decides the final commit. Do not assume it works identically across all JPA/JTA managers or all drivers.

**Practical choice:** if the requirement is "three repositories must succeed or fail together," start with a single service using default `@Transactional` (`REQUIRED`), and only change propagation when there is a tested reason.

## 9. Proxy Traps That Prevent `@Transactional` from Working as Expected

### Calling a Method Within the Same Instance (*Self-Invocation*)

~~~java
// Describes a Spring bean; not a standalone program.
public void processOrder() {
    this.saveOrder(); // does not go through the transactional proxy
}

@Transactional
public void saveOrder() {
    repository.save();
}
~~~

With Spring AOP's default **proxy mode**, `this.saveOrder()` does not go through the proxy; the annotation on `saveOrder()` **does not open a transaction on its own**. If `processOrder()` is already running in a valid transaction, the inner statements still participate in that transaction via the existing context; the problem is that the annotation on the self-invoked method is not applied by the interceptor.

The clear fix: place `@Transactional` on the entry-point method called by another bean through the proxy; or move the functionality needing separate propagation to another Spring bean and call it through that bean. Do not default to `AopContext.currentProxy()` or self-injection to patch a flawed boundary design.

### Instantiating with `new` or Calling Methods Not Intercepted by the Proxy

`new TransferService(...)` created manually outside the Spring container has no transactional proxy. `@Transactional` is metadata; it is not a Java keyword that automatically generates a transaction. With JDK interface proxies, the method must belong to the proxied interface and be public. With class-based proxies, visibility requirements may vary by Spring version; `private` and `final` methods cannot be overridden for the interceptor to act as on a normal public call.

Do not rely on `@Transactional` in constructors or `@PostConstruct` because the proxy may not be active yet. Prefer public methods on Spring beans called from other components.

### Mismatched Transaction Manager / DataSource

For example, one repository uses the `DataSource` of DB A, the other uses DB B, and `@Transactional` only points to DB A's manager. The result is not automatically a distributed transaction. Identify which manager owns each resource; if atomic coordination across multiple resources is needed, consider JTA/XA when the infrastructure genuinely supports it, or design consistency using events/sagas.

### Switching Threads or Reactive Contexts

Imperative transactions via `PlatformTransactionManager` are typically bound to the current thread. `CompletableFuture.supplyAsync(...)`, `@Async`, thread pools, or task schedulers do not automatically carry the parent thread's JDBC transaction across. Putting `@Transactional` on a method returning an async type does not by itself turn all asynchronous steps into the same JDBC transaction.

With R2DBC/reactive stacks, Spring uses `ReactiveTransactionManager` and the Reactor context, which is a different model. Do not mix the two contexts and assume all repositories share one transaction.

## 10. Isolation, Locking, and Concurrency Correctness

Transaction boundaries solve **atomicity**, whereas two concurrent requests can still create race conditions depending on isolation and SQL.

Wrong example:

~~~text
T1: SELECT stock = 1
T2: SELECT stock = 1
T1: UPDATE stock = 0, commit
T2: UPDATE stock = 0, commit
Result: both requests think they sold the single remaining item.
~~~

Merely putting `@Transactional` around both calls will not necessarily eliminate this bug under default isolation. You can use a conditional atomic UPDATE:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE product_id = ? AND available >= 1;
~~~

Then check `updateCount == 1`; if it is 0, the item is out of stock/missing and the business operation must terminate accordingly. For complex read-modify-write logic, consider version-based optimistic locking or pessimistic row locks, and configure `@Transactional(isolation = Isolation.SERIALIZABLE)` when supported by the DB/driver and acceptable for performance. Do not apply high isolation levels habitually to every method.

**Read-only:** `@Transactional(readOnly = true)` is primarily an optimization hint for the transaction/persistence infrastructure; depending on the database and manager, enforcement may be limited. Do not treat it as an absolute write-permission guarantee.

**Timeout:** `@Transactional(timeout = 10)` requests a 10-second timeout subject to the capabilities of the manager and the applied operations; do not assume every slow HTTP request, thread, or I/O call will be forcefully stopped at exactly 10 seconds. Avoid opening a transaction before non-DB work.

**Retry:** deadlocks, serialization failures, or transient connection errors sometimes require retrying **the entire use case from outside the failed transaction**, rather than retrying individual SQL statements inside a transaction whose state is no longer usable. Design for idempotency and limit retry counts to avoid double writes when a step has already committed.

## 11. When a Business Operation Also Calls Systems Outside the Database

A JDBC transaction for `orderRepository` and `inventoryRepository` **cannot roll back an email already sent or an HTTP payment request that already succeeded**:

~~~text
@Transactional placeOrder()
  INSERT order                 (DB transaction)
  UPDATE inventory             (DB transaction)
  HTTP charge payment gateway  (external system, commits separately)
  INSERT payment_record        (DB transaction)
  DB COMMIT / ROLLBACK
~~~

If the final INSERT fails, the DB rolls back, but the gateway may have already charged the payment. Keeping a DB transaction open while calling the gateway also causes locks/timeouts.

Approaches depending on requirements:

- **Transactional outbox:** within the **same DB transaction**, update the order and write an outbox event; after commit, a separate worker publishes the event with retry and deduplication mechanisms. Order data and the "intent to publish the event" commit or roll back together.
- **After-commit event:** run side effects after commit using an appropriate callback/event listener; avoid publishing events before knowing for sure that the DB has committed. However, a standalone callback does not guarantee delivery after a crash; an outbox is needed when high reliability is required.
- **Saga/compensating action:** a sequence of independent services/DBs using steps and compensating actions; do not assume a local `@Transactional` can wrap everything.
- **Idempotency key:** when retrying API/payment/event calls, detect duplicate requests to avoid double-charging or creating duplicate orders.

Be clear about what "atomic" refers to: **repositories sharing the same database and manager** can reside in a local transaction; multiple services or external infrastructure usually require different protocols/coordination.

## 12. `TransactionTemplate` When Explicit Programmatic Boundaries Are Needed

`@Transactional` is the common declarative approach. When you need explicit scope control within a flow or want to avoid self-invocation traps, you can use `TransactionTemplate` from Spring:

~~~java
// Illustrative snippet, assuming template is injected and repositories are available.
transactionTemplate.execute(status -> {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
    auditRepository.record(fromId, toId, amount);
    return null;
});
~~~

`TransactionTemplate` invokes the transaction manager, executes the callback, and commits/rolls back according to its logic; by default it uses `REQUIRED` propagation. A callback throwing a `RuntimeException` normally rolls back the transaction. You can call `status.setRollbackOnly()` when intentionally aborting the transaction without throwing an exception.

**Do not** instantiate `new TransactionTemplate(new DataSourceTransactionManager(otherDataSource))` ad hoc when the application already has a manager for another resource: this can break the intended transaction boundary. Inject a properly configured manager/template and keep transactions inside the service.

## 13. Testing the Boundary Properly Instead of Only Testing Individual Repositories

A useful integration test suite must verify the database state **after the service transaction has finished**:

1. **Happy path:** debit, credit, and audit all appear together, and the amounts/counts for each operation are valid.
2. **Failure at the first/middle/last repository:** intentionally induce an error after each step and verify there are **no** partial updates.
3. **Constraints:** duplicate keys, negative inventory, non-existent accounts; exceptions propagate or roll back according to the rules.
4. **Checked exceptions:** explicitly test default commit/rollback behavior and `rollbackFor` if needed.
5. **Inner transactions:** test `REQUIRED` marking rollback-only, independent `REQUIRES_NEW`, and `NESTED` savepoints if used in the design.
6. **Concurrency:** run two contending operations on the same data, checking locks/isolation and optimistic versioning.
7. **Proper configuration:** test through the bean obtained from the Spring context using the real manager/DataSource and transaction proxy; testing objects instantiated directly with `new` is insufficient.

**Testing trap:** if the test itself is annotated with `@Transactional` and the test framework automatically rolls back at the end of the test, you may accidentally merge multiple service calls into a single test transaction. That does not prove the service has independent boundaries or commits properly in production. When verifying actual commit/rollback behavior, choose tests without an outer test transaction or explicitly end/inspect the transaction at the right point.

Example assertions for `TransferDemo`:

~~~text
Initial:        balance(A)=500, balance(B)=200, audit=0
After success:  balance(A)=400, balance(B)=300, audit=1
After simulated failure: balance(A)=400, balance(B)=300, audit=1
~~~

Unchanged balances after the second failure are the sign that all operations in the second scope rolled back; **it does not test all failure modes of the production driver/DB**. You must retest against the real database when deciding on isolation, pooling, and XA.

## 14. Common Mistakes

| Symptom | Common Cause | How to Verify and Fix |
|---|---|---|
| First repository committed, later repository failed | `@Transactional` only on individual repos, service opens no shared transaction | Place boundary on public service method; test failure at the last step |
| Annotation has no effect | Bean created via `new`, self-invocation, method not proxied | Obtain bean from Spring, call through proxy, test rollback |
| `UnexpectedRollbackException` on completion | Inner `REQUIRED` marked rollback-only while outer still tried to commit | Inspect root exception and transaction logs; redesign error handling |
| Audit still saved when transfer rolled back | Audit uses `REQUIRES_NEW` or separate DB/manager | Use `REQUIRED` if it must roll back together; or acknowledge intentional independence |
| DB A rolled back while DB B committed | Only using DB A's local transaction manager | Use proper coordination (JTA/XA or saga/outbox) |
| Checked exception thrown yet data committed | Default rollback rule excludes checked exceptions | Use `rollbackFor`, or configure appropriate default rollback rule |
| Service swallows exception and commits partially | `catch` suppresses error without marking rollback | Rethrow or call setRollbackOnly as appropriate |
| Async operation does not join transaction | Imperative transactions are thread-bound | Open explicit separate transaction in worker/task or design an outbox |
| Long-running transaction / connection exhaustion | HTTP calls, file processing, or holding locks in scope | Narrow scope; move side effects to post-commit |
| Inconsistent data under concurrent requests | Isolation/locking or SQL does not preserve invariants | Conditional update, versioning, locking, unique constraints |
| Integration test "passes" but production fails | Test runs inside an outer transaction or H2 differs from real DB | Test via proxy and against production DB with committed state |

## 15. Design Checklist for a Multi-Repository Use Case

Before writing code, answer in order:

1. **Which business steps must be all-or-nothing?** For example, transfer = debit + credit + audit; identify which changes truly must commit together.
2. **Where is the boundary?** A public service method called by another bean via a Spring proxy is usually a good starting point.
3. **Which resources participate?** Same database, `DataSource`, `EntityManager`, and which transaction manager? Are any external APIs or brokers outside the local scope?
4. **Which propagation?** Default `REQUIRED`; use `REQUIRES_NEW` only when independence is genuinely wanted; do not accidentally detach audit/stock from the use case.
5. **Which failures must roll back?** Runtime, checked exceptions, business errors, caught exceptions; define rollback rules and error-return behavior.
6. **How is concurrency protected?** Conditional SQL, unique keys, locks/versioning, appropriate isolation, and whole-use-case retries.
7. **Are there slow tasks or non-DB side effects?** Move them outside the scope or use outbox/after-commit to avoid holding transactions open for long.
8. **Have committed and rolled-back states been tested?** Test via Spring bean, failures at each step, outer/nested transactions if any, and the production DB.

## 16. Hands-On Exercises

1. In `TransferDemo`, remove `@Transactional` from `TransferService.transfer`. Predict and verify the balances and audit count after the call that throws an exception; explain why the shared transaction is gone.
2. Reorder the operations to throw an error after `accounts.debit` but before `accounts.credit`. Write assertions for all accounts/audit rows to prove proper rollback.
3. Create another `AuditService` with `@Transactional(REQUIRES_NEW)`, call it through the bean proxy, and let the outer transaction roll back. Compare the surviving audit record against business requirements.
4. Add a custom checked exception, test default `@Transactional` and `@Transactional(rollbackFor = ...)`; compare the DB state after each run.
5. Have `transfer` call another `@Transactional` method via `this.method()` and compare with calling through a separate Spring bean; explain the impact of self-invocation.
6. Write an integration test with two concurrent transfer requests from the same account with limited balance. Ensure the total balance never goes negative and only valid transactions commit.

## References

- Spring Framework Reference — Declarative Transactions, Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework Reference — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Reference — Transaction Management Strategies: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Spring Framework Reference — Programmatic Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework Reference — JDBC Transaction Manager: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
