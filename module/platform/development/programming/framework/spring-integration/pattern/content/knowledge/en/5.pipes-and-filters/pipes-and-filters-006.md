# Placing Validation Close to the Data Entry Point

In a **Pipes and Filters** architecture, data flows through a chain of independent steps: each *filter* receives a message, performs one responsibility, and passes the result through a *pipe* to the next step. With **Spring Integration**, pipes are typically `MessageChannel` beans, while processing steps can be `Filter`, `Transformer`, `Router`, `Service Activator`, or other endpoints.

An important principle when designing such a chain is **placing validation close to where data enters the system or crosses a trust boundary**. Invalid data should be caught at the start of the flow before consuming resources on expensive steps or causing business side effects such as writing to a database, calling an API, sending an email, or updating state.

This lesson belongs to the **Pipes and filters** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channels, and correlation, as well as testing and observing processing branches. Here, validation is treated as part of the message contract and flow organization, not merely a few `if` statements.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why data should be validated early, immediately after intake and proper decoding.
2. Distinguish **syntactic**, **structural/schema**, **semantic**, **business rule**, and **access control** validation from downstream checks.
3. Choose the right Spring Integration tool: `Filter` to accept/reject, `Transformer` to normalize, `Router` to branch, and exception/error flows to report errors.
4. Use Jakarta Bean Validation inside an endpoint and handle rejected messages via `discardChannel`.
5. Preserve metadata such as `tenantId`, `traceId`, and `correlationId` as messages pass through validation.
6. Test the success path, rejection path, parse failures, and verify that invalid data never reaches handlers with side effects.
7. Build a strategy for observability, error classification, and safe retries.

## 2. What Does Validation Near the Entry Point Mean?

An order processing flow may begin from an HTTP Gateway, an AMQP/Kafka inbound adapter, JMS, a file polling adapter, or an in-application `MessagingGateway`. Regardless of source, incoming data must pass through a series of boundaries:

~~~mermaid
flowchart LR
    SRC["HTTP / MQ / File / Gateway"] --> LIMIT["Size limit + parse"]
    LIMIT --> STRUCT["Schema / data type check"]
    STRUCT --> VALID["Input validation"]
    VALID -->|Valid| NORM["Transformer: normalize"]
    NORM --> ROUTE{"Router"}
    ROUTE --> A["Handler A"]
    ROUTE --> B["Handler B"]
    VALID -->|Invalid| REJECT["Reject / discard channel"]
    LIMIT -->|Parse error| ERROR["Error response / error flow"]
    STRUCT -->|Failed| ERROR
~~~

Placing validation near the entry point **does not mean every check must run before every transformation**. For instance, JSON text must be parsed into a DTO before annotations like `@NotBlank` or `@DecimalMin` can be applied. A sensible pipeline usually looks like:

1. **Admission / resource limits:** enforce request body limits, message size limits, timeouts, and accepted formats; avoid reading unbounded data.
2. **Decode / parse:** convert bytes or JSON into a typed representation; parse failures stop at the intake boundary.
3. **Structural validation:** check required fields, types, length limits, and code formats.
4. **Trust / access validation:** determine trusted origin and permissions of the caller, tenant, channel, or principal; do not trust headers that clients can spoof.
5. **Normalize:** standardize strings, timezones, region codes, or units; clearly define whether normalization precedes or follows each validation check.
6. **Semantic validation:** check cross-field relationships, value ranges, and logical conditions without calling external systems.
7. **Routing / business processing:** send valid data to the needed branches; additional business checks depending on current state may still apply there.

**Principle:** check as close to the source as possible for invariants verifiable there; re-verify whenever a message crosses a **new trust boundary** or requires confirming a business condition that did not exist at intake.

### 2.1. Why Validate Early?

| If Validated Early | If Detected Late |
|---|---|
| Downstream handlers receive a consistent data structure | Every handler must guess types or duplicate logic |
| Stops before DB writes or expensive API calls | Discovered after hard-to-undo side effects occurred |
| Specific error feedback to the sender | Errors surface far from the source, hard to root-cause |
| Fewer code paths forced to handle malformed data | Every branch needs extra invalid-data cases |
| Rejected message rate can be measured separately | Bad data mixes into business/infrastructure errors |

However, do not push state-dependent queries—such as “is current balance sufficient?”—into ingress if they require transactional consistency at write time. Those checks should run again at the business boundary with an appropriate transaction.

## 3. Classifying Validation Layers

Suppose the system receives an order placement command:

~~~json
{
  "orderId": "order-1001",
  "amount": 120.50,
  "region": "north",
  "customerEmail": "buyer@example.com"
}
~~~

Responsibilities can be separated as follows:

| Layer | Example Check | Appropriate Location | Failure Handling |
|---|---|---|---|
| Resource limits | Body exceeds limit; excessively nested structure | Adapter / HTTP server / decoder | Reject before entering the flow |
| Syntax | Malformed JSON, unparseable number | Decoder / message converter | Parse error; return appropriate response |
| Schema / structure | Missing `orderId`, `amount` not a number | DTO binding / Bean Validation | Reject message per contract |
| Value / format | Non-positive `amount`, unlisted `region` | Validator near entry point | Reject or report validation error |
| Security / trust origin | Caller not authorized for this tenant | Boundary authentication / authorization | Deny, audit appropriately |
| Cross-field semantics | `deliveryDate` before `createdAt` | Pure data validator | Reject |
| State-dependent business rules | Sufficient inventory; order status allows edits | Business handler / transaction | Business rejection with reason |
| External system conditions | Does partner API accept the request? | Integration adapter / outbound | Integration error, controlled retry, or compensation |

`@Email` can check the **syntactic shape** of an email, not prove the mailbox exists or belongs to the user. Likewise, `@DecimalMin("0.01")` checks the numeric range at validation time, not the validity of a payment transaction.

## 4. Defining the Message Contract at the Entry Point

Between two components, establish a clear contract covering **payload**, **headers**, and **errors**.

Example:

~~~text
input channel: orders.received
payload: OrderRequest
headers:
  traceId: String?            # for observability, may be generated internally
  tenantId: String            # attached from authenticated context
  sourceSystem: String?       # originating source if verified
success output: orders.accepted
rejected output: orders.rejected
parse/exception error: error flow or adapter/gateway response
~~~

The `?` in the example above indicates an optional field; this is a documentation convention, not Java syntax.

**Never treat client-supplied headers as proof of authentication.** For example, a client sending `tenantId=shop-admin` does not mean the caller is allowed to process data for that tenant. The inbound adapter or security layer must verify the principal and authorized tenant, then pass only trusted information into internal processing.

### 4.1. Message ID and Correlation

- `MessageHeaders.ID` is the ID of a single message instance; a newly constructed message may receive a new ID.
- `traceId` tracks steps across the flow; it may be managed by tracing infrastructure or generated by the application per contract.
- `correlationId` / `businessCorrelationId` links multiple messages belonging to the same business workflow or Splitter/Aggregator group.
- `errorChannel` and `replyChannel` are headers governing error and reply paths in their respective flows.

Validation must preserve required metadata on **both the success branch and the rejection branch** so the system can explain which message from which source was rejected. When rejecting, you can store an error code and selected safe fields, while avoiding logging full payloads containing personal data or secrets.

## 5. Representing Input Data with DTOs and Jakarta Bean Validation

In Java 17+ systems using Spring Framework 6 / Spring Boot 3+, Jakarta Bean Validation uses the `jakarta.validation.*` namespace. An implementation library (such as Hibernate Validator) must be on the classpath; with Spring Boot, typically add the appropriate validation starter.

An illustrative DTO:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record OrderRequest(
        @NotBlank
        @Size(max = 64)
        String orderId,

        @NotNull
        @DecimalMin("0.01")
        BigDecimal amount,

        @NotBlank
        @Size(max = 24)
        String region,

        @NotBlank
        @Email
        String customerEmail
) {}
~~~

Explanation:

- `@NotBlank` rejects `null`, empty strings, or whitespace-only strings.
- `@Size(max=...)` bounds representation length, but **does not replace transport-level request size limits**.
- `@NotNull` and `@DecimalMin` guard monetary fields; `BigDecimal` is preferable to `double` for many financial use cases.
- `@Email` checks email syntax; stricter domain policies may be needed depending on the application.
- `record` provides a convenient payload definition without setters. If a record contains mutable collections or objects, defensive copies are still needed where appropriate.

Constraint annotations are only **the first part**. If business rules only allow `NORTH` or `SOUTH`, define the order of normalizing `region` and then validate against an enum or allowed values. Do not allow arbitrary strings just because they are non-blank.

### 5.1. Do Not Create a `ValidatorFactory` per Message

In Spring, use a lifecycle-managed `Validator` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean orderValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

`LocalValidatorFactoryBean` implements Jakarta's `Validator` interface and is suitable for injection into components. Never call `Validation.buildDefaultValidatorFactory()` repeatedly on every message handler invocation because factory setup carries overhead and resource lifecycle costs.

## 6. Blocking Invalid Messages with a Filter

`Filter` is the right choice when a step only asks **“may this message proceed?”**. A method annotated with `@Filter` can receive the payload and return a `boolean`:

~~~java
import jakarta.validation.Validator;

import org.springframework.integration.annotation.Filter;

public class OrderAdmissionFilter {

    private final Validator validator;

    public OrderAdmissionFilter(Validator validator) {
        this.validator = validator;
    }

    @Filter(
            inputChannel = "orders.received",
            outputChannel = "orders.accepted",
            discardChannel = "orders.rejected")
    public boolean accept(OrderRequest request) {
        return validator.validate(request).isEmpty();
    }
}
~~~

Once this class is registered as a Spring bean and Spring Integration annotation processing is enabled:

- `true`: the input message is forwarded to `orders.accepted`.
- `false`: the message is rejected and sent to `orders.rejected` via `discardChannel`.
- There is no need to manually construct a new message for the success or rejection branch in this example.

**Important:** `Filter` forwards the **received message** as-is and does not transform the payload into another DTO. To modify or normalize the payload, use a `Transformer` before or after the Filter depending on the contract.

### 6.1. Why Is a `discardChannel` Necessary?

By default, a Filter can **drop rejected messages** if no discard channel is configured and exception throwing on rejection is disabled. A payment/order flow should not silently discard critical data with no way to explain what happened to the sender.

~~~mermaid
flowchart LR
    A["orders.received"] --> F{"Filter: constraints OK?"}
    F -->|true| V["orders.accepted"]
    F -->|false| X["orders.rejected"]
    V --> H["Business processing"]
    X --> D["Audit / reject response / dead-letter policy"]
~~~

The rejection branch can log under control, increment metrics, build an error response, or route to a dead-letter destination per system policy. If you need to return a **field-level list of errors**, a simple `boolean` method does not carry reasons along; build a `ValidationResult` structure, use a validator returning detailed results, or propagate errors via exceptions/error flows as shown next.

### 6.2. `throwExceptionOnRejection` Has Different Semantics from Discard

You can set `throwExceptionOnRejection = "true"` in `@Filter` or the equivalent in DSL/config. When the Filter rejects:

- Default `throwExceptionOnRejection=false`: the message is discarded or sent to the discard channel if configured.
- When `true`: the Filter throws `MessageRejectedException`; if a discard channel is also configured, per `MessageFilter` behavior, the message may still be sent to the discard channel **and then** the exception is thrown.
- In synchronous flows, the exception can propagate back to the caller; in asynchronous flows, it follows the error handling mechanism configured on the channel/endpoint.

Do not enable both discard and throw together merely thinking it is “safer”; doing so can cause a single rejection to leave **two processing trails** (both discard branch and exception), risking double-counting or duplicate responses.

## 7. When Validation Needs Detailed Error Reporting Instead of a Boolean

There are two distinct needs:

1. **Intentional message filtering**: e.g., an event type outside the scope of interest—Filter with discard is natural.
2. **Reporting input contract violations**: e.g., an invalid monetary field in a request that must be validated—you should return a meaningful error to the caller or route into a validation error flow.

In the second case, validation can sit inside an endpoint that blocks propagation on error. For example, using a Transformer that returns the original payload when valid:

~~~java
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;

import org.springframework.integration.annotation.Transformer;

public class StrictOrderValidator {

    private final Validator validator;

    public StrictOrderValidator(Validator validator) {
        this.validator = validator;
    }

    @Transformer(
            inputChannel = "orders.parsed",
            outputChannel = "orders.checked")
    public OrderRequest requireValid(OrderRequest request) {
        var violations = validator.validate(request);

        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        return request;
    }
}
~~~

This class must be registered as a Spring bean. When invalid, the transformer throws an exception; **no message** reaches `orders.checked`. When valid, the transformer returns the payload and the framework builds the output message, typically propagating input headers per configuration.

**Do not `return null` from a Transformer to drop a message:** a Spring Integration Transformer expects a valid result and can throw `MessageTransformationException` if `null` is returned. If the intent is filtering, use a Filter; if the intent is reporting an error, throw a controlled exception.

### 7.1. Notes on Exceptions

In real flows, an exception from a transformer may be wrapped in a `MessagingException` or an endpoint-specific exception. When handling errors, inspect the **cause chain** to distinguish `ConstraintViolationException` from system failures rather than matching only the outermost exception class.

You do not need to expose every `ConstraintViolation` detail externally. Violation lists can contain sensitive property names or rejected values; at the API boundary, map them to safe error codes/field names and return only what the client needs.

### 7.2. An Alternative Model: `ValidationResult`

If the system needs to record errors without using exceptions for control flow, return an explicit result structure:

~~~java
import java.util.List;

public record ValidationIssue(
        String field,
        String code
) {}

public record ValidationResult<T>(
        T value,
        List<ValidationIssue> issues
) {
    public boolean valid() {
        return issues.isEmpty();
    }
}
~~~

A pure data validation step returns `ValidationResult<OrderRequest>`, and a Router picks the `accepted` or `rejected` branch based on `valid()`. Both branches can observe structured errors, making metrics and API responses straightforward. The trade-off is that downstream consumers must understand the new contract, or a Transformer must unwrap back to the business payload after the accepted branch.

## 8. Configuring a Pipes and Filters Chain with Java DSL

The Java DSL can express a chain directly: receive the message, filter, normalize, and pass to the next step.

~~~java
import java.util.Locale;

import jakarta.validation.Validator;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderIngressFlowConfiguration {

    @Bean
    IntegrationFlow orderIngressFlow(Validator validator) {
        return IntegrationFlow.from("orders.received")
                .filter(OrderRequest.class,
                        req -> validator.validate(req).isEmpty(),
                        endpoint -> endpoint
                                .discardChannel("orders.rejected"))
                .transform(OrderRequest.class, req ->
                        new OrderRequest(
                                req.orderId().trim(),
                                req.amount(),
                                req.region().trim()
                                        .toUpperCase(Locale.ROOT),
                                req.customerEmail().trim()))
                .channel("orders.normalized")
                .get();
    }
}
~~~

This assumes `OrderRequest` was successfully decoded before entering `orders.received` and string fields passed `@NotBlank`, making them non-null at the transform step. This configuration illustrates **two separate responsibilities**: the Filter checks the input contract, and the Transformer produces the normalized payload. If the contract permits surrounding whitespace and validation must run on canonicalized values, place a **safe, meaning-preserving** Transformer before the Filter; clarify which original data is still retained for audit.

Ordering choices are not merely cosmetic:

- **Validate then normalize:** fits when the raw input format must strictly conform to the contract (e.g., uppercase required as sent).
- **Normalize then validate:** fits when input allows equivalent representations (e.g., `" north "` and `"NORTH"`), provided normalization does not mask bad data.
- **Validate → normalize → re-validate selected invariants:** fits when normalization can alter string length, numeric range, or validity.

### 8.1. Do Not Equate a Filter with Security Controls

A message-processing `Filter` is only one step inside an integration flow; it does not replace authentication, authorization, rate limiting, or input size limits at the HTTP/Kafka/AMQP boundary. For instance, checking whether a user may read an order usually requires an authenticated security context; authorization must execute before side effects and wherever data could be accessed.

## 9. Placing Validation Near Boundaries and Keeping Business Logic in Place

“Near the data entry point” should be understood in terms of **trust boundaries**, not solely the very first step after an API.

~~~mermaid
flowchart TB
    A["External HTTP request"] --> A1["Limits / parse / validate / authorize"]
    A1 --> B["Internal message flow"]
    B --> C["Business transaction: check current state"]
    C --> D["Outbound adapter"]
    D --> E["External partner response"]
    E --> E1["Parse and validate response"]
    E1 --> F["Continue business flow"]
~~~

Examples:

- HTTP ingress must validate untrusted requests.
- A payment service must still enforce business rules inside its transaction, even though the DTO was already validated.
- When receiving a response from an external service, **validate the response at that new boundary**; validating the initial request does not mean returned data can be blindly trusted.
- For events read from a broker, consumers should minimally validate the message contract/version, especially when multiple producers may evolve schemas.
- For messages created by a Splitter, verify per-item invariants before corresponding side effects, even if the parent message was validated at ingress.

A “validated” message does not guarantee all future decisions stay valid forever. Inventory, permissions, and transaction status can change after ingress validation finishes.

## 10. Headers, Correlation, and Preserving Diagnostic Context

Placing validation early helps catch errors sooner, but it is only helpful if you can trace the message and why it was rejected.

Example message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderRequest> input = MessageBuilder
        .withPayload(new OrderRequest(
                "order-1001",
                new java.math.BigDecimal("120.50"),
                "north",
                "buyer@example.com"))
        .setHeader("traceId", "trace-1001")
        .setHeader("tenantId", "shop-a") // assumed attached by internal auth layer
        .setHeader("businessCorrelationId", "order-1001")
        .build();
~~~

When a Filter routes a message to `orders.accepted` or `orders.rejected`, downstream components can still read its headers. If you manually construct a new **Message** inside a Transformer to normalize or create a `ValidationResult`, explicitly carry over permitted headers:

~~~java
Message<OrderRequest> normalized = MessageBuilder
        .withPayload(new OrderRequest(
                input.getPayload().orderId().trim(),
                input.getPayload().amount(),
                input.getPayload().region().trim().toUpperCase(),
                input.getPayload().customerEmail().trim()))
        .setHeader("traceId",
                input.getHeaders().get("traceId"))
        .setHeader("businessCorrelationId",
                input.getHeaders().get("businessCorrelationId"))
        .build();
~~~

In Spring Integration, a Transformer returning a **payload** and a Transformer returning a **complete Message** follow different header propagation rules. Returning a payload lets the framework build the message and copy eligible headers; returning a `Message` means your code explicitly defines the output message. Therefore, whenever changing how validation/normalization endpoints are written, test metadata propagation specifically.

**Never use message `id` as a business correlation key** across retries or transformations; message IDs can change whenever a new message is constructed. Also, never place secrets, tokens, or full personal data into `headers` merely to simplify logging.

## 11. Distinguishing Rejects, Data Errors, and System Failures

A complete flow must explicitly define its failure paths.

| Situation | Example | Typical Handling | Should It Auto-Retry? |
|---|---|---|---|
| Parse failure | JSON missing a brace | Bad request / error event | No, unless data changes |
| Validation reject | `amount=0` | Discard/reject channel or 4xx response for HTTP | No |
| Authorization reject | Unauthorized tenant | Deny + security audit | No, unless context legitimately changes |
| Domain conflict | Order already cancelled, cannot pay | Business error | Per contract; usually no blind retry |
| Transient infrastructure | DB timeout, gateway 503 | Bounded retry, backoff, circuit breaker | Possibly, if idempotent |
| Programmer error | NPE in code | Error flow, investigate, alert | Will not self-heal via infinite retry |

Note: HTTP statuses like `400` or `422` are **HTTP adapter/API conventions**, not automatic results of a `Filter`. Likewise, `discardChannel` does not automatically write to a broker or dead-letter queue; it simply routes messages along the topology you configure.

### 11.1. A Filter Rejection Does Not Necessarily Make `send()` Fail

In default mode, a Filter can reject a message while the send call at the head of the flow is still considered delivered to the endpoint. Thus, **`send() == true` does not mean the order was accepted by business logic**. If a Gateway/API must return an explicit rejection outcome, design a dedicated reply/error path rather than inferring success from `MessageChannel.send()`'s boolean return value.

### 11.2. Error Channels Work Differently from Discard Channels

- **Discard channel:** receives messages intentionally rejected by a Filter's selection/filtering decision.
- **Error channel:** receives messaging/handler failures, especially in asynchronous flows or via configured error-handling mechanisms.
- **Exception in a synchronous flow:** may be thrown back to the caller thread; merely declaring an error channel does not mean every synchronous exception automatically routes there.
- **Rejected event:** an application-generated business event with error codes/explanations, suitable when domain-level rejection handling is needed.

Pick the right branch based on semantics, then test the actual topology. When writing structured error logs, record a code like `VALIDATION_FAILED`, message type, source, and correlation ID; avoid logging entire raw payloads.

## 12. Evolving and Extending Validation Contracts

When multiple producers and consumers exist, schemas change over time:

- Adding an **optional** field with a clear default causes far less disruption than changing a required field's type.
- You can use `schemaVersion` or a schema registry to route validation per version.
- Do not blindly accept arbitrary unknown fields when security requires allowlisting; unknown-field rules depend on format and converter settings.
- Test compatibility between v1/v2 producers and consumer validators at boundaries.
- Never turn a permanent version mismatch into infinite retries; route to quarantine/reject with enough metadata to replay after contracts are updated.

For example, if v2 requires `currency` while v1 lacks it: apply an approved policy default, convert in a controlled manner, or route v1 to a separate flow. Never guess currency from `amount`.

## 13. Validation and Performance Under High Load

Early validation saves work on messages dropped early, but validation itself consumes CPU and memory. Several guidelines:

1. Bound **byte size and parse complexity** before allocating large DTOs.
2. Share a single managed validator bean instead of instantiating factories per message.
3. Separate fast pure-data checks from I/O checks; put DB or API lookups in steps with proper timeouts/caching and transactions.
4. Avoid re-running the same expensive validation in every handler when steps share a single trust boundary and contract integrity is preserved.
5. After crossing a new system/source boundary, re-validate the parts of the contract that must be trusted there.
6. Track metrics such as `accepted_count`, `validation_reject_count`, `decode_failure_count`, `error_count`, and per-stage latency, while avoiding high-cardinality user IDs as metric labels.
7. If the pipeline is async, bound concurrency and queue sizes; validation neither creates backpressure nor guarantees delivery.

In secure systems, rejecting an oversized request **before parsing** is a necessary complement to Bean Validation. `@Size(max=64)` on `orderId` cannot protect a server while a 100 MB request body is being read into memory.

## 14. Integration Testing Across Real Channels

There are two distinct testing layers:

- **Validator unit test:** checks the constraint rules for a specific `OrderRequest`.
- **Flow integration test:** sends a `Message<OrderRequest>` through `orders.received`, verifying valid messages reach `orders.accepted`, invalid messages reach `orders.rejected`, headers are preserved, and downstream business branches receive no bad data.

The test below demonstrates a complete example with Java 17+, JUnit Jupiter 5, Spring Integration, and Spring Test. It requires no HTTP server startup.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@SpringJUnitConfig(classes = OrderIngressValidationTest.Config.class)
class OrderIngressValidationTest {

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("orders.received")
        DirectChannel received() {
            return new DirectChannel();
        }

        @Bean("orders.accepted")
        QueueChannel accepted() {
            return new QueueChannel();
        }

        @Bean("orders.rejected")
        QueueChannel rejected() {
            return new QueueChannel();
        }

        @Bean
        LocalValidatorFactoryBean validator() {
            return new LocalValidatorFactoryBean();
        }

        @Bean
        Gate gate(Validator validator) {
            return new Gate(validator);
        }
    }

    static class Gate {
        private final Validator validator;

        Gate(Validator validator) {
            this.validator = validator;
        }

        @Filter(
                inputChannel = "orders.received",
                outputChannel = "orders.accepted",
                discardChannel = "orders.rejected")
        public boolean allow(OrderRequest payload) {
            return validator.validate(payload).isEmpty();
        }
    }

    @Autowired
    @Qualifier("orders.received")
    MessageChannel received;

    @Autowired
    @Qualifier("orders.accepted")
    PollableChannel accepted;

    @Autowired
    @Qualifier("orders.rejected")
    PollableChannel rejected;

    @Test
    void validOrderReachesAcceptedChannel() {
        OrderRequest input = new OrderRequest(
                "order-1001",
                new BigDecimal("120.50"),
                "NORTH",
                "buyer@example.com");

        assertTrue(received.send(
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1001")
                        .build()));

        Message<?> output = accepted.receive(1000);
        assertNotNull(output);
        assertEquals(input, output.getPayload());
        assertEquals("trace-1001", output.getHeaders().get("traceId"));
        assertNull(rejected.receive(0));
    }

    @Test
    void invalidOrderGoesToRejectChannel() {
        OrderRequest input = new OrderRequest(
                "order-1002",
                BigDecimal.ZERO,
                "NORTH",
                "buyer@example.com");

        received.send(
                MessageBuilder.withPayload(input)
                        .setHeader("traceId", "trace-1002")
                        .build());

        Message<?> discarded = rejected.receive(1000);
        assertNotNull(discarded);
        assertEquals(input, discarded.getPayload());
        assertEquals("trace-1002",
                discarded.getHeaders().get("traceId"));
        assertNull(accepted.receive(0));
    }
}
~~~

Here, `OrderRequest` is the record defined in Section 5, and `@Filter` receives the decoded payload and uses `jakarta.validation.Validator`. The `QueueChannel` beans are used **for testing** to observe output; in a real application, the accepted channel connects to business endpoints and the rejected channel has its own handling endpoints.

Expected results:

| Input | `orders.accepted` | `orders.rejected` |
|---|---|---|
| `amount=120.50` | One message | None |
| `amount=0` | None | One message |
| `orderId="   "` | None | One message |
| Unparseable JSON | Never reaches Filter due to decode failure | Handled by adapter/converter error flow |

**Note:** this test verifies Filter branching, not HTTP statuses or broker infrastructure. To prove invalid data causes no side effects, attach a handler downstream of `orders.accepted` backed by a counter or fake repository and assert it is never invoked when a message is rejected.

### 14.1. Testing the Standalone Validator

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import jakarta.validation.Validator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

// Can reuse Config from the previous test.
@SpringJUnitConfig(classes = OrderIngressValidationTest.Config.class)
class OrderRequestValidatorTest {

    @Autowired
    Validator validator;

    @Test
    void zeroAmountIsInvalid() {
        OrderRequest order = new OrderRequest(
                "order-1002",
                BigDecimal.ZERO,
                "NORTH",
                "buyer@example.com");

        var violations = validator.validate(order);

        assertFalse(violations.isEmpty());
        assertTrue(violations.stream().anyMatch(v ->
                "amount".equals(v.getPropertyPath().toString())));
    }
}
~~~

Validator unit tests show **why** a payload is invalid, while flow tests show **where** it gets routed. Both test levels complement each other.

### 14.2. Testing Additional Error Paths

In an environment with real Gateways and adapters, also test:

- Parser throws an error on invalid JSON; no downstream DB writes occur.
- A client-supplied `tenantId` header cannot override the authenticated tenant.
- A message with an unsupported schema version routes to reject/quarantine.
- Exceptions from validation endpoints are handled properly in both synchronous and asynchronous configurations.
- `traceId` is present across accepted, rejected, and error flows per policy.
- Retries do not loop indefinitely on permanent data errors; transient errors are bounded and idempotent.
- Oversized payloads are rejected before allocating large object graphs.

## 15. Real-World Scenario: Receiving Events from Multiple Sources

An ordering system receives `OrderCreated` via both REST and Kafka. Although decoded payloads can map to the same `OrderRequest`, the two sources have different trust boundaries.

~~~mermaid
flowchart TB
    H["HTTP adapter"] --> HV["Size / auth / parse / validate"]
    K["Kafka inbound"] --> KV["Schema / producer trust / parse / validate"]
    HV --> N["Normalized internal OrderRequest"]
    KV --> N
    N --> C["MessageChannel: orders.ready"]
    C --> R{"Router: region"}
    R --> A["Order handler NORTH"]
    R --> B["Order handler SOUTH"]
    A --> DB["Transactional business write"]
    B --> DB
    HV -->|reject| RJ["API error response"]
    KV -->|reject| Q["Quarantine / dead-letter policy"]
~~~

Key differences:

- REST usually has a **caller waiting for a response**. When validation fails, the API adapter can return an explicit error such as HTTP 400 or 422 per contract.
- A Kafka consumer cannot “return HTTP 400” to a producer. It must manage ack/offset, dead-letter topics, quarantine, and replay according to consumer/broker policy.
- A permanent parse error must not retry forever and block the partition.
- When both sources merge into an internal flow, the normalized payload must follow a consistent contract, while authentication and permissions must be interpreted appropriately for each source.
- Before side effects, business handlers must still verify current state and maintain transactional integrity.

A common pattern is separating **adapter-specific validation** (HTTP, broker) from **common application validation** (DTO/invariants) and joining them at an internal channel. This preserves independence between communication frameworks and business logic.

## 16. Common Pitfalls

### 16.1. Placing Validation After Side Effects

**Symptom:** database writes or emails already ran before the system noticed `amount` was invalid.

**Fix:** move parsing/structural validation immediately after ingress; check transaction-dependent business invariants before writing state.

### 16.2. Using a Transformer Returning `null` to Filter

**Symptom:** the Transformer returns `null`, the endpoint throws an exception, and the message is not filtered as expected.

**Fix:** use a `Filter` with `discardChannel` for normal rejection behavior; throw an exception if input violates a contract that must report an error.

### 16.3. Filter Rejects Without Anyone Observing

**Symptom:** some orders vanish before downstream steps while producers believe sending succeeded.

**Fix:** define a rejected channel, metrics, and how callers receive outcomes; test rejection routing. Never infer business processing success from `MessageChannel.send() == true`.

### 16.4. Treating All Errors as Retryable

**Symptom:** a message with `amount=-1` is retried hundreds of times, clogging the queue.

**Fix:** classify permanent data errors, business errors, and transient errors; only retry failures likely to recover, with backoff and max attempts.

### 16.5. Using Validation as a Substitute for Authorization

**Symptom:** payload has a properly formatted `tenantId` belonging to a different tenant, causing handlers to access the wrong data.

**Fix:** verify principal/tenant from a trusted context and enforce permissions before side effects and inside necessary transactions.

### 16.6. Blindly Copying All Headers

**Symptom:** sensitive metadata or stale payload-version headers leak into an inappropriate branch.

**Fix:** define a header contract, apply an allowlist at new trust boundaries, and verify header propagation when Transformers return full `Message` objects.

### 16.7. Duplicate Validation and Mutable Data Dependencies

**Symptom:** three handlers run identical validations yet behave differently because the payload was mutated during asynchronous processing.

**Fix:** normalize and validate in a shared step before fan-out, emit immutable payloads or defensive copies, and only re-check context-dependent invariants inside each consumer.

## 17. Practice Exercises

**Exercise 1 — Basic admission filter.** Create `OrderRequest` with constraints as in Section 5, configuring input channel `orders.received`, output `orders.accepted`, and discard `orders.rejected`. Send three messages: valid, missing `orderId`, and `amount=0`. Assert the path taken by each message.

**Exercise 2 — Validation result with error codes.** Replace boolean returns with a `ValidationResult` structure. Attach stable error codes `ORDER_ID_REQUIRED`, `AMOUNT_TOO_SMALL`, and `REGION_UNSUPPORTED`. Route branches based on `valid()`. Try adding a new field and ensure legacy clients do not receive sensitive data in responses.

**Exercise 3 — Parse error vs. validation reject.** Send one malformed JSON string and one syntactically valid JSON string missing `amount`. Identify the code responsible for each error and demonstrate observable outputs. Do not treat a parse failure as a Filter reject if the message was never decoded into `OrderRequest`.

**Exercise 4 — Correlation and tracing.** Attach `traceId` to both valid and rejected messages, and assert it survives across endpoints. If a Transformer returns a complete `Message`, write a test proving it does not automatically keep uncopied headers.

**Exercise 5 — Asynchronous system.** Place an `ExecutorChannel` after validation. Test one message with a permanent error and one transient failure in another handler; configure retries for the second failure, count execution attempts, and explain the exception path. Ensure validation rejections are not pointlessly retried.

**Exercise 6 — Testing trust boundaries.** Simulate a client-sent `tenantId` header differing from the tenant derived from an authenticated principal. Prove the flow does not use the client-supplied value for access decisions. Add a branch receiving a partner response and validate the response before updating the DB.

### Self-Check Questions

1. Why should validation be placed before Routers and handlers with side effects?
2. At which stage do JSON parse errors and Bean Validation failures differ?
3. When is a Filter with a discard channel preferable to throwing an exception?
4. If a Filter returns `false` with no discard configured, how does the system observe rejected messages?
5. When is ingress validation insufficient to guarantee business invariants?
6. Why does a well-formatted `tenantId` not imply the caller is authorized?
7. If a Transformer returns `Message<?>` without copying headers, what can happen to tracing and correlation?
8. Why is retrying an `amount=-1` error counterproductive?
9. What must be tested to confirm rejected messages never touch the database?
10. If a Kafka consumer receives an unsupported schema, what metadata should a quarantine/replay path retain?

## 18. Adoption Checklist

- [ ] Trust boundaries and payload/header contracts are defined at every intake point.
- [ ] Size limits and timeouts exist in adapters/decoders before parsing.
- [ ] DTOs have appropriate null, type, length, and range validations.
- [ ] Validation/normalization sits before expensive work and unnecessary side effects.
- [ ] Filter is used for accept/reject decisions; Transformer for payload conversions; errors are classified separately.
- [ ] Rejected messages have a defined handling path and metrics rather than being silently dropped.
- [ ] Authorization relies on trusted context, never self-declared external headers.
- [ ] State-dependent business invariants are checked within appropriate transactions.
- [ ] Trace/correlation headers and permitted metadata are preserved across validation and rejection.
- [ ] Retries apply only to recoverable errors, with idempotency and attempt limits.
- [ ] Accepted, rejected, parse failure, authorization failure, and error flows are all tested.
- [ ] For Kafka/JMS/HTTP sources, ack, reply, dead-letter, or quarantine behaviors are explicitly defined.
- [ ] Monitoring tracks rejection and error rates without leaking sensitive data.

## 19. Summary

**Placing validation close to the data entry point** keeps a Pipes and Filters flow's contract clear from the start: valid messages proceed to business steps, while invalid messages are classified and handled at the right point. In Spring Integration, `Filter` fits accept/reject decisions, `Transformer` produces consistent data representations, `Router` directs branches, and exceptions/error flows serve cases requiring error reporting.

The core principle is placing **the right kind of check at the right boundary**. Enforce resource limits and parse before DTOs, validate structure/semantics early, authenticate permissions from trusted sources, and keep state-dependent business invariants close to their transactions. Measure rejection branches, preserve appropriate trace/correlation metadata, and test both success and failure behaviors. Doing so enables Router, Filter, Transformer, Splitter/Aggregator, Gateway, retry, and error channels to work together in a flow that is loosely coupled, observable, and easy to extend.

### References

- Spring Integration Reference — Message Filter: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference — Transformer: https://docs.spring.io/spring-integration/reference/transformer.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration Reference — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Framework Reference — Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Jakarta Bean Validation specification: https://jakarta.ee/specifications/bean-validation/
