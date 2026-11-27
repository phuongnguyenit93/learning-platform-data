# from PollableChannel

## Objectives and Scope

In the **Java DSL** chapter of **SPRING_INTEGRATION_CORE**, this lesson presents how to start an `IntegrationFlow` from a `PollableChannel`. This is how you connect an existing message queue to processing endpoints using Java DSL.

After this lesson, you will be able to:

- Distinguish declaring the input channel from configuring the message-fetching endpoint.
- Place the poller in the right spot when the first endpoint is a transformer, filter, or service activator.
- Explain the meaning of polling cadence, max messages per poll, and receive timeout.
- Observe valid messages, discarded messages, and processing errors on separate paths.
- Write bounded-timeout tests for an asynchronous processing flow.

The examples use Java 17+ and the Spring Integration 6.5 API. The primary class names belong to `spring-integration-core`; Java DSL is provided in this library. With Spring Boot, you can use `spring-boot-starter-integration` and let your project's dependency management handle versions. In older documentation, you may see `IntegrationFlows.from(...)`; the examples here use `IntegrationFlow.from(...)`.

## 1. What Capabilities Does PollableChannel Provide?

`PollableChannel` extends `MessageChannel` with message-receiving capability:

~~~java
public interface PollableChannel extends MessageChannel {

    Message<?> receive();

    Message<?> receive(long timeout);
}
~~~

`MessageChannel` provides the send operation; `PollableChannel` adds a receive operation where the consumer actively pulls data. When no message is received within the allowed time, `receive(long)` returns `null`. The timeout parameter is measured in milliseconds. See the [PollableChannel contract](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html).

`QueueChannel` is a common implementation: producers put messages into the queue, and consumers take them out later. A message in a queue is delivered to one consumer; adding consumers does not turn a queue into a broadcast mechanism delivering the same message to all receivers. Other implementations such as `PriorityChannel` and `RendezvousChannel` have different queuing or handoff rules. See [MessageChannel implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Example of creating a bounded queue:

~~~java
QueueChannel input = new QueueChannel(100);
~~~

The number `100` is the capacity of waiting messages. It does not specify the number of processing threads, retry counts, or messages per poll. You can inspect `getQueueSize()` and `getRemainingCapacity()` on `QueueChannel` to understand buffer state. See [QueueChannel API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/QueueChannel.html).

## 2. from(queue) Declares the Input, the Endpoint Performs Polling

Consider a declaration chain:

~~~java
IntegrationFlow.from(orderQueue)
        .transform(...)
        .filter(...)
        .channel(acceptedOrders)
        .get();
~~~

`from(orderQueue)` registers the input channel in the flow structure. This method does not call `receive()` immediately when Java executes the declaration line, nor does it generate orders by itself. Another producer still has to send a `Message<?>` to the queue.

In standard consumer configuration, the input channel type determines how the endpoint receives messages:

| Endpoint channel | Receiving mechanism | Endpoint typically created |
|---|---|---|
| `DirectChannel` | Invoked when a message is sent | `EventDrivenConsumer` |
| `QueueChannel`, a `PollableChannel` | Pulls messages on a schedule | `PollingConsumer` |

This is the endpoint selection mechanism of [ConsumerEndpointFactoryBean](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/config/ConsumerEndpointFactoryBean.html). This lesson covers the standard consumer mechanism, not reactive consumer configuration.

With a queue input, the poller must belong to the first endpoint **that actually consumes that queue**. If a transformer comes first, configure the poller on the transformer. If a filter or `handle` comes first, configure it on the corresponding endpoint. Methods `poller(...)`, `id(...)`, and `autoStartup(...)` are endpoint options; see [ConsumerEndpointSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Minimal example, given two already-supplied channel variables:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(
                String::trim,
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

`.get()` finishes building the flow definition. Only when the definition is registered as a bean and the application context starts does Spring Integration manage the components and their lifecycles. See [Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

## 3. Example Flow: Normalizing and Validating Order Codes

Suppose an application receives string order codes:

- `" order:ab-17 "` is normalized to `"ORDER:AB-17"` and goes to the accepted branch.
- `"invalid"` is normalized but fails the filter, so it goes to the rejected branch.
- A whitespace-only string causes a normalization error and goes to the error channel.

The rule of starting with `ORDER:` is purely illustrative. Real systems must validate the full structure and content of an order code.

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(message)"| Q["orderQueue: QueueChannel"]
    Q -->|"receive(timeout), per poller schedule"| T["Transformer: normalizeOrder"]
    T --> F{"Starts with ORDER:?"}
    F -->|"Yes"| A["acceptedOrders"]
    F -->|"No"| R["rejectedOrders"]
    T -.->|"Exception → ErrorMessage"| E["orderFlowErrors"]
~~~

In the diagram, the poller serves the `normalizeOrder` endpoint. The transformer and filter continue executing on the polling task's thread when there is no thread handoff between them.

### 3.1. Complete Java Configuration

~~~java
import java.time.Duration;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class PollableOrderConfig {

    @Bean
    public QueueChannel orderQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel acceptedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel rejectedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel orderFlowErrors() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow orderFlow(
            @Qualifier("orderQueue") PollableChannel orderQueue,
            @Qualifier("acceptedOrders") MessageChannel acceptedOrders,
            @Qualifier("rejectedOrders") MessageChannel rejectedOrders,
            @Qualifier("orderFlowErrors") MessageChannel orderFlowErrors) {

        return IntegrationFlow.from(orderQueue)
                .<String, String>transform(
                        PollableOrderConfig::normalize,
                        endpoint -> endpoint
                                .id("normalizeOrder")
                                .poller(
                                        Pollers.fixedDelay(
                                                Duration.ofMillis(200))
                                                .maxMessagesPerPoll(10)
                                                .receiveTimeout(0)
                                                .errorChannel(orderFlowErrors)))
                .<String>filter(
                        payload -> payload.startsWith("ORDER:"),
                        endpoint -> endpoint.discardChannel(rejectedOrders))
                .channel(acceptedOrders)
                .get();
    }

    private static String normalize(String raw) {
        String normalized = raw.strip().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Order code is blank");
        }

        return normalized;
    }
}
~~~

Points to read from the configuration:

1. `@Qualifier` identifies each queue unambiguously because the application context has multiple beans of the same type.
2. `proxyBeanMethods = false` pairs with passing beans as parameters; the flow uses the exact instances managed by Spring.
3. `normalizeOrder` is the endpoint ID, making it easy to locate the component when observing or controlling lifecycle.
4. The poller is configured on the transformer because the transformer's input is `orderQueue`.
5. The filter routes messages that fail the condition to `rejectedOrders`; rejection by a business rule does not mean throwing an exception.
6. `acceptedOrders` ends the flow with a queue holding results. The example does not yet declare a downstream endpoint reading from this result queue.

`Pollers` provides factories for triggers such as `fixedDelay`, `fixedRate`, and `cron`; overloads accepting `Duration` make the time unit explicit. See [Pollers API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/Pollers.html).

### 3.2. Sending a Message and Receiving the Result

The snippet below can be placed in a runner method. It requires imports for `AnnotationConfigApplicationContext`, `Message`, and `MessageBuilder`:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                PollableOrderConfig.class)) {

    var input = context.getBean("orderQueue", MessageChannel.class);
    var output = context.getBean("acceptedOrders", PollableChannel.class);

    var request = org.springframework.messaging.support.MessageBuilder
            .withPayload(" order:ab-17 ")
            .setHeader("traceId", "trace-001")
            .build();

    boolean queued = input.send(request, 500);

    if (!queued) {
        throw new IllegalStateException("Input queue did not accept the message");
    }

    org.springframework.messaging.Message<?> result = output.receive(3_000);

    if (result == null) {
        throw new IllegalStateException("No result received within timeout");
    }

    System.out.println(result.getPayload());               // ORDER:AB-17
    System.out.println(result.getHeaders().get("traceId")); // trace-001
}
~~~

The two wait operations have different meanings:

- `send(request, 500)` waits at most 500 ms to place the message into the input queue.
- `output.receive(3_000)` waits at most 3 seconds to retrieve one result message.

`send(...) == true` indicates that the channel accepted the message. When endpoints run behind a queue, that value does not prove business processing has completed. Verifying the outcome must rely on the output, errors, or a completion signal appropriate to the design.

## 4. Reading Poller Configuration Correctly

### 4.1. Cadence, Limits, and Wait Time

| Option | Question answered | Meaning in the example |
|---|---|---|
| `fixedDelay(200 ms)` | After a polling task ends, how long to wait before scheduling the next one? | Wait 200 ms, when not delegating to a separate executor |
| `maxMessagesPerPoll(10)` | At most how many messages does one polling task execution process? | At most 10; may be fewer if the queue runs empty |
| `receiveTimeout(0)` | How long will each fetch wait if the queue is empty? | Do not wait |
| `errorChannel(orderFlowErrors)` | Where are polling task errors sent by default? | The example's error queue |

`receiveTimeout` is in milliseconds and defaults to 1,000 ms in the 6.5 API. It does not bound the execution time of the transformer or HTTP calls inside a handler. See [PollerSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html).

With 25 messages already queued, no additional producers, no errors, and sequential consumer processing, a limit of 10 lets three polls take 10, 10, and 5 messages respectively. Messages still pass individually through the transformer and filter. `maxMessagesPerPoll` does not create a `List` holding the batch; to group messages for business logic, design a separate aggregator.

With a polling consumer, an unbounded configuration can keep pulling until `receive` returns `null`. A queue with continuous arrivals can keep a task holding the thread for a long time; using a positive limit makes each run's duration more predictable. See [Polling Consumer](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html#polling-consumer).

### 4.2. An Estimate to Understand Throughput

Suppose:

- Each message takes an average of 30 ms for the entire synchronous processing segment.
- Each poll retrieves a full batch of 10 messages.
- Fixed delay is 200 ms.
- There is no separate executor, and queue wait times and other overhead are ignored.

One processing batch takes roughly `10 × 30 = 300 ms`; adding the pause, the cycle reaches around 500 ms. Estimated throughput is:

~~~text
10 / (0.300 + 0.200) = 20 messages/second
~~~

This is an illustrative calculation from the assumptions above. In this scenario, inferring 50 messages/second solely from `10 / 0.200` ignores the 300 ms of processing. Raising the per-poll limit only reduces the share of idle time; it does not make the handler run faster by itself.

### 4.3. Choosing receiveTimeout Intentionally

`receiveTimeout(0)` fits when demonstrating trying to receive and yielding the thread if the queue is empty. Changing it to a positive number allows the task to wait for arriving messages, at the cost of holding the thread while waiting.

For example, `fixedDelay(200 ms)` combined with `receiveTimeout(1,000)` does not mean a poll always finishes in 200 ms. If the queue is empty, the receive call alone can wait one second. In particular, a poll cycle with multiple receive calls can wait on a later receive after already processing earlier messages.

## 5. Local Poller vs. Default Poller

The configuration style in `PollableOrderConfig` is a local poller: the parameters sit right next to the endpoint using them.

An alternative is declaring a global default poller. Any endpoint whose input is a `PollableChannel` and lacks its own poller will use this configuration. The bean must be named `PollerMetadata.DEFAULT_POLLER`. See [Global Default Poller](https://docs.spring.io/spring-integration/reference/6.5/endpoint.html#global-default-poller).

Example alternative bean method in a configuration class; requires importing `PollerMetadata` and `PeriodicTrigger`:

~~~java
@Bean(name = PollerMetadata.DEFAULT_POLLER)
public PollerMetadata defaultPoller() {
    PollerMetadata metadata = new PollerMetadata();
    metadata.setTrigger(new PeriodicTrigger(Duration.ofMillis(200)));
    metadata.setMaxMessagesPerPoll(10);
    metadata.setReceiveTimeout(0);
    return metadata;
}
~~~

Then a simple flow can be written as:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(String::trim)
        .channel(acceptedOrders)
        .get();
~~~

This is an alternative configuration option, not a requirement to remove the poller in the main example. If you remove the local poller from the main example, you also remove the local error channel configuration; you must redefine the desired error-handling path.

A local poller applies to the endpoint with its own configuration; the default poller serves as a fallback for remaining endpoints. There should be only one default poller in the same application context. Lacking both a local poller and a default poller can cause context startup to fail with a missing-poller error.

## 6. Choosing the Right from Overload

| Syntax | Meaning |
|---|---|
| `IntegrationFlow.from(queueBean)` | Uses the passed-in channel instance |
| `IntegrationFlow.from("orderQueue")` | References a channel bean by name; if the name does not exist yet, the DSL may create a `DirectChannel` |
| `IntegrationFlow.from(MessageChannels.queue("orderQueue", 100))` | Declares the channel via a queue spec inside the flow |
| `IntegrationFlow.from(messageSource, endpointConfigurer)` | Starts from a `MessageSource`, configuring the source's inbound adapter |

The overloads are described in [IntegrationFlow API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/IntegrationFlow.html).

When the problem requires an existing queue, passing a bean of type `PollableChannel` verifies that assumption right at the dependency injection site. Passing a name still works if the bean is declared properly, but the name `"orderQueue"` by itself does not guarantee the channel is a queue.

An easy mistake to make is copying inbound adapter configuration onto a channel:

~~~java
// There is no overload accepting a MessageChannel and an endpoint configuration lambda like this.
IntegrationFlow.from(orderQueue,
        endpoint -> endpoint.poller(Pollers.fixedDelay(200)));
~~~

With a channel, place the configuration on the consuming step:

~~~java
IntegrationFlow.from(orderQueue)
        .<String>handle(
                (payload, headers) -> payload.toUpperCase(Locale.ROOT),
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

`PollableChannel` and `MessageSource` both relate to receiving operations, yet they are two different abstractions. With an already-existing queue, using the channel directly as the input makes the junction with the producer clear in the flow.

## 7. Adding a Queue Mid-Flow Creates Another Polling Point

Example of a flow segment with channels already managed in the context:

~~~java
return IntegrationFlow.from(orderQueue)
        .<String, String>transform(
                String::trim,
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(10)
                                .receiveTimeout(0)))
        .channel(stagingQueue)
        .<String>handle(
                (payload, headers) -> payload.toUpperCase(Locale.ROOT),
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(5)
                                .receiveTimeout(0)))
        .channel(acceptedOrders)
        .get();
~~~

Here, assuming `stagingQueue` is also a `QueueChannel`:

- The transformer needs a poller to receive from `orderQueue`.
- The service activator needs a poller to receive from `stagingQueue`.
- `acceptedOrders` is only the destination holding the segment's output, with no downstream endpoint yet.

The transformer's poller does not automatically serve the downstream queue. When adding routers, filters, or aggregators, identify each endpoint's input channel before deciding where pollers belong. `PollingConsumer` is the component that connects a handler to a `PollableChannel`; see [PollingConsumer API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/endpoint/PollingConsumer.html).

## 8. Processing Threads, Errors, and Business Outcomes

### 8.1. A Queue Creates a Handoff Boundary

The producer runs `send` on the calling thread. Later, the endpoint pulls the message via its polling task and runs subsequent processing. Therefore:

- The producer can finish sending before the transformer runs.
- In the main example, the transformer and filter keep running synchronously inside the polling task.
- Increasing `maxMessagesPerPoll` does not create parallel processing.
- A messaging gateway sending a request into a queue can still wait for a reply if the gateway signature and configuration require one; having a queue does not automatically turn the call into fire-and-forget.

When adding a `taskExecutor` to a poller, the trigger schedule and actual task execution gain another delegation layer. Design thread count, executor queue, and rejection policy together; do not apply the sequential estimate from section 4.2 verbatim.

### 8.2. Errors Do Not Automatically Return to an Already-Completed send Call

In the example, a string that is empty after normalization causes the transformer to throw an exception. The error happens inside the polling task, after the producer has already placed the message into the queue.

With standard error handling, an exception from a polling task is wrapped into an `ErrorMessage`. A message's `errorChannel` header, when present, can select the error destination; otherwise, the error handler uses the configured default destination. The example sets that destination to `orderFlowErrors`. See [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Consequently, three outcomes must be observed separately:

| Input | Where to observe | What is confirmed |
|---|---|---|
| `" order:ab-17 "` | `acceptedOrders` | Payload normalized and passed filter |
| `"invalid"` | `rejectedOrders` | Filter actively discarded per rule |
| `"   "` | `orderFlowErrors` | An error occurred during processing |

Seeing a message on the error channel does not mean the system retried or recovered successfully. A consumer or operational mechanism is needed to keep processing the error queue.

With an in-memory `QueueChannel`, the message has already been removed from the queue before the handler finishes executing. A handler failure does not automatically put the message back onto the queue. When designing retries or error replay, determine which business operations are safe to repeat and use an order identifier key to prevent duplicate side effects.

## 9. Capacity, Ordering, and Durability

### 9.1. Full Queues Exert Backpressure on Producers

Suppose `orderQueue` has capacity 100 and the processing side is slower than the sending side. The queue will grow toward its limit. Producers must handle the return value of `send(message, timeout)`:

~~~java
boolean accepted = orderQueue.send(message, 500);

if (!accepted) {
    // For example: return a busy status to the caller or use a designed retry/re-intake mechanism.
}
~~~

Choose timeout behavior that matches the application's contract. Ignoring `false` can mislead the caller into thinking the request was accepted.

The output and error queues are also bounded. In this learning example, tests pull messages out of them; in long-running deployments, corresponding consumers are needed to prevent results from piling up. Blocking rules when a queue is full and timeout handling are described in [QueueChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html#queuechannel).

### 9.2. Dequeuing in Order Does Not Guarantee Completing in Order

A FIFO queue with a single sequential processing line keeps ordering straightforward. If multiple consumers read concurrently or processing runs in parallel, a message dequeued earlier can still finish later.

For example, order A calls a service taking 2 seconds while order B takes 50 ms. When processed concurrently, B's result can appear before A's. If business rules require per-customer ordering, design distribution and serialization around that key.

### 9.3. In-Memory Queues Are Not Durable Storage

The default queues in the example live in process memory. When the process stops, unprocessed messages have no recovery guarantee.

Configuring a transaction on a poller also does not automatically turn a RAM queue into a rollback-capable or durable resource. When data durability is required, choose an appropriate message store or broker and identify which resources participate in the transaction.

Transactions are typically bound to a thread; a queue or executor mid-flow creates a handoff boundary to another execution context. Commit and rollback scopes must be evaluated at each handoff boundary. See [Transaction Boundaries](https://docs.spring.io/spring-integration/reference/6.5/transactions.html#transaction-boundaries).

## 10. Testing Flows from a PollableChannel

Tests should assert observable outcomes, use bounded timeouts, and isolate state across test cases. You can use JUnit Jupiter with `spring-test`; in Spring Boot projects, the test suite is usually provided via `spring-boot-starter-test`.

The class below uses the `PollableOrderConfig` configuration from section 3. Place it in the same package or import the configuration class if placed in another package:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(PollableOrderConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class PollableOrderFlowTest {

    @Autowired
    @Qualifier("orderQueue")
    private MessageChannel input;

    @Autowired
    @Qualifier("acceptedOrders")
    private PollableChannel accepted;

    @Autowired
    @Qualifier("rejectedOrders")
    private PollableChannel rejected;

    @Autowired
    @Qualifier("orderFlowErrors")
    private PollableChannel errors;

    @Test
    void acceptsNormalizedOrderAndPreservesTraceId() {
        Message<String> request = MessageBuilder
                .withPayload(" order:ab-17 ")
                .setHeader("traceId", "trace-test-001")
                .build();

        assertTrue(input.send(request, 500));

        Message<?> result = accepted.receive(3_000);

        assertNotNull(result);
        assertEquals("ORDER:AB-17", result.getPayload());
        assertEquals(
                "trace-test-001",
                result.getHeaders().get("traceId"));
    }

    @Test
    void discardsPayloadThatFailsBusinessRule() {
        assertTrue(input.send(
                MessageBuilder.withPayload("invalid").build(),
                500));

        Message<?> discarded = rejected.receive(3_000);

        assertNotNull(discarded);
        assertEquals("INVALID", discarded.getPayload());
        assertNull(accepted.receive(0));
    }

    @Test
    void publishesErrorForBlankPayload() {
        assertTrue(input.send(
                MessageBuilder.withPayload("   ").build(),
                500));

        ErrorMessage error = assertInstanceOf(
                ErrorMessage.class,
                errors.receive(3_000));

        MessagingException failure = assertInstanceOf(
                MessagingException.class,
                error.getPayload());

        Message<?> failedMessage = failure.getFailedMessage();

        assertNotNull(failedMessage);
        assertEquals("   ", failedMessage.getPayload());
        assertNull(accepted.receive(0));
    }
}
~~~

How to read these tests:

- The success-path assertion checks both the payload and business header, rather than merely checking that `send` returned `true`.
- The discard branch verifies that the filter executed and the discarded message carries the normalized payload.
- The error branch reads the `ErrorMessage` and inspects the failed message; it does not expect the producer to catch business exceptions directly at `send`.
- Each method gets a fresh context after the previous context is marked dirty, preventing messages from an earlier case from leaking into a later case.
- `receive(3_000)` waits on the condition of data arriving with a deadline. No `Thread.sleep` or busy loop is needed.
- `receive(0)` only performs an instantaneous check of the output queue after observing the corresponding terminal branch; it is not general proof that no duplicate message could arrive later.

Do not call `orderQueue.receive(...)` inside a test to check the payload while the flow is actively consuming that same queue. That call will compete with the endpoint and may steal the message before the flow processes it.

## 11. Diagnosing Common Errors

| Symptom | Possibilities to check | Resolution |
|---|---|---|
| Context reports missing poller | Queue-reading endpoint has no local poller and no default poller exists | Configure the queue-consuming endpoint or add a default poller |
| Producer sends successfully, but queue does not drain | Endpoint not started, wrong channel instance, or blocked downstream | Check lifecycle, injected bean, and downstream queues |
| Queue drains, but no output appears | Filter dropped message, handler failed, or another consumer read the output | Check discard channel, error channel, and all consumers |
| Poller holds thread long under light load | Long receive timeout or handler performing a slow operation | Measure receive time and handler time; configure timeout on the right component |
| Increased maxMessagesPerPoll but no parallelism observed | Parameter only caps receives per task invocation | Evaluate threading or executor architecture as needed |
| Results arrive out of order | Multiple consumers or parallel processing | Identify ordering requirements and message distribution points |
| Data disappears on restart | Queue is stored in memory | Design appropriate durable storage |
| Flaky tests | Competing read on input, fixed sleep, or shared queue across tests | Observe outputs with timeouts and isolate test state |

To start a flow from a `PollableChannel`, identify the exact channel instance, the endpoint that pulls data, and that endpoint's poller configuration. Then define how to observe successes, discards, and errors. Those three decisions form the foundation for chaining transformers, routers, filters, or aggregators while still understanding the processing schedule and message path.
