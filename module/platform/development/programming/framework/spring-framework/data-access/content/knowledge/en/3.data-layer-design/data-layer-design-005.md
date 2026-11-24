# Placing Transaction Boundaries on the Right Business Operation

> **Goal:** Identify where to begin and end a database transaction around a business operation (use case) so that related changes succeed or fail together; keep transactions sufficiently short; understand accurately how Spring Framework's `@Transactional` works; and verify rollback, commit, and concurrency behavior.

## 1. Transaction Boundaries Are a Business Design Decision

A **database transaction** is a unit of work against a database: on commit, changes within the transaction are confirmed; on rollback, they are undone according to the transactional capabilities of the database and participating resources. ACID properties cover atomicity, consistency, isolation, and durability. Transactions resolve consistency **within the scope of resources that the transaction manager actually manages**; they do not automatically cover HTTP calls, emails, message brokers, or separate independent databases.

A **business operation (use case)** is an action meaningful to users and business rules, such as "transfer money", "confirm order", or "cancel booking". One operation may read/write multiple tables through multiple repositories. An appropriate transaction boundary typically wraps **the database changes that must succeed together or fail together to preserve business invariants**.

Example: transferring 100,000 VND from account A to account B (omitting real-world payment intricacies):

1. Check A, B, and transfer conditions.
2. Debit A.
3. Credit B.
4. Save the transfer record.

If step 2 commits separately and step 3 then fails, money has left A without reaching B. Therefore, **steps 2–4 must reside in the same transaction** with appropriate balance/concurrency checks. Conversely, sending a notification email can happen *after commit*; keeping the email inside the transaction does not make sending an email rollback-capable.

Several concepts should not be conflated:

| Concept | Meaning | Example scope |
| --- | --- | --- |
| **Use case** | Business behavior and success criteria | `transferMoney`, `placeOrder` |
| **Transaction boundary** | Where a database transaction begins, joins, commits/rolls back | `@Transactional` on a service method |
| **Repository/DAO method** | A single data access operation | `debit`, `credit`, `insertLog` |
| **HTTP request** | Lifecycle of communication with a client | Receive input → service → build response |
| **Long-running workflow** | Extended sequence of steps, possibly across multiple systems | Payment → inventory → shipping |

**Do not assume one HTTP request = one transaction**, nor assume "every SQL statement/repository method = one transaction". Choose boundaries according to the consistency invariants you need to uphold.

## 2. Design Principle: One Business Operation, One Transaction Coordination Point

In a layered Spring application, the clearest organization is usually:

```text
Controller / Job / Message Handler
    | validate request syntax, authenticate, convert DTO
    v
Application Service / Use-case Service
    | @Transactional on the business operation method
    | coordinates multiple DAOs/Repositories
    +--------------------+-------------------+
    v                    v                   v
  AccountDao         OrderRepository     AuditRepository
    |                    |                   |
    +--------------------+-------------------+
                     |
            Same transaction manager
            and participating DB resources
                     |
                 Commit/Rollback
```

- **Controller** should stay thin and avoid holding a transaction while reading request bodies, serializing responses, or making network calls.
- **Application service** knows all the steps that must be atomic. Place `@Transactional` at the *public entry point* of the use case, usually on this service, so every data access call inside joins the same transaction.
- **Repository/DAO** focuses purely on statements/data mapping. Annotations on an individual repository can be useful, yet *cannot replace* a transaction spanning a multi-repository use case.
- **Domain object** holds invariant rules; it does not need to know how Spring opens/closes transactions. Domain validation and database constraints complement one another.
- One service can expose multiple use-case methods with different policies (writes, reads, or multi-stage workflows); do not blindly slap `@Transactional` onto every method just because it is "easy".

### How to Derive Boundaries from Requirements

Ask four questions before annotating:

1. **Which invariants must hold?** For example, `balance >= 0` and "record all of debit/credit/log or record nothing".
2. **Which changes must be atomic?** Only SQL statements targeting the same database, or also an external API? If there is an external API, design an additional coordination mechanism.
3. **What is the expected lock/connection hold time?** If there are HTTP calls, retries, heavy computation, or user waits, separate them from the short transaction.
4. **What is the real entry point?** HTTP controllers, scheduled jobs, message listeners, etc., must call a **Spring bean through its proxy** so the transaction advice gets a chance to run.

Start with the default `Propagation.REQUIRED` for synchronous use cases within a single datasource. Increase complexity only when a measurable requirement demands it.

## 3. Wrong vs. Right Boundaries: Money Transfer

### Wrong: Three Operations Committed Independently

```java
// Illustrates a design flaw; not a standalone runnable program.
public void transfer(long from, long to, long cents) {
    accountDao.debit(from, cents);    // May have already committed
    accountDao.credit(to, cents);     // What if an error occurs here?
    transferDao.save(from, to, cents);
}
```

Without an enclosing transaction, each JDBC operation may run in auto-commit mode or a repository may start its own transaction. A failure in one step does not undo already-committed steps. Putting `@Transactional` on each `debit`, `credit`, and `save` method separately **does not** create one transaction for the entire use case.

### Right: A Transaction Wrapping the Steps That Must Be Atomic

```java
@Service
public class TransferService {
    private final AccountDao accountDao;
    private final TransferDao transferDao;

    public TransferService(AccountDao accountDao, TransferDao transferDao) {
        this.accountDao = accountDao;
        this.transferDao = transferDao;
    }

    @Transactional
    public void transfer(long from, long to, long cents) {
        // Validate + lock/synchronize data appropriately for concurrency.
        accountDao.ensureTransferAllowed(from, to, cents);
        accountDao.debit(from, cents);
        accountDao.credit(to, cents);
        transferDao.save(from, to, cents);
    }
}
```

The snippet above is an **architectural illustration**, not a standalone compilable class: `ensureTransferAllowed`, `debit`, `credit`, and `save` are hypothetical DAO APIs. A runnable version in Section 5 includes full SQL, data validation, and simulated rollback failure.

When the call passes through the Spring transactional proxy, `TransactionInterceptor` uses `PlatformTransactionManager` to begin or join a transaction before running the method body; afterward it commits on success or rolls back according to the exception policy. With JDBC and the same `DataSource`, `JdbcTemplate` acquires the connection bound to the active transaction, so the DAOs share the same unit of work.

**Subtle point:** the transaction opens when the proxy receives the `transfer()` call and ends when the call returns/throws through the proxy. Annotating a private helper or calling an annotated method via `this.someMethod()` on the same object does not guarantee creating a transaction as expected.

## 4. When to Open, When to End?

| Scenario | Reasonable boundary | Explanation |
| --- | --- | --- |
| Create order and deduct stock in the same DB | Use case `placeOrder` wraps the writes that must be atomic | Cannot have a "placed" order while stock remains unadjusted by rule |
| Update a profile in a single table | Use-case-level transaction works; a single SQL statement is also DB-atomic | Do not open a transaction wider than needed |
| Read a report with multiple queries needing a consistent snapshot | Read-only transaction with appropriate isolation, if the business truly requires a snapshot | `readOnly` alone does not automatically create the desired snapshot |
| Fetch DB data then call a slow REST API | Finish the DB transaction before the network call whenever possible | Holding locks/connections while waiting on the network causes contention and timeouts |
| Receive funds from a payment gateway, then write DB | Split local steps and coordinate with idempotency, state machines/sagas/outbox | DB rollback cannot undo an external payment |
| Process a batch of 50,000 records | Chunk into batches with resume points and a defined rollback strategy | One giant transaction creates heavy log/lock/memory pressure |
| Send notification after order commits | Post-commit event; if guaranteed delivery is required, use transactional outbox | Email/messaging does not participate in database ACID |

**A transaction should be wide enough to preserve invariants, yet short enough to minimize lock and connection hold times.** Never automatically stretch a transaction across an entire HTTP request or a multi-minute workflow.

## 5. Complete Runnable Example with Spring JDBC and H2

The example uses **Java 17+, Maven, Spring Boot 3.5.16, Spring Framework transactions, `JdbcTemplate`, and H2**. Spring Data JPA is omitted to focus on transaction boundaries; the same principle of placing `@Transactional` on the use-case service still applies when using JPA.

Directory layout:

```text
transaction-boundary/
├── pom.xml
└── src/main/
    ├── java/com/example/tx/
    │   ├── DemoApplication.java
    │   ├── AccountDao.java
    │   └── TransferService.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

**`pom.xml`** — The JDBC starter provides `JdbcTemplate` and transaction integration; H2 serves as an embedded database for testing:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>transaction-boundary</artifactId>
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

**`src/main/resources/schema.sql`** — amounts are represented in the smallest unit (here integer cents for illustration), with non-negative constraints:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
);

CREATE TABLE transfer_log (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    from_id BIGINT NOT NULL,
    to_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0)
);
```

**`src/main/resources/data.sql`**:

```sql
INSERT INTO accounts (id, balance_cents) VALUES (1, 100000);
INSERT INTO accounts (id, balance_cents) VALUES (2, 50000);
```

**`src/main/resources/application.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

Spring Boot executes `schema.sql`/`data.sql` when initializing the datasource; demo data lives only in memory and reinitializes on each run. Use a migration tool, a real database, and full accounting design if taking this idea into production.

**`src/main/java/com/example/tx/AccountDao.java`** — simple SQL operations; never opens its own transactions:

```java
package com.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountDao {
    private final JdbcTemplate jdbc;

    public AccountDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long lockedBalance(long id) {
        Long balance = jdbc.queryForObject(
                "SELECT balance_cents FROM accounts WHERE id = ? FOR UPDATE",
                Long.class, id);
        if (balance == null) {
            throw new IllegalStateException("Missing account: " + id);
        }
        return balance;
    }

    public void changeBalance(long id, long delta) {
        int updated = jdbc.update(
                "UPDATE accounts SET balance_cents = balance_cents + ? " +
                "WHERE id = ?",
                delta, id);
        if (updated != 1) {
            throw new IllegalStateException("Missing account: " + id);
        }
    }

    public void recordTransfer(long fromId, long toId, long cents) {
        jdbc.update(
                "INSERT INTO transfer_log (from_id, to_id, amount_cents) " +
                "VALUES (?, ?, ?)",
                fromId, toId, cents);
    }

    public long balance(long id) {
        Long value = jdbc.queryForObject(
                "SELECT balance_cents FROM accounts WHERE id = ?",
                Long.class, id);
        if (value == null) {
            throw new IllegalStateException("Missing account: " + id);
        }
        return value;
    }

    public int transferCount() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM transfer_log", Integer.class);
        return count == null ? 0 : count;
    }
}
```

**`src/main/java/com/example/tx/TransferService.java`** — one transaction for debit, credit, and log; consistent lock ordering reduces deadlock risk when two transactions transfer in opposite directions:

```java
package com.example.tx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final AccountDao accounts;

    public TransferService(AccountDao accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId,
                         long amountCents, boolean simulateFailure) {
        if (fromId == toId || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        // Lock in ascending ID order to avoid lock-order inversion.
        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);
        long firstBalance = accounts.lockedBalance(firstId);
        long secondBalance = accounts.lockedBalance(secondId);

        long fromBalance = fromId == firstId
                ? firstBalance : secondBalance;
        if (fromBalance < amountCents) {
            throw new IllegalArgumentException("Insufficient balance");
        }

        accounts.changeBalance(fromId, -amountCents);

        // Failure simulation flag only present in this hands-on lesson.
        if (simulateFailure) {
            throw new IllegalStateException("Simulated failure");
        }

        accounts.changeBalance(toId, amountCents);
        accounts.recordTransfer(fromId, toId, amountCents);
    }
}
```

`SELECT ... FOR UPDATE` locks the account rows within the active transaction. Checking balances and writing after acquiring locks prevents two concurrent transfers from spending the same stale balance. With a real database, verify isolation levels, locking syntax, fairness, and deadlock retry strategies. Consistent lock ordering **reduces risk**, though it does not guarantee absolute immunity to deadlocks.

**`src/main/java/com/example/tx/DemoApplication.java`** — invokes the service bean from another bean so calls pass through the transaction proxy; reads state after each call finishes:

```java
package com.example.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, AccountDao accounts) {
        return args -> {
            try {
                service.transfer(1L, 2L, 10000L, true);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "rollback: " + accounts.balance(1L) + "," +
                        accounts.balance(2L) + "; log=" +
                        accounts.transferCount());
            }

            service.transfer(1L, 2L, 10000L, false);
            System.out.println(
                    "committed: " + accounts.balance(1L) + "," +
                    accounts.balance(2L) + "; log=" +
                    accounts.transferCount());
        };
    }
}
```

Run from the project directory containing `pom.xml`, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

The logs include **two lines printed by the application**, excluding Spring startup lines:

```text
rollback: 100000,50000; log=0
committed: 90000,60000; log=1
```

**Step-by-step explanation:**

1. The first run starts a transaction, locks both rows, debits A, and then intentionally throws `IllegalStateException`. The unchecked exception escapes the service method, so the proxy rolls back; A, B, and log remain unchanged.
2. The second run executes all three SQL statements and returns normally; the proxy commits once for the entire operation. A decreases by 10,000, B increases by 10,000, and the log gains one record.
3. Removing `@Transactional` from `transfer()` would allow the JDBC UPDATE to auto-commit before the simulated failure; that is precisely the flawed design this lesson seeks to avoid.

This example verifies the transaction path **within a single H2 datasource**. It is not a production banking design: it lacks business idempotency keys, authorization checks, duplicate-request protection, a proper double-entry ledger, tracing, overflow handling for huge amounts, safe retries, and verification against a real database.

## 6. How Does Spring Actually Open and Close a Transaction?

`@Transactional` is **metadata** for Spring AOP. In the imperative model, the interceptor uses `PlatformTransactionManager` (e.g., `JdbcTransactionManager`/`DataSourceTransactionManager` for JDBC or `JpaTransactionManager` for JPA) to manage resources. Annotation defaults:

| Attribute | Default | Practical meaning |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Opens a transaction if none exists; joins an existing compatible transaction |
| `isolation` | `DEFAULT` | Uses the default isolation level of the database/manager |
| `readOnly` | `false` | Read/write transaction |
| `timeout` | Per transaction manager | A timeout is not always enforced everywhere |
| Rollback | `RuntimeException` and `Error` | Checked exceptions do not trigger rollback by default |

Typical execution flow:

```text
Caller --> Spring proxy --> TransactionInterceptor
                                 |
                            begin / join
                                 |
                            service body
                                 |
                       +---------+----------+
                       |                    |
                    return            throw exception
                       |                    |
                   commit             rollback rules
                       |                    |
                       +---------+----------+
                                 |
                           Caller receives result
```

**Critical conditions:** Spring must manage the object as a bean, transaction management must be enabled, and an appropriate transaction manager must exist. With properly configured Spring Boot JDBC/JPA and a single datasource, the infrastructure is usually auto-configured; outside Boot, you may need `@EnableTransactionManagement` along with a transaction manager bean.

### Why Shouldn't You Place the Annotation Arbitrarily?

- **Self-invocation:** `this.transfer()` or a method in the same bean calling another annotated method bypasses the proxy under default proxy configuration. The clean pattern is for bean A to call a public annotated method on bean B.
- **Manually instantiated objects:** `new TransferService(…)` bypasses the Spring container, so annotations are not intercepted by Spring.
- **Private/final methods:** interception support depends on proxying; to be safe, choose **public methods on Spring-managed services** called from another bean. Avoid annotating private helpers and assuming a transaction is active.
- **Bean initialization:** do not rely on `@Transactional` for calls inside constructors or `@PostConstruct`; the proxy is not ready along those paths.
- **Other threads:** standard JDBC/JPA transactions are bound to the current thread; `new Thread`, `@Async`, and executors do not inherit transactions automatically. Reactive transactions propagate via the Reactor context and require a different design.
- **On Controllers:** tends to hold transactions open too long across web handling, remote calls, and serialization. Service-level use cases are usually a much stabler entry point for HTTP, jobs, and message listeners.

## 7. Propagation Decides Whether a Transaction Is Shared or Split

A `@Transactional` method A calls an annotated method B on **another Spring bean**:

| Propagation of B | What does B do when A already has a transaction? | When to consider |
| --- | --- | --- |
| `REQUIRED` (default) | B joins A's **physical transaction**; all steps are atomic with A | Child repositories/services within one use case |
| `REQUIRES_NEW` | Suspends A's transaction and starts an **independent physical transaction** for B | Rare cases deliberately requiring an independent step to commit/roll back |
| `NESTED` | Uses a savepoint within the same physical transaction when supported by manager/driver | Partial rollback with JDBC savepoints and explicit specifications |
| `MANDATORY` | Requires caller to already have a transaction; throws otherwise | Guarding an internal API that may only run inside a transaction |
| `SUPPORTS` | Joins if a transaction exists, runs non-transactionally otherwise | Context-dependent reads; rarely used as a primary boundary |

**Do not choose `REQUIRES_NEW` just to "be sure there is a transaction".** It can commit B's data even if A rolls back; moreover, the outer transaction still holds its connection/resources while the inner transaction needs a new connection, risking pool exhaustion. `NESTED` does not mean an independent commit: a partial savepoint rollback still lives inside the outer transaction.

Another trap: method B uses `REQUIRED` sharing A's transaction, and B marks it **rollback-only**. Even if A catches the exception and tries to commit, Spring may throw `UnexpectedRollbackException` because the transaction was actually rolled back. This is the right signal so callers do not mistakenly assume data committed.

## 8. Exceptions and Rollback Must Reflect Business Rules

By default, Spring rolls back on `RuntimeException` or `Error`; checked exceptions such as `IOException` normally **do not** trigger rollback under the default configuration. Example where a checked exception must undo all changes:

```java
// Illustrative snippet in a Spring-managed service; not a standalone file.
@Transactional(rollbackFor = IOException.class)
public void importAndSave(Path path) throws IOException {
    // Read file; if reading fails after writing to the database,
    // the escaping IOException will trigger rollback.
}
```

If business rules define *not* rolling back for a specific error, `noRollbackFor` can be used deliberately. Do not abuse `rollbackFor = Exception.class` or `noRollbackFor` to mask poorly designed business operations.

**Exception-swallowing trap:**

```java
@Transactional
public void placeOrder() {
    stockDao.reserve();
    try {
        orderDao.save();
    } catch (Exception ex) {
        log.warn("Cannot save order", ex); // If you only log and return,
                                           // the transaction may commit!
    }
}
```

This is **flawed code**: unless another mechanism marks the transaction rollback-only, the proxy sees the method return normally and can commit `reserve()`. When a failure must roll back the entire operation, let an appropriate exception escape; if handling in place is mandatory, use a deliberate rollback-only mechanism and understand its consequences.

Additionally:

- An exception thrown **after commit** cannot undo an already-completed transaction.
- Catching in a **controller outside the transactional service call** still lets the proxy process rollback before the controller catches the exception.
- `@Transactional(readOnly = true)` is a **hint**, not a database permission guaranteeing write prohibition. Use it for appropriate reads, while still relying on DB permissions and constraints to prevent writes.
- With Spring Framework 6.2+, you can configure default rollback for all exceptions via `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. If changing from the default rule, align across the entire project and test the effects.

## 9. Transactions Do Not Automatically Solve Concurrency

Atomicity does not replace isolation. Two transactions reading the same balance/stock before either completes can cause lost updates, overdrafts, or overselling without proper controls.

**Three common tools:**

1. **Database constraints:** `CHECK (balance_cents >= 0)`, `UNIQUE` for idempotency keys, foreign keys for integrity. This is the last line of defense, and application logic must still handle constraint failures.
2. **Pessimistic locking:** `SELECT ... FOR UPDATE` or `@Lock(PESSIMISTIC_WRITE)` with JPA; locks rows inside the transaction and rechecks conditions before modifying. Keep transactions short and lock in a consistent order.
3. **Optimistic locking:** `@Version` on JPA entities, or conditional updates like `UPDATE ... WHERE version = ?`; on conflict, fail or retry *the whole operation* when safe/idempotent.

For example, selling a product should never just run "SELECT stock" and then "UPDATE stock" in two separate transactions. One SQL-based concurrency control approach:

```sql
UPDATE products
SET stock = stock - :quantity
WHERE id = :productId
  AND stock >= :quantity;
```

After the UPDATE, check the affected row count: `1` means stock was reserved successfully; `0` means out of stock, missing product, or unmet condition. This is a SQL example **using named parameters** for `NamedParameterJdbcTemplate`; do not copy it verbatim for positional JDBC parameters. If the use case also inserts an order and reservation log, a transaction must still wrap all of those changes.

**Isolation levels** such as READ COMMITTED, REPEATABLE READ, or SERIALIZABLE behave differently across databases. Do not crank isolation up to the highest level out of habit; identify the specific anomaly to prevent and measure lock, retry, and throughput costs. Isolation/timeout attributes on an inner `REQUIRED` method normally cannot override an already-active outer transaction's settings.

## 10. Never Hold a Database Transaction Across Non-Database Steps

**Avoid doing this:**

```java
@Transactional
public void checkout() {
    orderDao.createPendingOrder();
    paymentGateway.chargeCard();    // Network call may take several seconds.
    orderDao.markPaid();
    emailClient.sendReceipt();       // Email does not roll back with the DB.
}
```

The code above **illustrates a risky design** with hypothetical DAOs/clients. If payment succeeds in the external system but `markPaid()` or the DB commit fails, rollback cannot refund the payment. Meanwhile, the transaction holds connections/locks while waiting on the payment gateway and email server.

Separate *local transactions* from *distributed workflows* using stateful steps:

1. Write a `PENDING` order and request/idempotency key to the DB in a short local transaction.
2. Call the payment gateway outside the transaction or via a worker; use the idempotency key for safe retries per gateway API rules.
3. Upon receiving the result/webhook, open a **new transaction** to transition the order state with valid preconditions and write an event/outbox record.
4. Dispatch notifications from the outbox via a post-commit worker with retries and deduplication.

The **transactional outbox** stores the event record in the same transaction as business state in the *same DB*, so either both state and event exist or both roll back. A worker publishes events afterward; consumers must be idempotent because delivery can repeat. `@TransactionalEventListener(phase = AFTER_COMMIT)` works for side effects not needing strong delivery guarantees, yet **does not** create a durable queue: a process crash after commit can still lose the notification.

Across multiple databases, message brokers, or microservices, a plain `@Transactional` annotation **does not create a cross-system ACID transaction**. Design sagas, compensations, outbox/inbox patterns, or distributed transactions when the infrastructure and requirements genuinely warrant them.

## 11. Common Mistakes When Choosing Boundaries

1. **Annotating only individual repositories:** each individual call is safe, yet the overall use case can partially commit.
2. **Annotating the entire controller/request:** long transactions holding connections/locks while waiting on the network or rendering responses.
3. **Annotating private methods / self-calls:** proxies do not run transaction advice as expected.
4. **Catching exceptions and returning success:** earlier writes can commit while the caller thinks the use case succeeded.
5. **Assuming checked exceptions roll back by default:** configure rollback rules or project-wide defaults explicitly.
6. **Using `REQUIRES_NEW` indiscriminately:** accidentally creates independent commits and exhausts the connection pool.
7. **Treating `readOnly` as a security control:** it is only a hint, not a substitute for DB privileges.
8. **Reading then writing without locks/versions:** races can still occur inside a transaction; use constraints, locking, or optimistic concurrency.
9. **Doing DB work then sending HTTP/email inside the transaction:** high latency and non-rollbackable side effects.
10. **Assuming one database transaction covers multiple datasources:** the transaction manager must actually manage all participating resources; a local manager does not synchronize multiple systems.
11. **Annotating tests with `@Transactional` and thinking commits were tested:** test transactions usually roll back at the end of each test, hiding real production boundary bugs.
12. **Wrapping a giant batch in a single transaction:** hard to retry and holds locks too long; design checkpoints/idempotency and chunked transactions where appropriate.

## 12. Verifying via Tests and Production Observability

A sound design should be verified with deliberate failures and real data, not by glancing at annotations:

- **Happy path:** all use-case changes commit, and results match expected balances, stock, or order states.
- **Mid-way failure:** after the first operation, intentionally throw an unchecked exception; confirm *all* related tables remain untouched and intended audit/outbox records also roll back.
- **Checked exceptions:** explicitly test the chosen rollback/commit policy, especially if `rollbackFor` is set.
- **Concurrency:** run multiple genuinely independent transactions contending for the same resource; confirm constraints/locking or retries produce valid outcomes.
- **Missing transaction:** if code requires an active transaction, verify callers go through the proxy; test the real service bean through the Spring container.
- **Remote side effects:** simulate timeouts or payment success followed by DB commit failure; verify idempotency, reconciliation, and compensation.
- **Observability:** log SQL and transactions in test environments; measure transaction duration, connection pool wait times, deadlocks, and lock timeouts; distinguish DB failures from remote failures.

In `@SpringBootTest` integration tests, avoid placing `@Transactional` on the test itself where it could accidentally wrap calls in an outer transaction and mask the service's real commit behavior. Instead, use non-transactional tests, explicitly reset data before each test, and inspect database state **after the service method finishes**. For isolation bugs, test against a database engine close to production; H2 is suited only for foundational demos.

## 13. Short Checklist Before Adding `@Transactional`

- [ ] I have defined the **business invariants** and which steps must be all-or-nothing.
- [ ] The boundary sits at the **use-case entry point** managed by Spring and called through a proxy.
- [ ] Related JDBC/JPA operations use the matching transaction manager and datasource.
- [ ] The transaction does not wrap unnecessary network I/O, user waits, or long CPU work.
- [ ] Rollback rules for checked/unchecked exceptions match business rules; errors are not swallowed.
- [ ] Race-condition protections (constraints/locks/versions/idempotency) are in place as required.
- [ ] I understand propagation consequences, especially how `REQUIRES_NEW` differs from `REQUIRED`.
- [ ] Non-DB side effects are handled post-commit/outbox/saga as appropriate.
- [ ] Tests cover mid-way rollback, successful commit, and concurrency contention.

## 14. Self-Check

**Question 1:** A use case creates an `Order`, decrements `Stock`, and writes an `OrderEvent` into the same DB. Where should the annotation go?  
**Answer:** Usually on the public service method orchestrating all three steps; if using an outbox, the event must be written in the same transaction.

**Question 2:** A `@Transactional` service calls an email-sending API and then throws `RuntimeException`. Is the email rolled back?  
**Answer:** No; a database transaction cannot undo an email protocol send. Handle notifications/events after commit, or use an outbox if durability is needed.

**Question 3:** `A.method1()` calls `this.method2()`; `method2` is annotated with `@Transactional`. Is a transaction guaranteed to open?  
**Answer:** Not in default proxy mode; internal calls bypass the proxy. Place the annotation on the real public entry point, or move the transactional method to another bean.

**Question 4:** A and B use `REQUIRED`. B marks the transaction rollback-only; A catches the error and returns normally. Will it definitely commit?  
**Answer:** No; the shared physical transaction was already marked rollback-only, and Spring may throw `UnexpectedRollbackException` at the outer boundary.

**Question 5:** Two concurrent requests deduct stock by running SELECT first and UPDATE second. Does merely adding `@Transactional` stop overselling?  
**Answer:** Not necessarily; you must control concurrency with locking/conditional UPDATEs, versioning, or an appropriate isolation level and constraints.

## Official References

- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot — Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html
- Spring Boot 3.5 — SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html

**Remember:** "One consistency-requiring use case" typically maps to **one local transaction wrapping the DB changes that must be atomic**, opened at the **application service** and closed promptly once data work finishes. You must also design **concurrency, rollback rules, propagation, and non-DB side effects**; `@Transactional` alone does not solve those concerns.