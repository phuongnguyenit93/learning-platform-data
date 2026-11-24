# Choosing Propagation from Business Requirements Instead of Avoiding Configuration Errors

> **Spring Framework — Transaction Management → Other Propagation.** Choosing `@Transactional(propagation = ...)` is not about finding a way to make an exception disappear, nor tweaking parameters until the program "passes". Each propagation value is a **commitment about transaction boundaries**, directly impacting atomicity, data survival after rollback, data visibility, lock retention, and connection demand. This article presents a selection process based on **business requirements**, illustrates right/wrong decisions, and verifies them with a Java 17+ example.

## 1. Opening rule: ask about data outcomes before asking about annotations

Suppose an order-creation workflow has three steps:

1. Insert the order.
2. Deduct inventory quantity.
3. Write an audit record.

Before choosing propagation, you must answer these questions:

- If step 2 fails, must **both the order and inventory** return to their initial state together?
- Should the audit record be saved **only when the order succeeds** or saved **even if the order rolls back**?
- Does the audit need to reference **uncommitted** order data?
- Is a method allowed to run standalone, or **must the caller already have opened a transaction**?
- Should one failing sub-task be allowed to revert on its own **without aborting the entire** workflow?
- If there is no transaction, is the operation still safe/meaningful?

Those answers determine `REQUIRED`, `REQUIRES_NEW`, `NESTED`, `MANDATORY`, or another propagation. Without establishing those invariants first, changing propagation just because you saw `UnexpectedRollbackException` or "No existing transaction found" is an ungrounded decision.

**Stating the goal in business language:**

> "Order and inventory must commit or roll back together; a log of a payment attempt is retained even if the order fails; a balance update operation must never be called without an active transaction."

This statement is far more valuable than:

> "Set `REQUIRES_NEW` to avoid the rollback error" or "change `MANDATORY` to `REQUIRED` to stop the exception".

## 2. Two concepts to separate: logical scope and physical transaction

A call through a Spring proxy into a `@Transactional` method can create a **logical transaction scope**, yet does not always create a new **physical transaction**. This is the foundation for understanding propagation.

```text
Caller
  |
  +-- OrderService.placeOrder() @Transactional(REQUIRED)
  |       |
  |       +-- logical scope A
  |       |       physical transaction T1
  |       |
  |       +-- StockService.reserve() @Transactional(REQUIRED)
  |       |       logical scope B joins T1
  |       |
  |       +-- AuditService.recordAttempt() @Transactional(REQUIRES_NEW)
  |               |
  |               +-- logical scope C, separate physical transaction T2
  |                       T1 temporarily suspended (does not release locks by default)
  |
  +-- T1 completes after outer method returns
```

In the `REQUIRED` path, A and B have separate logical scopes, yet usually share **one physical transaction** when using the same manager and resource. Commit occurs at T1's boundary; inner B does not commit its part on its own.

In `REQUIRES_NEW`, C has an **independent T2**. C can commit and its data survives even if T1 later rolls back. Conversely, T2 can roll back while T1 continues when T2's error is handled properly. However, T2 needs its own resources—typically an extra JDBC connection—and does not automatically gain read access to T1's uncommitted data.

In `NESTED` (when supported by the manager), inner typically uses a **savepoint inside T1**. It is not an independent T2: if T1 rolls back, inner's data still rolls back.

**Key takeaway:** the physical transaction determines the real atomicity scope, not merely the count of `@Transactional` annotations in the call stack.

## 3. Seven propagation values: expressed as business commitments

`Propagation` lives in `org.springframework.transaction.annotation.Propagation`; Spring's default for `@Transactional` is `REQUIRED`.

| Propagation | When a compatible transaction already exists | When no transaction exists | Business question it helps answer |
| --- | --- | --- | --- |
| `REQUIRED` *(default)* | Joins the existing transaction | Opens a new transaction | "Does this work belong to the same all-or-nothing unit as the caller, while also being allowed as a standalone entry point?" |
| `REQUIRES_NEW` | Suspends outer transaction, opens a separate physical transaction | Opens a new transaction | "Is inner's outcome allowed to commit/roll back independently of the caller?" |
| `NESTED` | Creates a nested boundary/savepoint if manager supports | Usually opens a new transaction | "Allow rolling back a subset of operations and continuing outer **within the same physical transaction**?" |
| `SUPPORTS` | Joins the existing transaction | May run without an actual transaction | "Is this work still valid when the caller uses no transaction, yet can join if one exists?" |
| `MANDATORY` | Joins the existing transaction | Throws an error | "Is this method valid only when the caller owns the transaction boundary?" |
| `NOT_SUPPORTED` | Suspends outer transaction; runs without that manager's transaction | Executes without a transaction | "Must this block run outside the Spring-managed transaction?" |
| `NEVER` | Throws an error | Executes without a transaction | "Forbid calling this method when a transaction is active?" |

**Important caveat:** the table summarizes Spring propagation semantics. Suspension, savepoints, connection binding, transaction synchronization, isolation/read-only, and reactive/JTA/JPA support depend on the transaction manager and resources. `NESTED` is not guaranteed to work with every JPA provider. `SUPPORTS`/`NOT_SUPPORTED` do not mean all underlying I/O is safe or rollback-capable.

### 3.1. `REQUIRED` — should be the default for a shared atomicity unit

Example:

```java
@Transactional
public void createOrder(OrderRequest input) {
    orders.insert(input);
    stock.reserve(input.productId(), input.quantity());
}
```

Fragment: `orders`, `stock`, and `OrderRequest` are hypothetical application components. If both data writes must **commit together or roll back together**, making the outer service the transaction boundary and having inner operations join via `REQUIRED` is the sound model.

When no transaction exists, outer initiates one. When one already exists, outer can join the current transaction. That also means a higher caller can extend the scope, affecting how long connections/locks are held; boundaries must be designed sensibly.

### 3.2. `REQUIRES_NEW` — choose when true independent commit is required

For example, an audit that must record a failed **attempt**, not an audit asserting "the order succeeded":

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(long attemptId, String outcome) {
    auditRepository.insert(attemptId, outcome);
}
```

Fragment. If outer rolls back yet the audit record must still survive, transaction independence is a business requirement that can justify `REQUIRES_NEW`. Still, check that:

- The audit does not use a foreign key referencing an **uncommitted** outer order.
- The audit does not update the same row locked by outer.
- The connection pool has enough capacity while outer still holds resources.
- A failure to write the audit is handled/reported according to the business contract.
- The audit accurately states "attempted" or "encountered error", never misconstrued as "order committed".

If the audit must exist only when the order commits, usually **do not** use `REQUIRES_NEW` for that audit.

### 3.3. `NESTED` — choose for partial rollback and savepoints, not independent commits

A batch consisting of groups of operations may require "if a group fails, revert that group while other groups continue" inside **one physical transaction**:

```java
@Transactional(propagation = Propagation.NESTED)
public void importOneGroup(Group group) {
    // Can roll back to savepoint if this group's data is invalid.
}
```

Fragment assuming `Group`. With a manager supporting JDBC savepoints, a nested scope can roll back to the savepoint while outer continues. Yet if outer ultimately rolls back, **all changes inside the physical transaction** roll back.

Do not choose `NESTED` when the requirement is "once inner commits, it must remain even if outer rolls back". That is independent semantics, different from a nested savepoint.

### 3.4. `SUPPORTS` — when the operation is valid even without a transaction

An informational read function that does not require a consistent snapshot across multiple queries can run both inside and outside a transaction:

```java
@Transactional(propagation = Propagation.SUPPORTS, readOnly = true)
public ProductView findVisibleProduct(long id) {
    return repository.findVisible(id);
}
```

Fragment. `SUPPORTS` does not guarantee a physical transaction if the caller has none. Depending on the datasource/synchronization mechanism, a transaction synchronization scope may still exist; do not equate it with "always zero resource binding".

If a use case needs multiple SELECT statements to share a consistent snapshot/isolation, select an appropriate transaction boundary instead of blindly picking `SUPPORTS` just because the operation is a "read".

### 3.5. `MANDATORY` — turns "caller must open a transaction" into a runtime check

A helper modifying multiple tables is only valid inside a broader use case:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void applyAccountDelta(long accountId, long delta) {
    accountRepository.changeBalance(accountId, delta);
}
```

Fragment. `MANDATORY` throws an error if invoked through a proxy without a compatible transaction. This can be a **by-design guard**, not a bug to "fix" by switching to `REQUIRED` to make the exception go away.

If you change `MANDATORY` to `REQUIRED`, the helper can open and commit its own transaction when a caller forgets to open one, leaving outer business-layer operations non-atomic against requirements. Fix the caller's missing boundary first instead of removing the guard.

### 3.6. `NOT_SUPPORTED` — when running outside a transaction is genuinely needed

For example, a reference read outside the atomic unit where you do not want to occupy outer's transaction/resources:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public SystemHealthSnapshot gatherDiagnostics() {
    return diagnosticRepository.readSnapshot();
}
```

Fragment. If the caller has a transaction, the manager suspends that transaction and executes this block outside **the manager's managed transaction**. Depending on datasource/provider, non-transactional statements may auto-commit individually and see different data from outer's isolation snapshot.

Do not treat `NOT_SUPPORTED` as a "smaller transaction" or a way to guarantee independent commits. It has **no transaction of its own**; if code executes multiple SQL writes in auto-commit mode, part of them can commit before the next step fails.

### 3.7. `NEVER` — detects contract violations, not a performance optimization

```java
@Transactional(propagation = Propagation.NEVER)
public void requireNonTransactionalCall() {
    // An API allowed to be called only when there is no Spring-managed transaction.
}
```

Fragment. When a transaction exists, `NEVER` throws an error rather than proceeding. It fits when calling inside a transaction **violates architecture**, such as an API that must be orchestrated completely outside DB transaction boundaries. However, putting `NEVER` on every HTTP call does not automatically keep HTTP side effects and DB state consistent; proper orchestration design is still required.

## 4. Decision tree: choose by business invariant

```text
STEP A: Are there multiple changes that must commit/roll back together?
  |
  +-- YES ----------------------------------------------------+
  |                                                           |
  |   Can this work serve as a standalone tx entry point?     |
  |       +-- YES --> REQUIRED                                |
  |       +-- NO, caller MUST open tx --> MANDATORY           |
  |                                                           |
  +-- NO or special requirements -----------------------------+
                  |
                  v
       Must inner COMMIT independently, surviving outer rollback?
                  |
           +------+------+
           |             |
          YES           NO
           |             |
       REQUIRES_NEW      |
           |             v
           |     Need partial ROLLBACK via savepoint
           |     while staying inside outer physical tx?
           |             |
           |         +---+----+
           |         |        |
           |        YES      NO
           |         |        |
           |    NESTED*       v
           |             Is the operation valid without a transaction?
           |                +-- YES and may join if present --> SUPPORTS
           |                +-- YES but must stay outside ----> NOT_SUPPORTED
           |                +-- MUST NOT have a transaction --> NEVER
           |
           +-- Check pool, locks, data independence, retries

*NESTED only when transaction manager/resource supports savepoints.
```

A decision tree is a tool for asking the right questions, **not a substitute for review**. For instance, an activity that "does not strictly need shared atomicity" may still stay inside `REQUIRED` to reduce complexity, or be moved outside the transaction via orchestration rather than using `NOT_SUPPORTED`. What matters is that the reason is stated as a requirement and tested.

## 5. Mapping business requirements to propagation

| Scenario | Invariant to preserve | Usually suitable choice | What to watch out for |
| --- | --- | --- | --- |
| Create order + deduct stock | Succeed together or roll back together | `REQUIRED` | Same manager/resource; rollback rules; may need isolation/locking to prevent overselling |
| Balance updates in money transfer | Must never commit half of a transfer | Outer `REQUIRED`; `MANDATORY` helper to enforce caller | Switching helper to `REQUIRES_NEW` can cause mismatched balances |
| Save "attempt failed" audit even if order rolls back | Audit survives independently | `REQUIRES_NEW`, or a reliable independent recording channel | Do not reference outer's uncommitted rows; pool and lock contention |
| Store "order committed" event | Never emit event for uncommitted order | Outbox in same `REQUIRED`, publisher after commit | `REQUIRES_NEW` before outer commit emits false information |
| Import multiple data groups, skip failing groups | Valid groups kept if outer eventually commits | `NESTED` with savepoints or design per-group separate transactions | `NESTED` does not commit independently; manager limits |
| Simple catalog lookup | Can run both with and without transaction | `SUPPORTS` or dedicated read boundary | Do not assume consistency across multiple SELECTs |
| Orchestration method must not run with an open DB transaction | Violating callers must be caught | `NEVER` or layered architecture separation | Not a workaround for wrong transaction manager |
| Telemetry/diagnostics not needing to join T1 | Detach from outer transaction | `NOT_SUPPORTED` or run before/after transaction | No atomicity for writes |
| Operation must be wrapped by caller's unit of work | Never commits on its own | `MANDATORY` | Missing-transaction error signals caller needs fixing |

**Do not conflate audits, events, and logs.** "Saving a log" has at least three distinct semantics: best-effort technical logging, durable compliance auditing, and business events valid only once business state commits. The same method name `record()` may require three different transaction designs.

## 6. Anti-pattern 1: switching to REQUIRES_NEW to "fix" UnexpectedRollbackException

### Symptom

```text
Outer @Transactional REQUIRED
  -> Inner @Transactional REQUIRED
       -> throws RuntimeException
       -> inner interceptor marks shared transaction rollback-only
  -> Outer catches RuntimeException and returns normally
  -> Outer tries to commit
       -> UnexpectedRollbackException
```

`UnexpectedRollbackException` is not a bug to "turn off"; it is a signal that the caller reached the commit boundary **while the physical transaction could not commit**. Causes include a participating inner rollback, explicit `setRollbackOnly()`, resource failures, or other mechanisms.

### Wrong fix

```java
// Do not change propagation just to make the exception disappear.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void updateInventory() {
    // Inner suddenly commits independently from the order.
}
```

If `updateInventory` switches to `REQUIRES_NEW`, inventory can commit while the order rolls back. Sometimes the price of "no more UnexpectedRollbackException" is **violating a data invariant**. The error disappearing does not prove the new semantics are right.

### Proper analysis

- Must inventory and order be atomic together? Keep them in the same transaction, accept full rollback, and fix error reporting/caller handling.
- Is inner's failure a normal recoverable business case? Design a `NESTED` savepoint when suitable, or change the boundary so the error does not poison the shared transaction.
- Is inner genuinely independent, allowed to commit even if outer rolls back? Then `REQUIRES_NEW` makes sense, after reviewing pool/locking/idempotency.
- Did the caller catch the exception in the wrong place? Identify the outermost transactional proxy boundary and write tests outside the proxy to observe the final exception.

In particular, catching an exception in outer does not clear `rollback-only` already marked by inner. Do not recklessly disable `globalRollbackOnParticipationFailure` just to "force commit to succeed", because underlying DB/JPA resources may still be in an uncommittable state.

## 7. Anti-pattern 2: changing MANDATORY to REQUIRED just to silence errors

A domain helper is only valid when the use case's transaction spans multiple operations:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void debit(long accountId, long amount) {
    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, accountId);
}
```

This is a fragment, not a standalone program. When a caller invokes the helper without opening a transaction, Spring throws `IllegalTransactionStateException`; that may be **exactly per contract**. If changed to:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void debit(long accountId, long amount) {
    // ...
}
```

then the helper can commit the debit on its own. If the caller then fails before crediting the destination account, half of the transfer is already committed. Having no exception is a false "success".

The solution is opening the transaction on the **use-case façade**:

```java
@Transactional // REQUIRED
public void transfer(long fromId, long toId, long amount) {
    accountOperations.debit(fromId, amount);   // MANDATORY
    accountOperations.credit(toId, amount);    // MANDATORY
}
```

This fragment requires two real Spring-proxied beans; callers must enter the façade through its proxy. With the same manager/datasource, the entire transfer commits/rolls back together. Beyond the transaction boundary, you also need non-negative balance checks, locking/optimistic concurrency, and idempotency to avoid race conditions.

## 8. Anti-pattern 3: using SUPPORTS to bypass missing-transaction errors

If a JPA operation needs a transaction to flush/lock or a business invariant requires atomic updates, switching `REQUIRED` or `MANDATORY` to `SUPPORTS` **does not create a transaction** when the caller has none. It may delay errors until **later**, or produce partial writes under auto-commit.

```java
// Wrong design if the method requires an atomic multi-statement update.
@Transactional(propagation = Propagation.SUPPORTS)
public void settleInvoice() {
    updateInvoice();
    updateLedger();
}
```

Do not choose `SUPPORTS` based on "these queries just need to run". If `updateInvoice()` auto-commits and `updateLedger()` fails, business state may not roll back together. With JPA, updates may require an actual transaction and fail per the provider.

First identify the **transaction owner**. If the method can be called standalone and needs atomicity, `REQUIRED` usually fits. If it must participate in a caller's transaction, `MANDATORY` makes the contract explicit.

## 9. Anti-pattern 4: using NOT_SUPPORTED or NEVER to mask manager/annotation bugs

### Transaction manager on the wrong resource

An application with two datasources `ordersDataSource` and `auditDataSource` where a service uses the default `ordersTransactionManager` for JDBC audits can lead to "Spring has a transaction, yet audit SQL still auto-commits". Changing `REQUIRED` to `REQUIRES_NEW`/`NOT_SUPPORTED` cannot fix using **the wrong manager**.

You must identify the exact `DataSource`, `EntityManagerFactory`, or `ConnectionFactory` and pick the matching manager. If the business logic needs atomicity across multiple independent resources, a single local manager does not create a distributed transaction; use JTA/XA where appropriate or design a saga/outbox.

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void saveOrder() {
    // Order repository must actually use this manager's resource.
}
```

Fragment. The `transactionManager` attribute selects the appropriate bean; it does not change propagation semantics.

### Self-invocation

```java
@Service
class BillingService {
    public void process() {
        this.persist(); // bypasses the proxy for persist().
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist() {
        // persist's own annotation is not intercepted on this call.
    }
}
```

Fragment. In default Spring proxy mode, self-invocation bypasses transaction advice for the inner method. Changing `REQUIRES_NEW` to `REQUIRED` or `NESTED` **does not fix proxy bypass**. Move the transactional boundary to another bean and inject the Spring proxy, or consider `TransactionTemplate`/AspectJ mode when clearly justified.

### Checked exceptions and rollback rules

`@Transactional` rolls back by default for `RuntimeException` and `Error`, not automatically for checked `Exception`s (unless configuration/rollback policy changes). If a checked `IOException` escapes a method and the transaction still commits, inspect `rollbackFor`/`noRollbackFor`:

```java
@Transactional(rollbackFor = IOException.class)
public void importLedger() throws IOException {
    // ...
}
```

Fragment. Replacing `REQUIRED` with `REQUIRES_NEW` to get rollback on a checked exception operates at the wrong layer. Propagation defines *the relationship with an outer transaction*, whereas rollback rules define *which exceptions trigger rollback*.

## 10. Deciding propagation by transaction owner boundaries

Establish three clear roles:

1. **Use-case entry point**: typically owns the transaction boundary callable by clients, e.g., `TransferService.transfer()`.
2. **Domain operation**: performs part of the business logic inside the caller's transaction; can use `MANDATORY` when the contract must be enforced.
3. **Independent work**: allowed to have an independent commit outcome; only here should `REQUIRES_NEW` be considered after evaluating side effects and resources.

Structural example:

```text
TransferController
    |
    v
TransferService.transfer()                   @Transactional(REQUIRED)
    |
    +-- AccountOperations.debit()           @Transactional(MANDATORY)
    +-- AccountOperations.credit()          @Transactional(MANDATORY)
    +-- OutboxRepository.appendEvent()       joins T1
    |
    v
COMMIT T1
    |
    v
OutboxPublisher (another transaction at another time)
    |
    +-- sends message, separate retry/idempotency
```

All balance debits/credits and the outbox record commit together in T1. The publisher reads the outbox **after commit** and sends the message in a separate transaction/operation. This is usually far more reliable than sending a message outside the DB transaction and hoping some propagation makes the two operations atomic.

If there is a requirement to "log every failed money transfer", an independent audit stream/transaction can be appropriate; just name the event "transfer attempt", not "transfer completed".

### Relationship with transaction timeout/isolation/readOnly

Changing propagation also affects when `isolation`, `readOnly`, and `timeout` attributes take effect:

- `REQUIRED` joining an existing transaction usually uses the **outer physical transaction's** characteristics, creating no separate physical isolation or timeout for inner.
- `REQUIRES_NEW` creates a new physical transaction so it can set its own attributes for T2 according to manager/resource support.
- `SUPPORTS` without a transaction does not provide transactional isolation guarantees.
- `NOT_SUPPORTED` executes outside the manager's transaction; do not treat `readOnly=true` as an absolute write barrier.
- `MANDATORY` only requires an existing transaction; it does not "upgrade" the outer transaction's isolation.
- `NESTED` can use a savepoint in the same physical transaction, not a separate isolation level.

If a requirement stems from an isolation/read-only mismatch, you can enable `validateExistingTransaction` on a suitable manager or redesign transaction ownership; do not change propagation merely to avoid validation errors.

## 11. Runnable Java 17+ demo: same data, three different business requirements

Complete example using Spring Framework 6.2.8, Spring JDBC, and in-memory H2, with no Spring Boot needed. Objectives:

1. **REQUIRED:** Order and audit belong to the same unit of work; if outer fails, both roll back.
2. **REQUIRES_NEW:** Audit is an independent "attempt record"; outer fails yet the committed audit remains.
3. **SUPPORTS / MANDATORY:** Probe can operate without a transaction; helper requires the caller to open a transaction, showing that failing on a missing boundary is a useful guard.
4. **Successful REQUIRED:** Order and audit commit together; helpers participate in the right transaction.

**Modeling note:** the two tables have no foreign key between them so T2's audit does not depend on an uncommitted order row in T1. This **deliberately** avoids lock conflicts in the demo, and is not a recommendation to drop foreign keys in real applications.

### 11.1. File layout

```text
propagation-business-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── PropagationBusinessDemo.java
```

### 11.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>propagation-business-demo</artifactId>
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
                    <mainClass>dev.learning.PropagationBusinessDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 11.3. `PropagationBusinessDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class PropagationBusinessDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:business_tx;DB_CLOSE_DELAY=-1");
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
        RequiredAudit requiredAudit(JdbcTemplate jdbc) {
            return new RequiredAudit(jdbc);
        }

        @Bean
        IndependentAudit independentAudit(JdbcTemplate jdbc) {
            return new IndependentAudit(jdbc);
        }

        @Bean
        TransactionProbe transactionProbe() {
            return new TransactionProbe();
        }

        @Bean
        MandatoryGuard mandatoryGuard() {
            return new MandatoryGuard();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                RequiredAudit requiredAudit,
                IndependentAudit independentAudit,
                TransactionProbe probe,
                MandatoryGuard guard) {
            return new OrderService(
                    jdbc, requiredAudit, independentAudit, probe, guard);
        }
    }

    public static class RequiredAudit {
        private final JdbcTemplate jdbc;

        public RequiredAudit(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Audit belongs to the same atomic unit as OrderService.
        @Transactional(propagation = Propagation.REQUIRED)
        public void record(int id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, detail) VALUES (?, ?)",
                    id, "committed together");
        }
    }

    public static class IndependentAudit {
        private final JdbcTemplate jdbc;

        public IndependentAudit(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Audit of the ATTEMPT, allowed to survive even if outer rolls back.
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordAttempt(int id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, detail) VALUES (?, ?)",
                    id, "attempt recorded independently");
        }
    }

    public static class TransactionProbe {
        // Allowed to run both inside and outside an actual transaction.
        @Transactional(propagation = Propagation.SUPPORTS)
        public boolean isActualTransactionActive() {
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        }
    }

    public static class MandatoryGuard {
        // Contract: must only be called when caller has already opened a transaction.
        @Transactional(propagation = Propagation.MANDATORY)
        public void requireCallerTransaction() {
            System.out.println(
                    "mandatory.inside="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final RequiredAudit requiredAudit;
        private final IndependentAudit independentAudit;
        private final TransactionProbe probe;
        private final MandatoryGuard guard;

        public OrderService(
                JdbcTemplate jdbc,
                RequiredAudit requiredAudit,
                IndependentAudit independentAudit,
                TransactionProbe probe,
                MandatoryGuard guard) {
            this.jdbc = jdbc;
            this.requiredAudit = requiredAudit;
            this.independentAudit = independentAudit;
            this.probe = probe;
            this.guard = guard;
        }

        // Business invariant: this order and audit always roll back together.
        @Transactional
        public void rollbackTogether() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    1, "required order");
            requiredAudit.record(1);
            throw new IllegalStateException("rollback together");
        }

        // Different business invariant: audit records the ATTEMPT independently.
        @Transactional
        public void failButKeepAttempt() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    2, "independent audit order");
            independentAudit.recordAttempt(2);
            throw new IllegalStateException("outer failed");
        }

        // Normal success: same transaction, MANDATORY helper is valid.
        @Transactional
        public void createSuccessfully() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    3, "success");
            requiredAudit.record(3);

            System.out.println(
                    "supports.inside="
                    + probe.isActualTransactionActive());

            guard.requireCallerTransaction();
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table, Integer.class);
    }

    private static void printCounts(JdbcTemplate jdbc, String prefix) {
        System.out.println(
                prefix
                + " orders=" + count(jdbc, "orders")
                + " audits=" + count(jdbc, "audit_events"));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        id INT PRIMARY KEY,
                        detail VARCHAR(100) NOT NULL
                    )
                    """);

            // SUPPORTS: valid when caller has no transaction.
            System.out.println(
                    "supports.outside="
                    + context.getBean(TransactionProbe.class)
                            .isActualTransactionActive());

            // MANDATORY: direct call without a transaction must fail.
            try {
                context.getBean(MandatoryGuard.class)
                        .requireCallerTransaction();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                        "mandatory.outside="
                        + ex.getClass().getSimpleName());
            }

            OrderService service = context.getBean(OrderService.class);

            try {
                service.rollbackTogether();
            } catch (IllegalStateException ex) {
                System.out.println("required.failed=" + ex.getMessage());
            }
            printCounts(jdbc, "afterRequired");

            try {
                service.failButKeepAttempt();
            } catch (IllegalStateException ex) {
                System.out.println("independent.failed=" + ex.getMessage());
            }
            printCounts(jdbc, "afterIndependent");

            service.createSuccessfully();
            printCounts(jdbc, "afterSuccess");
        }
    }
}
```

### 11.4. Running and checking

Requires JDK 17+ and Maven 3.x. In the `propagation-business-demo` directory:

```bash
mvn -q clean compile exec:java
```

Lines **printed by the program itself** in expected order (excluding environment-dependent logs):

```text
supports.outside=false
mandatory.outside=IllegalTransactionStateException
required.failed=rollback together
afterRequired orders=0 audits=0
independent.failed=outer failed
afterIndependent orders=0 audits=1
supports.inside=true
mandatory.inside=true
afterSuccess orders=1 audits=2
```

**Explanation of each result:**

1. `supports.outside=false`: the `SUPPORTS` method can run without a physical transaction; it does not start a transaction just to return a boolean.
2. `mandatory.outside=IllegalTransactionStateException`: the contract that the caller must open a transaction is enforced. This is the **right** outcome, not an error forcing a propagation change.
3. `rollbackTogether()` uses outer `REQUIRED` and inner `RequiredAudit.REQUIRED` across **two Spring beans**. Inner joins the outer transaction. When outer throws an unchecked exception, both order and audit roll back: both counts are 0.
4. `failButKeepAttempt()` uses outer T1 and independent audit T2. Audit writes to a separate table without referencing the uncommitted order; T2 commits before T1 rolls back. Thus `afterIndependent orders=0 audits=1`.
5. `createSuccessfully()` opens a new transaction, writing order ID 3 and audit ID 3 in the same physical transaction. The `SUPPORTS` probe detects an active actual transaction; the `MANDATORY` guard passes validly.
6. When outer succeeds, order ID 3 and audit ID 3 are committed. Audit ID 2 from the earlier run still exists, so `afterSuccess orders=1 audits=2`.

**Note:** This example tests propagation *semantics* on a single JDBC datasource, and does not simulate full production load/concurrency. Expected output is based on the stated Spring/H2 configuration; run Maven to confirm directly. Each class is registered as a Spring bean via `@Bean` and cross-bean calls pass through proxies — an essential condition that `this.method()` calls would not satisfy.

### 11.5. Deliberate modifications for self-study

**Experiment A — change `IndependentAudit.REQUIRES_NEW` to `REQUIRED`.** When outer fails, both order and audit roll back: `afterIndependent orders=0 audits=0`. That is not merely an "optimization" but a change in business semantics: losing the record of the failed attempt.

**Experiment B — change `MandatoryGuard.MANDATORY` to `REQUIRED`.** Calling outside a transaction no longer fails and opens a new transaction. This illustrates why changing propagation to avoid an error can **strip away a design-protecting contract**, even though the exception line disappears from output.

**Experiment C — change `RequiredAudit.REQUIRED` to `REQUIRES_NEW`.** `rollbackTogether()` will leave behind audit ID 1 even though the order rolled back. If that audit states "order committed", it becomes **semantically false data**.

**Experiment D — call `requiredAudit.record()` directly without going through outer and with no transaction.** `REQUIRED` creates a new transaction on its own. That may suit an API meant for standalone calls, but not if the helper requires a caller-owned transaction — in that case consider `MANDATORY`.

**Experiment E — use a `@Transactional(NESTED)` helper on a JDBC savepoint** to roll back the helper's work while outer continues. Verify manager support first, and confirm that a final outer rollback still discards all changes remaining in the physical transaction. Do not interpret a nested savepoint as an independent commit.

## 12. Subtle decisions in larger codebases

### 12.1. Not every repository/helper needs to declare its own propagation

When the service façade already owns the transaction boundary, adding `@Transactional` to **every method** does not automatically make code safer. Low-level annotations can obscure the true business boundary, misleading readers into thinking every helper is an independent transaction.

Use a clear convention:

- Transaction entry points live on application services/use cases.
- Internal operations join the owner's transaction; use `MANDATORY` when the contract must be enforced.
- `REQUIRES_NEW` is an exception **justified by independent commit behavior** and covered by tests.
- Read-only operations use `SUPPORTS`/`REQUIRED` based on consistency needs, not merely because the method name starts with `find...`.

### 12.2. Transaction propagation does not determine isolation

`REQUIRED` and `REQUIRES_NEW` do not by themselves solve lost updates, write skew, or overselling. You still need database constraints, optimistic/pessimistic locking, isolation levels, and retry strategies. For example, two concurrent orders deducting stock can contend on the same row even when each transaction is properly marked `REQUIRED`.

Avoid saying "just pick `SERIALIZABLE` and skip transaction design": stronger isolation can increase contention/serialization failures and still requires retries/idempotency.

### 12.3. Transaction "suspend" does not mean "unlock"

With outer transaction T1 holding a connection and locks, an inner `REQUIRES_NEW` on the same datasource may need connection B and **wait on locks held by T1**. T1 can only resume and commit once inner returns control. Pool sizing, lock ordering, and transaction scope must be evaluated. Do not sprinkle `REQUIRES_NEW` across multiple helpers in one request.

### 12.4. Propagation does not cover networks, files, or message brokers

A DB rollback does not automatically undo an HTTP call, a sent email, or a published broker message if those resources do not share the same transaction coordinator. A use case spanning multiple microservices may need **sagas, outbox, idempotency, and compensation**. Switching `REQUIRED` to `REQUIRES_NEW` does not create distributed atomicity between a database and external APIs.

### 12.5. Watch imperative vs. reactive

`PlatformTransactionManager` ties to imperative resources such as JDBC/JPA and typically uses thread-bound context; `ReactiveTransactionManager` with R2DBC uses reactive context. Business decisions about atomicity still matter, while propagation mechanics and support depend on the manager. Do not take a thread-local JDBC example and assume every `Mono`/`Flux` behaves identically.

## 13. Investigation workflow before changing propagation

When a transaction error occurs, **separate configuration bugs from business requirements**:

### Step 1 — write down the data requirement

Write a single sentence describing which data must commit/roll back together and which data can be independent. If you cannot agree on that sentence, you do not yet have grounds to change propagation.

### Step 2 — identify the outermost boundary

Which method is the entry point? Does the caller pass through the Spring proxy? If the caller did `new Service()` manually, or a method called `this.inner()`, the propagation annotation may not even be applied. Fix proxy traversal instead of changing the enum.

### Step 3 — check the manager and datasource

Which datasource is `JdbcTemplate` using? Which `EntityManagerFactory` is `JpaTransactionManager` managing? Are there multiple transaction managers without qualifiers? A right propagation annotation on the wrong manager can let SQL run outside the intended transaction.

### Step 4 — inspect rollback-only and exceptions

- Did an exception escape the inner transactional boundary?
- Was `TransactionStatus.setRollbackOnly()` called?
- Did outer catch and swallow the exception?
- Do default rollback rules match the actual exception type?
- At which boundary did `UnexpectedRollbackException` arise?

If the issue is inner marking rollback-only, decide from business rules whether outer should abort before choosing a design.

### Step 5 — examine resource limitations

Is there connection pool exhaustion with `REQUIRES_NEW`? Are there lock waits, deadlocks, or timeouts? Is `NESTED` used where the manager/driver lacks savepoint support? Is there a JPA flush/persistence context mismatch? None of these root causes **disappear** by picking a different propagation at random.

### Step 6 — test the final outcome against a real DB

Tests must not check only exception classes or repository call counts. Query data after the transaction ends and assert exactly which tables/records exist.

```text
Given: initial data state
When : run the use case through the Spring bean proxy and trigger a deliberate failure
Then : the exact business records roll back/commit per contract
And  : there are no orphan records, partial transfers, or bogus events
```

## 14. Test matrix for propagation choices

| Test | Setup | Expected outcome |
| --- | --- | --- |
| REQUIRED all-or-nothing | Outer and inner share manager; inner writes; outer throws runtime exception | Neither outer nor inner writes remain |
| REQUIRED success | Outer and inner write and both finish normally | Both commit together |
| REQUIRES_NEW independence | Inner audit does not depend on uncommitted row and commits; outer rolls back | Audit remains, outer changes are lost |
| MANDATORY contract | Call helper directly without a transaction | Throws `IllegalTransactionStateException` |
| MANDATORY valid caller | Caller has a compatible transaction | Helper joins, does not commit separately |
| SUPPORTS outside | No outer transaction | Method runs if logic permits; no actual transaction required |
| SUPPORTS inside | Outer transaction exists | Joins existing transaction |
| NOT_SUPPORTED | Called under outer transaction | Method runs outside manager's transaction; verify resource semantics |
| NEVER | Called under outer transaction | Throws error, does not silently proceed |
| NESTED savepoint | Manager supports JDBC savepoints; inner failure is handled appropriately | Can roll back inner part while outer continues; outer rollback still reverts all |
| Self-invocation | Outer calls `this.inner()` | Inner annotation is not intercepted in proxy mode |
| Wrong transaction manager | Method uses a datasource not coordinated by the manager | Test reveals SQL does not roll back as expected; fix manager/resource |
| Checked exception | Checked exception escapes boundary | Outcome matches `rollbackFor` and actual default rollback policy |

**Beware of test-managed transactions:** A Spring TestContext `@Transactional` test method can roll back at the end of the test, masking whether a service actually committed/rolled back independently. When verifying actual commits, design appropriate test boundaries and separate queries or use `TestTransaction`.

## 15. Frequently asked questions

**Q1. Why not put `REQUIRES_NEW` on every method so they never interfere with one another?**

Because it breaks atomicity across steps that must commit together, can leave partial state behind, multiplies physical transactions/connections, and increases lock contention. Use it only when independent commit is a business requirement.

**Q2. Is `REQUIRED` always better than `MANDATORY`?**

No. `REQUIRED` lets the method open a transaction on its own. `MANDATORY` enforces a caller-owned transaction. If an operation is only valid as part of a larger transfer, `MANDATORY` prevents a caller that forgot a transaction from letting the helper commit half the work.

**Q3. Can I change `MANDATORY` to `SUPPORTS` to support callers without a transaction too?**

Only if the operation is **genuinely correct and safe** without a transaction. If the method performs multiple writes needing atomicity, making that change dangerously weakens the contract.

**Q4. If inner wants its own rollback without creating an independent transaction, what should I choose?**

Consider `NESTED`/savepoints if the JDBC manager and resource support them, and if an outer rollback must also revert inner's work. If inner must commit independently, `NESTED` does not fit.

**Q5. Is `NOT_SUPPORTED` the same as `REQUIRES_NEW`?**

No. `REQUIRES_NEW` starts a **new** physical transaction, whereas `NOT_SUPPORTED` suspends outer and executes **without the manager's actual transaction**. Multiple SQL statements may auto-commit individually when there is no transaction.

**Q6. Does `NEVER` mean the method never accesses the database?**

No. It only forbids running when a compatible transaction is currently active. The method can still access the database under non-transactional/auto-commit resource semantics if designed that way.

**Q7. Does every exception in inner `REQUIRED` roll back outer?**

Not automatically for every exception. Spring's default rollback rules target unchecked exceptions and `Error`; checked exceptions may need `rollbackFor`, and exceptions caught before escaping the proxy may not trigger rules. The DB/provider can also mark the transaction rollback-only on its own.

**Q8. Can `UnexpectedRollbackException` be treated as harmless and ignored?**

No. It informs you that the transaction the caller expected to commit actually rolled back. Ignoring it can cause the system to return a success response even though data was not saved. Trace the inner scope/resource and determine the intended semantics.

**Q9. Is a method annotated with `@Transactional` guaranteed to pass through the transaction interceptor?**

No. It requires a Spring-managed bean, active transaction infrastructure, a call through the proxy, and a method compatible with the proxy type. Self-invocation can bypass it.

**Q10. If a business event must appear exactly once after commit, should the event publisher use `REQUIRES_NEW`?**

Not by default. You can use a transactional outbox + idempotent publisher and deduplication to handle at-least-once delivery. An independent DB commit before outer commits does not prove the event matches committed business state.

## 16. Final code review checklist

- [ ] Every propagation other than `REQUIRED` has a clearly documented and tested **business reason**.
- [ ] It is stated which data must commit/roll back together.
- [ ] Independent commit, partial rollback/savepoint, and no transaction are clearly distinguished.
- [ ] `MANDATORY`/`NEVER` are treated as **contract guards**, not arbitrarily changed just to remove exceptions.
- [ ] Choosing `SUPPORTS` does not accidentally drop atomicity across multiple SQL statements.
- [ ] `REQUIRES_NEW` cannot leave behind semantically false business events/records if outer rolls back.
- [ ] Connection pool, locks, isolation, retries, and idempotency have been reviewed for independent transactions.
- [ ] Methods actually run through Spring proxies; no unintended self-invocation.
- [ ] Transaction managers match the right datasource/JPA/connection factory.
- [ ] Rollback rules reflect actual checked/unchecked exceptions.
- [ ] `NESTED` is used only when savepoints are supported and semantics match.
- [ ] Tests verify **data after the transaction boundary**, not only mocks/logs.
- [ ] Propagation is not changed as a default fix for configuration errors.

## 17. Conclusion

**Propagation is a choice about transaction ownership and atomicity scope.** Choose based on the data outcomes the business accepts:

- **`REQUIRED`:** shares the same all-or-nothing unit if a transaction exists, or opens that unit if none exists.
- **`MANDATORY`:** valid only when the caller has already opened a transaction; useful to enforce a contract.
- **`REQUIRES_NEW`:** independent physical transaction; use only when independent commit/rollback is intentional and resources suffice.
- **`NESTED`:** partial rollback via savepoint inside the same physical transaction if supported, not an independent commit.
- **`SUPPORTS`:** operation can run without an actual transaction.
- **`NOT_SUPPORTED`:** runs outside the active transaction, not a new transaction.
- **`NEVER`:** forbids calling while a transaction is active; expresses an architectural constraint.

When errors happen, fix **the transaction boundary, proxy, manager, rollback rules, resources, isolation, or workflow** according to root cause; never pick a propagation enum merely because it makes a stack trace go away.

## Official references

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and distinguishing physical/logical transactions.
2. [Spring Framework — `Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html): official definitions of all seven propagation values and support conditions.
3. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): defaults, transaction manager, proxy semantics, method visibility, isolation/readOnly/timeout.
4. [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): interceptors, proxies, and commit/rollback processing boundaries.
5. [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): exception rollback rules and `setRollbackOnly()`.
6. [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): `PlatformTransactionManager` and resource-specific managers.
7. [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): relationship between events and transaction phases; consider an outbox when reliable event delivery is needed.
