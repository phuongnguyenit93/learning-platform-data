# Retry and Backoff by Error Category in Spring Integration Adapters

> **Chapter:** Production  
> **Lesson:** Retry and backoff by error category  
> **Module:** Spring Integration Adapters  
> **Scope:** Message exchange flows across inbound/outbound adapters, gateways, pollers, MessageChannel, and external systems such as File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish **transient errors**, **permanent errors**, **data errors**, **authentication/authorization errors**, **overload errors**, **conflict errors**, and **unknown outcomes**.
2. Choose retry strategies by **error category + operation + idempotency + transaction/ack boundaries**, instead of retrying every exception.
3. Calculate time budgets from attempt counts, per-attempt timeouts, and backoffs; design exponential backoff, jitter, and rate limiting.
4. Understand the Spring Integration layers where retries can be applied: handler advice, poller, inbound listener/container, client library, broker, and async retry workers.
5. Manage failed messages with `ErrorMessage`, error channels, DLQ/DLT/quarantine, circuit breakers, and replay runbooks.
6. Apply tailored policies across File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC with their ordering, acknowledgement, and transaction constraints.
7. Prove via failure drills that retries **do not lose messages, do not duplicate side effects, do not trigger retry storms, and remain auditable**.

**Cross-cutting scenario:** A Spring Boot service uses Spring Integration to receive orders from SFTP, validate and save them to JDBC, emit Kafka events, and call a partner HTTP API. When the partner returns 503, retrying makes sense. When JSON fails schema validation, retrying repeatedly will not help. When the HTTP client times out after the partner already created a payment, retrying with a new request ID could create a duplicate payment. All are "exceptions", yet each demands a different handling policy.

**Version note:** Mechanisms and API names across Spring Integration, Spring Retry, Spring AMQP, Spring Kafka, JDBC drivers, JMS providers, and HTTP/SFTP clients vary by version. Examples use common patterns and do not claim every adapter or release shares one uniform retry property.

## 2. How Retry Differs from Redelivery, Replay, and Recovery

| Concept | What Happens? | Typical Responsible Party | Risk |
|---|---|---|---|
| **In-place retry** | Repeats an operation within the current execution | Client, handler advice, service | Holds threads/connections, exceeds deadlines |
| **Broker redelivery** | Unacknowledged message is delivered again | JMS/AMQP broker, Kafka consumer on uncommitted offset | Duplicate business side effects |
| **Scheduled retry** | Enqueues task into durable store for later attempt | Application, retry topic/queue, job | Ordering and backlog growth |
| **Replay** | Re-runs messages stored in DLQ/DLT/quarantine or event log | Operator/worker with approval | Data changed since failure, stale side effects |
| **Recovery** | Transitions to a valid fallback state after retries exhaust | Error flow, compensation, fallback | Swallowing errors or returning false success |
| **Compensation** | Undoes or offsets side effects that already occurred | Workflow/saga, business owner | Not an ACID rollback |
| **Circuit breaker** | Temporarily stops calling a heavily failing dependency | Resilience layer | Does not fix data or automatically replay messages |
| **Backpressure** | Throttles intake/inflight volume to match capacity | Poller, channel, broker, limiter | Backlog growth if unmonitored |

**Retry** does not equal **idempotency**. A message can still reach the same consumer twice even when the adapter retries "correctly". Idempotency prevents unintended impact when a valid request is received or processed more than once.

### 2.1. Error-Classified Processing Flow

~~~mermaid
flowchart TD
    IN["Inbound message / request"] --> VALID["Validate contract + business key"]
    VALID --> DECIDE{"Result / error type?"}
    DECIDE -->|"Valid"| EFFECT["Business action + durable state"]
    DECIDE -->|"Invalid schema/auth"| REJECT["Reject / quarantine + alert"]
    DECIDE -->|"Already processed"| NOOP["Idempotent no-op"]
    DECIDE -->|"Transient error"| BUDGET{"Retry budget left?"}
    DECIDE -->|"Unknown side effect"| VERIFY["Verify actual outcome"]
    VERIFY -->|"Completed"| DONE["Mark complete"]
    VERIFY -->|"Not executed"| BUDGET
    VERIFY -->|"Still unknown"| HOLD["Unknown-outcome queue + owner"]
    BUDGET -->|"Yes"| BACKOFF["Backoff + jitter"]
    BACKOFF --> EFFECT
    BUDGET -->|"Exhausted"| DLQ["Durable retry / DLQ / incident"]
    EFFECT --> ACK["Ack / checkpoint at right moment"]
    DLQ --> OPS["Controlled replay runbook"]
~~~

This diagram is logical: choosing **ack**, **rethrow**, or **DLQ** depends on transaction boundaries and adapter semantics. If an error is "recovered" by merely logging and returning, upstream may treat the message as completed even though business logic never ran.

## 3. Error Taxonomy: Decide Whether to Retry Before Choosing Backoff

An exception class alone does not always provide enough semantics. You need the **operation**, **send/receive stage**, **business key**, **idempotency**, and **actual response**.

| Category | Examples | Default Retry? | Handling Direction |
|---|---|---|---|
| **Transient network** | Connection reset, timeout, temporary DNS, broker reconnect | Conditional | Bounded retry + backoff/jitter; outcome may be ambiguous |
| **Overload / throttling** | HTTP 429, 503, pool saturation, temporary quota | Conditional | Honor `Retry-After` when valid; lower concurrency |
| **Transient dependency** | Broker leader election, DB deadlock, temporary unavailable | Conditional | Retry at proper boundary, idempotent, time-bounded |
| **Permanent schema** | Malformed JSON/XML/CSV, unsupported version | No for same payload | Quarantine; fix producer/schema/code |
| **Business validation** | Missing field, negative amount, invalid business state | No, unless dependency can change condition | Reject/DLQ for business review |
| **Authentication** | Invalid/expired credential, invalid client certificate | No tight-loop retry | Valid rotation/refresh or ticket |
| **Authorization** | HTTP 403, broker ACL denied, DB permission denied | No | Fix permissions after approval; audit |
| **Conflict** | Optimistic lock, unique constraint, HTTP 409 | Per contract | May reread/recompute; do not blindly retry raw request |
| **Resource not found** | HTTP 404, file/row not present yet | Usually no | Retry only if eventual-consistency contract allows |
| **Duplicate** | Business ID already processed | No need to repeat effect | Idempotent success/no-op or report conflict |
| **Unknown outcome** | Request sent but response/confirm/commit ack lost | No blind retry | Query/reconcile actual state; reuse idempotency key |
| **Poison message** | Payload triggering infinite repeated failures | No unbounded retry | Bounded attempts then quarantine |
| **Cancellation/deadline exceeded** | Caller SLA expired or pod shutting down | No retry inside expired flow | Durable handoff/recovery per workflow |

**There is no absolute "retry all 5xx" rule.** Sometimes a 500 stems from unsupported input that the server misclassified; sometimes a 409 is a conflict resolvable after re-reading state. Always prioritize the external system's contract and empirical behavior.

### 3.1. 401/403 Errors: Distinguish Credential Refresh from Permission Failure

- **401 Unauthorized:** A token may have just expired. If the system supports reliable token refresh, you can refresh credentials **once in a controlled way** and resend eligible operations—still accounting for idempotency.
- **403 Forbidden:** Typically indicates missing permissions or policy denial; retrying with the same credentials will not fix it.
- **Invalid TLS/SSH host key:** Never convert a security error into a network retry or disable verification.
- **Broker ACL/DB permission denied:** Requires an owner to fix configuration—do not increase call volume.

### 3.2. Conflicts Are Not Always Permanent Failures

An `OptimisticLockingFailureException` can often be handled by reloading the record, recomputing business state, and retrying in a new transaction. Conversely, a `DuplicateKeyException` on a business key may mean **the request was already processed** or a **true data conflict**—never blindly retry the insert. HTTP 409 semantics also vary by API: some mean "resource busy", others mean "invalid state transition".

### 3.3. When Wrapper Exceptions Obscure the Root Cause

In Spring Integration, an error may be wrapped in `MessageHandlingException`, `MessagingException`, or a client/framework exception. If a classifier inspects only the top-level exception, an inner network fault can be misclassified as permanent; conversely, checking only for the substring "timeout" in message text can trigger wrong retries.

Checklist:

- [ ] Classify using reliable **types/status codes/SQLState/broker error codes** whenever possible.
- [ ] Walk nested causes with a depth bound to avoid reference cycles or missing root causes.
- [ ] Never classify solely via naive `exception.getMessage().contains(...)`.
- [ ] Preserve original message ID, business ID, attempt count, and correlation ID.
- [ ] Log cause chains with sensitive data redacted.
- [ ] Test wrapper exceptions in both synchronous and asynchronous flows.

## 4. Which Layer Owns Retry?

A flow may have retries in several places:

1. HTTP/SFTP/JDBC/broker client;
2. Spring Integration request-handler advice;
3. Service method/transaction;
4. Inbound adapter, listener container, or poller;
5. Broker redelivery or retry topic/queue;
6. Error flow, scheduled job, or operator replay;
7. Upstream sender resending because it received no acknowledgment.

Without coordination, retry layers **multiply invocation counts** instead of complementing each other.

### 4.1. Responsibility Matrix

| Point | What Should It Retry? | What to Avoid |
|---|---|---|
| **Client library** | Protocol/connection errors the client knows are safe per its capabilities | Retrying ambiguous side-effect commands without idempotency |
| **Handler advice** | Repeating an idempotent handler call on specific transient faults | Wrapping transactions or unsafe handlers without classification |
| **Business service** | Recomputing and retrying a transaction on recognized locks/deadlocks | Retrying the whole flow when outbound side effects already ran |
| **Poller/source** | Re-fetching items with clear checkpoints; pacing down on source errors | Repeatedly scanning the same file/row without deduplication |
| **JMS/AMQP listener/broker** | Redelivering incomplete messages with a bounded DLQ policy | Infinitely requeuing poison messages |
| **Kafka listener / retry topic** | Reprocessing or scheduling failed records per policy, ending in DLT | Assuming offsets/ordering never shift |
| **Application retry queue** | Offloading operations exceeding sync deadlines to durable processing | Stuffing unbounded in-memory queues |
| **Operator replay** | Re-driving after root-cause fix and approval | Arbitrarily clearing queues or seeking offsets |

**Design rule:** Every operation should have **one primary retry owner**. Other layers must enforce coordinated budgets/guardrails so one layer doesn't keep retrying after another has already recovered.

### 4.2. Multi-System Transactions: What Gets Retried?

Suppose a service activator does:

~~~text
read input -> update DB -> invoke HTTP partner -> publish Kafka -> ack input
~~~

If the HTTP call fails after the DB update, retrying the **entire service activator** can update the DB twice and emit multiple events. A better design combines:

- DB transaction + idempotency key for internal mutations;
- Outbox event for the obligation to publish;
- Stateful outbound workflow/command with idempotent retries;
- HTTP idempotency key or partner status lookup;
- Input ack at the exact point contractual obligations are guaranteed;
- Per-target reconciliation instead of one global "SUCCESS" flag.

There is no default ACID transaction spanning DB, HTTP, files, SFTP, and Kafka in a Spring Integration flow.

## 5. A Retry Policy Is a Decision Function

A policy can be modeled as:

~~~text
retryDecision(
    errorCategory,
    operationType,
    isIdempotent,
    sideEffectStatus,
    sourceCheckpointStatus,
    attemptsMade,
    remainingDeadline,
    dependencyHealth,
    retryAfter
) -> RETRY_NOW | RETRY_LATER | RECONCILE | QUARANTINE | FAIL
~~~

**At least five independent decisions are required**:

1. **Can we retry?** Error category, contract, operation idempotency.
2. **Where to retry?** Client, handler, source redelivery, durable retry queue, or operator.
3. **How many times and for how long?** Attempt count, per-attempt timeout, elapsed/deadline budget.
4. **How long to wait before the next attempt?** Fixed/exponential/decorrelated backoff, `Retry-After`, and jitter.
5. **What happens when retries are exhausted or disallowed?** Fail, quarantine, dead-letter, reconcile, compensate, alert.

### 5.1. Decision Guide by Error Category

| Condition | Preferred Handling |
|---|---|
| Invalid schema/business validation | Reject/quarantine; do not retry the same payload |
| Unauthorized with validly refreshable token | Refresh once per contract; fail if still rejected |
| Forbidden/ACL denied | Fail, alert/ticket; no tight-loop retry |
| 429 with valid `Retry-After` | Wait per policy and deadline; reduce concurrency |
| 503, connection reset before side effect | Bounded retry within budget |
| Timeout on non-idempotent side-effect operation | Reconcile actual outcome before resending |
| Deadlock/serialization failure in pure DB transaction | Bounded transaction retry without repeating external side effects |
| `DuplicateKey` for already-completed business key | Idempotent no-op; do not retry insert |
| Ambiguous broker confirm/offset ack | Inspect state, allow duplicate delivery with idempotent consumer |
| Prolonged dependency outage | Open circuit, durable retry/dead-letter, and alert |
| Deadline exhausted | Stop synchronous retries; hand off to appropriate recovery |

### 5.2. Keep Retry Scope Small and Accurate

Retrying **an HTTP GET read** carries far less risk than retrying **an entire flow that writes a DB and publishes events**. Retries should wrap only idempotent, safely repeatable segments—never use a coarse handler that mutates data and calls three external systems as the default retry unit.

## 6. Backoff: Fixed, Exponential, Jitter, and Retry-After

### 6.1. Common Algorithms

| Strategy | Formula / Intuition | When Useful | Limitations |
|---|---|---|---|
| **Immediate retry** | Zero wait | Very brief glitches, safe for a single quick retry | Easily spikes load |
| **Fixed backoff** | Always wait e.g. 1 s | Low load, stable partner, testing | Clients stay synchronized |
| **Linear backoff** | 1 s, 2 s, 3 s... | Gradually increases wait pressure | Still prone to synchronization |
| **Exponential backoff** | 1 s, 2 s, 4 s, 8 s... up to cap | Outages and rate limits | Simultaneous starters stay aligned |
| **Exponential + full jitter** | Random in `[0, exponential cap]` | Reduces thundering herd | Some delays can be very short |
| **Equal jitter** | Fixed portion + random portion | Avoids near-zero delays, spreads load | Slightly more tuning than full jitter |
| **Decorrelated jitter** | Next delay depends on previous delay + bounded random | Breaks synchronization across waves | Harder to reason about / reproduce |
| **Server-directed** | `Retry-After` or valid quota signal | HTTP 429/503, APIs with backoff contracts | Must validate against deadlines and source trust |

A capped exponential model:

\[
D_k = \min(D_{\max}, D_0 \times m^{k-1}), \quad k = 1,2,\ldots,N-1
\]

where `N` is **total attempts**, not additional retries. Delay `D_k` sits **between attempt k and k+1**. With `N=4`, there are typically only **3 backoff intervals**.

**Example:** 4 attempts, up to 5 seconds each, backoffs 1 s, 2 s, 4 s. Simple worst-case total:

\[
T_{\max} \approx 4 \times 5\mathrm{s} + (1+2+4)\mathrm{s} = 27\mathrm{s}
\]

excluding pool waits, DNS/TLS, serialization, queues, cleanup, and scheduling. If the gateway caller has a 20 s deadline, this policy is **invalid**, even though every individual timeout is finite.

### 6.2. Jitter Reduces Retry Storms

Suppose 500 workers simultaneously receive 503 at 10:00:00. If all wait exactly 1 s, they all strike again together, worsening overload. Jitter spreads retry timing and pairs with **rate limiters + circuit breakers** to prevent thundering herds.

Do not let randomness harm auditability: log attempt numbers, effective delays, and retry decisions (no need to log random seeds).

### 6.3. Respect Retry-After Without Exceeding Deadlines

HTTP `Retry-After` can be **delay-seconds** or an **HTTP-date**. When honoring it:

1. Parse strictly and clamp values per policy.
2. Never blindly trust negative, infinite, or malformed dates.
3. Compare against the **remaining deadline**.
4. Do not block synchronous threads for long waits; offload to durable scheduled retries instead.
5. Apply shared throttling when quotas span multiple instances/tenants.
6. Never treat `Retry-After` as permission to retry unsafe operations with ambiguous side effects.

**Retry-After** is a pacing hint, not a substitute for idempotency or authorization.

## 7. Retry Budgets and Whole-Flow Deadlines

### 7.1. Designing from the Business SLA

For inbound HTTP calling downstream:

- Client/proxy may wait at most 15 seconds.
- Handler needs 2 s for validation, up to 3 s for DB, and at least 2 s reserve.
- Only ~8 seconds remain for outbound retries.
- Two 3-second attempts + 1 s backoff may fit; four attempts will not.

An **approximate** formula:

\[
T_{\mathrm{retry}} \approx \sum_{i=1}^{N}T_{\mathrm{attempt},i}
+ \sum_{i=1}^{N-1}D_i
\]

Whole-flow totals must also account for queues, connection acquisition, serialization, cleanup, DB, and reserves. Do not double-count overlapping timeouts; verify client semantics.

### 7.2. Rule: Only Retry While Budget Remains

~~~text
for attempt in 1..maxAttempts:
    remaining = deadline - monotonicElapsed()
    if remaining <= minimumUsefulTime:
        return DEADLINE_EXCEEDED

    result = invokeWithPerAttemptTimeout(
        min(configuredAttemptTimeout, remaining - reserve)
    )

    if result.success:
        return SUCCESS

    decision = classify(error, operation, sideEffectState)

    if decision == MUST_RECONCILE:
        return UNKNOWN_OUTCOME
    if decision != RETRYABLE:
        return FAIL_OR_QUARANTINE
    if attempt == maxAttempts:
        return RETRIES_EXHAUSTED

    delay = calculateBackoffWithJitter(attempt)
    if delay + reserve >= remaining:
        return RETRIES_EXHAUSTED_OR_DEFERRED

    sleepOrSchedule(delay)
~~~

This pseudocode illustrates **orchestration rules**, not runnable code. In Java, use a monotonic clock to measure elapsed time—never `System.currentTimeMillis()` for critical durations; keep wall-clock timestamps for auditing.

### 7.3. Do Not Hold Threads During Long Backoffs

Short retries of a few seconds can happen in-place under low load when SLA allows. For multi-minute delays:

- Use a **durable** retry queue/job storing scheduled execution time;
- Persist business key, attempt count, next-attempt time, error category, and status;
- Never hold an HTTP request thread, JMS listener session, or SFTP connection while sleeping;
- Use distributed claims/leases with expiry when multiple replicas run retry workers;
- Enforce TTL/maximum age, DLQ, and expiration cancellation policies when business requests expire;
- Alert on backlog depth and oldest retry item age.

**In-place backoff** does not guarantee messages survive process restarts. In-memory timers for critical tasks must be replaced or backed by durable storage.

## 8. Idempotency: Prerequisite When Redelivery Is Possible

### 8.1. Stable Business Keys

Choose keys guaranteed by contract to remain stable across retries:

- `(sourceSystem, sourceEventId)` for events with reliable source IDs;
- `(tenantId, orderId, revision)` when processing order revisions;
- `paymentRequestId` for payment actions where the partner supports idempotency;
- `(fileSource, fileBusinessId, contentVersion)` when files carry explicit versions.

Do not default to Spring `MessageHeaders.ID`, Kafka offsets, filenames, or correlation IDs as universal business deduplication keys. Their scopes and lifecycles differ.

### 8.2. Transactional Idempotency Pattern

~~~text
receive(message):
    key = stableBusinessKey(message)
    validate(message)

    begin database transaction
        if processed_message(key) already committed:
            commit
            return ALREADY_PROCESSED

        applyBusinessMutation(key)
        insertProcessedKeyWithUniqueConstraint(key)
        insertOutboxEvent(key, outboundEvent)
    commit

    # Ack source per adapter semantics.
    # Outbox worker publishes independently with idempotent retries.
~~~

To prevent race conditions when two workers receive the same key concurrently, enforce a **unique constraint / proper transaction isolation or lock**; SELECT before INSERT is insufficient. If an outbound side effect runs **outside** the DB transaction, separate idempotency or reconciliation is required.

### 8.3. Timeouts Create Unknown-Outcome States

A POST, publish, or commit that times out **after sending** may have succeeded. When unsure:

1. Record `UNKNOWN_OUTCOME` along with the business key.
2. Query the external system via status API/reconciliation where available.
3. If the target supports idempotency, retry using the **exact same key**.
4. If unsupported, route to owner verification or a compensating workflow.
5. Never treat a timeout as proof of "not executed".
6. Once outcome is clarified, update state and ack/replay per contract.

## 9. Spring Integration: Advice, `errorChannel`, and Retry Placement

Spring Integration processes messages across endpoints and channels. Retry logic may live as **handler advice** or inside the **source/listener/container**, depending on the pattern.

### 9.1. `RequestHandlerRetryAdvice`

`RequestHandlerRetryAdvice` can wrap a **message handler** to retry when it throws configured exceptions. It does not automatically provide source redelivery, transactions, or idempotency.

**Spring Retry + Spring Integration example (illustrating config for an idempotent remote call such as GET):**

~~~java
import java.net.SocketTimeoutException;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean
RequestHandlerRetryAdvice idempotentReadRetryAdvice() {
    RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(4)
            .exponentialBackoff(500L, 2.0, 5_000L, true)
            .retryOn(SocketTimeoutException.class)
            .build();

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

This snippet illustrates **max attempts, randomized exponential backoff, and retryable exception class**. Whether `SocketTimeoutException` surfaces directly or wrapped depends on the handler/client: build an exception classifier and test cause chains for your Spring Retry version. Also verify the builder/API against your **exact Spring Retry version** before compiling.

**Never attach this advice unconditionally to a non-idempotent POST handler** or one that already executed multiple side effects. Even when advice is technically configured right, the wrong retry scope still duplicates effects.

### 9.2. Choosing Where to Place Advice

| Location | When Appropriate | Avoid |
|---|---|---|
| Handler performing only GET/lookup | Can retry transient read errors in place | Blocking connections/threads across long backoffs |
| Outbound handler with idempotency key | Retrying per remote contract | Generating a fresh request ID per attempt |
| Handler updating DB | Transaction retries for verified serialization/deadlocks | Retrying whole handler after outbound already fired |
| Inbound poller | Retrying source fetch after transient faults | Causing scan loops and duplicate files/rows |
| JMS/AMQP listener container | Let broker redeliver per ack/transaction | Layering advice + broker retries multiplicatively |
| Kafka listener | Error handlers/retry topics per record/partition | Assuming DLT leaves ordering unaffected |

### 9.3. `ErrorMessage` and Error Channels

In Spring Integration:

- Synchronous `DirectChannel` allows exceptions to bubble back to the sender, influencing rollback/ack.
- For pollers, executors, or async listeners, error handling may use `ErrorMessage`, error channels, and configured handlers.
- Recovering an exception by logging and returning can trick the source into treating a failed operation as successful.
- An error channel is **not** a durable DLQ by default, nor does it automatically retry.
- Know explicitly whether errors are **rethrown, recovered, or persisted to a verified durable store** before upstream acks.

**Review question:** After attempts exhaust, who owns the message, where is it persisted, who will replay it, and has the source acknowledged yet?

### 9.4. One Policy for All Endpoints Is an Anti-Pattern

SFTP `stat` failures, HTTP 503, JMS redelivery, Kafka commits, and JDBC deadlocks have different boundaries. Define policies per **adapter/operation**, or at minimum per error category and side-effect class—never reuse one `RetryTemplate` everywhere just for convenience.

## 10. HTTP Adapters and Gateways: Classify by Status + Operation

HTTP outbound is where retries most easily duplicate side effects, because the server may have completed processing before the response was lost.

### 10.1. HTTP Matrix

| Result | Error Category | Recommended Policy | Condition |
|---|---|---|---|
| **200/201/202** | Contract success | Do not retry | For 202, track async status |
| **400/422** | Payload/business validation | Do not retry same payload | Quarantine or return error to caller |
| **401** | Authentication | Refresh valid credentials once per workflow, bounded | Never use infinite refresh loops |
| **403** | Authorization | Do not retry | Fix permissions via controls; never bypass |
| **404** | Resource not found | Usually do not retry | Retry only when API guarantees eventual consistency |
| **408** | Server request timeout | Conditional retry | Must know whether side effects occurred |
| **409** | Conflict | Do not retry as-is by default | May reread/recompute if optimistic locking conflict |
| **412** | Precondition failed | Reread state and re-evaluate | Never strip `If-Match` conditions |
| **425** | Too Early | Retry only per API and protocol semantics | Watch out for unsafe operations |
| **429** | Rate limited | Bounded retry, honor `Retry-After` if present | Use shared limiter for tenant-level quotas |
| **500** | Server error | Often transient retry candidate | Protect POST/side effects with idempotency |
| **502/503/504** | Gateway/downstream unavailable | Bounded retry/backoff | Response may have been lost after commit |
| **Network reset / connect refused** | Transport | Conditional retry | Distinguish pre-send from post-send |
| **Client read timeout** | Transport/unknown outcome | Prefer reconciliation if side-effecting | Timeout does not prove server didn't execute |
| **Invalid TLS certificate** | Security/config | Fail, alert | Never disable hostname verification |

### 10.2. Idempotency by HTTP Method

- **GET/HEAD:** Typically safe regarding business effects, though real APIs still enforce rate limits and indirect effects; bounded retries fit transient failures.
- **PUT/DELETE:** Idempotent in HTTP specs, though implementations may attach side effects; verify contracts.
- **POST/PATCH:** Not idempotent by default. If the API supports `Idempotency-Key` or business request IDs, keep the same key across all attempts; otherwise use status queries/compensation instead of blind retries.
- **202 Accepted:** Means accepted for async processing; do not retry just because the business result isn't ready yet. Poll status endpoints or await callbacks.

### 10.3. Deadlines and `Retry-After`

If the ingress gateway has only 3 seconds left while a partner returns `Retry-After: 30`, do not hold the request thread for 30 seconds. Return the contract-appropriate response and offload retries to a durable queue if allowed, or fail/alert cleanly.

**HTTP Checklist:**

- [ ] Policies vary by status, operation, idempotency, and side-effect state.
- [ ] Connect/read/pool acquisition timeouts are bounded and fit the retry budget.
- [ ] `Retry-After` is parsed, capped, and monitored.
- [ ] Never retry 400/422/403/certificate errors with the identical request.
- [ ] Circuit breakers/bulkheads protect degrading APIs from retry storms.
- [ ] POST retries require an idempotency contract or reconciliation.
- [ ] Timeouts after remote commit are tested with stable request IDs.
- [ ] Inbound APIs return accurate statuses and never claim success prematurely.
- [ ] Client timeouts, gateway reply timeouts, and proxy deadlines never conflict.

## 11. File Inbound/Outbound: Retries Do Not Always Involve Networks

The File adapter interacts with filesystems. Failures include **incomplete files**, **permission denied**, **disk full**, **invalid schemas**, or **business effects committed before file archiving**.

### 11.1. Grouping File Errors into Four Categories

| Error | Retry? | Mitigation |
|---|---|---|
| Producer still writing file | **Wait for readiness**, do not parse yet | Temporary filename/ready marker, stable-size check per contract |
| Transient filesystem/network-mount I/O | Conditional | Bounded retry, infrastructure alert |
| Permission denied, bad path, disk full | No tight-loop retry | Fix permissions/capacity, alert and pause if needed |
| Invalid CSV/JSON schema | No retry with same bytes | Quarantine, notify producer |
| File parsed, business commit failed | Retry per transaction/side effect | Retain file and business key for re-drive |
| Business committed, DONE move/rename failed | Do not blindly re-run business logic | Reconcile processed state then archive |
| Oversized file or path traversal | Fail/security action | Enforce file/path limits, quarantine appropriately |

### 11.2. Accept-Once Filter Differs from Business Idempotency

An `AcceptOnceFileListFilter` or persistent metadata filter avoids re-picking previously seen files as configured. However:

1. A file may be marked accepted **before** the business handler finishes.
2. The app can crash after ingesting but before DB commit.
3. A file's contents may change under the same filename.
4. Multiple pods may see the same file if stores/claims aren't shared properly.
5. If metadata is wiped, files can be re-polled.

**Safe design:** File-ready protocol + source metadata/filter + durable business processing state + idempotency key + archive/quarantine states. Never treat a filter as an end-to-end exactly-once guarantee.

### 11.3. File Outbound and Overwrites

When retrying file creation after timeout/I/O failures, determine whether the target file already exists and is complete. Use deterministic filenames, temp-write + rename, or checksums/manifests. Never retry by generating a new random filename for the same business event, or consumers may process both copies.

**File Checklist:**

- [ ] Track ready/processing/done/failed states with crash recovery.
- [ ] Data-invalid files are never polled endlessly.
- [ ] Temporary retries do not break ordering when required.
- [ ] Business commit status—not just filter state—determines completion.
- [ ] Tested files that committed DB but failed archiving.
- [ ] Shared/network filesystem locking and I/O failure semantics are verified.

## 12. SFTP: Distinguish Transfer Failures, Metadata, and Existing Targets

### 12.1. SFTP Error Classification

| Error | Decision |
|---|---|
| Connection reset, remote session closed, temporary timeout | Bounded retry with reconnect and backoff |
| Server overloaded or session limit reached | Reduce concurrency and wait longer with jitter |
| SSH host key mismatch | **Never retry to bypass**; fail security check |
| Authentication failed, private key expired | No tight-loop retry; rotate credentials and alert |
| Remote path does not exist | Usually fail/alert; retry only if producer contract creates folders lazily |
| Permission denied | Fail/config fix; do not retry as-is |
| Remote file unready or uploading | Wait for ready marker/rename; do not treat as corrupt |
| Partial download | Retry/resume per client support; verify checksum/content |
| Upload/rename timeout after server write | Reconcile remote file/path before retrying |
| Downloaded file fails parsing | Quarantine data; do not endlessly retry network |

### 12.2. Poller- and Session-Pool-Friendly Backoff

If poll interval is 5 seconds, session pool has 5 connections, and the remote server is down for 30 minutes, replicas hammering reconnects can overwhelm the server on recovery. Require:

- Bounded retries at client or poller per contract;
- Reconnect backoff with jitter;
- Circuit breakers or pausing endpoints during extended outages;
- Capped concurrent transfers and inflight files;
- Persistent metadata/claims across replicas;
- Alerts on oldest pending file and session failure rates;
- Resume/re-drive runbooks once the partner recovers.

### 12.3. Upload Resume and Ambiguous States

An SFTP upload can succeed while the client loses the `rename` response. Do not immediately pick a new filename or write a duplicate file. Check:

1. Does the temporary path still exist?
2. Has the final path appeared?
3. Do file size/checksum/manifest match?
4. Has the consumer already processed the destination file, and is deduplication present?
5. Could a retry overwrite a file from a different version?

**SFTP Checklist:**

- [ ] Host-key verification, session timeouts, and retry/backoff are explicit.
- [ ] File-ready protocol is agreed with the partner.
- [ ] Idempotency tracks source + file/version or business records.
- [ ] Auth/permission/host-key errors are separated from transient network errors.
- [ ] Recovery handles downloaded files whose business processing failed.
- [ ] Runbook covers verifying remote upload outcomes.

## 13. JMS: Redelivery Belongs to Broker/Container, Not Just Handler Advice

With JMS listeners, **exception propagation**, transactions, and acknowledgement modes determine whether the broker redelivers. This differs significantly from retrying a plain Java method.

### 13.1. Sequence to Understand

~~~text
JMS broker -> listener receives message
              |
              +-> business handler begins
              +-> DB commit successful
              +-> listener/process crash before JMS ack
              |
JMS broker redelivers (per session/transaction policy)
              |
              +-> consumer idempotency avoids duplicate business effect
~~~

**If the handler committed DB before ack completed**, no amount of "increasing timeout" turns this into exactly-once. Idempotency is mandatory.

### 13.2. JMS Checklist

- [ ] Transacted session / acknowledgement mode and actual ack timing are defined.
- [ ] Pick a single retry owner: handler advice **or** broker redelivery; avoid unintended multiplicative attempts.
- [ ] Broker/JMS provider has verified redelivery limits and DLQ policies.
- [ ] Schema-invalid poison messages do not redeliver forever.
- [ ] Transient DB errors have a retry budget compatible with transactions/acks.
- [ ] Listener concurrency/prefetch does not exhaust connections or break ordering.
- [ ] Request/reply gateways enforce reply timeouts and late-reply handling.
- [ ] Idempotency keys hold across multiple broker redeliveries.
- [ ] Audits and metrics track redelivery counts/age, DLQ backlogs, and pending queues.
- [ ] Tested broker restarts and listener crashes before/after commit/ack.

### 13.3. Never Swallow Exceptions When Redelivery Is Desired

A handler might catch and only log:

~~~java
try {
    processBusiness(message);
} catch (Exception ex) {
    log.warn("processing failed", ex);
    // Do not rethrow
}
~~~

In many listener setups, returning normally causes the container/broker to acknowledge the message despite business failure. If recovery intends to **persist durably to quarantine** and then ack, prove quarantine persistence succeeded first. Otherwise, let exceptions propagate per rollback/redelivery rules.

### 13.4. JMS Request/Reply

If a JMS gateway times out waiting for a reply:

- The consumer may still be processing the request.
- A late reply may arrive after the gateway dropped correlation.
- Retries must carry the same business ID/idempotency contract.
- Do not raise redelivery and gateway retries together without summing total attempts.
- For slow work, move to durable async request/status instead of synchronous RPC.

## 14. AMQP/RabbitMQ: Publisher Retries, Consumer Requeues, and DLQ

### 14.1. Producer Publishing Has Its Own Retry Semantics

A publisher can send a message and lose its connection **before receiving a broker confirm**. Missing a confirm does not mean the broker rejected or missed the message. Retrying publish can create duplicates, so:

- Use stable message/business IDs;
- Handle publisher confirms/returns where required by topology;
- Log/reconcile ambiguous publishes;
- Keep downstream consumers idempotent;
- Never generate a new random ID on retry for the same event;
- Maintain an outbox or delivery ledger if recovery across restarts is required.

### 14.2. Consumer Acknowledgement

| Reaction on Handler Failure | What Can Happen | Control |
|---|---|---|
| **Nack/requeue** | Broker redelivers record, potentially immediately | Bounded policy/backoff, prevent loops |
| **Reject without requeue** | Routes to DLX/DLQ if topology supports it; otherwise may be dropped | Ensure DLQ is configured, monitored, and retains details |
| **Ack after recovery** | Broker considers processing complete | Only after durable persistence of valid fallback state |
| **No ack due to crash** | Redelivery after connection/channel closes | Idempotent consumer |
| **Retry advice on listener** | Repeats handler within one delivery | Do not combine blindly with broker requeues |

### 14.3. Delayed Retry Mechanisms

Depending on broker/topology, you can use TTL + dead-letter exchanges, supported delayed-message plugins, or an application scheduler/queue to defer messages. Verify:

- Actual delay and ordering behavior;
- Message expiration and retention;
- Where attempt counts are stored;
- Whether poison messages eventually reach the final DLQ;
- Whether missing DLX/target queues drop messages silently or handle them safely;
- What happens if retry workers/publishers crash;
- Whether retries affect the primary queue or cause head-of-line blocking.

**AMQP Checklist:**

- [ ] Publisher confirms/returns and unknown outcomes are handled.
- [ ] Consumer ack/requeue/reject policies are explicit.
- [ ] Error handlers never infinitely requeue poison messages.
- [ ] DLQ, retention, replay runbook, and alerts exist.
- [ ] Backoff/delayed retries do not flood the broker.
- [ ] Consumers are idempotent with tuned prefetch/concurrency.
- [ ] Tested crashes after DB commit before ack and lost confirms.

## 15. Kafka: Separate Producer Retries from Consumer Record Retries

### 15.1. Kafka Producer

Kafka producers provide retries, acknowledgements, idempotence, and delivery limits per Kafka client semantics; they cannot make external DB/HTTP side effects safe on their own.

| Scenario | Rule |
|---|---|
| Metadata/broker temporarily unavailable | Client retries per policy when eligible; bound block/delivery timeouts |
| Kafka producer delivery timeout | Callback receives error; record state on broker may be ambiguous |
| Producer idempotence enabled | Reduces duplicates from producer retries within scope; does not protect if app generates new event IDs |
| Outbox worker retries publish | May double-publish if broker received message before ack loss; consumers must stay idempotent |
| Schema/serialization error | Usually permanent record failure; quarantine/fix schema instead of infinite sends |
| ACL/authentication error | Fail/alert; no tight-loop retries; fix permissions/credentials via process |

**Note:** Parameters such as `retries`, `delivery.timeout.ms`, `request.timeout.ms`, and `retry.backoff.ms` have specific semantics and constraints per Apache Kafka client version. Do not wrap an external `RetryTemplate` around a producer and treat it as the sole delivery mechanism.

### 15.2. Kafka Consumer

For Kafka listeners, Spring for Apache Kafka provides error handlers/retry topics/DLTs depending on version—such as `DefaultErrorHandler` or `DeadLetterPublishingRecoverer`. In Spring Integration, identify **which listener container** the Kafka inbound adapter uses, who owns error handling, and when offsets are committed.

| Error | Typically Appropriate Handling |
|---|---|
| Network/broker outage | Controlled reconnect/client retry, alert |
| Deserialization/schema error | Per-record error recovery/quarantine without poisoning partition forever |
| Transient DB timeout | Bounded in-transaction retry or suitable retry topic |
| Permanent business validation | DLT/quarantine per contract and offset policy |
| Recurring handler bug | Bounded attempts; alert owner to fix code |
| DB commit succeeded, offset uncommitted | Consumer idempotency for safe redelivery |
| Per-key ordered records | Consider blocking/retrying on partition or preserving order across retry topics |

### 15.3. Blocking vs. Non-Blocking Retries

- **Blocking retry:** Holds the record/partition at its current offset and retries after a delay, delaying subsequent records. Fits strict ordering requirements with short delays.
- **Non-blocking retry:** Moves the record to a retry topic/queue or scheduler so later records proceed. Improves throughput but can **break business ordering** if later revisions execute first.
- **DLT:** Unprocessable records move to isolation. DLT publishing must succeed durably before the main flow marks the record recovered per policy.

**Example:** OrderRevision 2 fails and moves to a retry topic; Revision 3 on the main partition processes first. If business rules require 1→2→3 ordering, retry-topic designs need version gating or per-business-key blocking.

### 15.4. Kafka Checklist

- [ ] Producer retries/delivery timeouts/idempotence/acks are verified.
- [ ] Consumer error handling lives in one layer without stacked retries.
- [ ] Deserialization/schema errors are separated from transient handler failures.
- [ ] DLT/retry topics have owners, ACLs, retention, partition/key policies, and alerts.
- [ ] Once routed to DLT, offsets commit cleanly and failed DLT publishes do not drop records.
- [ ] Consumer DB side effects are idempotent.
- [ ] Tested lost producer confirms/acks, rebalances, and crashes after DB commit.
- [ ] Partition/business-key ordering is preserved or deviations are approved.

## 16. JDBC/Database: Retry Transactions, Never Blindly Retry Whole Flows

JDBC faces network errors, deadlocks, serialization conflicts, lock timeouts, unique constraints, and schema/permission faults. In Spring applications, exceptions may be translated into the `DataAccessException` hierarchy or surface as `SQLException` with `SQLState` and vendor error codes.

### 16.1. Database Error Classification

| Error | Retry? | Condition |
|---|---|---|
| DB-detected deadlock | Usually yes | Bounded retry of the **whole transaction** without repeating external side effects |
| Serialization/concurrent update conflict | Conditional | Reread state and recompute, optimistic locking |
| Lock wait/query timeout | Conditional | Tune contention/queries; avoid retry storms |
| Connection reset before execution | Conditional | Retry on a fresh connection with idempotency |
| Connection loss during commit | **Unknown outcome** | Reconcile DB state via business key |
| Unique constraint/business duplicate | Do not retry raw insert | Idempotent success or conflict review |
| Missing table/invalid SQL | No | Fix schema/migration/code |
| Permission denied/invalid auth | No tight-loop retry | Security/credential process |
| Disk full/quota/DB overload | No immediate tight retries | Shed load, alert, defer retry |
| Business constraint violation | No | Fix data or rules; quarantine |

Under standard SQLState codes, classes like **08 (connection exception)** and **40 (transaction rollback)** often help classify transient faults; **23 (integrity constraint violation)** and **42 (syntax/access rule)** generally do not warrant blind retries. Error reporting and codes vary by database/driver—review against your exact vendor.

### 16.2. Retry at the Proper Transaction Boundary

One design approach:

~~~text
retryableDatabaseOperation():
    for attempt in boundedAttempts:
        begin NEW transaction
            read latest state
            validate state transition
            write row with uniqueness/business version
        commit
        if success:
            return
        if transient deadlock/serialization conflict:
            backoff then retry
        else:
            fail

after committed transaction:
    outbox worker publishes external event
~~~

**Never** open one DB transaction and retry SQL statements inside it after it has been marked rollback-only. Each attempt needs a fresh transaction and must reread state when needed. Avoid calling HTTP/SFTP or publishing broker events directly inside a multi-retry block.

### 16.3. Which Window Does Transactional Outbox Solve?

If a business DB commits but broker publishing fails, retrying the **entire handler** can write to the DB a second time. With an outbox, the business row and outbox event commit in the same transaction. A separate worker publishes events with adapter/broker retries, tracking status in a ledger alongside idempotent consumers.

### 16.4. JDBC Checklist

- [ ] Driver/pool/query timeouts fit the retry budget.
- [ ] Error classification via `DataAccessException`, SQLState, or vendor codes is tested.
- [ ] Deadlock/serialization retries happen at the transaction boundary with a clear owner.
- [ ] Unique constraints block concurrent duplicate business keys.
- [ ] Connection loss during commit is reconciled before retrying.
- [ ] Never retry SQL syntax/constraint/permission errors with the same input.
- [ ] Never hold DB locks across backoffs or remote API calls.
- [ ] Metrics track deadlocks, lock waits, pool waits, query timeouts, and exhausted retries.
- [ ] Tested multi-worker concurrency, DB failover, and ambiguous commit outcomes.

## 17. Scheduled Retries, DLQ/Quarantine, and Durability Across Restarts

### 17.1. When to Move Retries Off the Current Thread

| Scenario | Recommended Approach |
|---|---|
| HTTP GET transient fault expected to recover in seconds | Bounded in-place handler/client retry within SLA |
| HTTP 429 asking for 60 s wait when inbound deadline is 15 s | Durable retry job/queue; return valid async status |
| SFTP server offline for hours | Pause poller + backoff/reconnect per runbook; retain upstream files |
| JMS/AMQP data-error message | Bounded redelivery then DLQ |
| Kafka poison record | Recovery/DLT respecting ordering policy |
| Brief DB lock conflict | Short, bounded transaction retry |
| Payment partner timeout after possible commit | Unknown-outcome reconciliation before retrying |
| Consumer bug requiring hotfix | Quarantine, owner fixes bug, approved replay |

### 17.2. Durable Retry Record

A retry record should store:

- Stable business key / source event ID, tenant, and operation type;
- Target/protocol/endpoint alias (never raw secrets);
- Durable payload or reference governed by retention/PII policies;
- Error category and redacted technical cause;
- Current attempt count, max attempts, `nextAttemptAt`;
- Deadline/expiry and expiration policy;
- Idempotency key, expected business version, prior outcome;
- Correlation ID, source offset/file marker, owner/reviewer;
- Status: `PENDING`, `LEASED`, `SUCCEEDED`, `QUARANTINED`, `UNKNOWN_OUTCOME`;
- Audit trail whenever workers claim, retry, recover, replay, or delete.

Multiple instances require **distributed claims/leases** with expiry/recovery. If a worker dies after calling a remote target but before marking success, another retry worker will pick it up—side effects must be idempotent.

### 17.3. DLQ Differs from a Retry Queue

- **Retry queue:** Holds retryable operations with scheduled next attempts and remaining budgets.
- **DLQ/DLT:** Holds messages that exhausted retry policies or cannot self-recover on the active path.
- **Quarantine:** Isolates contract-invalid, sensitive, or uncertain payloads awaiting owner decisions.
- **Unknown-outcome store:** Used when actual side effects of a risky action are unconfirmed and need reconciliation.

Do not assume every DLQ message should be replayed immediately after a service restart. Contracts or business states may have shifted, or partial side effects may already exist.

## 18. Observability, Load Limits, and Security During Retries

### 18.1. Essential Log Fields

| Field | Why It Matters |
|---|---|
| `eventId` / idempotency key | Links retry attempts for the same request |
| `correlationId` / trace ID | Traces ingress → handler → outbound |
| `source`, `target`, `adapterType` | Identifies which partner/broker/DB failed |
| `errorCategory`, exception type/status | Classifies transient, permanent, unknown |
| `attempt`, `maxAttempts` | Shows whether retries remain |
| `elapsedMs`, `remainingBudgetMs` | Explains why retries aborted |
| `backoffMs`, `retryAfter` | Detects retry bursts |
| `sideEffectState` | Not called / in progress / committed / unknown |
| `ackState` / offset / file checkpoint | Investigates redelivery or data loss |
| `recoveryTarget` | Retry queue, DLQ, quarantine, or incident |
| `instanceId`, handler/client version | Pinpoints issues by replica/deployment |
| `outcome`, `owner`, `ticket` | Tracks final resolution |

Never log tokens, passwords, SFTP private keys, JDBC credentials, Authorization headers, session cookies, or sensitive payloads. In particular, **DLQ/DLT is not an open-access data store**: enforce ACLs, encryption, and retention.

### 18.2. Metrics and Alerts

| Metric | Signal to Investigate |
|---|---|
| Retry attempts by target and error category | Sudden spikes or sustained elevation |
| Retries exhausted | Operations out of budget |
| Backoff wait p50/p95 | Many workers sleeping/throttled |
| Timeout/429/503/5xx rates | Dependency degradation |
| Unknown outcome count and age | Unverified side effects |
| Circuit breaker open duration | Prolonged dependency outage |
| Handler/integration error rate | Spikes after releases or schema changes |
| DLQ/DLT/quarantine size and oldest age | Unhandled failed messages |
| Kafka lag / JMS-AMQP queue depth | Backlog from retries or stalled sources |
| File/SFTP oldest pending file | Remote outage or stuck files |
| DB deadlocks/lock waits/pool exhaustion | Rising contention or bad retry logic |
| Deduplicated events count | Increasing producer resends or redeliveries |
| Business completion latency | Whether SLA is met |
| Dead-letter replay success/failure | Validates runbooks and idempotency |

Metrics should slice by **adapter, operation, target, exception category, and outcome**, without attaching `eventId` or `userId` as high-cardinality metric tags. Business IDs belong in access-controlled logs and traces.

### 18.3. Retry Storms and Thundering Herds

When a dependency recovers from an outage, thousands of workers may retry at once.

- [ ] Use jittered backoff and shared rate limits for tenant/API-key quotas.
- [ ] Prevent infinite retries across clients, advice, and brokers.
- [ ] Apply circuit breakers/bulkheads so threads/connections aren't exhausted.
- [ ] Enforce bounded channel queues, poller throttling, and concurrency caps.
- [ ] Monitor backlog drain rates as dependencies recover.
- [ ] Cap batch sizes and inflight counts during batch replays.
- [ ] For global quotas, use distributed limiters or cross-replica coordination.
- [ ] Never shrink retry delays solely to lower average latency in local tests.

### 18.4. Errors That Must Never Be Masked by Retries

- Invalid TLS certificates / SSH host keys;
- 403 / broker ACL denied / DB permission denied;
- Invalid schemas, unknown message versions, tampered payloads;
- Missing idempotency on payments or resource deletions;
- Leaked credentials or misconfigured partner endpoints;
- Dead-letter messages containing data requiring approval before replay.

In these cases, **fail cleanly, fire security/ops alerts, and engage owner review**—never increase attempt counts.

## 19. Fault-Injection Testing by Error Category

A policy is only production-ready after representative errors have been injected in a test environment and results **verified at the target system**—not merely by asserting an exception was caught.

### 19.1. Designing Tests

1. Pick a stable business key and representative test message.
2. Deploy adapters and dependencies in an environment faithful enough to production.
3. Inject faults at exact points: pre-send, mid-send, post-remote-commit, pre-source-ack.
4. Measure attempt counts, actual backoffs, elapsed/deadline times, and held resources.
5. Inspect business state in the target DB, file, broker, or API.
6. Verify DLQ/quarantine or retry queues have owners and complete audit records.
7. Restart workers, replay, and confirm no duplicate effects occur.
8. Repeat under multiple replicas and concurrent traffic, especially targeting the same business key.

### 19.2. Matrix of 55 Test Cases

| ID | Scenario | Expected Outcome |
|---|---|---|
| **T01** | HTTP GET hits transient connect timeout | Bounded retry + backoff; succeeds when target recovers |
| **T02** | HTTP 429 with valid `Retry-After` | Delay/rate limit honors deadline |
| **T03** | HTTP 429 with huge/malformed `Retry-After` | Value validated/capped or safely deferred |
| **T04** | Sustained HTTP 503 | Attempts exhaust; circuit opens or moves to durable retry |
| **T05** | HTTP 400 missing field | No retry; validation/quarantine records reason |
| **T06** | HTTP 422 business validation | Never retried with same payload |
| **T07** | HTTP 401 from expired token | Bounded refresh per policy; no infinite loop |
| **T08** | HTTP 403 | Fail/alert; no retry |
| **T09** | HTTP TLS hostname mismatch | Fails closed; verification never bypassed |
| **T10** | HTTP 409 optimistic conflict | Reads current state/recomputes; no blind raw retry |
| **T11** | HTTP POST commits, response times out | Reuses idempotency key or reconciles; no double charge |
| **T12** | Proxy times out before backend | Outcome audited; client retry creates no duplicate |
| **T13** | HTTP client, handler advice, and ingress all retry | Total attempts stay within budget |
| **T14** | 500 workers receive 503 simultaneously | Jitter/limiter prevents synchronized spike |
| **T15** | Request has 1 s deadline left, backoff asks for 5 s | Skips in-place retry; defers or fails |
| **T16** | SFTP TCP reset during list | Bounded retry with safe reconnect |
| **T17** | SFTP host key mismatch | Never retried to bypass; security alert |
| **T18** | SFTP authentication failed | No tight-loop retry; credential incident raised |
| **T19** | SFTP file not ready | Waits per protocol; never parses corrupt partial data |
| **T20** | Partial SFTP download, retried | No data loss or partial processing |
| **T21** | SFTP rename response times out after upload | Inspects remote checksum/state; avoids duplicates |
| **T22** | SFTP session pool overloaded | Throttles concurrency/backoff; no storm |
| **T23** | Input file has invalid schema | Quarantined; not re-polled forever |
| **T24** | File written to DB, archive fails | Reconciles business state then archives; no re-insert |
| **T25** | Files share business ID under different names | Deduplicates properly on business key |
| **T26** | File on shared volume picked up by two pods | Claims/idempotency yield exactly one effect |
| **T27** | JMS consumer killed before ack, after DB commit | Idempotent redelivery |
| **T28** | JMS poison message hits 20 redeliveries | Bounded policy routes to DLQ; queue unblocked |
| **T29** | JMS handler swallows exception | Test catches false ack and fixes propagation |
| **T30** | JMS RPC reply arrives late | Correlation handles safely; no double side effects |
| **T31** | JMS broker restarts mid-processing | Recovery/redelivery follows semantics with audit |
| **T32** | AMQP publish succeeds, confirm lost | Sender marks ambiguous; consumer idempotent |
| **T33** | AMQP consumer crashes before ack | Redelivery does not duplicate business effect |
| **T34** | AMQP poison message continuously requeued | Storm blocked; routed to DLX/DLQ |
| **T35** | AMQP target DLQ does not exist | Topology alert fires; never silently marked recovered |
| **T36** | AMQP delayed retry via TTL/DLX | Attempts/delay/ordering follow contract |
| **T37** | Kafka broker temporarily unavailable on produce | Bounded client retry, callback/delivery status |
| **T38** | Kafka producer callback times out, record reaches broker | Consumer idempotent; sender keeps original ID |
| **T39** | Kafka serialization/schema error | Quarantined; producer does not retry forever |
| **T40** | Kafka consumer hits DB deadlock | Retries at proper transaction boundary |
| **T41** | Kafka consumer commits DB, offset uncommitted | Redelivery causes no duplicate insert |
| **T42** | Failed Kafka record routed to DLT | Durable DLT, proper commit/recovery policy |
| **T43** | Retry topic runs revision 3 before revision 2 | Ordering/version guard handles properly |
| **T44** | Kafka consumer rebalances mid-retry | No lost records, stays within budget |
| **T45** | JDBC deadlock | Bounded fresh-transaction retry yields correct state |
| **T46** | JDBC serialization conflict | Reread/recompute per business version |
| **T47** | JDBC unique key conflict from duplicate event | Idempotent no-op or conflict review |
| **T48** | JDBC connection lost during commit | Reconciles DB state before retrying |
| **T49** | JDBC missing table / invalid SQL syntax | No retry; deployment alert raised |
| **T50** | JDBC pool exhausted by 200 workers | Backpressure/circuit engages; no infinite blocking |
| **T51** | Quarantine replay after schema fix | Business key prevents duplicate impact |
| **T52** | Retry worker dies after claiming job | Lease/recovery safely reprocesses |
| **T53** | Deadline expires during backoff | Halts local attempts; durable handoff if applicable |
| **T54** | Rolling pod restart with active retry queue | Pending state persists safely; no lost events |
| **T55** | Circuit breaker trips from retry storm | Stops hammering dependency; recovery policy works |

**Evidence for every test:** expected/actual results, adapter/target, error category and exception chain, business/event ID, configured policy, actual attempts, total elapsed time, side-effect state, ack/offset, DLQ record/correlation ID, tester, and open issues.

## 20. Runbook: When Retries Spike or Messages Stall

### 20.1. Diagnostic Order

1. **Identify:** Which adapter/endpoint has elevated retries, and since when?
2. **Classify errors:** Transient network, overload, schema, auth, conflict, or unknown outcome?
3. **Check source state:** Message acked? Offset committed? File marked accepted/archived?
4. **Check target state:** DB committed? HTTP remote effect executed? Kafka broker received? SFTP file present?
5. **Check retry owner:** Client, advice, listener, broker, scheduled worker, or operator?
6. **Check budgets:** Are attempts × timeout + backoff, deadlines, and max inflight safe?
7. **Assess dependencies:** Is the remote server down/rate-limiting, or did code just change schemas?
8. **Shed load:** Pause pollers, lower concurrency, trip circuit, or defer retries if needed.
9. **Recover:** Fix root cause, replay idempotently, measure business completion.
10. **Close incident:** Verify backlog drains, DLQ age drops, audit, and write postmortem.

### 20.2. Operational Decisions by Error Type

| Observation | Do Not Do | Recommended Action |
|---|---|---|
| Continuous HTTP 429 | Raise max attempts infinitely | Respect quota/`Retry-After`, rate limiter, and deferred retries |
| HTTP POST timeout | Resend with a new request ID | Query remote result or retry with same idempotency key |
| TLS/SSH host-key mismatch | Disable security verification | Halt and verify certificate/key rotation |
| Truncated/incomplete SFTP file | Retry parsing forever | Check ready protocol or quarantine |
| JMS/AMQP poison message | Requeue immediately forever | Route to DLQ + owner fixes root cause |
| Kafka lag from retrying bad record | Arbitrarily reset offsets | Classify error, recover/DLT with ordering policy |
| Frequent DB deadlocks | Only raise attempt counts | Analyze locks/queries, reduce contention, bounded transaction retry |
| DB connection lost at commit | Re-insert immediately | Reconcile by business ID and transaction state |
| Retry queue grows while success drops | Scale concurrency infinitely | Shed load, apply circuit/bulkhead, inspect dependency |
| DLQ replay fails again | Delete the message | Log failure, update policy/runbook |

### 20.3. Replay After Root-Cause Fix

- [ ] Owner confirms root cause is fixed or an exception is approved.
- [ ] Reconcile side effects for critical messages before replaying.
- [ ] Reuse the **original business key**; never swap `eventId` to "bypass deduplication".
- [ ] Test small batches and limit concurrent replays.
- [ ] Preserve ordering per business key when required by contract.
- [ ] Monitor queue/DLT/DB actual state and business completion.
- [ ] Never replay messages past TTL if the action is no longer valid.
- [ ] Delete/retire DLQ records strictly per retention and audit rules.

## 21. Case Study: SFTP → JDBC/Outbox → Kafka + HTTP

Suppose a service pulls order CSVs from SFTP every 5 minutes, normalizes data, writes to a database, emits a Kafka event, and calls HTTP to register shipping. The producer can resend duplicate files, and the partner HTTP endpoint occasionally returns 429 or times out.

### 21.1. Unsafe Initial Design

- SFTP poller scans every 2 seconds and retries immediately when remote fails.
- File parsing errors are retried the same way as network errors.
- DB inserts lack a unique constraint; retried files create duplicate orders.
- Logistics HTTP POST retries with a fresh request ID after timeouts.
- Handler publishes to Kafka right after DB commit without an outbox.
- Kafka consumer retries failed records infinitely, stalling the partition.
- No metrics for `retries_exhausted` or `unknown_outcome`.
- No replica/poller concurrency caps, causing a thundering herd when SFTP recovers.

### 21.2. Improved Design

**SFTP:** Enforces file-ready markers, host-key verification, jittered bounded reconnect backoff, and transfer limits. Parse-invalid files go to quarantine; incomplete files wait for the source instead of re-parsing endlessly. Uses distributed claims/metadata and business idempotency.

**JDBC:** Every order has a unique `(partnerId, orderId, revision)`. The transaction writes order + processed key + outbox event. Deadlocks/serialization conflicts retry **at the transaction boundary**, never wrapping remote HTTP calls.

**Kafka:** Outbox publisher retries per client/broker settings; events retain stable IDs. Downstream consumers remain idempotent. Poison records move to DLT/recovery per ordering policy.

**HTTP logistics:** 429 honors `Retry-After` within deadline; 503 uses bounded retries. When POST times out after possible remote commit, query logistics status by business shipment ID or retry with the **exact same idempotency key** if supported.

**Error flow:** Permanent schema faults → quarantine; transient network faults → retry/backoff; unknown outcomes → reconciliation queue; exhausted retries → DLQ/ticket; owner maintains a replay runbook. In all cases, never ack or archive files until contractual business obligations are secured.

### 21.3. Illustrative Budget Choices

| Operation | Attempts | Per-Attempt Timeout | Backoff | Constraint |
|---|---:|---:|---|---|
| SFTP list on transient error | 3 | 5 s | 1 s, 2 s + jitter | Pause poller on prolonged outage |
| JDBC transaction deadlock | 3 | 4 s | 100 ms, 300 ms + jitter | Retry in fresh transaction |
| Kafka outbox publish | Per producer + worker policy | Depends on delivery timeout | Bounded/backoff | Stable event ID, consumer dedupe |
| HTTP GET status lookup | 3 | 3 s | 0.5 s, 1 s + jitter | Only within remaining deadline |
| HTTP POST logistics with idempotency key | 2 | 4 s | 1 s + jitter | Same key; verify if ambiguous |
| HTTP POST without idempotency | No blind retry | 4 s | Do not auto-retry | Reconcile or manual review |

These are **hypothetical numbers**, not standard thresholds. Real projects must measure p95/p99 latencies, rate limits, transaction costs, SLOs, and each system's idempotency capabilities.

### 21.4. Three Key Failure Drills

**Drill A — DB committed, worker dies before Kafka publish.** Outbox retains the event; another publisher emits it after restart. Business rows are never inserted twice.

**Drill B — Partner HTTP commits, response is lost.** Service marks unknown outcome, verifies shipment via business ID or retries with the same idempotency key; no second shipment is created.

**Drill C — SFTP network fails for 20 minutes, then recovers.** Poller throttles/pauses cleanly without launching thousands of simultaneous reconnects. Pending files are processed without loss or duplication.

### 21.5. Acceptance Criteria

- Retries occur only for eligible errors and safe operations.
- Every error category has a recovery path and owner.
- No lost or duplicate orders across crash/retry tests.
- Kafka/JMS/AMQP redeliveries produce no duplicate business effects.
- SFTP/files never vanish when parsing or DB commit fails.
- Timeouts and `Retry-After` never breach synchronous SLAs.
- Backlogs, DLQ, and unknown-outcome queues are actively monitored.
- Replay runbooks and rollbacks are tested with representative data.

## 22. Retry Policy Review Configuration Template

This is an **illustrative application-defined YAML format**, not properties automatically bound by Spring Integration/Spring Boot. The engineering team must bind, validate, and enforce it in the corresponding adapters/clients/error handlers.

~~~yaml
flow: supplier-orders
owner:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

retryPolicies:
  http-read:
    operation: idempotent-GET
    transientCategories: [NETWORK, HTTP_429, HTTP_503]
    maxAttemptsIncludingFirst: 3
    perAttemptTimeout: 3s
    backoff:
      type: exponential-full-jitter
      initial: 500ms
      max: 5s
    deadlineSource: inbound-request
    exhaustedAction: durable-retry-or-fail

  logistics-create:
    operation: POST
    idempotencyKey: partner-orderId-shipmentRevision
    transientCategories: [HTTP_429, HTTP_503, NETWORK_TIMEOUT]
    maxAttemptsIncludingFirst: 2
    backoff:
      type: retry-after-then-jitter
      max: 10s
    ambiguousOutcome: verify-by-shipmentId
    exhaustedAction: UNKNOWN_OUTCOME_QUEUE

  sftp-read:
    operation: DOWNLOAD
    transientCategories: [NETWORK_RESET, SESSION_CLOSED]
    permanentCategories: [HOST_KEY_MISMATCH, AUTH_FAILED, ACCESS_DENIED]
    maxAttemptsIncludingFirst: 3
    backoff:
      type: exponential-jitter
      initial: 1s
      max: 30s
    exhaustedAction: pause-and-alert

  jdbc-transaction:
    operation: BUSINESS_TRANSACTION
    transientCategories: [DEADLOCK, SERIALIZATION_FAILURE]
    maxAttemptsIncludingFirst: 3
    backoff:
      type: exponential-jitter
      initial: 100ms
      max: 1s
    duplicatePolicy: unique-business-key
    exhaustedAction: fail-to-source-retry-policy

  kafka-consumer:
    operation: PROCESS_RECORD
    transientCategories: [DB_TEMPORARY_FAILURE]
    permanentCategories: [INVALID_SCHEMA]
    maxAttemptsIncludingFirst: 4
    exhaustedAction: DLT
    orderingConstraint: preserve-order-per-business-key

controls:
  failOnUnknownCategory: true
  deduplicateByBusinessKey: true
  maxInflightPerTarget: REVIEW_REQUIRED
  circuitBreaker: reviewed-per-target
  auditDecision: true

approval:
  businessOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

**Note:** This template expresses intent; actual `errorCategory` mappings, jitter algorithms, and behaviors must be implemented and tested in real connector code. Do not switch to GO while `REVIEW_REQUIRED` or `PENDING` remains.

### 22.1. Per-Handler Policy Checklist

| Item | Question to Answer |
|---|---|
| Error classifier | Which exceptions/status codes/SQLStates does it inspect? Does it unwrap causes? |
| Operation | Read or write? Are side effects idempotent? |
| Retry owner | Client, handler advice, container, broker, or worker? |
| Attempts | Does the count include the initial attempt? What is the cap? |
| Per-attempt timeout | Which connection/pool/read/query stages are covered? |
| Backoff | Fixed/exponential/jitter/`Retry-After`, and with what cap? |
| Deadline | Does synchronous SLA still have room before retrying? |
| Ordering | Is there risk of overtaking later records/revisions? |
| Transaction/ack | What state is the source message in during retry/recovery? |
| Exhaustion | How are DLQ/quarantine/unknown-outcome/fail handled? |
| Visibility | Are logs, metrics, alerts, and correlation IDs present? |
| Recovery | Who replays, under what conditions, and where is state reconciled? |

## 23. Go/No-Go Decision and Deployment Checklist

### 23.1. Mandatory Checklist

- [ ] Error taxonomy defined for each adapter and operation.
- [ ] Permanent/auth/security errors never trigger tight-loop retries.
- [ ] Stable business IDs/idempotency keys exist with duplicate tests.
- [ ] Exactly one primary retry owner; checked for overlapping client/advice/container/broker retries.
- [ ] Attempts, per-attempt timeouts, backoff, and jitter stay within deadlines.
- [ ] `Retry-After`/rate limits/circuit breakers configured where targets support or require protection.
- [ ] Source ack/offset/file archive ties to durable business outcomes.
- [ ] Durable DLQ/DLT/quarantine and replay runbooks exist.
- [ ] `UNKNOWN_OUTCOME` and reconciliation mechanisms cover side-effecting operations.
- [ ] Guardrails protect against retry storms, queue growth, multi-replica contention, and overload.
- [ ] Metrics track retry attempts/exhausted, DLQ age, and business completion.
- [ ] Tested crashes, redeliveries, late responses, broker outages, and DB failovers.
- [ ] Owner, on-call, canary, and rollback plans are in place.
- [ ] All exceptions and sensitive policies are formally approved.

### 23.2. Acceptance Decision

| Status | Criteria |
|---|---|
| **GO** | Errors classified, idempotency/recovery tested, SLOs and security met |
| **GO WITH EXCEPTION** | Scoped exception with approved owner, expiration, and mitigations |
| **HOLD / RETEST** | Missing fault-injection results or unverified retry/ack semantics |
| **NO-GO** | Retries duplicate side effects, drop messages, bypass security, or lack recovery paths |

Never use "GO WITH EXCEPTION" to excuse retrying non-idempotent financial POSTs or accepting known data loss without adequate compensating controls.

## 24. Common Anti-Patterns

**Retrying every exception:** schema errors, 403s, and network glitches get identical handling; adds load without ever fixing root causes. Enforce policy-based error classification.

**One `RetryTemplate` for all adapters:** JMS redelivery, Kafka offsets, HTTP requests, and JDBC transactions have distinct boundaries. Scope policies per operation and side effect.

**Multi-layer retries without a budget:** 3 client attempts × 4 handler × 5 broker explodes total calls. Designate a single retry owner.

**Exponential backoff without jitter:** hundreds of replicas recovering together crash the dependency again. Add jitter, rate limiters, and circuit breakers.

**Assuming timeout means never sent:** HTTP/AMQP/Kafka may have executed even if the caller missed the response. Record unknown outcomes and reconcile.

**Changing the idempotency key on each attempt:** turns one logical request into multiple new commands; keep keys stable.

**Catching exceptions only to log them:** can make containers/sources ack failed messages as successful. Define rollback/rethrow/recovery behavior explicitly.

**Retrying an entire handler spanning DB + HTTP + broker:** an earlier attempt may already have committed partial effects. Separate transaction/outbox boundaries.

**Sleeping for minutes inside HTTP threads or pollers:** starves threads and connection pools. Offload to scheduled durable retries.

**Using Kafka retry topics while forgetting ordering:** later revisions overtake failed earlier ones. Enforce per-key/version gating.

**Infinitely requeuing RabbitMQ poison messages:** wedges brokers/consumers. Bound attempts and route to DLQ.

**Treating a File accept-once filter as exactly-once:** filters do not prove DB commits succeeded. Enforce business idempotency and recovery.

**Retrying JDBC deadlocks inside a rollback-only transaction:** open a fresh transaction and reread state.

**Raising `maxAttempts` to solve every outage:** inflates latency and load. Shed load, alert, and fix the underlying fault.

**Wiping the DLQ after service recovery:** destroys evidence and replay capability. Govern with retention, ownership, and audits.

## 25. Self-Check and Reference Material

### 25.1. Review Questions

1. How do in-place retry, broker redelivery, and manual replay differ?
2. Why is an HTTP 503 generally retryable while an HTTP 422 usually is not?
3. When HTTP 401 occurs, when is retrying valid? Why is 403 different?
4. How must `Retry-After` be evaluated against deadlines?
5. Why does `maxAttempts=4` typically produce only three backoff intervals?
6. What problem does adding jitter solve when many replicas fail simultaneously?
7. When an exception is wrapped in `MessageHandlingException`, what must the classifier do?
8. Why doesn't `RequestHandlerRetryAdvice` automatically guarantee idempotency?
9. When a handler fails and the error handler only logs and returns, how can source acks go wrong?
10. When an SFTP download succeeds but parsing/DB commit fails, should the file be removed from the source?
11. Why can't an HTTP POST timeout prove the receiver didn't create the resource?
12. How does JMS broker redelivery differ from handler-advice retries?
13. Does a lost AMQP publisher confirm prove the broker never received the message?
14. How do Kafka producer retries and Kafka listener error handlers differ in responsibility?
15. How can Kafka retry topics/DLTs affect per-key ordering?
16. At which boundary should a DB deadlock be retried?
17. Why is a unique constraint stronger than a SELECT check before INSERT?
18. When the same exception is retried by client, advice, and broker, how do you calculate total attempts?
19. When should you use durable scheduled retries instead of sleeping in a thread?
20. What evidence proves a DLQ replay will not duplicate business effects?

**Answer hint:** For each scenario, trace **error category → operation safety → retry owner → attempts/backoff/deadline → side-effect and ack boundaries → final outcome reconciliation**.

### 25.2. Glossary

| Term | Meaning |
|---|---|
| **Transient / permanent** | Recoverable error / error requiring data, config, or code fixes |
| **Retry policy** | Rules governing eligibility, count, and placement of retries |
| **Backoff** | Waiting interval between retry attempts |
| **Jitter** | Randomizing delays to prevent synchronized retry bursts |
| **Retry-After** | Server signal indicating when a client may retry |
| **Retry budget / deadline** | Cap on attempts and remaining flow time |
| **Idempotency key** | Key enabling safe reprocessing without duplicate business impact |
| **Unknown outcome** | Uncertain whether the receiver completed the side effect |
| **ErrorMessage / errorChannel** | Spring Integration's error notification/handling mechanism |
| **RequestHandlerRetryAdvice** | Advice wrapping a handler with policy-driven retries |
| **DLQ / DLT / quarantine** | Storage for failed or unrecoverable messages |
| **Redelivery** | Source/broker re-dispatching an incomplete message |
| **Circuit breaker / bulkhead** | Halting calls to failing dependencies / capping occupied resources |
| **Transactional outbox** | Recording event-publish obligations in the business DB transaction |
| **Reconciliation** | Verifying actual side-effect/state against desired state |
| **Poison message** | Payload causing repeated failures, requiring isolation or fixes |
| **Soak / fault-injection test** | Long-duration testing / deliberate error simulation |

### 25.3. Version-Specific Reference Documentation

- **Spring Integration Reference Guide:** Request-handler advice, polling consumers, `MessageChannel`, error handling, endpoint lifecycle, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC endpoints.
- **Spring Retry Reference:** `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, exception classification, recovery callbacks, and `RetryContext`.
- **Spring for Apache Kafka Reference:** listener container error handling, `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, non-blocking retries/retry topics, and transactions.
- **Spring AMQP Reference / RabbitMQ documentation:** publisher confirms, listener retries, consumer acknowledgements, redelivery, requeue, DLX/DLQ, and TTL.
- **Jakarta Messaging (JMS) and broker vendor documentation:** acknowledgement, transacted sessions, redelivery policies, reply destinations, and DLQ.
- **Apache Kafka Client Documentation:** producer retries/delivery timeout/idempotence, consumer offsets, group rebalances, and release-specific semantics.
- **HTTP semantics (RFC 9110) and partner API documentation:** idempotent methods, 429/5xx, `Retry-After`, request idempotency, and error contracts.
- **JDBC driver / database vendor documentation:** `SQLState`, deadlock/serialization failures, transaction rollbacks, timeouts, and unique constraints.
- **SFTP/SSH server/client documentation:** host-key verification, session recovery, file readiness, and transfer errors.

**Conclusion:** Retries and backoff are safe only when the system understands **error categories, operation semantics, and side-effect state**. For Spring Integration Adapters, pick the right retry owner, bound attempts and durations, apply jitter and backpressure, enforce idempotency, distinguish ack/redelivery across protocols, and prepare DLQs, reconciliation, observability, and runbooks. A flow is production-ready only when **retrying introduces no business inconsistencies and every failure has a tested recovery path**.
