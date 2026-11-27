# Handling Missing Data in a Transformer

## 1. Why Is Missing Data a Transformer Problem?

A system receives order events from HTTP, Kafka, or AMQP and converts them into a unified internal model. One producer sends complete `orderId`, `region`, and `quantity`; another omits `region` or leaves out `quantity`. If a Transformer silently replaces missing fields with unapproved default values, the message may still pass through a **Router** yet land on the **wrong channel**, causing the system to process the order for the wrong market or quantity.

For example, a payload received after deserialization:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EV-101",
  "orderId": "ORD-101",
  "region": null,
  "quantity": 3,
  "customerNote": null
}
~~~

Both fields hold `null`, yet their meanings differ:

- `region` determines the processing path; if the market cannot be determined, **never guess "VN"**.
- `customerNote` is optional information; it can be converted to an empty string **if the target contract specifies it**.

**Core principle:** a Transformer performs **contract-driven conversion**, not silent patching of broken data. You must classify *missing required fields*, *missing optional fields*, *wrong types*, *invalid values*, and *incompatible schemas* before deciding whether to **transform, reject, or route to an exception path**.

This lesson belongs to the **Transformer** chapter of the **SPRING_INTEGRATION_PATTERN** module, supporting the goal of learning **Enterprise Integration Patterns** with Spring Integration to design loosely coupled, extensible message flows. The examples place Transformer alongside **Gateway, Filter, Router, Splitter, Aggregator, retry, error channel, and correlation**, while showing how to test and monitor processing branches.

After this lesson, you will be able to design inbound DTOs capable of representing missing data, transform into internal payloads with explicit invariants, choose appropriate reject/default/derive strategies, preserve required metadata, and write tests for both valid and missing-data cases.

## 2. Identifying Which Layer "Missing" Occurs At

Not every problem described as "missing data" happens inside the Transformer:

| Situation | Example | Appropriate Layer |
|---|---|---|
| **Unreadable wire message** | Truncated JSON, broken byte stream | Inbound adapter/decoder |
| **Incompatible data type** | `quantity="n/a"` when schema requires Integer | Deserializer/schema validation |
| **Missing required field** | DTO has `orderId=null` | Validator/Transformer per contract |
| **Empty or whitespace-only string** | `region="  "` | Validation then normalization |
| **Absent optional field** | No `customerNote` | Intentional default |
| **Right type, invalid rule** | `quantity=-3` | Business validation |
| **Missing header** | No `traceId` or `tenantId` | Header policy/adapter; derive only from trusted source |
| **Unsupported schema version** | `schemaVersion=3` in a v1-only consumer | Version gate/migration |

Some deserialization frameworks can distinguish **field absent** from **field explicitly null** if you use tree models, custom deserializers, or presence-aware DTOs. A Java record with nullable fields usually **loses that distinction** after binding: both cases yield `null`. Therefore, if business logic distinguishes "field omitted" from "explicitly clear field," preserve presence metadata **right at the parse boundary**.

Additionally, **Spring `Message<?>` does not treat a `null` payload as a normal valid message**. "Payload missing data" here primarily means **fields inside the payload are missing**, or headers are absent; never turn a `null` payload into an implicit meaningful event.

## 3. Inbound Contract and Internal Contract

At the system boundary, use nullable types for fields that may be omitted or sent incorrectly:

~~~java
record IncomingOrderV1(
    Integer schemaVersion,
    String eventId,
    String orderId,
    String region,
    Integer quantity,
    String customerNote
) {}

record NormalizedOrder(
    String eventId,
    String orderId,
    String region,
    int quantity,
    String customerNote
) {}
~~~

The two types serve different roles:

- `IncomingOrderV1` reflects what the adapter *managed to parse*; `Integer` lets you distinguish a missing or `null` field from `0`.
- `NormalizedOrder` is the **verified contract**; `quantity` becomes `int`, and required Strings are guaranteed non-empty at the conversion boundary.

| Property | Required? | Rule | When Missing |
|---|---|---|---|
| `schemaVersion` | Yes | Only `1` supported in example | Reject `MISSING_VERSION` |
| `eventId` | Yes | Non-blank | Reject `MISSING_EVENT_ID` |
| `orderId` | Yes | Non-blank | Reject `MISSING_ORDER_ID` |
| `region` | Yes | Two-letter code, normalized uppercase | Reject `MISSING_REGION` |
| `quantity` | Yes | Positive integer | Reject `MISSING_QUANTITY` or `INVALID_QUANTITY` |
| `customerNote` | No | Max 500 characters, normalized whitespace | May default to `""` |

**Do not** use `int quantity` directly on the inbound DTO if the producer might omit the field: depending on the deserializer, an omitted field may default to `0`, erasing the distinction between "no data sent" and "sent 0."

Similarly, if `region` affects authorization, pricing, and warehousing, there is no safe excuse to default it to `VN` just because most customers are in Vietnam. Defaults must be **published business rules**, not developer guesses.

## 4. Recommended Pipeline: Decode, Validate, Transform, Then Route

~~~mermaid
flowchart TD
    W["HTTP / Kafka / AMQP input"] --> D{"Decode + schema"}
    D -->|"Unparseable"| P["Ingress error / quarantine"]
    D -->|"Parsed"| M["Message<IncomingOrderV1>"]
    M --> V{"Type, version, and required fields"}
    V -->|"Invalid"| R["Rejected result / exception"]
    V -->|"Valid"| T["Transformer: normalize + map"]
    T --> C["Message<NormalizedOrder>"]
    C --> ROUTE{"Router by region"}
    ROUTE -->|"VN"| VN["orders.vn"]
    ROUTE -->|"US"| US["orders.us"]
    ROUTE -->|"Other"| O["orders.unmapped"]
    R --> E["Error policy / rejected channel"]
~~~

**Decode** handles wire syntax and types. **Validation** decides whether the data satisfies minimum contract requirements. **Transformer** converts types, normalizes, and builds a stable model. **Router** selects the branch from the validated payload.

In a small flow, validation and transformation may live in the same Java function. Even so, keep **validation rules separated and testable**, avoiding a sprawling Transformer that parses JSON, calls APIs, computes prices, sends emails, and picks channels all at once.

A Filter only returns a boolean "pass/drop"; when multiple rejection reasons are needed, a classifier with error codes or a concrete result type is easier to observe. **Do not treat a Router's `defaultOutputChannel` as an automatic catch-all for Transformer errors**: an exception thrown before producing a routing key does not turn into an unmapped key.

## 5. Three Decisions When Encountering a Missing Field

For each field, choose **only one transparent policy**:

| Policy | When Appropriate | Example |
|---|---|---|
| **Reject / fail-fast** | Required field with insufficient basis to infer | Missing `orderId`, `quantity` |
| **Intentional default** | Optional field with explicitly documented default | `customerNote = ""` |
| **Derive from trusted source** | Another verified source exists with clear precedence | `region` from an authenticated identity/tenant context |

A fourth option is **preserving the absent state** if the internal model accepts optional fields and downstream handlers take responsibility; this must be reflected in the types via `Optional` or nullable fields and downstream contracts. Never silently turn an optional field into mandatory just because a handler forgot a null check.

To decide, ask:

1. Does this field control safety, pricing, financial amounts, access permissions, or routing?
2. Would a default value alter business meaning or mask producer bugs?
3. If falling back to a header, is that header verified, scoped to the same tenant/version, and governed by published precedence?
4. Can the system measure missing-data frequency and identify which source produced it?

**Missing data is not evidence that a retry will succeed.** If a producer emitted an event without `orderId`, re-reading the exact same event from the broker will not supply that field; reject/quarantine it or use a controlled remediation process instead of infinite retries.

## 6. Code: Transformer Validating Required Fields Before Building a New Payload

One implementation approach uses a pure Java service with no I/O during transformation:

~~~java
final class InvalidOrderException extends RuntimeException {
    private final String reasonCode;

    InvalidOrderException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}

final class OrderNormalizer {

    NormalizedOrder normalize(IncomingOrderV1 raw) {
        if (raw == null) {
            // Guard when calling the Java method directly;
            // null payload is not a normal valid message.
            throw new InvalidOrderException("MISSING_PAYLOAD");
        }
        if (raw.schemaVersion() == null) {
            throw new InvalidOrderException("MISSING_VERSION");
        }
        if (raw.schemaVersion() != 1) {
            throw new InvalidOrderException("UNSUPPORTED_VERSION");
        }

        String eventId =
            required(raw.eventId(), "MISSING_EVENT_ID");
        String orderId =
            required(raw.orderId(), "MISSING_ORDER_ID");
        String region =
            required(raw.region(), "MISSING_REGION")
                .toUpperCase(Locale.ROOT);

        if (!region.matches("[A-Z]{2}")) {
            throw new InvalidOrderException("INVALID_REGION");
        }
        if (raw.quantity() == null) {
            throw new InvalidOrderException("MISSING_QUANTITY");
        }
        if (raw.quantity() <= 0) {
            throw new InvalidOrderException("INVALID_QUANTITY");
        }

        String note = raw.customerNote() == null
            ? ""
            : raw.customerNote().strip();
        if (note.length() > 500) {
            throw new InvalidOrderException("NOTE_TOO_LONG");
        }

        return new NormalizedOrder(
            eventId, orderId, region, raw.quantity(), note);
    }

    private String required(String value, String reasonCode) {
        if (value == null || value.isBlank()) {
            throw new InvalidOrderException(reasonCode);
        }
        return value.strip();
    }
}
~~~

Design highlights:

- `normalize()` either returns a **complete** `NormalizedOrder` or throws an exception with a stable error code; it never constructs a half-valid object.
- Whitespace-only strings count as **missing** for required fields, rather than silently routing on a blank string.
- `quantity=null` differs from `quantity=0`: the first is missing, while the second has a value that violates the rule.
- `region="de"` normalizes to `DE`. A `DE` code that is **structurally valid yet unmapped** can go to `orders.unmapped`, distinct from a missing region.
- Optional `customerNote` defaults to `""`, while still bounding length to guard against abnormal inbound messages.

`InvalidOrderException` is an **application-defined illustrative class**, not a built-in Spring Integration exception. When invoked inside a Transformer endpoint, the framework may wrap this exception in a messaging/transformation exception; error handlers should inspect the **cause chain** and reason code rather than matching log text.

## 7. Configuring the Transformer in Spring Integration Java DSL

Connecting the pure Java service to the flow:

~~~java
@Configuration
@EnableIntegration
class OrderTransformFlow {

    @Bean
    OrderNormalizer orderNormalizer() {
        return new OrderNormalizer();
    }

    @Bean
    IntegrationFlow normalizeAndRoute(OrderNormalizer normalizer) {
        return IntegrationFlow.from("orders.decoded")
            .transform(IncomingOrderV1.class, normalizer::normalize)
            .route(NormalizedOrder.class, NormalizedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .defaultOutputChannel("orders.unmapped"))
            .get();
    }
}
~~~

This is a module-level Java DSL example with imports omitted. You must configure an adapter so `orders.decoded` actually receives `IncomingOrderV1`, and provide consumers for `orders.vn`, `orders.us`, and `orders.unmapped`.

When an order is missing `quantity`:

1. `OrderNormalizer.normalize()` throws `InvalidOrderException("MISSING_QUANTITY")`.
2. The Transformer endpoint propagates the exception via the messaging mechanism; **no `NormalizedOrder` is created**.
3. The downstream Router **is never invoked** with corrupt data.
4. The caller, error handler, or poller decides whether to reject, retry, or quarantine per policy.

**Assumption limit:** the typed transformer is designed for payloads of class `IncomingOrderV1`. If an adapter can emit an unexpected `String` or `byte[]`, conversion/type errors occur before or during method invocation; place an explicit type/schema gate upfront rather than expecting every type mismatch to turn into `MISSING_QUANTITY`.

## 8. Annotation-Based Transformer: When Is It Useful?

An endpoint can be declared using `@Transformer`:

~~~java
@MessageEndpoint
class AnnotatedOrderTransformer {
    private final OrderNormalizer normalizer = new OrderNormalizer();

    @Transformer(
        inputChannel = "orders.decoded",
        outputChannel = "orders.normalized")
    public NormalizedOrder toInternal(IncomingOrderV1 input) {
        return normalizer.normalize(input);
    }
}
~~~

**This is an alternative variant** to the Java DSL flow in section 7; do not register both consuming from `orders.decoded` in a sample application unless intentionally orchestrating multiple subscribers.

With annotations, the output channel is declared explicitly. If routing is needed, build a follow-up flow consuming from `orders.normalized`. Regardless of Java DSL or annotation syntax, the rule remains: **a Transformer emits only contract-compliant data**, never forwarding a payload missing required fields downstream.

A `@Transformer` returning a plain Java object normally has the framework build a reply message and copy appropriate headers from the original message per transformer mechanics. If you **manually construct a `Message<?>`**, explicitly evaluate which headers must be kept or stripped.

## 9. Never Use `return null` to Drop Messages

Beginners often write:

~~~java
@Transformer(inputChannel = "orders.decoded")
public NormalizedOrder transform(IncomingOrderV1 order) {
    if (order.quantity() == null) {
        return null; // Wrong intent: not a Filter discard
    }
    return normalizer.normalize(order);
}
~~~

**A Transformer in Spring Integration has a non-null output contract.** Returning `null` is not a valid way to say "skip this message": the system can throw a transformation error—such as `MessageTransformationException` or a related wrapper depending on endpoint and version. Therefore, never use `null` as a rejection signal or "no-op" condition.

Choose the right pattern:

| Intent | Appropriate Pattern |
|---|---|
| Do not want the message to proceed | **Filter** with an explicit discard policy |
| Want to raise an error on missing required fields | **Validator/Transformer** throwing a classified exception |
| Want to send invalid messages to a business error branch | **Classifier + Router**, or a two-state result type |
| Want to keep the original payload | Pass-through flow/handler with clear contract; never return null |
| Want to customize an optional field's value | Transformer builds a full payload with valid defaults |

A Filter by default can drop messages without sending a reply. When a Gateway is waiting for a response, "dropping" easily causes timeouts. If business logic mandates returning `ACCEPTED/REJECTED`, use a structured result type instead of mixing `return null`, exceptions, and undeclared discards.

## 10. Separate Missing, Blank, Zero, and "Invalid"

A field may hold a value and still be unusable. For example:

| Inbound Value | Recommended Classification | What Not to Do |
|---|---|---|
| `region=null` | Missing required field | Default to VN |
| `region=""` or `"  "` | Blank → contract violation | Pass to Router with blank key |
| `region="de"` | Present; normalize to `DE` | Reject solely for lowercase if contract permits |
| `region="D3"` | Malformed format | Treat as a new valid market |
| `quantity=null` | Missing quantity | Assign `0` and continue |
| `quantity=0` | Present, violates rule | Lump metrics with missing |
| `customerNote=null` | Absent optional field | Throw unnecessary exception |
| `customerNote="   "` | Empty after normalization | Keep noisy whitespace unless contract requires it |

Accurate classification helps producers fix bugs; metrics can separate "missing field rate" from "invalid value rate." For contracts where **zero is valid** (e.g., returned-item counts in another event type), separate DTOs/validators per use case instead of forcing one rule across every event.

## 11. Intentional Defaults and Value Source Precedence

Some fields have legitimate defaults. For example, an optional customer note may default to `""` and render as "no note." However, defaults always need **safety criteria**:

1. The default must be documented in the public schema/contract.
2. It must never alter routing, permissions, or monetary amounts unintentionally.
3. Operators can measure how often the default is applied.
4. Consumers know the difference between "intentionally empty value" and "unknown value," whenever that distinction matters.

Examples of overly dangerous defaults:

~~~java
String region = raw.region() == null
    ? "VN"               // Do not guess the market
    : raw.region();

int quantity = raw.quantity() == null
    ? 1                  // May trigger an erroneous transaction
    : raw.quantity();
~~~

If a field is **required by the business contract**, a default is not a "NullPointerException workaround." It can mask producer contract violations and let bad records slip past every downstream check.

**Apply defaults only when the business agrees to accept that value.** A missing value does not automatically mean `0`, `false`, `unknown`, or `VN`; each choice expresses a distinct semantic claim.

## 12. Can Missing Data Be Filled from Headers?

Some metadata attached by an adapter after authentication can help a Transformer supply missing data. However, distinguish **trusted headers** from **producer-supplied headers**.

For example, an ingress adapter authenticated the tenant and attached `verifiedRegion` from the server-side identity context. You can define a precedence policy:

~~~text
region in payload is present
   → validate and cross-check authorization against verifiedRegion

region in payload is missing
   → use verifiedRegion only if the contract allows
      and the header was server-verified

both are missing or conflicting
   → reject, never guess
~~~

A defensive header reader:

~~~java
String trustedRegionOrNull(Message<?> message) {
    Object raw = message.getHeaders().get("verifiedRegion");
    if (raw instanceof String region && !region.isBlank()) {
        return region.strip().toUpperCase(Locale.ROOT);
    }
    return null;
}
~~~

**This is only a header-reading helper, not source verification.** Naming it `verifiedRegion` does not make the value trustworthy: the inbound header mapper must block clients from overwriting it, and the adapter/authentication layer must be the sole authority setting that field. If a producer can spoof `verifiedRegion`, deriving routes from it causes cross-tenant routing.

When enriching from a header, record a decision code such as `VALUE_FROM_TRUSTED_CONTEXT` in access-controlled audits/traces; avoid exposing sensitive auth metadata in public payloads or outbound messages.

## 13. What Responsibilities Does a Transformer Have Toward Headers and Correlation?

A payload transformation must not accidentally lose context used for grouping messages and replying to Gateways:

| Header/Context | Consideration |
|---|---|
| `correlationId` | Links messages in the same workflow, especially Splitter/Aggregator |
| `sequenceNumber/sequenceSize` | Tells Aggregator ordering and group expectations |
| `replyChannel` | Needed for request–reply, especially when a Gateway awaits response |
| `errorChannel` | Can specify error path in certain contexts |
| `traceId`/baggage | Keep only selectively curated, safe context |
| `untrustedRoute`/raw headers | Do not automatically forward downstream if ingress-only |

With a Transformer returning a **payload object**, the framework usually constructs the reply message and copies appropriate headers. When building a new message manually via `MessageBuilder.withPayload(...)` **without copying headers**, you can drop correlation/reply metadata.

Manual message transformation example:

~~~java
Message<NormalizedOrder> transformMessage(
        Message<IncomingOrderV1> source,
        OrderNormalizer normalizer) {
    NormalizedOrder normalized =
        normalizer.normalize(source.getPayload());

    return MessageBuilder.withPayload(normalized)
        .copyHeaders(source.getHeaders())
        .removeHeader("untrustedRoute")
        .setHeader("normalizationVersion", "v1")
        .build();
}
~~~

This snippet is illustrative, not a claim that you must copy **every header** across every boundary. For brokers/outbound adapters, allowlist serialized metadata and never blindly push raw Spring `replyChannel`, `errorChannel`, or internal objects over the wire. Spring message IDs and timestamps also have their own semantics; **never use `MessageHeaders.ID` as a unique business idempotency key** when messages can be recreated.

## 14. SpEL and Null-Safe Navigation: Helpful, Not a Substitute for Validation

Spring Expression Language supports reading properties and handling missing values. For instance, an expression might use the Elvis operator:

~~~text
headers['customerNote'] ?: ''
~~~

Or when reading a potentially null property, a configuration might use safe navigation on an appropriate object:

~~~text
payload.customer?.name ?: 'UNKNOWN'
~~~

These expressions illustrate how SpEL works; they depend on payload structure and property accessors in a specific flow.

**Important caveats:**

- Elvis and safe-navigation prevent certain `null` dereference errors, but **do not check permissions, data types, or value domains**.
- An expression can still fail if a property does not exist on the runtime type, even if another segment uses `?.`.
- Defaulting to `'UNKNOWN'` is only safe if the downstream contract considers it valid; for data driving Routers or authorization, rejection is usually required.
- Avoid long expressions packed with business rules—they are hard to unit test and hard to attach reason codes to.
- **Never concatenate untrusted input into SpEL strings**; expressions belong to application configuration, while payloads/headers only supply values.

For transformations with multiple required fields, a pure Java validator/Transformer is usually easier to reason about and test than an expression stitched together with multiple `?:` operators.

## 15. Two Strategies for Reporting Errors: Exception or Result Type?

Not every API wants to receive exceptions. A Gateway may need to return:

~~~json
{
  "orderId": "ORD-101",
  "status": "REJECTED",
  "reasonCode": "MISSING_REGION"
}
~~~

There are two choices:

**Strategy A – Fail-fast via exception:** the Transformer throws `InvalidOrderException`; at the system boundary, an error handler turns it into a response/rejection record. Fits when data violates the contract and callers or transaction boundaries expect an error signal.

**Strategy B – Return a status-carrying result:** the Transformer **always returns a non-null object** of a result type, and a Router sends accepted and rejected outcomes to separate flows. Fits when `REJECTED` is a normal business state and every request requires a structured response.

~~~mermaid
flowchart LR
    IN["IncomingOrderV1"] --> T{"Normalizer/Classifier"}
    T -->|"Accepted"| A["Accepted(NormalizedOrder)"]
    T -->|"Rejected"| R["Rejected(reasonCode)"]
    A --> ROUTE["Business Router"]
    R --> REJ["Rejection handler / reply"]
~~~

**Do not mix the two styles:** if a Transformer returns `null` to mean rejected, that is not a status-carrying result; and if a Transformer throws an exception, a Router placed after it does not automatically receive an error message to branch on.

## 16. Example Result Type Instead of Exceptions for Expected Data Errors

Java 17 provides sealed interfaces to model both outcomes cleanly:

~~~java
sealed interface NormalizationResult
    permits AcceptedOrder, RejectedOrder {}

record AcceptedOrder(NormalizedOrder order)
    implements NormalizationResult {}

record RejectedOrder(String eventId, String reasonCode)
    implements NormalizationResult {}

final class ClassifyingOrderNormalizer {
    private final OrderNormalizer delegate = new OrderNormalizer();

    NormalizationResult normalize(IncomingOrderV1 input) {
        try {
            return new AcceptedOrder(delegate.normalize(input));
        } catch (InvalidOrderException invalid) {
            return new RejectedOrder(
                input == null ? null : input.eventId(),
                invalid.reasonCode());
        }
    }
}
~~~

Convert **only expected validation errors** into `RejectedOrder`. Never catch generic `RuntimeException` and turn bugs, database outages, or serialization failures into "bad data," which hides operational incidents.

Flow routing the outcome:

~~~java
@Bean
ClassifyingOrderNormalizer classifyingOrderNormalizer() {
    return new ClassifyingOrderNormalizer();
}

@Bean
IntegrationFlow normalizeWithBusinessOutcome(
        ClassifyingOrderNormalizer classifier) {
    return IntegrationFlow.from("orders.decoded")
        .transform(IncomingOrderV1.class, classifier::normalize)
        .route(NormalizationResult.class,
            result -> result instanceof AcceptedOrder
                ? "ACCEPTED"
                : "REJECTED",
            r -> r.channelMapping("ACCEPTED", "orders.accepted")
                  .channelMapping("REJECTED", "orders.rejected"))
        .get();
}
~~~

Register this classifier bean and flow in a `@Configuration` Spring class; this is an **alternative variant** to the fail-fast flow in section 7—do not enable both on the same input channel unless intentionally designing competing consumers. In this example, `orders.accepted` and `orders.rejected` receive the **wrapper result type**. If business consumers expect `NormalizedOrder` rather than `AcceptedOrder`, add an unwrapping Transformer **inside the accepted branch**. Each branch must have a real owner/handler.

**Error contract:** `RejectedOrder.reasonCode` is a stable application-defined code; never return raw exception stack traces as client response payloads. If raw messages must be kept for investigation, store them in an access-controlled quarantine channel with proper retention instead of attaching sensitive data to public error replies.

## 17. Missing Data in JSON: Errors Occurring Before the Transformer

A parser or Jackson adapter might encounter:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EV-102",
  "orderId": "ORD-102",
  "region": "US",
  "quantity": "three"
}
~~~

The JSON is **syntactically valid**, yet `quantity` fails the schema expecting an integer. Depending on converter/deserializer settings, it may:

1. Throw a type-conversion error before `IncomingOrderV1` is constructed.
2. Perform coercion if permitted by type policy (avoid guessing).
3. Produce an object of a different type than the Transformer expects if the adapter is configured differently.

Consequently, a unit test of `OrderNormalizer.normalize()` does not prove the entire ingress handles mistyped fields properly. Test **wire input → adapter → DTO → Transformer** to ensure consistent missing/invalid-field behavior.

Illustrative example:

~~~java
IncomingOrderV1 decode(byte[] json, ObjectMapper mapper)
        throws JsonProcessingException {
    return mapper.readValue(json, IncomingOrderV1.class);
}
~~~

In real systems, the decoder boundary needs payload size and depth limits, schema versioning, trusted-source verification, and no unrestricted polymorphic deserialization. Parse errors prior to the Transformer need dedicated **ingress error handling**; never expect a downstream Router's `defaultOutputChannel` to catch them.

## 18. Schema Evolution and Backward Compatibility

When a producer moves from schema v1 to v2, a field might:

- Become optional.
- Change name or type.
- Split into two fields.
- Gain a new default valid only in v2.

For example, v2 renames `region` to `shippingMarket`. If the deserializer keeps constructing a v1 DTO with `region=null`, Transformer v1 sees a missing field. Yet the root cause is not necessarily broken producer data; the consumer may simply not support the new version yet.

A clear strategy:

~~~mermaid
flowchart TD
    IN["Wire event + schemaVersion"] --> V{"Version gate"}
    V -->|"v1"| D1["Decode IncomingOrderV1"]
    V -->|"v2"| D2["Decode IncomingOrderV2"]
    V -->|"Unsupported"| REJ["Unsupported-version route"]
    D1 --> N1["Transformer v1 → NormalizedOrder"]
    D2 --> N2["Transformer v2 → NormalizedOrder"]
    N1 --> CORE["Core business flow"]
    N2 --> CORE
~~~

Both Transformers target a single internal contract while allowing version-specific validation and defaults. This keeps producers and consumers more loosely coupled than cramming every version into a `Map<String, Object>` and scattering casts or null checks.

**Never assume a missing field is automatically backward-compatible.** Every new field requires explicit rules for optionality, defaults, and migration; contract tests between producer and consumer are indispensable.

## 19. Error Channel, Retry, and Idempotency

When a Transformer throws an error in Spring Integration, the error path depends on execution boundaries:

| Context | Where Transformer Errors Can Go | What to Verify |
|---|---|---|
| Synchronous `DirectChannel` | Propagates back to caller/Gateway | Exception wrappers, API responses |
| `ExecutorChannel` | Occurs on worker thread | Appropriate error handler/error channel |
| `QueueChannel` + poller | Poller receives error after polling message | Transaction/error handler/recovery |
| Kafka/AMQP inbound | Listener/container or error flow | Ack/nack, retry, redelivery, DLQ |
| Downstream handler | Fails after normalized payload was emitted | Do not misattribute to Transformer |

**Permanent validation errors** like `MISSING_ORDER_ID` or `INVALID_QUANTITY` should normally **not be auto-retried repeatedly**: the same event will keep missing that data. Instead, emit a rejected result or quarantine it, ask the producer to fix the contract, and permit intentional replay once a corrected event arrives.

**Transient errors** (e.g., if a Transformer calls a database or remote service) can be retried, though that is also a signal to consider **separating I/O out of the Transformer** so timeouts, retries, and transactions are managed in a dedicated handler.

When retrying after a step prior to the Transformer already persisted data, the event may be reprocessed. Use a **stable event ID** and appropriate idempotency/transaction/outbox mechanics; `MessageHeaders.ID` may differ across redeliveries.

**A Router's default channel is not an error channel.** Rejecting a missing field may produce a `RejectedOrder` handled normally by a Router; an exception from a failing Transformer must be caught at a configured error boundary.

## 20. Missing Data in Splitter/Aggregator and Correlation

Suppose an order is split by a Splitter into three line items. The second line is missing `sku` and is rejected by the Transformer; the remaining lines are valid:

~~~mermaid
flowchart LR
    O["Order O-101"] --> S["Splitter: 3 line items"]
    S --> L1["Line 1"]
    S --> L2["Line 2: missing sku"]
    S --> L3["Line 3"]
    L1 --> T{"Transformer / validator"}
    L2 --> T
    L3 --> T
    T -->|"Accepted"| A["Aggregator"]
    T -->|"Rejected result"| ER["Failure result"]
    ER --> A
    A --> END["OrderResult"]
~~~

If the Transformer throws an exception or a Filter drops the second line, the Aggregator receives **one fewer member** than `sequenceSize`. Never assume the Aggregator will automatically release a successful group anyway.

Two valid business approaches exist:

1. **Fail whole order:** validate all items before the Splitter; if any required field is missing, fail the order without emitting child items.
2. **Partial outcome:** each line emits either `AcceptedLine` or `RejectedLine`; the Aggregator collects all results and concludes partial success or failure.

In the second approach, preserve `correlationId`, sequence metadata, and event/line IDs when the Transformer changes payloads. You may also need `groupTimeout`, a custom release strategy, and expired-message handling so groups never hang indefinitely when a failure emits no result.

**Never use `return null` in a Transformer to "skip one line"**; it can throw an exception and fails to deliver the failure result needed for the Aggregator to finish.

## 21. Unit Tests for Missing-Data Cases

`OrderNormalizer` is pure Java, so tests need no Spring context:

~~~java
@Test
void rejectsMissingRequiredFields() {
    OrderNormalizer normalizer = new OrderNormalizer();

    InvalidOrderException missingRegion = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(new IncomingOrderV1(
            1, "EV-1", "ORD-1", null, 2, null)));
    assertEquals("MISSING_REGION", missingRegion.reasonCode());

    InvalidOrderException missingQuantity = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(new IncomingOrderV1(
            1, "EV-2", "ORD-2", "VN", null, null)));
    assertEquals("MISSING_QUANTITY", missingQuantity.reasonCode());
}

@Test
void defaultsOnlyOptionalNote() {
    OrderNormalizer normalizer = new OrderNormalizer();

    NormalizedOrder output = normalizer.normalize(
        new IncomingOrderV1(
            1, "EV-3", " ORD-3 ", " vn ", 3, null));

    assertEquals("ORD-3", output.orderId());
    assertEquals("VN", output.region());
    assertEquals(3, output.quantity());
    assertEquals("", output.customerNote());
}

@Test
void distinguishesMissingFromInvalidQuantity() {
    OrderNormalizer normalizer = new OrderNormalizer();

    InvalidOrderException invalid = assertThrows(
        InvalidOrderException.class,
        () -> normalizer.normalize(
            new IncomingOrderV1(
                1, "EV-4", "ORD-4", "US", 0, "")));
    assertEquals("INVALID_QUANTITY", invalid.reasonCode());
}
~~~

These are illustrative JUnit 5 unit tests with imports omitted. Test every required field individually alongside edge cases: `null`, blank, whitespace, zero, negative numbers, malformed regions, and missing or unsupported versions. For money/prices, add precision, scale, and range cases per the specific contract.

## 22. Integration Test: Proving the Transformer Blocks Invalid Messages

With the Java DSL flow in section 7, a **test configuration** can assign `QueueChannel` targets for `orders.vn`, `orders.us`, and `orders.unmapped`. Send messages into `orders.decoded` via `MessageBuilder` and verify which channels receive—or do not receive—messages.

Example test body, assuming a Spring context initialized the flow and test channels:

~~~java
@Autowired
ApplicationContext context;

@Test
void acceptedOrderReachesCorrectRoute() {
    MessageChannel input =
        context.getBean("orders.decoded", MessageChannel.class);
    PollableChannel vn =
        context.getBean("orders.vn", PollableChannel.class);

    Message<IncomingOrderV1> message = MessageBuilder
        .withPayload(new IncomingOrderV1(
            1, "EV-10", "ORD-10", " vn ", 2, null))
        .setHeader("correlationId", "ORDER-10")
        .build();

    assertTrue(input.send(message));
    Message<?> output = vn.receive(1000);

    assertNotNull(output);
    assertInstanceOf(NormalizedOrder.class, output.getPayload());
    assertEquals("VN",
        ((NormalizedOrder) output.getPayload()).region());
    assertEquals("ORDER-10",
        output.getHeaders().get("correlationId"));
}
~~~

For rejected messages in synchronous flows, verify the exception/cause chain and confirm **no message reaches any business branch**. For result-type flows, verify `orders.rejected` receives `RejectedOrder(reasonCode)` and accepted receives nothing.

### Integration Test Matrix

| Case | Data | Expected Outcome |
|---|---|---|
| Happy path VN | `region=" vn "` | `NormalizedOrder` in `orders.vn` |
| Happy path US | `region="US"` | Arrives in `orders.us` |
| Valid new market | `region="DE"` | Arrives in `orders.unmapped`; **not** treated as missing |
| Missing region | `region=null` | Rejection/exception; never reaches Router |
| Blank region | `region="  "` | Rejection with reason code |
| Malformed region | `region="D3"` | `INVALID_REGION` |
| Missing quantity | `quantity=null` | `MISSING_QUANTITY` |
| Invalid quantity | `quantity=0` or negative | `INVALID_QUANTITY` |
| Missing `customerNote` | `customerNote=null` | Defaults to `""` if contract allows |
| Missing version | `schemaVersion=null` | `MISSING_VERSION` |
| Unsupported version | `schemaVersion=2` | `UNSUPPORTED_VERSION` |
| JSON wrong quantity type | Wire `"three"` | Decode/schema error at ingress |
| Wrong runtime payload type | `String` | Type/conversion error; not misclassified as missing |
| Correlation required | Correlation header present | Reply/child messages preserve metadata per contract |
| Retry of same event | Same `eventId` re-sent | No duplicate business side effects |

Tests must include **contract tests at the adapter boundary** if you need to distinguish an absent JSON field from JSON `null`, or verify the mapper never turns `Integer null` into `0`. A pure Java unit test cannot verify inbound converter details.

## 23. Observability: Spotting Producer Errors Instead of Masking with Defaults

Suggested metrics and logs:

| Signal | Meaning |
|---|---|
| `transform.accepted.count` | Number of payloads transformed successfully |
| `transform.missing.count` by reason | Which required fields are most often missing |
| `transform.invalid.count` by reason | Out-of-domain or malformed values |
| `transform.default.used.count` by field | Whether optional defaults are overused |
| `transform.error.count` | Runtime failures outside expected validation |
| `transform.duration` | Whether the Transformer is slow or making unintended I/O |
| `router.unmapped.count` | Whether valid new markets lack handlers |
| `dlq/quarantine.count` | Data needing investigation or replay |

These are **suggested metric names**, not necessarily Spring Integration's default meter names. When using Micrometer/observation, include only bounded values like reason codes, endpoints, and schema versions in metric tags. Never use `eventId`, `orderId`, or raw payloads as tags to avoid high cardinality and data leaks.

An investigation workflow should trace: **wire payload → decoder/schema → DTO presence/nullability → validation reason → normalized payload → Router key → handler outcome → error/retry**. Keep event IDs and correlation context in access-controlled traces/logs to follow messages across stages.

**If `MISSING_REGION` spikes suddenly after a producer upgrade**, do not rush to add a `"VN"` default; inspect schema evolution and adapter mappings first.

## 24. Common Pitfalls

**"Default missing fields to avoid `NullPointerException`."** Wrong. Defaulting a required field can change routing, pricing, or authorization.

**"Returning `null` from a Transformer drops a message."** Wrong. Transformers require non-null results; use a Filter, classifier, or rejection result.

**"A field of type `int` cannot be missing."** Wrong at the JSON boundary: primitive defaults can erase field presence information.

**"Blank/missing values are the same as an unsupported route."** No. Blank is a contract violation, whereas `DE` may be valid yet unmapped.

**"Safe navigation in SpEL means input is validated."** Wrong. `?.` and Elvis only guard certain null cases and enforce no business rules.

**"Reading a header named `verifiedRegion` proves it is trustworthy."** Wrong. Control its origin and prevent producers from overwriting it.

**"Retry every Transformer failure."** Wrong. Permanently missing data differs from transient network/DB failures.

**"A payload-returning Transformer never affects correlation."** Do not assume. Verify header propagation and serialization boundaries.

**"Having `defaultOutputChannel` prevents Transformer errors."** Wrong. A Router's default channel only applies once the Router computes a key that has no configured mapping.

**"Catching all `RuntimeException`s and returning `REJECTED` is safe."** Wrong. That disguises code bugs and operational outages as data-validation errors.

## 25. Practice Exercise: Handling Missing Data in Orders

Build an **OrderNormalization** flow as follows:

1. **Ingress:** receive JSON with `schemaVersion` and decode into a nullable DTO, separating parse errors from validation errors.
2. **Validation:** define required fields `eventId, orderId, region, quantity` and policy for `customerNote`.
3. **Transformer:** normalize `region` to uppercase, trim whitespace, build `NormalizedOrder`; apply defaults only to optional fields.
4. **Router:** `VN → orders.vn`, `US → orders.us`, valid new markets to `orders.unmapped`.
5. **Rejection:** try both fail-fast exceptions and `AcceptedOrder/RejectedOrder` result types; pick one primary contract for the application.
6. **Header policy:** supply `verifiedRegion` from an authenticated context; test missing/conflicting cases and source precedence.
7. **Error/retry:** classify validation errors as non-retryable; test error channel or Gateway responses and adapter-level broker recovery.
8. **Correlation:** send an order through Splitter/Transformer/Aggregator, test a line missing a field, and configure failure-result/timeout rules.
9. **Observability:** track missing/invalid/default/route metrics by reason code and schema version.
10. **Contract tests:** test absent JSON fields, explicit `null`, wrong types, new versions, and oversized payloads.

**Completion criteria:** no message missing required fields reaches business consumers; optional field defaults are explicitly documented; Transformer never returns `null`; a reason code explains every rejection; required metadata is retained; retries do not loop endlessly; tests verify both happy and failure paths.

## 26. Key Takeaways

**Handling missing data in a Transformer** is a **data contract** decision, not merely guarding against `NullPointerException`. Clearly separate required and optional fields, distinguish missing from blank/invalid/unsupported, apply defaults only when authorized, and never guess values that affect routing or authorization.

With **Spring Integration**, a safe flow follows **decode → validate → transform → route**, backed by proper rejection/exception paths, preserved correlation, and cause-aware retries. When a Transformer reliably emits either a valid internal payload or an explicit outcome, downstream **Routers, Filters, Gateways, Splitters, Aggregators**, and handlers can stay focused on their own jobs—keeping the message flow stable, testable, and observable.
