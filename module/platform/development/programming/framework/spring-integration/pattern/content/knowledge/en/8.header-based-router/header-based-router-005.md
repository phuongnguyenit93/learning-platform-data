# Header Mapper Before Routing

## 1. Why map headers before routing?

An order processing system receives messages from an **HTTP API**, **Kafka**, and **AMQP**. Producers send market information in a header so the system forwards messages to the appropriate branch: `VN` to `orders.vn`, `US` to `orders.us`, while other data must be classified. However, the three sources do not necessarily represent headers the same way:

- HTTP might send `X-Route-Region: vn` as a text request header.
- Kafka stores record headers as name and `byte[]` pairs; an adapter's deserializer or header mapper might convert them into another type.
- AMQP has its own application headers, properties, and routing key; not all are copied with identical names and types into Spring `MessageHeaders`.

If a Header Router reads `headers['X-Route-Region']` directly while the Kafka adapter only populates a `region` header of type `byte[]`, the expression may find no value or route incorrectly. If a malicious producer attaches `routeKey=orders.admin` and the flow trusts that raw value, using headers can turn into an authorization vulnerability.

**Solution:** design **inbound header mapping and normalization before routing**. Let the Router read only a single stable internal header with a controlled type and value domain; every adapter is responsible for translating its wire contract into that internal contract.

This lesson belongs to the **Header-based router** chapter in the **SPRING_INTEGRATION_PATTERN** module. It is part of practicing **Enterprise Integration Patterns** with Spring Integration to build loosely coupled flows combining **Gateway, Filter, Transformer, Router, Splitter, Aggregator, retry, error channel, correlation**, and per-branch testability and observability.

**After this lesson, you will be able to** distinguish `HeaderMapper` from `HeaderEnricher`, configure a mapping → validate → route pipeline, guard against missing/mistyped headers, design trust policies, and test header mapping across transports.

## 2. Three header layers to distinguish

In a messaging system, the word "header" can refer to several different things:

| Layer | Where it lives | Example | Responsibility |
|---|---|---|---|
| **Transport/native headers** | HTTP request, Kafka record, AMQP message | `X-Route-Region`, Kafka record header bytes | Reflects the protocol and serializer |
| **Spring MessageHeaders** | `Message<?>` inside the JVM | `headers['routeKey']`, `id`, `timestamp` | Holds metadata for internal flows |
| **Business context** | Command, DTO, or application context | `orderId`, verified `tenantId` | Carries business values independent of transport |

A **Header mapper** translates between native headers and `MessageHeaders` at adapter boundaries. A **Header enricher** adds or modifies headers on a Spring message already inside a flow. A **Header Router** reads a header to decide the target channel. They relate to one another, yet none replaces the others' jobs.

~~~mermaid
flowchart LR
    H["HTTP headers / Kafka bytes / AMQP properties"] --> M["Inbound HeaderMapper"]
    M --> I["Spring MessageHeaders: raw"]
    I --> N["Validation + normalization / HeaderEnricher"]
    N --> C["Internal header: routeKey"]
    C --> R{"Header-based Router"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"Invalid"| F["orders.route.rejected"]
~~~

Typically, **inbound mapping happens before the Router receives the message**. Outbound mapping is the reverse direction: when a Spring message is about to be sent over HTTP/Kafka/AMQP, the mapper chooses which headers are emitted and how they are represented on the transport.

Never infer that "the header exists in HTTP" means "Spring `MessageHeaders` has a header of the same name and type." Each adapter, mapper, and allowlist configuration can produce a different result.

## 3. The internal contract must be published upfront

Suppose the system receives an order processing command:

~~~java
record OrderCommand(String orderId, int quantity) {}
~~~

Instead of letting each Router guess between `X-Route-Region`, `region`, or `x-region`, publish a **single internal header**:

| Header | Source | Type in flow | Rules |
|---|---|---|---|
| `routeKey` | Computed from an accepted region | `String` | Only one of `VN`, `US`, `MISSING`, `INVALID`, `UNSUPPORTED` |
| `requestTraceId` | Verified request/trace context | `String` | For observability; never decides authorization |
| `sourceSystem` | Set by the application adapter | `String` or enum | One of `HTTP`, `KAFKA`, `AMQP` |
| `correlationId` | Valid integration/flow process | Type defined by framework/flow | Used when coordinating messages, especially Splitter/Aggregator |
| `tenantId` | Identity/authorization service, if needed | Defined business type | Never copied blindly from client headers |

At ingress, `routeKey` is **not** taken verbatim from an externally supplied header; it must be **rebuilt** from the source header after validation rules run. You may temporarily retain the raw header within the adapter zone for diagnostics, but never let business handlers use it in place of `routeKey`.

A header contract must answer: what is the canonical name, can the value be missing, what is its JVM type, what values are allowed, who has authority to set it, may it leave over another transport, and which channel handles errors.

## 4. How does HeaderMapper differ from HeaderEnricher?

**HeaderMapper** is a protocol bridge. For instance, an HTTP mapper selects certain inbound request headers and places them on a Spring message; a Kafka mapper converts binary record headers into Java values per configuration.

**HeaderEnricher** is an endpoint in a pipeline that already has a `Message<?>`. It can set default headers, extract values from the payload, compute new headers, or remove unneeded metadata. HeaderEnricher does not understand broker deserialization policies if the adapter has not decoded them yet.

| Task | HeaderMapper | HeaderEnricher/Transformer |
|---|---|---|
| Read/write headers from HTTP or Kafka wire format | Suitable | Not directly |
| Choose which native header names enter the Spring message | Suitable | Can re-filter, but does not replace boundary policy |
| Decode header bytes using proper charset/schema | Adapter/mapper fits | Can normalize further after decoding |
| Set normalized `routeKey`, check allowlist | Possible in adapter | Suitable in a dedicated step |
| Compute headers from business payload | Not its default role | Suitable |
| Select target channel | No | **Router** does this |

When you want to reuse the exact same Router for both HTTP and Kafka, the sustainable pattern is **two separate mappers at the boundaries** that both converge onto a single **internal contract** before the Router runs.

## 5. Inbound HTTP header mapping

In Spring Integration HTTP, `DefaultHttpHeaderMapper` selects which inbound request headers are copied into a Spring message. An intentional configuration example:

~~~java
@Bean
DefaultHttpHeaderMapper inboundHttpHeaderMapper() {
    DefaultHttpHeaderMapper mapper =
        DefaultHttpHeaderMapper.inboundMapper();
    mapper.setInboundHeaderNames(
        "X-Route-Region",
        "X-Request-Id"
    );
    return mapper;
}
~~~

This is a **mapper bean**; it only takes effect when **wired into an inbound HTTP adapter/gateway** that supports a `headerMapper` property. Merely declaring the bean does not mean all HTTP requests pass through that mapper. How it attaches, default header sets, and internal names can depend on the adapter and Spring Integration version in use.

Points to verify during testing:

1. Does request header `X-Route-Region` actually appear in Spring `MessageHeaders` after the mapper?
2. Is the header name case-normalized, prefixed, or renamed?
3. If a client sends **multiple values for the same name**, does the mapper pick one value, a list, or reject it?
4. Are non-allowlisted headers stripped as expected?
5. Does the system inadvertently pass `Authorization`, `Cookie`, or credentials into downstream messages/logs?

HTTP headers are **request-supplied data**, not automatically business truth. A client can send `X-Route-Region: VN`; if the route determines which data region a user is allowed to access, combine identity/authorization checks with server-side business data.

**Note on naming conventions:** the example uses `X-Route-Region` externally for clarity. In production code, do not rely on an `X-` convention across every protocol; publish names in a contract and test the mapping.

## 6. Header mapping when receiving Kafka and AMQP

Kafka headers are fundamentally name–`byte[]` pairs. Spring Kafka offers header mapper/converter options, yet how Java types are stored and reconstructed depends on the mapper, serializer, and trust settings. You cannot assume:

~~~java
String region = (String) message.getHeaders().get("X-Route-Region");
~~~

is always valid for every Kafka consumer. If the actual runtime value is still `byte[]`, that cast will fail. A properly managed adapter must define **how to decode**—such as UTF-8 for a published text header—and convert it into a type that the normalization step understands.

Example decoding directly from a Kafka record header inside a custom adapter:

~~~java
Header raw = record.headers().lastHeader("route-region");
String region = raw == null
    ? null
    : raw.value() == null
        ? null
        : new String(raw.value(), StandardCharsets.UTF_8);
// After decoding, still validate syntax, length, and allowed value set.
~~~

This only illustrates logic inside a **transport adapter**, not a complete Spring Integration Kafka configuration. In real systems, explicitly define behavior for missing headers, duplicate header entries, invalid UTF-8 byte sequences, oversized headers, or producer schema changes. Prefer a decoder that errors on malformed bytes rather than silently inserting replacement characters.

AMQP has application headers/properties alongside message properties such as delivery mode, routing key, and correlation. `DefaultAmqpHeaderMapper` (in the AMQP integration layer) controls inbound/outbound mapping. Do not confuse the broker's **AMQP routing key** with the **internal `routeKey`** used by a Spring Integration Header Router; they can serve two entirely different routing layers.

| Source | Data at the boundary | What the adapter must publish |
|---|---|---|
| HTTP | HTTP header names and values | Allowlist, multi-value handling, case normalization |
| Kafka | Record headers as bytes | Header mapper, encoding, type mapping, trust |
| AMQP | Message properties and application headers | Mapped fields, type conversion, separate broker metadata |
| File/polling adapter | Adapter-generated metadata | Canonical names and types; never assume HTTP headers exist |

Across every source, adapters can publish messages onto a shared channel once payloads/headers match the internal contract. **The downstream Header Router does not need to know which protocol the message originated from.**

## 7. Standard pipeline: inbound mapper → normalize → Header Router

Place a single header-adjustment step right after the adapters. This step takes the Spring message and computes the routing key under a unified policy.

~~~mermaid
flowchart TD
    H["HTTP ingress + mapper"] --> RAW["orders.headers.raw"]
    K["Kafka ingress + decoder/mapper"] --> RAW
    A["AMQP ingress + mapper"] --> RAW
    RAW --> P["Header policy: type check, normalize"]
    P --> R{"Header Router: headers.routeKey"}
    R -->|"VN"| V["orders.vn"]
    R -->|"US"| U["orders.us"]
    R -->|"MISSING"| M["orders.route.missing"]
    R -->|"INVALID"| I["orders.route.invalid"]
    R -->|"UNSUPPORTED"| X["orders.route.unsupported"]
    R -.->|"Exception"| E["Dedicated error handling"]
~~~

**Name target channels by purpose**, never using raw external header values as bean names. `MISSING` and `UNSUPPORTED` are distinct states: the first is missing data; the second is populated data without a matching branch yet.

The Header Router can use `HeaderValueRouter` when routing on a single header, or a `headers['routeKey']` expression in Java DSL. Both rely on **mapped and validated headers** and do not substitute for ingress parsing or authorization errors.

## 8. Writing a safe normalization step in Java

A pure Java policy function lets you test mistyped values, nulls, and unsupported keys before invoking the Router.

~~~java
public final class InboundHeaderPolicy {

    public Message<?> normalize(Message<?> source) {
        Object raw = source.getHeaders().get("X-Route-Region");
        String routeKey = toRouteKey(raw);

        return MessageBuilder.fromMessage(source)
            .removeHeader("X-Route-Region")
            .setHeader("routeKey", routeKey)
            .build();
    }

    public String toRouteKey(Object raw) {
        if (raw == null) {
            return "MISSING";
        }
        if (!(raw instanceof String text)) {
            return "INVALID";
        }
        String normalized =
            text.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            return "INVALID";
        }
        return switch (normalized) {
            case "VN", "US" -> normalized;
            default -> "UNSUPPORTED";
        };
    }
}
~~~

This example assumes **the adapter already produced a header named `X-Route-Region` of type `String`** per contract. When Kafka delivers bytes, the adapter must decode prior to this step; if undecoded, the policy intentionally classifies the message as `INVALID` instead of casting blindly. If your adapter uses the name `region`, **fix the boundary mapping** so everything feeds a unified source name, or design the policy to read a unified internal field.

Intentional design choices:

- `null` is classified as `MISSING`.
- Wrong runtime types, blank strings, or empty values are classified as `INVALID`.
- Valid-type but unsupported values like `DE` are classified as `UNSUPPORTED`.
- `VN` and `US` are normalized to uppercase, even if the client sends `" vn "`.
- `setHeader("routeKey", ...)` **overwrites** any `routeKey` that might have been injected externally; raw clients never dictate internal routes.
- The source header is removed after processing so consumers never accidentally rely on unchecked values. If needed for investigation, store limited metadata in an appropriate audit system rather than logging arbitrary payloads.

Example limitation: this class only checks the **routing hint value**; it does not verify market permissions, tenant, payload integrity, or request signatures. Those checks belong in authentication/authorization and business validation layers.

## 9. Wiring the Header Policy to a Router in Spring Integration Java DSL

Declare beans for the policy and flow. The example uses SpEL to read **one internal header**: this style creates an expression router exhibiting **header-based routing** behavior. If only a single header is needed, a dedicated `HeaderValueRouter` can be used instead.

~~~java
@Configuration
@EnableIntegration
class HeaderRoutingFlows {

    @Bean
    InboundHeaderPolicy inboundHeaderPolicy() {
        return new InboundHeaderPolicy();
    }

    @Bean
    IntegrationFlow routeOrdersByHeader(InboundHeaderPolicy policy) {
        return IntegrationFlow.from("orders.headers.raw")
            .transform(policy, "normalize")
            .route("headers['routeKey']",
                r -> r.channelMapping("VN", "orders.vn")
                      .channelMapping("US", "orders.us")
                      .channelMapping("MISSING", "orders.route.missing")
                      .channelMapping("INVALID", "orders.route.invalid")
                      .channelMapping("UNSUPPORTED", "orders.route.unsupported")
                      .defaultOutputChannel("orders.route.unclassified"))
            .get();
    }
}
~~~

Standard imports are omitted. In a real application, configure adapters so sources push decoded messages into `orders.headers.raw`, and register real consumers for each outcome channel.

With input `OrderCommand("O-101", 2)` and header `X-Route-Region = " vn "`, the policy sets `routeKey = "VN"`, and the Router delivers the message to `orders.vn`. The payload remains `OrderCommand`: normalization here primarily updates **headers**, not business data. The handler on `orders.vn` can invoke a use case, persist data, or emit an outbound message per business needs.

**Important:** `defaultOutputChannel` must not be used as a catch-all for every error. If the policy throws an exception or the Router fails to evaluate the expression, a synchronous flow can propagate the error to the caller; an asynchronous flow needs dedicated error handling. The default channel is for keys/destinations unresolved under the router policy, not a `catch` block for runtime exceptions.

### If you only need HeaderValueRouter

`HeaderValueRouter` is built specifically for selecting based on **one header name**. Conceptually, you configure `headerName = "routeKey"`, then define mappings `VN → orders.vn`, `US → orders.us`, plus a default. No custom SpEL expression is needed just to extract that header.

~~~java
HeaderValueRouter router = new HeaderValueRouter("routeKey");
router.setChannelMapping("VN", "orders.vn");
router.setChannelMapping("US", "orders.us");
// In an application, add mappings for MISSING/INVALID/UNSUPPORTED,
// configure the default, and attach the router to a single endpoint/flow.
~~~

In implementation, choose either the Java DSL variant or `HeaderValueRouter` directly; avoid chaining two Routers sequentially just to evaluate `routeKey`. The key difference here lies not in Router syntax, but in **header mapping and normalization discipline prior to routing**.

## 10. Why not use client headers directly as routing keys?

A header might originate from an untrusted actor, get modified by a proxy, vanish across a broker, or carry an unexpected type. Failing to control sources introduces at least four risks:

| Risk | Example | Control |
|---|---|---|
| **Spoofing** | Client sends `X-Tenant-Id=admin` | Derive tenant from authenticated identity, never trust headers alone |
| **Route injection** | Input supplies `orders.privileged` | Map from an allowlisted key set; never resolve channels from arbitrary input |
| **Type confusion** | `routeKey` is bytes/map instead of String | Decode/type-validate before the Router |
| **Untrusted metadata propagation** | Copying tokens or privilege info across every hop | Filter sensitive headers and define outbound mappings |

Even when a value belongs to the allowed set, **it may still be unauthorized for the current sender**. For example, `routeKey="US"` is syntactically valid while the user is only permitted to operate in VN. Authorization decisions must rely on verified identity/context and must not be skipped just because the Router mapped successfully.

Avoid accepting `spring_replyChannel`, `errorChannel`, correlation, tracing, or flow-control metadata as unchecked external input. Orchestration headers can misdirect replies or disrupt error handling if overwritten indiscriminately.

If using SpEL to route, **never build expressions from user-supplied strings**. Expressions are application configuration; external data acts strictly as validated values, never as executable code.

## 11. Missing, mistyped, duplicate, or multi-valued headers

The following cases require deterministic behavior:

| Input after inbound mapper | Sample policy outcome | Things to note |
|---|---|---|
| No `X-Route-Region` | `MISSING` | Do not treat as `VN` or safe default without an explicit rule |
| `null` | `MISSING` | `MessageHeaders` generally omits null entries; verify at boundaries |
| `" "` | `INVALID` | Blank differs from an unknown market |
| Undecoded `byte[]` | `INVALID` | Do not coerce blindly to String |
| `" vn "` | `VN` | Trim + uppercase using `Locale.ROOT` |
| `"US"` | `US` | Supported route |
| `"DE"` | `UNSUPPORTED` | Different from parse error; a branch may be added later |
| Header holds a list of values | `INVALID` if not a String | Adapter needs an explicit multi-value policy |
| Multiple headers with same name in Kafka | Depends on mapper/adapter | Decide first-wins, last-wins, or reject; never guess |

**Do not accidentally allow "last value wins"** for headers affecting authorization or business data if producers can send duplicates. Especially behind reverse proxies, HTTP headers are case-insensitive and may be folded under proxy rules. Include contract tests for multi-value headers and name casing variants.

A production policy can return a `HeaderValidationResult(status, routeKey, reasonCode)` object instead of just a String. A Transformer can then record the status in a dedicated header or route messages to a rejection channel to distinguish missing, wrong-type, malformed, and forbidden cases.

## 12. Inbound and outbound HeaderMappers are not symmetric by default

Configuring which inbound headers to accept does not imply the outbound adapter emits those exact headers. Across protocols, the two directions require separate policies:

~~~text
HTTP / Kafka / AMQP inbound
    └── HeaderMapper IN: allow select native headers
         └── Validation / normalization
              └── Internal flow: routeKey, trace context, eventId
                   └── Outbound adapter
                        └── HeaderMapper OUT: emit only allowed metadata
~~~

For example, `routeKey` is an **internal** orchestration header; if downstream services do not need it, do not expose it in HTTP responses or broker events. Conversely, `eventId` or trace context may need to cross a broker to sustain idempotency/tracing and must be explicitly specified in the wire-format contract.

If an outbound adapter maps all `MessageHeaders` by default, it risks leaking orchestration internals, request contexts, class names, or sensitive data. Specify the outbound header allowlist and serialized types; test actual messages on the wire rather than only checking in-memory Spring messages.

## 13. Correlation and other EIPs across header mapping

A flow may consist of **Gateway → Splitter → Router → Aggregator**. Here `correlationId`, `sequenceNumber`, and `sequenceSize` coordinate grouping. Broken header mapping can cause child messages to be misgrouped or never released.

~~~mermaid
flowchart LR
    G["Gateway: Order O-101"] --> S["Splitter"]
    S --> L1["Line 1 + correlation"]
    S --> L2["Line 2 + correlation"]
    L1 --> HM["Header mapping / normalization"]
    L2 --> HM
    HM --> R{"Header Router: warehouse"}
    R --> A["Warehouse A"]
    R --> B["Warehouse B"]
    A --> AG["Aggregator: correlation O-101"]
    B --> AG
    AG --> RES["OrderSummary"]
~~~

When crossing a broker between Router and Aggregator:

1. Verify that the header mapper propagates the required **correlation key** and sequence metadata.
2. Never use an unverified client-supplied `correlationId` as the sole group key without validating permissions/origin.
3. If a line is rejected due to header mapping or an unsupported route, design a **failure result**, timeout, or release strategy rather than waiting forever for the full group.
4. On redelivery, use a stable event/line ID to avoid computing the same result twice; a fresh `MessageHeaders.ID` does not prevent duplicates.

Header-based Routers also pair with **Filters** to drop ineligible messages, **Transformers** to build internal metadata, and **Gateways** to return results. Each pattern owns one job: HeaderMapper at the protocol boundary, Router selecting the branch, business handlers executing commands, and Aggregator gathering correlated outcomes.

## 14. Distinguishing fallback, rejection, exception, and retry

Not every case that fails to reach `VN`/`US` is the same kind of error:

| Scenario | Suitable handling path | Should it retry? |
|---|---|---|
| Missing region header | `orders.route.missing` | Usually no, unless the source intentionally backfills data |
| Wrong header type/blank | `orders.route.invalid` | Usually no; fix mapper/producer |
| New unsupported region value | `orders.route.unsupported` | Do not blindly retry; follow triage process |
| Router finds no channel | Default route or exception per config | Fix config or add consumer |
| Mapper/Normalizer throws exception | Context-appropriate error handling | Depends on whether the failure is transient |
| Downstream briefly loses DB connectivity | Handler/retry advice or broker policy | Bounded retry + backoff |
| Duplicate from broker redelivery | Service/storage idempotency | Must not cause duplicate side effects |

A **default output channel** mainly handles routing keys without a matching route; it does not catch deserialization failures, type-cast exceptions, expression errors, or handler exceptions automatically. On a `DirectChannel`, exceptions can propagate back to the caller; on an `ExecutorChannel` or polling consumer, configure the corresponding asynchronous error path.

If an outbound adapter fails **after business work already committed**, retrying can rerun the same business operation. Use idempotency keys, transactional outbox, or compensating actions as appropriate. Never confuse a channel accepting a message with downstream processing succeeding.

## 15. Unit testing the header mapping policy

Testing the value table directly on the policy separates normalization bugs from Router bugs:

~~~java
@Test
void normalizesAndClassifiesRegion() {
    InboundHeaderPolicy policy = new InboundHeaderPolicy();

    assertEquals("VN", policy.toRouteKey(" vn "));
    assertEquals("US", policy.toRouteKey("US"));
    assertEquals("MISSING", policy.toRouteKey(null));
    assertEquals("INVALID", policy.toRouteKey(" "));
    assertEquals("INVALID", policy.toRouteKey(new byte[] {86, 78}));
    assertEquals("UNSUPPORTED", policy.toRouteKey("DE"));
}

@Test
void overwritesUntrustedRouteKey() {
    InboundHeaderPolicy policy = new InboundHeaderPolicy();
    Message<OrderCommand> inbound = MessageBuilder
        .withPayload(new OrderCommand("O-101", 2))
        .setHeader("X-Route-Region", " vn ")
        .setHeader("routeKey", "orders.privileged")
        .build();

    Message<?> normalized = policy.normalize(inbound);

    assertEquals("VN", normalized.getHeaders().get("routeKey"));
    assertNull(normalized.getHeaders().get("X-Route-Region"));
    assertEquals("O-101",
        ((OrderCommand) normalized.getPayload()).orderId());
}
~~~

This example uses JUnit 5 and the types defined above. These unit tests do not yet prove that HTTP/Kafka headers actually arrive as the right key; they only verify the policy on an **in-memory Spring message already carrying headers**.

## 16. Integration testing the header → channel flow

In a test context, replace production consumers of `orders.vn`, `orders.us`, and rejection channels with `QueueChannel`s to inspect received messages. Do not declare test queues while simultaneously running production consumers on the same channel names.

Example test body when the context already declares the flow and test target channels:

~~~java
@Autowired
ApplicationContext context;

@Test
void routesMappedHeaderToVietnam() {
    MessageChannel input = context.getBean(
        "orders.headers.raw", MessageChannel.class);
    PollableChannel vn = context.getBean(
        "orders.vn", PollableChannel.class);
    PollableChannel us = context.getBean(
        "orders.us", PollableChannel.class);

    Message<OrderCommand> order = MessageBuilder
        .withPayload(new OrderCommand("O-501", 3))
        .setHeader("X-Route-Region", " vn ")
        .build();

    assertTrue(input.send(order));
    Message<?> routed = vn.receive(1000);

    assertNotNull(routed);
    assertEquals("VN", routed.getHeaders().get("routeKey"));
    assertEquals("O-501",
        ((OrderCommand) routed.getPayload()).orderId());
    assertNull(us.receive(0));
}
~~~

Additional scenarios to test:

| Test | Input | Expected result |
|---|---|---|
| Valid HTTP header | `X-Route-Region: vn` | Mapper imports right type; Router sends to `orders.vn` |
| UTF-8 Kafka header | Bytes of `"US"` | Adapter decodes to String; routes to `orders.us` |
| Undecoded raw Kafka bytes | `byte[]` in Spring header | Policy yields `INVALID`; never casts blindly |
| Missing header | No value present | `orders.route.missing` |
| Blank header | `" "` | `orders.route.invalid` |
| Unsupported region | `"DE"` | `orders.route.unsupported` |
| Spoofed header | Pre-set `routeKey=orders.admin` | Policy overwrites it; never routes outside allowlist |
| Multi-value HTTP header | Two distinct regions | Handled per multi-value policy, never picked implicitly |
| Wrong payload | Not `OrderCommand` | Payload/schema gate or consumer handles per error policy |
| Downstream failure | Service throws exception | Observe error path; not misdiagnosed as header mapping error |
| Cross-broker correlation | Splitter → adapter → Aggregator | Required headers preserved; no cross-group mixing |

**Also test right at the wire boundary.** For HTTP, send real requests in an integration test and inspect the Spring message after the mapper. For Kafka/AMQP, verify data received from a test broker/client and inspect each header's runtime type after mapping. If you only mock prebuilt `MessageHeaders`, you can miss bytes/string issues or adapter header renames.

## 17. Observability: measuring which branch messages take

Every stage of the pipeline should expose enough telemetry for diagnosis:

- **Inbound adapter:** decode success/failure rates, transport kind, schema/mapper version.
- **Header mapper:** which headers were accepted, missing mandatory header counts, type conversion errors.
- **Normalization:** counts of `MISSING`, `INVALID`, `UNSUPPORTED`; never place arbitrary header values into metric labels.
- **Router:** message counts by `VN`, `US`, and rejection branches; default-route hit counts.
- **Consumer:** p95/p99 latency, retries, errors, and queue backlog if applicable.
- **Correlation/tracing:** selective event ID and trace context; avoid logging tokens, cookies, or sensitive payloads.

When debugging "message did not reach the right branch," check in order: **native wire header → inbound mapper → Spring header name/type → normalization outcome → routing key → channel mapping → target consumer → error path**.

If using Micrometer/observation in Spring Integration, name endpoints/channels consistently and keep metric cardinality low. Assign clear ownership to rejection channels so messages do not accumulate unhandled.

## 18. Hands-on exercise: adding Kafka without touching the Header Router

Implement an order processing flow:

1. **Publish the contract:** `OrderCommand`, raw header `X-Route-Region`, and internal header `routeKey` with allowed values.
2. **HTTP inbound:** configure `DefaultHttpHeaderMapper` for only the required request headers and wire it into the adapter.
3. **Header policy:** write `InboundHeaderPolicy` to classify null, mistyped, blank, and unsupported values and normalize to uppercase.
4. **Header Router:** map `VN → orders.vn`, `US → orders.us`, along with rejection routes.
5. **Kafka inbound:** parse the payload, decode Kafka record headers per contract, and push to the same `orders.headers.raw` channel. Do not modify downstream routing logic.
6. **Errors and recovery:** attach owned consumers to rejection channels; distinguish non-retryable mapping errors from retryable transient downstream failures.
7. **Tests:** policy unit tests; per-branch flow tests; HTTP/Kafka contract tests for header types, multi-value headers, and spoofed headers.
8. **Extension:** add Splitter/Aggregator and verify correlation across a broker; observe backlog, timeouts, and incomplete-group behavior.

**Completion criteria:** identical valid region values yield the same routing key and target branch whether arriving over HTTP or Kafka; missing/mistyped headers never reach business branches; channel names never depend directly on untrusted input; outbound header mapping leaks no extra metadata; trace/correlation survives where required; every failure has a tested handling path.

## 19. Takeaways

**Header mapping before routing** keeps boundaries crisp: **native headers → Spring MessageHeaders → validate/normalize → internal routing key → Header Router**. `HeaderMapper` handles protocol translation and data types, `HeaderEnricher`/Transformer handles normalization and metadata enrichment, and the Router chooses the target channel.

Never trust a producer/client header merely because it is present; never confuse fallback channels with error channels; never overlook outbound mapping and correlation when flows cross a broker. Designed this way, Spring Integration scales cleanly across HTTP, Kafka, AMQP, or scheduled sources while keeping routing rules stable, testable, and observable.
