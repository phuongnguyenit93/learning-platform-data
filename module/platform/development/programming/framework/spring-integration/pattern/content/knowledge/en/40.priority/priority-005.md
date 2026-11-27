# Queue Capacity of a Priority Channel in Spring Integration

## 1. Why Does a Priority Queue Still Need a Capacity Limit?

**Priority Channel** is an Enterprise Integration Pattern that allows waiting messages to be dequeued by priority rather than always strictly FIFO. In Spring Integration, \`PriorityChannel\` is a \`PollableChannel\`: producers send messages into the queue and consumers or pollers dequeue them for processing.

Suppose a system receives order-processing requests:

- \`NORMAL\` messages are tagged with \`priority=1\`.
- \`URGENT\` messages are tagged with \`priority=9\`.
- The handler can only process a fixed number of messages per second.

When producers send faster than consumers can process, a backlog grows. Even though Priority Channel knows which message to pick first, it still needs a **queue capacity** policy to protect resources and produce a **backpressure** signal when overloaded.

This lesson **“Queue Capacity of a Priority Channel”** belongs to the **Priority** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, testing, and monitoring of processing branches. Capacity sits at the intersection of **routing**, **prioritization**, and **overload protection**.

After this lesson, you will be able to:

1. Distinguish the limit on queued waiting messages from the priority dequeue order.
2. Configure a bounded-capacity \`PriorityChannel\` using Java or XML.
3. Understand \`send(message)\`, \`send(message, 0)\`, and \`send(message, timeout)\` behavior.
4. Verify that high-priority messages **do not automatically evict** low-priority messages when the queue is full.
5. Write JUnit tests for full-queue state, slot release, and polling outcomes.
6. Choose appropriate overload policies, queue sizing, metrics, and recovery mechanisms.

## 2. Capacity and Priority Are Two Different Concerns

**Capacity** answers: *At most how many unconsumed messages can wait in the queue?*

**Priority** answers: *Among messages already accepted and still waiting, which one is dequeued next?*

~~~mermaid
flowchart LR
    P["Producer"] -->|"send"| A{"Capacity available?"}
    A -->|"Yes"| Q["PriorityChannel\nbounded queue"]
    A -->|"No"| B["Wait for slot / timeout / reject"]
    Q -->|"Higher priority dequeued first"| C["Consumer / Poller"]
    C --> O["Handler"]
~~~

Walk through an example with \`capacity=2\`:

| Step | Action | Queue after action | Result |
| --- | --- | --- | --- |
| 1 | Send \`LOW\`, priority 1 | \`[LOW]\` | Accepted |
| 2 | Send \`MEDIUM\`, priority 5 | \`[LOW, MEDIUM]\` | Accepted, queue full |
| 3 | Send \`URGENT\`, priority 9 with timeout 0 | Unchanged | No space left, so send fails |
| 4 | Consumer dequeues one message | \`LOW\` remains | \`MEDIUM\` is picked first because priority 5 > 1 |
| 5 | Producer resends \`URGENT\` | \`[LOW, URGENT]\` | Accepted because a slot is free |
| 6 | Consumer dequeues next | \`LOW\` remains | \`URGENT\` is picked first |

**Key conclusion:** \`priority=9\` is not a “right to cut into a full queue”. Capacity is enforced at **send time**, before the message enters the waiting set; the comparator governs ordering within the already accepted set.

### What Capacity Does Not Guarantee

A finite capacity **does not automatically**:

- Detect urgent messages and evict normal messages from the queue.
- Reserve a slice of slots exclusively for high priority.
- Prevent starvation of low-priority messages.
- Bound the number of tasks **actively being processed by handlers**, because dequeued messages no longer occupy queue slots.
- Persist messages across process crashes if the queue lives only in memory.
- Guarantee exactly-once processing, successful execution, or Gateway replies.

Those guarantees require separate mechanisms outside \`PriorityChannel\`.

## 3. Configuring PriorityChannel Capacity

Spring Integration supports common constructors:

| Java API | Meaning |
| --- | --- |
| \`new PriorityChannel()\` | Unbounded queue with no application-specified capacity limit |
| \`new PriorityChannel(100)\` | Queue holding at most 100 messages |
| \`new PriorityChannel(comparator)\` | Unbounded queue with a custom comparator |
| \`new PriorityChannel(100, comparator)\` | Queue bounded to 100 messages and ordered by comparator |

In the Spring Integration 6.x API, for the \`(int capacity, Comparator<Message<?>>)\` constructor, a **non-positive capacity** produces an **unbounded** queue. Therefore, do not set \`capacity=0\` thinking it will block all messages. For an explicitly bounded queue, always use a **positive** integer.

### Java Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.PriorityChannel;

@Configuration
class ChannelConfiguration {

    @Bean("orders.priority")
    PriorityChannel priorityOrders() {
        // At most 100 waiting messages; default ordering by priority.
        return new PriorityChannel(100);
    }
}
~~~

### XML Configuration

~~~xml
<int:channel id="ordersPriority">
    <int:priority-queue capacity="100"/>
</int:channel>
~~~

With a custom comparator, capacity can still be specified separately:

~~~java
import java.util.Comparator;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

Comparator<Message<?>> ordering = Comparator
        .<Message<?>>comparingInt(message ->
                (Integer) message.getHeaders().get("businessUrgency"))
        .reversed();

PriorityChannel channel = new PriorityChannel(100, ordering);
~~~

The comparator determines **which message is dequeued first**; it does not alter how many slots the queue has. If the comparator only reads \`businessUrgency\`, ensure that header is present and properly typed before sending into the queue.

### Is an Unbounded Queue Actually Safe?

Omitting capacity does not mean infinite memory. An in-memory queue can grow until memory runs out or trigger severe garbage-collection pressure, degrading the whole application. With large payloads or high arrival rates, choose capacity deliberately and define an explicit overload policy.

A **message count** limit is also not equivalent to a **byte** limit: a queue of 100 tiny payloads is vastly different from 100 multi-megabyte payloads.

## 4. Send and Receive Behavior When the Queue Is Full

\`PriorityChannel\` implements message send/receive interfaces. Behavior depends on the **timeout** supplied:

| Call | When queue has space | When queue is full |
| --- | --- | --- |
| \`send(message, 0)\` | Returns \`true\` after enqueuing | Returns \`false\` immediately without waiting for a slot |
| \`send(message, 500)\` | Returns \`true\` if accepted within timeout | Waits up to ~500 ms; returns \`false\` on expiration |
| \`send(message)\` | Enqueues normally | Follows channel's default send timeout semantics; may wait indefinitely for a slot |
| \`receive(0)\` | Returns top message by priority | Returns \`null\` if queue is empty |
| \`receive(500)\` | Returns message if available within timeout | Returns \`null\` if timeout expires with no message |

The timeout unit in these examples is **milliseconds**. Timeout-less calls must be examined carefully on latency-sensitive endpoints: a producer can stay blocked indefinitely simply because consumers stop polling.

Example:

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel queue = new PriorityChannel(2);

Message<String> first = MessageBuilder.withPayload("A").build();
Message<String> second = MessageBuilder.withPayload("B").build();
Message<String> third = MessageBuilder.withPayload("C").build();

queue.send(first, 0);          // true
queue.send(second, 0);         // true
boolean accepted = queue.send(third, 0);
// accepted == false: no third slot available.
~~~

**Always check the return value** when calling \`send\` with a timeout. Returning \`false\` means the channel **did not accept this send**; it does not mean the message was stored for automatic later retry.

Some endpoints, Gateways, channel adapters, and \`MessagingTemplate\` interpret send failures differently or throw exceptions when sending fails. Verify the actual behavior of the **invocation path** you use; never assume every layer returns a Boolean to business code.

## 5. Basic Tests: Capacity Is Independent of Priority

The examples below use **Java 17, Spring Integration 6.x, JUnit 5, and AssertJ**. The tests interact only with an in-memory queue without starting a Spring context, broker, or poller, keeping results deterministic.

Create \`src/test/java/example/PriorityCapacityTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Comparator;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityCapacityTest {

    private static Message<String> work(String name, int priority) {
        return MessageBuilder.withPayload(name)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", "req-" + name)
                .build();
    }

    private static Message<?> next(PriorityChannel queue) {
        Message<?> result = queue.receive(1_000);
        assertThat(result).isNotNull();
        return result;
    }

    @Test
    void high_priority_cannot_displace_messages_when_queue_is_full() {
        PriorityChannel queue = new PriorityChannel(2);

        assertThat(queue.send(work("low", 1), 0)).isTrue();
        assertThat(queue.send(work("medium", 5), 0)).isTrue();
        assertThat(queue.getRemainingCapacity()).isZero();

        // URGENT outranks both, but the queue is already full.
        assertThat(queue.send(work("urgent", 9), 0)).isFalse();

        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }

    @Test
    void released_slot_allows_high_priority_to_enter_and_be_polled_first() {
        PriorityChannel queue = new PriorityChannel(2);

        queue.send(work("low", 1), 0);
        queue.send(work("medium", 5), 0);

        // Dequeue MEDIUM to free one slot while LOW is still waiting.
        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(queue.getRemainingCapacity()).isEqualTo(1);

        assertThat(queue.send(work("urgent", 9), 0)).isTrue();
        assertThat(queue.getRemainingCapacity()).isZero();

        assertThat(next(queue).getPayload()).isEqualTo("urgent");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }

    @Test
    void capacity_is_still_enforced_with_a_custom_comparator() {
        Comparator<Message<?>> byPriority = Comparator
                .<Message<?>>comparingInt(m ->
                        (Integer) m.getHeaders().get(
                                IntegrationMessageHeaderAccessor.PRIORITY))
                .reversed();
        PriorityChannel queue = new PriorityChannel(1, byPriority);

        assertThat(queue.send(work("normal", 1), 0)).isTrue();
        assertThat(queue.send(work("urgent", 9), 0)).isFalse();
        assertThat(next(queue).getPayload()).isEqualTo("normal");
    }

    @Test
    void timed_send_succeeds_after_consumer_frees_one_slot()
            throws Exception {
        PriorityChannel queue = new PriorityChannel(1);
        assertThat(queue.send(work("already-queued", 1), 0)).isTrue();

        ExecutorService sender = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        try {
            Future<Boolean> pending = sender.submit(() -> {
                started.countDown();
                return queue.send(work("waiting", 9), 3_000);
            });
            assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();

            // First message occupies the slot; dequeue it to free space.
            assertThat(next(queue).getPayload())
                    .isEqualTo("already-queued");
            assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();
            assertThat(next(queue).getPayload()).isEqualTo("waiting");
            assertThat(queue.receive(0)).isNull();
        } finally {
            sender.shutdownNow();
        }
    }

    @Test
    void priority_order_applies_only_to_accepted_backlog() {
        PriorityChannel queue = new PriorityChannel(3);

        queue.send(work("low", 1), 0);
        queue.send(work("high", 9), 0);
        queue.send(work("medium", 5), 0);

        Message<?> first = next(queue);
        assertThat(first.getPayload()).isEqualTo("high");
        assertThat(first.getHeaders().get("requestId"))
                .isEqualTo("req-high");
        assertThat(next(queue).getPayload()).isEqualTo("medium");
        assertThat(next(queue).getPayload()).isEqualTo("low");
        assertThat(queue.receive(0)).isNull();
    }
}
~~~

### Interpreting Each Test Result

1. **Full queue:** Sends two low/medium priority messages into a capacity-2 queue, then proves \`URGENT\` is rejected despite having the highest priority.
2. **Slot release:** After dequeuing \`MEDIUM\`, the queue has one free slot; \`URGENT\` succeeds on send and is then polled ahead of \`LOW\`.
3. **Custom comparator:** The comparator only affects ordering; capacity 1 still rejects the second send when no slot is free.
4. **Timed send:** A producer thread sending into a capacity-1 queue completes once a consumer dequeues the existing message and frees a slot.
5. **Backlog ordering:** When all three messages are accepted before the first poll, the dequeue order is \`HIGH\`, \`MEDIUM\`, \`LOW\`.

The timed-send test uses **finite timeouts** and shuts down the executor in \`finally\`, avoiding leaked blocked threads after the test finishes. This tests slot release, not throughput under realistic load.

## 6. Distinguishing Send Timeout from Business Processing Time

A producer may experience several distinct durations:

~~~mermaid
flowchart LR
    P["Producer sends"] --> A["Wait for slot if queue full"]
    A --> Q["Message enqueued"]
    Q --> B["Wait for poll by priority"]
    B --> H["Handler processes"]
    H --> O["Output / Reply"]
~~~

Three durations to distinguish:

- **Admission wait:** Time the producer waits for a free queue slot to accept the message.
- **Queue wait:** Time the message remains enqueued waiting to be dequeued.
- **Processing time:** Time the handler executes after receiving the message.

\`send(message, 500)\` only bounds the **channel send operation**, not an SLA of “completed within 500 ms”. A successfully sent message can still wait a long time in the queue if higher-priority messages keep arriving.

Conversely, while a producer is waiting for a slot, the message is not yet in the queue and has not entered priority ordering. **Do not send a business ACK claiming work was accepted** before obtaining a confirmed send result or durable persistence.

## 7. When the Queue Is Full: Choosing a Backpressure Policy

A solid system must answer upfront: **Who is responsible when the queue has no remaining capacity?** Several options exist, each suited to different scenarios.

| Policy | Behavior | Best suited when | Risk |
| --- | --- | --- | --- |
| **Bounded wait** | \`send(message, timeout)\` | Producers tolerate brief delays | Increases latency, may still time out |
| **Fail fast** | \`send(message, 0)\` then return error/overload | APIs needing fast feedback | Callers must handle retries |
| **Retry + backoff** | Wait and resend with limits | Temporary inability to enter queue | Retry storm without jitter/rate limits |
| **Admission control** | Throttle producers ahead of queue | Traffic spikes, ingress control | Requires quota design |
| **Separate queues per priority class** | Split urgent/normal with dedicated capacities | Space must be guaranteed for urgent | More complex; each queue can still fill |
| **Durable storage** | Use an appropriate broker/store to retain work | Requests must survive app restarts | Requires acknowledgment, dedup, and store limits |
| **Load shedding** | Intentionally drop less critical messages by policy | Telemetry tolerant of sampling/drops | Unsuitable for mandatory business records |

There is no universally “best” policy independent of business requirements. A payment system generally cannot silently drop transactions; a high-frequency metrics stream may accept sampling during overload.

### Example: Handling a Rejected Send

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

static boolean tryEnqueue(
        PriorityChannel queue, Message<?> message) {
    boolean accepted = queue.send(message, 100);
    if (!accepted) {
        // Signal overload or route to a managed recovery mechanism;
        // do not record as processed successfully.
        return false;
    }
    return true;
}
~~~

In an HTTP application, you can translate overload into an appropriate response (such as HTTP 429 or 503, depending on contract) with retry guidance when safe. In an asynchronous messaging flow, you may need **negative acknowledgment**, bounded retries, or dead-lettering per adapter. **Do not treat routing to a dead-letter channel as a guaranteed success if the dead-letter channel itself can fill up.**

### Splitting High-Priority Flows When Capacity Is Contested

With a shared queue of capacity 100, 100 earlier \`NORMAL\` messages can fill all slots, causing newly arriving \`URGENT\` messages to be rejected. If that risk is unacceptable, use a Router to split streams:

~~~mermaid
flowchart LR
    IN["Input"] --> R{"Router by class"}
    R -->|"URGENT"| HQ["Urgent Queue\ncapacity 20"]
    R -->|"NORMAL"| NQ["Normal Queue\ncapacity 80"]
    HQ --> HC["Urgent Worker / Scheduler"]
    NQ --> NC["Normal Worker / Scheduler"]
    HC --> OUT["Result"]
    NC --> OUT
~~~

The numbers 20 and 80 are purely **examples of resource quotas**, not Spring Integration rules. Splitting queues provides dedicated slots, yet also requires:

- Sufficient consumers or scheduling policy so the urgent flow is actually polled.
- A clear policy for when the **urgent queue also fills up**.
- Never assuming global ordering across the two queues.
- Monitoring normal starvation when urgent traffic consistently maintains a backlog.

## 8. How Big Should the Queue Be?

No single fixed capacity suits every service. Start from arrival rate, service rate, burst duration, and available memory.

Suppose:

- Producers can send **70 messages/second** during a traffic spike.
- Consumers process **50 messages/second** during that spike.
- The spike lasts **12 seconds**.
- The queue starts empty and messages have roughly uniform size.

In an approximate model:

\[
\Delta Q \approx \max(0, \lambda_{\mathrm{in}}-\mu_{\mathrm{out}})\times T
\]

Substituting values:

\[
\Delta Q \approx (70-50)\times12 = 240\ \text{messages}
\]

A queue with capacity **below 240** risks filling up during the assumed burst unless producer rate is throttled or processing capacity increases. A larger capacity (such as 300) adds headroom in this **illustrative model**, yet you still must check payload sizes, peak concurrency, retries, and backlog recovery time.

### Memory Footprint Is Another Limit

Suppose each message averages \`S\` bytes including payload, headers, and object overhead. Memory usage can be estimated as:

\[
M_{\mathrm{queue}} \approx N_{\mathrm{queued}}\times S
\]

This estimate typically **understates** real Java object overhead, metadata, references, off-queue buffering, and payload variance. Measure with heap profiling under realistic load. A capacity of 300 messages is tiny if each payload is a few KB, yet huge if each payload holds a multi-MB object graph.

### Capacity Trade-Offs

| Capacity | Advantage | Limitation |
| --- | --- | --- |
| Too small | Early backpressure, bounded memory | Rejects short bursts that could otherwise be absorbed |
| Well-sized | Absorbs bounded bursts, protects consumers | Requires tuning against real traffic |
| Too large | Fewer short-term producer rejections | Masks overload, increases queue wait, uses excessive RAM |
| Unbounded | No configured admission ceiling | Risk of OOM/GC pauses and uncontrolled queue latency |

**Capacity is a pressure-regulation mechanism, not a cure for chronic under-capacity.** If input rate consistently exceeds service rate, every finite queue will eventually fill.

## 9. PriorityChannel in an IntegrationFlow with a Poller

PriorityChannel is a \`PollableChannel\`, so consumers in Java DSL are typically attached with a poller:

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
class PriorityCapacityFlowConfig {

    @Bean("work.priority")
    PriorityChannel priorityQueue() {
        return new PriorityChannel(100);
    }

    @Bean("work.done")
    QueueChannel doneQueue() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow workerFlow() {
        return IntegrationFlow.from("work.priority", source ->
                    source.poller(Pollers.fixedDelay(250)
                            .maxMessagesPerPoll(1)))
                .handle(String.class,
                        (payload, headers) -> "processed:" + payload)
                .channel("work.done")
                .get();
    }
}
~~~

The example uses a fixed poller to illustrate the consumer, not as a universal default recommendation. With a poller taking only one message per cycle, backlog can grow rapidly under high arrival rates. Tune \`fixedDelay\`, \`maxMessagesPerPoll\`, concurrency, and handler duration to real workloads.

**Ordering test trap:** When a poller runs concurrently with producers, a \`LOW\` message may be picked before \`URGENT\` is even sent. This is not a comparator bug. To verify priority ordering reliably, **enqueue the full backlog before a consumer runs** or control the poller directly, as in the Section 5 unit tests.

## 10. Capacity, Threads, and Transactions

### A Bounded Queue Does Not Limit Concurrent Handlers

Once a consumer dequeues a message, its queue slot is freed. The message may still be in-flight during processing:

~~~text
Queue capacity: 100
Messages currently in queue: 80
Messages dequeued, actively handled: 20

=> Do not conclude the system has at most 100 tasks in flight.
~~~

To bound **in-flight processing**, add worker/concurrency limits or an appropriate semaphore. Queue capacity and max workers are complementary limits.

### Blocked Producers Can Cause Cascading Contention

If a producer holds an expensive resource while \`send(message)\` waits for a slot (such as a lock, database transaction, or HTTP request thread), waiting too long can propagate stalls to other components.

When placing a PriorityChannel between synchronous endpoints, especially behind a Gateway, check:

1. Does the send path have an explicit timeout?
2. Does the producer block request-serving threads when the queue is full?
3. On timeout, can the caller detect it and retry safely?
4. If a message is accepted and the handler fails later, which path handles the exception?
5. Can a transaction remain open too long while waiting for queue space?

Never equate a successful \`send()\` with **business transaction completion**. It only indicates the channel accepted the message under its configured semantics.

## 11. Capacity with Retry, Error Channel, and Correlation

### Retries Can Worsen Overload

When the queue is full, multiple producers retrying immediately in parallel can trigger a **retry storm**. Use bounded retries, exponential backoff, and jitter rather than tight infinite loops:

~~~text
Queue full
   |
   +-- Signal overload
   |
   +-- Bounded retry + backoff
   |
   +-- If exhausted: recovery / dead-letter / return error
~~~

Distinguish retrying **enqueueing into the queue** from retrying **processing after a consumer dequeues the message**. The two operate at different boundaries and can cause duplicates or backlog growth in different ways.

### Error Channel Does Not Add Capacity

An error channel helps observe or handle failures, but it does not expand the primary queue. If a recovery flow forwards messages to another queue, that queue also needs appropriate bounds, durability, and overload handling.

For systems that must not lose messages, define the **durable persistence acknowledgment point**, retry rules, and idempotency. An in-memory queue does not preserve messages across abrupt process termination.

### Splitter, Aggregator, and Correlation

A large message may be split by a Splitter into many fragments. If the queue sits **after the Splitter**, a single inbound request can consume many slots. For instance, one request producing 50 fragments can nearly exhaust a capacity-60 queue even though the producer sent only one request.

When the queue fills partway through:

- Some fragments may be enqueued while subsequent fragments fail to send.
- An Aggregator receiving an incomplete set of fragments may never release the group under \`sequenceSize\`.
- \`correlationId\`, \`requestId\`, and sequence headers must be preserved to detect incomplete groups.
- Retrying fragments without idempotency can produce duplicate messages.

Therefore, size capacity in terms of **messages at the queue's location**, not just inbound requests at the system edge.

### Router and Priority

A Router can separate urgent and normal flows before enqueuing. In a shared PriorityChannel, normal messages can fill slots before urgent ones arrive. If dedicated capacity for urgent traffic is required, use two queues as in Section 7; raising the priority header alone will not resolve full-queue admission rejection.

## 12. Monitoring Queue Capacity in Operations

Do not alert only when the queue is already full. Track backlog growth rate, wait time, and send-failure rate.

| Suggested metric | Meaning | Question answered |
| --- | --- | --- |
| \`queue_depth\` | Number of waiting messages | How large is the backlog? |
| \`remaining_capacity\` | Remaining free slots when bounded | Are we about to run out of space? |
| \`queue_utilization\` | \`queue_depth / capacity\` | Is the queue persistently near capacity or only spiking briefly? |
| \`send_failure_count\` | Rejected send attempts | How many requests hit backpressure? |
| \`send_wait_duration\` | Time spent waiting for a slot | Are producers being blocked? |
| \`queue_wait_duration\` | Time from enqueue to receive | Are messages waiting due to backlog/priority? |
| \`oldest_message_age\` | Age of the oldest waiting message | Are low-priority groups starving? |
| \`consumer_rate\` | Dequeue/processing rate | Is consumption keeping up with arrivals? |
| \`retry_count\`, \`error_count\` | Failures and retries | Are retries amplifying overload? |

\`PriorityChannel\` exposes APIs such as \`getRemainingCapacity()\` to observe remaining space. Exact metrics and Micrometer/management integration depend on the Spring Integration version, so verify actual configuration before naming dashboard metrics.

### Do Not Mask Starvation with Aggregate Metrics

A queue with depth 10 can still hold a low-priority message that has waited for hours if high-priority messages are continuously added and drained. Tag wait-time metrics by priority or business class; avoid high-cardinality metric tags like per-\`requestId\`.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using \`PriorityChannel()\` thinking it is bounded | Uncontrolled queue growth | Specify a positive capacity |
| Setting \`capacity=0\` thinking it means “accept nothing” | Can create an unbounded queue | Understand constructor semantics |
| Assuming high priority always gets enqueued | Urgent messages get rejected when queue is full | Separate admission from ordering |
| Ignoring \`false\` returned by \`send(message, 0)\` | Silent work loss | Handle overload/recovery explicitly |
| Calling \`send(message)\` on latency-sensitive HTTP threads | Request threads block indefinitely | Use finite timeouts |
| Only increasing capacity when consumers are slow | Hides overload and inflates wait time | Measure rates, optimize handlers, scale consumers |
| Testing ordering while a poller is already running | Flaky tests because early messages are polled | Enqueue backlog before polling |
| Ignoring payload size | Underestimating RAM requirements | Heap-profile under realistic load |
| Treating in-memory queues as durable queues | Wrong expectations across restarts | Use an appropriate message store/broker |
| Skipping retry tests under full-queue conditions | Retry storms, duplicate messages | Add backoff, bounds, and idempotency |
| Overlooking a queue placed after a Splitter | One request creates too many fragments | Size capacity for post-split messages |
| Confusing queue capacity with in-flight handler limit | Too many handlers run concurrently | Bound concurrency separately |

## 14. Practice Exercises

### Exercise A — Can an Urgent Message Cut Into a Full Queue?

Create \`PriorityChannel(2)\`. Send \`LOW\` and \`MEDIUM\`, then send \`URGENT\` with \`timeout=0\`. Verify the third send is rejected and the two existing messages are dequeued in priority order. Explain why this is **capacity** behavior rather than a comparator bug.

### Exercise B — Slot Release and Polling Order

Continuing Exercise A: dequeue \`MEDIUM\`, then resend \`URGENT\`. Verify \`URGENT\` enters the queue and is dequeued ahead of \`LOW\`. Check \`getRemainingCapacity()\` at each step.

### Exercise C — Bounded Producer Wait

Create a capacity-1 queue and enqueue one message. From another thread, send a second message with a finite timeout; have a consumer thread dequeue the first message to free the slot. Use \`Future\`, \`CountDownLatch\`, and bounded timeouts so the test never hangs. Verify the second send succeeds and payload/headers remain intact.

### Exercise D — Bursts and Sizing

Assume a burst arrival rate of 70 messages/second, service rate of 50 messages/second, and burst duration of 12 seconds. Compute the resulting backlog and propose a capacity with headroom. Then multiply payload size several times over; explain why the RAM conclusion changes even though message count stays constant.

### Exercise E — Splitter Before the Queue

Split one request into 20 fragments; place a capacity-10 PriorityChannel after the Splitter. Design handling when some fragments are accepted before the queue fills, and ensure Aggregator does not unexpectedly release an incomplete group. Describe the needed recovery or group-level admission mechanism.

### Exercise F — Splitting Capacity by Priority Tier

Replace a shared capacity-100 queue with two queues: urgent capacity 20, normal capacity 80. Use a Router to route traffic and test when normal is full while urgent still has slots. Separately test overload when urgent also fills up. Discuss conditions needed so both queues are served fairly.

## 15. Pre-Deployment Checklist

1. Does the queue have a **positive, finite** capacity when RAM and backlog must be bounded?
2. Are **queue admission** and **priority polling** clearly separated in design?
3. Do producers use reasonable send timeouts instead of blocking indefinitely on latency-sensitive paths?
4. When \`send\` fails, does the system return explicit overload/recovery handling without silent message loss?
5. Is there a test verifying high-priority messages are rejected when the queue is full?
6. Is there a test verifying slot release allows new messages to be accepted?
7. Have burst rate, service rate, payload size, and RAM budget been estimated?
8. Are retries, backoff, and idempotency controlled during overload?
9. Are queues after Splitters, Routers, or other branches sized for **actual message counts**?
10. Are capacities of the main channel, recovery channel, and broker/store reviewed together?
11. Do metrics observe queue depth, send failures, queue wait, and starvation per priority?
12. Is queue capacity clearly distinguished from maximum concurrent in-flight handlers?

**Conclusion:** \`PriorityChannel\` decides **which waiting message in the backlog is dequeued next**, while **queue capacity** decides **whether another message can be accepted at all**. Never assume urgent messages can force their way into a full queue. With bounded capacity, send timeouts, backpressure policies, send/receive tests, and proper metrics, you can implement Priority Channel in Spring Integration to protect system resources while honoring your business priority contract.

### References

- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): configuring \`PriorityChannel\` and \`capacity\`.
- [Spring Integration API — PriorityChannel (6.4.2)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/channel/PriorityChannel.html): constructors, \`doSend\`, \`doReceive\`, and \`getRemainingCapacity\`.
