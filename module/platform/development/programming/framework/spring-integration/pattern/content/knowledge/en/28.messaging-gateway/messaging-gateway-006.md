# Gateway Header Mapping from Method Arguments

## 1. The Problem: Calling a Java Method While Sending a Context-Rich Message

In the **SPRING_INTEGRATION_PATTERN** module, we learn to implement Enterprise Integration Patterns with **Spring Integration** to build loosely coupled, extensible message flows. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation can work together in one flow, while the business calling layer usually wants a clean Java API:

~~~java
QuoteReceipt result = quoteGateway.preview(
        command,
        "tenant-a",
        "evt-quote-901",
        "quote:v1:tenant-a:SHIP-901:7");
~~~

Meanwhile, a downstream Service Activator, Router, or Aggregator needs more information than just the request payload:

~~~text
Spring Message
├── payload = QuoteCommand(
│       shipmentId="SHIP-901",
│       serviceLevel=EXPRESS,
│       parcelCount=2,
│       workflowEpoch=7)
└── headers:
    trustedTenantId       = "tenant-a"
    businessEventId       = "evt-quote-901"
    businessCorrelationKey= "quote:v1:tenant-a:SHIP-901:7"
    gatewaySource         = "JAVA_APP"
    operationKind         = "PREVIEW"
    id                    = <Spring Message ID>
    replyChannel          = <runtime reply destination>
~~~

**Messaging Gateway** converts a Java method call into a Message, sends it into an `IntegrationFlow`, and—if the method returns a value—converts the reply into a Java return value. This lesson's topic is **mapping method arguments to Message headers**: which Java parameter becomes the payload, which parameters become headers, and how static or computed headers are attached.

~~~mermaid
flowchart LR
    A["Java caller"] --> G["Messaging Gateway proxy"]
    G --> P["Mapping method arguments"]
    P --> M["Spring Message: payload + headers"]
    M --> C["Request channel"]
    C --> H["Router / Service Activator"]
    H --> R["Reply"]
    R --> G
    G --> O["Java return value"]
~~~

### Learning Objectives

After this lesson, you will be able to:

1. Explain why a Gateway is the boundary between a **Java API** and a **message-based flow**.
2. Use **@Payload** to select the payload and **@Header** to map an argument to a header.
3. Use **@Headers** for a `Map` carrying multiple headers when needed.
4. Distinguish static/SpEL **@GatewayHeader** from per-invocation **@Header** argument mapping.
5. Understand default conventions and **ambiguous `Map` / multi-argument** cases.
6. Design request/reply Gateways with clear header contracts, bounded timeouts, and without confusing business correlation with temporary `replyChannel`.
7. Inspect headers in a Service Activator, Java DSL, and downstream subflows.
8. Write unit/integration tests, negative tests, and verify trust boundaries, retries, error handling, and idempotency.

## 2. Messaging Gateway in Enterprise Integration Patterns

Enterprise Integration Patterns defines **Messaging Gateway** as a way to hide messaging details behind an application-friendly interface. Calling code does not have to manually build Messages, choose channels, or wait for replies.

~~~text
Business application
    |
    | Java method
    v
Gateway interface/proxy
    |
    | Spring Message
    v
IntegrationFlow
    |
    +-- Filter / Router / Transformer
    |
    +-- Service Activator / outbound adapter
    |
    +-- reply or error
~~~

Spring Integration provides **@MessagingGateway** on interfaces and **@Gateway** to configure individual methods. When the interface is properly registered in the Spring context, the framework builds a proxy that performs mapping and sends the Message.

### 2.1. A Gateway Is Not an HTTP Gateway

A **@MessagingGateway** is the application's Java interface to Spring Integration. It can send messages to `DirectChannel`, `QueueChannel`, `ExecutorChannel`, JMS/AMQP adapters, or many other endpoints.

An **HTTP inbound/outbound gateway** is an integration adapter over HTTP. Both use the word "gateway," yet their APIs, request/reply lifecycles, metadata mappings, and timeouts have different responsibilities.

### 2.2. The Gateway Is an Entry Point, Not an Automatic Business Identity Verifier

If code calls:

~~~java
gateway.preview(command, "tenant-admin", "evt-1", "quote:admin:...");
~~~

the annotation **@Header("trustedTenantId")** maps the second argument into a header named `trustedTenantId`. It **does not automatically verify** that the caller is authorized for `tenant-admin`.

A safe workflow must be:

~~~text
Authenticated application caller
    -> verify tenant + shipment + workflowEpoch
    -> calculate trusted event/group identity
    -> call Gateway method
    -> Spring Message with verified headers
~~~

If a Gateway interface is exposed directly to a controller accepting arbitrary HTTP parameters, an authentication/authorization layer must run before the Gateway call; having the word `"trusted"` in a header name does not create trust.

## 3. Mapping Direction: Gateway Differs from Service Activator

The easiest mistake is forgetting that both Gateway and Service Activator can use **@Header**, but in **opposite directions**:

~~~mermaid
flowchart LR
    C["Gateway method arguments"] -->|"@Payload / @Header"| M["Spring Message"]
    M -->|"@Payload / @Header"| H["Service Activator parameters"]
    H -->|"return value"| R["Reply Message"]
    R --> G["Gateway method return"]
~~~

| Annotation Site | Data Source | Target | Example |
| --- | --- | --- | --- |
| **Gateway @Payload** | Argument when Java calls Gateway | Message payload | `QuoteCommand` |
| **Gateway @Header** | One argument when Java calls Gateway | One Message header | `tenantId → trustedTenantId` |
| **Gateway @Headers** | Java caller's `Map` argument | Multiple Message headers | `Map.of("traceRef", "...")` |
| **Gateway @GatewayHeader** | Value/SpEL in Gateway config | Message header | `operationKind=PREVIEW` |
| **Service Activator @Payload** | Received Message payload | Java handler argument | `QuoteCommand request` |
| **Service Activator @Header** | Received Message header | Java handler argument | `String tenantId` |

On a Gateway, `@Header("trustedTenantId") String tenantId` means **put `tenantId` from the method call into the header**. On a downstream handler, the same-named annotation means **extract the header from the message into the parameter**.

### 3.1. Do Not Swap the Two Roles

~~~java
// Gateway: caller supplies a value, Gateway builds Message.
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);

// Service Activator: handler reads a value from Message.
QuoteReceipt handle(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

The two signatures look similar, yet the Gateway method has a Spring Integration–generated proxy; the Service Activator method is an implementation invoked by the framework when a message reaches the endpoint.

### 3.2. Spring Message Headers Are Not HTTP Request Headers

When a Java Gateway attaches `trustedTenantId`, it is a header in **Spring Messaging**. If the flow sends over HTTP/JMS/AMQP/TCP, a separate step determines how that header is serialized/mapped onto the protocol. There is no guarantee every Spring header passes through every adapter automatically.

## 4. Example Contract: Shipping Quote Request

This lesson uses Java 17 records to focus on header mapping without connecting to a bank or real carrier. A quote command has:

- **Payload:** `shipmentId`, `serviceLevel`, `parcelCount`, `workflowEpoch`.
- **Per-invocation headers:** `trustedTenantId`, `businessEventId`, `businessCorrelationKey`.
- **Fixed Gateway headers:** `gatewaySource` and `operationKind`.
- **Reply:** `QuoteReceipt`, containing fields needed to verify the request/reply path.

### 4.1. Data Types

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum ServiceLevel {
    STANDARD,
    EXPRESS
}

record QuoteCommand(
        String shipmentId,
        ServiceLevel serviceLevel,
        int parcelCount,
        int workflowEpoch) {

    QuoteCommand {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (parcelCount < 1 || parcelCount > 1000) {
            throw new IllegalArgumentException("INVALID_PARCEL_COUNT");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record QuoteReceipt(
        String shipmentId,
        String tenantId,
        String eventId,
        String businessCorrelationKey,
        String gatewaySource,
        String operationKind,
        ServiceLevel serviceLevel,
        BigDecimal amountVnd) {
}
~~~

The prices in the upcoming example are only an illustrative calculation for integration tests: `STANDARD = 30,000 VND/parcel`, `EXPRESS = 80,000 VND/parcel`. This is not a real product rate card.

### 4.2. Business Correlation Key Derived from a Trusted Scope

~~~java
final class QuoteIdentity {
    private QuoteIdentity() {}

    static String businessKey(
            String tenantId, QuoteCommand command) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        return "quote:v1:" + tenantId
                + ":" + command.shipmentId()
                + ":" + command.workflowEpoch();
    }
}
~~~

Using tenant, shipment, and `workflowEpoch` ensures:

- Two tenants with the same `shipmentId` are not merged into one group.
- Two processing epochs of the same shipment are not confused.
- Redeliveries of the same logical operation produce the same business key.

**Not enough for authorization:** the algorithm above only builds a deterministic string. An application service must still verify that the user/producer actually has permission for the tenant and shipment.

### 4.3. Headers Allowed in the Request

| Spring Header Name | Type | Source | Required? |
| --- | --- | --- | --- |
| `trustedTenantId` | String | Authenticated application context | Yes |
| `businessEventId` | String | Verified/persisted stable event ID | Yes |
| `businessCorrelationKey` | String | `QuoteIdentity` / business workflow registry | Yes |
| `gatewaySource` | String | `@MessagingGateway` default header | Yes per config |
| `operationKind` | String | `@Gateway` method header | Yes per config |
| `traceRef` | String | Observability, method-dependent | Optional |
| `replyChannel` | Runtime `MessageChannel` | Gateway framework | Not a business argument |

Some metadata can live in a payload envelope instead of headers when durability across wire/restarts is needed. This lesson primarily demonstrates **converting Java method arguments into Spring Message headers** inside the JVM.

## 5. Gateway Interface: `@Payload` + Multiple `@Header`s

Main example:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.GatewayHeader;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "JAVA_APP"))
interface ShippingQuoteGateway {

    @Gateway(
            requestTimeout = 5_000,
            replyTimeout = 5_000,
            headers = @GatewayHeader(
                    name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

When called:

~~~java
QuoteCommand command = new QuoteCommand(
        "SHIP-901", ServiceLevel.EXPRESS, 2, 7);

String groupKey = QuoteIdentity.businessKey("tenant-a", command);

QuoteReceipt reply = gateway.preview(
        command,
        "tenant-a",
        "evt-quote-901",
        groupKey);
~~~

The Gateway builds a Spring Message containing:

~~~text
Message.payload:
  QuoteCommand(SHIP-901, EXPRESS, 2, 7)

Message.headers:
  trustedTenantId        = tenant-a       (@Header method argument)
  businessEventId        = evt-quote-901  (@Header method argument)
  businessCorrelationKey = quote:v1:...   (@Header method argument)
  gatewaySource          = JAVA_APP       (@MessagingGateway defaultHeader)
  operationKind          = PREVIEW        (@Gateway method header)
  id/timestamp           = framework-assigned
  replyChannel           = Gateway-managed if reply is expected
~~~

**Note:** the Java method name `preview` does not automatically become a header named `operationKind`. The `PREVIEW` value in the example is attached **explicitly** via `@GatewayHeader`, not inferred automatically.

### 5.1. Role of Each Annotation

- **@MessagingGateway:** marks an interface for a Gateway proxy; can configure `defaultRequestChannel`/`defaultHeaders`.
- **@Gateway:** customizes request channel, headers, and timeouts for a specific method.
- **@Payload:** identifies which argument becomes the Message payload.
- **@Header("..."):** identifies which argument becomes a header with that name.
- **@GatewayHeader:** attaches a header from method/interface configuration without adding a Java argument.

### 5.2. Why Use `@Payload` Explicitly?

With a single simple parameter, the Gateway can infer the payload. When a method has multiple arguments—especially a **`Map`** alongside header-annotated arguments—adding `@Payload` makes the contract unambiguous and avoids relying on subtle conventions.

### 5.3. Why Not Pass `String sourceSystem` on Every Call?

If the source is always an internal Java API, `gatewaySource=JAVA_APP` need not be typed by every caller. A **@GatewayHeader(value=...)** expresses a fixed configured source and avoids typo-prone arguments.

By contrast, **`tenantId`**, **`eventId`**, and **`businessCorrelationKey`** vary per invocation, so they should be parameters or computed by a trusted facade—never hardcoded in `@GatewayHeader`.

## 6. `@GatewayHeader`: Static Headers, Default Headers, and SpEL

**@Header** on a parameter takes its value **from the invocation argument**. **@GatewayHeader** declares header values **in the Gateway configuration**. Its key attributes are:

- `name`: header name.
- `value`: static value.
- `expression`: SpEL expression evaluated when creating the Message.

These are two different header-creation paths, not interchangeable ways of writing the same thing in all cases.

### 6.1. Common Header for Every Method

~~~java
@MessagingGateway(
    defaultRequestChannel = "quoteRequests",
    defaultHeaders = {
        @GatewayHeader(name = "gatewaySource", value = "JAVA_APP"),
        @GatewayHeader(name = "contractVersion", value = "1")
    })
interface MultiOperationQuoteGateway {
    QuoteReceipt preview(@Payload QuoteCommand command);
    QuoteReceipt recalculate(@Payload QuoteCommand command);
}
~~~

This is a **separate interface variant** illustrating default headers; do not register it alongside the main example's gateway/flow without clear separation. Both methods receive `gatewaySource=JAVA_APP` and `contractVersion=1`.

**`contractVersion` here is a header string**, not automatically equivalent to a JSON payload version or business tariff version. If you need `schemaVersion` as an `Integer`, configure/convert accordingly and test it.

### 6.2. Per-Method Header

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteActions {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(@Payload QuoteCommand command);

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "RECALCULATE"))
    QuoteReceipt recalculate(@Payload QuoteCommand command);
}
~~~

Both methods can share one request channel while a downstream Router splits on `operationKind`. This value is configured by the Gateway, not chosen freely by clients as a dynamic channel name.

### 6.3. Header from Expression

Spring Integration documentation supports SpEL to build headers; the evaluation context can expose **gateway method** and **method arguments**. Example:

~~~java
@MessagingGateway(
    defaultRequestChannel = "quoteRequests",
    defaultHeaders = @GatewayHeader(
            name = "gatewayMethodName",
            expression = "method.name"))
interface DiagnosticQuoteGateway {

    QuoteReceipt preview(@Payload QuoteCommand command);
}
~~~

In compatible configurations, `method.name` produces the method name string. A String value can be helpful for internal audit/routing; **never serialize the raw `java.lang.reflect.Method` object**, as it is not a portable wire contract.

If you want to derive a header from method arguments, SpEL can also reference `args` per the Gateway expression context contract. However, an argument carrying business identity should generally use an **explicit `@Header`**, rather than a positional expression that breaks silently when refactoring the method signature.

### 6.4. Precedence on Name Collisions

Avoid defining the same header in multiple places. Per Gateway documentation, a **method-specific header configuration** can take precedence over a default header; in certain configurations, a method-specific header can even override a `@Header` parameter value. Meanwhile, **default headers do not override an interface method's `@Header`**.

Example to avoid:

~~~java
@Gateway(headers = @GatewayHeader(
        name = "trustedTenantId", value = "tenant-admin"))
QuoteReceipt unsafe(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

Here `trustedTenantId` is supplied **both via argument and static configuration**, creating privilege confusion. Never rely on precedence rules to resolve **authorization metadata**: clearly assign header ownership and test the actual value.

### 6.5. Never Use SpEL to "Authenticate" the Sender

An expression copying `args[1]` into `trustedTenantId` is still merely **copying data**. Authorization must rely on an authenticated principal and registry, not on SpEL evaluating successfully.

## 7. `@Headers` Map: One Argument Creating Multiple Headers

When the set of headers varies within a verified context, the Gateway supports `@Headers` on a **`Map`**:

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "JAVA_APP"))
interface QuoteWithContextGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt previewWithContext(
            @Payload QuoteCommand command,
            @Headers Map<String, Object> contextHeaders);
}
~~~

The caller can pass:

~~~java
Map<String, Object> trustedHeaders = Map.of(
        "trustedTenantId", "tenant-a",
        "businessEventId", "evt-quote-901",
        "businessCorrelationKey",
                "quote:v1:tenant-a:SHIP-901:7",
        "traceRef", "trace-901");

QuoteReceipt reply =
        gateway.previewWithContext(command, trustedHeaders);
~~~

This `Map` is **expanded into multiple Message headers**, rather than becoming the payload. `@Payload` explicitly marks `command` as the payload.

### 7.1. Risks of a Dynamic `Map`

If the `Map` comes from an unauthenticated client's body or request headers, the caller could try injecting:

~~~text
trustedTenantId=tenant-admin
businessCorrelationKey=quote:v1:tenant-admin:...
replyChannel=untrustedDestination
errorChannel=untrustedErrorRoute
~~~

**Never pass a raw external `Map` directly into `@Headers`.** The `Map` must be constructed by a verified application service and contain only allowlisted headers. At ingress, strip framework control headers such as `replyChannel`, `errorChannel`, and `routingSlip` unless explicitly permitted by internal trust policy.

### 7.2. `@Headers` Does Not Replace a Business DTO

If you need item value, weight, delivery address, or `parcelCount`, put them in the **typed payload** `QuoteCommand`, not stuffed into a `Map` of headers. Headers suit routing, correlation, tracing, and out-of-band metadata; business data deserves an explicit schema/version.

### 7.3. When the `Map` Is Typed and Validated

A facade can accept a **`VerifiedQuoteContext`** and construct the `Map`:

~~~java
record VerifiedQuoteContext(
        String tenantId,
        String eventId,
        String traceRef) {
}

final class QuoteGatewayFacade {
    private final QuoteWithContextGateway gateway;

    QuoteGatewayFacade(QuoteWithContextGateway gateway) {
        this.gateway = gateway;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            VerifiedQuoteContext context) {

        // Context must be created by auth/registry, not the client.
        String groupKey = QuoteIdentity.businessKey(
                context.tenantId(), command);

        Map<String, Object> headers = Map.of(
                "trustedTenantId", context.tenantId(),
                "businessEventId", context.eventId(),
                "businessCorrelationKey", groupKey,
                "traceRef", context.traceRef());

        return gateway.previewWithContext(command, headers);
    }
}
~~~

**Example limitation:** `VerifiedQuoteContext` is a record, not an authentication mechanism. Production must restrict where this context can be instantiated or use real authentication and authorization services before invoking the facade.

## 8. Default Conventions and Ambiguous Method Signatures

Gateway documentation describes conventions when **`@Payload`/`@Headers` are omitted**. Simple cases can be inferred, yet complex ones can become **unable to resolve the payload**.

### 8.1. One Non-`Map` Argument

~~~java
void send(QuoteCommand command);
~~~

By convention, this argument can be used as the payload. However, when an API carries several headers, `@Payload QuoteCommand command` makes responsibilities clearer.

### 8.2. One Object and One `Map`

~~~java
void send(QuoteCommand command, Map<String, Object> headers);
~~~

Spring Integration has a convention mapping the first object argument as payload and the second `Map`'s entries as headers when unambiguous. Still, code gets harder to read and can change meaning if the signature evolves. Explicit form:

~~~java
void send(
        @Payload QuoteCommand command,
        @Headers Map<String, Object> headers);
~~~

### 8.3. A Single `Map` Can Be the Payload Itself

~~~java
void send(Map<String, Object> body);
~~~

Per the documentation, when a method has only one `Map`, that `Map` can be treated as the **payload**, not a set of headers. If you intend to send a JSON-like `Map` as payload, write it explicitly:

~~~java
void send(@Payload Map<String, Object> body);
~~~

If you intend to use the `Map` as headers, add a payload argument or a valid payload expression per contract.

### 8.4. Two Unannotated `Map`s: Insufficient Information

~~~java
void ambiguous(
        Map<String, Object> first,
        Map<String, Object> second);
~~~

The Gateway lacks enough information to decide which `Map` is the payload and which is headers. This is not a "wrong headerName" bug; the **method-to-message mapping itself is ambiguous**.

~~~java
void explicit(
        @Payload Map<String, Object> payload,
        @Headers Map<String, Object> headers);
~~~

For large business data or stable schemas, a DTO is usually easier to validate than a `Map` payload.

### 8.5. Invalid Signatures

~~~java
// Do not use two independent payload parameters:
void invalidTwoPayloads(
        @Payload String a,
        @Payload String b);

// Do not mark the same argument as both payload and header:
void invalidSameArgument(
        @Payload @Header("x") String a);

// Do not mark a Map as both payload and header collection:
void invalidPayloadHeaders(
        @Payload @Headers Map<String, Object> input);
~~~

A Gateway needs **one well-defined payload**, while other arguments supply headers or feed a method-level payload expression.

## 9. When `@Payload` Uses Expressions and Zero-Payload-Argument Methods

Spring Integration supports supplying payloads via **expressions** on a Gateway, useful when a method only takes arguments used to compute a value or takes no arguments at all.

Example method-level expression:

~~~java
@MessagingGateway(defaultRequestChannel = "commands")
interface CommandTriggerGateway {

    @Gateway(payloadExpression = "'RUN_HEALTH_CHECK'")
    String runHealthCheck();
}
~~~

This is a **separate variant** using `requestChannel` `"commands"`; to run it, a consumer must return a matching `String` reply. It does not use `@Header` to construct the payload. Never register a zero-argument Gateway expecting the framework to invent business content without a payload expression or `PollableChannel` receive semantics.

### 9.1. Method-Level `@Payload` and Expressions

Documentation also permits `@Payload` with an expression in compatible scenarios:

~~~java
@MessagingGateway(defaultRequestChannel = "commands")
interface ExpressionGateway {

    @Payload("args[0] + ':' + args[1]")
    String combine(String prefix, String suffix);
}
~~~

This shows expressions can read method arguments; this is a way to **build the payload**, not attach headers. If `@Gateway(payloadExpression=...)` is also declared, check framework precedence and test the result instead of stacking duplicate expressions.

### 9.2. Should Expressions Be Used to Build Business Correlation?

You could write SpEL combining tenant and shipment from arguments, yet whenever correlation drives permissions or idempotency, let a **trusted facade/domain service** compute and validate the key and pass it via `@Header`. Concise expressions do not replace tenant/epoch validation or key-algorithm versioning.

## 10. When Conventions Are Not Enough: `MethodArgsMessageMapper`

If a method signature is so complex that annotations and conventions cannot express the mapping, Spring Integration offers the **`MethodArgsMessageMapper`** extension to convert `MethodArgsHolder` into a `Message` directly.

This is an **advanced** option and should not replace a few simple `@Header`s. When writing a custom mapper:

- Decide explicitly which argument is the payload.
- Decide allowed headers and type conversions.
- Own updates whenever method signatures/overloads change.
- Verify compatibility of default/method-level gateway headers and payload expressions with the custom mapper.
- Test the real gateway proxy, not only the mapper helper directly.

Per Gateway configuration docs, a custom mapper has **restrictions preventing combination** with certain default-payload-expression and header definitions. Do not pile every mapping mechanism onto one interface hoping the framework automatically picks the right one.

### 10.1. Choosing the Right Mapping Approach

| Requirement | Suitable Approach |
| --- | --- |
| Single typed payload | `@Payload` on the argument |
| A few per-invocation headers | `@Header` on each argument |
| Validated dynamic header set | `@Headers Map` |
| Static header across all Gateway methods | `@MessagingGateway(defaultHeaders=...)` |
| Static header for one method | `@Gateway(headers=@GatewayHeader(...))` |
| Header computed from gateway method metadata | `@GatewayHeader(expression=...)` |
| Payload computed from expressions | `@Gateway(payloadExpression=...)` or `@Payload` expression |
| Highly specialized mapping | Custom `MethodArgsMessageMapper` + contract tests |

**Prefer the simplest readable, testable approach.** When headers carry tenant/correlation/authorization context, explicitness is worth far more than saving a few lines of code.

## 11. Flow Receiving Messages Built by the Gateway

To inspect the mapped headers, build a **Service Activator via Java DSL**. It receives `QuoteCommand` and the headers `Map`, validates metadata, and returns `QuoteReceipt`.

### 11.1. Service Reading Headers and Building Reply

~~~java
import java.math.BigDecimal;
import java.util.Map;

final class QuotePreviewService {

    private static String requiredHeader(
            Map<String, Object> headers, String name) {
        Object value = headers.get(name);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REQUIRED_HEADER_" + name);
        }
        return text;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            Map<String, Object> headers) {

        String tenantId = requiredHeader(
                headers, "trustedTenantId");
        String eventId = requiredHeader(
                headers, "businessEventId");
        String correlationKey = requiredHeader(
                headers, "businessCorrelationKey");
        String source = requiredHeader(
                headers, "gatewaySource");
        String operation = requiredHeader(
                headers, "operationKind");

        String expected = QuoteIdentity.businessKey(
                tenantId, command);
        if (!expected.equals(correlationKey)) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }
        if (!"JAVA_APP".equals(source)
                || !"PREVIEW".equals(operation)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_GATEWAY_HEADER_CONTRACT");
        }

        long unitPrice = command.serviceLevel()
                == ServiceLevel.EXPRESS ? 80_000L : 30_000L;
        BigDecimal amountVnd = BigDecimal.valueOf(unitPrice)
                .multiply(BigDecimal.valueOf(command.parcelCount()));

        return new QuoteReceipt(
                command.shipmentId(),
                tenantId,
                eventId,
                correlationKey,
                source,
                operation,
                command.serviceLevel(),
                amountVnd);
    }
}
~~~

`QuoteReceipt` **echoes the key header fields** so tests can spot mismatches across Gateway → Message → handler. In real production handlers, do not expose all internal metadata to unprivileged clients; this example is solely for observing mapping.

### 11.2. Java DSL Configuration and Gateway Scanning

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteFlowConfig {

    @Bean
    MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    QuotePreviewService quotePreviewService() {
        return new QuotePreviewService();
    }

    @Bean
    IntegrationFlow quoteProcessingFlow(
            QuotePreviewService service) {
        return IntegrationFlow.from("quoteRequests")
                .handle(QuoteCommand.class, service::preview)
                .get();
    }
}
~~~

**Code placement:** Place the `ShippingQuoteGateway` interface in a package scanned by **@IntegrationComponentScan** (same package or explicitly configured scope). **@EnableIntegration** activates Spring Integration infrastructure. Standard `@ComponentScan` alone does not register `@MessagingGateway` interfaces by default; you need `@IntegrationComponentScan` or equivalent `GatewayProxyFactoryBean` registration.

### 11.3. Reply Path Back to the Gateway

When the Gateway method `preview()` has return type `QuoteReceipt`, the Gateway normally creates a **temporary anonymous reply channel** for the invocation. In this example, the handler at the end of the flow returns `QuoteReceipt` without sending it to another fixed `QueueChannel`, allowing the reply to return directly to the caller per framework semantics.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as ShippingQuoteGateway
    participant F as quoteRequests DirectChannel
    participant H as QuotePreviewService
    C->>G: preview(command, tenant, eventId, groupKey)
    G->>G: Map args to Message payload/headers
    G->>F: Message with temporary replyChannel
    F->>H: handle(command, headers)
    H-->>F: QuoteReceipt
    F-->>G: Reply via Gateway-managed channel
    G-->>C: QuoteReceipt Java return
~~~

Appending `.channel("someQueue")` after the handler without a reply path from that queue back to the Gateway can make the caller time out. Never equate a **custom `outputChannel`** with the **Gateway's `replyChannel`**.

### 11.4. Method-Level `@Gateway` and `defaultRequestChannel`

The example interface sets `defaultRequestChannel="quoteRequests"`, so `preview()` does not repeat `requestChannel`. If another method needs a different Router, you can write:

~~~java
@Gateway(requestChannel = "specialQuoteRequests")
QuoteReceipt special(@Payload QuoteCommand command);
~~~

However, a `MessageChannel` and consumer named `specialQuoteRequests` must exist. The annotation neither creates a full business flow automatically nor validates the new method's tenant/mapping.

## 12. Mapping to a Service Activator Using `@Header` on the Receiving Side

If you prefer reading headers via annotated parameters instead of a Java DSL `Map`, you can replace `QuotePreviewService` with a Service Activator:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class QuoteReceivingActivator {

    @ServiceActivator(inputChannel = "quoteRequests")
    public QuoteReceipt handle(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey,
            @Header("gatewaySource") String source,
            @Header("operationKind") String operation) {

        return new QuotePreviewService().preview(
                command,
                Map.of(
                        "trustedTenantId", tenantId,
                        "businessEventId", eventId,
                        "businessCorrelationKey", groupKey,
                        "gatewaySource", source,
                        "operationKind", operation));
    }
}
~~~

**This is an alternative option**: if you use the `QuoteReceivingActivator` bean, remove the `IntegrationFlow` bean consuming `quoteRequests`; never leave two consumers sharing one `DirectChannel` when only one business handler is intended.

Remember:

- **Gateway @Header**: Java argument → Spring header.
- **Service Activator @Header**: Spring header → Java parameter.

Combining both sides forms a clean data pipeline where domain services never need to inspect HTTP or broker headers.

### 12.1. Required Headers on the Receiving Side

At the Gateway, arguments can be passed as `null` or violate the contract; at the Service Activator, `@Header` usually requires the header to be present. If missing or unconvertible, the endpoint can fail **before entering the method body**.

**Checking presence alone is not enough:** `tenantId` could be syntactically valid `"tenant-admin"` while unauthorized. Authorization must be verified at the application boundary.

### 12.2. Why Not Use `Map` Across Every Layer?

A Gateway can flexibly take `@Headers Map` and a handler can take `@Headers Map`, yet passing `Map` down into the domain layer weakens schema control. A better pattern:

~~~text
VerifiedQuoteContext (typed)
    -> Gateway @Header arguments
    -> Spring Message headers
    -> Receiving adapter / Service Activator
    -> QuoteBusinessContext (typed)
    -> Domain service
~~~

Typed contexts allow construction-time validation and prevent mixing up `tenantId` with `traceId`, though **real authentication/authorization is still required**.

## 13. Header Mapping and Downstream Routers

A Gateway can set an `operationKind` header so a Router chooses branches:

~~~mermaid
flowchart LR
    G["Gateway methods"] --> M["Message + operationKind"]
    M --> R{"Header-based Router"}
    R -->|"PREVIEW"| P["previewSubflow"]
    R -->|"RECALCULATE"| C["recalculateSubflow"]
    R -.->|"Unsupported"| E["Reject / error"]
    P --> O["Reply"]
    C --> O
~~~

### 13.1. Why Route by Header?

The `QuoteCommand` payload describes the quote request. `operationKind` describes the **execution intent** of the Gateway method. When two operations share the same payload type yet need different routes, a header lets the Router branch without polluting `QuoteCommand` with non-domain fields.

### 13.2. Java DSL Header-Routing Example

~~~java
// Illustrative flow fragment; use instead of quoteProcessingFlow
// from Section 11 in a separate test Spring context.
@Bean
IntegrationFlow quoteRouteFlow() {
    return IntegrationFlow.from("quoteRequests")
            .route(
                    message -> message.getHeaders()
                            .get("operationKind"),
                    mapping -> mapping
                            .channelMapping(
                                    "PREVIEW", "previewRequests")
                            .channelMapping(
                                    "RECALCULATE", "recalcRequests")
                            .defaultOutputChannel("unsupportedQuoteRequests"))
            .get();
}
~~~

To run it, you must declare the channels and subflows handling `previewRequests`, `recalcRequests`, and `unsupportedQuoteRequests`. This is an isolated fragment, not a drop-in replacement for the entire prior chapter.

### 13.3. Never Route by Arbitrary Client Channel Names

Do not accept a `destination` method argument and dispatch directly to a client-named `MessageChannel` such as `adminPaymentQueue`. Let callers pick a **business operation** from an allowlist, then map operation → channel inside trusted configuration. Header routing is not authorization.

### 13.4. Never Turn the Default Route into Fake Success

If a new `operationKind` is not supported yet, reject/quarantine/route to an unsupported flow with an explicit error policy. Never fall back by routing to `PREVIEW` and returning a successful `QuoteReceipt`, as that makes an unverified business decision.

## 14. Which Headers Are Managed by the Framework?

Gateway mapping creates custom headers, while Spring Integration also manages **framework headers**:

| Header | Owner | Meaning |
| --- | --- | --- |
| `id` | Spring `Message` | Message instance identity |
| `timestamp` | Spring `Message` | Message creation timestamp |
| `replyChannel` | Gateway / request-reply runtime | Reply destination for the invocation |
| `errorChannel` | Flow / error-handling config | Error-handling path |
| `correlationId` | Splitter/Aggregator or scoped app | Groups messages |
| `sequenceNumber` | Splitter / sequence infrastructure | Child order |
| `sequenceSize` | Splitter / sequence infrastructure | Expected child count |
| `trustedTenantId` | Verified application boundary | Tenant |
| `businessEventId` | Application | Logical event ID |
| `businessCorrelationKey` | Application / workflow | Business group identity |

Gateway method arguments **should not manually inject `replyChannel`/`errorChannel`** via an arbitrary `Map`, unless building a tightly controlled infrastructure adapter with well-understood security semantics.

### 14.1. Spring Message ID Is Not `businessEventId`

~~~text
Invocation 1:
  Spring MessageHeaders.ID = m-001
  businessEventId          = evt-quote-901

Invocation 2 (retry):
  Spring MessageHeaders.ID = m-002
  businessEventId          = evt-quote-901
~~~

If a retry belongs to the same logical operation, **`businessEventId` stays identical**; the framework assigning a new Message ID is no reason to mint a new `eventId`.

### 14.2. Technical Correlation vs. Business Correlation

A Splitter can use `correlationId` to group child messages; a business workflow can use `businessCorrelationKey` across multiple adapters and epochs. Both values may occasionally coincide by design, yet **they do not have to be identical across every topology**.

Even if a Gateway method supplies `@Header("businessCorrelationKey")`, downstream handlers still need the matching `correlationStrategy` configured on the Aggregator; grouping does not happen just because the header exists.

### 14.3. Never Serialize Runtime `replyChannel` Over the Wire

A temporary `replyChannel` is an object in the Spring runtime. When sending requests over JMS/AMQP/HTTP/TCP, each protocol has its own reply/correlation mechanism; never serialize a live `MessageChannel` object into JSON or a broker property expecting another system to use it.

## 15. Gateway Return Types and Response Lifecycle

A Gateway can express:

- **Request/reply:** method returns a typed result.
- **Send-only:** method returns `void`.
- **Asynchronous/reactive variants:** when configured appropriately, method return types/adapters carry different semantics; never assume every return type is synchronous.

### 15.1. Typed Result

~~~java
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

The caller wants a `QuoteReceipt`. The Gateway must have a valid downstream reply path; if the handler only logs and returns `void`/`null` or a Filter discards, no `QuoteReceipt` can arrive.

### 15.2. Send-Only

~~~java
void submit(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

The caller receives no business result via the method. Spring Integration may set `nullChannel` as the reply destination on a one-way Gateway depending on framework version to discard any emitted reply, yet **send-only does not mean remote effects committed**.

### 15.3. Gateway Timeouts and Business Deadlines Are Two Different Clocks

`requestTimeout` governs waiting to send requests when a channel waits for space/registration; `replyTimeout` governs waiting for replies. With **`DirectChannel`**, a synchronous handler can run directly on the caller thread; setting `replyTimeout` does not interrupt an endlessly running business handler.

~~~text
requestTimeout = 2s:
  sending Message into a channel that may wait for capacity

replyTimeout = 5s:
  waiting for reply Message after request has been dispatched

businessDeadline = 2 minutes:
  quote workflow must reach a final decision
~~~

Never use a single timeout to infer whether a remote provider finished. When a Gateway times out, side effects may already have occurred; use an idempotency key and reconciliation when retrying.

## 16. Application Layer Should Verify Data Before Calling the Gateway

A Gateway interface with multiple `@Header` parameters makes the API explicit, yet it also allows any caller holding a reference to the proxy to pass arbitrary strings. For sensitive metadata, provide an **application facade** that enforces permissions and constructs headers.

### 16.1. Verified Principal and Policy

~~~java
record AuthenticatedActor(
        String principalId,
        String tenantId) {
}

interface ShipmentQuoteAuthorization {
    void assertMayQuote(
            AuthenticatedActor actor,
            QuoteCommand command);
}

interface StableQuoteEventRegistry {
    String findOrCreateEventId(
            String tenantId, QuoteCommand command);
}
~~~

These interfaces represent dependencies that must be backed by real implementations in production. **`AuthenticatedActor`** must never be built from an unverified HTTP header; it must come from authentication, paired with authorization policies covering shipment and epoch access.

### 16.2. Facade Attaching Headers from Verified Data

~~~java
final class SecureQuoteApplicationService {
    private final ShippingQuoteGateway gateway;
    private final ShipmentQuoteAuthorization authorization;
    private final StableQuoteEventRegistry events;

    SecureQuoteApplicationService(
            ShippingQuoteGateway gateway,
            ShipmentQuoteAuthorization authorization,
            StableQuoteEventRegistry events) {
        this.gateway = gateway;
        this.authorization = authorization;
        this.events = events;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            AuthenticatedActor actor) {

        authorization.assertMayQuote(actor, command);
        String tenant = actor.tenantId();
        String eventId =
                events.findOrCreateEventId(tenant, command);
        String groupKey = QuoteIdentity.businessKey(
                tenant, command);

        return gateway.preview(
                command, tenant, eventId, groupKey);
    }
}
~~~

**`StableQuoteEventRegistry`** is an abstraction: a real implementation must establish logical operation identity, persist it if needed, distinguish fresh requests from retries, and guard against event ID conflicts. Never generate a fresh UUID every time a caller retries the same job.

### 16.3. Why Not Let the Gateway Handle Authentication Itself?

A Gateway proxy primarily **maps arguments to a Spring Message and manages the invocation**, not acting as an identity provider or authorization engine. Keeping authorization at the application/ingress boundary clarifies metadata ownership and prevents unverified headers from driving security decisions.

### 16.4. Never Put Roles or Secrets into Gateway Headers

If a service needs to know whether a client has `ADMIN` rights, use a verified security context and a properly scoped authorization decision. An unprotected custom header `role=ADMIN` is trivially spoofed. Similarly, never stuff `Authorization` bearer tokens, session cookies, or private keys into headers just so downstream can log them.

## 17. Gateway Method Passing `Map<MessageHeaders>` or `Message<?>`?

Beyond typed payload + header annotations, a Gateway can accept a caller-built **`Message<?>`** to control both payload and headers. This option belongs in knowledgeable integration layers, not default business APIs.

~~~java
import org.springframework.messaging.Message;

@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface RawMessageQuoteGateway {
    QuoteReceipt preview(Message<QuoteCommand> message);
}
~~~

If the caller passes a `Message` with verified custom headers, the Gateway forwards that content. However, this couples the application caller to Spring Messaging and risks misconfiguring framework control headers.

### 17.1. When to Use `Message` vs. Multiple Arguments?

| Context | Recommendation |
| --- | --- |
| Domain/application service calling a simple command | Typed `@Payload` + `@Header` |
| Internal adapter already holding a validated Spring `Message` | `Message<?>` may fit |
| Custom middleware preserving headers across a trusted hop | `MessageBuilder.fromMessage(...)` |
| HTTP controller receiving raw requests | Parse/authorize → typed facade; never feed raw `Message` to Gateway |
| Persisting events long-term or sending to remote services | Versioned wire envelope/DTO |

**Never mix a `Message` parameter with `@Payload` parameters** for the same purpose unless you understand the custom mapping contract. A cleaner single source of truth is either accepting a complete `Message` **or** letting the Gateway construct the `Message` from arguments.

### 17.2. Distinguish `Map` Parameters from `MessageHeaders`

A `@Headers Map<String,Object>` on a Gateway **creates headers**. `MessageHeaders` on a received message is the **metadata of the created Message**. Both can hold custom entries, yet only `MessageHeaders` adds runtime framework-generated `id`, `timestamp`, and `replyChannel`.

Never require callers to supply `id` or `timestamp` for a Gateway method to work; the framework manages Message lifecycle metadata.

## 18. Header Propagation Across Transformers and Subflows

Header mapping at the Gateway is only the **first hop**. The Message may subsequently pass through Routers, Filters, Transformers, Splitters, and other subflows.

~~~mermaid
flowchart TD
    G["Gateway args -> headers"] --> R["Router"]
    R --> T1["STANDARD Transformer"]
    R --> T2["EXPRESS Transformer"]
    T1 --> C["Common Service Activator"]
    T2 --> C
    C --> O["Reply"]
~~~

### 18.1. Transformer Returning a New Payload

Spring Integration Transformers propagate inbound headers when returning a **new payload**, per framework rules. Example:

~~~java
// IntegrationFlow fragment, assuming quoteRequests has its own owner.
.transform(QuoteCommand.class, mapper::normalizeCommand)
~~~

When the mapper returns another DTO, custom headers such as `businessEventId` and `tenantId` normally remain on the outbound Message. Still, write **integration tests** to catch places where headers are stripped by a `HeaderFilter` or converter.

### 18.2. Handler Returning a New `Message`

~~~java
Message<?> rebuilt = MessageBuilder
        .withPayload(newPayload)
        .setHeader("businessEventId", originalEventId)
        .build();
~~~

If a handler builds a brand-new `Message` from scratch, other headers like `trustedTenantId`, `businessCorrelationKey`, or temporary `replyChannel` can go missing. Consequently, downstream Service Activators miss arguments or the Gateway never receives its reply.

For a **trusted internal `Message`**, to keep existing headers:

~~~java
Message<?> next = MessageBuilder.fromMessage(trustedInput)
        .setHeader("processingStage", "NORMALIZED")
        .build();
~~~

Never use `fromMessage` or `copyHeaders` to blindly copy all headers **from an unauthenticated external producer**. At the trust boundary, construct a new `Message` using an allowlist and verified identity first.

### 18.3. Splitter Changes the Technical Correlation Scope

When a Gateway request passes through a Splitter producing multiple child messages, the framework can attach `correlationId`, `sequenceNumber`, and `sequenceSize` for the Aggregator. Those are **topology sequence/group metadata** and do not replace the stable `businessCorrelationKey` from the Gateway method.

Example:

~~~text
businessCorrelationKey:
  quote:v1:tenant-a:SHIP-901:7

Splitter child 1:
  correlationId = batch-42
  sequenceNumber = 1
  sequenceSize = 2

Splitter child 2:
  correlationId = batch-42
  sequenceNumber = 2
  sequenceSize = 2
~~~

If a Gateway method awaits **one `QuoteReceipt`**, while a Splitter yields **two results** with no Aggregator/combiner, the reply path cannot guess which result to return. Design Scatter-Gather/Aggregator explicitly whenever multiple replies must be combined.

### 18.4. Routers Do Not Invent Business Correlation

A header-based Router can inspect `operationKind` to pick a branch, yet it does not verify tenant/correlation correctness or mint new event IDs. Business identity must travel across branches via trusted headers/envelopes or persist in a workflow store.

## 19. When a Gateway Calls a Remote Adapter

A Java Gateway can send Messages to a flow containing an outbound HTTP/JMS/AMQP/TCP gateway. **Two request/reply layers** can emerge:

1. **Java Messaging Gateway:** matches Java invocation to Spring reply message.
2. **Transport gateway:** matches request/response per protocol (HTTP response context, `JMSCorrelationID`/`JMSReplyTo`, AMQP `replyTo`/`correlationId`, TCP connection/request semantics).

### 19.1. The Two Correlation IDs Can Differ

~~~text
Business:
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7

Java Messaging Gateway:
  replyChannel = temporary Java runtime channel

JMS outbound gateway:
  JMSMessageID / JMSCorrelationID / JMSReplyTo

AMQP outbound gateway:
  replyTo / correlationId
~~~

Do not force all of these into the same string merely because they all use the word "correlation." The Gateway header `businessCorrelationKey` identifies the **business workflow**; transport correlation handles **one attempt's request/reply**.

### 19.2. HTTP Headers and Body

A custom Spring header does not automatically become an HTTP `X-Business-Correlation-Key` unless a `HeaderMapper`/converter is configured. For async callbacks, embed business identity in a **versioned wire envelope** or persisted mapping so the remote party can return it, never relying on the temporary `replyChannel` from the original Java call.

### 19.3. JMS and AMQP

JMS/AMQP support message properties/headers and their own request/reply correlation, yet not every Java object in Spring `MessageHeaders` serializes to a broker property. Simple headers (String/number/boolean) can be mapped per contract; a **`MessageChannel` object** is not a portable wire value.

### 19.4. TCP and File Adapters

TCP generally requires explicit framing/serializers to carry payloads and selected headers; a connection ID alone does not identify a business operation. File/SFTP adapters build messages from file contents, yet filename/`mtime` alone are not verified correlation keys.

### 19.5. Contract Tests Through Real Adapters

For the same Gateway method:

1. Verify headers right after the Gateway proxy.
2. Serialize through the outbound adapter.
3. Deserialize at the other inbound adapter.
4. Verify versioned business identity remains intact.
5. Check source/tenant authorization and protocol-level reply correlation.
6. Test retries, duplicates, timeouts, and late responses.

Pure Spring-context tests do not prove HTTP/JMS/AMQP/TCP header mapping works in production.

## 20. Async Flows: Headers Do Not Automatically Become `ThreadLocal`

When a request enters an `ExecutorChannel`, the worker thread can differ from the thread that invoked the Gateway:

~~~text
Caller thread:
  authenticated tenant = tenant-a
  gateway.preview(...)

Worker thread:
  ThreadLocal tenant may be absent/stale
  Message.header.trustedTenantId = tenant-a
~~~

Handlers must read **trusted Message metadata** or persisted workflow context rather than reading tenant authority from an unpropagated `ThreadLocal` belonging to another thread. Trace context may need instrumentation to link spans; it never replaces business `eventId`.

### 20.1. Synchronous and Asynchronous Flows Have Different Timeout Semantics

With `DirectChannel`, the handler runs on the caller thread and can block the entire invocation. With `ExecutorChannel`, the Gateway can send and wait for a reply on a temporary channel, yet scheduling, queue capacity, `errorChannel`, and reply timeouts must all be tested for that topology.

### 20.2. Do Not Treat Gateway Method Return as Durable Completion

If a method returns `QuoteReceipt` and the handler returns as soon as the command is **accepted**, the receipt may only be an intake ACK rather than the final business quote. Name/type `AcceptedReceipt` separately from `CompletedQuote` when operations have a longer lifecycle.

### 20.3. Late Callbacks

An HTTP/JMS callback arriving after the Gateway already timed out must reconcile into durable workflow state via `eventId`/`businessCorrelationKey`/`operationId`; it cannot send a reply into an expired temporary Java channel.

## 21. Unit Test: Business Logic After Headers Are Resolved

Before booting a Spring context, test `QuotePreviewService` by passing a **simulated header `Map` as if created by the Gateway**. These tests prove validation/business mapping, **not** that the Gateway proxy applied `@Header` properly.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class QuotePreviewServiceTest {

    private final QuotePreviewService service =
            new QuotePreviewService();

    private QuoteCommand command() {
        return new QuoteCommand(
                "SHIP-901", ServiceLevel.EXPRESS, 2, 7);
    }

    private Map<String, Object> validHeaders() {
        QuoteCommand command = command();
        return Map.of(
                "trustedTenantId", "tenant-a",
                "businessEventId", "evt-quote-901",
                "businessCorrelationKey",
                        QuoteIdentity.businessKey("tenant-a", command),
                "gatewaySource", "JAVA_APP",
                "operationKind", "PREVIEW");
    }

    @Test
    void completeHeaderMapCreatesExpectedReceipt() {
        QuoteReceipt receipt = service.preview(
                command(), validHeaders());

        assertEquals("tenant-a", receipt.tenantId());
        assertEquals("evt-quote-901", receipt.eventId());
        assertEquals(
                "quote:v1:tenant-a:SHIP-901:7",
                receipt.businessCorrelationKey());
        assertEquals("JAVA_APP", receipt.gatewaySource());
        assertEquals("PREVIEW", receipt.operationKind());
        assertEquals(ServiceLevel.EXPRESS, receipt.serviceLevel());
        assertEquals(new BigDecimal("160000"), receipt.amountVnd());
    }

    @Test
    void missingTenantIsNotSilentlyDefaulted() {
        Map<String, Object> incomplete =
                new HashMap<>(validHeaders());
        incomplete.remove("trustedTenantId");

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), incomplete));
    }

    @Test
    void forgedGroupKeyIsRejected() {
        Map<String, Object> forged =
                new HashMap<>(validHeaders());
        forged.put(
                "businessCorrelationKey",
                "quote:v1:tenant-b:SHIP-901:7");

        assertThrows(SecurityException.class,
                () -> service.preview(command(), forged));
    }

    @Test
    void headerOfWrongTypeCannotBecomeTenant() {
        Map<String, Object> wrong =
                new HashMap<>(validHeaders());
        wrong.put("trustedTenantId", 123);

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), wrong));
    }

    @Test
    void unsupportedOperationIsNotAcceptedAsPreview() {
        Map<String, Object> wrong =
                new HashMap<>(validHeaders());
        wrong.put("operationKind", "DELETE_SHIPMENT");

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), wrong));
    }

    @Test
    void businessKeyIsStableForSameWorkflow() {
        String first = QuoteIdentity.businessKey(
                "tenant-a", command());
        String replay = QuoteIdentity.businessKey(
                "tenant-a", command());

        assertEquals(first, replay);
        assertNotEquals(first, QuoteIdentity.businessKey(
                "tenant-b", command()));
    }
}
~~~

**Limitation:** the `Map` is constructed in test code, bypassing the Gateway. Thus these unit tests only verify `requiredHeader`, correlation, `operationKind`, and pricing logic. The centerpiece of this lesson—**real argument mapping**—requires an integration test.

## 22. Integration Test: Invoking the Gateway Proxy to Verify Argument → Header

In a Spring context with **@EnableIntegration**, **@IntegrationComponentScan**, and a `quoteRequests` consumer, call `ShippingQuoteGateway.preview` so the framework builds the real Message:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteFlowConfig.class)
class ShippingQuoteGatewayIntegrationTest {

    @Autowired
    ShippingQuoteGateway gateway;

    @Autowired
    QuoteWithContextGateway mapGateway;

    private QuoteCommand command(
            String shipment, ServiceLevel level, int epoch) {
        return new QuoteCommand(
                shipment, level, 2, epoch);
    }

    @Test
    void mapsPayloadAndEachAnnotatedHeader() {
        QuoteCommand command =
                command("SHIP-901", ServiceLevel.EXPRESS, 7);
        String groupKey =
                QuoteIdentity.businessKey("tenant-a", command);

        QuoteReceipt reply = gateway.preview(
                command,
                "tenant-a",
                "evt-quote-901",
                groupKey);

        assertNotNull(reply);
        assertEquals("SHIP-901", reply.shipmentId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("evt-quote-901", reply.eventId());
        assertEquals(groupKey, reply.businessCorrelationKey());
        assertEquals("JAVA_APP", reply.gatewaySource());
        assertEquals("PREVIEW", reply.operationKind());
        assertEquals(new BigDecimal("160000"), reply.amountVnd());
    }

    @Test
    void mapArgumentCreatesSeveralHeaders() {
        QuoteCommand command =
                command("SHIP-902", ServiceLevel.STANDARD, 2);
        String key =
                QuoteIdentity.businessKey("tenant-a", command);

        Map<String, Object> trustedHeaders = Map.of(
                "trustedTenantId", "tenant-a",
                "businessEventId", "evt-quote-902",
                "businessCorrelationKey", key,
                "traceRef", "trace-902");

        QuoteReceipt reply = mapGateway.previewWithContext(
                command, trustedHeaders);

        assertEquals("evt-quote-902", reply.eventId());
        assertEquals(key, reply.businessCorrelationKey());
        assertEquals("JAVA_APP", reply.gatewaySource());
        assertEquals("PREVIEW", reply.operationKind());
        assertEquals(new BigDecimal("60000"), reply.amountVnd());
    }

    @Test
    void twoTenantsWithSameShipmentHaveDifferentGroupKeys() {
        QuoteCommand command =
                command("SHIP-903", ServiceLevel.STANDARD, 1);

        QuoteReceipt tenantA = gateway.preview(
                command, "tenant-a", "evt-a-903",
                QuoteIdentity.businessKey("tenant-a", command));

        QuoteReceipt tenantB = gateway.preview(
                command, "tenant-b", "evt-b-903",
                QuoteIdentity.businessKey("tenant-b", command));

        assertEquals("tenant-a", tenantA.tenantId());
        assertEquals("tenant-b", tenantB.tenantId());
        assertNotEquals(
                tenantA.businessCorrelationKey(),
                tenantB.businessCorrelationKey());
    }

    @Test
    void reInvokingSameLogicalRequestDoesNotChangeBusinessKey() {
        QuoteCommand command =
                command("SHIP-904", ServiceLevel.EXPRESS, 3);
        String key =
                QuoteIdentity.businessKey("tenant-a", command);

        QuoteReceipt first = gateway.preview(
                command, "tenant-a", "evt-904", key);
        QuoteReceipt replay = gateway.preview(
                command, "tenant-a", "evt-904", key);

        assertEquals(first, replay);
    }
}
~~~

**Project integration note:** gateway interfaces must reside in a package scanned by `@IntegrationComponentScan`, or have their proxies registered equivalently. Variants like `MultiOperationQuoteGateway`, `QuoteActions`, `DiagnosticQuoteGateway`, and `ExpressionGateway` in this lesson are separate examples; do not place all of them into the same test package/context indiscriminately.

### 22.1. Why Does This Test Verify Mapping Properly?

Test code **never manually builds a Spring Message**; it simply calls `gateway.preview(command, tenant, eventId, groupKey)`. `QuotePreviewService` receives the `Map` of headers constructed by the framework. If `@Header` used the wrong name or `@GatewayHeader` default/method attributes did not apply, the service method would fail and the test would not receive the expected `QuoteReceipt`.

For `mapGateway.previewWithContext`, the integration test proves the `Map` is used by the Gateway as **headers** rather than payload—if mapping were wrong, the service would fail to receive `QuoteCommand` alongside all required headers.

### 22.2. Limitations of This Test

These tests use `DirectChannel` and pure handlers inside a Spring context. They **do not verify**:

- Real HTTP/JMS/AMQP/TCP `HeaderMapper` behavior over the wire.
- Authorization with JWT/mTLS/broker ACLs.
- Broker redelivery or process restarts.
- Distributed transactions and durable idempotency.
- Handlers blocking longer than timeouts on an asynchronous channel.
- External providers actually applying quotes or writing side effects.

They only prove **Gateway method-to-message mapping** and internal request/reply for the sample configuration.

## 23. Negative Integration Tests: Missing, Wrong-Type, or Spoofed Headers

Test these failure modes so refactoring a parameter or header name never silently delivers replies to the wrong tenant or group.

~~~java
// Add the following tests to ShippingQuoteGatewayIntegrationTest.
@Test
void wrongCorrelationArgumentCannotJoinAnotherWorkflow() {
    QuoteCommand command =
            command("SHIP-905", ServiceLevel.EXPRESS, 1);

    assertThrows(RuntimeException.class, () ->
            gateway.preview(
                    command,
                    "tenant-a",
                    "evt-905",
                    "quote:v1:tenant-b:SHIP-905:1"));
}

@Test
void wrongHeaderTypeFromMapIsRejected() {
    QuoteCommand command =
            command("SHIP-906", ServiceLevel.STANDARD, 1);
    String key = QuoteIdentity.businessKey("tenant-a", command);

    Map<String, Object> headers = Map.of(
            "trustedTenantId", 42,
            "businessEventId", "evt-906",
            "businessCorrelationKey", key);

    assertThrows(RuntimeException.class, () ->
            mapGateway.previewWithContext(command, headers));
}

@Test
void absentRequiredBusinessHeaderIsRejected() {
    QuoteCommand command =
            command("SHIP-907", ServiceLevel.STANDARD, 1);

    Map<String, Object> missingEventId = Map.of(
            "trustedTenantId", "tenant-a",
            "businessCorrelationKey",
                    QuoteIdentity.businessKey("tenant-a", command));

    assertThrows(RuntimeException.class, () ->
            mapGateway.previewWithContext(
                    command, missingEventId));
}
~~~

Gateway errors may be **wrapped** by Spring Integration in `MessagingException` with varying cause chains across handlers/versions. The examples assert `RuntimeException` to avoid tight coupling to the outer exception class; in real projects, assert the **root cause and error code** per your contract.

### 23.1. Testing Header Precedence with Two Same-Named Sources

If a method has both `@Header("operationKind")` on a parameter and `@Gateway(headers=...operationKind...)`, the final value may follow method-configuration precedence. Write a **dedicated contract test** to verify your exact dependency version if such a configuration must be supported. Better practice is **never letting two owners set the same header**.

### 23.2. Testing That Authorization Cannot Be Spoofed

A test could pass `tenant-admin` with a matching `businessKey` and `QuotePreviewService` would accept it because the two strings match. That is an **intentional limitation of the `QuotePreviewService` example**, not proof that `tenant-admin` is authorized. Real security tests must invoke `SecureQuoteApplicationService` with an authenticated actor and verify the policy denies shipments outside the tenant.

## 24. Dedicated Tests for `@GatewayHeader` Expressions and Default Headers

Beyond happy paths with static headers, write dedicated Gateway tests for `@GatewayHeader(expression="method.name")`:

1. Call `DiagnosticQuoteGateway.preview(command)`.
2. Use a test endpoint inspecting Message headers to verify `gatewayMethodName` equals `"preview"`.
3. Verify the header value is a `String`, not `java.lang.reflect.Method`.
4. If sending across a broker, serialize/deserialize through an adapter contract test.

When using `args[0]` expressions, also test reordering parameters: positional expressions can **run cleanly yet read the wrong semantic value**. A `@Header("businessEventId")`-annotated argument is far less fragile when signatures evolve.

### 24.1. Testing `Map` Ambiguity

An unannotated `send(Map first, Map second)` method must be treated as a **missing-contract configuration bug**, not a passing runtime scenario. Fix the signature to `@Payload Map payload, @Headers Map headers` before creating the Gateway proxy; if you test invalid examples, isolate them in a separate test configuration so they do not break the shared application context.

### 24.2. Do Not Assert Only That the Spring Context Started

A Gateway bean existing does not prove payload and headers map properly. Invoke the method, receive a reply from a handler that inspects the specific headers, and compare against inputs. When real adapters exist, verify outbound wire fields as well.

## 25. Where Do Failures Occur in the Gateway Lifecycle?

Errors involving header mapping and request/reply can happen across several layers:

~~~mermaid
flowchart TD
    A["Java method invocation"] --> B{"Method args mapping"}
    B -->|"Ambiguous / invalid"| E1["Gateway mapping error"]
    B -->|"PASS"| C{"Send to request channel"}
    C -->|"No capacity / no subscriber"| E2["Send failure / timeout"]
    C -->|"PASS"| D{"Downstream handler"}
    D -->|"Validation/security"| E3["Business rejection"]
    D -->|"Transient IO error"| E4["Retry / recovery"]
    D -->|"Reply"| R{"Reply path"}
    R -->|"Correct channel"| O["Java return value"]
    R -->|"Missing / late"| E5["Reply timeout / unknown state"]
~~~

### 25.1. Mapping Failure Before a Message Can Be Sent

For instance, a method with two unannotated `Map` arguments. The Gateway cannot determine payload vs. headers. This is a **method-to-message mapping** error, distinct from a business method receiving the Message and rejecting an invalid `correlationKey`.

### 25.2. Send Failure

The request channel may lack subscribers, be full, or target a misconfigured destination. `requestTimeout` applies where sends can block; with synchronous `DirectChannel`, subscriber exceptions can propagate on the same thread.

### 25.3. Downstream Business Handler Failure

If the Service Activator throws an exception, the Gateway may receive an error wrapped with `Message`/cause depending on the chain. Do not assume every exception routes to `errorChannel` before returning to the Java caller; sync/async semantics and error-channel configurations differ.

### 25.4. Reply Does Not Reach the Caller

A Transformer may return `null` or a Filter may discard, a one-way handler may emit no reply, or a rebuilt `Message` may drop `replyChannel`; in that case, a Gateway method returning `QuoteReceipt` can time out or get no result per Gateway contract.

**A reply timeout does not prove the business effect did not happen.** A provider that already recorded the command while the response was lost still causes a caller-side timeout.

### 25.5. Error Channels Are Not Automatically Durable

`ErrorMessage` can carry a `Throwable`, `failedMessage`, and related metadata depending on the exception. An in-memory `errorChannel` is not by itself a durable DLQ. With a configured error channel on the Gateway, errors can route to an error flow that transforms the response by design; test the Java caller's return type and exceptions.

### 25.6. Error-Handling Matrix

| Symptom | Likely Cause | Recommended Action |
| --- | --- | --- |
| Gateway bean missing | Missing `@IntegrationComponentScan`/config | Check registration/packages |
| Ambiguous payload | Two `Map`s / multiple unannotated payloads | Add `@Payload`/`@Headers` |
| Missing `tenantId` header | Caller omitted or wrong `Map` key | Reject and fix contract |
| Wrong header type | Bad raw map/string conversion | Parse/validate at facade |
| `CORRELATION_MISMATCH` | Mismatched tenant/shipment/epoch | Reject, audit trust boundary |
| `requestTimeout` | Channel rejected / queue full | Check capacity/backpressure/route |
| `replyTimeout` | Missing reply / late reply | Check `replyChannel`/handler contract |
| Result hits wrong workflow | Colliding/unverified business key | Enforce tenant/epoch scope, registry |
| Message redelivered | Broker ack/retry | Idempotency/recovery |
| Gateway returns unexpected `null` | No reply/error path or timeout contract | Check framework/version/return type |
| Remote side effect `UNKNOWN` | Timeout after sending request | Reconcile before retrying |

## 26. Retries, Redeliveries, and Idempotency: Mapped Headers Must Remain Stable

When a Gateway method is retried after a timeout, it can generate a new **`MessageHeaders.ID`** and temporary `replyChannel`. If it is still the **same logical operation**, `businessEventId` and `businessCorrelationKey` must remain unchanged.

~~~text
Attempt 1:
  Java Gateway invocation #1
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  Spring Message ID = msg-001
  replyChannel = temporary-A

Attempt 2:
  Java Gateway invocation #2
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  Spring Message ID = msg-002
  replyChannel = temporary-B
~~~

### 26.1. One Logical Event Must Never Generate a New UUID on Every Retry

If the facade writes:

~~~java
// Anti-pattern for operations requiring idempotency.
String eventId = java.util.UUID.randomUUID().toString();
gateway.preview(command, tenant, eventId, groupKey);
~~~

then every retry of the same job gets a new `eventId`; a downstream ledger will treat it as distinct work and create duplicate side effects. Obtain `eventId` from an **operation registry / persisted request identity** or a contract with stable identifiers.

### 26.2. Pure Preview Differs from Side-Effecting Commits

`QuotePreviewService` in this lesson is a pure calculation from `QuoteCommand`. Calling it twice returns the same price with no external changes. Yet if the flow expands to **reserve shipment**, **charge fee**, **create order**, or **send notification**, retries can create side effects. Enforce idempotency right at the handler/provider executing the effect.

### 26.3. Illustrative SQL Ledger

~~~sql
CREATE TABLE quote_operation_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    group_key VARCHAR(220) NOT NULL,
    shipment_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX quote_operation_pending_idx
    ON quote_operation_inbox (processing_status);
~~~

The primary key uses `tenant + producer + eventId` **if `eventId` is unique only within a producer namespace**. Adjust the schema if your identity contract differs. When the same identity arrives with a different `payload_digest`, that is an **`ID_CONFLICT`**, not a normal duplicate.

### 26.4. Crash Window After Marking Dedupe

~~~text
1. INSERT inbox event, status=SEEN
2. Commit
3. Crash before sending Message to downstream handler
4. Broker redelivers event
5. Dedupe sees SEEN and discards
=> Business effect may never run
~~~

Production designs can use **transactional inbox/outbox**, a workflow state machine, or recovery workers to distinguish `RECEIVED`, `DISPATCH_PENDING`, and `EFFECT_COMMITTED`. Gateway method mapping by itself does not solve distributed transactions.

### 26.5. Same Operation Across Different Transport Attempts

Across JMS/AMQP/HTTP, the protocol correlation token can change per attempt while **`businessEventId`/`operationId`** in the app stays stable. Never force `JMSCorrelationID` to equal the business key if the protocol Gateway requires a unique per-request token.

### 26.6. Late Replies and Final State

A reply from attempt 1 may arrive after attempt 2 has been sent. Attempt 1's temporary Gateway `replyChannel` may no longer have a waiting caller. If the reply still carries business meaning, reconcile into persisted workflow state using the **business key**. Never route a late reply into a newer Java invocation merely because `shipmentId` matches.

## 27. Security: Header Arguments Are Not Authorization

A Java method may look internal:

~~~java
gateway.preview(command, tenantId, eventId, groupKey);
~~~

yet its arguments may originate from an HTTP request, broker event, or file import. An attacker can supply someone else's `tenantId` if no trust boundary enforces access.

### 27.1. Wrong: Mapping Client Headers Directly to Gateway `@Header`

~~~java
// Anti-pattern that should not be used.
String tenant = request.getHeader("X-Tenant-Id");
String eventId = request.getHeader("X-Event-Id");

return gateway.preview(
        command,
        tenant,
        eventId,
        QuoteIdentity.businessKey(tenant, command));
~~~

Computing `groupKey` matches the `tenant` input, yet proves nothing about whether that `tenant` is authorized. A client can send `tenant-admin` and produce a syntactically valid business key.

### 27.2. Proper Order of Responsibility

~~~text
Authenticated principal
    -> verify tenant and shipment owner
    -> validate payload and workflowEpoch
    -> obtain stable event/operation identity
    -> compute trusted group key
    -> Gateway @Header arguments
    -> Message with allowlisted headers
~~~

### 27.3. `@Headers` `Map` Can Carry Control Headers

If an application passes a client-controlled `Map`, it might contain:

~~~text
trustedTenantId  = tenant-admin
replyChannel     = malicious-or-unintended-route
errorChannel     = arbitrary-route
routingSlip      = unexpected-internal-hop
~~~

Never pass that `Map` straight into the Gateway. Use an allowlist, strip framework control headers, and set reply/error routing via trusted configuration. In some topologies the framework may override/control certain headers, yet **never rely on that instead of explicit security checks**.

### 27.4. `traceId` Is Not Authority

A client-supplied `traceRef`/`traceId` can be used for observability after sanitization, yet never as business correlation, authorization, or an idempotency key. Logs/traces have separate access and retention controls; never log bearer tokens or private payloads from `MessageHeaders`.

### 27.5. Multi-Layer Validation

- **Payload:** command type, `shipmentId`, `parcelCount`, `workflowEpoch`.
- **Authenticated actor:** verified principal and tenant.
- **Binding:** shipment belongs to tenant; actor is allowed to preview.
- **Business group identity:** key computed/fetched from verified metadata.
- **Headers:** names, types, lengths, and sources per contract.
- **Transport:** source credentials, ACLs, signatures when needed.
- **Downstream:** `operationId`, idempotency, and service-level authorization.

**Never treat `@Header`, `@GatewayHeader`, or SpEL as authentication steps.**

## 28. Observability: Catching Mapping Bugs Before Business Incidents

When a Gateway method errors out, you need to know whether the issue lies in **argument mapping**, **send**, **downstream**, **reply**, or **business correlation**.

| Metric | Meaning | Suitable Labels |
| --- | --- | --- |
| **gateway_invocation_total** | Total Gateway invocations | `method`, `outcome` |
| **gateway_argument_mapping_failed_total** | Failed to resolve payload/headers | `method`, `reason` |
| **gateway_request_send_failed_total** | Message send failed | `channel`, `reason` |
| **gateway_reply_timeout_total** | Reply not received in time | `method` |
| **gateway_business_correlation_mismatch_total** | Wrong group identity | `method` |
| **gateway_header_missing_total** | Required header missing at receiver | allowlisted `headerName` |
| **gateway_header_type_error_total** | Wrong metadata type | `headerName`, bounded `typeClass` |
| **gateway_downstream_failed_total** | Handler error | `component`, `errorCode` |
| **gateway_duplicate_event_total** | Redelivery deduplicated | `operationType` |
| **gateway_inbox_pending** | Uncommitted operations | `state` |
| **gateway_integration_latency_seconds** | End-to-end invocation latency | `method` |
| **gateway_wire_mapping_failure_total** | Adapter serialize/deserialize failure | `protocol` |

Never attach `eventId`, `shipmentId`, `tenantId`, `traceId`, or `businessCorrelationKey` directly as metric labels because of high cardinality and potential data leakage. Use structured logs/traces with retention, redaction, and access controls.

### 28.1. Sample Log at Gateway Ingress

~~~json
{
  "component": "shippingQuoteGateway",
  "method": "preview",
  "payloadType": "QuoteCommand",
  "gatewaySource": "JAVA_APP",
  "operationKind": "PREVIEW",
  "eventRef": "evt-quote-901",
  "outcome": "SENT"
}
~~~

### 28.2. Sample Log on Mapping Error

~~~json
{
  "component": "quotePreviewService",
  "stage": "HEADER_VALIDATION",
  "headerName": "businessCorrelationKey",
  "reason": "CORRELATION_MISMATCH",
  "outcome": "REJECTED"
}
~~~

These are **application-defined logs**, not exact logs emitted automatically by Spring Integration. A mapping error can occur **before any Message enters a channel**, so instrumentation placed only inside a Service Activator misses Gateway method-to-message failures.

### 28.3. Distinguishing Trace IDs from Business IDs

- `traceId` links spans/requests for observability.
- `businessEventId` identifies a logical event for deduplication.
- `businessCorrelationKey` identifies a workflow/group spanning multiple events.
- Temporary `replyChannel` identifies the reply destination of a single Gateway invocation.
- Transport correlation identifies a protocol-level request/reply attempt.

Never lump everything into one header named `correlationId` without defining its scope.

## 29. Runbook: Gateway Receives All Arguments, Yet Downstream Misses Headers

**Symptom:** Java caller calls `gateway.preview(command, tenant, eventId, groupKey)`, yet the Service Activator or Router does not see `businessEventId` or `trustedTenantId`.

### Step 1 — Verify the Right Gateway Proxy

Check that the interface has `@MessagingGateway`, `@IntegrationComponentScan` scans the right package, and Spring registers the bean. Do not call a hand-written implementation class of the interface, as annotations do not automatically build Spring Messages on plain implementations.

### Step 2 — Compare Method Signatures

~~~java
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey);
~~~

Check whether annotations or header names changed during refactoring. If a `Map` is present, verify whether it is `@Payload Map` or `@Headers Map` with no ambiguous signature.

### Step 3 — Check Default/Method Headers

If a header comes from `@GatewayHeader`, check `name`, `value`, `expression`, and precedence. A method-specific header can override default/parameter headers in matching configurations. Avoid two sources owning the same header name.

### Step 4 — Inspect the Message Right After the Gateway

Use a test handler, wire tap, or endpoint instrumentation to inspect **which headers exist on the Spring Message** before any Transformer or adapter. Log only key names and redacted values; never log raw `replyChannel` or security tokens.

If `businessEventId` is already missing right after the Gateway, fix the mapping at the Gateway/facade. If present there yet lost downstream, move to Step 5.

### Step 5 — Find Transformers or `HeaderFilter`s Modifying the Message

If a Transformer only returns a payload, the framework generally propagates inbound headers per endpoint rules. If a handler constructs a new `Message`, check how selected headers are retained. A `HeaderFilter` may be stripping fields intentionally.

### Step 6 — Inspect Adapter Boundaries

Over HTTP/JMS/AMQP/TCP, a `HeaderMapper` may pass only a subset of headers or a serializer may send only the payload. Check outbound wire contracts and inbound mappings rather than expecting `@Header` to cross networks automatically.

### Step 7 — Check Types and Values

~~~text
Required Spring header:
  businessEventId: String "evt-quote-901"

Actual:
  X-Event-Id: List<String> ["evt-quote-901"]
~~~

These are **two different names and types**. Normalize at ingress or the adapter rather than letting domain handlers ad-hoc parse protocol-specific header shapes.

### Step 8 — Separate Header Errors from Reply Errors

If the Service Activator receives the right headers yet the Gateway still times out, inspect **`replyChannel`**, whether the handler returns a result, whether a Filter discards, or whether output went to a separate `QueueChannel`. Never tweak `businessCorrelationKey` to fix a broken `replyChannel`.

### Step 9 — Check Error Flow and Retries

A missing header is usually a schema, configuration, or authorization error; endlessly retrying the same input will not make the header appear. For transient DB/network errors, use bounded retries keeping the same logical identity.

### Step 10 — Verify After Fixing

A contract test should assert:

~~~text
@Payload QuoteCommand:
  shipmentId = SHIP-901
  serviceLevel = EXPRESS

Spring headers:
  trustedTenantId = tenant-a
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  gatewaySource = JAVA_APP
  operationKind = PREVIEW

Java return:
  QuoteReceipt for SHIP-901, 160000 VND
~~~

After the happy path, run negative tests: wrong tenant, group mismatch, missing header, two ambiguous `Map`s, timeout, and wire adapter mapping.

## 30. Practice Exercise: Gateway API for Order Processing

Build an `OrderProcessingGateway` with three operations:

1. **`validateOrder`:** validates data and returns `ValidationReceipt`.
2. **`reserveInventory`:** sends a reservation command and returns `ReservationReceipt`.
3. **`publishAudit`:** sends a one-way audit event.

All methods follow the same **typed payload + method arguments as headers** pattern, yet have distinct request/reply contracts.

### 30.1. Interface Sketch

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.GatewayHeader;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "orderCommands",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "ORDER_APP"))
interface OrderProcessingGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "VALIDATE"))
    ValidationReceipt validateOrder(
            @Payload OrderCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId);

    @Gateway(
            headers = @GatewayHeader(
                    name = "operationKind", value = "RESERVE"),
            replyTimeout = 3_000)
    ReservationReceipt reserveInventory(
            @Payload OrderCommand command,
            @Headers java.util.Map<String, Object> verifiedHeaders);

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "AUDIT"))
    void publishAudit(
            @Payload AuditEvent event,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId);
}
~~~

In this snippet, `OrderCommand`, `AuditEvent`, `ValidationReceipt`, and `ReservationReceipt` are **DTO placeholders** for learners to define themselves. You cannot paste the interface verbatim into a project without creating the corresponding DTOs, flows, and channels.

### 30.2. Metadata Contract

| Header | `validateOrder` | `reserveInventory` | `publishAudit` |
| --- | --- | --- | --- |
| `gatewaySource` | Fixed `ORDER_APP` | Fixed `ORDER_APP` | Fixed `ORDER_APP` |
| `operationKind` | `VALIDATE` | `RESERVE` | `AUDIT` |
| `trustedTenantId` | `@Header` argument | Verified `@Headers` `Map` | `@Header` argument |
| `businessEventId` | `@Header` argument | Verified `@Headers` `Map` | `@Header` argument |
| `businessCorrelationKey` | Per workflow needs | Required in verified `Map` | Per audit contract |
| `replyChannel` | Gateway runtime | Gateway runtime | One-way semantics |

**A facade must protect `reserveInventory`**: the `Map` must never come raw from an HTTP request, and inventory reservation requires a stable operation ID and idempotency. An inventory service timeout must never lead to assuming stock was not reserved.

### 30.3. Action Items

1. Define validated DTOs/enums for `OrderCommand` and `AuditEvent`.
2. Build an authenticated application context and authorize tenant/order access.
3. Define stable `businessEventId`/`operationId` and `businessCorrelationKey` per workflow.
4. Create the Gateway interface using `@MessagingGateway`, `@Gateway`, `@Payload`, `@Header`, and `@Headers`.
5. Build a Router on `operationKind` mapping cleanly to the three subflows.
6. `VALIDATE` subflow receives headers and returns `ValidationReceipt`.
7. `RESERVE` subflow receives headers, persists ledger/idempotency state, and returns `ReservationReceipt`.
8. `AUDIT` subflow sends one-way with an error policy without waiting for reservation results.
9. Add a negative route for unsupported `operationKind`.
10. Set bounded Gateway request/reply timeouts; distinguish timeouts from business deadlines.
11. Test header names, types, precedence, `Map` validation, and reply lifecycle.
12. Add tests for same `orderId` across different tenants, `eventId` replay, and `eventId` conflict.
13. Test a Transformer building a new `Message` that drops headers; fix using a trusted header strategy.
14. If external adapters exist, test wire header mapping and callback correlation.
15. Add tracing, monitoring, and DLQ/recovery for broker/async processing.

### 30.4. Test Matrix

| Case | Scenario | Expectation |
| --- | --- | --- |
| A | `VALIDATE` with all arguments | Message has expected payload and headers |
| B | `RESERVE` using verified `Map` | All keys mapped accurately |
| C | `AUDIT` `void` method | Does not wait for a Java business result |
| D | Missing `trustedTenantId` | Rejected without executing command |
| E | Empty or null `eventId` | Rejected/quarantined |
| F | Correlation mismatches tenant/order | Rejected per policy |
| G | `@GatewayHeader` and `@Header` share name | Precedence observed; design cleaned up |
| H | Two unannotated `Map`s | Ambiguous mapping rejected |
| I | Same `orderId` across two tenants | Two independent group identities |
| J | Retry `RESERVE` with same `operationId` | Does not create two reservations |
| K | `RESERVE` reply lost after commit | Reconcile instead of unconditionally re-reserving |
| L | Slow `DirectChannel` handler | `replyTimeout` not mistaken for hard execution deadline |
| M | `ExecutorChannel` switches thread | Context does not rely on `ThreadLocal` |
| N | Transformer drops `replyChannel` | Test catches broken reply path |
| O | Callback after Gateway timeout | Workflow handles late event per policy |
| P | JMS/AMQP header mapping uses different names | Adapter contract test catches mismatch |

### 30.5. Completion Criteria

Anyone reading the Gateway interface immediately knows:

- Where each operation's primary payload lives.
- Which headers come from `@Header` arguments.
- Which headers are statically configured via `@GatewayHeader`.
- Which headers come via `@Headers Map` and who validates it.
- Which methods expect a typed reply and which are one-way.
- Where correlation/event identity is generated and verified.
- How retry/idempotency handles side-effecting commands.

If you have to read the entire implementation to tell whether the second argument is a tenant or a secondary payload, the method signature is not explicit enough.

## 31. Self-Check Questions

1. How are Gateway method arguments converted into a Spring `Message`?
2. How do `@MessagingGateway` and `@Gateway` differ in role?
3. On a Gateway, which direction does `@Header("trustedTenantId") String tenantId` map?
4. On a Service Activator, which direction does `@Header("trustedTenantId") String tenantId` map?
5. With multiple arguments, why should `@Payload` be specified explicitly?
6. How is a method with a single unannotated `Map` argument interpreted?
7. What goes wrong if a method has two unannotated `Map` arguments?
8. How does `@Headers Map` differ from `@Payload Map`?
9. Can `@Payload` and `@Header` be placed on the same argument?
10. Can a Gateway method have two independent `@Payload` arguments?
11. How does `@GatewayHeader(name=..., value=...)` differ from `@Header` on a parameter?
12. How do `@MessagingGateway`'s `defaultHeaders` and `@Gateway`'s `headers` differ in scope?
13. If a default header and a parameter `@Header` share a name, which value may take precedence?
14. If a method-specific header and a parameter `@Header` collide, what should you do to avoid surprises?
15. What can the `method.name` header expression be used for?
16. Why should you never serialize a raw `java.lang.reflect.Method` object into a broker property?
17. When is `MethodArgsMessageMapper` needed instead of annotations?
18. Why should raw HTTP headers `Map` never go straight into Gateway `@Headers`?
19. Does passing `tenant-admin` via `@Header` automatically grant authorization?
20. How do `businessCorrelationKey` and a Gateway's temporary `replyChannel` differ?
21. Do `requestTimeout` and `replyTimeout` automatically interrupt a slow `DirectChannel` handler?
22. If a Service Activator sends replies to an unbridged `QueueChannel`, what will the caller experience?
23. Does a `void`-returning Gateway method prove external effects completed?
24. Why is Spring `MessageHeaders.ID` unsuitable as a `businessEventId` across retries?
25. Which headers can a Transformer drop if it constructs a new `Message`?
26. When should you use `MessageBuilder.fromMessage` instead of copying from a raw external message?
27. Why doesn't an Aggregator automatically group by `businessCorrelationKey` just because the Gateway attached that header?
28. Must a Splitter's technical `correlationId` match the business correlation key?
29. When a Gateway calls a JMS/AMQP outbound gateway, which correlation identities must be kept distinct?
30. Why is testing the Gateway proxy better than only unit testing the handler directly for mapping checks?
31. What negative tests prevent tenant/group spoofing?
32. When an event is redelivered, which identities must stay fixed and which may change?
33. When a reply times out after a provider created a reservation, is blind retrying allowed?
34. If a Gateway expression relies on `args[2]`, what bug can changing parameter order introduce?
35. Which headers belong to application metadata and which belong solely to framework runtime?
36. Which steps help investigate when Gateway mapping works yet an HTTP/JMS adapter loses headers?

## 32. Checklist Before Deploying Gateway Header Mapping

- Gateway interface carries `@MessagingGateway` and is registered via `@IntegrationComponentScan` or equivalent proxy config.
- Every method's `requestChannel`/`defaultRequestChannel` has an accurate owner and consumer.
- Payload argument is explicitly marked with `@Payload` on multi-argument signatures.
- Per-invocation headers use `@Header` with clear, consistent names.
- Dynamic header sets use `@Headers Map` only after validation/allowlisting.
- A single `Map` acting as the body is explicitly annotated with `@Payload`.
- No method has two payload arguments or an argument marked both `@Payload` and `@Header`/`@Headers`.
- Interface-wide static headers use `defaultHeaders`; method-level static headers use `@Gateway(headers=...)`.
- SpEL header expressions are tested and do not depend on fragile argument positions.
- No header name collides across default/method/parameter unless precedence is explicitly contracted and tested.
- Never treat protocol header names (e.g., `X-Tenant-Id`) as Spring trusted headers without mapping and verification.
- Business identity derives from authenticated principal, tenant, entity, and workflow epoch.
- `eventId`/`operationId` remain stable across attempts of the same logical work.
- `businessCorrelationKey` has a clear namespace/version and stays consistent across the flow.
- Never use `MessageHeaders.ID`, `traceId`, or `replyChannel` as a business idempotency key.
- Never pass arbitrary control headers like `replyChannel`, `errorChannel`, or `routingSlip` through external `Map`s.
- Gateway method return type matches its contract: typed reply or `void` one-way.
- Request/reply flows preserve a reply path to the Gateway-managed temporary channel.
- `requestTimeout`/`replyTimeout` fit channel semantics and are not confused with business deadlines.
- Downstream Routers use an `operationKind` allowlist instead of raw client-supplied destination names.
- Transformers/handlers have a strategy to preserve required trusted headers.
- If Splitter/Aggregator are present, technical sequence/correlation is scoped apart from business keys.
- `HeaderMapper` and `MessageConverter` on every HTTP/JMS/AMQP/TCP adapter have contract tests.
- External callbacks rely on persisted correlation rather than expired temporary `replyChannel`s.
- `DirectChannel`/`ExecutorChannel`/`QueueChannel` semantics are verified with bounded backpressure.
- Missing/invalid headers are rejected before causing side effects.
- Error channel/DLQ/quarantine semantics align with sync/async behavior, retries, and retention.
- Retries separate permanent schema/auth failures from transient infrastructure errors.
- Side effects use a ledger/transaction/idempotency key with crash recovery.
- Unit tests verify business handlers with simulated header `Map`s.
- Spring context integration tests invoke the real Gateway proxy and assert replies reflect mapped header values.
- Negative tests cover wrong correlation, missing headers, wrong types, ambiguous `Map`s, header precedence, and tenant spoofing.
- Tests cover multiple tenants with the same `shipmentId` and retries with the same `eventId` to avoid false joins and duplicate effects.
- Logs/metrics separate mapping, send, handler, reply, and adapter errors without leaking secrets/PII.
- A runbook exists to trace missing headers from caller → proxy → `Message` → subflow → adapter → reply.

## 33. Summary

**Gateway header mapping from method arguments** turns ordinary Java APIs into Spring `Message`s with **explicit payloads and headers**:

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

~~~text
Java call arguments
  | @Payload -> Message.payload
  | @Header  -> individual Message.headers
  | @Headers -> multiple Message.headers from Map
  | @GatewayHeader -> static/SpEL-defined headers
  v
Request channel
  -> Router / Transformer / Service Activator
  -> reply / error
  -> Java method return
~~~

The value of this design lies in a **clear contract between caller and flow**: the application never builds `Message`s manually for each call, while downstream reads consistent headers. Nevertheless, annotations only map **data**; they do not verify **authorization**, invent a **correlation strategy**, guarantee a **reply path**, or provide **exactly-once side effects**.

In Spring Integration flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, and error channels, pair a **verified facade + typed `@Payload`/`@Header` + Gateway/Service Activator contract tests + persistent idempotency**. That keeps tenant, `eventId`, and business correlation flowing accurately across branches without leaking control headers or corrupting workflows across timeouts, retries, or message redeliveries.

## References

- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): pattern hiding the Messaging API from business applications.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `GatewayProxyFactoryBean`, `@MessagingGateway`, `@Gateway`, mapping method arguments, header expressions, reply channels, timeouts, and error handling.
- [Spring Integration API — @Gateway](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html): method-level request/reply settings, header configuration, and payload expression.
- [Spring Integration API — @GatewayHeader](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/GatewayHeader.html): `name`, `value`, and `expression` for static/dynamic headers.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): `@EnableIntegration`, endpoint annotations, and `IntegrationComponentScan`.
- [Spring Framework API — @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html): naming a header for a method argument.
- [Spring Framework API — @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html): mapping `Map` headers.
- [Spring Framework API — @Payload](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): payload selection and SpEL.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, handler lambdas, and channel wiring.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): mapping from `Message` to Java handler methods and replies.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): Header Value Router, metadata-based routing, and default routes.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transformation and header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): technical correlation and sequence headers.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation strategy, release strategy, and group timeouts.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, `QueueChannel`, and dispatch semantics.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`/`errorChannel` and sync/async errors.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): deduplication and limitations of idempotency advice.
