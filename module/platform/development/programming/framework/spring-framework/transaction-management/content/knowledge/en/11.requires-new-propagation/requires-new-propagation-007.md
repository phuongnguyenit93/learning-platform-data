# REQUIRES_NEW for Independent Audit Logging: Benefits and Business Atomicity Trade-Offs

## 1. The Problem: Business Logic Fails, Yet a Trace Still Needs to Be Recorded

Suppose an order-placement application wants to write an audit record: who attempted to create an order, when, and with what operation ID. If inventory checks fail or the business transaction rolls back, certain monitoring, security, or compliance requirements still need to know **that an operation attempt occurred**.

The problem appears when placing both business work and audit logging in the **same transaction**:

```text
BEGIN business transaction
  INSERT business_order
  INSERT audit_log ("ORDER_ATTEMPTED")
  ANOTHER COMPONENT THROWS RuntimeException
ROLLBACK transaction
  => business_order disappears
  => audit_log disappears too
```

This is the **atomicity** of a single transaction: changes in the same transaction commit or roll back as a unit. When the goal is *recording a trace even when business logic rolls back*, this atomicity causes the audit log to vanish.

One Spring option is moving the audit method to another Spring bean and declaring:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(...) {
    // INSERT audit_log in an independent transaction.
}
```

This is an **illustrative signature**, not a standalone Java program. When invoked properly through Spring's transaction interceptor, `REQUIRES_NEW` requests **a separate physical transaction** without joining the caller's current transaction.

**The trade-off:** if the audit commits successfully and the business operation later rolls back, the audit data **still persists**. That may be the exact requirement for a failed-attempt log, yet it can also break business rules if the audit is mistakenly interpreted as certifying "the order was successfully created".

This lesson covers not only `REQUIRES_NEW` syntax, but more importantly **choosing the right log semantics, commit boundaries, and error-handling policy**.

## 2. Understanding `REQUIRES_NEW` Accurately

Spring distinguishes a **logical transaction scope** (each method with transaction attributes) from a **physical transaction** (the real transaction on a JDBC connection/ORM resource). With `Propagation.REQUIRED`, multiple logical scopes can share one physical transaction. With `Propagation.REQUIRES_NEW`, the inner scope always uses an **independent physical transaction** when the transaction manager can create one.

When the caller is already in a transaction:

```text
Caller -> BusinessService.placeOrder() [REQUIRED]
           |
           |  TX-A: business transaction (Connection A)
           |  INSERT business_order
           |
           +--> AuditLogService.record() [REQUIRES_NEW]
           |      SUSPEND TX-A (keep TX-A's resources for resume)
           |      BEGIN TX-B (Connection B)
           |      INSERT audit_log
           |      COMMIT or ROLLBACK TX-B
           |      RELEASE TX-B resources
           |      RESUME TX-A
           |
           |  Continue TX-A
           '-- COMMIT or ROLLBACK TX-A
```

Consequences:

- **TX-B has its own commit/rollback.** Rolling back TX-A **cannot automatically undo** records already committed in TX-B.
- If TX-B rolls back, TX-B's rollback-only status **does not automatically mark TX-A rollback-only**. However, an **exception from TX-B propagating out to TX-A** can still cause TX-A to roll back according to TX-A's rollback rules.
- If TX-A has not opened a transaction, `REQUIRES_NEW` still opens a new transaction. The word "new" does not mean it only creates one when an outer transaction exists.
- The outer transaction generally retains its borrowed resources while inner needs its own resource. With a JDBC local transaction manager, this is typically a **second connection**, not a savepoint on Connection A.
- `record()` returning normally is not enough to conclude all systems outside the DB have been updated. It simply lets the transaction interceptor begin committing TX-B; the commit itself can still fail.

### Comparing Commonly Confused Propagations

| Annotation on audit method | When caller already has TX-A | If TX-A rolls back after audit returns |
| --- | --- | --- |
| `REQUIRED` (default) | Audit joins the **same physical TX-A** | Audit rolls back along with TX-A |
| `REQUIRES_NEW` | Suspends TX-A; audit runs in **independent TX-B** | Audit committed in TX-B remains |
| `NESTED` | Usually uses a savepoint on the **same physical TX-A** (if supported) | Audit still rolls back if **all of TX-A** rolls back |
| `NOT_SUPPORTED` | Suspends TX-A; audit runs **outside a Spring transaction** | Depends on auto-commit/resources; no new atomic unit protects multiple audit SQL statements |

Do not use `NESTED` instead of `REQUIRES_NEW` when the requirement is "the log must survive a full business rollback". Conversely, do not use `REQUIRES_NEW` when the requirement is "audit and order must succeed or fail together".

## 3. Two Different Levels of Atomicity

A **separate physical transaction** still guarantees atomicity for *the SQL statements inside itself*. What is traded away is **the atomicity of the entire business operation spanning both TX-A and TX-B**.

For example:

- If TX-B contains two audit SQL inserts and TX-B rolls back, both are reverted.
- Once TX-B commits, however, TX-A rolling back later can no longer control TX-B.
- Conversely, TX-A can commit successfully even if TX-B rolled back, provided the caller handles the audit exception properly.

Outcome table when the business method **chooses to handle exceptions to continue**:

| Business physical TX | Audit physical TX | Permitted final outcome |
| --- | --- | --- |
| Commit | Commit | Business record exists, audit exists |
| Rollback | Commit | No business record, **audit still exists** |
| Commit | Rollback | Business record exists, **no audit** |
| Rollback | Rollback | No business record, no audit |

These are four **possible states**, not a claim that Spring generates all four automatically if your logic always throws. Exceptions, propagation, and caller handling determine whether the outer transaction can still commit.

**Splitting transactions is not a way to achieve cross-system atomicity between two databases or two systems.** `REQUIRES_NEW` provides independence, *not* a distributed transaction coordinator, and does not guarantee exactly-once alignment between audit and business work.

## 4. Choose Audit Messages Based on Real Semantics

Before writing code, distinguish three kinds of events:

1. **Attempt / intent:** "user X *attempted* action Y". This event remains meaningful even when the action fails. It is a sensible candidate for an independent audit.
2. **Outcome:** "action Y *actually* committed" or "rolled back". This event must be recorded **after knowing the final transaction outcome**, or through an appropriate durable mechanism.
3. **Business event / integration message:** "OrderCreated" for downstream systems to update state. If emitted before commit, consumers may act on a nonexistent order. This usually requires a **transactional outbox**, not merely a `REQUIRES_NEW` before outer commits.

Naming examples:

| Record | Outer rollback occurs | Is the interpretation accurate? |
| --- | --- | --- |
| `ORDER_ATTEMPTED` | Audit remains | **Accurate:** an order attempt occurred |
| `ORDER_CREATED` before outer commit | Audit remains | **Misleading:** the order never committed |
| `ORDER_CREATION_FAILED` after confirming rollback | Audit remains | Accurate if outcome is verified and logging succeeds |
| `ORDER_COMMITTED` emitted before commit | Audit remains | Can be wrong if the subsequent commit fails |

Never treat a "success" record in TX-B as proof that TX-A committed. **Event names, timestamps, correlation IDs, and recording placement** determine whether operators interpret reality correctly.

## 5. Complete Runnable Example: Four Symmetric Scenarios

We write a **Java 17+ program** using Spring Framework **6.2.5**, Spring JDBC, and H2 **2.2.224**. No Spring Boot, Jakarta EE server, or external database is needed.

Design highlights of the example:

- `BusinessService`: each method uses `@Transactional` with default `REQUIRED` propagation, creating business transaction TX-A.
- `AuditLogService`: `record(...)` has `@Transactional(propagation = REQUIRES_NEW)`, creating transaction TX-B **through a separate Spring bean**.
- The two tables `business_order` and `audit_log` have no foreign key between them, because TX-B cannot assume TX-A's new row is committed or visible.
- In-memory H2 ensures row counts are easy to inspect after each case.
- Exceptions use `IllegalStateException` (unchecked) to trigger rollback by default, unless outer explicitly catches and continues.

### 5.1. File Structure

```text
independent-audit-demo/
├── pom.xml
└── src/main/java/demo/IndependentAuditDemo.java
```

### 5.2. Create `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>independent-audit-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides ApplicationContext/JavaConfig, `spring-jdbc` provides JdbcTemplate and the JDBC transaction manager; H2 is the test database. `DriverManagerDataSource` below is suitable only for demos, not a production connection pool.

### 5.3. Create `src/main/java/demo/IndependentAuditDemo.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public class IndependentAuditDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BusinessService business = context.getBean(BusinessService.class);

            jdbc.execute("""
                CREATE TABLE business_order (
                    id INT PRIMARY KEY,
                    description VARCHAR(80) NOT NULL
                )
                """);

            jdbc.execute("""
                CREATE TABLE audit_log (
                    id INT PRIMARY KEY,
                    event_type VARCHAR(80) NOT NULL
                )
                """);

            // CASE A: audit commits first, business rolls back afterward.
            try {
                business.businessFailsAfterAudit(1, 101);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_A_ERROR=" + ex.getMessage());
            }
            report("AFTER_A", jdbc);

            // CASE B: audit rolls back, yet business catches the error and commits.
            business.auditFailsButBusinessCommits(2, 102);
            report("AFTER_B", jdbc);

            // CASE C: audit error propagates out; both transactions roll back.
            try {
                business.auditFailsAndPropagates(3, 103);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_C_ERROR=" + ex.getMessage());
            }
            report("AFTER_C", jdbc);

            // CASE D: both transactions commit.
            business.bothCommit(4, 104);
            report("AFTER_D", jdbc);
        }
    }

    private static void report(String label, JdbcTemplate jdbc) {
        int orders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM business_order", Integer.class);
        int audits = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_log", Integer.class);
        System.out.printf("%s business=%d audit=%d%n", label, orders, audits);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:independent_audit;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public AuditLogService auditLogService(JdbcTemplate jdbc) {
            return new AuditLogService(jdbc);
        }

        @Bean
        public BusinessService businessService(
                JdbcTemplate jdbc, AuditLogService audit) {
            return new BusinessService(jdbc, audit);
        }
    }

    public static class AuditLogService {
        private final JdbcTemplate jdbc;

        public AuditLogService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void record(int auditId, String eventType, boolean fail) {
            jdbc.update(
                    "INSERT INTO audit_log (id, event_type) VALUES (?, ?)",
                    auditId, eventType);

            if (fail) {
                throw new IllegalStateException("audit failure");
            }
        }
    }

    public static class BusinessService {
        private final JdbcTemplate jdbc;
        private final AuditLogService audit;

        public BusinessService(JdbcTemplate jdbc, AuditLogService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void businessFailsAfterAudit(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", false);
            throw new IllegalStateException("business failure");
        }

        @Transactional
        public void auditFailsButBusinessCommits(int orderId, int auditId) {
            insertOrder(orderId);

            try {
                audit.record(auditId, "ORDER_ATTEMPTED", true);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_B_AUDIT_ERROR=" + ex.getMessage());
                // Illustrative policy: audit failure does NOT block business.
            }
        }

        @Transactional
        public void auditFailsAndPropagates(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", true);
            // Exception is not caught: business transaction rolls back.
        }

        @Transactional
        public void bothCommit(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", false);
        }

        private void insertOrder(int orderId) {
            jdbc.update(
                    "INSERT INTO business_order (id, description) "
                    + "VALUES (?, ?)", orderId, "example order");
        }
    }
}
```

**Why does the code put the two services in two separate beans?** Spring `@Transactional` works via AOP proxies by default: calling from the `BusinessService` bean to the `AuditLogService` bean is intercepted by the proxy. Placing `@Transactional(REQUIRES_NEW)` on a `private` method in the same class and calling `this.record()` would normally **not apply** the new annotation due to self-invocation. In that case the audit could be folded into the outer transaction and lose independence.

In this configuration, `@Bean` creates Spring-managed beans; `@EnableTransactionManagement` enables the transaction interceptor; `JdbcTransactionManager` manages a `DataSource`. `proxyTargetClass = true` requests class-based proxies, fitting concrete-class bean lookups from the context. Both services' `JdbcTemplate` instances share the same `DataSource`, yet the transaction interceptor assigns a different connection to inner `REQUIRES_NEW` while outer is active.

**Why avoid a foreign key from audit to business_order?** If TX-A has not committed the order row, TX-B on its separate connection may not see that row. A foreign key requiring reference to an uncommitted order can block on locks, fail, or deadlock. Attempt audits should carry an independent correlation ID/operation ID rather than assuming the business row is durably present.

### 5.4. Running the Program

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.IndependentAuditDemo
```

The lines from the program's `System.out`, **excluding Maven/Spring messages**:

```text
CASE_A_ERROR=business failure
AFTER_A business=0 audit=1
CASE_B_AUDIT_ERROR=audit failure
AFTER_B business=1 audit=1
CASE_C_ERROR=audit failure
AFTER_C business=1 audit=1
AFTER_D business=2 audit=2
```

### 5.5. Analyzing the Four Cases

**CASE A — Audit commits, business rolls back**

1. `BusinessService.businessFailsAfterAudit(1, 101)` opens TX-A and `INSERT`s into `business_order`.
2. `audit.record(..., false)` passes through the bean proxy; TX-A is suspended and TX-B begins.
3. TX-B inserts into `audit_log` and commits; audit count becomes **1**.
4. TX-A resumes, and the method then throws `IllegalStateException("business failure")`.
5. TX-A rolls back the order row. Result: `business=0, audit=1`.

This is the case where **the failed-operation log is preserved**, while the overall operation **is no longer atomic** as a single unit.

**CASE B — Audit rolls back, business still commits**

1. Outer TX-A inserts order #2.
2. Inner TX-B inserts audit #102 and throws `IllegalStateException("audit failure")`; the transaction interceptor rolls back TX-B.
3. The exception returns to the outer method, where `try/catch` in `BusinessService` handles it and **does not rethrow**.
4. TX-A can still commit normally; result: `business=1, audit=1`.

This case illustrates the symmetric pitfall: **an order exists with no new audit record**. If auditing is mandatory under security/compliance policy, **do not swallow exceptions in this fail-open manner**. The example only demonstrates that the two transactions can act independently.

**CASE C — Audit rolls back, exception propagates causing business rollback**

1. Outer TX-A inserts order #3.
2. Inner TX-B inserts audit #103, then fails; TX-B rolls back.
3. `BusinessService.auditFailsAndPropagates()` does not catch the exception. `IllegalStateException` escapes TX-A's boundary.
4. Under the default rollback rule, TX-A also rolls back. Counts remain unchanged: `business=1, audit=1`.

Important: the two transactions roll back **due to two separate decisions**, not because TX-B automatically forced TX-A to roll back. The exception from inner caused outer's interceptor to decide on rollback. With a different exception type or `noRollbackFor` rule, the outcome could differ.

**CASE D — Both commit**

Inner TX-B audit #104 commits first; then TX-A order #4 commits. Result: `business=2, audit=2`. This is the normal path, **yet a gap still exists**: TX-B may have committed while TX-A fails during flush/commit immediately afterward. Never use the fact that both usually succeed as proof of atomicity between them.

## 6. What If `REQUIRES_NEW` Is Replaced with `REQUIRED`?

Change **only** the annotation on `AuditLogService.record(...)`:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void record(int auditId, String eventType, boolean fail) {
    // Same logic to INSERT audit_log and throw an error as the demo.
}
```

This is a **change-illustration snippet**, not a standalone method.

When outer already has TX-A, the audit shares TX-A:

- In **case A**, outer rollback reverts **both order and audit**. There is no longer a guarantee that the audit attempt is saved.
- In **case B**, the inner method throws an unchecked exception. Even if outer catches it, inner's transaction interceptor may have marked **TX-A rollback-only**. When outer tries to commit, Spring may throw `UnexpectedRollbackException` instead of silently committing. **Catching the exception in outer does not clear rollback-only.**
- In **case C**, both changes roll back inside the same TX-A.
- In **case D**, both order and audit commit in one shared transaction.

Thus `REQUIRED` fits when audit must **share fate** with business state; `REQUIRES_NEW` fits when audit is intentionally kept even after a business failure. No propagation setting can both guarantee "audit must commit even if business rolls back" **and** enforce "business and audit always commit/roll back together": those two requirements contradict each other at the transaction level.

## 7. Audit Failure: Fail-Open or Fail-Closed?

**Fail-open** means business logic is allowed to commit even when audit fails. It optimizes availability, yet can violate mandatory audit requirements.

**Fail-closed** means business logic must fail/roll back if audit fails. It reduces the risk of creating unaudited business state, yet makes business operations depend on audit infrastructure health.

| Requirement | Design direction | Trade-off |
| --- | --- | --- |
| Must retain every **attempt** even on business rollback | Audit via `REQUIRES_NEW` on an independent bean, with explicit error policy | Audit can persist even when business does not commit |
| No business record may exist without a matching audit | Write business + audit/outbox via `REQUIRED` in the same DB transaction | Business rollback also rolls back audit |
| Audit failure must block business work | Do not catch/swallow the exception; or explicitly mark outer rollback-only | Lower availability if audit DB goes down |
| Best-effort audit | Controlled catch, metrics/alerts, and appropriate fallback | Records may be lost; do not claim complete auditing |
| Need a "business committed" event sent externally | Transactional outbox or transaction-aware post-commit delivery | Requires sender/consumer, dedupe, and extra operations |

**Note:** even with fail-closed, `REQUIRES_NEW` does not provide reverse atomicity. If audit TX-B already committed and business TX-A later fails, the audit still survives. Fail-closed only governs **how audit failure is handled**, not merging two commits into one unit.

In systems with strict compliance requirements, define both **whether logs must survive rollback** and **whether business work may commit if logging fails**. Those are two separate questions.

## 8. Why Does `REQUIRES_NEW` Easily Cause Connection Pool and Lock Risks?

Spring warns directly: while inner `REQUIRES_NEW` runs, the outer transaction generally holds onto its connection while inner must acquire a new connection from the pool. This can exhaust the pool.

Suppose **10 threads** simultaneously hold **10 connections** in outer, and the pool size is only **10**. All 10 threads call `REQUIRES_NEW` audit and wait for a second connection; no thread releases its outer connection until inner finishes. The result can be pool starvation/timeout, or even a connection-allocation deadlock.

Spring's guideline is that the pool must be **larger than the number of concurrent threads by at least 1**, though actual sizing depends on `REQUIRES_NEW` nesting depth, competing requests, other DB tasks, and timeouts. Do not treat "plus 1" as a guaranteed formula under all workloads.

### Locks and Data Visibility

Inner runs in its own physical transaction. Under common isolation levels like `READ_COMMITTED`, inner cannot assume it sees **uncommitted** new rows from outer. An inner audit attempting to read or update the exact row locked by outer can block; if outer is waiting for inner to finish, a lock wait/deadlock or timeout occurs.

**Better design for independent audits:**

- Do not have inner query business records just inserted uncommitted by outer.
- Use a pre-generated `operationId`/`requestId` stored in the audit as a **descriptive value**, without requiring a foreign key to an uncommitted row.
- Keep the audit transaction **short**, inserting only necessary data.
- Avoid the audit service opening further nested `REQUIRES_NEW` calls.
- Monitor pool active/idle/wait counts, lock waits, deadlocks, connection acquisition latency, commit times, and audit failures.
- Configure reasonable timeouts and avoid holding outer transactions open across network calls or long slow processing.

This example uses two independent tables to avoid one type of lock mistake, **which does not prove** all production scenarios are deadlock-free.

## 9. What Cannot `REQUIRES_NEW` Guarantee?

An independent audit transaction is not an infallible audit system:

1. **No record if the app crashes before calling audit.** Until TX-B begins, there is nothing to commit.
2. **No record if the audit DB is unavailable.** TX-B can still fail; define a clear error policy.
3. **Does not prove the final business outcome.** TX-A can still roll back after TX-B commits.
4. **No exactly-once guarantee.** Request or inner-method retries can write duplicate logs without a unique idempotency key.
5. **No automatic global ordering.** Separate transactions and concurrent requests can commit in different orders.
6. **Does not guarantee immutability.** Insert-only privileges, tamper resistance, retention, and sensitive-data controls remain separate concerns.
7. **Does not turn multiple DBs into a distributed transaction.** A local JDBC manager does not coordinate XA/2PC.
8. **Does not make external side effects roll back.** Sending emails, HTTP requests, or queue messages inside TX-B cannot be undone if the DB rolls back.
9. **Target method return does not guarantee commit.** The transaction interceptor still must flush/commit; failures there can throw exceptions.
10. **Does not prevent every race condition.** Observers checking order status may see an ATTEMPTED audit event before TX-A decides to commit or roll back.

### Connection Drop During Commit

A tricky case is when the driver loses connection right when sending `COMMIT`: the application may not know whether the audit transaction committed. Unconditionally retrying `INSERT` can create duplicate logs. Use a **stable operation ID** with a unique constraint/idempotent write. Retry policies should distinguish clearly retryable errors from uncertain commit outcomes.

## 10. Separating Attempt Audits from Outcome Audits

If a problem requires storing **both attempts and outcomes**, design two events:

```text
Before/at request start:
  independent audit -> ACTION_ATTEMPTED(operationId)

Business transaction:
  perform business changes
  -> COMMIT or ROLLBACK

After known completion:
  best-effort or durable mechanism
  -> ACTION_COMMITTED(operationId)
  -> ACTION_ROLLED_BACK(operationId)
```

Do **not simply put a `REQUIRES_NEW` audit call inside the business method and rename it `ACTION_COMMITTED`**; that event could commit ahead of the business work.

Options include:

- At the caller layer **after the transactional service proxy returns normally**, you know the interceptor completed the scope it owns. However, if that service only joined an outer transaction, the final outcome is not yet determined.
- `TransactionSynchronization.afterCommit()` or `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` suits logic that must run only after the corresponding physical transaction commits successfully.
- `AFTER_ROLLBACK`/`AFTER_COMPLETION` callbacks observe Spring-managed transaction outcomes; understand propagation, exceptions, and cleanup timing thoroughly.
- If a callback wants to **perform a new DB write**, invoke a separate service opening `REQUIRES_NEW` when appropriate; resources from the just-completed transaction may still be bound to the thread during callback execution.
- Post-commit callbacks **do not make writing an outcome to another DB atomic** with the business commit. If the callback fails or the process crashes after commit, the outcome log can be lost.

Therefore, when the requirement is "do not tell consumers ORDER_COMMITTED until the order commits" and durability across process crashes is required, **outbox** is usually the right choice.

## 11. Transactional Outbox When Atomicity Between Business and Event Is Needed

Outbox serves a different goal. In the same `REQUIRED` physical transaction, write both the business row and the outbox record:

```sql
-- Both operations run in the SAME business transaction.
INSERT INTO business_order (id, description)
VALUES (10, 'new order');

INSERT INTO outbox_event (event_id, event_type, aggregate_id, payload)
VALUES ('op-10', 'ORDER_CREATED', 10, '{"orderId":10}');
```

This SQL only illustrates the table model; `outbox_event` is not defined in the Section 5 H2 program and **will not run standalone** without creating the table.

Result:

- TX-A commits: both the order and the outbox event exist together.
- TX-A rolls back: both the order and the outbox event vanish.
- A background worker/publisher reads committed outbox rows, sends messages to the broker, and records sent status or retries.
- Senders/consumers must handle **at-least-once / idempotency**, since publishing can succeed before the worker updates the outbox status.

Outbox solves **atomicity between business state and publishing intent within the same DB**, without making the message broker join the transaction. Nor does it **preserve an attempt audit** if the business transaction rolls back, because attempt audits and outboxes serve different purposes.

### Decision Table

| Goal | Usually appropriate approach |
| --- | --- |
| Record an attempt even when the operation fails | Attempt audit using an independent `REQUIRES_NEW` transaction |
| Order and audit must commit/roll back together | `REQUIRED`, same actual transaction / same resource |
| Emit `ORDER_CREATED` after commit without losing events | Transactional outbox + publisher |
| Need only an in-memory callback after commit, tolerating loss on crash | `afterCommit` / `@TransactionalEventListener(AFTER_COMMIT)` |
| Must log audit before allowing business commit | Fail-closed with real checks; consider same transaction if atomicity is needed |
| Transactions across multiple datasources must be atomic | Appropriate JTA/XA architecture or business coordination (saga), not `REQUIRES_NEW` alone |

## 12. Exception Propagation, Rollback-Only, and Self-Invocation

### 12.1. Exception Does Not Mean Shared Rollback

In case C, the audit error is thrown out of `AuditLogService` and then out of `BusinessService`. Both roll back, yet **each transaction rolls back because its own interceptor saw an unchecked exception**. `REQUIRES_NEW` does not copy a rollback-only flag into the outer transaction.

In case B, the exception was caught inside the business method, so outer continued to the end and committed. If mandatory auditing is required, a "catch and ignore" policy is a business design flaw, not a Spring bug.

### 12.2. Checked Exceptions and Custom Rollback Rules

By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions generally **do not** trigger rollback automatically. If audit throws a checked exception and you want TX-B to roll back, configure it explicitly:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = java.io.IOException.class)
public void recordWithCheckedError() throws java.io.IOException {
    throw new java.io.IOException("audit store unavailable");
}
```

This is an **illustrative method**; it must live on a Spring-managed bean, not be called directly inside the demo. If outer also receives the exception and is configured with a matching rollback rule, TX-A may roll back under its own rule.

### 12.3. Self-Invocation Does Not Create a New Transaction

**Common mistake:**

```java
@Service
class WrongService {
    @Transactional
    public void business() {
        saveAudit(); // this.saveAudit(): bypasses proxy!
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // May be using the outer transaction instead of opening TX-B.
    }
}
```

This code illustrates an anti-pattern and does not run standalone as it omits imports/implementation. In default Spring proxy mode, `this.saveAudit()` is an internal call and **is not intercepted by transaction advice as a new boundary**.

**Correct:** use a separate `AuditLogService` bean so `BusinessService` calls it through the Spring proxy as in the demo. You can use `TransactionTemplate` with `REQUIRES_NEW` propagation when you need a programmatic boundary independent of self-invocation, provided the transaction manager and exception handling are configured carefully.

### 12.4. Avoid Auditing Through Manually Instantiated Objects

`new AuditLogService(jdbc)` also bypasses the proxy and does not start a new transaction. Even if the method carries the right annotation, the object must be Spring-managed and the call must pass through the proxy/transaction interceptor.

## 13. Properly Testing Independent Transactions

Merely asserting that the audit method was invoked is **insufficient**. Verify database state **after the outer transaction has finished**:

- **Case A**: after outer throws, `business_order` has no row 1 while `audit_log` has row 101.
- **Case B**: inner exception is handled by outer; row 2 exists while audit row 102 does not.
- **Case C**: inner exception propagates; neither row 3 nor audit 103 exists.
- **Case D**: both row 4 and audit 104 exist.

Verification queries should run outside the transaction under test or in a fresh transaction capable of reading committed results. If you use Spring TestContext with `@Transactional` on the **test method**, it can open an outer test transaction and roll it back when the test finishes, altering the boundary you want to observe. For integration tests specifically checking commit/rollback, consider removing `@Transactional` from the test, or using `TestTransaction` with explicit transaction-completion management.

For effective verification in real systems, do not check counts alone; inspect **`operationId`**, event types, transaction timestamps, accurately encoded statuses, and idempotency under retries.

### Failure Cases to Add in Real Systems

1. Audit DB unreachable: does business fail-open or fail-closed?
2. Audit transaction commits and connection drops so caller does not know the outcome: does retrying create duplicate logs?
3. Outer holds a lock on a business row, and inner audit accidentally reads that row: does it time out?
4. Is the pool sized for peak traffic with concurrent outer + inner calls?
5. Is another outer transaction wrapping the service? Where is the actual final commit boundary?
6. What if `afterCommit`/`afterRollback` callbacks fail or the process crashes mid-way?
7. Is sensitive data masked and retained appropriately?
8. Is the audit event still **semantically accurate** when business fails yet the audit row persists?

## 14. Production Rollout Checklist

Before choosing `REQUIRES_NEW` for auditing, answer:

- **Business requirement:** Must the audit really persist when business rolls back? If yes, does the event represent an **attempt** or a **committed outcome**?
- **Failure policy:** If audit is down, may the request commit? Who gets alerted? Is there a durable fallback?
- **Boundary:** Is the audit service an independent Spring bean? Does `@Transactional(REQUIRES_NEW)` go through a proxy?
- **Resources:** Can outer and inner transactions hold connections simultaneously? Have pool sizes and timeouts been load-tested?
- **Locks:** Does inner touch uncommitted data or rows locked by outer? Could FKs cause blocking?
- **Data:** Are `operationId`/correlation ID, actor, operation type, outcome, and timestamp clear? Is there a unique constraint preventing duplicates?
- **Consistency:** Is `REQUIRES_NEW` being used to emit a "succeeded" business event before commit? If so, consider outbox.
- **Tests:** Are there integration tests covering cases A/B/C/D and commit failures? Are connection exhaustion, rollback, and retries tested?
- **Security:** Does auditing enforce least-privilege write access, retention, sensitive-data masking, and tamper protection?

Usually keep the inner transaction **short, single-purpose**, and free of slow network calls while outer holds connections and locks. An independent transaction is a tool, not a default "safer" setting for every audit call.

## 15. Self-Check Questions

**Q1.** Outer `@Transactional(REQUIRED)` writes an order, and inner `@Transactional(REQUIRES_NEW)` writes an audit and commits. Outer then throws `IllegalStateException`. What remains?

**A:** Outer rolls back the order; the audit committed in its own physical transaction can still remain. There is no shared atomicity across the two transactions.

**Q2.** Inner audit rolls back and throws an unchecked exception. Outer catches the error and returns normally. Must outer always roll back?

**A:** No. With inner `REQUIRES_NEW`, inner's rollback-only status does not automatically apply to outer. Outer can commit if it was not marked rollback-only and hit no other errors; that is case B.

**Q3.** If outer does not catch the audit exception, what happens?

**A:** The exception escaping outer's boundary can trigger outer's rollback rule. Both transactions roll back separately, as in case C.

**Q4.** We want the audit to appear only if the order actually commits. Is using `REQUIRES_NEW` before outer commits appropriate?

**A:** Not appropriate: audit could commit first and outer could roll back. If in the same DB and atomicity is needed, use a shared transaction/outbox; if it is strictly a post-commit action, consider an after-commit hook with its corresponding reliability trade-offs.

**Q5.** Audit is a method on `BusinessService` itself, called via `this.saveAudit()`, annotated `REQUIRES_NEW`. Is it independent?

**A:** You cannot assume so. Proxy mode bypasses self-invocation, so call through a proxy/another bean or use properly configured programmatic transactions.

**Q6.** Why can a 10-connection pool stall with 10 concurrent requests when each holds an outer connection and needs an inner connection?

**A:** All connections can be held by outers; no connection remains for inner, yet outer is waiting for inner to complete before releasing its connection. Proper sizing and timeouts are needed.

**Q7.** An independent audit wrote `ORDER_CREATED` and committed, yet the business transaction rolled back. Where is the bug?

**A:** Not necessarily in Spring; it is a bug of **naming/recording an event at the wrong time**. `ORDER_CREATED` is an outcome, whereas inner only knew the request was attempted. Distinguish attempted vs committed, or use an outbox.

## Takeaways

**`REQUIRES_NEW` creates an independent physical transaction.** It fits audits/logs of **intent or operation attempts** that must survive even when the business transaction rolls back. Yet that very independence creates two failure modes of divergence: **audit can commit when business rolls back**, or **business can commit when audit rolls back** if ignoring audit errors is allowed.

To guarantee joint commit/rollback, **do not split the physical transaction**; to guarantee events strictly reflect business commits, design with a shared DB transaction/outbox or an appropriate durable mechanism. Choose based on semantics, not because a method looks nicer with an annotation.

## Official References

1. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): distinguishing `REQUIRED`, `REQUIRES_NEW`, and `NESTED`, physical transaction independence, and pool warnings.
2. Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptors and proxies.
3. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): rollback rules and self-invocation limitations.
4. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`.
5. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
6. Spring Framework — [Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): notes on transaction callbacks and event limitations.
