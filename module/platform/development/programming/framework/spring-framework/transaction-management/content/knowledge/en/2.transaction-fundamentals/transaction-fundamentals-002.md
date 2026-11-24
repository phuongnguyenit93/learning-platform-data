# Begin, Commit, Rollback, and Ending States of a Transaction in Spring Framework

## 1. Where does a transaction begin and end?

A **transaction** groups a set of operations on a transactional resource (usually a database) into a single unit of work: either valid changes are **committed**, or changes still within the transaction are **rolled back**. For example, transferring 200 units from account A to account B must debit A and credit B in the same transaction; doing only half is unacceptable.

In Spring, distinguish three layers:

| Layer | Role | What to remember |
| --- | --- | --- |
| Business call | Service method, JDBC/JPA data operations | Typically does not call SQL `BEGIN`/`COMMIT` directly |
| Spring transaction boundary | `@Transactional`, `TransactionTemplate`, or `PlatformTransactionManager` | Decides whether to create, join, commit, or roll back according to policy |
| Resource physical transaction | JDBC connection, JPA transaction, JTA... | The database/resource actually confirms or discards the changes |

A **logical transaction scope** is the transaction scope corresponding to a Spring method/callback. Multiple `PROPAGATION_REQUIRED` scopes can share **one physical transaction**; therefore, "the child method finished" does not necessarily mean the database has committed. Furthermore, a method annotated with `@Transactional` does not automatically start a new transaction: that depends on propagation and the current transaction.

Main assumption of this lesson: **imperative/synchronous** processing using `PlatformTransactionManager` and JDBC/JPA resources. For reactive flows, Spring uses `ReactiveTransactionManager` and Reactor Context; the thread-bound transaction mechanism described below does not apply verbatim.

## 2. Begin: entering a transaction

With `@Transactional` under the usual proxy mechanism, the standard flow is:

1. The caller invokes a **Spring bean through a proxy**; `TransactionInterceptor` reads attributes such as propagation, isolation, timeout, readOnly, and rollback rules.
2. The transaction manager receives the request (`getTransaction(TransactionDefinition)` in the imperative API) and **creates a new transaction, joins an existing transaction, or runs without a transaction** according to propagation.
3. When creating a physical JDBC transaction, the transaction manager obtains an appropriate connection, prepares supported attributes, and manages auto-commit; the database may start the transaction via its own mechanism. **Do not equate "begin" with Spring always sending a SQL `BEGIN` statement.**
4. Data operations execute within the resources bound to the transaction. When the method/callback leaves the scope, Spring decides whether to complete it or hand the decision to an outer scope.

`PROPAGATION_REQUIRED` (default) means: create one if no suitable transaction exists; join if one already exists. `REQUIRES_NEW` requires an independent physical transaction, suspending the outer transaction when the infrastructure supports it. `SUPPORTS` can run without a transaction; `NOT_SUPPORTED` intentionally does not participate in a transaction. Thus, calling `getTransaction` or running a `@Transactional` method is not proof that a new physical transaction was just opened.

To inspect from the imperative Spring API: `TransactionStatus.isNewTransaction()` indicates whether that scope opened a new transaction according to the manager; `TransactionStatus.hasSavepoint()` indicates a nested scope based on a savepoint (if present). These flags are for observation, not a substitute for verifying resource behavior.

## 3. Commit: confirming changes

When the business logic finishes **normally**, the transaction advice usually requests a commit. Conceptual sequence:

1. Spring checks whether the transaction has been marked **rollback-only**.
2. For a transaction eligible to commit, necessary synchronization/flush operations may occur before commit (depending on JDBC, JPA, Hibernate, and the transaction manager).
3. The transaction manager asks the resource to commit. Only when the resource confirms success can the physical transaction's changes be considered committed.
4. Spring runs appropriate completion callbacks and cleans up transaction state: releases/returns the connection, unbinds resources, and resumes any suspended transaction.

**Flush is not commit.** JPA/Hibernate may send SQL to the database during flush, yet the result can still be rolled back before commit. Foreign-key/unique constraints, deadlocks, timeouts, or connection errors can cause commit to fail; "the method reached the end" does not guarantee data is persisted permanently.

If a scope merely **joins** an existing `REQUIRED` transaction, its commit request does not perform a physical commit immediately: the outer transaction still holds the final decision. If the transaction was marked rollback-only, calling commit may lead to rollback; a typical case is `UnexpectedRollbackException` when the outer transaction tries to commit after an inner scope forced the shared transaction to roll back.

Do not equate an exception thrown from a method with "guaranteed rollback": if the rollback rule does not match (for instance, a checked exception by default), Spring may commit and still propagate the exception to the caller.

## 4. Rollback: discarding changes in the transaction scope

Rollback instructs the resource to discard **uncommitted** changes belonging to the physical transaction. For example, A was debited 200 but an error occurred before crediting B: rollback returns the participating records to their pre-transaction state. This does not reverse external side effects such as sent emails, HTTP calls, file writes, or another already-committed transaction; sequences/identities and DDL may also behave differently depending on the database.

Spring has two common paths:

- **Exception-driven rollback:** by default `@Transactional` rolls back when a `RuntimeException` or `Error` crosses the proxy-managed boundary. Checked `Exception`s normally **do not** trigger rollback by default; use `@Transactional(rollbackFor = IOException.class)` or an appropriate policy if business logic requires it.
- **Programmatic rollback decision:** code calls `TransactionStatus.setRollbackOnly()` or `PlatformTransactionManager.rollback(status)`. `setRollbackOnly()` only records the decision—it **does not roll back immediately at the call line**; the manager executes it when exiting the appropriate scope.

If code **catches and swallows** a `RuntimeException` inside a `@Transactional` method and returns normally, the proxy never sees that exception; the result may be a commit unless the code marks rollback-only or rethrows. Conversely, calling another annotated method **via `this.method()` inside the same bean** normally bypasses the proxy, so the annotation on the called method does not automatically create a new transaction boundary in proxy mode.

Note on manual rollback: calling `rollback(status)` on a scope that joined an outer transaction may only mark the shared transaction rollback-only; it cannot arbitrarily "undo only this method's part" when operations share a physical transaction. Partial rollback requires savepoints/`NESTED` if the driver and transaction manager support them.

## 5. States and ending outcomes

The diagram below depicts **control logic**, not a finite-state machine whose state names match every transaction manager's exact API.

~~~mermaid
flowchart TD
    A["Outside transaction"] --> B["Enter proxy / TransactionTemplate"]
    B --> C["Create new or join transaction"]
    C --> D["Execute business logic"]
    D --> E{"Normal return or exception?"}
    E -->|Normal| F{"Rollback-only?"}
    E -->|"Exception matching rollback rule"| R["Request rollback"]
    E -->|"Exception not matching rollback rule"| F
    F -->|No| M["Request commit"]
    F -->|Yes| R
    M --> S["COMMITTED when resource confirms"]
    M --> U["Commit failed / outcome may be unknown"]
    R --> T["ROLLED_BACK when rollback completes"]
    S --> X["Completion callbacks and cleanup"]
    U --> X
    T --> X
~~~

Easily confused concepts:

| Name/Flag | Correct meaning | What NOT to infer |
| --- | --- | --- |
| Inside scope | Business logic is executing within a managed boundary | There is definitely a **new physical transaction** |
| `status.isRollbackOnly()` | A request has been recorded not to commit normally | Rollback has already happened |
| `status.isCompleted()` | This `TransactionStatus` has finished (committed/rolled back at the manager-handled scope) | Certainty of whether the outcome was committed or rolled back; or for a joining scope, that the outer physical transaction has also finished |
| `status.isNewTransaction()` | The scope is treated by the manager as a new transaction | Every child method opens its own connection/transaction |
| `TransactionSynchronization.STATUS_COMMITTED` | `afterCompletion` callback received committed status | Can be used like an `isCommitted()` flag on `TransactionStatus` (the API has no such flag) |
| `TransactionSynchronization.STATUS_ROLLED_BACK` | Callback was notified of rollback | Automatically undoes effects outside the transaction |
| `TransactionSynchronization.STATUS_UNKNOWN` | Infrastructure could not definitively determine completion status in some cases | Can be assumed to be a successful rollback |

A completed `TransactionStatus` **must not** be reused to commit/roll back: repeated operations can lead to `IllegalTransactionStateException`. When `commit(status)` throws an exception, the transaction manager still must perform completion/cleanup; **do not call `rollback(status)` after a commit has already been attempted and threw an error**. Network errors during commit may require reconciling actual database state rather than concluding with certainty that it committed or rolled back.

Four scenarios to predict outcomes:

| Scenario | Default policy | Expected outcome |
| --- | --- | --- |
| Two UPDATEs succeed, method returns normally, not rollback-only | `REQUIRED`, new transaction | Both commit |
| First UPDATE succeeds, then `IllegalStateException` is thrown through proxy | `RuntimeException` triggers rollback | First UPDATE is not persisted |
| UPDATE succeeds, then checked `IOException` is thrown through proxy | No `rollbackFor` | May commit even though caller receives exception |
| Inner `REQUIRED` marks shared transaction rollback-only; outer catches exception and tries to commit | One shared physical transaction | Entire transaction rolls back; outer may receive `UnexpectedRollbackException` |

In the last row, `UnexpectedRollbackException` is a safeguard so the caller does not mistake a failed commit request for success. Do not write business code assuming every form of `setRollbackOnly()` necessarily throws an exception; differences in local/global markers and scope placement can vary how errors are reported.

## 6. Runnable example: demonstrating rollback and commit with H2

This Java 17+ example uses Spring Boot 3.3.x, Spring JDBC, and H2 **only to provide a minimal runnable environment**; the transaction principles belong to Spring Framework. The entire program runs with the three files below, without a web server. Both transfer calls go through a **Spring bean** so `@Transactional` actually applies.

**`pom.xml`**

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
    <artifactId>tx-lifecycle</artifactId>
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

**`src/main/java/example/TxApplication.java`**

~~~java
package example;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfers) {
        return args -> {
            jdbc.execute("CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 1000);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 500);

            System.out.println("Initial: " + balances(jdbc));
            try {
                transfers.transfer(1, 2, 200, true);
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }
            System.out.println("After rollback: " + balances(jdbc));

            transfers.transfer(1, 2, 200, false);
            System.out.println("After commit: " + balances(jdbc));
        };
    }

    private static Map<Integer, Integer> balances(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, balance FROM account ORDER BY id",
            rs -> {
                Map<Integer, Integer> result = new LinkedHashMap<>();
                while (rs.next()) {
                    result.put(rs.getInt("id"), rs.getInt("balance"));
                }
                return result;
            }
        );
    }
}
~~~

**`src/main/java/example/TransferService.java`**

~~~java
package example;

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
    public void transfer(int from, int to, int amount, boolean failAfterDebit) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("insufficient funds");
        }

        if (failAfterDebit) {
            throw new IllegalStateException("simulated-after-debit");
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("destination not found");
        }
    }
}
~~~

Run in the directory containing `pom.xml` (requires JDK 17+ and Maven):

~~~bash
mvn spring-boot:run
~~~

Lines **printed by the program** (excluding Spring startup logs):

~~~text
Initial: {1=1000, 2=500}
Caught: simulated-after-debit
After rollback: {1=1000, 2=500}
After commit: {1=800, 2=700}
~~~

Comparative explanation:

- In the first call, the debit executed inside the transaction, but an exception occurred **before the credit**. The proxy received `IllegalStateException` and requested a rollback; the debit was not committed.
- The `catch` in `CommandLineRunner` is **outside** the proxy call, so catching the exception there does not prevent Spring from rolling back. This differs from catching the exception directly inside `transfer` and returning normally.
- In the second call, both debit and credit completed; when `transfer` returned, Spring performed a commit. Both balances changed together.
- The three setup/initialization statements in the runner run outside the service transaction; they establish the initial state for both attempts and do **not** belong to `transfer`'s transaction.

You can set a breakpoint before the `throw` statement: an UPDATE statement has already been sent to the DB, yet observing after the proxy completes rollback still shows the old data. That is the essential difference between "SQL has run" and "transaction has committed."

## 7. Controlling begin/commit/rollback with Spring APIs

`@Transactional` fits typical service boundaries, while the APIs below clarify who decides completion.

**Recommended approach for imperative logic: `TransactionTemplate`.** The following is a **snippet inside a Spring bean that has `TransactionTemplate` and `JdbcTemplate`**, not a standalone runnable program:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - 100 WHERE id = 1");
    boolean businessRuleRejected = true;
    if (businessRuleRejected) {
        status.setRollbackOnly();
        return;
    }
    jdbc.update("UPDATE account SET balance = balance + 100 WHERE id = 2");
});
~~~

`TransactionTemplate` creates/joins a transaction when entering the callback and completes it automatically when the callback exits. `setRollbackOnly()` requests rollback of the scope even though the callback returns normally. In practice, business conditions should be validated appropriately (e.g. not debiting before confirming when possible), and operations must target the same transaction manager/resource.

**Use `PlatformTransactionManager` directly** when manual control is genuinely needed (snippet, assuming `work()` only throws unchecked exceptions):

~~~java
TransactionStatus status =
    txManager.getTransaction(new DefaultTransactionDefinition());

try {
    work();
} catch (RuntimeException | Error ex) {
    txManager.rollback(status);
    throw ex;
}

txManager.commit(status);
~~~

The three operations correspond to `getTransaction` (begin/join), `commit`, and `rollback`. **Place `commit` outside the business-error `try`** so you do not accidentally call rollback again if `commit` itself throws an exception. When checked exceptions need to be supported, adjust the catch/throw flow explicitly. The transaction manager owns the `TransactionStatus`; do not mix a status from one manager with another manager.

## 8. Impact of propagation on completion timing

Consider `outer()` calling `inner()` across **two Spring beans/proxies**, with transaction configuration:

| Propagation on `inner` | Transaction relationship | Commit/rollback meaning at `inner` |
| --- | --- | --- |
| `REQUIRED` | Same physical transaction as `outer` (if outer already has one) | Exiting inner scope **does not physically commit**; rollback-only can cause the entire outer transaction to roll back |
| `REQUIRES_NEW` | Independent physical transaction; outer is suspended | Inner commits/rolls back independently. Outer can later roll back without undoing inner's commit |
| `NESTED` | Usually same physical transaction with a savepoint | Inner can roll back to the savepoint; final physical commit outcome is still decided by outer, if supported by infrastructure |

Risk example: `inner(REQUIRED)` throws an error; outer catches it and wants to ignore it. If the shared transaction was already marked rollback-only, outer cannot commit "the remaining parts" merely by catching the exception. When outer commits, `UnexpectedRollbackException` may be thrown. Isolating the inner part requires designing proper transaction boundaries, not just adding `try/catch`.

`REQUIRES_NEW` typically needs an additional connection while outer holds its own; an undersized pool can cause resource-wait deadlocks. `NESTED` depends on savepoint support (common with JDBC) and cannot be assumed to work with every JPA/JTA manager.

## 9. Tracking post-commit/rollback status and side effects

If you need to run an action **after the database has committed**, you can use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or register a `TransactionSynchronization` when transaction synchronization is active. The `afterCompletion(int status)` callback distinguishes `STATUS_COMMITTED`, `STATUS_ROLLED_BACK`, and `STATUS_UNKNOWN`. With event mechanisms, understand when the event is published and that by default the listener does not run if there is no managed transaction (unless fallback is configured).

Do not send emails, publish messages without a shared transaction, or call external services and assume a database rollback will retract those side effects. If data and messages must stay consistent, consider **transactional outbox**: persist the intent to emit an event in the same database transaction, then forward it asynchronously after commit. This mechanism goes beyond the basic lifecycle, yet explains why "rollback" only has effect on resources genuinely participating in the transaction.

For commit errors where the application cannot determine the outcome (such as a dropped connection right during confirmation), observe using a business key/idempotency key and query status to reconcile. Do not blindly retry a monetary write without knowing whether it already committed.

## 10. Common mistakes and how to verify

1. **Putting `@Transactional` on a method and calling it internally via `this`.** In proxy mode, self-invocation bypasses the proxy; extract to another bean or redesign the call site.
2. **Assuming every exception triggers rollback.** By default checked exceptions do not roll back; inspect `rollbackFor`/`noRollbackFor` and where exceptions are caught.
3. **Catching an exception in the same method and returning.** If business logic requires discarding changes, rethrow or mark rollback-only intentionally.
4. **Assuming `save()`/`flush()` means commit.** Queries may have executed, yet the transaction is still awaiting completion; verify by reading data after the transaction ends.
5. **Calling `rollback(status)` after `commit(status)` throws.** The status is already completed/cleaned up; handle the error and reconcile rather than calling rollback again.
6. **Spawning work onto a new thread and expecting it to share the imperative transaction.** Typical JDBC/JPA transactions are bound to the executing thread; `@Async`, `new Thread(...)`, or off-thread tasks do not automatically inherit them.
7. **Confusing inner `REQUIRED` with an independent transaction.** Inner commit only finishes its own scope; the outer transaction decides the shared outcome.

Checklist for verifying a transaction flow:

- Are you certain the call goes through the right Spring bean/proxy and right transaction manager?
- Is `Propagation` creating a new transaction, joining, or running without one?
- What type is the exception, does it cross the proxy, and which rule applies?
- In which scope was rollback-only marked?
- After the **outermost boundary finishes**, what is the actual data in the DB?
- Are there external side effects or post-completion callbacks that must be coordinated separately?

**Self-check exercise:** In the H2 example, change the `failAfterDebit` branch to throw a checked exception declared on the service. Try without and with `@Transactional(rollbackFor = Exception.class)`, predict the two balances after each run, and then verify by reading from a connection outside the transaction. When modifying the example, keep the transaction going through the proxy and re-run on a cleanly initialized database.

## Official references

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Transaction abstraction and `PlatformTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Configuring `@Transactional` and rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Propagation `REQUIRED` / `REQUIRES_NEW` / `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
