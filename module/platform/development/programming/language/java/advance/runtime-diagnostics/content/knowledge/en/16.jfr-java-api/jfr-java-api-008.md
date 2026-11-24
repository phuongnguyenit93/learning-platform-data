# 16.8. RecordingStream: Callback Registration, start vs. startAsync, and close

## 1. Problem Statement: Receiving JFR Events Directly in Java Code

`RecordingStream` belongs to the `jdk.jfr` module, package `jdk.jfr.consumer`. This API creates a recording in the **current JVM** and delivers recorded JFR events as `RecordedEvent` objects to application-registered callbacks. We can detect a GC cycle, inspect CPU load, or receive custom events while the program is running, rather than waiting to export an entire `.jfr` file for later analysis.

Practical example: a service needs to count how often an internal operation occurs for diagnostics. The service can define its own `Event`, enable that event type in `RecordingStream`, register `onEvent(...)`, and process metrics inside the callback. Long-lived usage requires controlling stream lifecycle, threads, callback speed, and collection overhead.

**After this lesson, you will:**

- Understand clearly how `RecordingStream` creates and receives events, and distinguish it from `Recording` and `EventStream.openFile(...)`.
- Properly register callbacks `onEvent`, `onError`, `onFlush`, and `onClose`; use `enable` and read `RecordedEvent` fields accurately.
- Decide when to use `start()` to process on the current thread vs. `startAsync()` to let the calling thread continue its work.
- Close the stream reliably with `close()` or `try-with-resources`; understand why `close` does not guarantee every event was processed.
- Write a runnable Java 17+ example covering **both `start` and `startAsync` modes**, verify callbacks, and guarantee resource cleanup.
- Avoid errors involving registration order, unflushed events, race conditions, blocking callbacks, and uncontrolled shutdowns.

This lesson focuses on **stream and callback lifecycles inside the JVM**, rather than custom event design, offline dump analysis, or remote JFR connections.

## 2. How It Works and Where Callbacks Execute

High-level data flow:

~~~text
Application code or HotSpot emits JFR event
            │
            ▼
    JFR recording in the same JVM
            │
            ▼
     JFR buffer / flushed into batches
            │
            ▼
     RecordingStream reads batch
            │
            ├─ onEvent("type name", Consumer<RecordedEvent>)
            ├─ onEvent(Consumer<RecordedEvent>)  [all events delivered by stream]
            ├─ onFlush(Runnable)                 [after batch flush]
            ├─ onError(Consumer<Throwable>)      [on error]
            └─ onClose(Runnable)                 [when stream closes]
~~~

The `EventStream` interface defines the callbacks and event-reading behavior. `RecordingStream` both owns a local recording and implements `EventStream`, so it can `enable`/`disable` event types and invoke `start` or `startAsync`. Events arrive in **batches after data is flushed**; there is no guarantee a callback runs instantaneously at the exact `event.commit()` line.

**Typical timeline:**

~~~text
Initializing thread  | create RecordingStream -> enable -> onEvent/onError/onClose
                     | startAsync() -> returns; this thread continues
Producer thread      | create Event -> commit()
JFR/stream thread    | reads batch after flush -> onEvent(RecordedEvent)
Coordinator thread   | deadline/service shutdown -> close() -> cleanup
~~~

With `start()`, **the thread calling `start()` is the thread executing callbacks**, and that call blocks until the stream ends. With `startAsync()`, callbacks run on **a dedicated thread**, and the method returns after starting the asynchronous processing mechanism. Callbacks for a single stream are dispatched sequentially on the stream-processing thread per the API docs, whereas producers can run across many threads; shared application data still needs proper synchronization or atomics.

Do not assume every `commit()`ted event is guaranteed to be received: delivery still depends on whether the event type is enabled, thresholds, recording/flushing, retention, start timing, and when the stream closes.

## 3. Distinguishing RecordingStream from Other JFR APIs

| API | Responsibility | Typical usage |
| --- | --- | --- |
| `jdk.jfr.Event` | Defines **custom events** by subclassing, adding fields, and calling `commit()` | Source of business events |
| `jdk.jfr.Recording` | Controls a recording, duration, settings, and file dumps | Capturing data for offline analysis |
| `RecordingStream` | Records and streams events **within the current JVM**, enabling events and delivering callbacks | Live reaction, local diagnostic counters |
| `EventStream.openFile(path)` | Reads events from an existing `.jfr` file | Offline reading; creates no new recording |
| `EventStream.openRepository(...)` | Tails data from a JFR repository | Reads repository chunks; requires appropriate permissions and repository |
| `RemoteRecordingStream` | Uses JFR via `jdk.management.jfr` for a remote JVM via management APIs | Remote monitoring scenarios; different configuration and permissions |

**Do not confuse** `RecordingStream.start()` with `Recording.start()`. Despite sharing a method name, `Recording.start()` transitions the recording state and returns; `RecordingStream.start()` begins **consuming events and invoking callbacks**, so it blocks the caller. If you want the caller to proceed immediately, use `RecordingStream.startAsync()`.

`RecordingStream` has existed since Java 14; examples here target **Java 17+**. Newer methods such as `RecordingStream.stop()` were added in Java 20, so the examples use `close()` to preserve Java 17 compatibility.

## 4. Registering Callbacks Before Starting

### 4.1. Enabling the right events and choosing filtered callbacks

Illustrative snippet (inside a method with an existing `RecordingStream stream`, not a standalone program):

~~~java
stream.enable("jdk.CPULoad").withPeriod(java.time.Duration.ofSeconds(1));
stream.onEvent("jdk.CPULoad", event -> {
    double machine = event.getDouble("machineTotal");
    System.out.println("Machine CPU ratio: " + machine);
});
~~~

Here `enable("jdk.CPULoad")` requests collecting this event type, `withPeriod(...)` sets the sampling interval for the periodic event, and `onEvent("jdk.CPULoad", ...)` receives only events matching the **JFR event type name**. `machineTotal` is a CPU ratio, not a percentage by default; to display `%`, multiply by 100 and check the field documentation for your JDK. Verify JFR event names and fields against the actual schema rather than guessing from Java class names.

There are two registration overloads:

~~~java
// Illustrative snippet, stream already created:
stream.onEvent("jdk.GarbageCollection", event -> handleGc(event));
stream.onEvent(event -> handleAnyEvent(event));
~~~

- `onEvent(String, Consumer<RecordedEvent>)` filters by type, usually more efficient than branching with `if/else` on every event inside a catch-all callback.
- `onEvent(Consumer<RecordedEvent>)` receives every event delivered by the stream, useful for initial exploration but potentially costly under high event rates.
- **Registering a callback does not automatically enable the event type**; you must understand the recording configuration. In practice, explicitly call `enable(EventClass.class)` or `enable("event.name")`.
- For custom events, `@Name("lesson.DemoEvent")` defines the JFR event type name, whereas the Java class name is merely a declaration detail. Read fields with typed APIs like `getInt("marker")` or `getString("message")` and verify field existence.
- `onMetadata(...)` (Java 16+) receives event type metadata and lets you register name-based callbacks dynamically as schemas appear; useful for evolving schemas. For most scenarios, registering known names upfront is clearest.

### 4.2. Remaining callbacks

| Callback | When invoked | Application notes |
| --- | --- | --- |
| `onEvent(String, Consumer)` | A matching named event is dispatched | Read fields quickly; avoid long blocking I/O |
| `onEvent(Consumer)` | Any event in the stream arrives | High-volume events increase handler load |
| `onFlush(Runnable)` | After an event batch has been flushed | Useful to push aggregated counters to metrics/queues; do not assume flush occurs every exact second |
| `onError(Consumer<Throwable>)` | An exception occurs while processing the stream/callback | If unregistered, stack trace prints to `stderr` by default; an error inside `onError` has unspecified behavior |
| `onClose(Runnable)` | Stream closes, whether manually or automatically | Helps with notification/cleanup; does not mean all events were processed |
| `remove(Object action)` | Unregisters a previously added callback | Pass the **exact `Consumer`/`Runnable` instance** originally registered; a new lambda will not match |

Example of unregistering a callback (illustrative method snippet; requires `stream` and imports):

~~~java
java.util.function.Consumer<jdk.jfr.consumer.RecordedEvent> consumer =
        event -> System.out.println(event.getEventType().getName());
stream.onEvent("jdk.GarbageCollection", consumer);
// When you need to update registrations:
boolean removed = stream.remove(consumer);
~~~

If an action was registered multiple times, `remove(action)` removes matching registrations of that action. Register essential callbacks—especially `onError` and `onClose`—**before starting** so you do not miss startup or early close notifications.

**Callbacks can fail the stream:** if a handler throws an exception, it enters the stream's error-reporting path. Never swallow every error silently inside `onError` and continue reporting healthy status. Log the cause and transition state so the system responds actively.

## 5. Decision Table: start(), startAsync(), close(), and stop()

| Method | Threading and blocking | Practical usage |
| --- | --- | --- |
| `start()` | Runs callbacks on the **calling thread** and **blocks** until the stream ends | A dedicated monitoring program; lifecycle ended by another thread, deadline, or signal |
| `startAsync()` | Dispatches callbacks on **a separate thread**, returning so the caller continues | Services/applications that have other work to do |
| `close()` | Releases resources; requests terminating the stream immediately or at next flush | Inside `finally`, `try-with-resources`, shutdown hooks, or lifecycle stop |
| `awaitTermination()` / `awaitTermination(Duration)` | Waits for termination/action completion within API limits | Coordinating async shutdown; the timeout overload returns `void`, not a boolean indicating completion |
| `stop()` (**Java 20+**) | Stops and waits for recorded events to be consumed | When draining is needed before analysis; avoid calling **inside a callback** due to deadlock risk |

**Two critical distinctions:**

1. `close()` **does not guarantee** all callbacks have finished running **before the method returns**. Never treat "called `close()`" as proof that all final events reached your database or metrics. If you need an explicit signal, design a `CountDownLatch` or dedicated completion mechanism; on Java 20+, consider `stop()` from a coordinator thread after accounting for latency/timeouts.
2. `startAsync()` **does not guarantee** an event `commit()`ted on the very next line is already received by a callback: startup and flushing are asynchronous. To verify callback behavior, emit events and **wait with a bounded timeout** on a handler signal instead of `Thread.sleep(10)` and guessing.

Common incorrect pattern:

~~~java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.onEvent(System.out::println);
    stream.startAsync();
} // Stream is closed almost immediately!
~~~

`try-with-resources` here closes the stream right after `startAsync()`, leaving virtually no time to receive events. Instead, tie the resource lifetime to the lifetime of the application/work being observed, or use a bounded scope with an explicit stop condition.

## 6. Runnable Java 17+ Example: Both Sync and Async

The following example intentionally uses a **small custom event** so results do not depend on whether the JDK happens to emit GC/CPU events. It uses `CountDownLatch` as a receipt signal, `AtomicReference` to pass errors from callbacks back to the checking thread, and `try-with-resources` for cleanup. On success, stdout is deterministic.

Save as **`RecordingStreamLifecycleDemo.java`**:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class RecordingStreamLifecycleDemo {
    @Name("lesson.DemoEvent")
    static class DemoEvent extends Event {
        int marker;
    }

    private static boolean emitUntilSeen(CountDownLatch seen, int marker)
            throws InterruptedException {
        for (int i = 0; i < 30; i++) {
            DemoEvent event = new DemoEvent();
            event.marker = marker;
            event.commit();
            if (seen.await(250, TimeUnit.MILLISECONDS)) {
                return true;
            }
        }
        return false;
    }

    private static void subscribe(RecordingStream stream,
                                  CountDownLatch seen, int marker,
                                  AtomicReference<Throwable> failure) {
        stream.enable(DemoEvent.class).withoutStackTrace();
        stream.onEvent("lesson.DemoEvent", event -> {
            if (event.getInt("marker") == marker) {
                seen.countDown();
            }
        });
        stream.onError(failure::set);
    }

    private static void asyncDemo() throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        CountDownLatch closed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        try (RecordingStream stream = new RecordingStream()) {
            stream.setMaxAge(Duration.ofSeconds(15));
            subscribe(stream, seen, 1, failure);
            stream.onClose(closed::countDown);
            stream.startAsync();
            if (!emitUntilSeen(seen, 1)) {
                throw new IllegalStateException("No async event received");
            }
        }
        if (!closed.await(3, TimeUnit.SECONDS) || failure.get() != null) {
            throw new IllegalStateException("Async stream did not close cleanly",
                                            failure.get());
        }
        System.out.println("asyncReceived=true");
        System.out.println("asyncClosed=true");
    }

    private static void syncDemo() throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        CountDownLatch closed = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicReference<Throwable> producerFailure = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            subscribe(stream, seen, 2, failure);
            stream.onClose(closed::countDown);

            Thread producer = new Thread(() -> {
                try {
                    if (!emitUntilSeen(seen, 2)) {
                        producerFailure.set(new IllegalStateException("No event"));
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    producerFailure.set(e);
                } finally {
                    stream.close(); // Wake the thread blocked in start().
                }
            }, "event-producer");
            producer.start();
            stream.start();       // Processes callbacks on this thread; blocks.
            producer.join();
        }

        if (seen.getCount() != 0 || !closed.await(3, TimeUnit.SECONDS)
                || failure.get() != null || producerFailure.get() != null) {
            throw new IllegalStateException("Sync stream did not finish cleanly");
        }
        System.out.println("syncReceived=true");
        System.out.println("syncStartReturned=true");
    }

    public static void main(String[] args) throws Exception {
        asyncDemo();
        syncDemo();
    }
}
~~~

Run in the directory containing the file, using **JDK 17+ with JFR support**:

~~~bash
javac RecordingStreamLifecycleDemo.java
java RecordingStreamLifecycleDemo
~~~

Stdout on a successful lab run (verified directly on JDK 24):

~~~text
asyncReceived=true
asyncClosed=true
syncReceived=true
syncStartReturned=true
~~~

### 6.1. Why doesn't the example just use a fixed sleep?

- `emitUntilSeen` emits an event and waits up to 250 ms, repeating up to 30 times to account for startup and delayed batch flushing. It **does not assume** the callback fires immediately upon `commit()`; it prints success only after observing the matching event.
- `onEvent("lesson.DemoEvent", ...)` reads `marker` and counts down only when the value matches, so the two tests cannot cross-confirm each other's events.
- `asyncDemo` calls `startAsync()`, allowing the caller to continue emitting events. On exiting `try-with-resources`, `close()` runs and the program awaits `onClose` to verify cleanup.
- `syncDemo` starts a separate producer thread, then calls `start()` on the main thread. The producer emits events until the callback observes one, then **calls `close()` from the separate thread**, letting `start()` return. This illustrates why `start()` keeps `main` blocked without an independent close trigger.
- `AtomicReference<Throwable>` surfaces callback/producer failures without relying on exceptions thrown on background threads.
- If the stream does not receive an event within the allotted time, the demo **throws an exception** so the learner sees the unmet condition rather than printing a false PASS. Heavily loaded hosts or slower JFR flushes may require a longer window.

Do not benchmark CPU/latency using this tight loop; it is a lifecycle demonstration. Actual emissions may exceed the number of counted callbacks, and the program does not attempt to drain every event before closing.

## 7. Step-by-Step: Applying the Lifecycle Correctly in Applications

**Sync usage — dedicated monitoring thread:**

~~~text
Create stream
    -> Configure events/retention
    -> Register onEvent, onError, onClose
    -> Provide an independent close mechanism (signal/shutdown/another thread)
    -> start() [blocks current thread]
    -> closed / terminated -> start() returns
    -> resources released
~~~

For example, a CLI tool dedicated to listening to JFR can call `start()` on the main thread and receive a stop signal via a shutdown hook. Without a deadline or close trigger, it remains blocked; that is intentional design, not an API hang.

**Async usage — background monitoring inside a service:**

~~~text
Application.start()
    -> new RecordingStream()
    -> enable + register callbacks
    -> startAsync()
    -> application serves requests
Application.stop()
    -> stop producing work if needed
    -> close stream once (idempotent per docs)
    -> wait for completion as needed, with bounds
    -> release application queues/workers
~~~

A real service needs a clear owner for the stream, such as an application `AutoCloseable` bean/resource. Never create a new stream per request and forget to close it: you will add unnecessary recording work, callback threads, buffers, and JFR resources.

### 7.1. Who should call close?

- **`try-with-resources`:** great for programs/tests with a clear lexical scope, ensuring cleanup even on exceptions.
- **Service shutdown hook:** when the application manages a stream across its lifetime, call `close()` in lifecycle stop/shutdown with error handling; ensure the hook actually runs during normal shutdown.
- **Coordinator thread:** used when `start()` is invoked on another thread to avoid blocking indefinitely.
- **Callback:** can call `close()` to stop immediately, though you should not call `stop()` directly inside a callback because waiting to drain can deadlock the stream thread against itself. It is simpler to signal a coordinator thread to perform shutdown.

For Java 17, **`close()` is the portable API within this lesson's scope**; on JDK 20+, `stop()` can wait for recorded events to be consumed before proceeding, though the wait must be designed carefully and never triggered from within a callback.

### 7.2. Waiting for async completion and reading errors properly

`EventStream.awaitTermination(Duration)` does not return a boolean telling you whether it timed out or finished. Therefore, for a business event requiring confirmation, use an independent signal such as `CountDownLatch.await(timeout, unit)` (which returns a boolean), `CompletableFuture`, or a synchronized result state. Calling `awaitTermination` can help coordinate shutdown, yet **never** treat it as verification that a specific event arrived.

If a waiting thread is interrupted, do not silently swallow `InterruptedException`. Restore the interrupt flag or propagate the exception while closing the stream in `finally`. Always use bounded timeouts so shutdown never hangs indefinitely due to a stalled source or handler.

## 8. Rules on Ordering, Synchronization, and Callback Performance

### 8.1. Event ordering is not a strict global total order across all time

JFR delivers events in **batches**. Within a delivered batch, events are sorted by end time when ordering is active. An event in a later batch can still carry an earlier timestamp than an event from an earlier batch depending on flush timing; never build business logic assuming "arrived later = happened later" without inspecting timestamps or IDs.

If ordering does not matter, `setOrdered(false)` can reduce sorting overhead. However, handlers must then tolerate arbitrary arrival order. For counters or histograms, order rarely matters; for timeline reconstruction, inspect event timestamps and handle out-of-order arrivals.

### 8.2. Do not retain RecordedEvent objects arbitrarily after the callback

Per `EventStream` documentation, `RecordedEvent` instances may be **reused** for subsequent events. Never push `RecordedEvent` directly onto a queue and read it long after the callback returns without controlling reuse. The safe pattern is **extracting needed fields immediately into an immutable DTO**:

~~~java
// Illustrative snippet inside a callback:
int marker = event.getInt("marker");
long at = event.getStartTime().toEpochMilli();
queue.offer(new EventSummary(marker, at)); // EventSummary/queue are application-defined types.
~~~

This is an illustrative snippet, **not standalone source**; you must define `EventSummary` and the queue. `setReuse(false)` alters event object reuse at the cost of extra allocations; copying into a small DTO and controlling data lifecycle is still preferable. If retention is unneeded, update counters or atomic state directly inside the callback.

### 8.3. Keep callbacks short and non-blocking

A slow callback causes the consumer to fall behind the event source. Common pitfalls:

- Making HTTP/database calls, logging excessively, or serializing huge payloads in every `onEvent`.
- Retaining large objects from events or callback closures in an application-wide registry.
- Using unbounded queues that grow memory when event rate exceeds downstream throughput.
- Calling `stop()` (Java 20+) directly inside a callback, risking deadlock because `stop()` waits to drain.
- Reading/writing shared state without thread safety across the callback thread, request threads, and shutdown thread.

Practical design: **callbacks only extract essential fields**, increment a `LongAdder`/counter, or enqueue a compact DTO into a bounded queue for a separate worker to handle I/O. Define clear backpressure policies when the queue is full: counted drops, sampling, or reducing event types/periods. Never block callbacks indefinitely waiting on downstream systems. Monitor event rate, callback latency, queue depth, dropped events, error counts, and stream state.

### 8.4. Multiple streams and event configurations

Multiple `RecordingStream` instances in the same JVM may share underlying JFR work while maintaining separate callbacks and retention. Never assume adding another stream costs zero, nor assume overhead scales strictly linearly. Measure realistically with your target event types and load. Event settings can alter JVM collection overhead; assign clear stream owners and avoid spawning streams per request.

A `RecordingStream` can call `dump(Path)` to write a `.jfr` file once started and before closing; the API recommends configuring `setMaxAge` or `setMaxSize` before starting to ensure data is retained. **Streaming callbacks do not automatically create a final dump file**: if offline analysis is needed, trigger `dump` explicitly per policy and manage access permissions, disk space, and cleanup.

## 9. Common Errors and Root-Cause Identification

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `onEvent` never runs | Forgot `start/startAsync`, event type disabled, wrong name, threshold filtered everything | Check `@Name`/metadata, `enable`, start timing, and actual event emission |
| Calling `start()` makes the program "hang" | `start()` is intentionally blocking; no close thread/condition | Use `startAsync()` or close from another thread |
| `startAsync()` exits method and receives no events | `try-with-resources` scope closes too early | Keep resource alive long enough and await a bounded callback signal |
| Callback not seen right after `commit()` | JFR flushes in batches, event unread or stream not ready | Wait with timeout, verify `onError`/flush, do not assume instant real-time |
| `close()` called but final few events missing | `close` can stop before all events finish processing | Use a completion protocol; if draining on JDK 20+, consider `stop()` outside callbacks |
| `startAsync()` after stream closed | Stream is already CLOSED or started | Do not restart the same object; create a new stream per lifecycle |
| App slows down despite light JFR settings | Callback does blocking I/O, logs every event, or uses unbounded queue | Minimize callback work, bound queues, cut event volume, measure overhead |
| `onError` set, yet no stack trace appears | `onError` handler overrides default `stderr` printing | Log and count errors explicitly, decide fail/restart rather than staying silent |
| Dashboard shows out-of-order data | JFR event batches do not guarantee global order | Use timestamps/sequences, tolerate late events, or re-sort |
| Stored `RecordedEvent` fields mutate unexpectedly | Object may be reused after callback returns | Copy fields into a DTO or use `setReuse(false)` if genuinely warranted |
| Shutdown waits forever | `close` never called, callback blocked, or infinite latch wait | Close from proper owner, use bounded timeouts, avoid sync I/O in callbacks |
| Callback runs multiple times per event | Lifecycle setup ran twice | Manage a single stream instance/owner; `remove` exact action when needed |

**Do not call a stream "healthy" just because `startAsync()` did not throw.** Healthy operation requires at minimum: the stream has not closed unexpectedly, no errors occurred, expected event types appear within the window, and downstream processing is not backed up. If target events are rare, health checks can rely on a custom heartbeat event or flush metrics rather than expecting every JVM to run GC every second.

## 10. Practice Exercises

**Exercise 1 — understanding blocking.** A `main` method has `stream.start(); System.out.println("READY");`. When does `"READY"` print? **Only after the stream ends/closes**. To let `main` continue immediately, use `startAsync()` and keep the resource alive long enough.

**Exercise 2 — callback never fires.** You registered `onEvent("lesson.Payment", handler)`, while code emits a class with `@Name("lesson.PaymentCreated")`. Why are no events seen? **Name mismatch**; you also need to enable the right event class and account for thresholds/flushing.

**Exercise 3 — closing too early.** A function creates a stream, calls `startAsync()`, and immediately exits the `try` block. How do you fix it? Move the resource into a service with a clear lifecycle, close it in the stop hook, and test with `CountDownLatch` rather than short sleeps.

**Exercise 4 — which thread is running?** With `start()`, which thread runs callbacks? **The thread calling `start()`**. With `startAsync()`? **A dedicated thread used by the stream to dispatch callbacks**. Accessing shared objects with request threads requires proper synchronization.

**Exercise 5 — ensuring all events before finalizing counts.** If you call `close()` and immediately read a counter, are all events guaranteed? **Not guaranteed**. On JDK 20+, consider `stop()` from a coordinator (not inside a callback), or a completion protocol with producers and a processed signal.

**Exercise 6 — unbounded queue growth.** Each callback pushes a DTO onto an unbounded queue; downstream consumes 100 items/s while JFR emits 10,000 items/s. Result? Queue grows at roughly **9,900 items/s** at steady state, risking OOM. Use a bounded queue, count dropped events, and adjust collection rates.

**Exercise 7 — empty `onError`.** Adding an empty `onError(t -> {})` suppresses the default stack trace. Is this good error handling? **No**. Error callbacks need telemetry and state handling to avoid silently losing failure signals.

**Exercise 8 — late-arriving event.** Event A with timestamp `10:00:00.200` reaches the callback after event B with timestamp `10:00:00.500`. Is the API broken? **Not necessarily**: batch-level ordering is not a strict global total order across batches. Reconstruct timelines using timestamps if truly required.

## 11. Quick Application Checklist

1. Initialize `RecordingStream` on the target JVM, choose settings, and enable only needed event types.
2. Register `onEvent`, `onError`, and `onClose` **before starting**; filter by name to avoid unnecessary work.
3. Choose `start()` if the caller owns running the stream loop; choose `startAsync()` if the caller has other work.
4. Define the owner and `close()` timing; never let the resource die right after `startAsync` or stay unclosed forever.
5. With async usage, use signals/timeouts to verify critical events and termination; never equate `close` with complete draining.
6. Read/copy required fields inside callbacks, keep processing fast, bound queues, and monitor errors/latency.
7. Account for event schemas, batching/ordering, `RecordedEvent` reuse, and possible missed tail events on shutdown.
8. Test on your actual Java/JDK target, measure overhead directly, and dump files only when offline analysis is required.

## References

- Oracle Java SE 21, [RecordingStream API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html) — constructors, `enable`, callbacks, `start`/`startAsync`, `close`, `awaitTermination`, `stop`, `dump`, `maxAge`/`maxSize`.
- Oracle Java SE 21, [EventStream API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html) — batch dispatch, event ordering/reuse, `onError`/`onClose`/`onFlush`, awaiting termination.
- Oracle Java SE 21, [RecordedEvent API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html) — reading event fields, timestamps, and durations.
- Oracle Java SE 21, [JFR Event API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html) and [EventSettings API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html) — custom events, `enable`, `threshold`, `stackTrace`, and `period`.
- Oracle Java SE 21, [Java Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.html) — working with JFR via Java code.
