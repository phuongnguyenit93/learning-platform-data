# Creating Custom JFR Events in Java

**Custom JFR events** allow an application to record business or technical events that the JVM's built-in events do not describe in sufficient detail. Examples include request processing time, cache hit/miss decisions, queue wait time, batch results, processed record counts, or the status of a workflow step.

JFR (Java Flight Recorder) stores events in a `.jfr` recording. Afterward, you can use the `jfr` command, JDK Mission Control (JMC), or the JFR Consumer API to read and analyze the data.

A custom event is typically created by extending `jdk.jfr.Event`, declaring metadata with annotations, enabling the event in a recording, and calling `commit()` once the data to record is ready.

Short example:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Category({"Demo", "Application"})
public static class RequestEvent extends Event {
    public String requestId;
    public int statusCode;
}
~~~

If the event measures duration, use `begin()`, `end()`, and `commit()`. If the event records a decision at a single point in time, simply assign the fields and call `commit()`.

## 1. When should you create a custom event?

JFR already includes many events for JVM activity such as garbage collection, threads, allocation, class loading, compilation, file I/O, socket I/O, and monitor contention. Custom events add context that only the application knows.

Some suitable use cases:

- Measuring the processing time of a request type or a business step.
- Recording cache hits and misses.
- Measuring wait times on message queues or semaphores.
- Tracking batch jobs: job name, record count, result, and duration.
- Recording retries, timeouts, or circuit breaker transitions.
- Correlating business events with JVM CPU, GC, thread, and I/O events.
- Marking deployment timestamps, workflow starts, or task completions.

For example, JFR can record a socket read that took 400 ms, while a custom event reveals which request was waiting and which business operation triggered it. Both groups of events can be correlated by timestamp and thread.

Avoid creating events for every minor calculation or every log line. Only record data that helps answer a specific diagnostic question. Overly frequent events, oversized fields, or stack traces enabled on every event can bloat the recording and increase overhead.

## 2. Structure of a custom event

A custom event typically consists of three parts:

1. **Event class:** extends `jdk.jfr.Event`.
2. **Metadata:** name, label, description, category, and fields.
3. **Lifecycle:** create the event, measure duration if needed, assign fields, and commit.

JFR recognizes the event class and generates metadata for the recording. You do not need to design a binary file format or serialize objects manually.

### Event class

~~~java
public final class RequestEvent extends Event {
    public String requestId;
    public String operation;
    public int statusCode;
}
~~~

Public fields are included in the event's metadata. Prefer small, meaningful data types: booleans, integers, floating-point numbers, short `String` values, or controlled identifiers.

Do not put full requests/responses, large object graphs, or sensitive content into an event. If you need to correlate with logs, record a correlation ID that contains no secrets.

### Annotations describing an event

Common annotations:

| Annotation | Purpose |
|---|---|
| @Name | Stable technical name of the event type |
| @Label | User-friendly label displayed in tools |
| @Description | Description of the event or field |
| @Category | Groups the event in JMC and metadata |
| @Timespan | Time unit for a custom duration field |
| @Timestamp | Timestamp unit for a custom point-in-time field |
| @DataAmount | Data size unit such as bytes |

Example:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Description("Records the duration and result of a request")
@Category({"Demo", "Application"})
public static final class RequestEvent extends Event {
    @Label("Request ID")
    @Description("Synthetic request identifier")
    public String requestId;

    @Label("Payload size")
    @DataAmount(DataAmount.BYTES)
    public long payloadBytes;

    @Label("Queue wait")
    @Timespan(Timespan.MILLISECONDS)
    public long queueWaitMillis;
}
~~~

Use a namespaced event name, such as `com.example.RequestEvent`, to avoid collisions with JDK or third-party library events. Keep event names stable across versions so analysis tools can consistently recognize the same data type.

### Custom fields and built-in fields

JFR automatically provides standard fields for events, depending on the event type and configuration:

- `startTime`: the start timestamp of the event.
- `duration`: the duration of the event.
- `eventThread`: the thread associated with the event.
- `stackTrace`: the stack trace, if the event is configured to record one.

For duration events, `begin()` and `end()` set the start time and duration. For instant events, `duration` is typically 0 because the event is committed at a single point in time.

You do not need to redeclare `startTime` or `duration` fields. Give business fields distinct names such as `queueWaitMillis`, `payloadBytes`, or `statusCode`.

## 3. Duration events and instant events

These two common event types have different lifecycles.

### Duration event

A duration event measures how long an operation takes:

~~~java
RequestEvent event = new RequestEvent();
event.begin();

performRequest();

event.end();
event.commit();
~~~

- `begin()` records the start timestamp.
- `end()` records the end timestamp and computes the duration.
- `commit()` writes the event to the recording if the event is enabled and satisfies the settings.

Place `begin()` immediately before the region to measure and `end()` immediately after it. Avoid placing unrelated work in between, as it will inflate the measured duration.

### Instant event

An instant event records something that happens at a single point in time without measuring duration:

~~~java
CacheDecision event = new CacheDecision();
event.cacheKey = "product:42";
event.hit = true;
event.commit();
~~~

The event is recorded at the moment `commit()` is called. There is no need to call `begin()` or `end()`.

Use instant events for state transitions, decisions, outcomes, or milestones. Use duration events for requests, transactions, batch steps, or operations where latency matters.

## 4. Enabling events and recording settings

Declaring an event class does not mean the event automatically appears in every recording. The event must be enabled via recording settings.

When using the JFR API:

~~~java
try (Recording recording =
         new Recording(Configuration.getConfiguration("profile"))) {
    recording.enable(RequestEvent.class)
             .withThreshold(Duration.ofMillis(10))
             .withStackTrace();

    recording.enable(CacheDecision.class)
             .withStackTrace();

    recording.start();

    // Application work

    recording.stop();
    recording.dump(Path.of("custom-events.jfr"));
}
~~~

Methods:

- `enable(EventClass.class)`: enables the event type in the recording.
- `withThreshold(Duration)`: only records duration events that meet the duration threshold.
- `withStackTrace()`: requests capturing a stack trace for the event.
- `withoutStackTrace()`: disables stack traces when not needed.
- `start()`: starts recording.
- `stop()`: stops the recording.
- `dump(Path)`: writes the recording to a file.

In this example, `RequestEvent` is only recorded when its duration is at least 10 ms. `CacheDecision` is an instant event, so no duration threshold is set.

### `default` and `profile`

The JDK provides two common JFC configurations:

- `default`: less data, lower overhead, suitable for long-running or continuous recordings.
- `profile`: collects more data for deeper investigation, generally has higher overhead, and should be used for short periods when needed.

You can create a `Recording` from either the `default` or `profile` configuration. Choose based on your workload and goals. Do not default to `profile` on every production JVM.

### Configuring events via `.jfc`

You can enable custom events using a JFC file:

~~~bash
jfr configure --input default.jfc \
    +com.example.RequestEvent#enabled=true \
    +com.example.RequestEvent#stackTrace=true \
    +com.example.CacheDecision#enabled=true \
    --output custom-events.jfc
~~~

The `+` prefix adds new event settings to the JFC file. The JFC file can then be used when starting a recording:

~~~bash
jcmd <pid> JFR.start name=CustomEvents settings=custom-events.jfc duration=60s filename=custom-events.jfr
~~~

Or pass the configuration at JVM startup via `StartFlightRecording`. Check the exact syntax for your JDK using `jfr help configure` and `jcmd <pid> help JFR.start`.

When using the `Recording` API, you can configure events directly with `recording.enable()`. When using JFC or `jcmd`, ensure the event type is defined in the application and the event name matches exactly.

## 5. Controlling cost with `isEnabled()` and `shouldCommit()`

Custom events are designed for low-overhead recording, but building `String` instances, serializing data, capturing stack traces, or computing field values still has a cost.

Two useful methods:

- `isEnabled()`: checks whether the event is enabled in any active recording.
- `shouldCommit()`: checks whether the event should be committed according to settings, including the duration threshold, after the event has ended.

Duration event example:

~~~java
RequestEvent event = new RequestEvent();

if (event.isEnabled()) {
    event.begin();
    performRequest();
    event.end();

    if (event.shouldCommit()) {
        event.requestId = requestId;
        event.operation = operation;
        event.statusCode = 200;
        event.commit();
    }
}
~~~

`isEnabled()` lets you skip preparing fields when the event is not enabled. `shouldCommit()` is useful after `end()` to avoid constructing additional data for events that are too short or fail to meet the threshold.

If the event is not enabled, there is no reason to build a large payload only to assign it to fields and call `commit()`. If a field comes from an expensive calculation, compute it only when the event actually needs to be recorded.

For instant events, you can check `isEnabled()` before computing expensive fields:

~~~java
CacheDecision event = new CacheDecision();

if (event.isEnabled()) {
    event.cacheKey = buildShortCacheKey();
    event.hit = cacheHit;
    event.commit();
}
~~~

Do not set a high threshold on instant events, because their duration is normally 0. Thresholds are primarily meaningful for duration-based events.

## 6. Safe duration measurement with `try`/`finally`

When an operation can throw an exception, ensure `end()` is still called so the event has a valid duration.

Example:

~~~java
RequestEvent event = new RequestEvent();

if (event.isEnabled()) {
    event.begin();

    try {
        performRequest();
        event.statusCode = 200;
    } catch (RuntimeException ex) {
        event.statusCode = 500;
        throw ex;
    } finally {
        event.end();

        if (event.shouldCommit()) {
            event.requestId = requestId;
            event.operation = "loadProduct";
            event.commit();
        }
    }
}
~~~

The exception is rethrown to preserve the application's error behavior. The custom event only adds diagnostic data.

If you want to record the error type, record only the exception class or a controlled error code. Do not record the full exception message by default, as it may contain SQL, URLs, user data, or secrets.

If you need to measure duration when checked exceptions are thrown, preserve the `throws` declaration or handle them according to your application's exception policy. Never swallow an exception just to record an event.

## 7. Fields with units and metadata

A numeric field may lack clear meaning if the reader does not know its unit. Annotations help tools interpret and display the data accurately.

### `@Timespan`

~~~java
@Timespan(Timespan.MILLISECONDS)
public long queueWaitMillis;
~~~

The field is described as a duration in milliseconds. JMC and JFR tools can display the field with the appropriate unit.

### `@Timestamp`

~~~java
@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
public long externalTimestamp;
~~~

Use this when you genuinely need to store a custom timestamp. Since events already have a built-in `startTime`, a duplicate timestamp field is usually unnecessary.

### `@DataAmount`

~~~java
@DataAmount(DataAmount.BYTES)
public long payloadBytes;
~~~

Helps display data sizes in bytes and appropriate scaled units.

Do not assign the wrong unit. Storing microseconds while annotating the field as milliseconds will make reports seriously misleading.

## 8. Custom event classes vs. `EventFactory`

The most common approach is defining a class that extends `Event`. This gives you type safety, easy refactoring, and compile-time checking.

JFR also provides `EventFactory` to create event types dynamically when the schema is only known at runtime. This is an advanced option for frameworks or plugin systems that need to generate events from dynamic metadata.

For typical applications, prefer classes extending `Event`. Use `EventFactory` only when you have a clear requirement for dynamic event schemas; this API requires defining `AnnotationElement` and `ValueDescriptor` accurately, making it more complex and harder to verify at compile time.

Whether using a class or a factory, keep event names, fields, labels, and units stable so recording data can be read consistently.

## 9. Reading custom events with the `jfr` command

After creating a recording file, check the summary:

~~~bash
jfr summary custom-events.jfr
~~~

Look for the event types created by your application. The summary shows the event count and recorded size.

Inspect metadata:

~~~bash
jfr metadata --events com.example.RequestEvent,com.example.CacheDecision custom-events.jfr
~~~

Metadata shows the label, category, description, and field layout. Use this step to verify that your annotations are recognized properly.

Print events:

~~~bash
jfr print --events com.example.RequestEvent,com.example.CacheDecision custom-events.jfr
~~~

Print only `RequestEvent`:

~~~bash
jfr print --events com.example.RequestEvent custom-events.jfr
~~~

Export as JSON:

~~~bash
jfr print --json --events com.example.RequestEvent custom-events.jfr
~~~

Export as XML:

~~~bash
jfr print --xml --events com.example.RequestEvent custom-events.jfr
~~~

You can filter by category if the event is annotated with `@Category`:

~~~bash
jfr print --categories "Demo,Application" custom-events.jfr
~~~

If events do not appear, check in order:

1. Was the event class actually used during the recording?
2. Was the event type enabled?
3. Was the recording started before the event was committed?
4. Did the event meet the threshold?
5. Was the recording stopped and dumped to the right file?
6. Does the event name in metadata match?

Do not confuse metadata presence with recorded event instances. Metadata describes the event type; only the summary count and `print` output confirm that events were actually recorded.

## 10. Reading custom events with JDK Mission Control

JDK Mission Control (JMC) reads `.jfr` recordings and displays custom events alongside built-in events.

Workflow:

1. Open JMC.
2. Select `File > Open File`.
3. Open `custom-events.jfr`.
4. Wait for JMC to parse the metadata.
5. Open the `Event Browser`.
6. Locate the `Demo` category or the `Request event` event.
7. Select an event to inspect its timestamp, duration, fields, and stack trace.

`@Label` and `@Category` make events easy to find in the UI. `@Description` and field labels help readers understand what the data means.

For duration events, sort by duration to find slow requests. Filter by request ID or operation to view related event groups. You can correlate custom events with GC pauses, CPU samples, monitor contention, and socket events on the same timeline.

JMC can display events by category or event type. If an event does not appear, check the Event Browser filters and verify that the event is actually in the file using `jfr summary`/`print`.

## 11. Reading custom events with the `RecordingFile` API

The JDK provides the `jdk.jfr.consumer` package to read structured events from a recording file.

Key classes and methods:

| API | Role |
|---|---|
| RecordingFile | Opens and reads a recording sequentially |
| RecordedEvent | Represents a recorded event |
| getEventType() | Retrieves the event type metadata/name |
| getStartTime() | Retrieves the start timestamp |
| getDuration() | Retrieves the duration |
| getThread() | Retrieves the associated thread, if present |
| getStackTrace() | Retrieves the stack trace, if present |
| getString()/getInt()/getBoolean() | Reads a field by type |
| getValue(name) | Reads a field by name |

Example:

~~~java
try (RecordingFile file = new RecordingFile(Path.of("custom-events.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();

        if (event.getEventType().getName()
                .equals("com.example.RequestEvent")) {
            String requestId = event.getString("requestId");
            int statusCode = event.getInt("statusCode");

            System.out.println(requestId + " status=" + statusCode);
        }
    }
}
~~~

Sequential reading scales much better for large files than loading all events into a collection. Close `RecordingFile` with try-with-resources and inspect the schema before assuming a field always exists.

When building an analyzer, filter by event type early, read only the fields you need, and aggregate metrics instead of retaining every `RecordedEvent` in memory.

## 12. Complete Java 17+ example

This example creates two custom event types:

- `RequestEvent`: a duration event, committed only when its duration meets a 10 ms threshold.
- `CacheDecision`: an instant event recording cache hits and misses.

A second program reads the file using `RecordingFile` and prints the recorded fields.

Directory structure:

~~~text
custom-jfr-event/
└── src/
    └── com/
        └── example/
            ├── CustomJfrEventDemo.java
            └── CustomJfrEventReader.java
~~~

### `CustomJfrEventDemo.java`

~~~java
package com.example;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;

public final class CustomJfrEventDemo {
    @Name("com.example.RequestEvent")
    @Label("Request event")
    @Description("Records the duration and result of a demo request")
    @Category({"Demo", "Application"})
    public static final class RequestEvent extends Event {
        @Label("Request ID")
        @Description("Synthetic request identifier")
        public String requestId;

        @Label("Operation")
        public String operation;

        @Label("Status code")
        public int statusCode;

        @Label("Payload size")
        @DataAmount(DataAmount.BYTES)
        public long payloadBytes;

        @Label("Queue wait")
        @Timespan(Timespan.MILLISECONDS)
        public long queueWaitMillis;

        @Label("Simulated work")
        public int simulatedWorkMillis;
    }

    @Name("com.example.CacheDecision")
    @Label("Cache decision")
    @Description("Records a cache hit or miss as an instant event")
    @Category({"Demo", "Application"})
    public static final class CacheDecision extends Event {
        @Label("Cache key")
        public String cacheKey;

        @Label("Cache hit")
        public boolean hit;
    }

    private CustomJfrEventDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path destination = Path.of(args[0]).toAbsolutePath();
        int requestCount = 0;
        int cacheCount = 0;

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("Custom JFR event demo");
            recording.setToDisk(true);

            recording.enable(RequestEvent.class)
                    .withThreshold(Duration.ofMillis(10))
                    .withStackTrace();

            recording.enable(CacheDecision.class)
                    .withStackTrace();

            recording.start();

            for (int i = 1; i <= 3; i++) {
                RequestEvent event = new RequestEvent();

                if (event.isEnabled()) {
                    event.begin();
                    Thread.sleep(i == 1 ? 2 : 20 + i * 5);
                    event.end();

                    if (event.shouldCommit()) {
                        event.requestId = "REQ-" + i;
                        event.operation = "loadProduct";
                        event.statusCode = 200;
                        event.payloadBytes = 1024L * i;
                        event.queueWaitMillis = i * 2L;
                        event.simulatedWorkMillis = 10 + i * 10;
                        event.commit();
                        requestCount++;
                    }
                }
            }

            CacheDecision hit = new CacheDecision();
            if (hit.isEnabled()) {
                hit.cacheKey = "product:42";
                hit.hit = true;
                hit.commit();
                cacheCount++;
            }

            CacheDecision miss = new CacheDecision();
            if (miss.isEnabled()) {
                miss.cacheKey = "product:99";
                miss.hit = false;
                miss.commit();
                cacheCount++;
            }

            recording.stop();
            recording.dump(destination);
        }

        System.out.println("Recording written: " + destination.getFileName());
        System.out.println("Request events committed: " + requestCount);
        System.out.println("Cache events committed: " + cacheCount);
    }
}
~~~

### `CustomJfrEventReader.java`

~~~java
package com.example;

import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class CustomJfrEventReader {
    private CustomJfrEventReader() {
    }

    public static void main(String[] args) throws Exception {
        int requests = 0;
        int cacheDecisions = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String type = event.getEventType().getName();

                if (type.equals("com.example.RequestEvent")) {
                    System.out.printf("request %s work=%dms%n",
                            event.getString("requestId"),
                            event.getInt("simulatedWorkMillis"));
                    requests++;
                } else if (type.equals("com.example.CacheDecision")) {
                    System.out.printf("cache key=%s hit=%s%n",
                            event.getString("cacheKey"),
                            event.getBoolean("hit"));
                    cacheDecisions++;
                }
            }
        }

        System.out.println("Matched request events=" + requests);
        System.out.println("Matched cache events=" + cacheDecisions);
    }
}
~~~

### Compile

From the `custom-jfr-event` root directory:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/CustomJfrEventDemo.java \
    src/com/example/CustomJfrEventReader.java
~~~

### Create the recording

~~~bash
java -cp build/classes \
    com.example.CustomJfrEventDemo custom-events.jfr
~~~

Output:

~~~text
Recording written: custom-events.jfr
Request events committed: 2
Cache events committed: 2
~~~

The first event sleeps for about 2 ms, which is below the 10 ms threshold, so it is not committed. The remaining two request events exceed the threshold. Both `CacheDecision` events are instant events, so both are recorded.

### Read the recording

~~~bash
java -cp build/classes \
    com.example.CustomJfrEventReader custom-events.jfr
~~~

Exact output:

~~~text
request REQ-2 work=30ms
request REQ-3 work=40ms
cache key=product:42 hit=true
cache key=product:99 hit=false
Matched request events=2
Matched cache events=2
~~~

### Inspect with the JFR CLI

~~~bash
jfr summary custom-events.jfr

jfr metadata \
    --events com.example.RequestEvent,com.example.CacheDecision \
    custom-events.jfr

jfr print \
    --events com.example.RequestEvent,com.example.CacheDecision \
    custom-events.jfr
~~~

In the `print` output, `RequestEvent` includes `duration`, `requestId`, `operation`, `statusCode`, `payloadBytes`, `queueWaitMillis`, `eventThread`, and `stackTrace`. `CacheDecision` includes `timestamp`, `cacheKey`, `hit`, and `eventThread`.

Actual durations depend on the scheduler and environment, while the event counts and simulated fields in this example are deterministic.

## 13. Checking metadata and thresholds

When a custom event does not show up, distinguish between three cases:

- The event type is not enabled.
- The event is enabled, but no instances were committed.
- Instances were created, but filtered out by a threshold or recording filter.

Use `metadata` to verify the event type and fields:

~~~bash
jfr metadata --events com.example.RequestEvent custom-events.jfr
~~~

Use `summary` to check event counts:

~~~bash
jfr summary custom-events.jfr
~~~

Use `print` to read the actual events:

~~~bash
jfr print --events com.example.RequestEvent custom-events.jfr
~~~

If `metadata` lists the event type but the count is 0, check the event settings and the code path calling `commit()`. If the event duration is below the threshold, the event will not be recorded under that configuration.

If a field is missing, check the field name, the event schema, and whether the code assigns a value before calling `commit()`.

## 14. Designing good custom events

### Use stable naming

Event names should be namespaced and describe their purpose:

~~~text
com.example.RequestEvent
com.example.CacheDecision
com.example.BatchCompleted
com.example.RetryScheduled
~~~

Avoid renaming events arbitrarily across releases, as dashboards, scripts, and JMC filters may depend on those names.

### Give fields clear semantics

Field names should convey both meaning and unit. Use `queueWaitMillis` instead of `wait`; use `payloadBytes` instead of `size` when the value is in bytes.

Use `@Label` and `@Description` so analysts do not have to read the source code to understand the fields.

### Capture enough context, but not too much

Useful fields might include operation, status code, duration, record count, payload size, retry count, and correlation ID. Do not record full payloads or large object graphs.

### Choose appropriate thresholds

Thresholds filter out short, low-value events. Choose thresholds based on your latency budget and diagnostic questions. A threshold that is too high may miss important events; a threshold that is too low can bloat the recording.

### Enable stack traces selectively

Stack traces help locate where an event originated, but they add data and overhead. Enable them for events where finding the call site matters; consider disabling them for very high-frequency events or when the stack is not needed.

### Avoid duplicate events

JFR already has events for GC, threads, allocations, monitors, and I/O. Before creating a custom event, check whether built-in events already provide the information. Custom events should add business context, not duplicate runtime data that already exists.

## 15. Security and privacy

JFR recordings can contain internal application details. Custom events can also expose data that developers explicitly place into fields.

Do not record:

- Passwords, API keys, access tokens, or session secrets.
- Cookies or authentication headers.
- Full request/response bodies.
- Unnecessary personal data or customer information.
- SQL queries containing sensitive values.
- URLs with query strings containing tokens.
- Internal paths or configurations unless required for diagnostics.

Prefer synthetic or controlled correlation IDs, status enums, error codes, counts, and durations. Store JFR files in access-restricted locations and review them before sharing.

Do not assume scrubbing a few events guarantees the entire recording is clean. Custom fields can still contain secrets; inspect the actual contents.

## 16. Overhead and limits

JFR is designed to record runtime data with low overhead, but the overhead is not zero. Impact depends on:

- Event frequency.
- Number of fields and data size.
- Thresholds.
- Whether stack traces are enabled.
- `default` vs. `profile` recording settings.
- Recording duration and file limits.
- Number of concurrent recordings.

Ways to reduce overhead:

- Enable only the events you need.
- Use thresholds aligned with your latency budget.
- Use `isEnabled()` before constructing expensive fields.
- Use `shouldCommit()` after `end()` to avoid preparing data for events that miss the threshold.
- Reduce stack trace capture when not needed.
- Avoid recording large `String` values or serializing objects.
- Set `maxage`/`maxsize` limits for long-running recordings.
- Measure overhead on a representative workload before broad rollout.

JFR does not replace logging, metrics, or distributed tracing. JFR provides detailed in-JVM runtime data; distributed tracing connects requests across services; metrics provide trends and alerts; logs capture messages and business errors. These tools complement one another.

## 17. Common issues

### Event class does not appear in metadata

Check that the class extends `Event`, has a valid `@Name` annotation, and was actually used during the recording. Verify that the event class is enabled in the `Recording` or JFC configuration.

### Event type has metadata but zero events

Check whether the code calls `commit()`, whether the recording had started, and whether the event was dropped by a filter or threshold.

### Duration is always 0

Verify that `begin()` and `end()` are called in the right order before `commit()`. For instant events, a duration of 0 is normal.

### Event duration is larger than expected

Place `begin()` right before the target region and `end()` right after it. Keep logging, serialization, and unrelated processing outside the measured region.

### Empty stack trace

Check `withStackTrace()` or the `stackTrace=true` setting. Not all recordings enable stack traces for custom events.

### Field is missing from the file

The field must be declared on the event class and assigned before `commit()`. Check the metadata of the exact recording file to confirm the schema.

### Too many events recorded

Increase the threshold, reduce event frequency, remove unnecessary fields, or enable the recording only during an investigation window. Check recording settings before changing code.

### Event does not show up in JMC

Use `jfr summary` and `jfr print` to confirm the event is in the file. Check filters, categories, time range, and JMC version.

## 18. Checklist before adding custom events to an application

- [ ] The event serves a specific diagnostic purpose.
- [ ] The event name is namespaced and stable.
- [ ] Appropriate `@Label`, `@Description`, and `@Category` annotations are present.
- [ ] Fields have clear names, types, and units.
- [ ] Duration events call `begin()`, `end()`, and `commit()` in the right order.
- [ ] Instant events commit at the exact point to record.
- [ ] The recording enables the correct event types.
- [ ] Thresholds match the latency you want to observe.
- [ ] `isEnabled()` / `shouldCommit()` are used when needed to reduce cost.
- [ ] Stack traces are enabled only when they add value.
- [ ] No secrets, payloads, or unnecessary personal data are recorded.
- [ ] `metadata`, `summary`, and `print` output have been verified.
- [ ] Overhead has been measured on a representative workload.
- [ ] Reading events with JMC or `RecordingFile` has been tested.
- [ ] Rules are in place for protecting and storing recording files.

## 19. Commands to remember

~~~bash
# Inspect available JFR commands
jfr help

# Configure custom event settings
jfr configure --input default.jfc \
    +com.example.RequestEvent#enabled=true \
    +com.example.RequestEvent#stackTrace=true \
    --output custom-events.jfc

# Start a recording using a custom JFC
jcmd <pid> JFR.start name=CustomEvents settings=custom-events.jfc duration=60s filename=custom-events.jfr

# Check active recordings
jcmd <pid> JFR.check

# Dump a running recording
jcmd <pid> JFR.dump name=CustomEvents filename=custom-events-snapshot.jfr

# Stop a recording
jcmd <pid> JFR.stop name=CustomEvents

# Inspect the recording
jfr summary custom-events.jfr
jfr metadata --events com.example.RequestEvent custom-events.jfr
jfr print --events com.example.RequestEvent custom-events.jfr
jfr print --json --events com.example.RequestEvent custom-events.jfr
~~~

Custom JFR events turn application-specific context into runtime data that can be analyzed alongside JVM events. Use stable names and metadata, choose the right duration or instant lifecycle, enable thresholds and stack traces intentionally, and verify recordings with `summary`, `metadata`, `print`, JMC, or `RecordingFile`. Keep fields small, unit-annotated, and free of secrets so recordings remain valuable for investigations while staying easy to protect.

## References

- [JDK Flight Recorder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [Event API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Recording API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [EventSettings API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [RecordingFile API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
