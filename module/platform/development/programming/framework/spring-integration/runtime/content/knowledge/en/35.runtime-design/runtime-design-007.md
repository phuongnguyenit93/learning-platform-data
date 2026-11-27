# Ensuring Lifecycle Start, Stop, and Cleanup in Spring Integration Runtime

A message flow can run fine during steady state yet drop messages during the first few seconds of **startup**, halt abruptly during **shutdown**, or leak connections/threads/pollers after **removing a dynamic IntegrationFlow**. These failures are hard to reproduce because they occur at the boundaries of <code>ApplicationContext</code>, <code>MessageChannel</code>, consumer endpoints, task executors, transactions, and message stores, rather than inside business methods.

The lesson **"Ensuring Lifecycle Start, Stop, and Cleanup"** belongs to the **Runtime Design** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will design lifecycles from flow creation, dependency-ordered startup, ingress blocking, draining in-flight work, stopping endpoints, resource cleanup, and post-restart recovery—while examining the impact of retries, correlation, error handling, pollers, threading, and performance.

> **Principle:** <code>start()</code> does not mean **ready to receive all messages**; <code>stop()</code> does not mean **in-flight work has drained**; and <code>destroy()</code> does not mean **persistent state has been deleted or external side effects have been cancelled**. Applications must explicitly define and test each post-condition.

## 1. Lifecycle Is a Contract, Not Just Three Methods

Spring Integration lifecycles involve **several distinct objects**:

| Object | Role | What Must Be Guaranteed |
|---|---|---|
| <code>IntegrationFlow</code> | Wires message sources, channels, endpoints, and handlers | Registered once; dependencies ready before accepting traffic |
| <code>MessageChannel</code> | Dispatches messages synchronously, asynchronously, or via queue | Producers know what accepted means; queues have bounds and recovery policies |
| <code>EventDrivenConsumer</code> | Subscribes handler to <code>SubscribableChannel</code> | Subscribes on start; stops receiving new messages on stop per endpoint semantics |
| <code>PollingConsumer</code> | Polls <code>PollableChannel</code> by trigger | Trigger/start state, messages per poll, in-flight execution, and transactions |
| <code>SourcePollingChannelAdapter</code> | Actively polls <code>MessageSource</code> | Does not poll before dependencies/downstreams are ready |
| <code>TaskExecutor</code>/<code>TaskScheduler</code> | Coordinates workers or scheduled tasks | Does not shut down before producers stop; refuses tasks after cutoff |
| <code>MessageStore</code> | Stores messages, groups, delays, or metadata | Restarts preserve required data; cleanup honors retention |
| Broker/HTTP/TCP adapters | Connects external sources/sinks | ACK, retries, redelivery, closing sessions, and draining per adapter API |
| <code>IntegrationFlowContext</code> | Registers/unregisters flows at runtime | Registrations carry stable IDs and clear ownership |

Calling <code>stop()</code> only halts the lifecycle aspect of the target object. If a handler already sent an HTTP request, a DB transaction is mid-commit, or an executor already accepted a <code>Runnable</code>, a separate **completion-tracking mechanism** is needed. Conversely, a <code>QueueChannel</code> can still hold messages after its polling consumer stops; stopping the poller does not empty the queue.

### From a Business Perspective: Five Milestones to Measure

1. **Accepted:** source or channel accepted the message/task.
2. **Started:** handler or consumer began processing.
3. **Completed:** task satisfied business post-conditions (potentially including commit/ACK).
4. **Recovered:** failure was retried/DLQed/quarantined per policy.
5. **Released:** runtime removed registrations and resources owned by the flow.

Never equate step 1 with step 3. With <code>DirectChannel</code>, synchronous handlers normally run on <code>send()</code>'s call stack. With <code>ExecutorChannel</code>, <code>send()</code> may return immediately once the task is handed to the executor. With <code>QueueChannel</code>, success may only mean the message was enqueued.

## 2. Proposed State Machine for Runtime Flows

Spring Integration does not provide the complete state machine below out of the box. It is an **application-designed coordination contract** so multiple endpoints and external sources follow one protocol.

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> REGISTERED: declare bean / register dynamic flow
    REGISTERED --> STARTING: start dependencies and endpoints
    STARTING --> READY: health/consumer/route conditions met
    READY --> QUIESCING: close admission
    QUIESCING --> DRAINING: no new work accepted
    DRAINING --> STOPPING: in-flight = 0 or moved to durable recovery
    STOPPING --> STOPPED: stop endpoints, adapters, schedulers per ownership
    STOPPED --> CLEANING: destroy owned flow / close owned resources
    CLEANING --> DESTROYED: post-conditions met
    STARTING --> FAILED: start failure
    DRAINING --> FAILED: timeout / data not yet safeguarded
    STOPPING --> FAILED: stop failure
    CLEANING --> FAILED: cleanup failure
    FAILED --> QUIESCING: retry with checkpoint
    STOPPED --> STARTING: resume if still permitted
~~~

Three points to emphasize:

- <code>READY</code> is announced **only after** processing paths and dependencies are ready; bean creation is insufficient.
- <code>DRAINING</code> requires a guaranteed **ingress cutoff point**. If producers keep sending forever, waiting for pending count to reach 0 may never terminate.
- <code>DESTROYED</code> is not a built-in state exposed via a getter on <code>IntegrationFlowRegistration</code>; the application may need its own checkpoint record.

### Start and Stop Workflows Are Asymmetric Mirror Images

~~~mermaid
flowchart LR
    A["START"] --> B["Create/verify dependencies"]
    B --> C["Register + start consumer/handler"]
    C --> D["Ready checks"]
    D --> E["Open admission / ingress"]
    E --> F["RUNNING"]
    F --> G["Close admission / ingress"]
    G --> H["Drain / settle pending"]
    H --> I["Stop endpoint / adapter"]
    I --> J["Destroy owned flow/resources"]
    J --> K["STOPPED / CLEAN"]
~~~

Never invert the order by **opening ingress before consumers are ready** or **shutting down executors before consumers stop submitting tasks**. Specifics vary by system, yet these two invariants must always be verified.

## 3. Spring Lifecycle, SmartLifecycle, and Phases

Spring Framework provides <code>Lifecycle</code> and <code>SmartLifecycle</code>. Many Spring Integration endpoints implement these interfaces to auto-start/stop alongside <code>ApplicationContext</code>.

| API | Operational Meaning |
|---|---|
| <code>start()</code> | Begins component operation; may subscribe or schedule polling |
| <code>stop()</code> | Requests halt per implementing class contract |
| <code>isRunning()</code> | Snapshot of lifecycle state, **not in-flight count** |
| <code>SmartLifecycle.isAutoStartup()</code> | Whether it participates in automatic startup on context initialization |
| <code>SmartLifecycle.getPhase()</code> | Relative ordering during start/stop |
| <code>SmartLifecycle.stop(Runnable callback)</code> | Async stop API; component must invoke callback once stop finishes |

Among <code>SmartLifecycle</code> beans **managed by the same lifecycle processor**, **lower phases start first and stop last**; higher phases start last and stop first. A typical layout:

~~~text
START:
  downstream/resources ready → worker consumer → inbound producer

STOP:
  inbound producer → worker consumer → downstream/resources
~~~

However, phase configuration does not mean every adapter follows that order in the exact way you assume; <code>depends-on</code> wiring, beans not implementing <code>SmartLifecycle</code>, dynamic registrations, or work outside the Spring context may interfere. Inspect **actual beans**, actual phases, and lifecycle logs.

Example endpoint inspection:

~~~java
SmartLifecycle worker =
    context.getBean("orders.worker", SmartLifecycle.class);

log.info("endpoint={}, autoStartup={}, running={}, phase={}",
    "orders.worker",
    worker.isAutoStartup(),
    worker.isRunning(),
    worker.getPhase());
~~~

<code>SmartLifecycle</code> lives in <code>org.springframework.context</code>. The name <code>orders.worker</code> must be the **endpoint bean ID**, not an arbitrary <code>OrderService</code> bean name.

**Counterexample:** A handler reports <code>isRunning() == false</code> while a task already submitted to an executor is still executing. That is not necessarily a framework bug—lifecycle state and in-flight tasks measure two different things.

## 4. Standardizing READY Criteria Before Accepting Traffic

An application should not advertise readiness the instant its HTTP server opens a socket. For critical flows, readiness should require:

- configuration/secrets loaded and flow beans registered;
- message channels and consumer endpoints started as designed;
- pollers or listener containers able to receive (not paused for maintenance);
- critical DB/brokers/downstreams passing health contracts;
- required error channels, DLQs/recovery sinks, or outboxes ready;
- business state not in <code>DELETING</code>, <code>MAINTENANCE</code>, or shutdown;
- external admission remains closed until all of the above hold.

Readiness does not require "every dependency in the world to be flawless" if valid degraded modes exist. Yet it must accurately reflect **the processing capability that readiness promises**.

### Ingress Differs from Consumers

| Component | Can Start Earlier? | Why? |
|---|---|---|
| Output channels, handlers, recovery sinks | Usually yes | Prepares destinations and error paths |
| Internal queue polling consumers | Usually yes, once dependencies are ready | Helps drain existing backlog if needed |
| External inbound adapters, HTTP admission, broker listeners | Open only when ready | Prevents accepting messages without consumers or durable storage |
| Metrics/tracing | Should start early | Observes startup and shutdown failures |

If the source is a broker supporting retries/redelivery, **pausing or deferring listener startup** keeps messages safely on the broker until the app is ready. Exact ACK, offset, and pause capabilities depend on the specific adapter, never inferred from <code>MessageChannel</code>.

## 5. Java DSL Example: Queue, Poller, and Non-Auto-Start Endpoint

The self-contained example below illustrates a single-JVM flow using a bounded <code>QueueChannel</code>. The input is an internal channel; HTTP/broker receivers call an admission gate shown in the next section.

~~~java
public record OrderCommand(String eventId, String orderId, int quantity) {}

public class OrderProcessor {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        // Example: write to DB keyed by eventId with unique constraint/idempotency.
        // Illustrative business code; does not assume a DB exists in this test.
    }
}
~~~

~~~java
@Configuration
@EnableIntegration
public class OrderRuntimeConfig {

    @Bean(name = "orders.pending")
    QueueChannel ordersPending() {
        return new QueueChannel(256);
    }

    @Bean
    OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    IntegrationFlow orderWorkerFlow(OrderProcessor processor) {
        return IntegrationFlow.from("orders.pending")
            .handle(processor, "process", endpoint -> endpoint
                .id("orders.worker")
                .autoStartup(false)
                .poller(Pollers.fixedDelay(200)
                    .maxMessagesPerPoll(10)
                    .receiveTimeout(0)))
            .get();
    }
}
~~~

Key types: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.Pollers</code>, <code>org.springframework.integration.channel.QueueChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, along with Spring's <code>@Configuration</code>/<code>@Bean</code>.

Here:

- <code>orders.pending</code> holds up to 256 **messages**; enqueue success alone does not perform business processing.
- Because input is a <code>PollableChannel</code>, the endpoint requires a poller calling <code>receive()</code>.
- <code>autoStartup(false)</code> configures **endpoint** <code>orders.worker</code>, keeping the consumer idle until the application calls <code>start()</code>.
- <code>maxMessagesPerPoll(10)</code> bounds each poll cycle; it does not guarantee processing 10 messages every 200 ms.
- While the endpoint is not started, senders can still push messages into the queue. Hence you need an **admission gate** to prevent traffic before readiness.

This example uses no persistent store: on a JVM crash, messages remaining in the in-memory queue are lost. Never ship this pattern to production assuming "shutdown will preserve the queue" without an upstream replay contract or a persistent channel store.

## 6. Admission Gate: Blocking New Messages Without Losing the Race with Stop

Code like:

~~~java
if (ready.get()) {
    inputChannel.send(message);
}
~~~

is **insufficient** to guarantee "no sends after cutoff": thread A can read <code>ready=true</code>, thread B closes the gate and stops the consumer, and then thread A executes <code>send()</code>.

The example below uses a <code>ReentrantReadWriteLock</code> to **serialize the cutoff with all submit calls passing through the gate**:

~~~java
public final class OrderAdmissionGate {
    private final MessageChannel input;
    private final ReadWriteLock lock = new ReentrantReadWriteLock(true);
    private boolean accepting;

    public OrderAdmissionGate(MessageChannel input) {
        this.input = input;
    }

    public boolean submit(OrderCommand command) {
        lock.readLock().lock();
        try {
            if (!accepting) {
                return false;
            }
            Message<OrderCommand> request = MessageBuilder
                .withPayload(command)
                .setHeader("businessEventId", command.eventId())
                .build();
            return input.send(request, 200);
        } finally {
            lock.readLock().unlock();
        }
    }

    public void open() {
        lock.writeLock().lock();
        try {
            accepting = true;
        } finally {
            lock.writeLock().unlock();
        }
    }

    public void close() {
        lock.writeLock().lock();
        try {
            accepting = false;
        } finally {
            lock.writeLock().unlock();
        }
    }
}
~~~

Types: <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.integration.support.MessageBuilder</code>, <code>java.util.concurrent.locks.ReadWriteLock</code>, and <code>ReentrantReadWriteLock</code>. Register the gate via:

~~~java
@Bean
OrderAdmissionGate orderAdmissionGate(
        @Qualifier("orders.pending") MessageChannel pending) {
    return new OrderAdmissionGate(pending);
}
~~~

Critical contract:

1. Once <code>close()</code> **returns**, every <code>submit()</code> *starting afterward* is rejected; any sends that entered the gate before cutoff have already completed or timed out before the write lock was acquired.
2. Only callers going **through the gate** are protected. Never expose the raw channel to another producer assuming the gate protects it.
3. <code>submit() == false</code> means **not accepted by this interface**. HTTP gateways, broker adapters, or outboxes need proper retry/NACK/persistence policies; never ACK the source as completed.
4. Across multiple JVMs, a **single-process** lock cannot block producers on other pods. You need durable state, versioning/CAS, broker pause/partition ownership, or distributed admission control.
5. Holding the read lock across <code>send(timeout)</code> can make <code>close()</code> wait up to that timeout; keep timeouts bounded and measure cutoff latency.

A gate does not process in-flight messages. It solely establishes the point of **no further acceptance** so draining can terminate.

## 7. Drain: When Is There Really No Unfinished Work Left?

After closing ingress, a common check looks like:

~~~java
if (queue.getQueueSize() == 0) {
    worker.stop();
}
~~~

**This check is unsafe.** The poller may have just dequeued the final message while the handler is still running. A message might also sit inside an executor queue or await retry/backoff; <code>getQueueSize()</code> reads 0 even though work is unfinished.

### Defining an Outstanding Unit of Work

For an accepted logical message:

~~~text
ACCEPTED
   │
   ├──> PENDING_QUEUE
   │          │
   │          └──> IN_FLIGHT
   │                    ├──> COMMITTED / ACKED      ──> SETTLED
   │                    ├──> DURABLY_QUARANTINED   ──> SETTLED per policy
   │                    └──> RETRY_SCHEDULED       ──> still OUTSTANDING
   │
   └──> REJECTED_BEFORE_ACCEPTANCE ──> not counted as outstanding
~~~

For draining, count **accepted but not terminally settled**, not merely messages sitting in a channel. The post-condition can be expressed as:

\[
\text{Outstanding} = \text{Accepted} - \text{Committed/ACKed} - \text{QuarantinedByPolicy} = 0
\]

**Formula caveat:** One message can fan out into multiple fragments/side effects, so <code>Accepted</code> and <code>Settled</code> units must be defined per **logical event**. If a message is ACKed only after outbound completion, do not decrement outstanding right after <code>handleMessage()</code> returns. Across multiple nodes, persist progress durably or derive it from broker/DB/outbox rather than local <code>AtomicInteger</code> counters.

### Preventing Races When Recording Accepted and Completed

Within a single JVM, if using counters, register a message as outstanding **before** any consumer can process it; if <code>send()</code> definitively fails before acceptance, roll back the counter. Incrementing **after** <code>send()</code> lets a fast worker finish before the increment runs, causing negative counts or premature drain completion.

Also decide explicitly:

- Does a retry reprocess the same logical event or spawn a new event?
- Does success mean handler return or transaction commit?
- When moved to DLQ/quarantine, who owns replay and when is it considered settled?
- When producer/broker cannot tell if ACK succeeded or failed, reconcile instead of blindly decrementing counters.

In production, an <code>admitted/settled</code> ledger in a durable inbox/outbox or broker offsets is far more reliable than in-memory counters alone.

### A Probe as the Contract Between Flow and Orchestrator

~~~java
public interface WorkDrainProbe {
    // Must include queue, in-flight, retries, and items lacking terminal outcomes.
    boolean allAcceptedWorkSettled();

    // For logs/metrics; insufficient on their own as stop conditions.
    long inFlight();
    long pending();
}
~~~

This is an **application-implemented interface**, not a Spring Integration API. For simple flows, a probe may combine race-free queue depth and in-flight tracking. With persistent queues and brokers, the probe must inspect DB/adapter state. No single "universal channel" implementation works without knowing transaction boundaries.

## 8. Coordinator: Start → Quiesce → Drain → Stop

The example below combines the Section 6 gate, endpoint <code>SmartLifecycle</code>, and an application-implemented <code>WorkDrainProbe</code>. It is a **single-process** coordinator skeleton, not a distributed controller.

~~~java
public final class OrderRuntimeCoordinator {
    private final OrderAdmissionGate gate;
    private final SmartLifecycle workerEndpoint;
    private final WorkDrainProbe probe;

    public OrderRuntimeCoordinator(
            OrderAdmissionGate gate,
            SmartLifecycle workerEndpoint,
            WorkDrainProbe probe) {
        this.gate = gate;
        this.workerEndpoint = workerEndpoint;
        this.probe = probe;
    }

    public synchronized void startAfterRecovery() {
        // Caller must confirm DB/broker/recovery sinks are ready beforehand.
        if (!workerEndpoint.isRunning()) {
            workerEndpoint.start();
        }
        if (!workerEndpoint.isRunning()) {
            throw new IllegalStateException("orders.worker is not running");
        }
        gate.open(); // Final step: open new intake only after consumer is ready.
    }

    public synchronized void quiesceDrainAndStop(Duration budget)
            throws InterruptedException {
        gate.close(); // Reject any new work through the gate.
        long deadline = System.nanoTime() + budget.toNanos();

        while (!probe.allAcceptedWorkSettled()) {
            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    "Drain timeout; keeping gate closed and worker running");
            }
            Thread.sleep(25);
        }

        workerEndpoint.stop();
        if (workerEndpoint.isRunning()) {
            throw new IllegalStateException(
                "Endpoint did not stop; inspect lifecycle");
        }
    }
}
~~~

<code>Duration</code> is from <code>java.time</code>; <code>SmartLifecycle</code> is from <code>org.springframework.context</code>. To wire it:

~~~java
@Bean
OrderRuntimeCoordinator orderRuntimeCoordinator(
        OrderAdmissionGate gate,
        @Qualifier("orders.worker") SmartLifecycle endpoint,
        WorkDrainProbe probe) {
    return new OrderRuntimeCoordinator(gate, endpoint, probe);
}
~~~

**Limitations to state clearly:**

1. <code>Thread.sleep(25)</code> merely illustrates a deadline-bounded wait loop on a **management/control thread**—never run it on poller threads or inside handlers being drained. Large systems should use completion signals, condition variables, or event-driven coordinators.
2. On timeout, this code does **not** destroy the flow or stop the consumer. The gate stays closed so operators can resolve the bottleneck and resume draining. This is intentional to avoid abandoning in-flight messages.
3. <code>isRunning()</code> reflects lifecycle state. Some implementations stop asynchronously via <code>stop(Runnable)</code>; returning from <code>stop()</code> does not automatically prove every task finished. Verify the implementation contract and <code>WorkDrainProbe</code>.
4. <code>synchronized</code> serializes coordinator calls within **one instance** only. Multi-pod deployments need leaders/locks/CAS or partition ownership so two coordinators do not start/stop the same flow concurrently.
5. <code>startAfterRecovery()</code> does not verify external dependencies itself; actual readiness checks must precede calling it.
6. In a Spring context, a <code>WorkDrainProbe</code> <code>@Bean</code> needs a real implementation; the example does not claim the framework provides one automatically.

### When Draining Cannot Finish Within the Shutdown Budget

If the orchestrator grants only a finite shutdown window, never fake <code>outstanding = 0</code> and destroy everything:

| Message Group | Safe Handling |
|---|---|
| Still in broker, unacked | Leave in broker / NACK / requeue per adapter contract |
| Written to durable inbox/queue | Stop consumer after proper commits; let new instance resume |
| Running handler that cannot safely cancel | Grant sufficient grace period, or use fencing to block stale writes post-restart |
| Only in an in-memory queue | Prioritize draining or flush to a durable store before process exit |
| External side effect sent with uncertain ACK | Use idempotency keys and reconcile after restart |
| Delayer/aggregator with pending groups | Preserve store/region, recover or quarantine per policy; never wipe blindly |

A shutdown qualifies as a **safe stop** if unfinished work retains a verifiable recovery path, even if not every business operation finished at the exact moment the pod stopped.

## 9. Stop Semantics by Channel and Endpoint Type

You cannot write one generic stop routine and assume identical behavior across every channel.

| Construct | When Consumer / Source Stops | Remaining Risks |
|---|---|---|
| <code>DirectChannel</code> + <code>EventDrivenConsumer</code> | Endpoint may unsubscribe handler; channel remains if declared as a standalone bean | Senders still calling send may hit <code>MessageDispatchingException</code> |
| <code>PublishSubscribeChannel</code> | Subscriber count drops as endpoints stop | Zero subscribers allowed by default can let send "succeed" with zero deliveries |
| <code>ExecutorChannel</code> | No new subscriber dispatch after stop, yet already-submitted worker tasks can continue | Post-stop worker errors, premature executor shutdown, late side effects |
| <code>QueueChannel</code> + <code>PollingConsumer</code> | Poller stops issuing new <code>receive()</code> calls per lifecycle | Messages stay in queue; in-flight handlers may still be running |
| <code>SourcePollingChannelAdapter</code> | Stops triggering polls | Messages received but not yet dispatched/committed remain subject to rollback/redelivery |
| <code>FluxMessageChannel</code> + reactive consumer | Must manage subscriptions/cancellations per reactive lifecycle | Cancellation does not mean remote side effects rolled back |
| Inbound Kafka/JMS/AMQP adapter | Container/listener stops via transport-specific API | ACKs, offsets, redeliveries, rebalances, and in-flight callbacks vary |

### Subtle Bug: DirectChannel Reporting Missing Subscribers During Shutdown

~~~text
Thread A: producer checks endpoint is still ACTIVE
Thread B: stops EventDrivenConsumer, unsubscribing handler
Thread A: calls send(M) on DirectChannel
→ MessageDispatchingException: Dispatcher has no subscribers
~~~

This is a **lifecycle boundary race**. Fix it by closing admission/stopping ingress **before** stopping consumers—never by increasing <code>sendTimeout</code> or attaching a dummy handler to swallow messages.

With <code>PublishSubscribeChannel</code> defaulting to <code>minSubscribers=0</code>, the bug is even subtler: sends can succeed silently after all subscribers stop. When delivery is mandatory, configure <code>requireSubscribers</code> or route events through a store/broker with a durable contract; never treat default publish–subscribe as a durable queue.

## 10. Stopping in the Right Order with Executors and Schedulers

Spring Framework distinguishes <code>TaskExecutor</code> (running tasks) from <code>TaskScheduler</code> (scheduling periodic tasks). An <code>ExecutorChannel</code> or poller may rely on these **shared** beans.

A generally safe sequence:

~~~text
1. Close ingress/admission; pause broker listeners if applicable
2. Stop issuing new polls; manage already-received polls/handlers per policy
3. Wait for accepted-but-unsettled to reach 0 or secure durable recovery
4. Stop endpoints/adapters and unregister subscribers
5. Shut down flow-owned executors/schedulers once tasks drain
6. Destroy the flow and close flow-owned resources
7. Verify no orphaned timers/subscriptions/connections/tasks remain
~~~

Depending on the source, you may need to **keep polling consumers running until the queue drains**; hence steps 2 and 3 must be carefully distinguished. "Stop new polls" above applies when no queue needs draining or work already lives in durable recovery; if a backlog exists and the poller is the sole consumer, keep it running during drain.

### ThreadPoolTaskExecutor Does Not Solve Delivery Guarantees by Itself

A flow-dedicated executor might be declared as:

~~~java
@Bean(name = "orders.executor")
ThreadPoolTaskExecutor ordersExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(64);
    pool.setThreadNamePrefix("orders-worker-");
    pool.setWaitForTasksToCompleteOnShutdown(true);
    pool.setAwaitTerminationSeconds(20);
    return pool;
}
~~~

<code>ThreadPoolTaskExecutor</code> lives in <code>org.springframework.scheduling.concurrent</code>. Waiting for tasks at shutdown is a **trade-off choice**—it does not guarantee HTTP/DB side effects committed cleanly or that uncooperative tasks will terminate. Across Spring Framework versions, shutdown options and <code>SmartLifecycle</code> interact; verify <code>acceptTasksAfterContextClose</code>, early shutdown behavior, and test with real beans.

Never configure <code>setAwaitTerminationSeconds(20)</code> and assume zero tasks remain after 20 seconds. Timeout expiration can leave tasks unfinished or interrupted; uninterruptible work (such as blocking I/O) can linger longer.

### Why Not Grow the Pool Infinitely to Drain Faster?

Adding workers can exhaust JDBC connection pools, worsen lock contention, or breach downstream rate limits. When DB/HTTP is the bottleneck, the right action is **throttling ingress**, keeping concurrency within dependency limits, and using durable buffering—not blindly raising <code>maxPoolSize</code>.

## 11. Transactions, ACKs, and Retries at the Stop Boundary

To stop safely, map what each transaction protects:

| Flow | Where Does the Transaction Usually Live? | What Must Never Be Assumed |
|---|---|---|
| <code>DirectChannel</code> same thread | Outer transaction may span handler | <code>send()</code> returning means all outbound effects committed |
| <code>ExecutorChannel</code> | Worker opens its own transaction if configured | Sender's JDBC transaction propagates automatically |
| <code>QueueChannel</code> with persistent store | Receive/handler inside poller transaction per advice/store | Dequeuing from queue means broker ACK succeeded |
| Kafka/JMS/AMQP inbound | Container transaction/acknowledgement and handler per adapter | ACK always rolls back when async handler fails |
| Reactive flow | Reactive transaction manager in Reactor Context | ThreadLocal JDBC travels across <code>publishOn</code> automatically |

**Handler retries differ from sender retries.** If a sender is rejected before reaching the handler, <code>RequestHandlerRetryAdvice</code> inside the handler never gets a chance to retry. If a retry runs after a remote side effect succeeded yet ACK failed, replay can create duplicates. Therefore:

- every logical event needs a stable business idempotency key;
- terminal commits/ACKs are recorded under a consistent contract or reconciled;
- retries are bounded with backoff/jitter, plus dead-letter/quarantine for poison messages;
- stop/cancel must not silently delete durably persisted retry jobs;
- stop must block **new attempts** on invalidated events (e.g., a DELETING tenant) without unlawfully wiping audit/recovery records.

### MessageStore Is a Data Responsibility, Not Just a Bean

<code>JdbcMessageStore</code>, <code>JdbcChannelMessageStore</code>, <code>MessageGroupStore</code>, or Redis stores can hold queues, aggregator groups, delayers, and claim-checks. When stopping/destroying a flow:

1. Identify which messages remain pending and who legally consumes them after restart.
2. Preserve namespaces/regions and serializers needed for recovery, or migrate/quarantine with audit trails.
3. Delete only eligible groups/messages per policy; never DELETE raw rows while workers are still reading.
4. Across multiple instances, coordinate locks/correlation/claims so two nodes never process the same event unintentionally.
5. Separate resource cleanup (closing connections/threads) from data cleanup (retention/purging).

Destroying a store bean **does not** delete database contents by default. Conversely, deleting store rows can prevent a flow from resuming after restart.

## 12. Lifecycle of Dynamically Registered IntegrationFlows

For statically declared <code>@Bean</code> flows, the Spring context handles many lifecycle aspects. For flows created at runtime, <code>IntegrationFlowContext</code> provides registration, start/stop, and removal.

For instance, an app maintains a dedicated processing flow per tenant. Each tenant receives a **stable flow ID** and its own <code>DirectChannel</code> to prevent cross-routing:

~~~java
@Component
public class TenantFlowRegistry {
    private final IntegrationFlowContext flowContext;
    private final TenantEventService service;

    public TenantFlowRegistry(
            IntegrationFlowContext flowContext,
            TenantEventService service) {
        this.flowContext = flowContext;
        this.service = service;
    }

    private String id(UUID tenantId, long generation) {
        return "tenant.flow." + tenantId + "." + generation;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration register(
            UUID tenantId, long generation) {
        String flowId = id(tenantId, generation);
        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException("Flow already registered: " + flowId);
        }

        MessageHandler handler = message -> service.process(
            tenantId, generation, (TenantEvent) message.getPayload());

        IntegrationFlow flow = IntegrationFlow.from(new DirectChannel())
            .handle(handler)
            .get();

        return flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
    }

    public void start(UUID tenantId, long generation) {
        var registration =
            flowContext.getRegistrationById(id(tenantId, generation));
        if (registration == null) {
            throw new IllegalStateException("Flow not registered");
        }
        registration.start();
    }

    public void unregisterAfterDrain(UUID tenantId, long generation) {
        var registration =
            flowContext.getRegistrationById(id(tenantId, generation));
        if (registration != null) {
            registration.stop();
            registration.destroy();
        }
    }
}
~~~

<code>TenantEventService</code> and <code>TenantEvent</code> are **application-defined types**, for example:

~~~java
public record TenantEvent(String eventId, String content) {}

public interface TenantEventService {
    void process(UUID tenantId, long generation, TenantEvent event);
}
~~~

Framework types: <code>org.springframework.integration.dsl.context.IntegrationFlowContext</code>, <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, and <code>org.springframework.messaging.MessageHandler</code>.

**Design implications:**

1. <code>registration(...).autoStartup(false)</code> registers the topology without opening processing yet—ideal when initialization is still incomplete.
2. <code>registration.start()</code> is called only once the tenant is ACTIVE, credentials/routes are ready, and the corresponding admission gate permits it.
3. <code>registration.stop()</code> halts lifecycle components of the flow; it **does not replace** draining.
4. <code>registration.destroy()</code> removes the registration and flow-owned dependent beans. You may use <code>flowContext.remove(flowId)</code> to remove by ID; do not call **both** on the same registration.
5. <code>useFlowIdAsPrefix()</code> avoids bean ID collisions when many flows share similar structure; it requires specifying <code>.id(...)</code>.
6. <code>TenantEventService</code> may be a shared bean; the flow only **references** the service and must never destroy a shared service when one tenant is removed.

Checking <code>getRegistrationById() != null</code> followed by registering is not atomic across multiple threads or nodes. Production must serialize per-tenant provisioning/deletion via CAS/versioning, single-owner assignment, or proper coordination. Using a generation number keeps stale cleanup from accidentally tearing down a newly recreated flow for the same tenant.

### Registry Is Not Persistent Configuration

Dynamic registration is runtime state inside <code>ApplicationContext</code>. After a JVM restart, the application must **rebuild flows** from a durable configuration source; never expect a Java-registered flow to reappear automatically in a new process simply because the message store still holds data.

## 13. Ownership: Which Resources Are Allowed to Close?

Lifecycle cleanup must start from an **ownership map**. Distinguish flow-created resources from application-wide shared resources:

| Resource | Typically Per-Flow / Per-Tenant? | Cleanup |
|---|---|---|
| <code>IntegrationFlowRegistration</code> | Yes | Stop/destroy after draining |
| Endpoints and channels created exclusively by dynamic registration | Yes | Registration manages dependents; verify beans/handles disappear |
| Shared <code>DirectChannel</code>, routers, and error channels | No | Unsubscribe/remove tenant route only; never close shared channels |
| Per-tenant <code>ThreadPoolTaskExecutor</code> | Possibly | Stop new submissions; drain then shut down with deadline |
| Shared executors or <code>TaskScheduler</code> | No | Never shut down just because one tenant stops |
| Flow-dedicated broker listener container | Possibly | Stop/unsubscribe exact container and verify ACKs/offsets |
| Shared connection factory / HTTP client | No | Never close while other tenants still use it |
| Custom <code>ScheduledFuture</code>, Reactor <code>Disposable</code> | Possibly | Cancel/dispose exact handle; verify no lingering callbacks |
| Per-tenant secrets/credentials/caches | Possibly | Revoke only once no valid in-flight/recovery needs them |
| <code>JdbcMessageStore</code>/Redis data | Data may be tenant-scoped on shared backends | Retention/purge by namespace and generation; never drop shared backend |
| Error/DLQ/outbox records | Data may belong to a tenant | Clean up per retention policy and audit, never automatically on flow destroy |

**Never pass a shared singleton into <code>IntegrationFlowRegistrationBuilder.addBean(...)</code> just for convenience** unless you intend it to fall under dependent-bean destruction. A connection factory or scheduler must only close when its **true owner** shuts down and zero consumers remain.

### Controlled Cleanup Hooks

An application can model owned resources as leases:

~~~java
public interface RuntimeResourceLease extends AutoCloseable {
    String ownerFlowId();
    String resourceName();

    @Override
    void close() throws Exception;
}
~~~

An application registry mapping <code>ownerFlowId → leases</code> can make cleanup idempotent, verify ownership before closing, and track results for retries. This is not a built-in Spring Integration interface.

**Avoid double-close:** If an object is already registered as a dependent bean of the flow registration and the framework calls its destroy hook, do not also close it again via a separate resource registry if the implementation is not idempotent.

### A Layered Cleanup Workflow

~~~mermaid
flowchart TD
    A["Ingress blocked, pending settled"] --> B["Stop flow endpoints"]
    B --> C["Destroy registration / owned beans"]
    C --> D["Cancel timers, custom subscriptions, owned leases"]
    D --> E["Check whether executor/connection/threads still have owners?"]
    E --> F["Purge data per policy by namespace/generation"]
    F --> G["Write cleanup checkpoint + verify post-conditions"]
    D -. "Do not touch" .-> H["Shared executor / channel / connection factory"]
~~~

Cleanup can fail partway through. Every step should be **idempotent**, checkpointed, and distinguish "resource confirmed absent" from "could not verify whether resource is absent".

## 14. Restart and Post-Crash Reconciliation

A procedure that works only during graceful shutdown is insufficient. Processes get killed by <code>kill -9</code>, power loss, OOMs, or forced pod eviction before deadlines. In those cases, <code>stop()</code>/<code>destroy()</code> callbacks **are not guaranteed to run**.

The application needs a startup **reconciler** driven by durable state:

| Durably Stored State | Startup Behavior |
|---|---|
| <code>ACTIVE</code> | Rebuild flow per config; hold traffic until all dependencies/routes are ready |
| <code>STARTING</code> from a dead process | Verify checkpoints, ownership, and idempotency before resuming |
| <code>QUIESCING</code>/<code>DRAINING</code> | Do not open new ingress; recover/drain/quarantine pending work per policy |
| <code>STOPPING</code> | Verify consumers stopped and inspect outstanding work; finish stop safely |
| <code>CLEANUP_FAILED</code> | Retry cleanup with generation fencing; do not provision a fresh flow yet |
| <code>DELETED</code> | Do not rebuild; run a separate leak/retention audit job if needed |

Example startup sequence for a new instance:

~~~text
1. Read config + operation/job states from DB
2. Initialize message stores, connection/transaction managers, and recovery sinks
3. Rebuild eligible flows without auto-starting inbound adapters
4. Recover pending groups/delayed messages/queues per endpoint type
5. Establish exclusive ownership per partition or tenant
6. Start consumers; run health and business readiness checks
7. Open admission / broker listeners / HTTP readiness
8. Enable lag, duplicate-event, error-rate, and startup-duration monitoring
~~~

These steps are an application design—not an atomic transaction spanning Spring context, broker, and DB. Persist checkpoints durably; an in-memory <code>AtomicBoolean</code> inside a singleton vanishes on crash.

### Managing Idempotency When Old and New Instances Overlap

During rolling deploys, an old instance may still be finishing a side effect while a new instance receives a redelivery. Combine:

- unique business event IDs, unique constraints, or durable inboxes to block double commits;
- lease/partition ownership preventing two consumers from processing simultaneously when disallowed;
- generation/version fencing before writing resources subject to stale cleanup;
- clear timeouts and transaction boundaries to determine which attempt is terminal;
- recovery workflows when remote side effects succeeded before ACK/DB markers committed.

Spring Integration orchestrates messaging, yet **does not automatically provide end-to-end exactly-once semantics** across brokers, DBs, and remote HTTP services.

## 15. Container / Kubernetes Shutdown and Rolling Deployments

Container runtimes send a termination signal and grant a finite grace window before killing the process. Design accordingly:

1. **Readiness off:** stop advertising the instance for new traffic. HTTP/load-balancer readiness and pausing broker listeners are **two separate paths**—configure both when used.
2. **Close admission:** reject new submissions inside the process, including requests that arrived right before readiness flipped.
3. **Allow drain:** keep required handlers/pollers running to finish accepted work; never shut down executors prematurely.
4. **Cut over safely:** if the drain budget expires, move pending work to durable recovery rather than interrupting blindly and assuming messages return on their own.
5. **Stop/destroy:** halt endpoints, then close resources according to ownership.
6. **Exit:** reconcile and flush final metrics/traces within time limits; do not hang the process indefinitely.

A <code>@PreDestroy</code> hook can help record checkpoints or run quick cleanups, yet should not be the sole mechanism for multi-second drains. By bean destruction time, the lifecycle processor may already have stopped components needed to finish work. A coordinator handling quiesce/drain **before context close** is usually far easier to control.

### SmartLifecycle Phases and Readiness Must Work Together

Lower phases starting first/stopping last provide **relative ordering**, not a substitute for:

- blocking requests at load balancers or gateways;
- pausing/stopping broker listeners with proper ACK/offset handling;
- confirming messages persisted or handlers completed;
- blocking new dynamic registrations while shutting down;
- waiting for async error publishers, trace exporters, and resource cleanup to finish.

When implementing <code>SmartLifecycle.stop(Runnable callback)</code> in a custom component, invoke the callback **once after stopping truly finishes**. Firing the callback immediately upon merely *requesting* executor shutdown can cause the lifecycle processor to close connections while tasks are still using them.

### Common Failure Pattern

~~~text
preStop: shuts down executor first
    ↓
HTTP/broker ingress still pushes messages
    ↓
ExecutorChannel rejects all new tasks
    ↓
Error handler fails to publish or recovery sink is already closed
    ↓
Messages falsely ACKed / request timeouts / retry storms
~~~

The real fix changes **event ordering** and admission checks—not merely bumping shutdown timeouts.

## 16. Observing Lifecycle and Cleanup Post-Conditions

In production, maintain **phase-specific metrics** rather than relying solely on an `"Application started"` log line.

| Observable | Meaning | How to Use During an Incident |
|---|---|---|
| <code>flow.state</code> by state group | <code>STARTING/READY/QUIESCING/DRAINING/STOPPED</code> | Spot flows stuck in abnormal phases |
| <code>ingress.accepting</code> | Whether admission gate is open or closed | Explain 429/503/NACKs or rejected messages |
| <code>accepted_not_settled</code> | Count of non-terminal logical events | Judge when stopping is safe |
| <code>queue.depth</code> and oldest age | Messages awaiting consumers | Detect missing pollers, backlogs, or slow consumers |
| <code>endpoint.isRunning</code> | Lifecycle status of pollers/subscribers | Cross-check against READY/STOPPED state |
| Executor active/queued/rejected | Workers exhausted or shut down | Locate unfinished tasks |
| Pending groups/delayed messages | Unreleased correlations, pending delays | Decide store retention or quarantine |
| Error/retry/DLQ counts | Whether recovery is accumulating backlog | Avoid closing flows with unsettled errors |
| Cleanup step duration/failures | Which resources/beans clean up slowly or leak | Retry checkpoints and evaluate grace periods |

Names like <code>flow.state</code>, <code>ingress.accepting</code>, and <code>accepted_not_settled</code> are **application-proposed metrics**, not default meters auto-created by Spring Integration. Spring Integration supports Micrometer/Observation for channels, handlers, and sources when configured, while business "terminally settled" metrics must be defined by the application.

### Correlation and Controlling Metric Label Cardinality

Include in authorized logs/traces:

~~~text
timestamp, service, instance, flowId, endpointId
phase, action, reason, elapsedMs, threadName
messageId, correlationId, businessEventId
accepted, settled, inFlight, queueDepth
~~~

Never attach high-cardinality raw business event IDs, request IDs, or tenant UUIDs to **every metric label**. Dynamic flows can explode time-series counts if every flow ID becomes a distinct tag. Use stable low-cardinality tags such as <code>flowType</code>, <code>endpointType</code>, and <code>outcome</code>; keep correlation IDs in traces/logs with proper security policies.

### Integration Graph and Lifecycle Snapshots

When <code>IntegrationGraphServer</code> is available, rebuilding a graph snapshot verifies added/removed topology:

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

var current = graphServer.rebuild();
log.info("Current integration graph: {}", current);
~~~

These types reside in <code>org.springframework.integration.graph</code>. Calling <code>rebuild()</code> is useful after dynamic registration/removal because the graph may be cached, yet **the graph does not prove specific messages were processed**. During shutdown, still reconcile ingress, ACKs, in-flight tasks, queues/stores, and lifecycle state.

## 17. Testing Lifecycle with JUnit 5

Lifecycle tests must catch races and complete **deterministically**, never relying on <code>Thread.sleep(1000)</code> hoping workers finished. With <code>QueueChannel</code>, sends/receives should use finite timeouts. For executors/in-flight work, use latches or futures.

### 17.1. Testing Gate Open/Close While Preserving Queued Messages

~~~java
@Test
void closedGateRejectsNewMessagesWithoutClearingBacklog() {
    QueueChannel queue = new QueueChannel(1);
    OrderAdmissionGate gate = new OrderAdmissionGate(queue);
    OrderCommand order = new OrderCommand("E-1", "O-1", 2);

    assertFalse(gate.submit(order)); // Gate starts closed.
    gate.open();
    assertTrue(gate.submit(order));
    assertEquals(1, queue.getQueueSize());

    gate.close();
    assertFalse(gate.submit(new OrderCommand("E-2", "O-2", 1)));
    assertEquals(1, queue.getQueueSize()); // Not cleared when gate closes.
    assertEquals(order, queue.receive(0).getPayload());
}
~~~

This test proves only single-JVM admission and queue logic. It does not simulate producers bypassing the gate or crashes before message persistence.

### 17.2. Testing the Race Between submit() and close()

This critical test verifies <code>close()</code> never reports completion while a sender still holds the read lock:

~~~java
@Test
void closeWaitsForAnAlreadyAcceptedSend() throws Exception {
    DirectChannel channel = new DirectChannel();
    CountDownLatch handlerEntered = new CountDownLatch(1);
    CountDownLatch releaseHandler = new CountDownLatch(1);
    CountDownLatch closeAttempted = new CountDownLatch(1);

    channel.subscribe(message -> {
        handlerEntered.countDown();
        try {
            if (!releaseHandler.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test handler timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    });

    OrderAdmissionGate gate = new OrderAdmissionGate(channel);
    gate.open();
    ExecutorService threads = Executors.newFixedThreadPool(2);
    try {
        Future<Boolean> sending = threads.submit(() ->
            gate.submit(new OrderCommand("E-1", "O-1", 2)));

        assertTrue(handlerEntered.await(2, TimeUnit.SECONDS));
        Future<?> closing = threads.submit(() -> {
            closeAttempted.countDown();
            gate.close();
        });

        assertTrue(closeAttempted.await(2, TimeUnit.SECONDS));
        assertFalse(closing.isDone()); // Send still holds read lock.

        releaseHandler.countDown();
        assertTrue(sending.get(2, TimeUnit.SECONDS));
        closing.get(2, TimeUnit.SECONDS);
        assertFalse(gate.submit(new OrderCommand("E-2", "O-2", 2)));
    } finally {
        releaseHandler.countDown();
        threads.shutdownNow();
    }
}
~~~

<code>CountDownLatch</code>, <code>ExecutorService</code>, <code>Executors</code>, <code>Future</code>, and <code>TimeUnit</code> belong to <code>java.util.concurrent</code>. This test intentionally uses <code>DirectChannel</code> so the synchronous handler holds the read lock inside <code>send()</code>. With <code>ExecutorChannel</code>, handlers run after submission so the lock protects only **acceptance time**, not worker completion; <code>WorkDrainProbe</code> is needed to drain.

### 17.3. Testing Non-Auto-Start Endpoints

Using <code>OrderRuntimeConfig</code> from Section 5:

~~~java
@SpringJUnitConfig(OrderRuntimeConfig.class)
@SpringIntegrationTest(noAutoStartup = "orders.worker")
class OrderWorkerLifecycleTest {

    @Autowired
    @Qualifier("orders.worker")
    SmartLifecycle worker;

    @Autowired
    @Qualifier("orders.pending")
    QueueChannel pending;

    @Test
    void pendingMessageDoesNotRequireWorkerToBeRunning() {
        assertFalse(worker.isRunning());

        Message<OrderCommand> event = MessageBuilder
            .withPayload(new OrderCommand("E-10", "O-10", 1))
            .build();

        assertTrue(pending.send(event, 0));
        assertEquals(1, pending.getQueueSize());

        // Fixture cleanup because this test intentionally never starts the poller.
        assertEquals(event, pending.receive(0));
    }

    @Test
    void workerCanBeStartedThenStopped() {
        assertFalse(worker.isRunning());
        worker.start();
        try {
            assertTrue(worker.isRunning());
        } finally {
            worker.stop();
        }
    }
}
~~~

<code>@SpringJUnitConfig</code> belongs to <code>org.springframework.test.context.junit.jupiter</code>; <code>@SpringIntegrationTest</code> belongs to <code>org.springframework.integration.test.context</code>. With Spring TestContext caching, ensure endpoints and queues return to the clean fixture state needed by subsequent tests—via post-test cleanup or context isolation. Operationally, this test demonstrates the queue still accepts messages before the consumer starts; it **does not** verify messages are processed without starting the worker.

### 17.4. Testing Clean Removal of Dynamic Registrations

~~~java
@Test
void registeredFlowCanStartStopAndBeDestroyed() {
    String id = "test.flow.orders";
    AtomicInteger processed = new AtomicInteger();
    MessageHandler handler = msg -> processed.incrementAndGet();
    IntegrationFlow flow = IntegrationFlow.from(new DirectChannel())
        .handle(handler)
        .get();

    var registration = flowContext.registration(flow)
        .id(id)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();
    try {
        registration.start();
        assertTrue(registration.getInputChannel().send(
            MessageBuilder.withPayload("item").build()));
        assertEquals(1, processed.get());
        registration.stop();
    } finally {
        registration.destroy();
    }

    assertNull(flowContext.getRegistrationById(id));
}
~~~

<code>flowContext</code> is an <code>IntegrationFlowContext</code> bean injected into a Spring-backed test; use unique test IDs if tests run in parallel. The test proves registration lifecycle and dispatch. It does not prove external resources closed or persistent message stores purged properly.

## 18. Failure-Injection Matrix for Start, Stop, and Cleanup

| Failure Point | Possible Consequence | Evidence to Verify |
|---|---|---|
| Register flow before dependencies are ready | Adapter/handler receives messages then fails | Admission stays closed; no unintended ACKs |
| Handler fails to start | Endpoint stays stopped; channel may lack subscribers | Health/exceptions/logs and recovery policy |
| Producer sends right as gate closes | Send succeeds or rejects relative to cutoff order | Zero new sends complete after <code>close()</code> when routed via gate |
| Stop <code>EventDrivenConsumer</code> while sender is active | <code>MessageDispatchingException</code> | Race prevented by quiescing before stop |
| Poller dequeues while handler is unfinished | Queue empty yet uncommitted | Outstanding > 0; do not destroy |
| Executor holds queued tasks at shutdown | Tasks rejected/interrupted or late side effects | Accepted/settled tracking and shutdown policy |
| Reactive subscription cancelled | Publisher terminates/cancels while remote operation runs | Cancellation hooks and external idempotency |
| DB commits while broker ACK fails | Message redelivered; potential duplicate side effects | Unique business event keys block duplicates |
| Broker ACKs while queue is RAM-only | Crash loses unprocessed messages | Durable handoff design; never ACK before required durability |
| Error flow closes before producer/worker | <code>ErrorMessage</code> has no subscriber | Original error still recorded with recovery |
| Delayer/aggregator holds groups at destroy | Messages/groups remain in persistent store | Proper recovery/retention; never delete raw rows |
| Resource cleanup partially fails | Leaked sockets, timers, dependent beans | Checkpoints + idempotent retries |
| Dynamic flow deleted and recreated for same tenant | Stale cleanup collides with new resources | Generation/owner fencing |
| Pod killed skipping shutdown hooks | In-memory state and dynamic registry vanish | Rebuild/reconcile from durable state |

### Defining Game-Day PASS Criteria

A "successful graceful shutdown" drill must verify:

- No messages accepted **after cutoff** lack a recovery path;
- All accepted events are either **settled per policy** or have verifiable durable replay;
- No stale worker continues writing unauthorized side effects after ownership shifts;
- Endpoints, timers, connections, and custom resources close per ownership;
- New instances rebuild only eligible flows without reviving tenants undergoing cleanup;
- Business events never produce duplicate side effects across redeliveries;
- Metrics/traces/audits suffice to prove all of the above.

Exiting with status code 0 is **not enough** to PASS if ACKed messages were lost inside an in-memory queue.

## 19. Runbook When Flows Refuse to Start, Stop, or Clean Up

| Symptom | Likely Cause | Investigation Steps |
|---|---|---|
| Flow declared yet processes no messages | <code>autoStartup=false</code>, endpoint unstarted, wrong input channel | Inspect <code>SmartLifecycle</code>, endpoint IDs, subscriber counts |
| Started yet still not ready | DB/broker/credentials unavailable, missing error sink | Check readiness dependencies and startup errors |
| <code>DirectChannel</code> has no subscribers | Endpoint stopped/unstarted or dynamic flow destroyed | Trace admission, wiring, and lifecycle timeline |
| Queue accepts messages with zero output | Poller stopped, slow handler, queue backlog | Inspect poller state, oldest age, worker/DB metrics |
| Stop hangs for a long time | In-flight blocking I/O, infinite retries, executor deadlock | Capture thread dumps, check outstanding, deadlines, dependencies |
| Stop finishes while tasks still run | Async tasks submitted prior to stop; lifecycle differs from completion | Check active/queued workers and task completion metrics |
| Restart loses messages | In-memory queue or premature ACK | Inspect durable store/offsets and recovery contract |
| Restart causes duplicate processing | Side effect committed while ACK failed | Verify business idempotency keys, outbox/inbox |
| Flow destroyed yet JDBC groups remain | Persistent data outlives bean lifecycle | Check region/group policy and retention jobs |
| Unrelated tenants disrupted during cleanup | Shared executor/channel/connection closed | Audit ownership map and bean destruction logs |
| Recreated dynamic flow fails with bean name collision | Duplicate ID/prefix or unremoved old registration | Check <code>getRegistrationById()</code>, flow IDs/generations |
| Metrics show zero traffic after rolling deploy | Admission closed, paused source, or changed component IDs | Verify readiness, broker listeners, graph rebuild |

### Ordered Runbook

1. Identify <code>flowId</code>, endpoint ID, channel type, instance/pod, and state transition timestamps.
2. Inspect <code>SmartLifecycle.isRunning()</code>, <code>autoStartup</code>, phase, and gate status.
3. Reconstruct the timeline across ingress accepted, worker started, handler completed, DB commit/ACK, and errors/retries.
4. If startup failed, keep admission closed until resources/consumers achieve readiness.
5. If stop stalls, separate queued pending work from in-flight tasks and durable recovery; capture thread dumps when needed.
6. If cleanup failed, confirm which resources belong exclusively to the flow; never close shared singletons.
7. On restart, read durable state and generations before rebuilding or replaying.
8. Reproduce incidents via tests with latches, timeouts, and fault injection instead of random restarts.
9. Record checkpoints/post-conditions, assign ownership for remaining DLQ/replay items, and close the incident only when zero orphaned work remains.

## 20. Production Design Checklist

- [ ] Explicit state machine covering register, start, ready, quiesce, drain, stop, and destroy.
- [ ] Readiness enabled **only after** consumers/dependencies/recovery sinks are ready; admission defaults to closed.
- [ ] All critical ingress passes through a gate/router enforcing cutoff during shutdown/tenant deletion.
- [ ] <code>SmartLifecycle</code> phase ordering verified on actual beans; never rely on phases alone.
- [ ] Accepted-but-unsettled tracker aligned with true completion boundaries; never treat empty queues or <code>send()==true</code> as committed.
- [ ] Pollers are not stopped before queues needing draining are processed or moved to durable recovery.
- [ ] Executors/schedulers have clear ownership, capacities, shutdown policies, and finite deadlines; never close shared resources from one flow.
- [ ] Transactions/ACKs/retries/idempotency tested against actual broker/store adapters.
- [ ] Pending messages/groups/delayers/outboxes have retention and restart plans rather than vanishing with beans.
- [ ] Dynamic <code>IntegrationFlow</code> registrations have stable IDs, generations, and idempotent cleanup; never double-destroy registrations.
- [ ] Crash reconciler, old/new instance fencing, and startup traffic holdback are in place.
- [ ] Container graceful shutdown orders readiness-off, ingress quiesce, drain, stop, and cleanup.
- [ ] Metrics/logs/traces cover lifecycle state, queues, in-flight counts, errors, cleanup timing, and resource leaks.
- [ ] JUnit/integration tests verify start/stop, admission races, pending queues, dynamic registrations, restarts, and fault injection.
- [ ] Drills exercised timeouts, poison messages, lost ACKs, rolling deploys, and mid-cleanup failures.

**Conclusion:** Ensuring Spring Integration runtime lifecycle means designing an **operational protocol with verifiable post-conditions**, rather than just invoking <code>start()</code>, <code>stop()</code>, and <code>destroy()</code>. The resilient sequence is **prepare dependencies and recovery → start consumers → announce READY / open admission → close ingress → drain or preserve pending work → stop endpoints → clean up owned resources → verify/reconcile**. Understanding channels, pollers, executors, transactions, and message stores lets applications start, stop, and upgrade without dropping or duplicating messages outside policy.

## References

- [Spring Integration Reference — Message Endpoints, Pollers, and Lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
