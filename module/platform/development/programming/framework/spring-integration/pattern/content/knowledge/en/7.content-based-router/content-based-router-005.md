# Routing When Data Is Missing or Mistyped

## 1. Why does a Content-Based Router need input defense?

A **Content-Based Router (CBR)** in Enterprise Integration Patterns determines the destination channel from message content. For instance, an order with `region = "VN"` goes to `orders.vn`, and an order with `region = "US"` goes to `orders.us`. When data is always well-formed, writing a Router is straightforward. In real integration systems, however, a message can:

- Have the right payload type yet miss `orderId`, `region`, `quantity`, or a required header.
- Contain `null` fields, blank strings, out-of-range values, or unsupported values.
- Carry an unexpected payload type altogether, such as `String` or `byte[]` instead of `IncomingOrderV1`.
- Have malformed JSON, missing schema fields, or fail deserialization.
- Have a valid type and valid values yet an unconfigured routing key, such as a newly launched market.
- Cause a SpEL expression to throw an exception before any target channel can be resolved.

**Core issue:** "unroutable" is not a single failure category. Routing every problem into one default channel can process bad data by mistake; letting exceptions leak without a policy can cause infinite retries or silent data loss.

This lesson belongs to the **Content-based router** chapter of the **SPRING_INTEGRATION_PATTERN** module. It helps build loosely coupled and extensible messaging flows in Spring Integration, combining **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channels, and correlation**. The goal is selecting the right branch, clarifying input contracts, and testing broken-data paths too.

After this lesson, you can design a CBR resilient to missing/mistyped data, separate fallback routes from error channels, preserve tracing context, and build a test matrix for each case.

## 2. Classifying failures before picking a route

Distinguish at least these six states:

| State | Example | Has a message entered Spring Integration? | Suggested handling path |
|---|---|---|---|
| **Invalid wire format** | Truncated JSON, missing brace | Not necessarily: error may occur in adapter/decoder | Classify deserialization error at ingress; quarantine or reject |
| **Wrong runtime payload type** | `String` instead of `IncomingOrderV1` | Yes, if adapter emitted a String message | Type gate → `orders.rejected.type` |
| **Missing required field** | `quantity = null` | Yes, if DTO was constructed/parsed | Validation → `orders.rejected.missing` |
| **Rule-violating value** | `quantity = -2`, `region = " "` | Yes | Filter/validator → `orders.rejected.value` |
| **Incompatible version** | `schemaVersion = 3` when only v1 is supported | Yes, if DTO decoded | Version gate → `orders.rejected.version` |
| **Valid data, no branch yet** | `region = "DE"`, only VN and US exist | Yes | Router → `orders.unmapped` per policy |

There is also a distinct state: **Router evaluation failure**, such as calling `payload.region()` on the wrong payload type or invoking a method on `null`. That is a **runtime exception**, not a new routing key; setting `defaultOutputChannel` does not turn an exception into "unknown".

Spring messages typically require a non-null payload. When this lesson refers to a "payload missing data", it means a **field inside the payload** is missing or a metadata header is absent; never send `null` to represent a valid event.

## 3. Designing a multi-layer defensive pipeline

Do not force a single Expression Router to handle everything. A clean pipeline looks like this:

~~~mermaid
flowchart TD
    A["HTTP / broker / file input"] --> D{"Decode & schema"}
    D -->|"Cannot parse"| PD["Ingress error / quarantine"]
    D -->|"Parsed"| M["orders.raw: Message<?>"]
    M --> T{"Type & version gate"}
    T -->|"Wrong type"| BT["orders.rejected.type"]
    T -->|"Unknown version"| BV["orders.rejected.version"]
    T -->|"Missing field"| BM["orders.rejected.missing"]
    T -->|"Invalid value"| BI["orders.rejected.value"]
    T -->|"Valid"| N["Transformer: normalized Order"]
    N --> R{"Content-Based Router: region"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"No match"| O["orders.unmapped"]
    T -.->|"Unexpected exception"| ER["Error handling"]
    R -.->|"Unexpected exception"| ER
~~~

The **type/validation gate** states the minimum conditions for a message to enter business processing. The **Transformer** produces a payload with stable structure and normalized values. The **CBR** routes on verified data. Downstream **consumers** execute business logic instead of re-checking protocol-level concerns.

Benefits of separation:

1. Avoids invoking SpEL methods on an incompatible class.
2. Provides separate metrics for type, missing-field, invalid-value, version, and unknown-route issues.
3. Lets you swap HTTP for AMQP/Kafka while keeping application routing logic intact.
4. Allows testing each stage without triggering external services.

Not every flow must use exactly these four endpoints. For small flows, a pure Java classifier can check input validity and return a routing key together; as complexity grows, split validation and routing into separate endpoints for better observability.

## 4. Data contract: representing potentially missing fields properly

Suppose an adapter has decoded a version-1 order message:

~~~java
public record IncomingOrderV1(
    Integer schemaVersion,
    String eventId,
    String orderId,
    String region,
    Integer quantity
) {}

public record ValidatedOrder(
    String eventId,
    String orderId,
    String region,
    int quantity
) {}
~~~

Use `Integer` instead of `int` in the inbound DTO so you can distinguish "the `quantity` field was missing or parsed as null" from "the value is 0". After verification, `ValidatedOrder` uses `int` because nulls are no longer permitted.

**Note:** depending on the JSON library and deserializer settings, a missing field may become a default value, fail parsing immediately, or fail constructor binding. Adapter contract tests must verify this behavior; never assume every missing JSON field becomes Java `null`.

A minimal contract must specify:

| Property | Rule in example | Purpose |
|---|---|---|
| `schemaVersion` | Required, currently supports 1 | Identifies processable schema |
| `eventId` | Non-null/non-blank | Event identity for tracing and deduplication |
| `orderId` | Non-null/non-blank | Order identifier |
| `region` | Non-null/non-blank, uppercased | Market routing key |
| `quantity` | Non-null, greater than 0 | Valid item quantity |

Distinguish **schema validation** from **business validation**. For instance, "`quantity` must be an integer" is a schema requirement, whereas "this customer cannot buy more than 20 items" is a business rule that must still be enforced in the use case even after passing the Filter.

## 5. Type gate: checking runtime type before reading payload properties

A Router using a Java function can branch on payload type and validate fields before forwarding. Using `instanceof` avoids forcing a parser to invoke methods on the wrong object type.

First, define a pure Java classifier. Its output is a **fixed routing key**, never a client-supplied channel name:

~~~java
public final class IngressClassifier {

    public String classify(Object payload) {
        if (!(payload instanceof IncomingOrderV1 order)) {
            return "WRONG_TYPE";
        }
        if (order.schemaVersion() == null) {
            return "MISSING_FIELD";
        }
        if (order.schemaVersion() != 1) {
            return "UNSUPPORTED_VERSION";
        }
        if (order.eventId() == null
                || order.orderId() == null
                || order.region() == null
                || order.quantity() == null) {
            return "MISSING_FIELD";
        }
        if (order.eventId().isBlank()
                || order.orderId().isBlank()
                || order.region().isBlank()
                || order.quantity() <= 0) {
            return "INVALID_VALUE";
        }
        return "VALID";
    }
}
~~~

The check order is intentional: **type → version → required fields → valid values**. An `IncomingOrderV1` with `schemaVersion = null` is classified as missing field rather than "unknown version". Choosing a consistent precedence keeps tests stable and metrics comparable over time.

`classify(Object)` does not write to a database, make HTTP calls, or throw exceptions for expected data defects. It is easy to unit test and reuse regardless of whether input comes from a Gateway, queue, or broker adapter.

## 6. Configuring the Content-Based Router with Java DSL

Plug the classifier into a Spring Integration Router, then map each key to a named channel. A second flow accepts only messages that passed the gate, transforms the data model, and selects the market branch.

~~~java
@Configuration
@EnableIntegration
public class DefensiveOrderRouting {

    @Bean
    IngressClassifier ingressClassifier() {
        return new IngressClassifier();
    }

    @Bean
    IntegrationFlow ingressGate(IngressClassifier classifier) {
        return IntegrationFlow.from("orders.raw")
            .route(Object.class, classifier::classify, r -> r
                .channelMapping("VALID", "orders.accepted")
                .channelMapping("WRONG_TYPE", "orders.rejected.type")
                .channelMapping("MISSING_FIELD", "orders.rejected.missing")
                .channelMapping("INVALID_VALUE", "orders.rejected.value")
                .channelMapping("UNSUPPORTED_VERSION", "orders.rejected.version")
                .defaultOutputChannel("orders.rejected.unclassified"))
            .get();
    }

    @Bean
    IntegrationFlow routeAcceptedOrders() {
        return IntegrationFlow.from("orders.accepted")
            .transform(IncomingOrderV1.class,
                order -> new ValidatedOrder(
                    order.eventId(),
                    order.orderId(),
                    order.region().trim().toUpperCase(Locale.ROOT),
                    order.quantity()))
            .route(ValidatedOrder.class, ValidatedOrder::region,
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .defaultOutputChannel("orders.unmapped"))
            .get();
    }
}
~~~

The example uses Java 17+ for `instanceof` pattern matching and records, along with Spring Integration Java DSL. Imports are omitted for brevity. **Output channels must have real consumers** (Service Activator, outbound adapter, or test receiver); the code intentionally separates classification from per-branch business execution.

The `orders.rejected.*` channels should have handlers recording error codes, source, and event ID (if available), then applying a reject/quarantine policy. Avoid logging raw payloads when sensitive data may be present.

**Note on channel mapping:** Spring Integration versions and configurations may support resolving routing keys directly as channel names alongside declared mappings. Therefore, **do not treat `channelMapping` as your sole security boundary**. Return keys only from a fixed set, explicitly configure channel-key resolution/fallback behavior compatible with your version, and test that an external value cannot route to an arbitrary channel.

### Expected classifier outcomes

| Input payload | First routing key | First channel | Next route |
|---|---|---|---|
| `IncomingOrderV1(1, "E1", "O1", " vn ", 2)` | `VALID` | `orders.accepted` | `orders.vn` |
| `IncomingOrderV1(1, "E2", "O2", "US", 1)` | `VALID` | `orders.accepted` | `orders.us` |
| `IncomingOrderV1(1, "E3", "O3", "DE", 4)` | `VALID` | `orders.accepted` | `orders.unmapped` |
| `"hello"` | `WRONG_TYPE` | `orders.rejected.type` | Order not processed |
| `IncomingOrderV1(1, "E4", "O4", null, 3)` | `MISSING_FIELD` | `orders.rejected.missing` | Transformer not called |
| `IncomingOrderV1(1, "E5", "O5", "VN", -1)` | `INVALID_VALUE` | `orders.rejected.value` | Order not processed |
| `IncomingOrderV1(2, "E6", "O6", "VN", 1)` | `UNSUPPORTED_VERSION` | `orders.rejected.version` | Route to new-version contract |

Messages with the right type yet missing `region` **do not** go to `orders.unmapped`: an unknown region is fundamentally different from a missing field.

## 7. When to use Filter instead of a classifier Router?

The **Filter EIP** answers "may this message continue?", whereas the **Content-Based Router** answers "which path should this message take?". Use a Filter before a Router when there are only two outcomes—**accept** or **reject**—for example:

~~~java
IntegrationFlow.from("orders.parsed")
    .filter(IncomingOrderV1.class,
        order -> order.orderId() != null
            && !order.orderId().isBlank()
            && order.quantity() != null
            && order.quantity() > 0,
        f -> f.discardChannel("orders.rejected"))
    .transform(IncomingOrderV1.class,
        order -> new ValidatedOrder(
            order.eventId(), order.orderId(),
            order.region(), order.quantity()))
    .route(ValidatedOrder.class, ValidatedOrder::region,
        r -> r.channelMapping("VN", "orders.vn")
              .defaultOutputChannel("orders.other"))
    .get();
~~~

**This snippet illustrates the Filter option, not a full equivalent of the multi-branch gate in section 6.** In a real system, validate `eventId` and `region` before the Transformer/Router reads them. If you need distinct error handling per cause (wrong type, missing field, new version, etc.), a multi-branch classifier fits better.

Similarly, using `discardChannel` to send Filter-rejected messages is **not** equivalent to `errorChannel`. A message failing a predicate is an expected outcome; a runtime exception is a case for error handling.

## 8. SpEL expressions when headers or fields may be missing

With a SpEL-based Router, look closely at the difference between:

~~~text
headers['riskLevel']
headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']
headers['riskLevel'] == 'HIGH' ? 'REVIEW' : 'AUTO'
~~~

The third expression sends a **missing header** into the `AUTO` branch. If `AUTO` skips manual review, that is a dangerous decision. Instead, the second expression returns `UNKNOWN` for separate handling.

Example flow routing by header:

~~~java
@Bean
IntegrationFlow riskByHeader() {
    return IntegrationFlow.from("orders.risk.in")
        .route(
            "headers['riskLevel'] == null ? 'UNKNOWN' : headers['riskLevel']",
            r -> r.channelMapping("HIGH", "orders.review")
                  .channelMapping("LOW", "orders.auto")
                  .channelMapping("UNKNOWN", "orders.risk.missing")
                  .defaultOutputChannel("orders.risk.unsupported"))
        .get();
}
~~~

If the header has `" "` or `"MEDIUM"`, it is not `null`; the message lands in the unsupported branch under the current mapping (assuming fallback behaves as expected). You can add a header check/normalization step to separate blank strings from unpublished values.

For a record payload, `payload.region()` invokes the accessor method. If an earlier Transformer changed the payload type to `String`, calling that method fails. An expression with null-safe navigation can handle **a null property**, but cannot replace **payload type checking**. Use a type gate before the Router instead of trying to write one giant SpEL expression to cope with every possible type.

**Security:** never concatenate user-supplied input into a SpEL string for evaluation. Use fixed expressions managed by the application; payloads and headers supply **values**, never expression code or arbitrary channel names.

## 9. Default output channel is not an error channel

This is the most important boundary when data has problems:

| Scenario | Does default output channel handle it? | Why? |
|---|---|---|
| Valid routing key not in expected routes | **Yes, when Router is configured accordingly** | Router computed a key, just found no matching route |
| Classifier returned `UNKNOWN` for a header | **Possible** | Key can be mapped explicitly or fall back to default |
| Expression calls a nonexistent method on payload | **No** | Evaluation failed before any routing key was produced |
| JSON fails to parse at inbound adapter | **No** | Message never reached the Router |
| Handler on target channel throws an exception | **No** | Router already delivered the message to target |
| Target queue is full or channel lacks subscribers | **Not necessarily** | Send/delivery failure differs from an unmapped key |

What happens when a Router cannot resolve a channel depends on resolution/fallback options. For critical transactions, always design an explicit fallback route or exception policy and test the behavior on your exact Spring Integration version.

An **error channel** serves error-handling flows for supporting endpoints/adapters, especially in asynchronous scenarios. In a synchronous flow over `DirectChannel`, exceptions typically propagate back to the caller/Gateway. Do not assume simply naming a channel `errorChannel` means every exception on every thread goes there.

## 10. Placing parsing error boundaries outside the Router

Suppose HTTP or a broker sends:

~~~json
{
  "schemaVersion": 1,
  "eventId": "E-100",
  "orderId": "O-100",
  "region": "VN",
  "quantity": "abc"
}
~~~

If the schema requires `quantity` to be an integer, the JSON is syntactically valid yet **violates the contract**. Depending on Jackson and coercion settings, the deserializer may fail or attempt conversion; test your actual configuration. Never force `"abc"` into an `Integer` via manual casting inside a Router.

When using an adapter that decodes explicitly, illustrative code:

~~~java
public IncomingOrderV1 decode(byte[] json, ObjectMapper mapper)
        throws JsonProcessingException {
    return mapper.readValue(json, IncomingOrderV1.class);
}
~~~

`decode` runs **before** an `IncomingOrderV1` payload is sent to `orders.raw`. On failure, the adapter should record a deserialization error code, return an appropriate HTTP response, or apply broker ack/reject/DLQ policies. Only on successful decode should the message enter the CBR.

For untrusted sources, enforce size limits, nesting depth limits, type allowlists, and avoid unrestricted polymorphic deserialization. Never let clients specify classes or arbitrary SpEL expressions. Use schema versioning and producer/consumer compatibility tests before upgrading contracts.

## 11. When version, type, and missing fields occur together

A message can fail multiple checks at once: unknown version, missing `region`, and `quantity = -1`. If a Router returns **one** key, define precedence rules. For example, the classifier in section 5 checks version before checking the remaining fields.

Three design options:

1. **Fail-fast single error code:** take the first failure in a published order; simple and well-suited for a routing gate.
2. **Aggregate multiple errors into a validation result:** return a list of errors from a validator; suitable when detailed feedback or full error reporting is needed.
3. **Version-specific decoder/adapter:** separate v1 and v2 into distinct contracts before building a unified internal model; suitable when schemas diverge significantly.

Avoid patching every version together with an uncontracted `Map<String,Object>`. For instance, if v2 changes the meaning of `region`, routing with the same expression sends messages to the wrong branch without throwing any exception. Semantic errors are far more dangerous than obvious type errors.

Define clearly when an unknown version can enter a compatibility workflow and when it must be rejected. The market Router's `defaultOutputChannel` is not the place to handle new schema versions.

## 12. Retry, idempotency, and recovery policies

Not every bad message is worth retrying:

| Error type | Retry? | Handling direction |
|---|---|---|
| Malformed JSON / undecodable payload | Usually no | Reject/quarantine, save enough metadata to investigate |
| Wrong payload type due to producer contract violation | Usually no | Alert producer–consumer contract mismatch |
| Missing required field | Usually no | Return schema/validation error code |
| Unknown version | Depends on rollout process | Wait for adapter support or managed DLQ/quarantine |
| Valid key with unsupported route | Never retry blindly | Default channel with an owner, classify later |
| Timeout from downstream service | Possible | Bounded retries, backoff, and circuit breaker as needed |
| Network error to broker | Possible | Retry per adapter, verify delivery, avoid duplicate emit |

**A retry can re-execute the entire handler.** If a handler updates the database and then fails while sending a reply, retrying can cause duplicate side effects. Use an **eventId/idempotency key**, unique constraints, transaction/outbox patterns, or an equivalent mechanism per your design. `MessageHeaders.ID` can change when a message is reconstructed; it is not a unique business deduplication key.

When error handling sits in a synchronous flow, the caller can catch exceptions. When using `ExecutorChannel` or a polled `QueueChannel`, configure error paths for asynchronous execution. With brokers, ack/nack, redelivery, and DLQs depend on the inbound adapter/container; they do not activate automatically just because you created a channel named "error".

## 13. Correlation when a Router branches

Suppose an order is split into three lines by a Splitter, each line goes through a CBR to different warehouses, and an Aggregator combines the results. If one line has missing or mistyped data, you must resolve **the whole workflow**, not just the single failed message:

~~~mermaid
flowchart TD
    O["Order O-101"] --> S["Splitter"]
    S --> L1["Line 1, correlation O-101"]
    S --> L2["Line 2, correlation O-101"]
    S --> L3["Line 3, correlation O-101"]
    L1 --> R["Type/validation gate + Router"]
    L2 --> R
    L3 --> R
    R -->|"Valid"| W["Warehouse handlers"]
    R -->|"Missing data"| REJ["Rejected line"]
    W --> A["Aggregator"]
    REJ --> POLICY["Group failure policy"]
    POLICY --> A
~~~

Decide up front:

- Which `correlationId` ties lines to the same order; whether `sequenceNumber` and `sequenceSize` survive transformers/adapters.
- Whether invalid messages are converted into a **failure result** so the Aggregator completes the group, or whether the group times out and reports an incomplete state.
- If a line is dropped by a Filter, how the release strategy knows a member is missing.
- Whether duplicate/redelivered messages can cause the Aggregator to receive one line multiple times; whether an appropriate message store or deduplication is in place.

**Never wait forever for a full group** if a line is rejected. Design timeouts, expired-message handling, compensation, or group failure reporting per business requirements, along with correlation tracing for investigation.

## 14. Testing from unit classifier to full flow

The classifier can be unit tested as plain Java, without Spring Integration:

~~~java
@Test
void classifiesMissingFieldsAndWrongType() {
    IngressClassifier classifier = new IngressClassifier();

    assertEquals("WRONG_TYPE", classifier.classify("not-an-order"));
    assertEquals("MISSING_FIELD", classifier.classify(
        new IncomingOrderV1(1, "E-1", "O-1", null, 2)));
    assertEquals("INVALID_VALUE", classifier.classify(
        new IncomingOrderV1(1, "E-2", "O-2", "VN", 0)));
    assertEquals("UNSUPPORTED_VERSION", classifier.classify(
        new IncomingOrderV1(2, "E-3", "O-3", "VN", 2)));
    assertEquals("VALID", classifier.classify(
        new IncomingOrderV1(1, "E-4", "O-4", " vn ", 2)));
}
~~~

For integration tests, you can replace production consumers on target channels with `QueueChannel` instances in a **test configuration**. Send messages to `orders.raw`, then `receive(timeout)` on the expected channel and verify **all other channels receive nothing**. Do not register both a test queue and a production handler on the same channel name simultaneously.

A test matrix should cover:

| Case | Data | Expected result |
|---|---|---|
| Valid market, unnormalized | `region=" vn "` | `orders.vn`, normalized payload |
| Another valid route | `region="US"` | `orders.us` |
| New but valid market | `region="DE"` | `orders.unmapped` |
| Wrong payload class | `String`, `byte[]` | `orders.rejected.type`, Transformer not invoked |
| Missing order ID | `orderId=null` | `orders.rejected.missing` |
| Missing quantity | `quantity=null` | `orders.rejected.missing` |
| Invalid quantity | `quantity=-1` | `orders.rejected.value` |
| Unsupported version | `schemaVersion=2` | `orders.rejected.version` |
| Unparseable JSON | Broken wire bytes | Adapter error, never enters `orders.raw` |
| Missing required header | No `riskLevel` | Designated missing/unknown branch |
| SpEL/handler throws error | Missing method or handler error | Exception/error handling, not treated as unmapped |
| Two orders through Splitter | Interleaved/shared correlation IDs | No group mixing; intentional timeout/rejection |

### Example integration test for one path

Assuming the test context provides `orders.vn` as a `PollableChannel` without registering a production consumer of the same name:

~~~java
@Autowired
ApplicationContext context;

@Test
void sendsValidatedOrderToVn() {
    MessageChannel input =
        context.getBean("orders.raw", MessageChannel.class);
    PollableChannel vn =
        context.getBean("orders.vn", PollableChannel.class);

    Message<IncomingOrderV1> inputMessage = MessageBuilder
        .withPayload(new IncomingOrderV1(
            1, "E-10", "O-10", " vn ", 3))
        .setHeader("correlationId", "O-10")
        .build();

    assertTrue(input.send(inputMessage));
    Message<?> output = vn.receive(1000);

    assertNotNull(output);
    assertInstanceOf(ValidatedOrder.class, output.getPayload());
    assertEquals("VN",
        ((ValidatedOrder) output.getPayload()).region());
    assertEquals("O-10",
        output.getHeaders().get("correlationId"));
}
~~~

This is an illustrative test body: your test suite must initialize the flow, match input/channel bean names, and replace target consumers with appropriate queues. For async flows, use bounded timeouts or conditional assertions; avoid fixed `Thread.sleep` calls to gauge completion.

## 15. Observing routing errors in operations

A "lost message" report can usually be diagnosed by inspecting data at each boundary:

| Observation point | Recommended metrics/logs | Question answered |
|---|---|---|
| Inbound adapter | Decode success/failure, schema version | Did the message reach the Router? |
| Type gate | Rates of WRONG_TYPE, MISSING_FIELD, INVALID_VALUE | Are producer inputs honoring the contract? |
| Normalizer | Transform errors, field normalization | Did data change unexpectedly before/after? |
| Content-Based Router | Count by key/channel, fallback count | Is the route seeing new unsupported keys? |
| Target consumer | Processing duration, timeouts, failed count | Did it finish or stall in a branch? |
| Error/retry | Retry attempts, DLQ/quarantine, error category | Are permanent errors being retried by mistake? |
| Aggregator | Correlation ID, group size, expiry | Did a rejected child leave a group incomplete? |

Never put raw payloads or customer details into metric tags; use bounded error codes and standardized route names to prevent **high cardinality**. Use Spring's observation/tracing mechanisms when configured to correlate logs across Gateway, Filter, Transformer, Router, adapters, and handlers.

When investigating misrouted messages, trace step by step: **wire format → runtime type → validation result → normalized payload → routing key → mapping/fallback → downstream channel/consumer → exception path**. Structured tracing finds root causes faster than inspecting only the final handler's logs.

## 16. Common pitfalls

**Calling accessors too early.** Evaluating `payload.region()` before confirming the payload is `IncomingOrderV1` risks runtime errors. Type gate first, business Router second.

**Lumping missing fields and unknown keys into the same default.** `region=null` violates the contract; `region="DE"` may be valid data not yet supported. The two cases require different policies.

**Believing default channel catches all exceptions.** Default does not catch deserialization failures, SpEL errors, or handler exceptions. Define error paths per synchronous/asynchronous boundary.

**Confusing Filter discard with an error channel.** A Filter dropping a message by predicate differs from code throwing an exception. If you need to know *why* a message failed, return meaningful error keys or structured validation results.

**Using `Map`/`String` payloads across every layer.** Every handler ends up parsing and casting, increasing runtime failures. Decode once at ingress and move to an explicit contract.

**Building expressions or arbitrary channel names from input.** Untrusted input must never choose classes, SpEL code, or channels outside an allowlist.

**Retrying invalid data infinitely.** Schema/type errors are usually resolved only at the producer or after migration. Retry only transient causes, with idempotency and bounds.

**Testing only the happy path.** A Router may work for VN/US while mishandling missing `quantity`, `riskLevel`, or new versions. A malformed-input test matrix is a mandatory part of the contract.

**Ignoring Splitter/Aggregator group impacts.** A rejected child message can make an Aggregator expire or wait forever. Decide failure-result, timeout, and compensation policies.

## 17. Comprehensive practice exercise

Build the **DefensiveOrderRouter** flow in Spring Integration step by step:

1. **Ingress:** receive JSON from an adapter and build `IncomingOrderV1`. Separate parse errors from the message flow.
2. **Type/version gate:** classify `WRONG_TYPE`, `MISSING_FIELD`, `INVALID_VALUE`, `UNSUPPORTED_VERSION`, and `VALID`.
3. **Transformer:** uppercase-normalize `region` and convert to `ValidatedOrder`.
4. **Content-Based Router:** `VN → orders.vn`, `US → orders.us`, others to `orders.unmapped`.
5. **Header router:** inspect `riskLevel`; missing headers must take a dedicated branch rather than silently defaulting to low risk.
6. **Error handling:** give every rejection channel a receiver; design exception/error channels and a retry policy for transiently failing handlers.
7. **Testing:** write classifier unit tests and integration tests with target queues, proving no malformed message leaks into a business branch.
8. **Extension:** split line items and aggregate results; test a missing child message, timeouts, redelivery, and correlation preservation.

**Completion criteria:** a data-contract table, branch diagram, tests covering missing/wrong-type/version/unknown-route cases, cause-based retry policies, per-channel routing metrics, and an end-to-end trace example from ingress to final outcome.

## 18. Key takeaways

**Routing when data is missing or mistyped** should not rely on one complex expression trying to guess every case. In Spring Integration, separate **decode → type gate → validate → transform → content-based route → business handler**. Rejected data gets explicit reasons and receivers; valid yet unsupported keys use fallbacks; runtime exceptions follow proper error handling.

Combined with **Filter, Transformer, Gateway, Splitter/Aggregator, retry, error channels, and correlation**, a defensive CBR keeps message flows both adaptable to new data and safe against broken data, while remaining easy to test and observe in distributed environments.
