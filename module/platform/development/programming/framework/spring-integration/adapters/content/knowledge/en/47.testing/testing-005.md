# Time-Based Inbound Adapter Testing in Spring Integration

In integration systems, many data sources do not proactively push to the application: files appear in a directory every hour, SFTP receives partner files every few minutes, or a database table holds pending records. Spring Integration typically uses an **inbound adapter paired with a poller** to fetch data, convert it into a `Message<?>`, and send it into a `MessageChannel`. Flows that work during manual testing can still fail in production: a poller starts before the source is ready, a file is read twice, a DB record is skipped, a message arrives before its effective time, or duplicates are sent after a connection failure.

**Time-based inbound adapter testing** means designing tests that control **trigger timing, poll frequency, endpoint lifecycles, source state, latency, concurrency, and error recovery**. What matters is not merely "eventually a message was received" but **the right data, at the right time, without duplicate processing outside the contract, and with evidence when time or connectivity shifts**.

This lesson belongs to the **Testing** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. The module scope covers connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`s, including File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This topic focuses on time-sensitive inbound flows—especially **polling adapters**—while distinguishing **message-driven** adapters so the wrong testing technique is not applied.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **polling inbound adapters**, **message-driven inbound adapters**, and **inbound gateways** by activation mechanism.
2. Explain `MessageSource.receive()`, `SourcePollingChannelAdapter`, `PollerMetadata`, and `TaskScheduler`.
3. Choose the right test layer: **time logic**, **scheduler-free flow**, **poller lifecycle**, **transport integration**, and **end-to-end**.
4. Use `@SpringIntegrationTest(noAutoStartup = "...")` and `MockIntegrationContext` to set up a fake `MessageSource` before starting the endpoint.
5. Test **`fixedDelay`, `fixedRate`, `cron`, `maxMessagesPerPoll`, empty sources, start/stop, restart, and timeouts**.
6. Test **File/SFTP/JDBC polling** and distinguish them from Kafka/JMS/AMQP listeners and HTTP inbound pushes.
7. Distinguish **event time, effective time, poll time, and processing time**, measuring latency meaningfully.
8. Design failure cases: duplicates, partial files, unavailable sources, transaction rollbacks, concurrent pollers, retries, and backpressure.
9. Reduce flaky tests using fake clocks, finite fake sources, bounded waits, isolated fixtures, and cleanup.

## 2. How Are Inbound Adapters Triggered?

Not every Spring Integration inbound adapter runs on a poll schedule:

| Group | Mechanism | Examples | Time-Testing Focus |
|---|---|---|---|
| **Polling inbound adapter** | Scheduler periodically invokes `MessageSource.receive()` | File, SFTP synchronizer/file source, JDBC polling | Cadence, lifecycle, items/tick, source state, duplicates. |
| **Message-driven inbound adapter** | Listener/consumer woken up by external source | JMS, AMQP, Kafka message-driven adapters | Listener startup, ack/offset, redelivery, concurrency, reconnect. |
| **Inbound HTTP gateway** | Client HTTP request triggers the flow | HTTP POST endpoint | Request/reply timeouts, server lifecycle, deadlines. |
| **Broker polling source** | Actively polls/receives from a specialized message source | JMS polling source, Kafka `MessageSource` when configured | Spring Integration trigger plus broker semantics. |

**Do not apply a single assertion template to all groups.** `maxMessagesPerPoll` applies to a Spring Integration polling endpoint, not `max.poll.records`, partition assignment, or offset commits in a Kafka message-driven consumer.

~~~mermaid
flowchart LR
    CLOCK["TaskScheduler / Trigger<br/>fixedDelay, fixedRate, cron"] --> POLLER["Poller"]
    POLLER --> SOURCE["MessageSource.receive()"]
    EXT["External source<br/>File / SFTP / JDBC"] --> SOURCE
    SOURCE --> CH["MessageChannel"]
    CH --> HANDLER["Filter / Transform / Route"]
    HANDLER --> TARGET["Business handler / outbound adapter"]
    SOURCE -. "Returns null if no data yet" .-> POLLER
    HANDLER --> ERR["Error / retry / recovery"]
~~~

A tick only creates an **opportunity** to fetch data. When the source is empty, `receive()` can return `null`; a single tick can also process multiple messages if `maxMessagesPerPoll` and the source permit.

## 3. Components Governing Timing

| Component | Role | Test Questions |
|---|---|---|
| `MessageSource<T>` | Fetches one message or returns `null` | Does it stop emitting when exhausted? How are errors handled? |
| `SourcePollingChannelAdapter` | Pulls from source into channel on schedule | Do start/stop work properly? |
| `PollerMetadata` | Trigger, transaction, advice, `maxMessagesPerPoll` | Is config bound to the right endpoint? |
| `TaskScheduler` | Runs scheduled tasks | Does it have appropriate threads and lifecycle? |
| **Trigger** | Computes next execution time | Does delay/rate/cron match contract? |
| `MessageChannel` | Delivers message into flow | How does sync/async affect outcomes? |
| **Metadata/filter store** | Tracks files/records already seen or processed | Does state survive restarts? |
| **Error handler/advice** | Retries, transactions, recovery | Are errors swallowed or looped infinitely? |

**A poller tick completing successfully does not mean the business handler succeeded.** Separate observation points across source, channel, handler, and target system.

## 4. Fixed Delay, Fixed Rate, and Cron

### 4.1. Fixed Delay

With **fixed delay**, the wait interval starts after the previous execution finishes, per the configured trigger/framework semantics.

~~~text
Tick 1: 10:00:00.000 → finishes at 10:00:00.300
        wait 1,000 ms
Tick 2: around 10:00:01.300
~~~

If the handler is slow, actual frequency drops. Never assert "exactly one event per second."

### 4.2. Fixed Rate

**Fixed rate** targets execution times on a steady cadence. Actual start times depend on the scheduler, thread pool, and task duration.

~~~text
Scheduled targets: 10:00:00, 10:00:01, 10:00:02, ...
Actual starts:     depends on load and TaskScheduler strategy
~~~

**Do not assume fixed-rate tasks automatically run in parallel.** If overlapping execution is risky, verify the scheduler's semantics and concurrent source-access safety.

### 4.3. Cron

Cron selects **calendar points** such as "every day at 02:30." Factors to verify:

- Explicit timezone vs. relying on JVM default?
- Leap months/years, month-end dates, and business calendars.
- Daylight Saving Time (DST): a local hour may not exist or may occur twice.
- When the app is down, are missed runs skipped or must a backlog be processed?

**Cron does not automatically catch up** all missed runs while the app was offline; backlog handling must be designed into the source/checkpoint/recovery mechanism.

| Trigger | What to Test | What Not to Assume |
|---|---|---|
| Fixed delay | Reasonable pause after processing, no busy-loop. | Always exact N ms regardless of load. |
| Fixed rate | Drift when handler is slow, overlap handling. | Every tick runs on a brand new thread. |
| Cron | Next execution with timezone, DST, and calendar boundaries. | Automatically catches up missed runs. |

## 5. Timeline Milestones of a Message

Suppose a partner uploads a file to SFTP at 10:00:00, the poller checks at 10:00:10, reads it at 10:00:12, and the handler finishes at 10:00:14.

| Milestone | Reference Name | Meaning |
|---|---|---|
| Data ready | `availableAt` | File/record is complete and eligible to read. |
| Business effective time | `effectiveAt` | Domain permits processing from this timestamp. |
| Poll tick | `pollAt` | Scheduler triggers a poll attempt. |
| Adapter receives message | `receivedAt` | Source returns a message. |
| Handler processes | `processedAt` | Business handler executed per defined semantics. |
| Final result verified | `verifiedAt` | Target persisted/processed properly, if required by workflow. |

~~~mermaid
flowchart LR
    A["availableAt<br/>Source ready"] --> B["pollAt<br/>Scheduler runs"]
    B --> C["receivedAt<br/>Source emits message"]
    C --> D["processedAt<br/>Handler"]
    D --> E["verifiedAt<br/>Target confirms"]
~~~

**Poll latency** can be measured as `receivedAt − availableAt` when source readiness is known. **End-to-end latency** requires a verified final milestone; never use `send() == true` or an intermediate ACK instead of `verifiedAt`.

An event whose `effectiveAt` is in the future might be downloaded early yet not permitted to trigger side effects yet. Therefore, distinguish **source received** from **business effective**.

## 6. Multi-Layer Testing Strategy

| Layer | Technique | What It Proves |
|---|---|---|
| **Clock/domain unit test** | `Clock.fixed` or fake clock | Due dates, expiration, time windows. |
| **Source unit test** | Call `MessageSource.receive()` directly with fixtures | Filtering, mapping, no-data behavior. |
| **Flow test** | `DirectChannel` → transformer → `QueueChannel` | Payload/headers and downstream wiring. |
| **Controlled poller test** | `noAutoStartup` + fake `MessageSource` + start/stop | Source–poller–channel wiring and lifecycle. |
| **Transport integration** | Real files, SFTP server, test DB/broker | I/O, transactions, filters, reconnects, acks. |
| **End-to-end/recovery** | Source → adapters → final outcome | Multi-system path, restarts, real failure modes. |

Rules:

- **Mock the source** to test downstream processing without hitting external sources.
- **Mock the outbound handler** to observe final flow messages without side effects.
- **Do not mock the file source** when testing real file filters, mtime, or metadata stores.
- **Do not mock the database** when verifying locking/isolation.
- **Do not mock the broker** when verifying real acks, offsets, and redeliveries.

## 7. Required Dependencies

Example when the project uses compatible Spring Boot dependency management/BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Without a BOM, supply compatible versions of Spring Integration, Spring Framework, JUnit, and Mockito. When testing real File/SFTP/JDBC/Kafka/JMS/AMQP/HTTP adapters, add the **matching adapter modules** and protocol test environment; `spring-integration-test` does not supply brokers or SFTP servers.

The examples below use standard Java DSL. Some DSL overloads or endpoint bean names vary across versions; verify against your project's API version.

## 8. Example: Controllable Inbound Polling Flow

Goal: a source emits strings, a transformer trims whitespace, and sends them to a `QueueChannel`. The test must **substitute the source before starting the poller** so it never depends on networks or external data.

### 8.1. Flow Configuration

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
class TimedInboundTestConfig {

    @Bean
    QueueChannel processedEvents() {
        return new QueueChannel();
    }

    @Bean
    MessageSource<String> idleSource() {
        return () -> null; // Does not access external sources in test context.
    }

    @Bean
    IntegrationFlow pollingFlow(MessageSource<String> idleSource,
                                QueueChannel processedEvents) {
        return IntegrationFlow
                .from(idleSource, endpoint -> endpoint
                        .id("timedInboundEndpoint")
                        .poller(Pollers
                                .fixedDelay(Duration.ofMillis(200))
                                .maxMessagesPerPoll(1)))
                .transform(String.class, String::trim)
                .channel(processedEvents)
                .get();
    }
}
~~~

In this example:

- `idleSource`: default `MessageSource<String>` bean returning `null`.
- `timedInboundEndpoint`: **endpoint ID** used to substitute the source and control lifecycle.
- `processedEvents`: output `QueueChannel` for bounded test receives.
- `maxMessagesPerPoll(1)`: caps **each poll cycle**, not the endpoint's lifetime.

### 8.2. Finite Fake Source

~~~java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;

final class FiniteSource<T> implements MessageSource<T> {

    private final Queue<Message<T>> pending =
            new ConcurrentLinkedQueue<>();
    private final AtomicInteger receiveCalls = new AtomicInteger();

    void enqueue(Message<T> message) {
        pending.add(message);
    }

    int receiveCount() {
        return receiveCalls.get();
    }

    @Override
    public Message<T> receive() {
        receiveCalls.incrementAndGet();
        return pending.poll(); // null when exhausted
    }
}
~~~

A thread-safe queue is essential when the scheduler thread invokes `receive()` while the JUnit thread prepares or inspects fixtures. To test races intentionally, use barriers/latches instead of an unsynchronized shared `ArrayList`.

### 8.3. JUnit Test with Explicit Start/Stop

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.test.context.MockIntegrationContext;
import org.springframework.integration.test.context.SpringIntegrationTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TimedInboundTestConfig.class)
@SpringIntegrationTest(noAutoStartup = "timedInboundEndpoint")
class TimedInboundFlowTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("processedEvents")
    QueueChannel output;

    private SmartLifecycle endpoint;

    @AfterEach
    void cleanup() {
        if (endpoint != null) {
            endpoint.stop();
        }
        mockContext.resetBeans();
        while (output.receive(0) != null) {
            // Drain remaining messages in QueueChannel.
        }
    }

    @Test
    void shouldPollMessageAfterExplicitStart() {
        FiniteSource<String> source = new FiniteSource<>();
        source.enqueue(MessageBuilder.withPayload("  invoice-2048  ")
                .setHeader("traceId", "test-2048")
                .build());

        mockContext.substituteMessageSourceFor(
                "timedInboundEndpoint", source);

        endpoint = context.getBean(
                "timedInboundEndpoint", SmartLifecycle.class);
        assertFalse(endpoint.isRunning());
        endpoint.start();

        Message<?> actual = output.receive(2_000);
        assertNotNull(actual, "No message received before timeout");
        assertEquals("invoice-2048", actual.getPayload());
        assertEquals("test-2048",
                actual.getHeaders().get("traceId"));
        assertTrue(source.receiveCount() >= 1);
    }
}
~~~

This test proves a message flows from the **fake source** through the **polling endpoint** into the channel and transformer after explicit startup. It **does not** prove real SFTP/DB reads, millisecond-exact fixed delays, or outbound adapter side effects.

**Endpoint bean note:** how Java DSL registers endpoint/bean names can vary across versions. Looking up bean `timedInboundEndpoint` assumes that ID is exposed accordingly; verify actual beans in your Spring context rather than guessing from channel names.

## 9. Testing Empty Sources and No Pre-Start Polling

### 9.1. Do Not Poll Before Setup

~~~java
@SpringIntegrationTest(noAutoStartup = "timedInboundEndpoint")
~~~

Meaning: the target endpoint will not auto-start when the context initializes. Order should be:

1. Create fixtures and the fake `MessageSource`.
2. Register the source in `MockIntegrationContext` under the exact endpoint ID.
3. Assert the endpoint is not running yet.
4. Explicitly call `start()`.
5. Wait for output or error via an observation point with timeout.

To prove `receive()` **was never called before start**, use an invocation-counting fake and assert during setup rather than merely calling `QueueChannel.receive(0)` once.

### 9.2. An Empty Source Is a Normal State

~~~java
MessageSource<String> emptySource = () -> null;
mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", emptySource);

// After starting and ensuring the channel is empty:
Message<?> none = output.receive(400);
assertNull(none);
~~~

The assertion above only proves **no output arrived within the 400 ms observation window**. To prove the scheduler actually polled, pair it with a counting fake or latch on `receive()`; otherwise missing output might just mean the poller never ran.

### 9.3. Infinite Fakes Create Artificial Duplicates

~~~java
MessageSource<String> alwaysProduces = () ->
        MessageBuilder.withPayload("same-message").build();
~~~

This source returns a message on **every call**. Thus even `maxMessagesPerPoll(1)` produces one message on **every tick**. For tests expecting one message, use `FiniteSource` or `AtomicReference<Message<T>>` so subsequent calls return `null`.

## 10. maxMessagesPerPoll Is a Per-Poll Limit

Suppose three messages sit in the source:

~~~text
Source: [M1, M2, M3]
maxMessagesPerPoll = 1
Tick 1 → M1
Tick 2 → M2
Tick 3 → M3
Tick 4 → null
~~~

The diagram illustrates the simple case; in practice, transactions, error handlers, and concurrency affect outcomes. **Do not confuse `maxMessagesPerPoll=1` with "process only one message in the endpoint's lifetime."**

A strong test should verify:

- Messages per tick do not exceed the configured cap under controlled conditions.
- Subsequent ticks drain remaining backlog.
- `receive() == null` terminates the receive loop within that tick cleanly.
- When a handler throws, messages retry/roll back per policy.
- With multiple instances, the limit is per-poller—not a cluster-wide limit.

Seeing M1 and M2 arrive 200 ms apart does not automatically prove **one message per tick** if tick boundaries aren't observed. When strict proof is needed, instrument the scheduler/poller or use a controlled scheduler.

## 11. Testing Business Time with Clock Instead of Sleeping

A business rule like "process only once `effectiveAt` is reached" belongs in a Java class accepting `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;

final class DueTimePolicy {
    private final Clock clock;

    DueTimePolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isDue(Instant effectiveAt) {
        return !clock.instant().isBefore(effectiveAt);
    }
}
~~~

Test three boundary points:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DueTimePolicyTest {
    private final Instant deadline =
            Instant.parse("2026-11-24T00:00:00Z");

    @Test
    void rejectsBeforeDeadline() {
        Clock before = Clock.fixed(
                deadline.minusNanos(1), ZoneOffset.UTC);
        assertFalse(new DueTimePolicy(before).isDue(deadline));
    }

    @Test
    void acceptsExactlyAtDeadline() {
        Clock at = Clock.fixed(deadline, ZoneOffset.UTC);
        assertTrue(new DueTimePolicy(at).isDue(deadline));
    }

    @Test
    void acceptsAfterDeadline() {
        Clock after = Clock.fixed(
                deadline.plusSeconds(1), ZoneOffset.UTC);
        assertTrue(new DueTimePolicy(after).isDue(deadline));
    }
}
~~~

**`Clock.fixed` does not change `TaskScheduler`'s internal clock.** This unit test proves business logic, not real cron/fixedDelay ticks.

Other boundary cases to test:

| Case | Question |
|---|---|
| `now < effectiveAt` | Does it avoid premature processing? |
| `now == effectiveAt` | Is the exact boundary treated as eligible? |
| Different offsets representing the same instant | Are comparisons made on absolute instants? |
| Event rescheduled from old version to new | Is the old schedule cancelled so it does not run twice? |
| Source and processor clocks skewed | What are tolerance and alerting policies? |

## 12. Testing Multiple Ticks with CountDownLatch

To prove a poller **keeps waking up** even when the source is empty, use a counting fake and latch rather than fixed sleeps:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger pollCount = new AtomicInteger();
CountDownLatch twoPolls = new CountDownLatch(2);

MessageSource<String> countingEmptySource = () -> {
    pollCount.incrementAndGet();
    twoPolls.countDown();
    return null;
};

mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", countingEmptySource);

endpoint.start();
assertTrue(twoPolls.await(3, TimeUnit.SECONDS));
assertTrue(pollCount.get() >= 2);
~~~

This proves **at least two invocations of the source**, not that intervals between ticks are exact 200 ms. When measuring real latency, record monotonic times via `System.nanoTime()` in-process with reasonable tolerances under controlled conditions.

### Why Are Timing Assertions So Flaky?

- JVM warmup, GC pauses, and CPU contention in CI.
- Scheduler thread pools shared with other tasks.
- Variable handler and I/O execution times.
- OS schedulers offer no millisecond-exact guarantees.
- Measurement start times differ from when the endpoint actually begins ticking.

Test **semantics and meaningful tolerances**, never `assertEquals(200, elapsedMs)` against wall-clock time.

## 13. Cron, Timezones, and DST

For "02:30 daily in Europe/Berlin," some local date-times **do not exist** during spring-forward DST, or **occur twice** during fall-back DST. Tests should:

1. Parse the cron expression using the Spring/version syntax in use.
2. Specify the timezone explicitly.
3. Compute next executions across month/year boundaries and DST transitions.
4. Confirm policies for skipped or repeated runs.
5. Check backlog behavior after extended downtime.

Never guess outcomes across `CronTrigger` versions; test trigger/calendar logic directly against your exact version and design contract. UTC fits **absolute instants**, while partner schedules may still require **local wall-clock time**.

## 14. Testing Stop, Restart, and In-Flight Work

~~~mermaid
stateDiagram-v2
    [*] --> STOPPED
    STOPPED --> RUNNING: start
    RUNNING --> STOPPING: stop
    STOPPING --> STOPPED: in-flight work settled
    STOPPED --> RUNNING: restart
~~~

| Scenario | What to Confirm |
|---|---|
| Auto-start disabled | No polling prior to setup. |
| Explicit start | Source begins receiving invocations. |
| Stop while idle | No new polls after stop settles. |
| Stop mid-handler | In-flight work honors lifecycle/transaction contract. |
| Restart with backlog | Pending items picked up per metadata/checkpoint. |
| Restart after failure | Connections/metadata recover or fail visibly. |
| Multiple instances running | No duplicate side effects outside policy. |

**`stop()` does not necessarily abort running tasks instantly.** An active handler or pending I/O request may need to finish or time out per configuration. Use latches/barriers to reproduce and observe stop-while-in-flight rather than calling `stop()` and assuming work ceased immediately.

## 15. Teardown and Test Isolation Principles

After a test, ensure:

1. **Stop started endpoints**; await in-flight work per contract where needed.
2. Call `MockIntegrationContext.resetBeans()` to restore substituted sources/handlers.
3. Drain output `QueueChannel`s or use fresh fixtures.
4. Delete test data from filesystems, SFTP servers, DBs, or brokers if used.
5. Close connections and test-owned schedulers/executors.
6. Never share static mocks, queues, or mutable sources across parallel tests.

`resetBeans()` **does not automatically delete files, database rows, Kafka topics, or JMS queues**, nor does it wait for async tasks to finish. Context caching can let endpoints/mocks from earlier tests leak into subsequent tests without thorough cleanup.

## 16. File Inbound: Testing When a File Is Ready

For File polling, **a file existing** does not guarantee **the file is completely written**.

### 16.1. Risks Requiring Tests

- Producer is still writing when the poller picks up the file.
- File is renamed or moved into the directory mid-scan.
- File keeps the same name while its content changes.
- `AcceptOnce` or metadata filters mark a file read before business processing succeeds.
- Two pollers scan the same directory or shared filesystem.
- File modification times have coarse resolution or clock skew with the source.

### 16.2. Ready-Markers or Atomic Renames

~~~text
10:00:00 producer starts writing orders-77.tmp
10:00:05 producer finishes, renames → orders-77.ready
10:00:06 poller scans *.ready
10:00:07 flow emits Message<File> for orders-77.ready
~~~

A common policy: the producer renames the file or drops a marker only after writing completes; the inbound adapter accepts only `*.ready`. Tests must verify **`.tmp` files never enter the flow** and ready files are read with complete bytes. Rename atomicity depends on filesystem/protocol; test network shares or remote filesystems in matching environments.

### 16.3. @TempDir for Fixture Creation

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileReadinessFixtureTest {

    @TempDir
    Path root;

    @Test
    void preparesFileWithReadyMarker() throws Exception {
        Path temp = root.resolve("orders-77.tmp");
        Files.writeString(temp, "id,total\n77,900\n");

        // File inbound adapter test accepts only *.ready.
        // Polling here should still yield empty output.

        Path ready = root.resolve("orders-77.ready");
        Files.move(temp, ready);

        assertTrue(Files.exists(ready));
        assertEquals("id,total\n77,900\n",
                Files.readString(ready));

        // Poll and assert a Message<File> produced by the real adapter.
    }
}
~~~

This snippet demonstrates only **how to prepare the fixture**, not proof that Spring Integration ingested the file. To test real File inbound behavior, configure `FileReadingMessageSource`, filters, directory, poller, and output channel, then assert on the emitted message.

### 16.4. Filters/Metadata and Restarts

| State Type | Required Tests |
|---|---|
| In-memory `AcceptOnce` | While context stays running, file is not re-read per rule. |
| Persistent metadata store | Does the checkpoint survive restarts? |
| File modified after read | Re-read or skipped per contract? |
| Failure after file marked seen | Is there retry/requeue if business side effects didn't complete? |
| Two processes sharing source | Uses designed claim/locking; do not test only inside one JVM. |

**Stop/start endpoint tests inside a single JVM do not prove metadata persists across process restarts** if the store lives in RAM. For durability requirements, recreate the context or process against the production store type.

## 17. SFTP Inbound: Upload Timing, Sync, and Sessions

SFTP inbound can involve **syncing remote files to local** and **emitting local files as messages**. Depending on adapter/mode, filters and metadata sit in two different places. Tests must state explicitly which boundary is under test.

| Scenario | Outcome to Confirm |
|---|---|
| Remote file still uploading | Incomplete file not emitted per ready-marker/rename rules. |
| No new files | Tick returns empty without false errors. |
| File arrives right after tick | Picked up on next tick within SLO. |
| SFTP unavailable | Bounded error/retry; backlog not lost. |
| Session timeout | Reconnects and keeps metadata state consistent. |
| Unexpected host key change | Rejected per trust policy; never disable verification to pass tests. |
| Duplicate filename/mtime | Filter and replay policy verified. |
| Restart mid-download | Partial files and metadata handled safely. |

`MockIntegrationContext.substituteMessageSourceFor(...)` works well for testing **logic after a file is received**, but does not test authentication, host keys, remote directories, transfers, or reconnects. Use an **isolated test SFTP server** to verify protocol behavior and session lifecycles. Never connect to production SFTP.

### 17.1. Separating the Two Tests

**Flow isolation:** fake `MessageSource<File>` feeds a test file from `@TempDir` into the flow; downstream validators/transformers run; outbound mock receives expected payload/headers.

**SFTP transport integration:** upload a file to the test server, start the real inbound adapter, await output, verify local bytes/remote metadata, disconnect, and test recovery.

Name tests accurately: `shouldBuildOrderEventFromSftpLikeMessage` vs. `shouldDownloadReadyFileFromSftpServer`.

## 18. JDBC Inbound: Due Records and Transactions

JDBC polling combines **timing, processing status, transactions, and concurrency**. Suppose a table:

~~~sql
CREATE TABLE inbox_events (
    id            VARCHAR(64) PRIMARY KEY,
    event_type    VARCHAR(80) NOT NULL,
    payload_json  TEXT NOT NULL,
    due_at        TIMESTAMP NOT NULL,
    status        VARCHAR(20) NOT NULL,
    claimed_by    VARCHAR(80),
    created_at    TIMESTAMP NOT NULL
);
~~~

Selecting due records might look like:

~~~sql
SELECT id, event_type, payload_json, due_at
FROM inbox_events
WHERE status = 'READY'
  AND due_at <= :now
ORDER BY due_at, id;
~~~

This query **only illustrates the timing predicate**; it does not prevent races when two instances poll concurrently. Production may require claim/lock/lease mechanisms or atomic status updates tailored to SQL dialect and transaction isolation.

### 18.1. JDBC Test Matrix

| Case | Condition | Expectation |
|---|---|---|
| Not yet due | `dueAt > now` | Not emitted prematurely. |
| Exactly due | `dueAt == now` | Eligible if policy uses inclusive bounds. |
| Past due | `dueAt < now` | Processed; measure delay. |
| Already processed | `status = COMPLETED` | Not re-selected outside policy. |
| Handler throws | Not yet committed | Rolls back/retries without losing record. |
| Two instances polling concurrently | Same `READY` row | No duplicate side effects violating contract. |
| DB loses connection | Multiple failing ticks | Alerts, backoff, recovery. |
| Crash after claim | Claim owner vanishes | Lease/claim recovered per policy. |
| Data inserted mid-batch | Concurrent inserts | No skipped rows from flawed pagination/watermarks. |

### 18.2. H2 Does Not Fully Replace Production DBs

H2 or fake repositories are great for fast logic tests, yet **locking, transaction isolation, timestamp precision, `SKIP LOCKED`, affected rows, and SQL dialects** are engine-dependent. To test real claiming/concurrency, run against the same DB engine as production via Testcontainers or an isolated environment.

DB transactions are **not inherently atomic with HTTP/Kafka/SFTP**. If a flow updates a row and sends an external message, test crashes between those two side effects and the designed outbox/inbox or idempotency mechanism.

## 19. JMS, AMQP, Kafka, and HTTP: Do Not Force One Poller Model

### Message-Driven JMS and AMQP

Inbound listeners are typically invoked by the broker on message arrival rather than via a `SourcePollingChannelAdapter` with `PollerMetadata`. Time-related tests should examine:

- Do listeners start/stop cleanly per lifecycle?
- Are messages sent before listener startup retained by the broker?
- What ack, reject, nack, rollback, or redelivery occurs on handler errors?
- Consumer concurrency, prefetch, and ordering per provider?
- When the broker disconnects, how long until recovery and alerting?

If you actually configure a **polling message source** for JMS/AMQP, add `MessageSource.receive()` and trigger tests. Never assume JMS/AMQP ack semantics equal Kafka's.

### Kafka Inbound

Kafka's **message-driven adapter** uses a listener/consumer container; Kafka's consumer calls `poll()` internally, which is **not the same scheduler poller** as Spring Integration's `MessageSource`.

Test:

- Topics, partitions, keys, serializers, and schemas.
- Consumer pause/resume/start/stop.
- Offset commits per container model.
- Rebalances when consumer counts change.
- Retries/DLT/idempotent side effects.
- Latency between broker append, consume, and business processing.

If using `KafkaMessageSource` as a polling source, test Spring Integration triggers alongside that source's offset/consumer behavior.

### HTTP Inbound Gateway

HTTP inbound is normally triggered by **client requests**, needing no cron/fixedDelay. Time-related tests should examine:

- Server readiness before requests arrive.
- Request/reply timeouts and statuses per contract.
- Correlation under concurrent requests.
- Deadlines/`effectiveAt` derived from trusted data, not just client headers.
- Backpressure/429/overload behavior under request spikes.

If a client runs a scheduler sending periodic HTTP requests, test the **client scheduler** and **server HTTP gateway** as two independent responsibilities.

## 20. Backpressure When Downstream Is Slower Than Inbound

Polling every 100 ms when the handler takes 500 ms can build backlogs or delay subsequent ticks depending on the channel:

| Component | Possible Effect | What to Test |
|---|---|---|
| `DirectChannel` | Synchronous handler blocks poller until complete | Handler duration; no dropped messages. |
| `ExecutorChannel` | Async dispatch grows in-flight tasks | Queue capacity, rejections, shutdown, off-thread errors. |
| `QueueChannel` | Messages buffer until consumer drains | Capacity, backlog, timeouts, cleanup. |
| Outbound broker | Slow send/timeouts/full buffers | Retries, acks, pending state. |

Before testing overload, define **the expected correct outcome**:

1. Does the poller cap messages per tick?
2. Should the source pause or slow down?
3. What is the maximum buffer size?
4. When the queue is full, does it block, reject, retry, or DLQ?
5. How are backlogs drained without duplicating side effects?
6. Are queue depth and oldest unprocessed event age observable?

Test with a latch-blocking handler to induce backpressure, then observe backlog and recovery. Never treat CI machine throughput numbers as production SLOs.

## 21. Retries and Idempotency When Failures Occur Between Ticks

~~~text
T0: MessageSource fetches event E
T1: Handler writes to database successfully
T2: App crashes or ACK is lost
T3: Next poll/restart sees E again
~~~

Without idempotency, event E can trigger duplicate side effects. **Spring-generated message IDs are not guaranteed stable business keys across transforms/replays**, so use a producer/contract-defined business key.

~~~json
{
  "eventId": "evt-2026-00128",
  "eventType": "INVOICE_READY",
  "schemaVersion": 2,
  "availableAt": "2026-11-23T10:00:00Z",
  "effectiveAt": "2026-11-23T10:05:00Z",
  "invoiceId": "INV-128",
  "tenantId": "VN"
}
~~~

### Failure Cases to Test

| Failure | Required Evidence |
|---|---|
| Source throws on first tick | Error observed; subsequent ticks can recover. |
| Handler throws before side effect | Event is not falsely marked complete. |
| DB commits then ACK is lost | Redelivery does not create duplicate invoices. |
| Partial SFTP download | Incomplete file is never treated as ready. |
| JMS/Kafka redelivery after restart | Business event ID deduplicated per policy. |
| Error handler also fails | Alerting/quarantine occurs without losing track of the message. |
| New tick arrives while old tick is still running | No overlap outside contract. |

Never assume **end-to-end exactly-once** merely because a broker supports scoped transactions; DB, HTTP, and file transfers each have separate transaction boundaries.

## 22. Poller Error Channels and Exceptions

Inbound pollers typically run on scheduler threads, so errors may not propagate back to the JUnit test method:

~~~java
MessageSource<String> failingSource = () -> {
    throw new IllegalStateException("source unavailable");
};

mockContext.substituteMessageSourceFor(
        "timedInboundEndpoint", failingSource);
~~~

To test this:

1. Identify the endpoint's configured error handler, error channel, or retry advice.
2. Attach an observation point (e.g., an error `QueueChannel` if matching the flow).
3. Start the endpoint and await the **error event** with a bounded timeout.
4. Assert error/cause and correlation.
5. Verify attempt counts/recovery per config.
6. Stop the endpoint and clean up.

**Do not wrap `endpoint.start()` in `assertThrows` expecting to catch an exception from a later poll tick.** Furthermore, not all errors automatically go to a channel named `errorChannel`; routing depends on where the failure happens and how the Spring Integration endpoint is configured.

### Do Not Equate Different Completion Levels

- Poller invoked source: **attempted to read source**.
- Source returned a message: **message received**.
- Handler ran: **crossed a processing boundary**.
- Outbound returned ACK: **technical acknowledgment received**.
- Target readback confirmed: **final state evidence obtained**, if required by workflow.

A test asserting only `send() == true` never proves the final outcome of a multi-step integration system.

## 23. Two Concurrent Pollers and Race Conditions

A system may run multiple instances for availability. For File/SFTP/JDBC, answer: **can a single record/file be processed multiple times?**

Test scenario:

1. Insert a `READY` record in the test DB.
2. Start two pollers pointing at the shared source.
3. Use a barrier/latch so both try to claim the record nearly simultaneously.
4. Pause instance one's handler before commit.
5. Check whether instance two can claim the same record.
6. Release the barrier and inspect final side effects.
7. Simulate instance one crashing; verify recovery and lease ownership.

**Two threads polling a fake `ConcurrentLinkedQueue` do not prove JDBC row locks or distributed metadata stores are safe.** Distributed concurrency claims must be tested on the real store/transport.

Semantics to document before testing:

- **At-least-once delivery**: messages may be redelivered; side effects must be idempotent.
- **Single claim ownership**: requires locks/leases or atomic state transitions as designed.
- **Ordering guarantees**: typically scoped by key, partition, batch, or specific source; never assume global ordering.

## 24. Data Arriving Between Ticks

~~~text
10:00:00.000 — Tick 1 starts
10:00:00.050 — New file appears
10:00:00.100 — Tick 1 ends
10:00:01.000 — Tick 2 starts
~~~

Verify that if Tick 1 missed the file, Tick 2 still picks it up. This involves **watermarks, file filters, query snapshots, or pagination**, not just scheduler timing.

### JDBC Pagination

`LIMIT/OFFSET` on a table undergoing inserts/deletes can skip or duplicate rows. Test with concurrently changing data and evaluate keyset pagination, claims, or watermarks where designed.

### File/SFTP mtime

Never rely solely on mtime to decide a file is new: timestamp granularity and source clock skew vary. Test identical filenames, equal mtimes, renames, and content updates per contract.

## 25. Time-Related Metrics Worth Measuring

| Metric | Definition | Caveat |
|---|---|---|
| **Poll attempts** | Source invocations in a window | Not equal to business message count. |
| **Empty poll ratio** | `receive() == null` / total receive attempts | Naturally high when data is sparse. |
| **Source-to-dispatch latency** | `dispatchedAt − availableAt` | Requires knowing exact source readiness time. |
| **Deadline lateness** | `processedAt − effectiveAt` for overdue cases | Early processing needs its own indicator. |
| **Oldest pending age** | Age of oldest incomplete file/event | Reveals stalls better than raw throughput. |
| **Retry aging** | Age and attempt count of unrecovered items | Do not count retries as new business events. |
| **Duplicate side-effect count** | Side effects exceeding expectation per event ID | Requires business keys and evidence. |
| **Recovery duration** | Time from source recovery until backlog drains | Not the same as reconnect time. |

Inspect **P50/P95/P99 latency of verified work** alongside **pending counts, overdue counts, and oldest pending age**. Reporting latency only for successful tasks hides stuck items. Never turn CI machine timings into production SLAs without proper baselines and risk analysis.

## 26. Comprehensive Test Matrix

| # | Scenario | Test Layer | Expected Outcome |
|---:|---|---|---|
| 1 | Endpoint `noAutoStartup` | Controlled flow | No polling before start. |
| 2 | Empty source | Controlled flow | `receive()` called, no message emitted. |
| 3 | Single-message source | Controlled flow | Payload/headers valid, no infinite emission. |
| 4 | Three messages, `maxMessagesPerPoll=1` | Poller/scheduler | Capped per tick, backlog drained over ticks. |
| 5 | Fixed delay with slow handler | Scheduler | Delay matches semantics within tolerance. |
| 6 | Fixed rate under overload | Scheduler | No overlap outside policy. |
| 7 | Cron across month-end | Trigger unit test | Valid next execution. |
| 8 | Cron across DST | Trigger unit test | Times match zone and policy. |
| 9 | Future `effectiveAt` | Clock unit test | Not processed early. |
| 10 | Exact `effectiveAt` boundary | Clock unit test | Matches inclusive/exclusive rule. |
| 11 | Rescheduled/versioned event | Domain + flow | Old schedule triggers no side effects. |
| 12 | `.tmp` file being written | File integration | Not emitted before ready. |
| 13 | `.ready` file | File integration | Emitted with full contents. |
| 14 | File modified after poll | File integration | Filter/metadata follows contract. |
| 15 | SFTP disconnect | SFTP integration | Alerts, reconnects, no lost backlog. |
| 16 | Partial SFTP transfer | SFTP integration | Incomplete file never processed. |
| 17 | JDBC row not yet due | DB integration | Not claimed early. |
| 18 | Two pollers claiming same row | DB concurrency | No duplicate side effects outside policy. |
| 19 | JDBC rollback | DB integration | Record recoverable, no data loss. |
| 20 | Source throws exception | Controlled flow | Error path/recovery observed. |
| 21 | Handler fails then succeeds | Flow + transport | Retries/attempts/idempotency accurate. |
| 22 | Stop mid-in-flight | Lifecycle | Graceful behavior per contract. |
| 23 | Restart after checkpoint | Transport/recovery | No skipped items; duplicates handled. |
| 24 | Kafka/JMS listener pause/restart | Broker integration | Ack/offset/redelivery accurate. |
| 25 | HTTP inbound timeout | HTTP integration | Status/correlation/timeout accurate. |
| 26 | Duplicate event ID | Flow + persistence | No duplicate business side effects. |
| 27 | Same filename across tenants | Flow + adapter | No cross-tenant routing. |
| 28 | Parallel CI execution | Fixture isolation | No queue/file/DB/mock contention. |

For every test, record **inputs, trigger config, initial state, observation point, timeout, cleanup, and evidence limits**. Observing zero messages over 1 ms does not prove the scheduler won't misbehave.

## 27. Case Study: SFTP Inbound Receiving Periodic Financial Reports

A partner uploads CSVs to SFTP. The application must poll periodically, accept only completed files, validate tenants, transform into events, and forward to an internal system. Files can arrive late, networks can drop, and the same report can be re-uploaded.

~~~mermaid
flowchart LR
    PARTNER["SFTP partner<br/>*.tmp → *.ready"] --> SYNC["SFTP sync / source"]
    CLOCK["Poller schedule"] --> SYNC
    SYNC --> CH["fileInput channel"]
    CH --> VALID["CSV/tenant validation"]
    VALID --> TRANSFORM["ReportEvent transform"]
    TRANSFORM --> OUT["Outbound adapter"]
    SYNC --> META["Metadata/filter"]
    VALID --> ERR["Reject/quarantine"]
~~~

### Suite A — Clock and Business Contract

- Files whose `effectiveAt` has not arrived trigger no business side effects.
- Test before, at, and after deadline with `Clock.fixed`.
- Test rescheduled effective dates, timezones, and schema versions.

### Suite B — Flow Isolation

- Use `MockIntegrationContext` to replace the inbound source with `Message<File>` from `@TempDir`.
- Keep real parsers/validators/transformers/channels.
- Mock the outbound handler and verify `eventId`, `tenantId`, and payload.
- Schema-invalid files must never reach the outbound boundary.

### Suite C — SFTP Integration

- Use a test SFTP server with dedicated host keys and accounts.
- Upload `*.tmp` and verify it isn't emitted; rename to `*.ready` and read accurate bytes.
- Test outages, reconnects, filters, duplicate filenames, and restarts.
- Inspect metadata and local outputs to verify side effects.

### Suite D — End-to-End

- Run SFTP, polling flow, and a test target system.
- Confirm files produce the right final outcomes.
- Simulate outbound succeeding then timing out; verify idempotency.
- Restart the application and reconcile backlogs and pending states.

**Success criteria:** no premature file reads, no skipped ready files, no duplicate side effects outside policy, correlation/event IDs preserved, error recovery works, and target evidence exists.

## 28. Designing CI to Eliminate Flakiness

1. **Separate fast suites from transport suites:** unit/flow on every PR; SFTP/DB/broker integration on adapter changes or CI schedules.
2. **Never use `Thread.sleep` as primary synchronization:** latches, channels, and bounded waits are superior.
3. **Bounded timeouts:** generous enough for test environments without hanging indefinitely.
4. **Isolated namespaces:** files, SFTP paths, topics, queues, DB rows, and correlation IDs per test.
5. **Explicit clocks:** inject `Clock` into domain logic; configure explicit timezones for cron.
6. **Never hardcode cron targets near wall-clock boundaries:** test next-execution logic via trigger unit tests.
7. **Manage lifecycles:** start after setup; stop and settle in-flight work during teardown.
8. **Reset mocks:** call `MockIntegrationContext.resetBeans()` whenever substitutions occur.
9. **Clean metadata:** filters/checkpoints, queues, files, brokers, DBs.
10. **Never touch production:** all transport tests use isolated resources.
11. **Never leak secrets:** use test fixtures/credentials per CI policy.
12. **Capture diagnostic evidence on failure:** endpoint ID, test ID, timestamp, attempts, message/business ID, and observed state.

### Context Caching

Spring Test can reuse `ApplicationContext`s. An unstopped poller or undrained queue feeds stale data into the next test. Resetting substitutions alone does not clean up external resources. `@DirtiesContext` helps if context mutations cannot be undone, yet rebuilding contexts is costly and no substitute for proper lifecycle management.

## 29. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Fixed sleep then assert | Flaky under CPU/GC load | Use latches or bounded-timeout observation points. |
| Fake source always returns same message | Duplicates on every tick | Finite fake returning `null` when exhausted. |
| Auto-start before setup | Reads real sources/stale files | `noAutoStartup` and explicit start. |
| Not stopping poller | Side effects continue after test | Stop and await in-flight work per contract. |
| Forgetting `resetBeans()` | Earlier test's mock affects later test | Reset in teardown. |
| Asserting millisecond-exact timings | Fails randomly in CI | Tolerances and trigger unit tests. |
| Thinking `Clock.fixed` speeds up scheduler | Confuses domain clock and scheduler | Separate both test types. |
| Thinking `maxMessagesPerPoll=1` means one-shot | Multiple ticks still emit more messages | Understand per-tick limits. |
| Treating Kafka listener like Spring poller | Uses wrong APIs/metrics | Test consumer containers and offsets. |
| Mocking SFTP then claiming upload/download works | Zero protocol evidence | Test against a real SFTP server. |
| Testing restart only within same JVM | Doesn't prove persistent checkpoints | Recreate context/process with real store. |
| Using H2 to prove production locking | Different dialect/isolation | Test against matching DB engine. |
| Counting successful sends only | Downstream may still fail | Readback/final target state verification. |
| Ignoring timezones/DST | Cron runs at wrong times or twice | Explicit zones and calendar tests. |
| Using filename alone as business ID | Breaks on re-uploads/tenant collisions | Scoped event key. |
| Sharing queues/files in parallel tests | Races and mixed data | Isolate fixtures and teardown. |

## 30. Practice Exercises

### Exercise 1 — Controlled Polling Flow

Create a `MessageSource<String>` emitting three messages, a `QueueChannel` receiving results, and a fixed-delay poller.

Requirements:

1. Use `@SpringIntegrationTest(noAutoStartup = "...")`.
2. Assign an explicit endpoint ID.
3. Substitute the source via `MockIntegrationContext` before starting.
4. Receive all three messages with bounded waits.
5. Confirm no endless emissions occur after the queue drains.
6. Stop, call `resetBeans()`, and drain the channel.

### Exercise 2 — Testing Business Time

Write `DueTimePolicy` taking `Clock` and `effectiveAt`. Test before, exactly at, and after the deadline, different offsets for the same instant, plus a rescheduled event `v1 → v2`. Explain why these unit tests do not prove real cron/fixedDelay behavior.

### Exercise 3 — File Readiness

Build a File inbound adapter scanning `@TempDir` for `*.ready` only. A producer writes `*.tmp` then renames upon completion. Verify the adapter ignores temp files, emits full contents of ready files, handles stop/restart, and updates metadata. Add a case where a file with the same name is updated per policy.

### Exercise 4 — SFTP or JDBC

Pick one:

- **SFTP:** test server, ready markers, host keys, outages, and restarts.
- **JDBC:** test DB, `dueAt`, row claiming, two competing pollers, and rollbacks.

Write the happy path plus at least three failure cases; document **inputs, observation points, timeouts, expected outcomes, and target evidence**.

### Exercise 5 — Polling vs. Message-Driven

Design two flows ingesting `ORDER_CREATED`: a JDBC inbound polling adapter reading an inbox table, and a Kafka message-driven adapter reading a topic. Compare start/stop, batch counts, retries, ordering, commit/offset, restarts, and backpressure. Identify where `MockIntegrationContext` applies and where real DB/Kafka is mandatory.

### Exercise 6 — Testing SLOs and Recovery

A partner sends SFTP files every 15 minutes. Define `availableAt`, `receivedAt`, `verifiedAt`, and latency/pending formulas. Design a 20-minute outage test and duplicate-upload test; choose SLO thresholds based on risk/baselines rather than treating illustrative numbers as defaults.

## 31. Acceptance Checklist

- [ ] **Inbound type classified**: polling source, listener, or HTTP gateway.
- [ ] **Trigger documented**: fixed delay/rate/cron, timezone, and semantics.
- [ ] **Explicit endpoint ID** for source substitution and lifecycle control.
- [ ] **`noAutoStartup`** applied where polling before fixture setup must be prevented.
- [ ] **Finite fake source**, returning `null` once exhausted.
- [ ] **Business clock** decoupled from scheduler clock.
- [ ] **Bounded timeouts**, never relying on sleeps as primary synchronization.
- [ ] **`maxMessagesPerPoll`** correctly treated as a per-tick limit.
- [ ] **Startup/stop/restart and recovery** tested.
- [ ] **File/remote readiness, metadata, and DB transactions** tested on appropriate sources.
- [ ] **Duplicates/idempotency** tested when redelivery is possible.
- [ ] **Concurrency/locking** tested on real backing stores when required.
- [ ] **Broker acks/offsets** not confused with Spring pollers.
- [ ] **Mocked boundaries** never mistaken for real side effects.
- [ ] **Endpoint/channel/mock/metadata cleanup** runs after every test.
- [ ] **Never touches production or leaks credentials** in tests.
- [ ] **Test matrix and observation points** accurately reflect what was proven.

## 32. Summary

Testing **time-based inbound adapters** starts by identifying whether the source is driven by a **poller** or by **external events**. For polling adapters, `@SpringIntegrationTest(noAutoStartup = "...")`, `MockIntegrationContext`, finite fake `MessageSource`s, `QueueChannel`s, and start/stop lifecycles enable fast, deterministic flow tests. For business deadline/expiry rules, `Clock` lets tests exercise exact time boundaries without sleeping.

Concerns like **incomplete files, SFTP reconnects, JDBC locking/transactions, Kafka/JMS/AMQP acks/offsets, HTTP gateway timeouts, retries, idempotency, and post-restart recovery** must be verified with the matching adapters and transports. A trustworthy test states **when it received data, from which source, with what payload, how many times it ran, what remains unverified, and what evidence proves the outcome at the exact boundary**.
