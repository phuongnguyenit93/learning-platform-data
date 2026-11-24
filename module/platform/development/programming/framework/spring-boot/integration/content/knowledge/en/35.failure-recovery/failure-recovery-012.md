# Testing Recovery When Connectivity Restores or Systems Overload

A Spring Boot integration flow can pass every test while HTTP APIs, databases, and brokers are healthy, yet lose data when connections flap or when systems recover from a multi-minute outage. For example: users place orders, the app writes orders to the database and emits events to a broker; the broker disconnects and publishes retry; once the broker comes back, thousands of app instances retry at once and overload it. Even though logs print **connection established**, some events vanish, duplicate, or stay stuck in queues.

This lesson belongs to the **Failure Recovery** chapter of the **SPRING_BOOT_INTEGRATION** module. The module covers integrating HTTP clients, databases, caches, message brokers, and Spring Integration adapters—focusing on configuration, data contracts, transactions, error handling, deduplication, testing, and observability. Therefore, **recovery testing** must prove not only that connections re-establish, but also business progress, data integrity, and stability under post-outage surge load.

## 1. Understanding Both Scenarios That Must Be Tested

**Connection recovery** is the process by which an application detects a dependency or socket is reachable again and resumes executing requests. It includes re-establishing connections, obtaining valid pooled connections, refreshing metadata/sessions, and deciding which pending work to resume.

**Business recovery** means requests accepted before or during the outage finish properly, transition transparently to terminal error states, or move to queues for policy-driven reprocessing. That is a much stronger requirement than merely "ping succeeded."

**Overload** occurs when incoming demand exceeds capacity at a bottleneck: thread pools, connection pools, partner APIs, DBs, consumers, brokers, or queue memory. Overload can strike during normal traffic or **right after connectivity restores**, triggered by accumulated backlogs and simultaneous retry bursts.

Distinguish failure modes:

| State | Example | What Tests Must Prove |
|---|---|---|
| **Total connectivity loss** | Bad DNS, TCP reset, broker unreachable | Failure detected, bounded timeout, never hangs forever |
| **Flapping connectivity** | 3 disconnects out of 10 requests | Bounded retries, zero duplicate side effects |
| **Connectivity restored** | Partner HTTP returns 200 again or broker recovers | New requests and backlogs process cleanly; no manual restart required if self-healing is contracted |
| **Partner overload** | HTTP 429/503, slow responses, concurrency caps | Backoff, `Retry-After` (if sent), proper rate limiting/circuit breaking |
| **Application overload** | Full queues, exhausted pools, high CPU, executor rejections | Controlled backpressure/load shedding; no unbounded queues |
| **Synchronized recovery** | Multiple replicas reconnect/retry together | No retry storm; completion rate climbs steadily |
| **Ambiguous success** | Client times out after partner already persisted | Idempotency keys or status reconciliation prevent duplicates |

**An HTTP 200 after an outage is not enough to mark a test PASS.** Tests must reconcile accepted work, completions, terminal failures, pending records, and actual side effects in target systems.

## 2. Recovery Lifecycle Model

~~~mermaid
stateDiagram-v2
    [*] --> Healthy
    Healthy --> Degraded: Timeouts, connection errors, 429/503, latency spikes
    Degraded --> Protected: Circuit opens / queue hits limit
    Protected --> Recovering: Downstream responds / probes succeed
    Degraded --> Recovering: Brief glitch ends
    Recovering --> Healthy: Health stable + backlog drains + SLO met
    Recovering --> Degraded: Failures return / load spikes
    Protected --> Protected: Shed load / defer retries within limits
~~~

At each phase, tests should observe **progress signals**, not guess from fixed sleep intervals:

| Phase | Expected System Behavior | Observable Signals |
| --- | --- | --- |
| **Healthy** | Processes within SLA while dependency is stable | Success rate, p95/p99 latency, low backlog |
| **Degraded** | Errors classified accurately; threads never held forever | Timeout/error counts, retry attempts, pool occupancy |
| **Protected** | Preserves stability via load caps and controlled rejections | Circuit breaker state, pending queues, rejected requests |
| **Recovering** | Paced retries; fresh connections/pools active; backlog shrinks | Successful probes, throughput, queue age, retry counts |
| **Healthy again** | All accepted work reconciled accurately | End-to-end completion, zero duplicate side effects, post-recovery SLO |

Two common test-design mistakes:

1. Marking **recovery complete** as soon as the dependency returns 200, while thousands of `PENDING` messages sit in the outbox.
2. Marking **zero data loss** simply because retries succeeded, even though the same payment command ran twice.

For side-effecting operations, separate three milestones: **request accepted**, **intent durably persisted**, and **confirmed on target system**.

## 3. Define Invariants and Acceptance Criteria Before Injecting Faults

Reliable test suites assert **invariants** during and after outages. For a flow receiving `OrderCreated`, writing an outbox row, and syncing to a warehouse API:

- **No lost accepted intents**: every accepted `eventId` retains a reconcilable durable state.
- **No duplicate side effects outside policy**: reprocessing an `eventId` never deducts stock twice, creates two orders, or sends two notifications.
- **Bounded failures**: failing requests enforce timeouts and total retry budgets without leaking threads/connections.
- **Bounded backlogs**: internal queues enforce explicit capacity; when full, reject or throttle producers per policy.
- **Observable recovery**: once the dependency stabilizes, backlogs shrink and remaining errors show clear causes.
- **Ordering where contracted**: for a given `orderId`, an older event never overwrites newer state.
- **Explicit landing place for terminal errors**: unprocessable records move to DLT, quarantine, or failed states for operator handling—never vanish silently.

Illustrative reconciliation equation:

~~~text
accepted_count
  = succeeded_count
  + terminal_failure_count
  + outstanding_count
~~~

This equation holds only when each **unique business ID** is counted in exactly one state rather than summing retry attempts. In-progress items belong in `outstanding_count`; actions potentially executed remotely without confirmation require reconciliation.

Derive PASS/FAIL criteria from real SLAs:

| Metric | Example Test Criterion | Meaning |
| --- | --- | --- |
| **Time to detect** | Detects failing dependency within a few seconds per configured timeouts | Never hangs indefinitely |
| **Time to resume** | New requests succeed within agreed bounds once dependency returns | Measures connection recovery |
| **Time to drain** | Accumulated backlog clears within SLO after restoration | Measures business recovery |
| **Duplicate side effects** | Exactly **0** per tested idempotency key | Protects data correctness |
| **Accepted but unaccounted** | Exactly **0** | Zero lost work state |
| **Max queue / active threads / connections** | Stays within configured capacities plus measurement tolerance | Avoids self-inflicted resource exhaustion |
| **Post-recovery latency and error rate** | Returns inside SLO without oscillating between recovery and overload | Evaluates stability |

Phrases like "a few seconds" or "a few minutes" are placeholders; substitute your system's **actual SLOs/SLIs**. Without remote idempotency, client retries alone can never justify claiming "exactly once."

## 4. Choosing Tools and Testing Layers

No single mock covers every recovery defect. Combine layers by test goal:

| Layer | Suitable Tools | What It Verifies | Limitations |
| --- | --- | --- | --- |
| **Retry/policy unit tests** | JUnit, Mockito, controllable clocks | Backoff, attempt counts, exception classification, state transitions | Does not test real TCP, connection pools, or side effects |
| **HTTP contract / adapter** | WireMock, OkHttp MockWebServer | 429/503, timeouts, headers, valid/invalid responses, request counts | Does not natively emulate complex network faults |
| **Network fault integration** | Testcontainers + Toxiproxy | Network drop/restore, latency, bandwidth caps, timeouts, stale sockets | Requires containers/networking and test resources |
| **DB/broker integration** | Testcontainers PostgreSQL, Kafka/RabbitMQ, Redis | Driver/pool recovery, transactions, acks, outboxes, redelivery | Slower than unit tests; needs cleanup and isolation |
| **System/load tests** | k6, Gatling, or chosen load tool | Saturation, retry storms, queue growth, resource exhaustion | Requires realistic workloads and environments |
| **Chaos/staging** | Controlled network shaping/fault injection | Multi-replica interactions, autoscaling, failovers | Needs strict safety guardrails and rollback |

To keep tests repeatable, explicitly record:

1. **Initial state**: event/record counts, consumer group offsets, DB seed data, empty vs. pre-seeded backlog.
2. **Injected fault**: client/server connection cut, 503 or 429 responses, injected latency, error ratio, duration.
3. **Input workload**: records/second, concurrency, payload size, key skew, queue depth.
4. **Recovery trigger**: proxy reopened, server returns 200, DB ready, broker accepts acks.
5. **Assertions**: durations, attempt counts, final per-ID state, queue depth, resource usage, logs/metrics.
6. **Cleanup**: delete test records by ID, reset proxy rules, stop containers so leftover groups or rows never pollute future runs.

Keep fast HTTP retry tests in pull-request pipelines and heavier network/load suites in dedicated pipelines. Never rely on fixed `Thread.sleep` durations to assume recovery finished; poll for **observable conditions** with explicit deadlines.

## 5. Connectivity Recovery Scenario Matrix

| Scenario | How to Inject Fault | PASS Criteria |
| --- | --- | --- |
| **TCP loss before send** | Block connections to HTTP/DB/broker | Bounded timeout, classified error; no fake success |
| **Connection reset mid-request** | Reset socket while sending/reading | Safe retry or status reconciliation; zero duplicate side effects |
| **Stale connections in pool** | Cut network, restore, then issue new requests | Pool evicts broken sockets cleanly; fresh connections succeed |
| **HTTP 503 several times then 200** | Mock 503, 503, 200 | Bounded retries eventually succeed; exact expected request count |
| **Permanent 400/422 contract errors** | Mock permanent payload failures | No blind retries; preserves error context for fixing payload |
| **HTTP 429 with `Retry-After`** | Mock throttling then recovery | Honors wait/rate-limit policy without adding partner pressure |
| **DB failover** | Drop connection mid-transaction | Active transaction rolls back or reconciles; new transactions succeed post-recovery |
| **Temporary broker outage** | Block publish/consume, then unblock | Messages preserved per durability/ack contract; redelivery stays idempotent |
| **DNS/TLS/certificate rotation** | Swap endpoint/credentials in test env | Client picks up valid config per rollout design; cert/auth errors never retry infinitely |
| **Repeated flapping** | Up–down–up cycling | Backoff/circuit breaker prevents oscillating retry storms |
| **App restart with backlog** | Kill container after intake | Durable work reloads, commits/acks cleanly, zero lost IDs |
| **Recovery under heavy load** | Build backlog then bring dependency back | Controlled exit from overload; queues drain, SLO returns, zero loss/duplication |

For **write** requests (charging payments, submitting orders, deducting stock), timeouts can occur *after the partner already committed*. Simulate "server persisted, client lost response" and verify replays are deduplicated via **idempotency keys** or partner status lookups.

## 6. JUnit Example: Recovering from HTTP 503 to 200

Start with a deterministic read case: **fetching stock via HTTP GET**, a read-only call without side effects. Uses `RestClient` (Spring Framework 6.1+, typically in Spring Boot 3.2+) and `Resilience4j Retry`, tested against **MockWebServer** returning 503 then 200 to verify bounded retries.

Illustrative Gradle dependencies matching your project's Spring Boot/JDK versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'io.github.resilience4j:resilience4j-retry:2.3.0'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

### 6.1. Adapter with Timeouts and Retry Policy

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

record Stock(String sku, int available) {}

final class StockGateway {
    private final RestClient http;
    private final Retry retry;

    StockGateway(String baseUrl) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(300))
                .build();

        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(client);
        requestFactory.setReadTimeout(Duration.ofSeconds(1));

        this.http = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .build();

        RetryConfig config = RetryConfig.custom()
                .maxAttempts(3)  // Includes initial attempt
                .waitDuration(Duration.ofMillis(20))
                .retryOnException(error ->
                        error instanceof HttpServerErrorException
                        || error instanceof ResourceAccessException)
                .build();

        this.retry = Retry.of("stock-lookup", config);
    }

    Stock get(String sku) {
        return retry.executeSupplier(() ->
                http.get()
                    .uri("/stocks/{sku}", sku)
                    .retrieve()
                    .body(Stock.class));
    }
}
~~~

**Example scope:** retries only HTTP 5xx server errors and resource-access I/O errors, capped at three GET calls. **HTTP 400/422** are not retried. **HTTP 429** is also excluded here: supporting throttling requires dedicated handling for `Retry-After`, time budgets, and rate limits. Never copy this GET retry setup onto side-effecting HTTP POSTs unless the partner enforces idempotency.

`maxAttempts=3` means initial call plus up to **two retries**. `20 ms` keeps tests fast; production needs progressive backoff, jitter, retry budgets, and concurrency limits. Exact `RestClient` timeout and exception behavior depends on the chosen request factory/version.

### 6.2. Testing Recovery and Bounded Retries

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

class StockGatewayTest {

    @Test
    void succeedsAfterDependencyRecovers() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(json(503, "{\"error\":\"busy\"}"));
            server.enqueue(json(200, "{\"sku\":\"SKU-1\",\"available\":7}"));
            server.start();

            Stock result = new StockGateway(server.url("/").toString())
                    .get("SKU-1");

            assertEquals("SKU-1", result.sku());
            assertEquals(7, result.available());
            assertEquals(2, server.getRequestCount());
        }
    }

    @Test
    void givesUpWhenDependencyKeepsFailing() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            for (int i = 0; i < 3; i++) {
                server.enqueue(json(503, "{\"error\":\"busy\"}"));
            }
            server.start();

            StockGateway gateway =
                    new StockGateway(server.url("/").toString());

            assertThrows(HttpServerErrorException.class,
                    () -> gateway.get("SKU-1"));
            assertEquals(3, server.getRequestCount());
        }
    }

    @Test
    void doesNotRetryPermanentClientError() throws IOException {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(json(400, "{\"error\":\"bad sku\"}"));
            server.start();

            StockGateway gateway =
                    new StockGateway(server.url("/").toString());

            assertThrows(HttpClientErrorException.class,
                    () -> gateway.get("BAD"));
            assertEquals(1, server.getRequestCount());
        }
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
~~~

**Three distinct assertions:** successful recovery (503 → 200), stopping at the retry ceiling (persistent 503), and skipping retries on unrecoverable errors (400). This verifies the **HTTP retry policy**, not TCP/pool healing or backlog draining, which require the integration tests below.

When production code emits metrics, also assert **retry attempt counts**, last exception, circuit breaker state, and correlation IDs. For timing tests, use controllable clocks where supported or bounded wait conditions—never assert exact millisecond timings on CI runners.

## 7. Real Network Tests: Cutting Connectivity, Reconnecting, and Checking Pools

Mocking 503 tests application logic; "network dropped then restored" requires testing the transport layer. Use real dependency containers behind a controllable proxy such as **Toxiproxy**:

~~~mermaid
flowchart LR
    A["Spring Boot application"] --> P["Toxiproxy"]
    P --> D["PostgreSQL / Redis / Kafka / HTTP test server"]
    C["JUnit test controller"] -. "cut / restore / inject latency" .-> P
    A --> M["Actuator / Micrometer"]
    M --> C
~~~

Sample scenario:

1. Start a real dependency (e.g., PostgreSQL) and proxy in the test network. Point the JDBC URL through the **proxy**, never directly at the database.
2. Verify read/write queries and transactions succeed while healthy. Record `accepted/succeeded/outstanding` baseline.
3. Inject a fault **severing both active and new connections**. Run several operations; confirm bounded timeouts, classified errors, and no fake commits for failed transactions.
4. Restore the proxy; within a clear deadline, wait for `SELECT 1` and a **new business transaction** to succeed without restarting the app if self-healing is required.
5. Inspect persisted rows, outbox records, and idempotency state to confirm zero dropped or duplicated work.
6. Observe HikariCP active/pending connections, connection acquisition failures, wait times, and recovery logs.

For **database connection pools**, remember that a transaction failing mid-disconnect **does not resurrect** when the network returns. Each retry attempt must open a **fresh transaction**—never rerun individual SQL statements inside a rolled-back transaction. Ensure service-level retries start a new transaction per attempt with clean boundaries, never pinning a broken connection across retries.

For HTTP/TCP tests, cover both fault positions:

- **Disconnect before the request reaches the server**: the client knows the command was not sent, yet still verify timeouts and retries.
- **Disconnect after the server completed the operation, before the client receives the response**: outcome is uncertain; retries are safe only with idempotency or status lookup.

When designing fault injection, distinguish **reset**, **timeout**, **latency**, **bandwidth throttling**, and **connection refused**, as each triggers different code paths. Testing only one flavor of "network down" is insufficient for pooled connectors and long-lived clients.

## 8. Overload Tests: Backpressure, Bulkheads, and Retry Storms

After restoration, suppose **20,000 events** sit in backlog while the partner handles **100 req/s** steadily, and 10 replicas each retry at 50 req/s. The combined 500 req/s surge immediately knocks the partner back down even though connectivity healed.

~~~text
Backlog(t + Δt) ≈ backlog(t)
                   + accepted_in(Δt)
                   - completed_out(Δt)
                   - terminally_resolved(Δt)

If new arrival rate + replay rate
  > real sustainable processing rate,
backlog keeps growing or turns into overload.
~~~

In this formula, `terminally_resolved` counts only items finalized per policy (e.g., routed to DLT with reconciled status), never silent drops. Count by **unique job ID**, not HTTP call count, because retries inflate call counts.

### Protecting Each Resource

| Mechanism | What It Prevents | What Tests Must Verify |
| --- | --- | --- |
| **Timeout** | Threads/connections waiting forever | Every attempt ends within deadline; clear error classification |
| **Retry budget + backoff + jitter** | Retry storms and runaway amplification | Attempt counts and retry rates stay bounded |
| **Circuit breaker** | Hammering a failing dependency | `OPEN` fails fast, `HALF_OPEN` probes boundedly, `CLOSED` on sufficient healthy signals |
| **Bulkhead / concurrency limit** | One slow downstream exhausting all workers | Unrelated flows' pools/threads remain responsive |
| **Rate limiter** | Exceeding partner quotas/throttling | Aggregate outbound rate stays under cap across all replicas |
| **Bounded queue / backpressure** | Unbounded buffering causing OOM and extreme latency | Queues enforce capacity; producers slow down or fail per policy |
| **Load shedding** | Wasting capacity on requests unlikely to finish | Meaningful 429/503 responses; critical traffic preserved |
| **Gradual ramp-up** | Unleashing entire backlog simultaneously on reconnect | Controlled concurrency/rate ramp-up without oscillation |

**Circuit breaker note:** entering `HALF_OPEN` after wait expiry does not prove downstream is healthy. Test probe limits and re-open/close criteria. **Jitter** stops instances from retrying in lockstep; unjittered exponential backoff can still produce synchronized spikes.

### Controlled Load-Test Scenario

Example workload in an isolated staging environment:

- Baseline steady state: 50 req/s within known downstream capacity.
- Fault downstream while continuing to ingest workload during an outage window.
- Once a backlog builds, restore downstream capped at 100 req/s.
- Drain replay traffic under configured concurrency/rate limits.
- Observe `accepted`, `rejected`, `retried`, `succeeded`, queue depth, oldest message age, p95/p99, CPU, heap, DB pool, and connection errors.

The test PASSES when the system **never exhausts resources**, rejected requests get contracted errors, accepted work resolves into durable states, and backlog drains within remaining capacity. Numbers 50/100 are illustrative; measure real capacity before setting thresholds.

**Key distinction:** `rejected_count` at the HTTP gateway counts requests turned away **before durable acceptance**—never mix them into `accepted_count`. Once input is durably accepted, failures afterward must retain retry or terminal error state.

## 9. Spring Boot Integration Boundaries to Test Under Recovery

### 9.1. HTTP Clients and External Partners

- Verify `connect timeout`, `read/response timeout`, overall deadline (across all retries), and max connections.
- On **HTTP 429**, honor `Retry-After` if provided; on **HTTP 503**, apply bounded jittered retries when safe.
- On side-effecting POST/PUT/PATCH, use **idempotency keys**, status queries, or replay-safe business protocols. Timeouts never prove remote rollback.
- For OAuth/TLS, separate **401/403/invalid certificate** errors from transient glitches; never retry config mistakes forever.
- Log correlation IDs, attempt counts, endpoint aliases, and durations; redact tokens and sensitive payloads.

### 9.2. Databases and Connection Pools

- Test stale-connection eviction after failover, connection acquisition timeouts, and transaction rollbacks.
- Retry the **proper business unit**, never single SQL statements inside a failed transaction.
- Never retry every `DataAccessException`: unique constraint violations are usually permanent or indicate existing records needing reconciliation.
- When DBs return, simultaneous pool reconnects can trigger a **connection storm**; bound pool sizes and concurrent recovery.
- When writing to DB and emitting messages, test the crash window between them; prefer a **transactional outbox**.

### 9.3. Caches

- Redis/cache outages can send all traffic straight to the database, triggering a **cache stampede** during recovery.
- Test degradation rules: which data allows stale reads, which must fail closed, TTLs, and refresh behavior.
- Use concurrency caps or per-key single-flight coalescing where appropriate; never turn cache misses into thousands of DB queries.
- Never rely on eviction-prone caches as the durable source of idempotency if business deduplication windows exceed cache retention.

### 9.4. Kafka, RabbitMQ, and Message Brokers

**Kafka:**

- On producer network errors, verify `acks`, retries, `delivery.timeout.ms`, idempotent producer behavior, and ambiguous publish outcomes.
- On consumers, verify committed offsets, partition rebalances, `max.poll.interval.ms`, `poll()` resumption once the broker returns, handler state, and duplicate handling.
- Never commit offsets before work is durably persisted/processed per policy. Processed-but-uncommitted records will be redelivered.
- Under heavy backlogs, scaling `concurrency` is bounded by partition count and downstream capacity; unbounded in-memory queues solve nothing.

**RabbitMQ / AMQP:**

- Verify channel/connection recovery, publisher confirms/returns, and **manual ack** along real code paths.
- If a consumer dies before ack, messages redeliver; side effects must be idempotent.
- Tune prefetch/concurrency so too many unacked messages do not exhaust memory or downstream capacity.
- Test dead-lettering and TTL settings; constant reject/requeue loops create hot failure cycles.

**Spring Integration:**

- With `DirectChannel`, handlers typically run synchronously on the sender's thread; downstream errors/timeouts propagate back to the caller.
- With `ExecutorChannel` or `QueueChannel`, verify executor/queue bounds, rejection policies, and `errorChannel` routing. In-memory `QueueChannel` is not durable by default.
- For inbound/outbound adapters and pollers, verify **where ack/commit actually happens** and where errors route. Putting a message on a channel does not mean processing finished.
- With `IdempotentReceiverInterceptor` or metadata stores, test deduplication state across restarts, key expiry, and crashes between key storage and side effects.

## 10. Testing Deduplication, Outbox, and Crash Windows

Recovery reliability often hinges on the boundary between **transactions** and **acks/commits**. Consider:

~~~mermaid
sequenceDiagram
    participant I as Inbound adapter
    participant DB as Business DB
    participant O as Outbox dispatcher
    participant P as Partner API
    I->>DB: Write order + outbox in 1 transaction
    DB-->>I: Commit
    I-->>I: Ack inbound per contract
    O->>DB: Fetch PENDING outbox
    O->>P: Send request with idempotency key
    P-->>O: Timeout after possible execution
    Note over O,P: Remote outcome uncertain
    O->>P: Query status or retry with same key
    P-->>O: Confirm unique outcome
    O->>DB: Mark outbox PROCESSED
~~~

Failure windows to inject in integration tests:

| Window | Risk | Key Assertion |
| --- | --- | --- |
| Crash **before** business DB commit | Request not durably saved | Can be re-received/retried; no half-baked state |
| Crash **after** DB commit but **before** inbound ack | Event redelivered | Event ID deduplicated; single order and outbox row |
| Broker/downstream drops right **before publish** | Work stays `PENDING` | Dispatcher retries once connection returns |
| Publish succeeds yet ack/HTTP response lost | Client unsure whether it succeeded | Retries with same idempotency key or reconciles; zero duplicates |
| Outbox sends successfully then crashes **before status update** | `PENDING` row reprocessed | Target side effect does not repeat thanks to idempotency key |
| System recovers yet one record fails schema continuously | Backlog stalls at one offset | Bad record goes to quarantine/DLT; valid records keep advancing |
| Multiple dispatchers compete for one outbox row | Concurrent duplicate sends | Leases/locking/unique business keys protect against duplicates |

**Transactional outbox** guarantees durable persistence of send intent alongside business data; it **does not by itself ensure exactly-once** against external APIs or between DB and broker. You still need retrying relays, status tracking, unique keys, target idempotency, and reconciliation.

For ordered processing, commit/ack higher progress only once preceding items in the partition/key have resolved per policy. Advancing offsets past an async in-flight item risks skipping it on crash.

## 11. Writing Deterministic, Non-Flaky Recovery Tests

Tests remain reliable only when they do not depend on arbitrary CI machine speed. For async events, use **eventual assertions** with explicit deadlines:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

// Illustrative integration-test assertion: variables come from test fixture.
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        assertEquals(expectedCount, outboxRepository.countProcessed());
        assertEquals(0, outboxRepository.countPending());
        assertEquals(expectedCount, partnerStub.distinctBusinessKeys());
    });
~~~

This is an **assertion pattern** to place inside a test fixture owning `outboxRepository` and `partnerStub`, not a standalone compilable class. Use `distinctBusinessKeys` to verify side effects by **unique business key**, and also assert total side-effect invocations if the stub supports it.

To prevent flakiness:

- Use **latches/barriers** or deterministic fault-injection hooks to pause right before/after commit rather than guessing with `Thread.sleep(2000)`.
- Inject controllable clocks for backoff, TTL, or circuit-breaker timing where supported; never assert exact millisecond delays.
- Tag events, idempotency keys, and rows with a `testRunId` to prevent cross-test contamination.
- Wait until dependencies are **genuinely healthy** before opening proxies, starting recovery, and measuring timings.
- Enforce deadlines per phase so broken ack/commit paths never hang builds forever.
- Compare data snapshots before and after recovery rather than relying on exceptions or `isConnected=true`.
- Test retries/overload with **deterministic concurrency** and bounded loads matched to CI/staging capacity.

A common false positive is `await().until(() -> httpPing() == 200)`: that confirms only reachability, not that outbox queues drained or customers weren't double-charged.

## 12. Observability, Alerting, and Criteria to Declare Recovery Complete

Both tests and production operations need the same signals to confirm an incident truly ended:

| Category | Metrics and Context |
| --- | --- |
| **Connectivity** | Connection error rate, timeouts, pool active/idle/pending, reconnect attempts |
| **Retries/circuits** | Attempts per logical request, retry exhausted, `OPEN`/`HALF_OPEN`/`CLOSED` state, rejected calls |
| **Load and queuing** | Queue depth, oldest queued age, worker saturation, active threads, heap, CPU, request rate |
| **Latency** | p95/p99 per outbound call, end-to-end duration from accepted to completed |
| **Progress** | Accepted vs. completed vs. terminal failure vs. outstanding, outbox pending age, consumer lag |
| **Data integrity** | Duplicate business effects, idempotency conflicts, outbox reconciliation failures |
| **Contract errors** | HTTP status codes, serialization/deserialization failures, DLQ/DLT volume, correlation IDs |
| **Recovery quality** | Time to resume, time to drain, recovery error rate, relapses into degraded state |

With Spring Boot, **Actuator/Micrometer** provides built-in HTTP, thread-pool, and JDBC/HikariCP meters; retry, queue, outbox, and idempotency metrics typically require custom instrumentation. Exact meter names and tags depend on library and exporter versions—verify **real meter definitions** when building dashboards rather than guessing names.

Attach `traceId`/`correlationId`, `messageId`, suitably masked `idempotencyKey`, adapter type, downstream alias, error code, and retry attempt to trace work end-to-end. Never log passwords, API keys, tokens, payment card details, or raw sensitive payloads.

**Criteria to declare recovery complete** should require all of:

1. Dependent services are healthy and serving requests.
2. Error rates and latencies returned within SLO at the target load.
3. Queues/backlogs are shrinking and draining within expected bounds.
4. Every accepted job has a reconciled state—zero "missing" IDs.
5. Zero duplicate side effects outside idempotency contracts.
6. No recurring reconnect → retry storm → circuit open → reconnect oscillation.

## 13. Complete Hands-On Exercise

Build a Spring Boot application modeling **order creation → outbox → warehouse HTTP** or **order creation → outbox → broker → consumer**. Assign unique reconcilable `eventId`s and provide a status-lookup endpoint keyed by idempotency key.

### Scenario A: Connectivity Restores

1. Submit a batch of valid orders; verify business DB and outbox commit cleanly.
2. Cut outbound connectivity via proxy so the dispatcher hits timeouts; measure attempt counts and wait durations.
3. Restore connectivity; verify new requests succeed **and** `PENDING` rows reprocess.
4. Audit every ID: zero lost records, zero duplicate side effects, accurate outbox states.
5. Repeat with a crash right after warehouse processes the call and before the dispatcher marks `PROCESSED`.

### Scenario B: Recovery Under Overload

1. Use multiple producers/replicas to generate a visible backlog within staging limits.
2. Have downstream return 429/503 or enforce a requests/sec cap.
3. Observe retries, queue bounds, rejections, circuit breakers, and latencies.
4. Restore downstream with finite capacity; verify replays are **paced** rather than firing simultaneously.
5. Wait for backlog drain within deadline. Reconcile accepted, completed, terminal failure, and remaining counts.
6. Confirm CPU, heap, thread/connection pools, and end-to-end latency return within acceptable bounds.

### Scenario C: Flapping Outages

1. Keep downstream healthy for 10s, down for a few seconds, briefly up, down again, then stable.
2. Verify circuit breakers and backoff avoid hot retry loops.
3. Verify outbox/queues stay within capacity and due jobs retain clear states.
4. Once downstream stabilizes, verify backlog drains completely with no records stranded in intermediate states.

**Passing criteria:** tests pass only by proving fault reproducibility, measured recovery times, honored retry/timeout budgets, 100% reconciliation of accepted work, zero duplicate side effects, and sustained exit from overload.

## 14. Pipeline Integration Checklist

- [ ] Tests distinguish real connectivity loss, HTTP 5xx, HTTP 429, 4xx contract errors, and uncertain-outcome timeouts.
- [ ] Per-attempt timeouts and total retry budgets enforced; permanent errors never retry blindly.
- [ ] Tests verify dependency return: new requests succeed, backlogs drain, and pending jobs complete.
- [ ] Fault injection covers both open-connection drops and post-processing lost-response timeouts.
- [ ] Queue bounds, concurrency caps, thread/connection pools, and load-shedding/backpressure policies enforced.
- [ ] Multi-replica reconnect retry storms tested with backoff/jitter or gradual ramp-up.
- [ ] Idempotency, reconciliation, and crash/ack/commit windows covered by tests.
- [ ] External DB/broker side effects verified directly, not merely counted at message intake.
- [ ] Time-to-resume, time-to-drain, event age, error rate, and resource usage measured against SLOs.
- [ ] Isolated test data, conditional timeouts, cleanup hooks, and state-reset tooling in place.

**Conclusion:** Connection restoration is only step one; true recovery proves **zero lost data, zero duplicate side effects, completion of pending work, and stability without re-overload**. In Spring Boot, solid recovery test suites trace from HTTP/DB/cache/brokers through transactions, acks/commits, outboxes, and Spring Integration adapters—combining fault injection, controlled load, idempotency, and reconcilable business metrics.
