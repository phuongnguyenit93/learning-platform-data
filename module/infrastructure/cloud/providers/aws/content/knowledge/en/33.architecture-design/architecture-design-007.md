# Idempotency, Outbox, and Distributed Consistency

## Lesson Objectives

In the `CLOUD_PROVIDERS_AWS` ecosystem, a business operation often spans multiple components: an API receiving requests, a service persisting data, a queue transmitting events, and other services continuing processing. Networks can time out after a database commits; message brokers can redeliver messages; Lambda can reprocess a batch; clients can retry because they did not receive a response. If every rerun creates new side effects, the system can record duplicate orders, charge payments twice, reserve inventory multiple times, or send incorrect notifications.

Idempotency allows an operation to be retried without creating unintended additional business outcomes. The transactional outbox ensures data changes and event-publishing intent are recorded atomically within the same database transaction. An inbox/deduplication mechanism helps consumers safely handle redelivered events. When a business process spans multiple services and databases, a saga coordinates local transactions alongside compensating actions to bring the system to a valid business state.

After this lesson, learners can:

- Distinguish idempotency, deduplication, retries, delivery semantics, and exactly-once processing.
- Design idempotency keys for APIs and consumers, handle concurrent requests, and store processed results.
- Identify dual-write failures between databases and message brokers.
- Implement a transactional outbox using relational databases or DynamoDB Streams.
- Use an inbox/processed-message table to ensure database side effects are applied only once per event ID.
- Choose SQS Standard, SQS FIFO, EventBridge, DynamoDB Streams, and Lambda based on ordering, durability, and retry requirements.
- Design versioning, ordering, retries, DLQs, and reconciliation.
- Use saga orchestration or choreography for transactions spanning multiple microservices.
- Observe, test, and operate distributed workflows under duplicates, timeouts, crashes, and connection drops.

## 1. Why Is Consistency Hard in Distributed Systems?

In a simple application, a single database transaction can update multiple tables atomically: either all changes commit, or all roll back. When business logic spans multiple services, databases, and message brokers, there is no longer a single ACID transaction covering every component.

For example, when a customer places an order:

1. Order service writes the order to RDS.
2. Order service sends `OrderPlaced` to SQS or EventBridge.
3. Inventory service reserves stock.
4. Payment service requests payment.
5. Notification service sends a confirmation email.

A network failure can occur between any two steps. Suppose the database commits the order, but the service times out before sending the event. The order exists, yet Inventory service never knows to reserve stock. If the service sends the event first and the database transaction then rolls back, Inventory service might reserve stock for a non-existent order.

This is a **dual-write** failure: a single business operation must write to two independent systems, such as a database and a message broker. No call ordering between two independent systems eliminates every failure window:

| Order | Failure | Consequence |
|---|---|---|
| Write database then send message | Database commits, sending message fails | Data saved without an event |
| Send message then write database | Message sent, database transaction rolls back | Consumer processes an event for uncommitted data |
| Send message, receive timeout | Broker may have received the message while producer missed ACK | Producer retries and may send duplicates |
| Consumer finishes processing without ACK | Message is redelivered | Consumer may repeat side effects |

The solution must address three distinct problems:

- **Atomicity at the source:** business data and the event to emit must be saved together.
- **Repeatable delivery:** the system must tolerate events or requests being delivered multiple times.
- **Cross-service consistency:** business steps must support retries, deduplication, compensation, and reconciliation.

The transactional outbox solves atomicity at the source. Idempotency and inboxes handle duplicates. Sagas coordinate distributed steps and compensation when a step cannot complete.

## 2. What Is Idempotency?

An idempotent operation can be executed multiple times with the same intent without producing additional unintended side effects. In a state model, an idempotent transformation satisfies:

\[
f(f(x)) = f(x)
\]

Examples:

- Setting an order's status to **SHIPPED** multiple times still results in `SHIPPED`.
- Setting desired capacity to 5 multiple times still keeps target capacity at 5.
- Recording a processed event ID multiple times does not deduct inventory again.

Conversely, the following operations are not inherently idempotent:

- `balance = balance - 100`.
- `inventory = inventory - 1`.
- `INSERT` a new order on every incoming request.
- Sending an email or charging payment on every handler invocation.

A `POST /orders` API usually creates a new resource, so retries can create multiple orders. The API can support an idempotency key so repeated submissions of the same logical request return the same order/result.

Distinguish:

| Concept | Question Answered |
|---|---|
| Idempotency | If the same operation is executed again, does business state change further? |
| Deduplication | How do we recognize that two requests/messages represent the same operation? |
| Retry | When a transient error occurs, how does the system try again? |
| Delivery semantics | How do producers/brokers/consumers guarantee message delivery? |
| Exactly-once effect | How do we ensure business side effects happen only once within a defined scope? |

Idempotency does not mean every call must return the exact same HTTP status or take the exact same response time. The first call might return `201 Created`, while a retry returns the saved result with `200 OK`; what matters is not creating another order or charge.

## 3. Why Cannot End-to-End Exactly-Once Be Assumed by Default?

In distributed systems, a producer can send a message successfully yet lose the ACK. A consumer can finish processing and crash before acknowledging the message. The broker must decide whether to redeliver the message. If it does not redeliver, events can be lost; if it redelivers, duplicates can occur.

Therefore, many AWS services provide at-least-once delivery at one or more boundaries:

- SQS Standard can deliver a message multiple times and does not guarantee strict ordering.
- Lambda event source mappings process records at-least-once; the same record can be reprocessed.
- Lambda consumers of DynamoDB Streams can also process the same stream record multiple times when invocations retry.
- EventBridge retries target delivery; source services may emit events with durable at-least-once or best-effort delivery depending on the event type.

SQS FIFO provides producer deduplication within a 5-minute window and preserves ordering within each message group. That helps reduce duplicate messages entering the queue, but does not turn every downstream consumer, database, and external system side effect into exactly-once. If a consumer processes a message but fails to delete it before the visibility timeout expires, the message can be redelivered.

A practical design approach is:

1. Accept that messages may be delivered at least once.
2. Give every event a stable identifier.
3. Have consumers record the event ID and update business data in the same transaction.
4. External side effects also use idempotency keys or safely retryable workflows.
5. Use DLQs and reconciliation to handle cases that cannot self-heal.

The goal is not to force every component to execute strictly once. The goal is to ensure multiple executions still yield one correct business outcome.

## 4. Designing Idempotency Keys for APIs

An idempotency key identifies a single logical business execution. The client generates the key before the first send and reuses that same key for every retry of the same request.

For example, a client creating an order:

~~~http
POST /orders
Idempotency-Key: 5f2a2c7e-8a52-4f35-aef2-9e5d87f7d3b1
Content-Type: application/json

{
  "customerId": "customer-123",
  "items": [
    {"sku": "SKU-001", "quantity": 2}
  ]
}
~~~

If the client times out after the server commits the order, the client resends the same request with the same `Idempotency-Key`. The server looks up the saved record and returns the previous result without creating a new order.

A key should have a clear scope, such as:

- Tenant or customer ID.
- Operation/API name.
- Client-generated idempotency key.
- Hash of the canonicalized payload.

Example logical key:

~~~text
tenant-42#POST:/orders#5f2a2c7e-...
~~~

Do not use the request body alone as the key if two valid orders can share identical contents yet represent two distinct purchase intents. Conversely, do not generate a new key on every retry, as the server would no longer recognize it as the same operation.

### 4.1. Same Key with Different Payload

If the same key is sent with a different payload, the server should reject it instead of guessing intent:

- First request: key `K1`, pay 100,000 VND.
- Subsequent request: key `K1`, pay 500,000 VND.

This is a key reuse conflict. The server can return `409 Conflict` or an equivalent error while logging for investigation. Never return the first request's result while silently executing the second payload.

### 4.2. Storing State and Results

An idempotency record typically contains:

| Field | Purpose |
|---|---|
| `idempotency_key` | Unique key within tenant/operation scope |
| `request_hash` | Detects same key with different payload |
| `status` | `IN_PROGRESS`, `SUCCEEDED`, or managed error status |
| `resource_id` | Created order/payment/job ID |
| `response` | Result to return on retries |
| `created_at` | Timestamp when the first request was received |
| `expires_at` | Expiration timestamp for retaining the record |
| `lease_until` | Processing lease deadline for the worker holding execution rights |

Processing flow:

~~~mermaid
flowchart TD
    A[Client sends request with key K] --> B[Read or claim idempotency record]
    B --> C{Record exists?}
    C -- No --> D[Conditional write IN_PROGRESS]
    D --> E[Execute business logic]
    E --> F[Commit result and response]
    F --> G[Return result]
    C -- Yes --> H{Request hash matches?}
    H -- No --> I[409 Conflict]
    H -- Yes --> J{Status?}
    J -- SUCCEEDED --> K[Return saved response]
    J -- IN_PROGRESS --> L[Return in-progress status or retry later]
    J -- Expired/Recoverable --> M[Reclaim per lease and policy]
~~~

Claiming the key must be atomic. With DynamoDB, use conditional `PutItem` or `UpdateItem`; with relational databases, use unique constraints and transactions. If two requests arrive concurrently, only one claims the key successfully. The other reads the current state and does not execute side effects again.

Do not leave records in `IN_PROGRESS` indefinitely. If a worker crashes, a lease or in-progress expiry tells the system when it can retry. However, an expired lease does not prove the old worker stopped running; if the old worker might still resume, use fencing tokens or version conditions to prevent the stale worker from overwriting newer results.

### 4.3. Idempotency Expiration

Record retention must exceed the retry/replay window accepted by the system. Deleting records too early allows an old resent request to trigger new side effects.

Consider:

- How long clients may retry.
- How long API gateways, SDKs, or proxies may retry.
- How long messages may stay in queues or DLQs.
- How long operators may replay events.
- Audit and transaction history retention requirements.

TTL is only for cleaning up expired records. Never rely on TTL as a millisecond-accurate lock; check `expires_at` in application logic before treating a key as new.

## 5. Idempotency for Consumers and Side Effects

Producers can send an event multiple times. Consumers must use the event ID or a stable business key to identify prior processing.

Example message:

~~~json
{
  "eventId": "evt-01J8QK9M4X",
  "eventType": "OrderPlaced",
  "aggregateId": "order-1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-20T05:30:00Z",
  "payload": {
    "orderId": "order-1001",
    "customerId": "customer-123",
    "total": 250000
  }
}
~~~

The consumer must store processed `eventId` values. If the event arrives a second time, the consumer detects the duplicate and skips side effects. Writing the inbox record and updating the business table should occur in the same transaction:

~~~sql
BEGIN;

INSERT INTO processed_messages (consumer_name, event_id, processed_at)
VALUES ('inventory-service', 'evt-01J8QK9M4X', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Apply inventory changes only if INSERT actually created a new row.
-- If the event was already processed, skip the update.

COMMIT;
~~~

The SQL above is pseudocode illustrating operation order. In real code, check the inserted row count; if 0, the event was already processed. If the inventory update fails, the transaction must roll back the inbox record as well so future retries can reprocess it.

The inbox table can use `(consumer_name, event_id)` as its primary key. If the same event is processed by two different consumers, each consumer needs its own state.

Never write an inbox record in one transaction and then call an external API afterward without protection. If the consumer commits the inbox before calling a payment provider and crashes, retries will skip the event even though payment never happened. If it calls the provider first and then commits the inbox, crashing in between can cause duplicate payments. For external side effects:

- Pass the same idempotency key to the provider if supported.
- Or write the intent to call the provider into a separate outbox.
- Track `PENDING`/`CONFIRMED`/`UNKNOWN` states.
- Include a query/reconciliation step to verify whether the provider already executed the action.

## 6. Transactional Outbox Solves Dual-Write

A transactional outbox stores events in a table inside the same database as the business data. The application writes business data and the outbox event within one transaction. A separate relay reads committed events and publishes them to the broker.

Flow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Order Service
    participant DB as RDS/Aurora
    participant R as Outbox Relay
    participant Q as SQS/EventBridge
    participant I as Consumer

    C->>S: POST /orders + Idempotency-Key
    S->>DB: BEGIN
    S->>DB: INSERT order
    S->>DB: INSERT outbox event
    S->>DB: COMMIT
    DB-->>S: Commit success
    S-->>C: Order created
    R->>DB: Read committed pending events
    DB-->>R: Event payload + event_id
    R->>Q: Publish event
    Q-->>R: Acknowledgement
    R->>DB: Mark event published
    Q->>I: Deliver event (possibly more than once)
    I->>I: Inbox dedup + business transaction
~~~

If the database transaction rolls back, neither the order nor the outbox row exists. If the transaction commits, the event intent is durably persisted and the relay can publish it later, even if the broker is temporarily unavailable.

The outbox does not create an ACID transaction spanning the database and broker. It creates atomicity between business state and event intent inside the database, followed by asynchronous delivery. Because the relay may resend, consumers must still be idempotent.

### 6.1. Outbox Table Structure

Example with PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(150) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    lease_owner VARCHAR(150),
    lease_until TIMESTAMPTZ,
    UNIQUE (aggregate_type, aggregate_id, aggregate_sequence)
);
~~~

Field meanings:

- `event_id`: stable identifier for deduplication.
- `aggregate_id`: entity producing the event, such as order ID.
- `aggregate_sequence`: event order within an aggregate.
- `event_type`: event type name.
- `payload`: data needed by consumers.
- `published_at`: timestamp when the relay confirmed broker receipt.
- `attempts`, `next_attempt_at`: manage retries and backoff.
- `lease_owner`, `lease_until`: coordinate multiple relay workers to avoid processing the same row concurrently.

You can also add `schema_version`, `correlation_id`, `causation_id`, tenant ID, and trace ID to support schema compatibility and tracing.

### 6.2. Writing Business Data and Outbox in the Same Transaction

Example order creation:

~~~sql
BEGIN;

INSERT INTO orders (
    order_id,
    customer_id,
    status,
    total_amount,
    version
) VALUES (
    'order-1001',
    'customer-123',
    'PENDING',
    250000,
    1
);

INSERT INTO outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_sequence,
    event_type,
    payload
) VALUES (
    '11111111-1111-4111-8111-111111111111',
    'Order',
    'order-1001',
    1,
    'OrderPlaced',
    '{"orderId":"order-1001","customerId":"customer-123","total":250000}'
);

COMMIT;
~~~

If either `INSERT` fails, the entire transaction rolls back. An event cannot be emitted for an uncommitted order. In real applications, order IDs and event IDs are generated uniquely; `aggregate_sequence` is incremented cleanly within the same transaction.

### 6.3. Relay and the Duplicate Window

The relay can use polling or change data capture (CDC).

**Polling relay:**

1. Query unpublished rows whose retry time is due.
2. Claim rows using a lock/lease.
3. Publish messages to SQS or EventBridge.
4. Only after receiving an ACK, set `published_at`.
5. If publishing fails, increment `attempts` and compute `next_attempt_at` using exponential backoff with jitter.

There is a failure window that polling alone cannot eliminate: the broker receives the event, but the relay crashes before marking `published_at`. Once the lease expires, the relay resends the event. Therefore, `eventId` must be stable and consumers must deduplicate.

Never mark `published_at` before sending; if the relay crashes after marking but before publishing, the event is lost. Sending first and marking afterward accepts possible duplicates in order to prevent lost events.

When running multiple relay workers, use `SELECT ... FOR UPDATE SKIP LOCKED` or an equivalent lease/claim mechanism. Never hold database locks open across slow network calls; claim rows, commit the lease, publish outside the transaction, and then update status.

**CDC relay:** uses database change streams or a CDC service to read changes from the outbox table. With relational databases, AWS DMS can stream changes to targets like Amazon Kinesis Data Streams or Amazon MSK; a downstream consumer normalizes and publishes events to the target broker. CDC reduces polling overhead, but still requires managing checkpoints, replay, schema evolution, and duplicates.

## 7. Outbox with DynamoDB and DynamoDB Streams

With DynamoDB, `TransactWriteItems` can write the business item and the outbox item in a single transaction. DynamoDB Streams captures table changes in chronological order; a Lambda event source mapping reads the stream and publishes events to SQS/EventBridge.

Pattern:

~~~mermaid
flowchart LR
    A[Order API Lambda] --> T[DynamoDB TransactWriteItems]
    T --> O[Order item]
    T --> X[Outbox item]
    X --> S[DynamoDB Streams]
    S --> L[Publisher Lambda]
    L --> Q[SQS or EventBridge]
    Q --> C[Consumer Lambda]
    C --> I[Inbox / processed event store]
~~~

Within a single transaction, the application can:

- Put the order item with a condition that it does not already exist.
- Put the outbox item with a unique event ID.
- Update an idempotency record or aggregate version if needed.
- Use condition expressions to prevent invalid state transitions.

`TransactWriteItems` executes actions atomically inside the transaction. The API supports up to 100 actions and a maximum total item size of 4 MB per transaction; all actions must be in the same account and Region. `ClientRequestToken` makes the same transaction request idempotent for 10 minutes after the initial request completes. After 10 minutes, the same token is treated as a new request; therefore, this token does not replace longer-lived business idempotency records.

DynamoDB Streams records are ordered within the stream, yet a Lambda consumer can still reprocess records on invocation retries. Use event IDs, sequence/version numbers, and an inbox to prevent duplicate side effects. In single-table designs, the publisher must filter for the right item type or outbox record so not every table mutation is emitted as a business event.

## 8. Choosing SQS Standard, SQS FIFO, or EventBridge?

Event delivery services have different characteristics. Choose based on ordering, fan-out, filtering, throughput, and integration needs.

| Service | Characteristics | When Suitable |
|---|---|---|
| SQS Standard | At-least-once, high throughput, no strict ordering guarantee | Independent task queues where consumers can deduplicate |
| SQS FIFO | Ordering per `MessageGroupId`, 5-minute producer deduplication window | Aggregate ordering needed or duplicate sends prevented within dedup window |
| EventBridge | Event bus, content-based routing, multiple targets, target retries and DLQ | Distributing events to multiple services, filtering via event patterns |
| DynamoDB Streams | CDC on item mutations, per-shard sequence | Emitting events from DynamoDB changes |
| Amazon SNS | Pub/sub fan-out to multiple subscribers | Broadcasting notifications simultaneously to multiple queues or endpoints |

SQS Standard can deliver duplicates and does not guarantee strict ordering. SQS FIFO provides ordering within the same message group; different groups can process in parallel. Producers can supply `MessageDeduplicationId` or enable content-based deduplication. The deduplication window is 5 minutes; resending after the window creates a new message.

With FIFO, set `MessageGroupId` by aggregate, such as order ID or account ID, when events for that aggregate must preserve order. Use a stable event ID for `MessageDeduplicationId`. Never use one single group ID for the entire system if you want parallel processing, as that serializes all messages.

EventBridge supports content-based event routing. For transient target delivery failures, EventBridge retries by default for up to 24 hours and 185 attempts with exponential backoff and jitter; retry policies and dead-letter queues are configurable. Delivery semantics from AWS service sources may be best-effort or durable at-least-once. Never assume every event source offers identical guarantees.

## 9. Consumers with SQS and Lambda

When Lambda reads SQS via an event source mapping, Lambda polls the queue and sends a batch of messages to the function. If the function processes the whole batch successfully, Lambda deletes the messages. If the invocation fails, messages can reappear after the visibility timeout.

Consumer design:

1. Parse and validate schema.
2. Extract `eventId`, `aggregateId`, and `aggregateVersion`.
3. Check the inbox or processed-message store.
4. If new, claim the event ID via conditional write/unique constraint.
5. Update business state in the same transaction as the inbox record.
6. Commit.
7. Only then acknowledge the message as processed.

For multi-message batches, enable partial batch responses (`ReportBatchItemFailures`) so only failed messages are returned. If one message fails and the function fails the whole batch, already-succeeded messages may be redelivered. Powertools for AWS Lambda includes a Batch Processing utility to simplify managing partial batch responses.

Visibility timeout must be long enough for batch processing time. AWS recommends setting the queue visibility timeout to at least six times the Lambda function timeout to leave room for retries/throttling. For extended processing, call `ChangeMessageVisibility` dynamically based on actual progress.

Configure a DLQ/redrive policy with an appropriate `maxReceiveCount`. Permanent failures or poison messages should not loop infinitely and clog the queue. DLQs need triage procedures, root-cause fixes, and controlled redrive; redrives can still produce duplicates, so consumers must remain idempotent.

## 10. Event Ordering and Versioning

Idempotency handles duplicates, but does not automatically handle out-of-order events.

For example, an order emits two events:

- Version 1: `OrderPlaced`.
- Version 2: `OrderCancelled`.

If a consumer receives `OrderCancelled` first and `OrderPlaced` second, a naive overwrite could revert the status from `CANCELLED` back to `PLACED`.

Solutions:

- Attach `aggregateVersion` or a sequence number to every event.
- Consumers apply only events matching the next expected version per business rules.
- If the version is less than or equal to the processed version, treat it as duplicate/stale and ignore it.
- If the version skips ahead, pause, retry, or request replay of the missing event.
- Use SQS FIFO `MessageGroupId` per aggregate when transport ordering is needed.
- Never assume timestamps alone suffice for strict ordering; clock skew and event creation time can differ from commit order.

A consumer can store `last_applied_version` alongside business state. Upon receiving an event with version `v`, check `v == last_applied_version + 1`; if true, update state and version in the same transaction. If `v` is less than or equal, the event is stale; if `v` is greater, wait or recover the missing event.

Ordering is typically only needed within a single aggregate or entity. Avoid global ordering across the entire system as it reduces throughput and increases coupling.

## 11. Retries, Timeouts, Backoff, and DLQs

Retries recover transient failures such as network timeouts, throttling, or service unavailability. However, retries cannot fix invalid data, permission errors, or business logic bugs.

A policy should define:

- **Timeout:** limit downstream call duration.
- **Retryable errors:** explicit list of errors eligible for retry.
- **Exponential backoff:** progressively increase wait duration.
- **Jitter:** add randomness so clients do not retry in lockstep.
- **Maximum attempts/age:** bound retry counts or total retry duration.
- **DLQ:** store messages that cannot be processed after retries.
- **Idempotency:** protect side effects across all retry attempts.

Do not immediately and continuously retry when downstream is overloaded. That triggers a retry storm. Use circuit breakers or rate limits to shed load when dependencies degrade.

For EventBridge targets, configure retry policies and DLQs. For SQS, use redrive policies and DLQs. For Lambda asynchronous invocations, configure retries/destinations suited to the trigger type. For DynamoDB Streams, monitor iterator age, retry behavior, and failed-record handling.

When replaying a DLQ, keep the original event ID and payload if it represents the same event. Never generate a new event ID just to force a retry, as consumers will treat it as a brand-new event and may repeat side effects.

## 12. Sagas and Cross-Service Consistency

An outbox guarantees event intent is saved alongside the local transaction. Yet a workflow may update multiple independent databases, such as Order, Inventory, Payment, and Shipping. Never keep a database transaction open while making remote service calls.

**Sagas** split a long-running business transaction into a sequence of local transactions. Each step commits in its data-owning service; when a step fails, the workflow executes forward recovery or compensating transactions.

Example checkout flow:

| Step | Local Transaction | Compensation |
|---|---|---|
| 1. Create order | Create order in `PENDING` state | Cancel order |
| 2. Reserve inventory | Reserve stock | Release inventory |
| 3. Authorize payment | Hold payment authorization | Void authorization |
| 4. Create shipment | Create shipping request | Cancel shipment if still possible |
| 5. Confirm order | Transition order to `CONFIRMED` | Separate business process if already shipped |

Compensation is not always a physical rollback. If a payment has already been captured or a shipment dispatched, compensation may involve a refund, return, or manual review case.

Two ways to organize a saga:

- **Choreography:** services emit events and other services react. Suits simple workflows with low coupling, though overall flow is harder to observe with many participants.
- **Orchestration:** a coordinator manages ordering, timeouts, retries, and compensation. AWS Step Functions can orchestrate steps and error-handling branches.

Each local transaction and compensation must also be idempotent. If the saga orchestrator retries a step, participating services must not reserve inventory or charge money twice. Persist saga ID, step ID, attempt, status, and correlation ID for troubleshooting.

## 13. Combining Idempotency, Outbox, and Sagas in an AWS Architecture

A reference architecture for orders:

~~~mermaid
flowchart TD
    C[Client with Idempotency-Key] --> A[API Gateway]
    A --> O[Order Service on Lambda or ECS]
    O --> D[(RDS or Aurora)]
    D --> I[Idempotency record]
    D --> B[Order business row]
    D --> X[Outbox event row]
    X --> R[Outbox relay or CDC]
    R --> Q[SQS FIFO or EventBridge]
    Q --> W[Workflow / Step Functions]
    W --> P[Payment service]
    W --> N[Inventory service]
    W --> S[Shipping service]
    P --> PI[(Payment inbox)]
    N --> NI[(Inventory inbox)]
    S --> SI[(Shipping inbox)]
    W --> DLQ[DLQ and operations queue]
~~~

Role of each component:

- **API Gateway:** receives requests, authenticates, and applies throttling. Business idempotency is still enforced at the application/database layer.
- **Order Service:** validates the key, creates the order and outbox event in one local transaction.
- **RDS/Aurora:** stores orders, idempotency records, and outbox rows.
- **Outbox relay/CDC:** publishes committed events to the broker.
- **SQS FIFO:** maintains per-order event ordering if needed; 5-minute producer dedup.
- **EventBridge:** routes events to multiple workflows or services by content.
- **Step Functions:** orchestrates sagas, timeouts, retries, and compensation.
- **Consumer inbox:** records processed event IDs alongside business updates.
- **DLQ:** retains unprocessable events for investigation and replay.

If using DynamoDB instead of RDS, `TransactWriteItems` can write the order and outbox item; DynamoDB Streams triggers the publisher Lambda. When using Lambda, AWS Lambda Powertools Idempotency can persist idempotency state in DynamoDB; the Java implementation supports a DynamoDB persistence layer. Verify library versions, TTL settings, and IAM permissions before production deployment.

## 14. Design Example: Order Creation API with Idempotency and Outbox

Suppose `POST /orders` receives an `Idempotency-Key`. A valid request must:

1. Canonicalize the payload and compute a request hash.
2. Open a database transaction.
3. Create or claim the idempotency record by unique key.
4. If the key already exists with a different hash, roll back and return `409 Conflict`.
5. If the key already succeeded, read the saved response/resource ID and return it.
6. If the key is new, create the order.
7. Insert the `OrderPlaced` event into the outbox with a unique event ID and aggregate version.
8. Save the response along with idempotency status `SUCCEEDED`.
9. Commit.
10. Return the response to the client.

Pseudocode:

~~~text
handleCreateOrder(request, key):
    requestHash = hash(canonicalize(request))
    scope = (tenantId, "POST:/orders", key)

    begin transaction

    record = claimIdempotencyKey(scope, requestHash)

    if record exists and record.requestHash != requestHash:
        rollback
        return 409 Conflict

    if record.status == SUCCEEDED:
        commit
        return record.savedResponse

    if record is IN_PROGRESS and owned by another active worker:
        rollback
        return 202 Accepted or retryable response

    order = insertOrder(request)
    event = createOrderPlacedEvent(order)

    insertOutbox(event)
    saveIdempotencyResult(scope, order.id, response, SUCCEEDED)

    commit
    return response
~~~

In production implementations, claiming the key, creating the order, inserting the outbox, and saving the response must happen in the same transaction or follow a clearly defined lease/fencing protocol. If the `IN_PROGRESS` record is created in a separate transaction, handle crashes between claiming the key and committing the business transaction.

### 14.1. When the Relay Sends the Event

The relay sends `OrderPlaced` to SQS FIFO:

- `MessageGroupId = orderId`.
- `MessageDeduplicationId = eventId`.
- Payload includes `aggregateVersion`.

After receiving an ACK, the relay marks the event published. If the relay crashes before marking it, the event may be resent; consumers will use `eventId` to deduplicate.

### 14.2. When the Inventory Consumer Processes It

Inventory service opens a transaction:

1. Insert `(consumer_name, event_id)` into the inbox.
2. If the key already exists, skip the event.
3. If new, check `aggregateVersion` and order state.
4. Reserve inventory using a conditional update.
5. Commit the inbox and inventory update together.

If inventory is insufficient, the consumer emits an `InventoryRejected` business outcome through its own outbox. The saga coordinator receives the event and executes compensation such as canceling the order or voiding payment authorization if payment already ran.

## 15. AWS Lambda Powertools Idempotency

AWS Lambda Powertools provides an idempotency utility to reduce boilerplate code. The utility can derive a key from the entire event or a selected subset of fields, store state and responses in a persistence layer, and return prior results when the same request is invoked again within the configured expiration window.

For Java, Powertools documentation describes DynamoDB as the supported persistence layer. The table typically uses `id` as the partition key and a TTL attribute to clean up expired records. The Lambda execution role needs matching DynamoDB read/write permissions, typically including:

- `dynamodb:GetItem`
- `dynamodb:PutItem`
- `dynamodb:UpdateItem`
- `dynamodb:DeleteItem`

Key considerations:

- Choose the right business fields as the idempotency key; do not hash the whole payload by default if it contains timestamps or fields that vary across retries.
- Set expiration longer than the actual retry window.
- Handle concurrent requests and `IN_PROGRESS` states.
- Do not store oversized responses in DynamoDB; DynamoDB items have a 400 KB size limit.
- Do not use Powertools as a substitute for an outbox or inbox; the utility protects handler invocations, whereas an outbox prevents dual-writes and an inbox protects consumer side effects.
- For external side effects, still pass an idempotency key to the provider or use reconciliation.

## 16. Consistency Models and Business Invariants

Not all data requires strong consistency across the entire system. Identify which invariants must hold immediately and which data can converge over time.

| Data or Invariant | Consistency Requirement |
|---|---|
| Never create two orders for the same idempotency key | Atomic unique constraint/conditional write |
| Never deduct inventory below available quantity | Conditional update or transaction in Inventory service |
| Payment never captured twice | Provider idempotency key and payment state machine |
| Confirmation email can arrive slightly later | Eventual consistency is usually acceptable |
| Search index updated after order commit | Eventual consistency with lag monitoring |
| Events for the same order follow version order | Per-aggregate ordering and version checks |
| End-of-day revenue reports | Eventual consistency and reconciliation |

Local strong consistency inside one database does not automatically produce strong consistency across multiple services. Identify where each invariant is owned. The data-owning service must enforce invariants using transactions, conditional writes, or state machines; other services interact via APIs/events.

Do not let multiple services write directly to the same database table without clear ownership boundaries and concurrency rules. Shared schema and transaction coupling prevent services from deploying independently.

## 17. Observability: Measuring Outboxes, Inboxes, and Duplicates

Monitor not only queue state, but also event latency and age.

Useful metrics:

| Category | Metrics or Data Points |
|---|---|
| API idempotency | New requests, replays, key conflicts, in-progress conflicts, record expirations |
| Outbox | Pending count, oldest pending age, publish attempts, publish failures, relay lag |
| Broker | Queue depth, age of oldest message, delivery count, DLQ depth |
| Consumer | Duplicate rate, processing latency, failure rate, retry count |
| Ordering | Version gaps, stale event count, out-of-order event count |
| Saga | Running duration, failed steps, compensation count, stuck workflows |
| Business | Duplicate orders/payments prevented, inventory mismatches, reconciliation backlog |

Every request/event should carry:

- `correlationId`: links steps across a business flow.
- `causationId`: the event/request that triggered the current event.
- `eventId`: unique identifier of the event.
- `aggregateId` and `aggregateVersion`.
- Protected `idempotencyKey` or hash.
- `sagaId` and step name when using orchestration.

Never log raw payment credentials, access tokens, session secrets, or unnecessary personal data. You can log a hash or masked portion of the idempotency key for searchability.

Alerts should focus on actionable operational signals: oldest outbox event age breaching thresholds, growing DLQs, rising event age, stuck sagas, abnormal spikes in duplicate rates, or incomplete reconciliations.

## 18. Testing Failure Modes

A solid test suite must simulate failures between steps, not just the happy path.

| Scenario | Expected Outcome |
|---|---|
| Client times out after DB commit and retries same key | Returns previous order/result; does not create a second order |
| Same key with different payload | Rejected with conflict |
| Two requests with same key arrive concurrently | Only one claims and executes side effects |
| DB transaction rolls back | Neither business row nor outbox event exists |
| Relay crashes before publishing | Event remains pending and gets retried |
| Relay crashes after publishing but before marking published | Duplicate may be sent; consumer deduplicates |
| Consumer commits DB then crashes before ACK | Message is redelivered; inbox prevents duplicate side effects |
| Consumer fails one message in a batch | Partial batch response retries only the failed message |
| Message arrives with wrong version | Consumer waits, retries, or requests replay; does not overwrite newer state |
| Payment provider times out after charging | Retry with same provider idempotency key or query status before charging again |
| DLQ is redriven | Original event ID is preserved and consumer remains idempotent |
| Saga fails at final step | Executes compensations in order and records outcomes |

Also test concurrent load, extended timeouts, service throttling, queue visibility timeouts, network partitions, and database failovers. For retries, verify backoff/jitter to avoid retry storms.

## 19. Security and Operations

Idempotency records and outbox tables can contain customer details, orders, payment references, and business data. Protect them like critical application data.

- Use least-privilege IAM for APIs, relays, Lambda consumers, and Step Functions.
- Encrypt data at rest with KMS as required.
- Restrict who can read outbox and inbox payloads.
- Omit secrets or sensitive payment data from event payloads if consumers do not need them.
- Use schema versions to evolve events safely.
- Limit outbox/inbox retention according to audit and replay needs.
- Maintain runbooks for DLQs, stuck outboxes, duplicate payments, and saga compensations.
- Audit changes to IAM, queue policies, event bus policies, and database permissions with CloudTrail.

The outbox should not hold unbounded payloads. It can store minimal data and a reference to a resource; consumers fetch the rest via authorized APIs. However, if consumers read current state rather than an event snapshot, remember that data may have changed by the time the event is processed. Choose explicitly between event-carried state transfer and event notification.

## 20. Hands-On: Designing a Safely Retryable Order Flow

An online store uses API Gateway, Order Service on Lambda, Aurora PostgreSQL, SQS FIFO, and Step Functions. Requirements:

- Client retries never create duplicate orders.
- Orders and `OrderPlaced` events never drift out of sync.
- Inventory reserves stock only once per event.
- Payments are never charged twice.
- Events for the same order are processed in order.
- If payment fails, inventory is released and the order transitions to the appropriate state.

Implement in this order:

1. Design an idempotency record with a unique key scoped by tenant, operation, and client key.
2. Compute a request hash and reject same-key different-payload requests.
3. Write the order, idempotency result, and outbox event in a single transaction.
4. Choose a polling relay or CDC; persist event ID and aggregate version.
5. Publish events to SQS FIFO with group ID set to order ID.
6. Use an inbox table in Inventory service and Payment service.
7. Forward idempotency keys to the payment provider.
8. Use Step Functions to orchestrate steps and compensations.
9. Configure DLQs, retries/backoff, and partial batch responses.
10. Build dashboards for outbox age, queue age, duplicate rate, and saga failures.
11. Simulate crashes after commit, crashes after publish, and timeouts from the payment provider.
12. Prove with data that every order/payment yields at most one valid business outcome.

The target outcome is not forcing every function to be invoked strictly once. The target outcome is that even when requests, events, or functions retry multiple times, the system converges on one correct, auditable business state.

## Conclusion

Idempotency allows requests and messages to be retried without repeating side effects. The transactional outbox records business state and event intent in the same transaction to eliminate dual-write errors. An inbox lets consumers deduplicate within the same transaction as business updates. SQS FIFO, EventBridge, DynamoDB Streams, and Lambda provide different event delivery mechanisms, yet none removes the need for application-level duplicate handling.

When a business flow spans multiple services, sagas coordinate local transactions and compensations. Reliable designs require stable event IDs, clearly scoped idempotency keys, ordering/versioning, bounded retries, DLQs, observability, and reconciliation. Test crash windows between commit, publish, consume, and ACK to prove the system recovers without creating duplicate transactions.

## References

- [Transactional outbox pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Idempotency — Powertools for AWS Lambda Java](https://docs.aws.amazon.com/powertools/java/latest/utilities/idempotency/)
- [Idempotency — Powertools for AWS Lambda Python](https://docs.aws.amazon.com/powertools/python/latest/utilities/idempotency/)
- [DynamoDB TransactWriteItems API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html)
- [How DynamoDB transactions work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [Exactly-once processing in Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-exactly-once-processing.html)
- [Outage recovery scenarios in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Best practices for DynamoDB Streams with Lambda](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.Lambda.BestPracticesWithDynamoDB.html)
- [Delivery level for AWS service events — EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/event-delivery-level.html)
- [EventBridge target retry policy](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [Saga patterns — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-patterns.html)
- [Saga orchestration pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html)
