# 16.3. Creating Custom Events by Extending Event

## Learning Objectives

After this lesson, you will be able to:

- Understand what a **custom JFR event** is and when to create dedicated events for business operations or application processing steps.
- Create a Java class extending `jdk.jfr.Event`; describe its type and fields using `@Name`, `@Label`, `@Description`, `@Category`, `@Threshold`, and `@StackTrace`.
- Record instant or duration events via `commit()` or `begin()`/`end()`/`commit()`; use `isEnabled()` and `shouldCommit()` to minimize overhead.
- Enable the event in a `Recording`, save a `.jfr` file, and read it back via `RecordingFile`, the `jfr` CLI, or JDK Mission Control.
- Recognize limitations around field types, thresholds, instrumentation overhead, sensitive data, and schema compatibility.

**Version:** The `jdk.jfr.Event` API has been available since Java 9; all examples are written to compile with **Java 17+**. The main example was compiled with `javac --release 17` and verified on OpenJDK 24.

## 1. What Is a Custom Event? Why Not Rely Only on Built-in Events?

**Java Flight Recorder (JFR)** captures events with timestamps, durations, attribute data, threads, and (if enabled) stack traces. The JDK already provides events such as GC activity, allocations, threads, locks, and I/O. However, infrastructure events do not inherently know which business step is running:

- "How long did the order validation step take?"
- "Did the payment provider call succeed?"
- "Which stage was a data import job in when latency spiked?"
- "Which processing thread's timeout or error correlated with the I/O spike?"

**Custom events** allow an application to emit domain-specific events with selected attributes at the right moments. For example, `demo.PaymentAttempt` carries `requestId`, `amountCents`, and `successful`, while JFR automatically records the timestamp, duration, and thread.

Custom JFR events **do not replace** structured logging, distributed tracing, or business metrics:

| Signal | Primary question | Limitations |
|---|---|---|
| Logs | What happened at a given moment, and what error was printed? | Can grow verbose; depends on log level and correlation |
| Metrics | How are request volume, error rate, and average/percentile latency changing? | Usually aggregated; little detail per individual event |
| Distributed traces | Which services/spans did a transaction traverse? | Requires cross-service propagation/instrumentation |
| Custom JFR events | When did a specific step inside the JVM happen, how long did it take, with what payload, stack, and thread? | Only contains events that were enabled, emitted, and above threshold; typically local to the JVM |

When correlation is needed, store a safely chosen correlation ID in the JFR payload to cross-reference logs/traces. Avoid recording tokens, passwords, customer data, sensitive request contents, or large payloads.

## 2. API Model: An Event Class Becomes an Event Type

The most static and explicit approach is declaring a class that extends `jdk.jfr.Event`:

```java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("demo.WorkStep")
@Label("Work step")
class WorkStep extends Event {
    @Label("Step")
    String step;
}
```

This is a **type definition snippet**, not a standalone program with `main`. Once the event type is enabled in a recording, the application can instantiate it and call `commit()`. Each `commit()` on an eligible instance writes an event into JFR; defining the type does not emit events merely because the class is loaded.

### 2.1. Common annotations

| Annotation | Placed on | Role |
|---|---|---|
| `@Name("demo.WorkStep")` | Event class | Sets a stable machine-readable name for filtering and analysis; prefer clear hierarchical names and avoid collisions |
| `@Label("Work step")` | Class or field | Human-readable label for display tools |
| `@Description("...")` | Class or field | Explains the meaning of the event/field |
| `@Category({"Application", "Orders"})` | Event class | Groups events in a category hierarchy for UI tools |
| `@Threshold("10 ms")` | Event class | Suggests a default duration threshold; shorter events are filtered out |
| `@StackTrace(true)` | Event class | Default configuration for whether to capture a stack trace at commit time |
| `@Enabled(false)` | Event class | Disables the type by default; recordings can still re-enable it |
| `@Timespan(Timespan.MILLISECONDS)` | Numeric field representing another duration | Declares the unit so tools display it properly |
| `@DataAmount(DataAmount.BYTES)` | Numeric field representing data size | Presents the value in bytes rather than a raw number |

Annotations such as `@Label` and `@Category` help tools present data; the name in `@Name` is the identifier used by filters and consumer code. Choose stable names when dashboards or analytics depend on them. If `@Name` is omitted, the default type name is derived from the class name, but renaming packages/classes can break downstream consumers.

**Annotations supply defaults; recording configuration decides what is actually captured.** For example, `@Threshold("10 ms")` is a default; `recording.enable(...).withThreshold(...)` or a `.jfc` file can apply a different threshold in a specific recording.

### 2.2. Field types supported by JFR

Per the `jdk.jfr.Event` contract on Java 17/21:

- Primitives: `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`.
- References: `String`, `Thread`, and `Class`.
- **Do not** use `List`, `Map`, arrays, enums, or arbitrary domain objects as fields expecting JFR to serialize them automatically; unsupported fields may be **silently ignored**.
- `static` fields are excluded from the payload. `transient` fields are also excluded from event data, even if their type is supported.

For instance, if you have an enum `OrderStatus status`, convert a **bounded, safe value** into `String statusName` instead of declaring the enum directly. To record file size, use `long bytes` with `@DataAmount(DataAmount.BYTES)`. Do not stuff huge JSON strings into a single `String` just to bypass type restrictions; that increases overhead and makes data harder to analyze.

For an `Event` subclass, populate fields via direct Java assignment (`event.step = "validate";`). `Event.set(int, Object)` is meant for events generated **dynamically** with `EventFactory`, not normal `extends Event` classes.

## 3. Lifecycle of a Custom Event

### 3.1. Instant event: a single point in time

```java
WorkStep event = new WorkStep();
event.step = "completed";
event.commit();
```

This is a **snippet using the `WorkStep` type just declared**, not a standalone program. If the type is enabled and satisfies current settings, `commit()` records the field values and timestamp; because `begin()` is not called, the duration is essentially zero-span. Such an event can be filtered out if a **positive duration threshold** is applied.

Suitable for state milestones such as "config loaded" or "retry scheduled", where elapsed time **between** milestones is not the content of the event itself.

### 3.2. Duration event: a processing interval

```java
WorkStep event = new WorkStep();
event.step = "validate";
event.begin();
try {
    // Work to measure goes here.
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
```

This is an **illustrative structural snippet**: replace the comment with actual work. `begin()` marks the start of the interval; `end()` marks the end; `commit()` submits the event with timestamp, duration, and fields. If `begin()` was called without `end()`, `commit()` may implicitly close the interval; however, using `finally` and explicit `end()` preserves accurate timing even when execution fails.

**Duration is elapsed time**, which can include waiting on I/O, locks, the scheduler, GC, or sleep. It is **not** CPU time. Never look at a custom event's duration and conclude that the method actually burned that much CPU.

### 3.3. Checking recording conditions

- `isEnabled()`: whether the type is enabled by at least one active recording. Useful for skipping expensive payload construction.
- `shouldCommit()`: whether the event currently qualifies to be written based on enabled settings and **duration threshold**. Check **after `end()`** for duration events.
- `commit()`: completes writing the event when recording conditions allow; calling it **does not guarantee** the file will contain the event, since the type may be disabled/filtered by threshold or no recording may be active.

When a payload is expensive (such as building a detailed summary string), a useful pattern is computing that part only **after `shouldCommit()`**. There is no need to micro-optimize rare events; however, events emitted hundreds of thousands of times per second warrant overhead testing.

## 4. Complete Java 17+ Example: Creating Custom Events and Reading the Recording

This example defines a simulated payment event with metadata, three supported fields, and explicitly measured duration. The program generates **two events**, writes them to `payment-attempts.jfr`, and uses the JFR consumer API to read back the exact two events created.

### 4.1. Source code

Create the file **`CustomJfrEventDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class CustomJfrEventDemo {
    @Name("demo.PaymentAttempt")
    @Label("Payment attempt")
    @Description("Outcome and elapsed time of a payment attempt")
    @Category({"Application", "Payments"})
    @Threshold("10 ms")
    @StackTrace(true)
    public static class PaymentAttempt extends Event {
        @Label("Request ID")
        String requestId;

        @Label("Amount, cents")
        long amountCents;

        @Label("Successful")
        boolean successful;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("payment-attempts.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(PaymentAttempt.class)
                    .withThreshold(Duration.ofMillis(10))
                    .withStackTrace();
            recording.start();

            for (int i = 1; i <= 2; i++) {
                PaymentAttempt event = new PaymentAttempt();
                event.requestId = "req-" + i;
                event.amountCents = 100L * i;
                event.begin();
                try {
                    Thread.sleep(30);
                    event.successful = (i == 1);
                } finally {
                    event.end();
                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }
            }

            recording.stop();
            recording.dump(file);
        }

        List<RecordedEvent> matching = RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName().equals("demo.PaymentAttempt"))
                .toList();

        System.out.println("Custom events: " + matching.size());
        for (RecordedEvent event : matching) {
            System.out.println(event.getString("requestId")
                    + ", cents=" + event.getLong("amountCents")
                    + ", success=" + event.getBoolean("successful"));
        }
        System.out.println("Recording: " + file.getFileName());
    }
}
```

### 4.2. Compile and run

In the directory containing the file, using **JDK 17 or later**:

```bash
javac CustomJfrEventDemo.java
java CustomJfrEventDemo
```

The program produces the following output (**verified on OpenJDK 24, compiled with `--release 17`**):

```text
Custom events: 2
req-1, cents=100, success=true
req-2, cents=200, success=false
Recording: payment-attempts.jfr
```

Because the program uses `Thread.sleep(30)` and the event threshold is 10 ms, both events were retained in the verified run. `Thread.sleep` only guarantees sleeping **at least** the requested duration under normal conditions; actual duration varies with OS and load. The program's output **does not print** those variable durations.

### 4.3. Inspecting the file with the JDK CLI

Right after running:

```bash
jfr summary payment-attempts.jfr
jfr print --events demo.PaymentAttempt payment-attempts.jfr
```

In `jfr print`, you will see output like:

```text
demo.PaymentAttempt {
  startTime = ...          
  duration = ... ms
  requestId = "req-1"
  amountCents = 100
  successful = true
  eventThread = "main" (...)
  stackTrace = [...]
}
```

This is only an **illustrative format**, not verbatim stdout. `startTime`, `duration`, `javaThreadId`, and stack line numbers vary by environment. The second event contains `req-2`, `amountCents = 200`, and `successful = false`. The CLI tool may display additional metadata/runtime events depending on the JDK and configuration.

You can also open `payment-attempts.jfr` in **JDK Mission Control (JMC)**, go to the Event Browser (UI label depends on release), and find `demo.PaymentAttempt` to inspect each field, duration, thread, and stack trace. Opening the file offline **does not require** the JVM that produced it to still be running.

### 4.4. Explaining each mechanism

1. `PaymentAttempt extends Event` defines **an event type** with the stable name `demo.PaymentAttempt` and attributes of types `String`, `long`, and `boolean`.
2. `@Category`/`@Label`/`@Description` provide presentation information for tools. `@Threshold` and `@StackTrace` establish default settings.
3. `recording.enable(PaymentAttempt.class).withThreshold(Duration.ofMillis(10)).withStackTrace()` ensures this type is collected in the **example's recording** with the chosen threshold and stack trace. It can override annotation defaults.
4. `begin()` and `end()` measure the task's elapsed time; `successful` is assigned in `try`, while `finally` ensures the interval closes and event emission is attempted even if the task terminates abnormally.
5. `shouldCommit()` avoids calling `commit()` when the event does not satisfy current settings.
6. `stop()` then `dump(file)` writes the recording to disk. `try` ensures resource cleanup.
7. `RecordingFile.readAllEvents(file)` returns **all events** in the file; filter by `getEventType().getName()` to count **only the custom event**. In a real recording, many other JDK events may also be present.
8. `RecordedEvent.getString/getLong/getBoolean` read fields with the appropriate types. `RecordedEvent` also allows reading `getStartTime()`, `getDuration()`, `getThread()`, and `getStackTrace()` when available.

**Limitation of this example:** `RecordingFile.readAllEvents` loads all events into memory, which suits small files. For large recordings, use `RecordingFile` to read events sequentially or a streaming analyzer to avoid unnecessary memory consumption.

## 5. Event Configuration: Annotations and Recording Settings

### 5.1. Duration threshold

`@Threshold("10 ms")` on the class means durations shorter than that threshold are generally not recorded by default. A recording can also set:

```java
recording.enable(PaymentAttempt.class)
         .withThreshold(Duration.ofMillis(50))
         .withStackTrace();
```

This is a **configuration adjustment snippet** used on an already-created `Recording`, not a standalone program. Now the recording's threshold is **50 ms**, overriding the 10 ms annotation default. With a workload where each attempt takes around 30 ms, `shouldCommit()` may return `false` and no event will appear in the file.

**Caution when testing:** if multiple concurrent recordings enable the same type with different thresholds, `shouldCommit()` behavior depends on the active configurations; it is not as simple as checking a single file in isolation. Align recording windows/configurations and log settings so measurements are reproducible.

For **instant** events (without `begin/end`), a positive duration threshold can prevent the event from appearing. For milestone events, use a `0` threshold or appropriate setting.

### 5.2. Stack traces and recording size

`withStackTrace()` captures the stack at the `commit()` call site when available, identifying where the event was emitted. It is not a full execution trace of every method called between `begin` and `end`. Stack traces, long `String` fields, and high event frequency all increase memory/CPU cost of the recording.

For very frequent events, consider:

- Emitting only at diagnostically valuable points (slow operations, timeouts, retries, key state transitions).
- Choosing thresholds aligned with SLOs and analysis goals.
- Recording only small, stable, sanitized fields.
- Enabling/disabling stack traces selectively, benchmarking overhead and disk size under realistic load.
- Disabling events via configuration in environments that do not need continuous observation.

### 5.3. Do not confuse enabled with recorded

There are three distinct conditions: **the event type is enabled**, **an event instance was actually committed**, and **the recording was saved/covers that timeframe**. `isEnabled() == true` does not immediately guarantee events appear in the file; instances may not have been committed, durations may not have exceeded the threshold, or the recording may not have been dumped/covered the target window.

Conversely, when `jfr print` shows no custom type, before suspecting a code bug, check: type name, enabled setting, threshold, `commit` invocation, recording start/stop, output file path, and time range.

## 6. Integrating Custom Events into Real Application Code

### 6.1. Placing events around meaningful boundaries

An event should reflect **a clear unit of work**, for example:

```text
paymentAttempt.begin()
    call provider
    decode response
    decide retry or finish
paymentAttempt.end()
paymentAttempt.commit()
```

This is a flow diagram, **not runnable Java code**. Decide the measurement scope upfront: does the event measure only the network round trip, or the whole attempt including validation, retries, and response handling? Those two scopes produce different durations. Document the scope clearly in `@Description` or docs.

Ensure `end()` runs in `finally`; if a request fails or throws, the event still reflects the elapsed time and failure state. If logs/traces already carry a correlation ID, you can safely include that same ID as a `String` field to link them with JFR.

### 6.2. When payload computation is expensive

One pattern is creating the event, timing the operation, and only **after `shouldCommit()` computing expensive fields** such as summarizing a large object. Diagram:

```text
create event -> begin -> process -> end
                                  |
                                  v
                            shouldCommit?
                              /        \
                           false       true
                            |            |
                          skip      build safe payload -> commit
```

If you want to avoid constructing events unnecessarily, check `isEnabled()` before expensive data preparation or stack inspection. Skipping instrumentation must **never alter business behavior**: core application logic must always run even when JFR is disabled.

Do not use JFR events as a guaranteed delivery mechanism for mandatory auditing or billing: recordings can be disabled, filtered by threshold, bounded by circular buffers, or fail to write to disk. Operations requiring guaranteed delivery must use dedicated persistence/audit systems.

### 6.3. Naming and schema for long-term maintenance

Once others build queries or dashboards on `demo.PaymentAttempt` and its field names, renaming types or fields can break analytics. Prefer:

- Hierarchical, stable event names distinguishing domain and work type.
- Field names with explicit units: `amountCents` is better than `amount`; for `latencyMs`, attach `@Timespan(Timespan.MILLISECONDS)`.
- Category/Label for presentation; never abuse them as identifiers in place of `@Name`.
- Adding only useful fields, avoiding high-cardinality or overly variable payloads.
- Clear policies on what data is allowed in events, recording retention, and who can download files.

JFR events can be consumed via **JDK Mission Control**, `jfr print`, `RecordingFile`, or internal analysis apps. Do not assume consumers automatically understand new fields or expect every consumer to handle all schema versions.

## 7. Common Misconceptions and Corrections

| Misconception | Accurate understanding |
|---|---|
| "Just subclassing `Event` makes JFR emit an event whenever a method runs" | You must **instantiate, assign fields, and call `commit()`**; the type must be enabled by a recording |
| "`begin()` already records a complete event" | `begin()` only marks the start of the duration; `commit()` emits the event |
| "`end()` automatically writes the event" | `end()` only marks the end time; you still need `commit()` |
| "`isEnabled()` true means the event is guaranteed to be in the file" | The event must also be committed, pass the threshold, and be in a saved recording |
| "Arrays/enums/POJOs are valid JFR fields because Java compiles them" | Unsupported field types can be **silently ignored** |
| "`@Label` sets the API name for `jfr print` filtering" | `@Name`/event type name is the identifier; Label is for display |
| "Duration event measures CPU time" | It measures **elapsed time**, including wait time |
| "Missing event means the operation did not happen" | The type could be disabled, not committed, filtered by threshold, or the file/filter covered a different window/name |
| "Stuffing every object/stack into events is always better" | Large payloads/high frequency add overhead and risk leaking sensitive data |
| "Custom JFR events can replace a guaranteed audit log" | JFR is for observability/diagnostics; it lacks delivery guarantees of business/audit systems |

### When reading results, ask yourself

1. Does the event measure the **exact code segment** you intended?
2. Was a recording running and enabling the exact **event type name**?
3. Are the duration threshold and stack trace settings appropriate for the issue under investigation?
4. Do event fields use supported types, and were values assigned before `commit()`?
5. Does the file opened in JMC/CLI cover the right **time window, JVM, and workload**?
6. Does duration reflect elapsed time or CPU? Should logs/metrics/traces be cross-checked for root cause?

## 8. Extension Exercises

**Exercise A — Instant and duration.** Create two custom event types: a "request accepted" milestone event and a "request processed" timed event. For the instant type, use an appropriate threshold (typically `0`). Verify with `jfr print --events ...` that the two types carry different properties.

**Exercise B — Threshold.** Run the main example with a 10 ms threshold and then change it to 50 ms while keeping processing time around 30 ms. Explain why the event count can change; do not rely on `sleep` to write brittle exact-timing assertions.

**Exercise C — Unsupported field.** Add a `String[]` or `enum` field to an event class and compare the field list in `jfr print`. Distinguish "Java allows declaring it" from "JFR includes that field in the schema".

**Exercise D — Inspecting in JMC.** Open `payment-attempts.jfr` in JDK Mission Control; filter for `demo.PaymentAttempt` and cross-check `requestId`, `amountCents`, `successful`, duration, and stack trace against CLI output. Identify attributes that help correlate to a specific request without putting sensitive data into the payload.

## Official References

- [Java SE 21 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): subclassing, supported fields, `begin/end/commit/isEnabled/shouldCommit`.
- [Java SE 21 — `jdk.jfr` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event definitions, metadata, `enabled`/`threshold`/`stackTrace` settings, and annotations.
- [Java SE 21 — `Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): recording configuration, start/stop/dump.
- [Java SE 21 — `RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): reading events from a JFR file.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summarizing and filtering events from the CLI.
