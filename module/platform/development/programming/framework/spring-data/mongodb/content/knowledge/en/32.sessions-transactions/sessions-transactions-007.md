# Rollback, Exceptions, and Commit Timing

> **Chapter:** Sessions and Transactions  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and interact with MongoDB via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objectives:** Understand exactly when a transaction starts, when MongoDB commits/aborts, which exceptions cause Spring to roll back, why `catch`/self-invocation causes unintended commits, how to use `rollbackFor`/`setRollbackOnly` and `TransactionTemplate`; handle unknown commit errors, safe retries, external side effects outside the database, and testing with a MongoDB replica set.

## 1. Problem: Method Returning Does Not Mean Committed

Suppose an application needs two writes when approving an order:

1. Transition the order state from `PENDING` to `APPROVED`.
2. Insert an `OrderApproved` outbox event for another system to process later.

If both operations must **succeed together or take no effect**, a transaction is an appropriate tool. However, developers often misunderstand:

~~~java
@Transactional
public void approveOrder(String orderId) {
    updateOrder(orderId);
    insertOutboxEvent(orderId);
    // Reaching here means committed? NOT NECESSARILY.
}
~~~

When the method is called **through a Spring transactional proxy**, the typical flow is:

~~~mermaid
flowchart TD
    A["Caller invokes @Transactional proxy"] --> B["Spring opens session and starts transaction"]
    B --> C["Execute business method"]
    C --> D{"How does method exit?"}
    D -->|"Normal return"| E["Spring requests commit"]
    D -->|"Exception matching rollback rule"| F["Spring requests rollback/abort"]
    D -->|"Checked exception not rolling back by default"| E
    E --> G{"commitTransaction succeeded?"}
    G -->|"Yes"| H["Proxy returns success to caller"]
    G -->|"No / outcome unknown"| I["Proxy throws error or unknown state"]
    F --> J["Proxy throws original or rollback error"]
~~~

**Key point:** the end of the method body finishes **before the transaction interceptor performs commit**. If commit fails, an exception can be thrown **after the method body has returned**, yet the caller never receives a successful call through the proxy.

### 1.1. Separating Three Concepts

| Concept | Meaning |
| --- | --- |
| **Application method returned** | Business code reached `return`; the transaction has not necessarily finished committing |
| **Commit acknowledged** | MongoDB has acknowledged `commitTransaction` per the active write concern/transaction options |
| **Business workflow complete** | Beyond MongoDB, events may still need publishing, payment gateway calls, reconciliation, or notifications |

Never treat a `"method finished"` log as proof the transaction committed, nor assume MongoDB transactions roll back sent emails, HTTP requests, or published messages.

## 2. What Does Rollback Mean in MongoDB?

When using a multi-document transaction, MongoDB groups read/write operations into **one transactional session**.

- **Commit:** writes inside the transaction are applied as a single atomic unit.
- **Abort:** uncommitted changes in the transaction never become committed state.
- **Replica set failover rollback:** a replication event distinct from application-initiated transaction abort; commit write concern affects result durability.

### 2.1. Atomicity Differs from Durability

A transaction can **commit atomically** across multiple documents, yet survival across a primary crash depends on the commit write concern. If commit is acknowledged only with `w:1`, an acknowledged transaction can still face failover rollback if the commit has not reached a majority.

**Hence two questions are required:**

- Do the operations commit/abort together? -> **Transaction atomicity**.
- After ACK, what protection does data have against failover/crash? -> **Commit write concern**.

### 2.2. Transactions Are Not Needed in Every Case

MongoDB supports atomicity for a **single document**. If a workflow only changes one order's state:

~~~javascript
db.orders.updateOne(
  { _id: "o701", state: "PENDING" },
  { $set: { state: "APPROVED" } }
);
~~~

a single-document operation with a state predicate is usually simpler than a multi-document transaction. When you must update an order **and** insert an outbox entry across two collections together, a transaction expresses one consistent boundary.

### 2.3. Do Not Equate Abort with "Manually Deleting Each Record"

When a transaction aborts, the application **does not need to undo** inserts/updates manually via a list of `delete`/`update` statements. Building manual compensation inside the same database when a transaction already provides atomicity risks deleting someone else's data or overwriting concurrent changes.

Compensation/saga is only needed across **multiple independent systems** or business workflows that cannot fit inside a single MongoDB transaction.

## 3. Prerequisites for Using Transactions

The following examples require MongoDB in a transaction-capable topology, commonly:

- A **replica set** with an active primary; or
- A **sharded cluster** meeting transaction requirements for your version.

A standalone MongoDB server does not support multi-document transactions under the replica set transaction mechanism. In dev/test, you can run a **single-node replica set** to verify commit/abort behavior; testing real failover requires multiple nodes.

### 3.1. Checking Topology in `mongosh`

On a test database:

~~~javascript
db.adminCommand({ hello: 1 });
// A replica set typically returns setName and isWritablePrimary.
~~~

This command only identifies the deployment. Never use admin privileges or run `rs.stepDown()` on a shared cluster just to test rollback.

### 3.2. Transaction Session

A MongoDB transaction is bound to a **`ClientSession`**. Operations must execute on that same session/transaction and a connection matching the database factory used by Spring Data.

~~~text
ClientSession S1
    +-- startTransaction
    +-- update orders
    +-- insert outbox
    +-- commitTransaction / abortTransaction

ClientSession S2
    +-- operations outside transaction S1
~~~

If `update orders` uses a `MongoTemplate` bound to session S1 while `insert outbox` uses a driver/client outside that session, you do **not** have a single transaction covering both.

### 3.3. Read Preference and Transactions

Reads inside a multi-document transaction must obey MongoDB's **primary read** requirement. Never force `secondaryPreferred` onto a transaction assuming you can read arbitrarily from secondaries. A read concern like `SNAPSHOT` has specific semantics inside transactions.

## 4. Learning Fixture: Two Collections and a Business State

Run on a **dedicated test database**, never production:

~~~javascript
use spring_data_mongodb_lab

db.orders_tx_demo_007.insertMany([
  {
    _id: "o701",
    tenant_id: "t01",
    state: "PENDING",
    amount_vnd: NumberLong(450000)
  },
  {
    _id: "o702",
    tenant_id: "t01",
    state: "PENDING",
    amount_vnd: NumberLong(700000)
  },
  {
    _id: "o703",
    tenant_id: "t02",
    state: "PENDING",
    amount_vnd: NumberLong(900000)
  }
]);

// Create outbox collection explicitly before transaction.
db.createCollection("outbox_tx_demo_007");

db.orders_tx_demo_007.createIndex({ tenant_id: 1, state: 1 });
~~~

Fixed IDs are only for initial fixture runs on a clean test collection. Never run `dropDatabase()`/`drop()` in a shared environment. In automated tests, use unique IDs and clean up only your test's own data.

### 4.1. Expected Results

| Scenario | Order After Operation | Outbox After Operation |
| --- | --- | --- |
| Approve o701, commit succeeds | `o701.state=APPROVED` | `OrderApproved(o701)` present |
| Approve o702, then throw unchecked exception | `o702.state=PENDING` | No matching outbox entry |
| Attempt to approve o703 using tenant t01 | `o703.state=PENDING` | No outbox entry |
| Checked exception without rollback config | May still be `APPROVED` | Outbox may still be present |

The last scenario is a warning about **Spring rollback rules**, not a desired business requirement. If a checked exception signals cancellation yet the transaction commits, that is typically a bug in exception-policy design.

## 5. Spring Data MongoDB Entities

### 5.1. Order Document

~~~java
// OrderDocument.java
package com.example.transactions;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_tx_demo_007")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    protected OrderDocument() { }

    public OrderDocument(
            String id, String tenantId,
            String state, long amountVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.state = state;
        this.amountVnd = amountVnd;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
}
~~~

### 5.2. Outbox Event

~~~java
// OutboxEvent.java
package com.example.transactions;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_tx_demo_007")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String eventType;
    private Instant occurredAt;

    protected OutboxEvent() { }

    public OutboxEvent(
            String id, String tenantId,
            String orderId, String eventType,
            Instant occurredAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.eventType = eventType;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
    public String getTenantId() { return tenantId; }
    public String getEventType() { return eventType; }
}
~~~

`@MongoId(FieldType.STRING)` ensures fixture `_id` values stay BSON strings rather than being implicitly converted to `ObjectId` when looking like hex IDs. Fields `tenant_id`/`order_id` map from Java properties when using `MongoOperations` with entity metadata.

### 5.3. Why Need a Stable Outbox ID?

Set the outbox ID such as `order-approved:o701` or a UUID/idempotency key derived from the **unique business event**. If a request/transaction retries, a stable ID detects duplicates instead of inserting identical events under brand-new IDs.

However, a stable ID **does not automatically guarantee exactly-once delivery** to external systems. Outbox publishers and consumers still need idempotency, checkpoints, and error classification.

## 6. Configuring `MongoTransactionManager` and Commit Options

### 6.1. Basic Transaction Manager

~~~java
// MongoTxConfig.java
package com.example.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

`MongoTransactionManager` is the Spring component that manages sessions, start/commit/abort, and binds transactions to thread context for **synchronous `MongoTemplate`/repositories**.

Spring Data MongoDB does not automatically enable transactions for `@Transactional` methods without a matching transaction manager. Use explicit manager names if your application also has JPA/JDBC/Kafka transaction managers.

### 6.2. Explicitly Configuring Majority Commit and Snapshot

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Bean
MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory) {

    TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .readPreference(ReadPreference.primary())
        .writeConcern(WriteConcern.MAJORITY.withJournal(true))
        .build();

    return new MongoTransactionManager(factory, options);
}
~~~

This is an **alternative** to the bean in section 6.1; **do not declare both identically named beans simultaneously**. Adjust transaction options per MongoDB/driver version and operational policy. The commit write concern determines the acknowledgment level for **`commitTransaction`**; do not try to set separate write concerns on individual `insert`/`update` calls inside the transaction.

### 6.3. Same Database Factory Rule

A transaction manager using `MongoDatabaseFactory` A while the service's `MongoTemplate` uses factory B will not enlist those operations in the same transaction. With multiple datasources or `MongoClient` instances:

- Identify which factory/session each template uses.
- Ensure operations needing atomicity share the same managed transaction infrastructure.
- Write integration tests proving both collections roll back together.
- Never assume an annotation alone guarantees a real transaction.

## 7. Service: Updating Order and Writing Outbox in One Transaction

### 7.1. Custom Exception to Signal Conflict

~~~java
// OrderStateConflictException.java
package com.example.transactions;

public class OrderStateConflictException
        extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

This is an **unchecked exception**, so under Spring's default rollback rules it tells the transactional interceptor to **mark rollback**, provided the exception actually exits the method through the proxy.

### 7.2. A Service Eligible to Run Through a Proxy

~~~java
// OrderApprovalService.java
package com.example.transactions;

import java.time.Instant;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApprovalService {
    private final MongoOperations operations;

    public OrderApprovalService(MongoOperations operations) {
        this.operations = operations;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approve(String tenantId, String orderId) {
        applyApproval(tenantId, orderId);
    }

    private void applyApproval(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        Query pending = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        var result = operations.updateFirst(
            pending,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order missing, wrong tenant or not PENDING"
            );
        }

        operations.insert(
            new OutboxEvent(
                "order-approved:" + orderId,
                tenantId,
                orderId,
                "OrderApproved",
                Instant.now()
            )
        );
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approveThenFail(
            String tenantId, String orderId) {
        applyApproval(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated failure before commit"
        );
    }
}
~~~

**Conditions to run properly:** callers inject `OrderApprovalService` and invoke `approve(...)`/`approveThenFail(...)` from **another bean** via the Spring proxy. `applyApproval(...)` is a private helper called **inside** an already-opened transactional method.

### 7.3. Why Use a Conditional `updateFirst`?

The predicate simultaneously requires:

~~~text
_id == orderId
tenant_id == authenticatedTenant
state == PENDING
~~~

It ensures only one workflow transitions a `PENDING` order to `APPROVED`, and prevents tenant t01 from modifying t02's order. `matchedCount == 0` can mean missing ID, wrong tenant, or changed state; your API contract must define the message/HTTP status.

Never do `findById` followed by `save` when concurrency requires "transition only if state is still PENDING" without guards/optimistic locking. Transactions do not replace business predicates.

### 7.4. When There Is No Exception

~~~text
Proxy opens tx T1
  -> update order (inside T1)
  -> insert outbox (inside T1)
  -> approve() returns
  -> Spring commitTransaction(T1)
  -> commit ACK succeeded
Proxy returns to caller
~~~

**Result:** `APPROVED` order and outbox commit together. Once the proxied service call **succeeds after commit**, you have grounds to know the transaction achieved its configured acknowledgment level, though not yet that consumers have processed the message.

### 7.5. When the Method Throws an Unchecked Exception

~~~text
Proxy opens tx T2
  -> update order (inside T2)
  -> insert outbox (inside T2)
  -> throw IllegalStateException
  -> Spring abortTransaction(T2)
Proxy propagates exception to caller
~~~

**Result:** both the order update and outbox insert in T2 are **not committed**. Never manually run a delete on the outbox after catching the exception in the controller.

## 8. Spring's Default Rollback Rules

Under Spring's familiar default rollback rules:

- `RuntimeException` (unchecked) -> **rollback**.
- `Error` -> **rollback**.
- Checked exceptions (`Exception` not extending `RuntimeException`) -> **do not roll back automatically**; the transaction may **commit** when the method throws one.

Some newer Spring versions/configurations allow changing the **application-wide default rollback policy**; thus the table below applies when the project **has not customized default rollback rules**.

| How `@Transactional` Method Exits | Default with Spring Proxy | Expected Outcome |
| --- | --- | --- |
| Normal return | Commit | Writes commit if commit succeeds |
| Throws `IllegalStateException` | Rollback | Writes in transaction are aborted |
| Throws `DuplicateKeyException` | Rollback | Spring Data exceptions are unchecked |
| Throws `DataAccessException` | Rollback | Unchecked exception |
| Throws `Error` | Rollback | Transaction interceptor requests rollback |
| Throws custom checked `BusinessRuleException extends Exception` | **Commits by default** | May commit even though caller receives exception |
| Catches unchecked exception and returns normally | Often commits if transaction remains valid | Failure may be masked; server errors may already have doomed the transaction |
| Calls `setRollbackOnly()` and returns | Rollback | Does not commit even though method returns normally |

### 8.1. Checked Exceptions Easily Create Business Discrepancies

~~~java
// BusinessRuleException.java
package com.example.transactions;

public class BusinessRuleException extends Exception {
    public BusinessRuleException(String message) {
        super(message);
    }
}
~~~

Suppose a service does:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void approveThenThrowChecked(
        String tenantId, String orderId)
        throws BusinessRuleException {

    applyApproval(tenantId, orderId);
    throw new BusinessRuleException(
        "Example checked error"
    );
}
~~~

**Surprise:** without rollback configuration for the checked exception and without a database-level error, Spring may **commit** both the order and the outbox while still throwing the exception to the caller.

This does not mean MongoDB "ignored rollback"; it happened because the **transaction interceptor chose commit per its rollback rules**.

### 8.2. Exception Type, Not Class Name, Determines Default Behavior

Two similarly named classes:

~~~java
class OrderRejectedRuntime extends RuntimeException { }
class OrderRejectedChecked extends Exception { }
~~~

have **different** default rollback behavior. When designing error APIs, classify exceptions intentionally and test actual transaction behavior; never rely on names like `...Failed` or `...Business`.

## 9. `rollbackFor`, `noRollbackFor`, and Explicit Rules

### 9.1. Rolling Back for Checked Exceptions

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void approveThenRollbackChecked(
        String tenantId, String orderId)
        throws BusinessRuleException {

    applyApproval(tenantId, orderId);
    throw new BusinessRuleException(
        "Must abort transaction"
    );
}
~~~

Now a checked exception escaping the transactional proxy causes Spring to **abort** per the explicit rule.

You can use `rollbackFor = Exception.class` for a broader policy, but review its impact: not every checked exception represents a failure requiring rollback. For example, an exception signaling "processed with warnings" might need a different contract.

### 9.2. `noRollbackFor` for Intentional Cases

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    noRollbackFor = NonFatalNotificationException.class
)
public void approveAndReportWarning(
        String tenantId, String orderId) {

    applyApproval(tenantId, orderId);
    throw new NonFatalNotificationException(
        "Notification scheduling was skipped"
    );
}
~~~

Here `NonFatalNotificationException extends RuntimeException` is an application-defined class. With `noRollbackFor`, Spring can **still commit** even though the caller receives the unchecked exception.

**Use only when you genuinely want data committed** and callers understand "writes finished with a business warning." If an operation already marked the transaction **rollback-only** or the MongoDB server aborted the transaction, `noRollbackFor` cannot "save" an uncommittable transaction.

### 9.3. Specific Rules and Precedence

When multiple rollback/no-rollback rules exist, Spring selects the rule **most closely matching** the exception type per transaction attribute resolution. Avoid stacking overlapping class/pattern rules without tests.

Prefer declaring by **class**:

~~~java
rollbackFor = BusinessRuleException.class
~~~

over broad string patterns like `rollbackForClassName = "Exception"`, because string patterns can accidentally match unrelated classes.

## 10. The `try/catch` Trap: Catching Exceptions Yet Committing Anyway

### 10.1. Bad Pattern: Swallowing Errors and Returning Success

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public boolean approveIgnoringFailure(
        String tenantId, String orderId) {
    try {
        applyApproval(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated business failure"
        );
    } catch (IllegalStateException ignored) {
        return false; // Method returns normally to transaction interceptor.
    }
}
~~~

Because the exception **never escapes the method**, the interceptor sees a **normal return** and attempts to commit. For pure Java errors like this example, the transaction remains valid, meaning both order and outbox **get committed** even though the method returns `false`.

### 10.2. Do Not Confuse This with MongoDB Errors That Invalidated the Transaction

If the exception came from the server (write conflict, duplicate, transaction aborted), the session may already be in an uncommittable state. Calling `catch` and returning normally **does not guarantee commit succeeds**; commit may fail or the transaction may already be aborted.

Therefore, do not write a simplistic rule like "catch always commits." The accurate rule is:

> Catching prevents Spring from **seeing an escaping exception**, while commit only succeeds if the transaction and server state still permit committing.

### 10.3. Correct Ways to Handle Errors

If the error must cancel the entire transaction:

~~~java
try {
    applyApproval(tenantId, orderId);
} catch (OrderStateConflictException ex) {
    logBusinessConflict(ex); // safe logging
    throw ex;                // Let interceptor see the error.
}
~~~

Or if translating the exception:

~~~java
try {
    applyApproval(tenantId, orderId);
} catch (OrderStateConflictException ex) {
    throw new ApprovalFailedException("Cannot approve", ex);
}
~~~

`ApprovalFailedException` should be an unchecked exception or listed in `rollbackFor`. Never wrap an unchecked exception in a checked exception and accidentally alter the rollback rule.

### 10.4. Which Boundary Should Catch Errors?

- **Inside the transactional service:** catch only to enrich context and rethrow, or to intentionally mark rollback-only.
- **At the application/controller boundary:** catch exceptions after the proxy has committed/rolled back (or failed commit) and translate into API responses.
- **At the retry/orchestration layer:** classify transient vs unknown outcomes and decide safe retries.

Do not catch `Exception` inside a transactional method without a concrete business reason.

## 11. Marking Rollback-Only When Not Throwing an Exception

Sometimes a service needs to return a business outcome while still wanting to **abort** the transaction. Spring allows marking the active transaction rollback-only.

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional(
    transactionManager = "mongoTransactionManager"
)
public boolean approveOrReturnFalse(
        String tenantId, String orderId) {
    try {
        applyApproval(tenantId, orderId);
        if (requiresCancellation(orderId)) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            return false;
        }
        return true;
    } catch (OrderStateConflictException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
}
~~~

`requiresCancellation(orderId)` is an illustrative business check without an implementation here. When using this pattern, avoid non-rollbackable side effects and inspect transaction status carefully.

### 11.1. Limits of Rollback-Only

`setRollbackOnly()` only works when running inside a **Spring transaction context**. Calling it outside a transaction throws `NoTransactionException` or reports no active transaction status.

If the method runs via a proxy with a **new transaction it owns**, Spring aborts upon return. **When participating in an outer transaction**, marking rollback-only in an inner scope causes the outer scope to fail with `UnexpectedRollbackException` when attempting to commit.

### 11.2. Do Not Treat `false` as Proof of Rollback

An API returning `false` can mean many things:

- Business predicate failed and transaction rolled back.
- Business predicate failed with no writes performed.
- Method swallowed an error and accidentally committed.
- Transaction commit failed after the method returned.

Define explicit contracts and test **database state after the proxy returns** rather than asserting only a boolean.

## 12. `UnexpectedRollbackException` When Multiple Methods Share a Transaction

A common situation: an outer method **catches an error** from an inner method, assuming everything is fine, yet the shared transaction was marked rollback-only.

### 12.1. Two Separate Service Beans

~~~java
@Service
public class InnerApprovalService {
    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void validateAndApprove(String orderId) {
        // MongoDB operations inside the active transaction...
        throw new OrderStateConflictException("Conflict");
    }
}

@Service
public class OuterCheckoutService {
    private final InnerApprovalService inner;

    public OuterCheckoutService(InnerApprovalService inner) {
        this.inner = inner;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void checkout(String orderId) {
        try {
            inner.validateAndApprove(orderId);
        } catch (OrderStateConflictException ignored) {
            // Not rethrown; however, the inner scope already
            // marked the shared transaction rollback-only.
        }

        // Possibly more operations in the same transaction...
    }
}
~~~

With **default `REQUIRED` propagation**:

~~~text
OuterCheckoutService.checkout()
    -> T1 starts
    -> InnerApprovalService.validateAndApprove()
           -> joins T1, does NOT open a new T2
           -> throws RuntimeException
           -> inner interceptor marks T1 rollback-only
    -> outer catches exception, continues
    -> outer method returns normally
    -> outer interceptor tries to commit T1
    -> T1 rolls back, may throw UnexpectedRollbackException
~~~

Spring throws `UnexpectedRollbackException` to prevent callers from believing commit succeeded when the transaction was marked rollback-only in another scope.

### 12.2. When Does `UnexpectedRollbackException` Appear?

It typically appears **at the outer transaction's commit boundary**, after the outer method body returns. At that point:

- The exception thrown by the inner service was already caught.
- Data inside the shared transaction was not committed.
- The outermost caller receives a different exception, typically `UnexpectedRollbackException`.

Never suppress `UnexpectedRollbackException` by arbitrarily weakening rollback rules; fix transaction ownership and error handling instead.

### 12.3. Three Ways to Clarify the Contract

**Option A — error means the workflow must abort:** outer **rethrows** the exception so rollback is explicit.

~~~java
try {
    inner.validateAndApprove(orderId);
} catch (OrderStateConflictException ex) {
    throw ex;
}
~~~

**Option B — inner error is ignorable:** the inner method should not mark the shared transaction rollback-only if outer genuinely expects to commit; return a business result **before performing corrupting writes**, or use a separate transaction scope.

**Option C — independent inner operation:** consider `REQUIRES_NEW` along with its overhead and isolation trade-offs. Do not use it as a Band-Aid when business logic truly needs all-or-nothing atomicity.

## 13. Propagation `REQUIRED`, `REQUIRES_NEW`, and `NESTED`

Spring defines **propagation behavior** for transactional methods. Distinguish Spring propagation from MongoDB's native transaction primitives.

| Propagation | When an Outer Transaction Exists | Consequences to Note |
| --- | --- | --- |
| `REQUIRED` | Joins active transaction | One rollback-only affects the entire transaction |
| `REQUIRES_NEW` | Suspends outer, starts new transaction if infrastructure permits | Inner commits independently of outer; uses extra session/connection resources |
| `SUPPORTS` | Joins if present, otherwise runs non-transactionally | Out-of-transaction writes are not atomic with outer |
| `MANDATORY` | Requires an already-active transaction | Missing outer transaction throws error |
| `NOT_SUPPORTED` | Suspends transaction to run non-transactionally | Writes here do not roll back with outer |
| `NEVER` | Disallows any active transaction | Active transaction throws error |
| `NESTED` | Nested savepoint where supported by infrastructure | **Do not assume MongoDB supports savepoints/nested transactions** |

### 13.1. `REQUIRES_NEW` Is Not a MongoDB Savepoint

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    propagation = Propagation.REQUIRES_NEW
)
public void writeIndependentAudit(...) {
    // New transaction, commits independently if successfully started.
}
~~~

This requires importing `org.springframework.transaction.annotation.Propagation`. Spring can suspend the outer transaction and open a separate session transaction for the inner call.

**Warning:** a new MongoDB transaction consumes another session/connection and can raise contention, especially under load. If inner commits and outer later rolls back, **inner's audit record still persists**. Use this only when independent survival is actually desired.

### 13.2. `NESTED` Is Not a "Mini-Transaction That Rolls Back Alone"

MongoDB does not provide savepoints the way JDBC does. `MongoTransactionManager` does not support `NESTED` via JDBC savepoints by default. If your requirement is:

~~~text
T1: write A
  T_nested: write B
  roll back only B
T1: still commit A
~~~

do not expect `@Transactional(propagation = Propagation.NESTED)` to turn MongoDB into a savepoint engine. Redesign the aggregate, split into independent transactions, or apply controlled saga/compensation.

### 13.3. Do Not Use `REQUIRES_NEW` Within the Same Class Expecting It to Fire

Proxy-based Spring AOP transactions only intercept calls **through the proxy**. If a method calls `this.inner()` within the **same object**, the annotation on `inner()` is bypassed; see the next section.

## 14. Self-Invocation: Annotation Present Yet No Transaction Starts

### 14.1. Bad Pattern

~~~java
@Service
public class OrderFacade {
    public void handle(String tenantId, String orderId) {
        approveInTransaction(tenantId, orderId);
        // Internal call this.approveInTransaction(...)
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void approveInTransaction(
            String tenantId, String orderId) {
        // When called via this from handle(), proxy does not intercept.
    }
}
~~~

If `handle()` is called through the proxy without its own transaction annotation, calling `approveInTransaction()` directly on `this` skips the proxy. Writes inside can run **outside any transaction**, even though `@Transactional` is right there in the source.

### 14.2. Maintainable Fix

Move the transactional method into **another Spring bean** and inject it:

~~~java
@Service
public class OrderFacade {
    private final OrderApprovalService approvalService;

    public OrderFacade(OrderApprovalService approvalService) {
        this.approvalService = approvalService;
    }

    public void handle(String tenantId, String orderId) {
        approvalService.approve(tenantId, orderId);
    }
}
~~~

Or place `@Transactional` on the **public entry point** that actually receives proxied calls. Workarounds like self-injecting a proxy or AspectJ weaving have different trade-offs/configs; do not default to them when splitting beans matches clean responsibilities.

### 14.3. Other Proxy Caveats

- `private`/`final` methods or unproxied classes/methods may not be intercepted; behavior depends on JDK proxies/CGLIB/Spring version.
- Instantiating via `new OrderApprovalService(...)` instead of fetching from the Spring context bypasses the transaction proxy.
- `@Transactional` on code running in **another thread** does not inherit the thread-bound transaction context; never launch `CompletableFuture.runAsync(...)` expecting writes on the new thread to share T1.
- Other interceptors (`@Async`, retry, security) have specific AOP ordering; verify real transaction boundaries with integration tests.

**Never use a unit test calling methods directly on a `new`-ed object to prove transaction annotations work.**

## 15. `TransactionTemplate`: An Explicit Programmatic Option

When you want to wrap a code block in a transaction without relying on proxy self-invocation rules or when you need explicit status control, use `TransactionTemplate` in imperative mode.

### 15.1. Creating a Template from the Manager

~~~java
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticOrderService {
    private final TransactionTemplate tx;
    private final MongoOperations operations;

    public ProgrammaticOrderService(
            MongoTransactionManager transactionManager,
            MongoOperations operations) {
        this.tx = new TransactionTemplate(transactionManager);
        this.operations = operations;
    }

    public boolean approve(String tenantId, String orderId) {
        Boolean result = tx.execute(status -> {
            // Call MongoOperations sharing the same MongoDatabaseFactory.
            Query query = Query.query(
                Criteria.where("id").is(orderId)
                    .and("tenantId").is(tenantId)
                    .and("state").is("PENDING")
            );

            var update = operations.updateFirst(
                query,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            );

            if (update.getMatchedCount() != 1) {
                status.setRollbackOnly();
                return false;
            }

            operations.insert(new OutboxEvent(
                "order-approved:" + orderId,
                tenantId, orderId,
                "OrderApproved",
                Instant.now()
            ));
            return true;
        });

        // commit/rollback occurs inside tx.execute(...)
        // BEFORE this method returns.
        return Boolean.TRUE.equals(result);
    }
}
~~~

To compile, import `java.time.Instant`, `MongoOperations`, `Criteria`, `Query`, and `Update` as in section 7. `TransactionTemplate.execute(...)` manages start/commit/rollback around the callback per configured policy.

### 15.2. Commit Timing of `TransactionTemplate`

~~~text
ProgrammaticOrderService.approve()
   -> tx.execute(callback)
       -> start tx
       -> callback returns true
       -> commitTransaction
   -> tx.execute(...) returns true
   -> approve() returns true
~~~

If commit fails, `tx.execute` **does not** return `true` to the caller; an exception is raised at the commit step before `execute` completes.

### 15.3. When to Choose Declarative vs Programmatic?

| Criterion | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Transaction boundary | Method invoked via proxy | `execute` callback |
| Visibility of start/end points | Less explicit | Immediately clear at the `execute` call |
| Separation from business logic | Less boilerplate | More boilerplate |
| Self-invocation | Prone to proxy trap | Does not rely on method AOP for the callback |
| Rollback-only | `TransactionAspectSupport...` | `status.setRollbackOnly()` |

Both rely on the **same transaction manager and Mongo session**. Choose whichever is clearer to review, easier to test, and fits your architecture — neither is "automatically safer" than the other.

## 16. Commit Timing and HTTP/API Boundaries

### 16.1. When a Controller Calls a Service Through a Proxy

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderApprovalService service;

    public OrderController(OrderApprovalService service) {
        this.service = service;
    }

    @PostMapping("/{id}/approve")
    ResponseEntity<Void> approve(
            @PathVariable String id,
            Authentication authentication) {

        String tenantId = tenantFrom(authentication);
        service.approve(tenantId, id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Here `tenantFrom(authentication)` is a project helper translating the security principal into an authenticated tenant. Authentication logic is omitted here to highlight the transaction boundary.

Execution path:

~~~text
Controller -> transactional proxy -> method body -> commit
                                               |
                                        commit succeeded?
                                               |
                                   Proxy returns to controller
                                               |
                                     HTTP 204 constructed
~~~

With the transaction annotation on the **service**, the controller constructs the success response **only after the proxy has finished committing**. If commit fails, the service call throws an exception and the controller never emits 204.

### 16.2. What If `@Transactional` Sits Directly on the Controller?

Technically configurable, yet keeping transactions on **application services** is strongly preferred over putting them on controllers. Reasons:

- Controllers also handle serialization, HTTP mapping, and request parsing.
- Commit boundaries become harder to review and mix exception/response formatting.
- Slow tasks like external HTTP streaming keep transactions open needlessly.

Never treat `ResponseEntity.ok(...)` constructed **inside a transactional method body** as proof the response was committed/sent: the transaction interceptor commits only after the method creates and returns that object.

### 16.3. Logging `"approved"` Before Commit Is Misleading

~~~java
@Transactional
public void approve(...) {
    applyApproval(...);
    logger.info("Order approved");
}
~~~

That log line runs **before commit**. If commit fails, the log still claims "approved." Use clearer phrasing:

~~~text
Approval changes prepared in transaction
~~~

and log/emit the `committed` metric at the boundary after successful proxy return or inside a `afterCommit` transaction synchronization.

## 17. External Side Effects Outside MongoDB Do Not Roll Back with Transactions

### 17.1. Bad Pattern: Sending HTTP or Email Inside a Transaction

~~~java
@Transactional
public void approveAndNotify(...) {
    applyApproval(...);
    emailSender.sendApprovalEmail(...);
    // MongoDB commit happens only after this.
}
~~~

If the email is sent and MongoDB later aborts/fails commit, the recipient receives an "approved" message while the database never saved that state.

MongoDB **cannot unsend an email or revert a request already processed by a remote API**.

### 17.2. Outbox Pattern

Instead of sending events directly inside the transaction:

~~~text
Transaction T1:
   update orders.state = APPROVED
   insert outbox(OrderApproved)
   commit

Outbox publisher (separate process):
   read committed outbox
   send event
   mark delivered / checkpoint

Consumer:
   process idempotently by eventId
~~~

The order and outbox record commit/abort together. The publisher sees the event only after commit, though **sending** can still occur multiple times if the publisher crashes between send and checkpoint; consumers must deduplicate.

### 17.3. `@TransactionalEventListener(AFTER_COMMIT)`

Spring supports hooks that run after a transaction commits successfully:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCommitListener {
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderApprovedSignal signal) {
        // Runs only after Spring sees successful commit.
        // Not part of the atomic MongoDB transaction.
        notifyLocally(signal);
    }
}
~~~

`OrderApprovedSignal` and `notifyLocally(...)` are illustrative types/helpers. If an event is published inside the transactional service via `ApplicationEventPublisher`, the `AFTER_COMMIT` listener runs per transaction synchronization.

**Do not confuse this hook with a durable outbox:** the process can crash **after commit but before the listener finishes sending**; the listener can fail or re-run when another workflow retries. For critical events, a persisted outbox remains safer.

### 17.4. Writing to MongoDB Inside `AFTER_COMMIT` Requires a New Transaction

Spring notes that right after commit/rollback, transaction resources may still be temporarily bound to the thread during completion callbacks; **never assume DB writes in `AFTER_COMMIT` automatically open and commit a new transaction**.

If a listener truly needs an independent transactional write, call another Spring bean method through a proxy with appropriate propagation such as `REQUIRES_NEW`, and test thoroughly. With an outbox, it is usually cleaner to let a background publisher/worker run outside completion callbacks.

## 18. Commit Errors: Transaction State Can Be *Unknown*

This is the critical difference between:

- **A clear error before commit**, telling the application the transaction was aborted.
- **An error during commit**, leaving the client unsure whether the server committed.

### 18.1. Example: Network Drops Right at Commit

~~~text
Service method:
   update order  -> ok in tx
   insert outbox -> ok in tx
   returns from method body

Spring/driver:
   sends commitTransaction
   MongoDB commits successfully
   CONNECTION DROPS before ACK reaches client

Caller:
   receives exception / timeout
   yet the transaction MAY HAVE COMMITTED.
~~~

**Nothing in a bare network exception proves the transaction aborted.** If the application re-runs the entire business method as a brand-new request, it can cause duplicate side effects or conflicts.

### 18.2. The `UnknownTransactionCommitResult` Error Label

The MongoDB Driver exposes error labels, notably:

- `UnknownTransactionCommitResult`: commit outcome is uncertain; primary action is to **retry commit** per driver/API rules rather than automatically re-running all writes in the transaction.
- `TransientTransactionError`: certain transient errors inside the transaction allow **retrying the entire transaction body** from scratch in a fresh transaction when safe.

These two labels are **not equivalent**. One recommends retrying **commit**, the other recommends retrying the **body**, and both are subject to driver limits/conditions.

### 18.3. Driver Has Retry Logic, Yet the Application Still Needs Design

The MongoDB Java Driver offers convenient transaction APIs and retry logic in applicable scenarios, whereas with manual transactions/Spring transaction managers you must not assume every version retries indefinitely.

You should:

1. Use appropriate MongoDB Java Driver/Spring Data versions.
2. Understand commit retry behavior for your driver/server version.
3. Classify errors at the application boundary instead of blindly doing `catch Exception; retry 3`.
4. Use business idempotency keys on requests.
5. Reconcile persisted state when commit outcomes remain unknown.
6. Enforce finite deadlines/retry counts and metrics to avoid amplifying cluster faults.

### 18.4. Detecting Error Labels in Practice

~~~java
import com.mongodb.MongoException;

public static boolean containsMongoLabel(
        Throwable error, String label) {
    for (Throwable cause = error; cause != null;
            cause = cause.getCause()) {
        if (cause instanceof MongoException mongo
                && mongo.hasErrorLabel(label)) {
            return true;
        }
    }
    return false;
}
~~~

When Spring Data translates exceptions into `DataAccessException` or another wrapper, the MongoDB label often sits on a **cause**. This helper **classifies** the error; it does not decide whether retrying is safe.

Example:

~~~java
if (containsMongoLabel(error,
        "UnknownTransactionCommitResult")) {
    // Do not assume guaranteed rollback.
    // Use driver commit retry if session/context still permits,
    // or transition to a state requiring idempotency-key reconciliation.
}
~~~

Never simply call `service.approve(...)` from the beginning solely based on this label, especially if the workflow also touches external systems.

## 19. Whole-Transaction Retries and Limits

### 19.1. When Should You Retry the Body?

For instance, two transactions concurrently updating the same order may trigger `WriteConflict` or an error carrying `TransientTransactionError`. MongoDB aborts one transaction to preserve consistency; the application may **open a new transaction** and retry the logic if:

- The operation is **idempotent** or strongly guarded by unique keys.
- The transaction body **produces no external side effects outside the database**.
- Deadlines, backoff, and max retry limits are enforced.
- Every retry re-reads and re-checks the latest business state.

### 19.2. Do Not Retry the Body on Every `DuplicateKeyException`

A duplicate on a deterministic outbox `_id` may mean the request already succeeded. Repeating the same insert will keep failing with duplicate key; instead, look up the existing record and verify the payload.

For payments/ledgers, never "randomize `_id` to get around duplicate key" because that destroys idempotency.

### 19.3. Do Not Assume `@Retryable` Understands MongoDB Transactions

When using Spring Retry or a custom retry interceptor:

- Check **AOP advice ordering**: does retry wrap the transaction, or does the transaction wrap retry?
- Does every retry attempt open a fresh transaction/session?
- Does it mistakenly handle commit uncertainty by re-running the body?
- Are external side effects inside the body?

If retry sits **inside** a transaction already marked aborted by MongoDB, retrying a single statement **within the same transaction** cannot recover it. Retries must wrap the **proper transaction boundary**.

### 19.4. Short Classification Matrix

| Situation | Usually Appropriate Action |
| --- | --- |
| Clear business conflict | Return conflict; do not auto-retry |
| Duplicate business ID | Reconcile against previous request; do not generate random new IDs |
| `TransientTransactionError` | Consider bounded retry of a **new transaction body** |
| `UnknownTransactionCommitResult` | Retry **commit** via driver/session if possible; otherwise reconcile |
| Unlabeled socket timeout | Treat outcome as unknown; do not assume aborted |
| Connection/server selection fail before starting | Conditional retry after classification and deadline check |

This is a business decision framework. Always inspect your **exact driver API and server version** before writing retry handlers.

## 20. Manual Sessions with the Java Driver: Explicit Commit/Abort

To understand what Spring manages underneath, look at an example using the MongoDB Java Sync Driver directly. Do not mix this into Spring-managed transaction beans unless session ownership is explicitly designed.

### 20.1. Illustrative Code

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import java.util.concurrent.TimeUnit;
import org.bson.Document;

public void approveManually(
        MongoClient client,
        String tenantId,
        String orderId) {

    TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(
            WriteConcern.MAJORITY.withJournal(true)
                .withWTimeout(5, TimeUnit.SECONDS))
        .build();

    try (ClientSession session = client.startSession()) {
        session.startTransaction(options);

        try {
            var database = client.getDatabase("spring_data_mongodb_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders_tx_demo_007");
            MongoCollection<Document> outbox =
                database.getCollection("outbox_tx_demo_007");

            var result = orders.updateOne(
                session,
                new Document("_id", orderId)
                    .append("tenant_id", tenantId)
                    .append("state", "PENDING"),
                new Document("$set",
                    new Document("state", "APPROVED"))
            );

            if (result.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Order is not in PENDING state");
            }

            outbox.insertOne(
                session,
                new Document("_id",
                    "order-approved:" + orderId)
                    .append("tenant_id", tenantId)
                    .append("order_id", orderId)
                    .append("eventType", "OrderApproved")
            );

            session.commitTransaction();
        } catch (RuntimeException error) {
            if (session.hasActiveTransaction()) {
                try {
                    session.abortTransaction();
                } catch (RuntimeException abortError) {
                    error.addSuppressed(abortError);
                }
            }
            throw error;
        }
    }
}
~~~

This snippet demonstrates a **basic manual transaction**:

- All `updateOne`/`insertOne` calls take the **same `ClientSession`**.
- `commitTransaction()` runs **only after** both business operations complete.
- On error before commit, `abortTransaction()` is attempted if a transaction is still active.
- `ClientSession` is closed via `try-with-resources`.

**Important:** `catch RuntimeException; abort` is not a complete `UnknownTransactionCommitResult` algorithm. If the network drops right at commit, the transaction may have committed even though the client receives an exception; never assume calling abort in `catch` proves the commit was undone.

### 20.2. Never Retry Commit by Starting a New Session

A valid commit retry is tied to the **existing session and transaction identity**. When commit outcome is unknown, opening a new session and re-running all writes executes a new business request, not "retrying the old commit."

When using manual transactions in production, use the driver's convenient transaction API (`withTransaction`) or implement the transaction retry loop **per the MongoDB Driver specification**, including error labels and deadlines.

### 20.3. Sessions Are Unsafe for Arbitrary Parallel Operations

A `ClientSession`/MongoDB transaction must not be shared to run parallel operations across threads or independent reactive branches in ways unsupported by the driver.

**Do not do this:**

~~~java
// Never run two operations on the same session via parallelStream():
// List.of(task1, task2).parallelStream()
//     .forEach(task -> collection.insertOne(session, task));
~~~

Operations inside a transaction must be coordinated sequentially or per official driver capabilities; Spring Data does not make a session thread-safe.

## 21. Reactive Transactions: Commit Happens After the Publisher Completes

In reactive Spring Data MongoDB, session/transaction context is carried in the **Reactor Context**, not in an imperative thread-local like `MongoTransactionManager`.

### 21.1. Reactive Transaction Manager

~~~java
// ReactiveMongoTxConfig.java
package com.example.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Never use synchronous `MongoTransactionManager` to manage a `ReactiveMongoTemplate` chain. Pick the matching manager and keep components on the same reactive factory/session.

### 21.2. Transactional Service Returning `Mono<Void>`

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderApprovalService {
    private final ReactiveMongoTemplate mongo;

    public ReactiveOrderApprovalService(
            ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<Void> approve(String tenantId, String orderId) {
        Query pending = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        return mongo.updateFirst(
                pending,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            )
            .flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new OrderStateConflictException(
                            "Order not PENDING"));
                }
                return mongo.insert(new OutboxEvent(
                    "order-approved:" + orderId,
                    tenantId, orderId,
                    "OrderApproved",
                    Instant.now()
                ));
            })
            .then();
    }
}
~~~

**Crucial point:** code inside the method **builds a publisher**; it does not complete the transaction when `approve(...)` returns a `Mono`. The reactive transaction interceptor manages the lifecycle when the publisher is **subscribed** and terminates.

~~~text
Caller subscribes
   -> reactive transaction opens
   -> updateFirst emits result
   -> insert outbox
   -> publisher body completes
   -> commitTransaction
   -> downstream sees terminal completion after transaction
~~~

If `Mono.error(...)` is emitted in the transactional chain, the interceptor aborts per reactive rules. If `onErrorResume(...)` swallows the error and completes normally **inside the same transaction flow**, you risk driving the transaction to commit just like the imperative `try/catch` trap.

### 21.3. `TransactionalOperator`

An explicit programmatic approach:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Void> approveWithOperator(
        String tenantId,
        String orderId,
        TransactionalOperator operator) {

    Mono<Void> operations = createApprovalPipeline(
        tenantId, orderId
    );

    return operations.as(operator::transactional);
}
~~~

`createApprovalPipeline(...)` is a helper returning a `Mono<Void>` combining update and insert; it must share the **same reactive database factory** as the operator. The `transactional` operator manages the transaction within the subscription scope, and does not enlist reactive sources outside the pipeline.

### 21.4. Do Not Use `block()` on an Event Loop

~~~java
// Never do this inside a WebFlux event loop:
// reactiveService.approve(tenant, order).block();
~~~

Blocking causes thread starvation, defeats reactive scalability, and introduces transaction context errors. Design controllers to return `Mono<ResponseEntity<...>>` and compose pipelines cleanly along the lifecycle.

### 21.5. Beware of Cancellation and Multiple Subscriptions

- Every **subscription** can trigger a fresh execution; if a publisher is not idempotent, subscribing twice can write twice.
- Cancellation can occur before the transaction completes; **never treat an HTTP client disconnect as proof MongoDB rolled back** if commit already began or its result is unknown.
- Never use `parallel()` or fan out branches sharing a transactional session when the driver forbids parallel transaction operations.
- Test using `StepVerifier` and verify persisted database state rather than just asserting `Mono.empty()`.

## 22. What Operational Limits Do MongoDB Transactions Have?

### 22.1. Transactions Should Not Be Long-Lived

Multi-document transactions retain snapshots and server resources. MongoDB enforces default transaction lifetimes via `transactionLifetimeLimitSeconds`; overly long transactions can be aborted by the server.

**Avoid:**

~~~java
@Transactional
public void approveAndWaitForExternalResponse(...) {
    updateOrder(...);
    httpClient.callSlowPaymentGateway(...); // waits on external network
    insertOutbox(...);
}
~~~

Keep MongoDB transactions **short**, containing only DB operations requiring atomicity. External workflows use state machines/outbox/sagas instead of holding transactions open over network waits.

### 22.2. Lock Contention, Write Conflicts, and Transaction Aborts

Two transactions modifying the same document can hit a write conflict. An aborted transaction may require retrying the entire body, re-evaluating business predicates against fresh data.

`@Transactional` **does not guarantee** every concurrent transaction completes; it provides atomicity/isolation within MongoDB's bounds, while contention and retries still require handling.

### 22.3. Collection/Index DDL and Transactions

MongoDB allows limited collection/index creation inside transactions depending on version, topology, and preconditions. However, production request paths should never create collections/indexes **on the fly inside per-request transactions**.

**Best practice:** create collections, indexes, and validators via migrations/deployments before accepting traffic; integration tests should likewise create fixture collections outside transactions to avoid errors unrelated to rollback.

### 22.4. Sharded Transactions and Write Concern

On a sharded cluster, transactions spanning multiple shards incur extra commit coordination overhead and topology dependencies. `WriteConcern.MAJORITY` at commit controls durability, while transaction atomicity is governed by the distributed commit protocol.

Do not assume latency/limits match a single replica set, and never rely on a single-node test as proof of distributed commit correctness.

### 22.5. Do Not Set Write Concern per Operation Inside a Transaction

In MongoDB, write concern must be set **at the transaction level**, specifically for `commitTransaction`. Driver APIs reject or disallow per-operation write concerns inside a transaction.

Do not do:

~~~javascript
// Do not design transactional operations like this:
// session.startTransaction(...);
// db.collection.updateOne(..., { writeConcern: { w: 1 } });
// db.collection.insertOne(..., { writeConcern: { w: "majority" } });
// session.commitTransaction();
~~~

Instead, decide durability policy for the **entire transaction** and pass it via transaction options.

### 22.6. Transactions and Index Uniqueness

Unique indexes remain enforced inside transactions. A transaction inserting two documents with the same unique key or colliding with an outside document fails. Do not expect transactions to allow "temporary constraint violations resolved before commit" like deferred constraints in some relational databases.

## 23. Integration Testing: Verifying Commit, Rollback, and Checked Exceptions

This is mandatory if you want proof that `@Transactional` genuinely works in Spring Data MongoDB.

### 23.1. Test Conditions

- Test MongoDB instance is configured as a **replica set**, not standalone.
- The `mongoTransactionManager` bean is registered in the application context.
- The service is a **Spring bean/proxy**, not manually instantiated with `new`.
- `MongoTemplate` and the transaction manager share the **same `MongoDatabaseFactory`**.
- Collections already exist or are created **before the transaction**.
- **Do not place `@Transactional` on the test method itself** to rely on test-framework rollback instead of testing the business service: observe state after the **service proxy** commits/aborts.
- Use dedicated fixture IDs and precise cleanup; avoid shared collections/DBs.

### 23.2. Adding Checked Methods to Test

Add these to `OrderApprovalService` from section 7:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void checkedDefault(String tenantId, String orderId)
        throws BusinessRuleException {
    applyApproval(tenantId, orderId);
    throw new BusinessRuleException("Checked exception");
}

@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
public void checkedRollback(String tenantId, String orderId)
        throws BusinessRuleException {
    applyApproval(tenantId, orderId);
    throw new BusinessRuleException("Checked exception");
}

@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void swallowUnchecked(String tenantId, String orderId) {
    applyApproval(tenantId, orderId);
    try {
        throw new IllegalStateException("Non-database error");
    } catch (IllegalStateException ignored) {
        // Intentionally swallowed to demonstrate unexpected commit.
    }
}
~~~

These example methods are called from **another bean through a proxy**. In tests, use a **distinct order ID per test case** so cases stay isolated.

### 23.3. Integration Test with Spring Boot Test Slice

~~~java
package com.example.transactions;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import({MongoTxConfig.class, OrderApprovalService.class})
class OrderApprovalTransactionTest {
    @Autowired MongoTemplate template;
    @Autowired OrderApprovalService service;

    private static final String TENANT = "test-tenant-tx007";
    private static final String COMMIT_ID = "tx007-commit";
    private static final String ROLLBACK_ID = "tx007-rollback";
    private static final String CHECKED_ID = "tx007-checked";
    private static final String CHECKED_RB_ID = "tx007-checked-rb";
    private static final String SWALLOW_ID = "tx007-swallow";

    @BeforeEach
    void prepare() {
        // Safe cleanup strictly on the test MongoDB database.
        cleanup();

        for (String id : new String[] {
                COMMIT_ID, ROLLBACK_ID,
                CHECKED_ID, CHECKED_RB_ID, SWALLOW_ID }) {

            template.insert(new OrderDocument(
                id, TENANT, "PENDING", 100000L
            ));
        }
    }

    @AfterEach
    void cleanup() {
        for (String id : new String[] {
                COMMIT_ID, ROLLBACK_ID,
                CHECKED_ID, CHECKED_RB_ID, SWALLOW_ID }) {

            template.remove(
                org.springframework.data.mongodb.core.query.Query.query(
                    org.springframework.data.mongodb.core.query.Criteria
                        .where("id").is(id)
                ),
                OrderDocument.class
            );

            template.remove(
                org.springframework.data.mongodb.core.query.Query.query(
                    org.springframework.data.mongodb.core.query.Criteria
                        .where("id").is("order-approved:" + id)
                ),
                OutboxEvent.class
            );
        }
    }

    @Test
    void commitsOrderAndOutboxTogether() {
        service.approve(TENANT, COMMIT_ID);

        assertThat(template.findById(
            COMMIT_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");

        assertThat(template.findById(
            "order-approved:" + COMMIT_ID, OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void uncheckedExceptionAbortsBothChanges() {
        assertThatThrownBy(() ->
            service.approveThenFail(TENANT, ROLLBACK_ID)
        ).isInstanceOf(IllegalStateException.class);

        assertPendingWithoutOutbox(ROLLBACK_ID);
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThatThrownBy(() ->
            service.checkedDefault(TENANT, CHECKED_ID)
        ).isInstanceOf(BusinessRuleException.class);

        assertThat(template.findById(
            CHECKED_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(template.findById(
            "order-approved:" + CHECKED_ID,
            OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void rollbackForCheckedAbortsBothChanges() {
        assertThatThrownBy(() ->
            service.checkedRollback(TENANT, CHECKED_RB_ID)
        ).isInstanceOf(BusinessRuleException.class);

        assertPendingWithoutOutbox(CHECKED_RB_ID);
    }

    @Test
    void swallowedJavaExceptionStillCommits() {
        service.swallowUnchecked(TENANT, SWALLOW_ID);

        assertThat(template.findById(
            SWALLOW_ID, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(template.findById(
            "order-approved:" + SWALLOW_ID,
            OutboxEvent.class
        )).isNotNull();
    }

    private void assertPendingWithoutOutbox(String orderId) {
        assertThat(template.findById(
            orderId, OrderDocument.class
        ).getState()).isEqualTo("PENDING");

        assertThat(template.findById(
            "order-approved:" + orderId,
            OutboxEvent.class
        )).isNull();
    }
}
~~~

**Configuration notes when running:** the example uses `@DataMongoTest` per Spring Boot 3.x. With Spring Boot 4 or different project layouts, the test slice package may differ; use the matching annotation. A running test replica set or configured Testcontainers instance is required, and tests should not modify project files/build configs.

### 23.4. Explaining the Test Results

| Test | Real Outcome After Service Proxy |
| --- | --- |
| `commitsOrderAndOutboxTogether` | Both order and outbox exist |
| `uncheckedExceptionAbortsBothChanges` | Order remains PENDING, no outbox |
| `checkedExceptionCommitsByDefault` | Exception is thrown, yet data **committed** |
| `rollbackForCheckedAbortsBothChanges` | Configured checked exception -> rollback |
| `swallowedJavaExceptionStillCommits` | Java error caught -> normal return -> commit |

The tests verify **persisted behavior** by querying after the service call, rather than asserting only the exception class.

### 23.5. Testing Self-Invocation and Real Transactions

Create two more services:

~~~java
@Service
public class BrokenFacade {
    public void run(String tenantId, String orderId) {
        this.inner(tenantId, orderId); // bypasses proxy
    }

    @Transactional(
        transactionManager = "mongoTransactionManager"
    )
    public void inner(String tenantId, String orderId) {
        // update + insert + throw
    }
}
~~~

With `BrokenFacade.run(...)`, because `inner` lacks an outer transaction context, writes can **commit individually** before the throw. To test, use isolated fixture data, inspect collection state, and compare against calling **through another transactional bean**.

### 23.6. Testing Commit Errors Is a Different Kind of Test

Throwing `IllegalStateException` inside the body tests **rollback rules**, not `UnknownTransactionCommitResult`. To genuinely test commit ambiguity:

- Use a dedicated chaos environment capable of controlling network/primary stepdowns.
- Inject failures at the commit boundary or use an appropriate driver/test harness.
- Verify server state via idempotency keys and defined read policies.
- Never assume a body exception is equivalent to a commit exception.

## 24. Reactive Integration Test with `StepVerifier`

With reactive beans and the matching manager configured, you can verify:

~~~java
import reactor.test.StepVerifier;

@Test
void reactiveApprovalCommitsAfterComplete() {
    StepVerifier.create(
        reactiveService.approve(
            "test-tenant-tx007", "rx007-commit"
        )
    ).verifyComplete();

    StepVerifier.create(
        reactiveTemplate.findById(
            "rx007-commit", OrderDocument.class
        )
    )
      .assertNext(order ->
          assertThat(order.getState())
              .isEqualTo("APPROVED")
      )
      .verifyComplete();
}
~~~

Before the test, insert `rx007-commit` in `PENDING` state using the **reactive test template** and pre-create collections outside the transaction. Likewise, test reactive errors:

~~~java
StepVerifier.create(
    reactiveService.approve(
        "wrong-tenant", "rx007-rollback"
    )
)
  .expectError(OrderStateConflictException.class)
  .verify();
~~~

Then verify the order remains `PENDING` and no outbox exists. Never assert only `expectError`; the error might occur **after an out-of-transaction write** if proxy/transaction manager configuration is wrong.

**Note:** reactive publishers must be subscribed. If a test only builds:

~~~java
Mono<Void> pipeline = reactiveService.approve(...);
~~~

without subscribing, the writes **have not run**; such a test proves neither commit nor rollback.

## 25. Diagnosing Common Mistakes

| Symptom | Common Cause | How to Investigate/Fix |
| --- | --- | --- |
| Method throws `RuntimeException`, yet order still changed | Missing transaction manager, self-invocation, different factory template, or out-of-tx write | Check proxy/factory/session and integration tests |
| Checked exception thrown, yet DB committed | Spring does not roll back checked exceptions by default | Configure `rollbackFor` per contract or change exception type |
| Method catches error and returns `false`, DB still commits | Exception does not exit proxy | Rethrow or mark rollback-only if business logic requires |
| Outer catches inner `RuntimeException` and receives `UnexpectedRollbackException` | Inner marked the shared transaction rollback-only | Clarify propagation and error handling |
| `@Transactional` on `private` method fails to fire | Spring proxy does not intercept internal/private calls | Move transaction boundary to proxied entry point |
| Used `REQUIRES_NEW`, outer rolls back, inner audit stays | Inner committed independently | Use only when independent persistence is intended |
| `NESTED` fails | MongoDB lacks JDBC-style savepoints | Do not assume nested rollback; redesign |
| Service returns normally, yet caller receives exception | Commit failed after method body | Classify commit errors/unknown outcomes |
| Client times out and retries, creating two side effects | Missing idempotency | Use stable business keys, reconcile, bounded retries |
| Caught MongoDB write error, yet commit still fails | Server already aborted/doomed the transaction | Do not continue using a broken transaction |
| Sent email before commit, DB rolled back | External side effects outside MongoDB are not aborted | Use outbox/`afterCommit` and idempotency |
| `AFTER_COMMIT` listener misses event when process crashes | In-memory callback is not durable | Use durable outbox |
| DB write inside `AFTER_COMMIT` is not persisted | Using completion resources without opening a new tx | Delegate to worker or proper `REQUIRES_NEW` |
| `MongoTemplate` does not join transaction | Different `MongoDatabaseFactory` or driver call without session | Align manager/factory; test both collections |
| Transaction on standalone throws error | Topology unsupported | Use a test replica set |
| Reactive `Mono` created yet writes nothing | Not subscribed | Use WebFlux chain/`StepVerifier` |
| Reactive error swallowed by `onErrorResume`, DB commits | Chain completed normally before interceptor | Put error handling outside transaction or make rollback explicit |
| Transaction runs too long and aborts | Snapshot/lock/resource timeout | Shorten transaction; move HTTP calls outside |
| `@Transactional` test rollback masks real results | Test transaction never commits | Test business service outside a test rollback scope |
| Single-node test PASSES, real failover fails | Multi-member/chaos scenarios untested | Test proper topology and dedicated failure injection |

## 26. Review Checklist for a MongoDB Transaction Workflow

1. **Define the atomic boundary accurately:** which writes strictly need to commit/abort together?
2. **Use transactions when spanning multiple documents/collections**, not needlessly replacing atomic single-document operations.
3. **Verify replica set/sharded topology** and create collections/indexes before transactions.
4. **Configure `MongoTransactionManager` or the reactive manager** matching your stack.
5. **Ensure same factory/session**, never mixing another `MongoClient` expecting shared atomicity.
6. **Place transactions on public service boundaries invoked via proxy**, avoiding self-invocation.
7. **Put business predicates in write filters** (tenant, state, version); never assume transactions replace optimistic locking.
8. **Check rollback rules:** unchecked, checked, `rollbackFor`, `noRollbackFor`.
9. **Never swallow exceptions**; when catching, decide explicitly whether to rethrow or mark rollback-only.
10. **Review propagation**, especially `REQUIRES_NEW` and `UnexpectedRollbackException`.
11. **Never assume MongoDB supports savepoints/nested rollback**.
12. **Understand commit runs after the method body**; callers only observe proxy success once commit finishes.
13. **Pick commit write concern** based on durability and failover policy.
14. **Distinguish body errors from commit errors**; handle `UnknownTransactionCommitResult` and `TransientTransactionError`.
15. **Keep retries bounded and idempotent**, never retrying balance changes as brand-new requests.
16. **Move external side effects to an outbox** or clearly bounded `AFTER_COMMIT` design.
17. **Never hold transactions open waiting on HTTP**, emails, or heavy CPU work.
18. **Use reactive manager + Reactor Context** for reactive operations; avoid blocking or parallel session ops.
19. **Test against a real MongoDB replica set**, not just repository mocks.
20. **Assert persisted state after the proxy call** across all collections, using isolated fixtures without wrapping tests in rollback scopes.
21. **Monitor commit/rollback errors, write conflicts, and latency**, paired with recovery procedures.

## 27. Practice Exercises with Answers

### Exercise 1 — Commit Point

A `@Transactional` method reaches `return;`. Can we guarantee MongoDB has finished committing?

**Answer:** No. When invoked through a Spring proxy, the transaction interceptor commits **after the method body returns**, before the caller receives a successful proxy return.

### Exercise 2 — Unchecked Exception

Inside a transactional service, an order is updated and an outbox is inserted, then `IllegalStateException` is thrown. What happens to the data if the manager/session are configured properly and rollback succeeds?

**Answer:** The transaction is aborted; the order reverts to its uncommitted state and the outbox entry is not persisted.

### Exercise 3 — Checked Exception

After two writes, a method throws `BusinessRuleException extends Exception` without `rollbackFor`. What does Spring do by default?

**Answer:** It commits by default if the transaction remains valid, even though the checked exception is thrown to the caller. Declare `rollbackFor` if that error must cancel the workflow.

### Exercise 4 — `rollbackFor`

Write the annotation to roll back when the method throws `BusinessRuleException`.

**Answer:**

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = BusinessRuleException.class
)
~~~

### Exercise 5 — `noRollbackFor`

A method throws unchecked `NonFatalNotificationException`, yet business logic wants data committed. What can be used?

**Answer:** Consider `noRollbackFor = NonFatalNotificationException.class` deliberately. However, if the server/transaction already aborted or was marked rollback-only, the rule cannot force an uncommittable transaction to commit.

### Exercise 6 — Catching Errors

A method catches an `IllegalStateException` thrown by its own code and executes `return false`. Will the Spring proxy know to roll back?

**Answer:** No; the exception never leaves the proxy. The transaction can commit if still valid, even though the service returned `false`.

### Exercise 7 — Rollback-Only

When you must return a business result while aborting, what API is used in imperative `@Transactional`?

**Answer:** `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` within an active transaction context; or use `TransactionTemplate` with `status.setRollbackOnly()`.

### Exercise 8 — Inner Transaction and Outer Catch

Outer `@Transactional(REQUIRED)` calls inner `@Transactional(REQUIRED)` on another bean. Inner throws `RuntimeException`, outer catches it and returns normally. Why can the caller receive `UnexpectedRollbackException`?

**Answer:** The inner interceptor marked the **shared transaction** rollback-only. Outer then tries to commit an uncommittable transaction, so Spring reports the unexpected rollback.

### Exercise 9 — `REQUIRES_NEW`

Inner uses `REQUIRES_NEW` to write an audit record and commits; outer later rolls back. Is the audit record kept?

**Answer:** Yes, it can persist because inner used an independent transaction. Use this only when that matches business intent, not as a band-aid for rollbacks.

### Exercise 10 — `NESTED`

Does MongoDB let you roll back a nested savepoint inside the same session transaction like JDBC?

**Answer:** No, there are no savepoints/nested transactions to arbitrarily roll back a subset of operations. `Propagation.NESTED` should not be assumed supported on `MongoTransactionManager`.

### Exercise 11 — Self-Invocation

Does `this.approveInTransaction()` go through the transaction proxy?

**Answer:** Under typical Spring AOP proxy configuration, no. Move the call to another Spring bean or place `@Transactional` on the externally called public entry point.

### Exercise 12 — Different Factory `MongoTemplate`

Order update uses template A inside transaction S1; outbox insert uses driver `MongoClient` B. Do both roll back together?

**Answer:** Not automatically. Operation B does not enlist in session S1; use the same factory/session mechanism or proper transaction coordination.

### Exercise 13 — External Side Effects

An application sends an email before Spring commits. MongoDB commit then fails. Is the email automatically unsent?

**Answer:** No. Use an outbox or post-commit workflow and handle external delivery failure modes explicitly.

### Exercise 14 — `AFTER_COMMIT`

Does `@TransactionalEventListener(phase=AFTER_COMMIT)` replace a durable outbox?

**Answer:** No. The callback runs after commit succeeds, yet events can be lost if the process crashes or sending fails. A persisted outbox supports retries and reconciliation.

### Exercise 15 — Commit Uncertainty

The server might have committed, yet the `commitTransaction` response was lost on the network. Should you start a fresh transaction and repeat the entire workflow?

**Answer:** Not automatically. That is an unknown commit outcome; retry the **existing commit** via driver/session where possible or reconcile by idempotency key. Re-running the body as a new request risks duplicates.

### Exercise 16 — Error Labels

What is the difference between `TransientTransactionError` and `UnknownTransactionCommitResult`?

**Answer:** A transient transaction error can trigger retrying the **entire body in a new transaction**; an unknown commit result requires handling/retrying the **commit**, without assuming the transaction aborted.

### Exercise 17 — Reactive

A `Mono<Void>` is returned from a reactive transactional method without being subscribed. Has the transaction run yet?

**Answer:** Normally no; reactive publishers are lazy. A subscriber/`StepVerifier` or WebFlux pipeline is needed to execute and observe commit/rollback.

### Exercise 18 — Reactive Error Swallowing

`Mono.error(...)` is handled by `onErrorResume(e -> Mono.empty())` inside a transactional pipeline. What is the risk?

**Answer:** The pipeline may complete normally and the interceptor proceed to commit if the transaction/server had not aborted. Place error recovery at the right boundary and verify database state.

### Exercise 19 — Trustworthy Tests

A test throws an unchecked exception and asserts the exception type without checking the DB. Has it proven rollback?

**Answer:** No. The exception might happen after an out-of-transaction write. Re-read both order/outbox after the proxy call completes against a test MongoDB replica set.

### Exercise 20 — Tests Running on Standalone

Standalone MongoDB throws an error when starting a multi-document transaction. Should you fix the test by disabling transactions?

**Answer:** No. Use a test replica set (a single-node replica set suffices for basic commit/abort behavior; use multiple nodes to test failover).

### Exercise 21 — Write Concern at Commit

Is placing `WriteConcern.MAJORITY` on every individual insert/update inside a MongoDB transaction valid per contract?

**Answer:** No; MongoDB transactions set write concern at the **transaction/commit level**. Configure it via `TransactionOptions`/transaction manager.

### Exercise 22 — Transaction Duration

A transaction stays open for 60 seconds waiting on an HTTP payment gateway. What are the risks?

**Answer:** It holds snapshots/locks/resources, raises write conflicts, and can be aborted by the lifetime limit. Separate external workflows using outbox/saga/state machines.

### Exercise 23 — Which Data Is Reverted?

A transaction updates the order and outbox, then aborts. Meanwhile, the service wrote logs and sent an HTTP request earlier. Which side effects does MongoDB revert?

**Answer:** Changes **inside that same MongoDB transaction** are aborted; written logs and outbound HTTP requests are **not** automatically undone.

### Exercise 24 — Commit `w:1`

A transaction committed with `w:1`. Can we guarantee it is majority-journaled and cannot roll back after an election?

**Answer:** No. Atomic commit and durability are distinct properties; choose majority/journal commit write concerns per requirements.

## References

- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, `@Transactional`, programmatic transactions, session binding, and transaction options.
- [Spring Data MongoDB — `MongoTransactionManager` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): transaction lifecycle, configuration, and limits.
- [Spring Data MongoDB — `ReactiveMongoTransactionManager` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/ReactiveMongoTransactionManager.html): reactive transaction/session management.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): `RuntimeException`/`Error`, checked exceptions, `rollbackFor`, `noRollbackFor`, rollback-only, and proxy boundaries.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, and `UnexpectedRollbackException`.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` and rollback-only status.
- [Spring Framework — `@TransactionalEventListener`](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `AFTER_COMMIT`, `AFTER_ROLLBACK`, and interacting with transaction resources.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomicity, sessions, topology, isolation, and operational limits.
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): contention, lifetime limits, DDL, and resource management.
- [MongoDB Manual — Commit Transaction Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/): commit write concern, acknowledgment, and timeout/commit behavior.
- [MongoDB Manual — Abort Transaction Command](https://www.mongodb.com/docs/manual/reference/command/abortTransaction/): abort semantics.
- [MongoDB Manual — Retry Transactions](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): `TransientTransactionError`, `UnknownTransactionCommitResult`, and retry loops.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): manual sessions, transaction API, and retry guidelines.
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/transactions/): reactive transaction publisher lifecycle.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): commit durability, majority, journaling, and rollback risk.
