# Graceful Shutdown and In-Flight Message Handling

A Spring Cloud Stream application typically runs continuously to consume messages from Kafka, RabbitMQ, or Pulsar. During a new release rollout, scale-down, node maintenance, or container replacement, the process may receive a termination signal while a consumer is mid-processing a message. If connections close too early, messages may be redelivered, offsets may remain uncommitted, outbound publishes may be incomplete, or business side effects may execute repeatedly.

Graceful shutdown is the process of stopping new work intake, allowing in-flight work to finish within a bounded window, completing required delivery acknowledgments, and then closing resources. It does not automatically make a pipeline exactly-once. The application still requires idempotency, bounded retries, and broker-appropriate recovery mechanisms.

## 1. What Happens When an Application Stops?

A consumer processing a message typically goes through these steps:

1. The broker delivers a message or record to the consumer.
2. The binder forwards the message to a `Function`/`Consumer`.
3. Business code calls a database, HTTP service, or external system.
4. The application completes its side effects.
5. The binder/client acknowledges the message or commits the offset.
6. If there is an output, the producer sends the downstream message.

Shutdown can occur at any step. For instance, the database has committed while the consumer has not yet acknowledged; the broker may redeliver the message. If the consumer acknowledges before the database commits, the message can drop out of the main flow while the business work remains incomplete.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Binder / Consumer
    participant S as Business Service
    participant D as Database
    participant P as Producer / Output
    B->>C: Deliver event
    C->>S: Invoke handler
    S->>D: Commit business change
    Note over C,S: SIGTERM may arrive here
    S-->>C: Handler completed
    C->>B: ACK / commit offset
    C->>P: Publish output (if any)
    P-->>C: Publish confirmation
~~~

The actual order among commit, acknowledge, and publish depends on application design, the binder, and transaction boundaries. The diagram depicts a conceptual flow for discussion; not every binder provides a single transaction spanning the database, input broker, and output broker.

## 2. What Goals Does Graceful Shutdown Have?

A safe shutdown workflow should achieve these goals:

- Stop accepting new requests or messages once the instance begins leaving the system.
- Avoid losing unacknowledged messages held by the broker.
- Allow running handlers to finish if enough time remains.
- Complete database transactions and required side effects.
- Acknowledge/commit only after work reaches the defined completion boundary.
- Finish pending outbound publishes or leave recoverable state.
- Close consumers, producers, connection pools, executors, and resources in the right order.
- Exit before the platform-granted deadline; otherwise, let the broker redeliver messages and have the application handle repeats safely.

It is impossible to guarantee all work finishes if a process receives `kill -9`, loses power, or experiences a sudden node crash. Proper design treats graceful shutdown as an opportunity to minimize disruption, while data durability comes from broker acknowledgments, transactions, outbox, and idempotency.

## 3. Distinguishing Readiness, Web Server Shutdown, and Message Consumer Shutdown

Three mechanisms are frequently confused:

| Mechanism | What It Controls | What It Does Not Do Automatically |
|---|---|---|
| Readiness | Whether the instance is considered ready for new traffic | Does not automatically stop Kafka consumers or Rabbit/Pulsar listeners |
| Graceful web server shutdown | Stops accepting new HTTP requests and waits for active requests | Does not automatically flush producers or drain message consumers |
| Binder/listener lifecycle | Stops or pauses message intake per binder capabilities | Does not automatically ensure business side effects and outputs committed |

Spring Boot supports graceful shutdown for the embedded web server:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

`server.shutdown=graceful` applies to the Spring Boot-managed web server. It is not a universal switch that automatically drains every Spring Cloud Stream message. `spring.lifecycle.timeout-per-shutdown-phase` sets the wait budget per lifecycle phase; configure it based on maximum processing times and the platform deadline.

When the `ApplicationContext` closes, lifecycle beans are stopped phase by phase. Spring Cloud Stream and the binder manage binding/consumer lifecycles. Detailed stop behavior depends on the binder implementation and library version. If you need to pause bindings first, wait for an in-flight counter, and then let the binder close, use the lifecycle/binding control mechanisms supported by your version and test the actual stop order.

### 3.1. Readiness Is Not a Consumer Switch

Setting readiness to `REFUSING_TRAFFIC` tells the load balancer or platform to stop routing new HTTP traffic to the Pod. A Kafka consumer or Rabbit listener may still keep receiving messages because it connects directly to the broker.

For a service with both HTTP endpoints and message bindings, the drain workflow must coordinate both:

1. Mark the instance as refusing new HTTP traffic.
2. Stop receiving new messages via the appropriate binding/listener lifecycle.
3. Wait for in-flight messages.
4. Shut down the application.

Do not use readiness DOWN as proof that consumers have stopped receiving messages.

## 4. Spring's Shutdown Lifecycle

Spring manages `Lifecycle` and `SmartLifecycle` beans when starting or closing the context. `SmartLifecycle` supports a callback in `stop(Runnable)` so a component can complete asynchronous stop work before reporting stopped.

Key principles:

- Initialize business dependencies before starting message intake.
- During shutdown, stop intake before closing databases/clients used by handlers.
- Allow enough time for active listeners and publish callbacks.
- Do not manually close binder-managed connection factories or producers without understanding lifecycle ownership.
- If you have custom lifecycle beans, define their phase relative to binders and dependencies.

Lifecycle phases govern start/stop ordering: components with higher phases generally start later and stop earlier. Do not pick an arbitrary phase value and assume the binder will wait for custom beans. Check the binder's lifecycle phase in your exact version and write integration tests to verify ordering.

### 4.1. Why `@PreDestroy` Alone May Not Be Enough

`@PreDestroy` is suitable for synchronous, fast, local resource cleanup. It is not always the right place to orchestrate a prolonged drain:

- It may run after some lifecycle components have already begun stopping.
- It does not provide an asynchronous lifecycle callback like `SmartLifecycle.stop(Runnable)`.
- An unbounded wait call can exceed the termination deadline.
- It does not automatically stop the broker from delivering new messages.

If a bounded drain is required, coordinate it in an appropriate lifecycle phase, use binder/listener APIs to stop intake, track in-flight work, and finish before the deadline. `@PreDestroy` should handle only final leftover cleanup.

## 5. Phased Shutdown Workflow

~~~mermaid
flowchart TD
    A["Receive SIGTERM / drain request"] --> B["Mark REFUSING_TRAFFIC"]
    B --> C["Stop accepting new HTTP and messages"]
    C --> D["Track in-flight handlers"]
    D --> E{"Completed before deadline?"}
    E -- Yes --> F["Complete ACK / offset / publish"]
    E -- No --> G["Stop waiting on timeout"]
    G --> H["Let un-ACKed messages redeliver"]
    F --> I["Close binder and dependencies"]
    H --> I
    I --> J["Exit process"]
~~~

A workflow can be broken into the following phases:

**Phase 1 — Start drain**

- Record the shutdown signal once; avoid multiple threads triggering drain simultaneously.
- Mark readiness to refuse new traffic.
- Reject or redirect new requests per the HTTP API contract.
- Stop spawning new background tasks or scheduled message emissions.

**Phase 2 — Stop intake**

- Pause/stop bindings or listeners using supported binder APIs.
- Stop polling new records or accepting new message deliveries.
- Do not close database connection pools while handlers still need them.
- Account for deliveries already dispatched by the broker before the stop command took effect.

**Phase 3 — Drain in-flight work**

- Track active handlers and longest running duration.
- Wait for database transactions or downstream calls to finish.
- Complete required outbound publishes.
- Let the framework perform ack/commit per configured mode.

**Phase 4 — Deadline**

- Stop waiting when the drain timeout expires.
- Never acknowledge unfinished work just to shut down faster.
- Close consumers so the broker can redeliver unacknowledged messages.
- Ensure safe reprocessing when a new instance picks up redelivered messages.

**Phase 5 — Cleanup**

- Close application-managed producers after flushing pending sends.
- Let binders close binder-owned producers/consumers/connections.
- Close executors, database pools, and downstream clients last.
- Log drain start/end timestamps and remaining unfinished work count.

## 6. Tracking In-Flight Work

An in-flight counter shows how many handlers have started and not yet finished. The counter helps observe drain progress; it does not replace the binder's listener pause/stop mechanism.

Example of a simple tracker:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class InFlightTracker {

    private int active;
    private boolean accepting = true;

    public synchronized Ticket enter() {
        if (!accepting) {
            throw new ShutdownInProgressException();
        }
        active++;
        return new Ticket(this);
    }

    public synchronized void stopAccepting() {
        accepting = false;
        notifyAll();
    }

    public synchronized int activeCount() {
        return active;
    }

    public synchronized boolean awaitDrained(Duration timeout)
            throws InterruptedException {
        long remaining = timeout.toNanos();
        long deadline = System.nanoTime() + remaining;

        while (active > 0 && remaining > 0) {
            TimeUnit.NANOSECONDS.timedWait(this, remaining);
            remaining = deadline - System.nanoTime();
        }
        return active == 0;
    }

    private synchronized void leave() {
        active--;
        if (active == 0) {
            notifyAll();
        }
    }

    public static final class Ticket implements AutoCloseable {
        private final InFlightTracker owner;
        private final AtomicBoolean closed = new AtomicBoolean();

        private Ticket(InFlightTracker owner) {
            this.owner = owner;
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                owner.leave();
            }
        }
    }

    public static final class ShutdownInProgressException
            extends RuntimeException {
        public ShutdownInProgressException() {
            super("Application is draining");
        }
    }
}
~~~

The handler uses a ticket in a try-with-resources block so the counter decrements whether processing succeeds or throws an exception:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderAccepted(String eventId, String orderId) {}

@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderAccepted> processOrder(
            InFlightTracker tracker,
            OrderService orderService) {
        return event -> {
            try (InFlightTracker.Ticket ignored = tracker.enter()) {
                orderService.processAndCommit(event);
            }
        };
    }
}
~~~

`processAndCommit` must return only after the business boundary completes. In real deployments, coordinate `stopAccepting()` with pausing/stopping bindings so the broker stops delivering messages. If a callback arrives after the tracker closes intake, the exception must be handled as a temporary shutdown rejection per binder policy; never catch the exception and return normally, as doing so could acknowledge an unprocessed message.

The tracker above illustrates counting and waiting with a timeout. It does not register itself as a lifecycle component, does not control the broker, and does not ensure all asynchronous callbacks have finished. If a handler offloads tasks to an executor and returns immediately, the ticket must span until the task actually finishes, not just submission time.

## 7. Setting the Drain Deadline

The drain window must be shorter than the platform's Pod termination budget. Example:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 50s

server:
  shutdown: graceful
~~~

Kubernetes:

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
~~~

These values are illustrative only. Leave time for:

- Pre-SIGTERM hooks, if configured.
- Readiness propagation and halting new traffic.
- Stopping listeners and waiting on in-flight handlers.
- Committing/acking and flushing outputs.
- Closing connection pools and the JVM.

Do not set the lifecycle timeout equal to `terminationGracePeriodSeconds`. Once the grace period expires, kubelet can send `SIGKILL`; the application gets no chance to clean up. Keep enough buffer to complete final phases.

Note that `timeout-per-shutdown-phase` is a budget per phase, not the total shutdown timeout of the entire application. If multiple phases wait, total time can exceed the configured value. Sum the budgets of actual phases, preStop time, and cleanup, and ensure the total fits inside the termination grace period.

### 7.1. Maximum Processing Time Must Be Bounded

If a handler can hang indefinitely on an HTTP or database call, drain time cannot be calculated. Configure timeouts for:

- HTTP client connect/read/request.
- Database queries, lock waits, and transactions.
- Futures or executor tasks.
- Retry delays and total retry duration.
- External processes or file operations.

A dependency timeout must fit the remaining deadline. If 10 seconds remain in drain, do not start a downstream call with a 60-second timeout.

## 8. How Does Kubernetes Send Termination Signals?

When a Pod is deleted or replaced, Kubernetes starts termination. A `preStop` hook (if declared) runs before the container receives `SIGTERM`, and hook execution counts toward `terminationGracePeriodSeconds`. The runtime then sends `SIGTERM` to the process; once the grace period expires, a still-running container may receive `SIGKILL`.

Deployment example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: example/order-consumer:1.0.0
          ports:
            - name: management
              containerPort: 8081
          lifecycle:
            preStop:
              httpGet:
                path: /internal/drain
                port: management
~~~

`/internal/drain` is an application-built endpoint, not a default Spring Boot endpoint. This endpoint must be secured, restricted to kubelet or the management network, and must trigger a genuine drain workflow: readiness, stopping message intake, and waiting with a deadline. If no custom drain endpoint exists, rely on lifecycle mechanisms that handle `SIGTERM` directly and avoid declaring hooks that mistakenly assume readiness stops consumers.

Container images should run the Java process in exec form so it receives `SIGTERM` properly. If a shell script runs as PID 1 without forwarding signals, the JVM may miss the signal; use `exec` in the entrypoint or an appropriate init process.

## 9. Kafka: Stopping Consumers, Committing Offsets, and Rebalancing

A Kafka consumer reads records per partition and tracks progress using consumer group offsets. When the application stops:

1. The listener container stops polling or stops receiving new records per its lifecycle.
2. Records currently handled by the listener must finish or be aborted.
3. Offsets are committed according to the configured acknowledgment/commit mode.
4. The consumer leaves the group; partitions can be assigned to other consumers.
5. Uncommitted records may be re-read by the new consumer.

With the Spring Cloud Stream Kafka binder, the binder manages listener containers and interacts with Spring Kafka. Do not spin up a separate `KafkaConsumer` to commit offsets for a binding without clearly designed ownership.

### 9.1. Committing After Processing

The usual goal is to commit offsets only after the handler finishes the work requiring protection. If the process dies after the database commits but before the offset commits, the record may be re-read. Hence database operations must be idempotent by event ID or business key.

If offsets commit before side effects complete, a crash can prevent redelivery even though business work failed to finish. Choose acknowledgment semantics based on acceptable message loss vs. duplication tolerances.

### 9.2. Poll Interval and Long-Running Handlers

Kafka uses `max.poll.interval.ms` to bound the interval between polls. If a synchronous handler takes too long, the consumer may be considered stalled and partitions rebalanced before the handler finishes. Commits may then fail and records may be redelivered.

Mitigations:

- Keep processing duration within measured limits.
- Tune `max.poll.interval.ms` and `max.poll.records` to actual load.
- Avoid feeding an entire huge batch into a slow handler.
- If processing asynchronously, manage offsets/acks strictly in partition order and per container semantics.
- Monitor rebalances, commit failures, and lag.

Do not raise `max.poll.interval.ms` just to mask a hanging handler. Bound dependency timeouts and monitor p95/p99 processing times.

### 9.3. Rebalancing and Duplicates

When a Pod leaves a consumer group, partitions are reassigned. A record already processed but uncommitted may be picked up by another consumer. This is part of at-least-once processing.

Producer idempotence prevents duplicates caused by producer retries within the Kafka protocol; it does not make a consumer's database side effects exactly-once. Kafka transactions can coordinate consume-transform-produce within Kafka, but do not automatically cover an arbitrary database or HTTP API.

### 9.4. Batch Listeners

If a single poll returns multiple records, determine which records have completed before stopping. Committing the whole batch when only part succeeded can skip failed records; skipping commit on the whole batch can cause succeeded records to be redelivered. Use the binder/container's error handling, batch acknowledgment, and retry semantics rather than manually guessing offsets.

## 10. RabbitMQ: Consumer Cancel and Unacknowledged Deliveries

RabbitMQ tracks unacknowledged deliveries. When a consumer channel/connection closes, remaining unacknowledged deliveries are typically returned to a state ready for delivery to another consumer. A new consumer can then receive those messages again.

A graceful shutdown workflow needs to:

- Stop new deliveries by stopping/canceling listener consumers.
- Let running callbacks complete.
- Acknowledge after business commits succeed.
- Allow unacknowledged deliveries to requeue when the channel closes.
- Avoid auto-ack when messages must be protected during processing.

### 10.1. How Prefetch Affects In-Memory Messages

Prefetch limits how many unacknowledged deliveries a broker can push ahead to a consumer. Excessively large prefetch can make an instance hold many messages in memory at shutdown, whereas overly small prefetch can reduce throughput.

Example: a consumer has prefetch 100 and processes 20 messages concurrently. When the Pod stops, account for both active messages and delivered messages sitting in the listener's buffer. If the channel closes before they are acked, unacknowledged messages may be redelivered.

Tune prefetch based on:

- Average and p99 processing times.
- Actual listener concurrency.
- Memory footprint per message.
- Unacked message count at shutdown.
- Business handler tolerance for duplicates.

### 10.2. Ack and Side Effects

With manual acknowledgment, send ack only after the business transaction commits. With container-managed acknowledgment, understand the exact ack mode and exception behavior of Spring AMQP/Rabbit binder.

Never ack in a `finally` block. If a handler throws an exception due to a database timeout, acking in `finally` confirms the message even though business logic failed.

When stopping listeners, Spring AMQP containers have mechanisms to stop consumers and wait for callbacks according to the container lifecycle. Timeouts, requeuing, and force-stop behavior can depend on container type and Spring AMQP version. Test against the exact listener container type in use; do not extrapolate from another RabbitMQ configuration.

## 11. Pulsar: Acknowledgment, Negative Acknowledgment, and Redelivery

Pulsar subscriptions track acknowledged messages. When a consumer closes, unacknowledged messages remain incomplete on the subscription and can be redelivered per the subscription/client redelivery policy.

Concepts to distinguish:

- Individual acknowledgment: Acknowledges a single message.
- Cumulative acknowledgment: Acknowledges a message and all preceding messages in supported subscription modes.
- Negative acknowledgment: Instructs the broker to redeliver the message per the redelivery policy.
- Acknowledgment timeout: Messages unacked within a configured window can be redelivered.
- Batch acknowledgment: A batch may be acknowledged according to client semantics.

For shutdown, stop the consumer from receiving new messages, wait for active handlers, ack completed messages, and let unacked messages be redelivered. Do not acknowledge before side effects finish merely to shrink backlog.

Not every subscription type supports the same acknowledgment modes or cumulative ack semantics. Check the subscription type (Exclusive, Failover, Shared, Key_Shared), batch settings, and Pulsar client version.

### 11.1. Ack Timeout Is Not Shutdown Timeout

Ack timeout is a broker/client redelivery policy for unacknowledged messages. Shutdown timeout is how long the process is allowed to drain before termination. These two settings solve different problems.

If ack timeout is shorter than legitimate processing time, messages may be redelivered while the original consumer is still working. If shutdown timeout is too short, the application may be killed before finishing. Configure both around processing time distributions and duplicate policies.

## 12. Do Not Let Async Work Escape the Ack Boundary

A common mistake is a function receiving a message, submitting work to an executor, and returning immediately:

~~~java
@Bean
Consumer<OrderAccepted> unsafeConsumer(
        Executor executor, OrderService orderService) {
    return event -> executor.execute(() -> orderService.process(event));
}
~~~

The binder may consider the handler done as soon as `execute()` returns, while the business task is still running. If the message is acked/committed and the process is then killed, the task can be lost and the broker will not redeliver the message.

When processing asynchronously, keep the acknowledgment boundary open until the task actually finishes. You can use asynchronous result APIs supported by the framework/binder in your version, or design a durable worker queue. Do not assume every `void`-returning `Consumer` tracks futures submitted internally.

As a guiding principle: increment the in-flight counter when the task begins, and decrement it only after the future completes. During shutdown, stop submitting new tasks and wait for running futures within the deadline; unfinished tasks must remain retryable and never be acked prematurely.

## 13. Producers Sending Output During Shutdown

A consumer may finish its input while still sending output to another broker. Distinguish:

- Message constructed in memory.
- Send submitted to the producer.
- Broker received and confirmed the publish.
- Downstream consumer processed the output.

These states are not equivalent. If the application uses a producer client directly, flush or await pending send futures/callbacks before closing the producer. For binder-managed producers, let the binder execute lifecycle cleanup and do not manually close underlying clients.

RabbitMQ publisher confirms indicate the broker acknowledged the publish per configuration; Pulsar send futures report client API send outcomes; Kafka producer callbacks/futures report send outcomes. None of them prove a downstream business consumer has finished.

If the input commit succeeds while the output publish fails, the link between steps can break unless coordinated by an appropriate transaction. The outbox pattern is a common choice: write the business change and an outbox record in the same database transaction, then relay-publish the outbox record with retries/idempotency. This enables publish recovery after restarts.

## 14. Idempotency to Handle Redelivered Messages

Graceful shutdown does not eliminate all duplicates. Example:

1. Consumer receives event `evt-123`.
2. Database updates the order successfully.
3. Process receives `SIGKILL` before ack/commit.
4. Broker redelivers `evt-123` to another instance.

If the handler is not idempotent, the order might be charged or notified twice.

A common pattern is storing processed event IDs in the same transaction as the business update:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudo-code:

~~~java
@Transactional
public void processAndCommit(OrderAccepted event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderService.apply(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId(), Instant.now())
    );
}
~~~

In production, the check-and-insert must be protected by a unique constraint/transaction to handle two concurrent consumers. Merely calling `existsById` followed by insert without a unique constraint suffers from race conditions.

If a duplicate arrives after the business update already committed, the handler returns success without repeating side effects; the binder can ack/commit the record. Retention of idempotency keys must exceed the maximum possible retry/replay window.

## 15. Transactions and Outbox During Shutdown

If a handler executes a database transaction:

- Do not ack before the transaction commits.
- If the transaction rolls back, the message must remain retryable.
- If the process dies mid-transaction, the database rolls back when the connection closes or the transaction times out.
- If the database commits but broker ack fails to complete, duplicates can still happen.

If a handler emits output:

- Sending directly after commit leaves a gap between database commit and broker publish.
- Sending output before commit can emit an event for a change that later rolls back.
- Use an outbox to write the outbound event in the same business transaction; relay-publish afterward.

Do not call this a distributed transaction when it only involves a database transaction and a broker publisher. Cross-system exactly-once requires specific coordination mechanisms and usually carries strict limitations.

## 16. Retries, DLQ, and Shutdown

When a handler fails during shutdown:

- Transient errors may be retried according to binder policy.
- Unacknowledged messages may be redelivered by the broker after the consumer closes.
- Poison or schema-incompatible messages may go to the DLQ via the error handler.
- Retry delays can exceed the shutdown window.

Do not wait indefinitely on retries during shutdown. Stop intake, finish active handlers within the deadline, and let the broker/framework handle incomplete messages per configured semantics. DLQs should be reserved for messages requiring special handling, not a dumping ground simply because a Pod is shutting down.

With Kafka, offset commits and retry topics can route records to another processing flow. With RabbitMQ, requeuing or dead-letter routing depends on reject/nack and queue policies. With Pulsar, negative acknowledgments, retry-letter topics, and dead-letter policies have their own semantics. Verify against your exact binder.

## 17. Readiness and preStop in Kubernetes

Even a message-processing Pod that receives no Service traffic may still need readiness for rollouts, yet readiness does not directly control consumer groups. You can build an internal endpoint to:

1. Mark the instance `REFUSING_TRAFFIC`.
2. Request binding pause/stop via a supported API.
3. Wait until the in-flight counter reaches 0 or the deadline expires.
4. Return the result to the hook.

A drain endpoint must be secured, idempotent, and time-bounded. If called multiple times, do not start multiple concurrent waits. If the hook times out, `SIGTERM` must still trigger a safe shutdown path.

`preStop` should not use an arbitrary `sleep` assuming endpoint routing has finished propagating. Measure actual propagation time and design hooks around real application/platform signals.

## 18. Shutdown During Rolling Deployments and Scale-Down

During a rolling deployment, old and new Pods may coexist in a consumer group briefly. As old consumers stop, Kafka may rebalance partitions; RabbitMQ may shift unacked deliveries to other consumers; Pulsar may redeliver unacked messages.

For safe rollouts:

- Deploy new consumers schema-compatible with existing messages.
- Ensure producers do not emit schemas/codecs unreadable by old or new consumers during transition.
- Choose `maxSurge`/`maxUnavailable` and replica counts matched to broker capacity.
- Set `terminationGracePeriodSeconds` comfortably above p99 drain duration.
- Monitor rebalances, unacked queues, Pulsar backlogs, and DLQs during rollout.
- Keep handlers idempotent because messages may move between instances.

`PodDisruptionBudget` limits simultaneous voluntary Pod disruptions, but does not guarantee handlers finish or messages avoid duplication.

## 19. Observing and Alerting on Shutdown

Record at least:

| Signal | Meaning |
|---|---|
| Shutdown started timestamp | Time `SIGTERM` or drain request arrived |
| Intake stopped timestamp | Time listeners stopped accepting new work |
| In-flight count | Number of handlers still running |
| Longest in-flight duration | Longest active handler |
| Drain duration | Total drain elapsed time |
| Drain timeout count | Number of times deadline expired with unfinished work |
| Ack/commit failures | Messages processed but acknowledgment failed |
| Producer flush duration/errors | Whether in-flight outbound publishes completed |
| Redelivery/duplicate count | Impact after consumer shutdown |

Logs should include application instance, binding name, consumer group/subscription, event ID (if safe), in-flight count, and remaining deadline. Do not log sensitive payloads.

A successfully completed shutdown does not necessarily have an in-flight count of 0 if the deadline expired; that case must be logged explicitly, expecting the broker to redeliver unacked messages. Never emit a generic `Shutdown complete` log while hiding unfinished work counts.

## 20. Testing Graceful Shutdown

Unit tests for a tracker only verify counters and timeouts. Integration tests with real binders/brokers or containers are needed to verify acknowledgment and redelivery.

### 20.1. Test Scenarios

| Scenario | How to Reproduce | Expected Outcome |
|---|---|---|
| Stop with no messages | Send `SIGTERM` while idle | Process exits quickly, connections close cleanly |
| Stop while handler is running | Handler waits on a latch or simulated slow downstream | Handler completes before deadline, message is acked/committed |
| Stop after DB commit before ack | Inject test pause after commit | Message may be redelivered; idempotency prevents duplicate side effects |
| Handler exceeds deadline | Hold handler longer than grace period | Process stops at deadline; unacked message is redelivered |
| Producer sending output | Hold send future incomplete | Flushes/awaits confirmation or outbox recovers after restart |
| Consumer stops mid-batch | Send multiple records then stop | Only confirmed portion is committed; remainder is redelivered |
| Multi-Pod rolling update | Scale or deploy under load | No lost messages; duplicates handled safely |
| SIGKILL | Sudden hard kill | No graceful cleanup expected; broker redelivery and idempotency protect state |

### 20.2. Testing Kafka

- Send records to a topic while handlers are running.
- Trigger shutdown and observe the consumer group.
- Verify committed offsets and partition reassignment.
- Stop after side effects but before commit to verify duplicate handling.
- Check rebalancing and `max.poll.interval.ms` with long-running handlers.

### 20.3. Testing RabbitMQ

- Send messages and hold the listener callback open.
- Stop the application context.
- Observe consumer cancellation and unacked messages.
- Verify unacked messages are requeued when the channel closes.
- Verify acked messages are not redelivered.

### 20.4. Testing Pulsar

- Send messages to a durable subscription.
- Stop the consumer while the handler is running.
- Verify acked messages are not redelivered.
- Verify unacked messages can still be redelivered.
- Test ack timeout, negative ack, and batch acknowledgment per subscription type.

## 21. Common Implementation Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Pod killed by SIGKILL with active handlers | Grace period shorter than processing time | Measure p99, bound dependency timeouts, and increase grace period appropriately |
| Readiness DOWN yet consumers still receive messages | Readiness only governs Service traffic | Stop bindings/listeners through lifecycle |
| Messages duplicated after rollout | Side effects finished while ack/commit did not | Add idempotency keys and proper transaction boundaries |
| Messages lost after restart | Ack/commit occurred before side effects completed | Ack only after the business boundary |
| Shutdown waits forever | Handler or dependency has no timeout | Set deadlines and per-dependency timeouts |
| Producer output not finished sending | Producer closed too early | Flush/await sends or use outbox; let binders manage binder producers |
| Continuous consumer group rebalancing | Handler too slow or shutdowns/scaling too frequent | Check poll interval, processing time, and rollout strategy |
| RabbitMQ has many unacked messages at Pod stop | Large prefetch or slow callbacks | Tune prefetch/concurrency and drain properly |
| Pulsar redelivers while old handler still runs | Short ack timeout or consumer has not acked yet | Align timeout with processing and make handlers idempotent |
| Messages routed to DLQ at Pod stop | Shutdown exceptions classified as poison failures | Separate shutdown exceptions from business failures; configure retry/requeue properly |
| Async tasks lost after handler returns | Ack happens before futures complete | Keep acknowledgment boundary open until tasks complete |

## 22. Design Principles

1. Distinguish readiness, web server graceful shutdown, and binder/listener lifecycles.
2. Stop intake before closing dependencies needed by handlers.
3. Set finite timeouts on handlers and all downstream calls.
4. Track in-flight work and wait within a bounded deadline.
5. Acknowledge/commit only after side effects cross the completion boundary.
6. Never ack in `finally` or return success while async tasks are still running.
7. Await outbound publishes according to actual semantics; use an outbox when publish recovery is needed.
8. Make handlers idempotent because duplicates can still occur.
9. Set Kubernetes grace periods larger than total drain and cleanup time.
10. Test each binder individually because Kafka, RabbitMQ, and Pulsar have distinct semantics.
11. Let binders manage binder-owned resources; do not arbitrarily close underlying clients.
12. Monitor drain timeouts, in-flight counts, commit/ack failures, and redeliveries after rollouts.

## Official References

- [Spring Boot - Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): Graceful shutdown of the embedded web server.
- [Spring Framework - Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): Lifecycle callbacks and `SmartLifecycle`.
- [Spring Cloud Stream - Binding Lifecycle](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): Observing and controlling bindings via supported APIs.
- [Apache Kafka Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs): `max.poll.interval.ms`, `max.poll.records`, and commit behavior.
- [Spring for Apache Kafka - Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): Listener container lifecycle and acknowledgment.
- [RabbitMQ Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): Ack, nack, unacked deliveries, and publisher confirmations.
- [Spring AMQP - Listener Container](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): Listener containers, concurrency, and lifecycle.
- [Apache Pulsar - Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): Subscriptions, acknowledgments, and redelivery.
- [Kubernetes - Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): Termination grace period, `preStop`, and `SIGTERM`.
