# Idempotency keys in Spring Kafka

Kafka consumers must normally accept the possibility that a record is delivered multiple times. A consumer may have written data to the database but the process crashed before committing the offset; a rebalance may assign the partition to another consumer; a producer or error handler may retry; or an operator may replay a record from a DLT. In those situations, the same **logical operation** can pass through the listener multiple times.

If every delivery creates a new side effect, the system may record duplicate orders, charge customers multiple times, send multiple emails, or generate repeated business entries. An **idempotency key** helps identify executions representing the same operation so the system applies the side effect only once under the chosen contract.

In the **Spring Kafka Reliability Operations** module, the idempotency key is a critical part of correctness and idempotency. Understand that a Kafka record key, an event ID, and an idempotency key may be related, but they are not synonymous. A reliable design must define the key scope clearly, generate stable keys, persist processing markers atomically with business side effects, handle concurrent duplicates, retain deduplication state long enough, and establish clear rules for retries, DLT, and replays.

This lesson covers how to design keys, implement an inbox/deduplication table with database transactions, protect external API calls, handle race conditions, choose retention, observe duplicates, and test crash boundaries.

## 1. What is idempotency?

An operation is called **idempotent** if executing it multiple times with the same input and the same identity does not alter the business outcome after the first execution.

For example, a command setting an order's status to SHIPPED can be designed to be idempotent:

~~~text
setOrderStatus(order-100, SHIPPED)

Attempt 1: CREATED -> SHIPPED
Attempt 2: SHIPPED -> SHIPPED
Attempt 3: SHIPPED -> SHIPPED
~~~

Conversely, an operation that increments a balance:

~~~text
balance = balance + 100
~~~

is not idempotent if run multiple times. If the same message is processed three times, the balance may increase by 300.

An idempotency key provides a stable identity for the operation. The application stores processed keys and checks them before applying the side effect:

~~~text
Receive message
      |
      v
Extract idempotency key
      |
      v
Key already completed?
   /       \
 yes       no
  |         |
  v         v
Skip     Apply side effect
duplicate    |
             v
        Persist key + result
~~~

The diagram is a conceptual model. In production, checking and recording the key must be atomic so two concurrent consumers cannot both pass the check.

## 2. Why does a Kafka consumer need an idempotency key?

Kafka consumers are typically deployed with at-least-once delivery semantics: an uncommitted record can be redelivered. This is normal and helps prevent data loss.

A typical scenario:

~~~text
1. Consumer receives record E.
2. Listener writes order to database.
3. Database commit succeeds.
4. Process crashes before Kafka offset commit.
5. New consumer receives E again.
6. Listener writes order again.
~~~

Kafka does not know the database committed the side effect in step 3. Offset commit and database transaction belong to two different systems unless a suitable coordination mechanism is used.

The idempotency key lets the consumer recognize the redelivery at step 5 as the same operation that already completed. The listener can then return success without executing the side effect again.

Common causes of redelivery:

- Process crash after database commit but before offset commit.
- Consumer rebalance while the listener has not committed.
- Offset commit failure or timeout leaving the outcome uncertain.
- Error handler retrying the record.
- Retry topic routing the same logical event through another consumer.
- DLT replay after fixing data or code.
- Operator re-running a batch or import.
- Producer resending the same command after a timeout.

**Duplicate delivery is not necessarily a Kafka bug.** Consumers must be designed to tolerate it.

## 3. Idempotency key, Kafka key, and event ID are different

Three types of identity are commonly confused:

| Identity | Primary purpose | Example |
|---|---|---|
| Kafka record key | Partitioning and key-based ordering | order-100 |
| Event ID | Identifies a specific event in the business contract | evt-7f3a |
| Idempotency key | Identifies an operation to guard against repeated execution | order-create:cmd-91 |
| Trace ID | Correlates spans in a distributed trace | trace-abc |
| Topic/partition/offset | Locates a record in the Kafka log | orders.events/2/105 |

Kafka keys are typically used to choose partitions. Many different events for the same order can share the same Kafka key order-100:

~~~text
Kafka key = order-100

Event A: OrderCreated
Event B: OrderAddressChanged
Event C: OrderShipped
~~~

If you use the Kafka key as the idempotency key, events B and C could be treated as duplicates of event A. That is wrong because they are distinct operations.

Event ID is often suitable as an idempotency key when each event represents exactly one operation to be applied once. However, not every system has an event ID matching that contract; sometimes a command-based or business-operation key is required.

Trace ID is also unsuitable: an event can be processed under a new trace during retry/replay, and a single trace can contain multiple events.

## 4. Choosing the scope of the idempotency key

Before creating a key, answer: **within what scope is an operation considered a duplicate?**

Common scopes:

- By consumer/service: each consumer applies its own side effect only once.
- By operation type: creating an order and sending an invoice have different identities.
- By tenant: the same command ID in two different tenants can be two separate operations.
- By aggregate: one order can have many distinct commands.
- By downstream system: each external API may have its own idempotency contract.

Example of namespaced keys:

~~~text
tenant-42:order-create:cmd-91
tenant-42:reserve-inventory:cmd-91
tenant-42:charge-payment:cmd-91
~~~

Same command ID, three different side effects. If a single shared key is used without an operation namespace, the second processing step could be wrongly skipped.

Schema design usually includes one or more components:

- consumer_name or operation_name.
- tenant_id if business identity must be isolated per tenant.
- idempotency_key.
- payload_hash or request fingerprint.
- operation status and result.
- processed_at/created_at.

Do not assume the namespace must be the Kafka consumer group. If two consumer groups share responsibility for the same side effect and must deduplicate system-wide, the key scope must be shared per business operation. Conversely, if two groups perform two different side effects, they need separate namespaces.

## 5. Generating keys that remain stable across all deliveries

An idempotency key must be generated **once per logical operation** and kept unchanged when the producer retries, the consumer redelivers, the record passes through a retry topic, or it is replayed from a DLT.

Possible key sources:

1. Event ID generated by the producer when the event is created.
2. Command ID supplied by the API/client and persisted with the command.
3. Operation ID generated at the service initiating the workflow.
4. Business natural key combined with operation type and version if the contract guarantees uniqueness.
5. Source Kafka coordinates if you only need to deduplicate a single source record within a topic log.

Example event:

~~~json
{
  "eventId": "evt-7f3a",
  "eventType": "OrderCreated",
  "tenantId": "tenant-42",
  "orderId": "order-100",
  "occurredAt": "2026-11-15T10:00:00Z"
}
~~~

If eventId is created when the producer creates the event and does not change across retries, you can use:

~~~text
consumer = order-projection
idempotency_key = evt-7f3a
~~~

Do not generate a new UUID every time the listener runs. If a key is generated inside the consumer per delivery, two redeliveries will have different keys and deduplication will not work.

## 6. Do not use a lone business entity ID if the entity has multiple events

Suppose an order undergoes multiple changes:

~~~text
order-100:
  OrderCreated
  AddressChanged
  PaymentAuthorized
  OrderShipped
~~~

If the key is only order-100, the first event could cause the three subsequent events to be treated as duplicates.

You could use:

~~~text
order-100:created:version-1
order-100:address-changed:version-2
order-100:payment-authorized:version-3
order-100:shipped:version-4
~~~

However, a dedicated event ID is usually clearer if the producer can generate it. An entity ID fits an idempotent state-setting operation when the semantics truly mean "set current state to X", but is unsuitable for increment/decrement commands or append-only events.

**The key must identify the operation, not just the object the operation acts upon.**

## 7. When to use source topic/partition/offset as the key

If a record lacks an event ID, Kafka coordinates can form an identity for the source record:

~~~text
orders.events:2:105
~~~

This key identifies a record within a topic partition log. It can fit when the goal is to prevent reprocessing the exact same source record in a consumer.

However, it has limitations:

- When a record is copied to a retry topic, the destination coordinates change.
- When a record is published to a DLT and replayed, the new coordinates differ from the source.
- When a topic is migrated or data is republished, the same logical event can get different coordinates.
- If two clusters share the same topic/partition/offset, keys can collide without a cluster/namespace prefix.
- If an operation is intentionally re-emitted, source-coordinate keys may fail to identify the same business operation.

If you need deduplication across retry/DLT/replay, a durable event ID or operation ID is usually better. If using Kafka coordinates, preserve original coordinates in DLT metadata and namespace the key by cluster/topic.

## 8. Keys need a payload fingerprint to detect improper reuse

A subtle bug occurs when the same idempotency key appears with a different payload:

~~~text
Request 1:
  key = payment-100
  amount = 50.00

Request 2:
  key = payment-100
  amount = 500.00
~~~

If the system merely sees the key already exists and silently skips request 2, it can hide a serious client bug or key collision.

You can store a payload hash/canonical request fingerprint alongside the key:

| Key | Payload hash | Behavior |
|---|---|---|
| payment-100 | hash-A | First time, process |
| payment-100 | hash-A | Valid duplicate, return prior result |
| payment-100 | hash-B | Key reuse conflict, alert/error |

The hash must be computed from a representation with stable canonicalization. Do not hash arbitrary JSON serialization if field ordering, whitespace, or default values can vary while semantics stay identical.

A canonical request may include normalized operation type, tenant, amount, currency, and business fields. Avoid including secrets or raw PII in hash inputs unless necessary.

If the same key arrives with a different payload, do not treat it as a normal duplicate. Return an investigable conflict.

## 9. Storing idempotency state in the database

For side effects in a relational database, the standard approach is storing processed keys in an inbox/deduplication table.

PostgreSQL example:

~~~sql
CREATE TABLE processed_messages (
    consumer_name   VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash    BYTEA NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

The primary key guarantees a consumer namespace cannot store the same key twice. If a multi-tenant namespace is already encoded in the key, you can use that key; or model tenant_id as a separate column included in the unique constraint.

A schema with an explicit tenant column:

~~~sql
CREATE TABLE processed_operations (
    consumer_name   VARCHAR(120) NOT NULL,
    tenant_id       VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash    BYTEA NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        consumer_name,
        tenant_id,
        idempotency_key
    )
);
~~~

This table acts as an inbox/deduplication ledger. It must persist across process restarts. An in-memory HashSet is insufficient across multiple pods or consumer rebalances because each instance has isolated state and state disappears on restart.

## 10. Writing the idempotency marker and business side effect in the same transaction

This is the most important rule:

**Inserting the idempotency marker and executing the business mutation must occur in the same database transaction.**

If the marker commits before the side effect:

~~~text
Insert processed key
Commit
Process crashes
Business update has not happened
Redelivery sees key already present
Skip
=> Lost business operation
~~~

If the side effect commits before the marker:

~~~text
Business update
Commit
Process crashes
Marker not yet written
Redelivery
Business update runs again
=> Duplicate side effect
~~~

The right approach:

~~~text
BEGIN TRANSACTION
    |
    v
Insert idempotency key
    |
    +--> Key already exists?
    |        |
    |        +--> Read fingerprint/result
    |        +--> Commit/return duplicate
    |
    +--> New key
             |
             v
       Apply business mutation
             |
             v
       Persist result/state
             |
             v
       COMMIT
~~~

If the transaction rolls back, both the marker and the business mutation roll back together. If the transaction commits, both exist together. When the record is redelivered, the database recognizes the completed key.

This protects side effects **inside the same database transaction**. It does not automatically cover HTTP requests, emails, or a different database.

## 11. Atomic SQL example with PostgreSQL

You can use INSERT ... ON CONFLICT DO NOTHING to claim the key:

~~~sql
INSERT INTO processed_messages (
    consumer_name,
    idempotency_key,
    payload_hash
)
VALUES (
    :consumerName,
    :idempotencyKey,
    :payloadHash
)
ON CONFLICT (consumer_name, idempotency_key)
DO NOTHING
RETURNING idempotency_key;
~~~

Interpretation:

- If one row is returned, this transaction inserted the marker and has the right to proceed with the business operation.
- If no row is returned, the key was inserted/committed by another transaction or already existed previously.
- The unique constraint prevents two concurrent consumers from both successfully inserting the same key.
- If a competing transaction has not committed yet, the database resolves the conflict per isolation/locking semantics; the statement may wait on the other transaction.

When the insert does not succeed due to a duplicate, read the stored payload_hash and compare it with the current hash. If they differ, raise a key reuse conflict.

All operations must live in the same transaction. Do not run the INSERT in one datasource transaction and the business mutation in another datasource while assuming they are atomic.

## 12. Implementing a service with Spring @Transactional

The example below uses JdbcTemplate and a repository with an atomic SQL statement:

~~~java
@Service
public class IdempotentOrderProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final OrderRepository orderRepository;

    public IdempotentOrderProcessor(
            JdbcTemplate jdbcTemplate,
            OrderRepository orderRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public ProcessingResult process(OrderCreated event) {

        String consumerName = "order-projection";
        String key = event.eventId();
        byte[] payloadHash = hashCanonicalEvent(event);

        int inserted = jdbcTemplate.update("""
                INSERT INTO processed_messages (
                    consumer_name,
                    idempotency_key,
                    payload_hash
                )
                VALUES (?, ?, ?)
                ON CONFLICT (consumer_name, idempotency_key)
                DO NOTHING
                """,
                consumerName,
                key,
                payloadHash
        );

        if (inserted == 0) {
            byte[] previousHash = jdbcTemplate.queryForObject(
                    """
                    SELECT payload_hash
                    FROM processed_messages
                    WHERE consumer_name = ?
                      AND idempotency_key = ?
                    """,
                    byte[].class,
                    consumerName,
                    key
            );

            if (!MessageDigest.isEqual(
                    previousHash,
                    payloadHash)) {
                throw new IdempotencyKeyConflictException(key);
            }

            return ProcessingResult.DUPLICATE;
        }

        orderRepository.createProjection(event);

        return ProcessingResult.APPLIED;
    }
}
~~~

This is a PostgreSQL/JDBC example; domain-specific hashCanonicalEvent helpers, ProcessingResult, exceptions, and repositories must be added. SQL text blocks require Java versions supporting text blocks. If using another database, upsert syntax may differ.

Because the method is annotated with @Transactional, the marker insert and createProjection participate in the same transaction if using the same transaction manager/data source. If createProjection throws an exception, the marker rolls back as well.

Do not catch exceptions and return success inside the transaction if you expect a rollback. Spring transactions roll back by default on runtime exceptions; checked exceptions require rollbackFor or equivalent configuration.

## 13. Why use a unique constraint instead of SELECT then INSERT?

An easy-to-write but unsafe pattern:

~~~java
if (!repository.existsByIdempotencyKey(key)) {
    repository.insert(key);
    orderRepository.create(event);
}
~~~

Two consumers can run simultaneously:

~~~text
Consumer A                  Consumer B
----------                  ----------
SELECT key -> absent        SELECT key -> absent
INSERT key                  INSERT key
CREATE order                CREATE order
~~~

Both see absent before either inserts. Without a unique constraint, duplicate side effects can be created.

Even with a unique constraint, running SELECT first and then performing the side effect is still insufficient. **Use the unique constraint as the concurrency arbiter**, insert the marker first inside the transaction, and only execute the side effect if the insert succeeded.

A distributed lock or in-memory synchronized block does not replace a unique constraint because consumers can run across multiple JVMs/pods.

## 14. Handling concurrent duplicates and transaction isolation

When two consumers receive the same key simultaneously, the database must decide which transaction owns the operation.

~~~text
Transaction A                       Transaction B
-------------                       -------------
INSERT key=evt-100                  INSERT key=evt-100
unique slot acquired                waits/conflicts
apply business mutation             |
COMMIT                              |
                                    INSERT returns duplicate
                                    read stored hash/result
                                    skip side effect
~~~

In PostgreSQL with a unique constraint and ON CONFLICT, the competing transaction typically waits for the outcome of the transaction holding the unique key. If transaction A rolls back, B can insert successfully and become the owner. If A commits, B takes the duplicate branch.

Do not rely solely on a cache check before the DB to decide whether to process. A cache can reduce reads, but the database unique constraint remains the final arbiter.

When using multiple database engines, verify upsert semantics, isolation levels, and locking behavior. Do not assume PostgreSQL concurrency behavior applies to every database system.

## 15. Same key with different payload hash must be a conflict

A key reuse conflict can indicate:

- Producer generated the wrong event ID or reused an ID.
- API client sent the same idempotency key for two different requests.
- An event was mutated during retry.
- Unstable canonicalization.
- Missing tenant namespace.
- Different version/schema without an operation version in the key.
- A bug in a replay tool.

Example exception:

~~~java
public class IdempotencyKeyConflictException
        extends RuntimeException {

    public IdempotencyKeyConflictException(String key) {
        super("Idempotency key reused with different payload");
    }
}
~~~

Do not include raw keys or payloads in exception messages if they may contain sensitive data. You can log a bounded fingerprint and key hash in structured logs.

Key conflicts should not be treated as successful duplicates. Depending on business rules, classify them as non-retryable, quarantine to a DLT, or alert on a producer contract violation.

## 16. Idempotency with Spring Kafka listeners

The listener should delegate processing to a Spring service with clear transaction boundaries:

~~~java
@Component
public class OrderListener {

    private final IdempotentOrderProcessor processor;

    public OrderListener(IdempotentOrderProcessor processor) {
        this.processor = processor;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderCreated event) {
        processor.process(event);
    }
}
~~~

When the processor returns DUPLICATE, the listener can return normally. The container considers the invocation complete and commits the offset according to the configured AckMode.

When the processor throws an exception, listener failure enters the error handler. If the same record is retried, the key remains identical. If the first attempt had already committed the transaction, the retry becomes a duplicate and does not repeat the business mutation.

Do not call acknowledge before the processor transaction commits. If using MANUAL AckMode, acknowledge after the service returns with the transaction completed per contract.

## 17. Offset commit and database transaction are two boundaries

Idempotency keys resolve the crash window between DB commit and Kafka offset commit:

~~~text
Kafka record
    |
    v
DB transaction:
  insert key + business update
    |
    v
DB COMMIT
    |
    +--> process crash
    |
    v
Kafka offset uncommitted
    |
    v
Redelivery
    |
    v
Key already exists -> skip business mutation
    |
    v
Listener returns success
    |
    v
Offset commit
~~~

This is one of the most important benefits of the inbox/deduplication pattern.

If the offset commits before the DB transaction, a crash after offset commit but before database commit can prevent the record from being redelivered and lose the side effect. Therefore, when performing database side effects, configure the acknowledgment boundary so the DB commit occurs before the record is considered complete.

Idempotency does not turn the database and Kafka into a distributed transaction. It makes redelivery safe within the failure window created by at-least-once processing.

## 18. Idempotency key is not Kafka producer idempotence

Kafka producer has an idempotence mechanism to prevent duplicate writes caused by producer retries at the Kafka protocol layer. This relies on producer ID, sequence numbers, and broker handling.

It **does not automatically prevent duplicate business processing at the consumer**:

| Kafka producer idempotence | Business idempotency key |
|---|---|
| Protects producer retries within protocol scope | Protects logical operations at the business layer |
| Applies to producer writes | Applies to side effects executed by consumers |
| Does not replace DB unique constraints | Typically enforced via DB unique constraints |
| Does not prevent consumer redelivery after uncommitted offsets | Recognizes redelivery of the same operation |
| Does not protect HTTP/payment/email side effects | Can coordinate with external API idempotency |

Enabling enable.idempotence=true on the producer is useful, but does not replace consumer deduplication. Also do not confuse it with exactly-once semantics of Kafka transactions.

## 19. Kafka exactly-once semantics do not automatically protect external databases

Kafka transactions can coordinate consume-transform-produce inside Kafka to atomically commit output records and consumed offsets under transaction semantics. However, if the listener also writes to PostgreSQL, calls a payment API, or sends an email, those side effects do not automatically join the Kafka transaction.

~~~text
Kafka input
    |
    v
Kafka transaction
    |
    +--> produce Kafka output
    |
    +--> commit consumed offset
    |
    v
Kafka transaction commit

PostgreSQL / HTTP API / Email
    |
    +--> not automatically part of Kafka transaction
~~~

A consumer can use Kafka EOS for a Kafka-to-Kafka flow and still need an idempotency key or inbox/outbox when external side effects exist.

Do not claim "exactly once" for the entire business workflow just because producer transactions are enabled. Specify exactly where the exactly-once boundary lies.

## 20. Idempotency with external APIs

Suppose a listener receives PaymentRequested and calls a payment gateway:

~~~text
Kafka listener
     |
     v
POST /payments
     |
     v
Payment gateway charges card
     |
     v
Response times out over network
~~~

A timeout does not indicate whether the gateway charged the card or not. If the consumer retries with a new request, the customer could be charged twice.

If the gateway supports idempotency keys, send the same key for every retry of the same payment operation:

~~~http
POST /payments
Idempotency-Key: payment-command-91
Content-Type: application/json
~~~

The retry uses the same key and the same request body. The gateway can return the stored result instead of creating a new charge, per the provider's contract.

Items to verify:

- Does the API provider truly support idempotency?
- How is the key scoped (merchant/account/endpoint)?
- How long does the provider retain the key?
- How is the same key with a different payload handled?
- Is the original response returned?
- After a timeout once the request was received, can the status be queried by key?
- Are there length/character limits on the key?

Do not simply add an Idempotency-Key header and assume any arbitrary API enforces idempotent semantics. The receiving server must actually persist and enforce the key.

## 21. Database inbox and external API idempotency must coordinate

A processed_messages table only protects the service's own database transaction. It cannot be atomic with a payment gateway.

A failure window:

~~~text
1. Insert idempotency marker.
2. Call payment API.
3. Gateway charge succeeds.
4. Service crashes before recording payment result.
5. Kafka redelivery.
6. Marker exists, service skips.
~~~

If the marker committed before the external call, the service could skip an operation whose local result was never saved. If the marker shares the transaction yet the external call occurs before commit, a crash/timeout can still leave an indeterminate state.

Design approaches:

- Send a stable idempotency key to the external provider.
- Store operation state and provider request key.
- Use PENDING/COMPLETED/FAILED states with explicit transitions.
- Run a reconciliation job to query external operation status after timeouts.
- Use an outbox to dispatch commands durably.
- Use sagas/compensation when workflows span multiple systems.
- Never treat a network timeout as proof that the external operation failed.

For critical side effects like payments, provider idempotency and reconciliation are essential protective layers; a local database marker alone is insufficient.

## 22. Inbox pattern for Kafka consumers

The **Inbox pattern** stores received or processed messages in the database alongside the business state change. A processed_messages table is a simple form of inbox.

~~~text
Kafka record
     |
     v
Consumer
     |
     v
BEGIN DB TRANSACTION
     |
     +--> INSERT inbox/idempotency key
     |
     +--> Apply business state change
     |
     +--> Store outcome
     |
     v
COMMIT
     |
     v
Listener success / Kafka offset commit
~~~

An inbox helps:

- Guard against redelivery.
- Identify duplicates.
- Leave an operation audit trail.
- Optionally store payload hashes and processing outcomes.
- Support auditing/reconciliation.
- Distinguish received messages from completed messages if the schema includes status.

An inbox table requires a unique constraint. Simply writing a text log "processed eventId" without a unique constraint/transaction does not guarantee concurrency safety.

## 23. Outbox pattern when a service both writes DB and publishes to Kafka

Idempotency keys often pair with the **outbox pattern** on the producer side. For example, a service creates an order and wants to publish OrderCreated:

~~~text
BEGIN DB TRANSACTION
    |
    +--> INSERT order
    |
    +--> INSERT outbox event with eventId
    |
    v
COMMIT
    |
    v
Outbox relay reads event
    |
    v
Publish Kafka
    |
    v
Mark outbox row sent
~~~

If the relay publishes successfully and then crashes before marking the row sent, the event can be published again. Downstream consumers still need idempotency keys to prevent duplicate business side effects.

Outbox solves atomicity between business database state and persisting the intent to publish within the same database. It does not guarantee a message appears only once on Kafka across all failure modes.

Common combination:

- Producer side: stable outbox event ID.
- Kafka: record key/partitioning by business aggregate if ordering is needed.
- Consumer side: inbox/idempotency table with unique key.
- Database side effect: same transaction as inbox marker.
- External API: provider idempotency key and reconciliation.

## 24. Idempotency state may require PENDING and COMPLETED

The simple model that only stores a processed marker works when the side effect and marker commit in the same transaction.

For long-running workflows or external APIs, a state machine may be needed:

~~~text
NEW
 |
 v
PENDING
 |
 +--> COMPLETED
 |
 +--> RETRYABLE_FAILURE
 |
 +--> PERMANENT_FAILURE
 |
 +--> UNKNOWN_EXTERNAL_RESULT
~~~

Example schema:

~~~sql
CREATE TABLE idempotent_operations (
    operation_scope VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash BYTEA NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_reference VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (operation_scope, idempotency_key)
);
~~~

States must have clear semantics:

- PENDING: operation has been claimed and is currently processing.
- COMPLETED: side effect finished with a durable outcome.
- RETRYABLE_FAILURE: eligible for retry.
- PERMANENT_FAILURE: requires manual handling or DLT.
- UNKNOWN_EXTERNAL_RESULT: external request timed out, outcome unknown.

Do not mark COMPLETED before the side effect finishes. When using PENDING, define lease/timeout rules and recovery mechanisms for when a worker dies mid-flight.

## 25. Leases and fencing for long-running operations

A PENDING workflow may be abandoned by a crashed worker. After some time, another worker may need to resume it. If you only have status and updated_at columns, the old worker might wake up after lease expiry and commit results alongside the new worker.

Techniques to use:

- lease_owner.
- lease_until.
- attempt/version number.
- optimistic locking.
- monotonically increasing fencing tokens.
- conditional state transitions.

Example:

~~~sql
UPDATE idempotent_operations
SET status = 'PENDING',
    lease_owner = :workerId,
    lease_until = now() + interval '30 seconds',
    version = version + 1
WHERE operation_scope = :scope
  AND idempotency_key = :key
  AND (
      status = 'NEW'
      OR (status = 'PENDING' AND lease_until < now())
  )
RETURNING version;
~~~

A worker may only commit results if the fencing version still matches the version it owns. Downstream systems must understand fencing tokens if side effects could be dispatched by an old worker after its lease expired.

Leases do not replace external idempotency keys. They only coordinate ownership; network timeouts can still leave external operation outcomes unknown.

## 26. Idempotency in batch listeners

A batch contains multiple records, each with its own idempotency key:

~~~text
Batch:
  E1 -> key-1
  E2 -> key-2
  E3 -> key-3
  E4 -> key-4
~~~

There are two transaction choices:

**One transaction for the whole batch**

- Insert markers and apply all business changes in one transaction.
- If one record errors, the entire batch rolls back.
- Batch retry sees prior records uncommitted and reprocesses them.
- Each key still needs a unique constraint.

**One transaction per record**

- Each record commits independently.
- Some records may have already completed before the batch fails.
- When the batch is retried, already-committed records become duplicates and are skipped.
- Requires understanding Spring Kafka batch error handling and offset semantics.

Do not use a single idempotency key for an entire batch if each record is an independent business operation. If the batch itself is a single command, define a batch key explicitly and clarify per-item semantics.

## 27. DLT replay and idempotency keys

When a record is sent to a DLT and later replayed, the critical question is: does the replay represent **the same logical operation** or a new operation?

If replaying to retry the same business event after fixing a database outage, keep the original idempotency key. If the side effect had already committed before the consumer crashed, the replay will be recognized as a duplicate.

~~~text
Source event E, key=evt-100
       |
       v
Business DB commit
       |
       v
Offset commit failure
       |
       v
Record redelivery / DLT replay
       |
       v
Same key evt-100
       |
       v
Skip duplicate side effect
~~~

If replay is meant to fix a projection or regenerate data from scratch, the policy may differ. In that case, use an explicitly defined **rebuild namespace** or a new operation version rather than accidentally deleting deduplication state.

Do not append a replay timestamp to the idempotency key. Doing so turns every replay into a new operation and can repeat side effects.

If intentionally creating a new operation, log an audit entry, define compensation/side-effect behavior, and make key versioning an explicit business decision.

## 28. Retention of idempotency keys

Deduplication state must be kept long enough to cover every redelivery/replay window the system commits to supporting.

A guiding rule:

~~~text
Idempotency retention
    >= max(
         Kafka source retention,
         retry-topic delay horizon,
         DLT retention/replay horizon,
         producer retry window,
         business replay window
       )
~~~

This estimates across independent horizons; in practice, add a safety margin for investigation time, replication/backups, and workflows that may be delayed.

If keys are deleted too early:

1. An old record is replayed.
2. The marker is gone.
3. The consumer treats it as a new operation.
4. The business side effect runs again.

If kept forever:

- Deduplication table grows unboundedly.
- Indexes bloat.
- Vacuum/maintenance consumes resources.
- Queries/backups/restores become heavier.
- Partitioning or archival is needed.

Retention is part of the reliability contract. If a DLT can be replayed after six months while markers are retained for only seven days, the system does not guarantee idempotency for six-month replays.

## 29. Cleaning up idempotency records safely

A table with processed_at can be purged in batches:

~~~sql
DELETE FROM processed_messages
WHERE processed_at < now() - interval '90 days';
~~~

This is a simple example; do not run one massive DELETE in production if the table is large. Instead:

- Partition the table by processed_at.
- Drop old partitions after retention expires.
- Delete in bounded batches.
- Archive audit records.
- Monitor dead tuples and index sizes.
- Align retention with Kafka topics and DLT replay policies.

Do not delete keys for PENDING or UNKNOWN_EXTERNAL_RESULT operations based solely on record age. Those states require reconciliation before cleanup.

If a consumer group is reset to an older offset, or a topic is replayed from backup, review the retention policy before permitting the operation.

## 30. Idempotency keys and multi-tenant systems

In a multi-tenant system, keys must be namespaced or uniquely constrained per tenant if two tenants can use identical command IDs.

Example:

~~~text
tenant-a:payment:cmd-100
tenant-b:payment:cmd-100
~~~

These are two distinct keys because cmd-100 in two tenants represents two different operations.

Schema:

~~~sql
PRIMARY KEY (
    operation_scope,
    tenant_id,
    idempotency_key
)
~~~

Do not take raw tenant ID from the payload and trust it unconditionally. Validate the tenant against the security context or a verified contract. A producer sending a wrong tenant ID can cause collisions or write side effects into the wrong namespace.

If tenant ID is PII or sensitive, use an appropriate internal tenant identifier and protect it in logs/metrics.

## 31. Should idempotency keys be hashed?

Some systems want to bound key length or avoid storing raw keys. A digest can be stored:

~~~text
raw idempotency key
       |
       v
canonicalization
       |
       v
SHA-256
       |
       v
stored key digest
~~~

Benefits:

- Fixed length.
- Smaller, more stable indexes for long keys.
- Avoids storing raw keys in the deduplication table.
- Easy normalization of key input.

However, hashing does not solve everything automatically:

- Identical canonicalization is required between producer and consumer.
- Collision, though extremely rare, remains a theoretical contract consideration.
- If keys have low entropy, hashing does not protect against dictionary guessing.
- Debugging needs a safe correlation mechanism.
- Payload hashes and idempotency key hashes serve two different purposes.

If a raw key contains secrets or PII, it is better to design an opaque random ID that carries no sensitive data from the outset. Never treat SHA-256 of an email or phone number as fully anonymous data.

## 32. Idempotency keys and aggregate ordering/versioning

Idempotency prevents an operation from executing twice, but does not automatically guarantee event ordering.

Example:

~~~text
Order version 2: AddressChanged
Order version 3: OrderShipped
~~~

If version 3 arrives before version 2, the two events have different idempotency keys so both can be processed. The system can still transition to the wrong state without version/order checks.

You can store aggregate version and apply an optimistic condition:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version = :incomingVersion - 1;
~~~

If the update affects no rows, distinguish between duplicate, stale event, and missing predecessor. The idempotency key handles duplicate identity; the version check handles ordering/state transitions. The two mechanisms complement each other.

Kafka keys can keep events for the same aggregate in one partition, but partitioning does not replace version validation because producer retries, migrations, and multiple sources can still affect order.

## 33. Side effects outside the database transaction

Some side effects cannot roll back alongside an inbox marker:

- Sending email.
- Sending SMS.
- Calling a payment gateway.
- Calling a partner REST API.
- Creating a file on object storage.
- Sending a command to another system.
- Emitting another Kafka message.

Do not place an HTTP call inside a DB transaction and assume DB rollback will cancel the HTTP request. If the HTTP call succeeds and the transaction rolls back, retries may send the HTTP request again.

Options:

1. External API supports an idempotency key.
2. Write intent to an outbox in the same DB transaction and let a worker execute the side effect.
3. Persist operation state and perform reconciliation.
4. Use sagas/compensation for multi-system workflows.
5. Design the side effect as state-setting if business rules allow.
6. Enforce timeouts and classify UNKNOWN outcomes when it is unclear whether the remote side processed the request.

An email provider without idempotency support can send duplicates even when the local service has a marker. You can use an outbox to guarantee dispatch intent, but still need provider deduplication or a duplicate-acceptance/compensation strategy.

## 34. Idempotency for payments and inventory

### Payment

The key should represent a specific charge/refund operation:

~~~text
merchant-42:charge:payment-command-91
merchant-42:refund:refund-command-18
~~~

Do not use orderId alone if an order can be charged multiple times, captured multiple times, or partially refunded.

Store the provider reference and outcome so retries can return the prior outcome or query the provider. On a timeout where it is unclear whether the charge occurred, do not generate a new key to retry.

### Inventory

A stock reservation command can use:

~~~text
warehouse-3:reserve:reservation-command-100
~~~

If the same command arrives twice, reserve only once. However, an order may need multiple reservation adjustments; the key must identify each adjustment.

When releasing or compensating inventory, that is a separate operation with its own key—never reuse the reservation key.

## 35. Error handling when idempotency storage fails

If the database deduplication table is unavailable, the consumer cannot determine whether a record was already processed. Two dangerous choices exist:

- Proceed with the side effect without checking the key: risks duplicates.
- Skip the record and commit the offset: risks losing a business operation.

For critical side effects, the safer choice is usually to **fail processing and let retry/backoff handle it** rather than bypassing the idempotency check.

~~~text
Idempotency DB unavailable
       |
       v
Cannot determine duplicate state
       |
       +--> Do not apply unguarded side effect
       |
       +--> Throw retryable exception
       |
       v
Error handler/backoff
       |
       v
Retry after recovery
~~~

Do not retry infinitely with overly short backoff. You can combine a circuit breaker or pause the listener during prolonged DB outages. Upon recovery, the same key is still used.

If the deduplication store is a separate database from the business DB, solve atomicity between the two stores. Checking a key in Redis and writing business state to PostgreSQL is not atomic; Redis outages or evictions can cause duplicate side effects. Prefer the same transactional database or a well-designed protocol.

## 36. Duplicate is not necessarily success in every business contract

When a key already exists:

- If payload hash matches and operation is COMPLETED: return prior result or skip side effect.
- If payload hash differs: conflict.
- If operation is PENDING: wait, return in-progress status, or coordinate lease.
- If operation is RETRYABLE_FAILURE: proceed per retry policy.
- If operation is UNKNOWN_EXTERNAL_RESULT: reconcile before resending.
- If operation is PERMANENT_FAILURE: return stored failure state or route to quarantine.

An API command should usually return the **original result** to the client when retrying the same key, rather than merely returning "duplicate". A Kafka listener may not return a business response externally, yet still needs to know whether the operation actually completed.

Do not mark every existing key as duplicate success if the schema tracks multiple states. Skip only when the status truly guarantees the side effect completed.

## 37. Observability for idempotency

Useful metrics:

| Metric | Meaning |
|---|---|
| idempotency_first_seen_total | New keys received |
| idempotency_duplicate_total | Duplicates identified |
| idempotency_key_conflict_total | Same key with different payload fingerprint |
| idempotency_in_progress_total | Operations currently PENDING |
| idempotency_reconciliation_total | Operations requiring external result reconciliation |
| idempotency_store_error_total | Failures accessing the deduplication store |
| idempotency_processing_duration | Operation processing duration |
| idempotency_cleanup_total | Number of records cleaned up |
| idempotency_lease_expired_total | Expired operation leases |

Metric tags should have low cardinality such as consumer, operation type, and outcome. Do not put idempotency keys, event IDs, order IDs, or trace IDs into metric labels.

Structured logs can record a truncated key fingerprint or permitted correlation identifier:

~~~json
{
  "level": "INFO",
  "event": "kafka_duplicate_skipped",
  "listener_id": "ordersListener",
  "consumer_group": "orders-service",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "operation_scope": "order-projection",
  "idempotency_outcome": "duplicate"
}
~~~

Do not log raw payloads or keys if they contain sensitive data. Traces can link the current delivery to upstream processing, while the idempotency key remains a distinct business identity.

## 38. Testing idempotency at true failure boundaries

A test that merely calls a processor twice sequentially is not enough to prove concurrency safety or crash recovery.

Scenarios to test:

| Scenario | Expected outcome |
|---|---|
| Same key, same payload first time | Business side effect applied once |
| Same key, same payload second time | Duplicate skipped / prior result returned |
| Same key, different payload | Key conflict, not silently skipped |
| Two concurrent consumers with same key | Only one transaction applies the side effect |
| Crash before DB commit | Both marker and side effect roll back |
| Crash after DB commit before offset commit | Redelivery is deduplicated |
| Offset commit before DB commit in misconfiguration | Test exposes risk of lost side effect |
| DB unavailable | Idempotency check is not bypassed |
| DLT replay with same event ID | Completed side effect is not repeated |
| Retry topic redelivery | Same logical key is preserved |
| Different keys for two commands on same order | Both valid operations are processed |
| Different tenants, same command ID | No collision when scopes differ |
| Old key after retention expiry | Behavior matches replay policy |
| Lease expired, old worker returns | Fencing prevents stale worker from committing |
| External API timeout after remote success | Retry with same provider key does not repeat side effect |
| Batch fails mid-way | Already-committed items are deduplicated on batch retry |
| Payload hash canonicalization | Equivalent requests produce identical fingerprints |

Verify database rows and business state rather than only asserting how many times the listener method was called. For concurrency tests, spin up real threads/transactions against the same database unique constraint.

## 39. Idempotency key implementation workflow

1. Identify the logical operation that must not execute repeatedly.
2. Distinguish Kafka key, event ID, command ID, and trace ID.
3. Choose namespace: consumer, operation, tenant, or business scope.
4. Generate the key once at the source and preserve it across retries/replays.
5. Define a canonical payload fingerprint.
6. Create an inbox/deduplication table with a unique constraint.
7. Insert the marker and business side effect in the same DB transaction.
8. Handle duplicates based on stored status and payload hash.
9. Let exceptions flow through the error handler when the transaction has not completed.
10. Commit the Kafka offset after the business transaction completes.
11. For external APIs, send the same provider idempotency key and persist the result.
12. For long workflows, design PENDING/COMPLETED, leases, and fencing.
13. Choose retention based on source/retry/DLT/replay horizons.
14. Clean up records in batches/partitions while preserving incomplete operations.
15. Emit metrics/logs for duplicates, conflicts, store errors, and reconciliation.
16. Test concurrency, crashes, timeouts, DLT replays, and cleanup.

## 40. Pre-production checklist

- Idempotency key identifies the logical operation, not just the entity.
- Key is generated once at the producer/command boundary and stays stable across redeliveries.
- No new random key is generated each time the listener runs.
- Kafka record key is not confused with event ID/idempotency key.
- Key scope has appropriate operation/tenant namespaces.
- Same key with different payload is detected as a conflict.
- Payload hash uses a stable canonical representation.
- Database unique constraint serves as the concurrency arbiter.
- Marker and business mutation share the same transaction.
- Duplicates are skipped only when the operation actually completed.
- Offset never commits before the business transaction.
- Retry/DLT/replay preserves the key for the same logical operation.
- Intentional replays creating a new operation have an explicit policy/version.
- Retention covers all committed redelivery/replay horizons.
- Cleanup does not delete PENDING or UNKNOWN operations.
- External APIs have an idempotency contract or reconciliation/compensation.
- Outbox/inbox are applied at the proper boundaries.
- Kafka EOS is not misunderstood as exactly-once for databases/HTTP.
- Async workers use leases/fencing if long-running and potentially overlapping.
- Batch listeners have explicit per-item or per-batch key/transaction semantics.
- Metrics do not use idempotency keys as tags.
- Logs do not expose payloads, PII, or secrets.
- Crash after DB commit before offset commit has been tested.
- Two concurrent consumers with the same key have been tested.
- Runbooks exist for key conflicts, store outages, duplicate spikes, and replays.

**Conclusion:** An idempotency key is the stable identity of a logical operation, enabling Spring Kafka consumers to withstand redelivery, retries, rebalances, and DLT replays without repeating business side effects. What determines correctness is that **the key must remain unchanged across all deliveries, a unique constraint must arbitrate concurrency, and the idempotency marker must commit atomically with the side effect in the same database transaction**. For external systems, provider idempotency keys, outbox/reconciliation, or compensation are needed. Retention and replay policies must also align; if deduplication state is deleted before an old event can return, idempotency protection ceases to hold.

