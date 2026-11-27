# Building an Event Pipeline with Serverless Functions and Error Handling

## Project Objective

In this capstone project, you will build an asynchronous event-processing pipeline using serverless functions. The pipeline receives business events, validates data contracts, enqueues events, invokes a function to process them, persists results, and emits follow-up events. When processing fails, the system performs bounded retries, isolates failed messages into a dead-letter queue (DLQ), triggers alerts, and enables recovery through controlled redrive.

The sample problem is online order processing. The Order API service emits an `OrderPlaced` event after an order is created. An event-processing function validates the payload, reserves inventory, and updates order status. When a dependency fails transiently, the message is retried. When a message cannot be processed after exhausting the retry policy, the queue moves it to the DLQ for investigation. After the root cause is fixed, operators can replay valid messages without creating duplicate orders or double-reserving inventory.

This project brings together the cloud compute skills covered so far: queues, event buses, serverless functions, storage, identity, autoscaling, monitoring, retries, idempotency, and cost optimization.

Upon completion, you will be able to:

- Design an asynchronous event flow using a queue as a buffer.
- Define event contracts, schema versions, and idempotency keys.
- Write producers and serverless consumers with clear responsibilities.
- Handle duplicates, retries, timeouts, poison messages, and partial batch failures.
- Configure DLQs, retention, redrive, and alerting.
- Limit concurrency and apply backpressure to protect dependencies.
- Observe the entire event lifecycle from publish to final outcome.
- Protect payloads, credentials, and access permissions.
- Inject intentional faults and prove recovery capability.
- Evaluate cost per successfully processed event.

## 1. Context and Business Requirements

An online store receives high volumes of orders. Once the Order API creates an order, the following tasks can run independently:

- Checking and reserving inventory.
- Calculating shipping details.
- Sending confirmation notifications.
- Updating analytics data.
- Emitting events for downstream systems.

If the Order API called every service synchronously in sequence, response times would depend on every dependency. A single slow service could cause order-creation requests to time out even after the order record was written. During traffic spikes, all downstream services could become overloaded simultaneously.

An event pipeline decouples order ingestion from downstream processing. The producer records the order and durably emits an event; the consumer processes independently within its own capacity. The queue absorbs bursts, retries handle transient faults, and the DLQ isolates persistent failures.

### 1.1. Functional Scope

The pipeline must:

1. Have the producer generate `OrderPlaced` with a stable event ID.
2. Validate the event against a schema before publishing.
3. Persist the event to a durable source.
4. Have the serverless function receive a message or batch.
5. Have the consumer check idempotency before applying side effects.
6. Have the consumer verify the order and reserve inventory.
7. Commit results durably.
8. Have the consumer acknowledge only after committing.
9. Retry transient errors according to policy.
10. Route messages exceeding retry thresholds to the DLQ.
11. Equip the DLQ with metrics, alerts, retention, and an owner.
12. Allow operators to investigate, fix bugs, and redrive valid messages.
13. Prevent duplicate side effects when messages are redelivered.

### 1.2. Non-Functional Requirements

| Requirement | Design Target |
|---|---|
| Durability | Confirmed published events must persist according to the queue's durability contract |
| Reliability | Duplicate deliveries must not create duplicate orders or inventory reservations |
| Availability | Producer continues accepting orders when consumers slow down, within queue and storage limits |
| Scalability | Functions scale with backlog without exceeding dependency capacity |
| Recoverability | Failed messages can be investigated and recovered |
| Observability | Track publish, processing, retries, DLQ, and end-to-end latency |
| Security | Least privilege, encryption, and sensitive data controls |
| Cost control | Bound concurrency, retry storms, log volume, and retention |

Quantitative targets such as throughput, latency, retention, and recovery time must be defined per deployment environment. Do not assume a single figure fits every workload.

## 2. Overall Architecture

A reference architecture:

~~~mermaid
flowchart LR
    API["Order API"] --> OB["Transactional outbox"]
    OB --> PUB["Outbox publisher"]
    PUB --> Q["Orders queue"]
    Q --> FN["Serverless consumer"]
    FN --> DB["Orders / inventory database"]
    FN --> OUT["OrderAccepted event"]
    Q -->|Retry exhausted| DLQ["Orders DLQ"]
    DLQ --> OBS["Alert and investigation"]
    OBS --> RD["Controlled redrive"]
    RD --> Q
    FN --> MET["Logs / metrics / traces"]
    Q --> MET
    DLQ --> MET
~~~

Components:

- **Order API:** validates requests and persists orders.
- **Transactional outbox:** stores events to be emitted in the same transaction as the order.
- **Outbox publisher:** reads the outbox and dispatches events to the queue.
- **Orders queue:** buffers events and decouples producer from consumer.
- **Serverless consumer:** processes events in batches or individually.
- **Database:** stores order state, reservations, and idempotency records.
- **OrderAccepted event:** notifies downstream systems of the outcome.
- **Orders DLQ:** isolates messages that have exceeded the retry policy.
- **Observability backend:** collects metrics, logs, traces, and alerts.
- **Redrive worker/tool:** returns verified messages to the processing flow.

You may substitute an event bus or stream for the queue if routing, fan-out, ordering, or replay requirements differ. However, select exact semantics before writing the consumer because acknowledgment and retry behavior vary across event sources.

### 2.1. Why Place a Queue Between Producer and Function?

A queue establishes an asynchronous boundary:

- The producer does not wait for the function to complete.
- The consumer can scale independently.
- Bursts buffer in the queue rather than hitting the database directly.
- Retries do not require the producer to resend the order-creation request.
- The DLQ isolates failed messages from the normal flow.
- Queue depth and message age measure processing pressure.

A queue does not eliminate capacity limits. If the sustained publish rate exceeds the processing rate, the backlog will grow. Monitor oldest message age and cap concurrency based on dependency capacity.

### 2.2. Success and Failure Flows

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant Q as Orders queue
    participant F as Serverless function
    participant DB as Database
    participant D as DLQ
    API->>Q: Publish OrderPlaced
    Q->>F: Deliver message
    F->>DB: Check idempotency and reserve stock
    alt Commit succeeds
        DB-->>F: Reservation committed
        F-->>Q: Acknowledge
        F->>Q: Publish OrderAccepted
    else Transient error
        DB-->>F: Timeout / temporary failure
        F-->>Q: Do not acknowledge
        Q->>F: Retry after visibility/delay
    else Attempts exhausted
        Q->>D: Move message to DLQ
    end
~~~

The ordering of publishing the downstream event and acknowledging must be designed carefully. If the database commit succeeds but publishing `OrderAccepted` fails, downstream systems may miss the event. Use a transactional outbox for output events or write both the result and the outbox record within the same transaction.

## 3. Event Contract and Schema

An event contract defines message structure, semantics, and compatibility rules. Producers and consumers must use a governed schema version.

Example `OrderPlaced`:

~~~json
{
  "eventId": "evt-01J9A6M7Q2",
  "eventType": "com.example.orders.order-placed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-22T09:30:00Z",
  "producer": "order-api",
  "correlationId": "req-7f31a2",
  "data": {
    "orderId": "ord-10482",
    "customerId": "cus-918",
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-RED-01",
        "quantity": 2
      }
    ]
  }
}
~~~

This example uses illustrative IDs. In a real system, the event ID must be unique and stable across all retries and redrives.

### 3.1. Key Fields

| Field | Purpose |
|---|---|
| eventId | Idempotency key and event identifier |
| eventType | Handler selection and routing rules |
| schemaVersion | Compatible parser/validator selection |
| occurredAt | Business occurrence timestamp |
| producer | Event origin |
| correlationId | Request and trace correlation |
| data | Business payload |

You can add tenant, partition key, trace context, event expiry, and sequence number if needed. Avoid putting tokens, passwords, or unnecessary sensitive data into events.

### 3.2. Schema Evolution Rules

- Adding optional fields with defaults is usually more compatible than changing existing field types.
- Never change the meaning of a field while keeping the same schema version.
- Consumers should ignore unknown fields if the contract permits.
- Breaking changes require a new version or a planned migration.
- Producers must not emit events before consumers support the new schema.
- Keep representative sample events in contract tests.

Do not use timestamps as event IDs. Two events can share the same timestamp and producer clocks can drift. Use a stable ID or a well-defined business key.

### 3.3. Payload Validation

The consumer should validate:

- Event ID is present and well-formed.
- Event type is supported.
- Schema version is accepted.
- Required fields are present.
- Quantities and numeric values fall within valid ranges.
- Payload size does not exceed limits.
- Tenant/customer is authorized to emit the event if source validation applies.

Schema or invalid-payload errors are typically permanent failures. Do not retry repeatedly without a data or code change.

## 4. Designing the Producer and Transactional Outbox

The producer must avoid scenarios where the database writes an order successfully but event publishing fails. If the two operations are not part of a distributed transaction, an order can exist while the consumer never receives the event.

A transactional outbox solves this by writing the order and the outbox record in the same database transaction.

Workflow:

1. Receive the order creation request.
2. Generate the order ID and event ID.
3. Insert the order record.
4. Insert the outbox record containing the event envelope.
5. Commit the transaction.
6. The publisher reads unpublished outbox records.
7. Publish the event to the queue.
8. Mark the outbox record as published upon confirmation.
9. If the publisher times out, resend the event with the same event ID.

Example logical table:

~~~sql
CREATE TABLE outbox_events (
    event_id        VARCHAR(80) PRIMARY KEY,
    aggregate_id    VARCHAR(80) NOT NULL,
    event_type      VARCHAR(160) NOT NULL,
    schema_version  INTEGER NOT NULL,
    payload         JSON NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL
);
~~~

Adapt the SQL schema to your actual database. The publisher should handle leases/locking so multiple instances do not claim the same record simultaneously. If publishing succeeds but updating `published_at` fails, the event may be resent; the consumer must still be idempotent.

### 4.1. Outbox Publisher

The publisher can be a scheduled serverless worker, a database change stream, or a continuous polling process. Bound batch sizes and retry counts.

Common states:

- `pending`: not yet sent.
- `publishing/leased`: currently being handled by a publisher.
- `published`: queue acknowledged receipt of the event.
- `failed/review`: persistent failure requiring investigation.

Do not delete outbox records immediately after publishing if audit or reconciliation is needed. Configure an appropriate retention and archival policy.

## 5. Designing the Serverless Consumer

The consumer receives messages from the queue, validates them, checks idempotency, executes business logic, and acknowledges only after results are durable.

Handler responsibilities should be clear:

- Parse the event envelope.
- Validate schema and business invariants.
- Check whether the event has already been processed.
- Execute side effects transactionally/idempotently.
- Classify transient versus permanent failures.
- Return results matching the event source's semantics.
- Log with correlation ID without exposing sensitive payloads.

### 5.1. Single-Message Processing Flow

~~~mermaid
flowchart TD
    A["Receive event"] --> B["Parse and validate"]
    B -->|Invalid| X["Permanent failure / quarantine"]
    B -->|Valid| C["Check idempotency"]
    C -->|Already completed| OK["Acknowledge safely"]
    C -->|New event| D["Apply business transaction"]
    D -->|Commit| E["Write result / outbox"]
    E --> OK
    D -->|Transient error| R["Retry"]
    D -->|Permanent business error| X
~~~

### 5.2. TypeScript Handler Example

The code below illustrates the structure for processing a single message. Database, queue, and logger interfaces must be implemented using the chosen platform's SDK.

~~~typescript
type OrderPlaced = {
  eventId: string;
  eventType: "com.example.orders.order-placed";
  schemaVersion: number;
  occurredAt: string;
  correlationId: string;
  data: {
    orderId: string;
    customerId: string;
    currency: string;
    items: Array<{ sku: string; quantity: number }>;
  };
};

class TransientError extends Error {}
class PermanentError extends Error {}

async function handleOrderPlaced(
  event: OrderPlaced,
  deps: Dependencies
): Promise<void> {
  validateOrderPlaced(event);

  await deps.database.transaction(async (tx) => {
    const alreadyDone = await tx.inbox.isCompleted(event.eventId);
    if (alreadyDone) return;

    await reserveInventory(tx, event.data.items);

    await tx.orders.markAccepted(event.data.orderId);
    await tx.inbox.markCompleted(event.eventId);

    await tx.outbox.add({
      eventId: createStableResultEventId(event.eventId),
      eventType: "com.example.orders.order-accepted",
      correlationId: event.correlationId,
      data: { orderId: event.data.orderId }
    });
  });
}
~~~

This example assumes the inbox, order, inventory, and outbox operations participate in a single database transaction. If inventory reservation lives in an external service outside the database, you need a saga or dedicated idempotent protocol; you cannot assume a single SQL transaction spans multiple services.

### 5.3. Error Classification in the Handler

~~~typescript
async function processMessage(
  message: QueueMessage,
  deps: Dependencies
): Promise<"success" | "retry" | "permanent"> {
  try {
    const event = parseAndValidateEnvelope(message.body);
    await handleOrderPlaced(event, deps);
    return "success";
  } catch (error) {
    if (error instanceof PermanentError) {
      await deps.quarantine.record(message, safeErrorCode(error));
      return "permanent";
    }

    if (isTransient(error)) {
      return "retry";
    }

    deps.logger.error("unclassified_processing_failure", {
      messageId: message.id,
      errorClass: classify(error)
    });
    return "retry";
  }
}
~~~

This is illustrative pseudo-code. Each event source expresses permanent failures differently. Some queue consumers only offer ack or nack; in that case, permanent failures must be safely recorded to a quarantine/DLQ before acking. Never ack a message whose quarantine write failed.

## 6. Idempotency and Side Effects

Queues typically provide at-least-once delivery. The same message may arrive multiple times. The consumer must ensure duplicates never create extra reservations, charges, or unintended notifications.

### 6.1. Inbox/Deduplication Store

An inbox table can store:

~~~sql
CREATE TABLE processed_events (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(160) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    processed_at   TIMESTAMP NULL,
    result_ref     VARCHAR(100) NULL
);
~~~

A primary key on `event_id` prevents two consumers from marking the same event as new when executed inside a proper transaction.

Statuses can include `processing`, `completed`, and `failed`, but require a lease/timeout in case a consumer crashes while recording `processing`. Never leave a `processing` record stuck permanently so that the event can never be retried.

### 6.2. External Side Effects

If the consumer calls a payment provider or external service, a database transaction cannot automatically roll back external side effects.

Use:

- Idempotency keys supported by the downstream provider.
- Request IDs stable per event and operation.
- Sagas with step-by-step state.
- Compensating actions where business logic allows.
- Reconciliation to detect uncertain outcomes.
- Timeouts and retries aligned with the dependency's contract.

If a downstream request times out, you cannot always assume the operation failed. The provider may have processed it while the response was lost. Query status using the idempotency key before resending.

### 6.3. Do Not Confuse Event ID with Attempt ID

The event ID stays constant across retries and redrives. The attempt ID may change on every invocation. Log both for troubleshooting, but deduplicate using the event ID or a stable operation key.

## 7. Retries, Visibility Timeout, and DLQ

The retry policy must be coordinated with processing duration, function timeout, and queue semantics.

### 7.1. Visibility Timeout

With polling queues, a message is typically hidden for a visibility timeout after a consumer receives it. If the consumer fails to ack/delete before the timeout expires, the message may be redelivered.

The visibility timeout must be large enough for:

- p99 processing duration.
- Database and output writes.
- Internal shutdown/retry time if applicable.
- Buffer for cold starts or network delays.

If visibility is too short, two workers may process the same message concurrently. If too long, failed messages wait excessively before retry. Size it based on measured processing duration and the provider's retry semantics.

### 7.2. Backoff and Jitter

Exponential backoff slows down retries when a dependency fails:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt)
~~~

Jitter spreads retry timing:

~~~text
actualDelay = random(0, delay)
~~~

An illustrative policy:

~~~yaml
retry:
  maxAttempts: 5
  initialDelay: 2s
  maxDelay: 2m
  jitter: full
  maxEventAge: 6h
~~~

This is a conceptual configuration, not a universal schema. Queues may retry based on visibility timeout and receive count rather than per-attempt delays.

### 7.3. Redrive Policy and DLQ

Example logical configuration:

~~~yaml
sourceQueue:
  name: orders-events
  visibilityTimeout: 120s
  retention: 4d
  redrive:
    deadLetterQueue: orders-events-dlq
    maxReceiveCount: 5

deadLetterQueue:
  name: orders-events-dlq
  retention: 14d
  encryption: enabled
  alertOnVisibleMessage: true
~~~

Values are illustrative. Verify service limits, maximum retention, receive count semantics, and source queue permissions to send to the DLQ.

A DLQ needs an owner, alerting, retention, access controls, and a runbook. Otherwise, failed messages can expire unnoticed.

### 7.4. Poison Events

A malformed payload or a value that consistently throws an exception can become a poison event. Never retry indefinitely.

Classification:

- transient: retry with backoff.
- permanent/schema: quarantine or route to DLQ early.
- unknown: bounded retries, log error class, preserve context.
- dependency outage: reduce concurrency, apply backpressure, or pause consumer per runbook.

Never log full payloads if they contain customer details or payment data.

## 8. Batching and Partial Failures

A function can receive multiple messages per invocation to boost throughput and reduce overhead. However, if one record fails and the handler marks the entire batch failed, successfully processed records may be re-executed.

There are two models:

- Batch-level retry: the whole batch is redelivered when one record fails.
- Partial batch response: the function returns only failed records if the event source supports it.

Conceptual response example:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "msg-17" },
    { "itemIdentifier": "msg-22" }
  ]
}
~~~

The actual schema depends on the platform and event source type. Use the exact identifier required by the mapping.

### 8.1. Limiting Batch Size

Larger batches increase throughput but also:

- Lengthen invocation duration.
- Increase in-memory data volume.
- Increase the number of retried records when partial response is unavailable.
- Make isolating poison records harder.
- Extend how long messages remain invisible.

Choose batch size by testing with maximum payload sizes, p99 processing time, and function memory limits.

### 8.2. Batch Bisect

Some stream integrations support splitting a failed batch in half to isolate the failing record. This helps locate faults, though it increases invocations and does not replace idempotency.

For ordered streams, a failing record can block the checkpoint and stall subsequent records in the same partition. Understand checkpoint semantics before enabling batch bisect or partial failure.

## 9. Concurrency, Backpressure, and Capacity

Serverless platforms can scale rapidly, but downstream dependencies do not necessarily scale at the same pace. If functions open too many database connections or flood the inventory service, the system can turn a queue backlog into a dependency outage.

### 9.1. Limiting Concurrency

Set concurrency limits based on dependency capacity:

~~~text
maxFunctionConcurrency <=
  safeDatabaseConnections / connectionsPerInvocation
~~~

This formula is a starting estimate. Subtract connections reserved for APIs, admin tasks, and other workloads; factor in connection pools, retries, and region/instance counts.

Mechanisms include:

- Reserved/provisioned concurrency or provider equivalents.
- Queue consumer batch size.
- Poller concurrency.
- Rate limits per tenant or event type.
- Semaphores for downstream calls.
- Circuit breakers when dependencies fail.

### 9.2. Backpressure

When consumers fall behind producers:

- Queue depth increases.
- Oldest message age increases.
- Event latency increases.
- Storage/retention limits risk being hit.
- Retries can amplify load.

Backpressure options include throttling producer rates, capping consumer concurrency, deferring low-priority events, or returning retryable status to producers. Never scale functions without bounds if the database is the bottleneck.

### 9.3. Estimating Capacity

If each invocation processes an average of B messages in S seconds with C concurrent invocations, approximate theoretical throughput is:

~~~text
throughput ≈ (B * C) / S
~~~

For example, B=10, C=20, S=2 seconds yields a theoretical throughput of about 100 messages/second. Actual throughput also depends on cold starts, throttling, databases, networking, batch failures, and retry delays.

Measure successful throughput and oldest message age under realistic load. Never treat theoretical throughput as a capacity commitment.

## 10. Ordering and Partitioning

Not every pipeline requires strict ordering. If `OrderPlaced` and `OrderCancelled` for the same order must execute in order, a queue without ordering guarantees can produce invalid state.

Options:

- Use FIFO or partition keys by order ID if the provider supports it.
- Include aggregate version/sequence in the event.
- Have consumers verify version before applying changes.
- Accept late-arriving events and handle them via a state machine.
- Partition to increase parallelism while preserving per-group ordering.

Global ordering typically reduces throughput and increases coupling. Require ordering only at the scope needed, such as per order ID or customer ID.

### 10.1. Late-Arriving Events

If `OrderCancelled` arrives before `OrderPlaced` due to retries or replay, the consumer must decide whether to:

- Hold the event awaiting its predecessor.
- Record a pending state.
- Reject with a retryable error.
- Apply versioned state transitions.
- Quarantine the event for investigation.

Do not rely solely on timestamps to determine order because of clock drift and delivery delays.

## 11. Securing the Pipeline

Each component should hold only the permissions it needs:

- Producers can only publish to the source queue.
- Consumers can only read the queue, write required database records, and publish output events.
- Redrive operators can read the DLQ and run redrives within approved scope.
- Monitoring agents can only read required metrics/logs.
- Never grant DLQ purge permissions to business functions.

Controls:

- Encrypt queues, DLQs, and databases at rest.
- Enforce TLS in transit.
- Use workload identities or short-lived credentials.
- Use a secret manager for tokens/credentials.
- Verify signatures or origins when events cross trust boundaries.
- Validate schemas and cap payload sizes.
- Mask PII in logs.
- Audit publish, receive, redrive, purge, and policy changes.
- Define retention and deletion policies for events carrying sensitive data.

### 11.1. Events Are Not Arbitrary Commands

Never execute shell commands, arbitrary SQL, or unvalidated URLs supplied by payloads. Events must represent well-defined business data with explicit schemas, never an arbitrary command execution channel.

If an event contains an object key or URL, validate the namespace, tenant, and access permissions before fetching data.

## 12. Observability and Correlation

The pipeline must trace events from producer to final outcome. Propagate event IDs and correlation IDs end to end.

Metrics:

| Metric | Meaning |
|---|---|
| events_published_total | Total events published |
| publish_failures_total | Total failed publishes |
| queue_visible_messages | Current backlog |
| queue_oldest_message_age_seconds | Age of oldest queued message |
| function_invocations_total | Total invocations |
| function_errors_total | Total failed invocations |
| function_duration_seconds | Processing duration |
| function_throttles_total | Total throttled invocations |
| event_success_total | Total business-completed events |
| retry_attempts_total | Total retry attempts |
| dlq_visible_messages | Number of messages in DLQ |
| dlq_oldest_message_age_seconds | Age of oldest message in DLQ |
| redrive_success_total | Total messages successfully redriven |
| duplicate_events_total | Total events deduplicated by idempotency |
| downstream_latency_seconds | Dependency latency |

### 12.1. Structured Logging

Logs should include:

- `eventId`.
- `correlationId`/`traceId`.
- `eventType` and `schemaVersion`.
- Queue `messageId`.
- Attempt count if available.
- Function version.
- Error class/code.
- Duration and outcome.
- `redriveRunId` if replayed.

Do not log full payloads by default. Use field allowlists, masking, and appropriate log levels.

### 12.2. Distributed Tracing

Create spans for:

- Event publishing.
- Queue wait time if timestamps/metadata exist.
- Function invocation.
- Database transaction.
- Downstream API calls.
- Output event publishing.
- Redrive/replay.

Queues create an asynchronous boundary, so trace context must be propagated in the message envelope or attributes. Never use a trace ID as an idempotency key; the two concepts serve different purposes.

### 12.3. Alerting

Alerts should cover:

- Source queue oldest age breaching SLO.
- Continuously growing queue depth.
- Rising function error/throttle rates.
- New messages in DLQ or oldest age approaching retention.
- Rising outbox pending age.
- Database connections/latency exceeding thresholds.
- Redrives returning messages back to the DLQ.
- Publish failures or permission denied errors.
- Falling event success rate despite rising invocation rate.

Alerts must map to an owner and a runbook. For critical events, alert on the very first DLQ message; for lower-priority flows, count/age thresholds may be appropriate.

## 13. Redrive and Recovery Strategy

Redrive moves messages from the DLQ back to the source queue or a recovery queue. Never redrive the entire DLQ immediately after a code fix without testing a single message first.

Procedure:

1. Identify the root cause of failure.
2. Confirm the code/config/dependency fix is deployed.
3. Check schema versions and event expiry.
4. Verify idempotency and downstream state.
5. Select one representative message.
6. Test-redrive it and verify side effects.
7. Run small rate-limited batches.
8. Monitor the source queue, DLQ, dependencies, and SLOs.
9. Stop immediately if messages fail again.
10. Record an audit log of redrive scope and results.

### 13.1. Preserve Event Identity

When replaying, preserve the original event ID so deduplication works. You may attach `replayRunId`, `replayedAt`, and `replaySource`. Never alter the event ID to bypass idempotency, as doing so can trigger duplicate side effects.

### 13.2. Expired Events

An event may no longer be business-valid after some time—for example, the order was canceled or the payment window closed. Before redriving, inspect current state and event expiry. Some messages should be closed per business policy rather than replayed.

### 13.3. Avoid Retry-DLQ Loops

Never configure a DLQ consumer to automatically loop messages back to the source queue indefinitely. Redrive must be a controlled action with batch limits, rate limits, and stop conditions.

## 14. Reference Deployment and Configuration

The project should manage queues, DLQs, functions, permissions, databases, and alarms via Infrastructure as Code. Exact resource names and schemas depend on the provider; the configuration below is a conceptual model illustrating relationships.

~~~yaml
pipeline:
  name: order-event-pipeline

  sourceQueue:
    name: orders-events
    encryption: enabled
    retention: 4d
    visibilityTimeout: 120s
    redrive:
      target: orders-events-dlq
      maxReceiveCount: 5

  deadLetterQueue:
    name: orders-events-dlq
    encryption: enabled
    retention: 14d
    alertThreshold: 1

  consumer:
    function: process-order-event
    runtime: nodejs
    timeout: 30s
    memory: 1024MiB
    batchSize: 5
    maximumConcurrency: 20
    partialBatchResponse: enabled

  idempotency:
    store: processed-events
    key: eventId
    retention: 30d

  observability:
    structuredLogs: enabled
    tracing: enabled
    metrics: enabled
    alarms:
      - sourceQueueOldestAge
      - functionErrorRate
      - dlqVisibleMessages
~~~

This is not a directly deployable manifest. When translating to Terraform, CloudFormation, Bicep, or other provider tooling, map fields to the actual schema and check quotas, timeouts, retention, permissions, and encryption policies.

### 14.1. Consistent Timeout Configuration

If the function timeout is 30 seconds, the visibility timeout must not be shorter than maximum processing time plus buffer. For batches, account for the entire batch duration and retry mechanics. Some providers enforce specific formulas or bounds for visibility timeouts; check service documentation.

### 14.2. Function Permissions

The consumer needs permission to:

- Receive/read messages from the source queue.
- Delete/ack messages per the integration.
- Write to required databases/tables.
- Publish output events if applicable.
- Write logs/metrics/traces.
- Read specific secrets if genuinely needed.

The consumer does not need permissions to purge queues or alter redrive policies. Separate deployment, runtime, and redrive operator roles.

## 15. Testing the Pipeline

Testing must prove both the happy path and recovery capabilities.

### 15.1. Unit Tests

Test:

- Valid and invalid schemas.
- Unsupported event types.
- Invalid quantities or business invariants.
- Already-processed events.
- Dependency timeouts.
- Throttling errors.
- Permanent business errors.
- Retry classification.
- Stable idempotency keys.

### 15.2. Integration Tests

Test:

1. Producer writes order and outbox in a single transaction.
2. Publisher delivers the event successfully.
3. Consumer receives and processes the event.
4. Database updates accurately.
5. Output event is emitted.
6. Duplicate events produce no duplicate side effects.
7. Consumer failure causes message retry.
8. Messages exceeding thresholds move to the DLQ.
9. Redrive succeeds after fixing the error.

### 15.3. Failure Injection

Simulate scenarios:

| Scenario | Expected Result |
|---|---|
| Single database timeout | Message retries and eventually succeeds |
| Extended database outage | Concurrency is capped; backlog grows controllably |
| Malformed schema payload | Quarantined/DLQ'd without infinite retries |
| Consumer crashes after commit before ack | Redelivery creates no duplicates |
| Visibility timeout too short | Test detects duplicate concurrency handling |
| Function timeout | Message is retried according to policy |
| Misconfigured DLQ permissions | Alerts fire and detect undelivered DLQ transition |
| Outbox publish timeout | Publisher retries with the same event ID |
| Redrive batch too large | Rate limiting protects downstream |
| Expired event | Consumer rejects or routes per business policy |

Do not just verify the function returns HTTP 200 or invocation success. Verify order state, inventory reservations, inbox/outbox tables, queue state, and DLQ contents.

### 15.4. Load and Resilience Tests

Generate ramp-up, burst, and sustained load. Measure:

- Publish throughput.
- Queue depth and oldest message age.
- Function concurrency and duration.
- Database connections and latency.
- Success/error/retry rates.
- DLQ arrival rate.
- Cost per completed order.

Test system behavior when consumers are paused, the database slows down, and cloud dependencies lose connectivity. Confirm the producer continues operating within durability and retention limits.

## 16. Operations Runbook

### 16.1. When Source Queue Backlog Grows

1. Check producer rate and consumer invocation rate.
2. Check function errors, throttles, and duration.
3. Check database connections, latency, and quotas.
4. Identify whether the bottleneck is compute, queue poller, or dependency.
5. Reduce concurrency if downstream is overloaded.
6. Increase concurrency only if dependencies have headroom.
7. Compare oldest message age against SLO.
8. Monitor backlog drain after adjustments.

### 16.2. When Messages Appear in the DLQ

1. Identify event type, consumer version, and error class.
2. Determine whether it is a poison event or a dependency outage.
3. Select one representative message for investigation.
4. Validate payload and schema.
5. Fix producer, consumer, or configuration.
6. Retest using a copy of the message.
7. Redrive one message, then small batches.
8. Watch whether messages return to the DLQ.
9. Log audit trail and close the incident.

### 16.3. When an Event Is Processed Twice

1. Identify the event ID and all attempts.
2. Inspect idempotency records and transaction boundaries.
3. Determine whether downstream side effects occurred.
4. Run reconciliation or business compensation as appropriate.
5. Fix unique constraints, locking, or idempotency keys.
6. Replay a duplicate sample in staging.
7. Confirm the event is acknowledged without repeating side effects.

### 16.4. When Outbox Backlog Grows

Check publisher health, permissions, queue availability, lease timeouts, and locked record counts. Never delete outbox records just to zero the backlog. When a publish timeout leaves outcome uncertain, retry with the original event ID and rely on downstream idempotency.

## 17. Cost Optimization

Serverless does not automatically guarantee low cost. Retry storms, overly small batches, verbose logging, mis-sized function memory, and long queue retention can drive costs up.

Cost drivers:

- Invocation count and execution duration.
- Memory/CPU allocation.
- Batch size and concurrency.
- Queue requests/polling.
- Database reads/writes and connection overhead.
- Log/trace ingestion and retention.
- DLQ storage and redrive operations.
- Network transfer.
- Cold starts and provisioned capacity if used.

### 17.1. Cost per Successful Event

Measure cost against business outcomes:

~~~text
Cost per successful event =
  (function + queue + database + network + logs + retry + operations cost)
  / successful events
~~~

Compare batch sizes, memory settings, concurrency, and retry configurations using equivalent workloads. Never cut logging or retries to the point of losing recoverability solely to reduce cost.

### 17.2. Safe Cost Reduction

- Size memory/CPU from benchmarks.
- Choose appropriate batch sizes.
- Cap retry counts and event age.
- Eliminate duplicate work via idempotency.
- Sample traces and debug logs.
- Align DLQ retention with investigation windows.
- Prune published outbox records per policy.
- Use queue buffering to avoid overprovisioning consumers.
- Optimize queries and connection reuse.
- Alert on rising DLQ or retry rates.

## 18. Project Acceptance Criteria

The pipeline is considered complete when it demonstrates the following criteria:

| Category | Acceptance Criteria |
|---|---|
| Producer | Events have stable IDs; outbox prevents lost events after commit |
| Contract | Schemas are versioned and validated |
| Consumer | Function processes successfully and persists durable results |
| Idempotency | Resending the same event creates no duplicate side effects |
| Retry | Transient failures retry with bounds and backoff |
| DLQ | Poison/permanent failures are isolated and alerted |
| Redrive | Small batches can be replayed after fixing the root cause |
| Capacity | Concurrency does not overwhelm downstream services |
| Observability | Queue age, error rates, DLQ, traces, and correlation are visible |
| Security | Least privilege, encryption, and auditing are enforced |
| Recovery | Crash after commit before ack tested with zero duplicates proven |
| Cost | Cost per successful event report or proxy metric documented |

### 18.1. Deliverables

Project deliverables include:

- Architecture and sequence diagrams.
- Event schemas and sample payloads.
- Producer/outbox publisher.
- Serverless consumer and unit tests.
- Queue, DLQ, and permission configurations.
- Idempotency store/schema.
- Infrastructure as Code.
- Dashboards, alarms, and runbooks.
- Failure injection and load test reports.
- Redrive and rollback guides.

## 19. Common Pitfalls and How to Avoid Them

**Publishing after commit without an outbox:** orders can exist while events are lost. Use a transactional outbox or equivalent guarantee.

**Acking before committing results:** function crashes can lose events. Acknowledge only after side effects are durable.

**Missing idempotency:** at-least-once delivery creates duplicates. Use stable event IDs and transactions/unique constraints.

**Retrying all errors:** malformed payloads loop endlessly. Classify transient versus permanent failures.

**Retrying without jitter:** multiple functions retry simultaneously, causing a thundering herd. Use backoff, jitter, and concurrency limits.

**Visibility timeout too short:** messages are redelivered while the original invocation is still running. Size it to processing time plus buffer.

**Unbounded function scaling:** databases become overloaded. Enforce maximum concurrency and backpressure.

**DLQ without an owner:** messages sit until retention expires. Assign an owner, alerts, and a runbook.

**Redriving everything at once:** dependencies get overloaded again. Test one message first, then use small rate-limited batches.

**Changing event ID on replay:** idempotency fails to detect duplicates. Keep the original event ID and attach replay metadata.

**Ignoring event expiry:** stale events mutate business state that is no longer valid. Validate business state before applying changes.

**Logging entire payloads:** leaks PII/secrets and inflates costs. Use structured logs, masking, and allowlists.

**Not testing crash after commit:** duplicate side effects surface only in this failure window. Write a dedicated commit-before-ack test.

## 20. Pipeline Implementation Checklist

- [ ] Architecture defines producer, queue, function, database, DLQ, and downstream events.
- [ ] Event contract includes `eventId`, `eventType`, `schemaVersion`, and `correlationId`.
- [ ] Schema validation executes before any side effects.
- [ ] Producer uses a transactional outbox or equivalent publish guarantee.
- [ ] Consumer is idempotent on a stable event ID.
- [ ] Side effects and inbox state commit atomically.
- [ ] Acknowledgment occurs only after durable persistence.
- [ ] Retries enforce max attempts, event age, backoff, and jitter.
- [ ] Visibility timeout aligns with function timeout and p99 processing duration.
- [ ] DLQ has a redrive policy, encryption, retention, and alerting.
- [ ] Permanent failures are quarantined appropriately.
- [ ] Partial batch responses are enabled when supported by the event source.
- [ ] Maximum concurrency protects databases and downstream services.
- [ ] Ordering/partition keys match business requirements.
- [ ] IAM/workload identities follow least privilege.
- [ ] Logs mask sensitive data and include correlation IDs.
- [ ] Dashboards track queue age, function errors, retries, and DLQ state.
- [ ] Redrive enforces batch limits, rate limits, auditing, and stop conditions.
- [ ] Duplicates, timeouts, poison events, and DLQ routing are tested.
- [ ] Load/resilience tests are executed and cost per successful event is calculated.
- [ ] Runbooks exist for backlogs, DLQs, duplicates, and outbox backlogs.
- [ ] Acceptance criteria and deliverables are archived.

This project builds a serverless event pipeline capable of ingesting asynchronous load, processing independently, and recovering when functions or dependencies fail. Pipeline quality depends on stable event contracts, idempotency, bounded retries, an owned DLQ, and end-to-end observability. By testing commit-before-ack crashes, poison events, backlogs, and controlled redrives, you can prove the system processes events accurately and scales without overwhelming downstream services.
