# Header Enricher, Content Enricher, and Adding Metadata

## 1. Why Does an Integration Flow Need Enrichment?

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters. An inbound message may contain only raw partner fields, while routing, contract checks, database writes, or event publishing need extra context such as tenant, schema version, correlation keys, and customer details.

**Enrichment** is a design pattern that turns an under-informed message into one with sufficient context for downstream processing without destroying its original meaning. In the **Routing and Transformation** chapter, Spring Integration provides two primary mechanisms:

- **Header enricher**: adds or computes **metadata inside `MessageHeaders`** while keeping the original business payload intact.
- **Content enricher / payload enricher**: adds **fields to the payload** from static values, expressions, or lookup results from another flow; it can also enrich headers from lookup results.

This is more than choosing an API. Enrichment impacts **data contracts, latency, transactions, idempotency, security, error flows, and observability**. If enrichment calls HTTP or a database, a seemingly simple "transform" box on a diagram can become the most critical bottleneck in the flow.

Lesson objectives:

1. Distinguish **headers** from **payload** and understand metadata's role in routing.
2. Configure **enrichHeaders** in Java DSL and explain overwrite, expressions, and functions.
3. Configure **content enrichers** to look up data over a request/reply channel and map returned properties.
4. Choose properly among enricher, transformer, filter, router, and service activator.
5. Design timeouts, fallbacks, error handling, and data ownership when enrichment calls external systems.
6. Audit metadata across adapters, avoid leaking sensitive information, and protect replayability.
7. Write tests proving payload contents, headers, execution order, and failure cases.

## 2. A Message Consists of Payload and Headers

Spring Messaging models a message via **Message<T>**, containing:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

This is an abbreviated interface for explanation; full imports and API details reside in Spring Messaging.

**Payload** holds business data: **OrderCreated**, JSON, `byte[]`, DTOs, or commands to process. **Headers** hold auxiliary properties for transport, correlation, routing, and flow control.

Example:

~~~text
Message
├── Payload
│   ├── orderId       = "O-172"
│   ├── customerId    = "C-44"
│   ├── tenantId      = "shop-east"
│   ├── amount        = 560000
│   └── customer      = (not yet looked up)
└── Headers
    ├── id            = framework-managed UUID
    ├── timestamp     = message creation timestamp
    ├── sourceSystem  = "partner-api"
    ├── flowVersion   = "2"
    ├── correlationId = "req-9f1"
    └── contentType   = "application/json"
~~~

**MessageHeaders are essentially immutable**: operations that "change headers" normally build a new message or new header map. However, **the payload object inside the message may be mutable**. If a content enricher mutates a JavaBean shared across parallel branches, other branches may observe unintended modifications.

### When Should a Field Be a Header?

| Information | Typical Placement | Reason |
| --- | --- | --- |
| `orderId`, `customerId`, `lineItems`, `amount` | **Payload** | Part of the business contract and often persisted |
| `sourceSystem`, `integrationFlow`, `schemaVersion` | **Header** | Metadata for adapters, routing, and processing |
| `correlationId`, trace context | **Header** | Links processing steps and replies |
| `idempotencyKey` | Explicitly defined header or payload/business record | Must remain stable across retries/replays and boundaries |
| `customerCreditLevel`, `customerAddress` | **Payload** if needed by downstream business logic | Enriched business data from customer service |
| `retryAttempt`, `deliveryCount` | Transport header/context or metric | Managed by broker/adapter; do not conflate with business retries |
| `accessToken`, `password`, API secret | Never attach blindly to messages | Risk of logging, serializing, or leaking to brokers/receivers |

**Never trust a header simply because it sits in `MessageHeaders`.** Headers coming from HTTP requests, broker records, or external partners can be forged. Security metadata such as tenant/role must be verified at a trusted boundary; never use unverified values to authorize data access.

## 3. Overall Flow: Header Enrichment Then Content Enrichment

Suppose the system receives a lightweight order from a partner. The flow must tag the flow version and look up the customer profile before routing delivery:

~~~mermaid
flowchart TD
    A["HTTP / Kafka / AMQP inbound"] --> B["Deserialize, validate schema & tenant"]
    B --> C["Header enricher"]
    C --> D["Headers: sourceSystem, flowVersion, correlationId"]
    D --> E["Content enricher"]
    E --> F["Request: customerId"]
    F --> G["Customer lookup: DB/cache/HTTP"]
    G --> H["Reply: CustomerProfile"]
    H --> I["Payload: OrderDraft + customer"]
    I --> J{"Router by customer tier/tenant"}
    J -->|"priority"| K["Priority processing"]
    J -->|"standard"| L["Standard processing"]
    F -.->|"timeout/error"| M["Retry / fallback / error flow"]
~~~

The order matters:

1. **Validate and authenticate tenant** before enrichment so you never look up another tenant's data.
2. **Enrich headers** first so lookup branches and traces carry normalized metadata.
3. **Enrich payload** from a contracted reply without stuffing entire sensitive objects into headers.
4. **Route** using the enriched field or verified metadata.
5. **Attach error handling at the right boundaries** so "customer not found" is not confused with "HTTP timeout."

## 4. Header Enricher in Spring Integration

**HeaderEnricher** fits when you want to set multiple headers without writing a custom transformer purely to manipulate `MessageHeaders`. In Java DSL, the standard method is **enrichHeaders(...)**.

### 4.1. Dependencies and Minimal Setup

With a Spring Boot parent or BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Illustrative `IntegrationFlow`:

~~~java
@Configuration
public class OrderHeaderFlowConfiguration {

    @Bean
    IntegrationFlow orderHeaderFlow() {
        return IntegrationFlow.from("validatedOrders")
                .enrichHeaders(h -> h
                        .header("flowVersion", "2")
                        .header("sourceSystem", "order-connector")
                        .headerFunction("businessKey", message -> {
                            OrderDraft order = (OrderDraft) message.getPayload();
                            return order.getOrderId();
                        }))
                .channel("headerEnrichedOrders")
                .get();
    }
}
~~~

Spring imports and **OrderDraft** are omitted; `OrderDraft` is defined in the next section. **validatedOrders** is a contract-checked input channel and **headerEnrichedOrders** is the output channel. Values like **flowVersion/sourceSystem** are trustworthy only when attached at an application-controlled boundary.

**header(name, value)** sets a static value; **headerFunction(name, fn)** computes a header from the message; you can also use **headerExpression(name, spel)** when a concise, testable expression fits:

~~~java
.enrichHeaders(h -> h
        .header("flowVersion", "2")
        .headerExpression("businessKey", "payload.orderId"))
~~~

In the expression example, **payload** is the source message's payload object and **orderId** must be accessible via SpEL (getter/property). Expressions are not compile-time checked like Java lambdas, so property renames may surface only at runtime or in integration tests.

### 4.2. Keep or Overwrite Existing Headers?

Spring Integration lets you configure **overwrite** behavior on header enrichers. Never assume every header can be safely overwritten.

| Header | Recommended Policy | Reason |
| --- | --- | --- |
| Application-set **flowVersion** | May be set/normalized explicitly | Controls internal contract |
| Verified **sourceSystem** | Set only at trusted ingress; avoid mid-flow edits | Supports audit and attribution |
| Valid **correlationId** | Usually preserved across steps | Overwriting breaks traces and reply matching |
| **replyChannel / errorChannel** | Never alter carelessly | Breaks request/reply or error routing |
| Spring Message **id / timestamp** | Leave to the framework | Reflects new message identity, not business event ID |
| **contentType** | Set only when matching the actual body sent | Claiming JSON on an unserialized object breaks adapters |

Default overwrite behavior **varies by component** and API overload. Check **HeaderEnricherSpec**/**ContentEnricher** in your Spring Integration version; when existing headers must not be overwritten, configure explicitly and test with pre-populated headers.

Once an input business key is validated, you can standardize a header name while still keeping **business id** inside the payload. Crossing brokers or rebuilding messages can generate a fresh message **id**; never treat the technical `id` header as an idempotency guarantee.

### 4.3. When to Use HeaderEnricher vs. MessageBuilder?

**MessageBuilder** makes sense inside Java code constructing an initial message:

~~~java
Message<OrderDraft> message = MessageBuilder
        .withPayload(order)
        .setHeader("sourceSystem", "order-connector")
        .setHeader("flowVersion", "2")
        .build();
~~~

**HeaderEnricher** shines mid-way inside an **IntegrationFlow**, declaring metadata enrichment as a distinct, testable, observable, and reusable step. For complex conditionals, heavy validation, or external service calls to compute headers, prefer a dedicated service/transformer over unwieldy lambdas.

## 5. Technical Metadata and Special Headers

Spring Integration relies on several framework headers to coordinate flows:

| Header | Typical Use | Risk if Modified Arbitrarily |
| --- | --- | --- |
| **MessageHeaders.ID** | Identifies a single message in the framework | Not stable like a business event ID |
| **MessageHeaders.TIMESTAMP** | Message creation timestamp | Does not replace original event occurrence time |
| **IntegrationMessageHeaderAccessor.CORRELATION_ID** | Links group parts or request/reply messages | May merge unrelated groups on collision |
| **SEQUENCE_NUMBER / SEQUENCE_SIZE** | Splitter/aggregator group membership | Wrong order/count stalls or miscombines groups |
| **MessageHeaders.REPLY_CHANNEL** | Destination for gateway replies | Corrupting it leaves callers timing out |
| **MessageHeaders.ERROR_CHANNEL** | Destination for `ErrorMessage` routing | Corrupting it misroutes or drops errors |
| **routingSlip** | Dynamic list of next-hop channels | Must be trusted; prevents routing to unauthorized channels |
| **priority** | Priority if channel/adapter supports it | Not automatically honored or preserved by every broker |

Avoid reusing framework header names like **id**, **replyChannel**, **errorChannel**, or **correlationId** for custom meanings unless you explicitly intend to drive Spring Integration semantics.

Use a clear namespace convention for tracing/correlation:

~~~text
businessEventId  = source-issued business ID, stable across replays
sourceSystem     = set by trusted adapter
flowVersion      = internal contract version
correlationId    = traces request/batch relationships per convention
retryAttempt     = explicitly defined delivery/attempt state
tenantId         = authenticated and carried across protected boundaries
~~~

### Header Channel Registry When Messages Persist or Cross Brokers

**replyChannel** and **errorChannel** headers can hold in-memory **MessageChannel** references, which are not serializable into JSON/JMS/Kafka messages. Spring Integration provides **header channels to string / HeaderChannelRegistry** to map channel references to time-limited string tokens across certain asynchronous boundaries.

Use it only when reply/error paths genuinely must survive persistent channels or adapters. Set a TTL exceeding the full round-trip so entries do not expire before replies return. **Never treat registry tokens as globally shareable reply addresses across separate applications or deployments**; design distributed correlation and reply contracts explicitly.

## 6. How Does a Content Enricher Augment the Payload?

**ContentEnricher** (also called **payload enricher**) sets properties on the original payload. When external data is needed, it sends a request to **requestChannel**, **waits for a reply**, and evaluates expressions on that reply to populate target payload fields or headers.

~~~mermaid
sequenceDiagram
    participant O as Order Flow
    participant E as ContentEnricher
    participant L as Customer Lookup Handler
    participant C as Customer DB / Cache / HTTP
    O->>E: OrderDraft(customerId=C-44)
    E->>L: request payload = C-44
    L->>C: lookup customer C-44
    C-->>L: CustomerProfile(gold)
    L-->>E: reply CustomerProfile
    E->>E: setCustomer(profile)
    E-->>O: OrderDraft enriched with customer
~~~

Key mechanics:

1. The request sent to the lookup channel can carry only **part of the original payload** (e.g., `customerId`) via **requestPayloadExpression**.
2. The reply can be a brand-new message; the content enricher uses the **reply message as root** when evaluating **propertyExpression**.
3. The **original payload** is augmented; it is not replaced wholesale by the reply payload. If you want a completely different DTO, a **transformer** is often better.
4. A request channel is optional: static values or local expressions can enrich directly within the flow.

### 6.1. Illustrative Data Model

Example using a JavaBean with setters so Spring Integration can assign properties:

~~~java
public class OrderDraft {
    private String orderId;
    private String customerId;
    private String tenantId;
    private long amount;
    private CustomerProfile customer;

    public OrderDraft() {}

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public long getAmount() { return amount; }
    public void setAmount(long amount) { this.amount = amount; }

    public CustomerProfile getCustomer() { return customer; }
    public void setCustomer(CustomerProfile customer) {
        this.customer = customer;
    }
}

public record CustomerProfile(
        String customerId, String tier, boolean active) {
}
~~~

The **customer** field holds business enrichment data; **sourceSystem/flowVersion** belong in headers. For sensitive records, return only fields the flow genuinely requires; do not load full profiles containing addresses, national IDs, or payment details into every message unnecessarily.

### 6.2. Java DSL: Lookup via Request/Reply Channel

~~~java
@Configuration
public class OrderEnrichmentFlowConfiguration {

    @Bean
    IntegrationFlow enrichOrderFlow() {
        return IntegrationFlow.from("validatedOrders")
                .enrichHeaders(h -> h
                        .header("flowVersion", "2")
                        .header("sourceSystem", "order-connector")
                        .headerExpression("businessKey", "payload.orderId"))
                .enrich(e -> e
                        .requestChannel("customerLookupChannel")
                        .requestPayloadExpression("payload.customerId")
                        .propertyExpression("customer", "payload")
                        .replyTimeout(2_500L))
                .channel("enrichedOrders")
                .get();
    }
}
~~~

**Line-by-line walkthrough:**

- **IntegrationFlow.from("validatedOrders")** reads already-validated messages.
- **enrichHeaders(...)** sets metadata for downstream steps.
- **requestChannel("customerLookupChannel")** sends a request and awaits a reply via ContentEnricher's internal gateway mechanism.
- **requestPayloadExpression("payload.customerId")** sends only `customerId` for lookup instead of shipping the entire DTO. Relevant headers can still travel with the request per gateway rules.
- **propertyExpression("customer", "payload")** extracts the **reply message's payload** (`CustomerProfile`) and assigns it to the **customer** property of the original `OrderDraft`.
- **replyTimeout(2_500L)** bounds how long the enricher waits for a reply in milliseconds; it **does not replace** network timeouts on `WebClient`, JDBC, caches, or overall message deadlines.
- **channel("enrichedOrders")** sends the enriched message downstream. That channel must have a subscriber/consumer; on a `DirectChannel` with no subscriber, sending fails.

The lookup channel consumer can be declared with a Service Activator:

~~~java
@Component
public class CustomerLookupHandler {
    private final CustomerDirectory directory;

    public CustomerLookupHandler(CustomerDirectory directory) {
        this.directory = directory;
    }

    @ServiceActivator(inputChannel = "customerLookupChannel")
    public CustomerProfile lookup(String customerId) {
        return directory.requireCustomer(customerId);
    }
}
~~~

**CustomerDirectory** is an application service backed by a database, cache, or HTTP client. **requireCustomer** should return `CustomerProfile` or throw a clear domain exception when missing. Avoid casually returning null, which leaves flows without replies, triggers timeouts, or silently leaves fields unset without logging.

The configuration above wires **synchronous request/reply**; if the lookup uses a `DirectChannel`, blocking service calls run on the sender thread. To run asynchronously or bound load, design executors/channels/transactions/timeouts explicitly; never rely solely on `replyTimeout` thinking it cancels blocking I/O on time.

## 7. Content Enrichers Do Not Always Call External Systems

For fields derivable from the payload itself, static enrichment or expressions avoid an HTTP/DB round-trip:

~~~java
IntegrationFlow staticEnrichmentFlow() {
    return IntegrationFlow.from("ordersWithoutState")
            .enrich(e -> e
                    .property("processingState", "VALIDATED")
                    .propertyExpression("sourceAmount", "payload.amount"))
            .channel("ordersWithState")
            .get();
}
~~~

This example requires the target JavaBean to have matching **setProcessingState(...)** and **setSourceAmount(...)** setters; missing properties or incompatible types fail at runtime during mapping.

Often it is cleaner to construct a **new output DTO** instead of mutating the original payload. In that case, a **transformer** expresses intent better:

~~~java
public record EnrichedOrder(
        String orderId,
        String customerId,
        CustomerProfile customer,
        long amount) {
}

public EnrichedOrder combine(
        OrderDraft order, CustomerProfile profile) {
    return new EnrichedOrder(
            order.getOrderId(),
            order.getCustomerId(),
            profile,
            order.getAmount());
}
~~~

**ContentEnricher** fits "populate properties onto a target object." **Transformer** usually fits better when reshaping payloads, creating immutable records, converting JSON/XML/Avro formats, or versioning contracts. Never force an immutable record into a content enricher hoping reflection will mutate final fields.

## 8. Choosing the Right Place for Enrichment in a Flow

**HeaderEnricher**, **ContentEnricher**, **Transformer**, **Router**, **Filter**, and **ServiceActivator** each have distinct responsibilities:

| Component | Primary Job | Example |
| --- | --- | --- |
| Header enricher | Adds control/routing metadata | `sourceSystem`, `flowVersion`, verified tenant scope |
| Content enricher | Populates missing properties on original payload | Looks up customer tier, risk category, warehouse metadata |
| Transformer | Creates a new payload/Message representation | JSON to `OrderCreatedV2`, or `OrderDraft` to `EnrichedOrder` |
| Filter | Allows or drops messages by condition | Accepts only valid order amounts |
| Router | Selects the next channel | Priority lane by customer tier |
| Service activator | Executes logic, calls downstream, optionally replies | Customer lookup, persistence, outbound publish |

A typical sequence:

~~~text
Validate input & trust boundary
    → Header enrich: trusted metadata
    → Content enrich: supplementary data
    → Business validation: post-enrichment checks
    → Route: based on completed data
    → Handler/adapter: business side effects
~~~

**Not every flow must follow this exact order.** If upstream already provides sufficient fields or only one branch needs lookup data, **route early and enrich only the branch that needs it** to save latency and external calls. Conversely, if the router inspects a looked-up field, enrichment must precede that router.

## 9. Overwrites, Nulls, Mutable Objects, and Consistency

A content enricher assigns properties onto a target object, raising key design questions:

### 9.1. Already-Populated Fields

If **OrderDraft.customer** already holds a `CustomerProfile` and the enricher looks up a fresh customer, the existing value may be replaced depending on property mapping configuration. Ask:

- Which trusted source supplied the existing data?
- Is the customer service guaranteed to be fresher?
- May we overwrite data provided by upstream?
- If two sources conflict, which wins and what should be audited?

For headers, **overwrite** is an explicit option; for content enrichers, property assignment tends to **set the new value**. Test cases with pre-existing headers/properties instead of assuming both components share identical defaults.

### 9.2. Null Replies or Missing Fields

If customer lookup finds no matching ID:

- Throw **CustomerNotFoundException** to reject the business operation.
- Route to an **error flow** to record unhandled events or send to a DLQ per contract.
- If the contract permits guest orders, apply an **explicitly documented** default profile, logging reasons and fallback metrics.

Content enricher supports **null result expressions** for certain property/header mappings, yet you must never substitute fake defaults like a "premium customer" when a lookup fails. **Data not found**, **timeout**, and **configuration error** are three distinct conditions.

### 9.3. Mutable Payloads and Shared References

Inside one JVM, a message may be broadcast to multiple subscribers or pass through a publish-subscribe channel. Header enrichment creates new `MessageHeaders`, while a JavaBean payload often remains the **same object reference**.

~~~java
OrderDraft draft = new OrderDraft();
Message<OrderDraft> initial =
        MessageBuilder.withPayload(draft).build();

// Building a new Message does NOT deep-copy draft.
Message<OrderDraft> withHeader =
        MessageBuilder.fromMessage(initial)
                .setHeader("flowVersion", "2")
                .build();

assertSame(initial.getPayload(), withHeader.getPayload());
~~~

ContentEnricher offers a **shouldClonePayload** option for `Cloneable` payloads, which does not replace a broader immutability/deep-copy policy. Shallow clones still share nested mutable objects. Across concurrent branches, prefer **immutable DTOs + transformers producing new objects** or controlled copying to prevent race conditions.

## 10. Metadata Across HTTP, Databases, and Message Brokers

In practice, metadata crosses multiple boundaries:

~~~mermaid
flowchart LR
    A["HTTP request headers"] --> B["HTTP inbound gateway"]
    B --> C["Internal MessageHeaders"]
    C --> D["Content enricher / DB/HTTP lookup"]
    D --> E["Kafka/AMQP/JMS outbound adapter"]
    E --> F["Broker headers + payload"]
    F --> G["Consumer service"]
~~~

**Not all internal headers automatically cross adapters.** Header mappers, converters, and serialization policies govern which names and types survive.

| Boundary | What to Check |
| --- | --- |
| HTTP inbound | Which headers may map into `Message`? Are tenant, auth, and correlation verified? |
| Database | Is critical replay metadata persisted as business/outbox columns? |
| Kafka | Headers are `byte[]`/serialized; do consumers agree on names, encoding, and versions? |
| AMQP/RabbitMQ | Header mapper, content type, correlation ID, reply-to, and field types |
| JMS | Standard JMS headers and provider-supported property types; avoid non-portable names |
| Spring Integration persistent channel | Message serialization, header channel registry, restart recovery |
| Cache | Are keys scoped by tenant/business with sensible TTLs? Are lookup errors hidden as cache misses? |

Framework headers holding live objects like **replyChannel/errorChannel** cannot cross process boundaries directly. Across networks, establish explicit **reply destination + correlation key** contracts or transport-native request-reply mechanisms.

### Which Metadata Must Be Persisted Durably?

If the system requires post-crash **replay** or event **deduplication**:

- **businessEventId** should reside in the payload or durable outbox/inbox columns.
- **schemaVersion** should travel by controlled contract so consumers know how to decode.
- **sourceOccurredAt** is when the event happened at the source, distinct from **MessageHeaders.TIMESTAMP**.
- **tenantId** must be re-verified when crossing another trust boundary.
- **processingStatus/retryCount** belong in durable state tables rather than purely in-memory headers.

Spring Integration's **MetadataStore** persists key–value operational state and is **not the same as per-message `MessageHeaders`**. Setting a header `processed=true` does not mean a broker, database, or consumer committed anything.

## 11. Request/Reply Timeouts on Content Enrichers

When **ContentEnricher** uses a request channel, it acts like a gateway awaiting a reply, with two main gateway timeouts:

| Setting | Meaning | Should NOT Be Mistaken For |
| --- | --- | --- |
| **requestTimeout** | Limit when **sending the request** to a potentially blocking `MessageChannel` (e.g., full `QueueChannel`) | HTTP client connect/read timeout |
| **replyTimeout** | Limit waiting for a reply from the lookup branch during async waits | An absolute kill switch interrupting any blocking handler |
| **HTTP/WebClient timeout** | Client connect/read/response timeouts and reactive operators | `MessageChannel` communication timeout |
| **JDBC query timeout** | Driver/DB query or lock wait limit | Total content enrichment duration |
| **Business deadline** | Overall time budget of the request or message workflow | A single default property on every component |

Example:

~~~java
.enrich(e -> e
        .requestChannel("customerLookupChannel")
        .requestPayloadExpression("payload.customerId")
        .propertyExpression("customer", "payload")
        .requestTimeout(300L)
        .replyTimeout(2_500L))
~~~

**Crucial:** if `requestChannel` is a **DirectChannel** and lookup blocks on the sender thread, a slow HTTP/JDBC call holds that thread while the handler runs; **requestTimeout** will not interrupt it. Nor should **replyTimeout** be treated as a kill switch for synchronous calls. Prevent unbounded hangs by configuring timeouts on HTTP/JDBC clients directly, introducing async boundaries where appropriate, and tracking end-to-end deadlines.

### 11.1. Timeout After Side Effects Already Occurred

If enrichment is purely **GET customer**, retries carry lower risk than writes. Yet if the lookup branch updates a cache, calls a mutating service, or emits events, timeouts can occur **after the side effect committed** before the reply returned.

Never retry blindly just because the enricher reported a reply timeout. Whenever a lookup causes side effects, attach a business-defined **idempotency key** and verify outcomes before retrying.

### 11.2. Late Replies

When requests cross an `ExecutorChannel`, queue, or broker, replies may arrive **after the gateway timed out**. Understand your framework/adapter's **temporary reply channel**, correlation ID, and late-reply behavior. Never share one reply queue without correlation, and never treat stray late replies as new business requests.

When lookup latency is unpredictable, consider an **async enrichment architecture**:

~~~text
OrderCreated → store pending enrichment
  → request customer lookup (event/command)
  → CustomerProfile reply with correlation
  → join by durable key
  → enriched order → routing
~~~

This architecture adds complexity yet avoids holding threads open; it requires durable state, TTLs, timeouts, deduplication, and explicit recovery.

## 12. Error Handling, Fallbacks, and DLQ

Typical enrichment failures:

| Error | Example | Recommended Handling |
| --- | --- | --- |
| Invalid input schema/tenant | Missing `customerId`, unauthorized tenant | Reject before enrichment; skip lookup |
| Data not found | Non-existent customer ID | Business rejection or contracted fallback |
| Transient timeout | Slow Customer DB/HTTP | Bounded retry with backoff and deadline |
| Downstream returns 429/503 | Rate limited or unavailable | Backoff per `Retry-After`/quota; avoid retry storms |
| Invalid reply schema | Lookup returns unexpected object | Contract error, alert, fix mapping |
| Property mapping failure | Missing JavaBean setter or wrong type | Fix config/code; do not retry infinitely |
| Header conflict | `correlationId`/`tenantId` overwritten accidentally | Audit trust boundaries and overwrite policy |
| DLQ publish failure | Handler failed and adapter failed to send to DLQ | Never ACK blindly; needs recovery/reconciliation |

Intentional error-handling flow:

1. Validate **before** enrichment so non-retryable errors fail early.
2. Route lookup exceptions to an **error channel** or container error handler matching the adapter type.
3. Use fallbacks only when the business accepts "incomplete data" with tracking/backfill.
4. Under at-least-once broker delivery, **every side effect** downstream of enrichment must be deduplicated.
5. Never catch an Exception and attach `enrichmentSucceeded=true` or return a fabricated default profile that misleads downstream logic.

`ContentEnricher` can configure an **errorChannel** for request-branch errors to produce fallback objects via framework mechanisms; however, an `ErrorMessage` reaching an error channel does not automatically mean the error is "resolved." The error consumer/flow must return a valid reply or route final failures to a DLQ per contract.

## 13. Performance, Caching, Batching, and Concurrency

A single innocent-looking content enrichment can trigger **N+1 network calls**: every order hits customer service even when many orders belong to the same customer.

Load example:

~~~text
2,000 orders/second
× 1 customer lookup/order
= 2,000 lookup requests/second
~~~

If each lookup takes p95 = 120 ms, synchronous flow latency jumps by at least that amount; across replicas, total concurrency and pools must match downstream capacity. Never size concurrency purely by the enrichment service's CPU when downstream is the bottleneck.

Mitigations:

- **Cache by `customerId + tenant`**, with TTL aligned to profile volatility and consistency rules.
- **Batch lookup** when upstream contracts allow; group by tenant or bucket while handling partial failures and ordering.
- **Conditional enrichment**: look up customer data only when the chosen router/handler needs it.
- **Pre-enrich at source** when upstream events can legitimately embed a valid snapshot under data policies.
- **Bound concurrent requests**, connection pools, rate limiters, and retry budgets.
- **Forbid unbounded queues** accumulating hundreds of thousands of enrichment requests while downstream is down.

### Caching Makes Enriched Data Stale

If a customer's tier changes between order placement and order processing, priority routing could differ. Define:

1. Use the **tier at order placement** or the latest tier at processing time?
2. How are cache entries versioned or invalidated?
3. When a consumer replays an old event, may it re-enrich against current live data?
4. Should the system snapshot enriched data inside the outbox/event?

Replaying an event can yield different outcomes if it always re-queries mutable live state. For **deterministic replay**, store a snapshot of critical enriched fields or versioned lookup records per contract.

## 14. Tracing and Measuring Enrichment Quality

Instrumentation should distinguish **message counts**, **lookup calls**, **cache hits/misses**, and **retries**:

| Suggested Metric | Unit / Measurement Point |
| --- | --- |
| **app.integration.enrichment.received** | Deliveries entering enrichment |
| **app.integration.enrichment.lookup.started** | Actual lookup invocations |
| **app.integration.enrichment.lookup.duration** | Timer for DB/HTTP/cache lookups |
| **app.integration.enrichment.lookup.outcome** | `success` / `not_found` / `timeout` / `failure` |
| **app.integration.enrichment.fallback** | Fallback executions by reason |
| **app.integration.enrichment.completed** | Successfully enriched messages forwarded |
| **app.integration.enrichment.failed** | Terminal failures before downstream |
| **app.integration.enrichment.cache.hit** | Cache hits/misses if cached |
| **app.integration.enrichment.retry.started** | Actually started retry attempts, not merely scheduled |

These are **recommended application metric conventions**, not built-in Spring Integration names. Spring Boot Actuator, Micrometer, and Spring Integration Observation instrument HTTP clients/handlers/channels; domain outcomes must be added intentionally.

Never use high-cardinality **orderId**, **customerId**, **requestId**, **raw tenantId**, or error messages as meter tags. Keep tags bounded like **flow**, **lookup_source**, **outcome**, **error_kind**. Place business IDs in access-controlled logs/traces if permitted by policy.

Typical trace:

~~~text
HTTP inbound order
  → validateOrder
  → enrichHeaders(flowVersion=2)
  → contentEnricher
      → customerLookup
          → cache miss
          → GET customer API (120 ms)
      ← CustomerProfile
  → route(priority)
  → outbound publisher
~~~

Crucially, separate **lookup failures** from **routing or outbound failures**. Lumping everything into **enrichment.failed** hides which downstream system needs attention.

## 15. Testing Header and Content Enrichers

### 15.1. Unit Testing Header Expressions

Extract header computation into pure Java helpers for easy unit testing:

~~~java
public final class OrderMetadata {
    public static String businessKey(OrderDraft order) {
        if (order.getOrderId() == null ||
                order.getOrderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        return order.getOrderId();
    }
}
~~~

Test with valid and invalid payloads:

~~~java
@Test
void businessKeyDoesNotDependOnTransportMessageId() {
    OrderDraft order = new OrderDraft();
    order.setOrderId("O-172");

    assertEquals("O-172", OrderMetadata.businessKey(order));
}
~~~

Unit testing a helper function **does not prove** the header enricher is wired to the right channel or propagates headers across gateways; flow tests must inspect actual messages.

### 15.2. Flow Test with Stubbed Lookup Reply

Create a test context containing two integration flows:

~~~java
@TestConfiguration
class EnrichmentTestConfiguration {

    @Bean
    IntegrationFlow customerLookupTestFlow() {
        return IntegrationFlow.from("customerLookupChannel")
                .handle(String.class, (customerId, headers) ->
                        new CustomerProfile(customerId, "GOLD", true))
                .get();
    }

    @Bean
    IntegrationFlow enrichOrderUnderTest() {
        return IntegrationFlow.from("testOrdersIn")
                .enrichHeaders(h -> h.header("flowVersion", "2"))
                .enrich(e -> e
                        .requestChannel("customerLookupChannel")
                        .requestPayloadExpression("payload.customerId")
                        .propertyExpression("customer", "payload")
                        .replyTimeout(1_000L))
                .channel("testOrdersOut")
                .get();
    }

    @Bean("testOrdersOut")
    QueueChannel testOrdersOut() {
        return new QueueChannel();
    }
}
~~~

Tests send to the input channel and poll the output channel:

~~~java
@Autowired
@Qualifier("testOrdersIn")
MessageChannel input;

@Autowired
@Qualifier("testOrdersOut")
PollableChannel output;

@Test
void contentEnricherAddsCustomerAndPreservesMetadata() {
    OrderDraft draft = new OrderDraft();
    draft.setOrderId("O-172");
    draft.setCustomerId("C-44");

    Message<OrderDraft> source =
            MessageBuilder.withPayload(draft)
                    .setHeader("correlationId", "req-9f1")
                    .build();

    assertTrue(input.send(source));

    Message<?> reply = output.receive(2_000);
    assertNotNull(reply);
    assertEquals("2", reply.getHeaders().get("flowVersion"));
    assertEquals("req-9f1", reply.getHeaders().get("correlationId"));

    OrderDraft enriched = (OrderDraft) reply.getPayload();
    assertEquals("C-44", enriched.getCustomer().customerId());
    assertEquals("GOLD", enriched.getCustomer().tier());
}
~~~

Imports for JUnit 5, Spring Integration DSL, Spring Messaging, and annotations are omitted. Beans run inside a **Spring test context**; `testOrdersIn` is auto-registered by `IntegrationFlow`. Because the stub lookup runs synchronously over a `DirectChannel`, results return fast; write separate tests with `ExecutorChannel`/real HTTP to test asynchronous timeouts.

### 15.3. Additional Scenarios to Test

| Test case | What to verify |
| --- | --- |
| Missing `orderId`/`customerId` | Validation blocks lookup; no invalid event emitted |
| Pre-existing header | Overwrite policy works; `correlationId` preserved |
| Lookup returns GOLD / STANDARD | Accurate content mapping; router picks right branch |
| Lookup not found | Classified as business not-found; no silent fake profile |
| Lookup throws HTTP timeout | Error channel/retry works; not misclassified as missing customer |
| Late lookup reply | Never attaches to next order or duplicates side effects |
| Immutable record payload | Transformer builds new object instead of failing setters |
| Two branches share JavaBean ref | No unintended mutation or race |
| Adapter sends via Kafka/JMS/AMQP | Only allowlisted headers with valid encoding are mapped |
| Replay old event | Consistent enrichment by version/snapshot |
| Multiple enrichment retries | Attempt metrics differ from delivery; no duplicate side effects |
| Sensitive metadata | Never leaks into broker headers, logs, or traces |

For HTTP/broker integration flows, real tests need **MockWebServer/WireMock** or broker Testcontainers; mocking a plain service method never verifies timeouts, header mapping, or wire serialization.

## 16. Common Misconceptions

**"Header enricher and content enricher differ only in name."** False. Header enrichers update **`MessageHeaders`**; content enrichers augment the **payload** and can invoke request/reply flows to look up data.

**"Putting a customer profile in headers is the same as in the payload."** Doing so can leak data via brokers/logs, cause serialization issues, and mix transport metadata with business contracts. Customer data used by domain logic belongs in the payload/DTO.

**"ContentEnricher always requires an HTTP request."** False. You can enrich from literals or expressions inline; a request channel is optional.

**"requestPayloadExpression sends a single field, so other headers automatically vanish."** Normally the request message retains headers copied by the gateway mechanism. To restrict headers crossing a boundary, configure an explicit header mapper/filter.

**"replyTimeout bounds every HTTP/JDBC call underneath."** False. It bounds gateway reply waiting under applicable conditions; you must configure timeouts on clients/drivers and deadlines in services.

**"Spring's `id` header is a business `eventId`."** False. Message `id` can regenerate whenever a message is rebuilt; `eventId` must be defined by the business source.

**"Adding `correlationId` provides idempotency automatically."** Correlation links a flow; idempotency requires persistent state and rules blocking duplicate side effects.

**"Because `MessageHeaders` are immutable, content enrichers cannot cause races."** Headers and payloads are separate; mutable payloads can still race when multiple branches share a reference.

**"Enabling retries after timeouts is always safe."** Safe for pure reads, yet if lookups have side effects or retries replay an already-committed downstream step, idempotency is mandatory.

**"If a flow has `errorChannel`, failed messages automatically enter a DLQ."** Error channels handle errors inside the application; moving to a DLQ requires dedicated adapters/publishers or broker policies.

**"All Spring Integration headers pass across Kafka/JMS/HTTP."** Each adapter has its own header mapper and conversion rules, especially for channel references, `contentType`, and non-serializable values.

## 17. Practical Implementation Checklist

1. List which fields belong to the **business payload** and which are **metadata**.
2. Validate tenant/contract at ingress before using headers for authorization or lookups.
3. Use **enrichHeaders** for lightweight control metadata; use **content enrichers** for missing payload properties.
4. When reshaping DTOs or working with immutable records, prefer an explicit transformer.
5. Define overwrite, null, and fallback policies; never let lookup errors masquerade as valid data.
6. Namespace custom headers cleanly and avoid accidentally altering `replyChannel`/`errorChannel`/`id`/`timestamp`.
7. Configure request/reply timeouts separately from client I/O timeouts and define an overall deadline.
8. When caching, define consistency, TTLs, tenant scoping, and deterministic replay behavior.
9. Across broker/HTTP boundaries, audit header mappers, serialization, correlation, and credential isolation.
10. Enforce idempotency keys and durable state at side-effect boundaries; in-memory metadata never guarantees exactly-once.
11. Bound concurrency, queue depth, and retries so enrichment cannot overwhelm customer service or downstream systems.
12. Monitor lookup counts, cache hit rates, p95/p99 latency, timeouts, `error_kind`, fallbacks, and final outcomes.
13. Test payloads/headers, pre-existing values, slow replies, mapping errors, and real adapters.

**Conclusion:** **HeaderEnricher** enriches transport/orchestration context; **ContentEnricher** enriches business data, often via request/reply. Respecting metadata boundaries, keeping data replayable, and controlling errors/timeouts keeps Spring Boot integration flows safe, testable, and observable.

## References

- [Spring Integration Reference — Content Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): header enricher, payload enricher, request/reply, property/header expressions, and Java DSL.
- [Spring Integration API — EnricherSpec (6.4)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/EnricherSpec.html): `requestChannel`, `requestPayloadExpression`, `propertyExpression`, `requestTimeout`, and `replyTimeout`.
- [Spring Integration API — ContentEnricher](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ContentEnricher.html): augmenting properties/headers, gateway mechanics, and payload cloning.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): `Message` structure, immutable headers, and framework metadata.
- [Spring Integration Reference — Header Channel Registry](https://docs.spring.io/spring-integration/reference/message-routing.html): considerations for `replyChannel`/`errorChannel` across persistent/asynchronous boundaries.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): defining `IntegrationFlow` and endpoint components.
- [Spring Framework — Integration with Spring Messaging](https://docs.spring.io/spring-framework/reference/integration.html): Spring Messaging model and integration applications.
