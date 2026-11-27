# Testing Duplicate Events, Out-of-Order Delivery, and Downstream Interruptions

In the **Event Processing Project** chapter, a serverless pipeline must handle data accurately even when messages are delivered multiple times, events arrive out of order, or downstream services temporarily fail to respond. These failures are normal properties of distributed systems: producers may retry after timeouts, queues may redeliver messages, multiple Lambdas may run in parallel, and downstream systems may have executed side effects even though the caller missed the response.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications, particularly Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, access control, retries, idempotency, cold starts, scaling, and cost to determine when FaaS fits. This project turns those failure risks into a repeatable, observable test suite verified against final persisted data states.

## 1. Project Goals

Build an event-processing flow for order management. A producer emits events such as `OrderCreated`, `PaymentAuthorized`, and `OrderCancelled`. A Java consumer receives events from a queue or event bus, updates order state, and calls a downstream service.

The test suite must prove three behavioral categories:

1. **Duplicate delivery:** the same event is delivered two or more times, yet business effects apply only once.
2. **Out-of-order delivery:** a newer event version arrives before an older one or an event is missing; the system never overwrites newer state with older data and enforces explicit gap-handling rules.
3. **Downstream interruption:** downstream APIs or databases time out, return 5xx/throttling, or go down; the system retains work, retries safely, and recovers once dependencies return.

Do not inspect only HTTP statuses or logs. Every test must assert durable state: order version, inbox/dedup records, outbox records, side-effect counts, message retries/DLQs, and final outcomes.

## 2. Reference Architecture

~~~mermaid
flowchart TD
    P["Order producer"] --> Q["Queue / Event bus"]
    Q --> C["Java Lambda consumer"]
    C --> V["Validate event and version"]
    V --> I["Inbox / idempotency store"]
    I --> DB["Order database"]
    C --> D["Downstream API"]
    C --> O["Outbox for follow-up events"]
    Q --> DLQ["DLQ / quarantine"]
    C --> M["Metrics, logs and traces"]
    D --> M
    DB --> M
~~~

Required components in the test environment:

- Producer or fixture generating events with stable `eventId` and `aggregateVersion`.
- Queue/event source to simulate delivery, retries, and redrives.
- Java handler responsible for validation, deduplication, and updating business state.
- Database supporting unique constraints, conditional updates, or transactions.
- Downstream stub configurable to return success, timeouts, 429, or 5xx per scenario.
- DLQ/quarantine to hold messages exceeding attempt caps.
- Metrics/logs/traces to observe retries, duplicates, stale events, and processing lag.

For small projects, you can run the consumer as a plain Java service in tests, then add test adapters for Lambda event formats or event source mappings. Decoupling business logic from adapters keeps unit tests independent of cloud runtimes.

## 3. Event Contract Used in Tests

Each event needs explicit identity, aggregate, and version:

~~~json
{
  "eventId": "evt-order-42-v3",
  "eventType": "OrderStatusChanged",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "order-42",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-17T10:15:00Z",
  "correlationId": "corr-checkout-77",
  "payload": {
    "status": "PAID",
    "paymentId": "payment-91"
  }
}
~~~

Each field serves a distinct role:

- `eventId` identifies an event across retries, redrives, and replays.
- `aggregateId` identifies the entity mutated by the event.
- `aggregateVersion` expresses business ordering within the aggregate.
- `eventType` determines processing behavior.
- `schemaVersion` identifies payload structure.
- `correlationId` links steps within a workflow.

Never substitute queue message IDs for business `eventId` if the same event can travel across multiple transports. Never rely solely on timestamps to determine which event is newer; producer clocks can skew.

Test fixtures must preserve the exact same `eventId` and version when simulating duplicates. Generating a new `eventId` on each send turns a duplicate test into two independent events.

## 4. Defining Invariants Before Writing Tests

An invariant is a data condition that must always hold. For order processing, examples include:

- An `eventId` is applied at most once per consumer.
- Order version advances only according to defined rules.
- Older events never overwrite newer state.
- Events following a missing version never leapfrog the gap if business rules require sequential order.
- One payment authorization never creates two charges.
- Messages are ACKed only after business state or pending state is durably persisted.
- Downstream failures never lose events.
- Retries never produce uncontrolled side effects.

Translate invariants into concrete assertions. For instance, after delivering the same `PaymentAuthorized` event three times, the order stays `PAID`, version increments once, and the payment provider records a single operation for that idempotency key.

## 5. Designing Event Processing Outcomes

A consumer can classify outcomes as:

| Outcome | Meaning | Message Action |
|---|---|---|
| APPLIED | Event applied and committed | ACK/checkpoint |
| DUPLICATE | Event already applied earlier | ACK after verification |
| STALE | Older event by version/sequence | ACK or audit per policy |
| DEFERRED_GAP | Prior event version missing | Persist pending durably then ACK, or retry per design |
| RETRYABLE_FAILURE | Temporary dependency failure | Do not ACK; retry per trigger policy |
| PERMANENT_FAILURE | Payload/schema/business error that won't self-heal | Quarantine/DLQ |
| CONFLICT | Same version with conflicting content/event identity | Quarantine and alert |

Never lump every exception into `RETRYABLE_FAILURE`. `AccessDenied`, malformed payloads, or version conflicts rarely resolve on retry. Conversely, once a version-gap event is safely saved to a durable pending table, you can ACK the original message and let a separate worker apply it once the gap closes.

## 6. Duplicate Delivery Test Suite

Duplicates can happen when:

- A consumer finishes processing but times out before ACKing.
- A queue visibility timeout expires while the old invocation is still running.
- A publisher sends successfully but crashes before marking published.
- Events are redriven or replayed.
- A producer retries after missing a response.

Tests must deliver the same `eventId` multiple times and verify business state, not just handler invocation counts.

### 6.1. Sequential Same-Event Test

JUnit 5 example with test-wired repositories and handler:

~~~java
@Test
void duplicateEventDoesNotRepeatBusinessEffect() {
    OrderCreated event = fixtures.orderCreated(
            "evt-100",
            "order-42",
            1);

    ProcessingResult first = handler.handle(event);
    ProcessingResult second = handler.handle(event);
    ProcessingResult third = handler.handle(event);

    assertThat(first).isEqualTo(ProcessingResult.APPLIED);
    assertThat(second).isEqualTo(ProcessingResult.DUPLICATE);
    assertThat(third).isEqualTo(ProcessingResult.DUPLICATE);

    assertThat(orderRepository.find("order-42").version()).isEqualTo(1);
    assertThat(inboxRepository.count("order-consumer", "evt-100"))
            .isEqualTo(1);
    assertThat(outboxRepository.countByCausationId("evt-100"))
            .isEqualTo(1);
}
~~~

Repositories and fixtures here represent project abstractions. Integration tests must use a real database or Testcontainers to verify unique constraints and transactions, rather than purely mocking repositories.

### 6.2. Concurrent Duplicate Test

Two invocations can run simultaneously across two execution environments. Concurrent tests expose race conditions when code executes separate "check then insert" steps.

~~~java
@Test
void concurrentDuplicateIsAppliedOnlyOnce() throws Exception {
    OrderPaid event = fixtures.orderPaid(
            "evt-pay-200",
            "order-42",
            2);

    var pool = Executors.newFixedThreadPool(2);
    try {
        var first = pool.submit(() -> handler.handle(event));
        var second = pool.submit(() -> handler.handle(event));

        List<ProcessingResult> results =
                List.of(first.get(), second.get());

        assertThat(results)
                .containsExactlyInAnyOrder(
                        ProcessingResult.APPLIED,
                        ProcessingResult.DUPLICATE);

        assertThat(paymentRepository.countByEventId("evt-pay-200"))
                .isEqualTo(1);
    } finally {
        pool.shutdownNow();
    }
}
~~~

In real tests, synchronize both workers to start nearly simultaneously, for instance using a `CountDownLatch`. If the scheduler happens to run threads sequentially, the test may fail to trigger a race. Unique constraints or conditional writes must act as the final database safeguard.

### 6.3. Crash After Side Effect Before ACK Test

This is a critical failure window:

1. Consumer calls downstream successfully.
2. Consumer writes business state or receives the response.
3. Invocation stops before ACKing.
4. Queue redelivers the event.
5. Consumer receives the same `eventId` again.

Expected outcome: downstream does not execute the side effect a second time. If the provider supports idempotency keys, send the same key on both calls. Tests must verify the provider stub recorded one logical operation despite receiving multiple HTTP requests.

If downstream lacks idempotency support, maintain internal operation state and reconciliation for ambiguous outcomes. You cannot rely on an in-memory boolean inside Lambda.

## 7. Out-of-Order Event Tests

Suppose an order is at version 1, and the producer emits:

- Version 2: `PAID` status.
- Version 3: `FULFILLING` status.

If the consumer receives version 3 before version 2, handling depends on the event contract. With delta events requiring strict order, version 3 must be held pending. With self-contained snapshot events carrying full state, a newer snapshot may apply directly if the domain permits skipping intermediate states. Tests must lock down these semantics.

### 7.1. Out-of-Order Delivery Test

~~~java
@Test
void versionGapIsDeferredUntilMissingEventArrives() {
    OrderStatusChanged version3 = fixtures.statusChanged(
            "evt-order-v3",
            "order-42",
            3,
            "FULFILLING");

    OrderStatusChanged version2 = fixtures.statusChanged(
            "evt-order-v2",
            "order-42",
            2,
            "PAID");

    ProcessingResult early = handler.handle(version3);
    assertThat(early).isEqualTo(ProcessingResult.DEFERRED_GAP);
    assertThat(orderRepository.find("order-42").version()).isEqualTo(1);

    ProcessingResult next = handler.handle(version2);
    assertThat(next).isEqualTo(ProcessingResult.APPLIED);

    pendingEventDispatcher.processReady("order-42");

    Order finalOrder = orderRepository.find("order-42");
    assertThat(finalOrder.version()).isEqualTo(3);
    assertThat(finalOrder.status()).isEqualTo("FULFILLING");
}
~~~

Tests must verify version 3 was persisted as pending before the original message was ACKed. Once version 2 commits, the pending dispatcher applies version 3 exactly once.

### 7.2. Older Event Arriving After Newer Event Test

If the order is already at version 3, a late version 2 event must never overwrite state. Depending on `eventId` and processing history, the outcome is `STALE` or `DUPLICATE`.

Distinguish two cases:

- Same `eventId` already applied: duplicate.
- Different `eventId` with lower version than current: stale or conflict per contract.

Never mark every lower-version event as a duplicate without checking identity. Two distinct events sharing a version may indicate a producer bug.

### 7.3. Same Version with Different Payload Test

Generate two events with the same `aggregateId` and `aggregateVersion` but different `eventId` or payloads. The consumer must detect the conflict rather than arbitrarily picking whichever arrived last. Log an audit record, preserve payloads, and route to quarantine/manual review unless explicit domain rules dictate otherwise.

## 8. Downstream Interruption Tests

Downstream dependencies can:

- Return 429 due to rate limits.
- Return 500/502/503 due to outages.
- Hang until the client times out.
- Drop connections mid-response.
- Succeed while the response is lost.
- Return permanent errors like 400 or 403.

Each failure mode requires distinct behavior. Never retry every status code.

| Failure Injection | Expected Behavior |
|---|---|
| HTTP 429 | Honor `Retry-After` if present, backoff, and throttle rate |
| HTTP 500/503 | Bounded retries with exponential backoff and jitter |
| Connect/read timeout | Treat outcome as potentially unknown; retry with same idempotency key |
| HTTP 400 | Quarantine or record business error; do not infinitely retry |
| HTTP 403 | Alert on config/permissions; stop retrying quickly |
| Connection refused | Retain message; retry per policy |
| Database unavailable | Never ACK before state commits |
| Downstream recovers | Drain backlog gradually without creating bursts |

During prolonged outages, circuit breakers or load shedding prevent workers from hammering an incapacitated service. Queues buffer work to wait for recovery instead of keeping thousands of invocations sleeping.

## 9. Simulating Downstream Services with WireMock

WireMock can serve responses by call sequence or endpoint. For instance, returning 503 on the first two calls and 200 on the third:

~~~java
stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs(Scenario.STARTED)
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("second-failure"));

stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs("second-failure")
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("recovered"));

stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs("recovered")
        .willReturn(aResponse().withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"status\":\"AUTHORIZED\"}")));
~~~

Run the consumer with its real retry policy, wait until the operation finishes, and verify attempt counts and final state. Avoid long fixed sleeps; prefer Awaitility or polling assertions with explicit overall timeouts.

To simulate network latency, connection resets, or packet loss, use Toxiproxy or an equivalent fault-injection proxy. WireMock excels at HTTP response behavior; network proxies test transport-layer failures.

## 10. Testing Timeouts After Downstream Commits

A timeout does not prove the downstream service skipped the operation. A critical scenario:

1. Client sends a request with an idempotency key.
2. Downstream commits the transaction.
3. Downstream delays the response.
4. Client times out.
5. Consumer retries.

Configure the stub to record the side effect before delaying the response past the client timeout. The retry sends the same idempotency key and receives the stored result. Assert a single logical payment operation rather than a single HTTP request.

If the stub creates a fresh operation on every request, the test fails to model provider idempotency. If the real provider lacks idempotency, test your query/reconciliation workflow for ambiguous first-attempt outcomes.

## 11. Retries, Backoff, and Retry Budgets

Exponential backoff with jitter prevents workers from retrying in lockstep:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Verify in tests:

- Delay grows with attempts without exceeding `maxDelay`.
- Jitter spreads retry timestamps.
- Total retry span never exceeds deadlines or event age policies.
- `Retry-After` headers are honored when valid.
- Permanent errors are never retried.
- Exhausted events move cleanly to DLQ/quarantine.
- Redrives after fixes preserve the original `eventId`/idempotency key.

In queue-triggered Lambdas, let queue visibility timeouts and event source mappings drive redelivery rather than sleeping inside handlers. Sleeping holds invocations and concurrency slots while doing no useful work. For synchronous HTTP requests, returning `429`/`503` with `Retry-After` may fit better if callers can retry.

Retries across SDK, application, and queue layers multiply total calls. Define retry budgets at each layer and calculate worst-case total attempts.

## 12. Testing Circuit Breakers and Recovery

Circuit breakers typically have three states:

- `CLOSED`: requests flow and failures are tracked.
- `OPEN`: calls to the dependency are short-circuited.
- `HALF_OPEN`: a few probe requests test recovery.

Tests must verify:

1. After crossing the failure threshold, the breaker opens.
2. New requests do not hit the dependency while `OPEN`.
3. After the reset window, probe requests are allowed.
4. When probes succeed, the breaker closes.
5. When probes fail, the breaker re-opens.
6. No retry storms occur while `OPEN`.

With Lambda scale-out, an in-memory circuit breaker applies only within a single execution environment. Testing a local breaker does not prove a global circuit breaker works. When global quota/circuit state is required, use shared state or enforce protection at gateways/downstream layers.

## 13. Verifying Queue Buffering and DLQs

In integration tests, simulate a sustained downstream outage:

1. Send a batch of events.
2. Have downstream return 503 or time out.
3. Verify messages remain eligible for redelivery and were not prematurely ACKed.
4. Track queue age and retry counts.
5. Once thresholds pass, verify messages move to the DLQ per configuration.
6. Restore downstream and fix the cause.
7. Redrive a small batch of messages.
8. Verify business state is accurate with zero duplicate side effects.

SQS Standard can deliver messages multiple times without global ordering guarantees. SQS FIFO preserves order within a `MessageGroupId`, yet still requires idempotency and understanding of queue deduplication semantics. Never treat FIFO as an end-to-end exactly-once promise.

With Kinesis or Kafka, failures affect checkpoints/offsets and can cause records to be re-read. Tests must match the exact semantics of your source rather than assuming one universal retry behavior across all triggers.

## 14. Java Service Boundaries for Testability

Business logic should depend on interfaces, with AWS SDKs, queue adapters, and HTTP clients injected from outside:

~~~java
public interface PaymentGateway {
    PaymentResult authorize(
            String paymentId,
            long amountMinor,
            String idempotencyKey);
}

public interface EventInbox {
    boolean claim(String consumerName, String eventId);
    void markDeferred(String consumerName, String eventId);
    void markCompleted(String consumerName, String eventId);
}

public interface OrderRepository {
    boolean applyIfVersionMatches(
            String orderId,
            long expectedVersion,
            String newStatus);
}
~~~

Handlers coordinate transactions and classify outcomes. AWS adapters translate SQS/Kinesis/EventBridge payloads into domain events. HTTP adapters invoke downstream APIs and map statuses/timeouts to explicit exceptions or results.

Never couple business logic directly to a cloud provider's raw event JSON. Doing so lets unit tests run with clean domain events while separate integration tests verify adapter mappings.

## 15. Example Event Handling with Idempotency and Versioning

Illustrative Java pseudocode showing step ordering:

~~~java
public ProcessingResult handle(OrderEvent event) {
    return transactionTemplate.execute(status -> {
        if (!inbox.claim("order-consumer", event.eventId())) {
            return ProcessingResult.DUPLICATE;
        }

        Order current = orders.findForUpdate(event.aggregateId());

        if (event.aggregateVersion() <= current.version()) {
            inbox.markCompleted("order-consumer", event.eventId());
            return ProcessingResult.STALE;
        }

        if (event.aggregateVersion() != current.version() + 1) {
            pendingEvents.save(event);
            inbox.markDeferred("order-consumer", event.eventId());
            return ProcessingResult.DEFERRED_GAP;
        }

        boolean updated = orders.applyIfVersionMatches(
                event.aggregateId(),
                current.version(),
                event.newStatus());

        if (!updated) {
            throw new ConcurrentModificationException();
        }

        outbox.append(OrderStatusChanged.from(event));
        inbox.markCompleted("order-consumer", event.eventId());

        return ProcessingResult.APPLIED;
    });
}
~~~

This is pseudocode to illustrate flow, not a complete implementation. When saving a pending event, the inbox transitions to `DEFERRED`, not `COMPLETED`. A pending dispatcher reads the saved record, applies the business update in a transaction, and transitions the inbox to `COMPLETED` only after commit. Redelivery of the same event while `DEFERRED` must not create a second pending record; the handler can return an accepted outcome so the broker ACKs because pending state is already durable. If pending state is not durably saved, never ACK the original message.

When calling downstream APIs outside transactions, never hold database locks across network waits. Create an operation/outbox task inside the transaction, let a dedicated worker call downstream with an idempotency key, and update operation state in a subsequent transaction.

## 16. Testing Crashes Between Steps

Inject fault hooks or test doubles to halt execution at every step:

| Stop Point | What to Verify |
|---|---|
| Before inbox insert | Retried message starts cleanly |
| After inbox claim, before business update | Transaction rolls back or claim lease/timeout recovers |
| After business update, before commit | No partial commit |
| After commit, before ACK | Redelivery resolves as duplicate |
| After downstream success, before saving result | Retry with same idempotency key avoids repeating side effect |
| After broker publish, before marking outbox | Event may publish twice; consumer deduplicates |
| After saving pending gap, before ACK | Redelivery creates no duplicate pending record |

Fault injection should mirror real crashes as closely as possible. Throwing exceptions inside a transaction tests rollback; killing processes/containers or severing connections more realistically exercises crash windows and acknowledgement behavior.

## 17. Testing Batches and Partial Failures

A single Lambda invocation can receive multiple records. When one record fails, verify already-succeeded records are not unnecessarily reprocessed.

With SQS, enable partial batch responses where appropriate and return failed message IDs. With Kinesis/DynamoDB Streams, failure responses must follow the exact format and sequence semantics of the event source mapping.

Batch tests should cover:

- Record A succeeds.
- Record B hits a transient failure.
- Record C succeeds.
- Handler reports B as failed.
- A and C produce no duplicate side effects on batch redelivery.
- B retries and applies exactly once upon recovery.

With FIFO, if one record in a message group fails, stop processing later records in the same group if continuing would violate ordering. Never share identical batch logic between Standard and FIFO without accounting for ordering semantics.

## 18. Suitable Testing Tools

| Tool | Purpose |
|---|---|
| JUnit 5 | Java unit and integration testing |
| Mockito | Interface mocking and call verification |
| Testcontainers | Real databases, Kafka, or dependencies in containers |
| WireMock | HTTP responses, delays, and failure scenarios |
| Toxiproxy | Network latency, resets, and connection failures |
| Awaitility | Waiting on async state with explicit timeouts |
| LocalStack | Local testing of select AWS integrations |
| Cloud test environment | Verifying real event source mappings, IAM, and service semantics |

LocalStack provides fast feedback but does not replace real AWS environments completely. Differences in retries, IAM, visibility timeouts, stream checkpoints, or event source mappings must be verified via integration tests in a dedicated cloud account when relevant.

Never run fault-injection tests against production queues or live databases. Use isolated accounts/projects, dummy data, and disposable resources.

## 19. Testing Observability and Alerts

Failure scenario tests should also verify operational telemetry:

- Duplicate event count.
- Stale event count.
- Version gap/pending event count.
- Downstream timeouts, 429s, and 5xx responses.
- Retry attempts and retry age.
- Circuit breaker state.
- Queue depth and oldest message age.
- DLQ depth.
- Lambda duration, throttles, and concurrency.
- Idempotency hit rate.
- Processing success rate and end-to-end latency.

Logs should contain `eventId`, `aggregateId`, `aggregateVersion`, `correlationId`, `attempt`, and failure category. Never log raw payloads containing PII, credentials, or payment data. Avoid high-cardinality `eventId` metric dimensions; use logs/traces to trace individual events.

Alerts must reflect business impact. For example, rising queue age alongside low Lambda error rates can still indicate consumers are falling behind or downstream dependencies are slowing down.

## 20. Load Testing and Recovery Testing

Load tests should mimic production traffic distributions:

- Steady periodic events.
- Bursts when gateways reconnect.
- Skewed tenants/devices sending more than others.
- Intentional duplicate injection rates.
- Gradually rising downstream latency.
- Sustained 429/503 downstream responses.
- Dependency recovery while a backlog exists.

Measure throughput, p95/p99 latency, queue age, concurrent executions, database write capacity, retry rates, and cost per successful event.

Recovery testing matters just as much as load testing. When downstream returns, the system must drain backlogs at a safe pace rather than slamming the dependency all at once. Test gradual ramp-ups, rate limiters, and consumer pause controls.

## 21. End-to-End Test Scenario Matrix

| ID | Scenario | Expected Outcome |
|---|---|---|
| DUP-01 | Send same `eventId` twice | One business effect; second returns duplicate |
| DUP-02 | Two workers process same event concurrently | Unique constraint allows only one claim |
| DUP-03 | Crash after commit before ACK | Redelivery does not repeat side effects |
| ORD-01 | Version 3 arrives before version 2 | Version 3 deferred or handled per snapshot policy |
| ORD-02 | Version 2 arrives after version 3 | Old event does not overwrite newer state |
| ORD-03 | Two distinct events share same version | Conflict detected and quarantined |
| DEP-01 | Downstream returns transient 503 | Retries with backoff, eventually succeeds |
| DEP-02 | Downstream times out after commit | Retry with same idempotency key yields one logical operation |
| DEP-03 | Downstream returns 403 | No infinite retries; alert emitted |
| DEP-04 | Prolonged outage | Queue buffers backlog; DLQ receives per policy |
| REC-01 | Dependency recovers | Backlog drains smoothly in a controlled way |
| REC-02 | DLQ redrive | Events process accurately without duplicates |
| OBS-01 | Retries and version gaps occur | Metrics/logs/alerts reflect reality accurately |

This matrix is a baseline. Extend tests for your actual triggers, queues, databases, and downstream services.

## 22. Acceptance Criteria

The project passes when:

1. Sending a valid event produces the expected business state and outbox event.
2. Resending the same `eventId` multiple times never repeats side effects.
3. Two concurrent invocations handling the same event never produce two business updates.
4. Older event versions never overwrite newer versions.
5. Version gaps are held pending or handled per defined snapshot policy.
6. Two distinct events sharing a version are detected as a conflict.
7. Downstream 429/5xx/timeouts trigger the proper retry policy.
8. Timeouts after side effects never create a second logical operation.
9. Permanent errors are never retried infinitely.
10. Prolonged outages lose no messages; DLQs capture events per policy.
11. Post-recovery, backlogs drain within safe concurrency/rate limits.
12. Partial batch failures never duplicate side effects for already-succeeded records.
13. Metrics and logs suffice to trace events, attempts, and failure causes.
14. Tests run standalone with dummy data and zero production impact.

Turn acceptance criteria into automated assertions running in CI. Never mark a test `PASS` merely because logs printed "processed successfully".

## 23. Common Mistakes

**Testing the handler only once:** misses duplicates and race conditions. Test redeliveries and concurrency.

**Mocking the entire database:** fails to test unique constraints, transactions, and locking. Run integration tests against real databases.

**Generating fresh `eventId` values per send:** ceases to test duplicates. Keep `eventId` constant across retries.

**Checking only HTTP responses:** business state may have been written twice. Assert database and external side effects.

**Assuming timeouts mean downstream skipped work:** downstream may have committed. Retry with stable idempotency keys.

**Retrying every error:** 400/403 or schema errors never heal on retry. Separate permanent from transient failures.

**Sleeping inside Lambda while waiting on dependencies:** holds concurrency slots and increases cost. Let queues/backoff schedule retries.

**Using static state for deduplication:** not shared across execution environments and lost on restarts. Use durable storage.

**Ignoring event version gaps:** newer events apply on incomplete state. Defer gaps or enforce explicit snapshot semantics.

**Ignoring the DLQ:** events get forgotten after outages. Alerts and redrive runbooks are mandatory.

**Running fault injection on production:** risks real data loss. Use isolated environments and dummy data.

## 24. Project Implementation Workflow

1. Define the event contract, `eventId`, `aggregateId`, and `aggregateVersion`.
2. Write business invariants and expected states.
3. Decouple domain handlers from AWS adapters.
4. Implement inbox/idempotency and conditional updates.
5. Add pending-event or snapshot policies for out-of-order events.
6. Build a downstream stub supporting timeouts, 429, 5xx, and ambiguous successes.
7. Write unit tests for duplicates, stale events, gaps, and retry classification.
8. Write integration tests with databases and queues/brokers.
9. Add fault injection for crash windows and network failures.
10. Verify partial batches, DLQs, and redrives.
11. Add metrics, logs, traces, and alerts.
12. Run load/recovery tests in an isolated environment.
13. Wire tests into CI and archive test reports per commit.
14. Canary a consumer subset before expanding to full production.

## Conclusion

Testing event-driven systems requires verifying business outcomes under duplicates, out-of-order arrivals, and downstream outages. Event IDs, inbox/unique constraints, and transactions prevent duplicate side effects; aggregate versions and pending-event policies protect ordering; timeouts, backed-off retries, circuit breakers, and queue buffering help systems recover from dependency disruptions.

Java Lambdas can scale and retry independently, so control state must live in durable storage and every critical operation must be idempotent. A test suite earns its keep by reproducing realistic failure windows, asserting final database and downstream states, and proving backlogs drain safely upon recovery. Once automated in CI, teams can evolve consumers and infrastructure with confidence in data correctness.
