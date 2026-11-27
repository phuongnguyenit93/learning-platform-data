# Priority Headers and Comparators in Spring Integration

## 1. What Problem Does Priority Solve?

In a messaging system, not every request needs to be processed in the exact order it was received. For example, an incident notification message may need to be dequeued before a periodic report synchronization message. **Priority Channel** is the Enterprise Integration Pattern designed for that scenario: messages **waiting in the queue** are selected based on priority level.

In Spring Integration, \`PriorityChannel\` provides a \`PollableChannel\` capable of ordering message retrieval based on the **default \`priority\` header** or an application-supplied \`Comparator<Message<?>>\`.

This lesson **“Priority Headers and Comparators”** belongs to the **Priority** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on building loosely coupled, extensible message flows using Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation; Priority Channel adds a mechanism for selecting *which message is dequeued next* when multiple messages are waiting to be processed.

After this lesson, you will be able to:

1. Attach and read the \`priority\` header using the proper data type.
2. Distinguish priority-based ordering from FIFO and business completion order.
3. Write a \`Comparator<Message<?>>\` to sort according to custom rules.
4. Define how to handle two messages with the same priority level.
5. Test Priority Channel using small messages with deterministic results.
6. Recognize limitations around starvation, capacity, retries, and parallel processing.

## 2. What Does Priority Channel Order?

Consider three messages placed into the queue before the consumer starts receiving:

| Send order | Payload | \`priority\` header | Expected dequeue order |
| --- | --- | --- | --- |
| 1 | \`"report"\` | 1 | 3 |
| 2 | \`"order"\` | 5 | 2 |
| 3 | \`"incident"\` | 9 | 1 |

With \`PriorityChannel\`'s default comparator, messages with a **higher priority** are dequeued before messages with a lower priority.

~~~mermaid
flowchart LR
    P["Producer"] -->|"report: 1"| Q["PriorityChannel"]
    P -->|"order: 5"| Q
    P -->|"incident: 9"| Q
    Q -->|"1. incident (9)"| C["Consumer / Poller"]
    Q -->|"2. order (5)"| C
    Q -->|"3. report (1)"| C
~~~

This has three important limitations:

- **Priority applies only to messages still sitting in the queue.** If the consumer already picked up \`"report"\` before \`"incident"\` arrived, the new message cannot preempt work already in progress.
- **Priority Channel does not decide routing.** Router chooses *which channel receives a message*; Priority Channel decides *which message in the channel's queue is dequeued next*.
- **Dequeue order differs from completion order.** When consumers process in parallel, a message dequeued earlier can still finish after another message.

Comparison with a standard \`QueueChannel\`:

| Channel type | Dequeue order | When to choose |
| --- | --- | --- |
| \`QueueChannel\` | FIFO (queue entry order) | Processing in arrival order is required |
| \`PriorityChannel\` | By priority or comparator | Urgent tasks must be pulled ahead of backlog |
| \`DirectChannel\` | Delivered directly to subscriber | Synchronous handoff without a priority queue |
| \`ExecutorChannel\` | Dispatched via an executor | Asynchronous processing; completion order depends on the executor |

## 3. The \`priority\` Header: Representation and Usage

Spring Integration recognizes the \`priority\` header name via \`IntegrationMessageHeaderAccessor.PRIORITY\`. This header has type **\`Integer\`**, for example:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> urgent = MessageBuilder.withPayload("incident-42")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 9)
        .setHeader("requestId", "req-42")
        .build();

Integer priority = (Integer) urgent.getHeaders()
        .get(IntegrationMessageHeaderAccessor.PRIORITY);
// priority == 9
~~~

On the message just created, \`priority=9\` is processing-order metadata, while \`requestId\` serves business tracing. Spring Integration does not automatically treat a message as urgent just because the payload contains the word \`"urgent"\`; when using the default comparator, the corresponding header must be set before the message enters \`PriorityChannel\`.

### Choosing a Consistent Priority Scale

The framework does not automatically define “Low”, “High”, or “Urgent” levels for your business domain. Your application should publish a convention, for example:

| Business level | \`priority\` value |
| --- | --- |
| Background sync | 1 |
| Regular processing | 5 |
| Urgent incident | 9 |

In this table, **a larger number is dequeued first**. Your convention may use different numbers, but it must remain consistent across all producers and through every Transformer, Gateway, or adapter. Do not confuse this with priority schemes where **a smaller number means higher urgency**, such as systems numbering P1 as the most severe. If the business uses P1/P2/P3, **map them to sortable numbers** or use an appropriate comparator.

### Missing or Wrongly Typed Headers

Define a policy at the queue entry point:

- **Missing \`priority\`:** Should an application-defined default be applied? If so, attach that value in a header normalization step before the queue so tests remain explicit.
- **\`priority="9"\` as a String:** This differs from \`priority=9\` as an Integer. Do not assume \`PriorityChannel\` coerces strings to numbers automatically. Validate types and convert intentionally.
- **Out-of-range business values:** If the system only permits 1–9, validate values like \`-10\`, \`0\`, or \`1000\` before enqueuing; this is an application rule.

Example header validation function before use:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

static int validatedPriority(Message<?> message) {
    Object raw = message.getHeaders()
            .get(IntegrationMessageHeaderAccessor.PRIORITY);

    if (!(raw instanceof Integer value) || value < 1 || value > 9) {
        throw new IllegalArgumentException(
                "priority must be an Integer from 1 to 9");
    }
    return value;
}
~~~

The function above illustrates a **sample business policy**, not a mandatory Spring Integration constraint. Separating validation from queue sorting produces clear errors and prevents the comparator from encountering unexpected data types during queue operations.

## 4. Default Comparator of PriorityChannel

Spring Integration provides constructors \`new PriorityChannel()\` and \`new PriorityChannel(capacity)\`. When no custom comparator is supplied, the channel compares messages using the \`priority\` header.

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel channel = new PriorityChannel(10);

channel.send(MessageBuilder.withPayload("low")
        .setHeader("priority", 1)
        .build());
channel.send(MessageBuilder.withPayload("medium")
        .setHeader("priority", 5)
        .build());
channel.send(MessageBuilder.withPayload("high")
        .setHeader("priority", 9)
        .build());

Message<?> first = channel.receive(0);  // "high"
Message<?> second = channel.receive(0); // "medium"
Message<?> third = channel.receive(0);  // "low"
~~~

**Key point:** All three messages were already in the queue **before** the first \`receive\` call. This is the condition required for the test to prove dequeue ordering from a backlog. If a test sends while a poller is concurrently running, a low-priority message might already be dequeued before the high-priority message arrives.

### When Two Messages Have the Same Priority

For example:

~~~text
Input:
  A: priority=9
  B: priority=9
  C: priority=1

Guaranteed expectation by priority:
  {A, B} are dequeued before C.

Without a tie-break contract:
  you must not assume A always precedes B.
~~~

\`PriorityChannel\` is not a stable FIFO queue for messages with equal comparison keys. If deterministic ordering is required between two messages with the same priority, design a **secondary criterion** in the comparator (such as an application-assigned enqueue sequence number).

## 5. Runnable Test Example: Priority Header

The following is a standalone **JUnit 5** class; testing the default comparator does not require starting a Spring Boot context or a real poller. Compatible Spring Integration and JUnit/AssertJ dependencies are required.

Create \`src/test/java/example/PriorityHeaderComparatorTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

class PriorityHeaderComparatorTest {

    private static Message<String> message(String payload, int priority) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", "test-" + payload)
                .build();
    }

    private static String nextPayload(PollableChannel channel) {
        Message<?> result = channel.receive(1_000);
        assertThat(result).isNotNull();
        return (String) result.getPayload();
    }

    @Test
    void higher_priority_is_polled_first() {
        PriorityChannel channel = new PriorityChannel(10);

        assertThat(channel.send(message("report", 1))).isTrue();
        assertThat(channel.send(message("order", 5))).isTrue();
        assertThat(channel.send(message("incident", 9))).isTrue();

        assertThat(nextPayload(channel)).isEqualTo("incident");
        assertThat(nextPayload(channel)).isEqualTo("order");
        assertThat(nextPayload(channel)).isEqualTo("report");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void each_priority_is_kept_in_the_message_header() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(message("low", 1));
        channel.send(message("high", 9));

        Message<?> first = channel.receive(1_000);
        Message<?> second = channel.receive(1_000);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getPayload()).isEqualTo("high");
        assertThat(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY)).isEqualTo(9);
        assertThat(second.getPayload()).isEqualTo("low");
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY)).isEqualTo(1);
        assertThat(first.getHeaders().get("requestId"))
                .isEqualTo("test-high");
    }

    @Test
    void high_priority_arriving_after_enqueue_can_overtake_low() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(message("low-first", 1));
        channel.send(message("high-later", 9));

        // No consumer has picked up "low-first" yet, so priority takes effect.
        assertThat(nextPayload(channel)).isEqualTo("high-later");
        assertThat(nextPayload(channel)).isEqualTo("low-first");
    }

    private static Message<String> businessMessage(
            String payload, int urgency, long enqueueOrder) {
        return MessageBuilder.withPayload(payload)
                .setHeader("businessUrgency", urgency)
                .setHeader("enqueueOrder", enqueueOrder)
                .build();
    }

    private static Comparator<Message<?>> businessComparator() {
        return Comparator
                .<Message<?>>comparingInt(m ->
                        (Integer) m.getHeaders().get("businessUrgency"))
                .reversed()
                .thenComparingLong(m ->
                        (Long) m.getHeaders().get("enqueueOrder"));
    }

    @Test
    void custom_comparator_breaks_ties_by_enqueue_order() {
        PriorityChannel channel =
                new PriorityChannel(10, businessComparator());

        // Send order intentionally differs from enqueueOrder key order.
        channel.send(businessMessage("urgent-later", 9, 3L));
        channel.send(businessMessage("background", 1, 1L));
        channel.send(businessMessage("urgent-earlier", 9, 2L));

        assertThat(nextPayload(channel)).isEqualTo("urgent-earlier");
        assertThat(nextPayload(channel)).isEqualTo("urgent-later");
        assertThat(nextPayload(channel)).isEqualTo("background");
        assertThat(channel.receive(0)).isNull();
    }
}
~~~

**Reading the results:**

- \`higher_priority_is_polled_first\`: three messages sent in order **1 → 5 → 9** are dequeued in order **9 → 5 → 1**.
- \`each_priority_is_kept_in_the_message_header\`: priority only affects queue order; the message preserves its payload and required business headers.
- \`high_priority_arriving_after_enqueue_can_overtake_low\`: a later-arriving message can overtake **if** the earlier message has not yet been dequeued.
- \`custom_comparator_breaks_ties_by_enqueue_order\`: at the same urgency level 9, the smaller \`enqueueOrder\` comes first; urgency level 1 still comes last.

These tests create and consume their own queue independently of poller schedules, other threads, or leftover data from previous tests. When you need to test full \`IntegrationFlow\` wiring, use a separate flow test as shown later.

## 6. Custom Comparator: Interpreting Order Correctly

The constructor \`PriorityChannel(int capacity, Comparator<Message<?>> comparator)\` lets you define custom ordering. A comparator follows the standard Java contract:

| Return value of \`compare(a, b)\` | Meaning in the priority queue |
| --- | --- |
| Negative | \`a\` comes before \`b\` |
| Zero | The two messages are equal according to the comparator's ordering |
| Positive | \`a\` comes after \`b\` |

Therefore, if **higher priority comes first**, the comparator must return a negative number when comparing a message with \`priority=9\` against a message with \`priority=1\`. \`Comparator.comparingInt(...).reversed()\` expresses this policy clearly.

### Two-Criteria Comparator

An easy-to-understand business rule:

1. **Higher urgency** is dequeued first.
2. Within the same urgency level, **smaller enqueue sequence number** is dequeued first.

~~~java
Comparator<Message<?>> ordering = Comparator
        .<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("businessUrgency"))
        .reversed()
        .thenComparingLong(message ->
                (Long) message.getHeaders().get("enqueueOrder"));

PriorityChannel channel = new PriorityChannel(100, ordering);
~~~

\`businessUrgency\` and \`enqueueOrder\` are **application-defined headers**. When a custom comparator is provided, \`PriorityChannel\` uses the comparator's criteria; the default \`priority\` header will **not automatically** be factored into ordering unless you include it in the comparison function.

Do not use \`message.getHeaders().getId()\` as a substitute for enqueue order: UUIDs do not reflect an ascending send sequence. Likewise, a message \`timestamp\` can collide or reflect message creation time at the producer rather than queue arrival order. If you need FIFO within the same priority, assign a monotonic sequence number right at the enqueue boundary, handling duplicate keys or multiple producers properly.

### Rules for Designing a Safe Comparator

- **Consistent:** Given the same two messages, the comparator should produce the same result for as long as they remain in the queue.
- **Transitive:** If A precedes B and B precedes C, A must precede C; avoid ad-hoc logic that introduces contradictory ordering.
- **Side-effect free:** Never write to a database, call an API, or mutate payloads or headers inside \`compare\`.
- **Do not rely directly on current wall-clock time to “boost priority”:** A priority queue does not automatically re-sort all elements simply because time passes.
- **Do not assume headers are always valid:** Validate types, value ranges, and presence at ingestion; handle defaults intentionally.
- **Provide a tie-breaker when needed:** A comparator returning 0 for two messages does not guarantee FIFO between them.

Example of a comparator with inverted intent:

~~~java
// WRONG if you want "larger number has higher priority":
Comparator<Message<?>> wrong = Comparator.comparingInt(
        message -> (Integer) message.getHeaders().get("priority"));

// CORRECT for the same policy:
Comparator<Message<?>> correct =
        Comparator.<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("priority"))
                .reversed();
~~~

The \`wrong\` comparator places smaller numbers before larger numbers. A test using **two messages with different priorities** will catch this inverted-order bug.

## 7. Integrating PriorityChannel into an IntegrationFlow

\`PriorityChannel\` is a **PollableChannel**, so consumers in Spring Integration typically require a **poller** to retrieve messages. Example configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
class PriorityFlowConfiguration {

    @Bean("work.priority")
    PriorityChannel priorityWork() {
        return new PriorityChannel(100);
    }

    @Bean("work.done")
    QueueChannel done() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow priorityConsumer() {
        return IntegrationFlow.from("work.priority",
                        source -> source.poller(
                                Pollers.fixedDelay(500)
                                        .maxMessagesPerPoll(1)))
                .handle(String.class,
                        (payload, headers) -> "processed:" + payload)
                .channel("work.done")
                .get();
    }
}
~~~

With the configuration above, producers send messages to \`work.priority\`; the poller periodically retrieves the next message, the handler processes the payload, and sends the reply to \`work.done\`. The value \`500\` is the delay between poller triggers in this example, **not** a business deadline or latency SLA.

~~~mermaid
flowchart LR
    IN["Gateway / Transformer / Router"] --> Q["PriorityChannel\nqueued by priority"]
    CLOCK["Poller"] --> Q
    Q --> H["Service Activator"]
    H --> OUT["Output Channel"]
    H -. "Exception" .-> ERR["Configured error flow"]
~~~

**Why shouldn't you use the flow above to assert that three messages always exit strictly as 9, 5, 1?** A running poller might dequeue the first message before the other two are enqueued. When testing the **queue ordering** policy, the most deterministic approach is to **enqueue the full backlog before starting \`receive\`**, as in the unit tests in Section 5. When testing **wiring and business processing**, use the application context, output channel, completion signals, and bounded timeouts.

If you want to test a poller deterministically, explicitly control when it fires (for example, starting the endpoint after building the backlog or controlling the trigger/poller in the test environment). Never rely on \`Thread.sleep\` hoping the queue fills up before the poller runs.

## 8. Capacity, Backpressure, and Limits of Priority

A \`PriorityChannel\` can be configured with a capacity limit, such as \`new PriorityChannel(100)\`. When the queue is full, sends may block waiting for space or fail depending on timeout and channel configuration.

Crucially: **high priority does not mean permission to force entry into a full queue** by automatically evicting a low-priority message. These are two distinct policies:

1. **Admission/backpressure:** When the queue is full, is a new message accepted?
2. **Ordering:** Among messages already in the queue, which one is dequeued next?

Example test for a queue with capacity 2:

~~~java
@Test
void full_priority_queue_cannot_accept_unlimited_messages() {
    PriorityChannel channel = new PriorityChannel(2);

    assertThat(channel.send(message("low", 1))).isTrue();
    assertThat(channel.send(message("medium", 5))).isTrue();

    // Timeout 0: do not wait for free space.
    assertThat(channel.send(message("urgent", 9), 0)).isFalse();

    assertThat(nextPayload(channel)).isEqualTo("medium");
    assertThat(nextPayload(channel)).isEqualTo("low");
}
~~~

This test can be added to \`PriorityHeaderComparatorTest\` in Section 5. It shows that **a full queue is a condition independent of priority level**. If the business wants reserved capacity for urgent requests, design dedicated headroom, separate queues, admission control, or an explicit eviction policy; \`PriorityChannel\` by default does not replace older messages with newly arriving urgent ones.

### Starvation

If \`priority=9\` messages arrive continuously, \`priority=1\` messages can wait for a very long time. This is **starvation**: one class of work is delayed indefinitely because another class is always preferred.

Operational control strategies include:

- Capping the amount of work processed per priority tier in each processing cycle.
- Splitting flows by priority group with dedicated resources/consumers.
- Defining an SLA or maximum wait threshold to trigger rebalancing.
- Using an intentional **aging** mechanism: raising a message's priority over time through a re-ordering or re-enqueueing step, rather than expecting a clock-reading comparator to update the heap automatically.

Testing starvation requires a longer workload than a single-queue ordering test: emit a continuous stream of high-priority messages while low-priority ones are waiting, then verify that your policy guarantees progress for the low-priority messages.

## 9. Relationship with Router, Filter, Retry, and Correlation

Priority Channel is usually part of a larger pipeline:

~~~mermaid
flowchart TD
    A["Input"] --> B{"Router"}
    B -->|"online"| C["Header Enricher\npriority=9"]
    B -->|"batch"| D["Header Enricher\npriority=1"]
    C --> E["PriorityChannel"]
    D --> E
    E --> P["Poller + Service Activator"]
    P --> OUT["Output"]
    P -. "Failure after retries" .-> ERR["Error channel / recovery"]
~~~

### Router and Filter

Router determines the path; Filter drops messages matching a condition; PriorityChannel orders messages **that have already been accepted into the same queue**. If Filter drops a high-priority message, it never enters queue ordering. Therefore, tests should separate:

- **Routing/filtering:** Is the message permitted into \`work.priority\`?
- **Ordering:** Once multiple messages are inside, is the dequeue order correct?

### Transformer and Header Enricher

If priority is derived from the payload (such as \`severity="CRITICAL"\`), you can use a Header Enricher before PriorityChannel to translate business data into a numeric \`priority\`. Tests must verify the header is correct **before enqueuing**, because modifying priority after a message is already in the queue does not automatically re-sort the queue.

### Retry and Error Channel

A high-priority message is dequeued first, yet the handler may fail and be retried. Retries can occupy a worker for a long time, affecting other messages. The retry policy governs resource occupation time, whereas PriorityChannel only governs dequeue order while messages wait.

If errors are handled by putting messages back into the queue, clearly define:

- Is the original priority preserved?
- Should priority be lowered or a delay added to prevent tight retry loops?
- Does the message retain \`requestId\`, correlation, and idempotency keys?
- Once retries are exhausted, which policy governs routing to the error channel/dead-letter queue?

Never assume that merely adding a \`priority\` header gives the system **exactly-once** delivery, completion ordering, or safe retries.

### Splitter, Aggregator, and Correlation

When Splitter produces multiple fragments, priority can be propagated to child messages. However, if fragments of the same group are retrieved at different speeds, Aggregator must still rely on \`correlationId\`, \`sequenceNumber\`, \`sequenceSize\`, or a configured release strategy to reassemble the group.

Even if all fragments have \`priority=9\`, that does **not** mean they will automatically be dequeued contiguously as a single group. Messages from other groups can share the same priority. Tests must separately verify **queue ordering** and **grouping correctness**.

## 10. Priority Header and Comparator Test Matrix

| Scenario | Minimum test data | Key assertion |
| --- | --- | --- |
| High priority dequeued first | Two messages with priority 1 and 9 | Receive 9 before 1 when both are already in the queue |
| Multiple levels | Three messages with priority 1, 5, 9 | Receive 9, 5, 1 |
| Reversed send order | Send 1 then 9 | Receive 9 then 1 if no consumer has polled yet |
| Preserve payload/headers | Message with priority 9 and \`requestId\` | Payload and business headers remain unchanged |
| Two equal-priority messages | Two messages with priority 9 | Do not rely on default FIFO; add a secondary comparator if needed |
| Business-driven comparator | \`businessUrgency\` and \`enqueueOrder\` | Higher urgency first; ties broken by smaller order |
| Wrong comparator direction | Priority 1 and 9 | Test fails if comparator returns 1 before 9 |
| Missing header | Message without priority | Default/validation policy matches requirements |
| Wrongly typed header | Priority as String \`"9"\` | Rejected or intentionally normalized before the queue |
| Full queue | Capacity 2, send 3 messages | Third send follows timeout/capacity policy |
| Consumer already took work | Send low, consumer receives, then send high | Do not assume high can preempt running low work |
| Retry or handler error | Selected message causes handler failure | Retry/error handling follows policy; do not confuse ordering with delivery |

## 11. Practice Exercises

### Exercise A — SLA-Based Priority Levels

Define levels \`CRITICAL=9\`, \`NORMAL=5\`, \`BACKGROUND=1\`. Send three messages in the order BACKGROUND, NORMAL, CRITICAL into \`PriorityChannel\` with no active consumer. Write a JUnit test asserting the dequeue order is CRITICAL, NORMAL, BACKGROUND, while payload and \`requestId\` remain unchanged.

### Exercise B — Comparator for P1/P2/P3

The system supports \`P1\` as highest severity and \`P3\` as lowest. Write a comparator that reads the business header \`incidentLevel\` and sorts strictly in P1 → P2 → P3 order. Add a test with two distinct P1 messages and an explicit tie-break rule. If using \`String\`, do not rely on lexicographical comparison if level naming conventions might change.

### Exercise C — Missing or Wrongly Typed Headers

Send one message missing priority and one message with \`priority="9"\` as a String through a validation step before the queue. Choose a clear policy: assign default, normalize, or reject. Tests must prove no invalidly typed message enters the queue before normalization.

### Exercise D — When the Queue Is Full

Create \`PriorityChannel(2)\`; send two messages with levels 1 and 5, then send a level 9 message with timeout 0. Explain why the level 9 message is not necessarily accepted. Propose an appropriate backpressure policy and write a test proving it.

### Exercise E — Adding a Poller and Parallel Processing

Starting from \`PriorityFlowConfiguration\`, build a backlog before allowing the consumer to run and verify the **dequeue** order. Then enable parallel processing with two different processing durations and compare the **completion** order. Document the exact ordering guarantees the application actually needs.

## 12. Pre-Production Checklist

1. Do producers attach \`priority\` with the proper \`Integer\` type and business scale?
2. Does the comparator return a negative number when a message **should be dequeued first**?
3. Is stable ordering required for two messages with equal priority? If so, what is the secondary criterion?
4. Is the comparator pure, consistent, and independent of mutable data or clocks changing inside the queue?
5. Are queue capacity and timeouts sized appropriately for high traffic?
6. Is there a plan for starvation or low-priority messages waiting too long?
7. Do ordering tests enqueue the full backlog **before** polling starts?
8. Is poll order distinguished from completion order when multiple consumers are used?
9. Do business headers, correlation, and retry/error mechanisms still uphold their contracts?
10. Can each test run independently without being affected by leftover messages from another test?

**Target outcome:** Looking at any \`PriorityChannel\`, you should be able to identify **which value determines priority**, **which message the comparator puts first**, **what happens on ties**, and **how far along the pipeline that ordering remains valid**. Testing each of these lets you introduce prioritization in Spring Integration while preserving scalability and flow observability.

### References

- Spring Integration Reference — [PriorityChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html).
- Spring Integration API — [PriorityChannel](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/channel/PriorityChannel.html).
