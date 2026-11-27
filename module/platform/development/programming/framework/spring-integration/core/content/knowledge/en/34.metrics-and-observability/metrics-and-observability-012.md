# Never log sensitive payloads

## 1. Objectives and scope

In the **Metrics and observability** chapter of the `SPRING_INTEGRATION_CORE` module, message flow observability must help determine where a message is, which step failed, and where the system is slow. That capability does not require copying business data into the logging system.

This lesson applies to Spring Integration flows using `Message`, `MessageChannel`, endpoints, gateways, and Java DSL. Transformers, routers, filters, and aggregators can all handle sensitive data; therefore, the same logging policy must span the entire flow, including error and discard branches.

After this lesson, you will be able to:

- Distinguish business data from metadata permitted for operations.
- Recognize logging patterns that inadvertently drag in payloads, headers, or exception causes.
- Write a Java DSL flow that emits only selected fields.
- Design error logs and combine metrics and tracing without leaking sensitive data elsewhere.
- Build verification checks that detect leaks using synthetic canary data.

Java snippets use Java 17 syntax and the Java DSL of Spring Integration 6.x or higher. These are illustrative components to place into an application that already has Spring Integration, SLF4J, and logging configured; the lesson does not provide a complete starter project.

## 2. Why can a single log line create another sensitive data store?

Suppose a system receives delivery requests. The payload holds an email and delivery instructions; headers hold authentication info injected by the transport layer. An endpoint needs part of that data to complete business logic, whereas operators usually only need to know:

1. Which flow received the request.
2. Which observation ID links related events.
3. The processing step and outcome.
4. Processing duration, retry count, and a normalized error category.

A casual logging statement can emit far more than needed:

~~~java
// Examples to avoid.
log.info("Received payload={}", message.getPayload());
log.debug("Received message={}", message);
log.warn("Headers={}", message.getHeaders());
~~~

When the payload is a DTO, `toString()` may print email, address, or note fields. With `Message`, its string representation may include both payload and headers. With a headers map, every value is allowed into the log formatter. The fact that a particular data type currently prints only a class name or object address is not a long-term security guarantee.

An event typically travels through consoles, files, collection agents, queues, and search platforms. Copies can also appear in alerts or diagnostic bundles. Therefore, filtering inside the log viewer UI does not remove data that was already ingested earlier.

**Design principle:** build a dedicated representation for observability containing only allowlisted fields; never use business objects as log representations.

## 3. Determining which data is allowed for export

### 3.1. The payload is not the only place holding data to protect

| Location | Example in an integration flow | How to handle when logging |
| --- | --- | --- |
| Payload | Email, address, document body, customer notes | Do not log the raw object or full contents |
| Transport headers | Authorization, Cookie, API keys | Exclude from log events |
| Business headers | Customer ID, record ID, username | Evaluate each field; do not allow by default just because it is a header |
| Exceptions | Error messages containing request bodies or partner responses | Map to bounded error codes; do not emit raw messages |
| MDC and tracing baggage | Data attached automatically to every event | Maintain a separate allowlist; do not copy all headers |
| Files or URLs | Filenames containing customer names, queries containing tokens | Emit only controlled path patterns or endpoint names |
| Aggregator results | Lists of requests or entire message groups | Log group counts and status if allowed; do not dump groups |

Data does not need to be a password to be sensitive. Free-form text such as notes can unexpectedly contain personal information.

OWASP highlights removing or specially handling tokens, passwords, and personal data before recording logs. A flow's concrete policy must go further than scanning for a few familiar field names: you must know every emitted field and its exact purpose. See [OWASP's guide on data to exclude from logs](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

### 3.2. Use an allowlist instead of copy-and-redact

Two approaches differ sharply in durability:

- **Denylist:** serialize everything, then strip keys like `password` or `token`.
- **Allowlist:** construct a fresh event from agreed fields, such as `event`, `flow`, `request_id`, `outcome`.

The first approach easily misses new fields, nested objects, alternate names for the same secret, or data embedded in free-form strings. The second omits new fields by default whenever the business model evolves.

A log contract for an order intake flow might be:

| Field | Source | Constraint |
| --- | --- | --- |
| `event` | Source-code constant | E.g., `order.received`, `order.completed`, `order.failed` |
| `flow` | Fixed flow name | E.g., `orders`; never taken from payload |
| `request_id` | UUID generated at application edge | Preserved across linked steps; contains no email or customer ID |
| `message_id` | Spring Message ID | Used only to distinguish one message |
| `outcome` | Bounded value set | `SUCCESS`, `FAILURE`, `REJECTED` |
| `error_code` | Application-defined error taxonomy | Never use `exception.getMessage()` |
| `duration_ms` | Measured duration | Non-negative number with explicit unit |
| `attempt` | Application-managed retry state | Reasonably bounded integer |

This list is an illustrative design, not a mandatory Spring Integration schema. When adding a field, you must be able to answer which problem it helps investigate and whether it could inadvertently accept external data.

### 3.3. IDs still need purpose and limits

`message_id` identifies one Spring Message. When a transformer creates a new message or a splitter produces child messages, do not assume this ID is a stable correlation key for the entire transaction.

`request_id` in this lesson is a dedicated observation header generated randomly at the boundary. It is not automatically synonymous with the `correlationId` header used by aggregators to group messages. If a transformer builds a new message instead of retaining headers, it must explicitly forward approved observation metadata.

Even a UUID can allow looking up records via another system, so it still belongs under appropriate access controls and retention periods. An observation ID is not proof of authentication or authorization. Checking format validity only constrains data shape, not trustworthiness of the sender.

## 4. Common leak points in Spring Integration

### 4.1. Logging Channel Adapter and Java DSL `log()`

Never interpret `log-full-message="false"` as "logs no sensitive data". The Logging Channel Adapter logs the payload by default; enabling full message can include headers too. Configure an explicit expression or data-selection function. See [Logging Channel Adapter](https://docs.spring.io/spring-integration/reference/logging-adapter.html).

~~~java
// No safe representation specified; do not use for sensitive messages.
.log()

// Return only selected metadata.
.log(
    LoggingHandler.Level.INFO,
    "integration.safe.orders",
    m -> "event=order.received flow=orders message_id="
            + m.getHeaders().getId()
)
~~~

String concatenation in the safe example combines only constants and a UUID; no business string enters the template. In regular logger calls, use fixed templates and controlled arguments.

According to the [Java DSL log() operator documentation](https://docs.spring.io/spring-integration/reference/dsl/java-log.html), this operator uses a wire tap together with LoggingHandler. Therefore, even without direct logger calls in business code, an observation step inserted into the DSL can emit records containing data. Since Spring Integration 6.0, `log()` at the end of a flow does not automatically make the flow a one-way endpoint; the lesson's example includes a one-way handler that terminates business execution.

### 4.2. Wire taps, interceptors, and secondary branches

A wire tap receives the message for a side branch; it does not automatically create a redacted copy. If that side branch logs `message`, `payload`, or `headers`, policies on the main flow are no longer enough.

Places requiring the exact same log contract include:

- `ChannelInterceptor` before and after sending.
- Filter discard branches.
- Routers and unmatched default branches.
- Aggregator timeout, expiry, or release branches.
- Retry advice, recovery callbacks, and dead-letter/error message stores.
- Code surrounding gateways, where callers may log entire requests or replies.

With a filter, an `order.rejected` event with `reason_code=UNSUPPORTED_TYPE` is usually sufficient to count and spot misconfigurations. If the reason string is constructed from the rejected value itself, it can reintroduce business data into logs.

With an aggregator, you can log `group_size` and processing state; there is no need to log every item in the group. Group keys must also be evaluated: if the correlation key is an email, logging the group key still leaks the email.

### 4.3. DEBUG, TRACE levels, and `nullChannel`

Lowering only the application's log level does not eliminate all data-emission paths. Framework loggers, HTTP client libraries, or broker clients may have their own settings.

Notably, `nullChannel` can log messages at DEBUG level per [Special Channels documentation](https://docs.spring.io/spring-integration/reference/channel/special-channels.html). Routing messages there to end or discard processing does not mean messages cannot appear in logs.

Do not enable broad DEBUG or TRACE for entire integration packages on real data without knowing what those loggers emit. When investigation is needed, narrow the scope, reproduce with synthetic data, and inspect actual output for your exact library versions.

## 5. Flow design: observing through dedicated metadata

~~~mermaid
flowchart LR
    A["Edge layer: generate request_id"] --> B["orders.input"]
    B --> C["Log allowed metadata"]
    C --> D["Order processing endpoint"]
    D --> E["Log allowed outcome"]
    C -.-> L["Operational log store"]
    E -.-> L
    D --> F["Handle errors per contract"]
    F -.-> L
~~~

The payload goes to endpoints that need to execute business logic. The log store receives only the observation representation. Error paths must uphold the exact same rule.

Two boundaries must stay clearly separated:

1. **Business processing boundary:** endpoints are permitted to read email or address when required.
2. **Observability output boundary:** loggers may receive only allowlisted fields.

Constructing log events must never mutate the original payload. Masking data by overwriting email or tokens inside the message and forwarding it can break business logic, retries, or external integrations.

## 6. Example: a metadata selector that does not read the payload

Place the following class in an application package. Every emitted value is a constant or UUID; malformed headers are represented as `missing`.

~~~java
import java.util.Map;
import java.util.UUID;

import org.springframework.messaging.Message;

public final class SafeLogFields {

    public static final String REQUEST_ID = "obsRequestId";

    private SafeLogFields() {
    }

    public static String requestId(Map<String, Object> headers) {
        Object candidate = headers.get(REQUEST_ID);

        // The application boundary must generate the UUID; do not forward
        // raw external headers here.
        return candidate instanceof UUID id
                ? id.toString()
                : "missing";
    }

    public static String received(Message<?> message) {
        UUID messageId = message.getHeaders().getId();

        return "event=order.received"
                + " flow=orders"
                + " request_id=" + requestId(message.getHeaders())
                + " message_id="
                + (messageId == null ? "missing" : messageId.toString());
    }
}
~~~

This class intentionally does not call `getPayload()`, does not iterate all headers, and does not serialize `Message`. If the payload gains new sensitive fields, the function will not automatically emit them.

Accepting only `UUID` also avoids calling `toString()` on an arbitrary header object. For a string-valued header, add dedicated format and length validation if you genuinely need to support it; never convert to string out of habit.

The function above controls its own return value. Logging patterns, JSON encoders, or MDC can still append other data to the final log record; verify those layers independently.

## 7. Java DSL example: keeping payload for business logic, logging only metadata

### 7.1. Declaring a one-way flow

Classes in the example belong to the same package. `OrderService` is the extension point where the application supplies real business processing.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.LoggingHandler;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class SafeOrderFlowConfiguration {

    private static final Logger LOG =
            LoggerFactory.getLogger("integration.safe.orders");

    public record Order(
            String customerEmail,
            String deliveryNote) {
    }

    public interface OrderService {
        void accept(Order order);
    }

    @Bean(name = "orders.input")
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow safeOrdersFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
                .log(
                        LoggingHandler.Level.INFO,
                        "integration.safe.orders",
                        SafeLogFields::received)
                .handle(Order.class, (order, headers) -> {
                    orderService.accept(order);

                    LOG.info(
                            "event=order.completed flow=orders"
                                    + " request_id={} outcome=SUCCESS",
                            SafeLogFields.requestId(headers));

                    // This handler produces no reply: one-way flow.
                    return null;
                })
                .get();
    }
}
~~~

The application must register a bean implementing `OrderService`. Do not supply an implementation that logs `order`, as that violates the policy right inside the service.

`order.received` only means the message reached the observation point at the start of the flow; it does not prove business completion. `order.completed` in the example means `accept()` returned normally. If a transaction commits only after the handler exits, this event is not proof of durable commit. With retries, one request can have multiple receipts or executions; document event semantics clearly rather than treating logs as "exactly-once" proof.

### 7.2. Gateway and edge-generated observation ID

You can declare a one-way gateway so callers do not interact with channels directly:

~~~java
import java.util.UUID;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrdersGateway {

    void submit(
            @Payload SafeOrderFlowConfiguration.Order order,
            @Header(SafeLogFields.REQUEST_ID) UUID observationRequestId);
}
~~~

Example call at the edge after receiving and validating a request:

~~~java
UUID observationRequestId = UUID.randomUUID();

ordersGateway.submit(
        new SafeOrderFlowConfiguration.Order(
                "learner@example.test",
                "DELIVERY_NOTE_CANARY"),
        observationRequestId);
~~~

Both the email and canary string above are synthetic test data. The observation header is generated by the application, not copied directly from `Authorization`, query strings, or a customer ID.

If you need to retain a correlation ID from a sending system, specify the allowed header, cap its length, validate its format, and keep it separate from internal IDs. Do not copy all headers as a blanket context propagation mechanism.

The two expected log lines look like:

~~~text
event=order.received flow=orders request_id=8f4e8631-7d25-4ea3-9f5c-102c2d770e72 message_id=6ec1ae9e-25b8-4b61-9fd9-63ee86b2801d
event=order.completed flow=orders request_id=8f4e8631-7d25-4ea3-9f5c-102c2d770e72 outcome=SUCCESS
~~~

Search by `request_id` to correlate events. There is no need to search by email or payload contents.

## 8. Error paths: exceptions can also carry the original message

### 8.1. Patterns that easily leak data

~~~java
// Avoid logging raw ErrorMessage or Throwable.
log.error("Error message={}", errorMessage);
log.error("Processing failed", exception);
log.warn("Failure detail={}", exception.getMessage());
~~~

Not every stack trace contains payloads. However, exception messages, cause chains, and exceptions constructed by integration libraries can place request data into error representations. Passing a `Throwable` argument to a logger is typically rendered by the backend as a separate stack trace outside the formatted message string.

In Spring Integration, asynchronous paths can publish an `ErrorMessage` via the `errorChannel` header or the global error channel. The default error channel already has a LoggingHandler. Therefore, adding a safe subscriber does not automatically remove the existing logger on a publish-subscribe channel. With a synchronous `DirectChannel` as in the example above, exceptions usually propagate back to the caller; do not assume every error automatically flows through an error channel. See [Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html).

### 8.2. Creating a bounded error representation

The following classifier never reads exception messages:

~~~java
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeoutException;

public final class SafeFailureCode {

    private SafeFailureCode() {
    }

    public static String classify(Throwable failure) {
        Throwable current = failure;

        // Limit traversed cause depth; do not print each cause.
        for (int depth = 0; current != null && depth < 8; depth++) {
            if (current instanceof TimeoutException
                    || current instanceof SocketTimeoutException) {
                return "DEPENDENCY_TIMEOUT";
            }

            current = current.getCause();
        }

        return "PROCESSING_FAILURE";
    }
}
~~~

The example below illustrates only a consumer of a dedicated error channel. It is not a complete error-handling configuration for every adapter:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class SafeOrderErrorLogger {

    private static final Logger LOG =
            LoggerFactory.getLogger("integration.safe.orders");

    @ServiceActivator(inputChannel = "orders.errors")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (failure instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            original = messaging.getFailedMessage();
        }

        String requestId = original == null
                ? "missing"
                : SafeLogFields.requestId(original.getHeaders());

        LOG.warn(
                "event=order.failed flow=orders"
                        + " request_id={} outcome=FAILURE error_code={}",
                requestId,
                SafeFailureCode.classify(failure));
    }
}
~~~

Here, the `ErrorMessage` payload is read because it is the `Throwable` used for classification. The consumer does not log the failed message's business payload, does not log the full `ErrorMessage`, does not log causes, and does not pass the `Throwable` to the logger.

To use this consumer, the application must declare the `orders.errors` channel and wire error-emitting adapters, pollers, or executors to it. This snippet does not automatically replace the default error channel or external client loggers.

A handler returning `void` acts as a terminal consumer in the example. With queues or brokers, consuming an error and returning normally can affect recovery, acknowledgments, or retries. Design retry decisions, dead-letter storage, or error replies to gateways separately. Fixing how errors are logged must never accidentally turn a failed request into a successful completion.

If stack traces are still needed for investigation, design a diagnostic mechanism with controlled data scope or reproduce with synthetic data. Do not assume stripping the top exception line removes all sensitive data inside the cause chain.

## 9. Masking, redaction, and log injection

### 9.1. Why masking a few fields is not enough

A DTO may have an `email` field, yet the same data can also appear in `contact`, nested JSON, or `deliveryNote`. A regex looking for a `password` key will not cover those locations.

Distinguish the options:

- **Omission:** do not emit the field; the right choice whenever operations do not need the value.
- **Masking:** hide part of the value; the remaining characters may still identify a person or record.
- **Hashing:** produces a deterministic fingerprint; inputs from small domains can be guessed by recomputation.
- **HMAC:** usable for controlled linkage when designed with key management and scoped usage; still produces linkable identifiers.
- **Encryption:** protects data while ciphertext, yet does not make dumping payloads into logs a sound operational requirement.

In the demonstration flow, generating an observation UUID eliminates any need to put emails or email hashes into logs.

If you must redact a structure for a defined purpose, build a new representation, handle nested structures, never mutate the business message, and define fallback behavior when redaction fails. When a safe representation cannot be built, emit only an event like `diagnostic.redaction_failed` with allowed metadata; never fall back to serializing the original object.

### 9.2. Fixed templates are not enough if values are unvalidated

~~~java
// Even with placeholders, external values can still contain CR/LF.
log.info("request_id={}", externalRequestId);
~~~

Strings containing newline characters can make text output look like multiple log events. Cap length, validate format, and use encoders that properly escape values for the output format. JSON helps delimit fields when properly encoded, though serializing a payload to JSON still leaves sensitive data inside the payload.

OWASP distinguishes fixed templates, input validation, and output encoding; parameterized logging alone does not prevent CR/LF log injection. See [Logging Cheat Sheet, Log Injection section](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#log-injection).

`SafeLogFields` restricts dynamic fields to UUIDs or the constant `missing`. That shrinks both sensitive-content exposure and control-character injection risks in the fields it emits.

## 10. Combining logs, metrics, and traces in their proper roles

Spring Integration supports Micrometer Observation for metrics and tracing. Observation does not mean the application should collect payloads; data placed into tags, span events, or baggage still requires its own contract. See [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html).

| Observability signal | What to include in the example | What to avoid |
| --- | --- | --- |
| Logs | Events, request ID, steps, and normalized outcomes | Payloads, full headers, raw exception messages |
| Metrics | Request counts, failures, latency distributions by flow and outcome | Emails, tokens, request IDs, message IDs as tags |
| Traces | Relationships across steps and systems, durations, trace/span IDs | Request bodies, baggage with customer info, raw URLs with sensitive queries |

Random IDs usually have very high cardinality. They are useful for looking up a single execution in logs or traces, but putting them into metric tags causes cardinality explosion.

Conversely, a bounded `error_code` such as `DEPENDENCY_TIMEOUT` suits counting or error classification. If an "error code" is built by concatenating exception text, it both inflates cardinality and leaks data.

Trace IDs can be added automatically to logs via MDC configuration. Never put a copy of the payload into MDC to "automatically have context everywhere". When crossing an `ExecutorChannel` or poller, propagating and clearing context across threads must follow the application's context propagation mechanism; do not rely on a previous thread happening to retain the right MDC.

Also check whether exporters or instrumentation automatically record exception events. A clean log line does not prove the corresponding span is clean too.

## 11. Verifying with canary data

Canaries here are clearly marked synthetic strings used to detect data escaping into outputs. Never use real tokens or customer data for testing.

### 11.1. Testing the metadata selector

The illustrative tests use JUnit 5. They test the field-selection boundary without starting a full application context:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeLogFieldsTest {

    @Test
    void emitsExactlyTheAllowedFields() {
        UUID requestId =
                UUID.fromString("8f4e8631-7d25-4ea3-9f5c-102c2d770e72");

        Message<String> message = MessageBuilder
                .withPayload(
                        "EMAIL_CANARY@example.test DELIVERY_NOTE_CANARY")
                .setHeader("Authorization", "Bearer HEADER_SECRET_CANARY")
                .setHeader("Cookie", "session=COOKIE_SECRET_CANARY")
                .setHeader(SafeLogFields.REQUEST_ID, requestId)
                .build();

        String expected = "event=order.received"
                + " flow=orders"
                + " request_id=" + requestId
                + " message_id=" + message.getHeaders().getId();

        assertEquals(expected, SafeLogFields.received(message));
    }

    @Test
    void doesNotStringifyPayloadOrInvalidHeader() {
        Object sensitiveObject = new Object() {
            @Override
            public String toString() {
                throw new AssertionError(
                        "Must not stringify sensitive object");
            }
        };

        Message<Object> message = MessageBuilder
                .withPayload(sensitiveObject)
                .setHeader(SafeLogFields.REQUEST_ID, sensitiveObject)
                .build();

        String actual = assertDoesNotThrow(
                () -> SafeLogFields.received(message));

        String expected = "event=order.received"
                + " flow=orders"
                + " request_id=missing"
                + " message_id=" + message.getHeaders().getId();

        assertEquals(expected, actual);
    }
}
~~~

Comparing the entire string in the first test catches accidental field additions too. The second test catches calling `toString()` on payloads or wrong-typed headers instead of checking only for one known secret string.

These two tests do not yet test LoggingHandler, encoders, MDC, or the logging framework. Nor do they verify that the complete business flow preserves behavior.

### 11.2. Checking actual output across the entire flow

In a test environment, send the following cases through real gateways or adapters:

| Case | Where synthetic data is placed | What to verify |
| --- | --- | --- |
| Success | Payload and auth headers | Only contract-approved metadata appears |
| Service throws error | Exception message and cause contain `EXCEPTION_SECRET_CANARY` | Canary does not appear in logs or spans |
| Filter rejects | Note contains `DISCARD_SECRET_CANARY` | Discard branch logs only the reason code |
| Retry then failure | Message carries same canary across attempts | Every attempt and recovery preserves the contract |
| Aggregator timeout | Child messages contain `GROUP_SECRET_CANARY` | No group dump or sensitive group key logged |
| Invalid header | String with CR/LF or arbitrary object | No forged log event, no object stringification |
| Expected diagnostic loggers on | Canaries as in cases above | No raw messages emitted by framework or clients |

If collecting events via a Logback appender in tests, do not inspect only `getFormattedMessage()`. Also inspect throwable proxies, arguments or structured fields, markers, and MDC. Post-encoder output should also be checked because encoders can append fields or transform strings.

For async flows, wait on a completion condition and flush logging appenders before asserting. An assertion running before the message is processed can report clean while data simply has not been written yet.

Canaries can be JSON-escaped, URL-encoded, or re-represented. Check properly decoded output alongside the allowlisted field schema; plain raw-string search does not cover every transformation. Simultaneously confirm email and notes still reach the service intact: protecting logs must not alter business payloads.

## 12. Investigating errors with sufficient information

Suppose a dashboard reports rising timeout errors. An investigation workflow without reading payloads can look like:

1. View metrics filtered by `flow=orders` and failure outcomes.
2. Search logs for `event=order.failed`, `error_code=DEPENDENCY_TIMEOUT` in the matching time range.
3. Use `request_id`, or trace ID if available, to locate related steps.
4. Compare processing duration, retry counts, and predefined endpoint names.
5. Reproduce using synthetic data of the same size or structural shape when deep analysis is needed.

If you only need to know a request was oversized, use an approved size bucket or counter instead of logging content. Never serialize payloads just to measure size for a log line; that adds overhead and creates another data-handling path.

Error message stores for replay, if required by the system, must be designed as business data storage with corresponding access controls. They are not operational log stores and should not be shipped wholesale to log search platforms by collectors.

For existing logs, determine where they are stored, who can query them, and retention duration. If a canary appears during testing, fix the emission site and re-run affected branches; adding a filter only on the viewing UI does not prove the emission path was fixed.

## 13. Applied practice exercise

Carry this out in a test application with an `Order` intake flow:

1. Define a log contract containing event, flow, observation UUID, outcome, and bounded error code.
2. Put a synthetic email, canary note, and synthetic auth header on messages; add no sensitive fields to the log contract.
3. Apply `SafeLogFields` to `log()`, and confirm the service still receives all required data untouched.
4. Have the service return normally, throw a timeout, and throw an error with a canary in its cause. Trace the error propagation path of the channel in use.
5. Add a filter discard case or retry branch if your application uses those components. Check secondary branch loggers too.
6. Capture encoded output along with MDC and exception fields; verify against allowlisted fields, not merely absence of a single string.

Completion criteria: events of one execution remain linkable, success and failure are distinguishable, and no canary data appears in inspected observation outputs. Any untested branches must be explicitly noted rather than generalized from one passing test.

## 14. Invariants to keep when expanding flows

When adding a transformer, verify whether the new message preserves allowed observation metadata. When adding a router or filter, use fixed decision codes to describe the path. When adding an aggregator, describe group state by counts and outcomes while evaluating group-key sensitivity. When adding retries or recovery, check exceptions, error channels, and error message stores too.

The most important boundary is observability output: **loggers receive an event constructed strictly from an allowlist**. Changing log levels, using placeholders, disabling full-message logging, or shifting data into traces cannot substitute for enforcing that boundary.
