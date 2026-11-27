# Post-Commit Business Events and Safe Side-Effect Handling

> **Chapter:** Lifecycle and Callbacks  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; practicing queries, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objectives:** Distinguish entity lifecycle callbacks from post-commit business events; understand `@TransactionalEventListener` with its phases, missing-transaction pitfalls, and error handling; use MongoDB transactions properly; design a transactional outbox, idempotency, and retry/claim/lease mechanisms for critical side effects; write integration tests that observe database state and post-commit/rollback behavior.

## 1. The Business Problem: Saving an Order Then Sending a Notification

Suppose a customer approves an order. The system must:

1. Transition the order from `PENDING` to `APPROVED` in MongoDB.
2. Emit an `OrderApproved` event to send an email, call an inventory API, or update another system.

A reasonable-looking implementation:

~~~java
public void approve(String orderId) {
    repository.save(approvedOrder);
    emailClient.sendApprovedNotice(orderId);
}
~~~

However, that code has these failure modes:

- The database write fails **after** the email has already been sent.
- The email client times out even though the recipient side **already sent the email**; retrying sends it twice.
- Inside a transaction, `save(...)` completes, but the transaction **has not committed yet**. Sending the email immediately inside the method may announce an event that never gets committed.
- The transaction commits, but the application **crashes before sending the email**.
- The client resubmits the same request, producing duplicate events/notifications.

No single simple callback eliminates all of these risks on its own.

### 1.1. Two Common Requirement Tiers

| Requirement | Typical suitable design |
| --- | --- |
| “If committed, *try* to notify immediately; occasional missed notifications are acceptable” | Spring `@TransactionalEventListener(AFTER_COMMIT)` |
| “Every committed order must have a persisted work record for subsequent delivery/reconciliation” | **Transactional outbox** written in the same MongoDB transaction |
| “If an email was sent, roll it back when MongoDB fails” | Emails **cannot** be rolled back via a MongoDB transaction |
| “Never deliver two messages to the external system” | Cannot be inferred from `AFTER_COMMIT`; requires consumer-side idempotency / delivery guarantees |

### 1.2. Conceptual Diagram

~~~mermaid
flowchart TD
    A["Client requests order approval"] --> B["Transaction: update order"]
    B --> C{"Choose event strategy"}
    C -->|"Best effort"| D["Publish domain event inside transaction"]
    D --> E["MongoDB Commit"]
    E -->|"Succeeded"| F["AFTER_COMMIT listener"]
    F --> G["Call email / external API"]
    C -->|"Durable"| H["Insert outbox inside same transaction"]
    H --> I["Commit order + outbox together"]
    I --> J["Worker reads committed outbox"]
    J --> K["Send external event with eventId"]
    K --> L["Record delivered / retry"]
~~~

**Distinction:** a best-effort listener is tied to the **currently running application process**, whereas an outbox is tied to a **persisted record** inside the same transaction. Do not treat them as equivalent in durability guarantees.

## 2. Terminology: Entity Callbacks, Application Events, Transaction Synchronization, Outbox

| Concept | Trigger | Purpose | Post-commit? |
| --- | --- | --- | --- |
| `BeforeConvertCallback<T>` | Before converting entity to BSON | Normalize fields, generate technical values | **No** |
| `BeforeSaveCallback<T>` | After convert, before save | Adjust entity/BSON per callback contract | **No** |
| `AfterSaveCallback<T>` | After save operation in mapping pipeline | Handle entity lifecycle | **Not guaranteed** |
| `AfterSaveEvent<T>` / `AbstractMongoEventListener` | Mapping event published by Spring Data | Observe mapping lifecycle | **Not guaranteed** |
| `ApplicationEventPublisher.publishEvent(...)` | When code calls the publisher | Publish in-process event | **Does not wait for commit automatically** |
| `@EventListener` | Application event is published | Handle event without commit-phase binding | **No** |
| `@TransactionalEventListener(AFTER_COMMIT)` | Transaction synchronization at successful commit phase | Side effect *after* commit | **Yes**, if the event is bound to a transaction |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Transaction finishes with rollback | Appropriate telemetry/cleanup | **After rollback** |
| Transactional outbox | Outbox record written in the same transaction | Durable work handoff to workers | Sent **after** the record is committed |
| Change stream | MongoDB publishes observed changes via stream | CDC/event consumer | Depends on resume token, pipeline, and durability; do not arbitrarily replace an outbox |

### 2.1. “After Save” Does Not Mean “After Commit”

With `MongoTemplate.save` or repository save:

~~~text
MongoDB transaction T1 started
    |
    +-- BeforeConvert
    +-- BeforeSave
    +-- MongoDB write in T1
    +-- AfterSave
    |
    +-- service method continues
    +-- May THROW exception
    +-- transaction T1 ABORTS
~~~

`AfterSaveCallback` already executed even though no record was committed. If the callback immediately sends an email/HTTP request, the external system receives the side effect while the database stores nothing.

In an operation without a multi-document transaction, a save is acknowledged under the configured write concern; even then, you should not infer that a lifecycle callback guarantees durability across failover or external delivery.

### 2.2. Callbacks Belong “Close to the Entity”

Example `BeforeConvertCallback`:

~~~java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderNormalizationCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument order,
            String collection) {
        // Example: only perform synchronous/deterministic transformations
        // such as populating technical fields or validating.
        return order;
    }
}
~~~

Do not use this callback to call an email service, publish events to a message broker, or start secondary transactions on every save.

### 2.3. Bulk/Template Operations May Bypass the `save` Lifecycle

`updateFirst`, `updateMulti`, aggregation updates, bulk operations, and raw driver calls are not uniform with the `repository.save` pipeline regarding callbacks/events. **Do not place essential business logic solely in `AfterSaveCallback`** if the system also updates data through those other APIs.

For example, a state transition:

~~~java
template.updateFirst(query, update, OrderDocument.class);
~~~

can update a document **without firing `AfterSaveCallback<OrderDocument>`** because there is no entity convert/save path like `save`. The point where a domain event is emitted should live in the **application service** after confirming the write actually took effect, rather than guessing from a callback that does not execute on every write path.

## 3. MongoDB Transactions Are the Foundation for “After Commit”

For `AFTER_COMMIT` to be meaningful across **multiple MongoDB writes**, an actual transaction is required.

### 3.1. Topology and Infrastructure

- Use a MongoDB **replica set** or a sharded deployment that supports transactions; standalone instances do not support multi-document transactions.
- Create collections/indexes before opening transactions on critical request paths.
- `MongoTemplate` and `MongoTransactionManager` must share the appropriate database factory/session.
- Services must be invoked **through the Spring transactional proxy**; calling a transactional method via `this...` bypasses the proxy.
- Choose an appropriate commit write concern. **Atomic commit does not automatically mean majority-durable** if the policy is only `w:1`.

### 3.2. Synchronous Manager

~~~java
// MongoTransactionConfig.java
package com.example.mongoevents;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .readPreference(ReadPreference.primary())
            .writeConcern(
                WriteConcern.MAJORITY.withJournal(true))
            .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

`MongoTransactionManager` creates and manages `ClientSession` according to Spring’s transaction context. Transaction options set `writeConcern` at the **commit** level, rather than assigning different write concerns to individual inserts/updates inside the transaction.

**Operational note:** A single-node replica set is sufficient for basic integration tests, but `majority` on a single node **does not prove** resilience against multi-node failover. Production requires a topology with multiple data-bearing members when replication durability is required.

### 3.3. Read Concern and What “Committed” Means

A successful commit under the transaction’s write concern **does not automatically make the data visible on every secondary instantaneously**. When consumers read from secondaries, replication lag, read concern, and session/causal consistency must be accounted for. For an outbox, workers should use consistent query/read preferences rather than assuming “after commit” means “every node has immediately applied the write.”

## 4. Business Fixture and Entities

The example uses two collections:

~~~text
orders_events_011
  _id: "order-011-01"
  tenant_id: "t01"
  state: "PENDING"

outbox_events_011
  _id: "order-approved:order-011-01"
  tenant_id: "t01"
  aggregate_id: "order-011-01"
  kind: "OrderApproved"
  status: "PENDING"
~~~

### 4.1. Initializing the Test Environment

Run only inside an **isolated test database**:

~~~javascript
use spring_data_mongodb_lab

db.createCollection("orders_events_011");
db.createCollection("outbox_events_011");

db.orders_events_011.insertOne({
  _id: "order-011-01",
  tenant_id: "t01",
  state: "PENDING",
  amount_vnd: NumberLong(250000)
});

db.outbox_events_011.createIndex(
  { status: 1, next_attempt_at: 1, _id: 1 },
  { name: "ix_outbox_due" }
);

db.outbox_events_011.createIndex(
  { tenant_id: 1, aggregate_id: 1, kind: 1 },
  { name: "ix_outbox_aggregate" }
);
~~~

Every collection always has a unique `_id` index. The outbox query indexes are starting examples; actual index design must be evaluated against real filters, sorts, throughput, and collection size.

### 4.2. `OrderDocument`

~~~java
// OrderDocument.java
package com.example.mongoevents;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_events_011")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    protected OrderDocument() {}

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
}
~~~

### 4.3. Transport-Agnostic Domain Event

~~~java
// OrderApproved.java
package com.example.mongoevents;

public record OrderApproved(
    String eventId,
    String tenantId,
    String orderId
) {}
~~~

`OrderApproved` is an **in-process business event**. It is not automatically stored in MongoDB, is not inherently a Kafka message, and carries no delivery guarantees on its own. `eventId` is derived from business identity to support reconciliation/idempotency.

### 4.4. `OutboxEvent`

~~~java
// OutboxEvent.java
package com.example.mongoevents;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_events_011")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("aggregate_id")
    private String aggregateId;

    private String kind;
    private String status;
    private int attempts;

    @Field("created_at")
    private Instant createdAt;

    @Field("next_attempt_at")
    private Instant nextAttemptAt;

    @Field("lease_until")
    private Instant leaseUntil;

    @Field("lease_token")
    private String leaseToken;

    protected OutboxEvent() {}

    public OutboxEvent(
            String id, String tenantId,
            String aggregateId, String kind,
            Instant now) {
        this.id = id;
        this.tenantId = tenantId;
        this.aggregateId = aggregateId;
        this.kind = kind;
        this.status = "PENDING";
        this.attempts = 0;
        this.createdAt = now;
        this.nextAttemptAt = now;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getAggregateId() { return aggregateId; }
    public String getKind() { return kind; }
    public String getStatus() { return status; }
    public int getAttempts() { return attempts; }
    public Instant getLeaseUntil() { return leaseUntil; }
    public String getLeaseToken() { return leaseToken; }
}
~~~

This is an example model with `PENDING`/`SENDING`/`DELIVERED` states. Production systems typically also need `leaseOwner`, `leaseToken`, `lastErrorCode`, `schemaVersion`, `traceId`, `deliveredAt`, and deadline/idempotency policies; do not log tokens, sensitive payloads, or personal data carelessly.

## 5. Emit Events Only After a Valid Business Write

When transitioning order state, you must confirm **a transition actually occurred**. Do not emit `OrderApproved` if the query does not match, the tenant is wrong, or the order was already approved.

~~~java
Query pending = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authorizedTenantId)
        .and("state").is("PENDING")
);

Update approve = new Update().set("state", "APPROVED");

UpdateResult result = mongo.updateFirst(
    pending, approve, OrderDocument.class
);

if (result.getMatchedCount() != 1) {
    throw new OrderStateConflictException(
        "Order not found or not PENDING"
    );
}
~~~

Here `UpdateResult` is `com.mongodb.client.result.UpdateResult`, and `Query`/`Criteria`/`Update` come from `org.springframework.data.mongodb.core.query`. The `OrderStateConflictException` class is declared below.

### 5.1. Domain Exception

~~~java
// OrderStateConflictException.java
package com.example.mongoevents;

public class OrderStateConflictException
        extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}
~~~

By default, Spring rolls back on `RuntimeException`/`Error` when the exception escapes the transactional proxy. Checked exceptions follow different rules unless `rollbackFor` is specified.

### 5.2. An Event with a Stable ID

~~~java
String eventId = "order-approved:" + orderId;
OrderApproved event = new OrderApproved(
    eventId, authorizedTenantId, orderId
);
~~~

Choose `eventId` based on **business identity** and semantics. If an order can be approved multiple times after reopening, `orderId` alone is not enough; in that case you need `orderId + transitionVersion` or a dedicated business command ID. Do not generate a fresh UUID for the same event on each retry if downstream consumers require deduplication.

## 6. Approach A: `@TransactionalEventListener(AFTER_COMMIT)` for Best-Effort Notifications

If the notification is an auxiliary feature that can tolerate loss during a process crash and has manual recovery available, you can combine Spring application events with transaction phases.

### 6.1. Service Publishing the Event **Inside** the Transaction

~~~java
// BestEffortOrderService.java
package com.example.mongoevents;

import com.mongodb.client.result.UpdateResult;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BestEffortOrderService {
    private final MongoTemplate mongo;
    private final ApplicationEventPublisher events;

    public BestEffortOrderService(
            MongoTemplate mongo,
            ApplicationEventPublisher events) {
        this.mongo = mongo;
        this.events = events;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approve(String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        UpdateResult result = mongo.updateFirst(
            eligible,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order not PENDING or wrong tenant"
            );
        }

        events.publishEvent(new OrderApproved(
            "order-approved:" + orderId,
            tenantId,
            orderId
        ));
        // Event is PUBLISHED here, but the AFTER_COMMIT listener
        // has not run yet because the transaction has not committed.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approveThenFail(
            String tenantId, String orderId) {
        approveInternalAndPublish(tenantId, orderId);
        throw new IllegalStateException(
            "Simulated failure before commit");
    }

    private void approveInternalAndPublish(
            String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );
        UpdateResult result = mongo.updateFirst(
            eligible, new Update().set("state", "APPROVED"),
            OrderDocument.class
        );
        if (result.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "Order not PENDING");
        }
        events.publishEvent(new OrderApproved(
            "order-approved:" + orderId,
            tenantId, orderId
        ));
    }
}
~~~

In the example, `approveThenFail` calls a private helper rather than `this.approve(...)` so readers do not mistakenly assume an internal self-call creates a second transaction. Both `@Transactional` entry points **must be called from another bean through the Spring proxy** for a transaction to actually exist.

In production, extract the `update + publish` logic into a shared helper to avoid duplicating code; keeping two separate paths in the example makes it easier to trace the success and rollback scenarios.

### 6.2. Listener Running on Successful Commit

~~~java
// NotificationGateway.java
package com.example.mongoevents;

public interface NotificationGateway {
    void notifyOrderApproved(OrderApproved event);
}
~~~

~~~java
// OrderNotificationListener.java
package com.example.mongoevents;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {
    private final NotificationGateway notifications;

    public OrderNotificationListener(
            NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderApproved event) {
        notifications.notifyOrderApproved(event);
    }
}
~~~

`NotificationGateway` must have an implementation in the runtime environment (email/HTTP adapter, or a mock/recording port in tests). The listener only **attempts to invoke the external adapter after commit**; adapter failure does not revert a committed order back to PENDING.

**Note:** the default phase of `@TransactionalEventListener` is already `AFTER_COMMIT`, but declaring it explicitly prevents readers from confusing it with a regular `@EventListener`.

### 6.3. Success Timeline

~~~text
Caller --> Spring proxy
  -> opens MongoDB transaction T1
  -> updates orders (T1)
  -> events.publishEvent(OrderApproved)
       -> listener is REGISTERED for AFTER_COMMIT
  -> method body returns
  -> Spring commitTransaction(T1)
  -> T1 commit ACK succeeds
  -> AFTER_COMMIT listener executes
       -> NotificationGateway sends notification
~~~

Do not read the line `events.publishEvent(...)` as “the email has been sent.” The Spring application event is published there, but a listener with a transaction phase waits for transaction completion.

### 6.4. Rollback Timeline

~~~text
Caller --> Spring proxy
  -> transaction T2
  -> updates orders (T2)
  -> events.publishEvent(OrderApproved)
       -> AFTER_COMMIT listener waits
  -> throws IllegalStateException
  -> Spring abortTransaction(T2)
  -> AFTER_COMMIT listener DOES NOT run
  -> order is not committed
~~~

If the service throws a checked exception **without** `rollbackFor`, Spring may still commit under its default rollback rules. In that case, the `AFTER_COMMIT` listener **can still run** even though the caller receives a checked exception. The phase depends on the **transaction outcome**, not directly on whether the controller sees an exception.

## 7. What Does the Listener Do When There Is No Transaction?

This is a common configuration mistake:

~~~java
events.publishEvent(
    new OrderApproved("evt-011", "t01", "order-011-01")
);
~~~

If the code above runs **outside a transaction** and `@TransactionalEventListener` does not set `fallbackExecution`:

> By default, Spring **does not invoke the listener** because there is no transaction synchronization to bind the phase to.

### 7.1. `fallbackExecution = true`

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onEvent(OrderApproved event) {
    notificationGateway.notifyOrderApproved(event);
}
~~~

When a valid transaction exists, the listener waits for the phase. When **there is no transaction**, Spring can process it immediately via the fallback, meaning **there is no commit to wait for**.

**Do not unconditionally enable fallback** just to “fix a listener not firing.” If the requirement is to **notify only after commit**, `fallbackExecution = true` can break that contract.

### 7.2. Why Can a Transaction Be Missing Without You Realizing It?

Common causes:

- `MongoTransactionManager` is not declared.
- `@Transactional` is on a method called internally via `this.method()`, bypassing the proxy.
- The service was instantiated with `new` instead of injected as a Spring bean from the container.
- Work runs on another thread via `CompletableFuture`/`@Async` without an active transaction scope.
- Using the wrong transaction manager (JPA/JDBC instead of MongoDB) or a template backed by a different `MongoDatabaseFactory`.
- Publishing the event after the transactional service has already returned and the transaction has ended.
- In reactive code, losing the `Reactor Context` or using a publisher that does not participate in the transaction.

### 7.3. Checking Transaction Status in Imperative Mode

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
~~~

These two flags have different meanings: an active transaction and enabled transaction synchronization **are not identical concepts in every configuration**. Use them for diagnostics; they will not make a misconfigured transaction manager valid.

**Do not use** these two thread-local APIs to prove a reactive transaction is active. Reactive transactions rely on the `Reactor Context` and the reactive transaction manager.

## 8. The Four Phases of `@TransactionalEventListener`

`TransactionPhase` provides four standard options:

| Phase | When it runs | Suitable use cases | Caveat |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before committing the transaction | Final checks, data preparation | Exceptions can cause the commit to fail / roll back |
| `AFTER_COMMIT` | After a successful commit | Best-effort notification, invalidation | Crash window; listener errors **do not undo the commit** |
| `AFTER_ROLLBACK` | After rollback | Telemetry, careful out-of-DB cleanup | Do not use to “delete again” an already-aborted document |
| `AFTER_COMPLETION` | After commit **or** rollback | Shared resource cleanup/metrics | Do not assume it means success |

### 8.1. `BEFORE_COMMIT` Is Unsuitable for Emails

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT
)
public void beforeCommit(OrderApproved event) {
    // Suitable for invariant checks; DO NOT send emails here.
}
~~~

If the callback sends an email before the transaction commits and the commit subsequently fails, the external recipient receives an erroneous notification.

`BEFORE_COMMIT` also does not guarantee the commit will succeed; write conflicts, network failures, majority write concern errors, or commit-time failures can still occur.

### 8.2. `AFTER_ROLLBACK` Does Not Mean “You Can Compensate Everything”

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_ROLLBACK
)
public void afterRollback(OrderApproved event) {
    // Example: record metrics for rejecting a workflow or clean up resources
    // outside the database transaction.
}
~~~

This only fires if the event was already published inside the transaction and the transaction later rolled back. If an exception happens **before the `publishEvent` call**, this listener knows nothing about it. If you need to audit **every failed attempt**, you need a dedicated audit path rather than relying on an event from a statement that never executed.

### 8.3. `AFTER_COMPLETION` Runs for Both Outcomes

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMPLETION
)
public void afterCompletion(OrderApproved event) {
    // This is not the default place to send an "Approved" notification.
}
~~~

If you need to distinguish commit from rollback, use two separate listeners or transaction synchronization with the appropriate status; never infer from the event name `OrderApproved` that this phase only runs on success.

### 8.4. Multiple Events Within the Same Transaction

~~~java
events.publishEvent(new OrderApproved("e1", tenantId, id1));
events.publishEvent(new OrderApproved("e2", tenantId, id2));
~~~

Each publication registers a callback invocation with transaction synchronization. Spring does not coalesce multiple similar business events into one, does not deduplicate them, and does not turn them into a persistent queue.

If you need “at most one event per transition,” design event IDs, conditional updates, and transaction/outbox uniqueness accordingly.

## 9. After Commit, Transaction Resources May Still Be Bound

The Spring Framework documentation warns: inside `AFTER_COMMIT`/`AFTER_COMPLETION` callbacks, transaction resources can sometimes still be **bound to the current context** while cleanup has not yet finished.

### 9.1. Pitfall of Writing to the DB Inside a Post-Commit Listener

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void afterCommit(OrderApproved event) {
    // Do not assume the following operation will reliably commit
    // under a new transaction:
    mongoTemplate.save(new DeliveryAudit(...));
}
~~~

`DeliveryAudit` in the snippet is an illustrative class, not a Spring Data type. When synchronization/transaction resources remain bound, DB operations may **join the old resources** after its commit has already finished, with no subsequent commit occurring for the new writes. **Do not treat `afterCommit` as a place that automatically starts a fresh transaction.**

### 9.2. If You Must Write New DB State: Use a Separate `REQUIRES_NEW` Service

~~~java
// DeliveryAuditWriter.java
package com.example.mongoevents;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class DeliveryAuditWriter {
    private final MongoTemplate mongo;

    public DeliveryAuditWriter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager",
        propagation = Propagation.REQUIRES_NEW
    )
    public void writeAudit(DeliveryAudit audit) {
        mongo.insert(audit);
    }
}
~~~

`DeliveryAudit` is an entity your project must define completely; the snippet illustrates requiring a **new transaction** on a **separate bean**, invoked through a proxy. Calling `this.writeAudit(...)` from the same class can bypass `REQUIRES_NEW` interception.

**Design consideration:** If this audit/event is critical, writing an **outbox/audit record inside the original transaction** is safer than waiting for commit and opening a second transaction. `REQUIRES_NEW` after commit still has a crash window between the two transactions.

### 9.3. Separating Listener Exceptions from Database Outcomes

An `AFTER_COMMIT` listener can throw an exception:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void send(OrderApproved event) {
    throw new IllegalStateException("Notification service unavailable");
}
~~~

**The committed order does not automatically roll back.** Whether the exception is logged, propagated to the caller, or handled by an error handler depends on the listener/transaction synchronization mechanism, multicaster, async configuration, and Spring version. Never assume “caller received an error ⇒ database did not commit” or “listener exceptions are always swallowed.”

The system must clearly separate **database committed** status from **notification delivered** status and track them with distinct metrics/event IDs.

## 10. Synchronous, Asynchronous, and Listener Durability

### 10.1. “After Commit” Does Not Mean “Runs in the Background”

`@TransactionalEventListener(AFTER_COMMIT)` participates in transaction synchronization by default. In a standard configuration, the callback runs on the thread handling transaction completion. It **does not automatically create a durable queue** or a retry job.

If a side effect such as an HTTP call takes 10 seconds, the request can still incur latency depending on the execution model. Deadlines and isolation for external dependencies must be considered.

### 10.2. `@Async` Changes Where Execution Runs, Not Durability

Using an async executor or asynchronous event multicaster carries important caveats:

- Transaction context from the original thread **does not automatically travel** to the new thread.
- Do not let transactional listener registration happen on an executor lacking transaction context.
- Background exceptions typically require dedicated error handlers and metrics.
- If the process crashes after commit—either before or after enqueuing the task onto the executor—in-memory tasks can be lost.
- Security context, tenant context, and tracing context must be propagated properly without exposing sensitive data in logs.

Do not treat `@Async` as a reliable delivery mechanism. When durability is required, use a persisted outbox/queue with an explicit retry contract.

### 10.3. Three Critical Crash Windows

~~~text
W1. Before MongoDB commit
    -> can abort; AFTER_COMMIT listener has not been invoked.

W2. MongoDB commit succeeded, process crashes
    -> may LOSE in-memory-only event.

W3. External API already processed, process crashes before recording result
    -> retry may SEND DUPLICATE.
~~~

`AFTER_COMMIT` handles window W1 properly, but **does not solve W2/W3**. A transactional outbox substantially solves W2 by persisting the work to be sent within the same commit, while W3 still requires an idempotent consumer / reconciliation.

## 11. Business Events Are Not the Same as Spring Data Entity Events

### 11.1. Events Should Describe What Happened in Business Terms

Name events as:

~~~text
OrderApproved
PaymentConfirmed
StockReservationCreated
CustomerEmailVerified
~~~

Rather than merely:

~~~text
OrderSaved
DocumentUpdated
MongoEntityChanged
~~~

`OrderApproved` carries business meaning and invariants: tenant, order, transition ID, and new state. `AfterSaveEvent<OrderDocument>` only states that a mapping save API executed; it can fire when updating fields unrelated to approval.

### 11.2. Domain Events Should Originate in the Service Layer

~~~java
UpdateResult result = mongo.updateFirst(
    pendingQuery, approveUpdate, OrderDocument.class
);

if (result.getMatchedCount() == 1) {
    events.publishEvent(
        new OrderApproved(eventId, tenantId, orderId)
    );
}
~~~

The emission source belongs in the **validated transition command**. If the update did not match, do not emit a success event. Tenant/state conditions must still be enforced at the database; a listener notification cannot undo an unauthorized write.

### 11.3. Domain Events on Spring Data Repositories

Spring Data Commons provides `@DomainEvents` / `@AfterDomainEventPublication` on aggregate roots to support publishing events during certain repository methods. This is a **repository-layer publication mechanism**, not a replacement for transaction synchronization or a durable outbox.

Caveats:

- Publication can happen before the transaction commits.
- Some write paths such as `MongoTemplate.updateMulti` or raw driver calls bypass aggregate domain events.
- Delete-by-ID or mass deletes may not instantiate the aggregate to collect events.
- In-memory events can be lost on process crash.

If you want to react **after commit**, tie publication to a transaction phase. If events must not be lost after commit, **persist** the event/outbox within the same transaction.

## 12. Approach B: Transactional Outbox for Side Effects That Must Be Reliably Delivered

A **transactional outbox** is a collection holding events/messages intended for post-commit delivery. With MongoDB:

~~~text
In transaction T1:
   update orders_events_011
   insert outbox_events_011
   commit T1

Outside transaction T1:
   OutboxDispatcher reads PENDING
   claims event and sends to external system
   marks DELIVERED or schedules retry
~~~

If transaction T1 aborts, **neither** the order approval **nor** the corresponding outbox event exists. If T1 commits successfully, the outbox record survives a process crash so workers can pick it up.

### 12.1. Service Atomically Writing the Order and Outbox

~~~java
// ReliableOrderService.java
package com.example.mongoevents;

import com.mongodb.client.result.UpdateResult;
import java.time.Clock;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReliableOrderService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public ReliableOrderService(
            MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void approve(String tenantId, String orderId) {
        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        UpdateResult updated = mongo.updateFirst(
            eligible,
            new Update().set("state", "APPROVED"),
            OrderDocument.class
        );

        if (updated.getMatchedCount() != 1) {
            throw new OrderStateConflictException(
                "No eligible order");
        }

        String eventId = "order-approved:" + orderId;

        mongo.insert(new OutboxEvent(
            eventId,
            tenantId,
            orderId,
            "OrderApproved",
            clock.instant()
        ));
        // The commit of BOTH writes happens after the method returns,
        // at the transactional proxy.
    }
}
~~~

`Clock` is a dependency enabling deterministic time testing; a bean must be provided:

~~~java
@Bean
java.time.Clock clock() {
    return java.time.Clock.systemUTC();
}
~~~

This is a `@Bean` method placed in a `@Configuration` class; the configuration can sit alongside `MongoTransactionConfig`. Do not create a new bean per request.

### 12.2. A Pre-Commit Failure Scenario

Suppose the order update succeeds inside the transaction, but `mongo.insert(outbox)` throws `DuplicateKeyException` due to a colliding `_id`. With transactions configured properly:

~~~text
update order -> succeeds inside transaction
insert outbox -> E11000
Spring rolls back/aborts transaction
APPROVED order not committed -> does not exist
new outbox -> does not exist
~~~

Any **pre-existing** outbox record is not deleted when the new transaction aborts. This is why you must not write indiscriminate compensation like `deleteById(outboxId)` when a transaction rolls back.

### 12.3. Idempotency Key in the Outbox

`_id = "order-approved:" + orderId` ensures two outbox records with the same key cannot be created. If business rules allow re-approving the same order after reopening, replace `eventId` with a key combining **orderId + transitionVersion** or a **business command ID**.

The goal is to identify **one logical event**, not “one HTTP request.” Retrying after a timeout with a different `eventId` can record two identical logical events.

### 12.4. How Many Indexes Are Needed?

Besides the built-in unique `_id` index, workers can use indexes such as:

~~~javascript
db.outbox_events_011.createIndex(
  { status: 1, next_attempt_at: 1, _id: 1 },
  { name: "ix_outbox_due" }
);

db.outbox_events_011.createIndex(
  { status: 1, lease_until: 1 },
  { name: "ix_outbox_expired_lease" }
);
~~~

These indexes support querying **due PENDING** events and **SENDING events with expired leases**. Real-world tuning depends on event volume, selectivity, sort order, shard key, write amplification, and `explain("executionStats")`. Do not add excessive indexes without measuring the cost.

## 13. Outbox Worker: Claim Atomically, Send, Then Record

For multiple instances to process the outbox concurrently, each event must be **claimed** before sending. Do not write:

~~~java
// WRONG when multiple workers are running:
OutboxEvent event = mongo.findOne(pendingQuery, OutboxEvent.class);
gateway.send(event);
mongo.updateFirst(markDelivered, ...);
~~~

Two workers can read the same `PENDING` event and both send it. A “read” state is not a lock.

### 13.1. Recommended State Machine

~~~mermaid
flowchart LR
    P["PENDING"] -->|"claim"| S["SENDING"]
    S -->|"external ACK + mark"| D["DELIVERED"]
    S -->|"transient failure"| R["PENDING / retry later"]
    S -->|"lease expired"| S2["SENDING / another worker claims"]
    S -->|"permanent failure or max retries"| X["DEAD_LETTER"]
    R -->|"re-claim"| S
    S2 -->|"retry claim"| S
~~~

`DEAD_LETTER` is a business design choice, not a MongoDB built-in state. Production deployments also track worker owner/token, retry count, next attempt, exponential backoff, and operational alerts.

### 13.2. Claiming with `findAndModify`

~~~java
// OutboxClaimService.java
package com.example.mongoevents;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OutboxClaimService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public OutboxClaimService(MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    public OutboxEvent claimNext() {
        Instant now = clock.instant();
        String claimToken = UUID.randomUUID().toString();

        Criteria duePending = Criteria.where("status").is("PENDING")
            .and("nextAttemptAt").lte(now);

        Criteria expiredLease = Criteria.where("status").is("SENDING")
            .and("leaseUntil").lt(now);

        Query eligible = Query.query(
            new Criteria().orOperator(duePending, expiredLease)
        ).with(Sort.by(
            Sort.Order.asc("nextAttemptAt"),
            Sort.Order.asc("id")
        ));

        Update claim = new Update()
            .set("status", "SENDING")
            .set("leaseUntil", now.plus(Duration.ofSeconds(30)))
            .set("leaseToken", claimToken)
            .inc("attempts", 1);

        return mongo.findAndModify(
            eligible,
            claim,
            FindAndModifyOptions.options().returnNew(true),
            OutboxEvent.class
        );
    }
}
~~~

`findAndModify` is an **atomic single-document operation**: each call claims at most one document matching the filter when the write is applied. Two concurrent workers cannot both claim the same `PENDING` record because the first transitions it to `SENDING`.

**Important limit:** After 30 seconds, worker A’s lease can expire **even if A is still slowly sending**. Worker B can re-claim the event. Therefore, the system must still tolerate **duplicate deliveries** and enforce `eventId`/idempotency on the receiver; a lease does not turn an outbox into exactly-once delivery.

### 13.3. Fencing Tokens Prevent Stale Workers from Overwriting State

Suppose A claims an event with token `A1`, the lease expires, and B re-claims it with token `B2`. A must not be allowed to “mark DELIVERED” using the expired token.

~~~java
public boolean markDelivered(
        String eventId, String claimToken) {

    Query mine = Query.query(
        Criteria.where("id").is(eventId)
            .and("status").is("SENDING")
            .and("leaseToken").is(claimToken)
    );

    Update done = new Update()
        .set("status", "DELIVERED")
        .unset("leaseUntil")
        .unset("leaseToken");

    var result = mongo.updateFirst(
        mine, done, OutboxEvent.class
    );
    return result.getMatchedCount() == 1;
}
~~~

This method can live in `OutboxClaimService` (which already holds `mongo`) or in a dedicated state writer. It protects **the state update in MongoDB**, though it cannot prevent the external API from being called twice if workers A and B send concurrently.

### 13.4. Controlled Retries

For retryable errors, only the writer currently holding the token may move the record back to `PENDING` and schedule `nextAttemptAt`:

~~~java
public boolean scheduleRetry(
        String eventId,
        String claimToken,
        Instant nextAttemptAt) {

    Query mine = Query.query(
        Criteria.where("id").is(eventId)
            .and("status").is("SENDING")
            .and("leaseToken").is(claimToken)
    );

    Update retry = new Update()
        .set("status", "PENDING")
        .set("nextAttemptAt", nextAttemptAt)
        .unset("leaseUntil")
        .unset("leaseToken");

    return mongo.updateFirst(
        mine, retry, OutboxEvent.class
    ).getMatchedCount() == 1;
}
~~~

Do not retry every error identically. For example, if the external API returns a validation error because the payload is invalid, waiting and retrying indefinitely helps nothing; transition it to `DEAD_LETTER` and alert operations. For HTTP 429/503, respect `Retry-After`, exponential backoff, jitter, and attempt caps.

### 13.5. Do Not Hold a MongoDB Transaction Open During External API Calls

**Do not do this:**

~~~java
@Transactional
public void claimSendAndMark(...) {
    claimEventInMongo();
    emailClient.send(...); // external network call, may take 30 seconds
    markDeliveredInMongo();
}
~~~

You cannot roll back an email inside a MongoDB transaction; holding a transaction open across HTTP calls increases contention, snapshot overhead, and timeouts. Split it into:

~~~text
DB atomic claim (short single-document transaction)
    -> external send outside MongoDB transaction
    -> DB atomic mark/lease-token guard
~~~

### 13.6. Single-Pass Dispatcher

~~~java
public void dispatchOne() {
    OutboxEvent event = claims.claimNext();
    if (event == null) {
        return;
    }

    try {
        gateway.send(
            event.getId(),          // External Idempotency-Key
            event.getKind(),
            event.getAggregateId()
        );

        boolean committed = claims.markDelivered(
            event.getId(), event.getLeaseToken()
        );
        if (!committed) {
            metrics.recordLostLease(event.getId());
        }
    } catch (RetryableDeliveryException ex) {
        claims.scheduleRetry(
            event.getId(),
            event.getLeaseToken(),
            nextRetryTime(event.getAttempts())
        );
    }
}
~~~

Here `gateway`/`claims` are worker service dependencies, `metrics` is a telemetry adapter, `RetryableDeliveryException` is a custom exception, and `nextRetryTime(...)` is a bounded exponential backoff function. This is **Java orchestration pseudocode** without concrete adapter definitions; do not copy it to production without permanent-failure handling and monitoring.

The dispatcher must verify:

- Classification of retryable vs. permanent exceptions.
- If a worker crashes after the external ACK but before `markDelivered`, retries can resend.
- If a lease expires, the old worker may still complete sending even though it fails to mark delivered; metrics and idempotency are essential.
- Avoid thousands of workers spinning `claimNext()` continuously when the queue is empty; use scheduling/backoff or event notifications.
- Protect tenant boundaries, credentials, and sensitive event information.

## 14. Why Does an Outbox Typically Provide At-Least-Once Semantics?

Consider this timeline:

~~~text
t0  T1 commits order + outbox.
t1  Worker A claims event e1.
t2  Worker A calls external API; remote receives and processes e1.
t3  Worker A crashes BEFORE marking DELIVERED.
t4  Lease on e1 expires.
t5  Worker B re-claims e1 and sends same eventId.
~~~

The receiver can receive the event **twice**, even though MongoDB holds exactly one outbox record. This is **at-least-once delivery attempt**, not an exactly-once external effect.

### 14.1. Receiver-Side Idempotency Contract

The receiver can maintain a table/collection:

~~~text
processed_events
  _id = eventId
  processed_at = ...
~~~

When receiving an event:

1. Validate `eventId`/fingerprint and tenant authorization.
2. Ensure the **business effect is applied at most once** per `eventId` using a unique key and appropriate atomic operation/transaction.
3. If the same `eventId` arrives again with the same payload, return the previously processed outcome.
4. If the same `eventId` arrives with a different payload, treat it as a **conflict/security anomaly** rather than silently ignoring it.

If the receiver uses MongoDB, it can enforce a unique `_id` in `processed_events` and insert the marker **in the same transaction** as the receiver’s business update. Writing the marker first and performing the side effect outside a transaction risks persisting the marker while the business effect never takes place.

### 14.2. What If an Email Provider Does Not Support Idempotency?

If an email provider lacks an idempotency-key API, the application can check a sent marker, yet it cannot completely eliminate the crash window:

~~~text
Send email succeeds -> crash before marker
Retry -> email may be sent again
~~~

Achieving near “once” semantics requires idempotency support from **the point executing the final effect**, or accepting duplicate possibilities and designing UX accordingly. Never claim “outbox guarantees sending emails exactly once” merely because outbox `_id` is unique.

### 14.3. Event Ordering

If an aggregate produces:

~~~text
OrderApproved(version=5)
OrderShipped(version=6)
~~~

Concurrent outbox workers can deliver version 6 before version 5 if no ordering rules exist. When downstream consumers require ordering:

- Store `aggregateId` and `aggregateVersion` on the event.
- Partition work by aggregate key.
- Have consumers handle conditional versions or wait on gaps.
- Enforce idempotency/version guards when updating state.

Sorting by `createdAt` only establishes **dispatch priority**, not guaranteed **external ACK order** across multiple workers and concurrent network calls.

### 14.4. Delivery Acknowledgement Differs from Business Commit

There are three milestones:

~~~text
Business MongoDB transaction committed
          ↓
Outbox event claimed and sent
          ↓
External consumer acknowledged / processed
~~~

An API can return `200/204` at the first milestone if its contract only promises the order is approved and notification follows asynchronously. If synchronous external confirmation is required, define a dedicated state like `PENDING_EXTERNAL_CONFIRMATION`; never stretch a MongoDB transaction to wait on a remote response.

## 15. Polling, Scheduling, and Change Streams

### 15.1. Polling Is a Simple Baseline

A worker can call `claimNext` on a schedule (for example every few hundred milliseconds to a few seconds, depending on SLOs). With Spring:

~~~java
@Scheduled(fixedDelayString = "${app.outbox.poll-delay-ms:1000}")
public void poll() {
    dispatcher.dispatchOne();
}
~~~

This requires `@EnableScheduling` in your configuration. `fixedDelay` measures from the end of the previous run; each poll handles one event in this example. At high throughput, you need time-bounded batch loops, concurrency controls, and worker starvation safeguards.

**Note:** `app.outbox.poll-delay-ms` is a **custom application property**, not a Spring Data MongoDB built-in property.

### 15.2. MongoDB Change Streams to Reduce Latency

A change stream can watch outbox inserts/updates when MongoDB runs as a replica set or supported sharded cluster. When new events arrive, workers wake up sooner than waiting for the next poll.

However, change streams involve:

- Persisting and managing resume tokens across reconnects.
- Finite oplog history; resume tokens can become invalid after prolonged outages.
- Events potentially being reprocessed on reconnect/crash between delivery and checkpointing.
- Controlling consumer lag, pipeline filters, and access permissions.

**Robust design:** treat the persisted outbox collection as the **source of truth**; use change streams purely to **trigger early wake-ups**, while keeping polling/reconciliation scans to recover from missed notifications or lost resume tokens.

### 15.3. Business Collection Change Streams Are Not Automatically an Outbox

Watching the `orders` change stream and inferring `OrderApproved` from raw BSON updates can:

- Confuse a metadata update with a business transition.
- Miss tenant/commandId/actor/event-version context.
- Make it difficult to construct a canonical payload for consumers.
- Depend heavily on change stream options (`fullDocument`/lookup/`updateDescription`).

An outbox record captures **domain event semantics** far more clearly; you can instead open a change stream **on the outbox** to trigger delivery.

## 16. Limits of “Eventual Consistency”

When an order commits before its email or inventory update finishes, the system temporarily exhibits two consistent point-in-time states:

~~~text
Order service: APPROVED
Inventory service: reservation not yet applied
~~~

That is **eventual consistency**, not automatically a bug if the contract permits it. APIs and UX should reflect this:

- Use `APPROVED_PENDING_FULFILLMENT` when an essential external step remains.
- Apply per-step retries/timeouts rather than blindly retrying the entire approve command.
- Enable reconciliation using `eventId` and `orderId`.
- Alert when outbox pending age breaches SLA.
- Provide compensation/saga workflows if the external effect ultimately cannot complete.

If a business workflow **cannot tolerate** a temporary inconsistency window across systems, revisit aggregate boundaries, architecture, and consistency requirements; a MongoDB transaction only covers MongoDB resources enrolled in that transaction, and cannot span SMTP/Kafka/HTTP services via an annotation.

## 17. Reactive Applications: Transaction Context Differs from Imperative

In reactive Spring Data MongoDB, the transaction manager is `ReactiveMongoTransactionManager`, and transaction context propagates via the **Reactor Context** rather than solely thread-locals.

### 17.1. Reactive Transaction Manager Beans

~~~java
// ReactiveMongoTransactionConfig.java
package com.example.mongoevents;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

This configuration is for reactive applications; do not configure the imperative `MongoTransactionManager` expecting it to manage a `ReactiveMongoTemplate` pipeline.

### 17.2. Writing Order and Outbox Sequentially in a Reactive Transaction

~~~java
// ReactiveReliableOrderService.java
package com.example.mongoevents;

import java.time.Clock;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReliableOrderService {
    private final ReactiveMongoTemplate mongo;
    private final TransactionalOperator operator;
    private final Clock clock;

    public ReactiveReliableOrderService(
            ReactiveMongoTemplate mongo,
            TransactionalOperator operator,
            Clock clock) {
        this.mongo = mongo;
        this.operator = operator;
        this.clock = clock;
    }

    public Mono<Void> approve(
            String tenantId, String orderId) {

        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("state").is("PENDING")
        );

        Mono<Void> work = mongo.updateFirst(
                eligible,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            )
            .flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new OrderStateConflictException(
                            "No eligible order"));
                }

                OutboxEvent outbox = new OutboxEvent(
                    "order-approved:" + orderId,
                    tenantId, orderId,
                    "OrderApproved", clock.instant()
                );

                return mongo.insert(outbox).then();
            });

        return work.as(operator::transactional);
    }
}
~~~

`updateFirst` is subscribed before `insert(outbox)` because they are chained with `flatMap`, and **both execute within the same reactive transaction** managed by `TransactionalOperator`.

**Do not write**:

~~~java
// Wrong: parallel operations within the same MongoDB transaction
// return Mono.when(
//     mongo.updateFirst(...),
//     mongo.insert(outbox)
// ).as(operator::transactional);
~~~

The MongoDB Java Reactive Streams Driver does not support **parallel operations within the same transaction**; moreover, the outbox write depends on the order update actually matching. Chain them sequentially as shown above.

### 17.3. Reactive `@TransactionalEventListener` Requires Transaction Context in the Event

Starting with Spring Framework **6.1**, transactional event listeners also support reactive transactions. However, reactive transaction state lives in the **Reactor Context**, not thread-locals.

Therefore, when publishing reactive transactional events:

- Ensure the event **carries transaction context in its source** per Spring’s contract.
- `org.springframework.transaction.reactive.TransactionalEventPublisher` is the utility Spring provides to publish events attached to the proper transaction context.
- Calling a plain `ApplicationEventPublisher.publishEvent(...)` outside reactive context **does not automatically ensure** the `AFTER_COMMIT` listener fires properly.
- Event publication must be **composed into the reactive chain**, not triggered via a detached `subscribe()`.
- Without a transaction, `fallbackExecution` carries the same trap: the listener may execute immediately with no commit to wait for.

When an event is **critical**, a reactive `approve` method like section 17.2 writing an outbox record **inside the transaction** is simpler for durability and reconciliation than relying solely on publishing events through the Reactor Context.

### 17.4. Cancellation Does Not Prove the Transaction Rolled Back

A WebFlux client disconnects while the server is committing:

~~~text
Publisher canceled / HTTP request timeout
              ≠
MongoDB definitely aborted
~~~

The commit may already have reached the server and succeeded while the client never received the acknowledgment. Use a stable `eventId`/`orderId` and perform reconciliation reads under an appropriate read concern/consistency policy.

Never retry a business event by generating a new ID merely because the client lost connection.

## 18. Integration Testing: Runs After Commit, Skipped on Rollback

Mocking `MongoTemplate` directly does not verify that transaction synchronization works. Use a **test MongoDB replica set** and a real Spring context.

### 18.1. Essential Test Matrix

| Scenario | DB state after service proxy finishes | AFTER_COMMIT listener |
| --- | --- | --- |
| Transaction commits successfully | Order APPROVED | Called once per published event |
| RuntimeException before commit | Order remains PENDING | **Not called** |
| Checked exception without rollback override | Transaction may commit | May be called if commit succeeds |
| Checked exception with `rollbackFor` | Order remains PENDING | Not called |
| Event published outside transaction, fallback false | N/A | Not called |
| Event published outside transaction, fallback true | No transaction | May run immediately |
| Transaction commits, process crashes before listener | DB committed | **Notification may be lost** |
| Listener calls external service and fails | DB stays committed | May cause duplicates on retry |
| Outbox transaction commits | Order APPROVED + outbox exists | Independent of listener |
| Duplicate outbox insert inside transaction | Order rolled back | No new outbox written |
| Worker crashes after external ACK before `markDelivered` | Outbox not yet DELIVERED | May retry and resend |

The two crash rows require dedicated **fault-injection/chaos tests**; they cannot be proven by ordinary unit tests alone.

### 18.2. Recording Gateway in Tests

~~~java
// RecordingNotifications.java (test source)
package com.example.mongoevents;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class RecordingNotifications
        implements NotificationGateway {

    private final CopyOnWriteArrayList<OrderApproved> received =
        new CopyOnWriteArrayList<>();

    @Override
    public void notifyOrderApproved(OrderApproved event) {
        received.add(event);
    }

    public List<OrderApproved> snapshot() {
        return List.copyOf(received);
    }

    public void reset() {
        received.clear();
    }
}
~~~

The recording gateway does not send real emails; it only observes listener invocations. It does not simulate network or remote response behavior.

### 18.3. Test Beans Injecting the Gateway and Clock

~~~java
// MongoEventsTestBeans.java (test source)
package com.example.mongoevents;

import java.time.Clock;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
public class MongoEventsTestBeans {

    @Bean
    RecordingNotifications recordingNotifications() {
        return new RecordingNotifications();
    }

    @Bean
    NotificationGateway notificationGateway(
            RecordingNotifications recording) {
        return recording;
    }

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}
~~~

In a real application, replace the recording adapter with the gateway supplying external notifications. In tests, ensure no other `NotificationGateway` bean conflicts or use `@Qualifier`.

### 18.4. Testing Commit/Rollback and Outbox Atomicity

~~~java
// MongoBusinessEventsTest.java (test source)
package com.example.mongoevents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
    MongoTransactionConfig.class,
    BestEffortOrderService.class,
    ReliableOrderService.class,
    OrderNotificationListener.class,
    MongoEventsTestBeans.class
})
class MongoBusinessEventsTest {

    private static final String TENANT = "it-mongo-evt-011";
    private static final String OK = "it-evt-011-ok";
    private static final String ABORT = "it-evt-011-abort";
    private static final String OUTBOX = "it-evt-011-outbox";
    private static final String CONFLICT = "it-evt-011-conflict";

    @Autowired MongoTemplate mongo;
    @Autowired BestEffortOrderService bestEffort;
    @Autowired ReliableOrderService reliable;
    @Autowired RecordingNotifications notifications;

    @BeforeEach
    void setUp() {
        // Create collections outside the transaction in an isolated test DB.
        if (!mongo.collectionExists(OrderDocument.class)) {
            mongo.createCollection(OrderDocument.class);
        }
        if (!mongo.collectionExists(OutboxEvent.class)) {
            mongo.createCollection(OutboxEvent.class);
        }

        clearFixtures();
        notifications.reset();

        for (String id : new String[] {
                OK, ABORT, OUTBOX, CONFLICT }) {
            mongo.insert(new OrderDocument(
                id, TENANT, "PENDING", 250000L
            ));
        }
    }

    @AfterEach
    void tearDown() {
        clearFixtures();
        notifications.reset();
    }

    private void clearFixtures() {
        for (String id : new String[] {
                OK, ABORT, OUTBOX, CONFLICT }) {
            mongo.remove(
                Query.query(Criteria.where("id").is(id)),
                OrderDocument.class
            );
            mongo.remove(
                Query.query(Criteria.where("id").is(
                    "order-approved:" + id)),
                OutboxEvent.class
            );
        }
    }

    @Test
    void afterCommitNotifiesAfterDatabaseCommit() {
        bestEffort.approve(TENANT, OK);

        assertThat(mongo.findById(
            OK, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");

        assertThat(notifications.snapshot())
            .extracting(OrderApproved::orderId)
            .containsExactly(OK);
    }

    @Test
    void afterCommitDoesNotRunAfterRollback() {
        assertThatThrownBy(() ->
            bestEffort.approveThenFail(TENANT, ABORT)
        ).isInstanceOf(IllegalStateException.class);

        assertThat(mongo.findById(
            ABORT, OrderDocument.class
        ).getState()).isEqualTo("PENDING");
        assertThat(notifications.snapshot()).isEmpty();
    }

    @Test
    void orderAndOutboxCommitTogether() {
        reliable.approve(TENANT, OUTBOX);

        assertThat(mongo.findById(
            OUTBOX, OrderDocument.class
        ).getState()).isEqualTo("APPROVED");
        assertThat(mongo.findById(
            "order-approved:" + OUTBOX,
            OutboxEvent.class
        )).isNotNull();
    }

    @Test
    void duplicateOutboxAbortsOrderUpdate() {
        String eventId = "order-approved:" + CONFLICT;

        mongo.insert(new OutboxEvent(
            eventId, TENANT, CONFLICT,
            "OrderApproved", java.time.Instant.now()
        ));

        assertThatThrownBy(() ->
            reliable.approve(TENANT, CONFLICT)
        ).isInstanceOf(DuplicateKeyException.class);

        assertThat(mongo.findById(
            CONFLICT, OrderDocument.class
        ).getState()).isEqualTo("PENDING");

        // The existing outbox record does not disappear due to the rollback
        // of the new transaction.
        assertThat(mongo.findById(
            eventId, OutboxEvent.class
        )).isNotNull();
    }
}
~~~

**Test constraints:** Use the Spring Boot test slice appropriate for your version (imports above illustrate Spring Boot 3.x), a running test MongoDB replica set, and an application context with the transaction manager. Tests **must not** carry `@Transactional` on the test method or test class because doing so alters the commit/rollback scope under observation.

Spring Boot 4 changes several packages/test starters; choose the matching version when integrating into a project. This lesson does not require running tests directly on an arbitrary project without checking dependencies and configuration first.

### 18.5. Additional Check for Behavior Outside a Transaction

Invoke:

~~~java
// Executed in a test method WITHOUT @Transactional:
events.publishEvent(
    new OrderApproved("outside-evt", TENANT, "outside-order")
);
~~~

With `@TransactionalEventListener(AFTER_COMMIT)` and `fallbackExecution=false`, the recording gateway **does not** receive this event.

If changed to `fallbackExecution=true`, the gateway can receive it immediately even without a transaction. Verify this with a dedicated test before enabling fallback.

### 18.6. Another Test: Listener Failure After Commit

A test `NotificationGateway` can deliberately throw an exception upon receiving an event. Verify:

- The committed order remains `APPROVED`.
- The handler/metric records the notification failure.
- Exception propagation behaves as expected for your Spring listener configuration.
- Whether a job/outbox exists to retry.

Do not write tests that only check `assertThrows(...)` and assume the DB rolled back; query the **actual database state after the proxy call**.

## 19. Reactive Integration Test for Outbox

For the reactive service in section 17, you need a MongoDB **replica set**, `ReactiveMongoTransactionManager`, and `StepVerifier` to test publishers.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import reactor.test.StepVerifier;

// Test setup already created order "rx-evt-011" in PENDING state
// and both collections before the transaction.
StepVerifier.create(
    reactiveReliableOrderService.approve(
        "test-tenant-rx-011", "rx-evt-011"
    )
).verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "rx-evt-011", OrderDocument.class
    )
)
  .assertNext(order ->
      assertThat(order.getState()).isEqualTo("APPROVED")
  )
  .verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "order-approved:rx-evt-011", OutboxEvent.class
    )
)
  .expectNextCount(1)
  .verifyComplete();
~~~

This snippet belongs inside a test method where `reactiveReliableOrderService` and `reactiveMongoTemplate` are injected, not a self-contained test class. Besides the happy path, also test inserting a duplicate outbox `_id` before approval: the publisher must emit an error and the order must remain `PENDING`.

Do not call `block()` inside WebFlux runtime code; in integration tests, use `StepVerifier` to subscribe and assert terminal signals. Simply creating a `Mono<Void>` without subscribing means the transaction/reactive write typically **has not executed**.

## 20. Common Issues and Diagnostics

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| `AfterSaveCallback` sends email for rolled-back order | Entity save callback runs before transaction commit | Move side effects to `AFTER_COMMIT` or outbox |
| `@TransactionalEventListener` misses events | Published outside transaction with fallback false | Check proxy/manager/synchronization |
| Listener runs even without a transaction | `fallbackExecution=true` enabled | Disable fallback if strict after-commit is required |
| `@EventListener` sends email before DB commit | `@EventListener` is not bound to transaction phases | Use transactional listener or outbox |
| Listener runs after checked exception | Spring defaults may commit checked exceptions | Configure `rollbackFor` per contract |
| `@Transactional` present yet DB commits per statement | Self-invocation or manager/template use different factories | Call via proxy; share the same `MongoDatabaseFactory` |
| Service returns yet listener runs at unexpected time | Confusing method body return with proxy commit | Observe lifecycle after transaction completion |
| `AFTER_COMMIT` listener errors, order stays `APPROVED` | Commit already happened | Separate business state from delivery state; retry via outbox |
| DB write inside `AFTER_COMMIT` is not persisted | Old transaction resources still bound, no new commit | Extract `REQUIRES_NEW` service or write outbox pre-commit |
| `REQUIRES_NEW` shows no effect | `this.method()` call or wrong manager | Separate bean via proxy; verify transaction |
| App crashes post-commit, no notification sent | In-memory listener is not durable | Transactional outbox |
| Two outbox workers send the same record | Polling `findOne` then sending without claiming | Atomic `findAndModify` + token/lease |
| Outbox duplicates despite unique `_id` | Crash after external ACK before marking `DELIVERED` | Receiver idempotency keyed by `eventId` |
| Worker stuck in `SENDING` forever | Missing lease expiry/recovery | Lease timeout, fencing token, monitoring |
| Worker A overwrites worker B’s status | Not checking token when updating status | Conditional update checking `claimToken` |
| Newly committed event not seen by worker | Poll interval / read preference / replication lag | Monitor lag, read consistency, retry scans |
| Change stream reconnects and misses events | Lost resume token or expired oplog window | Persist checkpoints and polling reconciliation |
| Consumer sees version 6 before version 5 | Concurrent delivery lacks ordering | Partition by aggregate; enforce version guards |
| One event published twice by business code | Missing idempotency/transition guard | State guard + unique `eventId`/fingerprint |
| Reactive listener misses transaction | Event lacks reactive transaction context | Use `TransactionalEventPublisher` / proper context |
| Reactive outbox partially committed | Writes not chained inside the same operator | Sequence update/insert within reactive transaction |
| Tests see no rollback on standalone | Standalone MongoDB lacks multi-document transactions | Use a test replica set |
| Mock tests pass, production emails go wrong | Mocks do not exercise commit/failure windows | Integration tests + fault injection |
| Unexpected callback order/transaction behavior | Driver/bulk/update paths bypass entity save lifecycle | Emit events in the application service |

## 21. Operations: Keeping the Outbox Healthy Long-Term

An outbox is only truly effective when its workers and recovery workflows are actively operated.

### 21.1. Minimum Metrics and Alerts

| Metric | Meaning |
| --- | --- |
| `outbox.pending.count` | Number of unsent events |
| `outbox.oldest_pending_age_seconds` | Age of the oldest undelivered event |
| `outbox.sending_expired_lease.count` | Worker crashes/hangs or missing lease renewals |
| `outbox.delivery_latency` | Time from business commit to external ACK |
| `outbox.delivery_attempts` | Retry storms and dependency issues |
| `outbox.dead_letter.count` | Events requiring manual remediation |
| `outbox.claim_conflicts` | Contention between workers |
| `outbox.mark_lost_lease` | Stale worker attempted to mark after token changed |
| `external.idempotency_conflicts` | Same `eventId` with differing payload |
| `transaction.commit_failures` | MongoDB tx/availability/durability issues |

Do not tag metrics per individual `orderId`/`eventId` on large systems because cardinality grows without bound. Use traces/logs with PII restrictions to investigate specific events.

### 21.2. Retention and Cleanup

After delivery:

- `DELIVERED` records may be retained for a defined audit/replay window.
- They may be archived separately before deletion.
- A TTL index on a timestamp may be used **only once the retention policy is explicitly defined**, ensuring `PENDING`/`SENDING` items are never purged accidentally.
- If using sharding, account for shard keys, load distribution, and transaction constraints.

**Never run `deleteMany({status: "PENDING"})` to “clear a slow queue.”** That destroys unfinished work.

### 21.3. Reconciliation Job

Run periodic jobs comparing:

~~~text
APPROVED Orders
    ↕
Corresponding OrderApproved outbox
    ↕
External delivery acknowledgement
~~~

In a sound outbox design, an `APPROVED` order missing an outbox entry typically indicates:

- Legacy data predating outbox migration.
- A code path updating orders directly without writing an outbox record.
- A transaction/session configuration error.
- Faulty cleanup or unsafe operational intervention.

Reconciliation must match on version/transition ID rather than assuming every currently `APPROVED` order needs a brand-new event when history was already processed or belonged to an earlier version.

### 21.4. Tenant Fairness Considerations

One high-volume tenant generating many events can saturate worker capacity. In multi-tenant systems:

- Enforce appropriate rate limits/quotas.
- Prevent batches from starving smaller tenants behind a single noisy tenant.
- Use partitioning, dedicated workers, or intentional round-robin scheduling if needed.
- Preserve tenant isolation across payloads and external destinations.

Never pass an unvalidated `tenantId` from an HTTP request directly to a higher-privilege external delivery endpoint.

## 22. Pre-Release Checklist

1. **Classify side effects:** best-effort or required to be persisted and retried?
2. **Clearly separate** entity lifecycle callbacks from transaction completion.
3. **Never send emails/HTTP from `AfterSaveCallback`** if DB writes can abort.
4. **Use `@TransactionalEventListener(AFTER_COMMIT)`** for best-effort notifications that tolerate the crash window.
5. **Verify `fallbackExecution`:** outside a transaction, should it be skipped or run immediately?
6. **Verify transaction manager, topology, proxy, and `MongoDatabaseFactory`.**
7. **Configure rollback rules** properly for checked and unchecked exceptions.
8. **Remember commits occur after method return;** do not trigger external side effects prematurely.
9. **Do not write DB state post-commit assuming an implicit new transaction.**
10. **Persist an outbox in the same transaction** whenever delivery cannot be lost on process crash.
11. **Keep outbox `eventId` stable** with uniqueness constraints matching domain semantics.
12. **Guard state transitions** on tenant, state, and version/idempotency.
13. **Claim outbox records atomically** using `findAndModify` or an equivalent mechanism.
14. **Use leases + fencing tokens** with crash recovery handling.
15. **Never hold MongoDB transactions open across external network calls.**
16. **Ensure idempotent receivers;** do not claim exactly-once semantics from the outbox alone.
17. **Design retry/backoff/dead-letter handling** according to error classes and SLOs.
18. **Establish event ordering** if consumers depend on aggregate versions.
19. **Keep polling reconciliation** even when using change streams for wake-ups.
20. **Use the right reactive transaction manager/context** with WebFlux.
21. **Verify commit/rollback against actual DB state**, not just callback invocations.
22. **Test crash windows and timeouts** in permitted chaos environments with recovery procedures.
23. **Protect personal data**, event payloads, logs, and outbox retention.
24. **Maintain dashboards/alerts** for pending age, retries, expired leases, and dead-letter counts.

## 23. Exercises with Answers

### Exercise 1 — `AfterSaveCallback`

An `AfterSaveCallback` sends an “Order approved” email. After the callback runs, the service throws `IllegalStateException` and the transaction rolls back. Is the email retracted?

**Answer:** No. The callback already triggered the external side effect before commit. Move email delivery to a best-effort `AFTER_COMMIT` listener or a durable outbox.

### Exercise 2 — `@EventListener`

If you only use `@EventListener` on an event published inside a transactional service, does it guarantee the listener runs after commit?

**Answer:** No. `@EventListener` does not bind to a transaction phase; you must use `@TransactionalEventListener(AFTER_COMMIT)` or another transaction-synchronization mechanism.

### Exercise 3 — Event Published Before Rollback

Inside transaction T1, code publishes `OrderApproved` and then throws a `RuntimeException`. Does the `AFTER_COMMIT` listener send the notification?

**Answer:** No, provided the transaction genuinely rolls back and the listener is bound to T1.

### Exercise 4 — Checked Exception

A service publishes an event and then throws an ordinary checked exception; can Spring commit the transaction?

**Answer:** Yes. By default Spring rolls back on `RuntimeException`/`Error`, not checked exceptions unless `rollbackFor` is configured; if it commits, the `AFTER_COMMIT` listener can run.

### Exercise 5 — Missing Transaction

An event for `@TransactionalEventListener(AFTER_COMMIT)` is published outside any transaction with `fallbackExecution=false`. What happens?

**Answer:** The listener is skipped because there is no transaction to bind the callback to.

### Exercise 6 — Fallback

Does setting `fallbackExecution=true` mean “wait for commit if there is no transaction”?

**Answer:** No. Outside a transaction, the listener can execute immediately; there is no commit to wait for.

### Exercise 7 — Self-Invocation

`this.approve()` invokes a `@Transactional` method on the same service instance. Why might the `AFTER_COMMIT` listener fail to run?

**Answer:** Self-invocation bypasses the proxy; a transaction may never start, so no synchronization phase exists. Invoke the entry point through the bean proxy.

### Exercise 8 — Writing to the DB After Commit

Inside an `AFTER_COMMIT` listener, you call `mongoTemplate.insert(audit)` expecting it to auto-commit in a new transaction. Is that correct?

**Answer:** No. Old transaction resources may remain bound with no new commit. If an independent DB write is required, use a separate `REQUIRES_NEW` service; for critical data, write the outbox/audit inside the original transaction.

### Exercise 9 — Crash Window

MongoDB commits successfully, then the application crashes before the `AFTER_COMMIT` listener calls the email service. Is the email guaranteed to be sent after restart?

**Answer:** No. An in-memory listener is not a durable queue. Use a transactional outbox to persist the work in the same commit.

### Exercise 10 — Transactional Outbox

A transaction updates an order and inserts an outbox record together. If the outbox insert fails with a duplicate key error and the transaction aborts, does the order remain `APPROVED`?

**Answer:** No. The update inside the transaction is not committed, and no new outbox record is created. Any pre-existing outbox record remains intact.

### Exercise 11 — `EventId`

A retried request generates a new `eventId` even though it represents the same business transition. What is the risk?

**Answer:** It can create two identical logical events. Use a deterministic ID derived from the business transition, version, or command ID.

### Exercise 12 — Two Workers

Two workers run `findOne({status:"PENDING"})` concurrently and both dispatch the event. How do you eliminate this race?

**Answer:** Claim atomically with `findAndModify`, transitioning `PENDING` → `SENDING` in a single operation.

### Exercise 13 — Expired Lease

Worker A claims an event with token A1; a long network stall causes the lease to expire. Worker B claims it with token B2. Should A be allowed to mark `DELIVERED` with token A1?

**Answer:** No. Use a conditional update on `eventId + status + leaseToken`; the stale token will not match.

### Exercise 14 — Exactly-Once

The outbox `_id` is unique and workers only pick one event per claim. Does that guarantee the external HTTP endpoint will never receive two requests?

**Answer:** No. A worker can crash after receiving the external ACK and before marking the DB; a retry will resend. Receivers should implement idempotency by `eventId`.

### Exercise 15 — External Side Effects Inside a Transaction

Why shouldn’t you keep a MongoDB transaction open while calling SMTP/HTTP?

**Answer:** MongoDB cannot roll back external effects, long transactions increase resource contention and timeouts, and remote failures complicate business reconciliation. Offload delivery to an outbox worker.

### Exercise 16 — `AFTER_ROLLBACK`

An error happens **before** the `events.publishEvent(...)` line. Will the `AFTER_ROLLBACK` listener for that event be called?

**Answer:** No, because the event was never published to register synchronization.

### Exercise 17 — Reactive Transactions

Can you run `Mono.when(updateOrder, insertOutbox)` inside a `TransactionalOperator`?

**Answer:** No. Operations within the same MongoDB transaction must not execute in parallel, and the outbox insert depends on the update matching. Use `update.flatMap(...insert...).as(tx::transactional)`.

### Exercise 18 — Reactive Event Context

In reactive code, does calling standard `ApplicationEventPublisher.publishEvent(event)` automatically ensure an `AFTER_COMMIT` listener sees the Reactor Context?

**Answer:** No. Spring Framework 6.1+ requires transaction context via the event source; `TransactionalEventPublisher` handles this. For critical delivery, prefer a reactive outbox.

### Exercise 19 — Change Streams

If a worker misses a change stream notification because its resume token expired, is the outbox record lost?

**Answer:** As long as the outbox record was persisted and not erroneously deleted, it remains in MongoDB. Workers can scan/reconcile and claim it; change streams are only a wake-up mechanism.

### Exercise 20 — Group Ordering

Two events `OrderApproved(v5)` and `OrderShipped(v6)` are dispatched concurrently by two workers. Is the receiver guaranteed to receive v5 before v6?

**Answer:** No. When ordering matters, use aggregate partitioning and version guards rather than relying solely on query sorting by `createdAt`.

### Exercise 21 — Testing

A test only asserts `NotificationGateway.notify...` was called once after calling the service. Does that prove the business transaction committed?

**Answer:** No. You must read the database state (order/outbox) after the transactional proxy call and verify rollback cases against a real test MongoDB replica set.

### Exercise 22 — Retention

Can you run `deleteMany({status:"PENDING"})` to shrink the outbox when the queue backs up?

**Answer:** No. That deletes pending, unprocessed work. Configure cleanup/TTL only for `DELIVERED`/eligible records according to your retention policy.

### Exercise 23 — Listener Failure

An `AFTER_COMMIT` listener throws an exception when sending an email. Does the MongoDB transaction revert to `PENDING`?

**Answer:** No. The commit has already completed; listener exceptions do not undo database state. Record the delivery failure and retry via an outbox or another mechanism.

### Exercise 24 — When Is an Outbox Unnecessary?

An internal monitoring metric for “Order approved” can tolerate occasional loss with no business impact. Do you have to use a transactional outbox?

**Answer:** No. Best-effort `AFTER_COMMIT` is appropriate; the operational cost of an outbox is justified when durability, retries, and reconciliation are required.

## References

- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `AbstractMongoEventListener`, mapping events, callback ordering, and limitations.
- [Spring Data MongoDB — Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, and reactive variants.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`, transaction options, and session binding.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify`, and bulk behavior.
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): `@DomainEvents` and `@AfterDomainEventPublication`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, phases, fallback, and reactive transaction context.
- [Spring Framework — `TransactionalEventListener` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): phase, `fallbackExecution`, and resource/commit caveats.
- [Spring Framework — `TransactionalEventPublisher` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html): publishing events with reactive transaction context.
- [Spring Framework — `TransactionSynchronization` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit`, `afterCompletion`, and bound resources.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW`, rollback scope, and proxy semantics.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): multi-document transaction atomicity and operational constraints.
- [MongoDB Manual — `findAndModify`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): atomic single-document claim and pre/post-update results.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): watching changes, resume tokens, and reconnect limitations.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): guaranteeing unique `eventId`/idempotency keys.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority, journal, acknowledgment, and rollback risk.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retries under transient errors and topology requirements.
