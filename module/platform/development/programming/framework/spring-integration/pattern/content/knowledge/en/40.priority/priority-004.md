# Tie-Breakers for Equal Priorities in Spring Integration

## 1. The Problem: Two Messages Are Equally Important—Which One Goes First?

When using **Priority Channel** in Enterprise Integration Patterns, we typically want higher-urgency messages processed first. But what happens when **two or more messages share the same priority**? For example, two orders are both marked \`priority=9\`, or hundreds of events all belong to \`NORMAL\`.

Without specifying a **tie-breaker**, the dequeue order among equal-priority messages is not a contract the application should depend on. An earlier message might not be dequeued first if the queue structure or comparator makes no stability guarantee.

This lesson belongs to the **Priority** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation. A tie-breaker adds a **deterministic and testable** rule for dequeuing messages when multiple messages share the same priority level.

After this lesson, you will be able to:

1. Distinguish priority ordering from FIFO and business completion order.
2. Explain why comparing priority alone is insufficient on ties.
3. Design a \`Comparator<Message<?>>\` with a secondary key, such as a monotonically increasing sequence.
4. Choose the right boundary to assign the sequence so it reflects the promised order.
5. Test ordering across different priority levels and within the same level.
6. Analyze duplicate timestamps, multiple producers, parallel processing, and retries.

## 2. What Happens When the Comparator Returns 0?

In Java, \`Comparator.compare(a, b)\` returns:

| Return value | Meaning for the priority queue |
| --- | --- |
| Negative | \`a\` comes before \`b\` |
| Zero | The comparator considers \`a\` and \`b\` equivalent in **order** |
| Positive | \`a\` comes after \`b\` |

If you rely solely on \`priority\`, two \`priority=9\` messages compare as 0. Returning 0 **does not mean** the queue is forced to dequeue them in enqueue order.

~~~text
Send order      Message      Priority
-----------     --------     --------
1               A            9
2               B            9
3               C            5

Guaranteed by priority level:
  A and B are prioritized ahead of C, if all three are already in the queue.

Not guaranteed without a tie-breaker:
  that A must always be dequeued before B.
~~~

In Spring Integration, \`PriorityChannel\` is a \`PollableChannel\` that accepts an application-configured comparator. When comparing only by the \`priority\` header, do not build business logic that relies on FIFO among equal-priority messages unless you have verified another stabilizing mechanism and made it an explicit contract.

### Why Is This Bug Hard to Spot?

A test that sends A then B and happens to receive A then B can **still pass** even without an ordering guarantee. After a library upgrade, implementation change, higher load, multithreading, or mixing in messages of other priorities, the observed order may change. Tests should force the algorithm to demonstrate its tie-breaking rule explicitly rather than asserting the accidental outcome of a single run.

## 3. Distinguishing Three Types of Ordering

~~~mermaid
flowchart LR
    P["Producer"] -->|"send() time"| Q["PriorityChannel"]
    Q -->|"poll / receive order"| H["Consumer / Handler"]
    H -->|"Completion order"| O["Output"]
~~~

| Ordering type | Observation point | Does PriorityChannel guarantee it automatically? |
| --- | --- | --- |
| **Send order** | Producer calls \`send()\` | Determined by producer or multi-producer coordination |
| **Dequeue order** | Consumer calls \`receive()\` | Follows the comparator among waiting messages |
| **Completion order** | Handler emits result | Not guaranteed by the queue comparator |

A FIFO tie-breaker usually means: **among waiting messages with the same priority that entered the queue, the one recorded into the queue earlier must be dequeued first**. This is a contract about *dequeue order*, not a promise that all tasks finish in that same order.

If handlers run concurrently, message A can be dequeued before B yet finish after B. For flows requiring completion order, you must also control concurrency or use appropriate resequencing, correlation, and result handling.

## 4. Ways to Choose a Tie-Breaker

There is no single best secondary key for every case. What matters is that the criterion **fits business semantics** and remains immutable while the message sits in the queue.

| Tie-break key | Rule | Best suited when | Notes |
| --- | --- | --- | --- |
| **Monotonic sequence at enqueue** | Smaller sequence dequeued first | FIFO within the same priority on one queue is desired | Must be assigned at the exact boundary without duplicates |
| **Timestamp at enqueue** | Earlier timestamp dequeued first | Message age matters | Clock skew and resolution can cause ties; needs a third key |
| **Deadline** | Closer due time dequeued first | Explicit SLA deadlines exist | Not equivalent to FIFO |
| **Business sequence** | Smaller event sequence dequeued first | Business order per aggregate/tenant is needed | Must define sequence scope and missing cases |
| **Request ID / UUID** | String comparison for deterministic order | You only want consistent ordering when other keys tie | Does not reflect arrival order |
| **Tenant weight or aging** | Additional fairness criterion | Preventing starvation across groups is needed | May require a separate scheduler, not just a comparator |

**Do not use a message's UUID as proof of FIFO.** The \`id\` header identifies a message, but UUID comparison order does not correspond to queue arrival time.

**Do not treat the default timestamp as enqueue time.** A message's timestamp usually reflects when the message was created; it may travel through Gateways, Routers, Filters, or wait in another channel before reaching PriorityChannel.

## 5. Designing a Two-Key Comparator: Descending Priority, Ascending Sequence

A transparent policy:

1. Higher \`priority\` is dequeued first.
2. When \`priority\` is equal, smaller \`enqueueSequence\` is dequeued first.

Example:

| Payload | Priority | Enqueue sequence | Dequeue order |
| --- | --- | --- | --- |
| \`A\` | 9 | 20 | 1 |
| \`B\` | 5 | 1 | 4 |
| \`C\` | 9 | 21 | 2 |
| \`D\` | 9 | 22 | 3 |

\`B\` arrived very early yet has level 5, so it still sits behind all level-9 messages **currently in the queue**. Within level 9, sequences 20, 21, and 22 determine the order.

~~~mermaid
flowchart TD
    IN["Multiple waiting messages"] --> P{"Compare priority"}
    P -->|"Different"| PK["Higher priority first"]
    P -->|"Equal"| S{"Compare enqueueSequence"}
    S -->|"Different"| SK["Smaller sequence first"]
    S -->|"Duplicate"| T["Incomplete tie-break: add third key or reject"]
~~~

### Comparator in Java

~~~java
import java.util.Comparator;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;

static Comparator<Message<?>> priorityThenSequence() {
    return Comparator
            .<Message<?>>comparingInt(m ->
                    (Integer) m.getHeaders()
                            .get(IntegrationMessageHeaderAccessor.PRIORITY))
            .reversed()
            .thenComparingLong(m ->
                    (Long) m.getHeaders().get("enqueueSequence"));
}
~~~

With the comparator above:

- If \`a.priority=9\` and \`b.priority=5\`, then \`a\` comes first.
- If both priorities are 9 and \`a.enqueueSequence=20\`, \`b.enqueueSequence=21\`, then \`a\` comes first.
- If both keys are equal, the comparator returns 0: order remains unspecified.

Ensure **both headers have the proper types** before messages enter the queue. In this example, \`priority\` is \`Integer\` and \`enqueueSequence\` is \`Long\`; a string \`"20"\` cannot be cast directly to \`Long\`.

## 6. Complete JUnit 5 Example: Testing Ordering and Tie-Breakers

The snippet below uses **Java 17**, **JUnit 5**, **AssertJ**, **Spring Messaging**, and **Spring Integration 6.x**. With Spring Boot, dependencies may include compatible versions of \`spring-boot-starter-integration\` and \`spring-boot-starter-test\`. The tests do not need a Spring context, message broker, or poller because the goal is testing **queue ordering**.

Create \`src/test/java/example/PriorityTieBreakerTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;
import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityTieBreakerTest {

    private static Message<String> work(
            String name, int priority, long sequence) {
        return MessageBuilder.withPayload(name)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence)
                .setHeader("requestId", "request-" + name)
                .build();
    }

    private static Comparator<Message<?>> priorityThenSequence() {
        return Comparator
                .<Message<?>>comparingInt(message ->
                        (Integer) message.getHeaders().get(
                                IntegrationMessageHeaderAccessor.PRIORITY))
                .reversed()
                .thenComparingLong(message ->
                        (Long) message.getHeaders().get("enqueueSequence"));
    }

    private static Message<?> next(PriorityChannel channel) {
        Message<?> message = channel.receive(1_000);
        assertThat(message).isNotNull();
        return message;
    }

    @Test
    void higher_priority_still_wins_over_earlier_sequence() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());

        // Send all messages before the first receive call.
        channel.send(work("normal", 5, 1L));
        channel.send(work("urgent", 9, 2L));
        channel.send(work("background", 1, 3L));

        assertThat(next(channel).getPayload()).isEqualTo("urgent");
        assertThat(next(channel).getPayload()).isEqualTo("normal");
        assertThat(next(channel).getPayload()).isEqualTo("background");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void equal_priority_is_sorted_by_sequence() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());

        // Send order is intentionally reversed relative to sequence to test the secondary key.
        channel.send(work("third", 9, 3L));
        channel.send(work("first", 9, 1L));
        channel.send(work("second", 9, 2L));

        assertThat(next(channel).getPayload()).isEqualTo("first");
        assertThat(next(channel).getPayload()).isEqualTo("second");
        assertThat(next(channel).getPayload()).isEqualTo("third");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void message_payload_and_business_headers_are_preserved() {
        PriorityChannel channel =
                new PriorityChannel(10, priorityThenSequence());
        channel.send(work("A", 9, 11L));

        Message<?> actual = next(channel);
        assertThat(actual.getPayload()).isEqualTo("A");
        assertThat(actual.getHeaders().get("requestId"))
                .isEqualTo("request-A");
        assertThat(actual.getHeaders().get(
                IntegrationMessageHeaderAccessor.PRIORITY))
                .isEqualTo(9);
        assertThat(actual.getHeaders().get("enqueueSequence"))
                .isEqualTo(11L);
    }

    @Test
    void comparator_has_expected_signs_for_both_keys() {
        Comparator<Message<?>> comparator = priorityThenSequence();

        Message<?> highEarly = work("high-early", 9, 10L);
        Message<?> highLate = work("high-late", 9, 11L);
        Message<?> lowEarly = work("low-early", 1, 1L);

        assertThat(comparator.compare(highEarly, lowEarly))
                .isLessThan(0); // Higher priority comes first.
        assertThat(comparator.compare(highEarly, highLate))
                .isLessThan(0); // Equal priority, smaller sequence comes first.
        assertThat(comparator.compare(highLate, highEarly))
                .isGreaterThan(0);
    }
}
~~~

### Two Important Points When Reading the Tests

**The \`equal_priority_is_sorted_by_sequence\` test** intentionally sends \`third\` before \`first\`. Thus it proves the comparator sorts by \`enqueueSequence\`, **not** FIFO by *actual send order* in that test. To implement true FIFO, you must assign the sequence at the exact point where enqueue order is established.

**The \`higher_priority_still_wins_over_earlier_sequence\` test** proves that sequence is a **secondary key**. Even though \`normal\` has a smaller sequence, \`urgent\` still goes first because priority is compared first.

Do not write a test expecting a specific order for messages with **both equal priority and equal sequence** unless a third distinguishing key exists. When both keys match, the comparator treats them as equivalent.

## 7. Where to Assign the Enqueue Sequence for True FIFO?

The example above passes sequence numbers manually for testing. In an application, you must know **who assigns the number** and **at what moment**.

Suppose two producers run concurrently:

~~~text
Producer A gets sequence=100, then pauses before send().
Producer B gets sequence=101 and completes send().
Producer A now completes send().

Actual queue arrival order:  B before A.
Order by sequence:           A before B.
~~~

In this situation, a sequence-based comparator produces a deterministic result, yet **does not match actual enqueue arrival order**. To accurately represent “arrived at the queue first”, sequence assignment and enqueuing must be **serialized together**, or you must adopt a different contract: “by sequence allocation order” rather than “by arrival order”.

### Simple Approach: A Single Serialized Enqueue Point

Within a single instance, a gateway/dispatcher component can own the queue and assign numbers sequentially. Below is a **simple Java model** for a single process; the \`enqueue\` method is synchronized to prevent two producers from acquiring sequences and sending out of order:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class SequencedEnqueue {
    private final PriorityChannel channel;
    private final AtomicLong nextSequence = new AtomicLong();

    SequencedEnqueue(PriorityChannel channel) {
        this.channel = channel;
    }

    // Single instance; all producers must go through this method.
    synchronized boolean enqueue(String payload, int priority) {
        long sequence = nextSequence.incrementAndGet();
        Message<String> message = MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence)
                .build();
        return channel.send(message, 0);
    }
}
~~~

With **the same \`SequencedEnqueue\` instance** and successfully accepted messages, sequences increase in the order \`send\` is called inside the \`synchronized\` block. However, when the queue is full, \`send(..., 0)\` may return \`false\`; skipped sequence numbers are normal as long as nothing assumes sequences are contiguous. If retrying failed enqueues, define whether to keep the old sequence or allocate a new one upon resend.

**Limitations of this example:**

- \`AtomicLong\` only guarantees monotonicity within one process. On restart, the counter resets, causing duplicate keys if the queue or message store still holds older messages.
- Each instance has its own counter; this does not establish a global order across multiple replicas.
- All producers must pass through the same enqueue point for the policy to hold.
- When handling many messages across multiple queues, “global ordering” can be both expensive and unnecessary; it is usually better to scope ordering per queue, aggregate, or tenant.

With brokers and partitioning, define whether ordering is promised per **partition**, **key**, or system-wide. Never promise global FIFO if the infrastructure only guarantees ordering within each partition.

## 8. Timestamps as Tie-Breakers: When They Work and When They Do Not

An intuitive option is using \`createdAt\` or \`enqueuedAt\` as the secondary key:

~~~java
Comparator<Message<?>> byPriorityThenTime = Comparator
        .<Message<?>>comparingInt(m ->
                (Integer) m.getHeaders()
                        .get(IntegrationMessageHeaderAccessor.PRIORITY))
        .reversed()
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueuedAtMillis"));
~~~

This sorts by recorded time **if timestamps are trustworthy**. However, there are several pitfalls:

1. Two messages can be recorded within the same millisecond, causing the comparator to still return 0.
2. Clocks across machines can drift or even step backward.
3. Producer \`createdAt\` does not necessarily reflect when the message entered PriorityChannel.
4. Timestamps can be copied across processing steps or retries even though enqueue order changed.

If fully deterministic ordering is needed, you can combine **priority → enqueue time → unique sequence**:

~~~java
Comparator<Message<?>> ordered = Comparator
        .<Message<?>>comparingInt(m ->
                (Integer) m.getHeaders()
                        .get(IntegrationMessageHeaderAccessor.PRIORITY))
        .reversed()
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueuedAtMillis"))
        .thenComparingLong(m ->
                (Long) m.getHeaders().get("enqueueSequence"));
~~~

Adding a sequence only resolves timestamp ties **if the sequence is genuinely unique and meaningful within the queue's scope**. Do not use a random UUID as a third key and call it FIFO.

## 9. Missing Headers, Wrong Types, and Duplicate Sequences

The comparator receives \`Message<?>\`, where values extracted from \`MessageHeaders\` are \`Object\`. Direct casting is convenient in sanitized examples; in production, validate before entering the queue.

A sample policy:

| Scenario | Recommended behavior in the example |
| --- | --- |
| Missing \`priority\` | Assign default at ingress or reject per contract |
| \`priority="9"\` as String | Convert in a controlled step or reject; never let the comparator mis-cast |
| Missing \`enqueueSequence\` | Assign at dispatcher before enqueuing |
| \`enqueueSequence\` as String | Normalize to Long or reject |
| Two messages with same sequence | Flag sequence allocation bug or apply an extra tie-break key |
| Negative or out-of-range sequence | Validate per contract; do not infer business intent |

A header validation function:

~~~java
static void validateOrderingHeaders(Message<?> message) {
    Object priority = message.getHeaders()
            .get(IntegrationMessageHeaderAccessor.PRIORITY);
    Object sequence = message.getHeaders().get("enqueueSequence");

    if (!(priority instanceof Integer)) {
        throw new IllegalArgumentException(
                "priority must be an Integer");
    }
    if (!(sequence instanceof Long)) {
        throw new IllegalArgumentException(
                "enqueueSequence must be a Long");
    }
}
~~~

This checks **types**. If priority must be in 1–9, or sequence must be positive, add those bounds to your application policy. Do not mistake those bounds for mandatory Spring Integration rules.

Note that Java comparators are not expected to safely tolerate header or key changes after a message enters the queue. \`MessageHeaders\` is unmodifiable directly, but payloads may contain mutable objects; never compare keys derived from mutable payload fields if those values might change while queued.

## 10. A Tie-Breaker Is Not an Anti-Starvation Solution

Adding a sequence ensures **messages of the same priority** are picked in a consistent order. It does **not** ensure a low-priority message is picked ahead of a continuous stream of high-priority messages.

~~~text
Already in queue:
  LOW-A:  priority=1, sequence=1

Each time consumer is about to poll:
  HIGH-1: priority=9, sequence=2
  HIGH-2: priority=9, sequence=3
  HIGH-3: priority=9, sequence=4
  ...

Priority remains the primary key.
LOW-A has a very small sequence yet still loses to every HIGH.
~~~

If you need to guarantee progress for low-priority classes, design **fairness** or a separate scheduling mechanism: tiered queues with quotas, reserved workers, deadline-aware scheduling, or properly re-evaluated aging. A priority-plus-sequence comparator only solves **fairness within the same level**, not cross-level fairness.

### Why Isn't Aging Simply \`System.currentTimeMillis()\` Inside the Comparator?

A priority queue maintains order during insertions and removals. If the comparison key changes on its own over time, the queue **does not automatically reorganize everything** just because the clock ticks. A comparator reading current time on every comparison can also break consistency invariants. Real aging requires a scheduler that recomputes effective priority and re-sorts, or routes messages through appropriate queues/dispatch groups.

## 11. Placement Within Router, Splitter, Aggregator, and Gateway

Priority and tie-breakers are usually just **one segment** of a flow:

~~~mermaid
flowchart LR
    IN["Gateway / Input"] --> R{"Router"}
    R --> V["Header Enricher\npriority + sequence"]
    V --> Q["PriorityChannel"]
    Q --> P["Poller"]
    P --> H["Service Activator / Transformer"]
    H --> OUT["Output"]
    H -.-> E["Error handling"]
~~~

When testing a flow like the above, separate two questions:

- **Ordering test:** Once all messages are in the queue, does \`receive()\` honor both priority and the tie-breaker?
- **Integration test:** Do Router, Header Enricher, Poller, and handlers preserve payloads, headers, and error paths?

### Router and Filter

Router may send several message types to the same PriorityChannel. Branches must agree on how priority and sequence are assigned. Filter may drop messages before the queue; dropped messages do not participate as waiting elements.

### Splitter and Aggregator

Splitter produces multiple fragments for one request. When fragments share the same priority, an **enqueue-order** sequence tie-breaker can determine dequeue order, yet it does not replace the **aggregation group** \`sequenceNumber\`.

Distinguish:

| Header | Purpose |
| --- | --- |
| \`enqueueSequence\` | Key for PriorityChannel ordering per application contract |
| \`correlationId\` | Group key for Splitter/Aggregator |
| \`sequenceNumber\` | Fragment position within the group |
| \`sequenceSize\` | Expected group size |

Do not use Splitter's \`sequenceNumber\` as a **global** tie-break key when multiple groups interleave: many groups each have fragment 1, fragment 2. If per-group ordering is needed, define the scope and test correlation alongside ordering separately.

### Gateway and Replies

A synchronous Gateway may wait for a reply while its message sits in PriorityChannel. A tie-breaker does not guarantee the order callers receive replies if handlers take varying durations. Configure bounded timeouts and test behavior when a request is not served in time.

### Retry and Error Channel

When a handler fails and a message is retried, it may be re-executed without re-entering the queue; alternatively, a recovery flow may re-enqueue it as a new message. When re-enqueuing, decide whether to keep the old \`enqueueSequence\` or issue a new one. The two options mean different things:

- **Keep sequence:** Honors original submission order; allows retried requests to overtake newer equal-priority messages.
- **Issue new sequence:** Places the retried message at the back of its equal-priority tier according to the new enqueue order.

Also verify \`requestId\`, correlation, and idempotency keys; a tie-breaker does not prevent duplicate side effects on retry.

## 12. Testing Multiple Producers and Edge Cases

For an in-memory queue, single-threaded tests can verify the comparator. When a system has multiple producers, multiple processes, or a message broker, expand test coverage.

| Scenario | What must be proven |
| --- | --- |
| Two messages, same priority, different sequence | Smaller sequence dequeued first |
| Different priorities, reversed sequence | Higher priority still dequeued first |
| Many messages with same priority | Committed sequence order is preserved |
| Two messages with same priority and same sequence | Warning/rejection or explicit secondary key applies |
| Wrongly typed or missing headers | Validation handles before queue |
| Producer allocates sequence then sends slowly | Test distinguishes allocation order from actual queue arrival order |
| Full queue | Do not assume a more important message evicts an older one |
| Two consumers processing concurrently | Poll order can be correct while completion order differs |
| Retry re-enqueues message | Sequence and idempotency adhere to policy |
| Multiple replicas with independent state | Do not claim global order without coordinated sequence allocation |

### Avoiding Flaky Tests

- Enqueue the **entire backlog** before the first \`receive\` when testing the comparator.
- Use a fresh \`PriorityChannel\` per test; drain all messages.
- Do not enable a concurrent poller when the goal is asserting exact dequeue order.
- Assert business headers and payloads rather than auto-generated UUIDs or timestamps.
- For asynchronous flows, use bounded timeouts and proper completion conditions; never use fixed \`Thread.sleep\` as proof of ordering.
- If testing true enqueue arrival order, explicitly define which boundary counts as **enqueue time**.

## 13. Practice Exercises

### Exercise A — Adding a Tie-Breaker Criterion

Create a \`PriorityChannel\` whose comparator compares only \`priority\`. Send three messages all with level 9. Explain why the observed output of a single run does not prove FIFO. Then add \`enqueueSequence\` and write a test with sequences 3, 1, 2; assert the dequeue order is 1, 2, 3.

### Exercise B — Combining Priority and Deadline

Build a comparator with two keys: descending priority, ascending deadline. Send two equal-priority messages with different deadlines and one lower-priority message with an earlier deadline. Verify priority remains the primary key while deadline only breaks ties on equal priority. Discuss how key order would have to change if the business wanted deadlines prioritized ahead of priority levels.

### Exercise C — Catching Data Errors

Create a message with \`priority="9"\` as a String, a message missing \`enqueueSequence\`, and two messages with duplicate sequences. Write validation or enrichment rules so these inputs cannot make queue ordering ambiguous.

### Exercise D — Concurrent Producers

Simulate producer A acquiring a sequence earlier yet sending after producer B. Compare two contracts: **sequence allocation order** versus **actual enqueue order**. Choose one contract, design the appropriate synchronization point, and write a test proving it.

### Exercise E — Retries Within the Same Priority

Simulate a failed priority-9 message being re-enqueued while two other priority-9 messages are waiting. Test both policies: keeping the original sequence versus issuing a new sequence. Document expected dequeue order and implications for fairness and idempotency.

## 14. Checklist and Conclusion

Before introducing a custom comparator into a Spring Integration flow, confirm:

1. Which priority is higher: larger number or smaller number, and is the comparator direction right?
2. When priorities tie, what is the tie-breaker: enqueue sequence, deadline, or business key?
3. Is the tie-breaker **unique, stable, and properly scoped**?
4. If using a sequence, when is it assigned and is it serialized at the same boundary as enqueue?
5. Can timestamps collide or suffer from clock skew?
6. Is there validation for missing/wrongly typed headers or duplicate keys?
7. Do tests distinguish dequeue order from completion order?
8. Do retries, multiple producers, and multiple replicas alter ordering semantics?
9. If the goal is preventing starvation across priority tiers, is there a separate fairness policy?
10. Are \`requestId\`, correlation, and metadata logged so you can explain why one message was picked before another?

**Conclusion:** A tie-breaker turns the “two equal-priority messages” situation from an unspecified order into an **explicit, testable rule**. In Spring Integration, priority should be expressed as a comparator with stable primary and secondary keys, and key generation must match the scope the system intends to guarantee. By clearly separating enqueue order, dequeue order, and completion order, you can scale flows with Router, Splitter/Aggregator, Gateway, retry, and error channels without accidentally depending on arbitrary queue order.
