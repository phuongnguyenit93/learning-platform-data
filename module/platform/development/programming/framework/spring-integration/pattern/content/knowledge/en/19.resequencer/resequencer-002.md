# Sequence Number and Sequence Size

**Resequencer** is an Enterprise Integration Pattern (EIP) that **restores the logical order of messages arriving out of order**. In Spring Integration, Resequencer uses each message's metadata to put elements of the same sequence back into the expected order. The two most important headers to understand are **`sequenceNumber`** — the message's position in the sequence — and **`sequenceSize`** — the expected total number of elements in the sequence. Typically, they are accompanied by **`correlationId`** to identify which sequence the messages belong to.

This lesson belongs to the **Resequencer** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module teaches how to practice Enterprise Integration Patterns with Spring Integration, combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, scalable, testable, and observable messaging flows.

**Key takeaway:** `sequenceNumber` and `sequenceSize` describe **position** and **expected size**; they do not prove a message has been successfully processed, do not replace a correlation key, and do not automatically resolve lost, duplicate, or late messages.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the role of Resequencer and distinguish it from Aggregator, Splitter, Router, Filter, and Transformer.
2. Properly read the `correlationId`, `sequenceNumber`, and `sequenceSize` metadata trio in `MessageHeaders`.
3. Understand that sequence numbers in parts produced by a Splitter typically **start at 1**, not 0.
4. Distinguish between **arrival** order, **processing** order, **output release** order, and **business commit** order.
5. Describe how Resequencer groups messages, waits for completeness, and releases multiple ordered messages without merging payloads like Aggregator.
6. Distinguish **complete-sequence release** from **partial-sequence release**; understand how gaps affect output emission.
7. Understand `sequenceSize=0` or unreliable sequence sizes and when custom release/timeout is needed.
8. Write Java DSL `.resequence()`, send messages with sequence headers through real channels, and test output order with JUnit 5.
9. Design validation for malformed, missing, inconsistent, duplicate sequence numbers, out-of-range values, and mismatched correlation groups.
10. Handle timeouts, expiry, duplicates, retries, late arrivals, state stores, concurrency, security, and observability.

## 2. Why Do We Need Resequencer?

Suppose an order has four steps or four data lines processed concurrently. The system emits messages in the original order:

~~~text
Part 1 → Part 2 → Part 3 → Part 4
~~~

After passing through an executor, broker, or multiple consumers, messages may arrive downstream in the order:

~~~text
Part 3 → Part 1 → Part 4 → Part 2
~~~

If downstream must process in the original logical order, it cannot assume **arrival order** is the **correct order**.

~~~mermaid
flowchart LR
    S["Splitter: 1, 2, 3, 4"] --> E["Parallel processing"]
    E --> A["Arrives: 3"]
    E --> B["Arrives: 1"]
    E --> C["Arrives: 4"]
    E --> D["Arrives: 2"]
    A --> R["Resequencer"]
    B --> R
    C --> R
    D --> R
    R --> O["Emits: 1, 2, 3, 4"]
~~~

Resequencer sorts **messages belonging to the same sequence** by metadata. It does not combine four payloads into a single collection like Aggregator.

### 2.1. Four Types of Order to Distinguish

| Order Type | Meaning | Example |
|---|---|---|
| **Logical sequence** | Original order defined by producer/contract | 1, 2, 3, 4 |
| **Arrival order** | Order in which Resequencer receives messages | 3, 1, 4, 2 |
| **Resequenced output order** | Order in which messages are emitted by Resequencer | 1, 2, 3, 4 |
| **Business completion order** | Order in which transactions/side effects actually finish | May differ if downstream is async |

**Resequencer guarantees emission order according to its policy**, not that asynchronous downstream workers commit to the database in order. If strict processing order across multiple workers is required, an additional mechanism to serialize by key or partition and acknowledge processing is needed.

## 3. The Trio: correlationId, sequenceNumber, and sequenceSize

Spring Integration uses headers defined by the message sequence contract. When a Splitter knows the total number of parts, it typically creates:

~~~text
Message 1:
  correlationId = batch-1001
  sequenceNumber = 1
  sequenceSize = 4

Message 2:
  correlationId = batch-1001
  sequenceNumber = 2
  sequenceSize = 4

Message 3:
  correlationId = batch-1001
  sequenceNumber = 3
  sequenceSize = 4

Message 4:
  correlationId = batch-1001
  sequenceNumber = 4
  sequenceSize = 4
~~~

This trio answers three distinct questions:

- **`correlationId`**: *Which group/sequence does this message belong to?*
- **`sequenceNumber`**: *At which position in that sequence does this message sit?*
- **`sequenceSize`**: *By contract, how many parts is this sequence expected to have?*

### 3.1. Sequence Numbers Start at 1

When a Splitter splits a standard collection into N parts and generates sequence metadata, positions are typically numbered **1, 2, ..., N**.

| `sequenceNumber` | `sequenceSize` | Interpretation |
|---:|---:|---|
| 1 | 4 | First part of a four-part sequence |
| 2 | 4 | Second part |
| 3 | 4 | Third part |
| 4 | 4 | Final part |
| 0 | 4 | Invalid under the example's 1-based contract |
| 5 | 4 | Exceeds sequence size |

Do not confuse `sequenceNumber=1` with index 1 of a Java `List` (the **second** element under zero-based indexing). If you need to look up the element in a list, the corresponding index is `sequenceNumber - 1` after validation.

### 3.2. Sequence Size Is Not the Count of Arrived Messages

Seeing `sequenceSize=4` represents the **expected size** of the sequence, not "four messages are currently in the store."

For example, at a given point in time:

~~~text
group.key = batch-1001
expected sequenceSize = 4
received numbers = [1, 3]
received message count = 2
missing numbers = [2, 4]
~~~

If message 3 arrives first, `sequenceSize` is still 4. Resequencer can hold it until release conditions are met.

### 3.3. CorrelationId Is Not MessageHeaders.ID

`MessageHeaders.ID` is the ID of a single **message instance**. When four parts are created by a Splitter, each part can carry a different ID while sharing the same `correlationId`.

~~~text
ID(msg1) = UUID-A      correlationId = batch-1001
ID(msg2) = UUID-B      correlationId = batch-1001
ID(msg3) = UUID-C      correlationId = batch-1001
ID(msg4) = UUID-D      correlationId = batch-1001
~~~

If grouped by individual message ID, each message becomes its own group, and Resequencer will never have enough related parts to reorder.

### 3.4. Java Constants

Spring Integration provides header names via `IntegrationMessageHeaderAccessor`:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;

String correlationHeader =
        IntegrationMessageHeaderAccessor.CORRELATION_ID;

String numberHeader =
        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER;

String sizeHeader =
        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE;
~~~

Prefer using constants over scattering raw header strings across multiple files. When integrating with producers outside Spring, verify the **name, type, serialization**, and meaning of metadata at the integration boundary.

## 4. How Does Resequencer Differ from Aggregator?

Both can use `MessageGroupStore` and correlation/release strategies, but their **output shapes differ**.

~~~mermaid
flowchart TB
    I["Arriving parts: 3,1,2"] --> R["Resequencer"]
    I --> A["Aggregator"]
    R --> R1["Message(1)"]
    R --> R2["Message(2)"]
    R --> R3["Message(3)"]
    A --> O["Single Message(Collection[1,2,3])"]
~~~

| Criterion | Resequencer | Aggregator |
|---|---|---|
| Goal | Restore message ordering | Combine multiple messages into one result |
| Input | N related messages | N related messages |
| Typical output | N messages emitted in order | One aggregated message |
| Payload | Preserves each message's payload | Builds a collection payload or new DTO |
| Sequence number | Used as sort key | May be used for release condition |
| Sequence size | Indicates when sequence is complete | Indicates group completeness in Splitter cases |
| Group state | Yes | Yes |
| Partial release | Can emit contiguous prefixes | Can emit partial aggregated results per config |
| When to use | Downstream needs each item in order | Downstream needs a combined result |

**Do not add an Aggregator just to sort** if downstream still needs individual messages. Conversely, if downstream needs the total amount of an entire order, Resequencer does not produce `OrderTotal`; you can use `.resequence().aggregate()` or an appropriate output processor.

## 5. How Are Headers Generated by a Splitter?

An `AbstractMessageSplitter` is responsible for adding correlation/sequence metadata to child messages. For a collection of known size, the sequence can be fully described.

~~~java
import java.util.List;

List<String> parts = List.of(
        "parse", "validate", "persist", "publish");
~~~

When a message containing this collection passes through a Splitter, the child messages can carry:

~~~text
payload="parse"     sequenceNumber=1 sequenceSize=4
payload="validate"  sequenceNumber=2 sequenceSize=4
payload="persist"   sequenceNumber=3 sequenceSize=4
payload="publish"   sequenceNumber=4 sequenceSize=4
~~~

All must share the **same correlationId of the split batch**. This is why the Splitter → ExecutorChannel → Resequencer pattern is common: Splitter generates metadata, executor lets parts process asynchronously, and Resequencer uses that metadata to restore emission order.

### 5.1. Using Resequencer Without a Splitter

An external producer can also send messages with sequence metadata—for example, a batch file chunked in service A and sent over a broker.

However, not every message broker automatically provides `sequenceNumber` and `sequenceSize` compatible with Spring Integration. When attaching headers manually, you must specify and verify:

- Each group has a correlation key that does not collide with other groups.
- Each part has a positive sequence number following the chosen convention.
- Parts in the same group have consistent sequence sizes.
- No two different payloads share the same sequence number without a conflict policy.
- Late, missing, or replayed messages are handled per contract.
- Headers cannot be spoofed to mix data from another tenant.

### 5.2. When a Splitter Has an Unknown-Size Iterator

Spring Integration can split an `Iterator`/`Iterable` without knowing the part count in advance. When the part count cannot be inferred, `sequenceSize` may be set to **0**.

~~~text
iterator -> part #1: sequenceNumber=1, sequenceSize=0
         -> part #2: sequenceNumber=2, sequenceSize=0
         -> ...
         -> part #N: sequenceNumber=N, sequenceSize=0
~~~

**`sequenceSize=0` means "total number of parts unknown" in this case, not a sequence of literally zero parts.** A default release strategy requiring the full size cannot rely on 0 to determine completion.

Design options:

1. If possible, materialize a finite collection with known N before splitting; mind memory usage.
2. Use an explicit end event/marker to signal completion.
3. Configure a custom release policy based on a verified completion signal.
4. Use timeout/expiry with partial results only if business rules allow.
5. For very long streams, consider stream processing/partitioning tools instead of a resequencer holding the entire group.

**Never overwrite `sequenceSize=0` with a guessed size** just to force group release.

## 6. Grouping and Ordering Mechanism

Suppose a producer emits a sequence N=4, but arrival order is:

~~~text
3 → 1 → 4 → 2
~~~

Resequencer typically works in these steps:

1. Read `correlationId` to look up the group.
2. Store the message in the group's `MessageGroupStore`.
3. Read `sequenceNumber` to determine logical order.
4. Use the release policy to decide whether enough required parts are present.
5. Emit messages in ascending sequence number order.
6. Retain or complete group metadata per configuration to handle late arrivals.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant R as Resequencer
    participant S as MessageGroupStore
    participant O as Output

    P->>R: Part 3/4
    R->>S: Store (3)
    P->>R: Part 1/4
    R->>S: Store (1,3)
    P->>R: Part 4/4
    R->>S: Store (1,3,4)
    P->>R: Part 2/4
    R->>S: Store (1,2,3,4)
    S-->>R: Group complete
    R->>O: Part 1
    R->>O: Part 2
    R->>O: Part 3
    R->>O: Part 4
~~~

The diagram illustrates **wait-for-full-sequence release mode**. When partial release is enabled, some parts may be emitted earlier while still respecting ordering constraints.

## 7. Complete-Sequence Release (Default)

Per Spring Integration documentation, `releasePartialSequences` defaults to `false`: Resequencer waits for the **complete group** before emitting ordered messages.

Suppose a group has `sequenceSize=4`:

| Arrival | Stored Sequences | Immediate Output |
|---|---|---|
| 3 | [3] | None yet |
| 1 | [1,3] | None yet |
| 4 | [1,3,4] | None yet |
| 2 | [1,2,3,4] | Emits 1,2,3,4 in order |

Pros:

- Simple guarantee that the entire sequence is present before emission.
- Sensible when downstream should only receive parts if the whole batch completes.
- Easy to test with QueueChannel: output stays empty until the final part.

Cons:

- One missing part holds back all waiting parts.
- Latency depends on the slowest part.
- Message store must retain many parts when gaps occur.
- Unsuitable for unbounded streams or indeterminable sequence sizes.

### 7.1. "Complete" Must Check Sequence Metadata

Do not simply write:

~~~java
// Anti-pattern for sources that may send duplicates:
return group.size() == expectedSequenceSize;
~~~

If a group contains two messages with `sequenceNumber=2` and is missing `sequenceNumber=3`, message count does not reflect a complete sequence. Use a release policy aware of sequence numbers/duplicates, along with deduplication or a conflict policy before the resequencer.

Spring Integration has default release behavior aligned with sequence metadata, but **do not treat the default as a business-level exactly-once guarantee**.

## 8. Partial-Sequence Release: Incremental Emission of Contiguous Segments

Resequencer also supports `releasePartialSequences(true)`: allowing a **validly ordered contiguous sequence segment** to be released early rather than waiting for the entire group.

Example with N=4 and arrival order:

~~~text
2 → 1 → 4 → 3
~~~

Expected behavior under incremental contiguous segment release:

| Arriving Message | Available Parts | Parts Eligible for Ordered Emission |
|---:|---|---|
| 2 | [2] | Part 1 missing, held |
| 1 | [1,2] | Emit 1 then 2 |
| 4 | [4] waiting | Part 3 missing, held |
| 3 | [3,4] | Emit 3 then 4 |

~~~mermaid
flowchart LR
    A["Arrival: 2"] --> B["Hold 2"]
    B --> C["Arrival: 1"]
    C --> D["Emit: 1,2"]
    D --> E["Arrival: 4"]
    E --> F["Hold 4"]
    F --> G["Arrival: 3"]
    G --> H["Emit: 3,4"]
~~~

**Important:** partial release **must not arbitrarily skip gaps**. Once 1 and 2 have been emitted, if 4 arrives while 3 is missing, 4 must not be emitted ahead of 3 merely because 4 is present.

### 8.1. When to Use Partial Release?

- Downstream can start processing prefixes early.
- Already-emitted parts do not need revision when later parts arrive.
- Latency matters more than waiting for the full batch.
- Temporary gaps still need to be tracked.
- A timeout/expiry policy exists in case some parts never arrive.

### 8.2. Partial Release Does Not Replace Timeout/Expiry

`releasePartialSequences(true)` allows sending valid parts early. Meanwhile, `sendPartialResultOnExpiry` governs behavior when a **group expires**, which is a separate mechanism. Do not confuse "partial" in these two configuration names: one refers to **emitting contiguous segments during reception**, while the other refers to **handling expired groups**.

### 8.3. Cost of Partial Release

Finding contiguous valid segments and tracking already-emitted sequences can consume CPU/memory, especially for large groups or many gaps. Resequencer is best suited for **relatively short sequences with few gaps**. For huge unbounded event streams, consider key partitioning or a stream processor with a dedicated state store.

## 9. Reading Metadata Safely in Java

Avoid unsafe casts from `MessageHeaders`, especially when data arrives from brokers or HTTP adapters with differing header mappers/serializers.

### 9.1. Observation Snapshot

~~~java
public record SequenceSnapshot(
        String stage,
        String correlationId,
        int sequenceNumber,
        int sequenceSize
) {}
~~~

`sequenceNumber` and `sequenceSize` are metadata of the **message being observed**. A Resequencer emitting 1,2,3,4 does not change all output messages to have the same sequence number.

### 9.2. Helper to Read from Message

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

public final class SequenceInspector {

    private SequenceInspector() {}

    public static SequenceSnapshot snapshot(
            String stage, Message<?> message) {

        Object correlation = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID);

        Integer number = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                Integer.class);

        Integer size = message.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                Integer.class);

        if (correlation == null
                || number == null
                || size == null) {
            throw new IllegalArgumentException(
                    "SEQUENCE_HEADERS_REQUIRED");
        }

        if (number < 1) {
            throw new IllegalArgumentException(
                    "SEQUENCE_NUMBER_INVALID");
        }

        // size=0: unknown size; size>0: known length.
        if (size < 0 || (size > 0 && number > size)) {
            throw new IllegalArgumentException(
                    "SEQUENCE_SIZE_INVALID");
        }

        return new SequenceSnapshot(
                stage,
                correlation.toString(),
                number,
                size);
    }
}
~~~

This function serves as an **inspector/validation** helper for the example, not a replacement for the framework resequencing strategy. Calling `toString()` on correlation is only appropriate under an observation contract with controlled types/values; if secure group keys or byte arrays are used, provide a dedicated identifier encoder and avoid logging arbitrary objects.

### 9.3. Validation at Ingress

If messages are created by an internal Splitter, Spring can generate valid headers automatically. However, for data from untrusted clients, verify:

- Correlation ID is present, in the right namespace, and belongs to the right tenant.
- Sequence number is a positive integer starting at 1.
- Sequence size is a positive integer, or 0 **only if the contract allows unknown length**.
- For known size, `sequenceNumber <= sequenceSize`.
- Every message in the group shares the same sequence size per contract.
- No two conflicting payloads share the same sequence number.
- Cap maximum size to prevent DoS via forged metadata.

**Do not** silently rewrite `sequenceNumber=0` to 1 or `sequenceSize=-1` to 0. That is invalid or incompatible data and must be handled per contract.

## 10. Creating Messages with Sequence Headers Without a Splitter

Below is a test/adapter example for creating metadata manually. When a real Splitter is present, **prefer letting the Splitter create headers** rather than building them manually.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public record Part(String batchId, String value) {}

public final class SequencedMessages {

    private SequencedMessages() {}

    public static Message<Part> part(
            String batchId, int number, int total, String value) {

        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException(
                    "BATCH_ID_REQUIRED");
        }
        if (total < 1 || number < 1 || number > total) {
            throw new IllegalArgumentException(
                    "INVALID_SEQUENCE_RANGE");
        }

        return MessageBuilder
                .withPayload(new Part(batchId, value))
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        batchId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        total)
                .setHeader("businessCorrelationId", batchId)
                .build();
    }
}
~~~

**Java note:** the two top-level `public` declarations in the example must live in separate source files named `Part.java` and `SequencedMessages.java` in a real project.

Adding `businessCorrelationId` helps with business tracing, but do not confuse that field with `correlationId` used by Resequencer by default.

## 11. Java DSL: Resequencer in Spring Integration

Spring Integration Java DSL supports `.resequence()`. The example below creates a **standalone** flow receiving messages that already carry sequence headers.

### 11.1. Default Complete-Sequence Flow

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
public class CompleteResequencerConfig {

    @Bean(name = "resequencer.complete.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "resequencer.complete.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow completeResequencerFlow() {
        return IntegrationFlow
                .from("resequencer.complete.input")
                .resequence()
                .channel("resequencer.complete.output")
                .get();
    }
}
~~~

This is a resequencer with default correlation/release behavior for sequences having complete metadata. `DirectChannel` receives input synchronously, and `QueueChannel` holds output for a JUnit test to read message by message.

There is no need to write a `@Resequencer`-annotated method: Spring Integration documentation does not provide a dedicated annotation equivalent to some other endpoints. Use the DSL or version-appropriate XML/bean endpoints.

### 11.2. Partial Release Flow

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
public class PartialResequencerConfig {

    @Bean(name = "resequencer.partial.input")
    public MessageChannel input() {
        return new DirectChannel();
    }

    @Bean(name = "resequencer.partial.output")
    public PollableChannel output() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow partialResequencerFlow() {
        return IntegrationFlow
                .from("resequencer.partial.input")
                .resequence(s ->
                        s.releasePartialSequences(true))
                .channel("resequencer.partial.output")
                .get();
    }
}
~~~

These two configuration classes are **alternative examples** that can be run/tested independently. If placed in the same project and context, distinct bean names as shown prevent endpoint contention or channel mix-ups.

### 11.3. Splitter → Executor → Resequencer Pattern

A canonical flow described by Spring Integration looks like:

~~~java
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.context.annotation.Bean;

// taskExecutor is an executor bean configured in the application.
@Bean
IntegrationFlow splitResequenceAggregateFlow() {
    return IntegrationFlow.from("work.batch")
            .split()
            .channel(MessageChannels.executor(taskExecutor))
            .resequence()
            .aggregate()
            .get();
}
~~~

This is an **illustrative configuration snippet inside a class where a `taskExecutor` field/bean already exists**, not a standalone compilable Java class. It demonstrates:

1. Splitter creates sequence headers.
2. ExecutorChannel can cause parts to arrive out of their original order.
3. Resequencer restores order.
4. Aggregator can combine emitted messages into one unified result.

If downstream only needs to process each **ordered** part individually, **remove `.aggregate()`**. If you want to assemble the entire result, Aggregator is a separate step from Resequencer.

## 12. Complete-Sequence Release Integration Test

The test reproduces the exact scenario: send `3,1,4,2` to a `DirectChannel` and read output from QueueChannel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.ArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = CompleteResequencerConfig.class)
class CompleteResequencerFlowTest {

    @Autowired
    @Qualifier("resequencer.complete.input")
    MessageChannel input;

    @Autowired
    @Qualifier("resequencer.complete.output")
    PollableChannel output;

    @Test
    void holdsUntilCompleteAndEmitsInSequenceOrder() {
        String group = "batch-complete-1001";

        assertTrue(input.send(
                SequencedMessages.part(group, 3, 4, "C")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 1, 4, "A")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 4, 4, "D")));
        assertNull(output.receive(0));

        assertTrue(input.send(
                SequencedMessages.part(group, 2, 4, "B")));

        List<Integer> numbers = new ArrayList<>();
        List<String> values = new ArrayList<>();

        for (int i = 0; i < 4; i++) {
            Message<?> next = output.receive(1000);
            assertNotNull(next);

            numbers.add(next.getHeaders().get(
                    IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                    Integer.class));

            values.add(((Part) next.getPayload()).value());
        }

        assertEquals(List.of(1, 2, 3, 4), numbers);
        assertEquals(List.of("A", "B", "C", "D"), values);
        assertNull(output.receive(0));
    }
}
~~~

**What this test proves:**

- Sequence numbers **1** through **4** carry ordering semantics.
- By default, Resequencer does not emit output before the group is complete.
- Output order follows sequence, **not arrival**.
- Output remains four **separate messages**, not a single collection.
- The group key identifies the four messages belonging to the same sequence.

The test does not prove messages were successfully processed in a downstream database or broker. If connected through an async channel, you must also test when the consumer actually completes.

### 12.1. Testing Two Independent Correlation Groups

When receiving:

~~~text
A#2, B#1, A#1, B#2
~~~

Resequencer must group by `correlationId` and emit each group in order. It does not need to guarantee **globally** that all messages of group A emit before group B if the two groups are independent.

With `sequenceSize=2` for each group, an integration test should use unique group keys and verify:

- Group A emits A#1 before A#2.
- Group B emits B#1 before B#2.
- No payload from group A appears in B's metadata.
- No global order is enforced between the two groups under higher concurrency.

## 13. Partial-Sequence Release Integration Test

The second test verifies the mode that emits contiguous prefixes without waiting for the full sequence size.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = PartialResequencerConfig.class)
class PartialResequencerFlowTest {

    @Autowired
    @Qualifier("resequencer.partial.input")
    MessageChannel input;

    @Autowired
    @Qualifier("resequencer.partial.output")
    PollableChannel output;

    private int nextSequence() {
        Message<?> next = output.receive(1000);
        assertNotNull(next);
        return next.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                Integer.class);
    }

    @Test
    void emitsOnlyContiguousPrefixAsItBecomesAvailable() {
        String group = "batch-partial-2001";

        input.send(SequencedMessages.part(group, 2, 4, "B"));
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 1, 4, "A"));
        assertEquals(1, nextSequence());
        assertEquals(2, nextSequence());
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 4, 4, "D"));
        assertNull(output.receive(0));

        input.send(SequencedMessages.part(group, 3, 4, "C"));
        assertEquals(3, nextSequence());
        assertEquals(4, nextSequence());
        assertNull(output.receive(0));
    }
}
~~~

These assertions describe the expected behavior of `releasePartialSequences(true)` for a finite, duplicate-free group with temporary gaps. Running the test against the project's library version verifies the actual implementation and lifecycle settings, especially if the project configures a custom release strategy or message store.

### 13.1. Why Not Test Partial Mode with a Synchronous Batch Split?

If a Splitter sends all parts 1,2,3,4 immediately and downstream does not alter order, the test could pass even if Resequencer had no effect. Sending **2,1,4,3** directly proves the logic holds across gaps and releases contiguous prefixes.

## 14. Validator/Inspector Unit Tests

A unit test independent of the Spring context verifies metadata constraints.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.integration.IntegrationMessageHeaderAccessor;

class SequenceInspectorTest {

    @Test
    void readsExpectedSequenceHeaders() {
        Message<Part> message =
                SequencedMessages.part("batch-1", 2, 4, "B");

        SequenceSnapshot snapshot =
                SequenceInspector.snapshot("ingress", message);

        assertEquals("batch-1", snapshot.correlationId());
        assertEquals(2, snapshot.sequenceNumber());
        assertEquals(4, snapshot.sequenceSize());
    }

    @Test
    void rejectsMissingCorrelationHeader() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                1)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                2)
                        .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> SequenceInspector.snapshot("ingress", input));
    }

    @Test
    void rejectsNumberLargerThanKnownSize() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                                "batch-2")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                5)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                4)
                        .build();

        assertThrows(
                IllegalArgumentException.class,
                () -> SequenceInspector.snapshot("ingress", input));
    }

    @Test
    void acceptsUnknownSizeWhenPolicyAllowsIt() {
        Message<String> input =
                MessageBuilder.withPayload("data")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                                "stream-1")
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                                3)
                        .setHeader(
                                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                                0)
                        .build();

        SequenceSnapshot snapshot =
                SequenceInspector.snapshot("ingress", input);

        assertEquals(0, snapshot.sequenceSize());
    }
}
~~~

**Test limitation:** `SequenceInspector` accepting `sequenceSize=0` does not mean the default Resequencer will complete such a sequence. It is only a valid metadata state if the application contract allows **unknown length**; the release mechanism still must be designed explicitly.

## 15. Common Sequence Metadata Errors

| Input metadata | Issue | Handling |
|---|---|---|
| `sequenceNumber=0`, `size=4` | Violates 1-based convention | Reject/validation |
| `number=-1` | Invalid position | Reject |
| `number=5`, `size=4` | Out of range | Reject |
| `number=2`, missing `correlationId` | Cannot determine group | Reject or custom correlation |
| `number=2`, `size="4"` as String | Type mismatch with contract | Normalize at adapter or reject |
| `number=3`, `size=0` | Unknown size | Custom completion policy if full release is needed |
| `number=2` appears twice | Duplicate/conflict | Dedup by eventId/partId |
| Sizes 4 and 5 in same group | Inconsistent metadata | Quarantine/contract violation |
| Two tenants use same group key | Risk of data mixing | Composite trusted key |
| Parts 1,3,4 present, 2 missing | Gap | Wait, timeout, partial policy |
| Huge sequence size sent by client | Risk of resource exhaustion | Cap size and apply quotas |
| Message arrives after group closes | Late arrival | Discard/correction per policy |

### 15.1. Duplicate sequenceNumber

Two messages with the same `sequenceNumber=2` may be:

- **Redelivery of the same event**: can be deduplicated by `eventId`.
- **Conflicting data**: two different payloads at the same position, requiring rejection or a versioning policy.
- **Upstream bug**: Splitter/producer generating unstable sequences.

Do not simply count messages and treat the group as complete. **Deduplication by MessageHeaders.ID** is also insufficient across replays if the new message has a different UUID. Use a durable event/part identity managed by the application.

### 15.2. Sequence Size Changing Across Parts

If part 1 carries `sequenceSize=4` while part 2 carries `sequenceSize=5`, that is an **inconsistent sequence contract**. Resequencer cannot infer a true ending from those numbers alone without an explicit policy. Validate the entire group or standardize at the producer, and route conflicting groups to error/quarantine.

### 15.3. Do Not Replace Sequence Numbers with Timestamps When Strict Ordering Is Required

Timestamps can collide, suffer from clock skew, or be generated on unsynchronized producers. If business rules require strict ordering, use a **logical sequence** assigned by an authoritative source (or appropriate key-partitioning) rather than hoping wall-clock sorting is always accurate.

## 16. Resequencer with Transformer, Filter, and Router

### 16.1. Transformer Can Strip Sequence Headers

If a Transformer returns a **new payload** via Spring Integration APIs, the framework usually propagates appropriate headers. If the application returns a manually constructed `Message<?>`, sequence headers can be lost unless handled by a copy/mapper.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> normalize(Message<String> input) {
    return MessageBuilder
            .withPayload(input.getPayload().strip())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

`copyHeaders(...)` is intended for **trusted internal flows**. At broker/API boundaries, whitelist headers carefully to avoid serializing `replyChannel`, security tokens, or internal objects.

### 16.2. Filter Drops a Part

If Splitter sets `sequenceSize=4` but a Filter drops part 2:

~~~text
Available: 1,3,4
Missing:   2
Expected:  4
~~~

- Complete release will never see a full sequence.
- Partial release can emit part 1, but 3 and 4 must wait on the gap at 2.
- At timeout, an explicit expiry/partial policy is needed.
- A Filter returning `false` is a business decision; **it does not automatically adjust sequence size**.

Design approaches:

1. Filter the collection before the Splitter, so only parts to be processed are split.
2. Emit a **skipped result/marker** at position 2 if downstream requires all slots.
3. Use a custom release/correction policy for intentionally skipped parts.
4. Configure timeout/expiry if the business accepts missing parts.

### 16.3. Router Branches After Splitter

If a Router sends parts 1,3 to branch A and 2,4 to B, neither branch may have a complete sequence for a Resequencer to release independently. When fan-in is needed, design converging output channels and preserve correlation/sequence headers.

### 16.4. Splitter → Resequencer → Aggregator

~~~mermaid
flowchart LR
    IN["List batch"] --> SPLIT["Splitter"]
    SPLIT --> EX["ExecutorChannel"]
    EX --> RS["Resequencer"]
    RS --> AG["Aggregator"]
    AG --> OUT["Single aggregate result"]
~~~

Resequencer helps **guarantee the order of messages entering Aggregator**, yet Aggregator remains a separate endpoint using groups and an output processor. If Aggregator does not require ordered parts to compute its result, Resequencer may be unnecessary; avoid adding state and latency just because an EIP exists.

### 16.5. Publish–Subscribe

A publish–subscribe channel can deliver the same message to multiple branches. If two branches send results back into a shared Resequencer without a dedicated sequence convention, duplicate sequence numbers may occur. Define a **fan-in result sequence** rather than blindly reusing metadata from broadcast copies.

## 17. Timeout, Expiry, Late Arrivals, and Empty Groups

Resequencer cannot force a producer to send a missing part. If part 2 is missing, the group may hold parts 3 and 4 indefinitely.

~~~mermaid
flowchart TD
    G["Waiting group"] --> C{"All valid parts present?"}
    C -->|Yes| OUT["Emit in sequence order"]
    C -->|No| T{"Group timeout/expiry?"}
    T -->|No| WAIT["Continue waiting"]
    T -->|Yes| P{"Policy allows partial on expiry?"}
    P -->|Yes| PART["Emit allowed parts per policy"]
    P -->|No| DISC["Discard / report incomplete"]
~~~

### 17.1. Timeout Is Not the Same as sendTimeout

- **Group timeout/expiry**: limits **how long to wait** for missing messages.
- **Send timeout**: time limit for sending output into a bounded-capacity channel, such as a bounded QueueChannel.

If a group is incomplete due to a missing part, increasing `sendTimeout` will not make the group release. Conversely, a complete group blocked on a full output queue is a dispatch/backpressure issue.

### 17.2. Emitting Partial Results on Group Expiry

Spring Integration has a `sendPartialResultOnExpiry` option on correlating handler configuration. It differs from `releasePartialSequences(true)`. When business rules permit emitting buffered messages upon group expiry, clarify:

- Are **gaps** tolerated in the sequence?
- Does downstream know which parts are missing?
- Is a message emitted on expiry considered final?
- Are subsequent late arrivals discarded, treated as corrections, or used to open a new group?
- Once cleaned up, must completed-group metadata remain to guard against replays?

Never emit an incomplete group to a business branch **requiring completeness** without an explicit partial-result contract.

### 17.3. Completed-Group Metadata

When a group releases or expires, Spring Integration can retain completed-group metadata in the store to detect late-arriving messages. Metadata storage mechanism, retention duration, and group removal options depend on message store/expiry configuration.

If metadata is purged too early, a late-arriving part can create a **new group missing its prefix** and wait endlessly. If kept forever, the store grows unboundedly. Set retention aligned with realistic replay windows.

## 18. MessageGroupStore, Concurrency, and Durability

Resequencer resembles Aggregator in needing to persist parts that cannot yet be released. An in-memory message store suits tests or applications that tolerate losing state on restart. When durability is required, choose a persistent `MessageGroupStore` and test it thoroughly.

### 18.1. Single JVM

- A `DirectChannel` yields a synchronous, easy-to-observe flow.
- Multiple producer threads can still submit to the same group concurrently.
- Never replace the store with an unlocked global `ArrayList`.
- Test groups with gaps, completion, duplicates, and timeouts.

### 18.2. Multiple Workers

With `ExecutorChannel`, parts may arrive out of order. Resequencer restores **emission** order, yet if downstream output crosses another executor, completion can still happen out of order. If business rules require strict serial commits, control downstream threading/concurrency by key.

### 18.3. Multiple JVMs

If messages sharing a correlation key are split across two app instances with separate in-memory stores, each instance may only receive some parts and never complete the group. Solutions include:

- Partition input by correlation key so all parts of a group reach the same instance.
- Use a shared/persistent message group store with proper locking.
- Use a stream-processing framework with keyed state and ordered partition semantics.
- Design a process manager if the sequence represents a long-running workflow.

### 18.4. Performance

Resequencer works best for relatively short finite sequences with few gaps. If millions of fragmented groups arrive with many missing messages, memory and CPU can rise as groups stay open too long. Monitor group counts, group age, and gaps; enforce quotas, timeouts, and security checks before admitting data into the store.

## 19. Retry and Idempotency

### 19.1. Retrying Input Parts

If a broker redelivers part 2, Resequencer may receive another message with the same logical sequence number but a different Message ID. You need:

- A stable `eventId` or `partId` across replays.
- Deduplication or conflict policy when the same sequence number recurs.
- Validation that all parts belong to the same correlation group.
- Bounded retries for infrastructure errors.
- No infinite retries for invalid metadata input.

### 19.2. Downstream Retries

Resequencer may emit messages 1,2,3 in order, while a downstream handler writes to the DB for 1 and fails on 2. When retrying the entire flow, part 1 may be emitted again. Resequencer **does not provide exactly-once side effects**.

Use idempotency keys in handlers, transactions/outbox where needed, and verify actual outcomes. Never equate "emitted in sequence" with "all committed in sequence."

### 19.3. Error Channel

On a synchronous `DirectChannel`, send/output errors can bubble back to the caller. On async executors/brokers, exceptions may travel via `ErrorMessage` and adapter-specific error handling. A missing message keeping a group unreleased **is not necessarily an exception**, so dedicated metrics/timeouts are required rather than relying solely on an error channel.

## 20. Monitoring sequenceNumber/sequenceSize

A Resequencer system needs visibility into both **inbound message counts** and **completion status and latency per sequence**.

| Metric/log | Meaning | Notes |
|---|---|---|
| `resequencer_messages_received_total` | Inbound part count | Can label by flow |
| `resequencer_messages_emitted_total` | Emitted part count | Not equal to group count |
| `resequencer_groups_open` | Open waiting sequences | Monitor memory/store |
| `resequencer_group_age_seconds` | Group age | Detect stuck groups |
| `resequencer_gaps_detected_total` | Gaps observed | Distinguish transient vs real gaps |
| `resequencer_expired_total` | Expired groups | Investigate missing parts |
| `resequencer_duplicates_total` | Duplicate sequence numbers/event IDs | Dedup/conflict policy |
| `resequencer_late_arrivals_total` | Parts arriving after group closure | Retention/producer SLA |
| `resequencer_output_failures_total` | Dispatch failures | Distinct from group timeout |
| `resequencer_buffered_messages` | Buffered parts | Capacity/backpressure |

A structured log example:

~~~text
flow=invoice-line-resequence
correlationId=batch-1001
sequenceNumber=3
sequenceSize=4
receivedUnique=[1,3]
missingCount=2
releaseMode=COMPLETE
emitted=false
groupAgeMs=1500
traceId=trace-1001
~~~

This example illustrates state representation. Do not log full payloads containing customer or payment information. Do not use `correlationId`, `orderId`, `eventId`, or `traceId` as high-cardinality metric labels; keep them in logs/traces governed by security policies.

### 20.1. A Sequence Gap Does Not Automatically Prove Data Loss

If you see parts 1 and 3 but not 2, possible reasons include:

- Part 2 is still processing slowly.
- Broker is retrying delivery.
- Producer omitted a part.
- Incorrect metadata on part 2 routed it to another group.
- Filter/Router dropped part 2.
- The event may arrive late past the deadline.

Check `groupAge` and deadlines before concluding a part is permanently lost.

### 20.2. Trace and Business Correlation

`traceId` tracks execution hops across services. `correlationId` lets Resequencer group parts. `businessCorrelationId` links a long-running business entity like an order/invoice. They may relate to one another, but **are not identical by default**, especially across multi-request or multi-producer systems.

## 21. Common Pitfalls

### Pitfall 1 — Using Zero-Based sequenceNumber

**Symptom:** producer creates parts 0,1,2 for a size=3 sequence; Resequencer does not operate under the 1-based contract.

**Fix:** number 1..N, or have an ingress adapter convert per contract with tests.

### Pitfall 2 — Treating sequenceSize as Received Part Count

**Symptom:** when a group holds two messages, code sets `sequenceSize=2` even though the producer expects four.

**Fix:** keep sequenceSize as the **expected total**, tracking received count separately.

### Pitfall 3 — Omitting correlationId

**Symptom:** parts fail to enter the same group or fail with missing group key errors.

**Fix:** use a unique key properly scoped to batch/tenant and validate before Resequencer.

### Pitfall 4 — Duplicates Causing False Completion

**Symptom:** part 2 arrives twice and the app counts three messages even though part 3 is missing.

**Fix:** deduplicate by eventId/sequence key and validate the sequence set; never release based on raw count alone.

### Pitfall 5 — SequenceSize=0 While Expecting Complete Release

**Symptom:** an iterator produces sequenceSize=0; the default flow cannot determine when the sequence ends.

**Fix:** use an explicit end signal/custom release or switch to a finite collection when appropriate.

### Pitfall 6 — Enabling Partial Release and Expecting Gaps to Be Skipped

**Symptom:** the app expects part 4 to be emitted before part 3 arrives.

**Fix:** partial release only emits valid contiguous segments and never skips missing parts automatically.

### Pitfall 7 — Missing Timeout/Expiry

**Symptom:** groups with missing parts retain state forever and memory grows.

**Fix:** configure deadlines and an incomplete-group policy; monitor group age.

### Pitfall 8 — Losing Headers After a Transformer

**Symptom:** payload survives, but sequence headers vanish when building a new Message.

**Fix:** test propagation of `correlationId`, `sequenceNumber`, `sequenceSize`, trace, and business IDs across every step.

### Pitfall 9 — Using Timestamps Instead of Logical Sequences

**Symptom:** clock skew or identical timestamps cause unstable output ordering.

**Fix:** use stable sequence numbers from an authoritative sequencing source.

### Pitfall 10 — Using Resequencer as a Substitute for Aggregator

**Symptom:** downstream expects a collection but receives multiple individual messages.

**Fix:** add an Aggregator if N→1 is needed; Resequencer only provides ordered N→N.

### Pitfall 11 — Assuming Resequencing Means Strict DB Commit Ordering

**Symptom:** output emits 1,2,3, yet async workers commit 2 before 1.

**Fix:** control concurrency/partitioning/processing acknowledgements downstream.

### Pitfall 12 — Splitting One Group Across Multiple App Instances

**Symptom:** each in-memory store holds partial items and no group ever completes.

**Fix:** route the same correlation key to a single instance or use a shared store with locking.

### Pitfall 13 — Forgetting Late Arrivals After Group Completion

**Symptom:** stale parts open new groups, duplicate output, or wait forever.

**Fix:** configure completed-group metadata retention and a late-arrival policy.

### Pitfall 14 — Trusting Client-Supplied Sequence Headers

**Symptom:** a client sends another tenant's correlationId or an enormous sequenceSize, causing data mixing or DoS.

**Fix:** authenticate/authorize, cap sizes, namespace group keys, and validate data at ingress.

## 22. Practice Exercises

**Exercise 1 — Identify Metadata.** For a four-part batch, write a table of `correlationId`, `sequenceNumber`, and `sequenceSize`, and explain why sequence numbers start at 1.

**Exercise 2 — Complete Release.** Set up `CompleteResequencerConfig`. Send in order 3,1,4,2; verify no output is produced until complete and then 1,2,3,4 are received.

**Exercise 3 — Partial Release.** Set up `PartialResequencerConfig`. Send 2,1,4,3 and assert output is emitted in two segments: 1,2 and 3,4.

**Exercise 4 — Two Interleaved Groups.** Send A#2, B#1, A#1, B#2. Assert each group maintains its own order without mixing payloads.

**Exercise 5 — Unknown sequenceSize.** Create an Iterator-based Splitter with unknown size and observe `sequenceSize=0`. Design an end signal or custom release strategy rather than waiting on default complete release.

**Exercise 6 — Duplicate Messages.** Send two messages with the same sequenceNumber=2 but different eventIds. Choose a dedup/reject/resolve policy and test that no wrong release occurs.

**Exercise 7 — Transformer Dropping Headers.** Build a Transformer returning a new Message without copying sequence headers and observe the flow failure. Fix it with proper header mapping and verify readback.

**Exercise 8 — Filter Dropping a Part.** Split 1..4, filter out part 2, and send the remainder through Resequencer. Observe the gap and design a skipped marker or timeout.

**Exercise 9 — Splitter → Executor → Resequencer.** Add random delays to part handlers to induce arrival disorder. Assert output order always follows sequence number, without assuming business commit order in a subsequent async consumer.

**Exercise 10 — Resequencer → Aggregator.** After ordering, append an Aggregator to produce one collection. Compare N→N vs N→1 and output metadata.

**Exercise 11 — Late Arrival.** Complete a group and resend a part; record the outcome under completed-group retention and error/discard policies.

**Exercise 12 — Testing Resource Limits.** Create many incomplete groups to test timeout/expiry, open group count, memory, and metrics.

### Self-Check Questions

1. How do `sequenceNumber` and `sequenceSize` differ?
2. Why does `sequenceNumber` start at 1 in the standard Splitter example?
3. What role does `correlationId` serve that `sequenceNumber` cannot replace?
4. Does `sequenceSize=4` prove all four parts have been received?
5. Does Resequencer turn N messages into a single collection?
6. How do complete-sequence release and partial-sequence release differ?
7. When part 4 arrives before part 3, can partial release emit 4?
8. Why does `sequenceSize=0` require a separate completion policy?
9. Why can two messages with the same `sequenceNumber` cause bugs?
10. If a Filter drops a part, what problem does Resequencer encounter?
11. Can `replyChannel` or `traceId` replace `correlationId`?
12. If output is 1,2,3 in order, has the downstream DB necessarily committed in that order?
13. Which errors should be retried, and which invalid metadata errors should not be retried forever?
14. On JVM restart, does an in-memory `MessageGroupStore` preserve gap state?
15. Why must we cap `sequenceSize` and validate tenant ownership on client messages?
16. What tests are needed to prove the system never mixes two different batches?
17. How does `sendPartialResultOnExpiry` differ from `releasePartialSequences(true)`?
18. When should you drop Resequencer in favor of keyed stream processing?

## 23. Implementation Checklist

- [ ] Clearly define 1-based sequence rules and unknown sequence size handling.
- [ ] Every message has a proper correlation key without cross-tenant/group mixing.
- [ ] Known sequence size reflects the expected total and is consistent across the group.
- [ ] Do not use raw group count instead of verifying a complete sequence set.
- [ ] Validate missing, wrong-type, out-of-range, and duplicate headers.
- [ ] Deliberately choose complete or partial release.
- [ ] Configure timeout, expiry, and an incomplete-group policy.
- [ ] Distinguish `releasePartialSequences` from `sendPartialResultOnExpiry`.
- [ ] Choose a `MessageGroupStore` matching memory and durability requirements.
- [ ] Handle concurrency, shared stores, and locking across multiple workers or instances.
- [ ] Ensure Splitter/Transformer/Router/Filter preserve required metadata per contract.
- [ ] Never use `sequenceNumber` as proof of business commit.
- [ ] Make downstream idempotent for replayable/redeliverable events.
- [ ] Test arrival orders 3,1,4,2 and 2,1,4,3.
- [ ] Test two interleaved groups, duplicates, missing parts, and late arrivals.
- [ ] Track metrics for group age, gaps, expired groups, received, and emitted counts.
- [ ] Enforce input size/quota limits and header security for external sources.
- [ ] Never run an unbounded stream through an in-memory resequencer without a segmentation/expiry strategy.

## 24. Summary

In Spring Integration, **`sequenceNumber` indicates a message's logical position**, **`sequenceSize` indicates the expected total number of parts**, and **`correlationId` identifies the related sequence**. For parts produced by a Splitter from a known-size collection, `sequenceNumber` is typically **1..N**, `sequenceSize=N`, and the correlation ID is shared across the batch. Resequencer buffers messages in the same group and emits them **in sequence number order** rather than arrival order, **without merging them** like Aggregator.

The default configuration waits for the complete sequence; `releasePartialSequences(true)` enables early emission of valid contiguous segments. Cases involving `sequenceSize=0` from unknown-length Splitters, missing parts, duplicates, or expired groups require additional policies; metadata alone cannot guarantee completion or exactly-once semantics.

To apply this in **SPRING_INTEGRATION_PATTERN**, use Splitter/Java DSL to create and preserve sequence metadata, Resequencer for ordering, Aggregator only when N→1 is genuinely required, and combine Filter, Router, Gateway, retry, error channel, and tracing/correlation for safe operation. Above all, **test actual emission order**, error/expiry behavior, and idempotency rather than trusting header numbers alone.

### References

- Spring Integration Reference — Resequencer: https://docs.spring.io/spring-integration/reference/resequencer.html
- Spring Integration Reference — Splitter: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference — Aggregators and Resequencers (Java DSL): https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration API — ResequencerSpec: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ResequencerSpec.html
- Spring Integration API — SequenceSizeReleaseStrategy: https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html
- Spring Integration API — IntegrationMessageHeaderAccessor: https://docs.spring.io/spring-integration/api/org/springframework/integration/IntegrationMessageHeaderAccessor.html
- JUnit 5 User Guide — Testing with JUnit Jupiter: https://junit.org/junit5/docs/current/user-guide/
