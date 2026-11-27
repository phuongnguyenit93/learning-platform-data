# Testing Graceful Shutdown with Pending Messages in Spring Integration Runtime

## 1. Practice Problem and Target Outcome

In the **SPRING_INTEGRATION_RUNTIME** module, messages flow across **channels, endpoints, consumers, pollers, and executors**, may reside in a **MessageStore**, and eventually write to a DB or call external services. When an instance receives `SIGTERM` during a rollout or scale-down, not every message has finished processing. Some sit in a **`QueueChannel`**, some have been dequeued while the handler is still running, and some have committed to the DB while the broker still awaits an acknowledgment.

This synthesis lab focuses on a **test-verifiable** objective:

> When asked to stop, the system stops accepting new work, continues processing already-accepted work within a finite deadline, and **tells the truth** about unfinished messages. If forced to stop with backlog remaining, the architecture must recover from a durable source/store; graceful shutdown alone never replaces durability.

After this lesson, you will have:

- A **Spring Integration Java DSL fixture** using `DirectChannel` → `QueueChannel` → polling consumer.
- An **ingress gate** simulating the intake cutoff point with an explicit pause action.
- A **`MessageHandler` using `CountDownLatch`** to hold one message in flight and build measurable backlog.
- **JUnit 5 tests** covering an undrained queue, paused ingress, successful drain, timeout when a handler blocks, and stopping the consumer.
- A coordinator model distinguishing **`DRAINED`** from **`TIMED_OUT_WITH_PENDING`** instead of treating timeout expiration as success.
- Advanced test designs for **JDBC `MessageStore`, brokers, transactions, retries, `errorChannel`, idempotency, crash/restart, and Kubernetes grace periods**.

**Technical scope:** Java DSL examples target Spring Boot 3, Spring Integration 6.x, JDK 17+, and JUnit 5; verify exact APIs and configuration against your actual BOM. Scenarios involving real DBs, brokers, or containers are laid out as fault-injection procedures because in-memory tests alone cannot prove durability after JVM death.

## 2. Defining "Graceful" Correctly Before Writing Tests

Suppose an instance has this topology:

~~~mermaid
flowchart LR
    SRC["Source / Broker"] --> IN["Ingress endpoint / gate"]
    IN --> C["DirectChannel"]
    C --> Q["pendingQueue - QueueChannel"]
    Q --> P["workConsumer - poller"]
    P --> H["Business handler"]
    H --> DB[("Business DB")]
    H --> EXT["External API"]
    H -. "Exception" .-> ERR["Retry / errorChannel"]
~~~

When the application is asked to shut down:

| Work Area | State to Observe | Example |
| --- | --- | --- |
| **Ingress** | Is it still accepting new messages? | Broker listener, file adapter, gateway, or gate |
| **Queued** | How many messages remain un-dequeued? | `QueueChannel`, `ChannelMessageStore` |
| **In-flight** | How many handlers started yet have not finished? | Polling consumer, executor workers |
| **Unacked** | Delivered by source yet awaiting ack/offset commit? | Kafka, JMS, AMQP |
| **Pending durable recovery** | Durably stored work awaiting next run? | JDBC queue, inbox/outbox, retry journal |
| **Unknown external effects** | Remote effect executed yet response lost? | HTTP payment, outbound messaging |

A test that merely calls:

~~~java
consumer.stop();
assertFalse(consumer.isRunning());
~~~

is **insufficient** to claim a graceful-shutdown test. It inspects only the consumer's lifecycle flag. Messages may still sit in the queue, inside an executor, or mid-execution in an already-started task.

### Invariants We Will Test

1. **After pause:** controlled ingress stops accepting new messages.
2. **During drain:** the consumer remains allowed to process queued work.
3. **Before deadline:** if queued = 0 and in-flight = 0, we can conclude **in-scope test work has drained**.
4. **After deadline:** if queued or in-flight work remains, the outcome is **`TIMED_OUT_WITH_PENDING`**, not **`DRAINED`**.
5. **When consumer stops:** no new polls start per endpoint contract; already-running tasks are tracked separately.
6. **On restart:** work that must not be lost is preserved by a **durable source/store**, not merely an in-memory `QueueChannel`.
7. **On redelivery:** two deliveries with the same `eventId` never cause two **business side effects**.

**`DRAINED`, `TIMED_OUT_WITH_PENDING`, and `DATA_LOSS_RISK` are lab-defined labels**, not built-in Spring Integration enums.

## 3. Why Use `CountDownLatch` Instead of `Thread.sleep`?

To test a queue holding pending messages during shutdown, you must first **create that state deterministically**.

A flaky test:

~~~java
input.send(message);
Thread.sleep(100);
assertEquals(2, pendingQueue.getQueueSize());
~~~

depends on CI speed, `TaskScheduler` timing, free threads, and handler duration.

Replace it with two signals:

- **`firstStarted`**: the handler has actually picked up the first message.
- **`releaseFirst`**: the test controls when the handler is allowed to proceed.

~~~mermaid
sequenceDiagram
    participant T as JUnit
    participant Q as QueueChannel
    participant P as Polling Consumer
    participant H as Blocking Handler
    T->>Q: Enqueue EV-1, EV-2, EV-3
    T->>P: start()
    P->>Q: receive EV-1
    Q-->>P: EV-1
    P->>H: handle EV-1
    H-->>T: firstStarted.countDown()
    Note over H: Wait on releaseFirst
    Note over Q: EV-2 and EV-3 still queued
    T->>T: Assert queued=2, in-flight=1
    T->>H: releaseFirst.countDown()
    H-->>P: EV-1 completed
    P->>Q: receive EV-2, then EV-3
~~~

With **one synchronous polling consumer**, while `EV-1` is held inside the handler, `EV-2` and `EV-3` have not been polled yet. The test observes this snapshot **without guessing processing durations**.

### Thread Boundary in the Lab

~~~text
JUnit thread:
    gate.submit(EV-1/EV-2/EV-3)
      → DirectChannel
      → QueueChannel enqueue
    returns

TaskScheduler / polling consumer thread:
    QueueChannel.receive()
    → BlockingOrderHandler.handleMessage()
    → success / failure
~~~

**`send()` returning true** means the channel accepted the message per contract—it **does not** prove the business handler completed. You must observe **queue depth, in-flight count, and final outcomes**.

## 4. Project Setup and Dependencies

A Maven/Gradle Spring Boot project needs:

| Dependency | Role |
| --- | --- |
| **spring-boot-starter-integration** | Spring Integration core and Boot configuration |
| **spring-integration-test** | `@SpringIntegrationTest`, `MockIntegrationContext`, and test utilities |
| **spring-boot-starter-test** | JUnit 5 and Spring Test |
| **spring-boot-starter-jdbc** | For advanced JDBC/transaction tests |
| **spring-integration-jdbc** | For `JdbcChannelMessageStore` when persistent queues are needed |
| **PostgreSQL driver / Testcontainers** | For DB tests surviving application restarts |

Illustrative Gradle config for the in-memory lab:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version-from-project>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.integration:spring-integration-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Strings like `<...>` in Gradle are placeholders**, not real versions; pick versions from your project's BOM. Never mix Spring Integration 5.x and 6.x arbitrarily.

Place the Java classes below in the same package:

~~~text
src/test/java/.../shutdown/
  ShutdownLabConfiguration.java
  IngressGate.java
  BlockingOrderHandler.java
  GracefulDrainTest.java
~~~

## 5. Creating an Ingress Gate to Simulate Stopping Intake

The lab needs no real broker. **`IngressGate`** models the contract "once paused, callers cannot enqueue new messages."

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

final class IngressGate {
    private final MessageChannel input;
    private boolean accepting = true;

    IngressGate(MessageChannel input) {
        this.input = input;
    }

    synchronized boolean submit(String eventId) {
        if (!accepting) {
            return false;
        }
        return input.send(
                MessageBuilder.withPayload(eventId)
                        .setHeader("eventId", eventId)
                        .build());
    }

    synchronized void pause() {
        accepting = false;
    }

    synchronized void resume() {
        accepting = true;
    }

    synchronized boolean isAccepting() {
        return accepting;
    }
}
~~~

**Why `synchronized`?** Synchronization prevents `pause` from interleaving between checking `accepting` and calling `send` on another request. In this fixture, the path after `input` is `DirectChannel` → `QueueChannel`, so enqueuing completes synchronously.

**Limitation:** `Gate` is **custom application code**, not `SourcePollingChannelAdapter.stop()` or a broker consumer stop. In production you must stop **the actual inbound endpoint/container** and verify in-flight deliveries. Any caller sending directly to `input` bypasses the gate.

## 6. Creating a Handler That Holds a Message In Flight

The handler uses these signals:

- **`firstStarted`**: `EV-1` has started.
- **`releaseFirst`**: test allows `EV-1` to continue.
- **`inFlight`**: count of currently executing handlers.
- **`allCompleted`**: all three messages have finished processing.

~~~java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

final class BlockingOrderHandler implements MessageHandler {
    final CountDownLatch firstStarted = new CountDownLatch(1);
    final CountDownLatch releaseFirst = new CountDownLatch(1);
    final CountDownLatch allCompleted = new CountDownLatch(3);

    private final AtomicInteger invocations = new AtomicInteger();
    private final AtomicInteger inFlight = new AtomicInteger();
    private final Queue<String> completed = new ConcurrentLinkedQueue<>();

    @Override
    public void handleMessage(Message<?> message) {
        inFlight.incrementAndGet();
        boolean success = false;
        try {
            int visit = invocations.incrementAndGet();
            if (visit == 1) {
                firstStarted.countDown();
                if (!releaseFirst.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Test did not release first message");
                }
            }

            completed.add((String) message.getPayload());
            success = true;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Handler interrupted before completion", interrupted);
        } finally {
            inFlight.decrementAndGet();
            if (success) {
                allCompleted.countDown();
            }
        }
    }

    int activeCount() {
        return inFlight.get();
    }

    int completedCount() {
        return completed.size();
    }

    Queue<String> completedEvents() {
        return completed;
    }
}
~~~

**Limitations of this test probe:**

1. The handler blocks the **first invocation**, regardless of `eventId`. Every test needs an isolated fixture.
2. `inFlight` wraps **`handleMessage`**; it does not count tasks waiting in an executor, source ACKs, or DB commits in outer proxies.
3. `completed` is an **in-RAM** collection, not committed business state.
4. Tests must always release latches in cleanup so nothing waits forever.
5. Adding `ExecutorChannel` or multiple polling consumers changes queue depth and ordering; update assertions to match the topology.

## 7. Building an `IntegrationFlow` with a Real Polling Consumer

Two flows: **`ingressFlow`** enqueues messages, and **`processingFlow`** polls and invokes `BlockingOrderHandler`. The endpoint gets ID **`workConsumer`** so tests can start and stop it.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ShutdownLabConfiguration {

    @Bean("ingressInput")
    MessageChannel ingressInput() {
        return new DirectChannel();
    }

    @Bean("pendingQueue")
    QueueChannel pendingQueue() {
        // In-memory queue: not durable across JVM restarts.
        return new QueueChannel();
    }

    @Bean
    IngressGate ingressGate(
            @Qualifier("ingressInput") MessageChannel ingressInput) {
        return new IngressGate(ingressInput);
    }

    @Bean
    BlockingOrderHandler blockingOrderHandler() {
        return new BlockingOrderHandler();
    }

    @Bean
    IntegrationFlow ingressFlow() {
        return IntegrationFlow.from("ingressInput")
                .channel("pendingQueue")
                .get();
    }

    @Bean
    IntegrationFlow processingFlow(BlockingOrderHandler handler) {
        return IntegrationFlow.from("pendingQueue")
                .handle(handler, endpoint -> endpoint
                        .id("workConsumer")
                        .poller(Pollers.fixedDelay(25)
                                .maxMessagesPerPoll(1)))
                .get();
    }
}
~~~

Inside this fixture:

- **`DirectChannel`** adds no thread boundary between ingress and enqueue.
- **`QueueChannel`** holds pending messages and creates a producer/consumer boundary.
- **`PollingConsumer`** pulls messages on a fixed delay and invokes the handler.
- **`maxMessagesPerPoll(1)`** leaves `EV-2` and `EV-3` queued while `EV-1` is blocked.
- **ID `workConsumer`** targets the exact endpoint lifecycle rather than guessing DSL-generated names.

**Scope:** `fixedDelay(25)` passes milliseconds in typical DSL overloads; verify exact overloads and units across API/version changes. This is a lab configuration; production also requires transactions, capacity bounds, and error handling.

### Do Not Attach Extra "Observer" Subscribers to `DirectChannel`

`DirectChannel` normally dispatches each message to **one subscriber**. Adding a debug handler can compete with the business flow. To observe without altering dispatch, use **`WireTap`** or a dedicated test channel.

## 8. JUnit 5: Building Backlog, Pausing Ingress, and Draining

Use **`@SpringIntegrationTest(noAutoStartup = "workConsumer")`** so the polling endpoint does not start immediately on context creation; the test starts it explicitly. **`@DirtiesContext`** isolates `QueueChannel` and `CountDownLatch` instances across test methods.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.Lifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ShutdownLabConfiguration.class)
@SpringIntegrationTest(noAutoStartup = "workConsumer")
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GracefulDrainTest {

    @Autowired
    IngressGate gate;

    @Autowired
    @Qualifier("pendingQueue")
    QueueChannel pendingQueue;

    @Autowired
    BlockingOrderHandler handler;

    @Autowired
    @Qualifier("workConsumer")
    Lifecycle consumer;

    @AfterEach
    void cleanup() {
        // Do not leave worker blocked if an assertion fails.
        handler.releaseFirst.countDown();
        consumer.stop();
    }

    @Test
    void stoppedConsumerDoesNotDrainQueue() throws Exception {
        assertFalse(consumer.isRunning());
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));

        assertEquals(3, pendingQueue.getQueueSize());
        assertEquals(0, handler.activeCount());
        gate.pause();
        assertFalse(gate.submit("EV-4"));
        assertEquals(3, pendingQueue.getQueueSize());
        assertEquals(0, handler.completedCount());
        assertFalse(handler.allCompleted.await(
                150, TimeUnit.MILLISECONDS));
    }

    @Test
    void pauseIngressAndDrainAllPendingMessages() throws Exception {
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));
        assertEquals(3, pendingQueue.getQueueSize());

        gate.pause();
        assertFalse(gate.isAccepting());
        assertFalse(gate.submit("EV-4"));

        // Keep consumer running during the drain phase.
        consumer.start();
        try {
            assertTrue(handler.firstStarted.await(
                    3, TimeUnit.SECONDS));
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());
            assertEquals(0, handler.completedCount());

            handler.releaseFirst.countDown();
            assertTrue(handler.allCompleted.await(
                    5, TimeUnit.SECONDS));

            assertEquals(0, pendingQueue.getQueueSize());
            assertEquals(0, handler.activeCount());
            assertEquals(3, handler.completedCount());
            assertEquals(Set.of("EV-1", "EV-2", "EV-3"),
                    new HashSet<>(handler.completedEvents()));

            consumer.stop();
            assertFalse(consumer.isRunning());
        } finally {
            handler.releaseFirst.countDown();
        }
    }

    @Test
    void deadlineCanExpireWhileMessagesRemain() throws Exception {
        assertTrue(gate.submit("EV-1"));
        assertTrue(gate.submit("EV-2"));
        assertTrue(gate.submit("EV-3"));
        gate.pause();

        consumer.start();
        try {
            assertTrue(handler.firstStarted.await(
                    3, TimeUnit.SECONDS));
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());

            boolean allDoneWithinBudget =
                    handler.allCompleted.await(
                            150, TimeUnit.MILLISECONDS);
            assertFalse(allDoneWithinBudget);
            assertEquals(2, pendingQueue.getQueueSize());
            assertEquals(1, handler.activeCount());

            // Cleanup: release worker before closing context.
            handler.releaseFirst.countDown();
            assertTrue(handler.allCompleted.await(
                    5, TimeUnit.SECONDS));
        } finally {
            handler.releaseFirst.countDown();
        }
    }
}
~~~

### Interpreting Each Test

| Test | State Constructed | Actual Conclusion |
| --- | --- | --- |
| `stoppedConsumerDoesNotDrainQueue` | Queue holds 3; consumer never started | The queue does not drain itself without a running polling consumer |
| `pauseIngressAndDrainAllPendingMessages` | Stopped new intake, held `EV-1` in flight with two queued, then released worker | Within the **3-message fixture**, all three complete, queue empties, and in-flight hits 0 |
| `deadlineCanExpireWhileMessagesRemain` | Handler held across the trial deadline | Budget expiration can happen with items still queued/in-flight; must never report `DRAINED` |

**What the tests do not prove:** there is no broker, JDBC store, DB transaction, or external side effect. The consumer is started/stopped via lifecycle; ingress is a **simulated gate**. Proving graceful shutdown on a real pod requires additional integration tests against real transports and resources.

### Why Not Call `stop()` While the Handler Is Still Blocked?

Stopping a polling consumer while its handler awaits a latch makes behavior depend on lifecycle callbacks, executors, and `TaskScheduler`—or hang if the test has not released the worker yet. That test focuses on **timeout while pending**, so it releases the worker in `finally`. Stopping while tasks are in flight belongs in its own dedicated test with controlled deadlines, interrupts, and cleanup.

### Why Use Isolated Contexts?

Spring Test caches `ApplicationContext` by default. Without isolation, `CountDownLatch` and `QueueChannel` state from one test can leak into the next. **`@DirtiesContext`** keeps tests clear at the cost of context restarts; large suites can reset fixtures manually if they guarantee zero in-flight tasks remain.

## 9. Queued Does Not Equal In-Flight, Nor Committed

At the instant `EV-1` has been dequeued and is awaiting `releaseFirst`:

~~~text
ingress accepting = false
pendingQueue size = 2
handler in-flight = 1
completed count = 0
~~~

**Total unfinished work is 3**, not 2. Queue depth counts only waiting items, excluding items currently inside the handler.

Once the handler is released and all three completions finish:

~~~text
ingress accepting = false
pendingQueue size = 0
handler in-flight = 0
completed count = 3
~~~

This is **`DRAINED` within lab scope**. Production must also inspect queued executor tasks, unacked broker deliveries, DB commits, pending outbox entries, and unconfirmed external effects.

### Single Snapshots Can Race

Between **`QueueChannel.receive()`** and the handler incrementing `inFlight`, a brief window exists where queue depth dropped while the handler has not yet marked itself active. Therefore:

~~~java
boolean drained = pendingQueue.getQueueSize() == 0
        && handler.activeCount() == 0;
~~~

**is not an airtight condition** while the consumer can still dequeue. In the lab, `CountDownLatch` **`allCompleted`** knows there are exactly three messages; production needs **ownership tracking spanning dequeue → commit, ack/transaction states**, or an explicit quiesce barrier.

Moreover, when a handler uses AOP transactions, the DB commit can happen **after the method returns**, so in-method `inFlight` tracking may end before commit. Base business completion on **committed/acked** points or durable state.

## 10. Modeling Shutdown Outcomes Instead of Returning a Boolean

A shutdown coordinator should distinguish:

| Application-Defined Outcome | Meaning | Required Action |
| --- | --- | --- |
| **`DRAINED`** | All in-scope work finished with confirmed outcomes | Close downstream and resources |
| **`TIMED_OUT_WITH_DURABLE_PENDING`** | Budget expired; remaining items live durably and can replay | Shut down instance; let a new worker take ownership |
| **`TIMED_OUT_WITH_UNACKED`** | Source still holds unacked deliveries per contract | Monitor redelivery after restart |
| **`RECONCILIATION_REQUIRED`** | External side effect status unknown | Query provider by `operationId`; do not blindly replay |
| **`DATA_LOSS_RISK`** | Work lives only in RAM while source may have acked | Never report safe; fix durable handoff |
| **`FAILED_TO_QUIESCE`** | A producer/replica is still admitting messages | Never infer drained from a `queueDepth` snapshot |

These are **lab-defined labels**, not built-in Spring Integration enums.

### What Should a Snapshot Contain?

~~~java
record DrainSnapshot(
        boolean ingressPaused,
        long queuePending,
        long handlersInFlight,
        long executorQueued,
        long sourceUnacked,
        long unresolvedEffects) {

    boolean noKnownPendingWork() {
        return ingressPaused
                && queuePending == 0
                && handlersInFlight == 0
                && executorQueued == 0
                && sourceUnacked == 0
                && unresolvedEffects == 0;
    }
}
~~~

- **`queuePending`** must be inspected non-destructively; never call `receive()` just to count.
- **`handlersInFlight`** must cover the full window owned by the application, including commit when applicable.
- **`executorQueued`** is a separate task queue, excluded from `QueueChannel` depth.
- **`sourceUnacked`** depends on the broker/adapter; if unmeasurable, record **`UNKNOWN`** rather than filling in 0.
- **`unresolvedEffects`** includes unknown external API outcomes or work lacking durable state.

**An all-zero snapshot is still not absolute proof**: a gap may sit between dequeue and incrementing `inFlight`. Combine quiesce barriers, explicit work ownership, and durable outcome checks.

### Finite-Deadline Wait Helper

This example illustrates deadline management only—it does not stop adapters or make snapshots atomic:

~~~java
import java.time.Duration;
import java.util.function.Supplier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

enum WaitOutcome {
    NO_KNOWN_PENDING,
    DEADLINE_EXCEEDED,
    INTERRUPTED
}

record WaitResult(WaitOutcome outcome, DrainSnapshot last) {}

final class DrainDeadline {
    static WaitResult await(Supplier<DrainSnapshot> sample,
                            Duration budget) {
        long start = System.nanoTime();
        long limit = Math.max(0, budget.toNanos());

        for (;;) {
            DrainSnapshot snapshot = sample.get();
            if (snapshot.noKnownPendingWork()) {
                return new WaitResult(
                        WaitOutcome.NO_KNOWN_PENDING, snapshot);
            }

            long remaining = limit - (System.nanoTime() - start);
            if (remaining <= 0) {
                return new WaitResult(
                        WaitOutcome.DEADLINE_EXCEEDED, snapshot);
            }

            LockSupport.parkNanos(Math.min(
                    remaining, TimeUnit.MILLISECONDS.toNanos(20)));
            if (Thread.currentThread().isInterrupted()) {
                return new WaitResult(
                        WaitOutcome.INTERRUPTED, snapshot);
            }
        }
    }
}
~~~

**Never run this helper on the sole worker thread responsible for draining**: the waiting thread would block progress. In production, run it on a management thread alongside quiescence invariants. Even `NO_KNOWN_PENDING` must still be backed by business/durable state before declaring `DRAINED`.

### Testing the Deadline Helper

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class DrainDeadlineTest {

    @Test
    void returnsTimeoutWhenPending() {
        DrainSnapshot pending = new DrainSnapshot(
                true, 2, 1, 0, 0, 0);

        WaitResult result = DrainDeadline.await(
                () -> pending, Duration.ofMillis(50));

        assertEquals(
                WaitOutcome.DEADLINE_EXCEEDED, result.outcome());
        assertEquals(2, result.last().queuePending());
        assertEquals(1, result.last().handlersInFlight());
    }

    @Test
    void acceptsQuiescedSnapshot() {
        DrainSnapshot done = new DrainSnapshot(
                true, 0, 0, 0, 0, 0);

        WaitResult result = DrainDeadline.await(
                () -> done, Duration.ofMillis(50));

        assertEquals(
                WaitOutcome.NO_KNOWN_PENDING, result.outcome());
    }
}
~~~

These tests verify **the helper's logic**, not millisecond scheduler precision or real Spring/Kubernetes shutdown deadlines.

## 11. Real Lifecycle Tests: Stop Ingress First, Stop Consumer Last

In our fixture, `gate` only simulates ingress. In real applications, identify both **the message-producing endpoint** and **the backlog-consuming endpoint**.

~~~mermaid
flowchart LR
    S["File / Broker source"] --> A["ordersInboundEndpoint"]
    A --> Q["ordersQueue"]
    Q --> P["ordersProcessingEndpoint"]
    P --> H["Business handler"]
    CMD["Admin / shutdown coordinator"] -. "stop ingress" .-> A
    CMD -. "stop after drain" .-> P
~~~

### Sequence to Test

1. Transition the instance to **`QUIESCING`** to block new work.
2. Stop **`ordersInboundEndpoint`** or the broker listener/container via adapter lifecycle.
3. Verify the right **instance/endpoint** stopped ingesting. If multiple inbound producers feed the same queue, quiesce all of them.
4. Keep **`ordersProcessingEndpoint`** and downstream DB/executors running to drain.
5. Monitor queue depth, in-flight tasks, unacked source counts, transactions, retries, and pending effects.
6. Only once drained or safely handed off durably, stop consumers, executors, and resources.

**Control Bus** can invoke SpEL lifecycle expressions:

~~~text
@ordersInboundEndpoint.stop()
@ordersInboundEndpoint.isRunning()
@ordersInboundEndpoint.start()
~~~

Yet **Control Bus does not drain queues automatically**. Because it is a high-privilege control plane, never pass expressions from untrusted callers directly into `controlBus`; enforce authentication, authorization, and strict allowlists.

### Spring Integration Orderly Shutdown

Spring Integration provides **Orderly Shutdown** through management APIs such as **`IntegrationMBeanExporter.stopActiveComponents(long howLong)`** in applicable versions. The concept is stopping sources/producers first and giving in-flight messages time to finish.

~~~java
// Fragment in an application with IntegrationMBeanExporter configured:
// howLong is specified in MILLISECONDS.
exporter.stopActiveComponents(30_000L);
~~~

**Never assume** every Spring Boot application automatically invokes this exact mechanism on `SIGTERM`. Production tests must verify who calls it, in which phase, whether it runs before or after lifecycle processors stop downstream consumers, and how much termination budget remains.

### Lifecycle State Differs from Business State

~~~text
INGRESS_STOPPED
DRAINING
DRAINED
PENDING_DURABLE
STOPPED
~~~

This is an **application state machine**, not a sequence managed automatically by `SmartLifecycle`. An endpoint reporting **`isRunning=false`** may still have handlers in flight or transactions awaiting commit.

## 12. Persistent `QueueChannel`: In-Memory Tests Are Not Enough

By default, `QueueChannel` stores messages on the JVM heap. Stopping and restarting an **`ApplicationContext`** in the same JVM with a new `QueueChannel` bean **does not preserve prior messages**. A JVM crash wipes all RAM-queued tasks immediately.

| Where the Message Lives | When JVM Dies | What Must Be Verified |
| --- | --- | --- |
| **In-memory `QueueChannel`** | Queue state vanishes | Can the source replay or did it already ack? |
| **In-memory executor task queue** | Unstarted tasks can be lost | Was handoff durable? |
| **`JdbcChannelMessageStore`** | Committed records can be read back | Schema, query provider, group ID, transactions |
| **Unacked on broker** | May redeliver per protocol/adapter | Ack mode, lease/offset, idempotency |
| **Transactional inbox/outbox** | Committed state survives restarts | Will a new consumer/publisher resume it? |
| **External provider** | Side effect may already have occurred | Operation ID and reconciliation |

### Java Configuration Fragment with `JdbcChannelMessageStore`

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;

@Configuration
class DurableQueueLabConfiguration {

    @Bean
    JdbcChannelMessageStore channelMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        return store;
    }

    @Bean("durablePendingQueue")
    QueueChannel durablePendingQueue(
            JdbcChannelMessageStore channelMessageStore) {
        return new QueueChannel(new MessageGroupQueue(
                channelMessageStore, "orders-shutdown-lab"));
    }
}
~~~

This is a **supplementary fragment**, not a drop-in replacement for all of `ShutdownLabConfiguration`. To run it:

- Add **`spring-integration-jdbc`**, a `DataSource`/PostgreSQL driver, an appropriate transaction manager, and your version's **Spring Integration JDBC schema**.
- Use a **stable `groupId`** (e.g., `orders-shutdown-lab`) across starts and restarts. If the `groupId` or `region` changes, new workers will miss old messages.
- Choose the query provider matching your real database (e.g., PostgreSQL).
- Ensure payload and headers use serializers compatible across restarts and upgrades; specifically avoid storing JVM-local `replyChannel` objects without a proper resolution strategy.
- Wire a polling consumer for **`durablePendingQueue`** and explicitly define the receive/dequeue transaction.

**Key takeaway:** swapping an in-memory `QueueChannel` for a persistent store preserves **un-dequeued messages** once writes commit, yet **does not automatically make every handler and external API atomic**.

## 13. Transaction Tests: Does a Failed Handler Put the Message Back in the Queue?

With a queue backed by **`JdbcChannelMessageStore`**, tests must distinguish **where the transaction begins**.

### Desired Topology

~~~text
JDBC QueueChannel (committed message)
    ↓
PollingConsumer starts transaction TX-A
    ↓
QueueChannel.receive() inside TX-A
    ↓
Business handler executes synchronously inside TX-A
    ↓
COMMIT on success / ROLLBACK on failure
~~~

An XML fragment illustrating transaction advice on the poller:

~~~xml
<int:service-activator
        input-channel="durablePendingQueue"
        ref="orderHandler"
        method="handle">
    <int:poller fixed-delay="50" max-messages-per-poll="1">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

This is a fragment; provide namespaces, beans, and `transactionManager` in a full config. With compatible transactions and DB resources, dequeue and synchronous handler work commit or roll back together.

### Rollback Test Scenario

1. Start PostgreSQL or a test DB with the Spring Integration JDBC schema.
2. Enqueue `EV-42` into `durablePendingQueue` and **commit**.
3. Configure the handler to throw a predefined exception on its first attempt; do not let a recovery callback swallow the error and report success.
4. Let the polling consumer receive `EV-42` **inside a transaction**.
5. Verify the transaction rolled back and the message remains pollable.
6. Let the handler succeed on the next attempt; verify the business DB commits and the queue entry is removed cleanly.
7. Count handler attempts separately from business effects: **two attempts** still yield **one logical completion**.

**Never run this test on an in-memory `QueueChannel` and conclude JDBC rollback works.** Removal and rollback mechanics depend on the concrete message store and transaction manager.

### A Dangerous Boundary: Poller → `ExecutorChannel`

~~~text
TX-A on polling consumer:
  JDBC queue.receive(EV-42)
  ExecutorChannel.send(EV-42)
  COMMIT TX-A; queue row removed

Worker thread:
  task sits in executor RAM
  JVM gets killed
~~~

Here `EV-42` **can be lost** despite starting in a persistent queue, because the durable dequeue committed **before the worker performed the business effect**. That is a **handoff/transaction-boundary design bug** that raising shutdown timeouts cannot fix.

**Fix:** persist work into a durable inbox/broker/work queue **before committing the dequeue**, or keep the atomic portion inside the same transaction. Use idempotency and fault-injection tests to confirm zero gaps between commit points.

## 14. Broker ACKs: Will the Source Redeliver Queued Messages?

In the in-memory lab, JUnit calls `input.send()` directly. Production apps usually use a **source adapter**: Kafka, JMS, AMQP, file, JDBC, or HTTP.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant A as Inbound Adapter
    participant Q as QueueChannel
    participant W as Worker
    B->>A: Deliver EV-42
    A->>Q: send EV-42
    Q-->>A: accepted
    opt An early-ack configuration
        A-->>B: ACK / commit offset
    end
    Note over Q: Message waiting in queue
    Note over Q,W: Process killed before worker handles it
~~~

**Hazard:** if the source received an ACK/offset commit while the message sits only in an **in-memory `QueueChannel`** and the JVM dies, the source may never redeliver `EV-42`. From the producer's view it was accepted, yet business-wise nothing ever ran.

### There Is No Single ACK Contract Across All Adapters

| Source | Specific Behavior to Verify in Tests |
| --- | --- |
| **Kafka** | Consumer polls, offset commit mode, listener transactions/error handling, rebalances, and handoff timing |
| **JMS** | Session transactions, ack mode, listener container stops, and redeliveries |
| **AMQP/RabbitMQ** | Manual/auto ack, requeue, prefetch, consumer cancel, and connection close |
| **File/FTP/SFTP** | File filters, metadata/checkpoints, move/delete/staging, and file replays |
| **JDBC polling source** | Row claims/status updates, transaction commits, and duplicate selection |
| **HTTP inbound gateway** | When 2xx returns, open requests, client HTTP retries, and durable acceptance |

**Never assume a throwing handler always triggers redelivery.** If the source already acked earlier or a recovery handler swallowed the error, semantics differ. Conversely, an at-least-once broker can redeliver even after side effects committed.

### Two Symmetric Tests

**Case A — ACK before durable handoff:** Send `EV-42`, let the adapter ACK right after enqueuing into a RAM `QueueChannel`, and kill the process before the worker runs. After restart, check whether `EV-42` exists at the source or store. If not, that is a **`DATA_LOSS_RISK`** requiring architectural remediation.

**Case B — Durable handoff before ACK:** Send `EV-43`, commit a durable inbox/JDBC queue before ACKing, and kill the process before the worker runs. After restart, the new worker must pick up `EV-43` from the store or source replay and complete the business operation.

Cross-check **both source metadata and database state**, not just consumer logs. Missing logs or delayed metric scrapes never prove zero message loss.

## 15. Crash/Restart: Test Separate Processes, Not Just Closing `ApplicationContext`

To prove messages survive restarts, run **two distinct processes/containers** connected to an external store/broker that remains alive across restarts.

~~~mermaid
flowchart TD
    DB[("PostgreSQL + broker remain intact")]
    A["Process A"] -->|commit pending EV-42| DB
    A -->|kill/crash| X["Process A gone"]
    DB -->|read pending| B["Process B"]
    B --> H["Business handler"]
    H --> Y[("Business state committed")]
~~~

### Test P1 — Pending JDBC Queue Survives Restart

1. Start PostgreSQL with the appropriate message-store schema.
2. Launch Process A, configure a `QueueChannel` with `groupId` **`orders-shutdown-lab`**, and **keep the polling consumer stopped**.
3. Send `EV-1`, `EV-2`, `EV-3` and verify the enqueue transaction committed.
4. Kill Process A; **do not wipe the database** or reset group metadata.
5. Launch Process B with the **same `DataSource`/schema/region/`groupId` and serializer**.
6. Start the consumer and collect three **business completion records** in the DB—do not trust `QueueChannel` counts alone.
7. Verify remaining backlog states are clean and zero `eventId`s were dropped.

**Expected:** committed pending messages in the store survive restart. **Not yet proven:** in-flight messages post-dequeue are safe in every topology.

### Test P2 — Rollback After Dequeue Before Business Commit

1. Put `EV-4` into the JDBC queue.
2. Start the polling consumer with a transaction wrapping **receive + synchronous handler**.
3. Place a fault checkpoint in the handler after receive but before business DB commit.
4. Let the handler throw/roll back and verify the message can be polled again.
5. Clear the fault; let the next attempt commit cleanly.
6. Verify **two handler attempts produced one business result**.

**Expected:** rolling back the shared transactional resource prevents the dequeue from committing permanently. Do not apply this test to an `ExecutorChannel` that broke the transaction before the handler.

### Test P3 — Crash After Side Effect Before Source ACK

1. Pick a **stable `operationId`** (e.g., `PAYMENT-42`) with a source configured for redelivery.
2. Let the handler commit a business update or invoke an idempotent provider.
3. Trigger a fault hook right after commit/side effect yet **before ACK**, then kill the process.
4. Start Process B and allow the broker to redeliver the same business `eventId`.
5. Verify the unique inbox/idempotency record or provider idempotency key ensures the **business effect happens only once**.
6. If a provider response was lost, mark **`UNKNOWN_OUTCOME`** and query/reconcile before issuing a new operation.

**Expected:** the system tolerates at-least-once delivery without double side effects. **Never assume** every transport shares identical ACK checkpoints.

### Test P4 — Executor RAM Holds Unstarted Tasks When Killed

1. Configure a one-worker executor with bounded queue capacity.
2. Block the first worker on `CountDownLatch`; enqueue `EV-5` into the executor queue.
3. Verify whether the source already ACKed and whether `EV-5` still exists in a durable store.
4. Kill Process A before `EV-5` enters its handler.
5. Start Process B against the old source/store and verify `EV-5` has a replay path.

**If `EV-5` existed only in executor RAM while the source already ACKed**, the test exposes work loss. That finding reveals an architectural bug; never "fix" the test by deleting the assertion on `EV-5`.

### Why Not Just Use `@DirtiesContext` or `context.close()`?

A clean `ApplicationContext` close executes lifecycle callbacks and may grant running tasks grace time to finish. **SIGKILL, OOM, node failure, or expired Kubernetes grace periods** do not guarantee cleanup, transaction synchronization callbacks, or `@PreDestroy` run. To prove durability, **include at least one abrupt process-kill test** against an intact external store.

## 16. Shutdown Budgets: Three Clocks That Do Not Automatically Sum

In a Spring Boot application on Kubernetes, several timers coexist:

| Deadline | Config or Owner | Limit |
| --- | --- | --- |
| **Spring Boot lifecycle phase** | `spring.lifecycle.timeout-per-shutdown-phase` | Wait budget **per phase** of `SmartLifecycle` |
| **Spring Integration orderly shutdown** | `stopActiveComponents(howLong)` | Duration for orderly shutdown in **milliseconds** |
| **Kubernetes pod termination** | `terminationGracePeriodSeconds` | Total window before pod receives SIGKILL |
| **`preStop` hook** | Pod lifecycle hook | **Consumes part of the same Kubernetes grace period** |
| **Broker lease/ack deadline** | Broker/adapter | When a message becomes eligible for redelivery |
| **HTTP/DB timeout** | Client/transaction manager | Does not guarantee remote side effects roll back |

Example in `application.yml`:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

server:
  shutdown: graceful
~~~

And a `PodSpec` fragment:

~~~yaml
terminationGracePeriodSeconds: 90
containers:
  - name: order-worker
    image: example.com/order-worker:lab
~~~

**These values are illustrative.** Spring Boot graceful web shutdown does not automatically stop or drain broker/file adapters. `timeout-per-shutdown-phase` is not added on top of Kubernetes grace, and `preStop` shrinks the remaining time available to Spring.

### Budget Math

~~~text
Kubernetes grace:                 90 seconds
preStop/quiesce + propagation:    10 seconds
target drain:                     55 seconds
resource close + metrics:         15 seconds
safety margin:                    10 seconds
~~~

This is an **illustrative sequential budget**. Some stages overlap; measure actual timings in rollouts. Never set drain=90 seconds when grace=90 seconds and `preStop`=10 seconds; the pod will be killed mid-cleanup.

### Kubernetes Test Scenario

1. Deploy two replicas backed by an external broker and persistent DB.
2. Push more backlog than can drain immediately in 10 seconds.
3. Trigger a real rollout or scale-down so the old pod receives termination.
4. Observe endpoint lifecycles, inbound rates, queue depth, executor tasks, in-flight handlers, unacked source items, and pod termination timestamps.
5. Verify the old pod **stops ingress** while draining or leaving durable pending work.
6. Let surviving/new replicas continue; reconcile **accepted event IDs against business completions**.
7. Run two variants: drain finishes within grace vs. drain exceeds grace.

**`readiness=false` does not stop Kafka/JMS/AMQP consumers.** It mainly affects traffic routed via readiness probes; stop source adapters explicitly. Likewise, a shell entrypoint that fails to forward `SIGTERM` can prevent the JVM from ever starting lifecycle shutdown.

## 17. Retries, `errorChannel`, and Transactions During Drain

A message that cannot complete immediately may be:

- Retrying inside a handler with backoff.
- Waiting on a long-timeout HTTP call.
- Waiting on a DB lock or connection pool.
- Being routed to `errorChannel`.
- Being persisted to a DLQ/quarantine/outbox for later handling.

**An expiring shutdown deadline never permits a handler to swallow exceptions and report success.** If a message has no final business outcome yet, durable recovery or source redelivery must take over per contract.

### Error Flow Example: Never Count Every Retry as a Separate Business Failure

~~~text
EV-42 delivery #1
  handler attempt #1 → timeout
  handler attempt #2 → timeout
  handler attempt #3 → success

Output business completion = 1
Handler attempts = 3
ErrorMessage count: depends on configured advice/error flow
~~~

Never assume one `ErrorMessage` is emitted for **every failed attempt**; many `RetryAdvice` setups publish only the final failure after retries exhaust. Use handler spies/metrics to count attempts and inspect the error flow for final recovery.

### Poison-Message Test

1. Enqueue `EV-BAD` with an invalid payload.
2. Have the handler throw a **non-retryable validation exception**.
3. Confirm the retry policy **does not retry infinitely**.
4. Confirm the message is persisted to **durable quarantine/DLQ** per contract.
5. Continue draining `EV-GOOD` behind `EV-BAD`; never let one bad message stall the queue until the deadline expires.

**Never use `queue.clear()` to force `queueDepth` charts down to 0.** That destroys recovery for unprocessed messages.

## 18. Observability for Graceful Shutdown: Record Evidence, Not Guesses

A convincing shutdown test emits **logs, metrics, and source/store states**. A lone `"shutdown finished"` log proves nothing about whether draining succeeded.

### Minimum Metric/Diagnostic Table

| Signal | Must Answer | Pitfall |
| --- | --- | --- |
| **`ingress.accepting`** | Are endpoints/callers still producing new messages? | One stopped replica does not speak for the whole cluster |
| **`queue.depth`** | How many messages remain un-dequeued? | Excludes handler and executor in-flight work |
| **`queue.oldest.age`** | Are messages waiting too long? | Cross-JVM age requires synchronized clocks |
| **`poller.running`** | Is the consumer still running to drain? | `isRunning=false` does not guarantee zero in-flight |
| **`handler.active`** | How many handlers are running? | In-method counts may end before DB commit |
| **`executor.queued/active`** | Are handed-off tasks still unfinished? | RAM executor queues vanish on crash |
| **`source.unacked`** | Are messages eligible for redelivery? | Depends on adapter/broker metadata |
| **`transaction.committed/rolledBack`** | Did durable effects commit or roll back? | RAM counters are not audit sources |
| **`retry.pending / dlq.pending`** | Is work waiting on recovery? | Infinite retries can block draining |
| **`outbox.pending`** | Committed events not yet published? | Publishing before mark-sent can duplicate |
| **`shutdown.result`** | `DRAINED` / `DURABLE_PENDING` / `RISK`? | Never turn timeouts into fake successes |
| **`budget.remaining`** | How much cleanup time remains? | Do not track only Spring Boot timeouts |

### Sample Logs While `EV-1` Is Blocked in a Test

~~~text
event=shutdown_observation
instance=order-lab-1
phase=DRAINING
ingressAccepting=false
queued=2
handlerInFlight=1
executorQueued=0
allCompleted=false
result=IN_PROGRESS
~~~

If 150 ms elapses before releasing the latch:

~~~text
event=shutdown_decision
phase=DRAINING
queued=2
handlerInFlight=1
deadlineReached=true
result=TIMED_OUT_WITH_PENDING
~~~

If using an in-memory `QueueChannel` after source ACK, escalate to **`DATA_LOSS_RISK`**; because the lab itself has no broker, **do not assume** a source will replay.

### After Releasing the Worker

~~~text
event=shutdown_decision
phase=DRAINED
queued=0
handlerInFlight=0
completedEvents=3
result=DRAINED_IN_LAB_SCOPE
~~~

These fields are **application-defined log formats**, not automatic Spring Integration output. Never log payloads, tokens, or customer data. Keep event IDs and correlation IDs in controlled traces/logs; **never use `eventId` as a metric tag** due to high cardinality.

### Using Micrometer at the Right Boundaries

- **`Timer`** for send/dispatch latency, queue wait, handler execution, and shutdown elapsed time.
- **`Counter`** for handler attempts, errors, retries, suppressed duplicates, DLQ publishes, and shutdown outcomes.
- **`DistributionSummary`** for batch sizes or serialized payload bytes.
- **`Gauge`** for queue depth, executor queued/active counts, in-flight counts, and pending groups.

Never count handler attempts as **unique business operations**. One event can run multiple times via retries and redeliveries. Base SLOs on durable business state or well-defined completion events.

## 19. Test Matrix to Avoid "Happy Path Only"

| ID | Scenario | Tooling | Decisive Assertion |
| --- | --- | --- | --- |
| **G01** | Queue holds three messages, consumer stopped | `QueueChannel` + `@SpringIntegrationTest` | Queue still holds 3; completed=0 |
| **G02** | Pause ingress before drain | `IngressGate` | `EV-4` rejected; backlog does not grow past gate |
| **G03** | One handler in flight, two messages queued | `CountDownLatch` | queued=2, inFlight=1, completed=0 |
| **G04** | Release handler and drain all three messages | `CountDownLatch` + polling endpoint | Exact completed IDs, queue=0, inFlight=0 |
| **G05** | Deadline expires while `EV-1` remains held | Timed await | Must not report `DRAINED` |
| **G06** | Stop consumer with zero in-flight work | `Lifecycle` | `isRunning=false`; no further polls per contract |
| **G07** | Stop a real inbound adapter | Lifecycle/broker/file test | No new intake on that endpoint/instance |
| **G08** | Handler throws and transaction rolls back | JDBC store + transaction | Message remains retryable; zero lost durable work |
| **G09** | Handler throws then recovers to DLQ | Error flow + durable DLQ | DLQ committed; no false success log |
| **G10** | Persistent queue retains messages after Process A dies | PostgreSQL + Process B | Process B reads exact committed events |
| **G11** | Dequeue commits while executor task sits in RAM | Executor + fault hook | Exposes handoff/work-loss gap |
| **G12** | Crash after DB commit before broker ACK | Broker + DB | Redelivery occurs; business effect executes once |
| **G13** | HTTP timeout after external side effect | Fake provider with status lookup | Reconciliation; no double operation |
| **G14** | Rollout with `preStop` and short grace | Kubernetes test | Never claims drained when pod is killed early |
| **G15** | Two replicas sharing one source/store | Multi-instance test | Ownership, acks, and per-instance state remain clear |
| **G16** | Shutdown ends with backlog remaining | Persistent store + restart | New worker processes durable pending items |
| **G17** | Correlation group missing a part at shutdown | `MessageGroupStore` | Incomplete group retained/expired per policy |
| **G18** | Executor rejects task during shutdown/overload | Bounded executor | Handoff error observed; no false success ACK |

**G01–G06** are intra-JVM logic/lifecycle tests; **G07–G18** require corresponding adapter, DB, broker, or orchestrator fixtures. Never mark the latter tests as passing just because the three in-memory lab JUnit methods passed.

## 20. Debugging Failed Graceful-Shutdown Tests

### Case 1 — Consumer Starts Running Before the Test Enqueues

**Symptom:** queue depth is not 3 even though the test just sent three messages.

**Common cause:** endpoint `autoStartup` ran, another consumer is polling, or fixtures leaked across tests. Verify **`@SpringIntegrationTest(noAutoStartup)`** matches the real endpoint ID and no other subscriber/poller exists.

### Case 2 — `firstStarted` Never Counts Down

**Symptom:** test times out waiting for the handler to begin.

Check:

1. Is endpoint **`workConsumer`** started with `isRunning == true`?
2. Is channel bean **`pendingQueue`** actually read by `processingFlow`?
3. Is the poller trigger/`fixedDelay` active and does `TaskScheduler` have a free thread?
4. Is the handler registered properly as a `MessageHandler`?
5. Did an exception occur before entering the first block, or did another flow consume the message?

**Never fix this by sleeping longer before verifying topology.**

### Case 3 — Fewer Than Three Completions After `releaseFirst`

**Symptom:** `allCompleted.await` returns false.

Inspect `errorChannel`/handler logs, transaction rollbacks, poller state, `eventId`, and exceptions. The test might have stopped the consumer too early, or the handler threw. If output goes to another `QueueChannel`, remember **`receive()` consumes messages**—do not let a test observer steal messages from a business consumer.

### Case 4 — Queue Depth Hits 0 Yet Final Outcome Is Wrong

Messages may have been dequeued into an executor queue or an in-flight external HTTP call. Check **in-flight counts, executor queued tasks, transaction commits, source acks, and provider status** rather than tweaking queue-depth math.

### Case 5 — Restart Test Loses Messages Despite `JdbcChannelMessageStore`

Check:

- Do both processes share the exact same **`DataSource`/schema/table prefix/region/`groupId`**?
- Did the enqueue commit before Process A died?
- Can payloads/headers deserialize under the new application version?
- Is Poller B running, or are DB locks/another consumer holding the messages?
- Did Process A dequeue and commit removal before being killed?
- If the handler created a side effect without checkpointing, do replay/reconciliation exist?

**Never wipe message-store tables to "clear errors"** when unprocessed data sits inside them.

### Case 6 — Kubernetes Kills the Pod Before Cleanup

Kubernetes counts `preStop` inside the same termination grace window. If the JVM starts via a shell script that fails to forward `SIGTERM`, Spring never receives the signal. Inspect signal forwarding, deadlines, `preStop`, lifecycle phases, and pod termination status; **`SIGKILL` never runs `@PreDestroy` or shutdown hooks**.

### Case 7 — Duplicates Appear After Restart

At-least-once redelivery is normal when an ACK did not complete. Check **stable `eventId`/`operationId`, inbox unique constraints, outbox publish state, and provider idempotency**. Never "fix" duplicates by ACKing before durable commits—that trades duplicates for **data loss**.

## 21. Runbook for Graceful Shutdown with Pending Messages

Applies to services following **inbound source → durable queue → polling consumer → DB/outbound**. Adapt to each adapter and transaction model; this is an **operational application procedure**, not an automatic feature of every `IntegrationFlow`.

### Phase 0 — Record Baseline

Before issuing the shutdown command, record:

~~~text
operationId=rollout-42
instance=order-worker-b
flow=order-import
ingressAccepting=true
queued=500
inFlight=8
executorQueued=12
sourceUnacked=3
retryPending=4
outboxPending=7
unknownExternalEffects=0
deadline=...
~~~

Check **replay sources if the process dies**: broker retention/unacked state, JDBC queue transactions/serializers, and restart-tested inbox/outbox tables. If only a RAM `QueueChannel` holds items after source ACK, record **`DATA_LOSS_RISK`** instead of blindly proceeding with a risky rollout.

### Phase 1 — Quiesce Ingress

1. Stop accepting new messages at **the exact inbound endpoint/consumer/container**.
2. For HTTP services, drop readiness or stop accepting new requests per gateway/load-balancer drain policy.
3. For broker/file adapters, stop their dedicated lifecycles; web server readiness **does not** automatically stop Kafka/JMS/AMQP consumers.
4. Across multiple replicas, monitor **each replica** plus newly joining instances during rollout.
5. Confirm new ingress has dropped to zero; timestamp when the barrier took effect.

**Do not stop the queue-draining consumer during this phase.**

### Phase 2 — Drain Within a Finite Budget

Keep polling consumers, executors, DB connection pools, and external clients alive. Sample periodically without **calling `receive()` just to count queue depth**.

~~~text
remainingWork :=
    queued
    + executorQueued
    + handlerInFlight
    + claimedButNotCommitted
    + sourceUnacked
    + unresolvedExternalOutcomes
~~~

This is a **conceptual model**, not an exact sum in every topology: one message may appear in multiple metrics briefly. Its goal is **missing zero places that own work**, not counting unique business operations.

When handlers fail:

- Transient failures: bounded retries with backoff inside budget or a durable retry queue.
- Permanent failures: commit quarantine/DLQ per contract.
- Unknown external outcomes: record `UNKNOWN` and reconcile by `operationId`.
- Never catch exceptions and return success when business work is incomplete.

### Phase 3 — Decide at the Deadline

| Evidence | Operational Outcome |
| --- | --- |
| Ingress quiesced; zero queued/claimed/in-flight/unacked; commits/acks confirmed | **`DRAINED`** |
| Committed backlog remains in durable store; new worker can read it | **`DURABLE_PENDING`** |
| Unacked broker deliveries remain and redelivery is guaranteed per adapter policy | **`REPLAYABLE_PENDING`** |
| Provider request sent yet response unknown | **`RECONCILIATION_REQUIRED`** |
| Tasks exist only in RAM after source ACK | **`DATA_LOSS_RISK`** |
| Unsure if ingress stopped, or key metrics missing | **`INCOMPLETE_EVIDENCE`**; do not declare success |

### Phase 4 — Stop Downstream and Close Resources

Once required work is finished or durably handed off, stop consumers/pollers, executors, and connections in order. Reserve a **safety margin** for transaction cleanup and process exit; never spend the entire Kubernetes grace window waiting on retries.

### Phase 5 — Verify After Restart

1. New workers connect to the exact broker/store/region/`groupId`.
2. Durable backlog and pending outbox items drain at expected processing rates.
3. Redelivering the same `eventId` produces zero extra business side effects.
4. `UNKNOWN_OUTCOME` items reconcile rather than replaying blindly.
5. No orphan `MessageGroup` or retry records age past SLA.
6. Flow desired state is restored; never open ingress while the cluster remains in maintenance.

### Handoff Report for Operations

~~~text
shutdownId=rollout-42
service=order-worker
oldInstance=order-worker-b
finalOutcome=TIMED_OUT_WITH_DURABLE_PENDING
queuedInJdbcStore=19
handlerInFlight=0
sourceUnacked=0
externalUnknown=1
newWorkerCanRecover=true
followUp=RECONCILE_EXTERNAL_OPERATION
~~~

This is a **conditionally valid outcome** if all 19 messages are committed in the store and new workers can resume them. It is **not `DRAINED`**.

## 22. Extension Exercises for Learners

### Exercise A — Replace the Fake Gate with a Real Inbound Endpoint

Replace **`IngressGate`** with an inbound polling adapter having an **explicit lifecycle ID** and a controllable mock `MessageSource`. Use **`@SpringIntegrationTest(noAutoStartup = {...})`** and **`MockIntegrationContext`** if appropriate, emit messages, and stop the source via `Lifecycle` or control messages.

**Pass when:** after `stop()`, no new polls occur per endpoint contract; the backlog-draining polling consumer keeps running; after `start()`, the source resumes ingesting. Never rely on fixed `Thread.sleep` calls.

### Exercise B — Switch `QueueChannel` to JDBC

Share one message store across **two application contexts** or two processes. Send three messages while the consumer is stopped, close context A, and start context B pointing to the same DB/`groupId`.

**Pass when:** context B receives all committed messages with no lost IDs or abnormal leftover rows. Then repeat with a **process kill** to contrast graceful context close with crash recovery.

### Exercise C — Insert an `ExecutorChannel` Before the Handler

Insert an `ExecutorChannel` with a one-worker pool and bounded queue after the consumer. Hold the worker with a latch and watch **`QueueChannel` depth** alongside **`executor queued`**.

**Pass when:** the test proves `QueueChannel` depth drops to 0 while the executor still holds tasks, and documents the gap when dequeue commits while tasks sit only in RAM.

### Exercise D — Add Transaction Rollback and Retries

Use a transactional JDBC queue with a handler failing on its first attempt and succeeding on the second. Observe handler attempts, business DB commits, error flows, and final queue state.

**Pass when:** one event retries yet yields **one business completion**. If the handler has external side effects, add an idempotency key or a reconcilable fake provider.

### Exercise E — Multi-Replica Testing

Run two workers against a shared durable source/queue. Trigger drain/stop on one instance while the other keeps running. Verify **ownership and idempotency** in the business store, not just log counts.

**Pass when:** zero accepted events are dropped and zero business effects double-execute, even if one instance crashes post-commit before acknowledgment.

## 23. Self-Check Questions and Answers

**1. If `QueueChannel.getQueueSize()` returns 0, is graceful shutdown complete?**

**Not necessarily.** Messages may already be dequeued and sitting inside a handler, executor task queue, or open transaction. Check in-flight counts, unacked sources, and durable business outcomes.

**2. Does stopping the polling consumer while 500 messages sit in the queue automatically process those 500 messages?**

**No.** A stopped consumer stops polling per contract, leaving the backlog idle. To drain, stop ingress first and keep consumers running until criteria are met or budget expires.

**3. While a handler waits on a latch, `await(timeout)` returns false. Is the test broken?**

**Not necessarily.** That is the expected result when simulating deadline expiration with in-flight work. Assert the timeout state properly and release the latch during cleanup.

**4. Does switching an in-memory `QueueChannel` to JDBC guarantee every message survives `SIGKILL`?**

**Not completely.** Committed store messages survive restarts, yet already-dequeued messages sitting only in executor RAM can be lost. Verify transaction/handoff boundaries and source ACKs.

**5. If a broker redelivers an event after a crash, is the framework broken?**

**Not automatically.** At-least-once redelivery follows protocol when ACKs fail. Business logic must be idempotent so redeliveries never duplicate side effects.

**6. When Kubernetes grace expires, is Spring guaranteed to finish `@PreDestroy`?**

**No.** Once the grace period ends, the process can be force-killed. `preStop` shares the same grace window; architectures must recover from durable state without depending on cleanup callbacks.

**7. Why not use `@DirtiesContext` instead of a crash test?**

Because **context close** runs lifecycle cleanup, whereas an abrupt process kill does not guarantee callbacks run. Only two independent processes/containers sharing an intact external store truly test restart/durability boundaries.

**8. An HTTP payment succeeded, yet the worker lost the response during shutdown. Should we issue a new payment operation?**

**No.** Record `UNKNOWN_OUTCOME`, look up by stable `operationId`/idempotency key, and reconcile. A request timeout never proves the remote side effect did not happen.

## 24. Checklist Before Marking the Lab Complete

- Did you address **testing graceful shutdown with pending messages**, rather than merely testing `stop()`?
- Did tests build queued and in-flight state deterministically using **`CountDownLatch`**, without lucky sleeps?
- Was the ingress gate or inbound endpoint paused **before** the consumer started draining?
- Did tests verify the source stops accepting new work within controlled scope?
- Did tests prove the queue **does not drain itself** while the consumer is stopped?
- Did tests observe **`queued=2, inFlight=1`**, followed by all three business events completing after releasing the latch?
- Did the **timeout path** return a pending outcome rather than falsely reporting `DRAINED`?
- Does `finally`/`@AfterEach` clean up latches so threads and test contexts never hang?
- Are contexts isolated or `QueueChannel`/latches cleanly reset between test cases?
- Have you distinguished **in-memory `QueueChannel`, JDBC-backed `QueueChannel`, and RAM executor queues**?
- If using JDBC, did you test restart with the exact same `DataSource`/schema/region/`groupId` and committed data?
- Does the poller transaction wrap dequeue + synchronous handler when rollback is required?
- If `ExecutorChannel` follows dequeue, did you verify the durable handoff gap?
- Do you know the exact **ACK/offset commit point** of your broker adapter relative to durable writes?
- Did you test crashing **after side effect before ACK** ensuring identical `eventId`s never double-execute business effects?
- Are **`UNKNOWN_OUTCOME`, retry budgets, DLQs, and pending outboxes** handled?
- Have you separated Spring lifecycle timeouts, Orderly Shutdown timeouts, and Kubernetes termination grace?
- Did you test a real rollout where **drain time is insufficient**?
- Does observability cover queue depth, in-flight, executor queued, unacked, durable pending, and explicit outcomes?
- Have you avoided wiping `MessageStore` or queues just to make shutdown charts look "green"?
- Do you have evidence that business DB/source/store state stays consistent after restarts?

## Conclusion

Testing **graceful shutdown with pending messages** is far more than calling `stop()` and asserting `isRunning=false`. This lab showed how to construct **deterministic backlog and in-flight work** with `QueueChannel`, a polling consumer, and `CountDownLatch`, then verify **pause ingress → drain queue → finish handlers → stop consumer**. It also exercises **deadline expiration with pending messages** without hanging tests or reporting fake success.

In real Spring Integration Runtime systems, safety also encompasses **transactions, broker ACKs, persistent `MessageStore`s, executor-queued tasks, retries/recovery, correlation, and external side effects**. A persistent queue does not protect tasks already dequeued into executor RAM; an HTTP timeout never proves a side effect did not occur; and broker redeliveries are harmless when handlers are idempotent.

Therefore, a truthful operational outcome must answer: **What work remains? Where does it live? Is it durable? Who picks it up after restart? Could business effects duplicate?** Only when those answers are proven via **in-JVM tests, fault injection, and crash/restart tests against real stores** is a system's graceful shutdown trustworthy for deployment.

## References

- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
