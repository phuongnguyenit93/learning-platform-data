# Headers Lost Across Adapters

## 1. A hard-to-spot routing incident

In Spring Integration, a **Header-based Router** reads information in **message headers** to pick an output channel. For example, header `routeRegion=VN` sends an order to the domestic branch, while `routeRegion=INTL` sends it to the international branch. This model decouples dispatch logic from payloads and business handlers.

However, when a message crosses an **inbound/outbound adapter or gateway** for HTTP, JMS, Kafka, AMQP, files, or another transport, headers can be filtered out, renamed, coerced to a different type, or omitted from the wire protocol. The receiving Router sees the header missing and cannot route—even though the sending side worked properly.

~~~mermaid
flowchart TD
    A["Message<Order>: routeRegion=VN"] --> B[Outbound Adapter]
    B --> C{Header mapping}
    C -->|Mapped| D[Transport has route metadata]
    C -->|Dropped header| E[Transport missing route metadata]
    D --> F[Inbound Adapter]
    E --> F
    F --> G{HeaderValueRouter}
    G -->|VN| H[(orders.vn)]
    G -->|INTL| I[(orders.intl)]
    G -->|Missing/invalid| J[Rejection / error flow]
~~~

This is a failure in the **metadata handoff contract**, not necessarily a Router bug. If you simply add a default route to mask a missing header, the application might accidentally send international orders into the domestic branch. Always trace the **header's path at every boundary** before altering routing policies.

This lesson belongs to the **Header-based router** chapter of the `SPRING_INTEGRATION_PATTERN` module: implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Preserving metadata affects Router, Filter, Transformer, Gateway, Splitter/Aggregator, retry, error channel, correlation, and testability/observability.

**Objectives:** identify where headers get dropped, distinguish Spring `MessageHeaders` from transport headers, configure `HeaderValueRouter` accurately, restore headers in a controlled manner, test across adapters, and fail closed when routing metadata is gone.

## 2. Distinguishing header layers

### 2.1. Spring Message headers

In Spring Messaging, `Message<T>` has a payload and `MessageHeaders`. For example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> order = MessageBuilder.withPayload("ORD-1001")
        .setHeader("routeRegion", "VN")
        .setHeader("traceId", "trace-ord-1001")
        .setHeader("sourceSystem", "checkout")
        .build();

String region = (String) order.getHeaders().get("routeRegion");
// region == "VN"
~~~

For flows within the same application, endpoints receiving `Message<?>` can read these headers. Yet when sending data over an external transport, Spring has to map metadata onto that protocol's format. There is no guarantee that all `MessageHeaders` are mapped or even serializable.

| Layer | Example | Responsibility |
|---|---|---|
| Spring MessageHeaders | `routeRegion=VN` | The value `HeaderValueRouter` needs to read. |
| Outbound header mapper | `routeRegion` → `x-route-region` | Selects keys/types allowed to leave the application. |
| Transport | HTTP header, Kafka header bytes, JMS property | Stores/transports according to protocol rules. |
| Inbound header mapper | `x-route-region` → `routeRegion` | Reads and normalizes back into internal headers. |
| Receiving Router | `HeaderValueRouter("routeRegion")` | Routes based on the normalized key. |

The name `routeRegion` **does not automatically equate** to HTTP `X-Route-Region` or a Kafka header of the same name. A specific adapter may allow only certain headers, add prefixes, alter types, or drop custom headers if unconfigured.

### 2.2. Header categories and cross-boundary propagation

| Header | Purpose | When crossing an adapter |
|---|---|---|
| `routeRegion`, `tenantId` | Pick branch by region/tenant | Requires mapping and **source trust verification**. |
| `traceId` / trace context | Link logs and distributed traces | Requires propagation matching protocol/tracing conventions. |
| `correlationId` | Group related messages | Critical when Splitter/Aggregator spans processes. |
| `sequenceNumber`, `sequenceSize` | Describe group position/size | Needs consistent type and semantics if used remotely. |
| `replyChannel` | Return address for internal request–reply | May be a JVM channel object; do not send raw object across JVMs. |
| `errorChannel` | Internal error handling destination | Does not automatically become a broker error destination. |
| `id`, `timestamp` | Message identity/creation time | May be regenerated when creating a new message. |
| `history` | Spring Integration Message History | Not a durable distributed trace across multiple services. |

**Do not pick "send all headers" as a default solution.** Some headers hold non-serializable objects; some contain sensitive data; some only make sense inside the current JVM. At system boundaries, define an **allowlist** of metadata, encoding rules, and access controls.

## 3. Common causes of lost headers

| Cause | Symptom | What to check |
|---|---|---|
| Outbound mapper filters out headers | Spring message has `routeRegion`, but outgoing request/record lacks it. | Outbound header names/patterns list, adapter configuration. |
| Inbound mapper fails to restore | Protocol carries `x-route-region`, but receiving Spring message lacks `routeRegion`. | Inbound mapper, decoder, normalization step. |
| Inconsistent header names | Sender sets `routeRegion`, receiving router reads `region`. | Naming contract, casing, and prefixes. |
| Value type changed | Header arrives as `byte[]`, router expects `String`. | Charset, converter, typed mapper. |
| New message built from payload only | Headers vanish after a custom transformer/adapter. | Whether `MessageBuilder.withPayload(...).build()` copied headers. |
| Unserializable header | Internal `replyChannel` object is skipped or errors out. | Reply/correlation protocol instead of shipping JVM objects. |
| Gateway builds a fresh reply | Request had the route header, response message does not. | Reply/response mapping contract. |
| Chained adapters | Header lost at the second or third hop. | Observe message and protocol at **every hop**. |
| Explicit removal step | `.removeHeaders(...)` or metadata-scrubbing handler. | Header filtering policy, security rules, and transformation order. |

**HTTP:** custom headers in an HTTP request/response must be permitted by the inbound/outbound gateway's header mapper. When normalizing HTTP `X-Route-Region` into `routeRegion`, verify the actual data type the application receives. Never trust headers supplied by public clients to determine tenant or permissions.

**Kafka:** Kafka record headers store values as bytes, while Spring `MessageHeaders` may hold objects decoded by a converter. Mapping behavior depends on Spring for Apache Kafka and serializer/converter configuration; do not assume the receiving side always gets a `String`.

**JMS/AMQP:** property/header names and types, transport metadata, and mapper policies differ. Do not treat them as channels for serializing arbitrary Java objects, especially internal `replyChannel` and `errorChannel` instances.

**File/CSV/JSON:** file contents may contain only the payload with no metadata to recover. If routing metadata is needed after reading a file, design an envelope, manifest, or authoritative lookup source rather than guessing lost header values.

## 4. How does HeaderValueRouter read headers and pick channels?

### 4.1. Three concepts to keep separate

~~~text
Message<Order> (routeRegion=VN)
             |
             v
HeaderValueRouter("routeRegion")
             |
        routing key VN
             |
        channelMapping
             |
          orders.vn
             |
        Domestic Handler
~~~

| Component | Example | Role |
|---|---|---|
| Header name | `routeRegion` | The key the Router looks up in `MessageHeaders`. |
| Header value / routing key | `VN` | Metadata-driven routing decision. |
| Channel destination | `orders.vn` | Target channel bean receiving the message. |

A header can have **the right name but wrong value type**, or **the right value under a different name**. Therefore, diagnostics must examine name, type, data source, and target mapping together.

### 4.2. Three header failure modes

1. **Missing:** `routeRegion` is absent.
2. **Invalid:** header exists, but is not in the allowed set—such as `UNKNOWN` or undecoded bytes.
3. **Untrusted:** `VN` looks valid, yet was self-declared by an unauthenticated external sender.

Do not paper over a missing case by defaulting to `VN` unless business rules permit it. Where tenant or regional isolation is required, that can be a severe security flaw.

### 4.3. Choosing a policy when a header is unusable

| Situation | Strategy to consider |
|---|---|
| Mandatory routing metadata was lost | Fail closed, record missing-header event; do not send arbitrarily to a valid branch. |
| Region outside supported set | Business rejection or `unroutable` branch with an explicit consumer. |
| Wrong value type after mapping | Normalize/decode/validate at the boundary. |
| Header sent by untrusted client | Authenticate first, then re-derive info from authorized data. |
| Mapping bug in a deployment | Fail fast and alert; do not hide bugs behind a default route. |

## 5. Java DSL example: routing on a qualified header

This example targets **Java 17+, Spring Boot 3.x, and Spring Integration 6.x** with the `spring-boot-starter-integration` dependency. It includes a Gateway setting `routeRegion`, a `HeaderValueRouter`, and two receiving channels. This covers the **internal path** and does not yet test real adapters.

~~~mermaid
flowchart LR
    G[OrderGateway] --> I[(orders.input)]
    I --> R{HeaderValueRouter: routeRegion}
    R -->|VN| V[(orders.vn)]
    R -->|INTL| X[(orders.intl)]
    R -. Missing / unknown .-> E[Failure / error flow]
    V --> VH[VN Handler]
    X --> XH[International Handler]
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.handler.annotation.Header;

record Order(String orderId, long amount) {}
record Receipt(String orderId, String route, String status) {}

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orders.input")
    Receipt submit(Order order, @Header("routeRegion") String region);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class HeaderRegionRoutingConfig {

    @Bean(name = "orders.input")
    MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "orders.vn")
    MessageChannel domestic() {
        return new DirectChannel();
    }

    @Bean(name = "orders.intl")
    MessageChannel international() {
        return new DirectChannel();
    }

    @Bean
    HeaderValueRouter regionRouter() {
        HeaderValueRouter router = new HeaderValueRouter("routeRegion");
        router.setChannelMapping("VN", "orders.vn");
        router.setChannelMapping("INTL", "orders.intl");
        router.setChannelKeyFallback(false);
        router.setResolutionRequired(true);
        return router;
    }

    @Bean
    IntegrationFlow routeOrders(HeaderValueRouter regionRouter) {
        return IntegrationFlow.from("orders.input")
                .route(regionRouter)
                .get();
    }

    @Bean
    IntegrationFlow processDomesticOrders() {
        return IntegrationFlow.from("orders.vn")
                .handle(Order.class, (order, headers) ->
                        new Receipt(order.orderId(), "VN", "ACCEPTED"))
                .get();
    }

    @Bean
    IntegrationFlow processInternationalOrders() {
        return IntegrationFlow.from("orders.intl")
                .handle(Order.class, (order, headers) ->
                        new Receipt(order.orderId(), "INTL", "PENDING_EXPORT"))
                .get();
    }
}
~~~

**Explanation:**

- `@MessagingGateway` converts a Java call into a message and waits for a reply.
- `@Header("routeRegion")` specifies the header used for routing. Callers must be controlled or have a verified region.
- `setChannelMapping` decouples **keys `VN`/`INTL`** from channel beans `orders.vn`/`orders.intl`.
- `setChannelKeyFallback(false)` prevents unmapped keys from being tried as channel bean names; `setResolutionRequired(true)` requires a resolved target.
- `DirectChannel` is convenient for synchronous request–reply examples; the `Receipt` return value is illustrative, not real broker/database processing.

An internal caller can invoke:

~~~java
Receipt vn = orderGateway.submit(
        new Order("ORD-101", 200_000L), "VN");
// vn.route() == "VN" and vn.status() == "ACCEPTED"

Receipt intl = orderGateway.submit(
        new Order("ORD-102", 200_000L), "INTL");
// intl.route() == "INTL" and intl.status() == "PENDING_EXPORT"
~~~

This sample proves the Router works when headers are intact, **not** that HTTP/Kafka/JMS adapters forwarded the header successfully. Boundary propagation must be tested separately.

## 6. Reproducing header loss when building a new message

### 6.1. Common mistake: copying only the payload

Suppose a custom adapter receives a message and builds a new message solely from the payload:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> source = MessageBuilder.withPayload("ORD-1001")
        .setHeader("routeRegion", "VN")
        .setHeader("traceId", "trace-1001")
        .build();

// Wrong: only forwards payload, omitting routing metadata.
Message<String> broken = MessageBuilder
        .withPayload(source.getPayload())
        .build();

System.out.println(source.getHeaders().get("routeRegion")); // VN
System.out.println(broken.getHeaders().get("routeRegion")); // null
~~~

This snippet **intentionally drops headers** to illustrate the problem. Do not conclude that every `Transformer` in Spring Integration drops headers: framework infrastructure preserves headers across many endpoint types; risk arises when custom code, adapters, or converters reconstruct messages without honoring the contract.

If `broken` continues into `HeaderValueRouter("routeRegion")`, the router has no value to select a channel. Adding `defaultOutputChannel("orders.vn")` only makes the bug harder to spot and risks misrouting.

### 6.2. Creating a new message while preserving internal metadata

When you genuinely need to copy headers within the **same trust zone**, build from the original message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> preserved = MessageBuilder
        .fromMessage(source)
        .build();

System.out.println(preserved.getHeaders().get("routeRegion")); // VN
System.out.println(preserved.getHeaders().get("traceId")); // trace-1001
~~~

Or when changing the payload:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<NormalizedOrder> normalize(Message<Order> input) {
    Order original = input.getPayload();
    NormalizedOrder normalized =
            new NormalizedOrder(original.orderId(), original.amount());

    return MessageBuilder.withPayload(normalized)
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`NormalizedOrder` here is an illustrative DTO that must be defined in the application if used. Calling `copyHeaders` **does not** mean all headers should cross out to an external transport. You still need to filter per the outbound contract, especially for objects like `replyChannel`, `errorChannel`, and security metadata.

### 6.3. Lost headers cannot be recovered without a source

If the `broken` message only has a string `ORD-1001`, no transport headers, no region inside the payload, and no independent verified source, **no transformation can accurately recover `routeRegion`**. Do not guess `VN` from an ID prefix or inject a default just to keep the flow moving.

Valid recovery options are:

1. **Fix the boundary mapper** on the sending/receiving side to retain expected metadata per the allowlist.
2. **Recompute from a trusted source** if the business contract allows, such as looking up the region from a verified order record.
3. **Reject and request redelivery** when mandatory metadata is missing.
4. **Route to a quarantine/manual recovery branch** designed with clear access controls, retention, and replay policy.

## 7. Controlled header mapping across transport boundaries

### 7.1. Designing a minimal envelope

The example below simulates how an adapter **encodes** a message onto the wire and how an inbound adapter **decodes** it back. This is standalone Java code illustrating the mapping contract, **not built-in configuration for HTTP, Kafka, or JMS adapters**:

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record WireEnvelope(Order payload, Map<String, String> metadata) {}

final class TransportOrderMapper {
    private static final Set<String> ALLOWED_REGIONS =
            Set.of("VN", "INTL");

    WireEnvelope encode(Message<Order> message) {
        Object raw = message.getHeaders().get("routeRegion");
        if (!(raw instanceof String region)
                || !ALLOWED_REGIONS.contains(region)) {
            throw new IllegalArgumentException(
                    "Missing or invalid routeRegion before sending");
        }

        // Illustrative contract: pass only allowed metadata.
        return new WireEnvelope(
                message.getPayload(),
                Map.of("x-route-region", region));
    }

    Message<Order> decode(WireEnvelope wire) {
        String region = wire.metadata().get("x-route-region");
        if (region == null || !ALLOWED_REGIONS.contains(region)) {
            throw new IllegalArgumentException(
                    "Missing or invalid region after transport");
        }

        return MessageBuilder.withPayload(wire.payload())
                .setHeader("routeRegion", region)
                .build();
    }
}
~~~

**Meaning:** the transport uses `x-route-region`; the internal router uses `routeRegion`. The mapper is where **names and types are translated**. This contract surfaces missing metadata clearly rather than silently routing to an inaccurate default channel.

**Security limitation:** `decode` only checks that the region is **syntactically valid**; it does not verify the sender is authorized to pick that region. On a public ingress or partner-facing consumer, authenticate the source and determine the region from authorized data rather than trusting a self-declared external header.

### 7.2. How to map headers per transport

With real adapters, design an **explicit contract** instead of wildcarding every header:

| Transport | What to configure/inspect | Diagnostic question |
|---|---|---|
| HTTP | Inbound/outbound header mapper; HTTP name, multi-value, casing/prefix, response mapping | Does `X-Route-Region` appear on the wire and normalize to `routeRegion`? |
| Kafka | Record header bytes, serializer/converter/header mapper, header patterns | How are `routeRegion` bytes encoded in the record; does the consumer receive `byte[]` or `String`? |
| JMS | Property/header mapping, allowed types, property naming | Are application attributes sent as properties and read back cleanly? |
| AMQP | Message property/header mapping, converter, and broker policy | Did `routeRegion` enter AMQP headers and return to Spring headers? |
| File/CSV | Schema/envelope/manifest | Does the file store routing metadata or only payload? |
| Custom adapter | `Message<?>` ↔ protocol conversion function | Does code call `MessageBuilder.withPayload` and forget headers? |

Do not proliferate arbitrary data types. For Kafka, if the application intentionally reads a byte header under a UTF-8 contract, decode with explicit checks:

~~~java
import java.nio.charset.StandardCharsets;

String decodeRegion(Object raw) {
    if (raw instanceof String region) {
        return region;
    }
    if (raw instanceof byte[] bytes) {
        return new String(bytes, StandardCharsets.UTF_8);
    }
    throw new IllegalArgumentException("Unsupported routeRegion type");
}
~~~

This function only demonstrates **type normalization under a known contract**. Never assume every `byte[]` is UTF-8 if the actual producer uses another format; and never use the decoded value to pick a tenant before authenticating the source.

### 7.3. Headers dropped by security policy — not a bug

An adapter may intentionally omit `Authorization`, cookies, tokens, `MessageChannel` objects, or headers containing sensitive data. That is usually **correct behavior**. Therefore:

- For **routing metadata**, pass only approved, non-sensitive fields at appropriate boundaries.
- For **security context**, use transport authentication / trusted identity mechanisms; never copy raw tokens or permissions across all messages.
- For **reply paths**, use request–reply protocols and correlation/return addresses supported by the transport rather than serializing channel objects from the origin JVM.
- For **trace context**, use standard propagation when tracing is configured instead of blindly copying all internal headers.

The right fix for a "lost header" is often **changing how its semantics are carried**, rather than forcing adapters to preserve the original internal object.

## 8. How Header-based Router, Filter, and routing errors relate

### 8.1. Checking before the Router

To prevent the Router from facing arbitrary external values directly, place validation/normalization at the boundary:

~~~text
External system
   -> Inbound Adapter
   -> Map/normalize header
   -> Validate allowed region + identity
   -> Header-based Router
       -> orders.vn
       -> orders.intl
~~~

Do not confuse **Message Filter** with **Content-Based Router**:

- Filter decides **whether the message may proceed**.
- Router chooses **the target channel** for a qualified message.
- Transformer/Header Enricher can normalize or supplement metadata per contract before routing.

If a Filter drops a message without an appropriate reject reply or discard flow, a Gateway waiting on request–reply may time out. If a route header is missing, return a meaningful error or send to an `unroutable` branch with a wired consumer instead of silently discarding the message.

### 8.2. Configuring a default channel does not fix root causes

A default channel is only appropriate when business rules explicitly state "all other regions must go to manual processing." It **must not** turn a missing `routeRegion` caused by a broken mapper into a `VN` request. When an adapter changes between releases, a default route can mask a regression that misroutes most traffic.

Error classification guides action:

| Error category | Does retry help? | Handling |
|---|---|---|
| Header missing due to static mapper config | Retrying the exact same request usually does not help. | Fix mapping, quarantine/replay once contract allows. |
| Header missing in one message from sender | Only if the sender can resend complete data. | Reject, return validation error, audit. |
| Header holds an unsupported value | Retrying identical data does not help. | Business rejection or manual review. |
| Target channel full or consumer paused | Possibly, if transient. | Bounded retry/backoff, overload policy, idempotency. |
| Outbound network timeout | Possibly, if operation is safe to retry. | Manage retries and uncertain/duplicate outcomes. |

### 8.3. When correlation or reply metadata is lost

`routeRegion` is not the only critical header. In a flow with Splitter/Aggregator:

~~~mermaid
flowchart LR
    O[Order] --> S[Splitter]
    S --> A[Item A]
    S --> B[Item B]
    A --> T[Adapter / Broker]
    B --> T
    T --> G[Aggregator by correlation]
    G --> R[OrderResult]
~~~

If correlation/sequence metadata is dropped across a transport, the receiving Aggregator may not know items belong to **the same group**, or may lack enough data to release properly. The solution is defining a stable **correlation key** in the protocol, mapping it on both send and receive sides alongside expiration/recovery policies, and never expecting an internal `replyChannel` header to traverse a broker on its own.

For request–reply, when an inbound adapter constructs a new message, it may create a **different reply channel** or require transport correlation data. Never use a `replyChannel` object from the sending application as an address inside the receiving JVM. When designing multi-service flows, distinguish:

1. **Business ID** such as `orderId`.
2. **Message ID** of a specific message instance.
3. **Correlation ID** of the group/request.
4. **Trace ID** of the observability journey.
5. **Reply destination** that is actually valid on the transport.

## 9. Tracing exactly where a header gets lost

### 9.1. Five observation points

To pinpoint root causes systematically, place minimal observation points:

~~~text
P1  Before outbound adapter: Spring MessageHeaders
P2  At transport: protocol headers / envelope
P3  After inbound adapter: Spring MessageHeaders
P4  Before HeaderValueRouter: normalized routing metadata
P5  After Router: branch channel that actually received the message
~~~

If `P1` has `routeRegion` but `P2` does not, the fault is in **outbound mapping**. If `P2` has it but `P3` does not, inspect **inbound mapping/converter**. If `P3` has it but `P4` does not, inspect custom Transformers, Header Enrichers/Filters, or message reconstruction code. If `P4` has the right type yet `P5` does not receive it, inspect **Router mapping/channel resolution/subscribers/dispatch** instead of modifying adapters.

### 9.2. Logging under the least-exposure principle

Illustrative structured event schema (application-defined, not default framework output):

~~~text
event=OUTBOUND_PREPARED  orderId=ORD-1 traceId=T-1
  routeHeaderPresent=true routeRegion=VN

event=TRANSPORT_RECEIVED orderId=ORD-1 traceId=T-1
  mappedRouteHeaderPresent=false

event=ROUTING_REJECTED orderId=ORD-1 traceId=T-1
  reason=MISSING_ROUTE_HEADER component=regionRouter
~~~

What matters is **presence**, **name**, **type**, and **source** of the header. Never log entire payloads, access tokens, or all message headers. For sensitive metadata like tenant, log a safe region code or policy-compliant hashed identifier.

`Message History` helps observe which Spring Integration components a message traversed when tracking is enabled; it does not log per-step header diffs automatically and does not become a distributed trace across brokers. If flows run asynchronously across executors or separate processes, ensure explicit trace/log context propagation—MDC on the old thread does not automatically follow onto a new thread.

### 9.3. Metrics worth monitoring

| Metric | When spiking unexpectedly |
|---|---|
| `routing_header_missing_total` | Inbound mapper or sender may have a regression. |
| `routing_header_invalid_total` | Header schema or type changed; sender violates contract. |
| `routing_header_untrusted_total` | Possible spoofing or misconfigured trust boundary. |
| `unresolved_route_total` | Issue in channel mapping, bean registration, or route key. |
| `branch_received_total` by bounded region | Inspect distribution across post-Router branches. |
| `processing_errors_total` by branch | Distinguish valid routing followed by handler failure. |
| `retry_attempts_total` | Observe recovery and prevent retry storms. |

Never use `orderId` or `traceId` as metric labels due to high cardinality. Specific IDs belong in logs/traces with controlled access and retention.

## 10. Testing header propagation and routing branches

### 10.1. Unit test demonstrating that rebuilding a message can drop headers

JUnit 5 lets you test the cause before loading a Spring context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class HeaderCopyTest {

    @Test
    void rebuildingPayloadOnlyDropsCustomHeaders() {
        Message<String> original = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("routeRegion", "VN")
                .build();

        Message<String> broken = MessageBuilder
                .withPayload(original.getPayload())
                .build();

        assertEquals("VN",
                original.getHeaders().get("routeRegion"));
        assertNull(broken.getHeaders().get("routeRegion"));
    }

    @Test
    void rebuildingFromOriginalRetainsRoutingHeader() {
        Message<String> original = MessageBuilder
                .withPayload("ORD-1001")
                .setHeader("routeRegion", "VN")
                .build();

        Message<String> preserved = MessageBuilder
                .fromMessage(original)
                .build();

        assertEquals("VN",
                preserved.getHeaders().get("routeRegion"));
    }
}
~~~

**Note:** this test intentionally does not assert whether `MessageHeaders.ID` matches or differs between the two messages. What must be verified is whether **routing metadata is present or lost**; to trace across reconstructed messages, rely on appropriate business/trace/correlation IDs.

### 10.2. Unit test simulating outbound/inbound mapping

Using `TransportOrderMapper` from section 7:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderEnvelopeMapperTest {
    private final TransportOrderMapper mapper =
            new TransportOrderMapper();

    @Test
    void routeRegionSurvivesTheEnvelopeRoundTrip() {
        Message<Order> original = MessageBuilder
                .withPayload(new Order("ORD-10", 400_000L))
                .setHeader("routeRegion", "INTL")
                .build();

        WireEnvelope wire = mapper.encode(original);
        Message<Order> restored = mapper.decode(wire);

        assertEquals("INTL",
                wire.metadata().get("x-route-region"));
        assertEquals("INTL",
                restored.getHeaders().get("routeRegion"));
    }

    @Test
    void missingRegionIsRejectedInsteadOfDefaulted() {
        WireEnvelope wire = new WireEnvelope(
                new Order("ORD-11", 200_000L), Map.of());

        assertThrows(IllegalArgumentException.class,
                () -> mapper.decode(wire));
    }
}
~~~

This test proves the **application-written mapper contract**, not that Spring HTTP/Kafka/JMS adapters are configured identically to the mapper. When moving to real adapters, add **integration tests traversing the actual transport or adapter test fixtures**.

### 10.3. Integration test for HeaderValueRouter

Spring Test/JUnit 5 test against `HeaderRegionRoutingConfig` from section 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(HeaderRegionRoutingConfig.class)
class HeaderRegionRouterTest {
    @Autowired
    private OrderGateway gateway;

    @Autowired
    @Qualifier("orders.input")
    private MessageChannel input;

    @Test
    void routesDomesticRequest() {
        Receipt receipt = gateway.submit(
                new Order("ORD-21", 200_000L), "VN");

        assertEquals("VN", receipt.route());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void routesInternationalRequest() {
        Receipt receipt = gateway.submit(
                new Order("ORD-22", 300_000L), "INTL");

        assertEquals("INTL", receipt.route());
    }

    @Test
    void failsWhenRoutingHeaderIsMissing() {
        assertThrows(MessagingException.class, () ->
                input.send(MessageBuilder
                        .withPayload(new Order("ORD-23", 100_000L))
                        .build(), 0));
    }

    @Test
    void failsForUnknownRouteInsteadOfUsingChannelName() {
        assertThrows(MessagingException.class, () ->
                gateway.submit(
                        new Order("ORD-24", 100_000L), "UNKNOWN"));
    }
}
~~~

In tests, exact exception subclasses may depend on framework version, gateway, and router configuration; the assertions above target the `MessagingException` hierarchy in this sample configuration. When running in practice, verify the exact exception type/cause and assert structured error codes like **MISSING_ROUTE_HEADER** or **UNKNOWN_ROUTE** rather than relying solely on fragile exception messages.

The first two tests **do not prove adapter propagation** because the internal Gateway sets the header directly. Testing headers across HTTP/JMS/Kafka requires end-to-end tests through real adapters, covering mappers, converters, transport header names, decoded types, and target channels.

### 10.4. Pre-deployment adapter test matrix

| Scenario | Expected result |
|---|---|
| Outbound message has `routeRegion=VN` | Header reaches the wire per protocol contract. |
| Outbound message has `routeRegion=INTL` | Header is transmitted with correct name/encoding. |
| Inbound transport carries valid header | Spring message restores `routeRegion` with right type and value. |
| Inbound transport lacks header | Rejected or quarantined per contract, never defaulted to `VN`. |
| Header has unsupported value | Business rejection or error, never picks a channel bean automatically. |
| Header has malformed bytes encoding | Decoding fails clearly, no random keys generated. |
| Spoofed header from client | Cannot bypass authorization/tenant isolation. |
| Custom Transformer copies payload only | Test catches header loss. |
| Adapter reply builds new message | Reply/correlation contract verified without relying on internal JVM objects. |
| Router branch lacks consumer | Dispatch error or timeout is observable; never reported as processed. |
| Splitter/Aggregator across broker | Correlation/sequence mapped and group released per policy. |
| System retries a failed message | No duplicate side effects; idempotency and audit hold. |

## 11. Step-by-step incident diagnosis procedure

Suppose the Router in application B reports missing `routeRegion` for `orderId=ORD-5001`. Do not adjust defaults immediately; go step by step:

1. **Identify business identity and trace:** gather `orderId`, time window, source, and `traceId`; do not rely solely on Message ID since it can change when new messages are constructed.
2. **Check before the outbound adapter:** is `routeRegion` present? What is its exact name and type? Did an earlier Transformer drop it?
3. **Inspect wire format:** do HTTP/broker headers actually contain the key and value? Check mappers, allowlists, and converters; do not log sensitive payloads.
4. **Check right after the inbound adapter:** is metadata present? Does the internal canonical name match `routeRegion`? Is its type `String` or `byte[]`?
5. **Check before the Router:** did any step rebuild `Message`, call `removeHeaders`, or run a custom filter that stripped headers?
6. **Check Router mapping:** is the key normalized and present in `channelMapping`? Is an unwanted `channelKeyFallback` or default masking the error?
7. **Check channels and consumers:** does the channel exist, is the endpoint running, and are queues/pollers/executors active? Routing may have succeeded while dispatch or processing failed.
8. **Check error/retry paths:** does the source resend complete metadata? Are retries safe/idempotent? Are Aggregator groups missing correlation and pending indefinitely?
9. **Fix at the exact boundary:** update the header mapper/normalizer, align contracts with the producer, or fix custom code; add regression tests for the discovered case.

If you discover **no trusted source remains to recover the region**, treat it as missing data rather than guessing. For critical business flows, apply quarantine/reject/replay per approved policy.

## 12. Common design mistakes

| Misconception | Consequence | Right approach |
|---|---|---|
| "Spring MessageHeaders automatically cross every adapter." | Receiving Router loses keys. | Design explicit outbound/inbound header mappings. |
| "HTTP header names always match Spring header names." | Receiver confuses `X-Route-Region` and `routeRegion`. | Normalize at boundaries and align contracts. |
| "Every Kafka header is a `String`." | ClassCastException or routing on `byte[]`. | Use converters/decoders matching the agreed format. |
| "`copyHeaders(*)` fixes everything." | Forwards unsupported objects or leaks sensitive metadata. | Copy only allowlisted fields, especially across trust boundaries. |
| "Missing header defaults to `VN`." | Misroutes tenant/region, creating security risks. | Fail closed or re-derive from verified sources. |
| "Client headers are always trustworthy." | Senders spoof privileges or regions. | Authenticate and recompute decisions from trusted context. |
| "Router picking a channel means processing succeeded." | Fails to detect stopped subscribers or handler errors. | Track `ROUTE_DECIDED`, `BRANCH_ENTERED`, and outcomes. |
| "Retries fix static mapping bugs." | Retry storms while headers remain missing. | Classify errors, fix configuration, and replay safely. |
| "Internal reply channel crosses brokers intact." | No valid reply target in the remote system. | Design transport return addresses and correlation. |
| "No need to preserve correlation when Splitter crosses adapters." | Aggregator fails to regroup messages. | Map correlation/sequence and define timeout/release strategies. |
| "Message History is distributed tracing." | Cannot stitch journeys across multiple processes. | Use proper trace propagation and observability. |

## 13. Self-practice exercises

1. **Reproduce the bug:** create a message with `routeRegion`, then build a new message solely from its payload. Send both to `HeaderValueRouter` and record results; explain why only one routes properly.
2. **Build a mapper:** using `TransportOrderMapper`, rename the wire field `x-route-region` and write a test that detects inbound/outbound name mismatches.
3. **HTTP:** build a flow with an HTTP inbound gateway or adapter configured with a header mapper; send HTTP `X-Route-Region: VN` and inspect the internal header name/type before the Router. Test missing headers separately.
4. **Kafka/JMS:** test with a real adapter and a custom routing header, verifying producer/consumer share encoding and mapping; do not mix business headers with transport offset/topic metadata.
5. **Authorization:** intentionally send `routeRegion=INTL` from a caller only allowed `VN`. Design boundary validation and assert the request is never misrouted.
6. **Correlated flow:** have a Splitter emit three item messages, send them through an adapter, and aggregate them back. Verify `correlationId` and sequence after mapping; simulate one missing message and handle group expiration.
7. **Retry/recovery:** simulate an outbound mapping bug caused by a deployment. Prove that retrying the raw message fails to help; design quarantine/replay after the mapper is fixed.
8. **Observability:** add metric `routing_header_missing_total`, log `HEADER_MAPPING_FAILED` and `ROUTE_DECIDED` with business ID/trace ID; write a test distinguishing pre-Router failure from target-channel failure.

### Self-check questions

**Question 1:** Why can `MessageBuilder.withPayload(old.getPayload()).build()` leave `HeaderValueRouter` missing its key? **Answer:** the new message does not automatically inherit headers from `old`; required metadata must be copied explicitly.

**Question 2:** The transport received HTTP `X-Route-Region: VN`, yet the Router reading `routeRegion` still sees `null`. Where should you check first? **Answer:** inbound header mapping/normalization, followed by intermediate steps before the Router.

**Question 3:** Should you serialize a raw Java `replyChannel` object over Kafka to receive replies in another JVM? **No.** You need a real transport correlation and reply-destination contract.

**Question 4:** Should a missing tenant-selection header automatically route to a default tenant? **No**, unless explicitly permitted by business contracts and security policy; normally fail closed.

**Question 5:** A message crosses an adapter with `routeRegion` intact, yet is not processed by the handler. Can you conclude header mapping failed? **Not yet.** Check channel mapping, subscribers, lifecycle state, and dispatch/downstream errors.

**Conclusion:** When a Header-based Router misroutes after an adapter, verify whether **the header was mapped onto the wire protocol and restored into Spring `MessageHeaders`**, rather than rushing to tweak the Router. Distinguish business data, routing metadata, correlation, and trace context; pass only permitted headers across trust boundaries, normalize names/types, reject missing or untrusted data, and test end-to-end across adapters. Doing so keeps EIP flows with Router, Gateway, Transformer, Splitter/Aggregator, retry, and error channels predictable, traceable, and recoverable under control.
