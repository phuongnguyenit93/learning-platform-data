# Commit, Rollback, and Independent Attributes of a New Transaction with REQUIRES_NEW

> **Module:** Spring Framework — Transaction Management. **Section:** REQUIRES_NEW. This lesson focuses on how a new transaction **commits/rolls back independently** of the outer transaction and owns its own **isolation, timeout, read-only, and rollback rules**. Examples assume Spring transaction management in **proxy mode**, a JDBC DataSource, and a corresponding transaction manager; the hands-on section includes a complete Spring Boot 3.5.7 / Java 17 / H2 / Maven project for self-verification.

## 1. Meaning of REQUIRES_NEW

`@Transactional(propagation = Propagation.REQUIRES_NEW)` instructs Spring to **start a new physical transaction** for the invocation actually handled by the transaction interceptor.

When an outer transaction `T1` is already active on the same thread/transaction manager:

1. Spring **suspends** the `T1` transaction context.
2. Spring starts a separate physical transaction `T2`, typically using a **different connection** for JDBC transactions on the same DataSource.
3. The inner method executes within `T2`. `T2` independently decides whether to commit or roll back based on its outcome and rollback rules.
4. Once `T2` completes, Spring cleans up `T2`'s context and **resumes `T1`**.
5. Outer continues in `T1`; finally `T1` commits or rolls back based on its own outcome.

```text
Caller
  |
  v
OuterService.outer()          @Transactional(REQUIRED)
  |                             start physical transaction T1
  |------ INSERT outer -------->
  |
  | call through Spring proxy
  v
InnerService.inner()          @Transactional(REQUIRES_NEW)
  |                             suspend T1
  |                             start physical transaction T2
  |------ INSERT inner -------->
  |                             commit or roll back T2
  v                             resume T1
OuterService continues
  |------ INSERT outer2 ------->
  v
commit or roll back T1

T2 completes before T1 ends; T2 is not a savepoint of T1.
```

**Key takeaway:** `REQUIRES_NEW` does not join the existing physical transaction. After `T2` commits successfully, a rollback of `T1` **does not automatically undo** `T2`'s data. Conversely, `T2` rolling back does not automatically mark `T1` as rollback-only, **but an exception from `T2` propagating to outer can still cause `T1` to roll back**.

When **no transaction exists yet**, `REQUIRES_NEW` starts a new transaction as requested; in that case there is only one physical transaction and no outer transaction to suspend.

## 2. Physical Transaction, Logical Scope, and Commit Boundaries

Understanding independence requires distinguishing two concepts:

- **Physical transaction:** the actual database/resource transaction. In JDBC, one connection in a transaction; in JPA, a transaction per entity manager/transaction manager. This is what truly commits or rolls back.
- **Logical transaction scope:** the transaction metadata/interception corresponding to a transactional method invocation. A scope can share a physical transaction with another scope or start its own physical transaction depending on propagation.

With `Propagation.REQUIRED` (the default), an inner logical scope typically **joins** outer's physical transaction `T1`. With `Propagation.REQUIRES_NEW`, the inner logical scope uses a **separate `T2`**.

| Question | Inner `REQUIRED` when outer T1 is open | Inner `REQUIRES_NEW` when outer T1 is open |
| --- | --- | --- |
| Physical transaction of inner | Reuses `T1` | Creates a separate `T2` |
| Independent commit before outer? | No | Yes |
| Does inner rollback-only directly affect T1? | Can mark T1 rollback-only | Not directly, because T2 is separate |
| Outer rollback after inner succeeds | Undoes inner data along with T1 | Does not undo data already committed by T2 |
| Inner's own isolation/timeout/readOnly | Generally not reapplied to T1 | Can be set for T2 when supported |
| JDBC connection | Usually shares T1's connection | T1 retains its connection; T2 usually needs another connection |
| Resource impact | Lower overhead | Extra transaction/connection/lock, pool exhaustion risk |

"Not directly affecting" **does not mean** "cannot affect". An exception thrown from `T2` and **not handled by outer** exits the outer method; outer's interceptor can roll back `T1` according to **outer's** rules. This is exception propagation, **not** `T1` rolling back because `T2` shared its physical transaction.

## 3. Commit and Rollback Matrix: Four Fundamental Outcomes

Suppose outer writes record `O` in T1, and inner writes record `I` in T2. The records use **different keys/rows** to avoid unnecessary locking; both methods are properly called through Spring proxies. The table describes the outcome after both T1 and T2 have ended.

| T2 Outcome | T1 Outcome | Inner record `I` | Outer record `O` |
| --- | --- | --- | --- |
| **Commit** | **Commit** | Present | Present |
| **Commit** | **Rollback** | **Present** | Absent |
| **Rollback** | **Commit** | Absent | **Present** |
| **Rollback** | **Rollback** | Absent | Absent |

This reflects the **independence of commit/rollback decisions** of the two physical transactions. Spring adds no "must commit together" rule. If the business logic requires both or neither to succeed, `REQUIRES_NEW` is **usually not** the right propagation; `REQUIRED` on the same resource may be more suitable.

### 3.1. Inner Commit, Outer Rollback

```java
@Transactional
public void processOrder() {
    orderRepository.insert(...);   // T1, illustrative example.
    auditService.writeAudit();      // T2, REQUIRES_NEW, already committed.
    throw new IllegalStateException("Order failed");
}
```

This is a **business snippet**, not a runnable class. When inner is a separate bean invoked through a proxy, audit `T2` can **remain** after outer `T1` rolls back. Use this only if that independent audit record is valid even when the order was not committed.

### 3.2. Inner Rollback, Outer Commit

```java
@Transactional
public void processOrder() {
    orderRepository.insert(...);   // T1.
    try {
        auditService.writeAndFail(); // T2 rolls back.
    } catch (IllegalStateException ex) {
        // Accept audit failure; continue outer business logic.
    }
    orderRepository.markReady(...); // T1 can still commit.
}
```

**Conditions:** the exception from T2 must be properly handled by outer, no other resource error marks T1 rollback-only, and database state remains consistent. If outer **does not catch** the unchecked exception, the outer interceptor will also roll back T1 by default.

### 3.3. Both Inner and Outer Commit

T2 commits first, then T1 commits. This is a possible outcome, yet it **does not form a shared atomic transaction**: between the two commit points, another transaction may already observe T2's data while T1's uncommitted data is not yet visible.

### 3.4. Both Inner and Outer Rollback

T2 encounters an error and rolls back. If the exception still escapes outer and matches `@Transactional`'s default rollback rule, T1 also rolls back. They remain **two separate rollback decisions**. Do not cite this case as proof that inner joined T1.

## 4. Two-Bean Call Example: Conditions for REQUIRES_NEW to Actually Work

```java
@Service
public class PaymentService {
    private final ReceiptService receipts;

    public PaymentService(ReceiptService receipts) {
        this.receipts = receipts;
    }

    @Transactional
    public void pay() {
        // Transaction T1.
        receipts.recordReceipt(); // Call proxy of another bean.
        // Continue transaction T1.
    }
}

@Service
public class ReceiptService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordReceipt() {
        // Transaction T2.
    }
}
```

This is an **illustrative snippet**; each public class belongs in its own file. Imports needed are `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, and `org.springframework.transaction.annotation.Propagation`. Configuration must include transaction infrastructure/a proper transaction manager, and Spring must actually inject the proxy of `ReceiptService`.

**It is not enough** to simply add the annotation to a method in the same class:

```java
@Service
class IncorrectSelfInvocation {
    @Transactional
    public void outer() {
        inner(); // this.inner(): bypasses Spring proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Inner annotation is not applied separately via self-call.
    }
}
```

In **Spring AOP proxy mode**, calling `this.inner()` executes directly on the target object without going back through the interceptor. If `outer()` has already opened T1, code inside `inner()` may use T1's connection/transaction; **there is no T2**. If `outer()` rolls back, writes in inner may roll back along with it.

With JDK interface proxies, the method must be a public method on a proxied interface; with class-based proxies, the method must be interceptable/overridable; `private` and `final` methods are problematic. Beans instantiated with `new` do not go through Spring proxies. `AspectJ` weaving has a different mechanism, but you should not rely on it when using default proxy mode.

## 5. Isolation, Timeout, and ReadOnly Are T2's Own Attributes

One benefit of `REQUIRES_NEW` is that the inner transaction **does not mechanically inherit the characteristics** of physical transaction T1. When starting T2, Spring can ask the manager/resource to apply separate isolation, timeout, and read-only settings.

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void queryImportantSnapshot() {
    // Read data in T2 with its own transaction attributes.
}
```

This is a **snippet**; import `Propagation`, `Isolation`, and `Transactional` from `org.springframework.transaction.annotation`.

- **`propagation = REQUIRES_NEW`:** suspends T1 (if any) and starts a new transaction T2.
- **`isolation = SERIALIZABLE`:** requests this isolation level for T2, if supported by the transaction manager/driver/database. This does not alter T1's isolation level.
- **`timeout = 5`:** configures a **5-second** transaction limit for the new T2. It is not a timer that automatically interrupts every Java method, HTTP call, or `Thread.sleep` at exact second 5. Enforcement depends on the manager/driver/database/statement.
- **`readOnly = true`:** metadata/hint for T2, which can enable optimizations and instruct the driver/database to apply read-only behavior. **It is not a database authorization mechanism and does not guarantee all DBs block `INSERT`/`UPDATE`.**
- When T2 ends, Spring restores T1's context. T1's isolation and readOnly are not "polluted" by T2's custom settings if the manager properly supports suspend/resume.

### 5.1. An Exception: Joining REQUIRED Does Not Re-Apply Characteristics

```java
@Service
class InnerReportService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE,
        timeout = 5,
        readOnly = true
    )
    public void readReport() {
    }
}
```

If this method **joins** an existing T1, Spring by default uses the characteristics of the **outer physical transaction**, without upgrading T1 to serializable, resetting the timeout, or turning all of T1 read-only. You can instruct the manager to check mismatches using `setValidateExistingTransaction(true)`, but validation **rejects incompatible configurations** rather than creating T2.

### 5.2. Own Defaults When Attributes Are Omitted

An inner `@Transactional(propagation = REQUIRES_NEW)` without extra attributes:

- `isolation` defaults to `Isolation.DEFAULT` -> the default isolation level of the underlying transaction resource.
- `timeout` defaults to the transaction manager/system default, which may be unlimited if the infrastructure does not set one.
- `readOnly` defaults to `false`.
- Rollback defaults to occurring when a `RuntimeException` or `Error` escapes the interceptor; checked exceptions usually **do not** trigger rollback by default.
- `REQUIRES_NEW` **does not copy** T1's isolation/readOnly/timeout; T2 is configured from its own annotation, manager defaults, and underlying resource.

Therefore, do not interpret "T2 has its own attributes" as **T2 automatically inheriting all of T1 and overriding a few attributes**. It is a new transaction with its own definition; for example, if outer is `SERIALIZABLE` while inner is `DEFAULT`, inner may use the database's default isolation level.

### 5.3. `timeoutString` and Placeholders

When configuring seconds via a property, use:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeoutString = "${app.tx.inner-timeout-seconds:5}"
)
public void runInnerJob() {
    // Timeout from property; default 5 seconds.
}
```

`timeoutString` accepts a **string of integer seconds** supporting placeholder resolution, not a `Duration` with units like `ms` or `PT5S`. Do not declare both `timeout` and `timeoutString` on the same annotation. The property can live in `application.properties`:

```properties
app.tx.inner-timeout-seconds=8
```

This is an **alternative** configuration option to `timeout=5` in the example above and does not need to be added to the hands-on project in Section 8.

### 5.4. Read-Only and Write Permissions

Many systems use `REQUIRES_NEW, readOnly=true` to read inside an independent snapshot transaction. However:

- `readOnly=true` is a hint/transaction metadata; DBs/drivers may interpret it differently.
- A `SELECT` in T2 **does not automatically see** uncommitted `INSERT/UPDATE` operations from T1; T2 is a separate physical transaction.
- If outer needs to read data just committed by inner T2, visibility still depends on isolation, snapshot, and database. Under `READ_COMMITTED` it may be visible on a subsequent query, whereas under `REPEATABLE_READ` or a fixed snapshot you must not assume it is visible.
- If inner T2 attempts to write to rows locked by T1, T2 may block on outer's own lock, leading to deadlock/timeout. Marking read-only does not eliminate all lock contention.

## 6. Rollback Rules and Exception Propagation Between T2 and T1

Spring asks two **independent** questions:

1. Should T2 commit or roll back based on the **inner method's** exception/rollback-only status?
2. What does outer observe when inner returns or throws an exception, and should T1 commit or roll back according to the **outer method's** policy?

### 6.1. Unchecked Exception from T2 Caught by Outer

```java
@Transactional
public void outer() {
    insertOuter();
    try {
        innerService.writeAndFail(); // REQUIRES_NEW, T2 rolls back.
    } catch (IllegalStateException expected) {
        // Error handled; outer can still commit T1.
    }
}
```

This is a **snippet**; `insertOuter`/`innerService` are provided by the application. Unlike `REQUIRED` joining T1, a `REQUIRES_NEW` rollback of T2 **does not mark T1 rollback-only merely because T2 rolled back**.

### 6.2. Unchecked Exception Not Caught by Outer

```java
@Transactional
public void outer() {
    insertOuter();
    innerService.writeAndFail(); // REQUIRES_NEW rolls back T2, throws exception.
    // Does not proceed further.
}
```

The exception continues out of outer, so outer's interceptor also rolls back T1 under the default rule. As a result, **both transactions roll back**, even though they are resource-independent.

### 6.3. Configuring `rollbackFor` for Checked Exceptions

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = java.io.IOException.class
)
public void importInner() throws java.io.IOException {
    // If IOException escapes through the interceptor, T2 rolls back.
}
```

Checked exceptions do not trigger rollback by default in standard Spring configurations; `rollbackFor` makes the intent explicit. You must also consider **outer's annotation** if that exception can escape outer. For example, if T2 rolls back due to `rollbackFor = IOException.class` while outer has no matching declaration, outer's interceptor may commit T1 if the checked `IOException` escapes and outer's rollback rules remain at their defaults. There is no rule saying "because inner rolled back, outer must roll back".

### 6.4. `noRollbackFor` Does Not Mean the Exception Never Occurs

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    noRollbackFor = IllegalArgumentException.class
)
public void saveThenThrow() {
    // Write to DB, then throw IllegalArgumentException.
}
```

This is a snippet. If an exception matching `noRollbackFor` escapes through the inner interceptor, inner may **commit T2 even though the caller receives the exception** (unless the resource/transaction was already marked rollback-only for another reason). However, if outer does not catch this unchecked exception, outer may still roll back T1 according to **outer's own rule**. Thus, an exception being thrown neither implies "every transaction rolled back" nor "no transaction committed".

### 6.5. Marking Rollback-Only Without Throwing an Exception

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void cancelInnerOnly() {
    // After processing, if you do not want to commit T2:
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

This is a snippet; import `org.springframework.transaction.interceptor.TransactionAspectSupport`. If the inner method is intercepted and marks **T2** rollback-only, T2 will roll back at the end of its scope. Outer T1 can continue and commit if no other error occurs. Make it explicit in the API/business contract that inner did not commit; do not return an ambiguous success result.

### 6.6. Why `UnexpectedRollbackException` Differs from REQUIRED

When an inner `REQUIRED` method joins T1 and marks the physical transaction rollback-only, outer can receive `UnexpectedRollbackException` when it expects to commit. By contrast, when inner `REQUIRES_NEW` rolls back T2 separately and outer **catches the exception**, T1 is not automatically marked rollback-only just because T2 failed. Therefore, you should not assume outer will receive `UnexpectedRollbackException` in this case.

Even so, `UnexpectedRollbackException` **can** still come from the manager if T1 was marked rollback-only for **another reason**, or if an error occurred during commit. Do not treat the annotation as a guarantee that "no exception can ever occur".

## 7. Why T2 Committing Can Still Pose Consistency Risks

`REQUIRES_NEW` fits when a record must survive independently; however, it breaks multi-step atomicity if misused.

Misguided example:

```java
@Transactional
public void transferMoney() {
    debitSourceAccount();             // T1
    paymentRecordService.credit();   // T2, REQUIRES_NEW
    updateLedger();                  // T1, then throws an error
}
```

This is an **illustrative business snippet**. If `credit()` already committed T2 while T1 rolls back, the system can end up with a credit entry while the debit/ledger entries from T1 vanish. The system **is no longer atomic across the business operation**.

If you need "all writes succeed or all roll back" in one database, prefer the **same T1** via `REQUIRED`; do not use `REQUIRES_NEW` just to "make sure the method commits".

Potentially suitable use cases, with careful design:

- Writing an independent **technical audit** even for a failed operation, if the audit does not depend on outer's uncommitted data.
- Recording an independent processing attempt log for operations tracking, accepting that an outer rollback still leaves the attempt history.
- A small independent transaction with clear locking, resource boundaries, and business contract.

Use cases that are **not automatically suitable**:

- Writing the other half of the same money transfer.
- Writing an outbox event in T2 while the corresponding business state change is in T1: the outbox can commit and be published while the T1 business change rolls back.
- Trying to hide errors in a large transaction by forcing every inner method to `REQUIRES_NEW`.
- Writing to a row currently locked by T1 and waiting for T2 to finish.

## 8. Complete Hands-On Project: Independent Commit/Rollback and T2 Attributes

**Goal:** runnable with Java 17, Maven, Spring Boot 3.5.7, JDBC, and H2. The `tx_log` table uses distinct IDs per case; each case is invoked when the runner has **no outer enclosing transaction**. That lets us accurately observe the boundaries created by the service methods.

We verify:

1. **T2 commits, T1 rolls back** -> only the inner row remains.
2. **T2 rolls back, T1 commits** when outer catches the exception -> only the outer rows remain.
3. **T2 rolls back, exception propagates to outer** -> both roll back.
4. **Inner uses REQUIRED instead of REQUIRES_NEW** -> both rows share T1 and roll back with outer.
5. **Self-invocation** to a method annotated `REQUIRES_NEW` in the same bean -> the inner annotation does not create T2 in proxy mode.
6. **New attributes of T2:** outer has read-only false / isolation READ_COMMITTED; inner has read-only true / isolation SERIALIZABLE; after inner, outer's flags are restored. T2's timeout is declared, though **we do not force the demo to run a slow query to guess exact timeout timing**.

### 8.1. Directory Structure

```text
requires-new-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/requiresnew/
        │       ├── RequiresNewApplication.java
        │       ├── OuterService.java
        │       └── InnerService.java
        └── resources/
            └── application.properties
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>requires-new-demo</artifactId>
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

The JDBC starter brings in `JdbcTemplate`, transaction management, and HikariCP in common configurations; `h2` is the in-memory JDBC driver/database.

### 8.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:requires_new_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Sequential T1 + T2 demo: pool has spare connections.
spring.datasource.hikari.maximum-pool-size=5
```

Sizing enough connections is important: when outer T1 holds a connection and inner T2 needs another connection, a pool with only one connection can force T2 to wait until connection-acquisition timeout, or cause a pool-level deadlock when multiple threads wait simultaneously.

### 8.4. `src/main/java/vn/example/requiresnew/InnerService.java`

```java
package vn.example.requiresnew;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {

    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void commitNew(int id) {
        insert(id, "inner-committed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void rollbackNew(int id) {
        insert(id, "inner-rolled-back");
        throw new IllegalStateException("Inner T2 failed");
    }

    @Transactional
    public void joinRequired(int id) {
        insert(id, "inner-required");
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE,
        timeout = 5,
        readOnly = true
    )
    public String ownAttributes() {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();
        boolean readOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        Integer isolation =
            TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

        boolean serializable = Objects.equals(
            isolation, Connection.TRANSACTION_SERIALIZABLE
        );

        // Do not write data in a read-only transaction.
        jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_log", Integer.class
        );

        return "inner-active=" + active
            + ",inner-readOnly=" + readOnly
            + ",inner-serializable=" + serializable;
    }

    private void insert(int id, String tag) {
        jdbc.update(
            "INSERT INTO tx_log(id, tag) VALUES (?, ?)",
            id, tag
        );
    }
}
```

Explanation:

- `commitNew` and `rollbackNew` can commit/roll back T2 independently because callers invoke them through the proxy of a **separate bean**.
- `joinRequired` serves as the control: it does not open T2 when outer T1 already exists.
- `ownAttributes` creates a **new** T2 with `readOnly=true`, `isolation=SERIALIZABLE`, `timeout=5`. It inspects Spring's transaction active status and flags, performing a harmless `SELECT`; there is no DML inside the read-only transaction.
- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` reflects Spring-managed metadata, **not proof that the database forbids writes**.
- `Objects.equals(isolation, Connection.TRANSACTION_SERIALIZABLE)` compares the corresponding Spring/JDBC isolation code. In this demo the manager is able to set the requested isolation; do not assume every database supports all levels identically.

### 8.5. `src/main/java/vn/example/requiresnew/OuterService.java`

```java
package vn.example.requiresnew;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OuterService {

    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void outerRollbackInnerCommit() {
        insert(101, "outer-rollback");
        inner.commitNew(102); // T2 commit completes.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional
    public void outerCommitInnerRollback() {
        insert(201, "outer-before");
        try {
            inner.rollbackNew(202); // T2 rolls back then throws error.
        } catch (IllegalStateException expected) {
            // T2 error was handled by outer.
        }
        insert(203, "outer-after");
        // T1 ends normally and can commit.
    }

    @Transactional
    public void outerRollbackWhenInnerExceptionEscapes() {
        insert(301, "outer-uncaught");
        inner.rollbackNew(302); // T2 rolls back; exception continues out to outer.
    }

    @Transactional
    public void outerRollbackWithRequired() {
        insert(401, "outer-required");
        inner.joinRequired(402); // Joins T1 itself.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional
    public void outerRollbackWithSelfInvocation() {
        insert(501, "outer-self");
        selfRequiresNew(502); // this.method(): bypasses proxy.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void selfRequiresNew(int id) {
        insert(id, "inner-self");
    }

    @Transactional(isolation = Isolation.READ_COMMITTED, timeout = 20)
    public String inspectAttributes() {
        boolean outerBeforeReadOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();

        String inside = inner.ownAttributes(); // Independent T2.

        boolean outerAfterReadOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        boolean outerReadCommitted = Objects.equals(
            TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel(),
            Connection.TRANSACTION_READ_COMMITTED
        );

        return "outer-before-readOnly=" + outerBeforeReadOnly
            + "\n" + inside
            + "\nouter-after-readOnly=" + outerAfterReadOnly
            + "\nouter-read-committed=" + outerReadCommitted;
    }

    private void insert(int id, String tag) {
        jdbc.update(
            "INSERT INTO tx_log(id, tag) VALUES (?, ?)",
            id, tag
        );
    }
}
```

Key characteristics:

- Each case uses distinct IDs: 101/102, 201/202/203, 301/302, 401/402, 501/502, avoiding key collisions across runs.
- Outer methods are public and invoked by the runner through the **Spring bean proxy**.
- `OuterService` injects `InnerService` via its constructor, so inner calls go through another bean and can run transaction advice.
- `selfRequiresNew` resides on the **same target** as the caller; calling `selfRequiresNew(502)` does not create transaction T2 even though the method is annotated.
- `inspectAttributes` intentionally executes no DML writes, allowing inner to use its own SERIALIZABLE/read-only settings without lock contention from T1. It only checks isolation/readOnly flags and does not run a slow query to test timeout.

### 8.6. `src/main/java/vn/example/requiresnew/RequiresNewApplication.java`

```java
package vn.example.requiresnew;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class RequiresNewApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequiresNewApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_log (" +
                "id INT PRIMARY KEY, tag VARCHAR(40) NOT NULL)"
            );

            expectOuterFailure(outer::outerRollbackInnerCommit);
            System.out.printf("innerCommit_outerRollback=%d,%d%n",
                count(jdbc, 101), count(jdbc, 102));

            outer.outerCommitInnerRollback();
            System.out.printf("innerRollback_outerCommit=%d,%d,%d%n",
                count(jdbc, 201), count(jdbc, 202), count(jdbc, 203));

            expectOuterFailure(
                outer::outerRollbackWhenInnerExceptionEscapes
            );
            System.out.printf("uncaughtException=%d,%d%n",
                count(jdbc, 301), count(jdbc, 302));

            expectOuterFailure(outer::outerRollbackWithRequired);
            System.out.printf("requiredSameTx=%d,%d%n",
                count(jdbc, 401), count(jdbc, 402));

            expectOuterFailure(outer::outerRollbackWithSelfInvocation);
            System.out.printf("selfInvocation=%d,%d%n",
                count(jdbc, 501), count(jdbc, 502));

            System.out.println(outer.inspectAttributes());
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_log WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectOuterFailure(Runnable call) {
        try {
            call.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("Expected simulated failure");
    }
}
```

Explicitly configuring `JdbcTransactionManager` for the same `DataSource` used by `JdbcTemplate`. `@EnableTransactionManagement(proxyTargetClass = true)` ensures results do not depend on an implicit environment proxy-type choice. The runner is an external caller created by Spring after context initialization and does not open a transaction around the entire runner; thus each outer call starts its own T1. Table creation runs before the test cases.

### 8.7. Running and Verifying stdout

From the `requires-new-demo` directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/requires-new-demo-1.0.0.jar
```

The lines **printed by the demo code itself**, in order, under the configuration above are:

```text
innerCommit_outerRollback=0,1
innerRollback_outerCommit=1,0,1
uncaughtException=0,0
requiredSameTx=0,0
selfInvocation=0,0
outer-before-readOnly=false
inner-active=true,inner-readOnly=true,inner-serializable=true
outer-after-readOnly=false
outer-read-committed=true
```

Spring Boot startup logs may appear on other lines. The output above **excludes** those logs. The test relies on transactional JDBC/H2 and `@Transactional` intercepted by Spring proxies. If you change the database, transaction manager, isolation support, or test lifecycle, verify again before expecting identical output.

### 8.8. Explaining Results and Commit Timing

| Case | Rows present | Why |
| --- | --- | --- |
| `innerCommit_outerRollback=0,1` | 101 absent; 102 present | T2 wrote and committed 102, then T1 threw an error and rolled back 101. |
| `innerRollback_outerCommit=1,0,1` | 201,203 present; 202 absent | T2 rolled back 202; outer caught the error, so T1 still committed its two inserts. |
| `uncaughtException=0,0` | 301,302 both absent | T2 rolled back on error; the error propagated to outer, so T1 also rolled back under outer's rule. |
| `requiredSameTx=0,0` | 401,402 both absent | Inner `REQUIRED` joined T1 with no T2; outer rolled back both. |
| `selfInvocation=0,0` | 501,502 both absent | The internal call bypassed the inner method's proxy, so write 502 remained in T1. |
| `outer-before-readOnly=false` | Outer flag false | T1 was created with default readOnly false. |
| `inner-readOnly=true,inner-serializable=true` | Separate T2 flags | Inner was intercepted with `REQUIRES_NEW` and its explicit attributes. |
| `outer-after-readOnly=false` | T1 flag restored | After T2, the thread/transaction context returned to T1. |
| `outer-read-committed=true` | Outer isolation intact | T1 used `READ_COMMITTED` and was not replaced by T2's `SERIALIZABLE`. |

**Important:** `inner-active=true` only confirms T2 has an active transaction on the thread during the method. The strongest proof of **independent commit** is that row **102 remains after outer 101 rolls back**, not just an active flag.

### 8.9. Why Doesn't the Demo Use `Thread.sleep` to Test Timeout?

`@Transactional(timeout = 5)` is a transaction deadline applied through the transaction manager/resource, **not a Java thread interrupt timer**. `Thread.sleep(7000)` inside a method does not prove the DB actually cancels the transaction at second 5. With JDBC, Spring can apply the remaining transaction timeout to `Statement` objects via `JdbcTemplate`; the database/driver determines how queries are timed out or interrupted. To verify real timeout behavior, write an integration test with a controlled slow query or lock wait against the target database/driver, and verify rollback, exception, and resource release.

### 8.10. When Changing Configuration in Real Runs

In real application code, transaction boundaries must be verified against the actual Spring version, manager, and configuration. For instance, replacing `JdbcTransactionManager` with `JpaTransactionManager` introduces JPA's resource/flush/isolation semantics; do not assume an H2/JDBC demo proves identical behavior across every stack. Additionally, if a test method already has a transaction opened by Spring TestContext before calling outer, there may be an **extra transaction** from the test itself; separate the test transaction from service transactions when evaluating behavior.

## 9. Suspended Resources and Connection Pool Risks

`REQUIRES_NEW` does not "reuse T1 and commit early". With JDBC on the same DataSource, typically:

- Outer T1 acquires connection `C1` and holds it for as long as T1 remains alive.
- When inner needs T2, Spring suspends T1's resources, yet **C1 still belongs to T1** and is not returned to the pool as an idle connection.
- Inner T2 acquires a separate connection `C2` to read/write and commit/roll back.
- After T2 finishes, `C2` is returned to the pool and Spring resumes T1 with `C1`.

```text
Thread A:
  T1: C1 [held -----------------------------------]
          |
          | suspend T1
          v
  T2:     C2 [begin -> work -> commit/rollback]
          |
          v
  resume T1 with C1 -> T1 commit/rollback
```

If concurrent threads each hold C1 and wait for C2 while the pool runs out of connections, the system can **stall on the pool**. Spring documentation recommends avoiding `REQUIRES_NEW` if the pool is not sized adequately; a minimum guideline for typical cases is a pool **larger than the number of concurrent threads by at least one connection**. In practice you must account for nesting depth, other connections in use, HikariCP `maximumPoolSize`/`connectionTimeout`, long-running transactions, and peak load.

### Lock Deadlock with T1

Suppose T1 has executed `UPDATE accounts SET ... WHERE id = 1` without committing yet; C1 holds the lock. In the same call stack, T2 on C2 tries to update the **same row id=1** and must wait for T1's lock. Yet T1 is **waiting for method T2 to return** before continuing. That situation easily causes a deadlock or lock timeout even when the code runs sequentially on a single thread.

**Recommendation:** with `REQUIRES_NEW`, prefer independent resources/records not locked by T1. Do not make inner update the same "currently uncommitted outer row" and expect T2 to always finish quickly.

### Visibility of Uncommitted Data

T2 is a separate transaction; typically under `READ_COMMITTED`, it **does not see** T1's uncommitted rows/writes. Therefore, an audit in T2 should not reference a foreign key to a row that T1 **just inserted without committing**, unless you have verified database constraints and designed appropriate handling; T2 may fail, block on locks, or not find that row.

Conversely, after T2 commits, whether T1 can read the row T2 just wrote depends on T1's isolation/snapshot. Avoid promising "outer can always read inner's commit immediately" across all databases and isolation levels.

## 10. Choosing REQUIRES_NEW vs. REQUIRED/NESTED?

| Criterion | `REQUIRED` | `REQUIRES_NEW` | `NESTED` |
| --- | --- | --- | --- |
| When outer T1 exists | Joins T1 | Suspends T1, creates T2 | Usually creates a savepoint on T1 |
| Number of physical transactions | One | Two (T1, T2) | One |
| Can inner commit before outer? | No | **Yes** | No — a savepoint is not an independent commit |
| Outer rollback after inner "succeeds" | Inner data rolls back with T1 | Inner T2 data persists if T2 committed | Inner data rolls back with T1 |
| Inner rolls back while outer continues | Can mark T1 rollback-only | Possible, if outer handles the error properly | Can roll back to savepoint if supported |
| Own isolation/timeout/readOnly | No new transaction to apply separately | Can be applied separately to T2 | Mostly uses T1's properties |
| Connections/locks | Usually uses one connection | Usually needs an extra connection | Usually same connection, uses savepoint |
| Use for | One atomic business unit in the same DB | Work that **needs independent commit/rollback** | Partial rollback within the same physical transaction |

Note: `NESTED` depends on JDBC savepoint support and the transaction manager; do not assume all JPA/reactive/data stores support it identically. If independent commit is not needed, `NESTED` may make more sense than `REQUIRES_NEW` for a partially rollbackable step, but verify on your stack.

## 11. Common Mistakes When Using REQUIRES_NEW

### 11.1. Assuming a Same-Bean Self-Call Creates T2

```java
@Transactional
public void outer() {
    inner(); // Does not go through proxy in Spring AOP proxy mode.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
}
```

This is a **snippet**. The clearest fix is usually to move `inner()` to another bean and inject it, or use `TransactionTemplate` explicitly when appropriate. Do not default to recommending bypassing via `AopContext.currentProxy()`, as it increases coupling and imposes configuration constraints.

### 11.2. Inner Rolls Back While the Exception Still Escapes to Outer

If T2 rolls back and an unchecked exception escapes to outer, T1 can still roll back because the **outer interceptor also sees the exception**. Transaction independence does not mean control-flow/exception independence. For outer to continue, you must deliberately catch and handle the error in outer, then verify state/ensure business validity.

### 11.3. Assuming T2's Attributes Alter T1's Attributes

Inner `REQUIRES_NEW(readOnly=true)` does not turn T1 read-only. Inner `SERIALIZABLE` does not raise T1's isolation; T2's timeout does not reset or shorten T1's timeout. When T2 finishes, Spring restores T1's context.

### 11.4. Assuming `readOnly` Blocks Every `INSERT`

`@Transactional(readOnly = true)` is not a substitute for a read-only database account, SQL security rules, or ACLs. Use real database privileges and business validation; do not rely on a hint to enforce security.

### 11.5. Leaving the Pool with Only One Connection

T1 holds a connection, and T2 needs another. A pool size of 1 commonly leads to waiting for a connection until timeout. If the application handles concurrent requests, sizing must consider concurrency and nesting depth, not just a sequential demo test.

### 11.6. Writing the Same Row Locked by T1

T2 cannot borrow T1's lock because they are two physical transactions. T1 waiting on T2 while T2 waits on T1's lock can hang the operation until deadlock/timeout.

### 11.7. "Independent Outbox" with the Wrong Boundary

If the business update is in T1 while the outbox row is in T2, the outbox can commit and publish a message **even when T1 rolls back**. For a transactional outbox tied to the same business action, the outbox record must commit/roll back in the **same transaction** as the business state. Using `REQUIRES_NEW` for an outbox is not an automatic fix.

### 11.8. Tests with an Enclosing `@Transactional`

Spring TestContext may open a test-managed transaction before calling the service. In that case, `REQUIRES_NEW` on the service creates T2 and commits independently, while the test-managed T1 may roll back at the end of the test. Reading state inside the same test context/connection can easily mislead you. Design tests without an outer test transaction, or carefully control the test transaction when asserting independent commits.

### 11.9. Two DataSources Without the Same Manager

One method using `ordersTransactionManager` and inner using `auditTransactionManager` can also commit/roll back independently, yet that is **not necessarily** a suspend/resume of T1 on the same manager. To describe it accurately, identify the manager, datasource, and transaction context of each resource. Two local managers do not automatically form XA/2PC.

### 11.10. Async and HTTP Do Not Automatically Join T1/T2

`@Async`/another thread does not automatically carry ThreadLocal transaction context from the caller in the imperative model. Calling a microservice over HTTP does not share a JDBC physical transaction either. `REQUIRES_NEW` only applies within the transaction management of the relevant resources/managers; it does not distribute transactions across the network.

## 12. Properly Testing Commit, Rollback, and T2 Attributes

A reliable integration test should inspect **database state after both outer and inner finish**, not merely whether an exception occurred.

### Test A — T2 Commit Survives T1 Rollback

1. Start from a clean state.
2. Invoke the outer method through its proxy; outer writes O and inner `REQUIRES_NEW` writes I.
3. Outer throws an unchecked exception, causing T1 to roll back.
4. Read the DB using a new connection/transaction: O is **absent**, I is **present**.
5. Checking only `isActualTransactionActive()` inside inner is insufficient to prove T2 is truly independent.

### Test B — T2 Rollback Does Not Make Outer Rollback-Only

1. Outer starts T1 and writes O1.
2. Inner starts T2, writes I, and throws `RuntimeException`.
3. Inner interceptor rolls back T2; outer properly **catches** the exception and writes O2.
4. Outer completes normally; read the DB: O1/O2 are **present**, I is **absent**.
5. If an unexpected `UnexpectedRollbackException` occurs, investigate whether T1 became rollback-only for another reason or whether inner did not actually go through the proxy.

### Test C — Propagating Exception Also Rolls Back Outer

1. Outer writes O; inner T2 writes I and then fails.
2. Outer **does not catch** the exception.
3. T2 rolls back; outer interceptor sees the exception and rolls back T1.
4. Both O and I are **absent**, yet these are two independent rollbacks.

### Test D — Ability to Set Separate Isolation/ReadOnly/Timeout

1. Outer T1 configures `READ_COMMITTED`, `timeout=20`, `readOnly=false`.
2. Inner T2 `REQUIRES_NEW` configures `SERIALIZABLE`, `timeout=5`, `readOnly=true`.
3. Inspect transaction metadata/`TransactionSynchronizationManager` in each scope and verify outer restoration after inner.
4. To verify real timeout enforcement, use a controlled query on a real database/Testcontainers and check exception/rollback/resource release, rather than sleeping the CPU thread.
5. Do not test writing data in a read-only inner transaction to "prove it is always forbidden": that behavior depends on the DB/driver.

### Test E — Proxy and Connection Pool

1. Place inner in a separate bean and inject via the container; compare against self-invocation.
2. Monitor active/pending pool connections when outer/inner are nested.
3. Simulate concurrency within safe bounds, avoiding destructive load on production.
4. Test what happens if outer holds a lock and inner tries to access the same row, ensuring clear timeout/retry policies and no unbounded deadlock.

### Distinguishing Output Correctness from Demo Limitations

H2 is great for learning transaction boundaries; however, isolation semantics, locking, read-only handling, and SQL errors can differ from PostgreSQL/MySQL/Oracle. Therefore, critical integration tests should run on the exact database/driver/version used in production. In tests where `@Transactional` is on the test method, prefer tests without a test-managed transaction or understand `TestTransaction` thoroughly when observing independent commits.

## 13. Frequently Asked Questions

**Q:** Inner `REQUIRES_NEW` commits and then outer rolls back; does Spring automatically roll back T2?

**A:** **No**. T2 has already committed as a separate physical transaction. Rolling back outer T1 does not revert T2's changes.

**Q:** Inner `REQUIRES_NEW` rolls back; does outer become rollback-only?

**A:** **Not directly from T2's rollback**. However, if an unchecked exception from inner escapes to outer, outer's interceptor may roll back T1 under its own rollback rules.

**Q:** Does `REQUIRES_NEW` mean spawning a new thread?

**A:** **No**. It usually still runs on the same calling thread; transaction resources are suspended/resumed and T2 uses a separate transaction/connection. It does not mean `@Async`.

**Q:** Does inner `REQUIRES_NEW` have to switch to a different DataSource?

**A:** **No**. It can use the same DataSource with a **different connection**; the transaction manager must manage resources properly. Sharing the same JDBC URL does not mean sharing the same physical transaction.

**Q:** If outer has no transaction, does `REQUIRES_NEW` still take effect?

**A:** Yes. It requests starting a new transaction, though because there is no T1, there is no suspend step.

**Q:** Is outer's isolation level automatically applied to inner?

**A:** **Not inherited in the sense of joining T1**. T2 uses its own transaction definition; if `isolation=DEFAULT`, it uses the underlying resource's default. If `isolation=SERIALIZABLE` and supported, T2 gets that isolation level.

**Q:** Can an inner `readOnly=true` transaction update data?

**A:** There is no universal answer. It is a hint/flag that each manager/driver/database may enforce differently; do not use it as an authorization mechanism.

**Q:** Should `REQUIRES_NEW` be used for every audit method?

**A:** Only when the audit record is allowed to exist independently, does not require T1's uncommitted data, and does not cause lock/pool issues. Business-coupled audits or outbox records should usually stay in the same transaction as the business state.

**Q:** Inner already has `REQUIRES_NEW` yet its row still rolls back with outer—why?

**A:** Check self-invocation, proxy type/method visibility, beans created outside Spring, transaction manager, exception handling, and how the test reads results. The presence of the annotation does not prove the interceptor ran.

## 14. Checklist When Designing REQUIRES_NEW

- [ ] Distinguished **physical T1/T2** from logical scopes.
- [ ] Inner genuinely needs **independent commit/rollback**; shared atomicity with the same business action is not required.
- [ ] The inner method is called through a **Spring proxy** with transaction advice; not `this.method()`.
- [ ] Transaction manager/DataSource are clearly configured, and resources actually support suspend/new transaction.
- [ ] Distinguished between inner rollback and whether the exception propagates out to outer.
- [ ] Designed `rollbackFor`, `noRollbackFor`, and `setRollbackOnly()` according to the business contract.
- [ ] Checked isolation, timeout, and readOnly of the **new T2**, without assuming inheritance from T1.
- [ ] Did not treat `readOnly` as a security guarantee or transaction timeout as a thread timer.
- [ ] Sized the connection pool sufficiently when T1 holds C1 and T2 needs C2; added monitoring/wait timeouts.
- [ ] Avoided inner updating rows/resources already locked by outer T1.
- [ ] Did not place outbox messages in T2 when related business state lives in T1.
- [ ] Tested all four commit/rollback combinations against database state after completion.
- [ ] Tested both when the exception escapes to outer and when outer catches the exception.
- [ ] Prevented test-framework-managed outer transactions from obscuring the boundary under test.
- [ ] Re-ran integration tests and checked actual transaction manager behavior when changing DB/driver/framework.

## 15. Exercises and Self-Check

**Exercise 1:** In the project, replace `inner.commitNew(102)` with `inner.joinRequired(102)`. If outer still throws `IllegalStateException`, will row 102 exist?

**Answer:** No. `joinRequired` joins T1; outer rolling back T1 reverts all changes from the inner `REQUIRED` call. Note that the IDs and descriptions are merely illustrative for the test cases.

**Exercise 2:** In `outerCommitInnerRollback()`, remove the `try/catch` around `inner.rollbackNew(202)` and let the exception propagate. What happens to rows 201/202/203?

**Answer:** 201 rolls back because the error escapes outer; 202 rolls back in T2; 203 is never inserted because execution never reaches that line. This is due to exception propagation, not because T1 shared a physical transaction with T2.

**Exercise 3:** Inner `REQUIRES_NEW` has `timeout=5` and `readOnly=true`, while outer `REQUIRED` has `timeout=30` and `readOnly=false`. When T2 finishes, does outer become read-only?

**Answer:** No. T1 is resumed with its own metadata/resources; T2 has its own separate attributes.

**Exercise 4:** Why is a pool with `maximumPoolSize=1` dangerous when T1 calls T2?

**Answer:** T1 holds the first connection; T2 needs another connection, but the pool has none left, potentially waiting until connection-acquisition timeout or stalling when multiple threads are in this state.

**Exercise 5:** T2 commits a shipment record, while T1 rolls back the order. Is the overall business outcome atomic?

**Answer:** No. That is precisely the independent-commit nature of `REQUIRES_NEW`; if shipment depends on the order, redesign the transaction boundaries.

## Official Documentation

- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): official description of `REQUIRED`, `REQUIRES_NEW`, and `NESTED`, physical transaction independence, rollback status, isolation/timeout/readOnly, and connection pools.
- [Spring Framework Reference — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `propagation`, `isolation`, `timeout`, `readOnly`, `rollbackFor`, and `noRollbackFor` attributes.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): interceptors, transaction managers, and transaction boundaries.
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation, JDK/class proxies, and interception limits.
- [Spring Framework — `DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC local transactions and resource management.
- [Spring Framework — `JdbcTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): the transaction manager used in the example.
- [Spring Framework Reference — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): pitfalls of test-managed transactions.

**Core Summary:** `REQUIRES_NEW` creates a **separate physical transaction T2** when the call is handled by Spring transaction advice. T2 can **commit even if T1 rolls back** and **roll back even if T1 commits**; however, an exception propagating from inner to outer can still cause outer to roll back. T2's isolation, timeout, and readOnly are attributes of the **new transaction** and do not modify T1's settings. This independence brings power, but demands deliberate design for business atomicity, locks, and connection pools.
