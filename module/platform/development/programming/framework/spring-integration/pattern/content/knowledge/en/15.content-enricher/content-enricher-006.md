# Preserving the Original Payload and Enriched Data

## 1. Why Must Both Original Data and Enriched Data Be Preserved?

In an order integration flow, the initial message contains only the order ID, customer ID, and amount. Before deciding the processing branch, the system needs to query customer profile information such as loyalty tier or verification status. **Content Enricher** is the Enterprise Integration Pattern (EIP) that adds information to a message using existing data or data fetched from another source.

Example:

~~~text
Original payload from Checkout:
  orderId    = ORD-1001
  customerId = C-007
  amountVnd  = 9000000

Data returned from Customer Profile Service:
  customerId = C-007
  tier       = GOLD
  verified   = true

Payload after enrichment:
  original:
    orderId    = ORD-1001
    customerId = C-007
    amountVnd  = 9000000
  profile:
    customerId = C-007
    tier       = GOLD
    verified   = true
  enrichment:
    source     = customer-profile
    retrievedAt= ...
~~~

The requirement to **preserve the original payload** means the initial data remains accessible after the enrichment step rather than being overwritten by the lookup system's reply. At the same time, **enriched data** must be retained as a distinct component, tracking where it came from, when it was fetched, and whether it still matches the original message.

~~~mermaid
flowchart LR
    A[Original OrderRequest] --> E[Content Enricher]
    E --> L[Profile lookup]
    L --> E
    E --> O["EnrichedOrder"]
    O --> OG["original: OrderRequest"]
    O --> PG["profile: CustomerProfile"]
    O --> MG["metadata: source / retrievedAt"]
    O --> R[Router / Filter / Handler]
~~~

If only the lookup result is kept, subsequent steps lose the **amount, order ID, and original request**. If the original payload is mutated directly to add fields, audits and retries may be unable to distinguish **what the client actually sent** from **what the system added**. An explicit structure solves both problems.

This article belongs to the **Content enricher** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module covers practicing Enterprise Integration Patterns in Spring Integration to build loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing every branch.

### Learning Objectives

After this article, you will be able to:

1. Distinguish **original payload**, **enriched payload**, **metadata/provenance**, and **message headers**.
2. Compare enriching by **mutating an object**, **creating a new object**, or **wrapping both original and enriched data in an envelope**.
3. Write a Java DSL integration flow that performs enrichment without losing the original input.
4. Understand how to use a synchronous lookup source, request/reply mapping, and the limits of Content Enricher.
5. Design for missing lookup data, mismatched IDs, timeouts, stale data, or errors.
6. Test invariants, enrichment data, correlation, idempotency, and traceability.

## 2. What Does Content Enricher Actually Do?

### 2.1. Basic Process

~~~text
Message<OrderRequest>
    |
    v
Extract lookup key from OrderRequest.customerId
    |
    v
Call Customer Profile (local repository / outbound gateway)
    |
    v
Verify response matches customerId and is valid
    |
    v
Build EnrichedOrder(original, profile, lookupMetadata)
    |
    v
Message<EnrichedOrder> -> downstream
~~~

Content Enricher typically involves **building an enrichment request**, **awaiting/receiving a reply**, and **combining** the received data with the original payload. Spring Integration provides a built-in **Content Enricher**, and the same pattern can also be implemented using endpoints/Gateways/Transformers with clear responsibilities.

**Key point:** Content Enricher is not a Router. It changes the **content available to the next step**, rather than deciding which channel the message goes to. If you need to route by `profile.tier` after enrichment, place a **Router after the enrichment step**.

### 2.2. What Must Be Preserved

| Component | Example | Role |
|---|---|---|
| **Original payload** | `OrderRequest(orderId, customerId, amountVnd)` | Proof of initial data used for business logic. |
| **Enrichment result** | `CustomerProfile(tier, verified)` | Supplementary information for decisions and processing. |
| **Lookup metadata** | `source`, `retrievedAt`, `lookupRequestId` | Provenance, timestamp, and traceability. |
| **Message headers** | `traceId`, `correlationId`, `replyChannel` | Message flow context, not an automatic copy of the payload. |
| **Business decision** | `requiresManualReview` | Conclusion derived by a policy from both original and profile; keep separate from raw data. |

Preserving the original payload **does not mean retaining all personal data forever**. Data minimization, retention, masking, and access control still apply. For sensitive data, keep only the fields required for approved business or audit purposes.

### 2.3. Why Not Replace the Original Payload with the Lookup Response?

Suppose Customer Profile Service returns:

~~~json
{
  "customerId": "C-007",
  "tier": "GOLD",
  "verified": true
}
~~~

If a Transformer or handler writes `return customerProfile` without carrying order details, the next endpoint receives only `CustomerProfile`; `orderId` and `amountVnd` vanish from the payload. Some headers might still exist, yet headers must not serve as an implicit dumping ground for lost business data.

Instead, build an envelope:

~~~text
EnrichedOrder
  original: OrderRequest
  profile: CustomerProfile
  metadata: LookupMetadata
~~~

Each field has one responsibility. A Router can read `profile.tier`, the payment handler can read `original.amountVnd`, and tracing/audit can use `metadata.source` and `retrievedAt`.

## 3. Three Ways to Combine Data and Their Trade-offs

### 3.1. Mutating the Original Object in Place

~~~java
// Example illustrating the hazard, not a recommended pattern.
class MutableOrder {
    String orderId;
    String customerId;
    String tier;
}

void enrichInPlace(MutableOrder order, String tier) {
    order.tier = tier;
}
~~~

The upside is minimal object allocation. However, when multiple subscribers hold references to `order`, updating `tier` can alter data another branch is reading. Over `ExecutorChannel` or Publish–Subscribe, shared mutable state causes race conditions, hard-to-reproduce tests, and muddy audits.

If you must use a mutable bean due to a library or adapter, define ownership and clone/copy semantics clearly; never assume Content Enricher automatically performs a **deep copy** of the entire object graph.

### 3.2. Creating a New Flat DTO

~~~java
record FlatEnrichedOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amountVnd,
        String tier,
        boolean verified) {}
~~~

This fits when consumers want a small projection with a simple schema. Yet it carries risks:

- Does not separate caller-supplied fields from looked-up fields.
- When the same field name exists in both sources, precedence rules easily become unclear.
- When adding data or evolving lookup schemas, a flat DTO struggles to express provenance.
- If you need byte-for-byte inspection of the original payload, the new object may not preserve original serialization evidence.

### 3.3. Wrapping Original and Enrichment Separately

~~~java
record EnrichedOrder(
        OrderRequest original,
        CustomerProfile profile,
        LookupMetadata metadata) {}
~~~

**This is the primary approach of this lesson**: original remains untouched, enriched data has its own namespace, and metadata suffices for provenance. Computed projections can be added later without mutating inbound data.

| Criterion | Mutate In-Place | New Flat DTO | Wrapper Keeping Original |
|---|---|---|---|
| Leaves input object untouched | No | Yes | Yes |
| Preserves source separation | Difficult | Needs naming conventions | Explicit |
| Traceability to original data | Low | Medium | High |
| Safe for concurrent processing | Risky | Good if immutable | Good if components immutable |
| Compact payload | Usually | Yes | May be larger |
| Simple downstream schema | Medium | Easy for small use cases | Consumers must understand wrapper |

Not every flow requires a wrapper. If you only need to compute a minor field and have no requirement to preserve the original intact, a simple Transformer may suffice. Yet when **preserving both the original payload and enriched data** is a strict contract, a wrapper makes intent and tests clearest.

## 4. Designing Immutable Data and Provenance

### 4.1. Domain Model

A Java 17 model can be written with `record`. All fields below use `String`, `BigDecimal`, `boolean`, `Instant`, or other records to illustrate value immutability:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderRequest(
        String orderId,
        String customerId,
        BigDecimal amountVnd) {}

record CustomerProfile(
        String customerId,
        String tier,
        boolean verified) {}

record LookupMetadata(
        String source,
        String lookupRequestId,
        Instant retrievedAt) {}

record EnrichedOrder(
        OrderRequest original,
        CustomerProfile profile,
        LookupMetadata metadata) {}
~~~

**Understand `record` accurately:** it fixes component references, yet **does not make nested objects immutable**. If a payload contains a `List`, `Map`, array, or mutable POJO, the constructor must perform a **defensive copy** or use a verified immutable type.

Collection example:

~~~java
import java.util.List;

record OrderWithItems(String orderId, List<String> itemIds) {
    OrderWithItems {
        itemIds = List.copyOf(itemIds);
    }
}
~~~

`List.copyOf` is a **shallow copy**: if elements are mutable objects, deeper handling is still required. Do not confuse an immutable wrapper with cloning an entire payload as a physical snapshot.

### 4.2. Key Business Invariants

A valid `EnrichedOrder` in this example must satisfy:

1. `original.orderId` and `original.customerId` are non-blank.
2. `original.amountVnd` is positive, normalized to VND.
3. `profile.customerId` **matches** `original.customerId`.
4. `profile.tier` belongs to the allowed set, e.g., `STANDARD`, `SILVER`, `GOLD`.
5. `metadata.source` identifies the actual lookup source.
6. `metadata.retrievedAt` is recorded by the enrichment component when fetching/producing the result.
7. The original object is not mutated during enrichment.
8. Unverified data is never placed into fields that a Router could mistake as verified.

**Returning another customer's profile must be treated as an error**, never merged with the order merely because both payloads contain values.

### 4.3. Knowing Which Source Each Piece Came From

| Field | Source | Always Trusted? |
|---|---|---|
| `original.amountVnd` | Checkout / upstream producer | Must be validated/authorized per contract. |
| `profile.tier` | Customer Profile Service | Depends on lookup timing and source trust. |
| `metadata.retrievedAt` | Enricher | Proves only when the app observed the result; does not prove latest data. |
| `metadata.lookupRequestId` | Enricher or lookup client | For correlation, does not replace business IDs. |
| `headers.traceId` | Observability context | Must propagate properly across executors/adapters. |

If the lookup service also returns a profile `updatedAt`, store both **`sourceUpdatedAt`** and **`retrievedAt`** to distinguish when the profile changed from when your system queried it. Never call `Instant.now()` and claim it represents when the profile was updated.

## 5. A Testable Content Enricher in Java

### 5.1. Separating Lookup from Payload Combination Logic

Content Enricher should not mix HTTP client calls, validation, mapping, and routing into one long function. First define a **lookup source contract**; tests can use an in-memory implementation while production plugs in a client with timeouts, security, and tracing.

~~~java
import java.util.Map;
import java.util.Optional;

interface CustomerProfileDirectory {
    Optional<CustomerProfile> findByCustomerId(String customerId);
}

final class InMemoryCustomerProfileDirectory
        implements CustomerProfileDirectory {

    private final Map<String, CustomerProfile> profiles = Map.of(
            "C-007", new CustomerProfile("C-007", "GOLD", true),
            "C-008", new CustomerProfile("C-008", "STANDARD", false));

    @Override
    public Optional<CustomerProfile> findByCustomerId(String customerId) {
        return Optional.ofNullable(profiles.get(customerId));
    }
}
~~~

`Optional.empty()` in this example represents only **profile not found**. It is completely different from an HTTP timeout or unreachable profile service; those two situations require separate error classifications.

### 5.2. Enrichment Service: Without Modifying `OrderRequest`

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Set;

final class ProfileNotFoundException extends RuntimeException {
    ProfileNotFoundException(String customerId) {
        super("PROFILE_NOT_FOUND: " + customerId);
    }
}

final class ProfileMismatchException extends RuntimeException {
    ProfileMismatchException() {
        super("PROFILE_CUSTOMER_ID_MISMATCH");
    }
}

final class OrderContentEnrichmentService {
    private static final Set<String> ALLOWED_TIERS =
            Set.of("STANDARD", "SILVER", "GOLD");

    private final CustomerProfileDirectory directory;
    private final Clock clock;

    OrderContentEnrichmentService(
            CustomerProfileDirectory directory, Clock clock) {
        this.directory = directory;
        this.clock = clock;
    }

    EnrichedOrder enrich(OrderRequest original) {
        validateOriginal(original);

        CustomerProfile profile = directory
                .findByCustomerId(original.customerId())
                .orElseThrow(() ->
                        new ProfileNotFoundException(
                                original.customerId()));

        if (!original.customerId().equals(profile.customerId())) {
            throw new ProfileMismatchException();
        }
        if (!ALLOWED_TIERS.contains(profile.tier())) {
            throw new IllegalArgumentException(
                    "INVALID_ENRICHED_CUSTOMER_TIER");
        }

        LookupMetadata metadata = new LookupMetadata(
                "customer-profile-directory",
                "lookup-" + original.orderId(),
                Instant.now(clock));

        // Original and new data reside in two separate fields.
        return new EnrichedOrder(original, profile, metadata);
    }

    private static void validateOriginal(OrderRequest order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()
                || order.customerId() == null
                || order.customerId().isBlank()
                || order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "MALFORMED_ORIGINAL_ORDER");
        }
    }
}
~~~

**Reading the code in order:**

1. Validate original before calling the enrichment source. Malformed requests should never trigger a wasted network request.
2. Use the order's `customerId` as the lookup key and retrieve `CustomerProfile`.
3. Verify the returned profile belongs to that exact customer rather than mixing data from another record.
4. Reject `tier` values outside the allowed set to avoid passing arbitrary values to a downstream Router.
5. Generate `LookupMetadata` to know which source provided the data and when.
6. Return a **new object** containing `original` and `profile`; no `setAmount` or `setTier` mutates the original object.

`lookupRequestId = "lookup-" + orderId` is only an **illustrative ID for readable tests**. In a system with multiple concurrent lookups for the same order, use a genuinely unique correlation/attempt ID; likewise, an idempotency key may carry different semantics. Do not use this illustrative string as a universal unique key in production.

**Limitations of the example:** lookup runs in memory without simulating timeouts or caching; `Instant.now(clock)` marks when the application built the enriched result. Production must track provenance, source version, and effective timestamps of the underlying data.

### 5.3. Direct Java Invocation Example

~~~java
import java.math.BigDecimal;
import java.time.Clock;

OrderContentEnrichmentService enricher =
        new OrderContentEnrichmentService(
                new InMemoryCustomerProfileDirectory(),
                Clock.systemUTC());

OrderRequest request = new OrderRequest(
        "ORD-1001", "C-007", new BigDecimal("9000000"));

EnrichedOrder enriched = enricher.enrich(request);

// Original payload remains accessible:
// enriched.original().orderId() == "ORD-1001"
// enriched.original().amountVnd() == 9000000

// Lookup result is kept separate:
// enriched.profile().tier() == "GOLD"
// enriched.profile().verified() == true
~~~

The `EnrichedOrder` return type keeps callers from **confusing** the original request with the profile system response. There is no need to stuff `orderId`/`amount` into ad-hoc message headers just to "keep" business data.

## 6. Integrating with Spring Integration Java DSL

### 6.1. Role of Content Enricher in the Flow

This example uses **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** with the `spring-boot-starter-integration` dependency. Spring Integration includes a dedicated Content Enricher component; here we implement the **same pattern using an enrichment service and a Transformer endpoint** to express the immutable wrapper cleanly. This approach avoids assuming mutable JavaBeans or in-place property mutation.

~~~mermaid
flowchart LR
    G[MessagingGateway] --> I[(orders.enrich.input)]
    I --> T["Transformer: OrderContentEnrichmentService"]
    T --> R["Message<EnrichedOrder>"]
    R --> RP[Gateway reply]
~~~

### 6.2. Configuration with a Gateway Returning `EnrichedOrder`

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@MessagingGateway
interface OrderEnrichmentGateway {
    @Gateway(requestChannel = "orders.enrich.input")
    EnrichedOrder enrich(OrderRequest request);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderEnrichmentFlowConfiguration {

    @Bean(name = "orders.enrich.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean
    Clock enrichmentClock() {
        return Clock.systemUTC();
    }

    @Bean
    CustomerProfileDirectory profileDirectory() {
        return new InMemoryCustomerProfileDirectory();
    }

    @Bean
    OrderContentEnrichmentService orderContentEnrichmentService(
            CustomerProfileDirectory directory,
            Clock enrichmentClock) {
        return new OrderContentEnrichmentService(
                directory, enrichmentClock);
    }

    @Bean
    IntegrationFlow enrichOrderFlow(
            OrderContentEnrichmentService service) {
        return IntegrationFlow.from("orders.enrich.input")
                .transform(OrderRequest.class, service::enrich)
                .get();
    }
}
~~~

**Why is it still called Content Enricher when the code uses `transform`?** An EIP describes **the semantic operation**, not a requirement that every implementation use the same class name. `OrderContentEnrichmentService` enriches data from `CustomerProfileDirectory` while keeping `original` in a wrapper; `.transform(...)` is the endpoint creating the new payload. When framework-managed property/header enrichment is desired, you can use the dedicated Content Enricher/`.enrich(...)`; just do not claim both mechanisms share identical mutation, request/reply, or header-propagation behavior in every setup.

In this example:

- `DirectChannel` makes the flow synchronous.
- `@MessagingGateway` wraps the parameter into a message and awaits an `EnrichedOrder` reply.
- Transformer performs enrichment and returns the new payload, which follows the Gateway's reply path when no fixed downstream channel is declared.
- Each lookup reads from the in-memory directory. There is no real database or HTTP call in the demo.
- In a real application, extract `public` types into separate Java files; records/classes are grouped here for readability.

### 6.3. Calling the Gateway and Comparing Before/After

~~~java
OrderRequest input = new OrderRequest(
        "ORD-1001", "C-007", new java.math.BigDecimal("9000000"));

EnrichedOrder result = orderEnrichmentGateway.enrich(input);

assert result.original().equals(input);
assert "C-007".equals(result.profile().customerId());
assert "GOLD".equals(result.profile().tier());
assert "customer-profile-directory".equals(
        result.metadata().source());
~~~

The snippet uses Java `assert` for illustration; in unit/integration tests, use JUnit 5 `assertEquals`, `assertSame`, and `assertNotNull` instead of relying on JVM flag `-ea`.

### 6.4. When a Downstream Channel Is Needed After Enrichment

If the Gateway does not need to return the enriched payload immediately, the message can proceed to a Filter or Router:

~~~text
orders.enrich.input
  -> Content Enricher / Transformer
  -> orders.enriched
  -> Router(profile.tier / profile.verified)
  -> Handler / external gateway
~~~

In a flow passing messages across multiple endpoints, track the **final completion state**. Creating `EnrichedOrder` does not mean the payment or order-persistence endpoint behind the Router succeeded.

## 7. Dedicated Content Enricher vs. Transformer

### 7.1. When to Use `ContentEnricher`?

Spring Integration provides a **Content Enricher** component to enrich messages using data returned from a request channel or expression—for example, calling a lookup service and updating configured properties/headers. When choosing this mechanism, check carefully:

- **Request channel:** where is the lookup request sent?
- **Request payload:** send the whole order or only `customerId`?
- **Reply payload:** is the response a `CustomerProfile`, a wrapper, or another type?
- **Property/header mapping:** which fields receive the returned data?
- **Original payload handling:** does the framework/bean mutate, copy, or transform?
- **Timeout/error flow:** if lookup emits no reply, how long to wait and how to handle it?

A conceptual configuration sketch:

~~~text
ContentEnricher
  requestChannel     = customer.profile.lookup
  requestPayload     = original.customerId
  lookup reply       = CustomerProfile
  target             = enriched.profile
  original           = kept in enriched.original
  on missing/timeout = error or controlled fallback
~~~

This is a **behavioral specification**, not DSL syntax to copy verbatim into Java. When using `.enrich(...)`, follow your Spring Integration version's API and test property mapping explicitly against mutable POJOs or records. **Never assume** a Content Enricher automatically deep-clones the original or wraps it in your application schema.

### 7.2. When Is a Wrapper-Building Transformer More Advantageous?

When the strict requirement is **original payload intact, enriched data in a separate namespace**, a Transformer returning `new EnrichedOrder(original, profile, metadata)` offers several benefits:

1. The output contract is expressed clearly in the Java type system.
2. No setters are needed on `original`.
3. `assertSame(original, result.original())` can be tested when `original` is immutable.
4. Profile mismatches are easy to catch before creating the enriched object.
5. Provenance metadata can be attached without modifying the original schema.

The trade-off is that the hand-written service owns lookup, timeouts, mapping, and validation; **do not overlook framework capabilities** if using native `ContentEnricher`. Choose based on contract clarity rather than fewer lines of code.

### 7.3. Enriching Headers vs. Enriching Payloads

Spring Integration also provides **Header Enricher** for adding routing/observability metadata, such as a controlled `routeGroup` or correlation header.

~~~text
Payload:
  original order + enriched customer profile

Headers:
  traceId, correlationId, routeVersion, replyChannel
~~~

Do not place the entire `CustomerProfile` into headers and force every consumer to read `headers.customerProfile` when it is genuinely part of the business result. Headers can be filtered or altered over HTTP/Kafka/JMS/AMQP; some headers also hold non-serializable internal objects. Choose payload vs. header based on **semantics, security, and transport contracts**, not just read convenience.

## 8. Testing That the Original Payload Is Neither Lost Nor Mutated

### 8.1. Most Important Invariants

For "preserving original payload and enriched data," tests must **assert both directions**:

1. **Original invariant:** input data remains unchanged after enrichment; `orderId`, `customerId`, and `amountVnd` do not change.
2. **Enrichment invariant:** lookup data matches the right customer, tier/verified status, and valid provenance.
3. **Separation invariant:** changing lookup results (across different runs) never mutates `original`.
4. **Failure invariant:** when lookup fails, no `EnrichedOrder` with a wrong or fake profile is emitted.
5. **Downstream invariant:** Router/Handler can access **both original and profile** in the same enriched payload.

Do not merely assert `result.profile() != null`. It could hold **the wrong customer's profile**, wrong source, wrong schema, or unverified data.

### 8.2. JUnit 5 Success Tests

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderContentEnrichmentServiceTest {
    private static final Instant FIXED_TIME =
            Instant.parse("2026-01-01T00:00:00Z");

    private final OrderContentEnrichmentService service =
            new OrderContentEnrichmentService(
                    new InMemoryCustomerProfileDirectory(),
                    Clock.fixed(FIXED_TIME, ZoneOffset.UTC));

    @Test
    void keepsOriginalAndAddsProfileAndMetadata() {
        OrderRequest original = new OrderRequest(
                "ORD-1", "C-007", new BigDecimal("9000000"));

        EnrichedOrder result = service.enrich(original);

        assertSame(original, result.original());
        assertEquals("ORD-1", result.original().orderId());
        assertEquals("C-007", result.original().customerId());
        assertEquals(new BigDecimal("9000000"),
                result.original().amountVnd());

        assertNotNull(result.profile());
        assertEquals("C-007", result.profile().customerId());
        assertEquals("GOLD", result.profile().tier());
        assertTrue(result.profile().verified());

        assertEquals("customer-profile-directory",
                result.metadata().source());
        assertEquals(FIXED_TIME, result.metadata().retrievedAt());
    }

    @Test
    void twoDifferentOrdersDoNotSwapOriginalInformation() {
        OrderRequest first = new OrderRequest(
                "ORD-A", "C-007", new BigDecimal("5000000"));
        OrderRequest second = new OrderRequest(
                "ORD-B", "C-008", new BigDecimal("800000"));

        EnrichedOrder one = service.enrich(first);
        EnrichedOrder two = service.enrich(second);

        assertSame(first, one.original());
        assertSame(second, two.original());
        assertEquals("GOLD", one.profile().tier());
        assertEquals("STANDARD", two.profile().tier());
    }
}
~~~

**Why use `Clock.fixed`?** Calling `Instant.now()` directly and asserting a fixed timestamp makes tests depend on wall-clock time. Injecting `Clock` lets you test metadata timestamps deterministically without `Thread.sleep`.

`assertSame(original, result.original())` is a strong assertion for implementations **retaining the original reference**. If production chooses **controlled deep copying** to prevent shared mutable state, tests should use `assertEquals` on normalized data/serialized representation rather than requiring reference identity. The true invariant is **preserving original data intact per contract**, not always keeping the same object identity.

### 8.3. Negative Tests: Never Merge the Wrong Profile

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderContentEnrichmentFailureTest {
    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void missingProfileIsNotSilentlyReplacedByFakeProfile() {
        CustomerProfileDirectory empty =
                customerId -> Optional.empty();
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        empty, FIXED_CLOCK);

        ProfileNotFoundException error = assertThrows(
                ProfileNotFoundException.class,
                () -> service.enrich(new OrderRequest(
                        "ORD-2", "C-404", new BigDecimal("2000000"))));

        assertEquals("PROFILE_NOT_FOUND: C-404",
                error.getMessage());
    }

    @Test
    void profileForAnotherCustomerIsRejected() {
        CustomerProfileDirectory wrongDirectory =
                id -> Optional.of(
                        new CustomerProfile("OTHER", "GOLD", true));
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        wrongDirectory, FIXED_CLOCK);

        assertThrows(ProfileMismatchException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-3", "C-007", new BigDecimal("2000000"))));
    }

    @Test
    void unsupportedTierIsRejectedBeforeBuildingWrapper() {
        CustomerProfileDirectory invalidTier =
                id -> Optional.of(new CustomerProfile(
                        id, "ADMIN", true));
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        invalidTier, FIXED_CLOCK);

        assertThrows(IllegalArgumentException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-4", "C-007", new BigDecimal("2000000"))));
    }

    @Test
    void invalidOriginalFailsBeforeLookup() {
        CustomerProfileDirectory notCalled = customerId -> {
            throw new AssertionError(
                    "Lookup must not be called for malformed input");
        };
        OrderContentEnrichmentService service =
                new OrderContentEnrichmentService(
                        notCalled, FIXED_CLOCK);

        assertThrows(IllegalArgumentException.class, () ->
                service.enrich(new OrderRequest(
                        "ORD-5", "C-007", BigDecimal.ZERO)));
    }
}
~~~

These tests are high-value because they protect **enrichment semantics**: never altering original data to "patch" a bad lookup, never accepting someone else's profile, and never silently fabricating `GOLD` when the lookup service returns incomplete data.

### 8.4. Testing Original Data Containing Collections

If `original` contains a `List<Item>`, verify:

- If the caller modifies the source `List` after constructing the payload, does the initial snapshot change?
- Can mutable items be modified by another subscriber?
- Does JSON serialization followed by deserialization retain all original items?
- If byte-level audit is needed, is the **raw inbound envelope** persisted at the allowed boundary, or only the parsed DTO?

**Keeping the original DTO** does not automatically preserve every byte or field from the wire request. Converters may drop unknown fields or normalize Unicode, timezones, or numbers. If the business requires exact proof of what arrived at the boundary, define a separate **raw-event retention mechanism** with sensitive-data protection and retention lifecycle.

## 9. Spring Integration Test: Gateway Receives Both Parts of Data

### 9.1. Testing the Pipeline, Not Just the Service

Using `OrderEnrichmentFlowConfiguration` from Section 6 with Spring Test/JUnit 5:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(OrderEnrichmentFlowConfiguration.class)
class OrderEnrichmentFlowIntegrationTest {

    @Autowired
    private OrderEnrichmentGateway gateway;

    @Test
    void gatewayReturnsOriginalAndEnrichmentTogether() {
        OrderRequest request = new OrderRequest(
                "ORD-900", "C-007", new BigDecimal("9000000"));

        EnrichedOrder result = gateway.enrich(request);

        assertEquals(request, result.original());
        assertEquals("C-007", result.profile().customerId());
        assertEquals("GOLD", result.profile().tier());
        assertNotNull(result.metadata());
        assertNotNull(result.metadata().retrievedAt());
    }

    @Test
    void aSecondCustomerHasItsOwnProfile() {
        OrderRequest request = new OrderRequest(
                "ORD-901", "C-008", new BigDecimal("500000"));

        EnrichedOrder result = gateway.enrich(request);

        assertEquals(request, result.original());
        assertEquals("STANDARD", result.profile().tier());
        assertEquals(false, result.profile().verified());
    }
}
~~~

The test above traverses **Messaging Gateway → DirectChannel → Transformer → Gateway reply**, not just a direct Java service call. To prove a **downstream channel** receives `EnrichedOrder`, add a downstream channel/handler or interceptor test after the Transformer and assert both `original` and `profile` are present.

### 9.2. Why Not Return `reply payload = CustomerProfile`?

The lesson's Gateway returns `EnrichedOrder` instead of `CustomerProfile` alone, enabling callers to access both original and enriched data. If a smaller reply such as `EnrichmentReceipt` is needed, build a **dedicated projection** at the boundary:

~~~java
record EnrichmentReceipt(
        String orderId,
        String customerTier,
        boolean verified) {}

EnrichmentReceipt toReceipt(EnrichedOrder result) {
    return new EnrichmentReceipt(
            result.original().orderId(),
            result.profile().tier(),
            result.profile().verified());
}
~~~

Creating a projection does not alter `EnrichedOrder` inside internal processing. However, **if only a receipt is returned externally**, external callers cannot access the full `original` through that reply; that is a contract decision, not data loss by the Enricher.

### 9.3. Testing the Gateway When Lookup Finds No Profile

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(OrderEnrichmentFlowConfiguration.class)
class OrderEnrichmentGatewayErrorTest {
    @Autowired
    private OrderEnrichmentGateway gateway;

    @Test
    void unknownCustomerDoesNotReturnFakeEnrichedOrder() {
        assertThrows(RuntimeException.class, () ->
                gateway.enrich(new OrderRequest(
                        "ORD-404", "C-404", new BigDecimal("500000"))));
    }
}
~~~

Inside a Spring Integration endpoint, business exceptions may be wrapped in `MessageHandlingException` or another messaging exception. **Do not couple tests to a specific wrapper class** unless your dependency version's contract requires it; in real systems, assert on the cause chain or error code and verify no fake "success" reply is produced. Extended tests can check for `PROFILE_NOT_FOUND`, while avoiding brittle dependencies on library message strings that vary across versions.

## 10. When Lookup Fails: Never "Enrich Randomly" to Keep Going

### 10.1. Separating Missing Data from Infrastructure Failures

| Scenario | Nature | Handling Direction |
|---|---|---|
| `customerId` not found | Domain outcome `NOT_FOUND`. | Business rejection/hold per contract; never fabricate GOLD/verified. |
| Response returns different `customerId` | Broken linkage or data corruption. | Fail closed, log security/data error, do not merge. |
| Profile missing mandatory fields | Schema/validation error. | Reject or quarantine; fix upstream/schema. |
| Lookup service times out | Potentially transient infrastructure failure. | Bounded retry, backoff, deadline, idempotency. |
| Cache returns overly stale data | Freshness violation. | Refresh/hold by criticality, never disguise as fresh. |
| Lookup succeeds but downstream fails | Enrichment succeeded, next step failed. | Error/recovery at downstream endpoint, do not count as lookup failure. |
| Customer profile loses verification/tier | Data changes over time. | Define validity window and appropriate source of truth. |

If downstream uses `verified` to authorize shipment, a lookup timeout **must never be interpreted as `verified=true`**. An "unknown" state must be represented explicitly, or the flow must fail/hold per rules.

### 10.2. When Is a Fallback Acceptable?

Some **non-critical** tasks, like displaying a customer greeting name in an email, can use a fallback such as `displayName="Customer"`. However, for data governing **access control, fraud checks, credit limits, taxes, or payments**, a bad fallback can cause real harm.

If using a fallback, the result must not impersonate a successful lookup:

~~~text
EnrichmentResult:
  original: ...
  profile:
    ... fields allowed to use fallback
  metadata:
    enrichmentStatus: FALLBACK
    source: local-cache
    sourceUpdatedAt: ...
    retrievedAt: ...
~~~

The main example flow does **not yet include `enrichmentStatus`**. That is an extended schema for cases where real business logic requires fallback. Never add default fields just so every message receives a reply.

### 10.3. Catching Errors at the Right Layer

Recommended handling path:

~~~mermaid
flowchart TD
    I[Original OrderRequest] --> V{Validate original}
    V -->|Malformed| E1[Input validation error]
    V -->|Valid| L[Lookup profile]
    L -->|Not found| E2[Business hold / reject]
    L -->|Timeout| E3[Retry / recovery]
    L -->|Response| C{Validate customerId + schema}
    C -->|Mismatch| E4[Data integrity failure]
    C -->|OK| W[Create EnrichedOrder wrapper]
    W --> N[Downstream processing]
    N -->|Error| E5[Downstream error flow]
~~~

Separating these errors prevents unit tests and metrics from conflating `malformed_original` with `lookup_timeout` or `downstream_failed`. Catching everything and returning `new CustomerProfile("unknown", "GOLD", true)` lets the system keep running with fabricated data and zero traceability.

### 10.4. Where to Place Retries

If the lookup lives inside a synchronous flow, retries can wrap the **lookup invocation** without necessarily retrying the entire pipeline from the start. Retrying the whole flow can re-execute earlier steps (auditing, DB writes, or outbound requests).

With `DirectChannel`, lookup exceptions typically unwind up the call stack. With `ExecutorChannel`, `QueueChannel`/poller, or a broker, failure may happen after the producer already handed off the message; design `errorChannel`, `ErrorMessage`, or per-adapter/poller error handlers accordingly.

Never assume every async error automatically enters one shared error channel or retries safely. Define **delivery semantics, ack, redelivery, retry scope, dead-letter/quarantine, timeouts, and attempt limits**.

## 11. Preserving Correlation and Message Context

### 11.1. Original Payload Does Not Replace `MessageHeaders`

When using the `EnrichedOrder` wrapper, the business original is preserved **inside the new payload**. Yet the message also carries Spring Integration **headers**:

| Metadata | Purpose | Watch Out for Through Enricher |
|---|---|---|
| `MessageHeaders.ID` | Identifies a specific Spring message. | May be regenerated when an endpoint builds a new message. |
| `timestamp` | Framework message creation time. | Does not necessarily match lookup time. |
| `traceId` / trace context | Cross-thread/service tracing. | Requires propagation via instrumentation/adapters. |
| `correlationId` | Groups messages or results of one task. | Critical for Splitter/Aggregator. |
| `sequenceNumber` / `sequenceSize` | Position and count in a group. | Never modify arbitrarily while enriching a child message. |
| `replyChannel` | Internal Gateway return path. | May be a JVM object; never serialize raw to HTTP/brokers. |
| `errorChannel` | Message error context. | Does not automatically guarantee every failure emits an `ErrorMessage`. |

**Preserving the original payload is distinct from preserving headers.** Never use `assertEquals(request, result.original())` to infer that trace/correlation headers survived across adapters.

### 11.2. Correlation for Lookup Request–Reply

Suppose two distinct orders share `customerId=C-007`:

~~~text
Order A: orderId=ORD-11, customerId=C-007
Order B: orderId=ORD-12, customerId=C-007
~~~

Both lookup requests may return the same customer profile, yet each reply must return to **its matching original order**. Relying solely on `customerId` to match async request–reply calls easily mixes up concurrent requests.

When implementing request–reply across transports, include a unique **lookupAttemptId / correlation ID** per in-flight request, along with timeouts and cleanup. Business `orderId` aids traceability, yet cannot fully replace an attempt ID if the same order triggers multiple concurrent lookups.

~~~mermaid
sequenceDiagram
    participant A as Order A
    participant B as Order B
    participant E as Enricher
    participant P as Profile Service
    A->>E: Order A (ORD-11)
    B->>E: Order B (ORD-12)
    E->>P: Lookup C-007 / attempt-a
    E->>P: Lookup C-007 / attempt-b
    P-->>E: Profile / attempt-b
    E-->>B: EnrichedOrder(original=B, profile)
    P-->>E: Profile / attempt-a
    E-->>A: EnrichedOrder(original=A, profile)
~~~

This diagram shows the **target contract**, not a guarantee that Spring Integration automatically attaches `attempt-a`/`attempt-b` across all adapters. Use transport- and component-supported correlation/reply-mapping mechanisms, or manage them explicitly in async workflows.

### 11.3. When Enrichment Occurs Between Splitter and Aggregator

Example of an order with three line items:

~~~mermaid
flowchart LR
    O[Order with 3 items] --> S[Splitter]
    S --> I1[Item 1]
    S --> I2[Item 2]
    S --> I3[Item 3]
    I1 --> E[Enricher fetching product details]
    I2 --> E
    I3 --> E
    E --> A[Aggregator]
    A --> R[EnrichedOrderItems]
~~~

Each item must retain both its original item data and the enriched product details, while **also keeping correlation/sequence metadata** so the Aggregator knows which items belong to the same order. If one item's lookup fails and emits nothing, the group may stall until timeout. Define:

- **Partial failure:** may a list of two enriched items be returned?
- **Release policy:** wait for all three, wait for quorum, or release on deadline?
- **Missing item representation:** is a failed item emitted as a result carrying failure status?
- **Retry:** retry only the failed item or re-split/re-lookup the entire order?
- **Duplicates:** could an item delivered twice make the Aggregator miscount `sequenceSize`?

An Enricher might preserve the original payload perfectly while the flow still fails if correlation metadata is dropped by an adapter. Therefore, wrapper unit tests and Splitter/Aggregator integration tests must remain **two separate verification layers**.

### 11.4. Message History Is Not Provenance

Spring Integration's **Message History** records which components a message traversed when tracking is enabled. It **does not tell you** which version of Customer Profile Service supplied `profile.tier`, when it was queried, or whether it was stale. Conversely, `LookupMetadata` describes lookup provenance without recording every endpoint along the journey.

To audit an important decision, combine:

1. Business IDs and correlation/trace context.
2. Original input from a trusted source.
3. Enrichment source, timestamps, and policy/data versions as needed.
4. Downstream routing decisions and outcomes.
5. Error/retry history reconcilable via stable IDs.

## 12. Freshness, Caching, and Replay

### 12.1. Enrichment Results Can Become Stale

Suppose:

~~~text
10:00 Customer tier = GOLD
10:01 Order ORD-10 enriched with GOLD
10:05 Customer tier changes to STANDARD
10:08 Replay ORD-10
~~~

On replay, there are two distinct choices:

| Policy | Replay Uses | When Appropriate |
|---|---|---|
| **Historical reproducibility** | The profile snapshot/provenance used at 10:01. | Auditing or reproducing past decisions. |
| **Re-evaluate latest** | Fresh profile lookup at 10:08. | Business allows re-deciding using current state. |

Without an explicit policy, the same original order can be enriched differently on every retry. That is **not necessarily a bug**, yet it must be understood whenever downstream branches compute limits, discounts, taxes, or permissions.

### 12.2. Distinguishing a Cache Hit from Verified Data

Caching lowers latency while raising freshness requirements:

~~~text
EnrichmentMetadata
  source          = profile-cache
  retrievedAt     = 10:08
  sourceUpdatedAt = 09:30
  cacheHit        = true
  maxAgeSeconds   = 300
~~~

This is an **extended illustrative schema**, not fields currently present in `LookupMetadata` from the main Java snippet. `retrievedAt=10:08` does not prove the profile was freshly updated at 10:08.

For access-control or payment data, define **TTL, whether stale-while-revalidate is allowed, invalidation mechanisms, fallback when the primary source is down**, and consistency guarantees. Never use a stale cache to "verify" a status that may have been revoked.

### 12.3. Idempotency When Enrichment Has Side Effects

Read-only lookups can be re-executed, yet an enrichment flow occasionally calls an external system to **create** a record, issue a code, or log a transaction. Retries then risk duplicate side effects. Define an operation/idempotency key and replay policy.

Even if the flow is purely:

~~~text
OrderRequest -> GET CustomerProfile -> EnrichedOrder
~~~

the enrichment appears side-effect-free yet can still return newer data over time. "Idempotent" in the sense of **no duplicate side effects** does not mean "byte-identical result on every call." Separate two goals:

- **Side-effect idempotency:** never duplicate business mutations.
- **Deterministic replay:** reproduce the exact decision and data as of a point in time.

### 12.4. Versioning Original and Enrichment Schemas

If Checkout evolves from v1 to v2 by adding `salesChannel`, while Profile Service renames `tier` to `membershipLevel`, a wrapper keeps the two schemas decoupled. Downstream still needs to know the `EnrichedOrder` schema and how to migrate new fields.

A protocol envelope over HTTP/Kafka might include:

~~~json
{
  "schemaVersion": 2,
  "original": {
    "orderId": "ORD-1001",
    "customerId": "C-007",
    "amountVnd": 9000000
  },
  "profile": {
    "customerId": "C-007",
    "tier": "GOLD",
    "verified": true
  },
  "enrichment": {
    "source": "customer-profile-directory",
    "lookupRequestId": "lookup-ORD-1001",
    "retrievedAt": "2026-01-01T00:00:00Z"
  }
}
~~~

This is an **illustrative wire JSON example**, not data from a live system. If old messages must be reinterpreted later, maintain backward compatibility for older versions and never confuse technical timestamps with business effective times.

## 13. Testing When Router or Filter Follows Enrichment

### 13.1. Router Must Read the New Data Section Properly

A Router may select a channel by customer tier while the payment handler still needs the original amount:

~~~text
EnrichedOrder
   |
   +-- original.amountVnd = 9000000
   +-- profile.tier = GOLD
   |
   v
Router
   | tier=GOLD  -> priority
   | other      -> standard
~~~

Never copy `profile.tier` into `original` just to give the Router a shorter path. A simple routing function can be:

~~~java
String routeFor(EnrichedOrder order) {
    return "GOLD".equals(order.profile().tier())
            && order.profile().verified()
            ? "priority" : "standard";
}
~~~

In practice, routing by `tier` may affect perks or privileges; verify the **tier is verified**, never trusting client-supplied fields in `original` to spoof a tier.

### 13.2. Filter After Enrichment Can Reject Valid Messages

If a Filter requires `profile.verified() == true`, an order that was **validly enriched** with `verified=false` will be **rejected by Filter policy**. That is neither a lookup failure nor malformed data.

~~~text
Order C-008
  -> lookup returns CustomerProfile(C-008, STANDARD, false)
  -> Valid EnrichedOrder
  -> Filter(verified)
  -> rejected / review
~~~

Distinguish clearly:

- **Lookup error:** unable to build a contract-compliant enriched payload.
- **Filter rejection:** valid enriched payload fails policy predicate.
- **Router decision:** selects a channel from the enriched payload.
- **Downstream error:** endpoint fails after accepting the message.

A dedicated test should assert that `profile.verified=false` **is never conflated with a missing profile**, and that the message enters the review branch per policy.

### 13.3. A Standalone Testable Decision Function

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EnrichedOrderRoutingPolicyTest {
    @Test
    void verifiedGoldGoesToPriorityWithoutChangingOriginal() {
        OrderRequest original = new OrderRequest(
                "ORD-1", "C-007",
                new java.math.BigDecimal("9000000"));
        EnrichedOrder result = new EnrichedOrder(
                original,
                new CustomerProfile("C-007", "GOLD", true),
                new LookupMetadata("test", "lookup-1",
                        java.time.Instant.EPOCH));

        String route = "GOLD".equals(result.profile().tier())
                && result.profile().verified()
                ? "priority" : "standard";

        assertEquals("priority", route);
        assertEquals(original, result.original());
    }
}
~~~

If the application wires this as a Spring Integration Router, integration tests must verify **which channel actually receives the message**, not just `routeFor`. Channel mapping tables, subscriber lifecycles, and error handling are separate layers to verify.

## 14. Observing Enrichment Without Leaking Data

### 14.1. Tracking Processing Milestones

An `OrderCreated` event may transition through these states:

~~~text
ORDER_RECEIVED
  -> ENRICHMENT_STARTED
  -> PROFILE_LOOKUP_SENT
  -> PROFILE_LOOKUP_RECEIVED
  -> ENRICHMENT_COMPLETED
  -> ROUTE_DECIDED
  -> BRANCH_COMPLETED
~~~

When lookup fails:

~~~text
ORDER_RECEIVED
  -> ENRICHMENT_STARTED
  -> PROFILE_LOOKUP_FAILED (timeout)
  -> ENRICHMENT_RETRY_SCHEDULED
  -> ... / ENRICHMENT_RECOVERY
~~~

**This is an application-proposed event schema**, not logs automatically emitted by Spring Integration when calling `.transform(...)`. Distinct event names prevent confusing **lookup sent** with **profile received** or **downstream completed**.

### 14.2. Structured Logs with Provenance

Example:

~~~text
event=ENRICHMENT_STARTED
  orderId=ORD-1001 customerRef=C-007
  traceId=T-1001 lookupAttemptId=L-0001

event=PROFILE_LOOKUP_RECEIVED
  lookupAttemptId=L-0001
  source=customer-profile-directory
  profileMatch=true

event=ENRICHMENT_COMPLETED
  orderId=ORD-1001
  lookupAttemptId=L-0001
  source=customer-profile-directory
  tier=GOLD

event=ROUTE_DECIDED
  orderId=ORD-1001
  route=priority
  reason=VERIFIED_GOLD
~~~

Never log full copies of `OrderRequest` or `CustomerProfile` if they contain names, addresses, emails, tokens, or personal data. In many systems, even `customerId` is an identifier needing masking/hashing or shorter retention. Log only fields permitted by policy.

### 14.3. Metrics Separating Lookup Time from Downstream Time

| Illustrative Metric | Meaning |
|---|---|
| `enrichment_requests_total` | Messages entering enrichment. |
| `enrichment_completed_total` | Valid enriched payloads produced. |
| `enrichment_failed_total{reason}` | Classified not-found, mismatch, timeout, schema errors. |
| `profile_lookup_latency_ms` | Latency of the lookup source. |
| `enrichment_total_latency_ms` | Total validate + lookup + merge duration. |
| `enrichment_cache_hit_total` | Cache hit count, if cached. |
| `enrichment_fallback_total` | Contract-permitted fallbacks used. |
| `enrichment_stale_result_total` | Results flagged as stale. |
| `enriched_branch_completed_total` | Downstream outcomes after enrichment. |
| `error_channel_messages_total` | Errors routed through configured error flows. |

These are **suggested metric names**, not meters automatically provided by Spring Integration. Never put high-cardinality `orderId`, `customerId`, or `traceId` into metric labels; keep them in authorized logs and traces.

### 14.4. Distinguishing Diagnostic Questions

| Signal | Valid Conclusion |
|---|---|
| `ENRICHMENT_STARTED` seen | Enricher began; lookup may not be done yet. |
| `PROFILE_LOOKUP_RECEIVED` seen | Response arrived; schema/`customerId` not yet guaranteed valid. |
| `ENRICHMENT_COMPLETED` seen | Wrapper built per contract; downstream success not yet guaranteed. |
| `ROUTE_DECIDED` seen | Router picked target; handler may not have received it yet. |
| `BRANCH_COMPLETED` seen | Branch reported completion per contract; check side effects and transactions. |

For instance, if a customer complains "a GOLD order didn't get priority," check in order: did the original order have the right `customerId`, which profile did lookup return, was there a mismatch or staleness, did the enriched payload have `verified=true`, did the Router read the right profile namespace, and finally inspect the priority channel and handler.

## 15. Security, Privacy, and Trust Boundaries

### 15.1. Do Not Let Input Data Masquerade as Enrichment

If a client sends:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "C-007",
  "amountVnd": 9000000,
  "tier": "GOLD",
  "verified": true
}
~~~

the fields `tier` and `verified` **must never be trusted just because they appeared in JSON**. In this lesson's model, `original` lacks those two fields; the Enricher fetches them from an authenticated source and checks `customerId`. If converters still accept unknown fields, explicitly decide whether to reject, ignore, or log schema violations—never let them silently overwrite the trusted `profile`.

### 15.2. Validating Lookup Results

A production Customer Profile Service call needs:

- Inter-service authentication/authorization with least privilege.
- Validation of response schema, matching customer ID, and allowed tier values.
- Timeouts, retry policies, and permanent vs. transient error classification.
- Purpose-limited response fields; avoid fetching full profiles when only tier/verified is needed.
- Data protection across logs, message stores, DLQs, tracers, and brokers.
- Never accepting profiles from a cache entry belonging to the wrong tenant or partition.

A **profile mismatch** can indicate a lookup bug or cross-tenant data leak, so never "ignore it and substitute the original's customerId" as if everything were fine.

### 15.3. Payload vs. Headers Across Adapters

An outbound adapter may map payloads and headers differently. If `EnrichedOrder` crosses Kafka or HTTP:

1. Define a versioned **wire schema** permitting `original`/`profile`/`enrichment`.
2. Test serialization/deserialization explicitly instead of assuming all internal headers transfer automatically.
3. Propagate trace/correlation context via transport-supported mechanisms.
4. Never serialize JVM `replyChannel`/`errorChannel` objects.
5. Write round-trip tests proving neither `original` nor enrichment drops fields.
6. Encrypt or minimize sensitive fields per security requirements.

If you send only `profile` as the payload and tuck `original` into a custom header, adapters may strip the header and lose initial business data. When **both parts are mandatory business data**, a wrapper payload is a far more verifiable contract.

## 16. Comprehensive Test Matrix

| ID | Input / Condition | Expected | Must Not Happen |
|---|---|---|---|
| CE-01 | Valid order, GOLD verified profile | Wrapper has original + profile + metadata | Original amount/`customerId` mutated. |
| CE-02 | Valid order, STANDARD unverified profile | Wrapper still valid | Auto-setting GOLD/verified. |
| CE-03 | Customer profile missing | `PROFILE_NOT_FOUND` error | Returning fake "success" profile. |
| CE-04 | Lookup returns different `customerId` | Mismatch error | Merging someone else's profile into original. |
| CE-05 | Tier outside allowlist | Validation error | Router receiving unknown key. |
| CE-06 | `amount` is `null`/0/negative | Original validation error before lookup | Calling lookup unnecessarily. |
| CE-07 | Blank `customerId` | Original validation error | Routing as valid customer. |
| CE-08 | Amount 9,000,000 | Result preserves exact `BigDecimal` | Losing precision via `double` cast. |
| CE-09 | Original contains mutable list | Defensive copy per contract | Another subscriber mutating original data. |
| CE-10 | Fixed clock | Metadata has exact timestamp | Tests depending on `sleep`. |
| CE-11 | Gateway sends `OrderRequest` | Replies with full `EnrichedOrder` | Returning only `CustomerProfile`. |
| CE-12 | Lookup returns valid data, downstream fails | Enrichment succeeds, downstream fails | Counting as lookup failure. |
| CE-13 | CustomerProfile Service times out | Bounded retry/recovery | Setting `verified=true` or retrying forever. |
| CE-14 | Cache returns stale data | Behavior matches freshness policy | Marking old data as fresh. |
| CE-15 | Two orders for same customer | Each enriched wrapper matches its order | Merging order A's reply onto B. |
| CE-16 | Splitter item passes through enrich | Correlation/sequence preserved | Aggregator mixing groups. |
| CE-17 | One item fails lookup | Explicit release/timeout | Aggregator waiting forever. |
| CE-18 | Message crosses HTTP/Kafka adapter | Original/enrichment round-trip intact | Critical headers/fields silently dropped. |
| CE-19 | Replay after profile changed | Matches historical/latest policy | Unknown which version was used. |
| CE-20 | Lookup succeeds, Gateway reply times out | Error/late reply managed | Caller assuming all side effects aborted. |
| CE-21 | Client supplies fake tier/verified | Never overrides trusted profile | Bypassing authorization. |
| CE-22 | Concurrent lookup requests | Correlation stays isolated | Matching all replies solely by `customerId`. |
| CE-23 | Retry of operation with side effect | Proper idempotency/reconciliation | Duplicate side effects. |
| CE-24 | Post-enrich handler needs original | Still accesses `orderId`/`amount` | Only hidden headers or `profile` left. |

Not every test needs live external services. **Unit tests** protect policies/wrappers, **Spring integration tests** verify Gateway/Transformer/channels, **adapter-level tests** verify serialization/header mapping, and **system tests** verify timeouts, caching, retries, consistency, and security. Choose the **test level capable of catching each failure mode**.

### 16.1. Tests Without a Spring Context

Use plain JUnit for `OrderContentEnrichmentService` with a fake directory:

~~~text
Given:
  original = OrderRequest(ORD-1, C-007, 9000000)
  directory returns CustomerProfile(C-007, GOLD, true)

When:
  enrich(original)

Then:
  result.original == original
  result.profile.customerId == original.customerId
  result.metadata.source != blank
~~~

Avoid over-mocking where tests only verify what a mock returned. For example, if a mocked `directory` returns a profile but the service skips checking `customerId`, only the **mismatched-ID negative test** in Section 8 catches that bug meaningfully.

### 16.2. Tests Through Real Adapters

If the module publishes enriched payloads to Kafka:

~~~text
Java EnrichedOrder
   -> serializer / outbound adapter
   -> broker record
   -> inbound adapter / deserializer
   -> Java EnrichedOrder
~~~

Assert after the round-trip:

- `original.orderId`/`customerId`/`amountVnd` are intact.
- `profile.tier`/`verified` are intact.
- `metadata.source`/`retrievedAt` match the contract.
- Schema versions are compatible and incompatible versions are detected.
- Trace/correlation context is mapped and restored where required.

Do not run an in-JVM serializer test and assume a broker consumer in another process preserves every header. Test adapters and transports under realistic configuration.

## 17. Common Design Mistakes

| Mistake | Risk | Right Approach |
|---|---|---|
| Enricher returns only `CustomerProfile`. | Loses `orderId` and `amount` from original payload. | Use a wrapper keeping both original and profile, or an intentional projection. |
| Overwriting original with lookup data. | Cannot tell what upstream sent; audits and retries become unreliable. | Keep original separate, attach enrichment provenance. |
| Treating Java `record` as deeply immutable. | Nested collections/objects can still be mutated. | Defensive copy and eliminate shared mutable state. |
| Skipping checks on response `customerId`. | Merges another customer's data, risking tenant breach. | Match lookup key, response identity, and authorization. |
| Using client-supplied tier. | Spoofing tiers/privileges. | Fetch from trusted source and validate. |
| Defaulting to GOLD when profile is missing. | Permits policy-violating processing. | Fail closed or use clearly labeled, scoped fallback. |
| Treating lookup timeout as `verified=false` without distinction. | Conflates infrastructure outage with verified unverified status. | Use dedicated unavailable/recovery states. |
| Treating `retrievedAt` as profile update time. | Decisions based on false freshness. | Separate `sourceUpdatedAt` and `retrievedAt` when needed. |
| Enriching every field "just in case." | Bloated payloads, high lookup cost, unnecessary data exposure. | Fetch only fields consumers actually need. |
| Storing original inside `replyChannel`. | Internal headers may not cross transports; wrong semantics. | Keep original in the business payload/schema. |
| Testing only `profile != null`. | Could merge wrong customer or lose original. | Assert both parts, ID matching, metadata, and negative cases. |
| Assuming `.transform` and native `.enrich` behave identically. | Overlooking mutation, property mapping, and reply differences. | Pick API by contract and test on actual framework version. |
| Running lookup on every full-flow retry. | Amplifies traffic, results may drift, duplicates side effects. | Retry at the right scope with idempotency and provenance. |
| Using stale cache without marking it. | Users/Routers believe data is up to date. | Enforce freshness policy and source metadata. |
| Assuming Dispatcher/MessageBuilder preserves all headers over HTTP/Kafka. | Drops correlation or reply context. | Map headers per transport contract; test round-trips. |
| Letting failed Enricher continue to Router with fake profile. | Wrong processing branch selected. | Never build a success wrapper when guarantees are unmet. |
| Logging full enriched profiles. | Leaks sensitive data. | Log controlled IDs/flags with masking and retention. |
| Treating Message History as profile data lineage. | Cannot tell which source/version supplied data. | Add provenance and audit records as needed. |
| Assuming Gateway accepted means external side effects committed. | Premature success reporting. | Track business outcomes at each endpoint. |
| Sharing one lookup correlation ID across requests with the same `customerId`. | Replies cross-wire between orders. | Generate unique attempt/request IDs for async correlation. |

## 18. Practice Exercises

1. **Preserve original:** create a valid `OrderRequest`, use `OrderContentEnrichmentService` to produce `EnrichedOrder`, and verify every original field keeps its exact value.
2. **Lookup source missing:** make directory return `Optional.empty()`. Write a test confirming no fake `CustomerProfile` is fabricated and `ProfileNotFoundException` is thrown.
3. **Wrong customer:** make directory intentionally return another ID's profile. Prove `ProfileMismatchException` is thrown before downstream receives any message.
4. **Immutability check:** add `List<OrderItem>` to `original`, mutate the source list after record construction, apply defensive copying, and write a test catching mutations.
5. **Provenance:** add `sourceUpdatedAt` to metadata and test its difference from `retrievedAt` using `Clock.fixed`.
6. **Gateway integration:** use `OrderEnrichmentFlowConfiguration`, call `OrderEnrichmentGateway.enrich`, and assert original, profile, and metadata are all present.
7. **Native Content Enricher:** replace the Transformer using your Spring Integration version's Content Enricher. Clarify request/reply mapping, property/header mapping, mutation/copy behavior, and output; test that both parts remain intact.
8. **HTTP enrichment:** replace the in-memory directory with a fake outbound gateway/client; test success, 404, malformed response schema, and timeout. Design deadline-aware retries and error classification.
9. **Router after enrichment:** if `GOLD` and verified, route to priority, otherwise standard; prove handlers on both branches can still read the original order.
10. **Filter after enrichment:** valid profile with `verified=false`. Verify business rejection is distinct from lookup failure.
11. **Stale cache:** simulate a cache entry with an overly old `sourceUpdatedAt`; choose fail closed or fallback per explicit policy and write tests.
12. **Replay:** enrich the same original at two different times while the customer tier changes. Compare historical snapshot vs. re-evaluate latest.
13. **Splitter/Aggregator:** split one order into three items, enrich each by product ID, and aggregate. Intentionally drop one item and handle timeout/group release.
14. **Async correlation:** send two requests with the same `customerId` but different `orderId`s to an async lookup service, reverse reply order, and prove originals are never swapped.
15. **Transport:** serialize `EnrichedOrder` to JSON and deserialize it. Verify original, profile, and provenance remain complete; add missing-field and schema-version tests.
16. **Security:** send an original payload containing a client-spoofed `tier=GOLD` field. Prove parsing/validation prevents it from overriding the looked-up profile.
17. **Observability:** emit `ENRICHMENT_STARTED`, `PROFILE_LOOKUP_RECEIVED`, `ENRICHMENT_COMPLETED`, and `ENRICHMENT_FAILED` logs and trace a failed request via trace/correlation.
18. **Error channel:** move lookup to an asynchronous adapter, configure appropriate error handling, and prove producer acknowledgement does not mean enrichment finished.

### Tips for Checking Exercise Outcomes

To evaluate a sound implementation, ask:

- After enrichment, can a consumer **access the original payload without looking it up again**?
- Does the enriched data have **matching identity and trusted provenance**?
- Do we know when the profile came from and whether it could be stale?
- When lookup fails or is missing, do we **refuse to emit a false success wrapper**?
- When a message is retried or replayed, is the old-vs-new snapshot policy explicit?
- In async flows, can we tell when a request was **dispatched**, **enriched**, and **completed downstream**?

If the answer is "no" to any business-critical question, strengthen schemas, error handling, or tests before going to production.

## 19. Self-Check Questions

**Q1:** Why can returning only `CustomerProfile` from enrichment be a bug?  
**Answer:** After lookup, the payload no longer contains `OrderRequest` and fields like `orderId`/`amountVnd` unless stored under a separate contract; downstream cannot access the original as required.

**Q2:** Does `record EnrichedOrder(OrderRequest original, CustomerProfile profile, ...)` guarantee every nested object is immutable?  
**Not yet.** A `record` fixes top-level references, yet nested mutable objects or collections can still change; apply defensive copying where needed.

**Q3:** Original has `customerId = C-007`, yet lookup returns profile `C-099`. Can we merge and proceed?  
**No.** That is an identity/data-integrity failure and potentially a security issue; reject or recover per contract.

**Q4:** How does "lookup profile not found" differ from "lookup HTTP timeout"?  
**Not found** is a deterministic domain outcome; **timeout** may be an infrastructure error or uncertain outcome. Their retry and recovery policies differ.

**Q5:** Can `Clock.fixed` be used to test `retrievedAt`?  
**Yes.** Injecting `Clock` makes tests deterministic without sleeping or reading wall-clock time for approximate comparisons.

**Q6:** If `EnrichedOrder` holds both original and profile, are all message headers guaranteed to survive over Kafka?  
**No.** Payload and `MessageHeaders` are separate; adapters, header mappers, and serializers determine which metadata crosses the wire.

**Q7:** If the same order is re-enriched the next day with a new tier, do differing results automatically prove a bug?  
**No.** You must check whether the policy is historical snapshot or re-evaluate latest; profiles legitimately change over time.

**Q8:** When a post-enrichment Filter drops an order because `verified=false`, is that a lookup failure?  
**No.** Lookup may have succeeded with a valid profile; the Filter rejected it per business policy.

**Q9:** Why can using only `customerId` as a correlation key break under async lookup?  
**Because** multiple orders or attempts can share the same `customerId`; each reply must return to its matching request/original.

**Q10:** Can using `.transform(...)` to build a wrapper implement the Content Enricher pattern?  
**Yes.** The pattern describes data enrichment semantics; the Transformer endpoint constructs the new payload. However, it differs from dedicated Content Enricher APIs in mapping, request–reply, and object-handling details, so test the chosen approach properly.

**Q11:** Should raw `replyChannel` and `errorChannel` objects be copied into JSON events to "preserve metadata"?  
**No.** They may be internal JVM references; design proper transport reply/correlation and header mapping instead.

**Q12:** Why is an `ENRICHMENT_COMPLETED` log not enough to prove an order was persisted?  
**Because** it only marks when the enrichment result was constructed. The downstream persistence endpoint may not have run yet, may still be running, or may have failed.

## 20. Conclusion

**Preserving the original payload and enriched data** is more than appending a few fields to an object. It is a decision about **data contracts, immutability, provenance, traceability, and the correctness of downstream steps**.

With Spring Integration, a clean design keeps `OrderRequest` in `original`, lookup results in `profile`, and provenance in `enrichment`/`metadata`. You can use a **dedicated Content Enricher** or a **Transformer paired with an enrichment service** to build an immutable wrapper; what matters is never losing input, never mixing identities, never fabricating data on lookup errors, and understanding the response/header semantics of the endpoints you use.

When combined with Router, Filter, Gateway, Splitter, Aggregator, and error channels in `SPRING_INTEGRATION_PATTERN`, test thoroughly across success paths, missing data, mismatches, timeouts, stale data, retries, and correlation. The result is a flow that is more loosely coupled, more extensible, and lets operators answer three essential questions: **"What was originally received?", "What data was enriched and from where?", and "What did the next step decide and do?"**
