# Release Once When Enough Signals Arrive

## 1. Problem: Multiple Branches Complete, Yet the Gate May Only Open Once

In the **SPRING_INTEGRATION_PATTERN** module, we use Spring Integration to implement Enterprise Integration Patterns for building loosely coupled and extensible message flows. A Gateway receives commands, a Router separates business decisions, a Filter validates data, and a Transformer reshapes payloads; results are sent over channels to different handlers. When multiple parallel processes run, a downstream step may need to wait for **sufficient signals** before executing.

For example, an order may only transition to **READY_TO_SHIP** once all three exist:

1. **PAYMENT_AUTHORIZED** — payment is confirmed.
2. **STOCK_RESERVED** — inventory has been reserved successfully.
3. **FRAUD_APPROVED** — risk checks have approved the order.

These three events may arrive **out of order**, from different Service Activators, over separate channels, and may be redelivered due to retries. The requirement is not merely "receiving three calls," but rather:

- Each order is evaluated under its exact **correlation key**.
- Only **valid, distinct signal types belonging to the same processing attempt** count.
- Once conditions are met, emit **a single release decision** for that order.
- Duplicate, late, or concurrent signals **do not trigger additional releases**.
- If the wait deadline expires, there is an explicit timeout/error path instead of holding the group forever.

This is the **Barrier** problem: allowing work past a synchronization point only when conditions are met. For "sufficient signals" requirements, we typically use an **Aggregator or a stateful coordinator** to collect conditions, then emit **one release trigger** to the barrier. Do not assume a built-in Barrier handler automatically counts arbitrary N-of-M business signals on its own.

~~~mermaid
flowchart TD
    A[Gateway: Create order] --> B[WAITING: order-101]
    C[PAYMENT_AUTHORIZED] --> D[Correlate + Deduplicate]
    E[STOCK_RESERVED] --> D
    F[FRAUD_APPROVED] --> D
    D --> G{All 3 signal types received?}
    G -->|Not yet| H[Stay WAITING]
    G -->|Yes| I{Not released and not timed out?}
    I -->|Yes| J[Transition state to RELEASED]
    J --> K[Emit one ReleaseCommand]
    I -->|No| L[Ignore duplicate / handle late event]
    K --> M[Ship flow]
~~~

**Release once** refers to **the gate-opening decision per barrier instance**. It does not mean messages are delivered exactly once over the network, or that downstream tasks execute exactly once without idempotency.

## 2. Defining "Sufficient Signals" Correctly

Two policy types must be distinguished:

| Policy | Example | Calculation |
| --- | --- | --- |
| **All-of** | Requires payment, stock, **and** risk | The signal set must contain all three required types |
| **Quorum / K-of-N** | Requires 2 of 3 independent confirmation sources | Count **distinct valid sources**, not duplicate messages |

In the order example, the condition is:

~~~text
required = {PAYMENT_AUTHORIZED, STOCK_RESERVED, FRAUD_APPROVED}
received = set of valid signal types belonging to the same barrierId
ready    = received contains all of required
~~~

If **PAYMENT_AUTHORIZED** arrives three times, we still have only **one signal type** and must not release. If **PAYMENT_AUTHORIZED**, **STOCK_RESERVED**, and **FRAUD_REJECTED** arrive, we must not release either: a rejection signal is different from an approval.

A signal should carry at least:

| Field | Purpose |
| --- | --- |
| **barrierId / correlationId** | Selects the exact waiting group |
| **signalType** | Identifies which business condition was satisfied |
| **eventId** | Detects duplicate deliveries of the same event |
| **workflowAttempt / version** | Prevents mixing signals from an old attempt with a new one |
| **occurredAt** | Supports deadline checks, auditing, and late-event handling |
| **authenticated tenant context** | Prevents mixing signals between two different tenants |

The correlation key should be **tenant + order + workflow attempt** or a unique gate identifier issued at ingress, not merely an order ID that might be reused.

## 3. A State Machine with Terminal States

A barrier must distinguish **waiting**, **released**, and **expired**.

~~~mermaid
stateDiagram-v2
    [*] --> WAITING
    WAITING --> WAITING: New signal, not sufficient yet
    WAITING --> WAITING: Duplicate signal, ignored
    WAITING --> RELEASED: Sufficient signals, atomic transition
    WAITING --> EXPIRED: Wait deadline exceeded
    RELEASED --> RELEASED: Duplicate or late, do not re-release
    EXPIRED --> EXPIRED: Late signal, do not open gate
~~~

| State | New signal | Emit release? |
| --- | --- | --- |
| **WAITING**, incomplete | Store unseen valid signal | No |
| **WAITING**, complete | Transition to RELEASED **once** | Only the caller winning the state transition |
| **RELEASED** | Duplicate or late | No |
| **EXPIRED** | Late signal | No; handle per late-event policy |
| **CANCELLED** (if business defines it) | Order cancelled before conditions met | No |

To prevent one thread reporting sufficient signals and another reporting timeout from both winning, both must compete on **one shared state** via compare-and-set or a transaction. Only one of the transitions **WAITING → RELEASED** and **WAITING → EXPIRED** may succeed.

The RELEASED state must also be retained long enough so replayed messages do not reopen the barrier. If state is deleted immediately after emitting the release and an old message returns, a new group could accidentally be created and released a second time.

## 4. A Barrier Is Neither CountDownLatch Nor Aggregator

Mechanisms that are easily confused:

| Mechanism | Role | Limitations to remember |
| --- | --- | --- |
| **Barrier EIP** | Blocks a request until a correlated gate-opening signal arrives | Does not natively understand three business signal types |
| **Aggregator EIP** | Collects multiple messages by correlation and release strategy | Requires exact completion, timeout, and duplicate handling |
| **Java CountDownLatch / CyclicBarrier** | Synchronizes threads inside a single process | Does not persist messages; unsuitable for guaranteeing distributed workflows |
| **Stateful coordinator** | Tracks signal set, decides release once | Requires atomicity, lifecycle management, durability, and cleanup |
| **Durable outbox** | Records release event for reliable post-commit dispatch | Consumers still need idempotency because delivery can repeat |

A **Spring Integration Barrier** is typically viewed as a point holding one request until a corresponding trigger arrives. If **three distinct events** are required before triggering, place an **Aggregator/coordinator ahead of the trigger channel**. A signal arriving on the trigger channel only means release when that signal itself already represents **all conditions met**, rather than allowing every sub-signal to open the barrier.

~~~mermaid
flowchart LR
    R[Waiting request] --> B[Barrier: order-101]
    S1[Payment signal] --> A[Aggregator / Coordinator]
    S2[Stock signal] --> A
    S3[Risk signal] --> A
    A -->|Conditions met, one trigger| T[Release trigger]
    T --> B
    B --> O[Request continues processing]
~~~

If the system must hold a waiting thread, timeouts and concurrency must be bounded. For high order volumes or long waits, prefer **asynchronous coordination with durable state** rather than holding thousands of threads in an in-memory barrier.

## 5. Race Conditions That Cause Duplicate Releases

Consider three workers receiving three signals nearly simultaneously. An unsafe implementation:

~~~java
// ANTI-PATTERN: non-atomic read-check-write.
State state = repository.load(barrierId);
state.add(signal);

if (state.hasAllRequired() && !state.isReleased()) {
    sendRelease(barrierId);
    state.setReleased(true);
}
repository.save(state);
~~~

Two workers can both read **released = false**, both see all signals present, and both send a release. Even though the database eventually stores released = true, the side effect **already happened twice**.

A safer approach is:

1. Receive and deduplicate the signal by eventId or business constraint.
2. Update the signal set using an operation synchronized by barrierId.
3. If the set is complete, attempt to transition **WAITING → RELEASED** with an **atomic** operation.
4. **Only the winning process** may create the release decision.
5. To survive crashes between writing state and sending the message, write an **outbox** record in the same transaction.
6. The consumer uses an **idempotency key** so side effects are not executed twice when the broker redelivers the outbox event.

Do not place REST calls, broker publishes, or separate business commits **inside a long compute/lock function**; lock-holding sections should be short and deterministic. Emitting events outside a transaction without an outbox leaves a crash window that can lose the release.

## 6. Java: Single-JVM Coordinator Illustrating One-Shot Decisions

The code below only illustrates **one release decision per key within a single process**. It is useful for learning atomic state transitions, but it is **not** a complete production solution because it does not survive restarts, lacks durable timeouts, and does not guarantee delivery on its own.

### 6.1. Message Contract

~~~java
public enum SignalKind {
    PAYMENT_AUTHORIZED,
    STOCK_RESERVED,
    FRAUD_APPROVED
}

public record BarrierSignal(
        String barrierId,
        String eventId,
        SignalKind kind
) {}

public record ReleaseCommand(
        String barrierId,
        String releaseKey
) {}

public record GateState(
        Set<SignalKind> received,
        boolean released
) {}
~~~

This example treats **each signal kind as one boolean condition**. Duplicate events of the same kind do not increase the count of completed conditions. If multiple sources of the same kind must be counted independently, the dedup key must include **sourceId** or another identifier per the contract.

### 6.2. Atomic State Transition Per barrierId

~~~java
@Component
public class BarrierCoordinator {

    private static final Set<SignalKind> REQUIRED = Set.of(
            SignalKind.PAYMENT_AUTHORIZED,
            SignalKind.STOCK_RESERVED,
            SignalKind.FRAUD_APPROVED
    );

    private final ConcurrentHashMap<String, GateState> states =
            new ConcurrentHashMap<>();

    /**
     * Returns null if incomplete or if the barrier is already RELEASED.
     * Only one thread can receive a ReleaseCommand for a given barrierId.
     */
    public ReleaseCommand onSignal(BarrierSignal signal) {
        AtomicReference<ReleaseCommand> firstRelease =
                new AtomicReference<>();

        states.compute(signal.barrierId(), (id, previous) -> {
            if (previous != null && previous.released()) {
                return previous;
            }

            EnumSet<SignalKind> received =
                    EnumSet.noneOf(SignalKind.class);

            if (previous != null) {
                received.addAll(previous.received());
            }
            received.add(signal.kind());

            boolean ready = received.containsAll(REQUIRED);

            if (ready) {
                firstRelease.set(
                        new ReleaseCommand(id, "release:" + id)
                );
            }

            return new GateState(Set.copyOf(received), ready);
        });

        return firstRelease.get();
    }
}
~~~

**Why does this code decide release only once?** For a given key, **ConcurrentHashMap.compute** serializes updates to the entry. The first thread that observes all signals flips released to true and receives the ReleaseCommand. Subsequent threads see released = true and return the existing state without creating a new command.

In this example **eventId** is present on the event but not yet used for separate deduplication. The rule that each kind counts once is already enforced by the Set. When business rules allow multiple signals per kind or require eventId auditing, add eventId set tracking or a durable unique constraint.

**Critical limitations:**

- State lives only in RAM; a restart erases release history.
- No deadline, EXPIRED, or CANCELLED handling; production must add these.
- The map grows with the number of barrierIds and lacks lifecycle cleanup. Deleting entries too early risks late events triggering a duplicate release.
- If the release command is created but the application crashes before sending it, **the release command may be lost**.
- If sent to a broker and processed by a consumer and the message is redelivered, **side effects can still repeat**.

Thus, this example demonstrates **at-most-once release decision within a live JVM**, without promising exactly-once delivery or exactly-once business execution.

## 7. Wiring the Coordinator into Spring Integration Java DSL

Spring Integration can receive signals from various adapters, normalize them into a **BarrierSignal** payload, and route them to the same channel.

~~~java
@Configuration
@EnableIntegration
public class BarrierFlowConfiguration {

    @Bean
    public IntegrationFlow barrierSignalFlow(
            BarrierCoordinator coordinator
    ) {
        return IntegrationFlow.from("barrier.signals")
                .handle(
                        BarrierSignal.class,
                        (signal, headers) ->
                                coordinator.onSignal(signal)
                )
                .channel("barrier.release.commands")
                .get();
    }

    @Bean
    public IntegrationFlow barrierReleaseFlow(
            ReleasePort releasePort
    ) {
        return IntegrationFlow.from("barrier.release.commands")
                .handle(
                        ReleaseCommand.class,
                        (command, headers) -> {
                            releasePort.deliver(command);
                            return null;
                        }
                )
                .get();
    }
}

public interface ReleasePort {
    void deliver(ReleaseCommand command);
}
~~~

In this flow:

- **barrier.signals** receives validated and normalized **BarrierSignal** messages.
- **BarrierCoordinator.onSignal** returns **null** when conditions are incomplete or already released. For a Service Activator, a null return means there is no reply message to forward.
- The first time all conditions are met, the handler returns **ReleaseCommand**, which is sent to **barrier.release.commands**.
- **ReleasePort** is an application abstraction to resume work or publish an event; this snippet does not create a durable consumer or storage by itself.

These interfaces/records are application examples, not built-in Spring Integration APIs. Depending on your Spring Integration version and request-reply usage, verify null-reply handler behavior in your actual flow.

**Crash risk in this example:** the coordinator may mark RELEASED in RAM, and then ReleasePort fails. A retried signal will see it is already released and **will not re-emit the command**. To guarantee delivery after failures, switch to the transaction + outbox model in the next section. Do not simply add retries to ReleasePort and assume consistency is solved.

## 8. Production: Transaction + Unique Constraint + Outbox

In a multi-pod system, an in-memory map is not a shared source of truth. You need an atomic mechanism visible to all workers, such as a database transaction with unique constraints.

A conceptual data design:

~~~text
barrier_instance(
    barrier_id PRIMARY KEY,
    tenant_id,
    workflow_attempt,
    status,          -- WAITING | RELEASED | EXPIRED | CANCELLED
    created_at,
    deadline_at,
    released_at
)

barrier_signal(
    barrier_id,
    signal_kind,
    event_id,
    occurred_at,
    UNIQUE(barrier_id, signal_kind),
    UNIQUE(barrier_id, event_id)
)

outbox(
    event_id PRIMARY KEY,  -- "release:" + barrier_id
    barrier_id,
    event_type,
    payload,
    delivery_status,
    created_at
)
~~~

The **barrier_instance record** should be created when starting the workflow (or via a reliable atomic initialization mechanism) so early signals are not lost. The UNIQUE constraints above represent identity and deduplication concepts; if the application allows multiple events of the same kind, design keys according to the actual source/scope.

### 8.1. One Transaction Deciding the Release

~~~text
BEGIN TRANSACTION

1. SELECT barrier_instance WHERE barrier_id = :id FOR UPDATE
   -> locks the row to serialize signals sharing the same barrierId.

2. If status != WAITING or deadline has passed:
   -> do not emit release; handle late/expired signal per policy.

3. INSERT barrier_signal(...), ignore on UNIQUE conflict.
   -> duplicate delivery adds no extra condition.

4. Count how many distinct required signal types have been recorded.
   If still incomplete:
   -> COMMIT and finish, do not create release.

5. If sufficient:
   UPDATE barrier_instance
      SET status = RELEASED, released_at = now()
    WHERE barrier_id = :id AND status = WAITING.
   -> proceed only if exactly one row was updated.

6. INSERT outbox(event_id = "release:" + :id, ...)
   with a unique event_id; in the same transaction.

COMMIT
~~~

This is **transactional pseudocode**, not literal SQL syntax runnable across every database engine. It expresses two invariants:

1. A barrierId can transition from **WAITING to RELEASED only once**.
2. The **RELEASED** record and the outbox release event appear in the **same commit**; there is no case where the state commits but the decision to emit the event is lost due to a pre-publish crash.

An independent **outbox publisher** dispatches undelivered events and marks outcomes per policy. If a broker ack is lost, the same outbox event may be redelivered. Therefore **the consumer must be idempotent**, for example persisting the processed releaseKey with a unique constraint before executing side effects, or passing an idempotency key upstream.

### 8.2. At-Most-Once, At-Least-Once, and Exactly-Once

| Goal | Solution and limitations |
| --- | --- |
| **One release decision** | Atomic state transition per barrierId |
| **No lost release on process crash** | Write outbox in the same transaction as the decision |
| **Deliver release to consumer despite transient failures** | At-least-once delivery with bounded retries |
| **No duplicate side effects** | Idempotent consumer / idempotency key and reconciliation |
| **End-to-end exactly-once** | Does not happen automatically from barriers, transactions, or brokers; must be verified at every boundary |

If the release command is "debit funds," idempotency criteria are even stricter: you need a contract returning the prior result on duplicate keys and a reconciliation mechanism when external outcomes are uncertain.

## 9. Timeouts and Late Events

A barrier cannot wait forever if a subsystem fails to respond. It needs a **deadline** created when the workflow starts and stored alongside the barrier instance.

Example:

| Time | Event | State |
| --- | --- | --- |
| 09:00:00 | Barrier created, deadline 09:00:30 | WAITING |
| 09:00:05 | PAYMENT_AUTHORIZED | WAITING, 1/3 |
| 09:00:11 | STOCK_RESERVED | WAITING, 2/3 |
| 09:00:30 | Timeout job transitions WAITING → EXPIRED | EXPIRED |
| 09:00:32 | FRAUD_APPROVED arrives late | **Does not** release because EXPIRED |

If the final signal and the timeout job arrive **at the same time**, both must use the same transaction / atomic compare-and-set on the WAITING state. Only one branch may win; the application must define clear time rules (for example, server-side deadline, comparing now against deadline_at) so different pods do not make conflicting decisions.

Options upon expiration:

- **Fail fast** and return **UNAVAILABLE/TIMEOUT** to the user.
- **Cancel or compensate** already completed steps, such as releasing reserved inventory if approval never arrived.
- **Partial result** if the business contract genuinely permits it.
- **Dead-letter / manual review** with correlation and signal history.

Never silently emit a release after expiration just because the final signal eventually arrived. If the business allows reopening the workflow, create a **new workflowAttempt and new barrierId**; do not reuse a gate already in a terminal state.

### 9.1. State Cleanup and Preventing Late Replay

You can prune signal details after a TTL to save storage, but keep a **tombstone/terminal marker** or idempotency record longer than the window in which duplicate deliveries can still arrive.

If you delete the entire RELEASED record and let an old signal recreate a new barrier with the same key, the application can release a second time. That is why **retention policy**, attempt identifiers, and maximum redelivery windows must be designed together.

## 10. Retry, Error Channel, and Correlation

In Spring Integration, each signal can travel through a QueueChannel, ExecutorChannel, broker adapter, or synchronous flow. You must define what happens when a handler fails.

### 10.1. Retries Must Not Double-Count Signals

If a **PAYMENT_AUTHORIZED** signal is redelivered three times by the broker due to lost ACKs, it still contributes only **one payment condition**. Never check "three messages received" when the requirement is "three distinct signal types received."

Retries must:

- Identify duplicate events via **eventId** or uniqueness of **barrierId + signalKind**.
- Enforce bounded attempts and backoff when storage/broker errors occur.
- Never re-emit a release after a terminal state.
- Preserve **barrierId, workflowAttempt, tenant context, and traceId**.
- Apply idempotency to side effects triggered by ReleaseCommand.

Redelivering a trigger in an at-least-once system is normal; **a single release decision** does not eliminate the need for consumer deduplication.

### 10.2. Error Channel Differs from Barrier Timeout

In a synchronous flow over **DirectChannel**, exceptions may propagate straight back to the Gateway caller. In an asynchronous flow, errors may route through **ErrorMessage/error channel** depending on endpoint configuration.

An **error channel** handles exceptions for a single message; a **barrier timeout** is when a group fails to receive enough signals by its deadline. You cannot simply register an error channel and assume the system will expire barriers automatically. You need a scheduler/expiry workflow or a completion timeout mechanism supported by the appropriate component.

If a signal has been persisted durably but release logic fails, the error handler must ensure retries use the **same idempotency key** instead of creating a new barrier.

### 10.3. Splitter and Aggregator Correlation

A Splitter can produce multiple child messages with **correlation ID**, **sequence number**, and **sequence size**. An Aggregator can use these headers to gather results. When using it to generate a release trigger:

1. Group strictly by **barrierId/workflowAttempt**, not merely because messages arrive close together.
2. Use strict correlation and completion strategies to verify **the exact signal types**.
3. Deduplicate before checking whether enough sources arrived.
4. Define group timeout, expired-group handling, and discard/error paths.
5. Preserve a unique release identifier when sending the trigger down to the barrier.

An Aggregator completing a group and emitting one message **does not by itself guarantee a side effect executes only once** under crashes/retries. Downstream consumers still require idempotency.

## 11. Safety with Multiple Tenants and Multiple Instances

In multi-tenant or multi-pod applications:

- **Tenant ID must be authenticated** at ingress; never trust an arbitrary external header directly.
- **BarrierId** must isolate tenant and workflow attempt; never mix signals across tenants.
- Pods must share **one common source of state** or a consumer partitioning scheme guaranteeing atomicity; a ConcurrentHashMap per pod will produce diverging release decisions.
- Transactions, unique constraints, leases/locks, and outboxes must be designed for the actual storage engine.
- Never put **order ID, detailed tenant ID, or correlation ID** into high-cardinality metric tags; use access-controlled logs/traces for investigation.
- If the barrier is a step in a transaction with side effects, propagate an **idempotency key** throughout downstream calls and provide reconciliation where needed.

Long-waiting groups also risk exhausting memory or filling the database. Enforce limits on WAITING barriers, TTLs, quotas, and backpressure.

## 12. Testing Release-Once Behavior

A good test suite must verify all of the following simultaneously:

- **Insufficient** signal types → no release.
- **Sufficient** → one release decision.
- **Duplicates** of the same signalType/eventId → no additional release.
- **Out-of-order** → same result achieved.
- **Concurrent arrival** → only one thread wins.
- **After timeout / already released** → no re-release.
- **Restart and broker redelivery** → if durability is required, no lost release and no duplicate side effects.

### 12.1. Unit Test with the In-Memory Coordinator

~~~java
@Test
void releasesOnceWhenAllDistinctSignalsArrive() {
    BarrierCoordinator coordinator = new BarrierCoordinator();
    String id = "tenant-A:order-101:attempt-1";

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-1",
                    SignalKind.PAYMENT_AUTHORIZED)));

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-2",
                    SignalKind.PAYMENT_AUTHORIZED)));

    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-3",
                    SignalKind.STOCK_RESERVED)));

    ReleaseCommand release = coordinator.onSignal(
            new BarrierSignal(id, "evt-4",
                    SignalKind.FRAUD_APPROVED));

    assertNotNull(release);
    assertEquals("release:" + id, release.releaseKey());

    // Replay after RELEASED must not trigger another release.
    assertNull(coordinator.onSignal(
            new BarrierSignal(id, "evt-4",
                    SignalKind.FRAUD_APPROVED)));
}
~~~

### 12.2. Concurrency Test with Duplicate Signals

~~~java
@Test
void concurrentSignalsProduceOnlyOneRelease() throws Exception {
    BarrierCoordinator coordinator = new BarrierCoordinator();
    String id = "tenant-A:order-102:attempt-1";

    List<BarrierSignal> events = List.of(
            new BarrierSignal(id, "p1",
                    SignalKind.PAYMENT_AUTHORIZED),
            new BarrierSignal(id, "s1",
                    SignalKind.STOCK_RESERVED),
            new BarrierSignal(id, "r1",
                    SignalKind.FRAUD_APPROVED),
            new BarrierSignal(id, "p1",
                    SignalKind.PAYMENT_AUTHORIZED),
            new BarrierSignal(id, "r1",
                    SignalKind.FRAUD_APPROVED)
    );

    ExecutorService workers = Executors.newFixedThreadPool(5);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<ReleaseCommand>> futures = new ArrayList<>();

    try {
        for (BarrierSignal event : events) {
            futures.add(workers.submit(() -> {
                start.await();
                return coordinator.onSignal(event);
            }));
        }
        start.countDown();

        int releaseDecisions = 0;
        for (Future<ReleaseCommand> future : futures) {
            if (future.get() != null) {
                releaseDecisions++;
            }
        }
        assertEquals(1, releaseDecisions);
    } finally {
        workers.shutdownNow();
    }
}
~~~

This test only checks **atomic decision-making within a single JVM**. It does not test database transactions, outboxes, or broker delivery. For multi-pod systems, add integration tests where workers genuinely race to update **the same barrierId on shared storage**, and test crashes before and after commit.

### 12.3. Production Test Matrix

| Scenario | Expectation |
| --- | --- |
| Missing one of the three signal types | WAITING, no release |
| One signal type sent multiple times | Deduplicated, no false completion |
| Three signal types arrive out of order | Exactly one release |
| Signals arrive concurrently | Single WAITING → RELEASED transition |
| Worker restarts mid-wait | State recoverable from storage |
| Crash after commit, before broker publish | Outbox still holds release event to publish |
| Broker delivers release event twice | Consumer does not execute duplicate side effects |
| Timeout and final signal race | Only one terminal branch wins |
| Signal arrives after EXPIRED | Does not auto-release; follows late-event policy |
| Signal from old workflow attempt | Does not match into new attempt |
| Signal from another tenant | Rejected, does not satisfy conditions |
| Aggregator group missing a branch | Timeout/partial/error path, never waits forever |
| Retry/error channel handles duplicate event | Preserves correlation and idempotency |
| Outbox publisher temporarily fails | Bounded retry/backoff, no lost events |

## 13. Observability and Operations

Monitor the Barrier at the **group**, **signal**, **release decision**, and **downstream outcome** levels:

| Metric/log | What do we need to know? |
| --- | --- |
| **barriers_waiting** | How many groups still lack sufficient signals? |
| **barrier_wait_age** | Which groups are nearing expiration? |
| **signals_received_by_type** | Which condition typically arrives slowly? |
| **signals_duplicate / invalid** | Are there replays, malformed data, or intentional duplicates? |
| **barrier_released_total** | How many groups have received a release decision? |
| **barrier_expired_total** | How many groups never received sufficient signals? |
| **outbox_pending / oldest_age** | Are release decisions waiting to be published? |
| **release_delivery_attempts** | Is the publisher retrying excessively? |
| **downstream_idempotent_duplicates** | Is the consumer seeing duplicate deliveries? |
| **Gateway/flow latency, Aggregator pending groups** | Is the Barrier slowing down or stalling the EIP flow? |

Logs/traces should retain **barrierId, correlationId, workflowAttempt, eventId, signalType, state transition**, and timeout cause. Never stuff individual barrierIds/orderIds into metric labels, as that creates very high cardinality. When comparing workflow categories, use stable metric tags such as **flow name**, **signal kind**, and **terminal state**.

An early warning sign requiring attention is **barriers_waiting rising steadily while barrier_released_total stays flat**. A signal source may have stopped emitting, correlation may be broken, timeouts may not be running, or events may be stuck in an error channel/DLQ.

## 14. Common Design Mistakes

1. **Counting messages instead of counting conditions:** three PAYMENT_AUTHORIZED messages do not mean payment, stock, and risk are all satisfied.
2. **Using non-atomic check-then-send:** two concurrent workers emit duplicate releases.
3. **Sending first and marking RELEASED afterward:** crashes or retries cause multiple sends.
4. **Marking RELEASED and sending without an outbox:** a crash can lose the release.
5. **Confusing one release decision with exactly-once delivery:** the broker can still redeliver the message.
6. **Deleting terminal state too early:** old events recreate the barrier and reopen it.
7. **Not handling deadlines:** WAITING persists forever and consumes resources.
8. **Using CountDownLatch to wait on thousands of workflows:** holds threads/memory and cannot survive restarts.
9. **Mixing correlation across tenants or attempts:** groups release the wrong order.
10. **Assuming Aggregator completion equals once-only side effects:** consumers still require idempotency.
11. **Not monitoring missing signal sources:** seeing only Gateway timeouts without knowing which branch never finished.
12. **Replaying write commands without idempotency:** creates duplicate orders or payments.

## 15. Spring Integration Adoption Checklist

- [ ] Clearly define all-of or quorum, the signalType list, and rejection conditions.
- [ ] Give each barrier a stable key per tenant/order/workflowAttempt.
- [ ] Validate signal sources and deduplicate by the appropriate identity.
- [ ] Transition WAITING → RELEASED only via an atomic operation.
- [ ] Resolve races between release and timeout through a single shared terminal state.
- [ ] When using Spring Integration Barrier, send the trigger only once the aggregator/coordinator confirms all conditions are met.
- [ ] When durability/multi-pod support is needed, use database transactions, unique constraints, and an outbox.
- [ ] Make the release consumer idempotent; duplicate deliveries must not cause duplicate side effects.
- [ ] Implement deadlines, late-event policies, terminal markers, and retention to prevent late replays.
- [ ] Preserve eventId, correlation ID, attempt, and original message across retries and error channels.
- [ ] Ensure Gateway, Router, Filter, Transformer, and Splitter/Aggregator have explicit partial/error paths.
- [ ] Write tests for missing signals, duplicates, arbitrary ordering, concurrency, timeout races, and crashes.
- [ ] Monitor pending groups, signal lag, expired groups, outbox backlog, and release outcomes.

**Release once when enough signals arrive** is a workflow invariant: for each valid barrierId, only one **WAITING → RELEASED** decision is allowed to succeed once conditions are satisfied. Combining Barrier with an Aggregator/coordinator, correlation, atomic state transitions, timeouts, an outbox, and idempotency enables a Spring Integration flow to resume at the right moment without losing signals or creating duplicate side effects under retries or concurrent workers.
