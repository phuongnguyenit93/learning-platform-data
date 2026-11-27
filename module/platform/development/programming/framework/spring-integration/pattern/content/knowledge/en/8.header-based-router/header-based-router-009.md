# Protecting Headers from Untrusted User Data

## 1. Context and objectives

In the **Header-based router** chapter of the **SPRING_INTEGRATION_PATTERN** module, we implement Enterprise Integration Patterns with Spring Integration to create loosely coupled, extensible message flows. As Router, Filter, Transformer, Splitter, Aggregator, and Gateway exchange messages, headers can be used for routing, replies, error handling, correlation, and observability. A header from the wrong origin can divert the entire flow down an unintended branch.

Consider an order intake API:

- Standard orders go to **standardOrdersChannel**.
- High-value orders go to **manualReviewChannel**.
- The target channel is chosen from the **trustedRoute** header.

If an external client sends a header with the same name or a value matching an **internal channel name**, and the application copies it straight into a Spring Message, the client can steer message flow unexpectedly. Likewise, headers like **tenantId**, **role**, **replyChannel**, **errorChannel**, or **routingSlip** can cause serious consequences if treated as already authenticated data.

**Lesson objectives:**

1. Identify trust boundaries between HTTP requests, message brokers, and internal `MessageChannel`s.
2. Distinguish **client-supplied headers**, **adapter-generated headers**, and **server-verified/server-generated headers**.
3. Construct new messages via an **allowlist**; never copy raw headers from untrusted sources.
4. Configure `HeaderValueRouter` with fixed channel mappings and **`channelKeyFallback(false)`**.
5. Evaluate sensitive headers, header filtering, and propagation rules across endpoints.
6. Test spoofing scenarios for routes, tenants, reply channels, traces, and unmapped values.

## 2. Message headers are metadata, not authentication proof

A Spring Message consists of a **payload** and **`MessageHeaders`**:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

**Headers** carry metadata for delivery and processing: event name, tenant context, correlation ID, reply destination, or error info. Spring Integration can feed headers into **`HeaderValueRouter`** or adapters. That metadata is useful, yet **the mere presence of a header does not prove its value is trustworthy**.

| Header or header group | Typical role | Risk if trusting external data |
| --- | --- | --- |
| **route**, **eventType**, **trustedRoute** | Pick processing branch | Sender picks a sensitive path or bypasses checks |
| **tenantId**, **organizationId** | Scope data access | Diverts message to another tenant |
| **role**, **isAdmin**, **approvalGranted** | Suggest business permissions | Spoofs approval authority |
| **replyChannel** | Request/reply return path | Redirects replies to an unintended channel |
| **errorChannel** | Path for certain messaging errors | Corrupts or hides error reporting |
| **routingSlip** | Dictates subsequent integration hops | Injects hops outside permitted topology |
| **priority** | Queue ordering if supported by channel | Abuses priority queues |
| **correlationId** | Groups related messages | Mixes Aggregator groups, impairs reconciliation |
| **traceId**, **clientRequestId** | Links logs and traces | Injects forged, oversized, or sensitive strings into logs |
| **id**, **timestamp** | Metadata managed by Spring Messaging | Confused with business IDs or attempts to spoof framework metadata |

**`MessageHeaders` is structurally immutable** after creation, yet that does not guarantee **the initial values are trustworthy**. If a message is constructed from forged headers, immutability merely preserves those forged values. Furthermore, mutable payloads or mutable header values can still be modified through shared references.

## 3. Threat model: what can a client control?

External sources can control:

1. **HTTP request headers** and query/body fields permitted by the API.
2. **AMQP/Kafka/JMS message headers or properties**, depending on adapters and producer privileges.
3. **JSON fields named like metadata**, such as a `route`, `role`, or `tenantId` property in the payload.
4. **Anomalous values**: null, huge strings, Unicode, newline characters, or unexpected data types.
5. **Replayed or intentionally reordered messages**, even when every header has a valid type.

Not every HTTP header automatically becomes a Spring Message header; conversion depends on the **HTTP inbound adapter/gateway**, header mapper, and configuration. Similarly, broker adapters apply their own mapping and serialization rules. Always inspect **where data enters** the flow rather than assuming the framework pre-filtered every header.

~~~mermaid
flowchart LR
    C["External client<br/>body + HTTP headers"] --> A["HTTP adapter / controller"]
    A --> B["Trust boundary<br/>authenticate + validate"]
    B --> M["Build new Message<br/>allowlisted headers only"]
    M --> R["HeaderValueRouter<br/>allowlist mapping"]
    R --> S["Standard orders"]
    R --> V["Manual review"]
    R --> Q["Unroutable / alert"]
~~~

A **trust boundary** is where the application verifies identity, permissions, and data validity, and then derives internal metadata itself. A message pushed into a `DirectChannel` is not automatically trustworthy merely because it sits inside the `ApplicationContext`. If any internal bean can send to a critical channel, enforce access controls or validation at the receiving point so authentication is never bypassed.

### 3.1. Example of route spoofing

Suppose a client is allowed to submit:

~~~json
{
  "orderId": "ORD-107",
  "totalVnd": 250000,
  "route": "manualReviewChannel",
  "tenantId": "tenant-other",
  "approvalGranted": true
}
~~~

Client-supplied `route`, `tenantId`, and `approvalGranted` fields **have no authority** to become router decisions unless the application verifies and recognizes them per contract. For an order of only 250,000 VND, the internal route computed from server policy may have to be **STANDARD**.

**Bad example** when the incoming message has client-controlled headers:

~~~java
// Do not use this approach at an untrusted boundary:
Message<OrderReceived> dangerous = MessageBuilder
        .withPayload(order)
        .copyHeaders(untrustedHeaders)
        .setHeaderIfAbsent("trustedRoute", "STANDARD")
        .build();
~~~

Two problems:

- **`copyHeaders`** brings along every header sent by the client, including names matching internal control headers.
- **`setHeaderIfAbsent`** does not overwrite `trustedRoute` if the client already set it. The forged value keeps flowing.

Simply changing `setHeaderIfAbsent` to `setHeader` is still insufficient when other dangerous headers are copied. You must **predefine an allowlist of allowed headers**, construct only server-owned fields, and handle retaining external observability metadata separately.

## 4. Design rule: every header has an owner

A testable governance approach groups headers by **who is authorized to create/update them**:

| Group | Who may supply/write? | Rule |
| --- | --- | --- |
| **Business payload** | Client may propose, server must validate | Business data inside DTO/record |
| **Client diagnostic metadata** | Client-supplied | Copy allowlisted fields only, validate format/length, never use for authorization |
| **Identity/tenant/role** | Authentication component or policy server | Built from verified principal/tenant context |
| **Routing decision** | Tested internal policy | Computed from validated payload and trusted context |
| **Reply/error destination** | Trusted gateway/adapter/endpoint configuration | Never accepted arbitrarily from clients |
| **Correlation/sequence** | Designated orchestration component | Prevent clients from forcing groupId/sequence to corrupt Aggregators |
| **Framework metadata** | Spring Messaging | Let the framework manage id/timestamp |

### 4.1. Ingress is not the place to copy messages verbatim

At the client → application boundary, build a **new Message from the validated payload**. Attach only headers computed or verified by the server. Never copy all headers and then try to strip a few banned names: a denylist can miss new adapter-specific or custom headers introduced later.

### 4.2. You can keep `clientRequestId`, but constrain it

A client-provided `requestId` can help customer support, yet strictly for **lookup**:

- Restrict charset and length, e.g., 1–64 ASCII letters, digits, underscores, and hyphens.
- Never use it as an authentication token, privileged routing key, or sole idempotency key without validation.
- Distinguish **`clientRequestId`** from server-generated **`serverEventId`**.
- Avoid placing uncontrolled values into metric labels or logs vulnerable to control-character injection.

## 5. Java example: creating a clean message at the trust boundary

Suppose an API receives an order. An authentication component has already produced a **`VerifiedActor`** containing trustworthy `userId` and `tenantId`; this actor comes from server verification and **must never be built directly from client-passed body/headers**.

### 5.1. Payload and authenticated context

~~~java
import java.math.BigDecimal;

record OrderReceived(String orderId, BigDecimal totalVnd) {}

record VerifiedActor(String userId, String tenantId) {}
~~~

Example factory creating a fresh message with allowlisted metadata:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TrustedOrderMessageFactory {
    private static final BigDecimal REVIEW_THRESHOLD =
            new BigDecimal("10000000");

    private TrustedOrderMessageFactory() {}

    static Message<OrderReceived> create(
            OrderReceived order,
            VerifiedActor actor,
            Map<String, ?> externalHeaders) {

        Objects.requireNonNull(actor, "Verified actor required");
        Objects.requireNonNull(externalHeaders, "Headers required");
        if (actor.userId() == null || actor.userId().isBlank()
                || actor.tenantId() == null || actor.tenantId().isBlank()) {
            throw new IllegalArgumentException("Unverified actor");
        }
        if (order == null || order.orderId() == null
                || !order.orderId().matches("[A-Za-z0-9-]{1,40}")
                || order.totalVnd() == null
                || order.totalVnd().signum() <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        String route = order.totalVnd().compareTo(REVIEW_THRESHOLD) >= 0
                ? "REVIEW" : "STANDARD";

        MessageBuilder<OrderReceived> builder =
                MessageBuilder.withPayload(order)
                        .setHeader("trustedRoute", route)
                        .setHeader("trustedTenant", actor.tenantId())
                        .setHeader("authenticatedUserId", actor.userId())
                        .setHeader("serverEventId", UUID.randomUUID().toString());

        // Only one diagnostic metadata field is allowed from the client.
        Object candidate = externalHeaders.get("clientRequestId");
        if (candidate instanceof String value
                && value.matches("[A-Za-z0-9_-]{1,64}")) {
            builder.setHeader("clientRequestId", value);
        }

        // Intentionally do not copy client-sent values like tenantId,
        // trustedRoute, replyChannel, errorChannel, routingSlip.
        return builder.build();
    }
}
~~~

Explanation:

1. **`OrderReceived`** holds only customer-proposed data, carrying no routing authority.
2. **`VerifiedActor`** must originate from server authentication/authorization logic. Naming a record `VerifiedActor` does not make it secure on its own.
3. **`trustedRoute`** is determined by the **validated** amount and server policy, not a client's route header.
4. **`trustedTenant`** is set from verified identity, never copied from a client-claimed `tenantId`.
5. **`serverEventId`** is minted server-side. For retryable or deduplicated events, apply a deterministic eventId/idempotency allocation mechanism rather than minting a fresh UUID on every retry.
6. **`clientRequestId`** is accepted only when valid and **never used for authorization**; malformed values are ignored per the illustrative policy.

The factory above is an **illustrative principle example**. In production applications, authentication should rely on Spring Security or an equivalent trusted mechanism, verify tenant permissions, limit request sizes, enforce review policies, and bound logged/persisted data. Also test paths that could bypass the factory if multiple internal producers exist.

### 5.2. Using `MessageBuilder.fromMessage`

**`fromMessage(existing)`** suits creating derived messages **inside an already trusted zone**; it starts from the previous message's payload/headers. If `existing` came from an untrusted source, calling `fromMessage` can **retain dangerous headers**.

~~~java
// Use only after incoming has passed authentication and normalization.
Message<OrderReceived> checked = MessageBuilder.fromMessage(trustedMessage)
        .setHeader("validated", true)
        .build();
~~~

If a Transformer or adapter automatically forwards input headers, check the endpoint's **header propagation** rules. Returning a payload or new Message from a step does not always strip all prior headers. To enforce safe boundaries, design message-rebuilding points explicitly and test actual outputs via integration tests.

## 6. Locking down the router with fixed channel mappings

In Spring Integration, **`HeaderValueRouter`** reads a designated header. The header value can be a business key or a channel name. The second option is flexible yet **unsuitable for untrusted inputs**: if the routing key acts directly as a channel name, a sender could cause the application to resolve an unintended channel bean.

To reduce this risk, combine:

- An **internal header** produced by the server, such as `trustedRoute`.
- **Fixed mappings** from business values `STANDARD`/`REVIEW` to channel names.
- **`channelKeyFallback(false)`** so unmapped keys are never tried as channel names.
- A **default output channel** to handle unrecognized keys without arbitrary dispatch.
- **No direct exposure from untrusted networks or brokers to `trustedIngressChannel`**.

### 6.1. Configuring `HeaderValueRouter`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class SecureHeaderRoutingConfig {

    @Bean
    MessageChannel trustedIngressChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel manualReviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel unroutableOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow securedOrderRoutingFlow() {
        HeaderValueRouter router = new HeaderValueRouter("trustedRoute");
        router.setChannelMapping("STANDARD", "standardOrdersChannel");
        router.setChannelMapping("REVIEW", "manualReviewChannel");
        router.setDefaultOutputChannelName("unroutableOrdersChannel");
        router.setChannelKeyFallback(false);

        return IntegrationFlow.from("trustedIngressChannel")
                .route(router)
                .get();
    }
}
~~~

**Routing rules**

| `trustedRoute` value | Destination |
| --- | --- |
| STANDARD | standardOrdersChannel |
| REVIEW | manualReviewChannel |
| Unmapped value or null | unroutableOrdersChannel, via fallback |

Channels must have actual subscribers/endpoints receiving messages. You can attach Service Activators to each branch; the unroutable branch should record safe metadata, emit alerts, or quarantine when internal errors require investigation. Never treat falling into fallback as **completed business processing**.

Example business ports ensuring each branch owns only its responsibility:

~~~java
interface StandardOrderPort {
    void accept(OrderReceived order);
}

interface ManualReviewPort {
    void review(OrderReceived order);
}

interface UnroutableOrderPort {
    void quarantine(OrderReceived order);
}
~~~

### 6.2. Producer authorized to send to `trustedIngressChannel`

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Service;

@Service
class OrderIngressService {
    private final MessageChannel trustedIngress;

    OrderIngressService(
            @Qualifier("trustedIngressChannel") MessageChannel trustedIngress) {
        this.trustedIngress = trustedIngress;
    }

    void accept(
            OrderReceived request,
            VerifiedActor verifiedActor,
            Map<String, ?> externalHeaders) {
        Message<OrderReceived> safeMessage =
                TrustedOrderMessageFactory.create(
                        request, verifiedActor, externalHeaders);

        if (!trustedIngress.send(safeMessage)) {
            throw new IllegalStateException("Channel rejected message");
        }
    }
}
~~~

**Important:** this is an illustrative service running after authentication/authorization. A REST controller must obtain `verifiedActor` from the security context, never calling `new VerifiedActor` with `userId`/`tenantId` from the request body. If other producers can send messages straight to `trustedIngressChannel`, enforce identical verification at those entrypoints or add an appropriate guard layer. **The header name `trustedRoute` does not create trust by itself**.

### 6.3. Why must `channelKeyFallback` be disabled?

Per the **`AbstractMappingMessageRouter`** API, when **`channelKeyFallback=true`**, an unmapped key can be tried as a **channel name to resolve**. This is convenient for fully trusted internal apps, yet dangerous if external inputs directly influence the key.

For example, suppose a message carries:

~~~text
trustedRoute = internalAdminChannel
~~~

If the key is unmapped while the router is allowed to resolve names directly, an identically named channel outside the allowlist can be selected. A key pointing back to an upstream router could even trigger a synchronous loop.

With **`channelKeyFallback(false)`**, **`internalAdminChannel`** is outside the `STANDARD`/`REVIEW` allowlist and takes the fallback path or raises an error, depending on configuration. Since **Spring Integration 6.0**, setting a default output channel also disables `channelKeyFallback` by default; setting `false` explicitly still documents the security contract and guards against unintended shifts.

**`resolutionRequired`** is a separate setting: it decides whether an **explicitly mapped yet unresolvable channel name** may be ignored. In sensitive routing configs, keep **`resolutionRequired=true`** so misspelled channel names fail visibly. A default route is no substitute for fixing broken wiring.

### 6.4. `HeaderValueRouter` is not authorization checking

The Router does not know whether a `verifiedActor` is permitted to approve orders or export another tenant's data. Even when a header originates from an authenticated server step, downstream handlers must still enforce critical business authorization preconditions.

For instance, routing a high-value order to manual review does not mean the caller is authorized to **skip review** or **approve** the order. The approval step must verify the operator's identity, role, tenant, and order state at execution time.

## 7. Using Header Filter and Header Enricher in the right places

Spring Integration provides **Header Filter** to strip named headers before the next step, and **Header Enricher** to add headers. They help sanitize metadata when a message crosses into another domain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
IntegrationFlow removeTemporaryHeaderFlow() {
    return IntegrationFlow.from("validatedMessageChannel")
            .headerFilter("debugOnly", "temporaryRouteHint", "externalNote")
            .channel("nextProcessingChannel")
            .get();
}
~~~

This snippet requires `validatedMessageChannel` and `nextProcessingChannel` to be declared. Header Filter removes only **the listed names**; it does not automatically scrub every potentially dangerous field. For APIs with untrusted inputs, **denylist filtering never replaces rebuilding messages via an allowlist at ingress**.

Header Enricher can attach server-computed metadata:

~~~java
@Bean
IntegrationFlow addVerifiedSourceFlow() {
    return IntegrationFlow.from("internalVerifiedChannel")
            .enrichHeaders(h -> h.header(
                    "sourceSystem", "trusted-order-api"))
            .channel("normalizedEventsChannel")
            .get();
}
~~~

In real systems, never assume naming a header "verified" proves the sender was authenticated. Define **who is permitted to invoke the enrichment endpoint** and **where the values originate**.

### 7.1. Do not indiscriminately strip framework headers

Headers like **`replyChannel`**, **`errorChannel`**, **`correlationId`**, **`sequenceNumber`**, and **`sequenceSize`** may be needed by Gateway, Splitter, Aggregator, or error flows. Deleting them mid-way through a verified flow can cause:

- Gateways losing the reply path or timing out;
- error handling misdirecting failures;
- Aggregators failing to collect complete child messages.

Therefore, the best defense is **preventing untrusted sources from injecting control headers**, then preserving framework- or trusted-component-managed metadata across necessary hops. Only use Header Filter when you know a header's lifecycle has ended.

### 7.2. HTTP and broker header mappers

Adapters can map headers from HTTP, JMS, AMQP, or Kafka into Spring Message headers. Exact rules depend on the adapter, inbound/outbound mapper settings, and framework version. When an app only needs a few diagnostic headers:

1. Configure **allowlist** mapping on the adapter where supported.
2. Validate types, lengths, and formats of accepted headers.
3. Separate **external headers** from **internal headers** with distinct names and ownership.
4. Rebuild the message at the authentication boundary before entering sensitive channels.
5. Test real adapters to catch mapped headers colliding with internal header names.

Never treat an **`X-`** prefix or an unverified value passed in an HTTP Authorization header as proof of authentication. Trust comes from **verification**, not field names.

## 8. Common attack vectors and mitigations

| Scenario | Risk | Primary mitigation |
| --- | --- | --- |
| Client sends `trustedRoute=MANUAL_REVIEW` | Steers routing against policy | Server computes route; allowlisted mappings |
| Client sends arbitrary channel name as route | Resolves unintended bean/channel | `channelKeyFallback(false)` |
| Client sends another org's `tenantId` | Cross-tenant access | Derive tenant from verified principal; verify at consumer |
| Client sends `role=ADMIN` | Privilege escalation | Never treat headers as authority |
| Client supplies its own `replyChannel` | Can hijack reply destination | Trusted gateway/endpoint owns reply path |
| Client sends anomalous `errorChannel` | Distorts error reporting | Manage error flows via config and trusted headers |
| Client injects `routingSlip` | Diverts through unexpected hops | Reject/ignore arbitrary `routingSlip` at ingress |
| Client sets `correlationId` matching another group | Mixes groups or breaks Aggregator | Orchestrator mints group keys from verified data |
| Client sets ultra-high `priority` | Starves `PriorityChannel` resources | Enforce permissions and priority policies |
| Header contains CR/LF or huge strings | Log injection, resource bloat | Validate format, cap sizes, escape logs |
| Transformer inadvertently retains headers | Forged headers survive downstream | Inspect propagation and test endpoint outputs |
| Bypassing factory straight to internal channel | Skips authentication step | Guard/restrict ingress; audit all producers |

**Defense in depth** makes sense: validate inputs, verify identity, mint trusted metadata, use allowlist mappings, re-check permissions in consumers, and monitor. No single control replaces the others.

## 9. When routing keys are invalid: fallback, fail fast, and quarantine

Even with server-generated data, bugs, version skew, or misconfigurations happen: for example, a policy service returns `REVIEW_FAST` while the router only knows `STANDARD` and `REVIEW`.

~~~mermaid
flowchart TD
    M["Message with trustedRoute"] --> R{"HeaderValueRouter"}
    R -->|"STANDARD"| A["Standard handler"]
    R -->|"REVIEW"| B["Manual review handler"]
    R -->|"Unmapped value"| F["Unroutable channel"]
    F --> Q["Record reason, alert, investigate"]
~~~

**Three common policies:**

1. **Fail fast:** no default channel; router raises an error if no target resolves. Suitable when all keys belong to a closed contract.
2. **Quarantine:** default output channel captures unmapped messages for investigation. To survive restarts, the endpoint must durably persist messages and metadata.
3. **Intentional discard:** default to `nullChannel` when dropping messages is genuinely permitted. For payments, approvals, or audits, silent discard is rarely acceptable.

**A default output channel does not rescue every failure.** If the router selects a `DirectChannel` lacking subscribers, or a downstream handler throws an exception, that is a dispatch/processing error. With `QueueChannel`, `send` may succeed even though the consumer has not run yet. Each failure mode needs dedicated error flows, retries, and metrics.

Do not retry an unmapped message endlessly: retrying will not invent a missing mapping. Separate **unknown keys** from **transient system failures**.

## 10. Trusted headers across Router, Filter, Transformer, Splitter, and Aggregator

In a complete pipeline, header protection coordinates with other patterns:

| Pattern | How headers affect it | Protection principle |
| --- | --- | --- |
| **Router** | `eventType`, `routeCode` pick channels | Use only normalized keys and explicit mappings |
| **Filter** | `tenantId`, `priority`, `featureFlag` decide acceptance | Never treat client headers as permission proof |
| **Transformer** | May copy/propagate inbound headers | Strip expired metadata; verify output |
| **Splitter** | Emits child messages with correlation/sequence | Let trusted components manage grouping |
| **Aggregator** | Groups by correlation and release strategy | Block forged group keys; bound message store |
| **Gateway** | `replyChannel`, `errorChannel`, request/reply | Let only trusted gateways manage reply/error routing |
| **Retry** | Error paths may replay messages | Stable event ID, idempotent consumers |
| **Observability** | `traceId`, `correlationId` appear in logs/metrics | Separate client hints from server-verified traces |

### 10.1. Do not confuse correlation ID with identity/authorization

A `correlationId` like `ORD-107` only groups or tracks messages; it does not prove the sender owns `ORD-107`. If a consumer loads records using `correlationId`, it must still check tenant and permissions.

With Splitter/Aggregator, letting external actors choose `correlationId` or `sequenceSize` can corrupt grouping, inflate pending groups, or exhaust the `MessageStore`. A trusted orchestrator must assign or validate group metadata before the Aggregator runs.

### 10.2. Headers alone are not cryptographic sender signatures

Attaching `verified=true`, `internal=true`, or `sourceSystem=trusted-api` **is not cryptographic proof**. When messages traverse a shared broker with multiple producers or untrusted systems, enforce producer authentication, topic/queue ACLs, protected transport channels, and where needed, signature verification or integrity protocols.

Conversely, a tightly controlled internal system does not necessarily have to sign every single header. Protection depth depends on your threat model and deployment boundaries.

## 11. Testing: forged inputs cannot alter server decisions

A test proving only that `HeaderValueRouter` reads a header does not satisfy security requirements. Verify **the end-to-end path**: client input → authentication/normalization boundary → constructed message → router → exact destination.

### 11.1. Unit testing the clean-message factory

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;

class TrustedOrderMessageFactoryTest {

    @Test
    void untrustedHeadersCannotOverrideRouteTenantOrReplyChannel() {
        OrderReceived order = new OrderReceived(
                "ORD-107", new BigDecimal("250000"));
        VerifiedActor actor = new VerifiedActor(
                "user-42", "tenant-A");

        Map<String, Object> clientHeaders = Map.of(
                "trustedRoute", "manualReviewChannel",
                "trustedTenant", "tenant-victim",
                "replyChannel", "privilegedOpsChannel",
                "errorChannel", "privilegedOpsChannel",
                "routingSlip", "privilegedOpsChannel",
                "clientRequestId", "REQ_107");

        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        order, actor, clientHeaders);

        assertEquals("STANDARD",
                result.getHeaders().get("trustedRoute"));
        assertEquals("tenant-A",
                result.getHeaders().get("trustedTenant"));
        assertEquals("user-42",
                result.getHeaders().get("authenticatedUserId"));
        assertEquals("REQ_107",
                result.getHeaders().get("clientRequestId"));
        assertNotNull(result.getHeaders().get("serverEventId"));

        assertNull(result.getHeaders().get("replyChannel"));
        assertNull(result.getHeaders().get("errorChannel"));
        assertNull(result.getHeaders().get("routingSlip"));
    }

    @Test
    void highValueOrderUsesReviewPolicyRegardlessOfClientHint() {
        OrderReceived order = new OrderReceived(
                "ORD-108", new BigDecimal("12000000"));

        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        order,
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("trustedRoute", "STANDARD"));

        assertEquals("REVIEW",
                result.getHeaders().get("trustedRoute"));
    }

    @Test
    void invalidOrderIsRejectedBeforeRouting() {
        assertThrows(IllegalArgumentException.class,
                () -> TrustedOrderMessageFactory.create(
                        new OrderReceived("", BigDecimal.ZERO),
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("trustedRoute", "REVIEW")));
    }

    @Test
    void malformedDiagnosticHeaderIsNotPropagated() {
        Message<OrderReceived> result =
                TrustedOrderMessageFactory.create(
                        new OrderReceived(
                                "ORD-109", new BigDecimal("500000")),
                        new VerifiedActor("user-42", "tenant-A"),
                        Map.of("clientRequestId", "bad\nvalue"));

        assertNull(result.getHeaders().get("clientRequestId"));
    }
}
~~~

These unit tests verify that forged headers are discarded and routing decisions follow server policy. They **do not** prove the API obtains `VerifiedActor` from a trusted source; test the authentication/inbound adapter layer separately.

### 11.2. Integration test: unknown keys never turn into channel names

This test intentionally sends a message straight to **`trustedIngressChannel`** with a key matching another internal channel name to verify the second defense line: **`channelKeyFallback=false`**. It demonstrates router safety even if an internal producer malfunctions or bypasses the factory.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.HeaderValueRouter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(HeaderRoutingIsolationTest.TestConfig.class)
class HeaderRoutingIsolationTest {

    @Configuration
    @EnableIntegration
    static class TestConfig {
        @Bean
        MessageChannel trustedIngressChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel standardOrdersChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel manualReviewChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel unroutableOrdersChannel() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel privilegedOpsChannel() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow routingFlow() {
            HeaderValueRouter router =
                    new HeaderValueRouter("trustedRoute");
            router.setChannelMapping(
                    "STANDARD", "standardOrdersChannel");
            router.setChannelMapping(
                    "REVIEW", "manualReviewChannel");
            router.setDefaultOutputChannelName(
                    "unroutableOrdersChannel");
            router.setChannelKeyFallback(false);
            return IntegrationFlow.from("trustedIngressChannel")
                    .route(router)
                    .get();
        }
    }

    @Autowired
    @Qualifier("trustedIngressChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("unroutableOrdersChannel")
    SubscribableChannel unroutable;

    @Autowired
    @Qualifier("privilegedOpsChannel")
    SubscribableChannel privileged;

    @Test
    void arbitraryChannelNameCannotEscapeTheAllowlist() {
        List<String> received = new ArrayList<>();
        MessageHandler fallbackHandler =
                message -> received.add("unroutable");
        MessageHandler privilegedHandler =
                message -> received.add("privileged");

        unroutable.subscribe(fallbackHandler);
        privileged.subscribe(privilegedHandler);
        try {
            assertTrue(input.send(
                    MessageBuilder.withPayload("probe")
                            .setHeader(
                                    "trustedRoute",
                                    "privilegedOpsChannel")
                            .build()));

            assertEquals(List.of("unroutable"), received);
        } finally {
            unroutable.unsubscribe(fallbackHandler);
            privileged.unsubscribe(privilegedHandler);
        }
    }
}
~~~

The test pre-registers **`privilegedOpsChannel`** to prove an unmapped key **is not resolved directly** to that channel. With a synchronous `DirectChannel`, results can be asserted right after `send()`. If any destination switches to an `ExecutorChannel` or `QueueChannel`, tests must wait and assert under async semantics.

### 11.3. Recommended security test matrix

| Scenario | Expected outcome |
| --- | --- |
| Client sets `trustedRoute=REVIEW` on small order | Server route remains `STANDARD` |
| Client sets `trustedRoute=STANDARD` on large order | Server route remains `REVIEW` |
| Client spoofs another tenant's `trustedTenant` | Internal header holds verified identity's tenant |
| Client sends `replyChannel`/`errorChannel`/`routingSlip` | Never copied raw into internal message |
| Unmapped key matches another channel's name | Enters fallback or fails; never enters non-allowlisted channel |
| Missing/malformed `clientRequestId` | Does not alter auth or routing |
| Client sends incomplete or mistyped payload | Rejected prior to router per validation policy |
| HTTP adapter maps a header matching route name | Ingress boundary strips or rebuilds the header cleanly |
| Internal producer bypasses ingress factory | Blocked by internal ingress controls/checks |
| Request/reply Gateway uses framework headers | Reply/error paths keep working after normalization |
| Message enters Splitter/Aggregator | Correlation/sequence come only from trusted components |
| Retrying same event after failure | No duplicate side effects thanks to `eventId`/idempotency policy |

### 11.4. Testing valid cases too

Overly strict controls can break legitimate flows. Alongside negative tests, verify:

- `STANDARD` orders reach the right handler and get processed.
- `REVIEW` orders reach the manual review branch.
- Valid `clientRequestId` still aids log lookup without becoming authority.
- Gateways handling request/reply retain proper framework-managed `replyChannel`.
- Correlation IDs/sequences emitted by Splitters reach Aggregators and release groups on schedule.
- The Router only picks the channel; downstream Service Activators still check tenant, role, and business state before sensitive side effects.

## 12. Observing and responding to anomalous headers

Header-spoofing attempts can happen without the application throwing exceptions, so monitor key signals:

| Signal | Meaning |
| --- | --- |
| **invalid_external_header_count** | Inputs dropped due to invalid format or length |
| **routing_fallback_count** | Unmapped trusted routes or messages hitting fallback |
| **channel_resolution_failure_count** | Misconfigured route or missing channel |
| **tenant_authorization_denied_count** | Consumer rejected cross-tenant operation |
| **unexpected_header_propagation_count** | Banned header detected past the trust boundary |
| **reply_or_error_route_failure_count** | Gateway or error handler failed to resolve return path |
| **event_replay_duplicate_count** | Re-delivered event already processed earlier |

Metric labels should use **bounded sets** of route names and error categories—never use raw `userId`, raw headers, or `eventId` as labels. Escape logs and minimize sensitive data. For suspected spoofing, log timestamp, verified source, violated policy, and server-minted correlation to support investigation.

A bad-header alert **does not prove an attack on its own**: an adapter may be misconfigured or a new producer may be emitting an unexpected header. Investigate using evidence and inspect real mapping paths.

## 13. Hands-on exercise: securing a refund system router

Design a flow accepting **`RefundRequested(refundId, paymentId, amountVnd)`**. Clients can submit refund requests, yet cannot choose their own approvers.

**Business requirements:**

1. Valid refunds under 2 million can go to standard review.
2. Refunds of 2 million or more require enhanced review.
3. Every request must bind to the verified tenant and identity.
4. Clients cannot select **`manualApprovalChannel`**, **`adminOverrideChannel`**, or `replyChannel`.
5. Diagnostic-only headers like `clientRequestId` must enforce format/length bounds.
6. The Router maps only **`STANDARD`** and **`ENHANCED_REVIEW`** to valid channels; unknown keys go to quarantine or raise an error.

**Implementation steps:**

1. Define `RefundRequested` and `VerifiedActor` records; define the boundary building `VerifiedActor` from the security context.
2. Write `RefundMessageFactory` taking payload/actor and an untrusted headers map, keeping only valid `clientRequestId`.
3. Derive header **`trustedRefundRoute`** from `amountVnd` after validating data and permissions.
4. Declare `HeaderValueRouter` with two channel mappings, `channelKeyFallback(false)`, and a default output channel.
5. Write unit tests where a client sends `trustedRefundRoute=adminOverrideChannel`, fake `tenantId`, `replyChannel`, and `routingSlip`; assert none survive on the internal message.
6. Add an integration test with an unknown key matching `adminOverrideChannel`, proving it never enters that channel.
7. Simulate an async processing branch and verify error channel, retry, and idempotency by `refundId`/`eventId`.
8. Write a test scenario where a Gateway receives replies without taking `replyChannel` from the client.

### Self-check questions

1. Why does immutable `MessageHeaders` not guarantee trustworthy headers?
2. Which external inputs can influence Spring Message headers?
3. Why is `copyHeaders` plus `setHeaderIfAbsent` unsafe at a trust boundary?
4. What can happen with `channelKeyFallback(true)` when routing keys are client-controlled?
5. How do `channelKeyFallback` and `resolutionRequired` differ?
6. When is it safe to retain a client-supplied `clientRequestId`?
7. Why should you avoid arbitrarily deleting `replyChannel` mid-way through a verified Gateway flow?
8. Why can `tenantId` or `role` headers never replace authorization checks?
9. What can go wrong for retries and Aggregators if clients choose `correlationId`?
10. How do you test to prove messages only enter allowlisted channels?

## 14. Production readiness checklist for Header-Based Routers

- Classified **data sources** and defined trust boundaries at every adapter/gateway.
- Identity, tenant, and permissions are verified by the server, never copied from client inputs.
- Routing headers are computed from policy and validated data.
- Router enforces an **allowlist channel mapping** and **`channelKeyFallback(false)`**.
- Missing/unknown keys have explicit **fail fast, quarantine, or discard** policies.
- Untrusted headers are never copied, including `replyChannel`, `errorChannel`, `routingSlip`, and `priority`.
- Diagnostic headers enforce length/format constraints and never grant access.
- Verified propagation across Transformers, Filters, Gateways, and adapters.
- Consumer authorization checks run before sensitive side effects.
- Tests cover spoofing of routes, tenants, channel names, control headers, plus valid happy paths.
- Error flows, retries, idempotency, and correlation are owned by trusted components.
- Metrics and logs detect unknown keys without leaking sensitive data.

**Conclusion:** A Header-Based Router makes decisions from **metadata**. Metadata is only safe when it has a **verified origin and clear ownership for creation/updates**. Build clean messages from validated payloads, attach server-verified tenant/permission info, use fixed mappings, and disable channel-name fallback. Protecting both ingress and consumers lets Spring Integration combine Router, Filter, Gateway, and other patterns into verifiable processing flows.

## References

- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): `HeaderValueRouter`, channel mappings, and destination resolution mechanisms.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): `channelKeyFallback`, `resolutionRequired`, `defaultOutputChannel`, and warnings about malicious routing keys.
- [Spring Integration Reference — Transformer / Header Filter](https://docs.spring.io/spring-integration/reference/transformer.html): removing specific headers and transformation rules.
- [Spring Integration Reference — Content Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): Header Enricher and endpoint metadata ownership.
- [Spring Integration Reference — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): header mapping at HTTP adapters/gateways.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): effects of channel types on dispatch, threading, and errors.
