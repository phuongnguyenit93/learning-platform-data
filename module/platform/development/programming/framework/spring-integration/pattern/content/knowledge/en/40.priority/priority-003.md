# High Priority Starving Other Messages: Starvation in Spring Integration

## 1. The Problem: Low-Priority Messages Can Wait Very Long

In a message integration system, putting urgent requests first makes sense: a production incident needs to be handled faster than a report-aggregation job. However, if high-priority messages arrive continuously, a low-priority message may **never be dequeued**, even though it has been waiting for a long time. This phenomenon is called **starvation**.

This lesson belongs to the **Priority** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and monitoring processing branches. When adding a **Priority Channel** to such a flow, we must care not only about *whether urgent messages go first* but also *whether normal messages are processed within an acceptable time*.

Example of a Spring Integration \`PriorityChannel\` queue using the \`priority\` header to prioritize messages with larger values:

~~~text
Time         Enqueued message                   Next dequeued message
---------    ---------------------------------- ----------------------
t0           L: priority=1                      (not polled yet)
t1           H1: priority=9                     H1
t2           H2: priority=9                     H2
t3           H3: priority=9                     H3
t4           H4: priority=9                     H4
...          ...                                ...

Message L remains in the queue, even though it arrived before all of H1, H2, ...
~~~

**Main point:** \`PriorityChannel\` determines the **dequeue order of waiting messages**. It does not guarantee fairness, does not automatically raise the priority of long-waiting messages, and does not preempt work that a consumer has already picked up.

After this lesson, you will be able to:

1. Explain why strict priority can cause starvation.
2. Distinguish queue wait time from handler processing time and completion order.
3. Write a test reproducing repeated overtaking of a low-priority message using \`PriorityChannel\`.
4. Choose an appropriate quota, queue-splitting, aging, or SLA policy.
5. Implement and test a simple polling schedule guaranteeing that the low-priority group still gets turns.
6. Design metrics, alerts, and load-test scenarios to detect starvation before production operation.

## 2. Distinguishing Priority, Fairness, and Starvation

These three concepts are related but not synonymous:

| Concept | Core question | Example |
| --- | --- | --- |
| **Priority** | When multiple messages are waiting, which one is dequeued first? | Preferring \`9\` over \`1\` |
| **Fairness** | Do different work classes receive a reasonable opportunity to be served? | After at most three urgent turns, give one turn to the normal group if it has work |
| **Starvation** | Can one group wait indefinitely while another group always has work? | A \`1\` message pushed back by a continuous stream of \`9\`s |

A strict priority algorithm can be **correct in ordering** yet still **fail business SLAs**. Therefore, a requirement like “urgent messages go first” should be paired with a requirement such as “normal messages must not wait more than 30 seconds at design load”.

### Do Not Confuse with Other Issues

- **Backpressure:** Producers send faster than the system consumes, causing the queue to grow or fill; starvation can occur even when the total queue is not full.
- **Priority inversion:** High-priority work is blocked by a resource currently held by low-priority work. This is a dependency and resource-locking issue, distinct from starvation caused by queue scheduling.
- **Deadlock:** Tasks wait on each other cyclically and make no progress. Starvation can happen while **many other tasks continue completing normally**.
- **Slow handler:** A message has already been dequeued, but processing takes too long. Queue wait-time metrics and handler processing-time metrics must be separated for accurate diagnosis.

## 3. How Starvation Happens in PriorityChannel

Spring Integration provides \`PriorityChannel\`, a \`PollableChannel\`. With the default comparator, the higher the \`Integer\` value of the \`IntegrationMessageHeaderAccessor.PRIORITY\` header, the earlier the message is **dequeued**.

~~~mermaid
flowchart TD
    P["Producer"] -->|"priority=1"| Q["PriorityChannel"]
    P -->|"continuous priority=9"| Q
    Q -->|"Poll selects high-priority message"| H["Service Activator"]
    H --> OUT["Output"]
    Q -.->|"Priority-1 message keeps waiting"| L["Wait time increases"]
    L --> ALERT["May violate SLA"]
~~~

On each poll, if the queue contains both \`9\` and \`1\` messages, the \`9\` message is chosen. When high-priority traffic is high enough that \`9\` messages are always present in the queue, \`1\` messages may never get served.

### Important Condition

Starvation does not mean **every low-priority message will wait forever**. Once the high-priority backlog drains, the low-priority group gets a chance to proceed. The risk arises when the **high-priority source continuously maintains a backlog**, or consumes resources to the point where no capacity remains for other groups.

Suppose a single consumer processes an average of 20 messages/second:

| Situation | High-priority arrival rate | Remaining capacity by simple arithmetic | Implication |
| --- | --- | --- | --- |
| A | 5 messages/second | About 15 messages/second | Low group usually still gets turns |
| B | 18 messages/second | About 2 messages/second | Low group can wait a long time whenever a backlog forms |
| C | 22 messages/second | No spare capacity left | High-priority backlog tends to grow; low group risks never being polled |

This is only an illustrative model assuming uniform average processing time and fixed capacity. In reality, handlers vary in complexity, retries, I/O, and worker count; you must measure **arrival rate, service rate, and latency** per class rather than relying solely on averages.

### Dequeue Order Differs from Completion Order

Even when a \`9\` message is dequeued first, an \`ExecutorChannel\` or asynchronous handler can still allow another message to finish sooner. Priority Channel does not by itself provide:

- Cancellation of a low-priority task already running.
- Completion ordering across multiple workers.
- Exactly-once guarantees, idempotency, or error handling.
- Guarantees that every priority group receives a turn within a bounded time.

## 4. Controlled Test Example Reproducing Starvation

Testing starvation is really testing **liveness** (the ability to keep making progress). You should not write an infinite test. Instead, simulate several consecutive high-priority rounds and verify that the low-priority message remains held back.

This example uses Java 17, JUnit 5, AssertJ, and Spring Integration 6.x, without needing a broker, database, or poller. For a Spring Boot project, you can use compatible dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Create \`src/test/java/example/PriorityStarvationTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityStarvationTest {

    static Message<String> work(String id, int priority) {
        return MessageBuilder.withPayload(id)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("requestId", id)
                .build();
    }

    static String next(PriorityChannel channel) {
        Message<?> message = channel.receive(1_000);
        assertThat(message).isNotNull();
        return (String) message.getPayload();
    }

    @Test
    void priority_high_is_polled_before_low_when_both_are_waiting() {
        PriorityChannel channel = new PriorityChannel(10);

        channel.send(work("low", 1));
        channel.send(work("high", 9));

        assertThat(next(channel)).isEqualTo("high");
        assertThat(next(channel)).isEqualTo("low");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void repeated_high_arrivals_can_keep_low_waiting() {
        PriorityChannel channel = new PriorityChannel(20);

        channel.send(work("low-original", 1));
        for (int round = 1; round <= 8; round++) {
            String highId = "high-" + round;
            channel.send(work(highId, 9));

            // On every poll round, both high and low are waiting.
            assertThat(next(channel)).isEqualTo(highId);
        }

        // The low-priority message remains intact after being overtaken eight times.
        Message<?> low = channel.receive(1_000);
        assertThat(low).isNotNull();
        assertThat(low.getPayload()).isEqualTo("low-original");
        assertThat(low.getHeaders().get("requestId"))
                .isEqualTo("low-original");
        assertThat(channel.receive(0)).isNull();
    }

    @Test
    void high_priority_does_not_preempt_a_message_already_taken() {
        PriorityChannel channel = new PriorityChannel(10);
        channel.send(work("low-already-taken", 1));

        Message<?> started = channel.receive(1_000);
        assertThat(started.getPayload()).isEqualTo("low-already-taken");

        // The consumer already took low; high cannot turn back time.
        channel.send(work("urgent-new", 9));
        assertThat(next(channel)).isEqualTo("urgent-new");
    }
}
~~~

The \`repeated_high_arrivals_can_keep_low_waiting\` test demonstrates **eight consecutive delays**, sufficient to prove the risk. It does **not** prove infinite waiting via a finite observation. The accurate design statement is: if at every poll there is always a higher-priority message present, a strict priority algorithm can continue picking high-priority messages and give no turn to low-priority ones.

**Why is this test deterministic?** Each test creates its own channel and uses a single thread to send and receive, with no concurrent poller running. Therefore, the result does not depend on thread scheduling. If you switch to a flow with an active poller, control when the backlog is built before asserting order.

## 5. Designing a Fair Service Policy

No single strategy fits every business case. Choose a policy based on urgency, SLAs, message volume, processing duration, and the consequences if normal messages wait too long.

| Strategy | How it works | Fits when | Limitations |
| --- | --- | --- | --- |
| **Strict priority** | Always picks the highest level | Emergency work where urgent latency is the top goal | Starvation risk for lower levels |
| **Weighted scheduling** | Allocates turns, e.g., three high then one low | Priority is needed while ensuring progress for all classes | High does not always precede every low |
| **Separate queues + worker quota** | Reserves a portion of workers per class | Large enough load and distinct SLAs | Higher resource cost, requires quota tuning |
| **Aging** | Increases priority as wait time grows | Urgent items come first without starving lower classes | Requires careful update and re-sorting design |
| **Deadline-aware scheduling** | Considers deadline or remaining time to SLA | Explicit processing deadlines exist | Requires trustworthy timestamps and deadlines |
| **Throttling high sources** | Rate limiting or admission control | One urgent source can monopolize the queue | Must decide what happens to excess messages |

Strategies can be combined. For example: a Router splits \`urgent\` and \`normal\` into two queues, a scheduler gives urgent three turns then normal one turn, and rate limiting is applied at the source if urgent traffic overloads the system.

### What Guarantees Are Realistic?

With a **single sequential consumer** model and a rule of “at most three consecutive high picks if the normal queue has work”, a normal message already at the head of its queue will be picked **at the latest after the next three high turns**, provided the scheduler keeps being invoked and does not halt on errors. This is a guarantee in **dispatch turns**, not a fixed millisecond commitment.

If a high-priority task occasionally runs for minutes, three high turns can still leave a normal message waiting very long. To bound wall-clock wait time, add timeouts, processing-time limits, spare capacity, or deadline-based prioritization.

## 6. Example Scheduler with a Three-High, One-Low Quota

A simple way to reduce starvation is to use **two separate FIFO QueueChannels**, then choose which queue to poll next. This is a scheduling mechanism **outside \`PriorityChannel\`**, not an automatic fairness feature of Spring Integration.

~~~mermaid
flowchart LR
    IN["Input / Router"] -->|"URGENT"| HQ["urgent.queue"]
    IN -->|"NORMAL"| LQ["normal.queue"]
    HQ --> S{"Quota Scheduler\nmax 3 urgent"}
    LQ --> S
    S --> H["Handler"]
    H --> OUT["Output"]
~~~

Below is a standalone Java class. It serves the normal queue after at most three consecutive urgent pulls **if normal currently has a message**, and utilizes whichever queue has work when the other is empty.

~~~java
package example;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

final class QuotaScheduler {

    private final QueueChannel urgent;
    private final QueueChannel normal;
    private final int maxUrgentStreak;
    private int urgentStreak;

    QuotaScheduler(
            QueueChannel urgent,
            QueueChannel normal,
            int maxUrgentStreak) {
        if (maxUrgentStreak < 1) {
            throw new IllegalArgumentException(
                    "maxUrgentStreak must be positive");
        }
        this.urgent = urgent;
        this.normal = normal;
        this.maxUrgentStreak = maxUrgentStreak;
    }

    // Assumes a single thread calls pollNext().
    Message<?> pollNext() {
        if (urgentStreak >= maxUrgentStreak) {
            Message<?> fromNormal = normal.receive(0);
            if (fromNormal != null) {
                urgentStreak = 0;
                return fromNormal;
            }
            urgentStreak = 0;
        }

        Message<?> fromUrgent = urgent.receive(0);
        if (fromUrgent != null) {
            urgentStreak++;
            return fromUrgent;
        }

        Message<?> fromNormal = normal.receive(0);
        if (fromNormal != null) {
            urgentStreak = 0;
        }
        return fromNormal;
    }
}
~~~

This is a **single-threaded** scheduler to illustrate the algorithm. When multiple threads call \`pollNext()\` concurrently, \`urgentStreak\` must be protected with appropriate synchronization; across multiple application instances, quota must either be coordinated globally or deliberately applied per instance.

### Turn-Based Guarantee Testing

Create the test class:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QuotaSchedulerTest {

    private static void enqueue(QueueChannel channel, String value) {
        assertThat(channel.send(
                MessageBuilder.withPayload(value).build())).isTrue();
    }

    private static String next(QuotaScheduler scheduler) {
        Message<?> message = scheduler.pollNext();
        assertThat(message).isNotNull();
        return (String) message.getPayload();
    }

    @Test
    void normal_gets_a_turn_after_three_urgent_dispatches() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        enqueue(normal, "normal-1");
        for (int n = 1; n <= 6; n++) {
            enqueue(urgent, "urgent-" + n);
        }

        assertThat(next(scheduler)).isEqualTo("urgent-1");
        assertThat(next(scheduler)).isEqualTo("urgent-2");
        assertThat(next(scheduler)).isEqualTo("urgent-3");
        assertThat(next(scheduler)).isEqualTo("normal-1");
        assertThat(next(scheduler)).isEqualTo("urgent-4");
        assertThat(next(scheduler)).isEqualTo("urgent-5");
        assertThat(next(scheduler)).isEqualTo("urgent-6");
        assertThat(scheduler.pollNext()).isNull();
    }

    @Test
    void unused_normal_quota_does_not_block_urgent() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        for (int n = 1; n <= 5; n++) {
            enqueue(urgent, "urgent-" + n);
        }

        for (int n = 1; n <= 5; n++) {
            assertThat(next(scheduler)).isEqualTo("urgent-" + n);
        }
        assertThat(scheduler.pollNext()).isNull();
    }

    @Test
    void normal_is_served_when_urgent_queue_is_empty() {
        QueueChannel urgent = new QueueChannel();
        QueueChannel normal = new QueueChannel();
        QuotaScheduler scheduler = new QuotaScheduler(urgent, normal, 3);

        enqueue(normal, "normal-only");
        assertThat(next(scheduler)).isEqualTo("normal-only");
        assertThat(scheduler.pollNext()).isNull();
    }
}
~~~

**Observation:** Even though urgent still had three other messages left, \`normal-1\` was selected on the fourth turn. The test needs no \`Thread.sleep()\`, has no thread races, and measures the **dispatch rule** rather than wall-clock latency.

### Applying the Policy in Spring Integration

In a real flow, a Router can send to two channels \`urgent.queue\` and \`normal.queue\`. A dedicated scheduling component calls \`receive\` across both channels in turn and forwards the selected message to the Service Activator's input channel. A production design also needs to decide:

1. Who owns the poll schedule and how is the scheduler started/stopped?
2. When the handler throws an error, does the failed poll count toward the quota?
3. When one queue is full, should the producer wait, be rejected, or take a fallback path?
4. When deployed across multiple replicas, is the quota per replica or system-wide?
5. How are backlog and latency observed, and how is the SLA verified under high load?

Simply using two queues with two independent pollers does **not automatically** enforce a three-high-then-one-low rule. To guarantee a quota like in the example, you need a coordinating scheduler or controlled resource partitioning.

## 7. Aging: Increasing Opportunity for Long-Waiting Messages

**Aging** is a policy that increases a message's priority based on wait time. A conceptual model:

\[
P_{\mathrm{effective}} = P_{\mathrm{base}} + \alpha \times T_{\mathrm{waiting}}
\]

Where:

- \(P_{\mathrm{base}}\): initial business priority.
- \(T_{\mathrm{waiting}}\): elapsed wait time, in consistent units (e.g., seconds).
- \(\alpha\): priority growth factor over time.

For example, if \(\alpha = 1\) point/minute, a message with an initial priority of 1 after 10 minutes has an effective priority of 11; in a mechanism that **actually re-sorts**, it can overtake a newly arrived message with priority 9.

**Technical warning:** Do not assume that merely replacing \`PriorityChannel\`'s comparator with a calculation reading \`System.currentTimeMillis()\` is enough to implement aging. A priority queue orders elements upon insert/remove; as time passes, the queue **does not automatically reposition** existing elements simply because comparison keys change. A clock-dependent comparator can also break structural consistency while elements sit inside the data structure.

Clearer ways to implement aging:

- Periodically pick aged messages, compute their effective priority, and **re-insert them** into a queue structure that re-sorts under controlled rules.
- Re-sort the backlog under synchronization or use a scheduler outside the queue that selects by \`priority\` and \`waitingTime\`.
- Apply **deadline-aware scheduling** if completion deadlines matter more than abstract priority scores.

When choosing aging, decide whether to cap the boost, how to handle messages reaching their deadline, and ensure re-enqueuing neither drops nor duplicates messages. Tests should use a controllable clock or isolated time logic for deterministic results.

## 8. Splitting Queues and Dedicating Capacity

An operationally straightforward approach is dedicating resources to each work class:

~~~mermaid
flowchart LR
    IN["Input"] --> R{"Router"}
    R -->|"critical"| HQ["Critical Queue"]
    R -->|"normal"| NQ["Normal Queue"]
    HQ --> HC["Critical Workers"]
    NQ --> NC["Normal Workers"]
    HC --> OUT["Result"]
    NC --> OUT
~~~

For example, with four workers, you can **reserve** three workers for critical and one worker for normal. Even when critical always has a backlog, normal still has its own worker to continue processing. Conversely, when the normal queue is empty, the reserved worker may sit idle unless capacity borrowing is supported.

Quick comparison:

| Design | Guarantee when one class is chronically overloaded | Cost |
| --- | --- | --- |
| Single \`PriorityChannel\`, single consumer | Only guarantees picking the highest waiting priority | Lower classes easily delayed |
| Two queues + quota scheduler | Guarantees dispatch turns for lower class while scheduler runs | Must manage scheduling policy |
| Two queues + dedicated workers | Lower class has dedicated processing capacity | Uses more resources |
| Single queue + re-sorting aging | Long-waiting messages gain higher standing | Complexity around time and consistency |

Policy selection should not rely solely on message counts. A critical task taking 10 seconds while a normal task takes 5 ms creates very different pressure than tasks of equal cost.

## 9. Relationship with Other Patterns

Priority and fairness cut across an entire integration system:

### Router and Filter

Router can classify \`CRITICAL\`/\`NORMAL\` and send to two queues. Filter can drop invalid requests before they occupy queue space. Misconfiguring priority in a Header Enricher could mark all messages as critical, rendering the priority policy meaningless.

### Transformer and Payload

A Transformer modifying the payload does not necessarily update priority. If priority is derived from payload severity, compute and **validate the header before enqueuing**. Messages already sitting in \`PriorityChannel\` are not re-sorted automatically just because a mutable payload object changes later.

### Splitter, Aggregator, and Correlation

A high-priority message may be split by a Splitter into many fragments. If all fragments enter a high-priority queue, they can consume many processing turns. When an Aggregator waits for all fragments, one delayed low-priority item can make **the entire group** emit late. Tests must check both ordering and **correlation group completion latency**.

### Gateway

A synchronous Gateway waiting for a reply can time out even while its message sits in the queue. If a Gateway serves interactive users, normal user requests should not be delayed indefinitely just because background jobs continuously receive high priority.

### Retry and Error Channel

A critical message that repeatedly fails and retries too aggressively can monopolize workers, lengthening the backlog for every priority level. Limiting \`maxAttempts\`, backoff, circuit breakers, dead-letter/recovery flows, and rate limiting prevent a failing message from becoming an endless resource drain.

When a message is retried or replayed into a queue, check \`requestId\`, \`correlationId\`, idempotency key, priority level, and replay order. Priority Channel does not by itself guarantee safe retries, exactly-once delivery, or deduplication.

## 10. Metrics to Monitor for Detecting Starvation

Do not monitor only **total queue depth**. A queue with 1,000 fast high-priority messages may cause less harm than 20 low-priority messages waiting for hours.

| Metric | Grouped by | What it reveals |
| --- | --- | --- |
| \`queue_depth\` | Priority, tenant, or class | Which group is accumulating backlog |
| \`oldest_message_age_seconds\` | Priority/class | How long the oldest message has been waiting |
| \`queue_wait_seconds\` | Priority/class; p50/p95/p99 | Whether wait-time SLAs are breached |
| \`dispatch_count\` | Priority/class | Whether any group is receiving zero dispatches |
| \`arrival_rate\`, \`service_rate\` | Priority/class | Whether arrival rate exceeds processing capacity |
| \`processing_duration_seconds\` | Handler/class | Slowness due to handler vs. queue wait |
| \`retry_count\`, \`error_count\` | Priority/class | Whether a failing group is consuming workers |
| \`gateway_timeout_count\` | Route/class | Callers impacted by wait time |

To measure **wait time**, attach a business header like \`enqueuedAt\` right at enqueue time and measure when the message is dequeued. Clocks across machines can drift; if strict SLAs are required, define a unified time source, transport overhead, and measurement boundaries.

### Impact-Based Alerting Instead of Size Alone

Hypothetical example:

~~~text
Normal SLA:
  99% of messages are dequeued within 30 seconds.

Alert:
  oldest_normal_age > 30 seconds for multiple consecutive intervals,
  or normal p99 queue_wait_seconds exceeds 30 seconds.
~~~

The \`30 seconds\` value is **illustrative**, not a Spring Integration limit. Urgent events may have stricter thresholds. Each alert should include queue depth, arrival/service rates, worker count, retry ratio, and sample correlation/request IDs to pinpoint root cause.

## 11. Load Testing and Liveness Testing

The unit tests in Section 4 prove that **strict priority can delay lower classes**. To confirm an anti-starvation policy satisfies real requirements, run tests with realistic duration, concurrency, and traffic patterns.

A useful test matrix:

| Scenario | Condition | Expectation |
| --- | --- | --- |
| No critical traffic | Only normal enters queue | Normal uses available idle capacity |
| Light critical traffic | Critical arrives occasionally | Critical goes ahead while waiting; normal still completes |
| Steady critical traffic | Critical arrives near processing capacity | Normal still gets turns via quota or reserved workers |
| Critical burst | A large burst of critical | Normal stays within defined wait limit |
| Sustained critical overload | Critical arrives faster than processing | Backpressure engages; normal still makes progress if promised by policy |
| Continuous critical retries | Some handlers always fail | Retries are bounded and do not starve all workers |
| Normal nearing SLA | A normal message approaches deadline | Aging/deadline policy triggers if configured |
| Two tenants at same priority | Tenant A dominates traffic | Tenant B is not starved if tenant fairness applies |

### Designing the Measurement

1. Specify **arrival rate**, priority distribution, processing time, and total test duration.
2. Create at least one traceable normal message with an ID tracked from enqueue to dispatch.
3. Sustain critical traffic long enough to exercise a continuous backlog.
4. Verify **normal throughput ratio**, max or p99 wait time against SLA, and remaining backlog.
5. Repeat with retries, slow handlers, consumer restarts, or multiple replicas if those are real risks.

Never write tests that use \`Thread.sleep\` and assume messages have definitely been processed. Use completion signals, latches, bounded-timeout polling, or controllable clocks when testing time-based logic. Keep unit tests of scheduler decisions separate from integration tests with pollers and adapters so failures are easy to diagnose.

## 12. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Always picking highest priority without defining low-group SLAs | Starvation | Define a fairness or quota policy |
| Assuming \`PriorityChannel\` ages messages automatically | Old low messages stay low | Aging requires actual re-evaluation and re-sorting |
| Using a clock-reading comparator without re-heaping | Order does not reflect expected aging | Implement aging in a scheduler or appropriate structure |
| Measuring only total queue depth instead of per-class | Hides starving low backlog | Track oldest age and p99 per priority |
| Running two independent pollers and calling it a 3:1 quota | No turn-count guarantee | Use a coordinating scheduler or explicit worker quota |
| Testing ordering with concurrent producer/consumer | Flaky tests | Build backlog before polling; test concurrency separately |
| Confusing polling order with completion order | Wrong SLA conclusions | Measure wait time and processing time separately |
| Unbounded retries on urgent errors | Workers monopolized, other groups wait | Max attempts, backoff, circuit breaker, recovery |
| Using priority to enforce security or authorization | Invalid requests still get processed | Authenticate and authorize independently of priority |
| Configuring a global quota while each replica counts locally | Skewed behavior when scaling | Clearly define per-instance vs. global quota |

## 13. Practice Exercises

### Exercise A — Reproducing Delay

Create a \`PriorityChannel\` and enqueue one \`LOW\` message with priority 1. Over the next eight rounds, send one \`HIGH\` message with priority 9 and perform one poll. Verify all eight polls retrieve HIGH; then stop sending HIGH and prove LOW is eventually retrieved. Explain why this demonstrates starvation risk rather than proving infinite wait.

### Exercise B — Reducing Wait Time with Quota

Starting from \`QuotaScheduler\`, change \`maxUrgentStreak\` from 3 to 2. Send five urgent and two normal messages. Check the dispatch schedule when both queues continuously have messages and derive the bound on urgent turns before each normal turn. Add a test for when the normal queue is empty to ensure the scheduler wastes no capacity.

### Exercise C — Evaluating Aging

Propose a formula computing effective priority from \`basePriority\`, enqueue time, and an aging factor. Test with a normal message waiting 10 minutes and a newly arrived critical message. Describe the re-sorting mechanism or scheduler using effective priority; do not merely swap the queue comparator and expect positions to update automatically.

### Exercise D — Priority and Retries

Create a critical handler that consistently fails transiently, with bounded retries. Meanwhile, send normal messages. Measure retry attempts, worker occupation time, and normal wait time. Choose a mitigation such as backoff, worker reservation, or circuit breaking to preserve normal progress, and write a test verifying it.

### Exercise E — Observing Latency by Work Class

Attach \`enqueuedAt\` and \`requestId\` to messages, measure at dequeue time, and emit a \`queue_wait_seconds\` metric tagged by \`critical\`/\`normal\`. Create a heavy critical scenario where normal exceeds a hypothetical threshold; verify the alert fires accurately and includes enough context to locate the delaying queue/handler.

## 14. Self-Assessment Criteria

The lesson meets its goal when you can clearly answer:

1. Why can a low-priority message wait indefinitely even when consumers are continuously processing work?
2. What state of \`PriorityChannel\` allows a newly arrived high-priority message to overtake an older message?
3. Why do finite tests only demonstrate **the possibility of repeated delay**?
4. Which policies guarantee progress for lower groups: quota, worker reserve, aging, or deadlines?
5. Is the policy bound expressed in dispatch turns or wall-clock time?
6. How do you verify the policy when multiple workers, retries, brokers, or replicas are involved?
7. Which metrics indicate that a group is being starved rather than merely processed slowly?

**Key takeaway:** Priority helps a system favor important work, yet a well-operated system must also define a **minimum level of fairness** for other classes. By designing testable quotas or aging, measuring wait time per priority, and controlling retries and capacity, you can use Spring Integration to serve urgent work while keeping the rest of the message flow moving.
