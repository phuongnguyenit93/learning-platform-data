# Distinguishing Priority from Deadlines in Spring Integration

## 1. Why Might a HIGH Message Not Have to Run Before a LOW Message?

An order-processing service receives two requests at 09:59:40:

| Request | Priority | Completion deadline | Estimated processing time |
| --- | ---: | --- | ---: |
| A: risk review | HIGH = 9 | 10:30:00 | 30 seconds |
| B: reserve stock hold | LOW = 1 | 10:00:00 | 5 seconds |

Under **strict priority**, the consumer may pick A before B. B starts around 10:00:10 and definitely misses its deadline in this single-worker scenario. If B is picked first, B can finish at 09:59:45 while A still has plenty of time. However, always picking the earliest deadline can allow many urgent-deadline LOW tasks to consume all slots away from an especially critical HIGH task.

These two concepts answer two different questions:

- **Priority**: *Which task is more important under the resource-allocation policy?* This is usually a **relative** ranking among waiting tasks.
- **Deadline**: *By what point in time must the result be achieved?* This is a **time** constraint tied to business requirements.

There is no universal rule that HIGH implies a near deadline or LOW implies permission to finish late. You need a **scheduling policy** that interprets both.

This lesson belongs to the **Priority** chapter of the `SPRING_INTEGRATION_PATTERN` module. When implementing Enterprise Integration Patterns with Spring Integration—Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation—we must preserve priority/deadline semantics across channels and branches while testing and observing actual outcomes.

### Target Outcomes

After this lesson, you will be able to:

1. Distinguish priority, deadline, TTL/expiration, timeout, delay, SLA, and SLO.
2. Explain clearly what `PriorityChannel` guarantees and what it does not guarantee.
3. Read and evaluate strict priority, earliest-deadline-first (EDF), least-slack-time (LST), quotas, and deadline overrides.
4. Design metadata/contracts to carry deadlines across EIPs and adapters.
5. Handle expired messages per business rules without silently dropping or retrying infinitely.
6. Write Java + JUnit tests using a fake `Clock` to test deadline selection and retry budgets.
7. Distinguish on-time **start** from on-time **completion/commit**; measure deadline misses under load.

## 2. Comparison Table of Related Concepts

| Concept | Meaning | Example | What not to infer |
| --- | --- | --- | --- |
| **Priority** | Relative importance when granting turns. | 9 outranks 5 and 1. | A priority-9 message definitely finishes in 2 seconds. |
| **Deadline** | Latest point by which the result is required. | Complete before 10:00 UTC. | The scheduler automatically meets that timestamp. |
| **Time-to-live (TTL)** | How long a message stays alive inside a resource per policy. | Broker TTL of 30 seconds. | The handler committed before TTL expired. |
| **Expiration** | Time/mechanism when a resource considers a message expired. | Broker dead-letters TTL-expired messages. | The business domain recorded an EXPIRED status. |
| **Timeout** | Time limit for a wait or operation. | Gateway waits 2 seconds for reply. | The server definitely halted side effects after 2 seconds. |
| **Delay / scheduled time** | Must not start before a given timestamp. | Run after 09:00. | Must finish before a deadline. |
| **Processing budget** | Estimated time allotted to a flow segment. | Handler takes roughly 500 ms. | Actual runtime is always 500 ms. |
| **SLO** | Measurable service-quality objective. | HIGH p99 queue wait under 1 second. | Every message meets its business deadline. |
| **SLA** | Commitment to customers/partners and applicability terms. | 99.9% of transactions finish within 5 seconds. | A single annotation creates a guarantee by itself. |

### Timestamps to Keep Separate

~~~text
createdAt      : when the request originated in the business domain
enqueuedAt     : when it was written into the queue
startedAt      : when the handler actually started
completedAt    : when the result is considered complete per contract
deadlineAt     : latest timestamp allowed for completion
~~~

Example:

~~~text
createdAt   09:59:30
enqueuedAt  09:59:35
startedAt   09:59:50
completedAt 10:00:05
deadlineAt  10:00:00

Queue wait = 15 seconds
End-to-end latency = 35 seconds
Completion lateness = 5 seconds
~~~

**Starting before the deadline does not equal completing on time.** If a domain defines the deadline on *start* rather than *outcome*, state that explicitly and test accordingly; never silently swap meanings.

## 3. Priority Is Ordering; Deadline Is a Time Constraint

Example business classification:

~~~java
enum WorkClass {
    HIGH(9), NORMAL(5), LOW(1);

    private final int value;

    WorkClass(int value) {
        this.value = value;
    }

    int priority() {
        return value;
    }
}
~~~

Values 9–5–1 are purely an **internal convention**, not three fixed Spring Integration constants. With default `PriorityChannel`, higher priority numbers are selected first among **messages remaining in the queue**.

Deadlines are stored as absolute timestamps:

~~~java
Instant deadlineAt =
        Instant.parse("2026-11-21T10:00:00Z");
~~~

Never pass timezone-less `LocalDateTime` across services in different regions. Store **`Instant` or ISO-8601 timestamps with explicit offsets**, and monitor clock skew across nodes. Use a monotonic clock like `System.nanoTime()` for intra-process durations; use wall-clock/UTC when comparing against a shared absolute deadline.

### Four Scenarios to Distinguish

| Scenario | Interpretation |
| --- | --- |
| HIGH with distant deadline, LOW with near deadline | Priority-first and deadline-first can pick differently. |
| HIGH and LOW with the same deadline | Need a tie-breaker by business criticality or FIFO. |
| LOW already picked up by worker, HIGH arrives later | HIGH does not automatically interrupt the running LOW task. |
| Both HIGH and LOW are already expired | Need an expiration policy rather than processing normally. |

## 4. Does PriorityChannel Use Deadlines?

`PriorityChannel` is a `PollableChannel`. It picks messages by the priority header or a configured `Comparator<Message<?>>`. It **does not automatically read** a custom `deadlineAt` header as a business deadline.

~~~java
@Bean("priorityPending")
PollableChannel priorityPending() {
    return new PriorityChannel(100);
}
~~~

~~~java
Message<String> high = MessageBuilder.withPayload("HIGH-FAR")
        .setHeader("priority", 9)
        .setHeader("deadlineAt",
                Instant.parse("2026-11-21T10:30:00Z"))
        .build();

Message<String> low = MessageBuilder.withPayload("LOW-SOON")
        .setHeader("priority", 1)
        .setHeader("deadlineAt",
                Instant.parse("2026-11-21T10:00:00Z"))
        .build();

priorityPending.send(low);
priorityPending.send(high);
Message<?> selected = priorityPending.receive(0);
// Under default strict priority, selected is usually HIGH-FAR.
~~~

| Component | Core behavior | Does it automatically guarantee deadlines? |
| --- | --- | --- |
| `DirectChannel` | Dispatches handler synchronously on caller thread. | No. |
| `ExecutorChannel` | Hands off per executor/thread scheduling. | No. |
| `QueueChannel` FIFO | Dequeues messages by queue entry order. | No. |
| `PriorityChannel` | Selects by priority/comparator. | No, unless a custom scheduler/comparator is designed—and still cannot guarantee completion. |
| `Delayer`/delayed endpoint | Defers processing until an allowed time. | No; delay differs from deadline. |
| `Service Activator` | Executes the business handler. | Only if code/architecture checks and enforces the contract. |

Just because a channel **propagates a header intact** does not mean it **uses** that header for scheduling. A `DirectChannel` carrying `priority=9` still runs synchronously without reordering.

## 5. Deadlines, Slack, and Feasibility

~~~text
remainingTime = deadlineAt - now
estimatedDuration = estimated processing duration
slack = deadlineAt - now - estimatedDuration
lateness = completedAt - deadlineAt
~~~

`slack > 0` means spare time remains per estimate; `slack = 0` means right on the edge; `slack < 0` means it is already estimated to be late even if started right now.

| Task | Priority | Remaining time | Estimated duration | Slack |
| --- | ---: | ---: | ---: | ---: |
| A | 9 | 15 seconds | 1 second | +14 seconds |
| B | 1 | 18 seconds | 17 seconds | +1 second |

B has a later deadline than A yet much less slack. Choosing earliest deadline versus least slack can pick differently.

**Estimates are not guarantees.** CPU, database locks, GC, network hiccups, retries, and prefetching can make actual runtime exceed estimates. Systems need timeouts, admission control, backpressure, and actual completion metrics.

## 6. Comparing Scheduling Algorithms

| Policy | Selection rule | Benefit | Limitation |
| --- | --- | --- | --- |
| **Strict priority** | Highest priority number first. | Helps critical classes get turns first. | LOW starvation; can miss near deadlines. |
| **EDF (earliest deadline first)** | Earliest deadline first. | Sensible when deadlines are the primary constraint. | Can starve HIGH or deadline-less tasks. |
| **LST (least slack time)** | Smallest `deadline - now - estimate` first. | Factors in remaining work needed. | Relies on estimates; fragile when task lengths vary. |
| **Weighted round-robin** | Allocates turns e.g. 4:2:1 across three tiers. | Gives LOW guaranteed progress turns. | Does not guarantee wall-clock deadlines in seconds. |
| **Deadline override** | Normally follows priority/quotas, promotes near-deadline tasks. | Balances criticality and time pressure. | Needs protection against deadline gaming. |
| **Reserved capacity** | Dedicates workers or quotas per class/tenant. | Limits starvation from pool sharing. | Shared downstreams can still bottleneck. |

### Illustrative Combined Policy

~~~text
On each work selection:
  1. Flag/route tasks already past deadline separately.
  2. Compute remainingTime and slack for remaining eligible tasks.
  3. If any task has slack <= 10 seconds, pick the earliest deadline among them.
  4. Otherwise, select by class priority or quotas.
  5. Log selection reason and timestamps.
~~~

This is an **application policy**, not a Spring Integration default. If every client claims a 1-second deadline, the near-deadline group will capture every worker; validate deadlines against caller permissions and business type.

## 7. EDF Comparator: Using Immutable Deadlines for Ordering

A stable `Comparator<Message<?>>` can select the earliest deadline first:

~~~java
static Instant requiredDeadline(Message<?> message) {
    Object value = message.getHeaders().get("deadlineAt");
    if (!(value instanceof Instant deadline)) {
        throw new IllegalArgumentException("Missing deadlineAt");
    }
    return deadline;
}

Comparator<Message<?>> byDeadlineThenPriority = (a, b) -> {
    int deadlineOrder =
            requiredDeadline(a).compareTo(requiredDeadline(b));
    if (deadlineOrder != 0) {
        return deadlineOrder; // Earlier deadline first.
    }
    int pa = ((Number) a.getHeaders().get("priority")).intValue();
    int pb = ((Number) b.getHeaders().get("priority")).intValue();
    return Integer.compare(pb, pa); // On equal deadlines, HIGH first.
};

PriorityChannel edfQueue =
        new PriorityChannel(100, byDeadlineThenPriority);
~~~

Before enqueuing, the application must validate `deadlineAt` and `priority` so the comparator never hits null or wrongly typed values. With persistent stores, **do not** assume an in-memory comparator applies to the store or external broker.

This comparator only orders waiting messages; it does not:

- Preempt a handler that has already started.
- Know actual processing duration.
- Automatically cancel expired messages.
- Automatically guarantee every deadline under overload.
- Manage transactions, ACK/redelivery, or idempotency.

### Clock-Based Comparator Pitfall

Never write a comparator depending on `Instant.now()` expecting a heap to re-sort automatically by age. A priority queue does not re-evaluate every element every second. If aging or deadline override depends on `now`, use a scheduler that re-evaluates at selection time, promotion/reinsertion, or policy-driven store queries, tested with a fake clock.

## 8. Building a Priority + Deadline Contract at Ingress

Place both values in the domain contract instead of inferring one from the other:

~~~java
record WorkRequest(
        String eventId,
        String type,
        Instant requestedDeadline) {}

record WorkCommand(
        String eventId,
        String type,
        int priority,
        Instant deadlineAt) {}

final class WorkPolicy {
    static int priorityFor(String type) {
        return switch (type) {
            case "FRAUD_REVIEW", "RISK_CANCEL" -> 9;
            case "PAYMENT_CONFIRM" -> 5;
            case "REPORT_REFRESH" -> 1;
            default -> throw new IllegalArgumentException(
                    "Unknown type: " + type);
        };
    }

    static WorkCommand normalize(WorkRequest request, Clock clock) {
        if (request.eventId() == null
                || request.eventId().isBlank()
                || request.requestedDeadline() == null) {
            throw new IllegalArgumentException("Missing required fields");
        }
        Instant now = clock.instant();
        Instant deadline = request.requestedDeadline();
        if (deadline.isAfter(now.plus(Duration.ofDays(7)))) {
            throw new IllegalArgumentException("Deadline too far away");
        }
        return new WorkCommand(
                request.eventId(),
                request.type(),
                priorityFor(request.type()),
                deadline);
    }
}
~~~

The 7-day limit is an **example policy**. For past deadlines, a domain may return an expired outcome rather than rejecting input; no single rule fits every API.

### Never Trust Arbitrary Caller-Supplied Deadlines

If an external client can pass `deadlineAt=now+1s`, it can seize urgent slots even when the underlying work is a LOW report. Therefore:

1. Authenticate caller authority and task type.
2. Enforce min/max deadline bounds per tenant SLA.
3. Let the server compute or clamp deadlines.
4. Apply separate quotas/rate limits per work type.
5. Record `deadlineSource` and `policyVersion` for decision auditing.

## 9. Message and Metadata Contract

~~~java
WorkCommand command = WorkPolicy.normalize(request, clock);

Message<WorkCommand> message =
        MessageBuilder.withPayload(command)
                .setHeader("priority", command.priority())
                .setHeader("deadlineAt", command.deadlineAt())
                .setHeader("businessEventId", command.eventId())
                .setHeader("deadlinePolicyVersion", "v1")
                .build();
~~~

| Field | Meaning | Notes |
| --- | --- | --- |
| `priority` | Importance level for scheduler/channel. | Validate type/range; broker mappers have native properties. |
| `deadlineAt` | Absolute deadline timestamp. | Custom header; does not trigger broker expiration automatically. |
| `businessEventId` | Business ID preserved across retries. | Never replace with `MessageHeaders.ID`. |
| `originalEnqueuedAt` | Tracks wait age across multiple enqueues. | Never reset on retry/promotion. |
| `correlationId` | Correlates Splitter/Aggregator branches. | Distinct from child event ID. |
| `deadlinePolicyVersion` | Version of deadline rule/source. | Useful during audits and policy updates. |

At external boundaries, export only an **allowlist** of wire-compatible headers. Headers like `replyChannel` and `errorChannel` may hold internal objects that must not be pushed blindly over HTTP/JMS/Kafka.

## 10. Java: Selector Combining Priority and Deadline

To test policy **independently of a Spring context**, write a selector operating on a pre-populated pending list in tests. This is not a durable/concurrent production queue.

~~~java
record PendingTask(
        String eventId,
        int priority,
        Instant deadlineAt,
        Instant acceptedAt,
        Duration estimatedDuration) {}

final class DeadlineAwareSelector {
    private final Clock clock;
    private final Duration urgentWindow;

    DeadlineAwareSelector(Clock clock, Duration urgentWindow) {
        this.clock = clock;
        this.urgentWindow = urgentWindow;
    }

    PendingTask select(List<PendingTask> pending) {
        Instant now = clock.instant();

        // Select only eligible tasks; expired ones must have a separate outcome.
        List<PendingTask> eligible = pending.stream()
                .filter(t -> !now.isAfter(t.deadlineAt()))
                .toList();
        if (eligible.isEmpty()) {
            throw new NoSuchElementException("No eligible tasks");
        }

        List<PendingTask> urgent = eligible.stream()
                .filter(t -> slack(t, now).compareTo(urgentWindow) <= 0)
                .toList();

        if (!urgent.isEmpty()) {
            return urgent.stream()
                    .min(Comparator
                            .comparing(PendingTask::deadlineAt)
                            .thenComparing(
                                    Comparator.comparingInt(
                                            PendingTask::priority).reversed())
                            .thenComparing(PendingTask::acceptedAt)
                            .thenComparing(PendingTask::eventId))
                    .orElseThrow();
        }

        return eligible.stream()
                .min(Comparator
                        .comparingInt(PendingTask::priority).reversed()
                        .thenComparing(PendingTask::acceptedAt)
                        .thenComparing(PendingTask::eventId))
                .orElseThrow();
    }

    private static Duration slack(PendingTask task, Instant now) {
        return Duration.between(now, task.deadlineAt())
                .minus(task.estimatedDuration());
    }
}
~~~

Meaning:

- If any eligible task has slack at most `urgentWindow`, pick the near-deadline task with the **earliest deadline**.
- Otherwise, pick the highest priority and then earliest acceptance time.
- Expired tasks are excluded from normal work selection, yet **must not be silently deleted from the source**.
- The selector uses an injected `Clock` so tests can freeze time.

**Limitation:** each selection scans `O(n)`. For millions of messages, use indexes, database claim/lease queries, or a dedicated queue scheduler. Multiple workers require atomic claim/ACK operations to avoid two workers picking the same task. If every task becomes near-deadline, the rule above can still delay HIGH, so add separate quotas/admission control when required by the domain.

## 11. Unit Tests with a Fixed Clock

### Near-Deadline LOW Prioritized Ahead of Distant-Deadline HIGH

~~~java
@Test
void lowNearDeadlineCanOvertakeHighWithDistantDeadline() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask high = new PendingTask(
            "HIGH-1", 9, now.plusSeconds(1800),
            now.minusSeconds(20), Duration.ofSeconds(2));
    PendingTask low = new PendingTask(
            "LOW-1", 1, now.plusSeconds(12),
            now.minusSeconds(40), Duration.ofSeconds(5));

    assertEquals("LOW-1",
            selector.select(List.of(high, low)).eventId());
}
~~~

LOW has **7 seconds** of slack, falling inside the 10-second urgent window. HIGH has plenty of time. This is a unit test of the deadline-override policy, **not** default `PriorityChannel` behavior.

### When No Task Is Urgent, HIGH Wins

~~~java
@Test
void highWinsWhenBothDeadlinesAreComfortable() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask high = new PendingTask(
            "HIGH-2", 9, now.plusSeconds(100),
            now, Duration.ofSeconds(5));
    PendingTask low = new PendingTask(
            "LOW-2", 1, now.plusSeconds(70),
            now, Duration.ofSeconds(5));

    assertEquals("HIGH-2",
            selector.select(List.of(low, high)).eventId());
}
~~~

Pure EDF would select LOW in this same case because LOW's deadline is earlier. This illustrates why you must **state the policy explicitly** before asserting expected order.

### Do Not Select Expired Work as Normal Tasks

~~~java
@Test
void expiredWorkIsExcludedFromNormalSelection() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    DeadlineAwareSelector selector = new DeadlineAwareSelector(
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofSeconds(10));

    PendingTask expired = new PendingTask(
            "EXPIRED", 9, now.minusSeconds(1),
            now.minusSeconds(20), Duration.ofSeconds(1));
    PendingTask valid = new PendingTask(
            "VALID", 1, now.plusSeconds(40),
            now, Duration.ofSeconds(2));

    assertEquals("VALID",
            selector.select(List.of(expired, valid)).eventId());
}
~~~

**Important:** production requires an explicit **expired transition**: record EXPIRED status, quarantine/reconcile, or route to late handling per domain rules. Filtering expired items out of a list without recording state is a silent work-loss bug.

## 12. Business-Specific Rules for Expired Messages

| Task type | When past deadline | Why |
| --- | --- | --- |
| Reservation hold valid only until 10:00 | Do not confirm late; record `EXPIRED_NOT_EXECUTED`. | Confirming past validity violates business rules. |
| Periodic report delivery | May proceed and record `COMPLETED_LATE`. | Data remains valuable even when SLA is late. |
| Security alert | May still require processing and escalation. | Ignoring alerts is riskier than finishing late. |
| Timed-out partner call | Verify actual remote state before retrying. | Partner may have committed despite caller timeout. |
| Multi-step payment/inventory hold | Re-check state; may cancel/compensate. | Another branch may already have committed side effects. |

Deadline handling also depends on transaction state and whether work is allowed to **start** before the deadline and **finish** afterward. Document this as a domain decision rather than a single `if (now > deadline)` check.

## 13. IntegrationFlow: Priority Queue and Deadline Guard Are Separate Responsibilities

A small flow separates **priority turn selection** from **deadline validity enforcement**:

~~~mermaid
flowchart LR
    A["Gateway / inbound adapter"] --> B["Normalize priority and deadline"]
    B --> C["PriorityChannel"]
    C --> D["Polling endpoint"]
    D --> E{"DeadlineGate"}
    E -->|"Eligible"| F["Service Activator"]
    E -->|"Expired"| G["Expired outcome / reconcile"]
    F --> H[("Business database")]
~~~

Java DSL example:

~~~java
@Configuration
@EnableIntegration
class PriorityDeadlineFlowConfig {
    @Bean("priorityIngress")
    MessageChannel priorityIngress() {
        return new DirectChannel();
    }

    @Bean("priorityPending")
    PollableChannel priorityPending() {
        return new PriorityChannel(200);
    }

    @Bean
    IntegrationFlow enqueueFlow() {
        return IntegrationFlow.from("priorityIngress")
                .channel("priorityPending")
                .get();
    }

    @Bean
    IntegrationFlow consumeFlow(DeadlineGate gate) {
        return IntegrationFlow.from(
                        "priorityPending",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(200)
                                        .maxMessagesPerPoll(1)))
                .handle(gate, "consume")
                .get();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

The gate checks deadline/priority before invoking the business service:

~~~java
@Component
class DeadlineGate {
    private final Clock clock;
    private final WorkProcessor processor;

    DeadlineGate(Clock clock, WorkProcessor processor) {
        this.clock = clock;
        this.processor = processor;
    }

    public void consume(Message<WorkCommand> message) {
        WorkCommand work = message.getPayload();
        Object headerPriority = message.getHeaders().get("priority");
        Object headerDeadline = message.getHeaders().get("deadlineAt");

        if (!(headerPriority instanceof Integer priority)
                || !(headerDeadline instanceof Instant deadline)
                || priority.intValue() != work.priority()
                || !deadline.equals(work.deadlineAt())) {
            throw new IllegalArgumentException(
                    "Priority/deadline header mismatch");
        }

        if (clock.instant().isAfter(deadline)) {
            throw new DeadlineExceededException(
                    work.eventId(), deadline);
        }

        processor.process(work);
    }
}

@Service
class WorkProcessor {
    @Transactional
    public void process(WorkCommand work) {
        // Perform business DB writes and idempotency using work.eventId().
        // Actual domain actions added in practice exercises.
    }
}

class DeadlineExceededException extends RuntimeException {
    DeadlineExceededException(String id, Instant deadline) {
        super("Work " + id + " expired at " + deadline);
    }
}
~~~

### Understanding the Exact Scope of This Example

1. `PriorityChannel` here is **in-memory** and strict priority: it does not enforce EDF or deadline override.
2. `DeadlineGate` only detects **expiration before processing**. If the processor runs slowly, the task can still finish late.
3. Throwing an exception does not automatically persist an expired state or route to a DLQ. Configure an appropriate error flow/message source.
4. An in-memory queue does not recover a dequeued message when JDBC rolls back; this snippet is not a durable production architecture.
5. `@Transactional` coordinates participating DB/transaction-manager resources; it does not undo HTTP or broker side effects.

When a near-deadline LOW must overtake a distant-deadline HIGH, replace the **selection mechanism** with the Section 10 selector, an appropriate EDF comparator, or a purpose-built scheduler/store. Adding `DeadlineGate` behind a strict priority queue alone is **not enough** to prevent deadline misses caused by starvation.

## 14. Gateway, Transformer, and Router: Preserving Deadlines Across Hops

~~~mermaid
flowchart LR
    A["Gateway request"] --> B["Header Enricher"]
    B --> C["Transformer"]
    C --> D{"Router"}
    D --> E["DirectChannel branch"]
    D --> F["Async executor / broker branch"]
    E --> G["Deadline validation"]
    F --> G
~~~

### Gateway: Request Timeout Differs from Deadline

~~~java
@MessagingGateway(defaultRequestChannel = "priorityIngress")
interface WorkGateway {
    void submit(Message<WorkCommand> command);
}
~~~

Requests can carry policy-assigned `priority` and `deadlineAt`. If the Gateway accepts only a payload, enrich metadata at an ingress step. A Gateway reply timeout such as 2 seconds **does not mean an asynchronous worker was cancelled after 2 seconds**.

### Transformer: Do Not Silently Extend Deadlines

When transforming payloads:

~~~java
Message<NormalizedWork> output =
        MessageBuilder.withPayload(
                    normalize(input.getPayload()))
                .copyHeaders(input.getHeaders())
                .setHeader("priority", validatedPriority)
                .setHeader("deadlineAt", validatedDeadline)
                .build();
~~~

`normalize(...)` and validation variables belong to the application service. Spring Integration applies endpoint-dependent reply-header copy/merge rules, so **test actual outputs**; when custom code constructs a `Message`, define the header policy explicitly.

### Router: Remaining Budget May Shrink Differently Per Branch

If a Router forwards to a service in another geographic region, the absolute deadline stays shared, yet **remaining budget shrinks** due to serialization, queuing, and network transit. Never pass a one-time duration computed at the producer as if it stayed constant across services.

When crossing an `ExecutorChannel`, thread-bound caller transactions do not follow the worker thread. Even if the sender commits, that does not prove the worker still has enough time left to finish.

## 15. Splitter and Aggregator: One End-to-End Deadline, Multiple Budgets

In a checkout workflow:

~~~mermaid
flowchart LR
    A["Checkout: deadline T"] --> B["Splitter"]
    B --> C["Reserve stock"]
    B --> D["Verify payment"]
    B --> E["Fraud check"]
    C --> F["Aggregator"]
    D --> F
    E --> F
    F --> G["Commit checkout before T"]
~~~

The parent deadline may be 10:00:00, yet child results must be ready **before** that time so aggregation and commit still fit:

~~~text
Parent completion deadline : 10:00:00
Inventory child deadline   : 09:59:45
Payment child deadline     : 09:59:45
Fraud check deadline       : 09:59:50
Aggregation/commit budget  : 10 seconds
~~~

These are illustrative budgets, not fixed policies. Key practices:

- Child messages retain `parentDeadlineAt` and `correlationId`.
- Each child has its own `deadlineAt` sized for its branch cost.
- Never silently “add 30 extra seconds” per child and push the overall workflow past the parent deadline.
- Each child has a stable `childEventId` for deduplication.
- On Aggregator timeout/partial release, define valid partial outcomes, retries, cancellations, or compensation.

**Group timeout does not necessarily equal the business deadline.** `Aggregator` has its own release strategy, timeout, and message store; late child arrivals require domain handling rather than expecting correlation to roll back sibling worker side effects.

### One Branch Committed, Another Branch Late

If Reserve Stock already committed to the DB while Verify Payment timed out, the Aggregator cannot automatically roll back an already committed transaction on another worker. You may need a new `ReleaseReservation` command, persisted workflow state, and retried compensation. That is **Saga/compensation**, not a distributed JDBC rollback across brokers.

## 16. Deadlines and TTL in JMS, RabbitMQ, and Kafka

| Resource | Priority | TTL/expiration or retention | Business deadline |
| --- | --- | --- | --- |
| **JMS** | Message `JMSPriority`; broker/provider defines semantics. | Producer TTL / JMS expiration per provider. | Store business timestamp separately when completion deadlines apply. |
| **RabbitMQ/AMQP** | Message priority property on priority-capable queues. | Message/queue TTL and dead-lettering per policy. | Custom timestamp plus gate/handler enforcing it. |
| **Kafka** | Custom headers do not reorder records within a partition. | Topic/log retention. | Carry in record header/payload; re-validate at consumer. |
| **JDBC-backed MessageStore** | May order by priority if store type supports it. | Cleanup or expiry per config. | Requires application policy; no built-in deadline scheduler. |
| **HTTP** | App headers do not create broker prioritization. | Request and connection timeouts. | Separate API contract and terminal status. |

### JMS: TTL Does Not Guarantee Business Commit

A message sent at 09:59:00 with a 60-second TTL can be delivered at 09:59:59 while the consumer finishes at 10:00:30. **The message was delivered within TTL yet business processing completed late.** Once a consumer receives the message, broker expiration does not roll back committed DB changes.

### RabbitMQ: TTL and Priority Coexist Independently

A HIGH message can expire via TTL before reaching a consumer if the queue is overloaded. A LOW message already **prefetched** before HIGH arrives is not pulled back into the queue for HIGH to run ahead. Test broker priority property, `x-max-priority` queue support, prefetch, and TTL/expiration **separately**.

### Kafka: Retention Is Not a Deadline

Kafka stores records by partition/offset; a `deadlineAt` record header does not make the broker jump offsets. To run near-deadline HIGH items first, partition into separate consumer pools or use an application-tier scheduler that still respects aggregate ordering invariants.

### Propagate Absolute Deadlines, Not Just `remainingMillis`

~~~text
Producer at 09:59:55: remainingMillis = 5000
Record waits in broker 4 seconds
Consumer receives at 09:59:59

If consumer reads stale remainingMillis=5000 -> wrong!
Must read deadlineAt=10:00:00 and recompute 1 second remaining.
~~~

Clock synchronization across nodes is an essential operational requirement. In distributed systems, measure and alert on clock skew, and pick a consistent time authority for financially consequential decisions.

## 17. Retries and Redelivery Consume Remaining Time

A message has a 9-second deadline from start:

~~~text
Attempt 1: 3 seconds -> transient error
Backoff:   2 seconds
Attempt 2: 3 seconds -> error
Backoff:   4 seconds

Retrying further already exceeds deadline.
~~~

Include:

- Maximum attempt limits.
- Backoff, jitter, and deadline-aware retry budgets.
- Stable `businessEventId` across retries/redeliveries.
- Classification of transient vs. permanent vs. ambiguous-outcome errors.
- Expired outcomes when insufficient budget remains.
- Observable DLQ/quarantine with controlled replay.

Checking *whether an attempt still fits*:

~~~java
static boolean canRetry(
        Instant deadline,
        Instant now,
        Duration backoff,
        Duration estimatedDuration) {
    return !now.plus(backoff)
            .plus(estimatedDuration)
            .isAfter(deadline);
}
~~~

Unit test:

~~~java
@Test
void retryRespectsRemainingDeadlineBudget() {
    Instant now = Instant.parse("2026-01-01T10:00:00Z");
    Instant deadline = now.plusSeconds(5);

    assertTrue(canRetry(
            deadline, now,
            Duration.ofSeconds(1),
            Duration.ofSeconds(2)));

    assertFalse(canRetry(
            deadline, now,
            Duration.ofSeconds(4),
            Duration.ofSeconds(2)));
}
~~~

`canRetry` uses estimates; real execution can still overrun. If an attempt committed to the DB while the broker ACK was lost, the source may redeliver past the deadline. Consumers must check **idempotency and prior commit state**, rather than assuming expired means the business operation never ran.

### Error Channel and Expiration Are Not One Single Error Type

When a handler throws, Spring Integration can wrap it in an `ErrorMessage` sent to `errorChannel` depending on adapter/configuration. The error payload is usually an exception; to inspect original message metadata, extract the failed message or keep a separate snapshot. Distinguish outcomes cleanly:

| Status | Semantics |
| --- | --- |
| `EXPIRED_NOT_EXECUTED` | Never started because validity expired before processing. |
| `COMPLETED_LATE` | Business work completed, but after the deadline. |
| `FAILED_RETRY_EXHAUSTED` | Exhausted retry budget or attempt cap. |
| `CANCELLED` | Cancelled by an authorized actor. |
| `NEEDS_RECONCILIATION` | Uncertain whether side effects occurred during timeout/network failure. |

Never funnel all expired messages into an infinite HIGH retry queue. Doing so increases starvation, backlog, and deadline misses for still-valid work.

## 18. Gateway Timeout Does Not Automatically Cancel Workers

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Worker
    participant DB
    Client->>Gateway: Request(eventId, deadline=T)
    Gateway->>Worker: Dispatch async
    Note over Gateway: Reply timeout
    Gateway-->>Client: Timeout
    Worker->>DB: Business COMMIT after T
    Note over Client,DB: Timeout does not automatically roll back commit
~~~

This scenario can create duplicate side effects if the client retries with a new event ID. For safe design:

1. Use a stable **idempotency key** for the same business request.
2. Provide a status lookup API when clients time out.
3. If cancellation is supported, record cancel intent and have workers check it before irreversible side effects.
4. If emails, external APIs, or payment commits already fired, plan compensation.
5. Clarify whether the deadline governs start, commit, or reply delivery.

Thread interruption or a Gateway timeout cannot undo a side effect already committed on another resource.

## 19. The Window Between Deadline Check and Commit

~~~text
09:59:59.900 -> DeadlineGate: 100 ms remaining
09:59:59.950 -> start transaction
10:00:00.100 -> update database
10:00:00.300 -> COMMIT

Deadline = 10:00:00
~~~

The gate passed before the deadline, yet the outcome **committed after the deadline**. If the business forbids confirmation past the cutoff:

- Check domain state and deadlines as close as possible to critical side effects.
- Use **atomic** conditional updates in storage to reduce races.
- Check affected row counts and distinguish expired, already processed, and not found.
- Never treat an on-time SQL statement as guaranteeing **transaction commit** before the deadline if commit happens afterward.
- Record actual `completedAt` per your published definition.

PostgreSQL/JDBC example:

~~~sql
UPDATE reservations
   SET state = 'CONFIRMED'
 WHERE reservation_id = ?
   AND state = 'PENDING'
   AND expires_at > CURRENT_TIMESTAMP;
~~~

If 0 rows are updated, inspect actual state rather than blindly retrying. Database and application clocks can differ; for strict financial transactions, decide **which system is the authoritative clock**.

## 20. Priority Starvation, Fairness, and Capacity

When distant-deadline HIGH work continuously occupies workers, near-deadline LOW tasks can miss deadlines. When a flood of LOW tasks self-declare early deadlines, EDF can stall HIGH progress. Therefore combine:

- Priority classified by trusted policy.
- Deadlines granted strictly within authorized limits.
- Fair scheduling / weighted quotas when all classes must progress.
- Bounded deadline overrides.
- Reserved capacity or bulkheads for critical branches.
- Backpressure and admission control when capacity is insufficient.

**No algorithm can meet an impossible deadline.** With 100 tasks taking 10 worker-seconds each, a single worker cannot finish all of them in 60 seconds—whether using EDF, LST, or strict priority. You must add workers, shed/throttle load, or renegotiate deadlines.

### Fairness Differs from Bounded Backlog

A 4:2:1 scheduler grants LOW one-seventh of **selection turns** when all three queues stay backlogged. If LOW arrives faster than one-seventh of processing capacity over long periods, LOW's backlog still grows and deadlines keep missing. Measure processing cost and capacity, not just selection counts.

## 21. Testing Priority and Deadline Scenarios

| Scenario | What to assert | What not to assume |
| --- | --- | --- |
| HIGH distant deadline, LOW near deadline | Deadline-override policy picks LOW when configured. | Strict `PriorityChannel` does this automatically. |
| Equal deadlines, different priorities | Tie-breaker uses priority. | FIFO without a comparator tie-breaker. |
| LOW already picked up, HIGH arrives later | Running handler is not preempted. | HIGH always finishes first in every case. |
| Already expired task | Explicit expired outcome and audit trail. | Filtering it out is complete handling. |
| Negative slack | Metric/decision reflects unfeasibility risk. | Estimates are always exact. |
| Gateway reply timeout | Worker may still finish; outcome must reconcile. | Client timeout rolls back the DB automatically. |
| Splitter with one late child | Aggregator timeout/partial/compensation per policy. | Correlation merges transactions across workers. |
| Retry backoff exceeds budget | Retries halt per expiration policy. | Retries automatically extend deadlines. |
| Broker TTL expires | Broker expiration behaves per config. | TTL equals business completion deadline. |
| Clock skew across nodes | Standardized timestamps and skew monitoring. | Local time strings mean the same thing everywhere. |
| Continuous HIGH, near-deadline LOW | Deadline override/fairness tested with HIGH constantly backlogged. | Testing with an empty HIGH queue is enough. |
| Sustained overload | Admission control, scaling, or deadline-miss state. | EDF guarantees every job finishes on time. |

### Testing Without Long Sleeps

Use `Clock.fixed` / `Clock.offset` in unit tests. For thread concurrency, use `CountDownLatch` and bounded awaits to control task availability. Selector unit tests do not prove ACKs, redelivery, or crash recovery; run integration tests against real brokers/JDBC stores whenever required for production.

## 22. Operational Observability: Measuring Two Orthogonal Axes

A trace might contain:

~~~text
eventId = E-17
correlationId = ORDER-17
priorityAssigned = 1
deadlineAt = 2026-11-21T10:00:00Z
enqueuedAt = 2026-11-21T09:59:45Z
startedAt = 2026-11-21T09:59:55Z
completedAt = 2026-11-21T10:00:03Z
outcome = COMPLETED_LATE
latenessSeconds = 3
~~~

| Metric | What it measures |
| --- | --- |
| `queue_wait_seconds{class}` | Delay before handler begins. |
| `end_to_end_latency_seconds{type}` | From business creation to final outcome. |
| `deadline_miss_total{type,class}` | Tasks missing domain-defined deadlines. |
| `remaining_budget_at_start_seconds{type}` | Remaining time when processing starts. |
| `negative_slack_total{type}` | Tasks accepted already estimated unfeasible. |
| `completed_late_total{type}` | Tasks that completed past deadline. |
| `expired_without_execution_total{type}` | Tasks marked expired before execution. |
| `oldest_pending_age_seconds{class}` | Detects starvation and stale backlogs. |
| `retry_total{type,reason}` | How retries consume deadline budget. |
| `timeout_total{endpoint}` | Technical timeouts, distinct from business misses. |

**Illustrative alerts:**

~~~text
IF deadline_miss_rate > agreed_SLO:
    alert("Business deadline SLO missed")

IF LOW_pending > 0 AND LOW_completed_last_60s == 0:
    alert("Possible LOW starvation")

IF remaining_budget_p10 < processing_time_p90:
    alert("Queued work may not meet deadlines")
~~~

Never put a unique `eventId` into high-cardinality metric labels; use controlled traces/logs for ID lookup. Avoid logging sensitive payloads unnecessarily.

## 23. Common Anti-Patterns

| Anti-pattern | Why it is wrong | Better approach |
| --- | --- | --- |
| Setting `priority=9` assuming it creates a deadline. | Priority is only relative ordering. | Store deadlines separately and define completion checkpoints. |
| Setting `deadlineAt` expecting default `PriorityChannel` to read it. | Channel ignores custom deadline headers. | Use an EDF comparator or deadline-aware scheduler. |
| Treating broker TTL as a completion SLA. | Broker expiration differs from business commit. | Separate TTL/expiration from business deadlines. |
| Treating Gateway timeout as worker cancellation. | Async workers may keep running. | Idempotency, cancel contracts, and status APIs. |
| Recomputing `now+30s` on every retry. | Extends deadlines endlessly. | Preserve the original absolute deadline. |
| Clock-reading comparator expecting heap auto-reordering. | Heaps do not re-sort all elements continuously. | Explicit promotion/re-selection logic. |
| Filtering out expired messages without recording state. | No audit trail or business outcome. | Mark EXPIRED/reconcile/quarantine per policy. |
| Checking deadline before handler and claiming on-time commit. | Handler execution can overrun deadline. | Check storage state and measure actual completion. |
| Letting clients set ultra-tight deadlines freely. | Resource abuse and deadline gaming. | Authz, quotas, and deadline bounds. |
| Assuming EDF always meets every deadline. | Overload and inaccurate estimates still miss. | Feasibility checks, scaling, and backpressure. |
| Splitter extending child deadlines independently. | Breaches parent end-to-end deadline. | Partition budgets from the parent deadline. |
| Using deadline as a deduplication key. | Multiple events share deadlines, and retries alter timing. | Dedicated stable `eventId`. |

## 24. Practice Exercises

**Exercise 1 — Strict priority vs. EDF.** Create a default `PriorityChannel` with A(HIGH, deadline in 30m) and B(LOW, deadline in 20s). Test order when both are enqueued, then switch to an EDF comparator; explain the difference.

**Exercise 2 — Least slack.** Give A 15s remaining and 1s duration; give B 18s remaining and 17s duration. Compute slack and LST selection. Analyze what happens if estimates are off by 50%.

**Exercise 3 — Deadline override.** Use `DeadlineAwareSelector` with three distant-deadline HIGH tasks, one near-deadline LOW, and two NORMAL tasks. Test both with and without urgent tasks. Add handling for expired tasks.

**Exercise 4 — Metadata propagation.** Gateway → Transformer → Router → PriorityChannel → Service Activator. Verify `priority`, `deadlineAt`, and `businessEventId` at every hop. Intentionally build a Transformer that drops the deadline and write a test catching it.

**Exercise 5 — Splitter/Aggregator.** Parent deadline 10:00:00, three branches (inventory/payment/fraud). Allocate budgets per branch and Aggregator, simulate one late branch, and design partial results, cancellations, and compensation.

**Exercise 6 — Retries.** 5s deadline remaining, 4s backoff, 2s estimated attempt. Verify `canRetry` returns false. Distinguish transient-error retries from expired outcomes.

**Exercise 7 — Broker TTL.** Publish a message with a 40s business deadline and a 10s broker TTL. Inspect the outcome and explain why TTL must not serve as a completion deadline.

**Exercise 8 — Completion and timeouts.** A worker runs LOW for 30s while HIGH arrives midway; the Gateway times out before DB commit. Identify what completed, what did not, and how clients can retry safely.

**Exercise 9 — Overload.** One worker, 100 tasks × 10s CPU each, 60s deadline. Propose admission control, scaling, or deadline negotiation; never pretend an algorithm can achieve the mathematically impossible.

### Self-Assessment Questions

**1. Is priority equivalent to a deadline?** No. Priority is relative importance; a deadline is a time constraint.

**2. Does `PriorityChannel` read a custom `deadlineAt` automatically?** Not in its default priority configuration.

**3. Does EDF guarantee all deadlines under heavy load?** No; feasibility, worker capacity, durations, failures, and network delays still govern outcomes.

**4. Does broker TTL mean business work completed before the deadline?** No. TTL applies to the message/resource.

**5. Why send absolute deadlines across services?** Because a one-time remaining duration does not shrink automatically while messages wait in brokers or transit.

**6. Is checking the deadline before the handler sufficient?** No; execution and commit can still finish past the deadline.

**7. Does Aggregator automatically roll back committed sibling branches when one child expires?** No; explicit policies and compensation are required where appropriate.

**8. When should a LOW task be picked ahead of HIGH?** When business policy permits deadline override and LOW is about to expire while HIGH still has spare slack.

## 25. Pre-Production Checklist

- [ ] Separately defined priority, deadline, TTL/expiration, timeout, and scheduled time.
- [ ] Clarified whether deadlines govern **start**, **commit**, or **end-to-end completion**.
- [ ] Used absolute UTC deadlines; never reset on retry/redelivery.
- [ ] Validated authority to set priority and deadlines at ingress; enforced per-tenant quotas.
- [ ] Preserved `eventId`, `correlationId`, `deadlineAt`, and `originalEnqueuedAt` across EIPs/adapters.
- [ ] Explicitly chose strict priority, EDF, LST, deadline override, WRR, or reserved capacity.
- [ ] When using heap comparators, avoided depending on a changing clock without re-evaluation.
- [ ] Implemented business-specific expired outcomes; zero silent drops.
- [ ] Checked feasibility via remaining budget and estimated duration.
- [ ] Guarded post-deadline side effects at critical business/storage boundaries.
- [ ] Budgeted deadlines across Splitter children, Aggregator, and Gateways.
- [ ] Tested Gateway timeouts with still-running workers; established idempotency/cancellation contracts.
- [ ] Bounded retries, factored backoff into deadlines, and implemented DLQ/reconciliation.
- [ ] For JMS/RabbitMQ/Kafka, verified priority properties, TTL/retention, and business deadlines **separately**.
- [ ] Used durable sources, ACK/redelivery, and idempotent consumers for critical messages.
- [ ] Added unit tests with `Clock.fixed` plus integration tests for concurrency, crashes, and overload.
- [ ] Monitored completion latency, deadline misses, negative slack, backlogs, and starvation.
- [ ] Added admission control or capacity scaling whenever load exceeds service capacity.

**Key takeaway:** **Priority decides who gets picked first; deadline decides when the result is due.** `PriorityChannel` orders waiting messages, yet it is not an on-time delivery engine. In Spring Integration, combine explicit deadline contracts, deliberate scheduling policies, expired handling, transactions/ACKs, deadline-budgeted retries, idempotency, and measurements of **when business work truly completes**.

### References to Verify Against Your Version

- Spring Integration Reference: Message Channels, `PriorityChannel`, Polling Consumer, and Delayer.
- Spring Integration Reference: Gateway, Transformer, Router, Splitter, Aggregator, and Error Handling.
- Spring Framework Reference: Transaction Management, Timeouts, and Scheduling.
- JMS Specification: Message Priority, TTL/Expiration.
- RabbitMQ Documentation: Priority Queues, TTL, Dead Lettering, Prefetch.
- Apache Kafka Documentation: Record Headers, Partition Ordering, Offsets, and Retention.

*Java snippets are partial examples illustrating design and testing; when integrating into a project, add proper classes/imports, wire adapters, and test against your actual Spring Integration version. Content QA, Gradle builds, or other STEPs were not run per Worker guidelines.*
