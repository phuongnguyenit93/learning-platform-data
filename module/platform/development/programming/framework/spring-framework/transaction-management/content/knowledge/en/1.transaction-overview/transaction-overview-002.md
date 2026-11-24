# Transaction Boundaries and a Business Unit of Work

## 1. Learning objectives

After this lesson, you will be able to:

- Identify a **business unit of work**: a set of changes that must succeed together or fail together to preserve business rules.
- Choose a **transaction boundary**: where a data transaction starts, participates, and ends.
- Place `@Transactional` in the right layer in Spring Framework and explain when commit/rollback actually occurs.
- Distinguish the atomicity of a database transaction from a workflow spanning multiple systems; recognize bugs caused by making transactions too small or holding them too long.
- Verify the boundary with one success scenario and one failure scenario with rollback.

This lesson focuses on boundary design and does not aim to cover the full isolation API, transaction propagation options, or distributed transaction models in depth.

## 2. What is a business unit of work?

A single user request often involves multiple technical operations while expressing **one business intent**. For example, transferring 100 currency units from account A to B may require:

1. Validating the amount and accounts.
2. Subtracting 100 from A, ensuring A does not go negative.
3. Adding 100 to B.
4. Recording a transfer history entry.

If step 2 succeeds while step 3 or 4 fails, the system must not let money "disappear" or leave an incomplete transfer behind. Therefore, if all four changes reside in the **same transaction-capable database**, they typically form one unit of work requiring an atomic commit.

A **business unit of work** is how we group changes around a meaningful business outcome. A **database transaction** is the technical mechanism that can enforce the atomicity of that group of changes within a given transactional resource scope.

| Concept | Question to answer | Transfer example |
| --- | --- | --- |
| Business operation / use case | What outcome does the user want to achieve? | Transfer money A → B |
| Business invariant | Which condition must always hold in committed state? | Non-negative balances; total funds conserved when there are no fees |
| Unit of work | Which changes must succeed together? | Debit, credit, history record |
| Transaction boundary | From where to where does the DB mechanism wrap the changes? | From when the service begins the transaction until all DB operations finish |
| Commit / rollback | What is the technical outcome of the transaction? | Persisting all changes durably or discarding all changes within the transaction scope |

Do not assume that one HTTP request equals one transaction: a request might be read-only, might contain multiple independent steps, or might coordinate a workflow lasting several minutes. Conversely, a single business operation might be triggered from HTTP, a scheduled job, a message consumer, or a CLI while sharing one meaningful application service method.

### Atomicity and consistency

In ACID, **Atomicity** states that changes belonging to a transaction are committed together or rolled back together. **Consistency** requires that the post-commit state satisfy designed constraints, such as primary keys, foreign keys, `CHECK` constraints, balance conditions, and business rules. A transaction does not invent valid rules on its own: developers must still validate business logic and apply appropriate constraints.

**Isolation** is a separate concern: two concurrent transactions can affect each other. Wrapping code in a transaction does not mean every race condition disappears automatically. **Durability** is guaranteed by the database according to its configuration and storage commitments. A sensible boundary achieves atomicity; correctness under concurrency also requires locking, conditional updates, versioning, appropriate isolation, and sometimes retries.

## 3. Where to place boundaries in a Spring application?

A common design for imperative applications with JDBC/JPA:

```text
HTTP / Message / Job
       |
       v
Controller / Adapter  -- maps request, authenticates, returns response
       |
       v
Application Service  -- coordinates one use case; @Transactional
       |
       +--> Repository A  -- reads/writes data
       +--> Repository B  -- reads/writes data
       +--> Repository C  -- reads/writes data
       |
       v
Commit if completed; roll back if an error matches transaction rules
```

The boundary is a **business decision at the service layer**, not simply annotating every repository with `@Transactional`. A service method such as `transferMoney`, `placeOrder`, or `confirmReservation` clearly expresses the "start/end" of a consistent state transition.

- **Too narrow:** each repository commits on its own before the service finishes; the second operation fails while the first is already persisted.
- **Too wide:** wrapping HTTP calls, sending emails, waiting for user input, or long computations; connections and locks are held too long, increasing contention/timeouts and deadlock risk.
- **Balanced:** cheap input validation can run beforehand; reads/writes requiring consistency stay inside the transaction; results or events to external systems are handled with an appropriate post-commit mechanism.

For example, placing an order in **one DB** might require saving the order, order lines, inventory deduction, and an outbox record in the same transaction. However, sending an email or calling a payment gateway does not automatically roll back with that transaction.

### "One use case = one transaction" is only a starting point

It is a useful heuristic for short operations using a single database. Do not force a workflow spanning multiple services, independent databases, multiple interaction turns, or hours of execution into a single transaction. Such workflows need to be broken into durable, stateful steps with recoverability, idempotency, and compensating actions where appropriate.

## 4. How does Spring implement this boundary?

With **imperative transactions** and the default proxy-based configuration, Spring intercepts calls from external beans to `@Transactional` methods. `TransactionInterceptor` coordinates with `PlatformTransactionManager`:

1. Determine whether an existing transaction is active and evaluate the propagation rule.
2. If needed, open a physical transaction on the data resource, or join the existing transaction.
3. Invoke the method body.
4. When the method completes, commit or roll back based on transaction status and exception rules.
5. Clean up thread-bound resources/synchronizations.

With JDBC and a single `DataSource`, `JdbcTemplate` uses the Spring-managed connection, so multiple SQL statements in the same transaction participate in the same transaction. With JPA, Spring can manage the `EntityManager` and synchronize changes to the transaction via flush/commit. The crucial point is that **reads/writes must actually share the same resource and transaction manager**; two independent connections or two separate transaction managers do not become a single atomic transaction just by sharing a method name.

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
    public void placeOrder(OrderRequest request) {
        inventory.reserve(request.items());
        orders.save(request);
    }
}
```

The snippet above is an **architectural illustration**, not a standalone program: the `OrderRepository`, `InventoryRepository`, and `OrderRequest` types are application-defined. If both repositories use the same compatible transaction manager, a runtime error in `orders.save` rolls back the DB changes made by `inventory.reserve`. If `inventory.reserve` actually makes an HTTP call to another system, that conclusion no longer holds.

**Important defaults of `@Transactional` in Spring Framework 6.x**:

- `propagation = REQUIRED`: joins an existing transaction; creates a new one if none exists.
- `isolation = DEFAULT`: follows the resource's default isolation level.
- `readOnly = false`; `timeout` follows the transaction system default (or none if unsupported).
- `RuntimeException` and `Error` roll back by default; a **checked exception** normally does not trigger rollback unless configured, e.g. `@Transactional(rollbackFor = IOException.class)`.
- In proxy mode, only calls **from another bean going through the proxy** trigger the advice. Calling `this.otherTransactionalMethod()` within the same object does not create a new transaction boundary.

Context affects decisions: `REQUIRES_NEW` creates an independent physical transaction that can commit even if the outer transaction rolls back; `NESTED` uses savepoints when supported by the transaction manager and resource. Do not use those two modes as a patch for a service with a flawed boundary. `readOnly = true` is an optimization signal/hint to the corresponding tools and drivers, **not** an absolute data-write protection mechanism. Imperative transactions are bound to the execution thread and do not automatically propagate to `@Async` or newly spawned threads. Reactive applications use a different context mechanism.

## 5. Runnable example: money transfer with Spring Boot, JDBC, and H2

This small example uses only **one H2 database** and integer balances for easy inspection; real monetary systems require smallest currency units or appropriate decimal types, validation, concurrency rules, and full auditing. The goal is to demonstrate transaction boundaries.

Project structure:

```text
transaction-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/transactions/
    │   ├── TransferApplication.java
    │   └── TransferService.java
    └── resources/
        ├── schema.sql
        └── data.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-boundary-demo'
```

**`build.gradle`** — uses Java 17 and Spring Boot 3.3.13 to reproduce the example; Gradle 8.x, JDK 17+.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance INT NOT NULL CHECK (balance >= 0)
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO account (id, balance) VALUES (1, 500), (2, 100);
```

Spring Boot executes `schema.sql` and `data.sql` by default with in-memory H2. No web server or controller is needed for this experiment.

**`src/main/java/demo/transactions/TransferService.java`**

```java
package demo.transactions;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, int amount, boolean failForDemo) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer request");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Source does not exist or has insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Destination does not exist");
        }

        // Failure occurs after BOTH UPDATE statements, before commit.
        if (failForDemo) {
            throw new IllegalStateException("Simulated failure after updates");
        }
    }
}
```

Both `jdbc.update` calls participate in the transaction created by the proxy when another bean calls `transfer`. The `balance >= ?` condition in the `UPDATE` statement is an important guardrail against overdrafts under concurrency; proper update/lock ordering and retries are still needed for real workloads. Do not use the `failForDemo` parameter in real business APIs: it only demonstrates rollback.

**`src/main/java/demo/transactions/TransferApplication.java`**

```java
package demo.transactions;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransferApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransferApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, JdbcTemplate jdbc) {
        return args -> {
            service.transfer(1L, 2L, 100, false);
            show("After successful transfer", jdbc);

            try {
                service.transfer(1L, 2L, 50, true);
            } catch (IllegalStateException ex) {
                System.out.println("Simulated error: " + ex.getMessage());
            }

            show("After rollback", jdbc);
        };
    }

    private static void show(String label, JdbcTemplate jdbc) {
        Integer balanceA = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 1", Integer.class
        );
        Integer balanceB = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 2", Integer.class
        );
        System.out.printf("%s: A=%d, B=%d%n", label, balanceA, balanceB);
    }
}
```

Run from the project directory using an installed Gradle 8.x:

```bash
gradle bootRun
```

Or use `./gradlew bootRun` if the project already has the Gradle Wrapper. Ignoring Spring Boot startup logs, the **three lines printed by the program itself** must be:

```text
After successful transfer: A=400, B=200
Simulated error: Simulated failure after updates
After rollback: A=400, B=200
```

Analysis of the output:

1. Initially A=500, B=100. The first call subtracts 100, adds 100, and returns normally; Spring commits, and the balances become 400/200.
2. The second call subtracts 50 and adds 50 inside the transaction, then throws `IllegalStateException` before commit. Because this is a `RuntimeException`, Spring rolls back both `UPDATE` statements. The balances remain 400/200.
3. The `catch` block sits in the **external calling bean** and catches the exception only after `transfer` has exited through the proxy, so it does not disable rollback. Swallowing the exception **inside** the transactional method and returning normally can cause Spring to commit unless the transaction has been marked rollback-only.

### Try the broken variant to observe a broken boundary

Remove `@Transactional` from `TransferService.transfer` and re-run the project with a freshly initialized H2 database. When each update runs independently under the connection's auto-commit mode, both `UPDATE` statements in the failing call may already commit before the exception is thrown. The result can now be A=350, B=250 even though the business operation reported an error. This proves that an exception **by itself is not a mechanism to roll back already-committed DB operations**.

Worse variant: without a transaction, if the second statement fails after the first has committed, A is debited while B is never credited, violating the invariant. The runnable example above keeps the Spring setup intact so the difference can be observed clearly; when re-testing, always initialize a fresh DB to avoid reusing stale state.

## 6. Common transaction cut points

### 6.1. Place at the orchestrating service, not in the controller

Controllers should focus on protocol handling, authentication, parsing/validation, and returning responses. Calling multiple repositories directly from a controller where each repository runs its own transaction easily fragments the use case. A service named after the business intent clearly expresses the boundary and can be reused when an endpoint becomes a scheduled job or message consumer.

A repository may still have its own transaction in standalone APIs; the issue is not "repositories must never have `@Transactional`", but **do not let it accidentally commit parts that the use case needs to roll back together**. With `REQUIRED`, repositories normally participate in the transaction opened by the service.

### 6.2. Do not wrap non-DB I/O in a long-running transaction

If a service writes to the DB and holds the connection open while calling an external API, two risks occur simultaneously: the transaction holds resources/locks for a long time, and the external API is **not** part of the DB rollback. Sending an email successfully followed by a DB rollback does not "unsend" the email. Charging a payment followed by a DB rollback does not automatically refund the payment.

You can write business data **and an outbox record** in one transaction, then use a worker after commit to read the outbox and publish messages; the receiving side must handle duplicates/idempotency because delivery can repeat. For cross-service operations requiring long-running coordination, consider workflows/sagas and compensating steps; that is not a single local ACID transaction.

### 6.3. Concurrency and locking are part of the design

In a transfer, if two requests simultaneously read A=100 and both decide to withdraw 80, simply doing "read → check → update" without an appropriate concurrency mechanism can cause lost updates or violate business rules. `UPDATE ... WHERE balance >= ?` checks and debits within the same update operation; `CHECK (balance >= 0)` provides a DB-level safeguard. Complex domains may require optimistic locking with a version column, pessimistic locking, or higher isolation levels. Transactions must still handle deadlocks/serialization failures and only retry when operations can be safely repeated.

### 6.4. Error handling must match rollback intent

- Throwing a `RuntimeException` out of a `@Transactional` method normally requests rollback by default.
- A checked exception requires an explicit rollback rule: `@Transactional(rollbackFor = SomeCheckedException.class)` if the operation must be aborted.
- If a `try/catch` catches an error and **does not rethrow** or mark rollback-only, Spring may treat the method as successful and commit. When a business failure should not throw an exception, explicitly decide whether the transaction may still commit or must roll back.
- An inner `REQUIRED` scope marked rollback-only can cause the outer scope to receive `UnexpectedRollbackException` upon trying to commit; do not misinterpret this as "Spring randomly ignoring the transaction."

### 6.5. Proxies and actual call flow

`@Transactional` on a method only takes effect when the transaction advice actually runs. In default proxy mode, `this.transfer(...)` called from another method of the same bean bypasses the proxy. Similarly, calling a method on an object created with `new` that Spring does not manage has no proxy. The practical approach is to place the use case in a Spring bean and invoke it through the injected bean; never rely on self-invocation expecting propagation changes. Imperative transactions do not automatically carry over to another thread.

## 7. How to decide boundaries: scenario table

| Scenario | Appropriate boundary | Reason |
| --- | --- | --- |
| Creating an order and order lines in the same DB | One transaction at `OrderService.placeOrder` | Prevents "half-created orders" |
| Transferring money between two rows in the same DB | One transaction at `TransferService.transfer` | Debit/credit require atomicity |
| Reading a list page without updating data | Can use a `readOnly` read scope if consistency/snapshot is needed | Not every HTTP GET requires a long transaction |
| Calling a payment gateway and saving an order | Split steps with state, outbox/workflow, and idempotency | A local DB transaction does not control external resources |
| Importing one million rows from a file | Chunked transactions with appropriate checkpoints | One giant transaction holds locks and logs for far too long |
| Writing an audit log in an independent transaction even if the business operation fails | Consider `REQUIRES_NEW` only when audit requirements explicitly demand it | Audit transaction can commit while outer transaction rolls back; account for connection pool sizing |

A pragmatic rule: **open the transaction as late as possible but before the first change requiring consistency; close it as early as possible after the last change requiring an atomic commit**. Never split between steps that an invariant requires to succeed together.

## 8. Testing the right boundary

Do not only test that "the service throws an error"; verify the **DB state after the error**. For the transfer example:

1. Seed two accounts with known balances and call the service through a real Spring bean.
2. Success case: assert that the source balance decreases and target balance increases by the exact amount; total remains unchanged.
3. Failure case after writing: assert the exception and assert that **both balances remain unchanged**.
4. Insufficient funds case: assert that neither account was updated.
5. Concurrent requests case: assert no negative balances and no lost funds; if the DB reports deadlocks/conflicts, verify the appropriate retry policy.
6. If changing propagation, transaction manager, or adding non-DB I/O, add tests covering the new boundaries.

**Note when writing tests with Spring:** test methods annotated with `@Transactional` are typically rolled back automatically by Spring TestContext after each test. While useful for data isolation, this can mask design flaws if you only inspect data **inside** the test's transaction. For real commit/rollback tests, manage the test transaction explicitly and read state after the service scope completes; never treat test auto-rollback as proof that the service rolls back properly.

## 9. Design checklist and common mistakes

Before adding `@Transactional`, ask yourself:

- What single business outcome must be guaranteed? Which invariant would break if one step committed alone?
- Do the changes actually belong to the **same transactional resource**? Are there emails, HTTP calls, queues, or other DBs outside it?
- Which method represents one use case and is invoked through a Spring proxy? Is there any self-invocation or new thread?
- Are any exceptions thrown that should trigger rollback but do not by default (checked exceptions or swallowed errors)?
- Are there locks, constraints, versions, or conditional updates protecting invariants against concurrent access?
- Does the transaction hold resources while waiting on network I/O, sleep, heavy computation, or user interaction?
- Is there a test that triggers a failure **between write steps**, then verifies the DB state by reading back after rollback?

Misconceptions to avoid: "every query is a transaction", "every request is a transaction", "`@Transactional` guarantees there are no race conditions", "external API calls also roll back", "catching an exception and returning still rolls back automatically", and "putting the annotation on a private method or calling it within the same bean always works".

## 10. Self-check

**Question 1.** In a use case saving an order and its line items in the same DB, should each repository commit independently? **Answer:** No, if invariants require them to succeed together; place the transaction around the use case in the service.

**Question 2.** A service deducts inventory in the DB, sends an email successfully, and then throws an exception. Does `@Transactional` recall the email? **Answer:** No; the DB can roll back, but the email is a side effect outside the DB. Choose an appropriate time to send, use an after-commit event if that reliability level is acceptable, or use a transactional outbox when reliable delivery is required.

**Question 3.** Calling `this.inner()` from `outer()`, where `inner()` has `@Transactional(propagation = REQUIRES_NEW)`—is a new transaction guaranteed? **Answer:** No, under default proxy mode; internal calls are not intercepted by the proxy.

**Question 4.** Can a transaction prevent all lost updates simply by wrapping multiple SQL statements? **Answer:** No. You must consider isolation, read/modify/write patterns, DB constraints, locking, or optimistic versioning.

**Question 5.** If an exception occurs in a service yet balances still change afterward, what should you check first? **Answer:** Was the service called through a Spring proxy, is there an appropriate transaction manager, did the exception escape past the interceptor and match rollback rules, do the repositories share the same transaction, or did the DB already auto-commit earlier?

## Reference documentation

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot — Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html

**Takeaway:** A business unit of work defines **what must be true upon completion**. The transaction boundary is the technical decision to realize atomicity over managed resources. Choose boundaries based on invariants and real resources, then prove them with rollback tests.