# Transformer Produces No Output

## 1. Problem to Solve

In the **SPRING_INTEGRATION_CORE** module, a transformer is an endpoint that converts a message into a data representation usable by the next step. When an application reports "the transformer produces no output," you need to pinpoint where the message stopped: inside the transformation logic, while dispatching through a `MessageChannel`, or along the reply path back to a gateway.

For example, a flow receives a product code, normalizes it, and forwards it to a lookup service:

```text
Message<String> → productsInput → transformer → normalizedProducts → consumer
                    " ab-123 "                   "AB-123"
```

If the consumer receives nothing, simply increasing wait timeouts is not enough. The transformation may have returned `null`, the endpoint may never have been invoked, the result may be sitting in a queue, or a downstream step after the transformer may have terminated the flow.

After this lesson, you will be able to:

- Distinguish a `null` return, an empty payload, a filtered-out message, and a result routed to a different channel.
- Choose a transformer, filter, router, or service activator according to the business contract.
- Reproduce the failure with Java DSL and test both the success path and the no-output path.
- Trace `outputChannel`, `replyChannel`, synchronous errors, and asynchronous errors.

The illustrative configurations and tests use **Java 17+ and Spring Integration 6.5.x**. That is a baseline for the examples, not a requirement to upgrade your project. When using Spring Boot, let Boot's dependency management choose the compatible version set; do not manually mix Spring versions just to run examples.

## 2. The Transformer Contract

### 2.1. A Successful Transformation Must Produce a Result

By design, a transformer implements the relationship:

```text
one input message → one valid output message
```

For a POJO method or lambda adapted into a transformer by the DSL, a normal return value becomes the payload of the new message. If it returns a `Message<?>`, that object becomes the resulting message. Do not use `return null` to mean "skip this message." The official documentation reserves message-dropping behavior for filters. [Transformer Contract Reference](https://docs.spring.io/spring-integration/reference/transformer.html).

Correct example:

```java
public String normalizeProductCode(String code) {
    return code.strip().toUpperCase(java.util.Locale.ROOT);
}
```

Flawed design example:

```java
public String normalizeProductCode(String code) {
    if (code.isBlank()) {
        return null; // Embedding a discard decision inside the transformation.
    }
    return code.strip().toUpperCase(java.util.Locale.ROOT);
}
```

A transformer can return a list, yet that list is still the payload of **one** message. To emit each element as an individual message, use a splitter.

### 2.2. Do Not Conflate Every Kind of "Empty" Value

| Method return value | Meaning in this scenario | How to handle |
| --- | --- | --- |
| `null` | No result to form transformer output | Fix conversion logic or move discard decision to a filter |
| `""` or whitespace-only string | Valid `String` payload object exists | Check business rules; do not assume the flow stopped |
| `List.of()` | Empty list payload exists | Consumer receives an empty list if downstream steps allow |
| DTO with optional fields set to `null` | The DTO itself is a non-`null` object | Check DTO schema and required fields |
| `void` | Method has no return value | Use a service activator for flow-ending actions |

Do not use `Optional.empty()` as a universal command telling a transformer to drop a message. `Optional` is a data type; whether it is kept as a payload or unwrapped by an adapter depends on the API in use. If your domain has a "not found" state, model that state explicitly or choose a suitable endpoint.

### 2.3. Exception Types to Inspect Along the Execution Path

In Spring Integration 6.5.x, `MessageTransformingHandler` enables `requiresReply=true` upon construction. If processing returns `null`, the superclass `AbstractReplyProducingMessageHandler` may throw `ReplyRequiredException`. If the transformation itself throws an error, you will commonly see `MessageTransformationException` in the cause chain. See [Transformer Handler 6.5.x](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/transformer/MessageTransformingHandler.java) and [Superclass Reply Check Logic](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractReplyProducingMessageHandler.java).

Therefore, do not write monitoring based on the assumption that "every case where a transformer returns `null` throws the exact same exception class name." Inspect the failing endpoint, the failed message, and the full cause chain.

Do not fix the issue by trying to disable reply requirements on a transformer. Choose an endpoint with the right contract. Notably, starting in Spring Integration 7.1, `MessageTransformingHandler.setRequiresReply(...)` is documented to throw `UnsupportedOperationException`. [Method Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformingHandler.html#setRequiresReply(boolean)).

## 3. Classify the Symptom Before Fixing

| Observation | Hypothesis to check | Evidence to gather |
| --- | --- | --- |
| No log entering transformer | Message never reached endpoint, endpoint not running, or another consumer took it | Input channel name, endpoint state, subscriber count, poller |
| Log enters function, then an error occurs | Branch returning `null`, type mismatch, or exception in conversion | Return value, stack trace, root cause |
| Function returned data, yet sending failed | Reply destination unresolved or target channel rejected message | `outputChannel`, `replyChannel`, dispatch/send errors |
| Output queue has messages, yet consumer does not run | Consumer not polling, stopped, or misconfigured | Channel type, poller, lifecycle |
| Output leaves transformer, yet gateway keeps waiting | Downstream step dropped message, returned `null`, or routed to a non-reply branch | Channels after transformer and gateway contract |
| Only some requests lose output | Conditional branch, competing consumers, or data-specific failure | Business ID / correlation ID of each request |

A useful measurement is identifying **the last boundary that saw the message**. A log saying "sent to input" proves only one checkpoint; a log saying "built DTO" does not prove the final consumer received that DTO.

## 4. Reproducing the Bug and Fixing It with a Filter + Transformer

### 4.1. Complete Configuration for Both Flows

The example below intentionally places the broken flow and the fixed flow in the same configuration for comparison. Output queues exist for testing; no consumer automatically drains messages from them.

The required dependency is `spring-integration-core`. The test section below uses JUnit Jupiter and `spring-test`. In a Boot project, the Integration starter and Test starter provide these artifacts.

Save the configuration as `TransformerNoOutputConfig.java` in an appropriate package of your project:

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class TransformerNoOutputConfig {

    @Bean
    public DirectChannel brokenInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel brokenOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow brokenFlow() {
        return IntegrationFlow.from(brokenInput())
                .<String, String>transform(text -> {
                    if (text.isBlank()) {
                        return null; // Intentionally triggers an error for observation.
                    }
                    return text.strip().toUpperCase(Locale.ROOT);
                }, endpoint -> endpoint.id("brokenTransformerEndpoint"))
                .channel(brokenOutput())
                .get();
    }

    @Bean
    public DirectChannel cleanInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel acceptedOutput() {
        return new QueueChannel();
    }

    @Bean
    public QueueChannel rejectedOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow cleanFlow() {
        return IntegrationFlow.from(cleanInput())
                .<String>filter(text -> !text.isBlank(),
                        filter -> filter.discardChannel(rejectedOutput()))
                .<String, String>transform(
                        text -> text.strip().toUpperCase(Locale.ROOT),
                        endpoint -> endpoint.id("normalizeTransformerEndpoint"))
                .channel(acceptedOutput())
                .get();
    }
}
```

The configuration relies on proxied `@Bean` methods by default on `@Configuration`; calls such as `brokenInput()` reference container-managed beans. The DSL `transform` and `filter` operators create the corresponding endpoints and flow connections. [Java DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

Illustrative inputs are restricted to `String` payloads. Handling other payload types requires a dedicated type conversion contract; do not treat this example as a general-purpose data validator.

### 4.2. Expected Results

| Flow | Input | Success output | Discard or error branch |
| --- | --- | --- | --- |
| `brokenFlow` | `" ab-123 "` | `brokenOutput` receives `"AB-123"` | None |
| `brokenFlow` | `"   "` | None | Error because transformer produced no reply |
| `cleanFlow` | `" ab-123 "` | `acceptedOutput` receives `"AB-123"` | `rejectedOutput` receives nothing |
| `cleanFlow` | `"   "` | `acceptedOutput` receives nothing | `rejectedOutput` receives original message |

In the fixed flow, the filter handles acceptance before the transformer normalizes the value. A rejected message goes to `discardChannel` rather than turning into a fake empty-string output. Filter also offers `throwExceptionOnRejection(true)` if rejection must be an error; define the discard policy explicitly instead of toggling options out of habit. [Filter Behavior](https://docs.spring.io/spring-integration/reference/filter.html).

The design goal to preserve is that every branch has an observable outcome: valid inputs are normalized, and invalid inputs enter the rejection branch. In a real system, the rejection branch can record the reason, count, and business keys to support operations.

## 5. Choosing an Endpoint Based on What "No Output Needed" Means

### 5.1. Performing Only a Side Effect and Ending the Flow

If the requirement is writing an audit log, sending a notification, or invoking a service needing no further result, use a service activator. The standalone example below receives a message and prints the payload; in your application, replace the print statement with an audit service:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class AuditOnlyConfig {

    @Bean
    public IntegrationFlow auditOnlyFlow() {
        MessageHandler auditHandler = (Message<?> message) ->
                System.out.println("AUDIT: " + message.getPayload());

        return IntegrationFlow.from("auditInput")
                .handle(auditHandler)
                .get();
    }
}
```

If the business method called by a service activator returns `null` or `void`, the endpoint can terminate without emitting a reply. For a service activator where a result must be mandatory, enable `requiresReply(true)` on the endpoint configuration so violations fail immediately at that step. [Service Activator Contract](https://docs.spring.io/spring-integration/reference/service-activator.html).

If you need to write an audit log **and continue**, the method must return data again or use a separate observation branch. DSL snippet example:

```java
.<String>handle((payload, headers) -> {
    System.out.println("AUDIT: " + payload);
    return payload;
})
```

Do not place a flow-terminating handler before a step that still needs to execute, and then wait for that downstream step to receive messages.

### 5.2. Producing a Result and Intentionally Discarding It

`nullChannel` is a channel that accepts messages and discards them. This concept is different from Java's `null` value. You can route valid output to this channel if the contract genuinely permits terminating there. [Special Channels](https://docs.spring.io/spring-integration/reference/channel/special-channels.html).

```java
@Bean
public IntegrationFlow normalizeAndDiscardFlow() {
    return IntegrationFlow.from("normalizeAndDiscardInput")
            .<String, String>transform(String::strip)
            .channel("nullChannel")
            .get();
}
```

This snippet is a bean inside an Integration-enabled configuration. The transformer must still produce a result before the final channel discards it. Replacing `String::strip` with a lambda returning `null` is still an error; `nullChannel` does not alter the transformer's contract.

Do not point results to `nullChannel` merely to silence a missing-destination error when callers still expect a reply.

### 5.3. Multiple Business Processing Paths

If a product code must be routed to "valid", "not found", or "needs enrichment" branches, a router makes those paths explicit. A business outcome such as `NOT_FOUND` can also be modeled as a non-`null` DTO, after which a router selects a channel by status.

Design decisions compare as follows:

| Need | Suitable component |
| --- | --- |
| Convert data from format A to format B | Transformer |
| Decide whether a message proceeds | Filter |
| Select one or more processing branches | Router |
| Invoke business logic allowed to produce no reply | Service activator |
| Accept and intentionally drop an existing output | `nullChannel` |

## 6. Result Produced, Yet Never Reaches the Expected Destination

### 6.1. Omitting an Output Channel Is Not Necessarily a Bug

A reply-producing endpoint can send to a configured output channel; if none is configured, the framework can use the request's `replyChannel`. Gateways typically supply this reply address. Consequently, a transformer at the end of a request-reply flow does not always have to declare an explicit output channel. [Reply Channel Selection Mechanism](https://docs.spring.io/spring-integration/reference/service-activator.html).

The example below is for request-reply callers where the request already carries `replyChannel`:

```java
@Bean
public IntegrationFlow normalizeRequestFlow() {
    return IntegrationFlow.from("normalizeRequests")
            .<String, String>transform(
                    text -> text.strip().toUpperCase(java.util.Locale.ROOT))
            .get();
}
```

If you send directly via `input.send(message)` without a `replyChannel` on the message and with no output channel on the endpoint, the result may have been computed yet have nowhere to be sent. That is a reply-routing failure, distinct from the transformation returning `null`.

Conversely, if an output channel is explicitly configured, do not assume the result will simultaneously bounce back to the gateway on its own. Trace the final endpoint on that output branch.

### 6.2. `QueueChannel` Must Be Drained

With a `QueueChannel`, output may be sitting inside the buffer. A consumer reading from a pollable channel needs a poller; in tests, you can call `receive(timeout)` directly. Wiring a consumer to a queue without polling configuration is a configuration issue separate from the transformer. [Channel Configuration](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

In section 4's example, queues act as terminal observation points. No poller is needed for the transformer because its input is a `DirectChannel`; tests pull results from the queues with `receive(...)`.

If you use a `DirectChannel` as output without a subscriber, look for a dispatch failure. A send failure does not mean the transformer failed to produce data. If multiple competing consumers subscribe to the same point-to-point channel, do not assume every consumer receives a copy.

### 6.3. Preserving Metadata When Building a `Message` Manually

When a method returns a full `Message<?>`, you control both payload and headers of the output. Creating a new message while dropping essential headers can starve a downstream endpoint of reply or correlation info.

Example method for a message-accepting transformer that preserves copyable input headers:

```java
import java.util.Locale;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class ProductCodeTransformer {

    public Message<String> normalize(Message<String> input) {
        return MessageBuilder
                .withPayload(input.getPayload().strip().toUpperCase(Locale.ROOT))
                .copyHeaders(input.getHeaders())
                .setHeader("normalized", true)
                .build();
    }
}
```

This example preserves metadata in an internal flow; at system boundaries, choose an allowlist of headers permitted to cross. `id` and `timestamp` follow framework-managed rules; do not treat them as business identity guarantees across every transformation. Copying headers also does not allow the payload to become `null`.

## 7. Gateway Waits for a Reply Even Though the Transformer Ran

Suppose a caller invokes a gateway method returning `String`, yet after the transformer sits a handler that only logs and terminates. The transformer worked properly; the final processing branch failed to produce the reply the gateway expects.

Three common design options:

1. Keep the request-reply contract and return a success result or an explicit rejection response.
2. If no result is needed, use a gateway method returning `void` with a matching one-way flow.
3. If rejection is an error, throw or route the error per gateway policy instead of silently losing the reply.

Setting a finite wait timeout prevents hanging forever, yet does not manufacture the missing reply. `replyTimeout` also does not interrupt a slow handler running on the caller thread over `DirectChannel`; it governs the reply-waiting phase. When no reply arrives, the gateway may return `null` or throw a timeout error depending on configuration and return type. [Gateway When No Response Arrives](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

For example, routing rejected data to a queue for operational inspection makes sense for a one-way flow. For a synchronous gateway, merely placing the request into a rejection queue is not enough: a reply path or error-reporting policy for the caller is still required.

## 8. Locating Failures by Execution Boundary

### 8.1. Synchronous Flows

With the default `DirectChannel`, the handler runs on the sender's thread. Exceptions from the transformer can propagate back to `send(...)` or the gateway caller. When sending directly over a `MessageChannel`, do not assume setting an `errorChannel` header automatically turns synchronous errors into error messages.

### 8.2. Asynchronous Flows

When an `ExecutorChannel` or a poller consumes from a queue, processing failures happen on another thread. The integration task's error-handling mechanism can publish an `ErrorMessage` to the channel named by the `errorChannel` header, or to the default error channel. The original caller may already have finished sending before the transformer fails. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Diagnostic information should include:

- Endpoint and channel names near the failure point.
- Business key or correlation ID linking processing checkpoints.
- Payload type, acceptance/rejection state, and exception type.
- Failed message if available, with sensitive data masked appropriately.

Avoid catching all exceptions inside a conversion function and executing `return null`. Flawed example:

```java
try {
    return convert(payload);
} catch (RuntimeException ex) {
    return null; // Masks the conversion cause and violates the reply contract.
}
```

Let errors flow into the designed error-handling mechanism, or wrap exceptions while preserving the cause. Retries suit transient failures; retrying a branch that always returns `null` just repeats the logic bug.

## 9. Testing Behavior with Concrete Messages

The test suite below accompanies `TransformerNoOutputConfig` from section 4. Place both classes in the same package or add appropriate imports. Tests use an isolated context for the sample configuration; no other consumers compete for messages on the output queues.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.ReplyRequiredException;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(TransformerNoOutputConfig.class)
class TransformerNoOutputTest {

    @Autowired
    @Qualifier("brokenInput")
    DirectChannel brokenInput;

    @Autowired
    @Qualifier("brokenOutput")
    QueueChannel brokenOutput;

    @Autowired
    @Qualifier("cleanInput")
    DirectChannel cleanInput;

    @Autowired
    @Qualifier("acceptedOutput")
    QueueChannel acceptedOutput;

    @Autowired
    @Qualifier("rejectedOutput")
    QueueChannel rejectedOutput;

    @Test
    void nullResultFailsInsteadOfSilentlyDropping() {
        MessagingException failure = assertThrows(
                MessagingException.class,
                () -> brokenInput.send(
                        MessageBuilder.withPayload("   ").build()));

        assertTrue(hasCause(failure, ReplyRequiredException.class));
        assertNull(brokenOutput.receive(0));
    }

    @Test
    void acceptedInputProducesNormalizedOutput() {
        assertTrue(cleanInput.send(MessageBuilder
                .withPayload(" ab-123 ")
                .setHeader("businessKey", "request-001")
                .build()));

        Message<?> output = acceptedOutput.receive(1000);
        assertNotNull(output);
        assertEquals("AB-123", output.getPayload());
        assertEquals("request-001", output.getHeaders().get("businessKey"));
        assertNull(acceptedOutput.receive(0));
        assertNull(rejectedOutput.receive(0));
    }

    @Test
    void rejectedInputGoesToDiscardChannel() {
        assertTrue(cleanInput.send(MessageBuilder
                .withPayload("   ")
                .setHeader("businessKey", "request-002")
                .build()));

        Message<?> rejected = rejectedOutput.receive(1000);
        assertNotNull(rejected);
        assertEquals("   ", rejected.getPayload());
        assertEquals("request-002", rejected.getHeaders().get("businessKey"));
        assertNull(acceptedOutput.receive(0));
        assertNull(rejectedOutput.receive(0));
    }

    private static boolean hasCause(
            Throwable failure, Class<? extends Throwable> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

The assertions distinguish three outcomes: contract failure, valid output, and message routed to the rejection branch. Assertions do not rely solely on an output queue being empty, because an empty queue can also mean the message never reached the endpoint or was consumed by another subscriber.

In this configuration, processing over the input `DirectChannel` finishes before `send(...)` returns. Thus `receive(0)` is sufficient to verify no stray messages remain in queues lacking competing consumers. For asynchronous flows, synchronize on task completion and inspect error channels before concluding "no output"; a brief `receive` alone is not enough.

These test snippets are practice code for learners. They must be run in an environment with your project's compatible dependencies; this guide does not treat expected results as proof that tests were executed.

## 10. Relationship to Aggregators and Operational Observability

A message failing to reach downstream can affect multiple requests in the same group. For instance, a splitter emits three items sharing a correlation ID and an expected group size of three. If one item is discarded after the splitter, an aggregator releasing on group size may receive only two items and keep waiting.

When adding a filter to such a flow, revisit the group contract: filter before splitting when appropriate, emit a structured rejection result so the group still completes, or configure a release/expiry policy for incomplete groups. Do not arbitrarily lower expected counts, as that risks emitting incomplete results.

Operationally, track separate counts per branch:

```text
received → accepted → transformed successfully → sent to next step
        ↘ rejected
                    ↘ transformation failed
```

This is an observability model for the example, not an identity equation valid verbatim for every system. Retries, fan-out, splitters, and replays can make processing counts differ from business request counts. Use business keys to correlate the same request across checkpoints instead of mechanically comparing raw totals.

## 11. Diagnostic Sequence You Can Apply Immediately

1. Verify the request enters the right channel and the transformer endpoint is running.
2. Inspect every `return` branch, `catch` block, and library call inside the transformation method.
3. Separate cases returning `null`, producing an empty payload, and throwing exceptions.
4. Check the result destination: explicit output channel first, then the request's reply path.
5. Inspect channel types, subscribers, pollers, and competing consumers.
6. Trace steps downstream of the transformer, especially filters, routers, and flow-terminating handlers.
7. Cross-check the gateway contract: whether the caller expects a reply, accepts rejections, or sends one-way.
8. Write a test with failing input and verify one designed outcome: output, discard, or error.

A transformer producing no output must be analyzed through both its transformation contract and the message path. Once conversion, filtering, and termination decisions live in the right endpoints, root causes become easy to reproduce and each branch's outcome becomes straightforward to verify.
