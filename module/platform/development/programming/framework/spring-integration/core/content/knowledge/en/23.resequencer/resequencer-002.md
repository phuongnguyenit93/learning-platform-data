# Ordering messages by sequence

In the **Resequencer** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson focuses on restoring message order after a processing step that can reorder messages. You will connect knowledge of `Message`, `MessageChannel`, endpoints, and Java DSL to design stateful flows, handle missing messages, and test outputs.

After this lesson, you will be able to:

- Design a sequence header contract for a finite group of messages.
- Choose between waiting for the complete group and releasing contiguous segments early.
- Configure `resequence()` using Java DSL.
- Identify correlation errors, missing sequences, and downstream out-of-order execution.
- Test both output ordering and the exact timing when messages are eligible for release.

## 1. The problem: finishing first does not mean coming first

A report export request is split into four parts. Workers run independently and finish in this order:

```text
Business order:       1 → 2 → 3 → 4
Arrival order:        3 → 1 → 4 → 2
Required forwarding:  1 → 2 → 3 → 4
```

If results are wired straight into the report writer, part 3 may be written before part 1. A FIFO queue here only preserves **queue arrival** order: `3, 1, 4, 2`. The order that needs to be restored was determined before the workers ran.

A resequencer holds related messages in groups by `correlationId` and forwards each message according to `sequenceNumber`. It does not combine payloads into a single result message like an aggregator. The framework supports waiting for the entire sequence or releasing a valid segment earlier. [Resequencer functionality](https://docs.spring.io/spring-integration/reference/resequencer.html).

```mermaid
flowchart LR
    A["List of report parts"] --> B["Splitter assigns sequence"]
    B --> C["Workers run in parallel"]
    C --> D["Results arrive: 3, 1, 4, 2"]
    D --> E["Resequencer"]
    E --> F["Outgoing messages: 1, 2, 3, 4"]
    F --> G["Report writer"]
```

In this problem, place the resequencer after the reordering step and before the step that relies on order.

## 2. The three-header contract

For a finite group of four parts:

| Header | Java constant in `IntegrationMessageHeaderAccessor` | Example | Role |
|---|---|---|---|
| `correlationId` | `CORRELATION_ID` | `report-42/run-7` | Identifies a single report generation run |
| `sequenceNumber` | `SEQUENCE_NUMBER` | `3` | Position in the group, starting at 1 |
| `sequenceSize` | `SEQUENCE_SIZE` | `4` | Total number of positions in the group |

In this lesson's contract, sequence numbers and sizes are `Integer`, every message in the same group declares the same size, and `1 <= sequenceNumber <= sequenceSize`. This is the data used by the sequence-based release mechanism; the count of arrived messages cannot substitute for a missing position. [SequenceSizeReleaseStrategy source code](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.java).

Example of the third message:

```java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> thirdPart = MessageBuilder
        .withPayload("Part 3 content")
        .setHeader(
                IntegrationMessageHeaderAccessor.CORRELATION_ID,
                "report-42/run-7")
        .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                3)
        .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                4)
        .build();
```

Three design rules:

1. **Assign positions before parallel processing.** Numbering by worker completion time loses the original order.
2. **Distinguish execution runs.** `report-42/run-7` and `report-42/run-8` must be two separate groups even for the same report.
3. **Preserve headers when creating subsequent messages.** A transformer may change the payload, but the result must return to the right group and position.

A standard splitter populates correlation and sequence headers automatically. For a `List`, the size is known. For an iterator whose size cannot be determined, `sequenceSize` may be `0`; in that case, you cannot rely solely on size to wait for the full group. [Splitter reference](https://docs.spring.io/spring-integration/reference/splitter.html).

The examples that follow use finite sequences of known size. An unbounded event stream needs additional windowing or group-closing rules.

## 3. Distinguishing grouping, release decision, and ordering

When reading a configuration, answer four questions:

| Question | Related component | Decision in this lesson |
|---|---|---|
| Which group does the message belong to? | Correlation strategy | `correlationId` header |
| When is it eligible to be emitted? | Release strategy | Wait for complete group or release contiguous segments |
| Where are unreleased messages held? | `MessageGroupStore` | In-memory store |
| In what order are they emitted? | Resequencer group processor | Ascending by `sequenceNumber` |

Java DSL lets you customize correlation, release, and store inside `resequence(...)`. This is a stateful endpoint: receiving a message does not necessarily produce output right away. [Aggregators and Resequencers in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html).

The release strategy answers **when**, not **which position comes first**. Avoid replacing it with `group.size() == 4` just because the example has four parts; the business contract might produce a group of seven parts.

## 4. Two message release modes

### 4.1. Wait for the full group: `releasePartialSequences(false)`

The default mode does not release early. For a valid group of size 4, the resequencer waits until complete and then forwards `1, 2, 3, 4` as individual messages. [SequenceSizeReleaseStrategy API](https://docs.spring.io/spring-integration/docs/7.1.x/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html).

| Newly arrived message | Held positions | Newly emitted messages |
|---|---|---|
| 3 | 3 | None |
| 1 | 1, 3 | None |
| 4 | 1, 3, 4 | None |
| 2 | Complete 1, 2, 3, 4 | 1, 2, 3, 4 |

Choose this mode if the requirement is “Do not start forwarding until all parts have been received.”

Emitting multiple messages consecutively does not automatically create an atomic business transaction. If the writer persists part 1 and fails on part 2, atomicity must still be addressed through a transaction or dedicated recovery mechanism.

### 4.2. Early release: `releasePartialSequences(true)`

In early release mode, the lowest waiting position must directly follow the last released position. The processor selects a contiguous segment and stops at the gap. Initially nothing has been released, so the starting eligible position is 1. [Partial release API](https://docs.spring.io/spring-integration/docs/6.3.2/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html), [group processor source code](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/aggregator/ResequencingMessageGroupProcessor.java).

With the same input `3, 1, 4, 2`:

| Newly arrived message | Released before this step | Newly emitted messages | Positions still waiting |
|---|---|---|---|
| 3 | None yet | None | 3 |
| 1 | None yet | 1 | 3 |
| 4 | 1 | None | 3, 4 |
| 2 | 1 | 2, 3, 4 | None |

After releasing 1, the resequencer still waits for 2; it does not release 3 merely because 3 is less than 4.

Mental model for reading the table:

```text
lastReleased = 0

Receive 3: next required position is 1 → wait
Receive 1: emit 1 → lastReleased = 1
Receive 4: next required position is 2 → wait
Receive 2: emit 2, 3, 4 → lastReleased = 4
```

This is an explanatory model, not a replacement for the framework's implementation code.

### 4.3. Choosing based on the output contract

| Report writer requirement | Choice |
|---|---|
| Start only when all parts are available | Wait for the full group |
| Can write part 1 while part 2 is still running | Release contiguous segments early |
| Part 2 is missing, yet still want to write part 3 and mark missing | Also configure a missing-part handling policy |
| Must roll back all parts if one part fails | Requires transactions or a compensation mechanism |

Early release reduces waiting latency for leading parts that are already ready. If part 1 is the slowest part, the whole group still has to wait for it.

## 5. Java DSL configuration for hands-on practice

The example uses the Spring Integration 6.x Java DSL API. Each flow has its own store. Inputs use `DirectChannel` to observe synchronous behavior; outputs use `QueueChannel` so tests can receive one message at a time.

The learning project needs:

- `org.springframework.integration:spring-integration-core`.
- `org.junit.jupiter:junit-jupiter` for the tests in the next section.

Use versions managed by your project's BOM; with Spring Boot, keep Spring Boot, Spring Framework, and Spring Integration aligned.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.SimpleMessageStore;

@Configuration
@EnableIntegration
public class ResequencingFlows {

    @Bean
    public DirectChannel strictInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel strictOutput() {
        return new QueueChannel(32);
    }

    @Bean
    public DirectChannel partialInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel partialOutput() {
        return new QueueChannel(32);
    }

    @Bean
    public QueueChannel discarded() {
        return new QueueChannel(32);
    }

    @Bean
    public SimpleMessageStore strictStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public SimpleMessageStore partialStore() {
        return new SimpleMessageStore();
    }

    @Bean
    public IntegrationFlow strictFlow() {
        return IntegrationFlow.from(strictInput())
                .resequence(spec -> spec
                        .releasePartialSequences(false)
                        .messageStore(strictStore())
                        .groupTimeout(30_000L)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel(discarded()))
                .channel(strictOutput())
                .get();
    }

    @Bean
    public IntegrationFlow partialFlow() {
        return IntegrationFlow.from(partialInput())
                .resequence(spec -> spec
                        .releasePartialSequences(true)
                        .messageStore(partialStore())
                        .groupTimeout(30_000L)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel(discarded()))
                .channel(partialOutput())
                .get();
    }
}
```

`messageStore`, `groupTimeout`, `sendPartialResultOnExpiry`, and `discardChannel` are correlation endpoint options; `releasePartialSequences` is provided by `ResequencerSpec`. [Correlation configuration API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html), [ResequencerSpec API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/ResequencerSpec.html).

Both flows preserve contiguous order during normal release; the difference is when emission begins.

The capacity of 32 is for small datasets. In long-running deployments, `discarded` needs a consumer and an appropriate retention policy rather than holding messages indefinitely.

## 6. Testing order and release timing

Place the configuration class and test class in the same package, or add the appropriate imports. Each test creates its own context so no state is shared.

```java
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

class ResequencingFlowsTest {

    @Test
    void waitsForTheWholeSequence() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ResequencingFlows.class)) {
            MessageChannel input =
                    context.getBean("strictInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("strictOutput", QueueChannel.class);

            assertTrue(input.send(part("batch-A", 3, 4)));
            assertTrue(input.send(part("batch-A", 1, 4)));
            assertTrue(input.send(part("batch-A", 4, 4)));
            assertNull(output.receive(0));

            assertTrue(input.send(part("batch-A", 2, 4)));
            for (int number = 1; number <= 4; number++) {
                assertNext(output, "batch-A", number, 4);
            }
            assertNull(output.receive(0));
        }
    }

    @Test
    void releasesOnlyTheNextContiguousSegment() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ResequencingFlows.class)) {
            MessageChannel input =
                    context.getBean("partialInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("partialOutput", QueueChannel.class);

            assertTrue(input.send(part("batch-B", 3, 4)));
            assertNull(output.receive(0));

            assertTrue(input.send(part("batch-B", 1, 4)));
            assertNext(output, "batch-B", 1, 4);
            assertNull(output.receive(0));

            assertTrue(input.send(part("batch-B", 4, 4)));
            assertNull(output.receive(0));

            assertTrue(input.send(part("batch-B", 2, 4)));
            for (int number = 2; number <= 4; number++) {
                assertNext(output, "batch-B", number, 4);
            }
            assertNull(output.receive(0));
        }
    }

    @Test
    void ordersEachCorrelationGroupIndependently() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ResequencingFlows.class)) {
            MessageChannel input =
                    context.getBean("strictInput", MessageChannel.class);
            QueueChannel output =
                    context.getBean("strictOutput", QueueChannel.class);

            assertTrue(input.send(part("A", 2, 2)));
            assertTrue(input.send(part("B", 1, 2)));
            assertNull(output.receive(0));

            assertTrue(input.send(part("B", 2, 2)));
            assertNext(output, "B", 1, 2);
            assertNext(output, "B", 2, 2);
            assertNull(output.receive(0));

            assertTrue(input.send(part("A", 1, 2)));
            assertNext(output, "A", 1, 2);
            assertNext(output, "A", 2, 2);
            assertNull(output.receive(0));
        }
    }

    private static Message<String> part(
            String group, int number, int size) {
        return MessageBuilder.withPayload(group + "-" + number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        group)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    private static void assertNext(
            QueueChannel output, String group, int number, int size) {
        Message<?> result = output.receive(1_000);
        assertNotNull(result);
        assertEquals(group + "-" + number, result.getPayload());
        assertEquals(
                group,
                result.getHeaders().get(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID));
        assertEquals(
                Integer.valueOf(number),
                result.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        Integer.class));
        assertEquals(
                Integer.valueOf(size),
                result.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        Integer.class));
    }
}
```

The three tests answer three questions:

- When one position is missing, does full-sequence waiting hold the entire group?
- Does early release stop at a gap and continue releasing once the gap is filled?
- Are two correlation groups independent of each other?

The third test shows that group B can finish before A. There is no global “A then B” ordering simply because a message for A appeared first.

In this configuration, `DirectChannel` invokes the endpoint on the sending thread, and `QueueChannel` supports timed receives. Thus you can check `receive(0)` immediately after `send` without `Thread.sleep`. When switching to asynchronous processing, wait on observable conditions rather than guessing completion timing. [DirectChannel and QueueChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

## 7. Pairing with a splitter and parallel workers

The following additional configuration assumes an input payload of `List<String>`. Add the beans to a `@Configuration` class with `@EnableIntegration`:

```java
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;

@Bean(destroyMethod = "shutdown")
public ExecutorService reportWorkers() {
    return Executors.newFixedThreadPool(4);
}

@Bean
public QueueChannel processedLines() {
    return new QueueChannel(64);
}

@Bean
public IntegrationFlow reportPartsFlow() {
    return IntegrationFlow.from("reportPartsInput")
            .split()
            .channel(MessageChannels.executor(reportWorkers()))
            .transform(
                    String.class,
                    value -> value.toUpperCase(Locale.ROOT))
            .resequence(spec -> spec
                    .releasePartialSequences(true)
                    .groupTimeout(30_000L)
                    .sendPartialResultOnExpiry(false)
                    .discardChannel("discarded"))
            .channel(processedLines())
            .get();
}
```

`discarded` is the bean already present in the practice configuration. `reportPartsInput` is a channel referenced by name in the DSL. The `split → executor → resequence` pattern is directly supported by Java DSL. [Java DSL flows with resequencer](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html).

With input `["introduction", "details", "conclusion"]`:

1. The splitter assigns positions 1, 2, 3 before dispatching through the executor.
2. Workers uppercase the payloads; completion order may differ from the original order.
3. The resequencer emits each part in position order.
4. The consumer reads `INTRODUCTION`, `DETAILS`, `CONCLUSION`.

Uppercasing represents a processing step such as rendering a page or normalizing a data row. The example does not try to force a specific completion order using artificial delays; the earlier tests already sent parts out of order intentionally.

If you need **one message containing the entire report**, add an aggregator or an appropriate result-combining step. `resequence()` does not perform that aggregation.

## 8. Missing messages, timeouts, and discards

Suppose a group has size 4, but only `1, 3, 4` arrive:

- Full-sequence waiting has forwarded nothing yet.
- Early release may already have emitted 1; parts 3 and 4 are waiting for 2.
- If part 2 never arrives, the group does not complete under normal sequence conditions.

The practice configuration uses:

```java
.groupTimeout(30_000L)
.sendPartialResultOnExpiry(false)
.discardChannel(discarded())
```

`groupTimeout` schedules handling for an unreleased group. When a new message arrives, the wait schedule is re-evaluated and may reset; this fixed value is not an absolute deadline from the start of the job. When a group is forced to terminate due to missing parts, `sendPartialResultOnExpiry(false)` chooses to discard the remaining held messages. [Group timeout rules](https://docs.spring.io/spring-integration/reference/aggregator.html#aggregator-and-group-timeout).

In the early-release experiment, discarding the waiting parts cannot recall part 1 that was already emitted. If the entire report must be canceled, the writer must manage a report session and perform a compensating action.

Two similarly named options apply to different situations:

| Option | Situation | Meaning |
|---|---|---|
| `releasePartialSequences(true)` | Normal release | Allows emitting the next contiguous segment |
| `sendPartialResultOnExpiry(true)` | Expired group handling | Allows emitting incomplete results under expiry handling |

Enabling partial results on expiry changes the completeness contract. You must define how the consumer handles missing parts and test which positions are actually emitted; do not infer expiry behavior from the normal-release table. [Correlation endpoint expiry options](https://github.com/spring-projects/spring-integration/blob/v6.5.10/spring-integration-core/src/main/java/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.java).

The resequencer retains group state after a timeout to identify late-arriving messages. While metadata of the finished group is retained, late messages are routed to discard. Recognition capability depends on metadata lifecycle and store cleanup. [ResequencingMessageHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/ResequencingMessageHandler.html).

### Distinguishing discards from exceptions

A message rejected by policy does not necessarily throw an exception. Malformed headers or downstream failures, however, can raise processing errors.

For a `DirectChannel` input, exceptions can propagate back to the `send` call. When running via an executor or scheduler, you need an error-handling path suited to the asynchronous context. A channel named `errorChannel` does not by itself replace a logging and recovery policy.

In the report problem, the discard path should record:

- Report key and run ID.
- Positions of held or discarded parts.
- Expected sequence size.
- Timestamp and next action: retry, cancel session, or handle manually.

These details help pinpoint which parts are missing rather than merely counting total failures.

## 9. Input contract and common pitfalls

### 9.1. Missing headers or wrong types

Place validation at the boundary if messages arrive from an external system. The following helper illustrates the lesson's finite-group contract:

```java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

static boolean validFiniteSequence(Message<?> message) {
    Object group = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.CORRELATION_ID);
    Object number = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
    Object size = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE);

    return group != null
            && number instanceof Integer sequenceNumber
            && size instanceof Integer sequenceSize
            && sequenceSize > 0
            && sequenceNumber >= 1
            && sequenceNumber <= sequenceSize;
}
```

This only validates a single message in isolation. It does not catch a group mixing `sequenceSize = 4` and `sequenceSize = 5`. Cross-message consistency must be enforced by the producer contract and stateful checks when needed.

If the source uses `0..N-1` indices or position codes like `"003"`, normalize them to `1..N` integers in the boundary adapter or transformer.

### 9.2. Accidentally merging runs

Two report exports both have positions `1..4`. If both use `correlationId = report-42` while overlapping, their parts risk being merged together.

The key should distinguish each execution run:

```text
tenant-8/report-42/run-7
tenant-8/report-42/run-8
```

If using a custom correlation strategy, the header or data forming the key must exist and stay intact throughout the journey.

### 9.3. Duplicate sequences and redelivery

The resequencer does not replace a system-wide idempotency mechanism. Detecting a duplicate sequence number within an active group does not prevent repeated side effects after a restart, metadata purge, or opening a new group.

In the report writer, you can use a business key `(runId, partNumber)` to avoid writing a part twice. The same key with different content is a conflict that must be handled explicitly.

### 9.4. A filter drops a position

The splitter produces four messages, and then a filter drops position 2. The remaining three messages may still declare size 4, leaving the resequencer waiting for the dropped part.

Depending on business rules, you can:

- Filter the list before the splitter assigns sequences.
- Emit a placeholder result for the skipped part so all positions remain present.
- Create a new group contract and intentionally renumber the sequence.

Do not reduce the size on a single message alone; the entire group must agree.

## 10. Scope of the ordering guarantee

### 10.1. Each correlation is an ordering domain

```text
A arrives: A2 ........ A1
B arrives: ... B1 B2 ...

A valid output: B1, B2, A1, A2
```

The guarantee to verify is `A1 before A2` and `B1 before B2`. If all groups must obey a single global order, the system must have a shared ordering rule.

### 10.2. Downstream steps can finish out of order

If the resequencer emits `1, 2, 3` into another executor:

```text
Resequencer emits:        1 → 2 → 3
Downstream completes:     3, 1, 2
```

An `ExecutorChannel` dispatches work to worker threads, so completion order can change again. If the writer requires ordered completion, use a sequential consumer per ordering domain or a position-controlled commit step. [ExecutorChannel characteristics](https://docs.spring.io/spring-integration/reference/channel/implementations.html#executorchannel).

Even when the resequencer fixes emission order, external service calls still need retry rules and success acknowledgments.

### 10.3. Correct order and idempotency are separate criteria

The writer persists part 1 and then the process crashes before saving the acknowledgment. On redelivery, part 1 may be processed again. The sequence order is still right, yet the data can be written twice.

Therefore, track three criteria separately: correct order, no duplicate side effects, and no lost parts.

## 11. Store and operations

The hands-on configuration uses the in-memory `SimpleMessageStore`. If the process stops while groups are waiting, do not expect that data to survive. For recovery requirements, choose a persistent `MessageGroupStore`. If multiple instances operate on the same group, use locks compatible with a shared model; in-process locks cannot coordinate across separate processes. [Store and lock configuration](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html).

A simple estimate for the report problem:

```text
500 waiting groups
× average 6 unreleased parts / group
× 4 KiB payload / part
≈ 12 MiB held payloads
```

This is payloads only, excluding headers, Java objects, group structures, and metadata. Measure actual memory usage rather than just summing content sizes.

| Metric to monitor | Sign requiring investigation |
|---|---|
| Incomplete group count | Producer dropping parts or group keys too fragmented |
| Held message count | Backlog of waiting data |
| Oldest group age | A few groups are stuck |
| Timeouts and discards count | Missing parts or late messages |
| Latency from arrival to release | Waiting time spent reordering |
| Downstream queue depth | Consumer processing slowly |

Spring Integration targets the resequencer at relatively short sequences with small gaps. Many fragmented groups with long-lived gaps call for revisiting how groups are partitioned and stored. [Resequencer usage scope](https://docs.spring.io/spring-integration/reference/resequencer.html).

Durable persistence also does not mean every timeout schedule is restored after a restart. Recovery design must account for stale groups in the store and a mechanism to scan or process them.

## 12. Extended practice

Use a new correlation ID or a new context for each experiment:

| Input | Mode | What to verify |
|---|---|---|
| `4, 2, 1, 3`; size 4 | Wait for complete | Only after the last send do `1, 2, 3, 4` appear |
| `2, 1, 4, 3`; size 4 | Early release | When 1 arrives emit `1, 2`; when 3 arrives emit `3, 4` |
| `1, 3`; size 3 | Wait for complete | No normal output yet |
| `1, 3`; size 3 | Early release | 1 emitted early; 3 waits for position 2 |
| `A2, B1, B2, A1`; each group has 2 parts | Wait for complete | B finishes before A; each group stays ordered |
| `sequenceNumber = 0` | Boundary check | Rejected by contract before entering the resequencer |

When testing timeouts, create a separate configuration with a short timeout and observe `discarded.receive(timeout)` with an appropriate wait limit. Confirm that discarded messages do not appear on normal output. Do not conclude timeout works merely because the test slept for some duration.

To evaluate a design, answer specifically: what is the group key, who assigns the sequence, under what condition does a group end, where do missing messages go, and which step guarantees the final write order. Those answers turn a `resequence()` configuration into an integration flow with verifiable behavior.
