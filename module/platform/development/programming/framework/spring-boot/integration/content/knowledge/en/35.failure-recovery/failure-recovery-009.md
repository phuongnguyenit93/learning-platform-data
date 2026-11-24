# Business-Meaningful Fallbacks Without Masking Data Errors

## 1. Why Is a Fallback Not Simply Returning a Default Value?

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot coordinates HTTP clients, databases, caches, message brokers, and Spring Integration adapters. These flows must manage configuration, data contracts, transactions, errors, deduplication, testing, and live observability. A fault-tolerant system must not merely stay up when a downstream fails; it must also **never trick users or other services into trusting incorrect data**.

A **fallback** is a pre-designed alternative behavior when the primary path fails or is temporarily unavailable. It may return a verified, sufficiently fresh snapshot, shed optional features, park work in a **PENDING** state, route an event to recovery, or **fail safely** when no trustworthy result can be produced.

Three examples:

- Product recommendation service goes down: hide the recommendation widget or serve a curated fallback list, since it does not affect the core checkout transaction.
- Shipment tracking service returns 503: show the **last verified status from 10:00**, clearly flagged as potentially stale—never present it as real-time truth.
- Payment confirmation API times out: **never** assume payment failed, assume it succeeded, or issue a second charge. Treat it as an **indeterminate outcome** requiring reconciliation by idempotency key.

Therefore, fallbacks need **business semantics, trusted data provenance, freshness limits, explicit uncertainty indicators, and recovery workflows**. Writing **`onErrorReturn(Collections.emptyList())`**, **`catch (Exception) { return true; }`**, or returning arbitrary defaults is not true fault tolerance.

After this lesson, you will be able to:

1. Distinguish transient infrastructure failures, business outcomes, data contract violations, security failures, and uncertain outcomes.
2. Decide when to **fail-open**, **fail-closed**, serve bounded stale data, or return `PENDING`.
3. Design fallbacks with explicit provenance, freshness, semantics, and time bounds.
4. Wire fallbacks into WebClient/Reactor, Resilience4j, or Spring Integration without hiding critical defects.
5. Preserve transaction, ACK, retry, idempotency, dead-letter, and event-replay boundaries.
6. Test fallbacks using realistic failure scenarios, metrics, and API contracts.

## 2. Classify Errors Before Deciding Whether to Fall Back

A blanket **`catch Exception`** lacks the context required to pick a safe fallback. Build a taxonomy by root cause and consequence:

| Error / Outcome Type | Examples | Fallback Allowed? | Usually Appropriate Handling |
| --- | --- | --- | --- |
| **Transient infrastructure** | HTTP 503/504, connection timeout, brief DB overload | Conditionally | Bounded retry, circuit breaker, verified substitute data |
| **Rate limit** | HTTP 429 | Conditionally | Honor `Retry-After`, shed load, cache if contract permits |
| **Business not found** | Order ID genuinely does not exist | Usually **no** | Return 404 or domain `NotFound`; never turn into 503 or stale data |
| **Business rejection** | Out of stock, payment declined | **Never** replace with success | Preserve business rejection outcome |
| **Invalid data/contract** | Malformed JSON, missing required field, unknown schema version | **Never** mask error | Report contract violation, quarantine payload, investigate producer |
| **Security failure** | Invalid signature, insufficient token permissions | **Never** fail-open | Deny access and log security alert; never serve stale sensitive data |
| **Uncertain side effect** | HTTP POST times out after sending request | Never guess success/failure | Query by idempotency key, keep `PENDING`, reconcile |
| **Cache miss** | No valid backup entry exists | Nothing to fall back to | Return error/degrade feature per contract; never fabricate data |
| **Cached data expired/poisoned** | Snapshot past max staleness or wrong tenant | **Never** use | Fail closed for that data; purge cache and reconcile |
| **Circuit open** | Circuit breaker blocks upstream calls | Conditionally | Verified fresh-enough backup data or explicit unavailable response |

**A 404 carries business information**, whereas a 503 indicates upstream availability. Never collapse both into **`Optional.empty()`** when callers must distinguish **no data exists** from **data is currently unreachable**.

### 2.1. Classify at the Adapter Boundary

An HTTP adapter should translate transport exceptions into business-meaningful error types:

~~~text
WebClientResponseException.NotFound
       → TrackingNotFoundException

HTTP 503, 504, or classified timeout
       → TrackingTemporarilyUnavailableException

JSON decode error / missing required field
       → TrackingContractViolationException

HTTP 401 or 403
       → UpstreamAuthorizationFailureException
~~~

These exception types are **application conventions**, not Spring defaults. Never build classifiers by inspecting **`exception.getMessage()`** text, which varies across drivers, locales, proxies, and library versions.

### 2.2. Retryable Errors Differ from Fallback-Eligible Errors

Two separate decisions:

- **Retryable** means the same operation can be repeated safely with a chance of succeeding.
- **Fallback-eligible** means an alternative response **still satisfies the business contract**.

For example, an HTTP GET 503 may be both retryable and eligible for a cache fallback. A payment POST 503 may require status lookup and must **never** fall back to **`paid=true`**. Malformed JSON payloads are neither retryable nor eligible for guessed fallback values.

## 3. Fail-Open, Fail-Closed, and Degraded-Mode Matrix

**Fail-open** lets the main flow proceed when an auxiliary service is unavailable. **Fail-closed** halts actions that require authoritative data. **Degraded mode** visibly serves reduced functionality with explicit bounds.

| Business Flow | When Upstream Fails | Acceptable Behavior | Dangerous Behavior |
| --- | --- | --- | --- |
| Product recommendations widget | Recommendation API fails | Hide optional widget; checkout proceeds unaffected | Label a generic default list as "personalized" |
| Shipment tracking lookup | Tracking API returns 503 | Show last verified status with timestamp and **STALE** badge | Present stale data as live status |
| Estimated delivery time | ETA service fails | Display "estimate unavailable" if contract allows | Promise a fabricated exact delivery date |
| Pre-sale stock check | Inventory service fails | Block confirmation or hold as **PENDING** | Default to **`available=true`** |
| Payment processing | Provider times out | **`UNKNOWN/PENDING`** state; query status by request ID | Assume success, or assume failure and charge again |
| Authorization/tenant isolation | Auth service fails | Deny access to protected resources | Grant full access when decision is unavailable |
| Ledger / reconciliation write | Database unavailable | Queue command durably or report unavailable | Report write success before commit |
| Mandatory audit event | Publisher cannot send | Outbox/retry; never report false completion | Swallow error and ACK source if audit would be lost |

For data driving **irreversible actions**, lean toward **fail-closed** or pending reconciliation. For **non-essential presentation data**, fail-open can make sense.

### 3.1. Mandatory Questions Before Approving a Fallback

1. **Which decisions** will callers or users make using the fallback result?
2. **Where does the fallback data come from**, and has it passed schema, tenant, and version validation?
3. What is the **maximum acceptable staleness** for this specific business flow?
4. Can callers **clearly tell it is a fallback** and choose an alternate action?
5. If no valid fallback exists, is there a **clear error code or `PENDING` state**?
6. Does the fallback path introduce **side effects** or break idempotency?
7. How will outcomes be **measured, reconciled, and recovered** once upstream heals?

Never approve a fallback solely because it lowers the HTTP 5xx percentage on dashboards.

## 4. Fallback Data Contracts: Provenance, Freshness, and Certainty

A shipment tracking API may return the last verified status as a fallback, explicitly stating:

~~~json
{
  "orderId": "O-204",
  "state": "IN_TRANSIT",
  "freshness": "STALE",
  "sourceUpdatedAt": "2026-11-21T09:58:00Z",
  "servedAt": "2026-11-21T10:02:00Z",
  "notice": "Last verified tracking update; live provider unavailable"
}
~~~

Here:

- **`state=IN_TRANSIT`** is the **previously verified** status, not a guarantee of current status.
- **`sourceUpdatedAt`** is when the upstream source recorded that state—not when the cache was read.
- **`servedAt`** indicates when this response was generated.
- **`freshness=STALE`** lets UIs and consumers separate cached data from live data.
- **`notice`** is human-readable explanation; machine logic must inspect structured fields, never parse English text.

### 4.1. Strongly Typed Outcomes

~~~java
public enum Freshness {
    LIVE,
    STALE
}

public record TrackingView(
        String orderId,
        String state,
        Instant sourceUpdatedAt,
        Instant servedAt,
        Freshness freshness) {
}
~~~

Do not overload a business status field with **`status="UNKNOWN"`** pretending it shares the same domain semantics as **`IN_TRANSIT`** or **`DELIVERED`**. If no valid source data exists, return an error or a separate **availability** model rather than inventing an unverified domain record.

For larger systems, use a wrapper type:

~~~java
public sealed interface LookupOutcome<T>
        permits LookupOutcome.Available, LookupOutcome.Unavailable {

    record Available<T>(
            T value,
            Freshness freshness,
            Instant sourceUpdatedAt) implements LookupOutcome<T> {
    }

    record Unavailable<T>(
            String reasonCode,
            boolean retryable) implements LookupOutcome<T> {
    }
}
~~~

This Java 17+ example uses a **sealed interface** and records. The contract lets controllers cleanly separate **trusted data (`LIVE`/`STALE`)** from **unable to provide data**. Add a separate **`NotFound`** variant if the domain requires it—never lump it into unavailable.

### 4.2. Never Use HTTP Status Codes to Mislead Consumers

If the public contract explicitly allows snapshots, **HTTP 200 with `freshness=STALE`** can fit *informational* endpoints when documented in the API spec. Whenever callers need an authoritative decision, **HTTP 503** or an explicit **`PENDING`/`UNAVAILABLE`** state is safer.

Never return **HTTP 200 + empty body** by default for every failure; callers may interpret that as "processed, nothing found" and skip retries or reconciliation. Likewise, for **`UNKNOWN`** payment results, never return 200 **`PAID`** just because the HTTP request arrived.

## 5. Cache Fallback Policy: Serve Verified Data Only

A proper cache fallback must enforce **tenant match, entity match, valid schema, integrity, and max staleness**. Distinguish:

| Timestamp | Meaning |
| --- | --- |
| **`sourceUpdatedAt`** | When the state was actually updated at the system of record |
| **`verifiedAt`** | When this app validated and accepted the payload as trustworthy |
| **`cachedAt`** | When written to cache (may differ from `verifiedAt`) |
| **`expiresAt / maxStale`** | Storage TTL vs. permitted fallback staleness window |
| **`servedAt`** | When the fallback response was returned to the caller |

### 5.1. Cache TTL Differs from Maximum Staleness

A record might stay in Redis for 24 hours for reconciliation, yet that **does not mean the UI may present it as current for 24 hours**. Separate **retention TTL** from **fallback staleness limits**. Allowable staleness depends on the domain: optional recommendations tolerate hours; ETAs tolerate minutes; authoritative payment outcomes tolerate zero staleness.

Example cache entry:

~~~java
public record VerifiedTrackingSnapshot(
        String tenantId,
        String orderId,
        String state,
        Instant sourceUpdatedAt,
        Instant verifiedAt) {
}
~~~

Persist snapshots only after **full upstream payload validation**. Never write error JSON or unverified data into the fallback cache.

### 5.2. Protecting Tenant Key Isolation

Cache keys must encode tenant scope:

~~~text
tracking:v2:{tenantId}:{orderId}
~~~

Yet a `tenantId` from user input is **never inherently trusted**. Authenticate and authorize tenant identity at ingress, and verify both key and stored payload belong to that tenant on cache read. Serving another tenant's snapshot via fallback is a **security breach**, not "graceful recovery."

If a cache entry is poisoned, expired, or missing required fields, **never** bypass validation to boost fallback hit rates. Evict the entry, emit a classified metric, and fall back to rebuilding or reconciling from the source of truth.

## 6. `WebClient`: Fall Back Only on Permitted Errors

Full service-level example: reading shipment tracking over downstream HTTP and serving a verified snapshot on **timeout or 503/504**. Assumes WebFlux and a reactive snapshot store.

### 6.1. Contracts and Abstractions

~~~java
public record TrackingDto(
        String orderId,
        String state,
        Instant sourceUpdatedAt) {
}

public interface VerifiedTrackingStore {
    Mono<VerifiedTrackingSnapshot> findVerified(
            String tenantId, String orderId);
}

public final class TrackingNotFoundException
        extends RuntimeException {
    public TrackingNotFoundException(String orderId) {
        super("Unknown tracking order: " + orderId);
    }
}

public final class TrackingContractViolationException
        extends RuntimeException {
    public TrackingContractViolationException(String message) {
        super(message);
    }
}
~~~

**`VerifiedTrackingStore`** is an application interface backed by Redis, a database, or a document store. It must return only validated/approved snapshots—**never a raw cache of every response including failures**.

### 6.2. Service with Conditional Fallback

~~~java
@Service
public class OrderTrackingLookup {

    private static final Duration MAX_STALE =
            Duration.ofMinutes(5);
    private static final Duration MAX_SOURCE_AGE =
            Duration.ofHours(24);
    private static final Set<String> ALLOWED_STATES =
            Set.of("CREATED", "IN_TRANSIT", "DELIVERED");

    private final WebClient trackingWebClient;
    private final VerifiedTrackingStore snapshots;
    private final Clock clock;

    public OrderTrackingLookup(
            WebClient trackingWebClient,
            VerifiedTrackingStore snapshots,
            Clock clock) {
        this.trackingWebClient = trackingWebClient;
        this.snapshots = snapshots;
        this.clock = clock;
    }

    public Mono<TrackingView> find(
            String authenticatedTenantId,
            String orderId) {
        return trackingWebClient.get()
                .uri("/tracking/{orderId}", orderId)
                .header("X-Tenant-Id", authenticatedTenantId)
                .retrieve()
                .onStatus(
                        status -> status.value() == 404,
                        response -> Mono.error(
                                new TrackingNotFoundException(orderId)))
                .bodyToMono(TrackingDto.class)
                .switchIfEmpty(Mono.error(
                        new TrackingContractViolationException(
                                "Tracking response body is missing")))
                .map(dto -> verifiedLiveView(orderId, dto))
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(
                        this::isEligibleForFallback,
                        error -> fromVerifiedSnapshot(
                                authenticatedTenantId, orderId, error));
    }

    private TrackingView verifiedLiveView(
            String requestedOrderId, TrackingDto dto) {
        if (dto.orderId() == null
                || !dto.orderId().equals(requestedOrderId)
                || dto.sourceUpdatedAt() == null
                || !ALLOWED_STATES.contains(dto.state())) {
            throw new TrackingContractViolationException(
                    "Tracking response failed contract validation");
        }
        return new TrackingView(
                dto.orderId(),
                dto.state(),
                dto.sourceUpdatedAt(),
                clock.instant(),
                Freshness.LIVE);
    }

    private boolean isEligibleForFallback(Throwable error) {
        if (error instanceof TimeoutException) {
            return true;
        }
        if (error instanceof WebClientResponseException response) {
            int status = response.getStatusCode().value();
            return status == 503 || status == 504;
        }
        return false;
    }

    private Mono<TrackingView> fromVerifiedSnapshot(
            String tenantId, String orderId, Throwable originalError) {
        Instant now = clock.instant();

        return snapshots.findVerified(tenantId, orderId)
                .filter(entry ->
                        tenantId.equals(entry.tenantId())
                        && orderId.equals(entry.orderId())
                        && ALLOWED_STATES.contains(entry.state())
                        && entry.sourceUpdatedAt() != null
                        && entry.verifiedAt() != null
                        && !entry.verifiedAt().isAfter(now)
                        && !entry.sourceUpdatedAt().isAfter(now)
                        && Duration.between(
                                entry.verifiedAt(), now)
                                .compareTo(MAX_STALE) <= 0
                        && Duration.between(
                                entry.sourceUpdatedAt(), now)
                                .compareTo(MAX_SOURCE_AGE) <= 0)
                .map(entry -> new TrackingView(
                        orderId,
                        entry.state(),
                        entry.sourceUpdatedAt(),
                        now,
                        Freshness.STALE))
                .switchIfEmpty(Mono.error(originalError));
    }
}
~~~

Omitted imports: `WebClient`, `WebClientResponseException`, `Mono`, `Duration`, `Instant`, `Clock`, `Set`, `TimeoutException`, and `@Service`. **`authenticatedTenantId`** must come from verified security context, never blindly from an untrusted user header. Real apps must also verify the tenant owns that order and reject implausible future source timestamps.

Design points:

1. **404** maps to **`TrackingNotFoundException`** and **never** enters fallback.
2. 2xx responses with missing bodies or invalid schemas map to **`TrackingContractViolationException`**, **never** falling back.
3. Only **operator timeouts**, HTTP **503**, and **504** trigger fallback.
4. Snapshots must match tenant/`orderId`, allowed states, valid timestamps, **`verifiedAt` within 5 minutes**, and **`sourceUpdatedAt` within 24 hours** in this illustrative policy. Both thresholds are independent; tune in production by entity criticality.
5. If no valid cache entry exists, re-emit the **original error** instead of faking a status.
6. Fallback responses always carry **`Freshness.STALE`** and the original **`sourceUpdatedAt`**.

**Intentionally conservative scope:** Netty transport timeouts or connection failures may arrive as exception types other than **`TimeoutException`**. This code intentionally avoids falling back on every **`WebClientRequestException`**, because that hierarchy can also wrap TLS or security errors. To support connect timeouts or DNS outages, add a cause-verified classifier in the HTTP adapter and test each failure type explicitly. Never write **`onErrorResume(Throwable.class, ...)`**.

### 6.3. What About Saving New Verified Snapshots?

To keep the cache strictly limited to verified data, implement a separate **`storeVerified`** step after contract validation and before downstream distribution where contracts allow:

~~~text
Live response
  → validate contract + tenant/orderId + version
  → conditionally update verified snapshot by version
  → return LIVE or emit verified source event
~~~

If caching fails while the live response is valid, treat caching as **best-effort** and still return `LIVE`—while emitting a cache-error metric. Never fire-and-forget `.subscribe()` inside a `map` where write errors vanish outside request lifecycles. Guard against out-of-order responses overwriting newer snapshots by using **version/`updatedAt` conditional updates**.

### 6.4. Timeouts Do Not Prove Downstream Did Not Process

For **pure read GETs**, snapshot fallbacks can be acceptable. For **side-effecting POST/PUTs**, timeouts can happen after downstream committed. **Cancelling a WebClient subscription does not roll back a remote transaction**. Always use idempotency keys, status lookups, and confirmation workflows before retrying.

## 7. Retries, Timeouts, Circuit Breakers, and Fallbacks Need Explicit Order

A recovery pipeline typically has multiple layers:

~~~mermaid
flowchart TD
    A["Business request"] --> B["Validate + authorize"]
    B --> C["Circuit breaker / bulkhead"]
    C -->|"Permitted"| D["HTTP/DB attempt with per-step timeout"]
    C -->|"Open / rejected"| E{"Valid fallback?"}
    D -->|"Success, valid data"| F["Return LIVE"]
    D -->|"Retryable error"| G{"Retry budget left?"}
    G -->|"Yes"| H["Bounded backoff"]
    H --> D
    G -->|"No"| E
    D -->|"Invalid data / business 4xx"| I["Return real error, no fallback"]
    E -->|"Verified fresh cache"| J["Return STALE with metadata"]
    E -->|"No"| K["Return UNAVAILABLE / PENDING"]
~~~

Do not blindly exhaust all retries before falling back. When a circuit breaker is open or the overall deadline is nearly gone, failing over early lowers load—provided business signals still expose prolonged downstream outages.

### 7.1. Bounded Retries Before Fallback

~~~java
Mono<TrackingView> live = trackingWebClient.get()
        .uri("/tracking/{id}", orderId)
        .retrieve()
        .bodyToMono(TrackingDto.class)
        .map(dto -> verifiedLiveView(orderId, dto))
        .timeout(Duration.ofSeconds(1))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(this::isEligibleForFallback))
        .timeout(Duration.ofSeconds(3));
~~~

**`Retry.backoff(2, ...)`** permits at most **two retries** after the initial attempt. Inner **`timeout(1s)`** bounds each attempt; outer **`timeout(3s)`** caps total elapsed time including retries and backoff. Production code must also include the empty-body and schema/404 handling from Section 6—do not copy this snippet alone as a complete service. Test operator placement carefully, as placing **`timeout`** after **`retryWhen`** behaves differently from placing it before.

Never allow stacked unbounded retries across **WebClient**, **Resilience4j**, **Spring Integration advice**, and **broker redeliveries**. Multiplying 3 retries across layers floods already-degraded upstreams.

### 7.2. A Circuit Breaker Is Not a Data-Selection Engine

A **circuit breaker** observes failures and pauses calls to a failing downstream once thresholds trip; it does not know which cache is safe to serve or whether a payment can proceed. A **`CallNotPermittedException`** (e.g., from Resilience4j) can trigger a **defined fallback policy**, not act as proof that every state can be replaced with `true` or an empty list.

With Resilience4j, include compatible Spring Boot modules and reactive adapters when using Reactor. Never mistake **`fallbackMethod`** on annotations for transaction boundaries or data validation. Extract fallback logic into a testable business policy rather than returning one generic default for every exception.

### 7.3. Bulkheads and Rate Limits

Internal fallback stores (cache or DB) can overload too. **Bulkheads** cap concurrent downstream calls; fallback paths need their own latency, concurrency, and memory budgets. When upstream returns **429**, honor **`Retry-After`** instead of triggering retry storms that push all traffic onto a weaker fallback store.

## 8. `UNKNOWN`/`PENDING` Status Is a Valid Recovery Outcome

For side-effecting workflows, a safe fallback is not a substitute business value. When a payment provider receives a command and the client times out:

~~~text
POST /payments with idempotency key=pay-7821
      |
      +--- Provider returns clear outcome ---> persist real result
      |
      +--- Timeout / lost response ----------> UNKNOWN state
                                                  |
                                                  v
                                        GET status for pay-7821
                                                  |
                             +--------------------+-------------------+
                             |                                        |
                         Completed                                Still unclear
                             |                                        |
                             v                                        v
                   Persist verified outcome              PENDING + retry/reconcile
~~~

**Never generate a fresh `paymentId` and resubmit a charge** merely because a response timed out. Reuse the original key within the provider's idempotency window if supported, or reconcile via reference/correlation lookups and manual review when uncertain.

An API can return a domain outcome:

~~~java
public enum PaymentDecision {
    CONFIRMED,
    REJECTED,
    PENDING_RECONCILIATION
}

public record PaymentOutcome(
        String paymentRequestId,
        PaymentDecision decision,
        Instant checkedAt) {
}
~~~

**`PENDING_RECONCILIATION`** is not a successful payment. Clients and UIs must **never ship goods, finalize revenue, or issue a new charge** while waiting on reconciliation.

Such a fallback requires **durable pending records**, polling or webhook callbacks, final business expiration timeouts, alerts for stuck transactions, and procedures when the provider fails to report status.

## 9. Fallbacks in Spring Integration: `errorChannel` Is Not Success

In Spring Integration, flows consume from HTTP gateways, file adapters, Kafka, RabbitMQ, or JMS. When a handler fails, behavior depends on **`DirectChannel` vs. `ExecutorChannel`**, endpoint type, retry advice, transactions, and error channels. One blanket "catch exception and send another message" rule never fits every flow.

~~~mermaid
flowchart TD
    A["Inbound adapter receives message"] --> B["Validate, parse, authorize"]
    B --> C["Handler / HTTP / database"]
    C -->|"Succeeded"| D["Persist business outcome / ACK per contract"]
    C -->|"Transient failure"| E["Bounded retry policy"]
    E -->|"Recovered"| D
    E -->|"Exhausted"| F["Recovery decision"]
    C -->|"Poison / invalid contract"| G["Data error: never fall back to success"]
    G --> F
    F -->|"Optional enrichment"| H["Degraded result with provenance"]
    F -->|"Mandatory processing"| I["Durable retry / DLQ / outbox"]
    F -->|"No recovery path"| J["Propagate failure; preserve redelivery"]
~~~

An **`ErrorMessage` on `errorChannel`** is an in-flow error representation—**not** a message safely persisted in a broker dead-letter queue/topic. An error flow that logs an `ErrorMessage` and exits normally can cause upstream adapters to treat the failure as handled, depending on ACK and recovery-callback mechanics.

### 9.1. `RequestHandlerRetryAdvice` and Recovery Callbacks

Spring Integration offers **`RequestHandlerRetryAdvice`** for handler retries via Spring Retry, and **`ErrorMessageSendingRecoverer`** to forward exhausted failures as `ErrorMessage`s onto a channel. Conceptual flow:

~~~text
inputChannel
  → idempotency/validation
  → request handler + RequestHandlerRetryAdvice
       ├─ transient error, attempts left → retry
       ├─ success → outputChannel
       └─ exhausted → ErrorMessageSendingRecoverer
                         → recoveryChannel
                             ├─ optional lookup → STALE with metadata
                             ├─ critical command → durable failure queue
                             └─ invalid payload → quarantine/DLQ
~~~

**A recovery callback can prevent exceptions from propagating to the main listener.** If the recovery flow returns without durable persistence, the broker may ACK the source and drop critical events. Before attaching a recoverer, verify:

1. Does the container treat the callback as **handled** or rethrow?
2. Does the recovery path **durably persist** messages needing reprocessing?
3. Is publishing to dead-letter **confirmed**, or merely fire-and-forget async?
4. Do idempotency/outbox/inbox states handle crashes mid-processing?
5. If the recovery channel itself fails, where does the exception go and does the source adapter ACK?

Never equate **`nullChannel`** with a DLQ. Routing critical commands to `nullChannel` and calling it "recovered" effectively **deletes work silently**.

### 9.2. Read-Only Fallbacks vs. Command Fallbacks

For an **enrichment service** adding optional display data, serving verified cache when a read downstream fails can be safe—provided **`degraded`/`freshness`** flags tell routers the data is stale.

For a **command handler** updating stock, recording ledger entries, or confirming payments, never substitute errors with **`success=true`**. Leave outcomes unresolved, persist to a durable queue, or create a trackable **`PENDING_RECONCILIATION`** state.

### 9.3. Async Boundaries Change Error Visibility

With **`DirectChannel`**, handlers normally run on the sender's thread, so exceptions propagate directly back to the gateway/adapter. With **`ExecutorChannel`** or `QueueChannel`, failures run asynchronously and become **`ErrorMessage`** instances instead of throwing on the dispatching thread. Thread-bound transactions also do not cross async boundaries automatically.

Always map out async boundaries when designing fallbacks:

~~~text
Source thread / transaction A
   ↓ dispatch via async channel
Worker thread / transaction B
   ↓ handler fails
errorChannel / recoverer
   ↓? ACK, DLQ, retry, fallback
~~~

Never treat an HTTP gateway returning `202` as proof a message cannot be lost; durable handoffs are required if the contract promises delivery.

## 10. Message Brokers: ACKs, Retries, and DLQs Must Not Hide Failures

Under **at-least-once** delivery, unacknowledged messages are redelivered. Fallbacks must never turn a retryable error into a fake success ACK.

### 10.1. Dangerous Scenario

~~~text
Broker delivers InventoryReserved
  → consumer writes DB step A
  → call to warehouse service fails
  → catch Exception
  → return success / do not throw
  → container ACKs message
  → warehouse never updated, and redelivery stopped
~~~

If the warehouse side effect is mandatory, this is **not** a valid fallback. You need protocols such as outbox/inbox, durable workflow states, compensating sagas, or retry queues with dead-letter policies.

### 10.2. Post-Failure Decision Matrix

| Handler Outcome | Reasonable Source Action | Conditions to Verify |
| --- | --- | --- |
| Business commit succeeded | ACK/commit offset per adapter | Committed and idempotent |
| Duplicate event already processed | ACK without repeating side effects | Receipt/unique key already committed |
| Transient failure before commit | Bounded retry/requeue | Do not ACK early; enforce deadline/backoff |
| Unprocessable poison message | DLQ/quarantine per policy | Error destination exists and publish/routing confirmed |
| Failure after partial side effects | Reconcile/compensate/idempotent retry | Never assume cross-system rollback |
| Approved optional fallback | May ACK after fallback outcome is recorded | Contract explicitly accepts this as final outcome |
| Indeterminate outcome | Keep `PENDING`/reconciliation | Never emit fake success or duplicate payment |

**ACK behavior differs across Spring Kafka, Spring AMQP/RabbitMQ, JMS, and Spring Integration adapters**. Handling an `ErrorMessage` or returning from a listener does not mean every broker ACKs identically. Verify transactions, manual/auto acknowledgment modes, recoverers, and dead-letter routes in practice.

### 10.3. Dead-Lettering Also Needs Confirmation

Distinguish:

- **Dead-letter decision**: app intends to route the message to the error path.
- **Publish/route confirmed**: broker confirmed persistence/routing per mechanism.
- **Dead-letter observed**: a consumer or broker metric observes the message in the target queue/topic.

If publishing to the dead-letter destination fails while the source ACKs, messages vanish. Therefore, "fallback to DLQ" is valid only with a **durable handoff** and fallback path if the DLQ itself is unavailable.

## 11. Transactions, Rollbacks, and Fallbacks: Avoid Committing Partial State

Transactions roll back only when the framework sees a rollback-triggering failure or rollback is explicitly requested. Swallowing exceptions inside **`@Transactional`** lets Spring treat the method as successful and commit prior writes.

Anti-pattern:

~~~java
// ANTI-PATTERN: never use this for mandatory business operations.
@Transactional
public void processOrder(OrderCommand command) {
    orderRepository.markProcessing(command.orderId());

    try {
        paymentGateway.capture(command.paymentRequestId());
    } catch (Exception ex) {
        // Logging and returning commits PROCESSING even though
        // the real payment outcome is completely unknown.
        log.warn("Payment unavailable");
        return;
    }

    orderRepository.markPaid(command.orderId());
}
~~~

Illustrative snippet only; interfaces are application-defined. Two flaws:

1. **External payment APIs are not part of the DB transaction**, even inside `@Transactional`.
2. **Returning after `catch`** commits a dangling **`PROCESSING`** state while callers/brokers may assume completion.

Instead, design a durable state machine:

~~~text
NEW
  → PAYMENT_REQUESTED (with idempotency key)
      → CONFIRMED (with provider evidence)
      → REJECTED (with explicit rejection outcome)
      → PENDING_RECONCILIATION (outcome unclear)
             → status inquiry / webhook / manual review
~~~

Within the DB transaction, persist **known state** and an **outbox event**; outside the transaction, call the provider and persist outcomes in a new transaction guarded by optimistic versions/checkpoints. Never transition to **`CONFIRMED`** inside an exception handler.

### 11.1. Write-Side Fallbacks Are New Business Operations

If a fallback writes caches, queues, audits, or `PENDING` records, those writes can fail too. They require:

- Durable state or proper transactions.
- Stable idempotency keys / correlation IDs across retries.
- Compensation and reconciliation for partial commits.
- Distinct metrics for **fallback attempted**, **fallback succeeded**, and **fallback failed**.
- Clear ACK rules when persisting the fallback itself fails.

**Never treat an in-memory write as durable recovery** across process restarts.

## 12. Ensure Fallbacks Do Not Violate Data Contracts

### 12.1. Never Hide Errors Behind Fake "Valid" Values

Code patterns that breed silent business bugs:

~~~java
// Wrong: unreachable upstream becomes "product does not exist".
return productClient.findById(id)
        .onErrorReturn(Optional.empty());

// Wrong: inventory API failure becomes "in stock".
return inventoryClient.available(sku)
        .onErrorReturn(true);

// Wrong: masks JSON/schema/auth failures and drops alerts.
return partnerClient.fetch(request)
        .onErrorResume(ex -> Mono.just(defaultBusinessRecord()));
~~~

These functions represent application APIs. The flaw is not Reactor syntax—it is **turning an infrastructure failure into a valid-looking business result**.

**Zero**, **`false`**, **empty lists**, and **`null`** carry distinct domain meanings per API. **`price=0`** can give away free goods; **`available=0`** halts sales; **`permissions=[]`** can be a valid fail-closed authorization choice only if clearly interpreted as "access denied" without leaking internal state.

### 12.2. Distinguish Malformed Payloads from Missing Data

| State | Example | More Accurate Outcome |
| --- | --- | --- |
| **ABSENT** | Data store confirms order does not exist | `NotFound` / domain absence |
| **EMPTY** | API succeeds with genuinely empty event list | Valid empty result |
| **UNAVAILABLE** | API unreachable | Error/unavailable, or contracted fallback |
| **STALE** | Previously verified data served within allowed staleness | Snapshot with freshness and `asOf` |
| **INVALID** | Schema violation, hash/signature mismatch | Contract/security error; never collapse to `EMPTY` |
| **UNKNOWN** | Side effect sent, response lost | `PENDING` / reconciliation |

In particular, **returning `Optional.empty` on JSON deserialization failures** hides data contract breaks—silently dropping orders, updates, or events needing fixes.

### 12.3. Versioning and Aged Snapshots

A snapshot verified 2 minutes ago might have **`sourceUpdatedAt`** from 4 days ago. Depending on the domain, that is either normal (unchanged shipment) or too stale. Specify both:

- **Maximum cache age**: time since cache verification/update.
- **Maximum acceptable source age** or **event version** rules: whether long-unupdated source records remain usable.
- **Finality rules**: e.g., a verified `DELIVERED` state may follow different retention rules than `IN_TRANSIT`.
- **Update ordering**: an out-of-order stale response must never overwrite a newer cached version.

Implement the policy as a pure function taking **snapshot + request context + current time + contract version** and returning a reasoned decision—never scatter checks across dozens of `catch` blocks.

## 13. Fallback Observability Is Mandatory

Fallbacks keep users from seeing 5xx errors yet can mask hours-long downstream outages. Therefore, measure **primary-path failures** even when APIs return fallback responses.

| Suggested Metric | Measurement Point | Meaning |
| --- | --- | --- |
| **`app.integration.primary.outcomes`** | After each primary attempt | `success`/`failure` and `error_kind` |
| **`app.integration.retry.started`** | When a retry attempt starts | Real re-executions, not scheduled timers |
| **`app.integration.fallback.attempts`** | Entry to fallback policy | How often primary handed off to fallback |
| **`app.integration.fallback.outcomes`** | When fallback finishes | `success` / `rejected` / `failure` |
| **`app.integration.fallback.age`** | When serving stale snapshots | Age of verified fallback data |
| **`app.integration.fallback.rejections`** | Policy rejects cache entry | `expired` / `invalid` / `wrong_scope` / `absent` |
| **`app.integration.pending.reconciliation`** | Commands awaiting verification | Keeps `UNKNOWN` items from being forgotten |
| **`app.integration.deadletter.confirmed`** | After confirmed DLQ publish | DLQ recovery effectiveness |
| **`app.integration.primary.duration`** | Primary path timer | Latency, p95/p99, and timeouts |

These are **suggested application metric conventions**, not built-in meters emitted automatically by Spring Boot, Spring Integration, or Resilience4j.

### 13.1. Low-Cardinality Tags

Keep tags within bounded value sets:

~~~text
flow=order-tracking | inventory-check | payment-status
dependency=tracking-service | inventory-service | payment-provider
error_kind=timeout | unavailable | invalid_contract | auth_failure
fallback_type=verified_cache | hide_optional_widget | pending
outcome=success | rejected | failed
~~~

Never put **`orderId`, `customerId`, `paymentId`, raw `tenantId`, tokens, or dynamic query URLs** into metric tags; they explode time-series cardinality. Keep those IDs inside access-controlled logs/traces per data governance policy.

### 13.2. Logging and Tracing

Non-sensitive structured log:

~~~text
flow=order-tracking
dependency=tracking-service
primaryOutcome=timeout
fallbackType=verified_cache
fallbackOutcome=success
freshness=STALE
verifiedAgeSeconds=120
traceId=...
~~~

Never log tokens/API secrets, `Authorization` headers, full personal-data response bodies, or cache keys exposing sensitive raw customer IDs.

Trace:

~~~text
HTTP inbound
  → authenticate + validate request
  → tracking WebClient GET
       → timeout
  → verified-cache lookup
       → valid snapshot age=120s
  → return STALE result
~~~

Traces must expose both **why the primary path failed** and **the recovery step**; an HTTP 200 alone does not prove upstream is healthy.

### 13.3. Rate- and Duration-Based Alerts

Alert when:

- **`fallback/requests`** ratio climbs persistently or exceeds SLO budgets.
- **Invalid cache entry rate** spikes, signaling schema drift or cache corruption.
- **Cache age** approaches max staleness, showing snapshots stopped refreshing.
- **Pending reconciliations** pile up or oldest pending breaches SLA.
- **Fallback failures** rise alongside primary failures (backup path failing too).
- DLQ volume grows or fallbacks mask drops in real business completions.

Never alert merely on a cumulative counter being `> 0`; use windowed rates and account for counter resets on restarts.

## 14. Testing Fallbacks Against Contracts, Not Just HTTP Codes

Testing that a method **"returned an object"** is insufficient. Verify the fallback object is genuinely permitted when the source fails and preserves data integrity.

### 14.1. Required Test Matrix

| Case | Primary | Snapshot / Recovery | What to Assert |
| --- | --- | --- | --- |
| Normal success | HTTP 200 valid JSON | Present or absent | Returns `LIVE`; does not read fallback needlessly |
| Temporary HTTP 503 | 503 | Same tenant, verified and fresh | Returns `STALE` with `sourceUpdatedAt`/`servedAt` |
| HTTP 504 with cache miss | 504 | None | Preserves upstream error; fabricates no data |
| Classified transport timeout | Timeout | Valid cache | Falls back only if classifier permits |
| HTTP 404 | Not found | Stale cache exists | Cache does not "resurrect" a deleted ID unless contract allows |
| HTTP 401/403 | Auth failure | Cache present | Never bypasses authorization using cache |
| HTTP 200 with invalid JSON schema | Invalid | Cache present | Returns contract error; never hides data defect |
| Cross-tenant cache entry | 503 | Wrong tenant | Rejects cache; zero data leak |
| Expired cache | 503 | `verifiedAge > maxStale` | Refuses to serve |
| Invalid cached state | 503 | Poisoned data | Rejects and increments rejection metric |
| Older event overwrites cache | 503 | Regressed cache version | Conditional write blocks regression |
| Circuit breaker open | Upstream skipped | Valid cache | Applies fallback policy without silencing upstream alerts |
| Cache lookup failure | 503 | Cache timeout | Bounded deadline and clear outcome; never hangs |
| Payment POST timeout | Uncertain outcome | No receipt | `PENDING`/reconcile; never auto-retries with a new ID |
| Mandatory broker handler fails | Throws | Unpersisted recovery | Does not false-ACK; redelivery preserved |

### 14.2. Testing Reactor's `timeout` Operator

Standalone test verifying `TimeoutException` when a `Mono` emits nothing:

~~~java
@Test
void monoTimeoutIsNotEquivalentToEmptyResult() {
    StepVerifier.withVirtualTime(
            () -> Mono.<TrackingView>never()
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

This verifies **Reactor timeout semantics**, not business fallback rules. In policy unit tests, inject **`Clock.fixed(...)`** and explicit snapshots to test exact age cutoffs—avoid **`Thread.sleep`** and wall-clock coupling.

### 14.3. Using Mock HTTP Servers to Verify the Real Service

With **MockWebServer/WireMock** or an equivalent HTTP test server:

1. Return 200 with valid schema → assert **`Freshness.LIVE`**.
2. Return 503 with 2-minute-old verified cache → assert **`Freshness.STALE`** with original timestamps preserved.
3. Return 503 with 6-minute-old cache → assert error/`UNAVAILABLE` rather than `STALE`.
4. Return 200 missing **`sourceUpdatedAt`** → assert contract violation, **no fallback**.
5. Return 404/403 → assert cache is never used to bypass policy.
6. Delay response bodies to verify real WebClient/transport timeouts and fallback budgets.
7. Fire concurrent requests for the same order → assert stale responses never overwrite newer cache snapshots.

**Never mock a `TimeoutException` alone and assume WebClient connect/read timeouts are configured properly.** Testing transport behavior requires the real connector and an HTTP server controlling delays and disconnects.

### 14.4. Testing Transactions, Redelivery, and Idempotency

Using database/broker integration tests (e.g., Testcontainers):

~~~text
Broker delivers event #1
  → DB writes partial marker
  → downstream times out
  → app rolls back or persists durable PENDING
  → broker redelivery / reconciler runs
  → identical eventId produces no duplicate side effects
~~~

Assert real **business state** and **ACK/DLQ** outcomes, not just handler invocation counts. A solid fallback survives **mid-workflow crashes**, not only clean exceptions in healthy processes.

## 15. Operational Procedure When Fallbacks Surge

Start from a diagnostic decision tree:

~~~mermaid
flowchart TD
    A["Fallback rate spikes"] --> B{"Is the primary path failing?"}
    B -->|"503/timeout"| C["Check latency, pools, DNS, broker, rate limits"]
    B -->|"No"| D["Check classifier, schema, and fallback rules"]
    C --> E{"Are snapshots still safe?"}
    E -->|"Yes"| F["Serve labeled degraded responses + watch age"]
    E -->|"No"| G["Reject fallback; return UNAVAILABLE"]
    F --> H["Recover upstream, refresh cache, reconcile"]
    G --> H
    D --> I["Fix data contract / classifier; do not swallow errors"]
~~~

Operational steps:

1. Identify the **root failure source** by downstream, `error_kind`, and recent deployments.
2. Check **accepted** vs. **rejected** fallback rates, data age, and pending reconciliations.
3. If cached data becomes unsafe, **disable that fallback via controlled policy**—return unavailable/`PENDING` rather than stretching TTLs endlessly.
4. Restore upstream using bounded retries, rate limiting, and pool protection; prevent retry storms.
5. Refresh verified data and replay/reconcile pending work using idempotency keys.
6. Inspect **primary failures, business completions, broker ACKs, and DLQs** rather than HTTP 200 rate alone.
7. Post-incident, refine classification rules, data contracts, and tests for newly discovered edge cases.

### Externalized Fallback Policy Configuration

~~~yaml
app:
  recovery:
    tracking:
      primary-timeout: 2s
      max-verified-cache-age: 5m
      max-source-age: 24h
      cache-lookup-timeout: 300ms
      allow-stale-informational-view: true
~~~

These are **suggested application properties**, not Spring Boot built-ins. Bind via **`@ConfigurationProperties`**, validate positive `Duration`s, and toggle only per approved policy. Always enforce a **separate timeout for cache lookup**: Section 6's service should add a configured timeout on the fallback path too, because **`timeout` placed before `onErrorResume` bounds only the primary call**, not the fallback lookup.

**Never use feature flags to disable validation or bypass authorization.** A flag can turn off stale lookups and return unavailable, never grant broader access during infrastructure failures.

## 16. Common Pitfalls

**"Fallback succeeded means downstream is healthy."** False. Fallbacks can mask multi-hour outages. Measure primary failures and fallbacks separately.

**"Returning an empty list on HTTP errors is always safe."** True only if the contract treats empty optional data as a valid substitute—never for orders, payments, stock, or permissions.

**"404/401/invalid JSON are all the same as timeouts."** False. They represent non-existence, denied access, or corrupt data; falling back hides serious defects.

**"If it's still in cache, it's fresh enough."** False. Storage TTL differs from max staleness and `sourceUpdatedAt`.

**"Another tenant's data can temporarily fill in."** Never. Fallbacks must never cross security boundaries.

**"HTTP 200 + fallback needs no metadata."** If callers cannot tell data is stale, they can make wrong decisions. Contracts must expose freshness/provenance.

**"When the circuit breaker opens, return success by default."** Circuit breakers only gate calls; business policy governs valid fallbacks.

**"`onErrorResume(Exception.class)` is the cleanest error handler."** It swallows contract violations, auth failures, and internal bugs.

**"A POST timeout proves no money was charged."** False. Outcomes may be unknown; idempotency and reconciliation are mandatory.

**"Having a `recoveryChannel` means errors are durably saved."** False. In-memory channels and `ErrorMessage` are neither durable queues nor DLQs.

**"Catching exceptions in `@Transactional` and returning rolls back."** Not necessarily. Spring may commit whatever writes ran beforehand.

**"Retrying across multiple layers makes things safer."** Attempts multiply exponentially, crushing downstreams; enforce a shared budget.

**"Testing HTTP status codes and exceptions is enough."** Also test staleness, tenant isolation, versioning, TTLs, side effects, ACKs, crashes, metrics, and recovery.

## 17. Pre-Release Checklist

1. Clearly separate **transient infrastructure**, **business outcomes**, **invalid contracts**, **security failures**, and **uncertain side effects**.
2. Decide which features may **fail-open** and which must **fail-closed/`PENDING`**, signed off by business owners.
3. Enable fallbacks only when a substitute exists with **valid schema, matching tenant, valid version, and acceptable freshness**.
4. Expose **`LIVE`/`STALE`/`UNAVAILABLE`/`UNKNOWN`**, data timestamps, and actionable guidance in API contracts.
5. Never turn missing data, 404, 401/403, or invalid payloads into fake business results.
6. Bound retries, circuit breakers, bulkheads, and timeouts under one shared budget without stacked infinite retries.
7. For side effects, enforce idempotency keys, transactions/outbox/inbox, and reconciliation when outcomes are unclear.
8. Never ACK critical messages when fallback merely logs or writes to an in-memory channel without durable persistence.
9. Test secondary fallback failures: cache unavailable, expired, wrong tenant, poisoned entries, and version races.
10. Enforce a dedicated timeout on the fallback path and measure total request latency.
11. Track **primary failures, accepted/rejected fallbacks, freshness age, pending counts, and DLQs** without high-cardinality personal ID labels.
12. Test happy paths, corrupt data, broker redeliveries, transaction rollbacks, open circuits, and mid-workflow crashes.
13. Maintain a runbook to disable unsafe fallbacks, restore sources, refresh snapshots, and reconcile pending work.

**Conclusion:** A good fallback is not "never throwing exceptions," but **preserving business meaning when the primary path fails**. Fallbacks should run only when substitute data is trustworthy, contracts transparently disclose degradation, and real defects stay visible. For flows with side effects or strong consistency needs, **failing safely, holding `PENDING`, and reconciling** beats a fake default disguised as success.

## References

- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): status classification, `bodyToMono`, and HTTP error handling.
- [Spring Framework — WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): custom response/error handling and body release.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `onErrorReturn`, retries, and timeouts.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and asynchronous error flows.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `RequestHandlerRetryAdvice`, recoverers, and retries.
- [Spring Cloud Circuit Breaker — Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/): circuit breakers, Resilience4j, and Spring integration.
- [Resilience4j — Getting Started](https://resilience4j.readme.io/docs/getting-started-3): circuit breakers, retries, bulkheads, and decorators.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, tags, and observing latency/outcomes.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retries, recoverers, DLTs, and failing listeners.
- [Spring AMQP — Message Recovery](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retries, recoverers, DLQs, and broker mechanics.
