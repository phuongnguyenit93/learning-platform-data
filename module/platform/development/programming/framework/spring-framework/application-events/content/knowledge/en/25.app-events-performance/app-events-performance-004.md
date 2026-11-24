# Large Payloads and Memory Pressure in Spring Application Events

An application event typically only needs to describe **what happened**: the aggregate ID, event type, version, and the minimal data needed for listeners to proceed. If we put entire files, images, large JSON strings, object/JPA entity graphs, or lists of tens of thousands of elements into an event, the cost does not stop at the object's size at the moment of `publishEvent(...)`. When listeners process slowly or asynchronously, objects can be **held by references in a queue**, increasing live heap, increasing garbage collection (GC) pressure, causing latency, and eventually leading to `OutOfMemoryError`.

This is a problem of **object lifetime and live object count**, not just “how many bytes a Java object weighs”. Spring Framework Application Events is an in-application-context communication mechanism, **not a durable message queue with automatic backpressure**. This lesson explains payload retention mechanisms, estimating memory pressure, safe design alternatives, bounded queue executor configuration, and how to test on Java 17+ with Spring Test.

## 1. What is a large payload and when is it dangerous?

A payload is the data carried by an event. Since Spring Framework 4.2, you can publish a plain Java object, such as `record ReportCreated(...)`. Spring wraps objects that do not extend `ApplicationEvent` in a `PayloadApplicationEvent` for dispatch. This wrapping **does not automatically serialize or deep-copy the entire object graph**.

Example of an event prone to memory pressure:

~~~java
record ReportGenerated(
    String reportId,
    byte[] pdfBytes,
    String customerId
) {}
~~~

When each PDF file is several MiB and each request allocates its own `byte[]`, the event holds a reference to that array. `record` makes field references final, **but does not make `byte[]` contents immutable**; another thread can still mutate its elements.

In practice, large payloads can also take the form of:

- `String` holding large XML/JSON;
- `List<OrderLine>` with hundreds of thousands of elements;
- JPA entities carrying full relationships or lazy-loading proxies;
- `Map<String,Object>` holding copies of request data;
- `byte[]`, `ByteBuffer`, images, documents, compressed archives;
- any object whose `toString()` or JSON serialization creates an additional huge copy.

“Large” depends on **event frequency, number of listeners, wait time, heap size, and copying behavior**. An occasional 8 MiB event might be fine in synchronous work; however, 200 distinct 4 MiB events waiting in a pool is concerning even if each individual object seems unremarkable.

## 2. Why can events hold memory longer than expected?

Consider the conceptual reference graph:

~~~text
ApplicationEventPublisher.publishEvent(reportGenerated)
                   |
                   v
      PayloadApplicationEvent / event object
                   |
                   +----> ReportGenerated
                                 |
                                 +----> byte[] pdfBytes (4 MiB)

If the listener is synchronous:
  publisher thread -> listener uses payload -> stack unwinds
  (if no other references remain, the payload can be GC'd)

If the listener is @Async:
  publisher thread -> submits Runnable into executor queue
                          |
                          +----> task/lambda/proxy holds event
                                       |
                                       +----> byte[] (4 MiB)
  An unexecuted task still keeps a strong reference path to the data.
~~~

**GC reclaims an object only when no live reference path reaches it.** Returning from `publishEvent` does not mean the object has become eligible for collection: an executor queue, listener, `CompletableFuture`, cache, retry buffer, or another application structure may still retain it.

Distinguish between:

1. **Allocation:** creating new objects or copies increases memory allocation rate.
2. **Retention:** an object remains reachable and therefore cannot yet be collected.
3. **GC pressure:** the system must trace/collect many objects; if the live set grows too large, heap headroom shrinks.
4. **True memory leak:** holding references longer than needed; not every transient heap spike is a leak.
5. **Extra copies from serialization:** `byte[]` -> Base64/JSON/String can create multiple intermediate buffers; the impact differs from a single reference.

A listener can hold the same object by reference (without copying) and still cause substantial **retained memory**. Conversely, if multiple events reference the same immutable object, you cannot multiply payload size by event count and assume that much new memory was allocated.

## 3. Estimating memory pressure via live outstanding events

For **distinct, unshared** payloads, a very rough estimate is:

~~~text
retained_payload_bytes ≈ distinct_outstanding_events × bytes_reachable_per_event

Example:
  each event contains a ~4 MiB byte[]
  about 200 distinct unprocessed events
  payload data alone is roughly 800 MiB
~~~

This is **not total measured heap** and not an exact upper bound: there are also event wrappers, executor tasks, queue nodes, object graphs, String/collection overhead, duplicated JSON buffers, and other references. The 4 MiB `byte[]` here is an example to illustrate order of magnitude, not a size automatically readable from a record.

When measuring performance, another useful model is the throughput–wait-time relationship:

~~~text
outstanding ≈ arrival_rate × average_time_in_system

Example (near steady state):
  50 events/sec × average 4 seconds per event waiting/processing
  -> roughly 200 outstanding events
~~~

This is an approximate deduction from Little's Law and holds only under appropriate assumptions such as a near-steady-state system. When the arrival rate exceeds processing capacity for an extended period, the queue can **keep growing**, so steady-state formulas must never be used to guarantee a ceiling.

### Why “adding threads” may not solve it

If the bottleneck is the DB, broker, external API, or disk, increasing worker count can cause more tasks to simultaneously retain payloads and increase pending connections/requests. Heap worsens while downstream gets overloaded further. Conversely, shrinking queue capacity without an appropriate rejection/backpressure policy can expose high-load failures directly to the caller.

You need to determine **payload size × live count × lifetime**, not just count requests or look at a single `usedHeap` snapshot.

## 4. Synchronous listeners, @Async, and custom multicasters retain payloads differently

| Mechanism | Main behavior | Memory risks to watch |
| --- | --- | --- |
| Default synchronous `@EventListener` | Executes on publisher thread; `publishEvent` may block | Payload stays on the call stack longer if the listener is slow; caller throughput drops |
| `@Async @EventListener` | Async proxy submits invocation to a separate executor | Pending Runnable/task can hold references to large payloads |
| `SimpleApplicationEventMulticaster.setTaskExecutor(...)` | Multicaster schedules listeners supporting async execution | Task count can multiply by listener count; task rejection behavior varies by version/config |
| `@TransactionalEventListener` | Listener bound to a transaction phase; usually registers synchronization before execution | Event can be retained until commit/rollback completion |
| Broker/outbox | Message is stored outside the in-memory event bus | Incurs serialization/persistence cost; large payloads still need separate management |

Under the default configuration, Spring uses `SimpleApplicationEventMulticaster` and handles listeners synchronously. `@Async` is a separate mechanism: a method proxy submits tasks to an executor. If a custom multicaster also uses an executor, you must understand **both scheduling layers** and their exception/queue semantics rather than assuming they behave identically.

**Important warning:** do not rely on a single task-rejection behavior across all multicasters/versions. Some implementations/versions may handle `RejectedExecutionException` by running on the caller thread, whereas an `@Async` proxy with `ThreadPoolTaskExecutor` can throw `TaskRejectedException`. Test **the exact configuration in use**, especially when transactions live on the publisher thread.

## 5. Designing small events: metadata instead of binary data

Instead of:

~~~java
// Anti-pattern: event carries the entire file.
public record ReportReady(
    String reportId,
    byte[] pdfBytes,
    String recipientEmail
) {}
~~~

Prefer an event with an identifier, version, and a reference to durable storage:

~~~java
public record ReportReady(
    String eventId,
    String reportId,
    String objectKey,
    long contentLength,
    String checksumSha256
) {}
~~~

These are **two independent data options**, each record needing its own matching Java file if declared as a `public` top-level type. `objectKey` in the second example should point to storage with proper durability, expiration policy, and access control (object store, blob store, database). Do not turn it into a presigned URL carrying long-lived tokens in events or logs.

Better processing flow:

~~~text
Application service
  -> create file / stream to durable object storage
  -> obtain objectKey, size, checksum
  -> publish ReportReady(eventId, reportId, objectKey, ...)
          |
          +-- Listener reads small metadata
                 |
                 +-- if bytes are needed, open stream from storage in chunks
                 +-- process/forward
                 +-- close stream and release resources
~~~

This is not a rule that “every payload must be tiny”. If a listener directly processes a DTO of a few KB, there is no reason to force a remote storage round trip. The principle is that **the payload carries only the data required by the event contract**, while large binary data should use appropriate storage or streaming.

### Do not put managed JPA entities in async events

~~~java
// Prone to issues: retaining the entire entity graph.
publisher.publishEvent(new OrderImported(orderEntity));
~~~

`OrderImported` is an application-defined example type. If the entity contains collections/lazy proxies, a listener running after the transaction/session closes may encounter `LazyInitializationException`. A mutable entity can also be modified after publish, causing the listener to read an inconsistent snapshot.

Choose an immutable DTO with IDs and minimal values. If exact data at event time is needed, store a **field-selected snapshot DTO** or a version in storage; if only the ID is passed and the listener reloads at runtime, it may observe **newer state** from subsequent aggregate updates. Clearly define semantics between “current state” and “state at event time”.

## 6. Immutable payloads: do not confuse record with deep immutability

Example:

~~~java
public record BinaryEvent(String id, byte[] bytes) {}
~~~

`bytes` is a final reference, yet the array itself remains mutable. Tests/production can suffer races:

~~~java
byte[] original = {1, 2, 3};
BinaryEvent event = new BinaryEvent("E-1", original);
original[0] = 9;
// event.bytes()[0] has become 9 even though the event record's fields did not change.
~~~

If the payload truly needs an immutable snapshot, you can defensively copy, though copying large data costs memory and CPU. A standalone Java 17 example illustrates this:

File `DefensiveCopyDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DefensiveCopyDemo {
    public record Snapshot(byte[] bytes) {
        public Snapshot {
            Objects.requireNonNull(bytes, "bytes");
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Snapshot snapshot = new Snapshot(input);
        input[0] = 9;

        byte[] someoneElse = snapshot.bytes();
        someoneElse[1] = 8;

        System.out.println(Arrays.toString(snapshot.bytes()));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Exact stdout:

~~~text
[1, 2, 3]
~~~

Here the constructor copies the data once, and the accessor copies again on read. This is a safe design for **small array examples**, but for files of hundreds of MiB it becomes very expensive. When immutability cannot be guaranteed at reasonable cost, use **a reference to an immutable object in storage**, or a streaming/ownership-transfer API with a clear contract, instead of passing a shared array and hoping nobody mutates it.

## 7. Bounded executors: preventing backlogs from holding payloads indefinitely

A `ThreadPoolTaskExecutor` can configure `corePoolSize`, `maxPoolSize`, `queueCapacity`, and a task rejection policy. **The queue must be bounded appropriately for load and payload size**, not merely theoretical request counts.

~~~java
@Configuration
@EnableAsync
class EventExecutorConfig {

    @Bean("largePayloadExecutor")
    ThreadPoolTaskExecutor largePayloadExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("large-event-");
        return pool;
    }
}
~~~

This is a **Spring configuration snippet**; it requires `@Configuration`, `@EnableAsync`, `@Bean`, and `ThreadPoolTaskExecutor` imports. When a listener is annotated with `@Async("largePayloadExecutor")`, method invocations go through this pool.

With the underlying `ThreadPoolExecutor` when the queue has positive capacity, typical behavior is: create up to core workers, then enqueue; only when the queue is full are additional threads created up to max; when both threads and queue are full, the rejection policy applies. Therefore, **`maxPoolSize=20` with a huge queue does not mean the system will quickly spin up 20 workers**.

### Task rejection is not complete backpressure

When the executor stops accepting more work, you need a **handling contract**:

- Critical tasks that must not be lost: do not rely solely on in-memory async events; persist durable work/outbox and redeliver in a controlled manner.
- Droppable tasks: record dropped metrics and state the policy explicitly; never silently drop mandatory business work.
- Self-throttling callers: rate limits, bounded semaphores, bounded ingestion queues, or returning retryable errors with backoff.
- `CallerRunsPolicy`: can make the publisher run the work itself to slow down, but **alters thread, latency, and transaction/security context semantics**. Must be tested in reality, not used carelessly.

In Spring, `TaskRejectedException` is a failure mode to monitor. With an `@Async` proxy, rejected submission can cause `publishEvent` to throw immediately at scheduling time, even though exceptions thrown **inside an async listener's body** typically do not propagate back to the publisher. The two cases are very different.

## 8. Java 17+ integration test: verifying reference sharing and bounded queues

This example uses Spring Framework, JUnit 5, and a `ThreadPoolTaskExecutor` with **1 worker + 1 pending slot**. We create three distinct event payloads (each containing a 1 MiB array):

1. The first event enters the worker and is blocked by `CountDownLatch`, proving the listener receives **the exact same array** passed by the publisher.
2. The second event is enqueued (queue size equals 1).
3. The third event is rejected because both worker and queue are full; the test asserts `TaskRejectedException`.
4. At the end of the test, the worker is released; both the first and second events complete. There is no forced GC or comparing `Runtime.freeMemory()`, which tends to be flaky.

### 8.1. settings.gradle and build.gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'large-event-payload-tests'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-aop'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.2. src/test/java/example/events/LargePayloadPressureTest.java

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(LargePayloadPressureTest.Config.class)
class LargePayloadPressureTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired Probe probe;

    @Autowired
    @Qualifier("boundedPool")
    ThreadPoolTaskExecutor pool;

    @AfterEach
    void cleanup() {
        // Do not keep the worker blocked indefinitely if an assertion fails.
        probe.release.countDown();
    }

    @Test
    void queueIsBoundedAndListenerGetsOriginalPayload() throws Exception {
        byte[] firstBytes = new byte[1024 * 1024];

        try {
            publisher.publishEvent(
                new LargeEvent("first", firstBytes));

            assertTrue(probe.firstStarted.await(5, TimeUnit.SECONDS));

            // Listener sees the same byte[] reference; Spring does not
            // automatically deep-copy the whole payload before dispatch.
            assertSame(firstBytes, probe.firstPayload.get());

            publisher.publishEvent(
                new LargeEvent("second", new byte[1024 * 1024]));

            assertEquals(
                1,
                pool.getThreadPoolExecutor().getQueue().size()
            );

            assertThrows(
                TaskRejectedException.class,
                () -> publisher.publishEvent(
                    new LargeEvent("third", new byte[1024 * 1024]))
            );
        } finally {
            probe.release.countDown();
        }

        assertEquals(
            "first",
            probe.completed.poll(5, TimeUnit.SECONDS)
        );
        assertEquals(
            "second",
            probe.completed.poll(5, TimeUnit.SECONDS)
        );
    }

    record LargeEvent(String id, byte[] bytes) {}

    static class Probe {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final AtomicReference<byte[]> firstPayload = new AtomicReference<>();
        final BlockingQueue<String> completed =
            new LinkedBlockingQueue<>();
    }

    static class Listener {
        private final Probe probe;

        Listener(Probe probe) {
            this.probe = probe;
        }

        @Async("boundedPool")
        @EventListener
        public void onLarge(LargeEvent event) {
            if ("first".equals(event.id())) {
                probe.firstPayload.set(event.bytes());
                probe.firstStarted.countDown();

                try {
                    if (!probe.release.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("gate timeout");
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("interrupted", ex);
                }
            }

            probe.completed.offer(event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync(proxyTargetClass = true)
    static class Config {
        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        Listener listener(Probe probe) {
            return new Listener(probe);
        }

        @Bean("boundedPool")
        ThreadPoolTaskExecutor boundedPool() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(1);
            pool.setThreadNamePrefix("bounded-events-");
            return pool;
        }
    }
}
~~~

### 8.3. Running the test and interpreting the conclusion properly

With the Gradle wrapper in the project:

~~~bash
./gradlew test --tests "example.events.LargePayloadPressureTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.LargePayloadPressureTest"
~~~

The test is expected to **PASS** under the `@Async` proxy + `ThreadPoolTaskExecutor` model above. It proves **reference sharing and bounded queue behavior**, not exact heap measurements or a guarantee that the entire system uses at most 2 MiB. The third event was already allocated on the caller before submission failed; other references outside the executor may still exist.

Why does the example use `1 worker + 1 queue slot`? While the first worker waits at the gate, the second task is deterministically in the queue; the third task has no remaining capacity. The test does not depend on CPU speed or arbitrary sleeps. When the gate is released, both events are processed, and JUnit asserts the IDs in order on the single worker.

**Test limitations:** it exercises one executor and one listener; it does not evaluate serialization, additional listeners, JPA entity graphs, external retries or buffers, nor does it directly measure GC. Production requires load testing and additional instrumentation. If switching to a custom multicaster executor, write dedicated tests for how that multicaster handles rejected tasks.

## 9. Monitoring heap, queues, and latency with real metrics

To understand memory pressure from application events, `used heap` alone is insufficient. Combine:

| Metric | Observed value | Why it matters |
| --- | --- | --- |
| `queue.size` and `queue.remainingCapacity` | Pending tasks | A large queue can retain event payloads for a long time |
| `activeCount`, `poolSize` | Busy/available workers | Indicates saturation and concurrency effectiveness |
| Rejected submissions | Overload count | Detects when backpressure/rejection policy triggers |
| Event processing latency | Actual processing time | Finds listener/downstream bottlenecks |
| Queue wait time | Delta submit -> start | Measures how long payloads may be retained before processing |
| Heap used, live set after GC | Live bytes | Detects lingering payload references |
| GC pause/time/allocation rate | GC impact | Distinguishes allocation spikes from prolonged retention |
| Event count/size percentiles | P50/P95/P99 of payload size | Identifies outliers rather than averages alone |

With `ThreadPoolTaskExecutor`, Spring provides `getActiveCount()`, `getPoolSize()`, and access to `getThreadPoolExecutor().getQueue()` for introspection. In Spring Boot, Micrometer/Actuator or internal metrics tools can record corresponding metrics depending on configuration. Avoid using `eventId` or `aggregateId` as **metric tags** due to high cardinality.

In Java 17+ JVMs, you can use **Java Flight Recorder (JFR)**, GC logs, heap histograms, or heap dumps appropriate for the environment to identify object types and allocation/retention sites. Heap dumps can contain sensitive data (payloads, secrets); apply access controls, store securely, and delete per retention policy. `System.gc()` or forcing GC in unit tests is not a reliable way to prove memory has been freed.

### Simple load experiment

1. Measure a baseline with events carrying only an ID.
2. Measure the same throughput with events carrying an extra distinct 1 MiB payload.
3. Keep worker count, queue capacity, and downstream processing time constant.
4. Collect queue depth, enqueue rejections, processing latency, heap after GC, and allocation rate.
5. Compare P95/P99 latency and live heap instead of a single snapshot.
6. Repeat with an ID-only event + storage reference; include I/O costs to evaluate the trade-off.

Never conclude “creating a 1 MiB object means heap permanently grows by 1 MiB”, because data may be reclaimed immediately, shared, compressed differently, or reside off-heap. What must be measured is the **retained live object graph** under realistic load.

## 10. Large payloads, transactions, and async consistency

Events with large payloads often appear when business workflows process documents, data imports, or reports. If published inside `@Transactional`, a long-running synchronous listener can prolong the transaction, holding locks and connections longer than needed.

~~~text
BEGIN DB TRANSACTION
  UPDATE reports SET state='READY'
  publish ReportReady(large byte[])
      -> synchronous listener compresses/uploads file: 3 seconds
  COMMIT
~~~

In this flow, the transaction remains open while the synchronous listener runs. Changing the listener to `@Async` can shorten publisher blocking time, **but does not automatically ensure the listener reads committed data**: the worker may run before commit and see stale state.

If the listener requires committed data:

- Use `@TransactionalEventListener(phase = AFTER_COMMIT)` with clear semantics; if post-commit work is heavy, offload work to an appropriate executor *after* the commit milestone.
- If processing intent must not be lost on process crash, use a **transactional outbox / event publication registry** or durable queue with retries and idempotency.
- In records sent via an outbox, store **metadata/references** to object storage; do not stuff entire large files into a message/outbox row unless DB/broker costs and retention requirements have been accounted for.
- Ensure the file/object is durably stored before publishing an event pointing to it; coordinate file lifecycle with the DB transaction using deliberate compensation/cleanup procedures on failure.

Do not assume `@Async` automatically transfers the JDBC transaction, `SecurityContextHolder`, or MDC to the worker. If the listener must reload an entity by ID, open an appropriate transaction/authorization context in its own work.

## 11. Managing large data via storage and streaming

A design using an object store and event IDs is only effective when these cases are addressed:

| Aspect | Design question |
| --- | --- |
| Durability | Is the object fully uploaded before the event can be processed? |
| Visibility | Can the consumer see the object given storage consistency and permissions? |
| Authorization | Who may read `objectKey`, and under which service identity? |
| Lifetime | How long must the object remain for retries, audits, and replays? |
| Integrity | Is there a checksum/version to detect modified objects? |
| Retry | How does the consumer re-read idempotently after failures? |
| Cleanup | If the transaction rolls back or delivery is cancelled, how are orphaned objects cleaned up? |
| Streaming | Does the consumer read in chunks, bound concurrent streams, and close resources? |

Contract example:

~~~java
public record ImageProcessed(
    String eventId,
    String imageId,
    String objectKey,
    long sizeBytes,
    String sha256,
    int schemaVersion
) { }
~~~

This is a standalone Java record without the raw file. The consumer validates IDs, access control, object metadata, size, and checksum before consuming. **Do not treat `objectKey` or an arbitrary URL as proof of authorization.**

When large files must be processed, prefer `InputStream`, channels, or reactive streaming APIs depending on backend capabilities, using bounded-size buffers. However, never place an open `InputStream` inside an application event for an async listener to read after the HTTP request ends: the stream may already be closed, is not safe for concurrent use, and cannot be replayed.

## 12. Common design mistakes

**1. Publishing multi-MiB `byte[]` directly into an unbounded executor queue.** Every pending task retains data until processed; heap can grow with the backlog. Use small metadata events, bounded queues, and an overload policy.

**2. Assuming Spring deep-copies events automatically.** `PayloadApplicationEvent` generally keeps a reference to the payload object rather than cloning it. If the producer mutates an array or list after publish, an async consumer may see mutated data. Design immutable objects or deliberate snapshots.

**3. Only raising `-Xmx` to cure backlogs.** A larger heap may delay OOM without fixing an arrival rate exceeding processing rate; GC/live set can keep growing. Find the bottleneck, measure queue depth, and add backpressure.

**4. Setting a huge `maxPoolSize` alongside an unbounded queue.** The executor may prefer queuing when core workers are busy. Raising max does not necessarily engage workers as expected. Understand the queuing strategy and test it.

**5. Using `DiscardPolicy` for critical business events.** Tasks can be silently dropped with no automatic retry/durable log. Choose an outbox/broker if loss is unacceptable.

**6. Using `CallerRunsPolicy` while forgetting transactions.** When the pool is full, an “async listener” can execute on the caller thread; latency, exception behavior, and context change. Use only when you understand the contract and have tested it.

**7. Putting `List<Entity>` or lazy proxies in events.** Can retain entire persistence graphs, hit lazy-loading errors after the transaction, or fail to reflect a snapshot. Choose IDs, versions, and small DTOs.

**8. Creating multi-layer copies without measuring.** Serializing to JSON, Base64-encoding, logging full payloads, then copying into an HTTP body creates numerous allocations. Use streaming/chunking and avoid logging sensitive data.

**9. Confusing queue capacity with a total byte limit.** A 100-element queue can hold a few KB or multiple GiB depending on payloads. If payload sizes vary widely, add size quotas or a byte-budget semaphore rather than task count alone.

**10. Measuring `Runtime.freeMemory()` before/after one event and drawing conclusions.** The JVM's GC/JIT/allocator behave non-deterministically across single test steps; use load profiling, JFR, analyzed heap dumps, and metrics.

**11. Attaching an open file stream directly to an event.** An async listener may run after the stream closes, or multiple listeners may exhaust the stream concurrently. Send a durable key and open the stream in the consumer with clear ownership.

**12. Claiming “event accepted” means durably persisted.** `ApplicationEventPublisher` does not provide durable delivery. If tasks are rejected, the process crashes, or consumers fail, critical work needs an independent retry/outbox design.

## 13. Pre-production checklist

- [ ] Events carry minimal required data with clear identifiers/versions.
- [ ] P50/P95/P99 payload sizes and events/second rates are known.
- [ ] Object graphs retained by events/lambdas/proxies are evaluated, not just shallow size.
- [ ] Events use immutable shared objects or defensive copies with measured cost.
- [ ] Async executors have bounded queue capacity and an explicit overload policy.
- [ ] Rejections, queue wait times, active workers, and heap/GC are monitored.
- [ ] Raising heap or max threads is not relied upon as the sole fix.
- [ ] For large data, storage references, integrity, authorization, cleanup, and retries are in place.
- [ ] JPA entity graphs, HTTP request streams, and credentials are kept out of events.
- [ ] Log serialization does not bloat payloads or expose sensitive data.
- [ ] Queue saturation/rejection tests and real async behavior tests exist.
- [ ] Load tests simulate peak throughput and slow downstreams.
- [ ] For workflows requiring guaranteed delivery, an outbox/durable queue and idempotency exist.
- [ ] Listener completion is never assumed to mean the source DB transaction committed.

## 14. Self-check questions

**Question 1:** Why does returning from `publishEvent` not mean a large payload has been GC'd?

Because the executor queue, listener, future, or another reference may still retain the event and its object graph. Spring does not automatically clear all strong references when the publisher returns.

**Question 2:** Does a 200-element queue always consume a fixed amount of memory?

No. Memory retention depends on each task's payload, the number of distinct objects, and sharing. If each task holds a separate 4 MiB `byte[]`, the arrays alone can approach 800 MiB.

**Question 3:** Is `record BigEvent(byte[] data) {}` deeply immutable?

No. The record makes the field reference final, but array contents remain mutable. Defensive copying can create snapshots at extra allocation/CPU cost; for very large data, consider a storage reference.

**Question 4:** Do a large `maxPoolSize` and large `queueCapacity` make all workers run immediately?

Not necessarily. In the underlying queuing strategy, tasks usually enter the queue once core workers are busy; max workers only scale out when the queue is full. Test under load.

**Question 5:** Does a bounded queue mean “OOM is impossible”?

No. It only bounds pending tasks for that specific executor; data can still accumulate at callers, other executors, object graphs, serialization buffers, and related subsystems. Bytes/throughput must also be bounded.

**Question 6:** Why not push a PDF file directly through an event for an async listener to process?

It keeps binary data in the heap and queue longer; if the process crashes, in-memory payloads are lost. When appropriate, persist the file durably and publish a small event with storage key, version, and checksum, then stream from storage.

**Question 7:** When should after-commit and outbox be used?

After-commit ties execution to transaction outcome; a durable outbox/registry is needed when sending intent must not be lost between commit and async/downstream processing. Neither solves payload size on its own; keep event metadata small.

**Key takeaway:** optimizing payloads in Spring Application Events means controlling **object graph size × outstanding events × retention time**, alongside bounded queues and a clear overload policy. For large binary data, **passing durable identifiers/references and streaming** usually keeps heap far more controllable than holding entire data blobs inside event objects.

## References

- [Spring Framework 6.2 — Application Events and asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — PayloadApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Oracle JDK 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
