# Timeouts, Retries, and Classifying Retryable Errors

In background and batch processing, a single task can traverse multiple components: scheduler, queue, worker, database, object storage, and external APIs. A dependency call timing out does not necessarily mean the operation failed. The request may never have arrived, the server may have processed it while the response was lost, or the operation may still be running after the client stopped waiting. If workers retry without controls, a business operation can execute multiple times, duplicate data can be written, or load can spike just as the system is recovering from an incident.

Good retry design starts with bounded timeouts, end-to-end task deadlines, and error classification. Only errors capable of self-recovery should be retried; data errors, permission errors, or business rule violations generally require fixing the root cause or routing to a separate handling path. For tasks with side effects, retries must be paired with idempotency, deduplication, or transactions to avoid repeating impacts.

This lesson belongs to the **Background and Batch Processing** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security configurations; deploy applications, scale under load, ensure availability, and optimize operational costs. Within that scope, timeouts and retries determine how workers utilize resources, recover during dependency disruptions, and preserve work correctness upon re-execution.

## 1. What problems do timeouts and retries solve?

### 1.1. A timeout is a wait time limit

A timeout specifies the maximum time an operation is allowed to wait before the caller stops waiting or cancels the portion of work it controls.

Timeouts are necessary because:
- Dependencies can stop responding.
- Network packets can be dropped or links interrupted.
- Workers can hold threads, connections, memory, and processing slots while waiting indefinitely.
- Queues can pile up if each task occupies a worker for too long.
- A single hung request can exhaust concurrency across an entire service.

A timeout does not by itself prove the server-side operation stopped. The client may time out while the server continues executing.

### 1.2. A retry is re-executing an operation

A retry re-attempts an operation after a previous attempt failed or failed to receive a result within the allowed window.

Retries can help when an error is transient, such as:
- Short-lived connection resets.
- Services returning temporary overload errors.
- A node undergoing replacement.
- Rate limits requesting a wait before resending.
- Brief network packet loss.

Retries cannot fix permanent errors such as malformed schemas, missing permissions, nonexistent resources, or business rejections. Retrying these errors only adds load and prolongs execution.

### 1.3. Three outcomes to distinguish

A call can end in three states:

1. **Confirmed success:** the caller receives a success result with evidence the operation completed.
2. **Confirmed failure:** the caller receives an error indicating the operation was not executed or was rejected.
3. **Unknown outcome:** the caller timed out or lost connection, so it does not know whether the server committed.

The third state is especially critical. For example, a worker sends an invoice creation request; the database commits successfully, but the response is lost. If the worker retries as a fresh request, it may create a second invoice.

For unknown outcomes, use idempotency keys, status lookups by operation ID, or deduplication mechanisms before re-issuing side effects.

### 1.4. Timeouts and retries must be designed together

If each call has a 10-second timeout and retries 5 times, total wait time can exceed 50 seconds, excluding backoff and processing time. If the queue visibility timeout is only 30 seconds, the message may be redelivered to another worker while the first worker is still retrying.

Design simultaneously:
- Per-operation timeout.
- Overall job deadline.
- Maximum number of attempts.
- Wait interval between attempts.
- Visibility timeout or lease.
- Maximum execution time of the worker/serverless function.
- Cancellation and expiry handling policy.

## 2. Classifying errors before retrying

### 2.1. Transient errors

Transient errors are likely to disappear after waiting a reasonable amount of time.

Examples:
- Network resets or connection timeouts.
- Temporary DNS resolver timeouts.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests when waiting as instructed is viable.
- HTTP 500, 502, 503, or 504 depending on the API contract.
- Database deadlocks or retryable failover errors.
- Storage throttling or service unavailable.
- Queues or brokers temporarily unavailable.

Not every 5xx code is guaranteed to be retryable. For example, a gateway might return 502 because an upstream is misconfigured; blind retries will not help. Combine status codes, detailed error codes, operation semantics, and dependency documentation.

### 2.2. Permanent errors

Permanent errors usually require fixing the request, data, permissions, or configuration before rerunning.

Examples:
- Payload failing schema validation.
- Missing required fields.
- Invalid data format.
- Access denied.
- Invalid or revoked credentials.
- Referenced resource does not exist.
- Business constraint violation.
- Deprecated API version no longer supported.
- Corrupted input file.

Do not automatically retry these errors with the exact same request. Route messages to a dead-letter queue (DLQ), persist error details, and require data remediation or operator intervention.

### 2.3. Errors requiring special handling

Some errors cannot be classified by status code alone:

- **Timeout after sending request:** the result may already be committed.
- **HTTP 409 Conflict:** may be a business conflict or a state resolvable by re-reading.
- **HTTP 401/403:** usually requires fixing credentials/permissions; refreshing an expired token can be a conditional retry case.
- **HTTP 404:** usually a nonexistent resource, though occasionally eventual consistency endpoints need a brief wait.
- **HTTP 429:** must respect `Retry-After` and cap retries.
- **HTTP 500:** may be a transient glitch or a deterministic logic bug.
- **Database connection lost during commit:** the transaction may have committed; check status via operation ID before replaying.

Classification must rely on the service contract and operation context rather than a generic HTTP status table alone.

### 2.4. Retry decision table

| Error category | Examples | Auto-retry? | Action |
|---|---|---|---|
| Transient network | Reset, connect timeout | Bounded | Backoff and jitter |
| Overload | 429, throttling, 503 | Conditional | Respect `Retry-After`, reduce concurrency |
| Dependency unready | 502/504 during deployments | Conditional | Retry, monitor health |
| Invalid request | 400, schema error | No | Fix payload or send to DLQ |
| Unauthorized | 401/403 | Usually no | Fix identity/policy or credentials |
| Not found | 404 | Not by default | Check reference or eventual consistency semantics |
| Conflict | 409, version conflict | Conditional | Read latest state and resolve per business logic |
| Unknown outcome | Timeout when commit may have happened | Do not blindly retry | Look up operation/idempotency key |
| Deadline exceeded | Job exceeded allowed duration | Not within current job | Checkpoint, requeue per policy, or flag for handling |

This table is a starting guideline. Each dependency needs an explicit policy covering status codes, error codes, retryable operations, and total limits.

## 3. Multi-layered timeout design

### 3.1. Connect timeout

Connect timeout bounds how long establishing a connection to a dependency can take. It covers completing the client's required connection handshake steps, depending on the protocol and library.

If connect timeout is too long:
- Workers hold slots while unable to do useful work.
- Waiting connections can exhaust connection pools.
- Queue backlogs grow.

If too short:
- Valid connections over high-latency networks fail repeatedly.
- Retries inflate connection attempts and network load.

### 3.2. Read/response timeout

Read timeout bounds how long to wait for response data after the connection is established or after sending the request, depending on the client library.

Some libraries define read timeout as the idle interval between received bytes rather than total response duration. Understand your library's semantics and enforce an overall deadline as well if needed.

### 3.3. Write timeout

Write timeout bounds how long sending the request body or data to the socket can take. For large uploads or streams, writes can block when the network or server cannot read fast enough.

### 3.4. Request/operation timeout

Operation timeout bounds total duration for one logical operation, which may include:
- Acquiring a connection from the pool.
- Connecting.
- TLS handshake.
- Sending the request.
- Waiting for the response.
- Reading the body.
- Deserializing and processing the result.

Set an operation timeout encompassing the component timeouts so actual total duration does not exceed expectations.

### 3.5. Job deadline

The job deadline is the final cutoff time by which the entire task must finish. The deadline must encompass all attempts, backoff, auxiliary operations, and commit steps.

Example:
- Job has a 60-second deadline.
- Connect timeout is 2 seconds.
- Per-attempt operation timeout is 8 seconds.
- Maximum 3 attempts.
- Backoff of 1 second and 2 seconds respectively.

Expected worst-case call duration: 3 × 8 + 1 + 2 = 27 seconds, excluding internal processing. The remainder covers validation, commits, and cleanup. If the first call already took 20 seconds, do not start another 8-second attempt when only 5 seconds remain before the deadline.

### 3.6. Timeouts tailored to dependencies and business logic

Do not apply one blanket timeout to every dependency. For example:
- Cache lookups might need tens of milliseconds.
- Internal APIs might need a few hundred milliseconds.
- Reports or batch queries might need several minutes.
- Large object uploads need timeouts scaled to size and throughput.

Timeouts must reflect SLOs, real latency, request sizes, and the job's time budget.

## 4. Deadline propagation and cancellation

### 4.1. Propagating deadlines end-to-end

If a job has a 30-second deadline, each downstream service must know how much time remains. If every service starts a fresh 30-second timeout of its own, total end-to-end duration can far exceed 30 seconds.

You can propagate:
- Absolute deadline as a timestamp with clock-skew awareness.
- Remaining timeout as a duration.
- Operation ID to track the task.
- Cancellation signal when the caller no longer needs the result.

When propagating deadlines across services, account for clock skew and reserve time for responses/cleanup. Commonly, remaining budgets are carried in request contexts or RPC deadlines.

### 4.2. Cancellation must propagate to dependencies

When a job hits its deadline or is cancelled, the worker should:
- Stop starting new operations.
- Cancel in-flight requests if the client library supports it.
- Close streams or connections appropriately.
- Stop batches at safe boundaries.
- Save checkpoints if possible.
- Release leases and resources.

Client-side cancellation does not guarantee the server stopped. For side effects already sent, still verify status or rely on idempotency.

### 4.3. A timeout is not a kill switch

A timeout may only make the caller stop waiting. The server might still:
- Continue running the database query.
- Commit the transaction.
- Write files or objects.
- Send messages.
- Call the next service.

Therefore, timeouts should be paired with server-side deadlines, cancellation tokens, transaction timeouts, or operation status checks where supported by the platform.

## 5. Backoff, jitter, and retry attempt limits

### 5.1. Immediate retries can worsen outages

Suppose a database is overloaded. 1,000 workers all receive errors and retry immediately. The database gets hit with 1,000 fresh requests while still unrecovered, driving errors even higher. This is a retry storm.

Retries without waiting can also:
- Open massive bursts of concurrent connections.
- Spike queues and CPU usage.
- Flood rate-limited APIs.
- Synchronize worker retries into lockstep waves.

### 5.2. Exponential backoff

Exponential backoff increases the wait interval after each failure.

Basic formula:

**delay(n) = min(max_delay, base_delay × 2^(n-1))**

Example with 500 ms base delay and 8-second max delay:

| Retry attempt | Delay before attempt |
|---:|---:|
| 1 | 0.5 seconds |
| 2 | 1 second |
| 3 | 2 seconds |
| 4 | 4 seconds |
| 5 | 8 seconds |
| 6 and beyond | 8 seconds |

Always set max attempts or an overall deadline. Unbounded backoff can keep jobs alive indefinitely.

### 5.3. Jitter

Jitter adds randomness to delays so workers do not retry at the exact same moment.

A common approach is full jitter:

**delay(n) = random(0, min(max_delay, base_delay × 2^(n-1)))**

For instance, when an attempt has a 4-second window, each worker picks a random time between 0 and 4 seconds. This spreads out requests and flattens load spikes.

Several jitter variants exist. Pick one consistent algorithm, test under heavy load, and document its bounds.

### 5.4. Respecting Retry-After

Some services return `Retry-After` to indicate how long a client should wait before resending. Its value may be a number of seconds or an HTTP-date timestamp.

Clients should:
- Parse the header format accurately.
- Never retry earlier than the requested time.
- Apply the overall deadline cap.
- Add extra jitter if aligned with policy.
- Prevent abnormal values from stalling jobs indefinitely; enforce a maximum wait and move to a long-term retry schedule if needed.

### 5.5. Capping attempts and retry budgets

A policy should explicitly state:
- Maximum attempt count.
- Backoff schedule.
- Overall deadline.
- Error classes eligible for retry.
- Service or dependency retry budget.
- Criteria for moving messages to a DLQ.

A retry budget limits total retry volume relative to original requests over a time window. When errors surge broadly, the system curtails retries to protect dependencies rather than amplifying load.

Do not stack retries across layers without summing the total. If the API gateway retries 3 times, the worker retries 4 times, and the SDK retries 3 times, one original operation can generate up to 36 downstream requests in the worst case.

## 6. Idempotency and preventing duplicate business effects

### 6.1. What is idempotency?

An idempotent operation can be executed multiple times with the same identifier or input without producing additional business side effects beyond the intended outcome.

Examples:
- Setting order status to `PAID` at a specific version.
- Writing processing results keyed by the job's unique key.
- Creating a resource with a client-supplied idempotency key.
- Recording processed messages in an inbox table with a unique constraint.

Conversely, "add 100 to balance" is not idempotent if executed twice. Money transfers or invoice creation require explicit duplicate prevention.

### 6.2. Idempotency keys

The client generates a stable key for a logical business operation and reuses that exact key across all retries. The server stores the key alongside operation status/results.

Example:
- `operation_id = order-8472-charge-v1`
- First request with this key executes the transaction.
- Retry requests with the same key receive the stored result.
- A new request for a different business action must use a different key.

Do not generate a fresh idempotency key on every retry; otherwise, the server cannot tell the attempts belong to the same operation.

### 6.3. Idempotency table

A key storage table might contain:

| Field | Purpose |
|---|---|
| `idempotency_key` | Unique identifier of the operation |
| `request_hash` | Detects reuse of the same key with a different payload |
| `status` | `IN_PROGRESS`, `SUCCEEDED`, `FAILED_FINAL` |
| `result_reference` | Reference to committed result |
| `created_at` | Creation timestamp |
| `expires_at` | Key retention expiration timestamp |
| `owner/lease` | Tracks currently processing worker if needed |

When an existing key arrives:
- If already succeeded, return the stored result.
- If currently in progress, return an in-progress status or let the caller wait within limits.
- If permanently failed, return the terminal error.
- If the payload hash differs, reject because the same key is being misused.

`idempotency_key` needs a unique constraint or equivalent compare-and-set mechanism so two workers receiving the same request concurrently cannot both create new records. Key retention must outlast the maximum window of retries, redeliveries, and DLQ replays. If an external provider retains idempotency keys only briefly, query or reconcile state after expiration before resending side effects.

### 6.4. Atomicity between side effects and idempotency records

Do not save a successful idempotency record before committing the side effect, nor commit the side effect and skip recording the key without a recovery mechanism.

If both live in the same database, use a single transaction to:
1. Check or insert the idempotency key.
2. Perform the business mutation.
3. Persist the result.
4. Commit together.

If side effects live in another system, use appropriate patterns such as transactional outbox, inbox/deduplication, saga, or provider-supported idempotency APIs.

### 6.5. Transactional outbox

The transactional outbox solves scenarios where an application must both update a database and emit a message.

Within one transaction:
- Update business state.
- Insert an event into an outbox table.

A dispatcher reads the outbox and publishes messages. If publishing succeeds but the dispatcher crashes before marking it sent, the event may be published again. Consumers still need inbox/deduplication or idempotent handling.

An outbox closes the gap between database commits and event publishing, though it does not automatically provide end-to-end exactly-once semantics.

### 6.6. Scoping exactly-once semantics

Many queues or streams offer exactly-once semantics within a bounded scope, such as between consumer offsets and broker transactions. That does not automatically guarantee side effects to databases, emails, payment providers, or external APIs happen strictly once.

Distributed systems are commonly designed around:
- At-least-once delivery.
- Idempotent processing.
- Durable deduplication.
- Transactions or outbox/inbox across data boundaries.
- Status reconciliation when outcomes are unknown.

## 7. Retries in queues and batch workers

### 7.1. Messages can be delivered multiple times

Many queues operate with at-least-once delivery. If a worker finishes processing but the ACK is lost, the message may be redelivered. If a worker crashes before ACKing, the message can also reappear after the visibility timeout.

Therefore:
- Every message should have a stable message ID or business operation ID.
- Side effects must be idempotent or deduplicated.
- ACK only after results are committed.
- Visibility timeouts must cover processing time or be safely extended.

### 7.2. Distinguishing in-process retries vs. queue-based retries

**In-process retry:** the worker holds the message and retries the dependency within the same execution attempt. Best for brief glitches likely to recover quickly.

**Queue-based retry:** the worker does not ACK or explicitly requeues the message for later processing. Best when long backoff is needed, workers should not hold slots, or a dependency is experiencing an outage.

Do not retry hundreds of times inside one process before returning the message to the queue. That ties up workers, connections, and memory unnecessarily.

### 7.3. Visibility timeouts and leases

A visibility timeout is the window during which a received message is temporarily hidden from other workers. If processing exceeds the timeout without renewal, the message can be redelivered while the old worker is still running.

Requirements:
- Set visibility timeout longer than normal processing duration with headroom.
- Renew visibility/leases while jobs remain active.
- Enforce an overall deadline and maximum renewal count.
- Stop writing if a worker loses ownership.
- Use fencing tokens if the system must block stale workers from writing data.

Lease renewal must never let a hung job hold a message forever. Monitor renewal counts, job age, and lease expirations.

### 7.4. Retry delays and delayed queues

For errors requiring longer waits, a delayed queue or scheduler can store the next eligible retry timestamp. Workers ACK/requeue per system semantics without holding threads during the wait.

Ensure:
- Retried messages keep the original operation ID.
- Attempt count and next-attempt time are preserved.
- Delays do not exceed job deadlines or retention.
- Messages are not accidentally dispatched to both the main queue and retry queue simultaneously.
- Recovery exists if publishing the retry succeeds while ACKing the old message fails.

### 7.5. Batch processing and partial failures

A batch can contain multiple records. If one record fails, there are two strategies:
- Retry the entire batch.
- Retry only failed records if the event source supports partial batch responses.

Retrying the entire batch may reprocess records that already succeeded. Consumers must be idempotent or persist results per record ID.

Example with a 100-message batch:
- 98 messages process and commit cleanly.
- 2 messages fail transiently.
- If the whole batch retries, the 98 succeeded messages run again.
- With partial failure support, only the 2 failed messages are redelivered.

For batches with side effects, record per-item outcomes or use proper transactions. Never ACK an entire batch if part of its outcomes is unprotected under the event source's semantics.

### 7.6. Poison messages and dead-letter queues

A poison message is a message that consistently fails due to data or conditions unrecoverable via normal retries.

After a configured attempt limit or age threshold, route the message to a DLQ. The DLQ should store:
- Payload or payload reference.
- Message ID and operation ID.
- Error class and error code.
- Attempt count.
- First/last failure timestamps.
- Processing worker/version.
- Trace ID and relevant dependency.

A DLQ is not a place to forget messages. Set up alerts, triage, data remediation workflows, and controlled replay.

## 8. Classifying and persisting error states

### 8.1. Error taxonomy

Define consistent error categories:

| Category | Examples | Auto-retry? | Action |
|---|---|---|---|
| `TRANSIENT_NETWORK` | Reset, DNS timeout | Bounded | Backoff and jitter |
| `TRANSIENT_CAPACITY` | 429, throttling | Conditional | Respect `Retry-After`, reduce concurrency |
| `DEPENDENCY_UNAVAILABLE` | 502/503/504 | Conditional | Retry, circuit breaker |
| `DEADLOCK_CONFLICT` | Deadlock, optimistic conflict | Bounded | Roll back and retry fresh transaction |
| `INVALID_INPUT` | Malformed schema or data | No | DLQ or fix data |
| `AUTHORIZATION` | Missing permissions, bad token | Usually no | Fix identity/policy |
| `NOT_FOUND` | Resource missing | Usually no | Verify reference |
| `BUSINESS_REJECTED` | Quota exceeded, invalid state | No | Terminate per business rules |
| `UNKNOWN_OUTCOME` | Timeout when commit may have happened | Do not blindly retry | Look up operation/idempotency |
| `DEADLINE_EXCEEDED` | Time budget exhausted | Not within current job | Checkpoint or requeue per policy |

Category names are examples. Standardize one taxonomy across workers, APIs, queues, and monitoring so dashboards do not have to reconcile dozens of similar names.

### 8.2. Error envelope

A structured error can contain:
- `code`: stable error code.
- `category`: error category.
- `retryable`: decided by policy.
- `retry_after_ms`: suggested wait time if applicable.
- `operation_id`: business identifier.
- `attempt`: current attempt number.
- `dependency`: involved system.
- `trace_id`: tracing identifier.
- `message`: scrubbed description containing no secrets or sensitive data.

Do not let every service guess retryability by parsing error message strings. Use structured error codes and clear contracts.

### 8.3. Persisting attempt state

For long-running or critical jobs, store:
- Job ID and operation ID.
- Attempt count.
- Last attempt timestamp.
- Next retry time.
- Deadline.
- Latest error category/code.
- Checkpoint or latest completed step.
- Idempotency state.
- Worker lease/owner if applicable.

Durable state lets new workers resume after restarts and helps operators investigate why a job is waiting.

## 9. Retry budgets, circuit breakers, and bulkheads

### 9.1. Retry budgets

A retry budget caps the total volume of retries permitted over a time window. When error rates surge, the system throttles retries so it does not amplify load.

Illustrative policy example:
- Retry at most 10% of original request volume within a window.
- When budget is exceeded, queue tasks for later or return controlled errors.
- Gradually replenish budget as the dependency recovers.

Numbers must reflect real traffic and capacity. Budgets can be managed per client, service, tenant, or dependency.

### 9.2. Circuit breakers

A circuit breaker tracks dependency errors and transitions across states:
- **Closed:** requests flow normally.
- **Open:** temporarily halts calls to the dependency when errors cross a threshold.
- **Half-open:** lets a small number of probe requests through to test if the dependency recovered.

When the circuit is open, workers should not keep retrying immediately. They can wait, requeue, or invoke a safe fallback.

A circuit breaker needs:
- Error threshold and observation window.
- Open-state duration.
- Probe count in half-open state.
- Error classification so business rejections do not trip the circuit.
- Metrics and logs for every state transition.

### 9.3. Bulkheads

Bulkheads isolate resources allocated to each dependency or workload group:
- Separate connection pools.
- Separate thread/worker pools.
- Per-dependency concurrency caps.
- Dedicated queues for heavy tasks.
- Per-tenant job limits.

If one dependency slows down, bulkheads stop it from consuming all workers and connections across the service.

### 9.4. Combining the mechanisms

Timeouts cap how long a single call waits. Retries handle transient glitches. Backoff/jitter reduce synchronization. Retry budgets prevent load amplification. Circuit breakers stop calling failing dependencies. Bulkheads protect remaining resources. Idempotency protects business correctness when operations re-run.

No single mechanism replaces the others.

## 10. Example retry implementation with deadline and idempotency

The following pseudocode illustrates a client calling a dependency with timeouts, error classification, backoff, jitter, and the same idempotency key across all attempts:

~~~python
import random
import time

RETRYABLE_CODES = {
    "TEMPORARY_UNAVAILABLE",
    "RATE_LIMITED",
    "NETWORK_RESET",
}

def call_with_retry(client, request, operation_id, deadline):
    attempt = 0
    base_delay = 0.2
    max_delay = 3.0
    max_attempts = 4

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("operation deadline exceeded")

        attempt += 1
        call_timeout = min(2.0, remaining)

        try:
            return client.execute(
                request,
                timeout=call_timeout,
                idempotency_key=operation_id,
            )
        except client.Error as exc:
            if exc.code not in RETRYABLE_CODES:
                raise

            if attempt >= max_attempts:
                raise

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("operation deadline exceeded")

            ceiling = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = random.uniform(0, ceiling)

            retry_after = getattr(exc, "retry_after_seconds", None)
            if retry_after is not None:
                delay = max(delay, retry_after)

            if delay >= remaining:
                raise TimeoutError("insufficient deadline for retry")

            time.sleep(delay)
~~~

This is illustrative pseudocode, not a production library. In production:
- Use a monotonic clock for deadlines.
- Map exact client error types/codes.
- Handle `Retry-After` per service contract with an upper cap.
- Do not retry operations with side effects if the server lacks idempotency or state is unverified.
- Add cancellation and telemetry.
- Avoid sleeping inside workers when retries can be scheduled via queues.

### 10.1. Example message-processing worker

~~~text
receive(message)
operation_id = message.business_operation_id
deadline = message.deadline

if already_committed(operation_id):
    acknowledge(message)
    return

result = execute_with_deadline_and_retry(
    operation_id,
    message.payload,
    deadline
)

commit_result_and_idempotency_record(result, operation_id)
acknowledge(message)
~~~

In real implementations, `already_committed`, the side effect, and the idempotency record must share an atomic boundary or reconciliation process. You cannot rely solely on line ordering in pseudocode if the side effect lives outside the local database.

## 11. Practical example: invoice creation worker

A worker receives a message to create an invoice after an order is paid. The worker calls an external invoicing API.

Scenario:
1. Worker sends an invoice creation request with operation ID `invoice-order-8472`.
2. The provider processes it successfully and creates the invoice.
3. The response is lost due to a network timeout.
4. The worker does not know whether the invoice was created.
5. If it retries with a fresh request lacking an idempotency key, the provider may create a duplicate invoice.

Design approach:
- Use a deterministic operation ID tied to the order and operation type.
- Send the exact same idempotency key on every retry.
- If the provider supports lookup by key, query status before creating again.
- Store `IN_PROGRESS` status and the provider reference upon completion.
- Mark the job complete only after durably persisting the result.
- ACK the message after committing.
- If the provider returns a permanent error, route to DLQ and alert the owner.
- If the provider times out continuously, open the circuit and schedule a later retry.

When replaying from the DLQ, keep the original operation ID. Generating a new key destroys the ability to detect that the operation already ran.

## 12. Batches, checkpoints, and partial retries

### 12.1. Splitting batches into recoverable units

Large batches should have checkpoints or commit boundaries. For example, processing 10,000 records:
- Split into 100-record chunks.
- Each chunk has a stable range or cursor.
- Persist chunk results inside a transaction.
- Save the checkpoint after committing.
- If the worker stops, resume from incomplete chunks.

Never update the checkpoint before committing chunk results. Saving the checkpoint first and crashing during data writes can skip unfinished chunks.

### 12.2. Retrying a chunk

Chunks can have stable IDs, such as `job-2026-11-22/chunk-0042`. On retry:
- Use the same chunk ID.
- Check whether the chunk already committed.
- Write results using unique keys.
- Update the checkpoint only on commit success.
- Do not re-run non-idempotent external side effects outside the transaction.

### 12.3. Partial success

A batch can contain many independent items. Track per-item state:
- `PENDING`
- `IN_PROGRESS`
- `SUCCEEDED`
- `RETRY_WAIT`
- `FAILED_FINAL`

Failed items can be retried without rerunning succeeded items. However, if succeeded items triggered external side effects outside the state store, per-item idempotency is still required.

### 12.4. Checkpoints do not replace idempotency

A checkpoint records how far progress has been saved. It does not automatically guarantee the action immediately preceding the checkpoint executed only once.

Example:
1. Worker writes a transaction successfully.
2. Worker crashes before saving the checkpoint.
3. Job resumes from the previous checkpoint.
4. The transaction may be written again.

You still need idempotency keys, unique constraints, inbox tables, or transactions combining side effects and checkpoints within the same data boundary whenever possible.

## 13. Timeouts and retries in serverless and containers

### 13.1. Serverless functions

Serverless functions typically have hard execution time limits. If an invocation times out, the event source may retry under its own policy. Account for:
- Function timeout.
- Dependency timeouts.
- Trigger retry policy.
- Event retention.
- Concurrency and scaling rate.
- DLQ or failure destination.
- Side-effect idempotency.

If a function times out at the last second after committing to the database but before acknowledging the event, the event may be redelivered. Consumers must be idempotent.

### 13.2. Container workers

Containers can be restarted, scaled in, or evicted during node replacements. Workers must:
- Catch shutdown signals.
- Stop accepting new messages.
- Enforce deadlines on in-flight jobs.
- Checkpoint or requeue if unable to finish.
- Never ACK before commit.
- Release leases and connections.
- Tolerate abrupt kills without receiving a shutdown signal.

In-application timeouts do not replace orchestrator, queue visibility, or external API timeouts. Limits must be coordinated across layers.

### 13.3. Kubernetes Jobs and CronJobs

Kubernetes Jobs recreate Pods when containers fail according to policy and retry limits. Configure:
- Appropriate `backoffLimit`.
- `activeDeadlineSeconds` for an overall time limit.
- Explicit `restartPolicy`.
- Safe re-executability of the job.
- Durable checkpointing on persistent storage.
- Monitoring of failed Pods and job conditions.

Kubernetes Pod retries have no awareness of whether business side effects committed. Applications still need idempotency and deduplication.

### 13.4. Avoid multiplying retries across layers

Example:
- Queue redelivers up to 5 times.
- Worker retries API 4 times.
- SDK auto-retries 3 times.

One message can generate up to 60 downstream requests in the worst case. Align retry ownership:
- SDK handles only very brief connection glitches if needed.
- Worker manages business retries and deadlines.
- Queue manages long-term retries and DLQs.
- API gateways do not auto-retry non-idempotent side effects.

Specify total maximum attempts end-to-end, not just per individual layer.

## 14. Observability and retry operations

### 14.1. Metrics to monitor

| Metric | Meaning | Warning signs |
|---|---|---|
| `operation_duration` | Total operation time | Rising p95/p99 |
| `dependency_latency` | Dependency latency | Rising alongside timeouts |
| `timeout_count` | Timeout count | Spiking by dependency or job type |
| `retry_attempts` | Retry count | Rising rapidly relative to original requests |
| `retry_success_rate` | Success rate after retry | Persistently low |
| `retry_exhausted` | Exhausted attempts | Rising and feeding DLQ |
| `queue_oldest_age` | Oldest message age | Approaching retention/SLO |
| `queue_depth` | Pending message count | Growing continuously |
| `dlq_depth` | Terminal failure count | New messages or rapid growth |
| `idempotency_hit` | Already-processed requests | Unusual spikes may indicate retries/duplicates |
| `duplicate_suppressed` | Duplicate side effects blocked | Unusual spikes need investigation |
| `circuit_state` | Circuit breaker state | Remaining Open too long |
| `deadline_exceeded` | Jobs hitting deadlines | Rising with load or dependency slowness |
| `lease_expired` | Leases expiring while jobs run | Risk of duplicate execution |

### 14.2. Structured logs

Each attempt should log:
- Job ID, message ID, and operation ID.
- Attempt number and max attempts.
- Error category/code.
- Dependency and operation name.
- Timeout, elapsed duration, and remaining deadline.
- Retry delay and next attempt timestamp.
- Trace ID.
- Idempotency check outcome.

Never log passwords, tokens, authorization headers, or sensitive payloads. Logs should connect all retry attempts back to one logical business operation.

### 14.3. Alerts

Alert when:
- Timeout rate crosses threshold.
- Retry-to-request ratio spikes sharply.
- New messages arrive in the DLQ or exceed threshold.
- Queue age breaches SLO.
- Circuit breaker stays open too long.
- Retry budget is burning rapidly.
- Jobs hitting deadlines or lease expirations increase.
- Duplicate side effects are detected.

Alerts should link to an owner and runbook: inspect dependency health, reduce concurrency, scale capacity safely, halt retries, or replay DLQ.

## 15. Timeout and retry incident troubleshooting procedure

1. Identify the affected workload, dependency, start time, and blast radius.
2. Compare request rate, duration, concurrency, and queue backlog.
3. Distinguish between connect timeouts, read timeouts, operation timeouts, and job deadlines.
4. Inspect status codes, error codes, and the dependency's retry contract.
5. Determine whether the operation has side effects.
6. For unknown outcomes, look up operation ID/idempotency key before retrying.
7. Check retry counts, backoff, `Retry-After`, and retry budgets.
8. Check connection pools, downstream quotas, and circuit breakers.
9. Inspect the DLQ, poison messages, and checkpoints.
10. Fix the underlying dependency or bad source data.
11. Replay under controlled limits while preserving operation IDs and watching for duplicates.
12. Re-measure latency, retry rates, queue age, and business correctness.

Do not bulk-purge the DLQ or reset attempt counts just to "clean up" dashboards before understanding the root cause. Doing so destroys evidence and triggers unsafe replays.

## 16. Common mistakes

**Retrying every exception.** Data or permission errors do not heal themselves. Classify errors by code and semantics.

**Using overly long timeouts.** Workers stay tied up, growing queue backlogs and concurrency pressure. Set timeouts based on SLOs and deadlines.

**Retrying immediately.** Synchronized worker retries create retry storms. Use exponential backoff and jitter.

**No maximum attempt limit.** Jobs can loop indefinitely. Enforce max attempts, deadlines, and DLQs.

**Generating a new idempotency key per retry.** The server treats each attempt as a brand-new operation. Keep keys stable per operation.

**ACKing messages before committing.** A worker crash can lose work. Commit results before ACKing.

**Assuming a timeout means the server never executed.** The server may have committed while the response got lost. Query status before replaying.

**Relying solely on checkpoints.** Crashing between side effect and checkpoint can still repeat effects. Combine with idempotency or transactions.

**Retrying at every layer.** Retries multiply across gateway, SDK, worker, and queue. Define clear retry ownership.

**Ignoring Retry-After.** Can keep violating rate limits. Wait as instructed within deadline bounds.

**Sleeping workers during long backoffs.** Wastes concurrency and compute resources. Schedule delayed retries via queues when appropriate.

**Replaying DLQs blindly.** Old messages may be stale or already applied. Verify operation state and preserve idempotency keys.

## 17. Design checklist

### Timeouts and deadlines

- [ ] Appropriate connect, read/write, and operation timeouts are set.
- [ ] Every job has an overall deadline.
- [ ] Deadlines propagate to dependencies.
- [ ] Cancellation and cleanup are implemented.
- [ ] Timeouts align with function runtimes, queue visibility, and orchestrators.

### Classification and retries

- [ ] A consistent error taxonomy exists.
- [ ] Only errors classified as transient are retried.
- [ ] Max attempts and overall deadlines are enforced.
- [ ] Exponential backoff and jitter are used.
- [ ] `Retry-After` is respected.
- [ ] Retry budgets and concurrency limits are enforced.
- [ ] Retries do not multiply uncontrollably across layers.

### Protecting business correctness

- [ ] Every business operation has a stable operation ID.
- [ ] Retries reuse the same idempotency key.
- [ ] Side effects and idempotency records share clear commit boundaries.
- [ ] ACKs happen only after commits.
- [ ] Deduplication or unique constraints are enforced.
- [ ] Checkpoints and partial batch failure handling exist.
- [ ] A lookup mechanism exists when timeouts leave unknown outcomes.

### Operations

- [ ] DLQs and replay procedures are established.
- [ ] Timeouts, retries, queue age, and duplicates are monitored.
- [ ] Circuit breakers and bulkheads are configured where needed.
- [ ] Attempt logs include operation IDs and trace IDs.
- [ ] Alerts fire when retry budgets or DLQs cross thresholds.
- [ ] Slow dependencies, network resets, and worker crashes are tested.
- [ ] Scenarios where the server commits but the response is lost are rehearsed.

## 18. Key takeaways

- Timeouts cap wait duration; they do not prove the server stopped or never committed.
- Retries suit transient errors only and must be bounded.
- Distinguish transient errors, permanent errors, and unknown outcomes.
- Connect/read/write timeouts, operation timeouts, and job deadlines cover different scopes.
- Exponential backoff, jitter, and `Retry-After` mitigate retry storms.
- Sum retries across gateway, SDK, worker, and queue; avoid retry amplification.
- Side effects require stable operation IDs, idempotency keys, or deduplication.
- ACK messages only after results are durably committed.
- Checkpoints do not replace idempotency; crashing between a side effect and checkpoint can still cause duplicate actions.
- Use retry budgets, circuit breakers, and bulkheads to protect dependencies.
- DLQs require owners, alerts, and controlled replay procedures.
- Test cases where the server commits while the client times out.

## Glossary

| Term | Meaning |
|---|---|
| Timeout | Wait time limit for an operation. |
| Connect timeout | Maximum time allowed to establish a connection. |
| Read timeout | Maximum time waiting for response data per client semantics. |
| Write timeout | Maximum time allowed to send data over a connection. |
| Operation timeout | Total time limit for one logical operation. |
| Deadline | Final point in time by which work is allowed to complete. |
| Retry | Re-executing an operation after a failure or missing response. |
| Transient error | Temporary error likely to self-recover. |
| Permanent error | Error requiring fixes to data, permissions, or configuration before re-running. |
| Exponential backoff | Progressively increasing the wait interval between retry attempts. |
| Jitter | Randomness added to delays to spread out retry timestamps. |
| Retry-After | HTTP header indicating when a client should resend a request. |
| Retry budget | Quota capping total retry volume within a time window. |
| Retry storm | Many clients retrying simultaneously, amplifying load on a failing dependency. |
| Idempotency | Ability to repeat an operation without causing unintended extra side effects. |
| Idempotency key | Stable identifier for a logical business operation across attempts. |
| Deduplication | Detecting and discarding duplicate messages or operations. |
| At-least-once delivery | Delivery guarantee where messages are delivered at least once and may be redelivered. |
| Acknowledgement (ACK) | Confirming a message was processed according to queue semantics. |
| Visibility timeout | Duration a received message is temporarily hidden from other workers. |
| Lease | Time-bounded ownership of a resource or work item. |
| Checkpoint | Persisted progress state allowing work to resume after interruption. |
| Partial batch failure | Reporting only a subset of failed items in a batch so only those retry when supported. |
| Dead-letter queue (DLQ) | Queue storing messages that could not succeed under the retry policy. |
| Poison message | Message that consistently fails due to data or conditions unrecoverable by normal retries. |
| Transactional outbox | Pattern storing events inside the business transaction and publishing via a dispatcher. |
| Inbox pattern | Pattern recording received/processed messages for deduplication. |
| Circuit breaker | Mechanism temporarily halting calls to a failing dependency. |
| Bulkhead | Resource isolation preventing one failing dependency from exhausting the entire system. |
| Cancellation | Signal requesting pending or active work to stop. |
