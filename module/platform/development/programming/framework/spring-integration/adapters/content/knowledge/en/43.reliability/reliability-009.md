# Resilience When External Systems Are Slow in Spring Integration Adapters

## 1. Problem statement and learning objectives

In integration systems, an HTTP partner may take 20 seconds to respond, an SFTP server may drop connections, a Kafka/JMS/AMQP broker may overload, or a target database may hold locks for a long time. If inbound adapters keep accepting messages unchecked, waiting requests consume threads, connections, and memory, dragging down the entire application.

**Resilience when external systems are slow** is the ability to maintain safe state, control load, recover within bounds, and protect data when a dependency responds slower than expected. Resilience does not mean "retry until it works," nor does it always make response times faster; the goal is isolating failures so the system still meets its business objectives.

In the `SPRING_INTEGRATION_ADAPTERS` module, we connect externally via inbound/outbound adapters, gateways, pollers, and `MessageChannel` across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This lesson shows how to combine **timeouts, backpressure, bounded concurrency, circuit breakers, bulkheads, retries, durable queues, idempotency, and observability** without losing messages or causing duplicate side effects.

After this lesson, learners can pinpoint where slow dependencies propagate pressure, choose mechanisms tailored to each transport, design recovery flows, and realistically test success, failure, timeout, and unknown-outcome states.

## 2. Slowness differs from immediate errors

| Scenario | Observed behavior | Risk |
|---|---|---|
| HTTP immediately returns 503 | Explicit error | Retry storm if unbounded |
| HTTP holds connection for 30 seconds | Threads/connections waiting | Pool exhaustion, queued requests |
| SFTP reads several MB then stalls | Partial data transferred | Session leaks, incomplete files |
| Kafka broker acks late | Producer remains in-flight | Full buffers, timeouts, and duplicate sends |
| JMS/AMQP consumer processes slowly | Broker messages un-acked or redelivered | Lag, duplicates, continuous requeues |
| JDBC query holds locks | DB connections waiting | Deadlocks, datasource starvation |
| Partner completes processing but response is lost | Outcome `UNKNOWN` | Retrying may cause duplicate effects |

A call that throws no exception **has not necessarily met its SLA**. Separate **latency**, **availability**, **business acknowledgement**, and **outcome ambiguity**. HTTP `202` only proves the request was accepted under the API contract—not that final work succeeded. Conversely, a timeout does not prove the server never processed the call.

## 3. Pressure points in message flows

~~~mermaid
flowchart LR
    A[Inbound adapter] --> B[MessageChannel]
    B --> C[Transform / validate]
    C --> D[Outbound gateway]
    D --> E[Slow external system]
    E -.-> F[Timeout / error / unknown]
    B -.-> G[Queue / executor capacity]
    D -.-> H[Thread and connection pools]
    G -.-> I[Backpressure and admission]
    H -.-> J[Bulkhead and timeout]
    F -.-> K[Retry / reconcile / DLQ]
~~~

A synchronous `DirectChannel` flow typically holds the upstream thread while downstream handlers execute. When an outbound gateway waits on HTTP, the poller or listener can be stalled—sometimes throttling source intake, yet also stretching transactions/acks. With `ExecutorChannel` or `QueueChannel`, pressure shifts into a buffer: if the queue is unbounded, latency turns into **unbounded memory growth**; if the queue is non-durable, crashes lose work.

Questions to answer for **each segment** of a flow: how many messages may be in-flight at most, where do queues live, is data durable, who receives backpressure signals, and who owns retries?

## 4. Setting timeouts from an end-to-end budget

No single timeout fits every system. Distinguish:
- **Connection timeout**: max time to establish a connection.
- **Read/response timeout**: time waiting for data or a response.
- **Request deadline/total budget**: total cap for one attempt, including DNS, TLS, body write, wait, and body read where supported by infrastructure.
- **Transaction timeout**: time limit for a local transaction; never use it as a substitute for network timeouts.
- **Message processing deadline**: max time to drive a message to completion, retry, or escalation.

For example, consider a business flow with a 15-second SLA: validation/transform 200 ms, outbound budget 3 seconds per attempt, up to two attempts with backoff and headroom. Never configure three retries at 15 seconds each while advertising a 15-second SLA. Timeouts must align with visibility/lease durations, consumer acks, and request cancellation.

Once a request has been sent, **a timeout may be `UNKNOWN`**, not guaranteed `FAILED`. Before resending a non-idempotent operation, query by business ID or run proper reconciliation.

## 5. Retry: retry only with justification

Retry helps on transient errors such as 429, 503, or connection resets. Yet bad retries amplify partner outages. A policy must define:
1. Which errors are retryable and which are not.
2. Max attempts, per-attempt timeout, and total deadline.
3. Progressive backoff and jitter so workers do not retry in lockstep.
4. A stable idempotency key across every attempt.
5. Post-exhaustion state: delayed queue, DLT/quarantine, or manual review.
6. How to tell when the remote processed the request without the client knowing.

~~~text
attempt #1: POST order-301 -> timeout, remote status UNKNOWN
  -> query remote by business ID
  -> if already applied: mark delivered
  -> if reliably absent: retry with same idempotency key
  -> if unknown: schedule reconciliation, not unbounded retry
~~~

Avoid retrying unrecoverable authentication errors or broken payloads/schemas. Avoid retrying a JDBC transaction already marked `rollback-only` within the same transaction; give each attempt an appropriate transaction scope.

## 6. Circuit breakers and bulkheads

**Circuit breakers** cut calls to failing or chronically slow dependencies. Logical states typically include `CLOSED` (allow calls), `OPEN` (fail fast), and `HALF_OPEN` (allow limited probe requests). Error/slow-call thresholds must match real observation windows and traffic volumes.

**Bulkheads** cap concurrency per dependency so one slow provider cannot monopolize shared worker threads and connections.

| Mechanism | When needed | Does not solve alone |
|---|---|---|
| Timeout | A single request hangs too long | Does not undo remote side effects |
| Circuit breaker | Dependency repeatedly fails or slows down | Does not persist messages durably |
| Bulkhead | One dependency consumes all capacity | Does not guarantee delivery |
| Rate limiter | Target enforces a quota | Does not replace retry/recovery |
| Bounded queue | Inbound outpaces outbound | Does not survive crashes if in-memory |
| Retry/backoff | Transient failures | Can duplicate operations |

When a breaker opens, **work must not silently vanish**. If business rules require eventual processing, persist to a durable queue/outbox and drain only when recovery permits. For interactive requests, return a structured "overloaded" error to the caller per contract.

## 7. Backpressure, queues, and concurrency limits

Rate example: inbound 500 messages/second, outbound serves 50 messages/second. Backlog grows by roughly 450 messages/second if unchecked. Adding executors cannot exceed the dependency's capacity, and unbounded queues only delay running out of memory.

Coordinate:
- Cap workers/in-flight requests per target.
- Use **bounded** queues or persistent stores with clear full-queue policies.
- Throttle pollers, `maxMessagesPerPoll`, and listener concurrency where supported by the source.
- Pick `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and durable channels to match source traits.
- Bound payload sizes and retention times; monitor oldest-message age.
- Tune rate limits against partner throughput and quotas.

Never assume `ExecutorChannel` provides safe backpressure just because it is asynchronous. Understand executor queues, rejection policies, and how errors propagate into the flow. With `FluxMessageChannel` or reactive publishers, demand signals only apply where Reactive Streams are truly supported; segments calling blocking adapters must be controlled separately.

## 8. Durable handoff: never hold transactions while waiting on slow services

Suppose a JDBC inbound poller opens a transaction, updates an order, and calls a slow HTTP gateway before committing:

~~~text
BEGIN JDBC TX -> claim order -> HTTP wait 25 seconds -> COMMIT
~~~

For all 25 seconds, JDBC connections/locks remain held while HTTP does not participate in the JDBC transaction. A more resilient pattern is the **transactional outbox**:

~~~mermaid
flowchart TD
    A[Inbound message] --> T[Short JDBC transaction]
    T --> B[Business state update]
    T --> O[Insert outbox job]
    B --> C[Commit]
    O --> C
    C --> P[Worker claims job in short TX]
    P --> H[HTTP / SFTP / Kafka outbound outside claim TX]
    H --> D{Outcome}
    D -->|Accepted| M[Short TX: mark delivered]
    D -->|Unknown| R[Reconcile / retry scheduled]
    D -->|Permanent failure| X[Quarantine with owner]
~~~

Workers should split **claim–send–finalize**: claim the job and commit, run network I/O without holding a DB transaction, then open a short transaction to record the outcome. If a worker dies after remote acceptance and before finalization, the job may re-run; rely on idempotency keys and remote status queries.

## 9. Designing idempotency and UNKNOWN states

Every business operation needs a stable identifier—e.g., `shipment:create:order-301`—never a new UUID generated per retry of the same operation. When targets support idempotency keys, reuse that exact key across retries per target TTL/contract.

A reference state machine:

~~~text
PENDING -> CLAIMED -> IN_FLIGHT
                    |        |
                    |        +-> ACCEPTED -> DELIVERED
                    |        +-> TIMEOUT  -> UNKNOWN
                    |        +-> REJECTED -> QUARANTINED
                    +-> LEASE_EXPIRED -> RETRY_ELIGIBLE
UNKNOWN -> remote query -> DELIVERED / RETRY_ELIGIBLE / MANUAL_REVIEW
~~~

`LEASE_EXPIRED` does not mean the previous request finished at the partner. Old and new workers may overlap; use lease versions/fencing tokens and optimistic updates when finalizing. Unique constraints in the source DB alone cannot stop a remote system from creating duplicates.

## 10. Spring Integration Java DSL example

The snippet below illustrates a synchronous outbound flow with `RequestHandlerRetryAdvice` and separate HTTP client timeout settings. Verify bean names and DSL against your actual Spring Integration version; this is an illustration, not a standalone compilable project.

~~~java
@Bean
IntegrationFlow outboundFlow(
        MessageChannel outboundRequests,
        MessageHandler partnerHandler,
        RequestHandlerRetryAdvice boundedRetryAdvice) {

    return IntegrationFlow.from(outboundRequests)
        .handle(partnerHandler, endpoint ->
            endpoint.advice(boundedRetryAdvice))
        .get();
}
~~~

Apply retry advice to fitting handlers; when a gateway has request–reply semantics and callers expect a reply, never swap in a one-way handler casually. Configure backoff and retryable exceptions in the retry policy. If a handler catches exceptions and returns normally, retry advice never sees a failure; define exception propagation explicitly.

A service-level wrapper expressing intent:

~~~java
public DeliveryResult sendWithPolicy(OutboundJob job) {
    if (!partnerCapacity.tryAcquire()) {
        return DeliveryResult.defer("bulkhead_full");
    }
    try {
        return partnerClient.send(
            job.payload(),
            job.idempotencyKey(),
            job.deadline()
        );
    } catch (OutcomeUnknownException ex) {
        return DeliveryResult.reconcile(job.id());
    } finally {
        partnerCapacity.release();
    }
}
~~~

This is Java pseudocode illustrating a contract; `partnerCapacity`, `partnerClient`, and `DeliveryResult` are application abstractions. Never run network I/O inside a lock-holding JDBC transaction just to force "send succeeds before commit."

## 11. HTTP adapters: slowness, connection pooling, and unclear outcomes

For outbound HTTP gateways:
1. Define connect timeouts, response timeouts, pool acquisition timeouts, and overall request deadlines per your actual HTTP client.
2. Never treat `202 Accepted` as business completion when the target processes asynchronously.
3. Cap concurrent connections per host; manage keep-alive, pool sizing, and idle eviction.
4. Retry 429/503 honoring `Retry-After` when permitted by contract.
5. Distinguish failures before sending the request body from failures after the server may have received it.
6. When streaming request/response bodies, ensure clean resource closure and cancellation.
7. Protect credentials; never log `Authorization` headers or full payloads during diagnostics.

For example, a shipping API times out at the client while the server creates the shipment. If a worker re-receives the same message from JMS/Kafka, query the API by business ID or reuse the same idempotency key. **Rolling back the source transaction does not undo an already-succeeded POST.**

## 12. SFTP and file adapters: slowdowns mid-transfer

With SFTP, a file may transfer 80% before dropping the connection. A target directory could hold a partial file that a partner reads prematurely. Design considerations:
- Upload under a temporary name, verify size/checksum if required by contract, then rename once complete.
- Never assume `rename` is atomic across every server/filesystem; verify actual semantics.
- Cap active SFTP sessions and concurrent files; never use unbounded pools.
- Use stable file IDs, checksums, and remote readbacks before retrying.
- Manage local staging and recovery when remote sessions drop.
- Avoid passing live streams across `ExecutorChannel` if session lifecycles do not cover downstream execution.
- Alert on aged files or budget-exceeding retries.

File inbound pollers may continue seeing the same file after failures; persistent accept-once filters, metadata stores, and locking have distinct semantics requiring redelivery tests. File moves/renames do not automatically roll back with JDBC transactions.

## 13. JMS, AMQP, Kafka: resilience by broker

| Transport | When consumer/outbound is slow | Controls |
|---|---|---|
| JMS | Un-acked sessions, listener throughput drops | Container concurrency, acks/transactions, retries, and DLQ |
| AMQP | Unacked deliveries climb; requeues can loop | Prefetch, consumer concurrency, nack/DLX/DLQ |
| Kafka | Consumer lag rises; slow processing affects polls/rebalances | Tune poll cadence, `max.poll.interval.ms`, concurrency, retry/DLT |
| JDBC | Connections/row locks held | Short transactions, pool/lock timeouts, outbox |
| File/SFTP | Files queue at source or sessions linger | Bounded polling, staging, retry/reconciliation |

For Kafka, exceeding `max.poll.interval.ms` can mark the consumer stalled and trigger rebalances per configuration. Never run unbounded slow callbacks on the listener thread assuming offsets stay safe. When handing off to async workers, ensure tasks are durably persisted before committing source offsets.

With JMS/AMQP, acking the source right after enqueuing onto an in-memory executor risks losing messages on crash. If the broker redelivers after remote acceptance, idempotency is mandatory. Dead-lettering is not completion: assign alerts, owners, and replay procedures.

## 14. Choosing a strategy when a dependency is unavailable

Three main approaches:
- **Fail fast:** fits interactive requests that cannot meet SLAs; return explicit retryable signals.
- **Defer:** persist work to a durable queue/outbox and acknowledge *acceptance* rather than final completion.
- **Degrade:** use fallback behavior or cached data if business rules allow, stating freshness and limitations clearly.

For instance, a report-export API facing slow partner SFTP can return a job ID and `ACCEPTED` status while workers track completion, rather than holding the HTTP caller open until upload finishes. For payments or sensitive authorization, never degrade by skipping business controls.

When retry queues fill up or are isolated, enforce admission policies: reject new requests or pause source ingestion rather than accepting endlessly and dropping data.

## 15. Observability and SLOs

Monitor both latency and work accumulation:
- `remote_call_latency` (p50/p95/p99), timeout rates, and error rates per dependency.
- `in_flight_requests`, thread pool active/queued/rejected counts, and HTTP connection pool pending waits.
- `circuit_breaker_state`, bulkhead rejections, and retry attempt counts.
- `inbound_rate`, `outbound_success_rate`, queue depth, and **oldest message age**.
- JMS/AMQP unacked/redelivery/DLQ counts; Kafka consumer lag/rebalances.
- JDBC transaction duration, connection pool waits, and lock waits.
- `UNKNOWN` ratio, reconciliation backlog, duplicates suppressed, and time-to-business-completion.

SLOs are more than process uptime. "99% of jobs confirmed within 5 minutes" must measure from acceptance to verified business outcome. A continuously growing queue while the HTTP server returns 200 does not indicate a healthy system. Traces should include `correlationId`, `businessId`, attempt number, and target, without putting `businessId` into high-cardinality metric labels.

## 16. Resilience test matrix

| ID | Scenario | Expected behavior |
|---|---|---|
| RL01 | HTTP response slower than timeout | Does not hold threads forever; `UNKNOWN` outcome handled properly |
| RL02 | Immediate HTTP 503 | Bounded retry with backoff, no storm |
| RL03 | HTTP remote succeeds but response lost | Zero duplicates created on retry |
| RL04 | Circuit breaker `OPEN` | No new calls sent; durable jobs remain intact |
| RL05 | Bulkhead full | Controlled reject/defer, no OOM |
| RL06 | Outbound 10 msg/s, inbound 100 msg/s | Bounded queues and load-shedding engage |
| RL07 | Worker crashes after DB commit before outbound | Outbox recovers the job |
| RL08 | Worker crashes after remote acceptance before finalize | Replay stays idempotent |
| RL09 | Lease expires while old request still runs | Stale worker cannot overwrite newer state |
| RL10 | SFTP drops mid-upload | Partner never sees a false complete file |
| RL11 | JMS/AMQP redelivery | Business effects do not duplicate |
| RL12 | Kafka listener processes slowly | Lag/rebalances detected and recovered cleanly |
| RL13 | In-memory `ExecutorChannel` lost on crash | Test demonstrates risk; replaced with durable handoff |
| RL14 | Prolonged JDBC lock wait | Timeouts/short transactions isolate impact |
| RL15 | Invalid payload | Not retried endlessly; properly quarantined |
| RL16 | Retry queue full | Clear admission policy and sufficient evidence |

To verify, tests must inspect source/target states, real timeouts, queues, send counts, and open resources. Unit tests merely verifying a mock ran once are insufficient to prove resilience.

## 17. Hands-on exercise: orders over HTTP and SFTP

Design flow:

~~~text
JDBC inbound / HTTP request
   -> validate
   -> short JDBC transaction: business state + outbox job
   -> outbox worker with concurrency limit
   -> HTTP shipment gateway
   -> SFTP document upload (if required)
   -> finalize or retry/reconcile
~~~

Requirements:
1. Build an HTTP test server simulating delays, 429s, 503s, and timeouts after saving an order.
2. Configure connect/response deadlines, retry budgets, and circuit breakers matching a chosen SLO, explaining your rationale.
3. Implement outbox claim–send–finalize so JDBC transactions are never held during network waits.
4. Bound concurrency/queues, drive inbound load higher than outbound capacity, and measure oldest-message age.
5. Upload via SFTP using temporary names; inject mid-transfer failures and inspect remote state.
6. Simulate a crash after remote acceptance and before finalization; verify idempotency.
7. Add alerts when breakers open, retry queues grow, oldest jobs breach SLA, or `UNKNOWN` counts climb.
8. Submit a report with `caseId, dependency, remoteLatencyMs, attempt, sourceState, targetState, queueAgeMs, expected, observed, evidence`.

## 18. Design review checklist

1. Does every dependency have finite connect/read/request timeouts and an end-to-end budget?
2. Is it clear whether acknowledgement means request receipt or business completion?
3. Are workers, connections, and in-flight messages capped per target?
4. Are queues bounded, durable, and paired with full-queue policies?
5. Do circuit breakers and bulkheads stop slow dependencies from cascading failures?
6. Are retries bounded, using backoff/jitter, error classification, and stable idempotency keys?
7. Are `UNKNOWN` states reconciled rather than blindly retried immediately?
8. Do JDBC transactions finish before slow HTTP/SFTP calls begin?
9. When brokers redeliver, do consumers enforce deduplication and DLQ/quarantine?
10. Have crash windows between source commit and finalization been tested?
11. Do replay runbooks, escalation paths, resource cleanup, and SLO dashboards exist?
12. Are secrets, sensitive payloads, and uncontrolled connection growth prevented?

**Conclusion:** Resilience when external systems are slow must be built **at each adapter and transport boundary**. Timeouts prevent hanging forever, bulkheads/circuit breakers protect resources, backpressure caps work in flight, and outboxes/idempotency/reconciliation safeguard business outcomes during retries or lost responses. A flow is truly fault-tolerant when partner slowdowns never bring down the whole system and every message has a verifiable processing, recovery, or escalation state.
