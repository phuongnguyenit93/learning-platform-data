# Mapping Headers to Parameters

## 1. Why does a Service Activator need to read both payload and headers?

In the **SPRING_INTEGRATION_PATTERN** module, we learn how to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows. When Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation work together, a Service Activator is typically where a message connects to a Java method that executes business logic.

Suppose a message requests recording a payment:

~~~text
Spring Message
├── headers
│   ├── trustedTenantId = tenant-a
│   ├── businessEventId = evt-payment-1042
│   ├── businessCorrelationKey = payment:v1:tenant-a:PAY-1042:3
│   ├── sourceSystem = BILLING
│   ├── traceId = trace-abc
│   ├── id = <Spring-generated Message ID>
│   └── timestamp = <Spring-generated timestamp>
└── payload
    ├── paymentId = PAY-1042
    ├── amountMinor = 125000
    ├── currencyCode = VND
    └── workflowEpoch = 3
~~~

The business method needs **the amount and payment ID** from the payload. But it also needs the **verified tenant**, the **eventId** to prevent duplicate processing, and the **businessCorrelationKey** to link the workflow. If every handler had to manually inspect `MessageHeaders` and cast types by hand, code would quickly become verbose, framework-coupled, and prone to missing validation.

Spring Integration lets a Service Activator method declare the exact parameters it needs:

~~~java
@ServiceActivator(inputChannel = "verifiedPayments")
public PaymentReceipt handle(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey) {
    // ...
}
~~~

The framework extracts the payload and header values from the **Spring Message being processed**, then passes them into the Java invocation. This is **method argument mapping**, not turning arbitrary external HTTP headers into trusted data.

### Lesson objectives

After this lesson, you will be able to:

1. Distinguish **payload**, **Spring MessageHeaders**, **application/transport headers**, and **method arguments**.
2. Use **@Payload**, **@Header**, and **@Headers** properly with methods annotated with **@ServiceActivator**.
3. Understand how required headers, optional headers, wrong-type headers, and type conversion rules are handled.
4. Choose between handlers taking separate arguments, handlers taking **Message<?>**, and Java DSL **.handle(...)**.
5. Design trust boundaries so tenant, role, replyChannel, or routing metadata cannot be spoofed.
6. Preserve business correlation, eventId, and sequence metadata as messages traverse subflows/adapters.
7. Distinguish **reply-returning handlers** from **one-way handlers**, sync/async errors, and retry/idempotency.
8. Write unit tests and Spring Integration integration tests verifying header values are mapped accurately.

## 2. Service Activator in Enterprise Integration Patterns

A **Service Activator** connects the messaging world to a business service or method. A Message is sent to an endpoint; the endpoint extracts data, invokes a Java method, and depending on the contract, may produce a reply.

~~~mermaid
flowchart LR
    A["Inbound adapter / Gateway"] --> B["MessageChannel"]
    B --> S["Service Activator"]
    S --> M["Java business method"]
    M -->|"Reply payload or Message"| R["Output / reply channel"]
    M -->|"Error"| E["Caller / errorChannel policy"]
~~~

A Service Activator typically:

- Receives a message that has passed validation, routing, or transformation steps.
- Converts the required information into Java arguments.
- Invokes a business service, which may persist data or call external systems.
- Returns a result if the flow requires request/reply.
- Lets the framework/flow handle replies, exceptions, retries, and error channels per configuration.

**@ServiceActivator** is a Spring Integration endpoint annotation; **@Payload**, **@Header**, and **@Headers** belong to Spring Messaging's method parameter annotations.

### 2.1. One message does not mean one HTTP call

The same Service Activator can be triggered by:

- A Gateway translating a Java call into a Spring Message.
- An HTTP/JMS/AMQP/Kafka inbound adapter after conversion and authentication.
- A Router or Transformer inside an IntegrationFlow.
- A branch of a Splitter or Aggregator.
- A message redelivered after a retry/restart.

Therefore, **Spring Message headers** are not always **HTTP headers**. Their source may be an internally constructed Java object, a header mapped from a broker, or a value attached by a Gateway/Transformer.

### 2.2. At which layer does mapping happen?

~~~mermaid
flowchart TD
    W["Wire: HTTP / broker / file"] --> P["Parse + authenticate"]
    P --> M["Spring Message payload + headers"]
    M --> A["@ServiceActivator method invocation"]
    A --> H["@Payload -> Java payload"]
    A --> X["@Header -> single header"]
    A --> Y["@Headers -> header Map"]
    H --> B["Business operation"]
    X --> B
    Y --> B
~~~

**Mapping headers to parameters** happens at the point of handler invocation. If ingress carried wrong or spoofed headers, annotations cannot fix that mismatch on their own. Data protection at the trust boundary must happen **before** the Service Activator.

## 3. Three frequently used annotations

| Annotation / parameter type | Input taken from Message | When to use |
| --- | --- | --- |
| **@Payload PaymentSubmitted** | Payload, with conversion applied if configured | Core logic relies on typed payload |
| **@Header("trustedTenantId") String** | A single header with an exact name | Handler needs one specific metadata field |
| **@Header(value="sourceSystem", required=false) String** | Optional header | Supplementary non-mandatory metadata |
| **@Headers Map<String, Object>** | Header map | Need to inspect or verify multiple headers |
| **Message<PaymentSubmitted>** | Entire Spring Message | Messaging-level operations needing headers/reply context |
| **MessageHeaders** | Framework headers collection | Need to read all metadata |

**@Payload** and **@Header** clarify parameter intent rather than hoping the framework infers them from Java variable names or argument order. For a Service Activator with multiple parameters, explicit annotations keep code stable across refactors.

### 3.1. @Header selects the exact header name

~~~java
import org.springframework.messaging.handler.annotation.Header;

void inspect(
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId) {
    // ...
}
~~~

Both header name strings must **match exactly** the values set on the Spring Message. Do not assume Spring automatically translates HTTP header **X-Tenant-Id** into Spring header **trustedTenantId**; that translation must be performed and verified at the inbound adapter.

### 3.2. @Payload binds the payload to a parameter

~~~java
import org.springframework.messaging.handler.annotation.Payload;

void inspect(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId) {
    // ...
}
~~~

The payload class should have its own schema/validation. Simply adding `@Payload` does not prove the payload has been authenticated or belongs to the tenant declared in the header.

### 3.3. @Headers is used when multiple metadata fields are needed

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;

void audit(
        @Payload PaymentSubmitted payment,
        @Headers Map<String, Object> headers) {

    Object correlation = headers.get("businessCorrelationKey");
    Object source = headers.get("sourceSystem");
    // Read only needed metadata; do not log all headers.
}
~~~

**@Headers** is not a reason to pass all headers into the business layer. Many headers are infrastructure metadata (`replyChannel`, `errorChannel`, sequence/correlation IDs, broker delivery tags) or may contain sensitive data. It is better to select specific headers when the business method only needs a few fields.

### 3.4. Do not mutate MessageHeaders to alter data

By contract, Spring `MessageHeaders` is an immutable set of metadata. If you need to update a header for the next message, use **MessageBuilder**, a header enricher, or a transformer that creates a new Message:

~~~java
Message<?> result = MessageBuilder
        .fromMessage(incoming)
        .setHeader("processingStage", "VALIDATED")
        .build();
~~~

Core metadata such as tenant, event ID, or business key should only change under **clear business rules and ownership**. A billing handler must never silently alter `trustedTenantId` and forward the message to another channel.

## 4. Required headers and optional headers

Spring Messaging's **@Header** has a **required** attribute; it is required by default. If a message arrives at a handler missing a header marked required, parameter resolution usually fails **before the business method runs**.

~~~java
// Required header:
@Header("trustedTenantId") String tenantId

// Optional header:
@Header(value = "traceId", required = false) String traceId
~~~

When `traceId` is absent, a reference-type parameter can be null; business code must handle that contract. Do not use primitives like **int** for a header that may be missing unless an appropriate default/conversion is configured and tested.

### 4.1. Syntactically required is not enough for business requirements

A header that is present but set to an empty string can still be invalid data:

~~~text
trustedTenantId = ""
businessEventId = "evt-1042"
~~~

`@Header` only handles extracting the data; a method/domain validator must check:

- Not null or blank.
- Matches expected pattern/length.
- Valid tenant/workflow permissions.
- Correct data type.
- Consistent relationship with the payload.

For security-sensitive metadata, **authorization checks and registry verification must occur before any business side effect**.

### 4.2. Do not use an optional header as an idempotency key

If `eventId` is absent and the handler generates a random UUID:

~~~text
attempt 1: generated-event-id = uuid-A
attempt 2: generated-event-id = uuid-B
~~~

Two deliveries of **the same logical event** will look like two distinct events. For handlers writing to a database, placing orders, or charging fees, `eventId` or `operationId` must be a **stable business identity**; if missing, halt/quarantine instead of generating a new one on each retry.

### 4.3. When should defaultValue be used?

Some method-argument binding annotations support a default value. Either way, distinguish **supplementary metadata** (such as a source label displayed in logs) from **metadata that governs permissions or business outcomes**. Never set default `tenantId="public"`, `correlationKey="unknown"`, or a random `eventId` just to bypass missing-header checks. If the source lacks a trustworthy identity, the flow should reject it before processing.

## 5. Creating payload and trusted context for the example

We will build a flow that receives payment details and returns a **PaymentReceipt**. This flow only illustrates argument mapping and simulated idempotency; it does not execute real bank transactions or charge money.

### 5.1. Payload contains only business data

~~~java
record PaymentSubmitted(
        String paymentId,
        long amountMinor,
        String currencyCode,
        int workflowEpoch) {

    PaymentSubmitted {
        if (paymentId == null
                || !paymentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_PAYMENT_ID");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT");
        }
        if (!"VND".equals(currencyCode)
                && !"USD".equals(currencyCode)) {
            throw new IllegalArgumentException("UNSUPPORTED_CURRENCY");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record PaymentReceipt(
        String tenantId,
        String paymentId,
        String eventId,
        String businessCorrelationKey,
        String decision) {
}
~~~

**PaymentSubmitted does not contain `trustedTenantId` or authorization roles.** The tenant must be verified by ingress or the application service. A client writing `tenantId` in JSON must not become the Spring header `trustedTenantId` merely because the field names look alike.

### 5.2. Context created by the trust boundary

~~~java
record VerifiedPaymentContext(
        String tenantId,
        String eventId,
        String sourceSystem) {

    VerifiedPaymentContext {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")
                || eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,96}")
                || sourceSystem == null
                || !sourceSystem.matches("[A-Z_]{1,40}")) {
            throw new IllegalArgumentException("INVALID_VERIFIED_CONTEXT");
        }
    }
}

interface PaymentAuthorization {
    void assertAllowed(
            VerifiedPaymentContext context,
            PaymentSubmitted payment);
}
~~~

**The name `VerifiedPaymentContext` does not magically create trustworthiness.** In production, such an object is only issued after authenticating the client/producer, checking tenant/paymentId/workflowEpoch permissions, and verifying the source. In unit tests, we use an assumed-verified context to test mapping independently of the auth system.

### 5.3. Correlation key with tenant/epoch namespace

~~~java
final class PaymentCorrelation {
    private PaymentCorrelation() {
    }

    static String key(
            String verifiedTenantId,
            PaymentSubmitted payment) {

        if (verifiedTenantId == null
                || !verifiedTenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        return "payment:v1:"
                + verifiedTenantId + ":"
                + payment.paymentId() + ":"
                + payment.workflowEpoch();
    }
}
~~~

The same logical event redelivered by a broker must carry the **same `eventId` and business key**. If the same `paymentId` is processed in a new business epoch, the new correlation key must distinguish that epoch. Do not use Spring `MessageHeaders.ID` as the business `eventId`, because that ID can change when messages are rebuilt.

## 6. Building the Message at ingress and setting owned headers

Once authorization passes, a factory constructs the Message so the downstream Service Activator does not need to know which HTTP/JMS/AMQP source delivered the event.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class TrustedPaymentMessageFactory {
    private final PaymentAuthorization authorization;

    TrustedPaymentMessageFactory(
            PaymentAuthorization authorization) {
        this.authorization = authorization;
    }

    Message<PaymentSubmitted> create(
            PaymentSubmitted payment,
            VerifiedPaymentContext context) {

        authorization.assertAllowed(context, payment);
        String groupKey = PaymentCorrelation.key(
                context.tenantId(), payment);

        return MessageBuilder.withPayload(payment)
                .setHeader("trustedTenantId", context.tenantId())
                .setHeader("businessEventId", context.eventId())
                .setHeader("businessCorrelationKey", groupKey)
                .setHeader("sourceSystem", context.sourceSystem())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupKey)
                .build();
    }
}
~~~

The **trustedTenantId**, **businessEventId**, and **businessCorrelationKey** headers are application-owned. They are attached only after permission checks. **CORRELATION_ID** is a Spring Integration technical header; in this topology we mirror the business key into it because it fits the scope, though nested Splitter/Aggregator flows may require a different correlation scope.

### 6.1. Why not use copyHeaders from the raw request?

An external request might send:

~~~http
POST /payments/events HTTP/1.1
Authorization: Bearer <redacted>
X-Tenant-Id: tenant-admin
X-Business-Event-Id: evt-stolen
X-Correlation-Id: payment:v1:tenant-admin:PAY-999:1
Content-Type: application/json

{"paymentId":"PAY-1042","amountMinor":125000,"currencyCode":"VND","workflowEpoch":3}
~~~

If the adapter copies those values verbatim into Spring headers without verification, the handler receives **untrusted @Header arguments**. Worse, a client might try injecting control headers like `replyChannel` or `errorChannel` into internal paths.

Safe workflow:

1. Parse and validate the wire payload against the supported schema.
2. Authenticate the producer (JWT/mTLS/broker identity).
3. Look up tenant, payment ownership, and `workflowEpoch` from the registry.
4. Construct **VerifiedPaymentContext** from the verified source.
5. Use **TrustedPaymentMessageFactory** to create a new Message with allowlisted headers.
6. Route the Message through an internal channel reserved for trusted messages.

**`@Header` only reads metadata; it does not perform authorization.** Never trust an annotation when the underlying data was attached without verification.

### 6.2. When headers from HTTP/JMS do not share the same names

A `HeaderMapper` can translate:

~~~text
HTTP:   X-Request-Id
JMS:    businessRequestId
AMQP:   x-request-id

            |
            v
Inbound adapter / context verifier
            |
            v
Spring header: businessEventId
~~~

Translating names and semantics should live at the **adapter or ingress boundary**. The Service Activator reads one consistent Spring Message contract instead of carrying three differently named annotations for each connector.

## 7. Service Activator binding multiple headers to individual parameters

Here is the core example of the lesson:

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

final class PaymentHeaderServiceActivator {
    private final PaymentLedger ledger;

    PaymentHeaderServiceActivator(PaymentLedger ledger) {
        this.ledger = Objects.requireNonNull(ledger);
    }

    @ServiceActivator(
            inputChannel = "verifiedPayments",
            outputChannel = "paymentReceipts")
    public PaymentReceipt accept(
            @Payload PaymentSubmitted payment,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey,
            @Header(value = "sourceSystem", required = false)
                    String sourceSystem,
            @Headers Map<String, Object> headers) {

        // @Header injects the exact field from MessageHeaders into the parameter.
        String expected = PaymentCorrelation.key(tenantId, payment);
        if (!expected.equals(groupKey)) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }

        // Only validate a supplementary metadata field; do not pass
        // all headers into the business operation.
        if (sourceSystem != null
                && !sourceSystem.matches("[A-Z_]{1,40}")) {
            throw new IllegalArgumentException("INVALID_SOURCE_SYSTEM");
        }
        if (!tenantId.equals(headers.get("trustedTenantId"))) {
            throw new SecurityException("TENANT_HEADER_MISMATCH");
        }

        // The service method processes the business event using
        // identities already obtained from trusted ingress.
        return ledger.apply(payment, tenantId, eventId, groupKey);
    }
}
~~~

**What happens when the endpoint receives a Message:**

1. Resolve the message payload → pass into **PaymentSubmitted payment**.
2. Look up header **trustedTenantId** → pass into **String tenantId**.
3. Look up header **businessEventId** → pass into **String eventId**.
4. Look up header **businessCorrelationKey** → pass into **String groupKey**.
5. Look up **sourceSystem** if present; if absent, the parameter may be null.
6. Pass the headers map into **Map<String,Object> headers**.
7. Invoke the method body and use **PaymentReceipt** as the reply payload.

Missing required headers or type-conversion failures can occur **before step 7**. Permission/correlation errors detected inside the method body occur in the handler and follow the flow's error policy.

### 7.1. Do not rely on ambiguous variable names instead of @Header

~~~java
// Recommended:
@Header("businessCorrelationKey") String groupKey

// Avoid relying on inference:
String groupKey
~~~

An unannotated `String` parameter can make method resolution hard to follow, especially when a method takes several strings: `paymentId`, `tenantId`, `eventId`, `traceId`. Explicit annotations form a stronger contract than Java variable names.

### 7.2. Why does the example also take @Headers?

To illustrate the difference between **extracting individual headers** and **receiving the full header map**. In production, if you do not need the Map, omit the `@Headers` parameter entirely to reduce coupling and avoid accidentally logging or copying sensitive metadata.

## 8. Business service and ledger: avoiding duplicate side effects

To complete the example, we define an interface for storing results and an in-memory implementation **solely for illustration/testing**.

~~~java
interface PaymentLedger {
    PaymentReceipt apply(
            PaymentSubmitted payment,
            String tenantId,
            String eventId,
            String businessCorrelationKey);
}
~~~

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

final class InMemoryPaymentLedger implements PaymentLedger {
    private final ConcurrentMap<String, Recorded> records =
            new ConcurrentHashMap<>();

    private record Recorded(
            PaymentSubmitted original,
            PaymentReceipt receipt) {
    }

    @Override
    public PaymentReceipt apply(
            PaymentSubmitted payment,
            String tenantId,
            String eventId,
            String businessCorrelationKey) {

        String dedupKey = tenantId + ":" + eventId;
        Recorded result = records.compute(dedupKey, (ignored, existing) -> {
            if (existing != null) {
                if (!existing.original().equals(payment)
                        || !existing.receipt()
                                .businessCorrelationKey()
                                .equals(businessCorrelationKey)) {
                    throw new IllegalStateException("EVENT_ID_CONFLICT");
                }
                return existing;
            }

            return new Recorded(
                    payment,
                    new PaymentReceipt(
                            tenantId,
                            payment.paymentId(),
                            eventId,
                            businessCorrelationKey,
                            "RECORDED"));
        });
        return result.receipt();
    }

    int uniqueEventCount() {
        return records.size();
    }
}
~~~

This example enables unit-testing redelivery: **same tenant/eventId and same payload** returns the same receipt; if an `eventId` is reused with a different payload, it raises a conflict. It is **not durable across restarts**, does not coordinate across multiple instances, does not provide database-level transactions, and is not a production ledger implementation.

In production, use unique keys/indexes and transactions/inbox/outbox or provider idempotency keys scoped to the real `eventId`. Never infer “exactly once” from a `ConcurrentHashMap` or merely from the Service Activator receiving the right parameters.

## 9. Registering the Service Activator and channels

The classes above can be registered as Spring beans. An endpoint is created from the method annotated with **@ServiceActivator**, and the handler receives the parameters mapped by the framework from the Message.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class PaymentHeaderFlowConfig {

    @Bean
    MessageChannel verifiedPayments() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel paymentReceipts() {
        return new QueueChannel();
    }

    @Bean
    InMemoryPaymentLedger paymentLedger() {
        return new InMemoryPaymentLedger();
    }

    @Bean
    PaymentHeaderServiceActivator paymentHeaderServiceActivator(
            InMemoryPaymentLedger ledger) {
        return new PaymentHeaderServiceActivator(ledger);
    }
}
~~~

Within **the same Spring context**, `@EnableIntegration` provides the infrastructure to process endpoint annotations like `@ServiceActivator`. Here the handler bean is registered via `@Bean`, so `@Component` on the class itself is not needed.

### 9.1. Complete processing flow

~~~mermaid
sequenceDiagram
    participant A as Trusted application ingress
    participant F as MessageFactory
    participant C as verifiedPayments
    participant S as Service Activator
    participant L as PaymentLedger
    participant O as paymentReceipts
    A->>F: PaymentSubmitted + VerifiedPaymentContext
    F->>F: Authorization + create trusted headers
    F->>C: Spring Message
    C->>S: Method argument resolution
    Note over S: @Payload, @Header, @Headers
    S->>L: apply(payment,tenant,eventId,key)
    L-->>S: PaymentReceipt
    S-->>O: Reply Message
~~~

Because **verifiedPayments** is a `DirectChannel`, the handler normally runs on the sending thread. **paymentReceipts** is a `QueueChannel` for example/test purposes. In a real system, ensure an appropriate consumer exists and avoid letting an in-memory `QueueChannel` accumulate unbounded data.

### 9.2. Why does returning PaymentReceipt produce output?

For a request/reply Service Activator, a non-null return value becomes the **reply payload** per framework rules. Because the endpoint declares **outputChannel = "paymentReceipts"**, the result is sent to that channel.

If a method only performs a side effect and returns **void**, that is a **one-way** contract: do not configure a synchronous Gateway waiting for a `PaymentReceipt` expecting a reply to appear automatically.

### 9.3. Do not register two competing endpoints on the same DirectChannel

If you register `@ServiceActivator(inputChannel="verifiedPayments")` above while also creating another `IntegrationFlow` consuming **the same `verifiedPayments` DirectChannel**, the two subscribers may compete or be selected per channel dispatch semantics, making tests unpredictable. The Java DSL examples below are **alternatives**, not configurations to add simultaneously.

## 10. Java DSL .handle(...) can also read headers

You are not required to write a `@ServiceActivator` method to process headers. Java DSL allows a handler lambda to receive **payload and headers**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import java.util.Map;

// Alternative variant to the @ServiceActivator endpoint in section 7.
@Bean
IntegrationFlow paymentDslFlow(PaymentLedger ledger) {
    return IntegrationFlow.from("verifiedPayments")
            .handle(PaymentSubmitted.class, (payment, headers) -> {
                String tenant = requiredString(
                        headers, "trustedTenantId");
                String eventId = requiredString(
                        headers, "businessEventId");
                String businessKey = requiredString(
                        headers, "businessCorrelationKey");

                if (!businessKey.equals(
                        PaymentCorrelation.key(tenant, payment))) {
                    throw new SecurityException("CORRELATION_MISMATCH");
                }

                return ledger.apply(
                        payment, tenant, eventId, businessKey);
            })
            .channel("paymentReceipts")
            .get();
}

private static String requiredString(
        Map<String, Object> headers,
        String name) {
    Object value = headers.get(name);
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "INVALID_REQUIRED_HEADER_" + name);
    }
    return text;
}
~~~

In complete code, place `requiredString` in the same configuration or an appropriate utility class. This is an **independent variant**: remove the `PaymentHeaderServiceActivator` bean or use a different input channel—never register two consumers on `verifiedPayments` when you only intend to have one handler.

### 10.1. Comparing annotations and DSL lambdas

| Criterion | @ServiceActivator with @Header | DSL .handle(payload, headers) |
| --- | --- | --- |
| Code style | Java method with annotated parameters | Lambda or handler object |
| Reading one header | Framework resolves directly into parameter | Code reads from Map manually |
| Missing header | Framework provides required semantics | Code checks manually |
| Conversion | Available via argument resolvers/conversion | Code handles casting |
| Unit testability | Call Java method directly | Extract lambda logic into service to test |
| Separation of business and messaging | Good when declaring needed metadata | Good if mapping is brief, but Map logic can bloat |
| Access to Spring MessageHeaders | `@Headers` or `Message<?>` | Passed headers `Map` |

**Neither approach automatically guarantees trustworthy data.** What matters is that ingress has checked permissions and the handler enforces a strict contract on header names, types, and semantics.

### 10.2. Put manual mapping into a separate class

When a DSL handler needs four or five headers, you can create an immutable **BusinessContext** to reduce the domain service's coupling to `MessageHeaders`:

~~~java
record PaymentBusinessContext(
        String tenantId,
        String eventId,
        String groupKey) {
}

final class PaymentContexts {
    static PaymentBusinessContext from(
            Map<String, Object> headers) {
        return new PaymentBusinessContext(
                requiredString(headers, "trustedTenantId"),
                requiredString(headers, "businessEventId"),
                requiredString(headers, "businessCorrelationKey"));
    }

    private static String requiredString(
            Map<String, Object> headers,
            String name) {
        Object value = headers.get(name);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REQUIRED_HEADER_" + name);
        }
        return text;
    }
}
~~~

This still only **converts already-verified metadata into an internal Java type**. If the context is built from unverified HTTP headers, the record merely makes code prettier without adding security.

## 11. Handler variant receiving the full Message

When an endpoint needs to inspect complex framework headers, a method can accept **Message<PaymentSubmitted>** instead of multiple annotated arguments:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

final class RawMessagePaymentHandler {
    private final PaymentLedger ledger;

    RawMessagePaymentHandler(PaymentLedger ledger) {
        this.ledger = ledger;
    }

    // Alternative variant; do not register on the same inputChannel simultaneously.
    @ServiceActivator(inputChannel = "verifiedPayments")
    public PaymentReceipt accept(Message<PaymentSubmitted> message) {
        PaymentSubmitted payload = message.getPayload();

        String tenant = (String) message.getHeaders()
                .get("trustedTenantId");
        String eventId = (String) message.getHeaders()
                .get("businessEventId");
        String key = (String) message.getHeaders()
                .get("businessCorrelationKey");

        if (tenant == null || eventId == null || key == null) {
            throw new IllegalArgumentException("MISSING_HEADER");
        }
        if (!key.equals(PaymentCorrelation.key(tenant, payload))) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }
        return ledger.apply(payload, tenant, eventId, key);
    }
}
~~~

**Pros:** the full message and all header metadata are available. **Cons:** the business method becomes directly coupled to Spring Messaging; manual casts risk `ClassCastException` and bypass the `required` semantics `@Header` provides.

If a handler only needs two or three fields, annotated parameters provide a cleaner boundary. If a handler truly performs infrastructure work such as routing, fan-out, reply/error header handling, or selective header copying, accepting `Message` can make sense.

### 11.1. Do not use the same parameter for two roles

A domain-focused service can accept:

~~~java
PaymentReceipt apply(
        PaymentSubmitted payment,
        PaymentBusinessContext context);
~~~

The Service Activator acts as an **adapter** from Spring Message to the business service:

~~~text
Spring Message
   -> @Payload + @Header arguments
   -> PaymentBusinessContext
   -> Domain service
~~~

That way the domain service has no direct dependency on **@Header**, **MessageHeaders**, or **replyChannel**, while still receiving the identities needed to prevent tenant mix-ups and duplicates.

## 12. Header data types and parameter conversion

Spring Messaging method invocation can use argument resolvers and conversion mechanisms depending on version and configuration. However, **do not rely on arbitrary Java objects in headers automatically converting to any target parameter type**.

### 12.1. Example with an integer header

~~~java
void consume(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenant,
        @Header("workflowEpoch") Integer epoch) {
    if (epoch == null || epoch != payment.workflowEpoch()) {
        throw new IllegalArgumentException("EPOCH_MISMATCH");
    }
}
~~~

If the message is constructed internally, set **workflowEpoch** as an **Integer**:

~~~java
MessageBuilder.withPayload(payment)
        .setHeader("workflowEpoch", payment.workflowEpoch())
        .build();
~~~

If a broker header sends **"3"** as a String, some conversion setups may convert it to `Integer`, but do not treat that as a guaranteed default across all adapters and types. It is best to **parse and validate at ingress**, then set the properly typed internal header. For complex types like `UUID`, `Instant`, enums, or custom records, explicit conversion rules and tests are required.

### 12.2. Converting a string to a UUID

~~~java
// If a @Header parameter has type UUID, a suitable converter must exist:
@Header("requestUuid") java.util.UUID requestUuid
~~~

If the input is an invalid String, a conversion error may occur **before the method body runs**. To control error codes, ingress should parse the UUID, catch errors, and quarantine/reject per schema rather than letting arbitrary values reach the business method.

### 12.3. Do not use a header Map for unverified dynamic data

~~~java
@Headers Map<String, Object> headers
~~~

can contain:

- **String**: tenant, trace ID, source.
- **Number**: sequence number, retry count.
- **UUID/Long**: Spring message id, timestamp.
- **MessageChannel or channel name**: `replyChannel`, `errorChannel`.
- **Transport metadata**: broker tags, native headers, content type.

A **Map<String, Object>** aids inspection but weakens type safety if passed across the business layer. Extract only the required fields and build an immutable typed context for the business logic.

### 12.4. Missing, null, and default headers: choose clear semantics

| Field | What if missing? | Why |
| --- | --- | --- |
| `trustedTenantId` | Reject | Unknown tenant/permissions |
| `businessEventId` | Reject or quarantine | Cannot reliably deduplicate |
| `businessCorrelationKey` | Reject if flow requires grouping | Prevent false split/join |
| `traceId` | May continue with appropriate trace instrumentation | Observability, not business authority |
| `sourceSystem` | Per contract; can be optional for logging | Never assumed to grant producer authority |
| `workflowEpoch` | Reject if used to distinguish workflow versions | Avoid mixing old/new versions |
| `replyChannel` | May be absent in one-way flows | Runtime routing, not a domain header |
| `sequenceNumber` | May be absent if not from a Splitter | Do not assume sequencing exists |

Never “fix” a missing header by generating a random `eventId` inside the Service Activator if transaction idempotency depends on the original `eventId`.

## 13. Important Spring Integration headers

When processing messages in an integration flow, not every header is a business header. Spring Integration defines technical headers for correlation, sequencing, request/reply, and dispatching.

| Header | Typical meaning | Pass straight to domain service? |
| --- | --- | --- |
| **id** | Current Spring Message ID | Do not use in place of business `eventId` |
| **timestamp** | Framework timestamp attached to Message | Does not replace business event `occurredAt` |
| **correlationId** | Grouping key within a scope | Use only within the intended Aggregator/Splitter scope |
| **sequenceNumber** | Position of a child message in a sequence | Only when logic needs sequence order |
| **sequenceSize** | Expected count of messages in a sequence | Do not assume it equals business outcomes in all cases |
| **replyChannel** | Reply destination in Spring runtime | Keep in the integration layer |
| **errorChannel** | Error handling destination | Keep in the integration layer |
| **contentType** | Content type hint | Does not replace schema validation |
| **priority** | Priority metadata (when used) | Only if processing contract specifies it |
| **custom trustedTenantId** | Tenant verified by ingress | Pass via validated context |
| **custom businessEventId** | Logical event identity | Use for properly scoped idempotency |

Spring `MessageHeaders.ID`/`TIMESTAMP` and `IntegrationMessageHeaderAccessor` constants help prevent header-name typos in code. For example:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.handler.annotation.Header;

void inspect(
        @Header(MessageHeaders.ID) java.util.UUID springMessageId,
        @Header(
                value = IntegrationMessageHeaderAccessor.CORRELATION_ID,
                required = false) Object correlationId,
        @Header(
                value = IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                required = false) Integer sequenceNumber) {

    // springMessageId is for diagnostics.
    // correlationId and sequenceNumber only have meaning
    // within the topology that created them.
}
~~~

**Note:** sequence headers may be absent if the message did not pass through a Splitter or the source did not set a sequence. `correlationId` may also be absent in one-way flows that do not require grouping.

### 13.1. Business correlation vs. technical correlation

Suppose an order has multiple packages:

~~~text
Business correlation:
  shipping:tenant-a:SHIP-901:epoch-3

Splitter technical correlation:
  split-batch-44

Child 1: sequenceNumber = 1
Child 2: sequenceNumber = 2
Child 3: sequenceNumber = 3
~~~

A Service Activator processing each package might need both **businessCorrelationKey** (belonging to the shipment) and **sequenceNumber** (belonging to the child group). If you assign the exact same `correlationId` across every nested grouping level, the Aggregator may group incorrectly.

### 13.2. @Header does not perform correlation automatically

~~~java
@Header("businessCorrelationKey") String groupKey
~~~

only extracts the header value. For an Aggregator to actually group by that header, configure a **CorrelationStrategy** using `businessCorrelationKey`, or set **CORRELATION_ID** when the scope matches and the default strategy is used.

Similarly, a method accepting `sequenceNumber` does not cause messages to arrive in order automatically. A Resequencer/Aggregator must be configured separately.

### 13.3. Handling the special replyChannel header

In request/reply flows, a Gateway may attach a temporary `replyChannel` that is a **`MessageChannel` object**. Even though it can be accessed in the infrastructure layer, never put this object into `PaymentBusinessContext`, JSON DTOs, or a database. It is not a business ID and has no meaning outside the invocation runtime.

For pure business processing, let the Service Activator return `PaymentReceipt` and let the framework route the reply via `outputChannel`/`replyChannel`. Only specialized messaging handlers should manipulate reply channels directly, and they must verify security/routing semantics.

## 14. Headers across Transformers, Routers, and subflows

Suppose ingress attached `trustedTenantId`, `businessEventId`, and `businessCorrelationKey`. Before the Service Activator, a Transformer converts the payload:

~~~mermaid
flowchart LR
    A["Verified input Message"] --> R["Content-Based Router"]
    R --> T1["Transformer A"]
    R --> T2["Transformer B"]
    T1 --> S["Service Activator"]
    T2 --> S
    S --> O["Business reply / event"]
~~~

Normally, when a Transformer returns **a plain payload**, Spring Integration propagates input headers to the output per framework semantics. If a Transformer returns **a full `Message`**, header preservation depends on how the new `Message` is constructed. The two variants behave very differently:

### 14.1. Transform payload, keep headers via message handling

~~~java
return IntegrationFlow.from("rawPaymentEvents")
        .transform(RawPayment.class, parser::convertToPaymentSubmitted)
        .channel("verifiedPayments")
        .get();
~~~

This snippet **only illustrates topology**. If `rawPaymentEvents` contains unverified input, never route straight into `verifiedPayments` merely because parsing succeeded: an authorization/identity-binding step is needed beforehand.

### 14.2. Deliberately creating a new Message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<PaymentSubmitted> rebuildTrusted(
        Message<RawPayment> input,
        PaymentSubmitted parsed,
        VerifiedPaymentContext verified,
        PaymentAuthorization auth) {

    // Rebuild allowlisted headers after checking permissions.
    return new TrustedPaymentMessageFactory(auth)
            .create(parsed, verified);
}
~~~

This is a **trust boundary**: instead of copying hundreds of headers from HTTP/broker, construct internal metadata from a verified context. However, rebuilding like this may **not preserve a temporary `replyChannel`** from a request/reply Gateway. If the flow needs to reply to the caller, design propagation of `replyChannel`/sequence headers at an appropriate **trusted internal hop**.

### 14.3. Creating a Message from a previous Message

~~~java
Message<?> next = MessageBuilder.fromMessage(inputMessage)
        .setHeader("processingStage", "NORMALIZED")
        .build();
~~~

**fromMessage** helps preserve existing headers on an already-verified internal Message. Never use it on a **raw client-controlled message** and assume all headers are safe.

### 14.4. A header can disappear when leaving the JVM

If a subflow sends a Message to an HTTP/JMS/AMQP/TCP outbound adapter, which headers travel across the wire depends on `HeaderMapper`/`MessageConverter`/serializers. A **`String businessCorrelationKey`** header can be mapped per contract; a **`replyChannel`** object is not a portable payload.

If a business workflow must survive restarts or late callbacks, put required identities into a **versioned wire envelope** and re-verify upon receipt instead of relying on temporary framework headers.

## 15. Request/reply Gateways and parameter mapping

A **@MessagingGateway** can accept a Java call and build a Spring Message. The Gateway typically manages the reply path for the invocation, while the Service Activator uses `@Payload`/`@Header` to read the data.

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway
interface PaymentGateway {
    @Gateway(requestChannel = "verifiedPayments")
    PaymentReceipt submit(
            @Payload PaymentSubmitted payment,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

**Safety requirement:** the application service must verify tenant/payment/epoch and compute `groupKey` **before calling the gateway**. This interface does not check permissions itself; it only turns arguments into Message headers/payload.

### 15.1. Gateway and Service Activator can both use @Header

~~~text
Caller:
  gateway.submit(payment, "tenant-a", "evt-1042", "payment:v1:...")

Gateway:
  Message.payload = payment
  Message.headers.trustedTenantId = tenant-a
  Message.headers.businessEventId = evt-1042
  Message.headers.businessCorrelationKey = payment:v1:...

Service Activator:
  @Payload -> payment
  @Header("trustedTenantId") -> tenant-a
  @Header("businessEventId") -> evt-1042
  @Header("businessCorrelationKey") -> payment:v1:...
~~~

However, the **PaymentHeaderFlowConfig** example in section 9 sets a **fixed `outputChannel`** named `paymentReceipts`. If you want a synchronous Gateway to receive replies, you need **dedicated request/reply wiring**: do not assume the Gateway automatically pulls Messages from a separate `QueueChannel` without a bridge or reply route. One option is to let the Service Activator reply to the Gateway's `replyChannel` in a dedicated request/reply flow rather than forcing all outputs onto a separate output queue.

### 15.2. Temporary replyChannel and businessCorrelationKey have different jobs

~~~text
Logical payment workflow:
  businessCorrelationKey = payment:v1:tenant-a:PAY-1042:3

Gateway invocation 1:
  replyChannel = temporaryChannelA

Gateway invocation 2 (retry):
  replyChannel = temporaryChannelB

Business workflow still shares the same key.
~~~

Do not use `replyChannel` as an idempotency key; do not use `businessCorrelationKey` as an arbitrary dynamic channel name. One serves **long-lived business correlation**, while the other serves **the reply path for a single short-lived invocation**.

### 15.3. Void Gateways and handlers without replies

If a Gateway method only sends a command and returns `void`, the caller does not receive a `PaymentReceipt` from the method. When a Service Activator is configured strictly for a one-way side effect, do not fabricate a fake reply under a new `eventId`. For requests whose outcomes arrive from a provider minutes later, choose **accepted + persisted workflow + async callback** instead of holding the Gateway caller open indefinitely.

## 16. Header mapping at inbound adapters

**Header mapping** has two layers that are easily confused:

1. **Adapter mapping:** HTTP/JMS/AMQP/TCP header/property → Spring Message headers.
2. **Method parameter mapping:** Spring Message header → Java argument via `@Header`.

Getting layer 2 right does not prove layer 1 is right. For example:

~~~text
HTTP X-Event-Id = evt-1042
      |
      v
HTTP HeaderMapper / inbound controller
      |
      v
Spring header businessEventId = evt-1042
      |
      v
@Header("businessEventId") String eventId
~~~

If the mapper fails to copy the header or maps it under the wrong name, `@Header("businessEventId")` cannot magically pull that field from HTTP.

### 16.1. Comparing adapters

| Adapter / transport | Headers to watch | Risk |
| --- | --- | --- |
| **HTTP inbound** | HTTP headers, request path, auth principal | Client self-asserts tenant/role/correlation |
| **JMS inbound** | JMS headers/properties, `messageId`, `correlationId`, `replyTo` | Broker properties do not equal application business identity |
| **AMQP inbound** | Message properties, routing key, headers | Publisher may supply custom properties depending on permissions |
| **TCP inbound** | Connection metadata, framing, serialized fields | Payloads may not carry Spring headers |
| **File/SFTP inbound** | Path/name, content, batch metadata | File name is not by default a trusted correlation |

A **HeaderMapper** is a representation-conversion tool, not an authorization system. The sender's identity must be verified and bound to tenant/workflow before being used in a Service Activator.

### 16.2. Counterexample: client spoofing a tenant

~~~http
POST /api/payments/events HTTP/1.1
X-Tenant-Id: tenant-admin
X-Event-Id: evt-fake
Content-Type: application/json

{"paymentId":"PAY-999","amountMinor":1000,"currencyCode":"VND","workflowEpoch":1}
~~~

If the application blindly maps `X-Tenant-Id` to `trustedTenantId` without checking credentials, the Service Activator can process the wrong tenant even though every annotation is written correctly.

### 16.3. Allowlist policy for ingress

- Accept only HTTP/broker headers that actually belong to the contract.
- Constrain length, charset, and types of metadata.
- Never forward external **replyChannel**, **errorChannel**, or **routingSlip** directly.
- Build internal `trustedTenantId` and `businessCorrelationKey` from the principal/registry.
- Never use a client-supplied `traceId` as access permission or an idempotency key.
- If a partner sends its own external `correlationId`, retain it separately as **externalCorrelationRef** for reconciliation rather than using it as the business group key.
- Test missing, unsupported, duplicate, and multi-valued headers.

## 17. Unit tests: verifying the method reads passed parameters properly

Unit-testing a Java method directly verifies **validation logic once arguments already have values**. Because the test invokes the method as plain Java, it **does not verify the framework's argument resolver**; that is covered by integration tests.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PaymentHeaderServiceActivatorUnitTest {

    private InMemoryPaymentLedger ledger;
    private PaymentHeaderServiceActivator handler;

    @BeforeEach
    void prepare() {
        ledger = new InMemoryPaymentLedger();
        handler = new PaymentHeaderServiceActivator(ledger);
    }

    private PaymentSubmitted samplePayment() {
        return new PaymentSubmitted(
                "PAY-1042", 125000, "VND", 3);
    }

    private String key(PaymentSubmitted payment) {
        return PaymentCorrelation.key("tenant-a", payment);
    }

    @Test
    void handlesTrustedMetadataAndReturnsReceipt() {
        PaymentSubmitted payment = samplePayment();

        PaymentReceipt receipt = handler.accept(
                payment,
                "tenant-a",
                "evt-payment-1042",
                key(payment),
                "BILLING",
                Map.of(
                        "trustedTenantId", "tenant-a",
                        "businessEventId", "evt-payment-1042"));

        assertEquals("RECORDED", receipt.decision());
        assertEquals("PAY-1042", receipt.paymentId());
        assertEquals("tenant-a", receipt.tenantId());
        assertEquals(
                "evt-payment-1042", receipt.eventId());
        assertEquals(key(payment),
                receipt.businessCorrelationKey());
        assertEquals(1, ledger.uniqueEventCount());
    }

    @Test
    void rejectsCorrelationFromDifferentWorkflow() {
        PaymentSubmitted payment = samplePayment();

        assertThrows(SecurityException.class, () ->
                handler.accept(
                        payment,
                        "tenant-a",
                        "evt-payment-1042",
                        "payment:v1:tenant-b:PAY-1042:3",
                        "BILLING",
                        Map.of("trustedTenantId", "tenant-a")));

        assertEquals(0, ledger.uniqueEventCount());
    }

    @Test
    void missingOptionalSourceCanBeHandled() {
        PaymentSubmitted payment = samplePayment();

        PaymentReceipt receipt = handler.accept(
                payment,
                "tenant-a",
                "evt-no-source",
                key(payment),
                null,
                Map.of("trustedTenantId", "tenant-a"));

        assertEquals("RECORDED", receipt.decision());
    }

    @Test
    void headerMapConflictIsRejectedBeforeLedgerCall() {
        PaymentSubmitted payment = samplePayment();

        assertThrows(SecurityException.class, () ->
                handler.accept(
                        payment, "tenant-a", "evt-conflict",
                        key(payment), "BILLING",
                        Map.of("trustedTenantId", "tenant-b")));

        assertEquals(0, ledger.uniqueEventCount());
    }

    @Test
    void duplicateLogicalEventDoesNotCreateSecondRecord() {
        PaymentSubmitted payment = samplePayment();
        Map<String, Object> headers =
                Map.of("trustedTenantId", "tenant-a");

        PaymentReceipt first = handler.accept(
                payment, "tenant-a", "evt-repeat",
                key(payment), "BILLING", headers);
        PaymentReceipt replay = handler.accept(
                payment, "tenant-a", "evt-repeat",
                key(payment), "BILLING", headers);

        assertEquals(first, replay);
        assertEquals(1, ledger.uniqueEventCount());
    }
}
~~~

These unit tests verify handler logic and the fake ledger; **they do not have Spring invoke `@Header`**. A test calling `handler.accept(...)` directly cannot prove the framework maps header names properly or handles required/optional arguments.

## 18. Integration test: Spring performs @Header argument mapping

Build a context from **PaymentHeaderFlowConfig**, send a Message to **verifiedPayments**, then read **PaymentReceipt** from **paymentReceipts**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentHeaderFlowConfig.class)
class PaymentHeaderMappingIntegrationTest {

    @Autowired
    @Qualifier("verifiedPayments")
    MessageChannel input;

    @Autowired
    @Qualifier("paymentReceipts")
    QueueChannel output;

    @Autowired
    InMemoryPaymentLedger ledger;

    // Test-only authorization stub: DO NOT deploy to production.
    private final PaymentAuthorization stubAuthorization =
            (context, payment) -> {
                if (!Set.of("tenant-a", "tenant-b")
                        .contains(context.tenantId())) {
                    throw new SecurityException("TENANT_NOT_ALLOWED");
                }
            };

    private TrustedPaymentMessageFactory factory() {
        return new TrustedPaymentMessageFactory(stubAuthorization);
    }

    private PaymentSubmitted sample(
            String id, int epoch) {
        return new PaymentSubmitted(id, 125000, "VND", epoch);
    }

    @BeforeEach
    void drainOutput() {
        while (output.receive(0) != null) {
            // Prevent replies from earlier tests from polluting subsequent tests.
        }
    }

    private PaymentReceipt nextReceipt() {
        Message<?> reply = output.receive(0);
        assertNotNull(reply);
        assertInstanceOf(PaymentReceipt.class, reply.getPayload());
        return (PaymentReceipt) reply.getPayload();
    }

    @Test
    void frameworkMapsRequiredAndOptionalHeaders() {
        PaymentSubmitted payment = sample("PAY-1101", 3);
        VerifiedPaymentContext context =
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1101", "BILLING");

        Message<PaymentSubmitted> message =
                factory().create(payment, context);
        assertTrue(input.send(message));

        PaymentReceipt reply = nextReceipt();
        assertEquals("PAY-1101", reply.paymentId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("evt-1101", reply.eventId());
        assertEquals(
                "payment:v1:tenant-a:PAY-1101:3",
                reply.businessCorrelationKey());
        assertEquals("RECORDED", reply.decision());
        assertNull(output.receive(0));
    }

    @Test
    void twoTenantsWithSamePaymentIdGetDifferentKeys() {
        PaymentSubmitted payment = sample("PAY-1102", 4);

        assertTrue(input.send(factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1102a", "BILLING"))));
        assertTrue(input.send(factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-b", "evt-1102b", "BILLING"))));

        PaymentReceipt first = nextReceipt();
        PaymentReceipt second = nextReceipt();

        assertEquals("tenant-a", first.tenantId());
        assertEquals("tenant-b", second.tenantId());
        assertNotEquals(
                first.businessCorrelationKey(),
                second.businessCorrelationKey());
    }

    @Test
    void duplicateMessageReturnsSameBusinessReceipt() {
        PaymentSubmitted payment = sample("PAY-1103", 1);
        Message<PaymentSubmitted> message = factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1103", "BILLING"));

        assertTrue(input.send(message));
        assertTrue(input.send(message));

        PaymentReceipt first = nextReceipt();
        PaymentReceipt replay = nextReceipt();

        assertEquals(first, replay);
        // The total event count in the ledger may include other tests,
        // so do not assert == 1 on the suite-wide singleton.
    }

    @Test
    void missingOptionalHeaderDoesNotBlockValidPayment() {
        PaymentSubmitted payment = sample("PAY-1104", 2);
        Message<PaymentSubmitted> message = factory().create(
                payment,
                new VerifiedPaymentContext(
                        "tenant-a", "evt-1104", "BILLING"));

        // Without sourceSystem. Required headers remain intact.
        Message<PaymentSubmitted> withoutSource =
                org.springframework.messaging.support.MessageBuilder
                        .fromMessage(message)
                        .removeHeader("sourceSystem")
                        .build();

        assertTrue(input.send(withoutSource));
        assertEquals(
                "evt-1104", nextReceipt().eventId());
    }
}
~~~

**Significance of the integration test:** the Spring context actually registers the endpoint and method invocation must resolve **@Payload**, **@Header**, and **@Headers** itself. This is fundamentally different from unit tests calling the Java method directly.

### 18.1. outputChannel results and replies

The tests use `QueueChannel` because the example declared `outputChannel` explicitly. Do not confuse this with testing a Gateway `replyChannel`: synchronous Gateway flows require dedicated request/reply wiring and may not use this output queue.

### 18.2. Be careful with test state and framework context caching

Spring Test may cache `ApplicationContext` across tests. The fake `InMemoryPaymentLedger` is a singleton in the context, so events from prior tests can remain in the map. Tests use distinct `eventId`s to avoid order dependence and do not assert a context-wide record count of 1. If strict isolation is required, reset test fixtures cleanly or use `@DirtiesContext` as needed.

### 18.3. Timeout and infrastructure error tests are outside this example

`DirectChannel` + a fake ledger in the same JVM only prove **argument mapping** and the output path. They do not test database transactions, broker acknowledgments, redelivery after restarts, poller error channels, or Gateway results across the network.

## 19. Negative tests: missing headers or conflicting data

These tests are crucial because wrong headers can lead to **tenant mixing** or **wrong workflow attachment** without obvious errors.

### 19.1. Missing required header

~~~java
// Test snippet inside PaymentHeaderMappingIntegrationTest.
@Test
void missingTrustedTenantHeaderRejectsBeforeBusinessEffect() {
    PaymentSubmitted payment = sample("PAY-1201", 2);
    String groupKey = PaymentCorrelation.key("tenant-a", payment);

    Message<PaymentSubmitted> missingTenant =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(payment)
                    .setHeader("businessEventId", "evt-1201")
                    .setHeader("businessCorrelationKey", groupKey)
                    .build();

    // Exception may be a MessagingException wrapper depending on version.
    assertThrows(RuntimeException.class,
            () -> input.send(missingTenant));
    assertNull(output.receive(0));
}
~~~

With a **required `@Header`**, the framework must never substitute a default trusted tenant. Verify outcomes outside the flow to confirm rejection, and track error codes/exception chains in real deployments.

### 19.2. Spoofed businessCorrelationKey header

~~~java
// Test snippet inside PaymentHeaderMappingIntegrationTest.
@Test
void forgedCorrelationHeaderIsRejected() {
    PaymentSubmitted payment = sample("PAY-1202", 1);

    Message<PaymentSubmitted> forged =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(payment)
                    .setHeader("trustedTenantId", "tenant-a")
                    .setHeader("businessEventId", "evt-1202")
                    .setHeader(
                            "businessCorrelationKey",
                            "payment:v1:tenant-b:PAY-1202:1")
                    .build();

    assertThrows(RuntimeException.class,
            () -> input.send(forged));
    assertNull(output.receive(0));
}
~~~

The handler recomputes the expected `groupKey` from `tenantId` and the payload, so the mismatch is blocked. **However, this example still assumes `trustedTenantId` is genuinely trustworthy**: if an attacker is allowed to set both `tenantId` and `groupKey` to matching fake values, string comparison does not replace ingress authorization.

### 19.3. Same event ID but different payload

~~~java
// Test snippet inside PaymentHeaderMappingIntegrationTest.
@Test
void sameEventIdWithDifferentAmountIsAConflict() {
    VerifiedPaymentContext context =
            new VerifiedPaymentContext(
                    "tenant-a", "evt-1203", "BILLING");

    Message<PaymentSubmitted> first = factory().create(
            new PaymentSubmitted("PAY-1203", 1000, "VND", 1),
            context);
    Message<PaymentSubmitted> changed = factory().create(
            new PaymentSubmitted("PAY-1203", 2000, "VND", 1),
            context);

    assertTrue(input.send(first));
    assertNotNull(output.receive(0));

    assertThrows(RuntimeException.class,
            () -> input.send(changed));
    assertNull(output.receive(0));
}
~~~

If `eventId` is unique only per **tenant + producer**, a fake ledger keyed by `tenant+eventId` is insufficient for production. Adjust the key per contract and implement conflict detection on payload digests/operation identity.

### 19.4. Wrong header type or conversion failure

~~~java
// Example payload built with a header type violating the contract.
Message<PaymentSubmitted> wrongHeaderType =
        org.springframework.messaging.support.MessageBuilder
                .withPayload(sample("PAY-1204", 1))
                .setHeader("trustedTenantId", java.util.List.of("tenant-a"))
                .setHeader("businessEventId", "evt-1204")
                .setHeader(
                        "businessCorrelationKey",
                        "payment:v1:tenant-a:PAY-1204:1")
                .build();
~~~

Do not depend on a single exception class for every header type error because conversion can vary across Spring versions and converters. In real systems, inspect the exception cause and ensure **no side effect occurs** when a required identity header has the wrong type.

### 19.5. Do not log all headers when assertions fail

A test might print `Message.toString()` for debugging, but in production headers can hold tokens, session identifiers, or framework channel references. Structured logs with **eventRef**, **reasonCode**, **component**, and **source** are safer than dumping the raw Message.

## 20. When should a handler read one header, many headers, or the full Message?

Three signature styles have different pros and cons:

~~~java
// A: Minimal, declaring exact dependencies.
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId) {
    // ...
}

// B: Need a metadata map for monitoring/diagnostics.
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Headers Map<String, Object> headers) {
    // ...
}

// C: Need to manipulate the Message in the integration layer.
public PaymentReceipt accept(
        org.springframework.messaging.Message<PaymentSubmitted> message) {
    // ...
}
~~~

**These are alternative signatures**, not three overloaded methods to register together on one Service Activator. Never copy/paste methods with the same name and conflicting parameter patterns in a real class.

| Scenario | Preferred option | Why |
| --- | --- | --- |
| Business service needs tenant and `eventId` | `@Payload` + `@Header` | Explicit, low coupling |
| Adapter needs three or four metadata fields | Individual `@Header`s or typed context | Easy to test required/validation rules |
| Error/log decorator inspects dynamic headers | `@Headers Map` | Can selectively observe multiple fields |
| Endpoint builds a custom reply Message | `Message<?>` | Needs runtime context, though more complex |
| Small flow with brief logic | DSL `.handle(payload, headers)` | Avoids creating an annotated handler class |
| Processing in the domain layer | DTO + immutable `BusinessContext` | No Spring Message dependency |

### 20.1. Annotated parameters do not replace domain validation

A method may receive a syntactically valid **`String tenantId`**, yet have no proof that the tenant is authorized for `paymentId`. Enforce binding at ingress:

~~~text
AuthenticatedPrincipal
    + paymentId / workflowEpoch
    + tenant registry / ACL
    -> VerifiedPaymentContext
    -> Spring Message headers
    -> @Header Java arguments
~~~

Never construct **`VerifiedPaymentContext`** from unauthenticated client data and treat it as a permission check.

### 20.2. When a handler needs a derived value

Suppose a handler needs **`businessCorrelationKey`** computed from `tenant+paymentId+epoch`. Two choices:

- Ingress verifies and precomputes the business key; the handler reads it via `@Header` and re-verifies it.
- The handler receives a typed `BusinessContext` and calls a trusted service to derive the key.

Do not let multiple handlers compute keys using different algorithms (for example, one adding a prefix or normalizing case arbitrarily), or the same event will receive different group keys. Versioned correlation algorithms and contracts must be used consistently.

## 21. Error handling: missing headers are not business rejections

In Java code, some errors happen **before the method is called**, others happen **inside the method**, and others surface **only after the service has performed a side effect**.

~~~mermaid
flowchart TD
    A["Incoming Message"] --> M{"Argument mapping"}
    M -->|"Missing / invalid header"| E1["Mapping error"]
    M -->|"PASS"| B{"Business handler"}
    B -->|"Security / validation fail"| E2["Business rejection"]
    B -->|"Transient IO failure"| E3["Retry / recovery"]
    B -->|"Effect committed"| R{"Reply delivery"}
    R -->|"Reply arrived"| O["Receipt"]
    R -->|"Timeout / lost ack"| U["Unknown to caller"]
~~~

### 21.1. Error paths on DirectChannel

In a synchronous `DirectChannel` flow:

- The argument resolver may throw due to a missing required header or conversion failure.
- The Service Activator may throw `SecurityException`/`IllegalArgumentException` when metadata and payload conflict.
- Spring Integration may wrap the exception in a `MessagingException` or `MessageHandlingException`.
- The caller or inbound adapter decides how to return errors/ACK/retry per contract.

Therefore tests can assert a general `RuntimeException` first, then inspect the **cause chain and error code** specific to your Spring Integration version during full integration. Never assume every error always surfaces with the exact same outer exception class.

### 21.2. Error paths on ExecutorChannel/poller

When a handler runs on an executor or poller, exceptions may be sent as an **ErrorMessage** to the appropriate error channel. `ErrorMessage` carries a `Throwable` payload and may include `failedMessage` in supported contexts; never assume the `ErrorMessage` payload itself is `PaymentSubmitted`.

To produce a failure outcome:

1. Recover event/tenant/workflow identity from a trustworthy source.
2. Classify schema, auth, business rejection, transient I/O, or unknown-effect errors.
3. Produce a terminal business outcome only when **business state is genuinely known**.
4. Preserve `eventId`/`operationId` across retries.
5. Audit/quarantine when trustworthy metadata is missing.

**`errorChannel` is not automatically a durable DLQ.** If persistence across restarts is needed, configure storage/broker persistence and recovery policies.

### 21.3. Mapping errors must not be retried infinitely like network errors

If a message lacks `trustedTenantId` due to a misconfigured adapter, retrying the same input thousands of times will never make the header appear. Classify errors:

| Error | Retry? | Handling |
| --- | --- | --- |
| Missing `trustedTenantId` | Never retry endlessly | Security reject, fix ingress |
| Correlation mismatch | Do not proceed with business effect | Quarantine/alert |
| Invalid `amountMinor` | Do not retry same payload | Source correction |
| Unsupported source schema | Do not retry endlessly | Update parser/contract |
| Database unavailable | Bounded retries allowed | Backoff + recovery |
| Reply delivery timeout after commit | Do not blindly run a new effect | Idempotent lookup/reconcile |
| Duplicate exact event | Do not create a new effect | Return stored receipt or skip |
| Same event ID, different payload | Do not treat as normal duplicate | `ID_CONFLICT` |

### 21.4. Never turn exceptions into fake success replies

Counterexample:

~~~java
try {
    return ledger.apply(payment, tenant, eventId, key);
} catch (Exception ex) {
    return new PaymentReceipt(
            tenant, payment.paymentId(), eventId, key,
            "RECORDED");
}
~~~

A DB error, missing permission, or timeout does not prove the payment was recorded. If an `UNKNOWN`/`PENDING` result is needed, use a dedicated domain state, reason, and reconciliation mechanism; never return **RECORDED** just to hide errors from callers.

## 22. Retry and idempotency when @Header arguments are re-read

When a message is redelivered, Spring Integration may create a **new Message** or reuse the old one depending on the adapter/recovery mechanism. **Technical IDs** and retry headers may change, but **businessEventId and businessCorrelationKey** for the same logical operation must stay stable.

~~~text
Attempt 1:
  Spring message ID: a1
  @Header("businessEventId"): evt-payment-1042
  @Header("businessCorrelationKey"): payment:v1:tenant-a:PAY-1042:3

Attempt 2:
  Spring message ID: b2
  @Header("businessEventId"): evt-payment-1042
  @Header("businessCorrelationKey"): payment:v1:tenant-a:PAY-1042:3
~~~

The handler can call the ledger using these exact two identities to prevent duplicates. If `eventId` is regenerated on every Service Activator invocation, the ledger has no way to recognize the same logical event.

### 22.1. Durable inbox schema instead of an in-memory Map

A PostgreSQL example:

~~~sql
CREATE TABLE payment_event_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    payment_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    business_key VARCHAR(220) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX payment_event_inbox_status_idx
    ON payment_event_inbox (processing_status);
~~~

Here `producer_id` is included in the identity because an `eventId` may only be unique per producer. Adjust to match the real contract. Same `eventId` with a different `payload_digest` must raise **ID_CONFLICT**, never overwrite silently.

### 22.2. Crash windows must be closed

~~~text
1. Write inbox status=SEEN
2. Commit
3. Crash before Service Activator executes side effect
4. Redelivery sees SEEN and drops the message
=> Side effect is permanently lost
~~~

You need **transactional inbox/outbox**, a state machine, or a recovery worker to distinguish `RECEIVED`, `DISPATCH_PENDING`, `EFFECT_COMMITTED`, and `FAILED` with enough data to recover. Never annotate a method with `@ServiceActivator` and assume the entire flow has atomic exactly-once semantics.

### 22.3. Retry advice can invoke the handler multiple times

If a handler is wrapped in retry advice, the business method can run again after an exception. **A higher `retryCount` header** does not turn the work into a new business operation. Keep the idempotency key stable, guard external API calls with provider idempotency keys/lookups, and test lost responses after effect commit.

### 22.4. Sequence headers are not idempotency keys

If a Splitter sets `sequenceNumber=1,2,3`, never use `sequenceNumber` alone for deduplication: every parent batch has a child #1. The right scope may be **tenant + parent event ID + child logical ID**, while `sequenceNumber` is merely the processing position.

## 23. Security: which header fields can grant permissions?

Short answer: **a `String` in `MessageHeaders` is not access permission by itself**. Data is trustworthy only after being created at a boundary with proper authentication/authorization.

### 23.1. HTTP spoofing scenario

~~~http
POST /api/payments/events HTTP/1.1
X-Tenant-Id: tenant-admin
X-Role: SUPERUSER
X-Correlation-Id: payment:v1:tenant-admin:PAY-999:1
Content-Type: application/json

{"paymentId":"PAY-999","amountMinor":1000,"currencyCode":"VND","workflowEpoch":1}
~~~

Wrong code:

~~~java
// Do NOT do this:
String tenant = request.getHeader("X-Tenant-Id");
Message<?> internal = MessageBuilder
        .withPayload(parsedPayment)
        .setHeader("trustedTenantId", tenant)
        .build();
~~~

Proper **order of responsibility**:

~~~text
HTTP request + security principal
    -> verify signature/session
    -> authorize principal against payment/tenant/workflow
    -> verified tenant from registry / principal binding
    -> TrustedPaymentMessageFactory
    -> @ServiceActivator @Header("trustedTenantId")
~~~

If an external party sends a custom correlation header for tracing, store it separately as **externalCorrelationRef** after validating length/charset, and never let it replace `businessCorrelationKey` or tenant permissions.

### 23.2. Header injection into control channels

Spring Integration has special headers affecting reply/error routing. If clients can arbitrarily supply `replyChannel`, `errorChannel`, or `routingSlip`, they can steer internal flows to unintended destinations.

Do not do this:

~~~java
// Anti-pattern:
MessageBuilder.withPayload(payment)
        .copyHeaders(allHeadersFromHttpRequest)
        .build();
~~~

Map only **allowlisted business fields**, and reconstruct framework control headers inside trusted internal flows when genuinely needed.

### 23.3. Data minimization

Do not let a Service Activator receive all headers containing Authorization tokens, cookies, broker secrets, or PII and forward them all to domain services/logs. Pass only required business data: verified tenant, event ID, business correlation, and typed payload.

### 23.4. Test the security boundary separately

The integration tests in section 18 create `VerifiedPaymentContext` with a stub. They **do not prove** JWT/mTLS/broker ACLs are configured properly. Production needs controller/adapter tests with real credentials, cross-tenant access attempts, expired tokens, invalid signatures, replays, and forged headers.

## 24. Observability: finding which hop dropped a header

A common failure is downstream reporting “Missing trustedTenantId” even though ingress confirmed the payment was accepted. The culprit may be a `HeaderMapper`, a Transformer building a new Message, a Router dropping expected metadata, or a callback arriving from a different flow.

### 24.1. Recommended metrics

| Metric | Meaning | Controlled labels |
| --- | --- | --- |
| **service_activator_input_total** | Messages arriving at endpoint | `endpoint`, `sourceType` |
| **service_activator_success_total** | Successful handler calls | `endpoint`, `decision` |
| **service_activator_error_total** | Business/mapping errors | `endpoint`, `reasonCode` |
| **service_activator_duration_seconds** | Handler latency | `endpoint` |
| **service_activator_missing_header_total** | Missing required header | `headerName` from allowlist |
| **service_activator_invalid_header_total** | Wrong type, value, or scope | `headerName`, `reason` |
| **service_activator_correlation_mismatch_total** | Wrong `businessKey` | `endpoint` |
| **service_activator_duplicate_event_total** | Dedup/redelivery | `producerType` |
| **service_activator_identity_conflict_total** | Same `eventId`, different payload | `sourceType` |
| **service_activator_reply_failure_total** | Reply send failures | `endpoint` |
| **service_activator_retry_total** | Retry attempts | bounded `errorClass` |
| **service_activator_inbox_pending** | Uncommitted events | `status` |

Metric labels should not include high-cardinality fields like `tenantId`, `paymentId`, `eventId`, `correlationKey`, or `traceId`. Use structured logs/tracing with proper retention and access controls to trace a single logical event.

### 24.2. Sample log on successful mapping

~~~json
{
  "component": "paymentServiceActivator",
  "stage": "HANDLE",
  "eventRef": "evt-payment-1042",
  "source": "BILLING",
  "headerContractVersion": 1,
  "businessCorrelationRef": "redacted-group-reference",
  "result": "RECORDED"
}
~~~

### 24.3. Sample log on invalid header

~~~json
{
  "component": "paymentServiceActivator",
  "stage": "ARGUMENT_BINDING",
  "headerName": "trustedTenantId",
  "reasonCode": "MISSING_REQUIRED_HEADER",
  "result": "REJECTED"
}
~~~

These are **illustrative application logs**, not formats automatically emitted by Spring Integration. When the framework fails to resolve an argument, the method body never runs; to emit metrics/logs at the argument-binding step, place instrumentation in the error handler or endpoint wrapper rather than only inside the handler body.

### 24.4. Tracing and security context

Trace/span IDs can be propagated by instrumentation. They help track execution from adapter through Service Activator, but they do not replace `eventId`, grant tenant permissions, or prove a business operation committed.

With `ExecutorChannel`, a **`ThreadLocal`** holding the previous HTTP request's tenant may be empty on the worker thread. Business identity must come from the verified Message/context, never from a leftover `ThreadLocal`.

## 25. Runbook: @Header receives null or fails to bind a value

**Scenario:** a method has `@Header("businessEventId") String eventId`, but integration tests or production fail before calling the handler.

### Step 1 — Verify the message actually enters the right endpoint

Check the inbound channel, Router mapping, and Service Activator bean. Two endpoints on the same `DirectChannel` can alternate which consumer receives messages; if the method never runs, do not immediately blame `@Header`.

### Step 2 — Check the payload type and bean method

Is the payload really `PaymentSubmitted`? Did a Transformer change it to a `Map`, `String`, or envelope? Is `@EnableIntegration` active and is the bean properly scanned/registered?

### Step 3 — Check the exact header name

~~~text
Expected Spring header:
  businessEventId

Actual Spring headers:
  BusinessEventID
  X-Business-Event-Id
  event_id
~~~

Those are **different names**. The `HeaderMapper` or ingress factory must produce **`businessEventId`** per contract; do not change `@Header` every time a partner renames an HTTP header.

### Step 4 — Check header presence and type

A header may be present with the wrong type:

~~~text
expected: trustedTenantId -> String
actual:   trustedTenantId -> List<String>
~~~

If no converter handles it, method argument binding can fail. Use logs/tests to check types and normalize at ingress; never cast blindly and treat identity as verified.

### Step 5 — Check the required/optional contract

If `businessEventId` is mandatory, leave the default `required=true` and reject when missing. If supplementary `traceId` may be absent, use `required=false` and handle null cleanly. Never mark every header optional just to “stop errors” and sacrifice business guarantees.

### Step 6 — Check upstream Transformers/subflows

A Transformer returning a plain payload usually gets framework header propagation; a handler creating a brand-new `Message` may drop required headers. Inspect message-building code, `HeaderEnricher`/`HeaderFilter`, and intermediate endpoints.

### Step 7 — Check adapter mapping

Over HTTP/JMS/AMQP/TCP, `MessageConverter` and `HeaderMapper` govern what crosses the wire. If the sender puts a header on a Java Message while the receiver only gets a JSON payload, design a wire envelope or selective header mapping.

### Step 8 — Check error channel and exception chain

If the failure occurs before the method body runs, logs inside the Service Activator will not execute. Inspect the cause chain and `errorChannel`/poller/adapter error handling. Never auto-retry a missing tenant as if it were a transient network glitch.

### Step 9 — Check business correlation scope

If Spring `correlationId` differs from `businessCorrelationKey`, that may be **correct** across nested Splitter groups. Compare technical and business scopes; do not overwrite the global technical `correlationId` just to make them look identical.

### Step 10 — Verify after fixing

Send a valid event and assert:

~~~text
@Payload.paymentId            == PAY-1042
@Header.trustedTenantId       == tenant-a
@Header.businessEventId       == evt-payment-1042
@Header.businessCorrelationKey== payment:v1:tenant-a:PAY-1042:3
PaymentReceipt                == RECORDED
~~~

Next, test messages with missing headers, wrong tenants, duplicate `eventId`s, and inputs from real adapters to ensure **no improper side effects occur**.

## 26. Anti-patterns when mapping headers to parameters

| Anti-pattern | Why it is dangerous | Replacement |
| --- | --- | --- |
| Guessing header names from Java variable names | Refactoring makes binding ambiguous | Use `@Header` with explicit names |
| Treating HTTP `X-Tenant-Id` as `trustedTenantId` | Clients can spoof it | Auth + registry binding |
| Setting `required=false` on every header | Missing identity is hidden | Require per contract |
| Defaulting `eventId` to a new UUID | Redelivery bypasses deduplication | Stable logical `eventId` |
| `copyHeaders` all external headers | Can inject unsafe `replyChannel`/`errorChannel` | Allowlist + verified context |
| Arbitrary Number/String mapping | Runtime conversion failures | Parse/validate at ingress |
| Using `MessageHeaders.ID` as business ID | Rebuilt messages get new IDs | Dedicated `businessEventId` header |
| Using `replyChannel` as correlation key | Each invocation has its own channel | Durable business correlation |
| Passing raw Header Map into domain | Infrastructure coupling / secret leakage | Immutable `BusinessContext` |
| Using `group.size()` to infer complete outcomes | Duplicates skew counts | Unique members + release strategy |
| Two Service Activators on same `DirectChannel` | Subscribers compete for messages | Single clear owner or deliberate pub-sub |
| Attaching headers after side effects | Validation happens too late | Verify before dispatch |
| Mutating `MessageHeaders` directly | Violates immutability, hard to trace | `MessageBuilder` or `HeaderEnricher` |
| Using `ThreadLocal` tenant in async handlers | Worker thread loses context | Verified header/context |
| Swallowing exceptions and returning `RECORDED` | Hides errors and creates false success | Typed error + recovery |
| Treating `@Header` as authorization | Annotation only reads values | Security boundary before handler |
| Skipping error-path tests | Missing/malformed headers fail only in prod | Negative + contract tests |
| Infinite retries on full flow | Side effects can repeat | Bounded retry + ledger/reconcile |
| One-way handler behind reply-waiting Gateway | Reply timeout | Explicit request/reply contract |

## 27. Practice lab: mapping headers from three sources into one Service Activator

Design a flow recording **OrderPaymentEvent** from HTTP, JMS, and an internal job:

~~~mermaid
flowchart LR
    A["HTTP adapter"] --> V["Ingress verify"]
    B["JMS adapter"] --> V
    C["Internal scheduler"] --> V
    V --> M["MessageBuilder trusted headers"]
    M --> S["@ServiceActivator"]
    S --> D["Domain service / inbox"]
    D --> R["Receipt / status"]
~~~

### 27.1. Input contract

Payload:

~~~java
record OrderPaymentEvent(
        String orderId,
        String paymentReference,
        long amountMinor,
        String currencyCode,
        int workflowEpoch) {
}
~~~

Trusted Spring headers:

~~~text
trustedTenantId         -> String, required
businessEventId         -> String, required
businessCorrelationKey  -> String, required
sourceSystem            -> String, optional for logging
traceId                 -> String, optional for tracing
workflowEpoch           -> Integer, required if not read from payload
~~~

If `workflowEpoch` is stored in both the payload and a header, the Service Activator must **check consistency** rather than picking one arbitrarily. If a registry serves as the single source of truth, it is cleaner to compute the business key at ingress and avoid redundant duplicate metadata.

### 27.2. Implementation steps

1. Create the payload DTO and validate currency, amount, and order/payment identity.
2. Define verified identity/context from principal, certificate, or broker ACL.
3. Verify tenant permissions for `orderId`/`paymentReference` and `workflowEpoch`.
4. Use **MessageBuilder** to attach trusted headers with exact names/types.
5. Write `@ServiceActivator` receiving `@Payload` and the three required `@Header`s.
6. Add an optional `@Header` for `traceId` or `sourceSystem`.
7. If many metadata fields are genuinely needed, try `@Headers Map` and refactor into a typed context.
8. Write a DSL `.handle(payload,headers)` variant for comparison—**never register both endpoints on the same `DirectChannel` simultaneously**.
9. Add an error path for missing/invalid headers and authorization mismatches.
10. Configure `outputChannel` or Gateway reply path per request/reply contract.
11. Build an idempotent fake ledger for unit tests and a durable store for production-stage integration.
12. Test an event redelivered with the same `businessEventId`.
13. Test the same `eventId` with a different payload digest: must report `ID_CONFLICT`.
14. Test two tenants with the same `orderId`: `businessCorrelationKey` must differ.
15. Test absent `replyChannel` in a one-way flow; handler must never use it as a business key.
16. Add tracing/logging and mapping-error metrics without logging tokens or sensitive raw payloads.

### 27.3. Testing matrix

| Case | Condition | Expected |
| --- | --- | --- |
| A | All required headers present | Handler receives each argument properly |
| B | `sourceSystem` missing | Still runs if contract marks it optional |
| C | `trustedTenantId` missing | Rejected before business side effects |
| D | `trustedTenantId` wrong type | Rejected/converted per tested contract |
| E | `businessCorrelationKey` wrong tenant | Rejected, nothing written to ledger |
| F | `businessEventId` missing | Rejected/quarantined, no UUID generated on retry |
| G | Same `eventId` and same payload | Idempotent replay |
| H | Same `eventId` but changed payload | `ID_CONFLICT` |
| I | Two tenants with same `paymentId` | Two independent business groups |
| J | Forged HTTP header `tenant-admin` | Security ingress rejects |
| K | JMS message loses custom header | Adapter mapping error, no false success |
| L | Transformer creates new Message dropping headers | Caught by contract test |
| M | Sync Gateway without reply path | Times out per contract; effect not assumed failed |
| N | `ExecutorChannel` switches threads | Identity does not depend on `ThreadLocal` |
| O | Splitter creates child messages | Sequence/correlation scoped accurately |
| P | Broker redelivery after commit | Side effect not executed a second time |

### 27.4. Passing criteria

Anyone reading the handler code should immediately see:

- Which data is the **business payload**.
- Which metadata comes from **@Header**.
- Which headers are **required** vs. **optional**.
- Who verifies tenant, event ID, and business key before the handler runs.
- Whether the handler produces a reply or a one-way side effect.
- How mapping errors are recorded and retried/quarantined.
- How redelivered events avoid duplicate side effects.

If a reader has to dig through every HTTP/JMS field inside the business method to figure out tenant or correlation, the mapping boundary is not clear enough.

## 28. Self-check questions

1. What role does a Service Activator play between a Spring Message and a Java business service?
2. Given a message with payload `PaymentSubmitted` and header `trustedTenantId`, which parameter uses `@Payload` and which uses `@Header`?
3. How does `@Header("businessEventId")` differ from `@Headers Map<String,Object>`?
4. If `@Header` has `required=true` and the message lacks that header, will the method body necessarily execute?
5. Is a header that exists as an empty string considered business-valid?
6. Why should you never default `tenantId="public"` to avoid missing-header errors?
7. Does HTTP header **X-Tenant-Id** automatically become **trustedTenantId** in a Spring Message?
8. Does `HeaderMapper` itself prove a tenant is authorized for a payment?
9. Why should you never copy all HTTP headers into `MessageBuilder`?
10. How can `@Header` handle a wire `String` needing to become a `UUID` or `Integer`, and what must be tested?
11. When should a handler accept `Message<?>` instead of multiple `@Header` parameters?
12. Why does passing `@Headers Map` couple the business layer more tightly to infrastructure?
13. Should Spring `MessageHeaders.ID` be used as the `eventId` for deduplication?
14. How does `businessCorrelationKey` differ from `replyChannel` and a Splitter's technical `correlationId`?
15. If a Service Activator returns `PaymentReceipt` with no output/reply route, will a Gateway caller receive the result?
16. What does a `void` Service Activator method mean for a request/reply flow?
17. Why can a Transformer returning a new `Message` lose headers?
18. When is `MessageBuilder.fromMessage` useful, and when is it risky?
19. Why must the same payload/`eventId` for different tenants live in separate idempotency namespaces?
20. Should reusing an `eventId` with a different payload return “already processed” or “conflict”?
21. Is a fake `ConcurrentHashMap` ledger sufficient to prevent duplicates across restarts and multiple instances?
22. Does an incremented `retryCount` header represent a new business event?
23. When a missing header fails before the handler runs, where should metrics/logs be placed?
24. Why should a permanent schema error not be retried the same way as a transient DB error?
25. When `ExecutorChannel` switches threads, should tenant be read from an HTTP request's `ThreadLocal`?
26. Does an `ErrorMessage` on `errorChannel` automatically carry `PaymentSubmitted` as its payload?
27. If a Gateway times out after a side effect committed, can you retry unconditionally?
28. How do you test the difference between a direct unit test and an integration test for `@Header` argument resolution?
29. Why should two Service Activators not compete on the same `DirectChannel` when only one handler is intended?
30. What bugs arise if `sequenceNumber` alone is used as an idempotency key?

## 29. Pre-deployment checklist for Service Activator mapping

- The **@ServiceActivator** method is registered on the right `inputChannel`.
- **@Payload**, **@Header**, or **@Headers** is chosen intentionally rather than relying on implicit parameter names.
- Business-significant headers use clear names consistent between producer and consumer.
- Required/optional contracts are explicitly defined per header.
- Missing required tenant, `eventId`, or business correlation is rejected before side effects.
- Header types and conversions are tested with real messages, not just direct Java calls.
- Ingress authenticates producer/tenant and business object/workflow epoch.
- Self-asserted headers like `X-Tenant-Id`, `X-Role`, and `X-Correlation-Id` are never trusted directly.
- `MessageBuilder` at the trust boundary uses a header allowlist and never copies live control headers from external input.
- `businessCorrelationKey` is namespaced by tenant/entity/workflow instance using a versioned algorithm.
- `eventId` is a logical identity stable across retries; `MessageHeaders.ID` is never used.
- Custom headers map properly across HTTP/JMS/AMQP/TCP adapters or versioned envelopes.
- When Transformers create new Messages, preservation of required trusted/runtime headers is verified.
- `correlationId`, `sequenceNumber`, and `sequenceSize` are used strictly within Splitter/Aggregator scope.
- `replyChannel`/`errorChannel` are runtime control metadata and never placed in domain contexts or non-portable wire DTOs.
- Handlers executing business effects use appropriate transactions and idempotency/ledgers.
- Duplicate events and `eventId` conflicts have clear policies.
- Recovery handles crashes between inbox insert, dispatch, and effect commit.
- Error handling distinguishes mapping, auth, schema, transient I/O, and unknown external effects.
- `DirectChannel`/async/poller/broker ACK semantics are tested against the actual topology.
- Request/reply Gateways have output/reply paths and bounded timeouts; one-way methods are not treated as sync results.
- Tracing/metrics read needed metadata without logging tokens, secrets, or sensitive raw payloads.
- Queue channels, executors, retries, and quarantine have limits and retention policies.
- Unit tests prove business logic handles passed arguments properly.
- Spring integration tests prove the framework actually binds `@Header`, `@Headers`, and `@Payload`.
- Negative tests cover missing headers, wrong types, correlation mismatches, tenant spoofing, duplicates, and `ID_CONFLICT`.
- Adapter contract tests cover header names/casing/conversion, multi-value headers, and schema upgrades.
- A runbook exists tracing inbound adapter → `MessageBuilder` → Transformer/Router → Service Activator → Ledger/reply.

## 30. Summary

**Mapping headers to parameters** lets a Service Activator receive the exact **payload** and **metadata** a Java method needs without manually unpacking the entire Spring Message:

~~~java
@ServiceActivator(inputChannel = "verifiedPayments")
public PaymentReceipt accept(
        @Payload PaymentSubmitted payment,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey) {
    // Validate identity and process business logic with idempotency.
}
~~~

**@Payload** binds the message content to a typed DTO. **@Header** binds a named metadata field with required/optional semantics. **@Headers** provides the full header map when an endpoint genuinely needs it. Java DSL **.handle(payload, headers)** and handlers accepting **Message<?>** are alternatives when flow structure calls for them.

More important than annotation syntax is **metadata ownership**:

~~~text
External HTTP/JMS/AMQP message
    -> parse + authenticate + authorize
    -> build trusted Spring Message headers
    -> Router / Transformer / subflows
    -> @ServiceActivator argument mapping
    -> typed business context + idempotent operation
    -> reply / error / persistent state
~~~

If tenant, `eventId`, or correlation has not been verified at ingress, annotations cannot turn them into trustworthy data. If a Transformer, adapter, or Gateway drops headers against contract, the method can miss arguments even though business code did not change. Therefore, **testing both the method and Spring runtime mapping**, alongside error paths, retries, and trust boundaries, is essential for using Service Activators safely in a multi-branch Spring Integration system.

## References

- [Enterprise Integration Patterns — Service Activator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html): connecting business logic to a messaging system through a service activation endpoint.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): POJO method invocation, input/output channels, request/reply, and endpoint configuration.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): `@ServiceActivator` and endpoint annotations.
- [Spring Framework API — @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html): binding a Message header to a Java method parameter, required/default semantics.
- [Spring Framework API — @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html): binding a collection of Message headers to a method.
- [Spring Framework API — @Payload](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): binding payload to a method parameter.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): `Message`, `MessageHeaders`, and immutable message semantics.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, handler lambdas, channels, and composition.
- [Spring Integration Reference — Messaging Gateway](https://docs.spring.io/spring-integration/reference/gateway.html): Gateway request/reply, temporary reply channels, and timeouts.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `QueueChannel`, `ExecutorChannel`, and dispatch semantics.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): routing by message content and header values.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): payload transformation and header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequence/correlation metadata of child messages.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): grouping and release strategies.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, and synchronous/asynchronous errors.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): duplicate detection and limitations to keep in mind when protecting side effects.
