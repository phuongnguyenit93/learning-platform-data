# Scatter-Gather and Limits of Coordinating Multiple Systems

In **SPRING_BOOT_INTEGRATION**, a Spring Boot flow may need to coordinate multiple HTTP clients, databases, caches, message brokers, and Spring Integration adapters. A classic scenario: the application receives **one request** and must fetch data from **multiple systems** before returning **one response**. The **scatter-gather** pattern splits this flow into two phases: **scatter** distributes the request across branches, while **gather** collects related replies and decides when to emit a combined result.

Scatter-gather looks simple on a diagram, yet is far from simple in operations. When one source is slow, returns an error, replies twice, or responds late, the application must decide whether to keep waiting, return partial data, fail, or switch to asynchronous processing. When branches **mutate state** rather than just reading, gathering results also entails transaction boundaries and recovery when only a subset of systems committed.

The goal of this lesson is to apply scatter-gather with accurate semantics in Spring Integration and recognize the limits of **timing, consistency, errors, stateful memory, duplicate messages, and observability** in real integration flows.

## 1. Running Scenario: Requesting Quotes from Three Partners

Suppose a **Quoting** service receives an HTTP API request and needs price quotes from partners A, B, and C. Each partner has its own endpoint, rate limits, latency, and data contract. The application converts prices to VND, checks validity timestamps, and picks the lowest valid quote.

~~~mermaid
flowchart TD
  IN["HTTP request: quote SKU-001"] --> SG["Scatter: fan-out by partner list"]
  SG --> A["HTTP Client A"]
  SG --> B["HTTP Client B"]
  SG --> C["HTTP Client C"]
  A --> GA["Gather: correlation + group"]
  B --> GA
  C --> GA
  GA --> REL{"Release condition met?"}
  REL -->|Met| MAP["Normalize, pick best quote, build response"]
  REL -->|Not yet| WAIT["Wait for replies or group expiry"]
  WAIT --> GA
  MAP --> OUT["HTTP response"]
~~~

Illustrative **hypothetical** figures, not real SLAs:

| Partner | Result | Duration |
| --- | --- | --- |
| A | 400,000 VND | 120 ms |
| B | 390,000 VND | 700 ms |
| C | Timeout | Still no reply after 1,000 ms |

If the rule is **all-of-3**, full aggregation cannot complete while C is unresponsive. If the rule is **at least 2 of 3 valid quotes**, you can return B's price marked **PARTIAL**. If business rules mandate C, having both A and B complete is still insufficient. Completion rules are a **business contract**, not something the framework can guess on its own.

Decide before implementing:

1. Which branches are invoked per request: a fixed list, or dynamically routed by SKU, region, permissions, or customer tier?
2. Do we require all replies, K valid replies, or only the first reply matching a criterion?
3. Does one branch failing fail the whole request? Can cached data or partial results be returned?
4. Once a response is sent, should late replies be discarded or routed to another workflow?

## 2. Distinguishing Scatter-Gather from Other Enterprise Integration Patterns

| Pattern | Unit Distributed | Purpose |
| --- | --- | --- |
| **Splitter** | Distinct parts of one payload | Splitting an order into line items |
| **Content-Based Router** | One message routed to a chosen branch by condition | Sending international orders to a dedicated adapter |
| **Publish-Subscribe** | One message to multiple subscribers | Broadcasting the same event to multiple departments |
| **Recipient List Router** | One message to a selected recipient set | Requesting quotes from A and C for a product |
| **Aggregator** | Multiple messages belonging to one group | Consolidating replies into a list or computed result |
| **Scatter-Gather** | One request sent to multiple recipients and replies gathered | Querying multiple sources and returning one result |

In Spring Integration, **ScatterGatherHandler** pairs a distributor with an **AggregatingMessageHandler**. Distribution comes in two primary forms:

- **Auction:** backed by a **PublishSubscribeChannel**, convenient when every request hits the same subscriber set.
- **Distribution:** backed by a **RecipientListRouter**, allowing dynamic recipient selection by condition. This is common when each SKU matches only certain suppliers.

Both are different scatter modes of the same endpoint. The gather side always needs correlation, a release condition, a group store, and an output processor. Spring Integration also lets you compose individual EIP components directly when requirements exceed standard request-reply flows.

## 3. Correlation, Sequence, and Reply Paths

### 3.1. Why Never Group Simply by Arrival Time?

Suppose two HTTP requests **R-101** and **R-102** execute concurrently. Partner A's reply for R-102 may return before Partner A's reply for R-101. If the aggregator simply bundles the next three arriving messages, two customers' quotes get mixed. Each fan-out needs a **stable, unique group identifier**.

Spring Integration uses critical message headers:

| Header | Role |
| --- | --- |
| **correlationId** | Identifies messages belonging to one gather group |
| **sequenceNumber** | 1-based index in the group, helpful for tracking sources and order |
| **sequenceSize** | Expected reply count when waiting for a full sequence |
| **replyChannel** | Path collecting replies from recipients to forward to the gatherer |
| **errorChannel** | Error handling path, especially when branches run asynchronously |

**applySequence=true** attaches correlation and sequence metadata to distributed messages. Starting with Spring Integration **6.0**, XML and Java DSL scatter-gather configurations enable apply-sequence automatically in standard setups. When assembling **ScatterGatherHandler** and scatterers manually in Java, ensure this configuration or provide an explicit correlation strategy.

With a dynamically filtered **RecipientListRouter**, `sequenceSize` must match **the actual selected recipient count**, not the total registered partners in the application. If only A and B are called while the group waits for three replies, gathering stalls until timeout even when both sources succeed.

~~~mermaid
sequenceDiagram
  participant API as API Gateway
  participant SG as ScatterGatherHandler
  participant A as Supplier A
  participant B as Supplier B
  participant C as Supplier C
  participant G as Aggregator
  API->>SG: request R-101
  SG->>A: correlation=g-1; seq=1/3
  SG->>B: correlation=g-1; seq=2/3
  SG->>C: correlation=g-1; seq=3/3
  A-->>G: quote A; correlation=g-1
  C-->>G: quote C; correlation=g-1
  B-->>G: quote B; correlation=g-1
  G->>G: ReleaseStrategy + MessageGroupProcessor
  G-->>SG: aggregate reply
  SG-->>API: single response
~~~

Keep an application-generated **requestId** in the payload or a clearly contracted transport header for tracing across HTTP, DBs, and brokers. Never equate business `requestId` with internal `correlationId` if an application may scatter multiple times for the same request.

### 3.2. What Does the Gatherer Do?

**AggregatingMessageHandler** has four core pieces:

1. **CorrelationStrategy:** assigns each reply to the right message group.
2. **MessageStore:** holds collected replies and group metadata until release.
3. **ReleaseStrategy:** decides whether the group is ready.
4. **MessageGroupProcessor:** transforms collected replies into one output—such as a list, best quote, or partial-result object.

By default, release checks **full `sequenceSize`** and output is a list of payloads. However, an error message placed into the group also increments the received reply count. Thus, **having enough replies** and **having enough valid replies** are two different things.

## 4. Illustrative Java DSL Configuration

The following example runs on Spring Boot with modern Spring Integration Java DSL. HTTP adapters sit behind a **QuoteClients** interface separating external calls from orchestration.

~~~java
// Domain types; split into separate files in real implementations.
public record QuoteRequest(
        UUID requestId, String sku, int quantity) {}

public record SupplierQuote(
        String supplier, BigDecimal totalVnd, Instant validUntil) {}

public interface QuoteClients {
    SupplierQuote quoteA(QuoteRequest request);
    SupplierQuote quoteB(QuoteRequest request);
    SupplierQuote quoteC(QuoteRequest request);
}
~~~

~~~java
@Configuration
public class QuoteIntegrationConfig {

    @Bean
    IntegrationFlow bestQuoteFlow(QuoteClients clients) {
        return IntegrationFlow.from("quoteRequests")
            .scatterGather(
                scatter -> scatter
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteA(request)))
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteB(request)))
                    .recipientFlow(f -> f.handle(
                        (QuoteRequest request, Map<String, Object> headers) ->
                            clients.quoteC(request))),
                gather -> gather
                    .outputProcessor(group -> group.getMessages().stream()
                        .map(message -> (SupplierQuote) message.getPayload())
                        .filter(q -> q.validUntil().isAfter(Instant.now()))
                        .min(Comparator.comparing(SupplierQuote::totalVnd))
                        .orElseThrow(() ->
                            new IllegalStateException("No valid quote"))),
                scatterGather -> scatterGather
                    .gatherTimeout(1_500)
                    .requiresReply(true))
            .channel("quoteResults")
            .get();
    }
}
~~~

~~~java
// Caller-facing gateway decoupled from message channels.
@MessagingGateway
public interface BestQuoteGateway {
    @Gateway(requestChannel = "quoteRequests", replyTimeout = 2_000)
    SupplierQuote bestQuote(QuoteRequest request);
}
~~~

**What this example shows:**

- The scatterer defines three recipient flows; each invokes an adapter and **returns a reply**, never terminating in a side-effect-only sink.
- The gatherer reads `SupplierQuote` payloads, filters out expired quotes, and selects the lowest VND total. This is a **happy-path** example assuming every branch returns a valid object in the same currency and price terms.
- **gatherTimeout(1_500)** caps waiting for the aggregator's reply in **milliseconds**. It does not configure HTTP client timeouts and does not automatically construct partial results.
- **requiresReply(true)** requires a reply; timing out without a result throws an exception instead of returning normally.
- Add the appropriate imports from Spring Integration, Spring Framework, and the Java standard library. `QuoteClients` needs a Spring bean implementation configured with proper connect/read/response timeouts.

Notably, synchronous channels like **DirectChannel** invoke handlers on the current thread. The three recipient flows here **are not guaranteed to run in parallel** merely because the pattern is called scatter-gather. If the first adapter blocks, sending to subsequent adapters is delayed; gather timeout does not enforce a **request-wide end-to-end deadline**.

### 4.1. Parallelism with Bounded ExecutorChannel

To call suppliers concurrently, place an **ExecutorChannel** at the start of each recipient subflow before calling the adapter:

~~~java
// Illustrating ONE branch; apply the same principle to others.
.recipientFlow(f -> f
    .channel(c -> c.executor(providerExecutor))
    .handle((QuoteRequest request, Map<String, Object> headers) ->
        clients.quoteA(request)))
~~~

**providerExecutor** should have bounded threads, a bounded queue, and an explicit rejection policy. When an async branch throws an exception, errors typically route to **errorChannel** instead of returning as replies; handle them explicitly so the aggregator does not hang waiting for a missing reply. When building a reply from an async error, preserve required reply and correlation headers.

When using newer Spring Integration **async/reactive** modes, waiting semantics can differ. Always check the exact library version your project runs, especially when relying on non-blocking behavior.

## 5. Partial Results: Modeling Failures as Data

A pragmatic strategy for quoting is having **each branch strive to return a status-bearing reply**, even on partner network errors. That tells the gatherer which sources succeeded, failed, or returned bad data instead of merely leaving an incomplete group.

~~~java
public enum SupplierStatus {
    OK, TIMEOUT, UNAVAILABLE, INVALID_RESPONSE
}

public record SupplierResult(
        String supplier,
        SupplierStatus status,
        BigDecimal totalVnd,       // present only when OK
        Instant validUntil,        // present only when OK
        String errorCode) {}
~~~

~~~java
SupplierResult callSupplierA(QuoteRequest request) {
    try {
        SupplierQuote quote = clients.quoteA(request);
        return new SupplierResult(
            "A", SupplierStatus.OK,
            quote.totalVnd(), quote.validUntil(), null);
    } catch (ResourceAccessException e) {
        return new SupplierResult(
            "A", SupplierStatus.UNAVAILABLE,
            null, null, "NETWORK_ERROR");
    } catch (HttpServerErrorException e) {
        return new SupplierResult(
            "A", SupplierStatus.UNAVAILABLE,
            null, null, "UPSTREAM_5XX");
    }
}
~~~

In production, **distinguish** connect timeouts, read timeouts, HTTP 429, permanent 4xx, transient 5xx, and invalid JSON schemas. Never swallow arbitrary **RuntimeException**s into valid data, which hides code bugs. Never expose raw exceptions, tokens, or sensitive partner response bodies on public APIs.

Combining **SupplierResult** objects enables a richer output structure than returning a bare quote:

~~~json
{
  "requestId": "d0e3e4d3-4bc8-4c52-bd08-6b3a18ab32c1",
  "status": "PARTIAL",
  "expected": 3,
  "received": 2,
  "bestQuote": {
    "supplier": "B",
    "totalVnd": 390000
  },
  "failures": [
    {
      "supplier": "C",
      "code": "NETWORK_ERROR"
    }
  ]
}
~~~

Here **PARTIAL** states clearly that the comparison covers only partners returning valid data within the deadline. If business rules mandate C, never reuse this response to treat the process as completed.

## 6. Choosing a Release Strategy Aligned with Business Commitments

| Policy | Release Condition | Limitations |
| --- | --- | --- |
| **All-of-N** | All N sequence replies arrive | Heavily impacted by a single slow or silent source |
| **K-of-N** | At least K valid replies arrive | May miss a better result from a slower source |
| **First-valid** | First reply meeting criteria arrives | Favors speed; does not guarantee global best |
| **Priority sources** | Mandatory sources plus minimum count arrive | Must accurately identify completed sources |
| **Deadline partial** | Group deadline expires with at least one usable result | Requires partial expiry config and explicit missing-source reporting |

Example **K=2** on **SupplierResult** messages:

~~~java
// Pseudocode expressing business rule, not a full flow.
boolean canRelease(MessageGroup group) {
    long usable = group.getMessages().stream()
        .map(m -> (SupplierResult) m.getPayload())
        .filter(r -> r.status() == SupplierStatus.OK)
        .count();
    return usable >= 2;
}
~~~

In a **K-of-N** setup, decide how to handle:

- A and B succeed fast, while C returns a lower price after the response was already sent.
- Only A succeeds while B and C fail; K=2 will **never be reached**, even though all three branches finished.
- C sends the same reply twice; raw message counts could falsely satisfy K.
- A dynamic recipient list chose only A and C; K=2 represents all chosen sources, not 2 of 3 registered partners.

Release strategies normally run when new replies arrive. If no more replies arrive, K=2 never transitions to partial on its own; add a **dedicated timeout/expiry policy** with a scheduler and output/error handling.

## 7. Different Types of Timeouts

| Timeout/Limit | Example | Effect |
| --- | --- | --- |
| **HTTP client connect/read timeout** | 200 ms connect, 800 ms response | Prevents individual adapters from blocking indefinitely |
| **Retry policy, circuit breaker, bulkhead** | Max 2 attempts with backoff, 20 concurrent calls/source | Bounds attempts and resources spent on external sources |
| **Gather timeout** | 1,500 ms | Bounds how long `ScatterGatherHandler` waits for aggregator output |
| **Group timeout** | Expire group after 1,200 ms | Decides when to clean up or handle groups missing replies |
| **Gateway/HTTP deadline** | 2,000 ms | Total wait limit acceptable to the caller |

**Gather timeout does NOT equal group timeout.** A request can exceed `gatherTimeout` inside `ScatterGatherHandler` while **the message group remains in the store**, waiting for the last branch. Configure **groupTimeout**, **sendPartialResultOnExpiry**, a task scheduler, discard channels, and group cleanup per policy. Never set `gatherTimeout` alone expecting the framework to emit partial lists and reclaim stored messages automatically.

In Spring Integration 6.5/7.x, current documentation notes a default gather timeout of **30 seconds**; configure explicitly to match your SLA rather than relying on defaults or older version behavior.

Illustrative **hypothetical** time budget for a 2,000 ms HTTP API:

~~~text
HTTP request -------------------------------------------------- response
  0 ms                      1,500 ms                       2,000 ms
  |---- dispatch + group wait ---|---- serialize / network ----|
        HTTP calls enforce                  500 ms reserve
        timeouts and rate limits
~~~

Real budgets must also account for queue wait, authentication, request building, cache/DB lookups, serialization, and network time. With synchronous branches, gather timeout may **not bound the entire fan-out duration**, since dispatching to recipients also consumes time. Measure end-to-end deadlines and skip or cancel work once the caller's budget expires.

**All-of-N** policies experience latency close to the **slowest branch** (when truly parallel). Adding more external dependencies increases the probability of hitting tail latency. Parallelism reduces latency compared to sequential calls when sources are healthy, yet never makes slow or unreliable upstreams faster or safer.

## 8. MessageStore, Late Replies, Duplicates, and Restarts

**An Aggregator is stateful**, unlike typical filters or routers. It stores replies until release conditions hold. In-memory **SimpleMessageStore** fits small, short-lived flows; on process restart, in-memory group state disappears.

For crash-recoverable flows, consider a **persistent `MessageGroupStore`**, cross-instance locking, and group expiry metadata. Still, persisting groups in a database **will not resurrect a dead HTTP request thread**. For long-running or replayable jobs, persist job state and use callbacks or polling.

Key decisions:

- **Late replies:** after release or caller timeout, are trailing replies discarded, audited, or emitted as updates? An already-sent HTTP response cannot be silently rewritten.
- **Duplicate replies:** key deduplication at least by `requestId + supplierId` (plus `attemptId` if retries constitute distinct versions). Never treat plain **sequenceNumber** as business idempotency.
- **Completed group metadata:** deleting too soon lets late replies form a brand-new group; retaining forever balloons RAM/storage. Define retention and cleanup.
- **Incomplete groups:** without expiration when a final message never arrives, groups linger indefinitely, especially under high traffic.
- **Horizontal scaling:** replies sharing a `correlationId` hitting different instances cannot merge across isolated in-memory stores. Route matching keys to the same instance or use shared stores/locking.
- **Message contract:** when transforming payloads, preserve correlation, sequence, and reply headers. Building fresh messages without them prevents the gatherer from completing.

Understand **expireGroupsUponCompletion**, **sendPartialResultOnExpiry**, **discardChannel**, and group cleanup policies before tuning them; they govern both memory footprint and how late or duplicate replies behave.

## 9. Classifying Errors and Coordinating Recovery

| Scenario | Potential Consequence | Recommended Policy |
| --- | --- | --- |
| A returns HTTP 503 | One branch has no quote | Convert to **UNAVAILABLE** if partials are allowed; circuit breaker |
| B returns 429 | Retry storm causes overload | Respect quota/`Retry-After`, jittered backoff |
| C read timeout | Missing reply; all-of-N stalls | Per-branch timeout, deadline, and group expiry |
| Synchronous branch throws | Exception bubbles to caller, wasting other branches | Catch expected errors or wrap branches with advice |
| Async branch throws | Error enters error channel; aggregator misses reply | Configure **errorChannel** and emit an error reply keeping correlation/reply headers |
| Source returns invalid schema | Cast/transform failure or wrong pricing | Validate DTO before entering gather |
| Differing currencies/taxes | Invalid comparison | Normalize and verify contracts before taking min |
| Branch sends duplicate reply | Inflates valid reply count | Deduplicate by source/request and test concurrency |
| Reply arrives post-timeout | Caller gone, group retained | Late-reply policy, discard, metered cleanup |

When branches run over **ExecutorChannel**, errors normally flow to an error channel via async error handling. To turn an error into a gatherer reply, that reply must **preserve required headers** (`replyChannel`, correlation/sequence, and internal framework headers) from the failed message. Otherwise the request hangs and surfaces only as a timeout. Never log full payloads or exceptions containing tokens, PII, or partner response bodies.

## 10. The Most Important Limit: No Distributed Transactions

Scatter-gather **coordinates messages**; it does not turn multiple HTTP calls, databases, and brokers into **one ACID transaction**. Consider another task: sending **stock reservation** commands to three warehouses rather than read-only quote lookups.

~~~mermaid
sequenceDiagram
  participant API as Booking API
  participant A as Warehouse A
  participant B as Warehouse B
  participant C as Warehouse C
  API->>A: Reserve(order-1)
  A-->>API: COMMITTED
  API->>B: Reserve(order-1)
  B-->>API: COMMITTED
  API->>C: Reserve(order-1)
  Note over C: May have committed
  C--xAPI: Timeout / lost reply
  Note over API,C: Gather lacks full results while A and B already reserved stock
~~~

Spring Boot's **@Transactional** protects only resources managed by that local transaction manager, such as one local database. It never rolls back committed reservations on A and B when C times out. Worse, **a timeout does not prove failure**: C may have committed while the response dropped on the wire. Blind retries risk double-reserving stock.

For mutating commands, prefer:

1. **Idempotency keys** on every command plus status-query APIs when outcomes are uncertain.
2. **Sagas/compensation** for already-committed steps: e.g., canceling A/B reservations if the overall flow fails.
3. **Durable workflow state** in a DB/workflow engine when work spans seconds/minutes or needs post-restart retries.
4. **Transactional Outbox** when updating a DB and publishing broker events; **Inbox/idempotent consumers** for redeliveries.
5. **Reconciliation** comparing caller state against target systems.

A gather returning **FAILED** does not undo side effects already executed on other systems. Distinguish three problem classes: **multi-source read aggregation**, **multi-target write commands**, and **long-running workflow orchestration**. Scatter-gather excels at the first; the latter two require durable state and explicit recovery contracts.

### Crossing HTTP, Brokers, or Separate Processes

When combining Spring Integration with RabbitMQ, Kafka, or external HTTP adapters, reply paths are no longer simple in-JVM channels. Internal **replyChannel** objects cannot simply be serialized across the network. Design:

- Correlation/request IDs carried in transport-supported headers or versioned payloads.
- Reply routing via transport gateways or dedicated reply queues/topics and handlers.
- Deadlines, TTLs, deduplication, retries, and **orphan reply** handling after callers exit.
- Ack/commit policies and idempotency for broker redeliveries.
- For slow work, return **HTTP 202 Accepted + jobId**, persist state, and provide polling or webhooks rather than holding HTTP connections open indefinitely.

Never assume an **AMQP outbound adapter** automatically behaves like a request-reply gateway. Pick the proper gateway/adapter and test reply contracts for your transport.

## 11. System Load and Fan-Out Amplification

If the system receives **R** requests/sec and each hits **N** sources, outbound load is roughly:

\[
\text{Outbound requests per second} \approx R \times N
\]

For example, **100 requests/sec × 4 suppliers ≈ 400 HTTP calls/sec**, before counting retries. Four slow suppliers consume far more threads than sequential calls, even though customer latency improves when sources respond cleanly.

To prevent failure amplification:

- **Bounded concurrency:** cap thread pools, HTTP connection pools, semaphores, and queues with clear overload rejection.
- **Bulkheads/circuit breakers:** isolate each partner so one slow supplier cannot starve the entire service.
- **Rate limits and backoff retries:** honor partner quotas, cap retries, and never retry non-retryable HTTP 4xx errors.
- **Deadline propagation:** avoid launching fresh outbound calls once the request budget is nearly spent.
- **Freshness-aware caching:** offload relatively static lookups without serving stale prices where real-time quotes are required.
- **Limit dynamic recipients:** prevent router misconfigurations from fanning out one request into hundreds of unintended calls.

Parallel execution pushes all-of-N latency toward the **slowest branch**; adding more sources raises the odds of hitting tail latency. Measure **end-to-end p95/p99**, not merely average individual HTTP client latency.

## 12. Observability and Testing Critical Invariants

### 12.1. Logging, Tracing, and Metrics

| Layer | Data to Measure |
| --- | --- |
| Gateway | `requestId`, `traceId`, deadline, final status, total duration |
| Scatter | `correlationId`, actual recipient count, order, dispatch outcome |
| HTTP client | Source name, latency, HTTP status, retry count, circuit state |
| Gather | Group size, expected size, OK count, release reason, age, timeout count |
| Operations | Incomplete groups, `MessageStore` size, late/discarded replies, executor saturation |

Logs and traces use `requestId` and `correlationId` to stitch steps together. Tag metrics by supplier name and error kind; **never** put `requestId` in Prometheus labels due to unbounded cardinality. Alert on rising partial rates, surging group timeouts, growing group backlogs, or thread-pool saturation.

### 12.2. Test Matrix

| Case | Desired Outcome |
| --- | --- |
| A/B/C all succeed | Single response comparing matching currency and valid quotes |
| One supplier returns 503 | Clear partial/error policy; group does not hang |
| K=2, only A/B succeed | Early release allowed if business permits |
| K=2, only A succeeds | Partial/error after deadline; state not retained forever |
| Source sends duplicate reply | Never double-counts toward quorum or triggers duplicate side effects |
| Two concurrent requests | Replies never mix across `correlationId`s |
| Recipient router picks only two sources | `sequenceSize` and release reflect the two selected sources |
| Async handler throws exception | `errorChannel`/fallback responds; caller never hangs |
| Late reply arrives | Discarded/audited per policy; never sends a second HTTP response |
| Restart mid-gather | Group loss or recovery is controlled and observable |
| Traffic spike, slow suppliers | Pool limits, backpressure, and deadlines hold |

Use **Spring Integration Test** for message flows, **MockWebServer/WireMock** for HTTP partners, and **Testcontainers** when databases, Redis, or RabbitMQ are involved. For timing tests, use deterministic synchronization controls rather than scattered sleeps that create flaky suites.

Example feature acceptance criterion: **given three partners, if at least two valid quotes arrive within 1,500 ms, return PARTIAL or COMPLETE reflecting source statuses; late replies never alter sent responses; expired groups clean up per policy; concurrent requests never mix replies.** This requires explicit release, expiry, and output contracts—it is **not default behavior** of the all-of-N example in section 4.

## 13. Pre-Production Checklist

- [ ] Define **N/K**, mandatory sources, release rules, and response when data is insufficient.
- [ ] Establish unified request/reply contracts: `requestId`, `supplierId`, `schemaVersion`, currency units, and validity deadlines.
- [ ] Verify **`correlationId`**, `sequenceSize`, `replyChannel`, and `errorChannel` across every branch.
- [ ] Configure per-adapter timeouts, gather timeout, group expiry/cleanup, and overall API deadline.
- [ ] Enforce executor/connection pool limits, rate limits, circuit breakers, and backoff retries.
- [ ] Handle partial results, late replies, duplicates, restarts, and observable `MessageStore` state.
- [ ] For side-effecting branches, implement idempotency and compensation/reconciliation.
- [ ] Test concurrent requests, partial failures, timeouts, overload, and recovery paths.

**Principle to remember:** **Scatter-gather coordinates fan-out queries and response aggregation.** It does not guarantee distributed commits across external systems, provide end-to-end exactly-once semantics, or know by itself what counts as enough data. Reliable designs start with **data contracts, correlation, release policies, deadlines, failure policies, and recovery strategies**.

### Reference Documentation

- [Spring Integration Reference — Scatter-Gather](https://docs.spring.io/spring-integration/reference/scatter-gather.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
