# Splitting Collection Payloads

## 1. Objectives and Context

In the **SPRING_INTEGRATION_CORE** module, a splitter turns a single message containing multiple elements into multiple messages so each element flows through the endpoints of an integration flow. This lesson focuses on collection payloads, such as a list of order lines.

After this lesson, you will be able to:

- Design an input contract containing a list and an output contract containing a single element.
- Configure a splitter using the Java DSL, combining it with a transformer and `MessageChannel`.
- Read `correlationId`, `sequenceNumber`, and `sequenceSize` to track elements belonging to the same split batch.
- Handle empty lists and distinguish per-element errors from batch-wide failures.
- Write tests for payloads, headers, and stop-on-error behavior.

The examples use Java 17+, Spring Integration 6.5.x, and JUnit Jupiter. If your project uses Spring Boot, let the project's dependency management select compatible Spring versions; the examples do not require manually upgrading existing module versions. The splitter configuration syntax used in this lesson is **splitWith(...)** from the Java DSL in the 6.5 documentation branch.

## 2. A Collection in a Payload Is Still Just One Message

Suppose a producer sends a `Message` with the payload:

~~~text
[
  OrderLine("L1", "BOOK", 2),
  OrderLine("L2", "PEN", 5),
  OrderLine("L3", "BAG", 1)
]
~~~

Before the splitter, this is **one message containing three objects**. After the splitter, there are three messages, each carrying a single `OrderLine`.

~~~mermaid
flowchart LR
    A["Message containing List of L1, L2, L3"] --> S["Splitter"]
    S --> B["Message containing L1"]
    S --> C["Message containing L2"]
    S --> D["Message containing L3"]
    B --> T["Transformer processing one line"]
    C --> T
    D --> T
    T --> Q["Results queue"]
~~~

The arrows represent data decomposition; they do not mean the three elements are processed concurrently.

Different ways of handling the same input can be distinguished as follows:

| Configuration | Meaning for a three-line list |
| --- | --- |
| Transformer receiving the entire list | Transforms the list into a single result payload |
| Splitter receiving the list | Emits one message per line |
| Router receiving a message containing the list | Selects a destination for that message based on a condition |
| PublishSubscribeChannel receiving a message containing the list | Sends that message to subscribers; the payload remains a list |

If a transformer returns a `List`, a standard transformer endpoint still produces a single message carrying that `List`. To make the next step receive individual elements, pass the result through a splitter.

In the Java DSL, **split()** with no arguments uses `DefaultMessageSplitter`. Other configurations can provide a split function or expression. The scope of this lesson is collections already constructed in memory. [Java DSL Splitters Documentation](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-splitters.html).

## 3. Defining the Data Contract Before Configuration

For the order example, the contract should be stated clearly:

~~~text
Input:
  Message<List<OrderLine>>
  Header orderId: String
  List contains no nulls
  Each element represents a line with its own lineId

Output after splitter:
  N messages, each with an OrderLine payload
  Messages in the same batch carry correlation/sequence metadata

Output after transformer:
  N messages, each with a LineResult payload
  Condition: every element is processed successfully
~~~

The final condition has practical significance. A list of N elements does not guarantee the system will always produce N business results if a downstream endpoint can throw an exception.

### 3.1. Which Collection Type Fits?

| Collection type | What the application must decide |
| --- | --- |
| `List` | Suitable when input line order matters |
| `LinkedHashSet` | Preserves iteration order as managed by this collection, while removing duplicates per `Set` rules |
| `HashSet` | Do not rely on iteration order as business order |
| `List` containing `List` | A single split extracts each inner `List` |
| `List` containing mixed types | Normalize or validate types before an endpoint that only accepts `OrderLine` |

For example, suppose the payload is a list of two sublists, each containing two lines. An outer splitter produces **two messages containing Lists**, rather than automatically recursing into four lines. If the business requires per-line processing, flatten the data intentionally or add another splitter stage.

### 3.2. Checking for Null Elements and Mutable Data

A standard message payload must be non-null; therefore, a `null` element is not a valid way to represent "no line." Filter out or reject such elements before creating child messages. [GenericMessage API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/support/GenericMessage.html).

For application-controlled input, you can use `List.copyOf(lines)` to snapshot the list structure and reject `null` elements. This is a shallow copy: if an element is a mutable object, its contents can still change. Therefore, the examples use records containing only `String` and `int` so the data contract is easy to follow.

Do not let a producer add or remove elements in the same list while the splitter is iterating over it. If the data originates from a JSON request, validate the schema, element types, and line count limits right at the request boundary.

## 4. Complete Configuration: Splitting a List and Processing Each Line

In a project that already includes Spring Integration Core and Spring Context, place the following configuration in **CollectionSplitConfig.java**. The Java DSL is part of Spring Integration Core; the example does not require a separate DSL library.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class CollectionSplitConfig {

    public record OrderLine(String lineId, String sku, int quantity) {
    }

    public record LineResult(
            String lineId,
            String sku,
            int quantity,
            String status) {
    }

    @Bean
    public MessageChannel orderLinesInput() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel processedLines() {
        return new QueueChannel();
    }

    @Bean
    public PollableChannel emptyBatches() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow collectionSplitFlow() {
        return IntegrationFlow.from("orderLinesInput")
                .splitWith(s -> s
                        .applySequence(true)
                        .discardChannel("emptyBatches"))
                .<OrderLine, LineResult>transform(
                        CollectionSplitConfig::processLine)
                .channel("processedLines")
                .get();
    }

    private static LineResult processLine(OrderLine line) {
        if (line.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive: " + line.lineId());
        }

        return new LineResult(
                line.lineId(),
                line.sku(),
                line.quantity(),
                "ACCEPTED");
    }
}
~~~

The configuration has four parts:

1. **orderLinesInput** receives the message containing the list.
2. The splitter creates messages containing `OrderLine`.
3. The transformer validates `quantity` and converts `OrderLine` into `LineResult`.
4. **processedLines** stores result messages for a consumer or test to retrieve.

The **emptyBatches** channel receives requests whose split result is empty. This branch serves the "no lines" contract, independent of the business error-handling branch.

`IntegrationFlow` beans describe the flow using Java DSL builders; Spring registers the corresponding channels and endpoints in the application context. [Java DSL Documentation](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

### 4.1. Sending a List into the Flow

The snippet below is the body of a method in an application or test that already has a **context** variable pointing to the application context containing the configuration above:

~~~java
var input = context.getBean(
        "orderLinesInput",
        org.springframework.messaging.MessageChannel.class);

var results = context.getBean(
        "processedLines",
        org.springframework.messaging.PollableChannel.class);

var lines = java.util.List.of(
        new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
        new CollectionSplitConfig.OrderLine("L2", "PEN", 5),
        new CollectionSplitConfig.OrderLine("L3", "BAG", 1));

var request = org.springframework.messaging.support.MessageBuilder
        .withPayload(lines)
        .setHeader("orderId", "ORD-100")
        .build();

input.send(request);

for (int i = 0; i < lines.size(); i++) {
    var result = results.receive(1_000);
    if (result == null) {
        throw new IllegalStateException("Missing result at index " + i);
    }
    System.out.println(result.getPayload());
}
~~~

Expected payload output:

~~~text
LineResult[lineId=L1, sku=BOOK, quantity=2, status=ACCEPTED]
LineResult[lineId=L2, sku=PEN, quantity=5, status=ACCEPTED]
LineResult[lineId=L3, sku=BAG, quantity=1, status=ACCEPTED]
~~~

`QueueChannel` in the example helps observe output without external services. In a real system, the consumer might write to a database or call an outbound adapter.

## 5. Reading Metadata of Split Messages

With `applySequence(true)` configured, understand these three headers:

| Header | Meaning in this lesson's single-level split flow |
| --- | --- |
| `correlationId` | Links child messages to the split batch; derived from the `id` of the splitter's input message |
| `sequenceNumber` | Position of the element in the iteration, starting at 1 |
| `sequenceSize` | Number of elements in the split collection |

For example, if the request has UUID **P** and a payload of three lines:

~~~text
Message containing L1: correlationId=P, sequenceNumber=1, sequenceSize=3
Message containing L2: correlationId=P, sequenceNumber=2, sequenceSize=3
Message containing L3: correlationId=P, sequenceNumber=3, sequenceSize=3
~~~

The splitter enables `applySequence` by default; the example declares it explicitly so readers see the configuration intent. When manually building child messages with `MessageBuilder`, let the splitter's sequencing mechanism manage the split group. [AbstractMessageSplitter API](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/splitter/AbstractMessageSplitter.html).

The corresponding constants belong to `IntegrationMessageHeaderAccessor`:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;

Object correlationId = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.CORRELATION_ID);

Integer sequenceNumber = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
        Integer.class);

Integer sequenceSize = message.getHeaders().get(
        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
        Integer.class);
~~~

Here, **message** is a message received from the result channel. Using constants avoids mistyping header names. [IntegrationMessageHeaderAccessor API](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/IntegrationMessageHeaderAccessor.html).

In the example, the business header `orderId` is propagated through both the splitter and transformer. Keep **orderId** and **lineId** as business identifiers:

- `orderId` identifies which order is being processed.
- `lineId` identifies which line needs updating or reprocessing.
- `correlationId` serves to group messages within one split execution.

Resending the same data in a new input message can generate a different `correlationId`. Therefore, an idempotency key should be based on stable business identifiers, such as `orderId` combined with `lineId` and a request version.

If a downstream endpoint constructs a brand-new `Message` and drops required headers, group tracking can break. When returning a `Message` instead of just a payload, explicitly preserve metadata in accordance with the flow contract.

## 6. When the Collection Lives Inside a Business Object

Real-world payloads are often an **OrderBatch**, not a bare `List`. Such a data type can be declared in the application as follows:

~~~java
import java.util.List;
import java.util.Objects;

public record OrderBatch(
        String orderId,
        List<CollectionSplitConfig.OrderLine> lines) {

    public OrderBatch {
        Objects.requireNonNull(orderId, "orderId");
        lines = List.copyOf(lines);
    }
}
~~~

With this type, you must specify how to extract the list. This is an alternative input option for the previous example; if adopted, declare an additional **batchInput** channel and use an equivalent endpoint:

~~~java
@Bean
public MessageChannel batchInput() {
    return new DirectChannel();
}

@Bean
public IntegrationFlow batchInputFlow() {
    return IntegrationFlow.from("batchInput")
            .enrichHeaders(h -> h.headerExpression(
                    "orderId", "payload.orderId()"))
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orderLinesIndividual")
            .get();
}
~~~

In this variant, **orderLinesIndividual** is a channel declared by the application to connect to an endpoint that accepts **a single OrderLine**. Do not connect it to the main example's **orderLinesInput**, because that channel's contract expects **an entire list**.

Extracting `orderId` into a header must happen before the splitter: after splitting, the payload is `OrderLine`, no longer `OrderBatch`.

To connect this variant to business processing, move the transformer into a separate `IntegrationFlow` starting from `orderLinesIndividual`. List extraction and line processing then have two clear contracts.

A POJO splitter can also accept a business object and return a collection. If different headers are needed for each line, the split function can return a collection of `Message` objects instead of a collection of payloads. [Splitter Programming Model](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

## 7. Empty Collections and Special Result Forms

### 7.1. An Empty List Does Not Produce an Empty Child Message

In the main configuration, sending `List.of()` yields:

~~~text
processedLines: no new messages
emptyBatches: receives the original request whose payload is an empty list
~~~

`discardChannel` receives the **request message**, not a dummy `OrderLine` and not an `ErrorMessage`.

Without `discardChannel` configured, an empty split result emits no output message to continue the flow. For contracts requiring a response per batch, explicitly define the response for an empty batch during design.

### 7.2. Empty Differs from Null

In a custom splitter, returning an empty collection means there are no elements to emit. Returning `null` indicates there is no result to continue the flow and does not go through the empty-collection discard mechanism. A `requiresReply` policy, if enabled separately, can also turn having no result into an error.

Therefore, use an empty collection when you mean "split validly, but no lines present"; use an input validation error when you mean "invalid request." [Splitter Empty and Null Result Rules](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

### 7.3. Do Not Switch List to Iterator Just for Convenience

This example knows the element count upfront thanks to the collection. With an `Iterator` or another traversal source whose size cannot be determined, `sequenceSize` is typically `0`, indicating an unknown size. An aggregator relying on exact element count cannot infer completion the way the `List` example does.

If the data is too large to hold as an entire collection, explicitly design a streaming, group-completion, and resource-closing strategy. That is a contract change, not merely swapping a method's return type. [Splitter and Iterator](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

## 8. Splitting Data, Execution Threads, and Result Ordering

The main configuration uses a `DirectChannel` at the input and direct connections between the splitter and transformer. Consequently, each line is processed on the thread calling `send`; the `QueueChannel` at the end of the flow simply buffers results.

If child messages are routed through an `ExecutorChannel`, downstream handlers can run on different threads. A `QueueChannel` likewise becomes an asynchronous boundary only when a consumer or poller pulls messages to process them. [MessageChannel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Consider three tasks with different durations:

~~~text
L1: 300 ms
L2:  20 ms
L3: 100 ms
~~~

When processed synchronously from a `List`, the consumer observes results in order L1, L2, L3. When processed concurrently, the completion order may be L2, L3, L1.

In both modes, `sequenceNumber` still describes the position in the split batch. It is not the completion rank. If the output requires preserving order, the application must incorporate that requirement into a resequencing or aggregation sorting design.

Do not infer "the entire batch has finished processing" solely because `send` returns `true` in a flow with an asynchronous boundary. If the caller needs a final result for the whole order, use an explicit aggregation mechanism.

## 9. Single-Element Failure and Reprocessing Scope

Try this input:

~~~text
L1: quantity=2
L2: quantity=0
L3: quantity=1
~~~

With the main configuration, having no enclosing transaction and no continue-on-error mechanism:

1. L1 produces a `LineResult` and is placed in `processedLines`.
2. The transformer throws an exception on L2.
3. The error propagates back to the `send` call.
4. L3 is not processed during that send.

Synchronous error behavior over `DirectChannel` means exceptions can propagate to the caller. Simply setting an `errorChannel` header does not automatically turn every synchronous call-stack exception into an `ErrorMessage`. For framework-managed asynchronous tasks, the error-handling mechanism can send an `ErrorMessage` to the appropriate error channel. [Error Handling in Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

From this scenario, the flow designer must choose:

| Business requirement | Appropriate design approach |
| --- | --- |
| Reject the entire batch when invalid data is present | Validate the entire list before the splitter |
| Retry transient failures on a single line | Configure retry on the line-processing endpoint and verify which actions are safe to repeat |
| Collect success or failure results for all lines | Convert expected errors into per-line business results and continue processing |
| Resend the entire batch after one line fails | Use stable idempotency keys and appropriate update rules |

For instance, if L1 has already created a transaction in an external system, resending the entire list may trigger duplicate side effects for L1. A splitter does not automatically guarantee exactly-once execution per line.

If you choose the "every line always has a result" policy, create a result type containing `lineId`, status, and appropriate error details. Convert only expected business errors into data; infrastructure errors need their own retry or recovery policy.

Do not use `sequenceNumber` as a unique business key: prepending a new line to the list shifts the sequence numbers of all subsequent lines.

## 10. Combining Filter, Router, and Aggregator After a Splitter

After the split step, a filter or router receives **a single OrderLine**, so business conditions are usually simpler. For example, a router can choose a processing route by `sku`; a filter can block lines outside the processing scope.

If a response for the entire batch is needed afterward, an aggregator can group messages by `correlationId` and wait for `sequenceSize` messages. Grouping strategy and release conditions are two separate decisions for an aggregator. [Aggregator Documentation](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

With three initial lines, filtering out L2 leads to:

~~~text
Before filter:
  L1: sequenceNumber=1, sequenceSize=3
  L2: sequenceNumber=2, sequenceSize=3
  L3: sequenceNumber=3, sequenceSize=3

Arriving at aggregator:
  Only L1 and L3 remain
~~~

The application must decide what counts as "complete" once the line count changes:

- Filter the collection before splitting if the sequence should only include accepted lines.
- Produce a `REJECTED` result for dropped lines if the report must cover the entire input.
- Design a custom release strategy and timeout when the group only needs a subset matching a business condition.

If a router distributes lines across multiple branches and each branch has its own aggregator, do not assume each branch will receive the full original count.

A gateway returning a single result per invocation also needs a clear contract: to respond for the whole order, aggregate before replying. Having three child messages does not automatically turn into a single return value containing three results.

## 11. Testing the Contract with JUnit Jupiter

Place the following class in test sources, in the same package as `CollectionSplitConfig`. The test suite uses a fresh context per test so results in `QueueChannel` do not leak across runs.

~~~java
import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class CollectionSplitConfigTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private PollableChannel output;
    private PollableChannel emptyBatches;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                CollectionSplitConfig.class);
        input = context.getBean("orderLinesInput", MessageChannel.class);
        output = context.getBean("processedLines", PollableChannel.class);
        emptyBatches = context.getBean("emptyBatches", PollableChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void splitsCollectionAndPreservesGroupMetadata() {
        var lines = List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
                new CollectionSplitConfig.OrderLine("L2", "PEN", 5),
                new CollectionSplitConfig.OrderLine("L3", "BAG", 1));

        Message<List<CollectionSplitConfig.OrderLine>> request =
                MessageBuilder.withPayload(lines)
                        .setHeader("orderId", "ORD-100")
                        .build();

        assertTrue(input.send(request));

        for (int i = 0; i < lines.size(); i++) {
            Message<?> actual = output.receive(1_000);
            assertNotNull(actual);

            var expected = lines.get(i);
            assertEquals(
                    new CollectionSplitConfig.LineResult(
                            expected.lineId(),
                            expected.sku(),
                            expected.quantity(),
                            "ACCEPTED"),
                    actual.getPayload());

            assertEquals("ORD-100", actual.getHeaders().get("orderId"));
            assertEquals(
                    request.getHeaders().getId(),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.CORRELATION_ID));
            assertEquals(
                    Integer.valueOf(i + 1),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                            Integer.class));
            assertEquals(
                    Integer.valueOf(lines.size()),
                    actual.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                            Integer.class));
        }

        assertNull(output.receive(0));
        assertNull(emptyBatches.receive(0));
    }

    @Test
    void singletonCollectionStillProducesOneItemMessage() {
        var request = MessageBuilder.withPayload(List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2)))
                .build();

        assertTrue(input.send(request));

        Message<?> actual = output.receive(1_000);
        assertNotNull(actual);
        assertInstanceOf(
                CollectionSplitConfig.LineResult.class,
                actual.getPayload());
        assertEquals(
                Integer.valueOf(1),
                actual.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        Integer.class));
        assertEquals(
                Integer.valueOf(1),
                actual.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        Integer.class));
        assertNull(output.receive(0));
    }

    @Test
    void emptyCollectionRoutesOriginalRequestToDiscardChannel() {
        var request = MessageBuilder.withPayload(
                List.<CollectionSplitConfig.OrderLine>of())
                .setHeader("orderId", "ORD-EMPTY")
                .build();

        assertTrue(input.send(request));

        assertNull(output.receive(0));
        Message<?> discarded = emptyBatches.receive(1_000);
        assertNotNull(discarded);
        assertEquals(request, discarded);
        assertNull(emptyBatches.receive(0));
    }

    @Test
    void synchronousFailureLeavesEarlierOutputAndStopsLaterItems() {
        var request = MessageBuilder.withPayload(List.of(
                new CollectionSplitConfig.OrderLine("L1", "BOOK", 2),
                new CollectionSplitConfig.OrderLine("L2", "PEN", 0),
                new CollectionSplitConfig.OrderLine("L3", "BAG", 1)))
                .build();

        assertThrows(MessagingException.class, () -> input.send(request));

        Message<?> first = output.receive(1_000);
        assertNotNull(first);
        assertEquals(
                new CollectionSplitConfig.LineResult(
                        "L1", "BOOK", 2, "ACCEPTED"),
                first.getPayload());

        assertNull(output.receive(0));
        assertNull(emptyBatches.receive(0));
    }
}
~~~

The tests verify things easily missed when only printing payloads to the console:

| Test | Contract verified |
| --- | --- |
| Three-line list | Count, data, synchronous ordering, `orderId`, and group metadata |
| Single line | Output is the element's result, sequence starts at 1 |
| Empty list | No line results, original request goes to discard channel |
| Failure on second line | Caller receives exception; prior result stays in queue and later line is not processed |

The `receive` calls include a timeout so tests do not block indefinitely. `receive(0)` checks immediately whether any messages remain in the queue. That final check fits this synchronous flow; for asynchronous flows, use a bounded wait-for-completion mechanism before concluding no results remain.

This is test code for the learner to place into a project and run. The lesson text does not substitute for running tests against the project's actual dependency configuration.

## 12. High Load and Observability

Suppose a request contains 10,000 lines and each line calls an external service. After the splitter, the application may execute 10,000 tasks even though the producer sent only one input message.

Therefore, set limits according to the usage contract:

- Limit the number of lines per request to protect response times and memory.
- When increasing worker threads, cap in-flight tasks based on downstream system capacity.
- If using bounded queues, define full-queue behavior and send timeouts; avoid unintentionally blocking upstream callers indefinitely.
- Scope retries to a well-defined task, accounting for side effects that may already have occurred.
- If sending in batches of 100 lines is required, design a chunking step returning a collection of groups; a splitter does not automatically choose batch sizes.

The default `QueueChannel` in the example serves this in-memory lesson; it is not durable storage across process restarts. For crash-recovery requirements, choose an appropriate message store or delivery infrastructure. [QueueChannel and Message Storage](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

To trace a failed line, logs should include `orderId`, `lineId`, `correlationId`, and `sequenceNumber`. Also track input line counts, succeeded lines, failed lines, and empty batches. When a batch is missing results, these metrics help distinguish intentionally filtered items, failed tasks, and still-pending tasks.

## 13. How to Apply This to a New Flow

When introducing collection payloads into a system, proceed in order:

1. Finalize the input payload type and the element type after the splitter.
2. Choose business identifiers for the batch and each element.
3. Specify whether order matters and how `null` and empty collections are handled.
4. Preserve batch-level information needed after the payload becomes individual elements.
5. Choose channels based on threading, buffering, and result-ordering requirements.
6. Place error, retry, and idempotency policies on the right business endpoint.
7. If a batch-wide response is needed, design the aggregation condition covering successes, failures, and discarded lines.
8. Test message counts, payloads, metadata, the empty branch, and mid-list failures.

With a well-defined contract, a splitter bridges list-shaped data to single-element endpoints. This allows transformers, routers, and filters to operate on small business units, while aggregation and recovery are designed to meet the requirements of the entire flow.