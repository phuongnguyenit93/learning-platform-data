# 16.5 begin, end, commit, isEnabled, and shouldCommit on the Execution Path

## Objectives

In a Java application, defining custom **Java Flight Recorder (JFR)** events attaches timing, state, and a few business attributes to code segments you need to observe. However, misplacing **begin()**, **end()**, or checking **shouldCommit()** at the wrong point can yield misleading durations; computing expensive data before checking recording eligibility also adds overhead.

After this lesson, you will be able to:

1. Distinguish the roles of **Event.begin()**, **Event.end()**, **Event.commit()**, **Event.isEnabled()**, and **Event.shouldCommit()** in a custom event's lifecycle.
2. Design accurate **measurement boundaries** around real work, including with exceptions, interruptions, or early returns.
3. Distinguish checking **enabled** before execution from checking the **duration threshold** after measurement.
4. Avoid computing expensive fields, stacks, or debug payloads when an event will not be saved.
5. Configure event settings with **Recording.enable(...).withThreshold(...)**, then verify the JFR file using **jfr summary** and **jfr print**.
6. Understand the differences between **instant** events, **duration** events, and how multiple concurrent recordings behave.

This lesson uses **jdk.jfr.Event** and APIs available since Java 9, along with a standalone **Java 17+** program. Verification examples reference Java/JFR 21 without relying on Spring Boot or external monitors.

## 1. Putting All Five Methods in One Diagram

~~~text
A processing segment needs observation
             |
             v
     new CustomEvent()
             |
             v
      isEnabled() ?
       /        \
     false      true
       |          |
       |        begin()
       |          |
       |     actual processing
       |          |
       |        end()          (should be in finally)
       |          |
       |    shouldCommit() ?
       |       /       \
       |     false     true
       |       |         |
       |       |    populate expensive data
       |       |         |
       |       |      commit()
       |       |         |
       +-------+---------+
             |
            done
~~~

This diagram optimizes **observation**; the business execution path must run even when JFR is off. Never put the entire business logic inside the `isEnabled()` branch and skip it when false.

| Method | Primary meaning | When to use |
| --- | --- | --- |
| **begin()** | Marks the start timestamp for measuring the instance's duration | Immediately before the unit of work to measure |
| **end()** | Marks the end of the duration; must be called after `begin()` | After the measured work, typically in `finally` |
| **commit()** | Submits timestamp, duration, and fields to JFR per effective settings | Once required fields are ready |
| **isEnabled()** | True when at least one recording is running and the event type is enabled in a recording | Check early to skip expensive instrumentation when JFR is off |
| **shouldCommit()** | True when the event is enabled and duration meets the applicable threshold | After `end()`, before constructing expensive field data and calling `commit()` |

**Note:** JFR decides for itself whether an event qualifies to be recorded when `commit()` is called. **shouldCommit() is not a command to enable/disable the event** and does not replace `commit()`; it is a helpful guard to avoid preparation work that would otherwise be discarded.

## 2. Lifecycle of an Event: Object, Timing, and Recording

### 2.1. Creating an instance does not emit an event record

A class extending **jdk.jfr.Event** defines an event type. Calling **new RequestEvent()** merely creates a Java object for preparing an event; it **does not appear** in the JFR recording just from instantiation.

Minimal example (a code snippet inside a method with appropriate imports):

~~~java
RequestEvent event = new RequestEvent();
event.operation = "lookup";
event.commit();
~~~

When the type is enabled and threshold allows, **commit()** emits an **instant event** if `begin()` was not called. An instant event has identical start and end times in the `RecordedEvent` model; it is not suitable for inferring business processing duration.

**You do not need `begin()`/`end()` for every event.** If you only want to mark "cache refreshed", "feature toggled", or "job accepted", an instant event can be more accurate semantically.

### 2.2. begin() marks the start of measurement

~~~java
RequestEvent event = new RequestEvent();
event.begin();
// Execute the work being measured.
~~~

From this point, JFR can determine duration once an end point is marked. Calling `begin()` **after** the observed segment misses real time. Calling it too early includes waiting, data preparation, or setup outside the intended scope.

For example, if you want to measure only a database query, put `begin()` right before the query call; if you want to measure the entire request from receipt to response, `begin`/`end` must wrap all those steps. Both are valid, yet have **different meanings**.

### 2.3. end() locks in the end timestamp

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
}
~~~

**end() must follow begin().** Placing it in `finally` avoids forgetting it on early returns or thrown exceptions. Catching exceptions to record status is optional based on requirements, but never swallow exceptions just because you are recording JFR.

You can call **commit()** after `begin()` without calling `end()`; per the API, **commit() will close the duration automatically** in that case. However, if you still need to compute extra information after the work finishes, an **explicit end()** keeps the measurement boundary exact and lets you call `shouldCommit()` based on the completed duration.

### 2.4. commit() submits the event's data

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
    event.operation = "lookup";
    event.commit();
}
~~~

**commit()** records **the populated fields, timestamp, and duration** according to settings. When the event type is disabled or the duration is below threshold, no record is written even though the code called `commit()`. This is normal filtering behavior, not a bug.

Best practice: each operation gets its own `Event` instance and one intentional `commit()`. Do not share a single `Event` instance mutated concurrently across requests or threads; data will overlap and timing boundaries will become nonsensical. For async flows, use a correlation ID in an event field and clearly define the unit of work being measured.

## 3. isEnabled(): Fast Check Before Expensive Work

**Event.isEnabled()** returns true when **at least one recording is RUNNING** and **enabled=true** for that event type. False can result from no active recording, the event being disabled in configuration, or collection not having started yet.

Crucially: **isEnabled() does not check the duration threshold** and **does not guarantee the instance will appear in the file**. A 1 ms event can have `isEnabled()=true` yet not be recorded when `threshold=20 ms`.

Usage pattern:

~~~java
StepEvent event = new StepEvent();
boolean tracing = event.isEnabled();

if (tracing) {
    event.begin();
}

try {
    businessLogic(); // Always runs even when tracing=false.
} finally {
    if (tracing) {
        event.end();
        event.commit();
    }
}
~~~

*This is an illustrative fragment; `StepEvent` and `businessLogic()` must be defined in the application class.* This works well when only duration and cheap fields are recorded, since `commit()` automatically drops events below threshold. If you need to build costly messages, add `shouldCommit()` as shown next.

### Why should you never wrap business logic directly in the guard?

**Business-incorrect snippet:**

~~~java
StepEvent event = new StepEvent();
if (event.isEnabled()) {
    event.begin();
    businessLogic(); // When JFR is off, business logic does not run.
    event.commit();
}
~~~

Business logic must be **independent of whether JFR is on or off**. Enabling a recording to observe behavior must never change how requests are processed. Keep processing logic outside instrumentation, or use a guard solely to decide whether to begin measurement.

### Is isEnabled() invariant throughout the operation?

No. A recording can start/stop or settings can change while the operation is running. Checking at the start is only a **point-in-time optimization**. JFR can apply settings at write time; never promise "because `isEnabled()` was true, the file is guaranteed to contain the event". When investigating an incident, inspect the actual recording and its timeframe.

## 4. shouldCommit(): Checking Duration Threshold After end()

Per the Java 21 API, **shouldCommit()** returns true if the event is enabled and its duration satisfies the active threshold. The threshold is a **minimum duration**, so:

- **duration below threshold**: event is not recorded.
- **duration meets threshold**: event *may* be recorded, if the event type is still enabled and recording/settings allow.
- **threshold = 0**: no duration-based filtering.
- **isEnabled() = true** does not imply `shouldCommit() = true`.

Typical pattern:

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.description = buildExpensiveDescription();
        event.commit();
    }
}
~~~

*Illustrative fragment; `processRequest()` and `buildExpensiveDescription()` are application-defined methods.*

**Why call after end()?** At that point the final duration is fixed. Calling `shouldCommit()` at the start of the operation cannot make a valid threshold decision about **work that has not happened yet**. Start of operation suits `isEnabled()`; end of operation suits `shouldCommit()`.

**Why populate expensive fields after shouldCommit()?** If the duration is filtered out, you avoid building large strings, serializing objects, formatting stack traces, making extra DB queries, or reading telemetry-only data. For ultra-cheap fields like an already-available status code, setting them earlier is fine.

**Avoid side effects:** `buildExpensiveDescription()` should only prepare observational data; never put business side effects, database updates, or response-shaping decisions inside the `shouldCommit()` branch. Turning recording on or off would alter execution behavior.

### Thresholds across multiple concurrent recordings

If recordings A and B both enable the same event type with different thresholds, the API docs state that **shouldCommit() considers the smallest threshold among active recordings**.

Illustrative example:

| Recording | Event enabled | Threshold |
| --- | --- | --- |
| A | Yes | 10 ms |
| B | Yes | 100 ms |

A 50 ms operation can have **shouldCommit()=true** because it satisfies A's 10 ms threshold, even though it does not meet B's threshold. **Do not interpret true as meaning the event appeared in every recording file**. Each recording has its own settings and filtering results. Settings toggling, buffers/drops, and dump timing also affect what is later observed.

### shouldCommit() is not required for correct commit behavior

You can write:

~~~java
event.begin();
try {
    doWork();
} finally {
    event.commit(); // Automatically ends if end() was not called, and applies settings.
}
~~~

*This is an illustrative fragment.* It is valid when you do not need to inspect duration beforehand and have no expensive payload construction to skip. However, the duration span will include everything executed up to `commit()`; if `finally` performs cleanup, logging, or serialization before `commit()`, those are included in the measured interval.

## 5. Configuring Events: Enabled, Threshold, and Stack Trace

With **jdk.jfr.Recording**, you can configure each custom event:

~~~java
try (Recording recording = new Recording()) {
    recording.enable(StepEvent.class)
            .withThreshold(Duration.ofMillis(25))
            .withStackTrace();

    recording.start();
    // Run the workflow that emits StepEvents.
    recording.stop();
    recording.dump(Path.of("workflow.jfr"));
}
~~~

*Illustrative fragment requiring a `StepEvent` definition and imports for `Recording`, `Duration`, and `Path`.* Key points:

- **enable(StepEvent.class)**: enables this event type for the recording. Does not implicitly enable all event types.
- **withThreshold(25 ms)**: only instances meeting this duration pass this threshold. Use **withoutThreshold()** or duration 0 for instant events.
- **withStackTrace()**: requests capturing a stack trace when the event is committed and JFR data is available; the stack is captured at the `commit()` call site, not the entire call graph history of the request.
- **recording.start()**: starts collection. If business logic runs before start, `isEnabled()` cannot act on behalf of an unstarted recording.
- **recording.stop()** and **dump(Path)**: finish and export data. With a Recording using the default disk repository, dumping after stop is valid as long as the recording is not closed.

In addition to the Recording API, you can place annotations on the event class such as **@Enabled(false)**, **@Threshold("20 ms")**, and **@StackTrace(false)** to set defaults. Recording settings can override actual collection behavior; do not rely solely on annotations to predict results when multiple recordings exist.

**Differences across configuration types:**

| Type | What does it control? | When to verify? |
| --- | --- | --- |
| @Enabled / enabled setting | Whether the event type is recorded | Before/during recording |
| @Threshold / threshold setting | Durations shorter than the threshold are filtered out | After the event finishes |
| @StackTrace / stackTrace setting | Whether a stack snapshot is taken at commit | When inspecting events in the file |
| @Category, @Label, @Description | Metadata aiding comprehension of types/fields | When reading metadata; not automatic business filters |
| JFR file collection | Whether the file was dumped for the right time window | When analyzing the actual recording |

Different JDKs and Flight Recorder versions may support extended settings; this section focuses on the standard settings directly tied to the five methods.

## 6. Correct Pattern in Requests/Services: try, catch, finally

Suppose you need to measure an order-processing operation. When the application throws an exception, the event must still end; the error status is merely a **recorded field**, and must never alter exception propagation.

~~~java
StepEvent event = new StepEvent();
boolean trace = event.isEnabled();
if (trace) {
    event.begin();
}

String outcome = "ok";
try {
    return processOrder(orderId);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    if (trace) {
        event.end();
        if (event.shouldCommit()) {
            event.operation = "processOrder";
            event.outcome = outcome;
            event.commit();
        }
    }
}
~~~

*This fragment must be placed inside a method with a matching return type and definitions for `StepEvent`, `processOrder`, and `orderId`.*

Why each step exists:

1. **isEnabled()** checks early so JFR timing can be skipped when no relevant recording is active.
2. **begin()** sits right before the whole operation.
3. **try** always executes the business logic.
4. **catch** records the outcome and **rethrows** the error; never turn a business failure into success.
5. **finally** calls **end()** on both normal returns and exceptions.
6. **shouldCommit()** uses the finalized duration to decide whether to build fields and commit.
7. **commit()** runs only after fields are populated.

For **InterruptedException**, restore the interrupt flag when the application explicitly catches the exception to handle it, and continue honoring the cancellation contract; you can mark the outcome as **interrupted**. Never swallow an interrupt just to finish recording an event. The runnable program below includes this branch as well.

**Choose cleanup boundaries intentionally:** If cleanup is part of the latency you want to observe, call `end()` after cleanup. If you only want to measure business computation without telemetry overhead, call `end()` before JFR field preparation/logging. The measured scope must be clear in the event name and description.

## 7. Standalone Java 17+ Program: Instant Marker, Fast Step, Slow Step, and Failed Step

The following complete example demonstrates:

- **WorkflowMarker**: instant event calling only `commit()`.
- **StepTiming**: duration event measured with `begin()`/`end()`.
- **isEnabled()** ensuring work still runs when JFR is disabled.
- **shouldCommit()** filtering field creation using a 25 ms threshold.
- **finally** closing the measurement interval even when processing fails.
- **Recording** exporting **step-events.jfr** to read back via the CLI.

Create **JfrEventLifecycleDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrEventLifecycleDemo {

    @Name("demo.WorkflowMarker")
    @Label("Workflow Marker")
    @Category({"Demo", "Workflow"})
    public static class WorkflowMarker extends Event {
        @Label("Action")
        public String action;
    }

    @Name("demo.StepTiming")
    @Label("Step Timing")
    @Category({"Demo", "Workflow"})
    public static class StepTiming extends Event {
        @Label("Step Name")
        public String step;

        @Label("Outcome")
        public String outcome;
    }

    private static String work(String name, long sleepMillis,
                               boolean fail) throws InterruptedException {
        if (sleepMillis > 0) {
            Thread.sleep(sleepMillis);
        }
        if (fail) {
            throw new IllegalStateException("simulated failure");
        }
        return name.toUpperCase(Locale.ROOT);
    }

    private static String runStep(String name, long sleepMillis,
                                  boolean fail) throws InterruptedException {
        StepTiming event = new StepTiming();
        boolean trace = event.isEnabled();

        if (trace) {
            event.begin();
        }

        String outcome = "ok";
        try {
            return work(name, sleepMillis, fail);
        } catch (InterruptedException ex) {
            outcome = "interrupted";
            Thread.currentThread().interrupt();
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            if (trace) {
                event.end();

                if (event.shouldCommit()) {
                    event.step = name;
                    event.outcome = outcome;
                    event.commit();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("step-events.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkflowMarker.class).withoutThreshold();
            recording.enable(StepTiming.class)
                    .withThreshold(Duration.ofMillis(25))
                    .withStackTrace();

            recording.start();

            WorkflowMarker marker = new WorkflowMarker();
            if (marker.isEnabled()) {
                marker.action = "workflow-start";
                marker.commit();
            }

            System.out.println(runStep("fast", 0, false));
            System.out.println(runStep("slow", 80, false));

            try {
                runStep("failed", 80, true);
            } catch (IllegalStateException ex) {
                System.out.println("Handled: " + ex.getMessage());
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Created " + output);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --add-modules jdk.jfr JfrEventLifecycleDemo.java
java --add-modules jdk.jfr JfrEventLifecycleDemo
~~~

**Stdout printed by the program itself** when it completes normally in a writable directory:

~~~text
FAST
SLOW
Handled: simulated failure
Created step-events.jfr
~~~

There is no dependency on PID, thread count, timezone, or actual runtime duration in the stdout above. The exact set of events written to the file may vary depending on scheduling, JIT, or VM activity. What is guaranteed functionally is that the `fast` and `slow` branches return results, and the `failed` branch throws an exception handled by `main`.

### Reading JFR output

~~~bash
jfr summary step-events.jfr
jfr metadata --events demo.StepTiming,demo.WorkflowMarker step-events.jfr
jfr print --events demo.StepTiming,demo.WorkflowMarker step-events.jfr
~~~

Expected in a typical HotSpot environment:

- **demo.WorkflowMarker** has one instant event with `action=workflow-start`, because the threshold was removed and the recording was running.
- **demo.StepTiming** typically records **slow** and **failed** because both `sleep(80 ms)` calls exceed the 25 ms threshold.
- **fast** is usually filtered out due to its very short duration. However, **never assume Count=2 unconditionally**: the thread could be preempted by the scheduler or JIT/class-loading could push `fast` past 25 ms, or collection anomalies could occur. Always verify using actual output from `jfr summary`/`print`.
- **failed** still carries `outcome=error` when recorded, proving `finally` ran despite the exception.

Timestamps, threads, durations, and stack frames vary across runs. **jfr summary** shows `Count` per type; **jfr print** reveals individual field values. A recording lacking events of a certain type does not necessarily mean the operation never ran: it may have been filtered by settings/threshold or the recording may not have covered the right interval.

### What happens if the recording is turned off?

In the example, if JFR has no active recording, `isEnabled()` is false and business logic still runs. You can extract `runStep()` into an application that never creates a `Recording`; the method **does not couple its business outcome to JFR state**.

### What happens if you omit shouldCommit()?

Replacing the final branch with:

~~~java
event.end();
event.step = name;
event.outcome = outcome;
event.commit();
~~~

JFR still enforces the threshold inside `commit()`. For cheap fields like two existing string references, the overhead difference may be tiny. For expensive payloads, omitting `shouldCommit()` wastes work preparing discarded events. The order **end → shouldCommit → build fields → commit** protects against overhead in the common case.

## 8. Choosing a Pattern by Goal

| Goal | Recommended pattern | Conditions to watch |
| --- | --- | --- |
| Point-in-time milestone | Populate fields → `commit()` | No `begin`/`end` needed; check `isEnabled()` if payload is expensive |
| Measure duration of a synchronous block | `begin` → `try` work → `finally` `end` → `commit` | Define start/end boundaries clearly |
| Measure duration and filter short steps | `isEnabled` → `begin` → work → `end` → `shouldCommit` → fields → `commit` | Do not call `shouldCommit()` before final duration is known |
| Track exceptions | `begin` → `try`/`catch` record outcome → `finally` `end`/`commit` | Rethrow errors; do not drop commits on early return/throw |
| Async processing span | One event per logical operation, measuring from start until callback completion if that is the target scope | Use correlation ID and clear ownership; never mutate the same instance concurrently |
| Recording enabled dynamically | `isEnabled` guard on hot path | Guard is a point-in-time decision and can change mid-recording |
| Expensive telemetry fields | `shouldCommit` after `end`, then compute fields | Avoid business side effects inside telemetry branch |

**Do not confuse duration with CPU time.** An event with a 500 ms duration caused by waiting on a lock, socket, or `Thread.sleep` still measures only **elapsed time**. If you need CPU time, allocations, or lock contention, also collect the appropriate standard events (`ExecutionSample`, `ThreadPark`, `JavaMonitorEnter`, File/Socket I/O) and correlate timestamps.

## 9. Understanding Overhead and Avoiding Excessive Data

JFR is designed for efficient observation, yet **custom events still carry cost**. Event frequency, stack capture, field count, payload construction, and recording retention all affect CPU, memory, and file size.

Good practices:

1. Emit events only at **meaningful points**: completed requests, batch runs, slow queries, notable retries. Avoid emitting inside tight loops unnecessarily.
2. Use **thresholds** to focus on slow operations, understanding that filtered samples cannot be recovered from the file later.
3. Place **isEnabled()** before instrumentation-only logic; place **shouldCommit()** after duration measurement to avoid unneeded serialization, string formatting, or heavy snapshots.
4. **Never put full HTTP bodies, credentials, tokens, sensitive SQL parameters, or large objects into events**. Use status, counts, operation type, non-sensitive correlation IDs, and compact fields.
5. Directly supported JFR `Event` fields are **primitives, `String`, `Thread`, and `Class`**. Reference fields such as `Map`, `List`, `Throwable`, arrays, or enums do not become arbitrary payloads in the recording by default; JFR may ignore them when constructing the event type. Convert information into small fields of supported types.
6. Avoid manually capturing **stack traces** in Java code just to populate a `String` when JFR can capture commit-time stacks via appropriate settings.
7. Never treat events as a mandatory transaction audit mechanism or a guaranteed-delivery message queue; recordings have retention policies and can be disabled, filtered, overrun, or dumped after an incident has passed.
8. Bound `maxAge`/`maxSize` and apply file access policies for long-lived recordings; JFR files can contain class, method, thread, path, and sensitive business details.

### When to use isEnabled() without shouldCommit()?

For instant events or `threshold=0`, `isEnabled()` can be sufficient as a guard. If fields are always trivial, calling `commit()` directly is also valid. However, in paths with `threshold > 0` and nontrivial payload formatting, use both: **isEnabled early, shouldCommit late**.

### When should you avoid starting an event too early?

If `begin()` runs before a request is enqueued, duration measures **queue wait + execution**. If the goal is **execution time**, `begin()` must be inside the worker when processing actually begins. If you want end-to-end latency, including queue wait is intentional. Name and describe the event so readers do not confuse the two timings.

## 10. Diagnosing When Custom Events "Disappear"

When `commit()` was called yet the expected type/instance is missing from the file, check in order:

1. **Right JVM/file/time window?** The recording must have been running when the operation executed, and the file must be dumped from that recording.
2. **Was the event type enabled in at least one active recording?** Check configuration and `isEnabled()` at runtime; the event name may differ from the class name if `@Name` is used.
3. **Did the threshold filter out the event?** A 2 ms operation not appearing under a 25 ms threshold is expected. Do not remove thresholds in production just to see data without assessing overhead.
4. **Did `commit()` actually run on the executed path?** Early returns or exceptions can skip it if not in `finally`.
5. **Did `begin`/`end` wrap the work?** An instant commit or ending too early yields near-zero duration that gets dropped by thresholds.
6. **Was `shouldCommit()` called after `end()`?** Calling it before work finishes can yield wrong filtering decisions or mislead your understanding.
7. **Are multiple recordings active with different thresholds?** `shouldCommit()` evaluates the lowest threshold among active recordings; that does not mean every file gets the instance.
8. **Was the JFR file stopped/dumped completely and queried with the right event type?** Check with **jfr summary**, **jfr metadata**, and **jfr print --events**.
9. **Were events dropped/rotated due to limits, or were there JDK differences?** Never use the absence of an event as sole proof of application behavior.

### Three common mistake patterns

**Mistake A — wrong measurement scope**

~~~java
doBusinessWork();
event.begin();
event.end();
event.commit();
~~~

Duration is near zero and does not reflect `doBusinessWork()`. Place `begin` before the work to measure and `end` after it.

**Mistake B — losing events on error paths**

~~~java
event.begin();
doBusinessWork(); // If this throws, the next two statements do not run.
event.end();
event.commit();
~~~

Use `finally` to close the event; `catch` if you need to record an outcome. Still preserve the exception.

**Mistake C — computing expensive payloads even when the event fails threshold**

~~~java
event.end();
event.details = expensiveSerialize();
if (event.shouldCommit()) {
    event.commit();
}
~~~

Place `shouldCommit()` **before `expensiveSerialize()`**. However, if `expensiveSerialize()` is business work that must run regardless of JFR, do not move it inside the conditional branch; separate business data from telemetry.

## 11. Before–After Analysis Exercises

### Exercise 1. Why call end() before buildDetails()?

A request runs in 12 ms, `buildDetails()` takes 80 ms, and the threshold is 50 ms.

- If you call **commit() after buildDetails()** without `end()`, the duration can include the 80 ms of telemetry work and make the event look like a slow request.
- If you call **end() right after business work**, the duration reflects 12 ms; **shouldCommit()** filters out the event against the 50 ms threshold and skips `buildDetails()`.

That is why measurement boundaries and check ordering must match the analytical goal.

### Exercise 2. Two recordings, one event

Recording A enables the event with `threshold=20 ms`; B enables the same event with `threshold=200 ms`. The operation takes 75 ms.

**Conclusion:** `isEnabled()` can be true; `shouldCommit()` can be true because the minimum threshold is 20 ms. The event meets A's threshold, not B's. Do not expect both files to contain a record for this operation.

### Exercise 3. Event type enabled, but method never ran

The application invokes the operation only on incoming requests; the recording is running, yet no requests arrive during the capture window. Summary shows no events. Is this a JFR bug?

**Conclusion:** Not a bug. No instances appear because the instrumented code path did not execute; cross-check traffic, invocations, and the recording interval.

### Exercise 4. Code with return inside try

~~~java
event.begin();
try {
    if (cacheHit()) {
        return cached();
    }
    return compute();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

**Conclusion:** `finally` still executes on normal returns; the event ends and is committed if settings/threshold allow. To distinguish cache hit vs. miss, populate a valid field before `commit()`.

### Exercise 5. 500 ms duration in JFR—can we conclude high CPU?

**Conclusion:** Not enough evidence. 500 ms is elapsed duration between `begin`/`end`. It could be I/O wait, lock contention, sleep, scheduling, or CPU. Correlate with CPU samples, lock/park events, and I/O events to identify the cause.

## 12. Code Review Checklist

- **Event class**: Does it have an easily searchable name and category? Do fields use only supported types, stay concise, and avoid leaking sensitive data?
- **Business logic**: Does it always run even when JFR is disabled? Are there zero business side effects gated behind `shouldCommit`?
- **begin/end**: Do they wrap the exact segment to measure? Is `end()` guaranteed via `try`/`finally` on return and throw?
- **commit**: Is it called with fields populated? If duration is unneeded, is an instant commit more appropriate?
- **isEnabled** placed early for costly instrumentation? **shouldCommit** placed after `end` before expensive payload construction?
- **Settings**: Are threshold, enabled, and stackTrace defined clearly? Were multiple active recordings considered?
- **Java exceptions/interruption**: Are contracts preserved and outcomes recorded without swallowing errors?
- **Practical QA**: Did you run `jfr summary`/`print` to confirm instances, fields, durations, and filtering, while noting the recording window?

## References

- [Oracle JDK 21 — `jdk.jfr.Event` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`, `end`, `commit`, `isEnabled`, `shouldCommit`, and supported field types.
- [Oracle JDK 21 — `jdk.jfr.EventSettings` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `enabled`, `threshold`, `stackTrace`, and settings.
- [Oracle JDK 21 — `jdk.jfr.Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump`, and recording lifecycle.
- [Oracle JDK 21 — `jdk.jfr.Threshold` annotation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Threshold.html): default threshold per event type.
- [Oracle JDK 21 — `jdk.jfr.consumer.RecordedEvent` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `duration`, `startTime`, `endTime`, `thread`, and stack when reading back.
- [Oracle JDK 21 — JFR package and predefined settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): `enabled`, `threshold`, `stackTrace` semantics.
- [Oracle JDK 21 — `jfr` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, and `print` on `.jfr` files.
