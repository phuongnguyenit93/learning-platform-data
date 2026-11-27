# Splitter Output Channel

## 1. Objectives and Context

In the **Splitter** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains where child messages are sent after splitting an input message. This is the connection point between data-splitting logic and downstream endpoints such as transformers, routers, filters, service activators, or aggregators.

After this lesson, you will be able to:

- Identify the splitter's output channel in Java DSL and annotation configurations.
- Distinguish a directly configured channel from the `replyChannel` header.
- Choose a channel type matching synchronous processing, buffering, or executor-based processing needs.
- Track child messages using correlation and sequence headers.
- Recognize delivery failures, partial batch sends, and the need to aggregate results before replying to a gateway.
- Write tests that directly observe messages appearing on the output channel.

Examples use Spring Integration 6.5 APIs and Java 17. The project requires `org.springframework.integration:spring-integration-core`; tests use JUnit Jupiter. Dependency versions should follow your project's dependency management to stay compatible with the Spring Framework version in use.

## 2. The Output Channel Receives Each Child Message

Suppose a request contains three product codes:

~~~text
Input message:
  payload = ["BOOK", "PEN", "BAG"]
  headers.batchId = "B-42"
~~~

After splitting, the splitter sends three separate messages:

~~~text
Message 1: payload = "BOOK"
Message 2: payload = "PEN"
Message 3: payload = "BAG"
~~~

`outputChannel` is the destination the splitter uses to send those messages. One output channel can receive multiple `send(...)` calls while processing a single input message. The [Spring Integration Splitter documentation](https://docs.spring.io/spring-integration/reference/6.5/splitter.html) describes the model of splitting one message into multiple parts and sending each part for independent processing.

~~~mermaid
flowchart LR
    A["Message containing List of 3 SKUs"] --> B["Channel batches"]
    B --> C["Splitter"]
    C -->|"Message BOOK"| D["Output channel lineItems"]
    C -->|"Message PEN"| D
    C -->|"Message BAG"| D
    D --> E["Endpoint processing one SKU"]
~~~

In this example, `lineItems` receives three messages with `String` payloads. It does not receive a single message whose payload is the whole three-element list.

Nor is there an automatic rule sending the first element to channel A and the second to channel B. If you need to pick destinations by element content, place a router after the splitter. If every subscriber must receive every element, choose a channel with publish-subscribe semantics.

Splitting into multiple messages also does not determine the number of processing threads. A flow using only `DirectChannel` can still execute all work sequentially on the initial sending thread.

## 3. How Does a Splitter Determine the Send Destination?

### 3.1. Explicitly Declared Output Channel

In a typical flow, configuring the output channel directly is the easiest approach to observe:

~~~java
IntegrationFlow.from("batches")
        .split()
        .channel("lineItems")
        .get();
~~~

At this position, `.channel("lineItems")` connects the splitter's output to the `lineItems` channel. This is a structural configuration of the flow.

Equivalent configuration styles include:

| Configuration style | Declaration location |
|---|---|
| Java DSL | `.split().channel("lineItems")` |
| Annotation | `@Splitter(outputChannel = "lineItems")` |
| XML | `<int:splitter ... output-channel="lineItems"/>` |
| Handler Java config | `splitter.setOutputChannel(channel)` or `setOutputChannelName("lineItems")` |

Do not configure both a channel object and an output channel name on the same handler simultaneously. When using the DSL, let the DSL wire flow steps together rather than assigning a different destination inside the handler and declaring another destination afterward.

### 3.2. Fallback via the replyChannel Header

Without a direct output channel, the splitter can use `replyChannel` to find where to send results.

In flows not using a Routing Slip, the resolution order is:

1. Use the configured output channel if present.
2. Otherwise, look for `replyChannel` on the request message.
3. If still absent and the result is a message carrying its own `replyChannel`, that header may be used.
4. If a result must be sent and no destination can be resolved, a destination resolution error occurs.

`replyChannel` can be a `MessageChannel` instance or a `String` channel name. These rules appear in [AbstractMessageProducingHandler of Spring Integration 6.5.0](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/handler/AbstractMessageProducingHandler.java). Routing Slip has its own destination selection mechanism when no output channel is declared; the examples in this lesson do not use that mechanism.

Example building a request with a reply destination:

~~~java
QueueChannel replies = new QueueChannel();

Message<List<String>> request = MessageBuilder
        .withPayload(List.of("BOOK", "PEN"))
        .setReplyChannel(replies)
        .build();
~~~

If the splitter has no output channel, child messages can be sent to `replies`. If the splitter is already wired to `lineItems`, child messages go to `lineItems`; the `replyChannel` header can still be preserved so a downstream endpoint returns the final result.

Setting an arbitrary custom header named `outputChannel` is not equivalent to configuring the endpoint's output channel.

### 3.3. Distinguishing Cases with No Output Data

| Case | Behavior to understand |
|---|---|
| Child messages exist, but no send destination | Destination resolution failure; typically `DestinationResolutionException` as cause |
| Splitter returns an empty collection | No child messages to send; can route original request to discard channel if configured |
| Split logic returns `null` | Terminates the branch by default; if `requiresReply` is enabled, consider missing-reply error |
| Output is `nullChannel` | Child messages are sent to the discarding channel |
| Output is a queue with no consumer | Messages may be sitting in the queue, unprocessed |

An empty collection differs from a collection containing a message with an empty payload. When there are zero elements, no "completed" message automatically appears.

## 4. Complete Example: From Batch to a Queue of Individual SKUs

The following configuration explicitly declares both input and output channels. `batches` is a `DirectChannel` to receive requests; `lineItems` is a `QueueChannel` to observe results.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class SplitterOutputConfig {

    @Bean
    public DirectChannel batches() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel lineItems() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow batchToItems() {
        return IntegrationFlow.from("batches")
                .split()
                .channel("lineItems")
                .get();
    }
}
~~~

`.split()` here uses the default splitter with a `List<String>` payload. Each element becomes the payload of one child message.

The program below starts a Spring context, sends a batch, and reads the output messages. Place this class in the same package as `SplitterOutputConfig`.

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class SplitterOutputDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            DirectChannel input =
                    context.getBean("batches", DirectChannel.class);
            QueueChannel output =
                    context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK", "PEN", "BAG"))
                    .setHeader("batchId", "B-42")
                    .build();

            input.send(request);

            for (int i = 0; i < 3; i++) {
                Message<?> item = output.receive(1000);

                if (item == null) {
                    throw new IllegalStateException(
                            "Missing child message #" + (i + 1));
                }

                Object number = item.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
                Object size = item.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE);

                System.out.printf(
                        "%s | batchId=%s | sequence=%s/%s%n",
                        item.getPayload(),
                        item.getHeaders().get("batchId"),
                        number,
                        size);
            }
        }
    }
}
~~~

Expected output:

~~~text
BOOK | batchId=B-42 | sequence=1/3
PEN  | batchId=B-42 | sequence=2/3
BAG  | batchId=B-42 | sequence=3/3
~~~

Printed whitespace padding may vary; the three payloads and sequence values are what to observe.

In this configuration:

- One request enters `batches`.
- The splitter is invoked on the request-sending thread.
- Three child messages are placed sequentially into `lineItems`.
- The program manually calls `receive(...)` to retrieve each message.
- No business endpoint is automatically consuming messages from the queue yet.

The queue limit of `100` is chosen for this exercise. With batches larger than capacity and no concurrent consumer, sending can block and then fail on timeout.

## 5. Explicit Channels vs. Implicit Channels in Java DSL

### 5.1. Connecting Directly to an Endpoint

You do not have to name every channel:

~~~java
@Bean
public IntegrationFlow normalizeItems() {
    return IntegrationFlow.from("rawBatches")
            .split()
            .transform(String.class, value -> value.strip().toUpperCase(
                    java.util.Locale.ROOT))
            .channel("normalizedItems")
            .get();
}
~~~

This is an illustrative alternative configuration; `normalizedItems` must be declared according to how you intend to receive results.

Between the splitter and transformer, the DSL wires an implicit channel, typically a `DirectChannel`. The splitter's direct output channel is that implicit channel in front of the transformer. `normalizedItems` comes after the transformer, so it is the transformer's output.

~~~text
rawBatches
  -> splitter
  -> implicit channel
  -> transformer
  -> normalizedItems
~~~

Reading the flow this way prevents confusing any subsequent `.channel(...)` with the splitter's direct output. The Java DSL builds channels and endpoints in the Spring context, as explained in the [Java DSL documentation](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

### 5.2. Placing Named Channels at Observable Boundaries

A named channel is helpful when:

- Another flow needs to receive messages from that point.
- Tests need to capture or inspect messages.
- Interceptors, wire taps, or traffic monitoring are needed at a specific boundary.
- You want to change delivery semantics by swapping the channel type.

Channel names expressing responsibility, such as `lineItems` or `validatedItems`, are usually easier to read than positional names like `splitterOutput3`.

### 5.3. Configuration with Annotations

The splitter flow in Section 4 can be replaced by an annotation-based endpoint:

~~~java
import java.util.List;

import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Splitter;

@MessageEndpoint
public class BatchSplitter {

    @Splitter(
            inputChannel = "batches",
            outputChannel = "lineItems")
    public List<String> split(List<String> items) {
        return items;
    }
}
~~~

The method returns a list; the splitter adapter handles creating and sending child messages. `BatchSplitter` must be registered via component scanning or `@Bean`, while keeping the necessary channels.

This is an **alternative** to `batchToItems()`. Registering both on the same `DirectChannel batches` creates two competing consumers. Input messages could be distributed between them, making observations inconsistent with the exercise's intent.

The [@Splitter API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/annotation/Splitter.html) also provides `applySequence`, `sendTimeout`, and poller configuration for the endpoint.

## 6. Output Channel Type Changes End-to-End Flow Behavior

The name `outputChannel` describes only the role. The concrete channel class determines how messages are handed to consumers.

| Channel type | How each child message is delivered | When to apply |
|---|---|---|
| `DirectChannel` | Invokes one subscriber on the sending thread | Synchronous processing, short step chains |
| `ExecutorChannel` | Hands work to an executor; typically runs on a worker thread | Need thread decoupling or bounded concurrency |
| `QueueChannel` | Enqueues messages for a consumer to retrieve later | Need buffering and decoupling send rate from receive rate |
| `PublishSubscribeChannel` | Broadcasts each message to all subscribers | Each element needs to trigger multiple branches |
| `nullChannel` | Accepts and discards messages | Intentionally terminating a branch |

`DirectChannel` and `QueueChannel` have point-to-point semantics: one message is successfully consumed by one consumer, even if multiple consumers are registered or polling the queue. Dispatcher failover can try another subscriber if an earlier subscriber throws an exception.

With `PublishSubscribeChannel`, each split element is broadcast to all subscribers. For instance, three elements and two subscribers yield six subscriber invocations when all deliveries succeed.

`ExecutorChannel` delegates delivery through an executor; the executor's rejection policy can cause the sending thread itself to run the task under overload. Completion order must therefore be designed explicitly. These semantics are described in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 6.1. Emission Order Differs from Completion Order

With a `List` batch, a standard splitter iterates in list order. If all downstream steps are synchronous and single-pathed, each element finishes before the next element is sent.

With parallel workers, the following is normal:

~~~text
Emission order:     BOOK -> PEN -> BAG
Completion order:   PEN  -> BAG -> BOOK
sequenceNumber:     2      3      1
~~~

`sequenceNumber` describes the element's position in the split, not a constraint forcing the scheduler to finish in that order. If business logic requires sequential execution, design a sequential consumer or use an appropriate sorting mechanism.

### 6.2. Impact on Processing Latency

Suppose a batch has 100 elements and each requires roughly 50 ms of synchronous work. On a single sequential path, that work alone takes approximately 5 seconds, excluding overhead.

Switching to a queue allows the send call to return early while space remains. Returning at that point means the message was accepted by the queue; it does not prove the entire batch has completed business processing.

## 7. QueueChannel Output: Consumers, Pollers, and Wait Limits

### 7.1. Poller Attached to the Queue-Reading Endpoint

Setting a `QueueChannel` as output does not create a consumer automatically. You can poll manually with `receive(...)` as in Section 4, or attach an endpoint with a poller.

The following example is a standalone supplementary configuration. Place the `@Bean` methods inside a `@Configuration` class with `@EnableIntegration` and import `QueueChannel`, `IntegrationFlow`, and `Pollers`:

~~~java
import org.springframework.integration.dsl.Pollers;

@Bean
public QueueChannel queuedItems() {
    return new QueueChannel(32);
}

@Bean
public IntegrationFlow queueingFlow() {
    return IntegrationFlow.from("queuedBatches")
            .splitWith(spec -> spec
                    .applySequence(true)
                    .sendTimeout(500))
            .channel("queuedItems")
            .get();
}

@Bean
public IntegrationFlow consumingFlow() {
    return IntegrationFlow.from("queuedItems")
            .handle(message -> {
                System.out.println(
                        "Processing: " + message.getPayload());
            }, endpoint -> endpoint.poller(
                    Pollers.fixedDelay(100)
                            .maxMessagesPerPoll(10)))
            .get();
}
~~~

`queuedBatches` is the entry point of this example. The consumer in `consumingFlow` uses a poller to fetch at most 10 messages per poll.

Distinguish poller placement:

~~~text
DirectChannel queuedBatches
  -> splitter
  -> QueueChannel queuedItems
  -> endpoint with poller
~~~

The splitter here needs no poller because its input is a subscribable channel. The downstream endpoint needs a poller because its input is a queue. Only if the splitter's own input is a `PollableChannel` does the splitter endpoint require a poller.

`splitWith(...)` has been available since Spring Integration 6.2; this lesson uses it for endpoint configuration. See [BaseIntegrationFlowDefinition](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html) and [SplitterSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/SplitterSpec.html).

### 7.2. sendTimeout Only Bounds Blocking Sends

In the example:

~~~java
.sendTimeout(500)
~~~

The value is in milliseconds and applies to the endpoint's send operation when the channel supports blocking, such as a full queue. This is not:

- A deadline for the entire batch.
- A timeout for an HTTP request inside the consumer.
- A cancellation mechanism for slow consumers on a `DirectChannel`.
- A cap on the number of split messages.

If a queue has capacity 32 and temporarily lacks a consumer, a 40-element batch may enqueue 32 messages and stall on the next one. When the timeout expires while the queue remains full, the send fails; messages already in the queue do not vanish automatically.

Therefore, size capacity to acceptable limits and ensure adequate consumer throughput. Standard in-memory queues also do not guarantee data durability across process restarts.

## 8. Headers Flowing Through the Output Channel

With the `List<String>` example in Section 4 and `applySequence=true`, child messages carry metadata for tracking and grouping:

| Header | Illustrative value | Meaning |
|---|---|---|
| `id` | Child message's own ID | Distinguishes each message |
| `correlationId` | Splitter input message's ID | Links elements of the same split |
| `sequenceNumber` | `1`, `2`, `3` | Element position |
| `sequenceSize` | `3` | Number of elements in the split |
| `batchId` | `B-42` | Propagated business header |

Constants for correlation and sequence live in `IntegrationMessageHeaderAccessor`. For standard splitters, `applySequence` is enabled by default. Changing the output channel type does not alter the rules for assigning these headers.

Distinguish two kinds of identifiers:

- `correlationId` serves message execution and grouping mechanisms.
- `batchId` or `orderId` are business identifiers, useful for reconciliation and idempotency design.

When a transformer or service activator produces results per element, preserve headers relied upon by subsequent steps. Building a brand-new message and stripping all headers can cause an aggregator to lose grouping metadata.

### 8.1. When Element Count Is Unknown Upfront

If split logic returns an `Iterator` or another source whose size the framework cannot determine, `sequenceSize` may be `0`. That indicates unknown size, not that zero messages were emitted.

For example, an iterator might emit 10,000 elements while every message still carries `sequenceSize=0`. An aggregator relying on the default count-based completion will need a different completion policy.

When choosing to disable `applySequence` to reduce headers or pair with custom grouping rules, design corresponding correlation mechanisms and completion conditions. Refer to [AbstractMessageSplitter API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/splitter/AbstractMessageSplitter.html).

## 9. Connecting Output to Router, Filter, Aggregator, and Gateway

### 9.1. Router Decides the Branch for Each Element

Example of a batch containing `DIGITAL-BOOK` and `PEN`:

~~~java
@Bean
public IntegrationFlow routeItems() {
    return IntegrationFlow.from("mixedBatches")
            .split()
            .<String, Boolean>route(
                    code -> code.startsWith("DIGITAL-"),
                    mapping -> mapping
                            .channelMapping(true, "digitalItems")
                            .channelMapping(false, "physicalItems"))
            .get();
}
~~~

This is an alternative configuration; consumers for `digitalItems` and `physicalItems` must be declared and wired.

The router receives each product code after the splitter separates them. The two branch channels are the router's targets; the splitter's direct output is the connection leading into the router.

### 9.2. Filters Can Alter Batch Completion Conditions

Suppose the splitter emits three messages with `sequenceSize=3`. A filter discards `PEN`, so only the remaining two messages reach the aggregator.

If the aggregator waits for all three elements based on sequence size, the group will never complete. The output channel is still working properly; the issue lies in the contract between filtering and aggregation.

Design options include:

- Filter the list before the splitter if the business only needs to aggregate valid items.
- Retain a status result for every element, including rejected ones.
- Define a custom release condition and timeout handling if the number of valid results varies.

These choices carry different semantics. For example, a report requiring an entry for every input line usually fits returning both success and failure statuses so the total result count still reflects the original batch.

### 9.3. Gateways Need an Aggregated Result for Request-Reply Contracts

A gateway method returning `List<String>` does not automatically gather all messages emitted by a splitter into a list. A Java method's return type does not replace an aggregator.

If the requirement is to send one batch and receive one combined result:

~~~mermaid
flowchart LR
    G["Request-reply gateway"] --> S["Splitter"]
    S --> C["Per-element processing channel"]
    C --> T["Transformer or service activator"]
    T --> A["Aggregator"]
    A --> R["Single aggregated reply to gateway"]
~~~

The flow below illustrates that structure, assuming the gateway sends to `requestReplyBatches` and the payload is `List<String>`:

~~~java
@Bean
public IntegrationFlow requestReplyBatchFlow() {
    return IntegrationFlow.from("requestReplyBatches")
            .split()
            .transform(String.class, value -> value.toUpperCase(
                    java.util.Locale.ROOT))
            .aggregate()
            .get();
}
~~~

In this lossless example, the aggregator can use the correlation and sequence set by the splitter to produce one message whose payload is a list of results. Because there is no fixed output channel at the end, the result is sent to the request's reply destination.

The [Aggregator documentation](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html) explains grouping by correlation and releasing groups by sequence. The [Messaging Gateways documentation](https://docs.spring.io/spring-integration/reference/6.5/gateway.html) explains the temporary reply channel used by gateways.

The reply address must be preserved across processing steps. If the flow crosses a broker or serialization boundary, design how reply metadata is carried; a local channel reference does not automatically become a remote reply address.

## 10. Output Failures and Partial Batch Delivery

### 10.1. Channel Exists but Has No Subscriber

A `DirectChannel` without subscribers cannot buffer messages waiting for a consumer to appear. When the splitter sends a child message there, dispatch and delivery fail with a message such as:

~~~text
Dispatcher has no subscribers
~~~

For synchronous channels, verify downstream endpoints are registered and running. For queues, verify a consumer or poller is draining data.

### 10.2. Synchronous vs. Asynchronous Errors

With `DirectChannel`, exceptions in a consumer can unwind the call stack back to the sender. Setting an `errorChannel` header does not automatically turn every synchronous exception into an error message.

When processing through a Spring Integration executor or scheduled poller, the error handler mechanism can publish an `ErrorMessage` to the `errorChannel` header or the default error channel. Examine the actual error handlers configured on executors, pollers, and gateways.

In both cases, `errorChannel` is distinct from the output channel receiving successful results. See [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

### 10.3. A Batch May Have Side Effects Before an Error Occurs

Consider a simple synchronous path with no continue-on-error recovery:

~~~text
BOOK -> sent and processed successfully
PEN  -> consumer throws exception
BAG  -> not sent because the processing loop aborted
~~~

The fact that the initial request failed is insufficient to conclude `BOOK`'s side effects were rolled back. Rollback capability depends on transactions and participating resource types.

With an output queue, some messages may already be enqueued before the queue fills and the next send fails. With an executor, some tasks may already be scheduled or completed before another task fails.

If the entire batch is resent, already-succeeded items may be processed again. A key such as `(batchId, itemId)` can anchor idempotency design when appropriate for the business. Checking and recording that key must also be tied to the business operation so two workers do not process the same item concurrently.

Consequently, output channel design must pair with explicit decisions: per-element vs. batch retries, where failed items are recorded, and how batch completion is confirmed.

## 11. Testing Behavior at the Output Channel

Testing a function that returns a list only proves the list-building algorithm. To test the output channel contract, observe the actual messages sent by the splitter.

The test class below uses `SplitterOutputConfig` from Section 4. Each test creates its own context so queues contain no leftover data from earlier tests.

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class SplitterOutputTest {

    @Test
    void sendsOneMessagePerItemWithSequenceHeaders() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK", "PEN", "BAG"))
                    .setHeader("batchId", "B-42")
                    .build();

            assertTrue(input.send(request));

            List<String> expected = List.of("BOOK", "PEN", "BAG");

            for (int i = 0; i < expected.size(); i++) {
                Message<?> item = output.receive(1000);
                assertNotNull(item);

                assertEquals(expected.get(i), item.getPayload());
                assertEquals(
                        "B-42",
                        item.getHeaders().get("batchId"));
                assertEquals(
                        request.getHeaders().getId(),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID));
                assertEquals(
                        Integer.valueOf(i + 1),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER));
                assertEquals(
                        Integer.valueOf(3),
                        item.getHeaders().get(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE));
            }

            assertNull(output.receive(0));
        }
    }

    @Test
    void configuredOutputChannelTakesPriorityOverReplyChannel() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);
            var replies = new QueueChannel();

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.of("BOOK"))
                    .setReplyChannel(replies)
                    .build();

            assertTrue(input.send(request));

            Message<?> item = output.receive(1000);
            assertNotNull(item);
            assertEquals("BOOK", item.getPayload());
            assertNull(output.receive(0));
            assertNull(replies.receive(0));
        }
    }

    @Test
    void emptyListProducesNoChildMessage() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SplitterOutputConfig.class)) {

            var input = context.getBean("batches", DirectChannel.class);
            var output = context.getBean("lineItems", QueueChannel.class);

            Message<List<String>> request = MessageBuilder
                    .withPayload(List.<String>of())
                    .build();

            assertTrue(input.send(request));
            assertNull(output.receive(0));
        }
    }
}
~~~

Here, `receive(1000)` includes a timeout so tests do not block indefinitely when output is missing. `receive(0)` checks instantaneously. An instantaneous check is valid because in this specific configuration the splitter completes synchronous sends before `input.send(...)` returns.

When replacing the output with asynchronous processing, wait for a completion signal or bounded-timeout result before concluding. Do not infer "no extra messages" from a single instantaneous poll while workers are still running.

Scenarios worth adding to a real application's test suite:

| Scenario | What to prove |
|---|---|
| No output declared, but request has reply channel | Child messages arrive at the reply destination |
| Full output queue | Wait time is bounded and the app detects partial sends |
| Synchronous consumer fails on middle item | Identify which items processed and which were never sent |
| Parallel executor present | All required items yield results; do not assume completion order |
| Filter before aggregator | Group still has a valid completion condition |
| Gateway receives a batch | Exactly one aggregated result per contract |

## 12. Diagnosing Missing Messages After a Splitter

Start from the flow structure and trace one concrete request:

1. Confirm the request reached the splitter's input using logs or an appropriate interceptor.
2. Determine whether the split produced elements, an empty collection, or `null`.
3. Locate the direct output: `.channel(...)` immediately after the splitter or the implicit channel connecting to the next endpoint.
4. If no fixed output is configured, check the `replyChannel` address and Routing Slip mechanism if used.
5. Check subscribers for subscribable channels; check queue depth and consumers for pollable channels.
6. Inspect timeouts, dispatch errors, consumer errors, and error flows.
7. If waiting for a combined result, verify how many parts actually reached the aggregator and its release condition.

For example, "gateway receives no reply" can stem from all child messages sitting idle in an output queue, or the aggregator having received only two of three results. Both can occur even when the splitter correctly sent all child messages.

The key takeaway for flow design is: **the splitter creates child messages; the output channel defines how each message is handed to the next step**. From that boundary, the application must clearly define who consumes messages, when an element is considered complete, and when the entire batch can return its result.