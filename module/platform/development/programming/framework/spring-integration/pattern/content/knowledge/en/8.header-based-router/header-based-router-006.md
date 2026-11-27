# Null Values or Missing Headers

In **Spring Integration**, a **Header-Based Router** is an Enterprise Integration Patterns (EIP) variant that uses **metadata in message headers** to select the target channel. Instead of reading the entire payload, the router can rely on `region`, `messageType`, `priority`, or a header previously authenticated and normalized by the system.

However, routing flows commonly face an easily overlooked question: **What happens when the header value is `null` or the header does not exist at all?** Without an explicit specification, messages may drop out of the flow, get routed to an inappropriate default branch, or trigger hard-to-diagnose exceptions. This lesson focuses on distinguishing **missing header**, **null value**, **empty string**, **unsupported value**, and **wrong data type**, while designing testable fallback/reject behavior.

This lesson is in the **Header-based router** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module aims to implement Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, extensible, and observable message flows.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain `MessageHeaders` and how headers are read when a key is absent or its value is `null`.
2. Understand the effect of `MessageBuilder.setHeader(name, null)` and the difference between `get` and `containsKey`.
3. Distinguish **missing header**, **empty-string header**, **wrong type**, and **unmapped value**.
4. Choose explicit behavior for required and optional headers: fallback, reject/discard, or exception.
5. Integrate a pure Java policy into `@Router`, work with `@Header(required = false)`, and understand the limitations of `HeaderValueRouter`.
6. Test both decision logic and actual paths through Spring Integration channels with JUnit.
7. Preserve metadata such as `traceId`/`correlationId` and avoid trusting self-declared client headers.

## 2. Why might a header be missing?

A message has two parts: the payload is the main data, and headers are metadata. For instance, the same `OrderCreated` payload can arrive from multiple sources:

~~~text
Source A (HTTP Gateway)
payload: OrderCreated(orderId=ORDER-1001)
headers: region=NORTH, tenantId=shop-a, traceId=trace-1

Source B (message broker)
payload: OrderCreated(orderId=ORDER-1002)
headers: tenantId=shop-b, traceId=trace-2

Source C (legacy program)
payload: OrderCreated(orderId=ORDER-1003)
headers: region="", traceId=trace-3
~~~

For a router keying on `region`, Source A carries a valid value; Source B **carries no `region` header**; Source C has the **`region` key** with an empty string value. Both B and C fail to identify a region, yet they may require **different** handling:

- If region is **optional**, a message without `region` may go to `orders.default`.
- If `region` is present as an empty string, the data violates the contract; it may need `orders.invalid`.
- If `region` is required for tax calculation or tenant partitioning, **do not use a fallback**. The message must be rejected or raise a structured error.

### Decision diagram

~~~mermaid
flowchart TD
    IN["Inbound message"] --> H{"Has region value?"}
    H -->|Missing / null| OPT{"Is region optional?"}
    OPT -->|Yes| DEF["orders.default"]
    OPT -->|No| REJ["orders.invalid / error flow"]
    H -->|Present| TYPE{"Is it String type?"}
    TYPE -->|No| REJ
    TYPE -->|Yes| VALUE{"Trimmed value?"}
    VALUE -->|NORTH| N["orders.north"]
    VALUE -->|SOUTH| S["orders.south"]
    VALUE -->|Blank / unknown| REJ
~~~

**A fallback is a business decision**, not a way to hide malformed data or misconfiguration.

## 3. States to distinguish

In Java, `MessageHeaders` exposes a read interface closely resembling `Map<String, Object>`. Observe the states of the `region` key:

| State | `headers.get("region")` | `headers.containsKey("region")` | Meaning |
|---|---|---|---|
| Key does not exist | `null` | `false` | Missing metadata |
| Key exists with `null` value in a special map | `null` | `true` | Key is present with no value; rare with normal builders |
| Value is `""` | `""` | `true` | Header present with empty string |
| Value is `"   "` | `"   "` | `true` | Whitespace only |
| Value is `"NORTH"` | `"NORTH"` | `true` | Valid value per example |
| Value is `"north"` | `"north"` | `true` | Must decide whether normalization is allowed |
| Value is `"WEST"` | `"WEST"` | `true` | Value outside the supported list |
| Value is `42` (`Integer`) | `42` | `true` | Wrong type relative to String contract |
| Value is `"null"` (string) | `"null"` | `true` | **Not** a Java `null` value |

Key takeaway:

> `get("region") == null` does not by itself prove whether the key is present. If you genuinely need to distinguish them, use `containsKey("region")`. With standard message construction, the builder's setter treats a `null` value as removing the header.

### 3.1. `MessageBuilder.setHeader(..., null)`

Example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> message = MessageBuilder
        .withPayload("ORDER-1001")
        .setHeader("region", "NORTH")
        .setHeader("region", null)
        .build();

System.out.println(message.getHeaders().get("region")); // null
System.out.println(message.getHeaders().containsKey("region")); // false
~~~

In Spring Messaging's standard `MessageBuilder`, passing `null` to `setHeader` means **removing the header**, not "assigning null while keeping the key." This is why code that already attached a header can accidentally drop it during an enrich/transform step.

For example, the following code is easy to misread:

~~~java
Message<String> changed = MessageBuilder.fromMessage(message)
        .setHeader("region", lookUpRegionOrNull())
        .build();
~~~

If `lookUpRegionOrNull()` returns `null`, `region` will no longer exist on the new message. When you want to keep the previous region if no replacement is found, **check for null before calling `setHeader`**:

~~~java
MessageBuilder<String> builder = MessageBuilder.fromMessage(message);
String newRegion = lookUpRegionOrNull();

if (newRegion != null) {
    builder.setHeader("region", newRegion);
}

Message<String> updated = builder.build();
~~~

This snippet is illustrative logic; `lookUpRegionOrNull()` is an application method. Avoid performing network/DB lookups directly inside a router; place enrichment in a dedicated endpoint.

### 3.2. Why is a null header not the same as the string `"null"`?

~~~java
Message<String> a = MessageBuilder.withPayload("A")
        .setHeader("region", null)
        .build();

Message<String> b = MessageBuilder.withPayload("B")
        .setHeader("region", "null")
        .build();
~~~

In `a`, the `region` header is absent. In `b`, the header is a four-character string `n-u-l-l`; if the router does not check an allowlist of accepted values, that string could easily be mistaken for a channel name. Always inspect type and value after decoding.

### 3.3. Do not mutate MessageHeaders directly to "patch" a missing header

~~~java
// Wrong: MessageHeaders structure is read-only.
message.getHeaders().put("region", "NORTH");
~~~

This throws `UnsupportedOperationException` in standard `MessageHeaders` usage. When metadata needs updating, construct a **new message** with `MessageBuilder` or use a **Header Enricher** in the flow.

## 4. Consequences of `@Header` as a required parameter

Spring supports binding headers to method parameters annotated with `@Header`:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.handler.annotation.Header;

@Router(inputChannel = "orders.route")
public String route(@Header("region") String region) {
    return "NORTH".equals(region)
            ? "orders.north"
            : "orders.south";
}
~~~

By default, `@Header` requires the header to be present. When `region` is absent, **a parameter binding error can occur before the body of `route` ever runs**. Therefore, `"NORTH".equals(region)` does not handle missing headers if the framework cannot even pass the argument into the method.

### 4.1. Accepting missing headers with `required = false`

~~~java
@Router(inputChannel = "orders.route")
public String route(
        @Header(value = "region", required = false)
        String region) {

    if (region == null) {
        return "orders.default";
    }

    return switch (region.trim().toUpperCase(
            java.util.Locale.ROOT)) {
        case "NORTH" -> "orders.north";
        case "SOUTH" -> "orders.south";
        default -> "orders.invalid";
    };
}
~~~

This approach works for **optional headers**. However, it does not distinguish non-`String` header types before the framework binds the parameter. In systems receiving metadata from external sources, a stricter pattern is having the router accept `Message<?>` and inspect the raw `Object` itself, as shown in the next section.

Note: this `@Router` snippet is an **alternative** example to the method above. An input channel should have one clearly designed topology; do not register two competing routers listening to the same `DirectChannel` just by copying both examples.

### 4.2. When should you use `Message<?>` instead of `@Header`?

| Requirement | Appropriate parameter style |
|---|---|
| Required header, type already guaranteed | `@Header("region") String region` |
| Optional header, absence is valid | `@Header(value = "region", required = false) String region` |
| Need to distinguish absent/null/blank/wrong-type yourself | `Message<?>` and `getHeaders()` |
| Need multiple validated headers | `Message<?>`, or a typed context built before the router |
| Complex business logic needing pure unit tests | Extract a `RoutingPolicy` so the router method is just an adapter |

Importantly, **never use `required = false` just to mask a header that is actually mandatory** for security or business processing.

## 5. Writing a pure routing policy

Instead of scattering ad-hoc conditionals inside annotations, express region handling as a pure Java function.

### 5.1. Policy contract

In this example, `region` is optional, but if declared it must be valid:

- **Missing or null:** `DEFAULT` — applied when the message has no region info.
- **`"NORTH"`:** `NORTH`.
- **`"SOUTH"`:** `SOUTH`.
- **Empty, whitespace-only, wrong type, unknown region name:** `INVALID`.

~~~java
public enum RegionDecision {
    NORTH,
    SOUTH,
    DEFAULT,
    INVALID
}
~~~

### 5.2. Pure logic with no Spring dependency

~~~java
import java.util.Locale;

public final class RegionRoutingPolicy {

    public RegionDecision decide(Object regionHeader) {
        if (regionHeader == null) {
            return RegionDecision.DEFAULT;
        }

        if (!(regionHeader instanceof String region)) {
            return RegionDecision.INVALID;
        }

        String normalized = region.trim()
                .toUpperCase(Locale.ROOT);

        return switch (normalized) {
            case "NORTH" -> RegionDecision.NORTH;
            case "SOUTH" -> RegionDecision.SOUTH;
            default -> RegionDecision.INVALID;
        };
    }
}
~~~

The `decide` function has useful properties:

- Takes a single input value and reads no hidden state.
- Does not mutate `MessageHeaders`, send messages, or make HTTP/DB calls.
- Given the same immutable `Object` value, returns the same decision.
- Allows only two known region values, so an external string like `"orders.admin"` can never become an internal channel name.
- **Missing** semantics are crisp: an empty `String` is never treated as missing.

For a policy that does not need to distinguish a present map key holding `null`, simply pass `headers.get("region")` into the function above. If a special system case must distinguish **key present with null value** from **key absent**, expand the policy input to `HeaderSnapshot(boolean present, Object value)` instead of passing a single value.

### 5.3. When null means something different from missing in business terms

~~~java
public record HeaderSnapshot(boolean present, Object value) {}

public HeaderSnapshot inspectRegion(
        org.springframework.messaging.Message<?> message) {
    var headers = message.getHeaders();
    return new HeaderSnapshot(
            headers.containsKey("region"),
            headers.get("region"));
}
~~~

This distinguishes states under the `Map` contract:

- `present=false, value=null`: key is absent.
- `present=true, value=null`: key exists with a null value, if some header creation mechanism permits it.
- `present=true, value=""`: header holds an empty string.

In standard flows using `MessageBuilder.setHeader(..., null)`, the second case is not a typical representation. Avoid introducing confusing extra states unless the business truly requires them.

## 6. Connecting the policy to `@Router` and channels

A small endpoint invokes the policy and maps the outcome to declared channels:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.messaging.Message;

public final class RegionMessageRouter {

    private final RegionRoutingPolicy policy;

    public RegionMessageRouter(RegionRoutingPolicy policy) {
        this.policy = policy;
    }

    @Router(inputChannel = "orders.route")
    public String destination(Message<?> message) {
        Object region = message.getHeaders().get("region");

        return switch (policy.decide(region)) {
            case NORTH -> "orders.north";
            case SOUTH -> "orders.south";
            case DEFAULT -> "orders.default";
            case INVALID -> "orders.invalid";
        };
    }
}
~~~

The router receives **the whole message**, so a missing header never triggers a `@Header(required=true)` binding failure. Nor does the code blindly cast `Object` to `String`: if the value has the wrong type, the policy deliberately classifies it as `INVALID`.

### 6.1. Declaring channels

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class RegionRoutingConfiguration {

    @Bean(name = "orders.route")
    public MessageChannel incoming() {
        return new DirectChannel();
    }

    @Bean(name = "orders.north")
    public PollableChannel north() {
        return new QueueChannel();
    }

    @Bean(name = "orders.south")
    public PollableChannel south() {
        return new QueueChannel();
    }

    @Bean(name = "orders.default")
    public PollableChannel fallback() {
        return new QueueChannel();
    }

    @Bean(name = "orders.invalid")
    public PollableChannel invalid() {
        return new QueueChannel();
    }

    @Bean
    public RegionRoutingPolicy regionRoutingPolicy() {
        return new RegionRoutingPolicy();
    }

    @Bean
    public RegionMessageRouter regionMessageRouter(
            RegionRoutingPolicy policy) {
        return new RegionMessageRouter(policy);
    }
}
~~~

Here, `QueueChannel` makes results easy to observe in exercises and JUnit. In production systems, each channel typically connects to a dedicated handler or processing flow; default `QueueChannel`s do not provide durability across restarts.

### 6.2. Sending messages with and without headers

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> known = MessageBuilder
        .withPayload("ORDER-1001")
        .setHeader("region", "NORTH")
        .setHeader("traceId", "trace-1001")
        .build();

Message<String> missing = MessageBuilder
        .withPayload("ORDER-1002")
        .setHeader("traceId", "trace-1002")
        .build();

Message<String> blank = MessageBuilder
        .withPayload("ORDER-1003")
        .setHeader("region", "  ")
        .build();
~~~

When sending these three messages to `orders.route`, the example topology routes them respectively to `orders.north`, `orders.default`, and `orders.invalid`. The router merely forwards the message, so the payload and headers like `traceId` continue with the original message; there is no need to construct a new message just to switch branches.

**Note:** the `orders.invalid` channel in this example is a handling path for **invalid data**, not necessarily Spring Integration's `errorChannel`. A normally routed invalid branch and an exception thrown by an endpoint have distinct meanings.

## 7. Using the built-in `HeaderValueRouter`

Spring Integration provides `HeaderValueRouter`, a specialized router that uses the value of **one header** to select the destination channel. It is handy when you only need a direct header → channel mapping without complex business distinctions.

### 7.1. Configuring mappings

Java configuration example for the router object:

~~~java
import org.springframework.integration.router.HeaderValueRouter;

public HeaderValueRouter createRouter() {
    HeaderValueRouter router =
            new HeaderValueRouter("region");

    router.setChannelMapping("NORTH", "orders.north");
    router.setChannelMapping("SOUTH", "orders.south");
    router.setDefaultOutputChannelName("orders.default");

    return router;
}
~~~

For the router to actually receive messages, attach this object to an **endpoint/IntegrationFlow** and declare the target channels. The snippet above only shows mapping configuration, not a complete flow on its own.

The same idea can be expressed in **Java DSL**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow simpleHeaderRoute() {
    return IntegrationFlow.from("orders.simple.input")
            .route("headers['region']", spec -> spec
                    .channelMapping("NORTH", "orders.north")
                    .channelMapping("SOUTH", "orders.south")
                    .defaultOutputChannel("orders.default"))
            .get();
}
~~~

This example illustrates expression routing when the header has already been normalized to `"NORTH"` or `"SOUTH"`. A bean named `orders.simple.input` and the corresponding target channels are required; channel names in the snippet are part of the flow contract.

### 7.2. What does default output solve?

Mapping-based routers need a behavior when no target channel is determined. `defaultOutputChannel` can act as a fallback branch for cases with **no matching route**, depending on exact router configuration and Spring Integration version behavior.

Pay close attention: a single shared fallback usually **does not distinguish** between a missing header and a header carrying an unmapped value. If business rules want:

- **Missing header** → `orders.default`;
- **Wrong-type header or out-of-list value** → `orders.invalid`;

then `RegionRoutingPolicy` paired with `@Router` in sections 5–6 expresses that requirement more accurately. Do not assume configuring `defaultOutputChannel` will classify these cases differently for you.

### 7.3. `resolutionRequired` and no target channel

Spring Integration routers have a setting governing whether **failing to resolve a channel** is an error or ignorable. When you must guarantee messages are never silently lost, verify how `resolutionRequired`, default output, and channel mappings behave in the exact library version you are using.

Distinguish three situations:

| Situation | Cause | Approach |
|---|---|---|
| Header absent | Producer omitted optional metadata | Fallback **if allowed by the contract** |
| Header has a value without a mapping | E.g., `WEST` or new schema version | Reject, quarantine, or update mapping per policy |
| Router returns a non-existent channel name | Typo in bean name or missing configuration | Report configuration error and fix deployment; never silently fall back |

For messages that must be processed, write tests ensuring all valid branches resolve a channel and nothing is dropped when a mapping is missing.

## 8. Required headers: reject or throw, never blindly fall back

Not every header is permitted to be absent. For example, `tenantId` affects data access isolation and `eventType` can determine which validator/schema applies. If missing, sending the message to `orders.default` can cause security or business bugs.

### 8.1. Policy for a required header

~~~java
public enum TenantRoute {
    TENANT_A,
    TENANT_B,
    REJECT
}

public TenantRoute tenantRoute(Object trustedTenantHeader) {
    if (!(trustedTenantHeader instanceof String tenant)) {
        return TenantRoute.REJECT;
    }

    return switch (tenant) {
        case "tenant-a" -> TenantRoute.TENANT_A;
        case "tenant-b" -> TenantRoute.TENANT_B;
        default -> TenantRoute.REJECT;
    };
}
~~~

This is a pure Java example: missing, null, blank, wrong type, or unsupported tenants are all rejected. Never treat a tenant name in a header as proof of access permission; authentication/authorization layers must verify it first, and the router should use only the **trusted** value.

### 8.2. Filter before Router

If the system wants to separate validation from routing:

~~~mermaid
flowchart LR
    IN["Inbound adapter"] --> V{"Validation / authorization"}
    V -->|Fail| REJ["Reject response / discard channel"]
    V -->|Pass| E["Header enrichment"]
    E --> ROUTER{"Header-Based Router"}
    ROUTER --> A["Channel A"]
    ROUTER --> B["Channel B"]
~~~

You can use a `Filter` to drop messages missing required headers, paired with a `discardChannel` for observation or reply. If an immediate error must return to a Gateway, you may choose to throw an exception and route through an appropriate error flow. Normal Filter rejection differs from an exception:

- **Filter with discard channel:** sends rejected messages to a separate handling channel, if configured.
- **Exception:** can propagate back to the caller in synchronous flows or pass through error handling in asynchronous flows.
- **Router returning `orders.invalid`:** is a normal route, useful when retaining original payload/headers for error classification in a dedicated handler.

Choose one style matching the contract, and avoid routing **the exact same failure** to both discard and error flows and counting it twice.

## 9. Subtle details that easily cause bugs

### 9.1. Header names are case-sensitive

`region` and `Region` are two distinct keys under the `Map` contract. If an inbound adapter or external library renames a header, the router may see `null` even though operators believe the metadata exists.

~~~java
var headers = message.getHeaders();

Object a = headers.get("region");
Object b = headers.get("Region");

// Two different keys; do not mix names arbitrarily.
~~~

Define header names as application constants, use header mappers/normalizers at protocol boundaries, and test real adapters. For HTTP headers, HTTP's case-insensitivity rule **does not automatically allow** treating keys inside `MessageHeaders` as identical.

### 9.2. Empty strings, whitespace, and default values

Some code treats every non-matching string as `default`:

~~~java
// Avoid when blank or invalid data must be rejected:
return "NORTH".equals(region) ? "orders.north" : "orders.default";
~~~

This sends `"SOUTH"`, `""`, `"WEST"`, and possibly `null` to the exact same branch, hiding data errors. Write an explicit decision table instead.

### 9.3. Do not cast blindly

~~~java
// Risks ClassCastException if the header is an Integer:
String region = (String) message.getHeaders().get("region");
~~~

If headers can come from heterogeneous producers or adapters, use `instanceof String` and handle invalid types explicitly. Do not use `String.valueOf(raw)` if it turns `null` into the literal `"null"` or numbers into seemingly valid strings.

### 9.4. A null header value is not a null payload

Normally a message must have a valid payload; the absence of `region` metadata does not imply the payload is absent. Processing flows should separate decode/payload failures from header routing failures.

### 9.5. Headers containing mutable objects

`MessageHeaders` is structurally read-only on a built message, yet if a header value is a mutable `List`/`Map`, the object's contents can still be mutated via reference. Use immutable strings/enums/records for routing keys; if a collection is needed, take a defensive snapshot. This matters in `PublishSubscribeChannel` and asynchronous executor flows.

### 9.6. Do not use client headers as channel names

~~~java
// Unsafe when the destination is decided entirely by the client:
return message.getHeaders().get("nextChannel", String.class);
~~~

A caller could pick an internal channel outside permitted scope. Instead, map **validated, allowlisted values** to a fixed set of target channels.

## 10. Fallback, reject, and error reporting: decision table

Before implementation, the team should write a contract for each header.

| Situation | Optional `region` | Required `tenantId` | Required `messageType` |
|---|---|---|---|
| Header absent | `orders.default` | Reject/authorization error | Reject/unsupported message |
| `null` after builder drops header | Treat as absent | Reject | Reject |
| `""` or whitespace string | Invalid | Reject | Reject |
| Wrong type | Invalid | Reject | Reject |
| Valid value | Route via mapping | Route verified tenant | Pick handler per schema |
| Unknown value | Invalid/quarantine | Reject | Reject/quarantine |
| Target channel does not exist | Configuration error | Configuration error | Configuration error |

No single policy fits every application. A header may be optional in a notification flow yet mandatory in a payment flow. **What matters is that the policy is written down clearly, applied consistently, and tested before production.**

### 10.1. When there is no downstream subscriber/handler

Returning a channel name from a Router does not mean a consumer is listening downstream or that the work finished. Depending on channel type and topology, messages may go unconsumed or fail upon send. Test real endpoints, check subscriber counts on `SubscribableChannel` where appropriate, and configure error handling as required. `send()==true` does not prove end-to-end business success, especially in async flows.

## 11. Testing the policy with JUnit 5

The pure function in section 5 can be tested without booting a Spring application context.

### 11.1. Testing every value kind

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class RegionRoutingPolicyTest {

    private final RegionRoutingPolicy policy =
            new RegionRoutingPolicy();

    static Stream<Arguments> values() {
        return Stream.of(
                Arguments.of("NORTH", RegionDecision.NORTH),
                Arguments.of("north", RegionDecision.NORTH),
                Arguments.of("  south  ", RegionDecision.SOUTH),
                Arguments.of("", RegionDecision.INVALID),
                Arguments.of("  ", RegionDecision.INVALID),
                Arguments.of("WEST", RegionDecision.INVALID),
                Arguments.of("null", RegionDecision.INVALID),
                Arguments.of(42, RegionDecision.INVALID));
    }

    @ParameterizedTest
    @MethodSource("values")
    void handlesSupportedAndUnsupportedValues(
            Object header, RegionDecision expected) {
        assertEquals(expected, policy.decide(header));
    }

    @Test
    void missingHeaderUsesDefault() {
        assertEquals(RegionDecision.DEFAULT, policy.decide(null));
    }
}
~~~

This test clearly expresses **semantics**: only null/missing routes to default, whereas present-but-invalid headers go to invalid. Testing `"null"` guards against accidental stringification bugs.

### 11.2. Testing `setHeader(..., null)`

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class NullHeaderBuilderTest {

    @Test
    void assigningNullRemovesHeader() {
        Message<String> input = MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("region", "NORTH")
                .build();

        Message<String> output = MessageBuilder
                .fromMessage(input)
                .setHeader("region", null)
                .build();

        assertTrue(input.getHeaders().containsKey("region"));
        assertFalse(output.getHeaders().containsKey("region"));
        assertNull(output.getHeaders().get("region"));
    }
}
~~~

This test also confirms that creating a new message does not mutate the original message's metadata.

## 12. Testing the real flow with Spring Integration

The unit tests above do not yet prove that Spring resolves the channels properly. We need to send messages through `orders.route` and inspect output queues. Example using Java 17+, JUnit Jupiter 5, Spring Test, and `spring-integration-core`, built on `RegionRoutingConfiguration` from section 6.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = RegionRoutingConfiguration.class)
class RegionRoutingFlowTest {

    @Autowired
    @Qualifier("orders.route")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.north")
    PollableChannel north;

    @Autowired
    @Qualifier("orders.south")
    PollableChannel south;

    @Autowired
    @Qualifier("orders.default")
    PollableChannel fallback;

    @Autowired
    @Qualifier("orders.invalid")
    PollableChannel invalid;

    @Test
    void knownHeaderGoesToNorth() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1001")
                .setHeader("region", "NORTH")
                .setHeader("traceId", "trace-1001")
                .build()));

        Message<?> received = north.receive(1000);

        assertNotNull(received);
        assertEquals("ORDER-1001", received.getPayload());
        assertEquals("trace-1001",
                received.getHeaders().get("traceId"));

        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
        assertNull(invalid.receive(0));
    }

    @Test
    void missingHeaderGoesToFallback() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1002")
                .setHeader("traceId", "trace-1002")
                .build()));

        Message<?> received = fallback.receive(1000);

        assertNotNull(received);
        assertEquals("ORDER-1002", received.getPayload());
        assertEquals("trace-1002",
                received.getHeaders().get("traceId"));

        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(invalid.receive(0));
    }

    @Test
    void blankHeaderGoesToInvalid() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1003")
                .setHeader("region", "  ")
                .build()));

        assertNotNull(invalid.receive(1000));
        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
    }

    @Test
    void wrongTypeGoesToInvalid() {
        assertTrue(input.send(MessageBuilder
                .withPayload("ORDER-1004")
                .setHeader("region", 42)
                .build()));

        assertNotNull(invalid.receive(1000));
        assertNull(north.receive(0));
        assertNull(south.receive(0));
        assertNull(fallback.receive(0));
    }
}
~~~

All output channels in the configuration use `QueueChannel`, so synchronous tests can call `receive(...)` to observe routing. The tests verify:

- Missing headers **do not cause `@Router` binding failures**.
- Null/absent values are handled intentionally per policy.
- Blank or mistyped values do not accidentally enter the fallback.
- `traceId` stays intact on messages forwarded through the router.
- Messages reach **only the single** intended branch.

If parallel execution is enabled or topology changes, ensure tests use isolated contexts/queues so messages do not collide. To test channels with real handlers, replace `QueueChannel` with handlers backed by fake repositories/counters and assert the expected side effects.

## 13. Combining with other Enterprise Integration Patterns

### 13.1. Transformer and Header Enricher

If an inbound message lacks `region` yet the system can derive it from the payload or a trusted source, a **Header Enricher** step before the router can attach `region`:

~~~mermaid
flowchart LR
    IN["Inbound message"] --> V["Validate"]
    V --> E["Trusted Header Enricher"]
    E --> R{"Header-Based Router"}
    R --> A["NORTH"]
    R --> B["SOUTH"]
    R --> D["Fallback / Reject"]
~~~

If a Transformer returns a complete `Message<?>`, it must explicitly retain required headers. Transformers returning payloads typically have input headers propagated by the framework per endpoint rules. Therefore, when a header "suddenly vanishes" before a router, inspect the preceding transform/enrich step and its header propagation settings.

### 13.2. Filter and Router

A Filter answers "is this message valid or should it be dropped?", while a Router answers "which branch does this message take?" If `region` is required, a Filter can divert messages missing `region` to `orders.rejected` before the router runs. If `region` is optional, the Router can pick `orders.default`.

Do not use Filters to split complex multi-branch business flows where a Router with a policy is clearer; nor should you use a Router to replace all authentication/validation.

### 13.3. Splitter and Aggregator

After a `Splitter`, each part of an order may need `correlationId`, `sequenceNumber`, and `sequenceSize` so the Aggregator regroups them accurately. When creating new messages on any branch, preserve this metadata per contract. A `region` header used for routing **does not automatically substitute for correlation ID**.

If parts of the same order lack `region`, decide whether to accept per-part fallback or reject the whole group. If the Aggregator waits for a full part count while one branch discards an item, the group may never complete under the current release strategy; define timeouts and an incomplete-group policy.

### 13.4. Gateway, retry, and error channel

A Gateway may wait for a reply, so fallback/reject paths must either produce a response matching the request–reply contract or throw a clearly handled exception; never drop messages into a queue and leave the caller hanging indefinitely.

In synchronous processing, exceptions in a router or handler can bubble back to the caller. In asynchronous flows, errors typically go through error handling as configured by `errorChannel`. Do not treat a routed `invalid` message as an automatic `ErrorMessage`; it is simply a message routed to the invalid channel like any other route.

A missing mandatory header is a **permanent data error**: retrying the exact same message without a valid enrichment step rarely helps. Reserve retries for transient failures in databases, brokers, HTTP calls, or recoverable causes, paired with an idempotency policy.

### 13.5. Publish–Subscribe vs. Header-Based Router

`PublishSubscribeChannel` delivers to **every** registered subscriber, whereas a header-based router like this example selects **one** channel from metadata. When you want to notify audit, analytics, and notifications concurrently, do not pick the wrong channel pattern merely because the message has an `eventType` header. You can place Publish–Subscribe downstream of a route if fan-out is needed inside a specific branch.

## 14. Observing and diagnosing missing headers

When a router sends a message to a fallback, you need enough telemetry to tell whether it is expected behavior or a producer bug.

### 14.1. Information worth tracking

| Field/metric | Purpose | Safe usage |
|---|---|---|
| `traceId` | Trace a single execution | Do not use values as high-cardinality metric labels |
| `businessCorrelationId` | Link multiple business steps | Keep in logs per data policy |
| `routeDecision` | Know whether message went NORTH/SOUTH/DEFAULT/INVALID | Suitable as a low-cardinality label |
| `routeReason` | `MISSING_REGION`, `BLANK_REGION`, `UNSUPPORTED_REGION` | Use stable error codes |
| `sourceSystem` | Identify which producer lacks metadata | Use only verified sources |
| `schemaVersion` | Analyze contract evolution | Verify against actual producers and converters |

Keep policy logic pure by placing logging/metrics inside **adapters or monitoring handlers** rather than calling observability systems directly from `decide`.

### 14.2. Do not log all headers indiscriminately

Headers can carry reply/error addresses, tokens, user data, or internal details. Log only reviewed, safe keys. If a client is caught sending `nextChannel` or `admin=true`, never treat it as trusted input without validation and authorization.

## 15. Common errors

### Error 1 — Assuming `get() == null` means "key exists with null value"

**Cause:** `Map.get` also returns null when the key does not exist, and `MessageBuilder.setHeader(..., null)` removes the key in normal usage.

**Fix:** use `containsKey` if the contract needs to distinguish them, then define clear handling for null vs. absent.

### Error 2 — `@Header` is required by default when the code wants fallback

**Symptom:** argument resolution fails before the router method even executes.

**Fix:** use `@Header(value = "region", required = false)` or accept `Message<?>` to read the header proactively—only when missing `region` is valid.

### Error 3 — Grouping missing, empty, and unsupported into the same fallback

**Symptom:** messages with `region="WEST"` are treated identically to messages with no `region`.

**Fix:** use a decision table: only valid missing headers go to default; blank/type mismatch/unknown go to reject unless the contract states otherwise.

### Error 4 — Null accidentally deletes headers during copy/enrich

**Symptom:** a pre-router step calls `setHeader("region", null)` and downstream steps lose `region`.

**Fix:** avoid setting null when you intend to keep the prior value; guard with null checks in the builder and test propagation.

### Error 5 — Routing directly to a client-supplied channel name string

**Symptom:** producers can send messages to unauthorized internal channels.

**Fix:** authenticate sources, normalize metadata, and map through a fixed enum/allowlist. Never use arbitrary values as destinations.

### Error 6 — Ignoring key names and data types

**Symptom:** producer sends `Region` instead of `region`, or sends `region=7`, so the router misses or misunderstands the value.

**Fix:** define a shared header schema, validate at ingress, and write integration tests against real adapters.

### Error 7 — Fallback turns configuration bugs into silent false successes

**Symptom:** a primary channel is renamed, yet every message silently enters fallback unnoticed.

**Fix:** test all mappings and channel beans, monitor fallback rates, and separate business defaults from channel resolution errors.

### Error 8 — Retrying endlessly on messages missing a mandatory header

**Symptom:** messages lacking `tenantId` are fed back through the same router repeatedly.

**Fix:** separate data errors from transient errors; reject/quarantine unfixable static inputs, and retry only if an enrichment step can recover.

## 16. Hands-on exercise: region routing flow

**Context:** an application receives `OrderCreated` events from HTTP and a broker. Newer messages include `region` as `NORTH` or `SOUTH`; older messages may omit the header. Senders may also submit blank strings or invalid values.

### 16.1. Requirements

1. Create `RegionDecision` and `RegionRoutingPolicy` as in section 5. Define `null` → DEFAULT, `NORTH/SOUTH` → respective branches, everything else → INVALID.
2. Write unit tests for `null`, `""`, `"  "`, `"north"`, `"WEST"`, `"null"`, and an integer.
3. Use `MessageBuilder` to create a message with `region=NORTH`, then remove it via `setHeader("region", null)`; prove `containsKey` flips from true to false.
4. Write a `@Router` accepting `Message<?>` and mapping the enum to four corresponding channels.
5. Create `QueueChannel`s for `orders.north`, `orders.south`, `orders.default`, and `orders.invalid`; send messages and assert the right branch.
6. Preserve `traceId` through the router and test both fallback and reject paths.
7. Change the policy to make `region` mandatory: null/absent must go to reject rather than default. Compare test results before and after.
8. Try replacing `@Router` with `HeaderValueRouter` mapping for the simple case; test missing, unknown, and wrong-type behavior on your Spring Integration version.
9. Advanced scenario: client-sent `tenantId` differs from the tenant derived from the authenticated principal; use only the **verified** tenant for routing.
10. Advanced scenario: a Gateway sends a request without `region` and waits for a reply; design the default/reject branch to return a contract-compliant error code response.

### 16.2. Completion criteria

- Every header state has an explicit outcome.
- No exceptions from blind unboxing or casting inside the policy.
- Optional missing headers fall back properly; invalid data is never misprocessed as valid.
- Messages are never routed to client-injected channel names.
- Tests verify both **pure Java policy** and **real channels**.
- Tracing metadata follows the message; error branches retain enough info for observability.
- Parse/validation errors and infrastructure failures follow distinct handling paths.

### Self-check questions

1. Under what conditions does `MessageHeaders.get("region")` return null?
2. What does `MessageBuilder.setHeader("region", null)` normally do?
3. Why should `region=""` not be treated as missing by default?
4. When should you use `@Header(required = false)`, and when should you accept `Message<?>`?
5. If `tenantId` is mandatory for authorization, should you fall back to a default tenant when the header is missing?
6. Why might `HeaderValueRouter` with a default output not suffice to separate missing from unknown?
7. Why is returning an enum from `RegionRoutingPolicy` better than returning channel name strings directly?
8. Which test catches a router pointing to a non-existent channel bean?
9. Does routing to an invalid branch automatically send an `ErrorMessage`?
10. When a message is replayed, how can you keep the routing policy stable for identical inputs?

## 17. Design checklist

- [ ] Clearly documented which headers are required and which are optional.
- [ ] Distinguished absent, null, blank, wrong-type, and unsupported values.
- [ ] Aware that `setHeader(name, null)` normally drops the key from the new message.
- [ ] Chosen default/reject/error policies per business contract.
- [ ] Never using unverified headers for access control or channel selection.
- [ ] Router takes the right input form to handle missing headers without unintended binding failures.
- [ ] Mappings are allowlisted; all output channels exist.
- [ ] Validation/normalization placed at ingress where needed.
- [ ] Trace/correlation metadata preserved across routing and transformations.
- [ ] Error channel and discard/reject channel have distinct semantics.
- [ ] Unit tests exist for policy, null builder behavior, and integration tests verify exact branches.
- [ ] No infinite retries on missing mandatory data, wrong types, or static unknown values.
- [ ] Fallback/reject metrics exist without logging secrets or personal data.

## 18. Summary

**Header-Based Router** lets processing flows make decisions from metadata without requiring every handler to inspect payload structure. However, a header that is missing, set to `null`, left empty, or carrying an unexpected type can produce wrong routing decisions. Therefore, define an **explicit decision table for every header state** before choosing an implementation technique.

In Spring Integration, `get` returns `null` when a key is absent; `containsKey` checks key presence; `MessageBuilder.setHeader(..., null)` normally removes the key. `@Header(required=false)` lets a router accept missing cases; `Message<?>` lets it inspect type and value explicitly. When you need to separate valid defaults from invalid data, a pure policy returning an enum paired with a `@Router` mapping to channels keeps testing consistent and maintainable.

Keep validation, authorization, and header enrichment at the proper boundaries; route messages with clear tracing/correlation, handle errors per Gateway/retry/error-channel contracts, and test on real channels. These principles help the **SPRING_INTEGRATION_PATTERN** module build loosely coupled, extensible, and observable message flows.

### References

- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — HeaderValueRouter: https://docs.spring.io/spring-integration/api/org/springframework/integration/router/HeaderValueRouter.html
- Spring Framework API — MessageHeaders: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html
- Spring Framework API — MessageBuilder: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- Spring Framework API — @Header: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html

