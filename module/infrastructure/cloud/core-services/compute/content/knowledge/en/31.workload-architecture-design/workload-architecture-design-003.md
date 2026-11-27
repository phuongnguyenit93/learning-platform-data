# Designing Event-Driven Processing Systems with Serverless Functions

## Learning Objectives

After this lesson, you will be able to:

- Explain how serverless functions receive and process events under an asynchronous model.
- Select event sources, routers, queues, and handler functions aligned with business requirements.
- Design event envelopes, schemas, identifiers, and safe retryable processing flows.
- Combine serverless functions with queues, pub/sub, event buses, and workflow orchestration.
- Control concurrency, execution duration, cold starts, security, and costs.
- Set up observability and test resilience when events arrive duplicated, out of order, or fail processing.

## 1. Event-Driven Architecture with Serverless Functions

In an event-driven architecture, one component emits an event when something has happened; other components subscribe to and react to that event. For example, when a customer uploads an image, the system emits an `ObjectCreated` event. A serverless function receives the event, generates a thumbnail, and saves the result. Another function can update a search index or send a notification without directly modifying the image upload service.

A serverless function is an execution unit whose underlying infrastructure is managed by the platform, invoked on demand by requests or events and typically billed by execution duration, invocation count, or allocated resources. The engineering team focuses on handler code, runtime configuration, access permissions, and operational limits. The platform handles provisioning execution environments, scaling instance counts, and replacing failed instances within the scope of the service.

A typical architecture includes these components:

- **Event producer:** the service or user generating an event, such as an API, object storage, database, or application.
- **Event source:** the source delivering events, such as a queue, stream, event bus, webhook, or service trigger.
- **Router/broker:** filters, routes, or distributes events to one or more consumers.
- **Serverless function:** executes logic in response to events.
- **State store:** persists business state, results, checkpoints, or idempotency keys.
- **Dead-letter queue (DLQ):** holds events that cannot be processed after the retry policy is exhausted.
- **Observability:** captures logs, metrics, traces, and alerts to monitor the end-to-end flow.

Basic processing flow:

1. A business action occurs, such as an order being confirmed.
2. The producer emits an `OrderConfirmed` event with an identifier and required data.
3. The event bus or queue receives the event and applies retention, filtering, and retry policies.
4. The platform invokes the corresponding serverless function.
5. The function validates the event, checks idempotency, and executes side effects.
6. The function durably persists the outcome and then acknowledges processing per the event source's protocol.
7. On transient errors, the event is retried; once limits are exceeded, the event moves to a DLQ for investigation.

An event describes something that has happened, such as `OrderPaid`. A command describes an action to perform, such as `CapturePayment`. Distinguishing the two prevents consumers from misinterpreting an informational event as an instruction to re-execute an action. An event may have multiple independent consumers; a command typically has a single responsible executor.

## 2. When Should You Use Serverless Functions?

Serverless functions are a good fit when work can be divided into independent invocations, execution durations stay within platform limits, and resource demand fluctuates. Common use cases:

- Reacting to object storage events: generating thumbnails, inspecting files, extracting metadata.
- Processing messages: sending emails, updating order statuses, syncing data.
- System integration: receiving webhooks, transforming payloads, calling external APIs.
- Operational automation: scheduled tasks, alert responses, running short maintenance jobs.
- Stream or micro-batch data processing: normalizing records, filtering events, writing to data stores.

Serverless functions are not optimal for every task. Consider containers or long-running workers when:

- Tasks exceed the function's maximum execution duration.
- Continuous background processes, long-lived connections, or heavy native libraries are needed.
- High steady load makes serverless execution more expensive than a well-sized container model.
- Deep control over the OS, runtime, or GPU resources is required.
- Work involves coordinating many long-running, stateful steps with complex compensation; in that case, use workflow orchestration or dedicated workers.

You can combine serverless and containers: a function receives events, validates, and orchestrates; heavy work is pushed to a queue for container workers to process. This keeps the ingestion path lightweight and bounds function execution time.

## 3. Choosing an Event Ingestion Model

Not all event sources share the same delivery mechanics. Choose based on event rate, retention capability, ordering, fan-out, and how consumers acknowledge.

| Model | How It Works | Best Suited For |
|---|---|---|
| Direct trigger | Service invokes the function when an event occurs | Simple events needing low latency where the source has direct integration |
| Queue | Stores messages; consumers pull/receive and acknowledge | Asynchronous processing, burst absorption, retries, and backlog control |
| Pub/sub | One event is distributed to multiple subscriptions | Multiple systems needing to react independently to the same event |
| Event bus | Receives events from multiple sources, filters by rules, and routes to targets | Multi-service integration and decoupling producers from consumers |
| Stream | Stores an ordered sequence of events with partitions and offsets | High throughput, replay, and per-partition ordered processing |
| Webhook | External system sends HTTP requests to an endpoint | SaaS or partner integrations requiring signature verification and retry control |

### 3.1. Direct Triggers

Direct triggers have fewer components, are simple to deploy, and reduce latency. For example, object storage invokes a function when a new file is created. However, you need to understand whether the source retries, whether events can be duplicated, how long events are retained, and what happens when the function is unavailable.

If the event source lacks durable queuing or sufficiently strong replay capability, consider placing a queue or event bus in between for buffering, retry control, and fault isolation.

### 3.2. Queues and Competing Consumers

Queues fit when each task generally needs only one consumer to process it successfully. Multiple instances of the same function can read from a single queue to increase throughput. The broker retains messages during processing while awaiting acknowledgment. If the function fails or the visibility/lease timeout expires, the message can be redelivered.

Queues decouple the producer from knowing how many function instances are running. They also provide backpressure: when consumers slow down, the backlog grows and can be observed, bounded, or drained later. A queue does not solve overload by itself; you still need limits on queue depth, message age, producer rate, and consumer concurrency.

### 3.3. Pub/Sub and Fan-Out

When one event requires multiple independent reactions, use pub/sub or an event bus. For example, `OrderPaid` can be delivered to:

- A function that updates shipping status.
- A function that issues an invoice.
- A function that updates analytics data.
- A function that notifies the customer.

Each subscription can have its own retry policy and DLQ. One failing consumer should not block other consumers from processing if the platform supports independent subscriptions. Fan-out multiplies total invocations and side effects, so you must control costs, access permissions, and duplicate handling in every consumer.

### 3.4. Streams and Ordering

Streams fit when you need to retain event history and process by offset. A partition key typically governs ordering within a partition. For example, using `accountId` as the key ensures events for the same account are processed sequentially within the corresponding partition.

Do not assume global ordering if the platform guarantees ordering only within a partition. If two events relating to the same entity can be processed concurrently, use versions, sequence numbers, or optimistic concurrency to detect stale events.

## 4. Designing Event Envelopes and Schemas

An event envelope is a common metadata wrapper surrounding the business payload. A consistent format lets routers, loggers, schema registries, and consumers handle events uniformly.

Example:

    {
      "specversion": "1.0",
      "id": "evt-8c1f2a",
      "source": "commerce.orders",
      "type": "com.example.order.confirmed.v1",
      "subject": "orders/order-00421",
      "time": "2026-11-22T09:30:00Z",
      "datacontenttype": "application/json",
      "data": {
        "orderId": "order-00421",
        "customerId": "customer-018",
        "total": 1250000,
        "currency": "VND"
      },
      "correlationId": "checkout-req-9d3",
      "traceparent": "00-..."
    }

Key fields:

- **id:** unique identifier of the event; consumers use it for tracking and deduplication.
- **source:** the system or component emitting the event.
- **type:** event type and schema version.
- **subject:** the related business entity, such as an order or account.
- **time:** timestamp when the event was generated, used for latency analysis and stale-event detection.
- **data:** minimal business payload needed by consumers.
- **correlationId:** links events belonging to the same business flow.
- **traceparent:** propagates distributed tracing context if supported.

CloudEvents is a widely adopted specification for event envelopes. You can use an equivalent format if your organization already has an internal standard, but field names, identifiers, timestamps, content types, and versioning must remain consistent.

### 4.1. Versioning and Compatibility

Event schemas evolve over time. If a producer adds a new field, older consumers should ignore unknown fields whenever possible. If a data type changes or a field is removed, older consumers may break.

Design principles:

- Add optional fields in a backward-compatible manner.
- Never change the semantics of an already published field.
- Use explicit versions when introducing breaking changes.
- Maintain a schema registry or CI/CD schema checks when multiple teams collaborate.
- Keep consumers able to read emitted versions throughout the rollout window.
- Test new producers against old consumers and vice versa.

Avoid generic event names like `Updated` for multiple distinct business changes. Names such as `OrderAddressChanged` or `PaymentCaptured` clearly express what happened and let consumers filter accurately.

### 4.2. Small Payloads and Data References

Events should include enough data for consumers to process without excessive service calls. However, large payloads increase transmission, storage, and retry costs; sensitive data is also easily replicated across multiple systems.

For large files or sensitive data, store them in object storage or a controlled data store, then emit a reference containing the object key, version, checksum, and necessary metadata. Consumers verify access permissions, integrity, and reference validity before reading. Avoid placing long-lived privileged URLs in event buses or logs.

## 5. Example Flow Design: Processing Uploaded Images

An application stores original images in object storage. When a file is uploaded, the system needs to validate the file type, generate a thumbnail, save metadata, and emit a completion notification.

Reference architecture:

    Client
      |
      v
    API / Upload service
      |
      v
    Object storage (originals)
      |
      v
    Event bus: ObjectCreated
      |
      +------> Queue: image-processing
      |                |
      |                v
      |          Serverless function
      |                |
      |                +----> Validate / decode
      |                |
      |                +----> Create thumbnail
      |                |
      |                v
      |          Object storage (derived)
      |
      +------> Function: audit metadata
                       |
                       v
                 Metadata database

Workflow:

1. The API issues upload permission or receives the file and saves the original into the `originals` bucket.
2. Storage emits an `ObjectCreated` event.
3. The event bus filters events by bucket and prefix, routing only files in the `originals` area.
4. The `image-processing` queue receives the message and triggers the processing function.
5. The function validates format, size, access permissions, and resource limits.
6. The function creates the thumbnail, writes the derived file, and updates processing status.
7. The function emits `ImageProcessed` or updates status so the frontend can display the result.
8. If processing fails, the queue retries per policy; persistently failing messages move to a DLQ.

Using a queue between the event bus and processing function decouples upload rate from processing rate. If an upload burst produces thousands of files, the queue absorbs the spike and the function scales with the backlog. Set concurrency limits so you do not exhaust CPU, memory, or connections to the metadata store.

One pitfall to avoid is creating an event loop: the function writes the thumbnail back into the same bucket and prefix registered to trigger `ObjectCreated`, causing the thumbnail itself to re-trigger the function. Use a separate bucket/prefix for derived files, filter events by prefix, or inspect the object type before processing.

## 6. Idempotency and Duplicate Event Handling

Many platforms deliver events with at-least-once semantics. An event may be redelivered if a consumer fails to acknowledge in time, times out, or the platform cannot be sure the prior invocation completed. Therefore, a function must be designed to handle the same event multiple times without producing duplicate side effects.

Approach:

1. Use the event `id` or a stable business key as the idempotency key.
2. Record the key in a data store enforcing a unique constraint or conditional write.
3. If the key has already succeeded, skip side effects and return success.
4. If not yet processed, execute the business logic and persist the outcome consistently.
5. Set an idempotency record retention/TTL aligned with retry windows, retention, and replay capability.

Example tracking table:

| event_id | status | processed_at | result_ref |
|---|---|---|---|
| evt-8c1f2a | SUCCEEDED | 2026-11-22T09:31Z | invoice-00421 |
| evt-8c1f2b | RUNNING | 2026-11-22T09:32Z | |
| evt-8c1f2c | FAILED_RETRYABLE | 2026-11-22T09:33Z | |

Performing a read-check followed by a separate write introduces a race condition: two invocations can both see the key missing and both execute side effects. Use unique constraints, conditional puts, transactions, or leased distributed locks so only one invocation wins the right to process. Locks must have an expiration and handle crashed invocations.

For side effects outside your database, such as sending emails or calling a payment gateway, pass an idempotency key to the target service if supported. Otherwise, use outbox/inbox tables, sagas, or reconciliation workflows to handle uncertain states. End-to-end exactly-once semantics cannot be guaranteed merely by configuring function retries.

## 7. Retries, Timeouts, and Dead-Letter Queues

Retries recover from transient errors, but unbounded retries can create error loops and amplify load. Classify errors carefully:

- **Transient:** network timeouts, throttling, unavailable downstream dependencies.
- **Non-retryable without data fixes:** malformed payloads, invalid schemas, missing permissions, or business rule violations.
- **Indeterminate:** invocation timed out after side effects may already have occurred; idempotency must be checked before retrying.

A retry policy should define maximum attempts, wait intervals, backoff, jitter, and maximum event age. Exponential backoff slows down retries when a dependency is degraded:

    delay = min(maxDelay, baseDelay * 2^attempt)
    actualDelay = random(0, delay)

Jitter spreads retry attempts so multiple invocations do not wake up simultaneously and cause a thundering herd. On HTTP 429 or `Retry-After`, respect the delay specified by the target service.

### 7.1. Retries by Event Source

Retry mechanics vary by trigger:

- With queues, messages are typically redelivered if the function fails to acknowledge or throws an error. Visibility timeout/lock duration must cover processing time and may need renewal.
- With event buses, the platform may retry targets over a configured window and attempt count before sending events to a DLQ.
- With streams, consumers may block at the partition or advance offsets depending on commit and error-handling configuration. Prevent a poison-pill record from blocking an entire partition indefinitely.
- With webhooks, endpoints should return appropriate HTTP status codes; the sender needs retries and backoff. Consumers should durably record the request before returning success if processing asynchronously.

Do not apply the same retry policy blindly across all sources. Define clearly which component owns retries: the broker, the function invocation platform, or application code. Avoid stacking unbounded retries across multiple layers, as total attempts can multiply exponentially.

### 7.2. Batches and Partial Failures

Some event source mappings group multiple messages into a single batch to reduce function invocations. If one record fails and the function fails the entire batch, already-succeeded records may be redelivered. Consumers must be idempotent or use partial batch response mechanisms if supported by the platform.

With Amazon SQS and AWS Lambda, you can enable `ReportBatchItemFailures` so the function indicates which specific messages need retrying. Illustrative example:

    def handler(event, context):
        failures = []

        for record in event["Records"]:
            try:
                process_record(record)
            except RetryableError:
                failures.append({
                    "itemIdentifier": record["messageId"]
                })
            except InvalidRecordError:
                quarantine_record(record)
                # Only treat as processed if quarantine write succeeds.

        return {
            "batchItemFailures": failures
        }

If quarantining fails, never silently acknowledge the bad message; let the message retry or apply the appropriate failure policy. For unexpected exceptions, let the invocation fail so the broker applies configured retries. Verify the exact response contract and event source mapping settings for your runtime.

### 7.3. DLQs and Redrive

A DLQ captures events that exceed retry limits so the main pipeline can continue processing healthy events. DLQs require monitoring and an operational procedure:

1. Alert when messages enter the DLQ or when arrival rate crosses a threshold.
2. Categorize by event type, source, schema version, and error.
3. Determine whether the root cause is data, code, permissions, dependencies, or configuration.
4. Fix the root cause and test with a representative message.
5. Redrive in small batches with rate limits while watching for duplicate side effects.
6. Maintain an audit log of replay operations and outcomes.

Never enable continuous automatic redrive before fixing the underlying issue. For sensitive events, enforce approval workflows and authorization checks before replaying.

## 8. Event Ordering and Late-Arriving Events

Events can arrive late or out of order due to retries, network partitions, parallel processing, or latency differences across sources. For example, `OrderShipped` may arrive before `OrderPacked` even though the business actions occurred in the opposite order.

Protective strategies:

- Include a monotonically increasing version or sequence number in events.
- Persist the current state along with the last applied version.
- Apply an event only if its version is newer than the stored state.
- Separate event time from processing time; do not confuse emission time with consumer receipt time.
- Use a stable partition key if per-entity ordering is needed.
- Design consumers to discard stale events or wait for missing events per business rules.

Example order state update:

    if event.version <= order.lastAppliedVersion:
        ignore_as_duplicate_or_stale(event)
    else:
        apply_transition(event)
        order.lastAppliedVersion = event.version

This is illustrative logic only. Under concurrent updates, use optimistic concurrency, transactions, or conditional updates so two invocations cannot overwrite versions simultaneously. When events arrive out of sequence, decide whether the new state can be applied directly or must wait for intermediate transitions.

## 9. Fan-Out, Orchestration, and Sagas

There are two common ways to coordinate multiple functions:

- **Choreography:** components react to events and emit subsequent events. Services stay decoupled, though the end-to-end flow can become hard to trace across many branches.
- **Orchestration:** a workflow coordinates step ordering, timeouts, retries, conditional branches, and state. Suits long-running processes or flows where tracking completed steps is essential.

Example order-processing workflow:

1. `OrderCreated` triggers an inventory-check function.
2. `InventoryReserved` is emitted when stock is successfully held.
3. The payment function receives `InventoryReserved` and calls the payment gateway.
4. `PaymentCaptured` triggers the shipping service.
5. `ShipmentCreated` triggers the customer notification function.

If payment fails after stock is reserved, the system must release the inventory. This is a saga: each step has a compensating action to return the system to a valid state. Do not rely on hypothetical distributed transactions spanning multiple independent services.

When a process has many steps, waits for callbacks, has long timeouts, or needs unified state tracking, use a workflow service such as AWS Step Functions, Google Workflows, or Azure Durable Functions. Serverless functions execute individual steps; the workflow persists state and manages retries/timeouts per its definition. For simple flows, event choreography can be lighter weight.

## 10. Controlling Concurrency and Protecting Dependencies

Serverless functions can automatically scale up many parallel invocations. While beneficial under fluctuating load, this can overwhelm databases, external APIs, or payment gateways if left unconstrained.

Manage:

- **Total concurrency:** limit concurrent invocations per function or account within platform capabilities.
- **Reserved concurrency:** dedicate or cap concurrency for a function on platforms that support it.
- **Provisioned concurrency:** keep execution environments warm to reduce cold starts, at an ongoing cost.
- **Queue batch size:** messages per invocation; larger batches cut overhead but increase processing time and retry blast radius.
- **Event source maximum concurrency:** cap how many consumers poll a queue or stream if supported by the service.
- **Connection pools:** reuse connections across warm runtime invocations, without assuming instances live forever.
- **Rate limits:** throttle dependency calls within target service quotas and SLAs.

For example, if a database supports only 300 connections and each invocation opens a connection, scaling to 500 concurrent invocations can overload the database. Use proper connection pooling, connection proxies, concurrency caps, or queue buffering to smooth traffic.

Do not blindly raise concurrency just to shrink queue depth. Monitor downstream latency, throttling, and errors simultaneously. If a dependency is overloaded, adding invocations makes the problem worse. Lower concurrency, increase backoff, trip circuit breakers, or pause consumers.

## 11. Cold Starts, Execution Duration, and Cost

A cold start occurs when the platform must initialize a new execution environment before running the function. Startup time depends on runtime, package size, libraries, network configuration, and platform resource provisioning. Sudden traffic spikes can trigger many simultaneous cold starts.

Ways to mitigate impact:

- Keep packages and dependencies lean; strip unused libraries.
- Initialize clients outside the handler so warm runtimes reuse them.
- Avoid loading large datasets or running migrations on every invocation.
- Use provisioned/minimum instances when latency requirements are strict and budget permits.
- Choose appropriate runtimes and memory; increasing memory also increases CPU on several platforms.
- Measure p95/p99 latency rather than looking only at averages.

Cost optimization requires a holistic view:

| Factor | Cost Impact |
|---|---|
| Invocation count | Every event or retry can incur an invocation charge |
| Duration and memory | Longer execution or higher memory allocations cost more |
| Event bus/queue | Requests, operations, polling, storage, and data transfer |
| Logging/tracing | Overly verbose logs or long retention drive up storage costs |
| DLQ and replay | Backlogged messages, redrives, and reprocessing consume extra resources |
| Downstream | Databases, APIs, object storage, and network egress can dominate total cost |

A function that is cheap per invocation can still generate high bills if one event triggers many branches, loops on retries, or fires thousands of downstream requests. Measuring cost per business event—such as cost to complete one order or process one file—is more informative than looking at function pricing alone.

## 12. Security and Event Governance

Events can carry business data and trigger high-impact actions. Protect the producer, transport channel, and consumer functions alike.

- Authenticate event sources; for webhooks, verify signatures, timestamps, and prevent replay.
- Use least-privilege IAM/service identities per function.
- Allow a function to read only its designated queues/topics and write only to necessary resources.
- Encrypt data in transit and at rest per platform capabilities.
- Store secrets in a secret manager; never embed credentials in payloads or source code.
- Validate schemas, sizes, and input data before executing side effects.
- Partition data by tenant and verify access permissions inside consumers.
- Restrict permissions to purge queues, delete DLQs, alter rules, and trigger redrives.
- Enable audit logging for configuration changes and operational actions.

Do not trust a payload simply because it arrived via an internal event bus. A compromised producer or misconfigured permission can emit forged events. Consumers still must verify sources, check business state, and deduplicate.

## 13. End-to-End Event Flow Observability

A successful invocation does not mean the business process is complete. Link producers, brokers, functions, and dependencies using event IDs, correlation IDs, and trace context.

Key metrics:

| Group | Metrics | Meaning |
|---|---|---|
| Ingress | Incoming events, publish rate, publish failures | Can producers emit events? |
| Queue | Queue depth, oldest message age, in-flight count | Is backlog growing or breaching SLA? |
| Function | Invocation count, duration, errors, timeouts, throttles, concurrency | Does the function have enough capacity and stability? |
| Reliability | Retries, redeliveries, duplicates, DLQ count | Are events being duplicated or dropped? |
| Dependency | Database latency, connections, API 429/5xx | Are consumers overloading downstream systems? |
| Business | Time from event to completion state, business success rate | Are users receiving results on time? |
| Cost | Cost per invocation and cost per business event | Are costs rising abnormally? |

Logs should include `eventId`, `eventType`, `source`, function version, `attempt`, `correlationId`, and processing outcome. Never log full payloads containing sensitive data. Use distributed tracing to measure time spent in queues, inside function execution, and waiting on dependencies.

Alerts should tie to SLAs: oldest event age exceeding thresholds, growing DLQs, rising timeout rates, sustained function throttling, or end-to-end business completion time missing targets. Alerting on queue depth alone can be noisy if processing throughput is sufficient and messages remain fresh.

## 14. Platform Examples: AWS and Equivalents

An AWS implementation might use Amazon S3 to emit events, Amazon EventBridge to filter and route, Amazon SQS as a buffer, AWS Lambda to process, and DynamoDB to store idempotency records. An SQS DLQ holds messages exceeding allowed receive counts. CloudWatch collects logs and metrics.

Equivalent services on other platforms can include:

| Role | AWS | Google Cloud | Microsoft Azure |
|---|---|---|---|
| Serverless function | AWS Lambda | Cloud Run functions | Azure Functions |
| Event routing | Amazon EventBridge | Eventarc | Azure Event Grid |
| Queue/pub-sub | Amazon SQS, SNS | Pub/Sub | Service Bus |
| Workflow | Step Functions | Workflows | Durable Functions |
| Logs/metrics | CloudWatch | Cloud Logging/Monitoring | Azure Monitor |

Specific naming and features differ. Verify payload limits, timeouts, retries, concurrency, retention, regional availability, and quotas for the service you use. Never assume a service shares identical delivery semantics or limits with an equivalent service on another platform.

Conceptual configuration example for a queue-triggered function:

    Function:
      Runtime: Python
      Timeout: 30 seconds
      Memory: 1024 MB
      ReservedConcurrency: 40

    EventSourceMapping:
      SourceQueue: image-processing
      BatchSize: 5
      ReportBatchItemFailures: true

    Queue:
      VisibilityTimeout: greater than function timeout with safety margin
      Retention: according to business SLA
      RedrivePolicy:
        MaxReceiveCount: 5
        DeadLetterQueue: image-processing-dlq

This is an illustrative configuration, not a complete deployment manifest. Cross-check IaC syntax and service limits. Visibility timeout must be long enough for the function to process the batch and acknowledge; if too short, messages can be redelivered while the prior invocation is still running.

## 15. Design and Deployment Process

You can follow this process when building an event-driven system:

1. **Identify business events:** describe what happened, the producer, and consumers that must react.
2. **Define service requirements:** latency, throughput, ordering, retention, recovery time, and SLAs.
3. **Choose event sources:** direct trigger, queue, pub/sub, event bus, stream, or webhook.
4. **Design event envelopes:** ID, source, type, schema version, timestamp, correlation, and payload.
5. **Design failure paths:** timeouts, retries, backoff, idempotency, DLQs, and redrive.
6. **Design side effects:** transactions, outbox/inbox, conditional writes, or sagas.
7. **Set resource bounds:** memory, timeout, batch size, concurrency, and dependency quotas.
8. **Design security:** identity, least privilege, secrets, encryption, and payload validation.
9. **Set up observability:** structured logs, metrics, traces, dashboards, and SLA-based alerts.
10. **Deploy with IaC:** manage functions, triggers, queues, DLQs, rules, permissions, and alarms in a unified release pipeline.
11. **Test failures and load:** duplicates, out-of-order events, throttling, timeouts, bursts, and dependency outages.
12. **Roll out gradually:** canary or traffic shifting if supported; monitor before ramping traffic.

## 16. Pre-Production Verification Scenarios

Execute in staging:

1. **Valid event:** emit a sample event and confirm the right function runs and the right business state is persisted.
2. **Duplicate event:** resend the same event ID; confirm side effects do not repeat.
3. **Invalid schema event:** send a payload with missing fields or wrong types; confirm controlled rejection or quarantine.
4. **Function timeout:** simulate processing exceeding timeout; confirm retries and idempotency protect outcomes.
5. **Dependency throttling:** make target APIs return 429 or 503; confirm backoff and concurrency caps work.
6. **Partial batch failure:** fail one message in a batch; confirm only the failed message is retried if partial responses are enabled.
7. **DLQ:** force a message past max attempts; confirm the DLQ receives it and alerts fire.
8. **Out-of-order:** send a newer version before an older version; confirm state is not overwritten backward.
9. **Burst:** generate a sudden load spike; measure queue age, function concurrency, throttles, and downstream capacity.
10. **Replay:** replay a set of already-processed events; confirm consumer idempotency and audit trails.
11. **Access control:** attempt to invoke a function or read a queue with an unauthorized identity; confirm denial.
12. **Cost:** measure invocations, duration, queue operations, logs, and downstream requests across a representative event volume.

Record results, recovery times, and discovered limits. Increase production traffic only when metrics are within SLO and the DLQ has designated operational ownership.

## 17. Common Incidents and Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Function is not invoked | Wrong trigger, missing permissions, or non-matching rule | Inspect event source, rule filters, permissions, and ingress metrics |
| Function invoked multiple times | At-least-once delivery, timeout, or ack failure | Check event ID, idempotency store, retries, and visibility timeout |
| Queue backlog growing | Slow consumer, low concurrency, or failing dependency | Compare arrival rate, processing rate, duration, and downstream latency |
| Function throttling | Concurrency hitting limit or account quota | Check reserved/max concurrency, account quotas, and event source scaling |
| DLQ growing rapidly | Bad payloads, incompatible schemas, or prolonged dependency outage | Classify errors, verify producer version, and halt automatic redrive |
| Cold starts inflating latency | Heavy runtime/package or no warm instances | Measure init duration, trim packages, and consider provisioned/min instances |
| Events processed out of order | Concurrent consumers or source lacks global ordering | Inspect partition keys, versions, and conditional updates |
| Unusual cost spike | Broad fan-out, retry loops, excessive logging, or huge payloads | Break down cost by event type, retries, invocations, and downstream calls |
| Infinite trigger loop | Function writes objects back to the triggered bucket/prefix | Check event filters and separate input/output storage paths |
| Function succeeds but business action incomplete | Ack before commit or logging without persisting state | Verify transactions, job state, and ack timing |

## 18. Design Checklist

- [ ] Each event describes a business occurrence with a clear source and type.
- [ ] Event envelope contains ID, schema version, timestamp, and correlation/trace context.
- [ ] Queue, pub/sub, event bus, or stream is chosen according to delivery and ordering requirements.
- [ ] Delivery semantics are identified and consumer idempotency is designed.
- [ ] Outcomes are durably persisted before acknowledging messages.
- [ ] Timeouts, retries, backoff, jitter, DLQs, and redrive are configured.
- [ ] Partial batch failures are handled when the source supports batching.
- [ ] Strategies exist for versioning, late events, and out-of-order delivery.
- [ ] Concurrency, batch size, and load on dependencies are bounded.
- [ ] Outbox/inbox or sagas are used when multiple systems and side effects are involved.
- [ ] IAM, secrets, encryption, and source validation are properly managed.
- [ ] Queue age, duration, errors, throttles, DLQs, and business latency are monitored.
- [ ] Duplicates, timeouts, bursts, replays, out-of-order events, and dependency outages are tested.
- [ ] Configuration is managed via IaC with a release/rollback process.
- [ ] Cost per business event is measured with budget alerts configured.

## Conclusion

Event-driven systems built on serverless functions decouple producers from consumers, scale on demand, and reduce server maintenance overhead. Reliability hinges on choosing the right event source, designing stable schemas, handling duplicates, configuring bounded retries and DLQs, and persisting results before acknowledgment. Concurrency must align with database and downstream API capacities; observability must connect event IDs from emission through business completion. Always test error cases, duplicates, out-of-order arrivals, and traffic spikes before promoting the architecture to production.
