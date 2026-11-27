# Resequencer and Sequence Headers

In the **SPRING_INTEGRATION_CORE** module, a resequencer restores out-of-order processed messages to their proper sequence before forwarding them to the next endpoint. This topic connects `Message`, `MessageChannel`, and Java DSL with a common integration scenario: processing in parallel for speed while still emitting results in a defined order.

The running example is a document batch split into multiple parts. Workers may finish part 3 before part 1, yet the document-writing step requires receiving part 1, then part 2, then part 3. The resequencer maintains state per batch and decides when received parts may be forwarded.

The examples use Java 17 or higher and the Spring Integration 6.5 API. The practice project requires `spring-integration-core`; tests use JUnit Jupiter. If your project uses Spring Boot, manage versions through your project's dependency management so Spring libraries stay compatible.

## 1. Objectives and flow model

After this lesson, you should be able to explain:

- How the three headers `correlationId`, `sequenceNumber`, and `sequenceSize` work together.
- When to wait for the full group and when contiguous segments can be released early.
- How to place a resequencer after an asynchronous processing stage using Java DSL.
- Why a missing part, dropped header, or reused correlation key can break the flow.
- How to test output ordering without depending on thread execution speeds.

```mermaid
flowchart LR
    A["One document batch"] --> B["Splitter: generate sequence headers"]
    B --> C["Workers process in parallel"]
    C --> D["Resequencer: hold and reorder"]
    D --> E["Endpoint receives each part in order"]
```

The desired order must be established **before any stage that can reorder messages**. Numbering parts by worker completion time merely records the outcome of a race among workers.

In this scenario, the resequencer restores the order of parts within a batch. It does not infer business order from document content or from when messages arrive at the system.

## 2. What does a resequencer do?

A resequencer receives multiple related messages, holds them by group, and forwards each message by `sequenceNumber`. A group of three messages still produces three output messages. Payloads are not merged into a list merely by passing through a resequencer. This is the fundamental difference from an aggregator. See [Spring Integration: Resequencer](https://docs.spring.io/spring-integration/reference/6.5/resequencer.html).

For a valid batch of size 3:

```text
Arrival input over time:  part 3 → part 1 → part 2
Sequence output:          part 1 → part 2 → part 3
```

Three concepts to keep separate:

| Concept | Question to answer | Example |
|---|---|---|
| Correlation | Which batch does the message belong to? | `document-42:attempt-1` |
| Sequence | What position is the message at within the batch? | Part `2` |
| Release | Given current state, which messages may be emitted? | All 3 parts arrived, or next contiguous segment ready |

A resequencer does not automatically re-fetch lost parts. If part 2 never arrives, the system must have a waiting, expiry, or recovery policy.

## 3. Contract of the three sequence headers

The constants belong to `org.springframework.integration.IntegrationMessageHeaderAccessor`. Actual header names and value types must be agreed upon across senders, processors, and receivers. See [IntegrationMessageHeaderAccessor 6.5.10 source](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/IntegrationMessageHeaderAccessor.java).

| Constant | Header name | Meaning | Value of the second part |
|---|---|---|---|
| `CORRELATION_ID` | `correlationId` | Group key used by the default correlation strategy | `"document-42:attempt-1"` |
| `SEQUENCE_NUMBER` | `sequenceNumber` | Position in the sequence, typically starting at 1 | `2` |
| `SEQUENCE_SIZE` | `sequenceSize` | Total number of parts in a finite sequence | `3` |

For the finite-batch example in this lesson, the input convention is:

```text
correlationId is non-null and uniquely identifies one batch processing run
sequenceSize = N, with N > 0
sequenceNumber in 1..N
Every part in the same batch has the same sequenceSize
Each position represents exactly one business part
```

In Java, set `sequenceNumber` and `sequenceSize` as integers, such as `Integer`. Adapters receiving data from HTTP, JSON, or brokers must normalize string values like `"2"` into the appropriate numeric type before sending messages to the resequencer.

Do not use `MessageHeaders.ID` as a correlation key for individual parts. Every message has its own unique ID; parts of the same batch must share **the same group key** while having **different positions**.

The correlation key must also distinguish processing runs. For example:

```text
document-42:attempt-1
document-42:attempt-2
```

Using a constant key such as `"all-documents"` puts parts from multiple documents into the same group.

## 4. Ordering is meaningful only within each group

Suppose there are two batches A and B, each with two parts:

```text
Received: A2, B2, A1, B1
Possible output in full-group wait mode: A1, A2, B1, B2
```

A finishes before B, so A is emitted first under this send order. If B1 arrives before A1, B can be emitted first. The system requirement is `A1 < A2` and `B1 < B2`; it establishes no ordering relationship between A and B.

If business logic requires all batches to be written in one shared order, you need a shared sequence or another coordination layer. Cross-group ordering cannot be assumed as default resequencer behavior.

Group keys should be designed around actual business scope. In a multi-tenant system, the key may need tenant, document ID, and run ID to avoid collisions across customers.

## 5. Full-group waiting vs. contiguous-segment release

### 5.1. Wait for the full group

With `releasePartialSequences(false)`, the normal path waits until the group reaches `sequenceSize` parts and then forwards them in sequence. This is also the default described in the resequencer documentation. The lesson configures it explicitly to show intent. See [Resequencer configuration](https://docs.spring.io/spring-integration/reference/6.5/resequencer.html).

This approach fits when the receiver must start processing only after the entire batch is present. The trade-off is that early parts must wait for the slowest part.

The “full group” condition is only meaningful when the header contract holds. Do not treat simply counting enough messages as proof that the producer sent valid positions `1..N`.

### 5.2. Release contiguous segments

With `releasePartialSequences(true)` and the default strategy, the resequencer can release the next segment as soon as its leading position matches the next expected number. It records the released position to decide subsequent releases. See [SequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html) and [resequencer group processor source](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/aggregator/ResequencingMessageGroupProcessor.java).

With `sequenceSize = 4` and arrival order `3, 1, 4, 2`:

| Arrival step | Full-group wait: newly emitted | Partial release: newly emitted | Waiting state in partial mode |
|---|---|---|---|
| Receive 3 | None yet | None yet | Waiting for 1, holding 3 |
| Receive 1 | None yet | 1 | Waiting for 2, holding 3 |
| Receive 4 | None yet | None yet | Waiting for 2, holding 3 and 4 |
| Receive 2 | 1, 2, 3, 4 | 2, 3, 4 | Released through 4 |

When only 3 and 4 are present, that segment is contiguous within itself yet cannot be emitted on the normal path because 1 and 2 have not been emitted yet. Initially, the expected number is 1.

This rule applies to the default mechanism with valid input. If you supply a custom `releaseStrategy`, you are responsible for the new release condition; you can no longer assume all guarantees of the default strategy hold.

| Consideration | Wait for full group | Partial segment release |
|---|---|---|
| Receiver starts processing | After full batch arrives | Once a valid leading segment arrives |
| Leading part with a very slow trailing part | Continues waiting | May already be emitted |
| A middle position is lost | Entire group remains unreleased | Parts after the gap continue waiting |
| Receiver needs to support incomplete batches | Less common on the normal path | Yes, since some parts already arrived early |

Partial release does not allow going back to undo parts already forwarded. If the receiver already wrote part 1, a timeout on part 2 will not automatically roll back that write.

## 6. Where are sequence headers created and preserved?

Spring Integration's splitter populates sequence headers on the parts it emits. When sequence application is enabled, splitting a finite collection can populate the group key, sequence number, and total count. Iterators whose size cannot be determined may carry `sequenceSize = 0`; do not treat that value as “batch complete.” See [Spring Integration: Splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

Two common ways data enters a resequencer:

1. Use a splitter within the same system and preserve headers through transformers and service activators.
2. Receive parts from an external system and map external metadata onto the three standard headers at the inbound boundary.

A typical Java DSL pattern is `split → ExecutorChannel → process → resequence`. The [Aggregators and Resequencers in Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-aggregators.html) guide illustrates placing a resequencer after an executor-backed processing stage.

When manually building a new message in business code, actively preserve metadata. Example method converting a payload to uppercase:

```java
static Message<String> normalize(Message<String> input) {
    return MessageBuilder.withPayload(
                    input.getPayload().toUpperCase(java.util.Locale.ROOT))
            .copyHeaders(input.getHeaders())
            .build();
}
```

This snippet uses `org.springframework.messaging.Message` and `org.springframework.messaging.support.MessageBuilder`. Do not rely on preserving the message ID when constructing a new message; the resequencer needs the batch's correlation and sequence headers.

With standard transformers, the framework propagates headers, but manual message construction, protocol mapping, or header filtering should still be verified at integration boundaries. Logging the three headers before and after workers helps pinpoint where metadata was dropped.

When splitting across multiple levels, each level has its own sequence scope. Do not overwrite an outer level's headers without designing how to restore outer correlation after the inner level finishes.

## 7. Complete Java DSL configuration for both modes

The example below intentionally sends messages with pre-set headers to isolate and observe resequencer behavior. Save the practice configuration class as `ResequencerLessonConfig.java` in package `example.integration`.

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class ResequencerLessonConfig {

    @Bean
    public DirectChannel fullInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel fullOutput() {
        return new QueueChannel();
    }

    @Bean
    public DirectChannel partialInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel partialOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow fullSequenceFlow() {
        return IntegrationFlow.from(fullInput())
                .resequence(spec -> spec.releasePartialSequences(false))
                .channel(fullOutput())
                .get();
    }

    @Bean
    public IntegrationFlow partialSequenceFlow() {
        return IntegrationFlow.from(partialInput())
                .resequence(spec -> spec.releasePartialSequences(true))
                .channel(partialOutput())
                .get();
    }
}
```

`@EnableIntegration` initializes the Spring Integration infrastructure in a plain Spring application context.

Both inputs are `DirectChannel`, so send calls to the resequencer run synchronously on the sending thread. Both outputs are `QueueChannel`, allowing tests to pull individual messages with `receive`. These channel properties are documented in [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

The two flows maintain separate state. They do not share a user-supplied message store. Inputs in the example must follow the finite header contract from section 3.

An application receiving individual parts can use a gateway with a one-way send method. Avoid designing each part to call a request-reply gateway expecting an immediate reply: part 3 may be held until parts 1 and 2 arrive. If a single reply is needed for the entire batch, explicitly design the batch-completion step—such as placing a suitable aggregator downstream.

## 8. Testing out-of-order inputs

The test class below shares the same package as the configuration. Each test gets a fresh application context so group state from an earlier test does not affect subsequent tests.

```java
package example.integration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ResequencerLessonTest {

    private AnnotationConfigApplicationContext context;

    @BeforeEach
    void openContext() {
        context = new AnnotationConfigApplicationContext(
                ResequencerLessonConfig.class);
    }

    @AfterEach
    void closeContext() {
        context.close();
    }

    @Test
    void waitsForAllPartsThenEmitsInSequence() {
        MessageChannel input = context.getBean(
                "fullInput", MessageChannel.class);
        QueueChannel output = context.getBean(
                "fullOutput", QueueChannel.class);

        assertTrue(input.send(part("doc-A", 3, 3)));
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-A", 1, 3)));
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-A", 2, 3)));

        assertNext(output, "doc-A", 1, 3);
        assertNext(output, "doc-A", 2, 3);
        assertNext(output, "doc-A", 3, 3);
        assertNull(output.receive(0));
    }

    @Test
    void emitsOnlyTheNextContiguousPartOfTheSequence() {
        MessageChannel input = context.getBean(
                "partialInput", MessageChannel.class);
        QueueChannel output = context.getBean(
                "partialOutput", QueueChannel.class);

        assertTrue(input.send(part("doc-B", 3, 4)));
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-B", 1, 4)));
        assertNext(output, "doc-B", 1, 4);
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-B", 4, 4)));
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-B", 2, 4)));
        assertNext(output, "doc-B", 2, 4);
        assertNext(output, "doc-B", 3, 4);
        assertNext(output, "doc-B", 4, 4);
        assertNull(output.receive(0));
    }

    @Test
    void keepsDifferentCorrelationGroupsIndependent() {
        MessageChannel input = context.getBean(
                "fullInput", MessageChannel.class);
        QueueChannel output = context.getBean(
                "fullOutput", QueueChannel.class);

        assertTrue(input.send(part("doc-C", 2, 2)));
        assertTrue(input.send(part("doc-D", 2, 2)));
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-C", 1, 2)));
        assertNext(output, "doc-C", 1, 2);
        assertNext(output, "doc-C", 2, 2);
        assertNull(output.receive(0));

        assertTrue(input.send(part("doc-D", 1, 2)));
        assertNext(output, "doc-D", 1, 2);
        assertNext(output, "doc-D", 2, 2);
        assertNull(output.receive(0));
    }

    private static Message<String> part(
            String batchId, int number, int total) {
        return MessageBuilder.withPayload("part-" + number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        batchId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        total)
                .build();
    }

    private static void assertNext(
            QueueChannel output, String batchId, int number, int total) {
        Message<?> message = output.receive(1_000);
        assertNotNull(message);
        assertEquals("part-" + number, message.getPayload());
        assertEquals(batchId, message.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertEquals(Integer.valueOf(number), message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                Integer.class));
        assertEquals(Integer.valueOf(total), message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                Integer.class));
    }
}
```

The tests inspect payloads, correlation keys, and both numeric headers together. If you only count how many messages were received, tests can miss ordering bugs or two batches mixing together.

`receive(0)` checks the queue's current state immediately. It works here because the path from input to output queue is synchronous. When switching to `ExecutorChannel`, use bounded waits or condition-based synchronization; checking immediately after `send` does not prove workers have finished.

The code snippets are practice examples for this lesson. To verify in a specific project, run them with the dependency and JUnit versions used by your project.

## 9. Validating headers at the inbound boundary

Validate each message before it is held in a group. An illustrative predicate for **the lesson's integer contract**:

```java
static boolean validFiniteSequence(Message<?> message) {
    Object correlation = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.CORRELATION_ID);
    Object number = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
    Object total = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE);

    return correlation instanceof String key
            && !key.isBlank()
            && number instanceof Integer position
            && total instanceof Integer size
            && size > 0
            && position >= 1
            && position <= size;
}
```

The predicate uses the same `Message` and `IntegrationMessageHeaderAccessor` imports as the test class. You can attach it to a filter ahead of the resequencer and route invalid parts to a dedicated handling channel.

This condition checks only a single message. It cannot verify:

- Whether parts sharing a correlation key declare the same `sequenceSize`.
- Whether two messages at the same position have conflicting payloads.
- Whether the producer actually sent every position.
- Whether a correlation key was reused for another batch.

For example, receiving `1/3`, `2/3`, and `3/4` must be treated as an inconsistent batch contract. Do not patch the last part alone to `3/3` without knowing the true total from an authoritative source.

If you need a custom correlation strategy—for instance reading from a business header—you can configure:

```java
.resequence(spec -> spec
        .correlationStrategy(
                message -> message.getHeaders().get("documentBatchKey"))
        .releasePartialSequences(false))
```

This is a replacement snippet within the DSL chain. The `documentBatchKey` value must exist and accurately identify the batch. Changing the correlation key does not replace the need for valid sequence numbers and completion criteria.

These configuration methods belong to `ResequencerSpec` and its base class; see [ResequencerSpec 6.5.10](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/dsl/ResequencerSpec.java) and [CorrelationHandlerSpec 6.5.10](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/dsl/CorrelationHandlerSpec.java).

## 10. Missing parts, timeouts, and late messages

### 10.1. Distinguishing the two “partial” options

`releasePartialSequences` controls early emission during normal reception. `sendPartialResultOnExpiry` controls how held parts are handled when a group is forced to complete due to expiration.

Enabling early release does not create a timeout by itself. A group can still hold parts 3 and 4 forever if part 2 is missing and there is no termination mechanism.

In the document-writing example, suppose the requirement is to keep incomplete results on an incident-handling channel for operations inspection. You can add these three beans to the configuration class from section 7:

```java
@Bean
public QueueChannel expiredSequence() {
    return new QueueChannel();
}

@Bean
public QueueChannel expiringOutput() {
    return new QueueChannel();
}

@Bean
public IntegrationFlow expiringSequenceFlow() {
    return IntegrationFlow.from("expiringInput")
            .resequence(spec -> spec
                    .releasePartialSequences(false)
                    .groupTimeout(5_000)
                    .sendPartialResultOnExpiry(false)
                    .expireGroupsUponTimeout(false)
                    .discardChannel(expiredSequence()))
            .channel(expiringOutput())
            .get();
}
```

`expiringInput` is the input channel of the additional flow. With this configuration, an incomplete group is scheduled to terminate after an interval with no new messages. `groupTimeout(5_000)` is in milliseconds; it is not a fixed 5-second deadline measured from the first message. See [correlation endpoint group timeout rules](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html#aggregator-config-xml).

With inputs `1/3` then `3/3`:

1. The group is incomplete, so nothing appears on `expiringOutput`.
2. When the expiry task runs and the group is still incomplete, held parts are routed according to the discard policy.
3. `expiredSequence` receives the messages for another flow to handle the incident; the queue itself is not durable error storage.
4. Group metadata is retained per `expireGroupsUponTimeout(false)` to detect late-arriving parts.

The resequencer documentation describes retaining metadata after timeout and discarding late messages. If the group is deleted completely, a subsequent message with the same key can open a new group. See [timeout and empty-group policy](https://docs.spring.io/spring-integration/reference/6.5/resequencer.html).

### 10.2. Do not interpret a timeout as a complete batch

If `sendPartialResultOnExpiry(true)` is enabled, output emitted upon expiry does not prove every position arrived. That path requires an explicit business contract.

For instance, an endpoint expecting to write a complete document must know the batch missed parts so it avoids finalizing a corrupt document. You can use a separate batch-completion event, status table, or application-managed business metadata. Do not assume the resequencer automatically attaches a “document complete” flag.

In particular, when partial release is enabled, parts emitted before timeout have already left the resequencer. The discard policy applies only to state still held; recovering the entire document must be designed at the business level.

## 11. Memory, state, and scope of guarantees

The resequencer is stateful. When a position is delayed or lost, subsequent parts must sit in the store. For example, 2,000 waiting batches each holding 10 payloads of around 100 KB already amounts to roughly 2 GB of payload data, excluding overhead.

Monitor waiting group count, held message count, oldest group age, and the next missing position. Many long-lived groups typically indicate a producer dropping parts, a wrong correlation key, or an inadequate termination policy.

`SimpleMessageStore` uses process memory by default. When recovery across restarts is required, choose a suitable persistent `MessageGroupStore` and verify serialization of both payloads and headers. Serialization can affect metadata across write-and-read cycles. See [Spring Integration: Message Store](https://docs.spring.io/spring-integration/reference/6.5/message-store.html).

When deploying multiple instances, design the topology so every message of the same group reaches a single logical state. You can route matching keys to the same instance or use a shared store with appropriate locking. Simply adding more instances with local stores will split a batch's parts apart.

State for already-released positions and closed groups has its own lifecycle. Cleanup must balance reclaiming storage against the window during which late messages must still be recognized. Consult [ResequencingMessageHandler](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/aggregator/ResequencingMessageHandler.java) when verifying group lifecycle on your exact version.

Ordering guarantees also depend on the flow after the resequencer. If messages are forwarded through a multi-threaded executor, **completion** order at downstream endpoints can still become unordered. Clarify exactly what must be guaranteed: channel send order, processing start order, or business commit order.

A resequencer also does not replace idempotency. Detecting some duplicate messages based on sequence numbers and held state is not equivalent to guaranteeing once-only business writes across retries, restarts, or group cleanup.

## 12. Distinguishing discards from exception handling

The two events require separate handling paths:

| Situation | What to observe | Handling approach |
|---|---|---|
| Message rejected by policy | Original message, batch key, position, rejection reason | Discard channel or application quarantine channel |
| Endpoint throws exception | Exception and failed message context | Synchronous error catching or appropriate error channel mechanism |
| Batch incomplete but within deadline | Held group and waiting duration | Track status; do not treat as a terminal error yet |
| Business part already written before retry | Processed business key | Enforce idempotency on the receiver side |

With `DirectChannel`, exceptions inside synchronous handling can propagate back to the caller of `send`. When moving to an executor or background task, configure and observe an appropriate asynchronous error-handling path. Do not assume every discarded message becomes an `ErrorMessage` on `errorChannel`. See [Spring Integration: Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

When logging, useful fields include batch key, sequence number, total part count, endpoint name, receipt timestamp, and termination reason. For large or sensitive payloads, these identifiers are usually enough for investigation without logging the full payload.

## 13. Common mistakes and how to reason through them

| Symptom | Cause to check first | Fix per contract |
|---|---|---|
| Each part ends up in its own group | Correlation key generated per message | Share a single key for the entire batch |
| Multiple documents get mixed | Correlation key too broad or missing tenant/run | Narrow the key down to the exact batch run |
| Group never releases despite many messages | Missing position, wrong size, or dropped header | Compare received positions against `1..N` |
| Partial mode has not released 3 and 4 | Earlier positions have not been released yet | Inspect the next expected position |
| External input fails header type check | Numeric metadata is still a string | Normalize types in the inbound adapter or transformer |
| Batch from an iterator waits forever | Total part count is unknown | Design a completion condition, size boundary, or expiry policy |
| Database order is still out of order | Parallel processing happens after the resequencer | Keep execution sequential up to the required commit point |
| Late part appears as a brand-new batch | Old group metadata was deleted or key was reused | Review retention policy and issue keys per processing run |

Do not treat the symptom by installing a `releaseStrategy` that always returns `true`. That can allow processing a group without complete information about missing positions.

Also do not replace a resequencer with a `PriorityChannel` using a sequence-number comparator and treat them as equivalent. A priority queue only picks among items currently present; if part 3 is consumed before part 1 arrives, it cannot restore lost ordering.

## 14. Applied practice exercise

Suppose a service receives four parts of a document. The contract requires writing each part in order and reporting failure if any part fails to arrive within the agreed wait period.

Work through these steps in sequence:

1. Send `3, 1, 4, 2` into both flows in section 7 and compare against the state table in section 5.
2. Interleave two correlation keys and verify output preserves order within each batch.
3. Omit part 2 and observe the difference between emitted parts, held parts, and parts discarded upon expiry.
4. Resend part 2 after timeout and compare behavior with group metadata retention settings.
5. Intentionally drop `sequenceNumber` in a manual message-building step and verify boundary error detection.
6. Place an executor after the resequencer with varying processing durations per part to distinguish emission order from completion order.

The completion criterion is being able to explain which group each message belongs to, what the next expected position is, when a group terminates, and what the receiver must do when a batch finishes only partially. That is the foundation for using a resequencer properly in enterprise integration flows.
