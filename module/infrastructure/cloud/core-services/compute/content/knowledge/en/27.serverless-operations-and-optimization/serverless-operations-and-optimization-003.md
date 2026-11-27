# Timeouts, Retries, Backoff, and Handling Duplicate Events

## 1. Why Does Serverless Require Timeout and Retry Management?

Serverless applications are typically triggered by HTTP requests, queue messages, object storage events, schedules, or calls from other services. The platform can automatically spin up an execution environment, invoke the function, and reclaim resources after processing. This model reduces server management, but it does not eliminate network errors, slow dependencies, execution duration limits, or an event being delivered multiple times.

A function may complete its business logic yet lose connectivity before sending back its acknowledgment. The event-emitting system does not know whether the function finished and may resend the event. A function may receive the same message twice due to at-least-once delivery, timeouts, expired visibility timeouts, or caller-side retries. If the second execution creates an order or charges a customer again, users suffer duplicate side effects even though neither execution reported an error.

Therefore, serverless operations require coordinating four mechanisms:

- **Timeouts and deadlines:** bounding the duration of functions, requests, and dependency calls.
- **Retries:** deciding which errors are retried, where retries happen, and the maximum number of attempts.
- **Backoff and jitter:** spacing out attempts to avoid piling load onto a failing dependency.
- **Idempotency and deduplication:** ensuring reprocessing the same event does not produce additional business side effects.

These mechanisms must be designed together with queues, event sources, databases, external APIs, and SLOs. Simply increasing timeouts or enabling retries does not automatically make a system more reliable; misconfiguration can prolong hung requests, trigger retry storms, or duplicate transactions.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this topic connects directly to serverless operations and optimization: functions must process events within compute limits, connect to dependencies efficiently, withstand fluctuating load, and control costs when failures occur.

After this lesson, learners will be able to:

- Distinguish function, request, queue visibility, and dependency timeouts.
- Establish overall deadlines and allocate a timeout budget across steps.
- Distinguish retries performed by callers, invocation platforms, and event sources.
- Choose exponential backoff, caps, jitter, retry budgets, and attempt limits.
- Explain why events can be delivered multiple times and why idempotency is required.
- Design idempotency keys, deduplication stores, and atomic processing alongside business state changes.
- Use DLQs, redrives, and safe replays.
- Monitor retries, timeouts, duplicates, message age, and cost.
- Test failure scenarios, race conditions, and out-of-order events.

## 2. Timeouts, Deadlines, and Processing Time

### 2.1. A Timeout Is a Limit on a Single Operation

A timeout defines the maximum time an operation is allowed to wait. When the time expires, the caller or runtime stops waiting and returns an error or cancels the operation according to protocol capabilities.

A serverless flow may involve multiple independent timeouts:

- Client or API gateway timeout.
- Synchronous function invocation timeout.
- Maximum execution duration of the function.
- Connection timeout for databases, caches, or HTTP APIs.
- Storage read/write operation timeout.
- Message visibility timeout or lease duration.
- Business deadline, e.g., an order must be confirmed within 30 seconds.

These timeouts do not align automatically. A client may give up before the function finishes; a function may be terminated by the runtime before the database commits; a message may be redelivered while a worker is still processing if the visibility timeout is too short.

### 2.2. Overall Deadline

A deadline is the final point in time by which the entire unit of work remains valid or is permitted to complete. Unlike an individual timeout, a deadline spans the whole chain of steps, including queuing time, startup, processing, dependency calls, and retries.

For example, an API must return a result within 8 seconds. If the gateway times out at 8 seconds while the function timeout is 30 seconds, the function may keep running after the client has given up. If the function continues writing data or calling a payment service, the caller may retry and create duplicate effects.

Good design propagates the deadline or remaining time budget across layers. Each dependency receives a timeout smaller than the remaining budget so the function still has time to handle errors and return a response before the deadline.

### 2.3. Timeout Budget

Suppose the overall deadline is \(T_{total}\), initialization/coordination overhead is \(T_{overhead}\), and there are processing steps with budgets \(T_1, T_2, \ldots, T_n\). The following must hold:

\[
T_{overhead} + \sum_{i=1}^{n} T_i \leq T_{total}
\]

Allocating the entire deadline to each individual dependency can cause total duration to exceed the limit. For instance, a function with a 10-second deadline calls a database, payment API, and email API sequentially. Setting an 8-second timeout on each call makes it impossible to guarantee completion within 10 seconds.

An illustrative budget breakdown:

| Stage | Budget |
|---|---:|
| Parse/validate and overhead | 0.5 seconds |
| Database read/write | 2 seconds |
| External API | 3 seconds |
| Commit state and response | 1 second |
| Error handling/serialization reserve | 1 second |
| Total | 7.5 seconds |

The margin below the deadline provides headroom for variance. Actual numbers should be derived from observed latency percentiles and real business requirements.

### 2.4. Setting Timeouts Based on Measured Latency

Do not pick timeouts by guesswork. Measure p50, p95, p99, and tail latency of dependencies under normal load, peak load, and degraded conditions. Timeouts that are too short trigger false errors and unnecessary retries; timeouts that are too long tie up execution environments, connections, and concurrency unproductively.

Guidelines:

- Connect timeouts are typically shorter than overall request timeouts.
- Read/write timeouts must match payload sizes and throughput.
- A dependency timeout should be smaller than the function's remaining time.
- Function timeouts must cover legitimate work without exceeding the business deadline.
- Queue visibility timeouts or leases must cover expected processing time plus renewal mechanisms if available.

### 2.5. A Timeout Does Not Mean the Operation Was Canceled

When a client times out, the server or dependency may still be executing the operation. For example, a function sends a transaction creation request to a payment API, but the connection drops before the response arrives. It is unknown whether the transaction was created.

This is an unknown-outcome state. Do not immediately send a new request to create the transaction again. Use a stable idempotency key to query or safely repeat the same operation. With databases, verify whether the transaction committed or rolled back by reading state using the business key.

## 3. Timeouts Across Serverless Invocation Models

### 3.1. Synchronous Invocation

In synchronous invocations, the caller waits for the function's result. Timeouts can occur at the client, gateway, SDK, and runtime. The smallest limit in the chain determines how long the caller will wait.

If the client times out while the function keeps running, the caller may resend the request. Therefore, APIs that create data or process payments must support idempotency even when the caller never receives the response.

### 3.2. Asynchronous Invocation

In asynchronous invocations, the caller submits an event and does not wait directly for the function's result. The platform may persist the event, retry execution according to a retry policy, and send failed events to a destination or DLQ if configured.

Retry policies and attempt counts vary by platform, event type, and configuration. Clarify who owns retries: the calling service, the serverless platform, or the event source. Never assume all asynchronous invocations share the same retry count or event retention period.

### 3.3. Queue/Event Source Mapping

With queues, an event source mapping typically polls messages and invokes the function in batches. If the function fails, messages may return to the queue after the visibility timeout or equivalent mechanism. Partial batch responses may need to be configured so only failed messages are retried rather than the entire batch.

For standard queues, ordering is not necessarily guaranteed and messages may be delivered more than once. For FIFO queues, ordering within a message group and deduplication follow specific rules; application-level idempotency is still required because retries or timeouts can create uncertain states in external systems.

### 3.4. Object Storage, Schedule, and Stream Events

Object storage events, schedulers, and streams may replay events when a consumer fails or a checkpoint is not committed. Events may carry an object key, version, sequence number, or event ID. Use these fields as inputs for idempotency/deduplication when semantics fit.

Never assume events always arrive exactly once or in exact order. If business logic depends on ordering, use sequence/version numbers, state machines, or dedicated ordering mechanisms.

### 3.5. Comparison Table

| Trigger Type | Caller Waits for Response? | Typical Retry Source | Key Design Considerations |
|---|---|---|---|
| Synchronous HTTP/API | Yes | Client, SDK, gateway, or caller | Deadlines, unknown responses, idempotency keys |
| Asynchronous invocation | Does not wait for final result | Invocation platform or destination | Retry policy, event age, failure destination/DLQ |
| Queue polling | Does not wait for original client | Queue visibility/redelivery and event source mapping | Visibility timeout, batch failure, ack/delete, DLQ |
| Stream | Consumer processes per shard/partition | Replay from checkpoint or offset | Checkpoints, ordering, batch retries, and poison records |
| Scheduled event | Does not wait for user | Scheduler/event delivery policy | Event ID, missed schedules, duplicate runs, and idempotency |

This is a high-level classification. Always verify the actual semantics of your cloud provider and event source.

## 4. Retries: When Should You Retry?

### 4.1. Retries Are Not a Cure for Every Failure

Retries help with transient errors such as brief network timeouts, connection resets, temporary throttling, or a restarting dependency. Retries do not fix bad data, validation errors, wrong permissions, or deterministic bugs.

Classify errors before retrying:

| Error Category | Examples | Appropriate Action |
|---|---|---|
| Transient | Connection reset, brief DNS timeout | Retry with backoff and limits |
| Throttling | HTTP 429, temporary quota exhaustion | Honor `Retry-After`, slow down |
| Dependency unavailable | HTTP 503, database failover | Backoff, circuit breaker, retry budget |
| Unknown-outcome timeout | Payment sent but response lost | Query via idempotency key before deciding |
| Permanent/business error | Invalid input, closed account | Do not retry; return error or route to business handling |
| Authorization/configuration | `AccessDenied`, wrong endpoint | Do not keep retrying; fix config/permissions |
| Poison event | Unparseable payload | Quarantine, send to DLQ, and investigate |

### 4.2. Retry at the Right Layer

A single request can be retried across multiple layers: client, API gateway, SDK, function wrapper, event source, and downstream service. If every layer retries multiple times independently, total calls can multiply rapidly.

For example, 3 client retries, 4 function SDK retries, and 5 event source redeliveries can produce up to 60 downstream executions in the worst case, depending on how layers nest. Designate one primary layer responsible for retries and enforce an overall limit across the end-to-end flow.

### 4.3. Retry Only Safe Operations

Before retrying, determine whether the operation is idempotent. Reads are usually safe to retry; writes or transaction-creating API calls require idempotency keys or transaction semantics. If a timeout leaves the outcome uncertain, inspect state before resending.

### 4.4. Retry Budgets

A retry budget caps the number or percentage of requests permitted to retry over a time window. When errors spike, exhausting the budget stops the system from amplifying load further. Budgets can be scoped per service, dependency, tenant, or operation.

A policy might allow at most 2 retries per request and cap total retries at 5% of requests in a window. Thresholds must align with SLOs rather than acting as universal defaults for every system.

### 4.5. Do Not Retry Permanent Errors

Validation failures, schema mismatches, missing business entities, or denied permissions typically require fixing data or configuration. Retrying only increases invocation and logging costs. Classify error codes and response bodies deliberately; avoid blindly retrying every HTTP 4xx or generic exception.

## 5. Exponential Backoff and Jitter

### 5.1. Exponential Backoff

Exponential backoff increases the wait time between retry attempts. A basic model:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Where:

- \(d_0\): initial wait time.
- \(n\): number of retries already attempted, starting from 0.
- \(d_{max}\): maximum cap on wait time.
- \(d_n\): wait time before the next retry attempt.

For example, with a 0.5-second base delay and an 8-second cap, the unjittered delay sequence is 0.5, 1, 2, 4, 8, 8 seconds. The cap prevents wait times from growing unboundedly.

### 5.2. Why Is Jitter Needed?

If thousands of functions encounter the same error and all retry after 1, 2, and 4 seconds, they send requests almost simultaneously. This creates a thundering herd that overwhelms a recovering dependency all over again.

Jitter adds randomness to wait times to spread out attempts. One form is full jitter:

\[
d_n = U(0, \min(d_{max}, d_0 \times 2^n))
\]

Where \(U(0,x)\) is a uniform random value between 0 and \(x\). Several jitter variants exist; choose based on your library or system standard and verify the actual implementation.

### 5.3. Honoring Retry-After

If a downstream service returns `Retry-After`, treat it as a wait hint or minimum delay per the API's semantics. Combine it with jitter so multiple callers do not wake up simultaneously. If the requested delay exceeds the business deadline, stop retrying and transition to a waiting state or fail gracefully.

### 5.4. Bounding Both Attempts and Total Duration

Retries need both `maxAttempts` and an overall deadline. Limiting attempts alone is insufficient if each wait is long; limiting total time alone is insufficient if retries fire in tight bursts. Track attempt counts, total elapsed time, and cost.

### 5.5. Delay Calculation Example

```python
import random

def retry_delay(attempt, base_seconds=0.5, cap_seconds=20.0):
    upper = min(cap_seconds, base_seconds * (2 ** attempt))
    return random.uniform(0.0, upper)
```

The function above illustrates full jitter. In production, cap attempts, guard against overflow for very large attempt numbers, respect deadlines and `Retry-After`, and apply a retry budget. Never let a retry loop run past the function's maximum execution duration.

## 6. Timeout Budgets During Retries

### 6.1. Total Duration of a Retry Sequence

Suppose each attempt has timeout \(t_i\), delays between attempts are \(d_i\), and there are \(A\) attempts. Approximate total duration:

\[
T_{retry} = \sum_{i=1}^{A} t_i + \sum_{i=1}^{A-1} d_i
\]

You must ensure:

\[
T_{retry} + T_{cleanup} + T_{response} \leq T_{remaining}
\]

If insufficient time remains, do not start a new retry attempt. Save necessary state and let the event source or scheduler retry later, or return a retryable response to the caller.

### 6.2. Deadline Example

A function has 6 seconds remaining. A dependency call has a 1.5-second timeout; the policy allows up to 3 attempts with 0.5-second and 1-second delays. The approximate worst-case duration is:

\[
3 \times 1.5 + 0.5 + 1 = 6 \text{ seconds}
\]

This excludes parsing, cleanup, and logging. Therefore, this policy does not fit if the function must return a response within 6 seconds. Reduce attempts, lower per-attempt timeouts, move processing to an asynchronous flow, or let the caller/event source retry at a later time.

### 6.3. Propagate Deadlines Instead of Fixed Timeouts

When a function calls multiple services, propagate an absolute deadline or remaining time rather than setting independent fixed timeouts for each service. Each client computes remaining time before sending a request. When the budget is nearly exhausted, skip non-essential steps or fail gracefully.

### 6.4. Operation Cancellation

Some runtimes/clients support cancellation tokens or abort signals. When a function nears its deadline, cancel in-flight downstream calls where supported to avoid wasting resources. However, cancellation does not guarantee the remote operation rolled back. For write operations, idempotency and state checks are still required.

## 7. Why Are Events Delivered Multiple Times?

### 7.1. At-Least-Once Delivery

Many queue/event systems target at-least-once delivery: events are retained until the consumer acknowledges or checkpoints them. If the consumer finishes processing but the ACK is lost, the event source may redeliver the event. This prioritizes zero event loss at the cost of potential duplicate deliveries.

"At least once" does not mean an event is guaranteed to succeed; it means the system may redeliver according to policy until completion criteria are met or retention/retry limits expire. Exact semantics depend on the event source.

### 7.2. Common Causes

- The function finishes business logic but times out before the ACK/response is recorded.
- The runtime or worker is terminated after writing partial data.
- Visibility timeout expires before the function completes.
- One failed record in a batch causes the entire batch to be redelivered.
- The event source retries after a transient error.
- The caller resends a request after receiving no response.
- The scheduler fires the same schedule due to retries or catch-up runs.
- Operators redrive messages from a DLQ multiple times.
- A stream consumer replays from an older checkpoint.
- An event producer republishes because a transaction/outbox was not marked completed.

### 7.3. Duplicates Do Not Necessarily Arrive Close Together

Two copies of an event may arrive milliseconds apart or hours/days apart. Deduplication must retain keys long enough relative to retry windows, retention, redrives, and replays. A TTL that is too short allows an old event to be reprocessed after its key expires.

### 7.4. Duplicate and Out-of-Order Events Are Different Problems

Idempotency prevents repeated effects of the same event. It does not by itself solve out-of-order events. For example, `OrderPaid` may arrive before `OrderCreated` across two separate processing paths. Sequence/version numbers, valid state transitions, or per-aggregate event buffering are needed when order matters.

## 8. Idempotency and Deduplication

### 8.1. Idempotent Operations

An idempotent operation can be executed multiple times with the same identifier/input while leaving the final business state equivalent to executing it once.

Examples:

- Setting an order's status to `PAID` for the same payment ID.
- Writing a partition's output under a deterministic key.
- Creating a resource with a client-supplied idempotency key and returning the existing result.
- Upserting a record by business key with deterministic update rules.

An operation that increments a balance by 100 on every call is not idempotent. Changing it to "record transaction ID X if it does not yet exist, then derive balance from the ledger" makes retries safer when executed inside a transaction.

### 8.2. Idempotency Keys

An idempotency key is a stable identifier for a business request. It can be derived from:

- An event ID issued by the producer.
- A message ID if event source semantics guarantee stability across redeliveries.
- A business transaction ID or order ID combined with operation type.
- A client-generated request ID preserved across retries.
- Object key + version ID + event type for object storage events.

Do not generate a new UUID on every retry of the same operation; doing so treats each attempt as a brand-new request. Also avoid blindly hashing payloads if two legitimate distinct business events can have identical payloads.

### 8.3. Deduplication Store

A dedupe store records keys that have been processed or are in progress, along with status and outcome. It can be implemented using a database, conditional writes, unique constraints, or a key-value store supporting atomic operations.

A record may contain:

| Field | Meaning |
|---|---|
| `idempotency_key` | Unique key of the operation |
| `status` | `IN_PROGRESS`, `COMPLETED`, or a retryable error state |
| `request_hash` | Detects same key reused with a different payload |
| `result_ref` | Reference to the created outcome |
| `created_at` | Start timestamp |
| `expires_at` | Key retention expiration timestamp |
| `owner/lease` | Currently processing worker or lease if needed |

### 8.4. Key Checking and Writing Must Be Atomic

Unsafe pattern:

1. Read the dedupe store and observe the key does not exist.
2. Create the order.
3. Write the processed key.

If the function crashes after step 2 and before step 3, the event is redelivered and the order is created a second time.

A safer pattern uses a unique constraint/conditional insert so only one worker claims the key, then commits business changes and idempotency state in the same transaction when both live in the same database. If side effects happen in external systems outside the transaction, use an outbox/inbox pattern, downstream idempotency APIs, or a reconcilable state machine.

### 8.5. Handling the Same Key with a Different Payload

If the same idempotency key arrives with a different request hash, do not silently return the prior result. This indicates a caller bug or key collision. Reject with a clear error, log with the correlation ID, and investigate.

### 8.6. TTL and Key Retention Period

The TTL must exceed the window over which an event can be retried, redriven, or replayed. Account for queue retention, DLQ retention, retry schedules, operator redrive windows, and business rules.

If permanent duplicate protection is required for financial transactions, do not rely on a short TTL; use a business transaction ID/ledger with a unique constraint or long-term retention policy. A dedupe cache can accelerate lookups, but should not be the sole source of truth if cache loss would permit duplicate transactions.

## 9. Idempotent Processing Examples

### 9.1. SQL Pattern with Unique Constraint

Suppose an application receives payment events carrying `payment_event_id`. You can create an inbox table:

```sql
CREATE TABLE processed_events (
    event_id        VARCHAR(200) PRIMARY KEY,
    request_hash    VARCHAR(128) NOT NULL,
    processed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Inside a transaction:

```sql
BEGIN;

INSERT INTO processed_events (event_id, request_hash)
VALUES (:event_id, :request_hash)
ON CONFLICT (event_id) DO NOTHING;

-- Application checks the number of inserted rows.
-- Only the worker that wins the insert performs the business update.
UPDATE orders
SET payment_status = 'PAID'
WHERE order_id = :order_id
  AND payment_status <> 'PAID';

COMMIT;
```

This is a sketch; logic must check the insert row count and payload hash before updating. If the event already exists with the same hash, return the already-processed result. If the same key has a different hash, route to the conflict branch. The inbox insert and order update must share the same transaction to eliminate a crash window between the two operations.

### 9.2. State Machine for Multi-Step Workflows

For business logic with multiple side effects, persist explicit states:

```text
RECEIVED -> VALIDATED -> PAYMENT_REQUESTED -> PAYMENT_CONFIRMED -> COMPLETED
                  |              |
                  v              v
               REJECTED       UNKNOWN
```

`UNKNOWN` represents a timeout calling the payment API where it is unclear whether the transaction succeeded. The worker must query downstream using the idempotency key or payment reference before issuing a new command.

The state machine should define valid transitions, retryable states, terminal states, and reconciliation steps when a step's outcome cannot be determined.

### 9.3. Idempotency Keys for HTTP APIs

The client sends a stable `Idempotency-Key` header for an order-creation operation. The server stores the key along with the request hash and response. If the client retries after a timeout, the server returns the stored response instead of creating a new order.

```http
POST /orders
Idempotency-Key: order-create-7f3a...
Content-Type: application/json
```

The key must remain identical across all retries of the same operation. The server should scope the key, for example by tenant/account and operation, to prevent cross-user collisions.

### 9.4. Idempotency Does Not Replace Authorization

When returning a stored result, still verify that the current caller is authorized to view that resource. Never allow an idempotency key to expose another tenant's results. Dedupe keys should be scoped by tenant or principal as appropriate.

## 10. Batch Processing and Message Queues

### 10.1. Why Does Batching Make Duplicates Harder?

A function may receive multiple messages in a single batch. If 9 messages succeed and the 10th fails, some event sources redeliver the entire batch. The first 9 messages will run again even though they already completed.

Idempotency must be enforced per message, not only at the batch level. When the event source supports partial batch responses, return only the failed records to reduce duplicate executions.

### 10.2. Partial Batch Failure

With queues/event source mappings supporting partial batch responses, the function can report a list of failed message IDs. The event source redelivers only those records according to its supported semantics.

Logic example:

```python
def handler(records):
    failures = []
    for record in records:
        try:
            process_idempotently(record)
        except RetryableError:
            failures.append({"itemIdentifier": record["messageId"]})
        except PermanentError:
            send_to_failure_store(record)
    return {"batchItemFailures": failures}
```

This is pseudocode modeled on a common response shape; exact field names and how partial batch responses are enabled depend on the platform/event source. Permanent errors must be recorded or routed to a DLQ per policy—never silently dropped.

### 10.3. Visibility Timeout

In queues with visibility timeouts, a received message becomes temporarily hidden from other consumers. If the function has not finished when the visibility timeout expires, the message can be redelivered while the first execution is still running.

Set the visibility timeout longer than the expected maximum processing duration, plus headroom for batching and overhead. If processing may run longer, use visibility/lease extension mechanisms when supported. Do not set it excessively long if doing so delays recovery when a worker crashes.

### 10.4. Batch Size and Concurrency

Large batches reduce invocation overhead but increase processing time and retry blast radius on failure. High concurrency boosts throughput but increases simultaneous requests to dependencies and duplicate risk when multiple leases expire.

Tune batch size, maximum concurrency, and timeouts together. Check dependency connection pools, API rate limits, and p99 processing duration.

### 10.5. FIFO and Ordering

FIFO queues or message groups can preserve ordering within a defined scope, yet consumers must still handle duplicates. A single failing message may block subsequent messages in the same group depending on semantics. DLQ/redrive designs must account for restoring order and preventing one poison message from blocking an entire group indefinitely.

## 11. Dead-Letter Queues and Redrives

### 11.1. What Is a DLQ?

A dead-letter queue (DLQ) or failure destination stores events that could not be processed after a configured number of attempts or age threshold. It isolates failing messages from the main flow for later investigation and remediation.

A DLQ is not a place to dump messages and forget them. Monitor message counts, message age, error types, ownership, and recovery procedures.

### 11.2. Distinguishing Retryable vs. Poison Messages

Retryable messages can succeed once a dependency recovers. Poison messages always fail due to invalid payloads/schemas, missing prerequisite data, or deterministic bugs. Retrying poison messages repeatedly only wastes money and delays healthy messages.

Use max receive counts or max retry attempts to move messages to the DLQ. Thresholds should match failure modes, dependency recovery times, and retention windows.

### 11.3. Safe Redrives

Before redriving:

1. Confirm the root cause has been fixed.
2. Verify payloads and schemas are still valid.
3. Check whether event IDs/idempotency keys are preserved.
4. Inspect business state to avoid creating duplicate effects.
5. Rate-limit the redrive so dependencies are not overwhelmed.
6. Monitor outcomes, retry counts, and messages returning to the DLQ.

Do not generate new event IDs during redrive if the goal is to resume the same business operation. If a new business operation must be initiated, assign a new ID and audit the reason clearly.

### 11.4. DLQ Retention and Access Control

DLQs may contain sensitive data or malformed payloads. Restrict read access, encrypt at rest, configure retention, and audit access. Never dump full payloads into public logs; use correlation IDs and sanitized fields.

## 12. Retry Storms, Circuit Breakers, and Backpressure

### 12.1. Retry Storms

A retry storm happens when many clients/functions simultaneously retry a failing dependency. Request volume can grow faster than the service can recover. Functions holding concurrency while waiting drive up queue backlogs and invocation costs.

Warning signs:

- Both retry rates and timeouts rise simultaneously.
- Downstream 429/5xx responses spike.
- p95/p99 latency climbs while successful throughput drops.
- Queue age and in-flight message counts grow.
- Function concurrency hits its limit while completed work stalls.

### 12.2. Circuit Breakers

A circuit breaker tracks dependency error/timeout rates. Once a threshold is crossed, the breaker opens and rejects or delays new calls for a cooldown period. Afterward, it enters half-open state to probe with a limited number of requests; if those succeed, it closes again.

Circuit breakers relieve pressure on failing dependencies, but they do not replace retry policies, timeouts, or idempotency. Avoid letting each execution environment track isolated breaker state with no awareness of total concurrency; a gateway or shared state mechanism may be needed.

### 12.3. Backpressure

Backpressure slows upstream work when downstream systems cannot accept more load. In serverless architectures, you can cap event source concurrency, reserved concurrency, queue consumer rates, or admission rates. Depending on the platform, reserved concurrency caps overall function scale but does not replace per-dependency rate limiting.

If a queue backlog grows due to downstream throttling, increasing function concurrency usually makes things worse. Keep backlogs within retention limits, lower consumer rates, and alert on message age.

### 12.4. Load Shedding

When deadlines are nearly exhausted or dependencies are saturated, shed low-priority requests early, return guided retryable errors, or offload work to queues. Do not accept additional work if the system cannot process it within business deadlines.

### 12.5. Combining Retry Budgets with Circuit Breakers

Retry budgets cap total retry effort; circuit breakers halt calls to dependencies during sustained outages. When a breaker is open, do not burn retry budget on doomed attempts. When half-open, allow only a small number of probe requests to test recovery.

## 13. Optimizing Timeouts and Retries for Performance and Cost

### 13.1. Cost of an Invocation

Each retry adds invocation duration, dependency requests, logs, network transfer, and storage operations. A function with a long timeout that frequently waits on dependencies holds concurrency longer and inflates costs.

Evaluate for optimization:

- Execution duration and billed duration by runtime.
- Invocations/retries per event.
- Cold starts and initialization time.
- Memory/CPU allocation and throughput.
- Queue wait time, message age, and concurrency.
- Dependency request counts and throttling.
- DLQ/redrive and storage costs.

### 13.2. Do Not Mask Bugs with Excessive Timeouts

Long timeouts help legitimate long jobs finish, but they also tie up resources on hung requests and delay message recovery. Split long tasks into workflows/queues or break jobs down when appropriate. Choose timeouts based on actual duration distributions and deadlines, not merely platform maximums.

### 13.3. Reusing Connections and Clients

Reusing SDK clients and connection pools within an execution environment reduces setup time. However, serverless environments can be frozen or reclaimed, causing connections to expire. Validate connections before use, set idle timeouts, and reconnect safely.

Avoid opening a new connection per request when reuse is possible, while ensuring total connections during scale-out stay within database limits. Use proxies/poolers or concurrency caps where needed.

### 13.4. Right-Sizing Payloads and Batches

Large payloads increase serialization, transfer, and parsing time. For file/object events, pass references and version IDs instead of embedding full data. Batching reduces invocation overhead, but balance it against processing time, retry scope, and memory usage.

### 13.5. Optimizing Bounded Concurrency

Higher concurrency does not always increase throughput. When downstream services saturate, extra concurrency only increases wait times, timeouts, and duplicates. Determine safe concurrency through load testing, then enforce limits per function and dependency.

## 14. Observing Timeouts, Retries, and Duplicates

### 14.1. Essential Metrics

- Invocation count, success/error rates, timeouts, and duration p50/p95/p99.
- Retry attempts per event and retry rates by dependency.
- Function concurrency, throttled invocations, and execution environment initializations.
- Queue depth, age of oldest message, in-flight count, and receive count.
- Duplicate event count and idempotency hits/misses/conflicts.
- DLQ depth, DLQ age, and redrive success/failure rates.
- Downstream latency, 429/5xx rates, connection pool wait times, and circuit breaker states.
- Invocation/duration cost and dependency cost per completed event.

### 14.2. Logs with Correlation IDs

Logs should contain event IDs, masked or hashed idempotency keys, request IDs, trace IDs, attempt numbers, function versions, dependency names, and outcomes. Never log tokens, passwords, payment details, or full sensitive payloads.

Correlation IDs tie an event together across multiple invocations and distinguish retries from brand-new business events.

### 14.3. Distinguishing Retries from Business Duplicates

Retry attempt counts show attempts within a single delivery chain; duplicate business events are identified via idempotency keys. The two concepts are not always identical: a message can be redelivered after retry metadata is lost or via a separate replay pipeline.

### 14.4. Impact-Based Alerting

Prioritize alerts for:

- Timeout rate breaching SLO.
- Retry rate spiking while success rate drops.
- Age of oldest message exceeding deadline.
- New messages entering the DLQ or rapid DLQ growth.
- Idempotency conflicts occurring.
- Duplicate side effects detected.
- Dependency circuit breakers remaining open for prolonged periods.
- Function concurrency hitting caps while backlogs keep growing.

Do not alert solely on rising invocation counts; that may be legitimate traffic. Correlate with errors, latency, and completed work.

## 15. Testing Reliability

### 15.1. Timeout Testing

Test dependencies responding slower than timeouts, hanging indefinitely, dropping connections mid-stream, and responding after the caller deadline expires. Verify the function stops causing unintended side effects after timing out.

### 15.2. Duplicate Testing

Send the same event ID multiple times both concurrently and sequentially. Verify only one business change commits, subsequent calls return stable results, and reusing the same key with a different payload is rejected.

### 15.3. Crash Window Testing

Deliberately terminate functions at critical points:

- Before writing the dedupe key.
- After claiming the key but before business execution.
- After committing business logic but before ACK.
- After calling downstream but before persisting the outcome.
- While writing a checkpoint or updating state.

Verify that redeliveries recover or reconcile cleanly without creating duplicate side effects.

### 15.4. Retry Storm Testing

Have dependencies return 429/503 or inject high latency for a sustained interval. Verify backoff+jitter spreads requests, retry budgets cap total attempts, circuit breakers open, and concurrency stays within protective bounds.

### 15.5. DLQ and Redrive Testing

Send a poison message to the DLQ, fix the root cause, and redrive a small batch. Verify idempotency keys are preserved, redrive rate is throttled, and messages do not bounce back to the DLQ endlessly.

## 16. Practical Examples

### Example 1: Order Creation API Retried by Client After Timeout

A client calls `POST /orders`. The function creates the order in the database, but the response is lost when the API gateway times out. The client resends the request and the function creates a second order.

**Cause:** the system does not distinguish a retry of the same operation from a new order request.

**Redesign:** the client sends a stable `Idempotency-Key`; the server stores the key and request hash with a unique constraint. Order creation and recording the idempotency result share the same transaction. On repeat requests, the server returns the stored result; if the payload differs for the same key, it returns a conflict error.

**Verification:** simulate losing the response after commit and resend the same key multiple times; verify only one order is created.

### Example 2: Queue Worker Times Out and Message Is Redelivered

A function takes 90 seconds to process a message, while the queue visibility timeout is only 60 seconds. The message becomes visible again before the first function finishes; a second worker picks up the same message.

**Cause:** lease/visibility timeout is shorter than processing time without renewal, and the business operation is not idempotent.

**Redesign:** adjust visibility timeout to p99 duration plus headroom; use heartbeat/extension if supported by the platform; persist an idempotency key based on message ID or business ID; only ACK after state commits.

**Verification:** extend processing duration, kill a worker mid-flight, and verify redelivery creates no duplicate side effects.

### Example 3: Retry Storm When an External API Returns 429

A traffic spike causes an external API to return 429. Each function retries immediately three times; thousands of invocations resend simultaneously, keeping the quota exhausted.

**Cause:** missing backoff, jitter, shared rate limiting, and retry budgets.

**Redesign:** honor `Retry-After`, apply exponential backoff with full jitter, cap attempts and overall retry budget; reduce event source concurrency or queue work. Monitor quota consumption and age of oldest message.

**Verification:** inject 429 responses for several minutes, measure request rate to the dependency, and verify it drops rather than multiplying with retries.

### Example 4: Payment API Timeout with Unknown Outcome

A function sends a payment request. The payment API processes it, but the response is lost. The function retries with a brand-new request and the customer is charged twice.

**Cause:** timeouts are treated as definite failures, even though the remote operation may have committed.

**Redesign:** use a stable idempotency key generated from the business transaction; on timeout, query the payment API by key/reference before retrying. Store `UNKNOWN` state and run reconciliation if the outcome remains unresolved.

**Verification:** drop the connection after the payment API commits and before the response returns; verify retries do not create a second charge.

### Example 5: Single Bad Record in a Batch Causes Full Reprocessing

A function receives a batch of 100 messages. 99 messages succeed, and one fails due to an invalid payload. The event source redelivers the entire batch; the first 99 messages run again.

**Cause:** missing per-record idempotency or partial batch responses.

**Redesign:** store state per message/business ID; enable partial batch failure if supported by the event source; route poison records to a DLQ per policy. Preserve outcomes for the 99 committed records so redeliveries cause no new side effects.

## 17. Common Mistakes

- **Setting function timeout equal to gateway timeout:** the function can keep running after the caller gives up.
- **Setting large timeouts on every dependency:** one hung dependency holds the entire execution longer than necessary.
- **Retrying every exception:** validation and permission errors do not heal on retry.
- **Retrying at multiple layers:** downstream call counts multiply exponentially.
- **Retrying immediately:** creates a thundering herd just as the dependency recovers.
- **Not bounding total retry time:** the function hits its deadline mid-loop without saving state.
- **Treating timeouts as rollbacks:** remote operations may have committed even if the response was lost.
- **Deduplicating with volatile caches:** cache eviction lets old events re-execute.
- **Writing dedupe records after side effects:** a crash window creates duplicate effects.
- **Generating a new idempotency key per retry:** every attempt is treated as a new business action.
- **Setting dedupe TTL too short:** redrives/replays arrive after keys expire.
- **Deduplicating only at the batch level:** one repeated record triggers reprocessing of an entire batch.
- **Setting visibility timeout too short:** two workers process the same message concurrently.
- **Leaving DLQs without owners:** failed messages accumulate unhandled.
- **Redriving everything at once:** overloads dependencies and restarts retry storms.
- **Confusing duplicate handling with out-of-order handling:** business state gets overwritten out of sequence.

## 18. Operational Checklist

### Timeouts and Deadlines

- [ ] Defined business deadlines and per-layer timeouts.
- [ ] Total timeout budget fits within the deadline, including cleanup/response headroom.
- [ ] Dependency timeouts are based on latency percentiles and real load.
- [ ] Functions do not hold executions open excessively when dependencies hang.
- [ ] Cancellation is never mistaken for remote rollback.

### Retries and Backoff

- [ ] Classified transient, throttling, permanent, and unknown-outcome errors.
- [ ] Only safe or idempotent operations are retried.
- [ ] Retries have max attempts, deadlines, and retry budgets.
- [ ] Backoff includes caps and jitter.
- [ ] `Retry-After` is honored where applicable.
- [ ] Avoided uncoordinated multi-layer retries without an overall cap.

### Duplicates and State

- [ ] Events carry stable IDs or idempotency keys.
- [ ] Dedupe store uses atomic unique/conditional writes.
- [ ] Dedupe records and business changes commit in the same transaction when possible.
- [ ] External side effects use idempotency keys or reconciliation workflows.
- [ ] Same key with a different payload is handled as a conflict.
- [ ] TTL matches retry, retention, redrive, and replay windows.
- [ ] Out-of-order handling exists if required by business logic.

### Queues, DLQs, and Observability

- [ ] Visibility timeouts/leases cover processing duration with extension if needed.
- [ ] Batch failures are handled per record where supported by the event source.
- [ ] DLQs have retention, encryption, ownership, and alerting.
- [ ] Redrives are rate-limited and preserve idempotency keys.
- [ ] Monitoring covers timeouts, retries, duplicates, queue age, DLQs, and dependency throttling.
- [ ] Logs include correlation IDs without exposing secrets or sensitive payloads.

### Testing

- [ ] Tested response loss after side effects commit.
- [ ] Tested concurrent and sequential duplicates.
- [ ] Tested crashes between dedupe, commit, and ACK.
- [ ] Tested dependency 429/503 responses and retry storms.
- [ ] Tested poison messages, DLQs, and redrives.
- [ ] Verified cost and SLO behavior under elevated retry rates.

## 19. Conclusion

A timeout bounds the duration of a single operation; a deadline bounds the entire business flow. Split timeout budgets across the function and its dependencies rather than letting every layer consume the full deadline. Retries are appropriate only for recoverable errors and require max attempts, backoff, jitter, retry budgets, and time limits.

In serverless systems, an event may be delivered multiple times due to lost ACKs, timeouts, redeliveries, batch retries, or replays. Stable idempotency keys, atomic deduplication, transactions, state machines, and reconciliation prevent duplicate business side effects. DLQs and redrives provide a recovery path for messages that cannot complete; observability and failure testing prove these safeguards work under real conditions. When timeouts, retries, and idempotency are designed together, serverless workloads recover from failures while protecting data integrity, SLOs, and operational costs.
