# Synchronous and Asynchronous Errors

In Spring Integration, how an error reaches its handler depends on **the execution boundaries of the message flow**. For the exact same transformer throwing `NumberFormatException`, the sender might receive an exception immediately inside the `send()` call, or learn of the failure only through an `ErrorMessage` sent to another channel. To design this properly, determine who is running the handler, who is still waiting for a result, and which component is responsible for turning exceptions into messages.

This lesson belongs to the **Error handling** chapter of the **SPRING_INTEGRATION_CORE** module, connecting concepts of `Message`, `MessageChannel`, endpoints, gateways, and Java DSL with observing, handling, and testing errors.

After this lesson, you will be able to:

- Distinguish errors propagated along a call stack from errors represented as messages.
- Identify the impact of `DirectChannel`, `ExecutorChannel`, and `QueueChannel` on error paths.
- Read `ErrorMessage`, find the failed message, and retain business correlation details.
- Write tests proving errors took the right path rather than merely checking that `send()` returned.

## 1. Synchronous and Asynchronous Must Be Evaluated from a Specific Call Site

Suppose an application receives an item-quantity string, parses it into an integer, and updates an order. There are three ways to organize this:

~~~text
A. caller -> DirectChannel -> transformer -> handler
   One thread runs this entire segment.

B. caller -> ExecutorChannel | worker -> transformer -> handler
   The | mark is where work is handed off to an executor.

C. caller -> QueueChannel | poller -> transformer -> handler
   The sender puts the message into a queue; a poller retrieves it for processing.
~~~

In A, if the handler fails with nothing catching the error, the exception can return to the caller along the call stack. In B and C, an exception occurring during processing on another thread cannot automatically jump into a `try/catch` block that already exited on the sender's thread.

However, a handler downstream of a `DirectChannel` can still be running on a worker thread. For example:

~~~text
HTTP thread -> ExecutorChannel | worker -> DirectChannel -> transformer
~~~

The transformer runs synchronously relative to the worker calling it, yet asynchronously relative to the initial HTTP thread. Therefore, when analyzing errors, draw the full path from the entry point to the failure site and mark every thread transition.

### 1.1. How Do Channels Affect Execution?

| Component | Typical execution behavior | Implication for the original sender |
| --- | --- | --- |
| `DirectChannel` | Invokes subscriber directly on the sending thread | Handler can throw errors back to the `send()` call |
| `ExecutorChannel` with a thread pool | Hands dispatch off to an executor | Handler errors need a separate reporting path |
| `QueueChannel` with a polling endpoint | Buffers messages to be retrieved by a poller | Processing errors belong to the poller execution |
| `PublishSubscribeChannel` without an executor | Invokes subscribers on the sending thread | Publish-subscribe alone does not guarantee asynchrony |

`QueueChannel` does not create workers on its own. A `PollingConsumer`, or code actively calling `receive()`, is what pulls messages. If you receive and process messages yourself on the same thread, analyze that code's own call stack. Queue-backed channels store messages in memory by default; buffering does not mean durable persistence. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

`ExecutorChannel` also depends on the actual executor. An inline executor or a `CallerRunsPolicy` can run work on the sending thread in certain situations. Do not treat this possibility as a thread or transaction guarantee; see the [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

## 2. Synchronous Errors: Exceptions Follow the Call Stack

For a completely direct processing segment:

~~~java
try {
    inputChannel.send(message);
} catch (MessagingException exception) {
    // You can inspect failedMessage and the cause chain here.
}
~~~

When a transformer or service activator throws a business error, the framework typically wraps it in a messaging-layer exception. With a transformer, you may encounter `MessageTransformationException`; with other handlers, you may encounter `MessageHandlingException`. Both belong to the `MessagingException` family.

Consequently, catching `NumberFormatException` directly around `MessageChannel.send()` can miss wrapped errors. Distinguish:

- **Outer exception:** tells you which messaging layer detected the error.
- **Inner cause:** explains the reason, such as data that could not be parsed as a number.
- **`failedMessage`:** the message being processed at the failure point, if the exception supplies it.

Do not write operational logic hardcoded to a single wrapper class or an exact number of `getCause()` hops. The wrapping chain can change when adding a transformer, advice, or intermediate endpoint.

### 2.1. The `errorChannel` Header Does Not Automatically Catch All Synchronous Errors

Attaching a header as follows does not create an exception-catching boundary around the entire flow:

~~~java
Message<String> request = MessageBuilder.withPayload("not-a-number")
        .setHeader(MessageHeaders.ERROR_CHANNEL, errors)
        .build();

directInput.send(request);
~~~

If the caller sends directly into a `DirectChannel` and the transformer fails on that same call stack, the exception still propagates back to the caller. The header only identifies the error destination when a component actually catches the exception and publishes an `ErrorMessage`, such as the error handler of an executor, poller, or appropriately configured gateway. This is the distinction between **an error destination address** and **an error-catching mechanism**.

## 3. Asynchronous Errors: Exceptions Become Data on Another Path

When a Spring Integration task runs under an asynchronous error-handling mechanism, exceptions can be packaged inside an `ErrorMessage`. With the default mechanism, the request's `errorChannel` header takes precedence; if absent, the error goes to the global channel named `errorChannel`. Pollers also have an error-publishing mechanism. The default global channel is a `PublishSubscribeChannel` with a subscriber logging at ERROR level. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant I as ExecutorChannel
    participant W as Worker
    participant E as Error channel
    participant H as Error consumer
    C->>I: send(request)
    I->>W: Hand off task
    I-->>C: Send result or handoff failure
    W->>W: Execute transformer/handler
    W->>E: Publish ErrorMessage on processing failure
    E->>H: Deliver error message
~~~

The diagram depicts the roles of each party; it does not promise that the worker only starts after `send()` returns. The worker can execute very quickly and finish before then. The invariant is that an exception on the worker is not propagated directly via the sender thread's call stack.

### 3.1. Distinguishing Task-Handoff Errors from Task-Processing Errors

An asynchronous flow can still cause `send()` to fail immediately:

| Stage | Example failure | Where to observe |
| --- | --- | --- |
| Before or during task handoff | Interceptor rejects, executor rejects task, channel rejects message | Result or exception at the send call |
| Enqueueing into queue | Queue full and send timeout elapsed | Return value of `send(message, timeout)` and caller policy |
| Running handler on worker/poller | Data parsing fails, service throws exception | Task's error-handling path, usually an error flow |
| Publishing or consuming error | Error channel fails to accept message, error handler itself fails | Logs, metrics, and fallback mechanism for the error path |

Therefore, a `try/catch` around the send operation remains useful in an asynchronous flow. It guards the task-handoff step; to know the business processing outcome, you must have a corresponding reply, task result, or error-reporting channel.

### 3.2. What Does `send() == true` Mean?

In a flow using a queue or executor, this value typically indicates that the message was accepted by the channel per its send mechanics. It does not prove that:

- Data passed validation.
- The order was updated successfully.
- The worker's transaction committed.
- The message can be recovered if the process stops.

Even a synchronous flow can have a filter that discards the message or a handler that performs an action producing no reply. Send results belong to the channel contract; business outcomes belong to the application contract.

### 3.3. An Error Flow Can Run Synchronously on the Worker

The term "asynchronous error" describes the relationship to the original caller. If the worker sends an `ErrorMessage` to a `DirectChannel`, the error handler can run right on that worker thread. If the error channel is a `QueueChannel`, another consumer will handle it upon receiving the message.

Thus, an error handler that logs slowly or calls a slow alerting service can tie up the worker's time. Select error-path channels and resource limits according to actual load.

Manually calling `executor.execute(...)`, spawning threads, or launching a `CompletableFuture` inside a service does not automatically wire into Spring Integration's error flow. When work detaches from framework-managed invocations, the application must design how results or exceptions return to an observed mechanism.

## 4. Reading `ErrorMessage` and Recovering Failure Context

`ErrorMessage` is a `Message<Throwable>`. The payload is typically a `MessagingException`, though do not cast unconditionally—it can carry another `Throwable`. Two pieces of context to distinguish are:

| Information | How to access | Meaning |
| --- | --- | --- |
| Published exception | `errorMessage.getPayload()` | Starting point for inspecting wrappers and causes |
| Message at point of failure | `messagingException.getFailedMessage()` | Payload and headers the endpoint was processing |
| Original message, if supplied | `errorMessage.getOriginalMessage()` | Message in the error-message creation context; may be `null` |

`failedMessage` may have undergone transformations and thus differ from the initial input message. `originalMessage` is optional and is also not guaranteed to always be the very first request in the entire system. See the [ErrorMessage API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html).

Example method reading a correlation ID from the failed message:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

static Object findBusinessRequestId(ErrorMessage errorMessage) {
    Throwable current = errorMessage.getPayload();
    while (current != null) {
        if (current instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            if (failed != null) {
                Object requestId = failed.getHeaders().get("businessRequestId");
                if (requestId != null) {
                    return requestId;
                }
            }
        }
        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    Message<?> original = errorMessage.getOriginalMessage();
    return original == null
            ? null
            : original.getHeaders().get("businessRequestId");
}
~~~

This method uses Java 17 syntax and targets typical application exception cause chains. Tolerate a `null` result, since errors can happen before a message exists or when context was not retained.

Do not assume all business headers were copied onto the `ErrorMessage` headers. Attach the correlation ID at the request ingress boundary, preserve it across message transformations, and retrieve it from the failed message when recording errors. For messages crossing a broker or message store, do not rely on serializing a channel object inside a header; use a header-mapping and error-addressing strategy suited to the system boundary.

## 5. Java DSL Practice: Same Error Across Three Channel Types

The following example parses a string into an integer. Input `"42"` produces `42`; `"abc"` causes the transformer to fail.

The application requires `spring-integration-core`; tests require `spring-test`, JUnit Jupiter, and its matching test engine. Use synchronized Spring versions via your project's dependency management. The example needs no Spring Boot, broker, or database; the Java syntax uses Java 17 or higher and requires a JDK compatible with your chosen Spring version.

Place the configuration and test class in the same package, or import the configuration class. The class names here serve the practice exercise and do not require changing an existing module's structure.

### 5.1. Configuring the Three Flows

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class ErrorBoundaryConfig {

    @Bean
    public DirectChannel syncInput() {
        return new DirectChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("integration-worker-");
        return executor;
    }

    @Bean
    public ExecutorChannel asyncInput(
            @Qualifier("workerExecutor") ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public QueueChannel queuedInput() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel parsedResults() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel asyncErrors() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel pollerErrors() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow syncParseFlow(
            @Qualifier("syncInput") MessageChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow asyncParseFlow(
            @Qualifier("asyncInput") MessageChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow queuedParseFlow(
            @Qualifier("queuedInput") QueueChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofMillis(50))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("pollerErrors")))
                .channel(results)
                .get();
    }
}
~~~

Spring manages creating and shutting down `ThreadPoolTaskExecutor` because it is a bean. All three flows share the same transformation so that only the execution boundary changes.

In this configuration:

- `syncInput` invokes the transformer directly on the sending thread.
- `asyncInput` hands work to a worker; the test will attach a header pointing to `asyncErrors`.
- `queuedInput` is read by a polling endpoint; the poller is configured with a dedicated default error channel `pollerErrors`.
- `parsedResults` holds outputs so tests can observe completed processing.

The error and result channels use bounded queues so the exercise can easily observe them via `receive(timeout)`. They have no background business consumers running. In a real application, there must be consumers, full-queue policies, and suitable persistence; sending without draining will fill the queues.

The poller belongs to the endpoint consuming `queuedInput`, not to `QueueChannel` itself. `errorChannel(...)` is a poller option; see the [PollerSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html). Distinguish polling endpoints from polled message sources in [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

### 5.2. Testing the Error Propagation Paths

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ErrorBoundaryConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ErrorBoundaryTest {

    @Autowired
    @Qualifier("syncInput")
    MessageChannel syncInput;

    @Autowired
    @Qualifier("asyncInput")
    MessageChannel asyncInput;

    @Autowired
    @Qualifier("queuedInput")
    QueueChannel queuedInput;

    @Autowired
    @Qualifier("parsedResults")
    QueueChannel parsedResults;

    @Autowired
    @Qualifier("asyncErrors")
    QueueChannel asyncErrors;

    @Autowired
    @Qualifier("pollerErrors")
    QueueChannel pollerErrors;

    @Test
    void directFailureReturnsToSenderEvenWithErrorHeader() {
        Message<String> request = badRequest("SYNC-001", asyncErrors);

        MessagingException exception = assertThrows(
                MessagingException.class,
                () -> syncInput.send(request, 1_000));

        assertInstanceOf(NumberFormatException.class, rootCause(exception));
        Message<?> failed = exception.getFailedMessage();
        assertNotNull(failed);
        assertEquals("SYNC-001", failed.getHeaders().get("businessRequestId"));
        assertNull(asyncErrors.receive(0));
        assertNull(parsedResults.receive(0));
    }

    @Test
    void executorFailureArrivesAtRequestErrorChannel() {
        Message<String> request = badRequest("ASYNC-001", asyncErrors);

        assertTrue(asyncInput.send(request, 1_000));

        ErrorMessage error = receiveError(asyncErrors);
        assertFailure(error, "ASYNC-001");
        assertNull(parsedResults.receive(0));
    }

    @Test
    void executorSuccessIsObservedThroughResultMessage() {
        Message<String> request = MessageBuilder.withPayload("42")
                .setHeader("businessRequestId", "ASYNC-OK-001")
                .setHeader(MessageHeaders.ERROR_CHANNEL, asyncErrors)
                .build();

        assertTrue(asyncInput.send(request, 1_000));

        Message<?> result = parsedResults.receive(3_000);
        assertNotNull(result);
        assertEquals(42, result.getPayload());
        assertEquals("ASYNC-OK-001",
                result.getHeaders().get("businessRequestId"));
        assertNull(asyncErrors.receive(0));
    }

    @Test
    void pollingFailureArrivesAtConfiguredPollerChannel() {
        Message<String> request = MessageBuilder.withPayload("abc")
                .setHeader("businessRequestId", "POLL-001")
                .build();

        assertTrue(queuedInput.send(request, 1_000));

        ErrorMessage error = receiveError(pollerErrors);
        assertFailure(error, "POLL-001");
        assertNull(parsedResults.receive(0));
    }

    private static Message<String> badRequest(
            String requestId, MessageChannel errors) {
        return MessageBuilder.withPayload("abc")
                .setHeader("businessRequestId", requestId)
                .setHeader(MessageHeaders.ERROR_CHANNEL, errors)
                .build();
    }

    private static ErrorMessage receiveError(QueueChannel errors) {
        Message<?> message = errors.receive(3_000);
        assertNotNull(message, "No error message received within timeout");
        return assertInstanceOf(ErrorMessage.class, message);
    }

    private static void assertFailure(ErrorMessage error, String requestId) {
        assertInstanceOf(NumberFormatException.class,
                rootCause(error.getPayload()));
        MessagingException exception = assertInstanceOf(
                MessagingException.class, error.getPayload());
        Message<?> failed = exception.getFailedMessage();
        assertNotNull(failed);
        assertEquals("abc", failed.getPayload());
        assertEquals(requestId, failed.getHeaders().get("businessRequestId"));
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

The assertions on the wrapper and `failedMessage` suit the specific transformer in this lesson. Shared error-reading functions used across multiple endpoint types should be more flexible, as in the section 4 example.

`@DirtiesContext` recreates the context after each test so queues, schedulers, and executors do not leak state to subsequent tests. This is a simple choice for an exercise; larger test suites can use other isolation mechanisms to reduce startup time. Tests sharing these queues must not run in parallel against the same context.

Do not use `Thread.sleep()` to guess when a worker is done. `receive(3_000)` waits with a bound specifically for the event the test needs to observe. The timeout in a test is a failure-detection threshold, not an application SLA. In practice, pick a threshold suited to your CI environment.

The success test receives a result message rather than inferring success merely from the absence of errors. The `receive(0)` checks only inspect current state after an observed event; they do not prove no error will ever occur in the future. This configuration has no retries or follow-up background work after the result.

The example only needs Spring Test because it uses real channels. When you need to substitute handlers or prevent inbound adapters from connecting externally, you can use `spring-integration-test` with `MockIntegrationContext`; see [Testing support](https://docs.spring.io/spring-integration/reference/testing.html).

## 6. Pollers Have an Additional Error Boundary to Understand

A poller can fail at two different points:

1. **While polling data:** the data source throws an exception before a message is created. At this point there may be no `failedMessage` and no request headers from which to choose an error channel.
2. **While processing a received message:** a downstream transformer, router, or service activator throws an exception. Here the framework can typically attach the failed message.

In the example, the failure occurs at the second point. The request has no `errorChannel` header, so the default error path configured on the poller is `pollerErrors`.

With the standard `MessagePublishingErrorHandler`, an `errorChannel` header read from the failed message can take precedence over the error handler's default channel. Do not assume declaring a channel on a poller always overrides every header. If an application configures a custom `ErrorHandler`, check that handler's own contract. The API allows setting the default channel via `setDefaultErrorChannel` or `setDefaultErrorChannelName`; see the [MessagePublishingErrorHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html).

This also explains why a polling source needs a default error channel: you cannot expect a message that has not yet been created to already carry an error destination address.

## 7. Gateways Provide a Different Error-Observation Contract Than `send()`

A messaging gateway can keep the caller waiting for a reply even when the internal flow includes an `ExecutorChannel` or polling endpoint. When the reply/error path is preserved, the framework can route errors from the asynchronous branch back to the waiting gateway and throw them to the caller. This is an exchange of error messages through gateway infrastructure, not an exception jumping between two call stacks.

A default gateway can unwrap wrappers before throwing errors; when configured with an `errorChannel`, it can also send the error through a flow that converts it into a reply matching the return type. Thus, for the exact same business error, a gateway caller and a caller sending directly to a channel may receive different exception classes. See [Messaging Gateways — Error Handling](https://docs.spring.io/spring-integration/reference/gateway.html#error-handling).

### 7.1. Clearly Defining the Contract at the Application Boundary

| Call pattern | What the caller really needs to know | Error-path design |
| --- | --- | --- |
| One-way send to an asynchronous channel | Whether acceptance succeeded | Check the send step; record processing outcomes via error flow or task status |
| Request-reply gateway returning a DTO | Success or error per return contract | Maintain reply/error path; map errors to DTO if required by contract |
| Gateway returning an async type | Result will complete after the call | Observe completion and exceptional completion per return type and gateway config |

A `void`-returning gateway is not a guarantee that work runs asynchronously. Conversely, a DTO-returning gateway can still wait for a flow executing on a worker. Separate **API return type**, **thread placement**, and **error-reporting mechanism** when reading configurations.

### 7.2. A Logging-Only Error Handler May Fail to Produce a Reply

Suppose the caller expects an `OrderResult`, yet the error flow merely logs and terminates. You must define what the caller receives when no reply arrives: timeout expiration, a null value, or an exception per configuration. A log entry does not automatically become a business reply.

If you choose to map errors to results, define a clear DTO, such as:

~~~java
public record OrderResult(
        String orderId,
        boolean successful,
        String errorCode) {
}
~~~

For example, with invalid quantity data, the error flow returns `successful=false` and code `INVALID_QUANTITY`. Do not return a valid default number like `0` and let the caller mistakenly believe processing succeeded. `orderId` context should be taken from the failed message or preserved correlation data.

### 7.3. Timeouts Do Not Cancel In-Flight Work

With a flow running completely synchronously on the caller's thread, `replyTimeout` cannot interrupt a service running long on that very call stack. When the flow hands off to another thread and the gateway waits for a reply, the timeout bounds waiting time; the worker can still finish afterward. Therefore, configure deadlines for I/O operations and mechanisms to handle late-arriving results if business logic requires it. These scenarios are described in [Gateway Behavior When No response Arrives](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

For ordering or payment, a caller timing out is not sufficient proof that the operation never occurred. A retry call must be tied to a business key and duplicate-prevention strategy.

## 8. Thread Boundaries Also Affect Transactions and Retries

### 8.1. Transactions Do Not Automatically Follow Messages to Workers

A transaction bound to the caller thread can cover a direct processing chain if operations participate in that transaction. When work is handed off to a worker, do not assume the old transaction continues covering the handler. If the handler needs a transaction, establish the transaction at the appropriate processing boundary on the worker or poller.

Example:

~~~text
caller: starts transaction -> sends to ExecutorChannel -> commits
worker: picks up work -> database update fails
~~~

A worker failure does not automatically roll back a transaction the caller already committed. Similarly, sending an `ErrorMessage` does not automatically undo an email, API call, or database record already written successfully earlier. For multi-step workflows, design states, idempotency, or business compensating actions. The basis for `ExecutorChannel` not sharing transactions between sender and handler is stated in the [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

### 8.2. Routing Errors to an Error Channel Does Not Mean Retry

A logging error consumer only creates observability. If you want retries, configure a retry policy, retry scope, and behavior when attempts are exhausted. `RequestHandlerRetryAdvice` can wrap a handler; when a recovery callback is present, the final behavior can differ from continuing to throw the exception. See [Provided Advice Classes — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html#retry-advice).

Before adding retries to the order-update example, answer:

- Can a data error like `NumberFormatException` be resolved merely by trying again? Usually the data must be fixed.
- If an external call already succeeded while the response was lost, will retrying create duplicate orders?
- Does retry re-execute only the failing handler, or re-run segments with side effects?
- After the final attempt, is the error rethrown, routed to a recovery flow, or stored for manual handling?

Do not automatically send every failed message right back to the main input without limits. That approach can create rapid loops, saturate workers, and overflow error queues.

## 9. Organizing Error Flows for Operations

An asynchronous error must be turned into actionable information. For an order-update flow, an error record should include:

| Field | Purpose |
| --- | --- |
| `businessRequestId` or `orderId` | Links to the request known by users |
| Message ID and endpoint/flow | Locates the failed processing step |
| Wrapper type and cause | Distinguishes infrastructure errors from data/business errors |
| Timestamp, attempt count, final status | Distinguishes in-progress retries from permanent failure |
| Reference to data needed for recovery | Enables controlled inspection or reprocessing |

Log only necessary and appropriate fields; for payloads containing personal or authentication data, prefer identifiers and masked fields over logging the entire message.

Error handlers can fail too. If one calls an alerting system that is down, the initial error-reporting path can keep failing. Keep the minimal recording step simple, bound wait times on dependencies, and have fallback storage or metrics. Avoid looping errors from an error handler back into that same flow.

In particular, when turning an error into a normal reply message, upstream may consider the work handled per contract. If using a source with acknowledgments or transactions, verify the consequences for commit, rollback, and redelivery on that specific adapter. The practice exercise uses in-memory queues and thus does not simulate broker guarantees.

## 10. Common Misconceptions

| Claim | Correction needed |
| --- | --- |
| "Having an `errorChannel` header means every exception goes there" | The header is an address; there must be a component catching and publishing errors |
| "In an asynchronous flow, `send()` cannot throw errors" | Sending or task handoff can still fail synchronously |
| "Having a `DirectChannel` means the whole flow runs on the caller" | It runs on the current sending thread, which could be a worker after another boundary |
| "Error channels always spawn another thread" | Execution depends on the channel type and the error path's consumers |
| "No exception at the caller means processing succeeded" | Work may merely be accepted, not yet run, or errors went down another path |
| "When a gateway times out, the worker stops" | Timing out is not a handler cancellation mechanism |
| "`ErrorMessage` preserves all request headers directly" | Read the supplied context, specifically `failedMessage` and `originalMessage` |
| "Logging is enough for order errors" | You also need business status, correlation, and a recovery plan |

## 11. Reinforcement Exercises

1. In the `executorFailureArrivesAtRequestErrorChannel` test, change the header value from the `asyncErrors` object to the bean name `"asyncErrors"`. Verify the framework still resolves the channel and the error carries the right `businessRequestId`.
2. Add a test sending a failing message to `queuedInput` with a header pointing to `asyncErrors`. With the standard error handler, verify the header takes precedence and `pollerErrors` does not receive this request's error.
3. Add a handler after the transformer to simulate updating an order. Prove that handler does not run when the transformer fails, without inferring that side effects prior to the transformer are rolled back.
4. Design a task result with three states: `ACCEPTED`, `SUCCEEDED`, `FAILED`. Specify which events are allowed to transition states rather than immediately assigning `SUCCEEDED` from `send()`.
5. Draw a flow containing a filter and a request-reply gateway. Show what happens when the filter drops a message without producing a reply, then propose how to represent data rejection under the gateway's contract.

When analyzing a new flow yourself, identify the send point, thread-handoff boundaries, where exceptions are caught, and who is still waiting for results. Then choose the appropriate observation mechanism: exception at the caller, contract reply, asynchronous completion outcome, or an `ErrorMessage` with sufficient context to process.
