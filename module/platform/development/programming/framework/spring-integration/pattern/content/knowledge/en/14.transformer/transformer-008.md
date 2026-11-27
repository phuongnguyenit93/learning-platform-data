# A Transformer Can Throw Exceptions

## 1. Context: Data Transformation Does Not Always Succeed

In the **Transformer** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn how to implement Enterprise Integration Patterns with **Spring Integration** to create loosely coupled, extensible, and testable message flows. A Transformer converts a message's content so subsequent steps can process it under a clear contract. It typically precedes a Router, Filter, Splitter, Aggregator, or Gateway because those components rely on stable payload structures and data types.

Example order ingestion flow:

~~~mermaid
flowchart LR
    P["HTTP / Broker"] --> I["rawOrdersChannel"]
    I --> T["Order Transformer"]
    T -->|"Valid"| N["validatedOrdersChannel"]
    N --> R["Content-Based Router"]
    R --> A["Standard fulfillment"]
    R --> B["Manual review"]
    T -.->|"Failed"| E["Error handling / quarantine"]
~~~

Inbound inputs may contain:

- Malformed monetary amounts, such as **abc** instead of a number.
- Missing country codes, blank order IDs, or negative amounts.
- Syntactically broken JSON, incompatible schemaVersion, or unexpected data types.
- Oversized data that exceeds parser limits.
- Programming bugs: NullPointerException, invalid casts, or unchecked invariants.
- I/O errors if a Transformer is designed to call external services.

In such cases, a Transformer **can throw an exception**. The right reaction depends on whether the failure occurs on a **synchronous or asynchronous thread**, whether **retry** is appropriate, and whether the message should be **rejected, quarantined, or reprocessed**.

**Lesson Objectives**

1. Understand a Transformer's contract: turn one input into one valid output without silently returning null.
2. Distinguish conversion errors, business contract violations, and transient system failures.
3. Structure exceptions in a pure Java Transformer and let Spring Integration orchestrate failures.
4. Distinguish exceptions propagating directly through **DirectChannel** from **ErrorMessage** in asynchronous paths.
5. Configure appropriate error channels, quarantine, retry, and idempotency.
6. Write unit tests and integration tests verifying failures, logging, correlation, and impact on downstream branches.

## 2. What Contract Does a Transformer Have?

A Transformer receives a Spring Message containing **payload** and **headers**, and produces a new payload or Message. A Transformer may change:

- **Data types**: JSON String → OrderCreated.
- **Format**: XML → JSON, byte[] → object.
- **Content**: raw input values → normalized DTO.
- **Headers**: stripping or adding appropriate metadata.

Model:

~~~text
Message<RawOrder> --transform--> Message<ValidatedOrder>
~~~

A Transformer should own **transforming the shape or semantics of data**, not every other duty in the pipeline. If you only want to **keep or drop a message** by condition, use a **Message Filter**. If you want to execute business side effects with no reply, consider a **Service Activator**.

### 2.1. A Transformer Must Never Return `null`

According to official Spring Integration documentation, **since version 2.0, Transformers are not allowed to return null**. A transformation method returning null raises a **MessageTransformationException** because a Transformer is always expected to produce a valid result. A Transformer's **requiresReply** property is always true and must not be disabled to turn it into a Filter.

**Anti-pattern:**

~~~java
// Wrong: null does not mean "skip message" in a Transformer.
String transform(String input) {
    if (input.isBlank()) {
        return null;
    }
    return input.trim();
}
~~~

**Correct if blank data is an error:**

~~~java
String transform(String input) {
    if (input == null || input.isBlank()) {
        throw new IllegalArgumentException("EMPTY_INPUT");
    }
    return input.trim();
}
~~~

**Correct if blank data should be dropped per policy:**

~~~java
// A separate Filter decides which messages may proceed.
@Bean
IntegrationFlow filterThenTransform() {
    return IntegrationFlow.from("textInputChannel")
            .filter(String.class, value -> !value.isBlank())
            .transform(String.class, String::trim)
            .channel("normalizedTextChannel")
            .get();
}
~~~

This example requires declaring both channels and an appropriate consumer. Decide how Filter-discarded messages are handled: silently dropped, sent to a discard channel, or reported as errors. **Never equate Filter discard with Transformer failure.**

### 2.2. A Transformer Error Differs from a Filter Rejection

| Event | Responsible Component | Expected Behavior |
| --- | --- | --- |
| Valid, convertible input | Transformer | Return normalized payload/Message |
| Contract-violating input that must be rejected | Validation/Transformer | Throw a classified error |
| Input allowed to be skipped | Filter | Discard per policy |
| One-way handler with no reply | Service Activator | May return null when requiresReply=false |
| Transformer returns null | Transformer | Framework raises transformation error |
| Output created, downstream fails | Downstream Router/handler | Handle downstream error; do not mislabel as parse failure |

### 2.3. Transformation Errors and Downstream Errors Can Look Alike

If a single `send()` call fails, the root cause is not guaranteed to be inside the Transformer. For example:

1. Transformer successfully converts RawOrder to ValidatedOrder.
2. Router picks manualReviewChannel.
3. The manualReviewChannel handler throws an exception.

The exception can unwind straight to the caller on the same thread. If logs only state **send failed**, operators cannot tell whether the error occurred in **transform** or **review**. Therefore, attach clear component IDs, error categories, eventId, schemaVersion, and trace context.

## 3. Classify Errors Before Choosing Retry

| Error Category | Example | Does Retrying Same Input Help? | Starting Handling Approach |
| --- | --- | --- | --- |
| **Malformed input** | Broken JSON, non-numeric amount | Usually no | Reject or quarantine |
| **Validation failure** | Missing order ID, negative amount | Usually no | Return coded error, log safely |
| **Unsupported schema** | Unsupported schemaVersion | No, until consumer upgrades | Quarantine, route to owner |
| **Conversion bug** | NPE or ClassCastException from code | Usually no | Fail fast, alert, fix code |
| **Resource limit** | Payload exceeds size limit | No if data stays unchanged | Reject per limit |
| **Transient infrastructure** | Schema lookup service timeout | Possibly, if lookup is idempotent | Bounded retry with backoff |
| **Downstream failure** | DB insert fails after Transformer | Not a Transformer error | Retry/error flow on that branch |

**Principle:** a deterministic parse error on the same input will not become valid after 100 retries. Conversely, transient network failures can recover, though separating I/O out of the Transformer is preferable when possible.

### 3.1. Explicit Error Contract

Every error should answer:

- What is the **stable error code**? E.g., INVALID_AMOUNT, INVALID_COUNTRY, UNSUPPORTED_VERSION.
- Is the error **non-retryable** for the same input?
- Must the input be **retained for replay** after fixing data or upgrading versions?
- Which caller receives the error and through what channel?
- Which eventId/correlation identifies it for investigation?
- Does the payload contain sensitive info that must be stripped from exceptions and logs?

Never write code that catches **Exception** and returns a fake default payload like a zero-value order. That turns bad input into **seemingly valid business data**, pushing failures downstream and breaking traceability.

## 4. A Pure Java, Easily Testable Transformer

Suppose an external caller sends a payload like:

~~~json
{
  "orderId": "ORD-103",
  "amountVnd": "15000000",
  "destinationCountry": "SG"
}
~~~

We want to convert it into stronger types with a **BigDecimal** amount, normalized country code, and validated data.

### 4.1. Input and Output DTOs

~~~java
import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String amountVnd,
        String destinationCountry) {}

record ValidatedOrder(
        String orderId,
        BigDecimal amountVnd,
        String destinationCountry) {}
~~~

**RawOrder** reflects unvalidated data. **ValidatedOrder** reflects minimum preconditions that downstream can trust under the **internal contract**, not proof that the sender is authorized to access the order.

### 4.2. Business Exception with Classification Code

~~~java
final class InvalidOrderException extends RuntimeException {
    private final String errorCode;

    InvalidOrderException(String errorCode) {
        super(errorCode);
        this.errorCode = errorCode;
    }

    String errorCode() {
        return errorCode;
    }
}
~~~

The exception holds only the **error code**, not full card numbers, emails, or payloads. Detailed diagnostics, if required, should be written per logging policy in access-controlled stores; avoid putting sensitive data into exception messages sent over error channels.

### 4.3. Pure Java Transformer

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderNormalizationTransformer {

    ValidatedOrder transform(RawOrder raw) {
        if (raw == null) {
            throw new InvalidOrderException("MISSING_ORDER");
        }
        String id = raw.orderId();
        if (id == null || !id.matches("ORD-[A-Za-z0-9-]{1,32}")) {
            throw new InvalidOrderException("INVALID_ORDER_ID");
        }

        String rawAmount = raw.amountVnd();
        if (rawAmount == null || rawAmount.isBlank()) {
            throw new InvalidOrderException("MISSING_AMOUNT");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(rawAmount.trim());
        } catch (NumberFormatException ex) {
            throw new InvalidOrderException("INVALID_AMOUNT_FORMAT");
        }

        // VND units in this example use positive integer amounts only.
        if (amount.signum() <= 0
                || amount.stripTrailingZeros().scale() > 0) {
            throw new InvalidOrderException("INVALID_AMOUNT_VALUE");
        }

        String country = raw.destinationCountry();
        if (country == null || !country.trim()
                .matches("[A-Za-z]{2}")) {
            throw new InvalidOrderException("INVALID_COUNTRY");
        }

        return new ValidatedOrder(
                id,
                amount,
                country.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

**Strong properties of this Transformer:**

1. **No side effects:** writes no DB rows, sends no HTTP requests, emits no events.
2. **Deterministic:** identical valid input produces identical output (under the same contract).
3. **Fail fast:** invalid input raises an error before downstream executes transactions.
4. **Type-safe:** downstream receives ValidatedOrder rather than re-parsing amountVnd.
5. **Easy to unit test:** no Spring startup needed to verify logic.

In production, add payload size limits, maximum amount bounds, allowlisted country codes, schemaVersion, and proper internationalization rules. A two-letter regex checks **syntax only**, not whether a code is a business-valid country.

### 4.4. Avoid Attaching I/O to the Same Method Unless Necessary

~~~java
// This makes the Transformer hard to predict and hard to retry:
ValidatedOrder transform(RawOrder raw) {
    ValidatedOrder parsed = parser.transform(raw);
    riskClient.enrichFromRemoteService(parsed.orderId());
    return parsed;
}
~~~

This snippet is an **architectural anti-pattern**; `parser` and `riskClient` are hypothetical dependencies. Whenever possible, split them:

~~~text
RawOrder
  -> Normalize Transformer
  -> Risk Enricher (dedicated timeout/retry/circuit breaker)
  -> Content-Based Router
~~~

That way **invalid input** errors are not retried like network errors, and risk-service failures are not misreported as parse failures.

## 5. Wiring the Transformer into a Synchronous `IntegrationFlow`

Spring Integration Java DSL provides the **transform** method to pass data through a handler. The configuration below declares three DirectChannels: input, normalized output, and a downstream endpoint after completion. Its goal is to illustrate where exceptions surface.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderTransformationConfig {

    @Bean
    OrderNormalizationTransformer orderTransformer() {
        return new OrderNormalizationTransformer();
    }

    @Bean
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validatedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderNormalizationFlow(
            OrderNormalizationTransformer transformer) {
        return IntegrationFlow.from("rawOrdersChannel")
                .transform(RawOrder.class, transformer::transform)
                .channel("validatedOrdersChannel")
                .get();
    }
}
~~~

**Reading the flow:**

1. A message carrying **RawOrder** arrives on rawOrdersChannel.
2. Transformer invokes **OrderNormalizationTransformer.transform**.
3. If it returns ValidatedOrder, the framework sends the output message to **validatedOrdersChannel**.
4. If the method throws InvalidOrderException, transformation fails; the message **does not proceed down the success branch**.
5. validatedOrdersChannel needs a subscriber or downstream IntegrationFlow. Without a consumer, dispatch can fail **after transformation already succeeded**.

Example consumer using a business port:

~~~java
interface ValidatedOrderPort {
    void accept(ValidatedOrder order);
}

// Placed inside the @Configuration class above:
@Bean
IntegrationFlow acceptedOrderFlow(ValidatedOrderPort port) {
    return IntegrationFlow.from("validatedOrdersChannel")
            .handle(ValidatedOrder.class, (order, headers) -> {
                port.accept(order);
                return null; // One-way Service Activator ends here.
            })
            .get();
}
~~~

Do not confuse a **terminal handler returning null** with a **Transformer returning null**: in a one-way Service Activator, returning null can be a valid completion when no reply is expected; a Transformer must always produce a result.

### 5.1. Producer and the Synchronous Error Path

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

RawOrder raw = new RawOrder(
        "ORD-103", "abc", "SG");

// rawOrdersChannel is an injected MessageChannel bean.
rawOrdersChannel.send(
        MessageBuilder.withPayload(raw).build());
~~~

In this configuration, **rawOrdersChannel is a DirectChannel**, so the Transformer runs on **the thread calling `send()`**. Because `amountVnd` is `"abc"`, the transformation method throws. The framework may wrap the exception in **MessageTransformationException/MessagingException**, whose root cause is `InvalidOrderException`.

**Do not write tests tightly coupled to a single wrapper class** unless you control framework versions and endpoint types; verify the **root cause**, the failing component, and that the output receives no message.

### 5.2. An Exception Does Not Automatically Send an `ErrorMessage`

This distinction is critical:

- With a **synchronous DirectChannel**, errors normally unwind on the call stack back to the sender. They are **not published by default** to the global errorChannel.
- With a Spring Integration–managed **TaskExecutor/poller**, errors can be **wrapped in an ErrorMessage** and sent to an errorChannel per configuration.

If you want synchronous errors routed into a message-based error flow instead of throwing back to the caller, place an explicit gateway/error-handling boundary or recovery advice. Merely declaring a bean named `errorChannel` **does not alter** DirectChannel's synchronous behavior.

## 6. Error Handling: DirectChannel and ExecutorChannel Differ

### 6.1. Comparing Paths

~~~mermaid
flowchart TD
    A["Caller / Producer"] --> D{"MessageChannel"}
    D -->|"DirectChannel"| T["Transformer on same thread"]
    D -->|"ExecutorChannel"| X["TaskExecutor picks up work"]
    X --> TA["Transformer on worker"]
    T -->|"Exception"| C["Error back to caller"]
    TA -->|"Exception"| EM["ErrorMessage"]
    EM --> EC["errorChannel header or global errorChannel"]
~~~

| Mechanism | Who Runs Transformer? | Can Caller Catch Error Directly? | How Does `ErrorMessage` Work? |
| --- | --- | --- | --- |
| **DirectChannel** | Message-sending thread | Usually yes | Does not publish errors by default |
| **ExecutorChannel** | TaskExecutor thread | Normally no, after dispatch | MessagePublishingErrorHandler can emit ErrorMessage |
| **QueueChannel + poller** | Poller thread | Not the earlier sending caller | Poller/error handler can emit ErrorMessage |
| **Inbound Gateway sync** | Depends on flow and gateway | Can return error to caller | Gateway can be configured with an error channel |
| **Broker adapter** | Depends on consumer container/adapter | Original caller is rarely on the same call stack | Ack/requeue/error handling per adapter |

**Not every Executor automatically produces an `ErrorMessage`.** Error publishing depends on Spring Integration task infrastructure, executors, pollers, error handlers, and versions. For work dispatched onto application-managed threads, do not assume they automatically use Spring Integration's global errorChannel.

### 6.2. What Does `ErrorMessage` Contain?

In Spring Integration's message-oriented error model, **ErrorMessage** is a Spring Message whose payload is a **Throwable**. That payload may be a MessagingException referencing `failedMessage`; an ErrorMessage may also carry **originalMessage**, depending on the failure type and error-creation strategy.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

void inspectError(Message<?> incoming) {
    if (!(incoming instanceof ErrorMessage errorMessage)) {
        throw new IllegalArgumentException("Expected ErrorMessage");
    }

    Throwable failure = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    // Use failure to classify the error.
    // original may be null; never assume the original payload is always present.
}
~~~

**Never unconditionally log the entire Throwable and originalMessage** when payloads carry sensitive data. Exception messages, stack traces, and headers can expose tokens, addresses, PII, or transaction secrets. Log an **errorCode**, **componentId**, trusted **eventId**, and appropriate trace ID; record details only under access control.

### 6.3. Global `errorChannel` vs. `errorChannel` Header

When an asynchronous error-handling component sends an ErrorMessage, Spring Integration typically resolves the destination in order:

1. Request message's **errorChannel header**, if present and valid.
2. **Global errorChannel** created by Spring Integration or supplied by the application.

The default global errorChannel is a **PublishSubscribeChannel**, typically subscribed to by a LoggingHandler. That does not mean failed messages are durably persisted, retried, or moved to a DLQ automatically.

~~~text
Input Message
  headers:
    businessCorrelationId: ORD-103
    errorChannel: orderTransformationErrors
~~~

**Security:** never take `errorChannel` directly from a client-supplied HTTP header and trust it as an internal channel name. Control values like this must be created or verified at the trust boundary, since they dictate where error details are routed.

## 7. Creating an Async Boundary and Dedicated Error Channel

Goal: send `RawOrder` to an **ExecutorChannel** so the Transformer executes on a worker thread. When transformation fails, route the error to the header-configured channel; never equate `send()` returning `true` with transformation success.

### 7.1. Bounded Executor Configuration

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncOrderTransformationConfig {

    @Bean
    ThreadPoolTaskExecutor normalizationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("normalize-");
        return executor;
    }

    @Bean
    MessageChannel asyncOrderInputChannel(
            @Qualifier("normalizationExecutor")
            ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    MessageChannel normalizedOrderOutputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel orderTransformationErrors() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow asyncOrderTransformFlow(
            OrderNormalizationTransformer transformer) {
        return IntegrationFlow.from("asyncOrderInputChannel")
                .transform(RawOrder.class, transformer::transform)
                .channel("normalizedOrderOutputChannel")
                .get();
    }
}
~~~

This example requires `@EnableIntegration` in the application context (or equivalent Spring Boot Spring Integration auto-configuration), the **OrderNormalizationTransformer** bean, and consumers on both output and error channels. `ThreadPoolTaskExecutor` has its lifecycle managed by Spring when declared as a `@Bean`.

`ExecutorChannel` establishes an **async boundary**; when queued tasks exceed capacity, dispatch can be rejected. That is an admission/backpressure failure requiring different handling from `InvalidOrderException` inside the Transformer. Never grow queues infinitely just to hide congestion.

### 7.2. Producer Selecting a Trusted Error Channel

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

RawOrder raw = new RawOrder(
        "ORD-109", "not-a-number", "VN");

Message<RawOrder> message = MessageBuilder.withPayload(raw)
        .setHeader("eventId", "evt-109")
        .setHeader("businessCorrelationId", raw.orderId())
        .setHeader(
                MessageHeaders.ERROR_CHANNEL,
                "orderTransformationErrors")
        .build();

// asyncOrderInputChannel bean is injected.
boolean submitted = asyncOrderInputChannel.send(message);
~~~

**submitted=true** means the send operation was accepted per `ExecutorChannel` semantics—it **does not** mean the Transformer succeeded. The failure `ErrorMessage` may arrive **after** `send()` returns.

At ingress, `eventId` and `errorChannel` must be assigned by trusted internal code, never copied unchecked from clients. With brokers, verify how `errorChannel` propagates across adapters; you may need to configure the inbound endpoint's error channel directly rather than relying on a wire header.

### 7.3. Error Consumer and Root-Cause Classification

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

interface InvalidOrderPort {
    void recordFailure(
            String errorCode,
            String eventId,
            String component);
}

@Bean
IntegrationFlow transformErrorFlow(InvalidOrderPort errors) {
    return IntegrationFlow.from("orderTransformationErrors")
            .handle(message -> {
                if (!(message instanceof ErrorMessage error)) {
                    throw new IllegalArgumentException(
                            "Expected ErrorMessage");
                }

                Throwable failure = error.getPayload();
                Throwable current = failure;
                while (current.getCause() != null
                        && current.getCause() != current) {
                    current = current.getCause();
                }

                String code = current instanceof InvalidOrderException invalid
                        ? invalid.errorCode()
                        : "UNEXPECTED_TRANSFORMATION_FAILURE";

                String eventId = "UNKNOWN";
                if (failure instanceof MessagingException messaging
                        && messaging.getFailedMessage() != null) {
                    Object candidate = messaging.getFailedMessage()
                            .getHeaders().get("eventId");
                    if (candidate instanceof String valid) {
                        eventId = valid;
                    }
                }

                errors.recordFailure(
                        code, eventId, "orderNormalizationTransformer");
            })
            .get();
}
~~~

Place this configuration fragment in the `@Configuration` class defining the corresponding channels. **InvalidOrderPort** is implemented by the application to quarantine/log with proper permissions and retention. In production code, also inspect `originalMessage` if `failedMessage` is absent, and handle the case where neither exists.

**Do not inspect root cause only to retry everything.** A parse error cannot heal itself. Conversely, an I/O error from an enrichment step may need bounded retries on that exact step.

If the error handler itself throws an exception, `ErrorMessage` handling also fails. Monitor error-path failures, persist durably where required, and prevent cycles routing `errorChannel` back into the same failing flow.

## 8. Retrying a Transformer: When Helpful vs. Dangerous?

A **pure Java** Transformer performing parsing, validation, and normalization should almost always be deterministic. With unchanged input, an `INVALID_AMOUNT_FORMAT` error will repeat identically. Retrying it three times only adds load and delays flagging the invalid message.

In some cases, a real-world Transformer interacts with another system: reading schemas from a registry, converting via an external service, or fetching supplementary data. Then you must distinguish:

- **Permanent failures**: invalid data, unsupported schemas, bugs.
- **Transient failures**: timeouts, dropped connections, temporary registry outages.
- **Ambiguous outcomes**: an outbound request may have executed side effects, yet the response was lost.

### 8.1. Policy Matrix

| Error | Retry Same Input? | Appropriate Handling Point |
| --- | --- | --- |
| INVALID_ORDER_ID | No | Return error/quarantine |
| INVALID_AMOUNT_FORMAT | No | Return error/quarantine |
| UNSUPPORTED_SCHEMA_VERSION | Not before upgrading consumer | Quarantine for replay after upgrade |
| Code NullPointerException | Do not loop infinitely | Fail fast, alert, fix bug |
| Schema Registry timeout | Possibly, bounded | Dedicated enrichment/lookup step |
| Database connection timeout | Possibly | DB endpoint with dedicated transaction/retry |
| HTTP provider timeout after side-effecting call | Only if idempotent or reconciled | Gateway/service adapter with stable key |

**Separating errors by cause** keeps retries from causing queue backlogs or duplicate side effects.

### 8.2. `RequestHandlerRetryAdvice`

Spring Integration provides **RequestHandlerRetryAdvice** to retry a handler/endpoint. Attached to **the specific recoverable Transformer or enrichment step**, it retries selected errors per policy. You can configure a `RecoveryCallback`, such as **ErrorMessageSendingRecoverer**, to emit the final failure as an `ErrorMessage` once retries are exhausted.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.messaging.MessageChannel;

// Use only for recoverable errors and suitable adapters.
@Bean
RequestHandlerRetryAdvice transientLookupRetry(
        MessageChannel transientLookupRecoveryChannel) {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(
                    transientLookupRecoveryChannel));
    return advice;
}
~~~

This configures the **advice** component, not a complete flow. To take effect, attach it to the target endpoint via DSL `endpointConfigurer` or `adviceChain`. Choose retry attempts/backoff and recovery policy according to your **Spring Integration/Spring Retry versions**. Never attach retry advice across an entire flow if re-running Router/Aggregator/Gateway would replay branches with side effects.

**Important caveat:** default retry counts and backoffs vary by API and version; never rely on defaults when business SLAs impose strict bounds. Configure them explicitly, test invocation counts, and measure wait times.

### 8.3. Stateless Retry vs. Stateful Redelivery

| Mode | Who Performs Next Attempt? | Consequence |
| --- | --- | --- |
| **Stateless retry in advice** | Endpoint retries immediately in-process | Holds thread/waits for backoff; can increase latency |
| **Stateful retry/redelivery** | Source such as JMS/Kafka/broker redelivers | Needs stable keys, ack/requeue, and proper state stores |
| **Manual replay from quarantine** | Operator/job replays after fixing issue | Needs schemaVersion, eventId, idempotency, and audit trail |

Never configure unbounded retries. Add backoff, jitter where appropriate, attempt caps, failure metrics, and DLQ/quarantine routing when unrecoverable.

## 9. Idempotency: Pure vs. Side-Effecting Transformers

### 9.1. Pure Transformers

A normalization like `RawOrder → ValidatedOrder` can be recomputed without altering external state. If a message repeats due to broker redelivery, **re-running pure normalization** causes no duplicate side effects.

Still, remember:

- The Transformer may construct a **new Message**, with a different `MessageHeaders.ID`.
- Steps **after the Transformer** may write to databases, send emails, or charge payments.
- Producing an identical normalized payload does not guarantee downstream processed it only once.

Therefore, business `eventId` must remain stable across redeliveries rather than generating a fresh `eventId` inside the Transformer.

### 9.2. Side-Effecting Transformers

**It is discouraged** to use a Transformer to update databases or call external APIs, because retries risk duplication. If unavoidable, every side effect needs an **idempotency key, transaction, or reconciliation check** like a full business endpoint.

Dangerous example:

~~~java
ValidatedOrder transform(RawOrder raw) {
    ValidatedOrder order = parser.transform(raw);
    stockClient.reserve(order.orderId()); // Side effect.
    return order;
}
~~~

If `stockClient.reserve` succeeds and the handler fails while sending the reply, retrying can reserve inventory twice. A cleaner design:

~~~text
RawOrder
  -> OrderNormalizationTransformer (pure)
  -> InventoryReservation Service Activator
     (idempotencyKey = eventId + ":reserve-inventory")
  -> Fulfillment Router
~~~

**Never use `MessageHeaders.ID` as a default business idempotency key.** When a Transformer creates a new message or an adapter serializes/reconstructs it, the technical ID can differ between retry attempts.

### 9.3. `ErrorMessage` Is Not a Durable DLQ

When a Transformer fails, sending an `ErrorMessage` to `errorChannel` **does not guarantee** the data is persisted for recovery across restarts. If the contract requires replay:

1. Persist **eventId**, error category, schemaVersion, and necessary payload to durable storage/broker.
2. Protect sensitive data and enforce retention policies.
3. Track status such as **pending-review**, **replayable**, **rejected**, or **completed**.
4. Replay only after fixing data, adding converters, or restoring infrastructure.
5. Ensure side-effecting downstream branches handle duplicates safely.

A channel named **deadLetterChannel** does not create dead-letter semantics by itself. You must configure real consumers, storage, retry/ack handling, and operations.

## 10. Message Headers and Correlation When a Transformer Throws

Spring Integration can preserve/propagate headers during transformation depending on whether payload or Message is returned and on the endpoint type. Verify explicitly **which fields travel from input to output**.

| Header | Meaning | Requirement During Transformation |
| --- | --- | --- |
| **eventId** | Stable logical event identifier | Preserve or assign at trust boundary before transform |
| **businessCorrelationId** | Links related order/payment messages | Do not alter arbitrarily on error |
| **traceId / tracing context** | Distributed flow observability | Keep context compatible with adapters |
| **replyChannel** | Gateway return path | Do not accidentally strip during request/reply |
| **errorChannel** | ErrorMessage routing path | Retain only values from trusted sources |
| **sequenceNumber / sequenceSize** | Splitter/Aggregator grouping | Never mutate when reassembly is needed |
| **schemaVersion** | Payload contract version | Verify support before converting |

### 10.1. Client-Supplied Headers Can Be Spoofed

When receiving messages from HTTP or untrusted brokers, never copy raw **replyChannel**, **errorChannel**, **routingSlip**, **tenantId**, **role**, or **trustedRoute** straight into internal messages. Those values can hijack message routing and business authorization.

Build internal messages from validated payloads and **allowlisted metadata**, setting tenant from a verified principal. If a Transformer builds a new message, test header propagation to confirm unwanted values cannot reach downstream.

### 10.2. Never Put Raw Payloads into Exceptions

With malformed JSON, a dangerous habit is throwing an exception containing the entire input:

~~~java
// Avoid: raw input may contain personal data or secrets.
throw new IllegalArgumentException("Invalid JSON: " + rawBody);
~~~

Use error codes, bounded reasons, and sanitized failure positions instead. If raw payloads must be saved to quarantine, encrypt them and enforce access control and retention policies. An error channel with multiple subscribers could broadcast raw payloads to unauthorized consumers.

## 11. Coordinating Transformer, Filter, Router, and Gateway for Error Handling

Do not overload a single Transformer with every business decision. A clear separation of responsibilities:

~~~mermaid
flowchart LR
    I["Ingress"] --> V["Schema validation"]
    V --> T["Pure Transformer"]
    T --> F{"Message Filter"}
    F -->|"Valid to process"| R{"Content-Based Router"}
    R --> S["Standard handler"]
    R --> M["Manual review"]
    T -.->|"Exception"| E["Error handling"]
    F -->|"Discard per policy"| D["Discard handler"]
    S -.->|"Downstream error"| X["Service error handler"]
~~~

**Separation of responsibilities:**

- **Transformer**: converts inbound data to a contracted format; throws when unable to convert.
- **Filter**: decides whether a message continues; discarding is a policy outcome, not an automatic failure.
- **Router**: picks a channel from valid data; unmapped keys can go to a fallback.
- **Gateway**: submits requests into the flow and optionally awaits replies; needs explicit timeouts and error contracts.
- **Retry**: applied on the specific endpoint with recoverable failures.
- **Error channel**: carries failure info in configured contexts; does not heal data or imply retries automatically.
- **Correlation**: tracks a logical event; does not guarantee exactly-once side effects.

### 11.1. Request/Reply Communication on Parse Failures

If an API must return HTTP 400 for invalid input, validate at the controller before sending the message or configure a gateway/error flow translating `InvalidOrderException` into a business response. **Never treat a Transformer exception as a successful response payload** unless the contract explicitly defines it.

If the pipeline is asynchronous and the HTTP endpoint already returned 202 Accepted, it typically cannot retroactively switch to 400 once a worker fails. Define an **accepted for processing** contract with a status/error notification mechanism later.

### 11.2. Combining with Splitter/Aggregator

A Transformer sitting between a Splitter and an Aggregator receives child messages carrying **correlationId**, **sequenceNumber**, and **sequenceSize**. If one child message fails transformation, the Aggregator may **receive an incomplete group**, leading to timeouts or stalled groups.

Business-dependent solutions:

- Throw and mark the entire group failed.
- Emit a structured **failure result** into an aggregation branch, if the Aggregator is explicitly designed for partial results.
- Retry that specific child message on transient failures.
- Configure release strategies, group timeouts, message stores, and incomplete-group handling.

**Never alter `sequenceSize` arbitrarily to make the Aggregator "complete,"** as that hides unprocessed data. An `ErrorMessage` and a business failure result are distinct message types; if sharing an aggregator, define an explicit contract.

## 12. Unit Testing a Pure Java Transformer

Before starting a Spring context, test the transform function like a normal Java method. Use **JUnit 5** to cover both happy paths and every coded failure.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderNormalizationTransformerTest {
    private final OrderNormalizationTransformer transformer =
            new OrderNormalizationTransformer();

    @Test
    void normalizesValidOrder() {
        ValidatedOrder result = transformer.transform(
                new RawOrder("ORD-103", "15000000", "sg"));

        assertEquals("ORD-103", result.orderId());
        assertEquals(new BigDecimal("15000000"), result.amountVnd());
        assertEquals("SG", result.destinationCountry());
    }

    @Test
    void rejectsMalformedAmountWithStableErrorCode() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-103", "abc", "SG")));

        assertEquals("INVALID_AMOUNT_FORMAT", error.errorCode());
    }

    @Test
    void rejectsNegativeAndFractionalVnd() {
        InvalidOrderException negative = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-104", "-10", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", negative.errorCode());

        InvalidOrderException fractional = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-105", "12.5", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", fractional.errorCode());
    }

    @Test
    void rejectsInvalidCountryWithoutLeakingRawPayload() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(
                        new RawOrder("ORD-106", "12000", "UNKNOWN")));
        assertEquals("INVALID_COUNTRY", error.errorCode());
    }

    @Test
    void rejectsMissingOrder() {
        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> transformer.transform(null));
        assertEquals("MISSING_ORDER", error.errorCode());
    }
}
~~~

Unit tests do not prove Spring Integration wired channels or routed `ErrorMessage` correctly. Integration tests are needed for that.

## 13. Integration Test with `DirectChannel`: Error Reaches Caller

Use `QueueChannel` as a **test-only output** to poll messages immediately with `receive(0)`. No dummy subscriber or `Thread.sleep` is needed.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(SynchronousTransformerTest.Config.class)
class SynchronousTransformerTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        OrderNormalizationTransformer transformer() {
            return new OrderNormalizationTransformer();
        }

        @Bean
        MessageChannel testInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel testOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow testTransformFlow(
                OrderNormalizationTransformer transformer) {
            return IntegrationFlow.from("testInput")
                    .transform(RawOrder.class, transformer::transform)
                    .channel("testOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("testInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    QueueChannel output;

    @Test
    void validPayloadProducesOneOutputMessage() {
        RawOrder raw = new RawOrder(
                "ORD-201", "100000", "vn");

        assertTrue(input.send(
                MessageBuilder.withPayload(raw).build()));

        Message<?> received = output.receive(0);
        assertNotNull(received);
        ValidatedOrder normalized =
                (ValidatedOrder) received.getPayload();
        assertEquals("VN", normalized.destinationCountry());
        assertEquals(new BigDecimal("100000"), normalized.amountVnd());
        assertNull(output.receive(0));
    }

    @Test
    void invalidPayloadThrowsAndDoesNotProduceOutput() {
        RawOrder raw = new RawOrder(
                "ORD-202", "broken", "VN");

        RuntimeException failure = assertThrows(
                RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload(raw).build()));

        Throwable root = failure;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }
        assertInstanceOf(InvalidOrderException.class, root);
        assertEquals(
                "INVALID_AMOUNT_FORMAT",
                ((InvalidOrderException) root).errorCode());
        assertNull(output.receive(0));
    }
}
~~~

**What this test proves:** with a synchronous `DirectChannel`, the caller observes the exception and the output branch receives nothing when the Transformer fails. The test does not insist on a single wrapper class: it walks down to the root cause.

**What this test does not prove:** `ErrorMessage` in async flows, broker redelivery, durable DLQs, retries across restarts, or downstream idempotency. Those must be tested separately.

### 13.1. Testing a `null` Result

For a Transformer intentionally returning `null`, a separate integration test can configure:

~~~java
@Bean
IntegrationFlow invalidNullTransformExample() {
    return IntegrationFlow.from("nullTransformInputChannel")
            .transform(String.class, text -> (String) null)
            .channel("unusedOutputChannel")
            .get();
}
~~~

This is a **contract-violation test example**, requiring both channels declared in the test context; never deploy this flow to production. Sending a non-null String into `nullTransformInputChannel` throws a transformation error rather than treating it as a Filter-discarded message.

## 14. Integration Test with `ExecutorChannel`: Failure Travels as `ErrorMessage`

The example below uses a **CountDownLatch** to observe `ErrorMessage` on the error channel. We do not assume the error returns to the thread calling `send()`.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AsyncTransformerFailureTest.Config.class)
class AsyncTransformerFailureTest {

    static final class FailureProbe {
        final CountDownLatch received = new CountDownLatch(1);
        final AtomicReference<Throwable> failure = new AtomicReference<>();
    }

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        OrderNormalizationTransformer transformer() {
            return new OrderNormalizationTransformer();
        }

        @Bean
        FailureProbe failureProbe() {
            return new FailureProbe();
        }

        @Bean
        ThreadPoolTaskExecutor testExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("test-transform-");
            return executor;
        }

        @Bean
        MessageChannel asyncInput(
                @Qualifier("testExecutor")
                ThreadPoolTaskExecutor executor) {
            return new ExecutorChannel(executor);
        }

        @Bean
        QueueChannel successOutput() {
            return new QueueChannel();
        }

        @Bean
        MessageChannel testErrorChannel() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow transformerFlow(
                OrderNormalizationTransformer transformer) {
            return IntegrationFlow.from("asyncInput")
                    .transform(RawOrder.class, transformer::transform)
                    .channel("successOutput")
                    .get();
        }

        @Bean
        IntegrationFlow failureFlow(FailureProbe probe) {
            return IntegrationFlow.from("testErrorChannel")
                    .handle(message -> {
                        if (message instanceof ErrorMessage error) {
                            probe.failure.set(error.getPayload());
                            probe.received.countDown();
                        }
                    })
                    .get();
        }
    }

    @Autowired
    @Qualifier("asyncInput")
    MessageChannel input;

    @Autowired
    @Qualifier("successOutput")
    QueueChannel output;

    @Autowired
    FailureProbe probe;

    @Test
    void malformedPayloadProducesErrorMessage() throws Exception {
        Message<RawOrder> message = MessageBuilder
                .withPayload(
                        new RawOrder("ORD-300", "oops", "VN"))
                .setHeader(
                        MessageHeaders.ERROR_CHANNEL,
                        "testErrorChannel")
                .setHeader("eventId", "evt-300")
                .build();

        assertTrue(input.send(message));

        assertTrue(probe.received.await(5, TimeUnit.SECONDS));
        assertNotNull(probe.failure.get());
        assertNull(output.receive(0));
    }
}
~~~

**What this test proves:** when Spring Integration processes a message on an `ExecutorChannel` and routes errors via a valid `errorChannel` header, an error consumer can receive the `ErrorMessage` **after** `send()` returns. The 5-second wait is a test timeout, not a production latency guarantee.

**Note:** if your system uses custom executors/error handlers, or messages run on library threads outside Spring Integration tasks, test error publishing separately. Do not assume setting a header is enough to catch every exception on every thread.

## 15. Remaining Test Cases to Cover

| Scenario | What to Verify |
| --- | --- |
| Valid input | Exactly one output of type `ValidatedOrder` |
| Unparseable amount | `INVALID_AMOUNT_FORMAT` and no success output |
| Negative or fractional amount | `INVALID_AMOUNT_VALUE` |
| Missing country code | `INVALID_COUNTRY` |
| Transformer returns null | Transformation error, not silent discard |
| Downstream handler throws | Not misattributed to parse error code |
| `ErrorMessage` lacks `originalMessage` | Error handler does not throw NPE |
| Untrusted `errorChannel` header | Ingress strips/replaces with internal channel |
| Unsupported `schemaVersion` error | Quarantined or rejected, no infinite retries |
| Transient failure in separate lookup step | Bounded retry with `RecoveryCallback` |
| `ExecutorChannel` overload | Admission failure/backpressure detected |
| `QueueChannel` without consumer | Monitoring detects backlog, not confused with parse error |
| Splitter child fails transform | Aggregator has explicit timeout/partial policy |
| Replay after schema fix | Same `eventId`, downstream idempotency applied |
| Error consumer inside error flow fails | Alerting/secondary error path exists |

## 16. Observability for Transformers

Multi-step flows easily lump every failure under "message failed." Measure the transformation stage separately:

| Signal | Purpose |
| --- | --- |
| **transform_attempts_total{transformer}** | Total transformation attempts |
| **transform_success_total{transformer}** | Successful transformations |
| **transform_failed_total{transformer,error_code}** | Classified failures |
| **transform_duration_seconds{transformer}** | Latency p50/p95/p99 |
| **transform_retry_total{transformer}** | Retries when policy applies |
| **transform_quarantine_pending_total** | Messages awaiting investigation/replay |
| **error_channel_delivery_failed_total** | Error notification path also failed |
| **downstream_failed_total{component}** | Avoid confusing post-Transformer failures with parse errors |

Metric labels should have **bounded cardinality** such as Transformer name or error code. Never use `orderId`, `eventId`, exception messages, or raw inputs as labels due to cardinality and data exposure risks.

### 16.1. Structured Logging

Example rejected event:

~~~json
{
  "eventId": "evt-109",
  "component": "orderNormalizationTransformer",
  "errorCode": "INVALID_AMOUNT_FORMAT",
  "schemaVersion": 1,
  "retryable": false,
  "outcome": "QUARANTINED"
}
~~~

A log entry like this conveys **cause and handling decision** without exposing raw amounts or full payloads. When reconciliation requires the original input, save it securely in a dedicated quarantine store with access control and retention.

### 16.2. Alerting and Operations

Alert when:

- `INVALID_AMOUNT_FORMAT` spikes suddenly, indicating a possible producer format change.
- `UNSUPPORTED_SCHEMA_VERSION` appears after a deployment.
- The global `errorChannel` receives an unusual surge of `ErrorMessage`s.
- `ErrorMessage` has no subscriber or the error handler keeps failing.
- Failed/retry queues accumulate and message age climbs.
- Transformer success stays steady while downstream errors climb: likely a target-system outage, not a converter bug.

Never create an unbounded **transform error → retry raw input → transform error** loop. For deterministic input errors, replay only after fixing data, schemas, or code.

## 17. Practice Exercise: Malformed JSON Event in a Payment Flow

Build a Spring Integration application receiving events:

~~~json
{
  "eventId": "evt-801",
  "eventType": "payment.completed",
  "schemaVersion": 1,
  "paymentId": "pay-801",
  "amountVnd": "2400000",
  "currency": "VND"
}
~~~

**Requirements:**

1. Receive JSON Strings from an inbound channel.
2. Convert JSON into **PaymentEvent** with a `BigDecimal` amount and valid currency.
3. Reject malformed JSON, missing `paymentId`, or invalid amounts.
4. For unsupported `schemaVersion`, quarantine the event instead of retrying infinitely.
5. For valid data, a Router picks either **accountingChannel** or **auditChannel** per published business contract. If an event must go to both simultaneously, use a Recipient List rather than assuming a Router picks one.
6. In synchronous flows, callers must see conversion errors; in async flows, `ErrorMessage` must reach the configured error channel.
7. `ErrorMessage` must never leak personal data, tokens, or payment secrets.
8. `eventId` remains stable across replays; the accounting consumer must be idempotent.

### Design Hint

~~~mermaid
flowchart LR
    P["Producer"] --> I["rawPaymentEvents"]
    I --> V["JSON schema validation"]
    V --> T["Payment Transformer"]
    T --> R["Recipient List / Router"]
    R --> A["Accounting"]
    R --> B["Audit"]
    V -.->|"Malformed"| Q["Quarantine"]
    T -.->|"Invalid amount"| Q
    R -.->|"Downstream failure"| E["Recipient retry / error flow"]
~~~

### Implementation Steps

1. Write `RawPaymentEvent` and `PaymentEvent` records, with `PaymentEvent` using `BigDecimal`.
2. Build a pure Java **PaymentEventTransformer** assigning an `errorCode` per data error.
3. Configure an `IntegrationFlow` with the Transformer and dedicated output channel.
4. Write success tests and an intentional `null`-return test to observe `MessageTransformationException`.
5. Write `DirectChannel` tests: invalid input throws and produces no output.
6. Switch input to `ExecutorChannel` with a bounded executor and dedicated `errorChannel`.
7. Use `CountDownLatch` in tests to assert `ErrorMessage` receipt without `Thread.sleep`.
8. Add a schema lookup step against a mock service that can time out; apply retries only to transient errors on that step.
9. Simulate an accounting consumer that already wrote to the DB while the response was lost; test `eventId` and unique constraints/idempotency.
10. Design a durable quarantine with storage, replay status, attempt limits, and metrics.

### Evaluation Criteria

| Criterion | Passing Standard |
| --- | --- |
| Pure transformation | No DB, email, or payment API calls inside Transformer |
| Error classification | Error codes distinguish data errors from infrastructure errors |
| Null contract | Never uses `null` to represent discard |
| Sync path | Errors propagate to caller on `DirectChannel` |
| Async path | `ErrorMessage` handled on right channel with timeout-based test |
| Retry | Only recoverable failures are retried |
| Idempotency | Replay creates no duplicate accounting side effects |
| Observability | Traces and error codes reconcile without leaking sensitive data |

## 18. Advanced Scenarios for Self-Analysis

### Scenario A: Failures on Individual Splitter Child Messages

A Splitter emits 100 invoice items and a Transformer converts each item into a DTO for an Aggregator. Item 43 has a malformed currency format.

Decide:

- Should the entire batch fail or only item 43?
- Should a structured **failure result** be sent to the Aggregator?
- What timeout and release strategy should the group use?
- If item 43 is retried after fixing data, will already-completed items duplicate?
- Which `correlationId` and sequence metadata must be preserved?

### Scenario B: New Data Arrives Before Consumer Upgrades Version

A producer starts sending `schemaVersion=2` while the consumer supports only version 1. The Transformer fails with **UNSUPPORTED_SCHEMA_VERSION**.

Explain why retrying immediately with unchanged payloads is useless, how to hold events in quarantine, deploying the new consumer, and replaying using the original `eventId`.

### Scenario C: Errors After an HTTP Enrichment Step

A workflow runs a normalizing Transformer first, then enriches via HTTP lookup. The HTTP lookup repeatedly times out and an operator enables retry across the entire pipeline.

Evaluate the cost of re-running parsing, the risk of repeating earlier side-effecting steps, and moving retry onto the HTTP endpoint itself with a circuit breaker and timeout.

### Scenario D: Failure Occurs After `send()` Succeeds

A caller sends a message to `ExecutorChannel`, receives `true`, and immediately returns HTTP 200 to the client. Seconds later the Transformer finds invalid JSON.

Propose an asynchronous status contract (e.g., HTTP 202 with a tracking ID), failure notification channel, event retention, and how clients query completion status.

## 19. Self-Check Questions

1. Why is a Transformer not allowed to return `null`? How does a Message Filter differ from a Transformer?
2. When is a Service Activator method allowed to return `null`?
3. Should `INVALID_AMOUNT_FORMAT` be retried with the same input? Why or why not?
4. When using `DirectChannel`, how do exceptions from a Transformer propagate?
5. Why does declaring a global `errorChannel` bean not automatically catch every synchronous exception?
6. What does `ErrorMessage` hold in its payload? Is `originalMessage` always present?
7. When does the `errorChannel` header take precedence over the global `errorChannel`?
8. Why should you never trust an `errorChannel` supplied by an HTTP client?
9. What is `RequestHandlerRetryAdvice` responsible for, and why must it be attached to the right endpoint?
10. When should `ErrorMessageSendingRecoverer` be used?
11. Why must a replayed event with a new `MessageHeaders.ID` still be treated as the same logical event?
12. What happens if a child message fails before an Aggregator?
13. Should a downstream failure occurring after a Transformer be counted as a parse error?
14. Can an `ErrorMessage` or a channel named DLQ serve as proof that a message was durably persisted?
15. How do synchronous and asynchronous tests differ in how they wait for and observe results?

## 20. Pre-Deployment Checklist

- Transformer has an explicit input/output contract and never uses `null` to drop messages.
- Raw data is validated and size-bounded before expensive parsing.
- Exceptions are classified by stable error codes and retryability.
- Failures are never hidden behind seemingly valid default payloads.
- Pure transformation has no side effects; I/O is isolated in proper adapters/enrichers.
- Java DSL wires input/output channels properly, and outputs have real consumers.
- **DirectChannel vs. ExecutorChannel/QueueChannel** boundaries are defined and tested.
- Error channels match ingress/gateways and trusted metadata sources.
- Error handlers tolerate missing `originalMessage` or `failedMessage`.
- Every retry policy specifies attempt count, backoff, timeout, and recovery.
- Malformed/unsupported messages are not retried infinitely; intentional quarantine or rejection exists.
- Critical replayable messages are durably stored with `eventId`, `schemaVersion`, and retention.
- Downstream replay is idempotent wherever business actions have side effects.
- Reply/error/correlation headers are managed by trusted components and preserved where needed.
- Logs, traces, and metrics provide observability without exposing raw payloads or sensitive headers.
- Unit tests cover valid/invalid/null; integration tests cover sync/async/error flows.
- Failures in the `ErrorMessage` handling path trigger alerts and cannot loop infinitely.

**Conclusion:** A Transformer is permitted to **throw exceptions** when it cannot produce a valid result. That is contract-compliant behavior, not a reason to return `null` or pass corrupt data downstream. In Spring Integration, where errors surface and how they route depend on **channel/thread boundaries**: synchronous paths normally throw back to the caller, while asynchronous paths require proper **ErrorMessage/errorChannel** handling. Combining error classification, pure transformation, targeted retries, quarantine, correlation, and thorough testing keeps Transformer flows safe, observable, and resilient.

## References

- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): Transformer contracts, null returns, MessageTransformationException, and annotations.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): DirectChannel, ExecutorChannel, ErrorMessage, errorChannel, and pollers.
- [Spring Integration API — MessageTransformationException](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformationException.html): specialized exception type for transformation errors.
- [Spring Integration Reference — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): RequestHandlerRetryAdvice, stateless/stateful retry, and recovery.
- [Spring Integration API — ErrorMessageSendingRecoverer](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html): recovery via ErrorMessage after retries exhaust.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel, and execution boundaries.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): configuring IntegrationFlow, Transformers, and endpoints.
