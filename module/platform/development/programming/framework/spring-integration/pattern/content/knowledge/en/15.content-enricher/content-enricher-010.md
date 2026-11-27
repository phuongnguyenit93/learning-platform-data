# Correlation Between the Original Message and the Enrichment Request

## 1. Why Must a Content Enricher Maintain the Link to the Original Message?

A sales system receives an `OrderCreated` event containing `eventId`, `orderId`, and `customerId`. Before choosing a promotion policy or routing the order to the right branch, the system must add the **customer tier** from a Customer Profile service.

~~~text
Order A: eventId=EV-A, orderId=O-101, customerId=C-01
Order B: eventId=EV-B, orderId=O-102, customerId=C-02

Enrichment request A: lookup C-01
Enrichment request B: lookup C-02

Reply B: CustomerProfile(C-02, STANDARD) arrives first
Reply A: CustomerProfile(C-01, GOLD) arrives later
~~~

If the system matches solely by **response arrival order**, Reply B could be attached to Order A by mistake. If it matches by `MessageHeaders.ID`, that value can change when the framework creates a new message or crosses a broker. If it copies every header blindly, the reply might even overwrite `correlationId`, `replyChannel`, or the original message's tenant metadata.

**Correlation between the original message and the enrichment request** is the ability to know **which lookup request belongs to which message**, ensuring returned data is applied to the exact right entity, tenant, and execution—even amid concurrency, timeouts, retries, duplicates, or out-of-order replies.

In **Spring Integration**, a **Content Enricher** sends a request to `requestChannel` and awaits a reply using an internal gateway model; the reply populates information on the **original message's target payload**. On standard internal request–reply paths, the framework correlates replies with waiting invocations via the `replyChannel` mechanism. However, when requests cross Kafka/AMQP/async HTTP or need crash recovery across restarts, the system must still design **business correlation IDs and durable pending state** for end-to-end guarantees.

This article belongs to the **Content enricher** chapter of the **SPRING_INTEGRATION_PATTERN** module. The learning objective is practicing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows combining **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing every processing branch.

**After this lesson, you will be able to** trace the lifecycle of original message/request/reply, separate ID types, configure request–reply Enrichers, prevent cross-order profile mix-ups, handle late/duplicate replies, recognize JVM-vs-broker boundaries, and test correlation under concurrency.

## 2. Three Artifacts in One Enrichment

To avoid confusion, name the three message roles:

| Artifact | Illustrative Payload | Role |
|---|---|---|
| **Original message (M0)** | `OrderDraft(O-101, C-01)` | Carries data needing enrichment and business context |
| **Enrichment request (Q1)** | `customerId=C-01` | Lookup request for supplementary data at another service |
| **Enrichment reply (R1)** | `CustomerProfile(C-01, GOLD)` | Lookup result applied to the matching M0 |
| **Enriched output (M1)** | `OrderDraft(O-101, C-01, GOLD)` | Message after applying R1 data onto M0's payload |

The logical relationship is:

\[
M_1 = \operatorname{enrich}(M_0,\ \operatorname{lookup}(Q_1(M_0)))
\]

Here `Q1(M0)` means the request constructed from the original message, and `lookup()` returns the supplementary data. The core rule is **R1 must belong to Q1 and Q1 must belong to M0**—not merely because R1 happened to arrive first or share the same payload type.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant E as Content Enricher
    participant L as Lookup handler
    participant O as Downstream
    P->>E: M0 = OrderDraft(O-101,C-01)
    E->>L: Q1 = lookup(C-01), internal replyChannel
    L-->>E: R1 = CustomerProfile(C-01,GOLD)
    Note over E: Match reply to the right waiting call
    E->>O: M1 = OrderDraft(..., profile=GOLD)
~~~

Content Enricher is a variant of **Transformer**, yet differs from a standalone Transformer in that it typically needs data absent from the current payload. It executes a **request–reply subflow** to obtain data before applying property/header expressions.

## 3. Distinguishing ID Types and Headers Used for Correlation

No single ID fits every purpose:

| Field | Owner | Purpose | Suitable as Durable Request Correlation? |
|---|---|---|---|
| `MessageHeaders.ID` | Spring Messaging | Identifies a single message object | **No**, messages can be recreated |
| `eventId` | Producer / business contract | Idempotency and event tracing | Usable as reference, though one event may trigger multiple lookups |
| `orderId` | Domain | Ties to an order | Insufficient to distinguish multiple requests or attempts |
| `customerId` | Domain | Lookup data key | Insufficient to distinguish orders or tenants |
| `correlationId` | Integration flow / aggregator | Groups messages belonging to a group/process | Use per flow semantics; never overwrite arbitrarily |
| `enrichmentRequestId` | Enrichment coordinator | Pairs one request with exactly one reply | **Suitable** across brokers or durable pending state |
| `traceId` | Tracing framework | Observes call chains across services | Does not replace authorization or request IDs |
| `replyChannel` | Gateway/Enricher runtime | Return address inside the flow | **Not** an ID to persist or serialize arbitrarily |

In a message carrying both `eventId` and `enrichmentRequestId`, we can express: "enrichment attempt `ER-5` belongs to event `EV-A`." If the same event must look up **Customer** and **Fraud**, each operation needs its own correlation—such as `ER-5/customer` and `ER-5/fraud` or two distinct IDs linked to the shared business event.

Never set `correlationId` equal to `customerId` simply because the lookup is by customer. Multiple orders for the same customer can run concurrently; they must never share one pending reply slot just because their lookup keys match.

**Principle:** separate **business identity**, **processing/request identity**, **trace context**, and **routing/reply channel semantics**. Link them in logs or a pending-request table, but never conflate them.

## 4. Request–Reply Enricher in Spring Integration

Per Spring Integration documentation, when a Content Enricher specifies `requestChannel`, it acts much like a **gateway**: sending a message to the request channel, awaiting a reply, and applying the reply onto the original payload. If no explicit `replyChannel` is declared, the framework typically uses a per-request **temporary reply channel** to match the response to the waiting call.

~~~mermaid
flowchart TB
    ORIG["M0: OrderDraft + original headers"] --> EN["ContentEnricher"]
    EN -->|"Q1: request payload + headers"| REQ["customer.lookup.requests"]
    REQ --> LOOK["Customer Lookup"]
    LOOK -->|"R1: lookup reply"| TEMP["Temporary reply channel"]
    TEMP --> EN
    EN -->|"M1: original payload + profile"| NEXT["orders.enriched"]
~~~

When `requestPayloadExpression` is configured, the Enricher can send **only part of the payload** as the request, such as `payload.customerId`. Crucially: **shrinking the request payload does not automatically strip `MessageHeaders`**. As documented in Spring Integration, the request message may still carry all headers from the original message, including metadata that should not leak to external services.

Consequences:

1. The Enricher must hold **M0**'s context while waiting for **R1**.
2. The lookup reply becomes the **evaluation root for property/header expressions**; `payload.tier` references reply data, not automatically M0.
3. Data inside Q1 does not have to be all of M0.
4. For ordinary in-process synchronous request–reply, you do not need a custom external correlation map just to link Q1/R1 to the waiting call.
5. When Q1 crosses a broker or external boundary, design header serialization, return addresses, and deadlines; never assume an in-JVM temporary reply channel survives across process boundaries.

**Never repurpose the `replyChannel` header to store a business event ID.** It serves Spring Messaging's reply mechanism; overwriting it with a non-channel string can drop replies or cause timeouts.

## 5. A Clear Domain Model for the Practice Example

Suppose an `OrderDraft` is missing `CustomerProfile`:

~~~java
record CustomerProfile(
    String customerId,
    String tier
) {}

class OrderDraft {
    private final String eventId;
    private final String orderId;
    private final String customerId;

    private CustomerProfile customerProfile;

    public OrderDraft(String eventId, String orderId,
                      String customerId) {
        this.eventId = eventId;
        this.orderId = orderId;
        this.customerId = customerId;
    }

    public String getEventId() {
        return eventId;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public CustomerProfile getCustomerProfile() {
        return customerProfile;
    }

    public void setCustomerProfile(CustomerProfile customerProfile) {
        this.customerProfile = customerProfile;
    }
}
~~~

These are **illustrative types** to place in appropriate Java files when implementing, not source files written into the module during STEP 4. `OrderDraft` is a JavaBean with a setter because Payload Enricher supports setting properties on the target payload. `CustomerProfile` is an immutable record returned from the lookup service.

Sample input:

~~~text
M0.payload = OrderDraft(
  eventId=EV-101,
  orderId=O-101,
  customerId=C-01,
  customerProfile=null
)
M0.headers.businessEventId = EV-101
M0.headers.traceId = TRACE-101
~~~

The goal is not replacing the whole message with a `CustomerProfile`, but getting **M1 with the original `OrderDraft` fields and its `customerProfile` property populated**. That is the difference between a Content Enricher and a Transformer unconditionally replacing the payload with lookup output.

**Note on mutability:** the example uses a setter to explain Content Enricher, yet in production, if the same payload instance is shared via `PublishSubscribeChannel` or across threads, mutating the object in place can cause races or side effects. Consider cloning/copying the payload before enriching or using a Transformer that builds an **immutable result** per system requirements. `shouldClonePayload` helps only when the payload satisfies appropriate cloning rules; never assume every DTO is deep-cloned automatically.

## 6. Java DSL Configuration: Fetching Profile and Enriching the Original Payload

Spring Integration Java DSL provides `enrich(...)`; `EnricherSpec` offers options such as `requestChannel`, `requestPayloadExpression`, `propertyExpression`, `requestTimeout`, and `replyTimeout`.

~~~java
@Configuration
@EnableIntegration
class OrderEnrichmentFlow {

    @Bean
    IntegrationFlow enrichOrderWithCustomerProfile() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderDraft.class,
                order -> order.getCustomerId() != null
                    && !order.getCustomerId().isBlank(),
                f -> f.throwExceptionOnRejection(true))
            .enrich(e -> e
                .requestChannel("customer.lookup.requests")
                .requestPayloadExpression("payload.customerId")
                .propertyExpression("customerProfile", "payload")
                .requestTimeout(2_000L)
                .replyTimeout(3_000L))
            .channel("orders.enriched")
            .get();
    }
}
~~~

A **synchronous** lookup handler for the demo:

~~~java
@MessageEndpoint
class CustomerLookupHandler {

    @ServiceActivator(
        inputChannel = "customer.lookup.requests")
    public CustomerProfile lookup(String customerId) {
        return switch (customerId) {
            case "C-01" -> new CustomerProfile("C-01", "GOLD");
            case "C-02" -> new CustomerProfile("C-02", "STANDARD");
            default -> throw new IllegalArgumentException(
                "UNKNOWN_CUSTOMER");
        };
    }
}
~~~

This is an **example flow** with imports omitted. The Filter rejects null/blank `customerId` before constructing Q1; real applications also check authorization and other mandatory domain fields. Input `orders.in` expects a properly typed `OrderDraft`; `orders.enriched` needs a real consumer or a `QueueChannel` in tests. The lookup service is simulated with a `switch`; real systems call repositories, HTTP, databases, or external services with dedicated timeouts and policies.

Reading each setting:

- `requestChannel("customer.lookup.requests")` specifies where Q1 is sent.
- `requestPayloadExpression("payload.customerId")` builds Q1's payload as the **customer ID**, not the whole `OrderDraft`.
- `propertyExpression("customerProfile", "payload")` reads **R1's payload** and assigns it to `customerProfile` on **M0**.
- `requestTimeout` bounds send waits when sending can block; `replyTimeout` bounds reply waiting per the corresponding API/configuration. Do not treat them as end-to-end business timeouts.
- Leaving `replyChannel` unset lets the Enricher's internal gateway manage a per-request reply channel.

After receiving `CustomerProfile("C-01","GOLD")`, M1 remains the `OrderDraft` for `EV-101/O-101` now carrying the matching profile. **Never turn the lookup result into the flow's entire new payload** unless that is genuinely the contract you want.

## 7. Equivalent XML Example and Reply Meaning

For projects using XML namespaces, Payload Enricher looks like:

~~~xml
<int:enricher input-channel="orders.in"
              output-channel="orders.enriched"
              request-channel="customer.lookup.requests"
              request-payload-expression="payload.customerId">
    <int:property name="customerProfile" expression="payload"/>
</int:enricher>
~~~

Per Spring Integration documentation, a `property` expression is evaluated with the **reply message from the request flow** as its root when `request-channel` is configured. Hence `expression="payload"` here refers to `CustomerProfile` in the reply and sets it on the original `OrderDraft` property.

Declaring an explicit `reply-channel` is unnecessary for this synchronous use case; the Enricher creates a temporary reply channel. If you configure an explicit reply channel, ensure it has proper semantics for **concurrent requests**, never turning a shared queue into a pool where callers steal each other's replies.

The XML and Java DSL examples are **two alternative forms**; do not register both on the same input simultaneously in a sample app unless competing consumers are intentional.

## 8. Internal Reply Routing Is Not Business Correlation

An enrichment request has two kinds of links:

**Temporary coordination link** — Enricher sends Q1, and a handler returns R1 to the managed `replyChannel` so Enricher resumes M0. In an in-process request–reply path, this usually suffices to keep concurrent calls from grabbing each other's replies.

**Business and traceability link** — M0 belongs to `eventId=EV-101` and executes `CUSTOMER_LOOKUP` under a known policy/version; it must correlate across logs, metrics, errors, and post-restart replays. Those concerns are not solved automatically by an in-memory temporary reply channel object.

~~~mermaid
flowchart LR
    O["M0: eventId=EV-101"] --> E["Enricher invocation"]
    E --> Q["Q1: customerId=C-01"]
    Q --> L["Lookup"]
    L --> R["R1: CustomerProfile"]
    R --> E
    E --> M["M1: original + profile"]
    O -.->|"Business context"| B["eventId / tenant / trace"]
    Q -.->|"Operation context"| B
    R -.->|"Lookup outcome"| B
~~~

If you only need a Content Enricher within one JVM without long-running business state, **do not reinvent a concurrent request→reply map outside the framework** just to replace the temporary channel; you will introduce races, memory leaks, and timeout bugs.

Conversely, if a lookup may return hours later over a broker or an independent HTTP callback, use an explicit **correlation store** or coordinator; an in-memory temporary reply channel is not durable state.

## 9. Preserving Original Context When the Request Payload Is a Single Field

Sending only `customerId` as Q1's payload helps because the lookup service does not need the entire order. However, **the request message may still carry headers from the original message**.

Suppose the publisher sends:

~~~java
OrderDraft order =
    new OrderDraft("EV-101", "O-101", "C-01");

Message<OrderDraft> original = MessageBuilder
    .withPayload(order)
    .setHeader("businessEventId", order.getEventId())
    .setHeader("traceId", "trace-101")
    .build();
~~~

Under the Content Enricher contract, when `requestPayloadExpression` is used, the request payload sent to lookup may be just `"C-01"`, while headers `businessEventId` and `traceId` can still reach the request flow. The handler can observe them:

~~~java
@ServiceActivator(inputChannel = "customer.lookup.requests")
public CustomerProfile lookup(Message<String> request) {
    String customerId = request.getPayload();
    Object eventId = request.getHeaders().get("businessEventId");
    // Use eventId for tracing/logging per policy, never for authorization.
    return customerRepository.findProfile(customerId);
}
~~~

This is an **alternative variant** of the lookup handler from Section 6; do not register two competing handlers on the same channel just for illustration. `customerRepository` is an application dependency you implement and inject.

**Security warning:** inherited headers are not automatically trustworthy. If an inbound adapter allows clients to supply `tenantId`, `isAdmin`, `verifiedCustomerId`, or authorization metadata, copying headers to the lookup **does not validate them**. Trusted identity and tenant must be derived at an authenticated boundary or re-verified in the receiving service.

**Leakage warning:** never copy all `MessageHeaders` out to HTTP/Kafka/AMQP. Specifically, `replyChannel` and `errorChannel` may be internal non-serializable objects; tokens, cookies, security headers, and PII must never propagate blindly across transports.

## 10. When Two Concurrent Requests Return Replies Out of Order

An essential test runs two requests nearly simultaneously while their lookup results return in **reverse order**:

~~~mermaid
sequenceDiagram
    participant PA as Publisher A
    participant PB as Publisher B
    participant EA as Enricher call A
    participant EB as Enricher call B
    participant L as Lookup service
    PA->>EA: M0-A (C-01)
    PB->>EB: M0-B (C-02)
    EA->>L: Q-A
    EB->>L: Q-B
    L-->>EB: R-B (arrives quickly)
    EB-->>PB: M1-B (STANDARD)
    Note over L: Q-A still waiting
    L-->>EA: R-A (arrives late)
    EA-->>PA: M1-A (GOLD)
~~~

Replies are never matched by "first come, first served." On **Content Enricher's request–reply path** with framework-managed per-call reply channels, each execution stays bound to its own invocation.

Still, test this against your real configuration—especially if:

- Developers replaced the temporary reply channel with a **shared queue** lacking a selector/correlation mechanism.
- Requests traverse an outbound gateway and broker where replies become new messages.
- The lookup service replies via another consumer or after a restart.
- A handler constructs a new `Message<?>` manually and drops the headers used to return to the reply channel.

**Concurrent calls do not need to finish in order**, yet they must preserve **exact request–reply pairing**. That is the primary invariant of correlation.

## 11. Business Request IDs When Enrichment Crosses a Broker

When querying over Kafka or AMQP, the request may leave process A, execute in process B, and return to process A on another consumer. An explicit correlation contract is then mandatory:

~~~java
record CustomerLookupRequest(
    String enrichmentRequestId,
    String eventId,
    String orderId,
    String tenantId,
    String customerId
) {}

record CustomerLookupReply(
    String enrichmentRequestId,
    String tenantId,
    String customerId,
    String tier,
    String outcome
) {}
~~~

**This is an application wire-level contract**, not auto-generated framework classes. `enrichmentRequestId` identifies a logical lookup. For retries, declare the policy explicitly: keep the same ID for idempotent retries or attach a distinct attempt ID to one logical request ID. Never mint a fresh `UUID` per retry and lose the link to prior attempts.

A pending state record might store:

~~~text
enrichmentRequestId = ER-001
eventId             = EV-101
orderId             = O-101
tenantId            = tenant-A
customerId          = C-01
status              = WAITING
createdAt           = ...
deadline            = ...
policyVersion       = 3
originalPayloadRef  = location in durable store
~~~

Upon receiving a reply, the coordinator must:

1. Look up the record by `enrichmentRequestId`.
2. Authenticate the reply source and **verify `tenantId`/`customerId` match** the original request.
3. Check deadline, current status, and attempt count.
4. Use a conditional state transition (e.g., `WAITING → COMPLETED`) to handle duplicates.
5. Retrieve the durably stored original payload, merge valid data, and emit the enriched event **once per business effect**, using idempotency/outbox where needed.

Depending on the use case, the **correlation store** can be a database table, message store, workflow engine, or custom coordinator. It does not have to be a Spring Integration Aggregator, since an Aggregator focuses on grouping messages by correlation key and release strategy, whereas restoring **M0 + R1** may need dedicated persistence for original payloads and deadlines.

## 12. Never Serialize Temporary `replyChannel` as Wire Correlation

A dangerous mistake:

~~~text
Request sent to broker:
  payload.customerId=C-01
  headers.replyChannel=<TemporaryReplyChannel Java object>
~~~

A temporary reply channel is an in-JVM coordination construct, not a durable address another process can resolve. If a message mapper tries to serialize all headers, it may fail, expose internal metadata, or create the false assumption that process B can invoke an object inside process A directly.

Instead, publish a **broker return address** or adapter-supported reply topic/queue plus a **simple-typed correlation key**:

~~~text
request.topic = customer.lookup.requests
request.enrichmentRequestId = ER-001
request.replyDestination = customer.lookup.replies

reply.topic = customer.lookup.replies
reply.enrichmentRequestId = ER-001
~~~

Spring Integration's broker adapters/request–reply gateways may provide technology- and version-specific correlation mechanisms. If using them, verify **wire header mapping, reply destination, timeouts, reply containers, and post-restart behavior** before building a custom coordinator. Never assume all gateways share identical reply correlation or durability guarantees.

**Distinction:** an in-JVM Gateway's `replyChannel`, a broker reply address, and a wire-level `enrichmentRequestId` are three different concepts. A proper design maps between them at **transport boundaries** without letting clients target arbitrary internal channels.

## 13. Multi-Tenant: Matching Request ID with the Wrong Tenant Is Still a Bug

Suppose tenant A and tenant B both have `customerId=C-01`. If the lookup service queries by `customerId` while ignoring tenant, the system could attach tenant B's profile to tenant A's order—even though `enrichmentRequestId` matched the call cleanly.

Correlation and authorization are therefore **complementary controls**:

| Check | Question |
|---|---|
| Correlation | Which request does this reply belong to? |
| Tenant scope | Do request and reply share the authenticated tenant? |
| Domain identity | Does `customerId` in the reply match the requested key? |
| Freshness / version | Is the returned profile of an acceptable version or point in time? |
| Authorization | Is the caller/service allowed to read and use this profile? |

If the profile governs pricing, credit limits, or access rights, never trust reply values solely because they "came off the channel." Validate the responding service, schema, values, and business invariants.

When storing pending state, scope keys and unique indexes properly—for example `(tenantId, enrichmentRequestId)` plus source verification. Using a globally unique ID still does not replace tenant checks.

## 14. Handling Replies That Do Not Match Any Request

A mismatched reply can stem from a bug, buggy producer, stale replay, customer tenant migration, or spoofing.

| Scenario | What Never to Do | Suggested Handling |
|---|---|---|
| `enrichmentRequestId` missing from pending store | Attach to the first waiting request | Quarantine and emit unknown-correlation metric |
| Reply has a different `customerId` | Ignore `customerId` and enrich anyway | Reject mismatch, inspect service/schema |
| Reply tenant differs from original tenant | Enrich cross-tenant | Security error, never emit message |
| Late reply after timeout | Reopen an already failed original | Apply late-reply policy; avoid double completion |
| Two replies for the same request ID | Overwrite state and emit twice | Deduplicate / conditional state transition |
| Reply uses unsupported schema | Force-cast to grab tier | Version gate / quarantine |
| Valid reply missing tier | Auto-set GOLD | Default or reject per contract |

**Never use arrival order, payload type, or lookup key as the sole correlation mechanism.** Those attributes collide across concurrent requests; use a proper correlation identity.

When two orders share the same `customerId`, caching may reuse the profile value; **cache key** and **enrichment request correlation** remain distinct concepts. The cache can supply the same profile to both requests while each original message receives its own isolated output.

## 15. Timeouts: How Long to Wait for a Reply and What to Do Afterward

A Content Enricher calling a remote service can stall at multiple points:

~~~mermaid
flowchart TD
    EN["Enricher sends Q1"] --> SEND{"Send to requestChannel"}
    SEND -->|"Cannot send"| SE["Send failure / request timeout"]
    SEND -->|"Sent"| WAIT["Wait for lookup reply"]
    WAIT -->|"Valid reply"| DONE["Enrich M0 → M1"]
    WAIT -->|"Timeout"| TO["Reply timeout / failure policy"]
    WAIT -->|"Exception"| ER["Error path / fallback policy"]
    TO --> LATE["If reply arrives later: late-reply policy"]
~~~

**`requestTimeout`** bounds a blocking send operation; **`replyTimeout`** bounds waiting for the reply. Neither replaces timeouts on HTTP clients, database queries, Kafka producers/consumers, or an external Gateway.

Moreover, default timeouts and timeout error reporting **vary by version and configuration**. Never rely on unverified defaults; declare timeouts aligned with SLAs and test real behavior on your project's stack.

After a timeout, three strategies are common:

1. **Fail enrichment:** do not emit M1; raise a traceable error so the caller or error handler decides next steps.
2. **Contracted fallback:** only where business rules allow, use backup data like tier `UNKNOWN` with provenance/quality flags and reduced privileges.
3. **Deferred completion:** persist pending state and complete asynchronously when the reply arrives within an explicit deadline; usually requires a process manager/store instead of holding HTTP requests open indefinitely.

**A timeout does not prove the lookup never executed.** The remote service may have processed Q1 and sent R1 right after the deadline. Retries must account for idempotency and never turn a late reply into a second enrichment.

## 16. Retries, Duplicates, and Idempotency for Enrichment

Suppose Q1 hits a network error. The client retries and emits Q1' identical to Q1. If lookup is purely read-only, business impact may be low; if the lookup service also writes audits, decrements quotas, or updates state, retries can cause side effects.

**Recommended strategy:**

- Separate **logical enrichment request ID** from attempt ID when tracking multiple attempts.
- Keep original `eventId` unchanged across redeliveries.
- When sending over a broker, persist state/outbox so crashes between DB commit and publish do not emit unintended duplicate requests.
- Even when remote lookup is an idempotent GET, still handle **duplicate replies** and deadlines in the coordinator.
- Classify errors: network timeouts allow bounded retries; `CUSTOMER_NOT_FOUND` or tenant mismatches must not retry forever.
- Once enriched output is emitted, mark completion conditionally to avoid emitting the same business outcome twice, or rely on downstream idempotency keys.

A state model:

~~~mermaid
stateDiagram-v2
    [*] --> WAITING: send lookup request
    WAITING --> COMPLETED: matching correlation + valid reply
    WAITING --> FAILED: unrecoverable error
    WAITING --> TIMED_OUT: deadline exceeded
    TIMED_OUT --> RETRIED: intentional retry
    RETRIED --> COMPLETED: valid reply
    RETRIED --> FAILED: attempts exhausted
    COMPLETED --> [*]
    FAILED --> [*]
~~~

This is an **illustrative application state machine**, not automatic behavior of a basic `ContentEnricher`. When production uses brokers and durable stores, define late replies, terminal states, and idempotency at every transition.

## 17. Header Propagation: Keep Enough to Correlate, Never Too Much

The original message might carry headers such as:

~~~text
eventId, tenantId, traceId, correlationId,
replyChannel, errorChannel, sequenceNumber, sequenceSize,
Authorization, Cookie, rawSourceHeader
~~~

Not all of them should enter the lookup or return onto M1.

| Header | In M0 | Sending Q1 to Subflow | Emitting M1 / Outbound |
|---|---|---|---|
| `eventId` / business ID | Keep | May pass for tracing/idempotency | Keep per contract |
| Trusted `tenantId` | Keep | Send if lookup needs scope and auth | Keep within authorized zone |
| `traceId` | Keep | Propagate via appropriate tracer/mapper | Keep if safe |
| Splitter `correlationId` | Keep | Never overwrite with lookup request ID | Keep for Aggregator |
| Internal `replyChannel` | Per gateway flow | Enricher manages temporary reply | Never serialize arbitrarily to broker |
| `errorChannel` | Per error policy | Never let external producers overwrite | Per error boundary |
| `Authorization` / `Cookie` | May exist at ingress | Pass only via designed auth mechanisms | Never copy indiscriminately |
| `enrichmentRequestId` | Not necessarily present | Mint when going async external | Keep in audit/logs; never overwrite business correlation |

**Never call `MessageBuilder.copyHeaders(...)` blindly** when building an external request. Instead, construct an explicit wire contract from permitted fields. When producing M1, preserve original context needed downstream without merging reply headers under a "reply wins all" rule.

If the reply service sends a header colliding with `tenantId` or `correlationId`, decide explicitly which headers may overwrite and verify their origin. Especially when using `headerExpression` in Enricher, verify `overwrite` semantics and expression roots against your API version—**never populate critical routing headers from untrusted replies**.

## 18. Distinguishing Content Enricher, Header Enricher, Transformer, and Aggregator

| Pattern | Responsibility | Correlation to Consider |
|---|---|---|
| **Header Enricher** | Adds/normalizes metadata | Does not call lookup itself; avoid overwriting critical headers |
| **Content / Payload Enricher** | Fetches supplementary data and sets onto original payload | M0 ↔ Q1 ↔ R1, especially when remote/async |
| **Transformer** | Converts payload A to B per contract | Preserve event/correlation when creating new messages |
| **Request–Reply Gateway** | Exposes call path and receives result | `replyChannel`, timeout, error propagation |
| **Splitter** | Splits original message into child messages | `correlationId`, sequence metadata |
| **Aggregator** | Collects multiple results per group | Correlation key, release strategy, timeout |
| **Routing Slip** | Orchestrates channel sequence | Does not correlate remote replies to original itself |

Content Enricher typically awaits **one lookup reply** to enrich **one original**. If you must call **three independent services** and return only once all three respond, that also involves **Scatter-Gather / Aggregation**; configuring a single Enricher expecting it to gather all replies is insufficient.

If you only need a constant value or one derived from M0, there is no need for a remote request. Use a Transformer or a header/payload enricher without `requestChannel` as appropriate.

## 19. With Splitter/Aggregator: Never Confuse the Two Correlation Levels

An order splits into three line items. Each line needs SKU details looked up:

~~~mermaid
flowchart LR
    ORD["Order O-101"] --> SPLIT["Splitter"]
    SPLIT --> L1["Line 1"]
    SPLIT --> L2["Line 2"]
    SPLIT --> L3["Line 3"]
    L1 --> E1["Enricher Q-1/R-1"]
    L2 --> E2["Enricher Q-2/R-2"]
    L3 --> E3["Enricher Q-3/R-3"]
    E1 --> AG["Aggregator by order correlation"]
    E2 --> AG
    E3 --> AG
    AG --> RES["OrderWithSkuDetails"]
~~~

Here **two levels** exist:

1. **Order-group correlation:** groups lines belonging to Order O-101 using `correlationId` and `sequenceSize` managed by Splitter/Aggregator.
2. **Per-line enrichment correlation:** pairs each lookup reply with the matching waiting line item, such as `enrichmentRequestId` for SKU-1, SKU-2, SKU-3 across a broker.

Never overwrite the Splitter's `correlationId` with `enrichmentRequestId`. Doing so makes the Aggregator treat three lines as three separate groups or wait forever.

**When one line's enrichment reply fails:**

- If that line stops moving forward, the Aggregator will be short of `sequenceSize` and wait.
- If the business permits partial results, convert the error into a **failure result carrying the order and line correlation**.
- If the whole order must fail, the coordinator must propagate failure, cancel/time out remaining parts, and prevent unwanted side effects.
- Configure an appropriate release strategy, group timeout, and expired-message policy; never mark complete just because one branch arrived early.

## 20. Lookup Data Consistency: Profiles Can Change Between Attempts

Even when a reply is correlated to **the exact right ID**, the enrichment result can still mismatch the business point in time.

For instance, Order EV-101 was created at 09:00, and lookup returned `GOLD` at 09:00:01. Replayed a day later, the customer has changed to `STANDARD`. Using current values on the same order may alter totals or perks.

Design must decide whether to:

- Use the **current snapshot** at reprocessing time.
- Use a **version / as-of timestamp** from when the event occurred.
- Persist the **enrichment result snapshot** in event/process state for deterministic replay.
- Use an **ETag / version on returned data** and reject version mismatches.

For critical domains (pricing, risk, limits, tax), record enrichment **provenance**: source, version, timestamp, request ID, and applied policy. Correlation guarantees *matching the right entity*, whereas versioning/freshness guarantees *using the right version of data*.

## 21. Error Channel and Recovery: Never Equate Every Error with "Not Found"

A Content Enricher can fail at multiple boundaries:

| Failure | Cause | Handling Direction |
|---|---|---|
| Request cannot be sent | Channel full, adapter stopped | Bounded retry / backpressure |
| Reply timeout | Slow lookup, lost reply | Deadline / late-reply policy |
| `CUSTOMER_NOT_FOUND` | Key has no record | Business rejection or published fallback |
| Reply schema mismatch | Service returned unexpected type | Version gate / quarantine |
| Reply correlation/tenant mismatch | Misrouted or spoofed | Security/reconciliation error; do not enrich |
| Property expression error | Reply missing field or incompatible type | Fix contract / Transformer |
| Downstream Router/handler error | Enrichment succeeded, next step failed | Downstream error/retry policy |

Spring Integration Content Enricher offers an `errorChannel` configuration for failures during the request subflow, enabling an alternate reply path for enrichment. **Never assume declaring an error channel automatically builds a valid fallback for every exception.** If fallback is desired, explicitly define the alternate reply type, deadlines, and rules for missing fields.

In synchronous flows, exceptions propagate back to the caller/Gateway. With queues, executors, pollers, or brokers, errors occur after the producer already sent the message and must be handled at the right **async error boundary**.

**Never retry indefinitely** on invalid requests, tenant mismatches, or non-existent keys. Permanent validation errors do not heal on redelivery. Conversely, network timeouts may be transient yet still require attempt caps, jitter/backoff, and duplicate guards.

## 22. Correlation Stores Must Manage Deadlines and Cleanup

A `ConcurrentHashMap<requestId, original>` may suffice for a single-JVM demo, yet production must evaluate:

- **Durability:** does restarting while awaiting a reply lose the original message?
- **Capacity:** are pending requests capped per tenant or worker?
- **Deadlines:** which requests expired, who transitions them to `TIMED_OUT`, and who notifies callers?
- **Late replies:** are post-timeout replies dropped, logged to state, or eligible for recovery?
- **Duplicates:** how are two identical replies handled without emitting M1 twice?
- **Cleanup:** after success/failure/timeout, are pending records purged and resources freed?
- **Privacy:** do original payloads/references hold PII requiring encryption and retention rules?
- **Consistency:** do state updates and M1 emission use outbox/idempotency to prevent mid-crash event loss?

If request–reply stays entirely in-JVM and finishes quickly, the framework already manages call correlation; do not drag all that complexity into simple use cases. **Expand to a pending store only when recovery, durability, or concurrency requirements exceed local reply limits.**

## 23. Unit Test: Validating Enrichment Matching Before Modifying the Original

For broker-based request patterns, extract a pure Java validator confirming R1 truly belongs to Q1:

~~~java
record PendingLookup(
    String enrichmentRequestId,
    String tenantId,
    String customerId
) {}

final class LookupReplyValidator {
    void validate(PendingLookup pending, CustomerLookupReply reply) {
        if (pending == null || reply == null) {
            throw new IllegalArgumentException("UNKNOWN_REQUEST");
        }
        if (!Objects.equals(
                pending.enrichmentRequestId(),
                reply.enrichmentRequestId())) {
            throw new IllegalArgumentException("CORRELATION_MISMATCH");
        }
        if (!Objects.equals(
                pending.tenantId(), reply.tenantId())) {
            throw new IllegalArgumentException("TENANT_MISMATCH");
        }
        if (!Objects.equals(
                pending.customerId(), reply.customerId())) {
            throw new IllegalArgumentException("CUSTOMER_MISMATCH");
        }
    }
}
~~~

JUnit 5 example:

~~~java
@Test
void rejectsCrossTenantReplyEvenWithMatchingRequestId() {
    PendingLookup pending =
        new PendingLookup("ER-1", "tenant-A", "C-01");
    CustomerLookupReply suspicious = new CustomerLookupReply(
        "ER-1", "tenant-B", "C-01", "GOLD", "OK");

    assertThrows(IllegalArgumentException.class,
        () -> new LookupReplyValidator()
            .validate(pending, suspicious));
}

@Test
void rejectsWrongCustomerForSameRequestId() {
    PendingLookup pending =
        new PendingLookup("ER-1", "tenant-A", "C-01");
    CustomerLookupReply suspicious = new CustomerLookupReply(
        "ER-1", "tenant-A", "C-02", "GOLD", "OK");

    assertThrows(IllegalArgumentException.class,
        () -> new LookupReplyValidator()
            .validate(pending, suspicious));
}
~~~

These tests verify **application invariants**, not temporary reply channel behavior. In production, add reply-producer authentication, outcome/version checks, deadlines, and deduplication via conditional durable-store updates.

## 24. Integration Test: Two Concurrent Orders Must Never Swap Profiles

Create a Spring test context with the Java DSL Content Enricher and lookup handler. Register `orders.enriched` as a `QueueChannel` **in test-only configuration** so production consumers do not race with tests.

Example integration test body:

~~~java
@Autowired
ApplicationContext context;

@Test
void enrichesCorrectOriginalOrder() {
    MessageChannel input =
        context.getBean("orders.in", MessageChannel.class);
    PollableChannel output =
        context.getBean("orders.enriched", PollableChannel.class);

    OrderDraft original = new OrderDraft(
        "EV-101", "O-101", "C-01");
    Message<OrderDraft> message = MessageBuilder
        .withPayload(original)
        .setHeader("businessEventId", "EV-101")
        .build();

    assertTrue(input.send(message));
    Message<?> enrichedMessage = output.receive(2_000);
    assertNotNull(enrichedMessage);

    OrderDraft enriched =
        (OrderDraft) enrichedMessage.getPayload();
    assertEquals("O-101", enriched.getOrderId());
    assertEquals("C-01",
        enriched.getCustomerProfile().customerId());
    assertEquals("GOLD",
        enriched.getCustomerProfile().tier());
    assertEquals("EV-101",
        enrichedMessage.getHeaders().get("businessEventId"));
}
~~~

This is an **illustrative integration test**; wire the flows, handlers, and test queue in a real Spring context. `send()` returning `true` does not prove the Enricher ran; always inspect the output payload and headers.

**Concurrency tests** should:

1. Create two orders `O-101/C-01` and `O-102/C-02`.
2. Send from two publisher threads through an ingress supporting concurrent processing.
3. Use latches/futures so the `C-01` lookup finishes **after** the `C-02` lookup—never rely on `Thread.sleep` to force ordering.
4. Receive both enriched outputs, match by `eventId`/`orderId`, and assert the exact right profile on each.
5. Inject duplicate/late replies when testing a broker coordinator; assert only one valid final outcome is allowed.

Never assert merely "two messages arrived"; two messages could have **swapped profiles** while still counting as two.

## 25. End-to-End Test Matrix

| Test | Setup | Expected |
|---|---|---|
| Single synchronous request | M0 has C-01; R1 returns GOLD | M1 keeps O-101 and gets GOLD |
| Two parallel requests | R-B arrives before R-A | M1-A gets profile A, M1-B gets profile B |
| Request payload subset | Only `customerId` sent as Q1 payload | Headers/lookup adhere to contract |
| Original header | `businessEventId=EV-A` | M1 preserves published ID |
| Duplicate reply | Two R replies with same `enrichmentRequestId` | Never emits two business outputs |
| Unknown correlation ID | R has no pending request | Quarantined/ignored with metric, never attached blindly |
| Cross-tenant reply | Request tenant A, reply tenant B | Safely rejected, profile never leaked |
| Customer mismatch | Q asks C-01, R returns C-02 | Rejected, never enriched |
| Timeout | Lookup fails to reply in time | Error/fallback per policy; never hangs forever |
| Late reply | R arrives after deadline | Never causes double completion |
| Lookup error | Remote throws exception | Proper error boundary / retry classification |
| Unexpected reply type | Reply lacks `CustomerProfile` | Contract/validation error |
| Missing lookup key | `customerId=null` | Rejected before request; never calls service with null |
| Splitter / Aggregator | Three lines trigger three distinct lookups | Preserves order correlation; never mixes with request ID |
| Cross-JVM serialization | Q/R cross broker | Never serializes internal reply channel arbitrarily |
| Restart while pending | Process dies before R arrives | Recovers per durability contract |
| Profile version | Replay same order on another day | Snapshot/version policy matches business rule |

Beyond unit and integration tests, write **contract tests** against real broker or HTTP adapters: verify header mappers, encoding, reply destinations, request IDs, tenant scopes, and schema versions. Mocks returning direct Java objects cannot catch wire serialization/deserialization bugs.

## 26. Observing Correlation in Production

A useful trace tells the full story:

~~~text
EV-101 / O-101
  → Enricher start, operation=CUSTOMER_LOOKUP, requestId=ER-001
  → Request sent, destination=customer.lookup.requests
  → Reply received, requestId=ER-001, customer=C-01
  → Validation passed, tenant matched
  → Profile applied, tier=GOLD
  → orders.enriched, downstream result
~~~

Suggested metrics:

| Signal | Detects |
|---|---|
| `enrichment.request.count` | Lookup throughput |
| `enrichment.reply.duration` | Request–reply latency |
| `enrichment.pending.count` | Currently waiting requests |
| `enrichment.timeout.count` | Lost or overly slow replies |
| `enrichment.correlation.mismatch.count` | Wrong-key replies or missing pending records |
| `enrichment.duplicate.reply.count` | Duplicate replies delivered |
| `enrichment.late.reply.count` | Replies arriving past deadline |
| `enrichment.fallback.count` | Fallback frequency |
| `enrichment.error.count` by reason | Network, schema, permission, mapping errors |
| `enrichment.result.age` | Age of lookup data when applied |

These are **suggested metric names**, not default Spring Integration meters. Never use `eventId`/`requestId`/`customerId` as metric tags due to high cardinality and privacy risks. To inspect a specific request, use **tracing and controlled structured logs**.

When enrichment times out, investigate in order: **M0 accepted → Q1 sent → request ID → lookup executed → R1 emitted → reply destination → correlation mapping → property applied → M1 reached downstream**. Distinguish "no reply sent" from "reply arrived but was dropped for mismatch/timeout."

## 27. Common Misconceptions

**"Matching `customerId` proves the reply matches the original."** False. Multiple orders or tenants can share `customerId`; you need request identity and tenant scope.

**"`MessageHeaders.ID` is a durable `enrichmentRequestId`."** False. Recreating messages, retries, or adapters changes IDs.

**"Content Enricher always needs a pending-request table by default."** No. Inside single-JVM request–reply paths, Enricher uses gateway/reply-channel mechanics to pair replies with calls.

**"Shrinking the request payload automatically strips sensitive headers."** False. Request messages can still carry original headers; outbound mappers need explicit policies.

**"`replyChannel` is a business `correlationId`."** False. One coordinates internal return routing; the other identifies requests or groups.

**"Once a reply arrives, it is always safe to apply to M0."** False. Verify tenant, customer identity, schema, outcome, freshness, and authorization as needed.

**"A shared reply queue is equivalent to a temporary reply channel."** Not automatically. You need a real resolver/correlation mechanism so concurrent calls do not steal replies.

**"Enricher timeout means the lookup caused no side effects."** False. The service may have processed it or the reply may still be in transit.

**"Replacing Splitter's `correlationId` with `requestId` makes matching faster."** False. That breaks order Aggregation.

**"A duplicate reply means enrich twice."** False. Use idempotency and conditional state transitions.

**"Profile caching and reply correlation are the same problem."** False. Caching reuses data; correlation pairs each reply with its matching original/request.

**"Having an `errorChannel` automatically selects a valid fallback for every error."** False. Alternate reply contracts and retry/failure policies must still be designed explicitly.

## 28. Practice Exercise: Proving Correct Correlation Under Out-of-Order Replies

Build the **OrderCustomerEnrichment** flow:

1. Create `OrderDraft` with `eventId`, `orderId`, `customerId`, and enriched property `customerProfile`.
2. Configure Content Enricher to send `customerId` via `customer.lookup.requests`, using `propertyExpression("customerProfile","payload")`.
3. Write a lookup Service Activator returning `CustomerProfile` and intentionally vary delays using a latch in tests.
4. Send two orders in parallel, having C-02 reply before C-01; assert profiles are never swapped.
5. Inspect original headers on both request and output messages; design an allowlist when moving to a broker.
6. Add timeouts and simulated lookup failures; verify the error path without mistaking `send()` for business success.
7. Extend over a broker: emit `CustomerLookupRequest/Reply` with `enrichmentRequestId` and tenant-scoped pending state.
8. Inject unknown, duplicate, late, and cross-tenant replies; emit enriched output only when correlation and validation pass.
9. Route three line items of one order through per-line enrichment into an Aggregator; keep order correlation intact while minting per-line request IDs.
10. Measure request latency, pending counts, mismatches, timeouts, errors, and fallback rates; attach traces to investigate individual events.

**Completion criteria:** M1 retains original identity and content; out-of-order replies are never cross-wired; pending state does not leak across timeouts/restarts per policy; framework reply channels are never serialized as business IDs; retries/duplicates never emit wrong or duplicate outputs; tests separate enrichment correlation from Aggregator correlation.

## 29. Key Takeaways

**Correlation between the original message and the enrichment request** has two layers: **technical correlation** of the request–reply mechanism so the right R1 returns to the waiting Enricher invocation, and **business correlation** linking event/order/tenant/operation across processes, attempts, and observability systems.

In a standard Spring Integration Content Enricher, the framework can use a **temporary reply channel** to pair request–reply calls. When integrating across brokers, callbacks, or long-running workflows, design **`enrichmentRequestId` + pending state + deadlines + validation + idempotency** per the application contract. Preserve original business identity, **Splitter/Aggregator** correlation headers, and controlled header propagation—and never rely on `customerId` or `MessageHeaders.ID` as a unique pairing key.

That way, **Gateway → Content Enricher → Router/Filter/Transformer → handler or Aggregator** pipelines keep data bound to the exact right entity despite async execution, retries, error channels, or out-of-order completion.

### References

- Spring Integration Reference, **Content Enricher**: https://docs.spring.io/spring-integration/reference/content-enrichment.html
- Spring Integration Java DSL API, **EnricherSpec**: https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/dsl/EnricherSpec.html
- Enterprise Integration Patterns, **Content Enricher**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/DataEnricher.html
