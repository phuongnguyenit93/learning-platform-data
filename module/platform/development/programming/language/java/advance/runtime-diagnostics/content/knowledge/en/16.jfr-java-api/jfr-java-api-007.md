# 16.7 Reading JFR Files via RecordingFile and Accessing RecordedEvent Fields

## 1. Objectives and Problem Statement

Java Flight Recorder (JFR) persists runtime data into **`.jfr`** files: GC events, CPU samples, threads, allocations, locks, I/O, and application-defined custom events. You can view files using `jfr print` or JDK Mission Control, but when you need to **automate filtering, aggregate metrics, correlate timestamps, export investigation summaries, or build internal tooling**, you need to read JFR directly in Java.

The `jdk.jfr.consumer` package provides two central classes:

- **`RecordingFile`:** opens a `.jfr` file and reads events sequentially; implements `AutoCloseable` via `Closeable`, so wrap it in `try-with-resources`.
- **`RecordedEvent`:** represents **a single recorded event** in the recording; provides event type, timestamps, duration, thread, stack trace, and typed field access by name.

This lesson teaches how to read files, filter by event type, access typed fields, discover schemas dynamically, handle absent fields, and aggregate data efficiently. Examples run on **Java 17+**, verified on JDK 21.

After this lesson, you will be able to:

1. Stream a `.jfr` file sequentially using the `hasMoreEvents()` / `readEvent()` loop.
2. Filter events via `event.getEventType().getName()` and distinguish technical names from display labels.
3. Use `getString`, `getInt`, `getLong`, `getBoolean`, `getValue`, and `hasField` appropriately.
4. Read `Instant`, `Duration`, `RecordedThread`, `RecordedStackTrace`, and `ValueDescriptor` metadata.
5. Handle large files, JDK version differences, or missing fields without drawing false conclusions from empty data.

**Important boundary:** `RecordingFile` is an API for **reading events already stored in a file**. It is not an API for starting recordings or subscribing to live events. To create a recording, use `jdk.jfr.Recording` or `jcmd`; to consume events live as a stream, the JDK offers `RecordingStream`, which is a separate mechanism.

## 2. Data Flow from JVM to Java Objects

```text
JVM/application
  |
  |  JVM built-in events / custom Event.commit()
  v
JFR recording
  |
  |  dump / stop / write file
  v
recording.jfr
  |
  v
new RecordingFile(Path)
  |
  +-- hasMoreEvents() ? -- false --> finish + close()
  |
  +-- true --> readEvent() --> RecordedEvent
                                |
                                +-- getEventType().getName()
                                +-- getStartTime(), getEndTime(), getDuration()
                                +-- hasField(), getString(), getLong(), ...
                                +-- getThread(), getStackTrace()
                                |
                                v
                         filter / group / aggregate / alert
```

A single file contains **many event types**, and each event type has a **different field schema**. Therefore, never write a parser that blindly forces every `RecordedEvent` into a fixed "duration + bytes + path + thread" structure.

For example:

- `jdk.GarbageCollection` describes a GC event using the JDK's schema.
- `jdk.JavaMonitorEnter` describes waiting to enter a monitor.
- `jdk.FileRead` describes a file read operation.
- `demo.Request` can be an application-defined event with `endpoint`, `status`, `bytes`, and `ok`.

All of them appear as `RecordedEvent` instances, yet business fields like `status` **belong only to event types that declare them**. Always filter by type before reading type-specific fields.

## 3. Core API Set

| API | Meaning | Notes |
| --- | --- | --- |
| `new RecordingFile(Path)` | Opens an existing JFR file | `IOException` if file is corrupt/invalid; use trusted sources |
| `hasMoreEvents()` | Checks whether unread events remain | Call before `readEvent()` |
| `readEvent()` | Reads the next event | Can throw `EOFException` if called when exhausted; also `IOException` |
| `close()` | Releases file resources | Use `try-with-resources` |
| `RecordingFile.readAllEvents(Path)` | Loads all events into a list at once | Suitable only for small files; high RAM usage |
| `readEventTypes()` | Retrieves metadata of event types in the file | Having a type in metadata does not mean matching instances exist |
| `event.getEventType().getName()` | Technical name of the event | Use full name for accurate classification |
| `event.getStartTime()` / `getEndTime()` | Timestamps as `Instant` | Not request wait duration |
| `event.getDuration()` | Elapsed time as `Duration` | Not a raw integer millisecond count |
| `event.hasField(name)` | Does the schema contain a field of that name? | A field may exist yet hold `null` |
| `event.getValue(name)` | Generic value | Return type depends on schema; avoid blind casting |
| `event.getString/getInt/getLong/...` | Typed field getters | Wrong field name or type can throw `IllegalArgumentException` |
| `event.getFields()` | List of `ValueDescriptor` | Inspect field names/types without hardcoding |
| `event.getThread()` / `getStackTrace()` | Recorded thread and stack info | May be `null` if not recorded |

### 3.1. Standard reading loop

```java
// Illustrative fragment; requires imports, enclosing method, and a real file path.
Path path = Path.of("recording.jfr");
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
```

This is the most important pattern: **read one event at a time**, process it, and move to the next. `RecordingFile` manages parser/file resources and closes cleanly if an exception occurs.

`readEvent()` makes no guarantee about which type arrives next: event A might be GC, event B CPU, event C an application event. Before accessing type-specific fields, filter by type.

### 3.2. Ordering and completeness

`RecordingFile` reads events from the file. When analyzing latency, use **timestamps inside the event**, not print order or iteration order, as evidence of causality between two events. A file can contain multiple threads, overlapping duration events, identical timestamps, and periodic events.

Being able to read a file successfully does not prove **all relevant data was captured**. Events may be disabled, filtered by threshold, sampled, cut off by recording duration, or absent due to inactivity. Reading 0 events of a type requires distinguishing "did not happen", "was not recorded", and "filtered out incorrectly".

## 4. Complete Hands-on Lab: Creating a JFR File and Reading It Back

To avoid depending on an external `.jfr` file, the example emits three custom events with deterministic fields, writes them to `requests-demo.jfr`, and opens the file with `RecordingFile`. The recording creation part is purely for testing; **the focus** is the `inspect` method.

Create **`JfrFileReadLab.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public final class JfrFileReadLab {
    @Name("demo.Request")
    public static final class RequestEvent extends Event {
        public String endpoint;
        public int status;
        public long bytes;
        public boolean ok;
    }

    private static void emit(String endpoint, int status, long bytes, boolean ok) {
        RequestEvent event = new RequestEvent();
        event.endpoint = endpoint;
        event.status = status;
        event.bytes = bytes;
        event.ok = ok;
        event.begin();
        event.end();
        event.commit();
    }

    private static void inspect(Path file) throws Exception {
        List<String> lines = new ArrayList<>();
        int count = 0;
        int successful = 0;
        long totalBytes = 0;

        try (RecordingFile input = new RecordingFile(file)) {
            while (input.hasMoreEvents()) {
                RecordedEvent event = input.readEvent();

                if (!"demo.Request".equals(event.getEventType().getName())) {
                    continue;
                }
                if (!event.hasField("endpoint") || !event.hasField("bytes")) {
                    throw new IllegalStateException("Missing expected JFR fields");
                }

                String endpoint = event.getString("endpoint");
                int status = event.getInt("status");
                long bytes = event.getLong("bytes");
                boolean ok = event.getBoolean("ok");

                if (event.getStartTime() == null
                        || event.getDuration().isNegative()) {
                    throw new IllegalStateException("Invalid event timing");
                }

                RecordedThread thread = event.getThread();
                if (thread != null) {
                    thread.getJavaName();
                }
                RecordedStackTrace trace = event.getStackTrace();
                if (trace != null) {
                    trace.getFrames();
                }

                count++;
                totalBytes += bytes;
                if (ok) {
                    successful++;
                }
                lines.add(endpoint + " status=" + status
                        + " bytes=" + bytes + " ok=" + ok);
            }
        }

        Collections.sort(lines);
        for (String line : lines) {
            System.out.println(line);
        }
        System.out.println("events=" + count
                + " totalBytes=" + totalBytes
                + " successful=" + successful);
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("requests-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(RequestEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();
            emit("/orders", 200, 100L, true);
            emit("/reports", 503, 200L, false);
            emit("/orders", 200, 300L, true);
            recording.stop();
            recording.dump(output);
        }

        inspect(output);
    }
}
```

Compile on JDK 17 or later. The `--release 17` flag verifies the code uses Java 17 APIs:

```bash
javac --release 17 JfrFileReadLab.java
java JfrFileReadLab
```

**Stdout verified on JDK 21:**

```text
/orders status=200 bytes=100 ok=true
/orders status=200 bytes=300 ok=true
/reports status=503 bytes=200 ok=false
events=3 totalBytes=600 successful=2
```

The program prints only events named `demo.Request` and sorts strings before printing, so the example output does not depend on event read order. Normal JFR/JVM activity may emit other event types as well, which the `if` filter skips. Each run creates/overwrites `requests-demo.jfr` in the working directory; use a dedicated practice directory.

Explanation of the reading logic:

1. `new RecordingFile(file)` opens the JFR snapshot; `try-with-resources` guarantees closing the parser.
2. `hasMoreEvents()` and `readEvent()` iterate sequentially through whatever the file recorded.
3. `getEventType().getName()` selects only the custom type `demo.Request`; it avoids trying to read an `endpoint` field from an unrelated GC event.
4. `hasField(...)` verifies the schema has the required fields before reading them.
5. `getString("endpoint")`, `getInt("status")`, `getLong("bytes")`, and `getBoolean("ok")` return typed Java values. `totalBytes` is the **sum of the demo event payloads**, not the size of the JFR file in bytes.
6. `getStartTime()` and `getDuration()` are validated; actual values vary per run, so the program does not print them in the fixed stdout.
7. `getThread()` and `getStackTrace()` are handled safely against `null`. Here `withoutStackTrace()` saves space; do not expect stack traces for this custom type in the file.
8. Event count, total bytes, and `ok` count are application-level aggregations computed from the read fields, not built-in counters maintained by `RecordingFile`.

Run external CLI commands as well to cross-check:

```bash
jfr summary requests-demo.jfr
jfr print --events demo.Request requests-demo.jfr
```

`jfr summary` lists event types and counts in the file; `jfr print` displays a human-friendly view. They may include metadata/timestamps that vary across runs, so do not treat CLI output as a fixed transcript.

## 5. Accessing RecordedEvent Fields with the Right Types

`RecordedEvent` inherits methods from `RecordedObject`. Beyond common event metadata, specific fields are accessed by **schema field name**, not by custom column headers you might use in a CSV.

### 5.1. Common getters

| Data type in event | Read via | Example |
| --- | --- | --- |
| `String` | `getString(name)` | `event.getString("endpoint")` |
| `boolean` | `getBoolean(name)` | `event.getBoolean("ok")` |
| `int` | `getInt(name)` | `event.getInt("status")` |
| `long` | `getLong(name)` | `event.getLong("bytes")` |
| `double` | `getDouble(name)` | For `double` fields or eligible primitive widening |
| Generic value | `getValue(name)` | `Object raw = event.getValue("bytes")` |
| Event start/end | `getStartTime()` / `getEndTime()` | `Instant` |
| Event duration | `getDuration()` **no arguments** | `Duration` |
| Annotated custom timespan field | `getDuration("fieldName")` | `Duration` of that field |
| Annotated custom timestamp field | `getInstant("fieldName")` | `Instant` of that field |
| Class reference field | `getClass("fieldName")` | `RecordedClass`, not `java.lang.Class` |
| Thread reference field | `getThread("fieldName")` | `RecordedThread` |

**Do not confuse same-named overloads**:

- `event.getDuration()` returns the duration **of the entire event** (from start to end).
- `event.getDuration("myDurationField")` reads **a timespan field inside the event** if the schema declares it in a way JFR can convert to `Duration`.

Similarly, `event.getThread()` is the thread associated with committing/recording the event, while `event.getThread("sampledThread")` reads a **specifically named thread field** if that type defines one. For sampling events, the sampled thread and the committing thread can differ in meaning.

### 5.2. Missing fields vs. null-valued fields

`hasField("x") == false` means the schema does not contain field `x`. It **does not** mean "the field is null" or "the value is 0". If a field exists in the schema but its value was not recorded or is null, `hasField("x")` still returns `true`. Read fields defensively:

```java
// Fragment where RecordedEvent event is available.
if (event.hasField("endpoint")) {
    String endpoint = event.getString("endpoint");
    if (endpoint != null) {
        System.out.println(endpoint);
    }
}
```

A typed getter can throw `IllegalArgumentException` if the field name does not exist or the data type is incompatible. `getInt("bytes")` can fail if `bytes` is actually `long`; `getString("status")` will not convert an `int` to a `String` for you. To display arbitrary event types flexibly, use `ValueDescriptor` and `getValue` with runtime type checks.

### 5.3. `getValue` and nested field paths

`event.getValue("field")` returns a generic value; for complex fields, it may be a `RecordedThread`, `RecordedClass`, `RecordedObject`, or another consumer-supported type. Therefore, avoid blindly casting everything to `String`.

`RecordedObject` also supports dot-separated nested paths such as `"thread.group.parent.name"` if the field graph actually contains those components. This is convenient for querying nested metadata, provided **the path exists** in the actual schema/value:

```java
// Illustrative fragment showing how to guard a custom field path.
String path = "thread.group.parent.name";
if (event.hasField(path)) {
    Object nested = event.getValue(path);
    System.out.println(nested);
}
```

Do not infer that every `RecordedEvent` has `thread`, `group`, or `parent` fields matching this exact path. It is an example of **syntax**, not a universal schema across all events. A field may be absent or an intermediate object may be `null`.

## 6. Discovering Schemas with EventType and ValueDescriptor

A long-lived JFR analysis tool must tolerate different JDK versions adding fields, renaming fields, or omitting certain events. The safe approach is inspecting metadata rather than hardcoding every schema.

- `event.getEventType()` returns the `EventType` describing the event's kind.
- `event.getEventType().getName()` is the full name, e.g., `jdk.JavaMonitorEnter` or `demo.Request`.
- `event.getEventType().getLabel()` is a human-oriented label, not a stable filter key.
- `event.getFields()` returns a list of `ValueDescriptor`; each descriptor provides `getName()`, `getTypeName()`, and annotations/metadata.
- `file.readEventTypes()` returns the `EventType` metadata known in the file; this is **not** a list of event instances.

Example inspecting an event's schema:

```java
// Illustrative fragment, requires import jdk.jfr.ValueDescriptor.
for (ValueDescriptor descriptor : event.getFields()) {
    String fieldName = descriptor.getName();
    String fieldType = descriptor.getTypeName();
    Object value = event.getValue(fieldName);
    System.out.println(fieldName + " [" + fieldType + "] = " + value);
}
```

This reveals **which fields actually exist**. However, printing full `toString()` output of nested objects or stack traces across large files can be huge. In real tools, limit the number of events and fields printed, and format complex values explicitly.

### 6.1. A generic file reader: JfrInspect

Create **`JfrInspect.java`**. The program takes a file and an event type name from the command line, scans the entire file to count matching events, yet **prints at most the first two samples**; when the type is `demo.Request`, it prints `endpoint` and `status` if metadata confirms their presence:

```java
import java.nio.file.Path;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrInspect {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: java JfrInspect <file.jfr> <event-type>");
            System.exit(2);
        }
        String targetType = args[1];
        long matches = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if (!targetType.equals(event.getEventType().getName())) {
                    continue;
                }

                matches++;
                if (matches <= 2) {
                    System.out.println("type=" + event.getEventType().getName());
                    System.out.println("start=" + event.getStartTime());
                    System.out.println("duration=" + event.getDuration());

                    for (ValueDescriptor field : event.getFields()) {
                        if (field.getName().equals("endpoint")
                                || field.getName().equals("status")) {
                            System.out.println(field.getName() + " ["
                                    + field.getTypeName() + "]="
                                    + event.getValue(field.getName()));
                        }
                    }
                }
            }
        }

        System.out.println("matched=" + matches);
    }
}
```

Compile and read the file generated by the previous example:

```bash
javac --release 17 JfrInspect.java
java JfrInspect requests-demo.jfr demo.Request
```

**Verified output shape** (timestamp and duration vary per run):

```text
type=demo.Request
start=<actual Instant of the first event>
duration=<actual Duration of the first event>
endpoint [java.lang.String]=/orders
status [int]=200
type=demo.Request
start=<actual Instant of the second event>
duration=<actual Duration of the second event>
endpoint [java.lang.String]=/reports
status [int]=503
matched=3
```

In the transcript above, placeholders inside `<...>` are **illustrative annotations, not literal stdout**. When compiled and run, `Instant` prints in ISO-8601 format and `Duration` prints in Java's `PT...S` format. Although the reader prints only the first two matching events, `matched=3` still counts all three events.

Use the same approach on another JFR file, for instance:

```bash
java JfrInspect service.jfr jdk.JavaMonitorEnter
```

For that type, the example prints only the name, timestamp, and duration because it intentionally does not hardcode fields outside the demo schema. To inspect specific fields, check `event.getFields()`, metadata from `jfr metadata`, or JMC, then add matching logic. Do not conclude that a type "missing `endpoint`" indicates a corrupt file: `endpoint` exists only in the custom demo event.

### 6.2. Schemas and formats vary across JDKs

A brittle assumption is expecting every `jdk.FileRead` to always have the exact same fields, names, and types across all JDK releases/vendors. In reality, JDKs can add or alter fields. A robust tool should:

1. Filter using explicit event type names.
2. Verify required fields and types via `ValueDescriptor`.
3. Handle optional fields with `hasField` and `null` checks.
4. Record the JDK/version, recording name, event types, and schemas encountered.
5. Avoid blind casting or using `toString()` as a canonical storage format.

If exporting JSON or CSV, explicitly map `RecordedThread`, `RecordedClass`, `Duration`, `Instant`, and nested fields; never let a generic serializer dump a huge object graph.

## 7. Time, Duration, Units, and Context

### 7.1. `Instant` vs. `Duration`

`getStartTime()` and `getEndTime()` return `java.time.Instant`: **points in time**. `getDuration()` returns `java.time.Duration`: **an elapsed interval**. For example, a `jdk.JavaMonitorEnter` event may start at `10:00:02.123` with a 24 ms duration; that **does not prove** the entire HTTP request took 24 ms or was slow solely due to that single event.

```java
// Illustrative fragment for a read RecordedEvent.
java.time.Instant start = event.getStartTime();
java.time.Instant end = event.getEndTime();
java.time.Duration duration = event.getDuration();
double milliseconds = duration.toNanos() / 1_000_000.0;
```

`duration.toMillis()` returns a `long` and truncates sub-millisecond fractions; use `toNanos()/1_000_000.0` when fractional precision is needed and the span fits within bounds. For huge `Duration` values, `toNanos()` can overflow, requiring safer conversion. Never confuse timestamp, size, and ratio fields that carry different unit metadata.

### 7.2. Do not invent invalid total durations

If events A and B run concurrently on two threads and overlap, summing `duration(A) + duration(B)` can **exceed** the wall-clock time between the two points. If JFR collects events via sampling or thresholds, the sum of recorded event durations is also **not necessarily** the total duration of all activity that occurred.

When analyzing: filter accurately by event type, time window, thread/request correlation, and units; explicitly note whether the sample was filtered by threshold or period.

### 7.3. Time zones and correlating other logs

`Instant` carries no local time zone; it represents an absolute point on the timeline. When generating reports in Vietnam time:

```java
// Illustrative fragment.
java.time.ZonedDateTime local = event.getStartTime()
        .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"));
```

Correlate JFR with application logs, APM, and container logs using consistent timestamps, keeping clock skew in mind across multiple hosts. Do not convert `Instant` into a local string without offset/time zone if cross-service analysis is needed.

## 8. Threads, Stack Traces, and Nested Objects

### 8.1. `RecordedThread`

`event.getThread()` returns a `RecordedThread` if that information was recorded on the event. To display the Java thread name:

```java
// Illustrative fragment, requires importing RecordedThread.
RecordedThread thread = event.getThread();
String threadName = thread == null ? "(not recorded)"
        : thread.getJavaName();
System.out.println(threadName);
```

`getJavaName()` can return `null` if no Java thread name is available. `getJavaThreadId()` and `getOSThreadId()` are distinct IDs; never interchange them when joining data. On JDKs supporting virtual threads, `isVirtual()` describes the recorded thread kind, yet does not imply all events stayed on the same OS carrier thread.

An event may carry **another thread field** (such as a sampled thread). In that case use `event.getThread("fieldName")` once the schema confirms the field. Never assume `event.getThread()` is always the sampled thread.

### 8.2. `RecordedStackTrace` and `RecordedFrame`

`getStackTrace()` can be `null` when stack capture is disabled or the event type does not record stacks. When present:

```java
// Illustrative fragment, requires importing RecordedStackTrace/RecordedFrame.
RecordedStackTrace stack = event.getStackTrace();
if (stack != null) {
    System.out.println("truncated=" + stack.isTruncated());
    for (var frame : stack.getFrames()) {
        System.out.println(frame.getMethod().getName()
                + ":" + frame.getLineNumber());
    }
}
```

- `getFrames()` returns a list of `RecordedFrame`; `getLineNumber()` can be `-1` when line numbers are unavailable.
- `isTruncated()` indicates whether the stack was truncated due to depth/size limits.
- `frame.getMethod()` returns `RecordedMethod`; to get the declaring class name of the method, check `frame.getMethod().getType().getName()`.
- Event frames are not a distributed trace: they represent the call stack captured at the point defined by the event's semantics.

Enable stack traces only for events needed in investigations; on high-frequency events, stack traces increase data size and overhead. You cannot recover stacks that **were never recorded** by increasing `jfr print --stack-depth` at read time.

### 8.3. Composite types

`event.getValue(name)` can return boxed primitives, `String`, `RecordedClass`, `RecordedThread`, `RecordedObject`, or other schema-defined types. When building a CSV exporter, **serialize deliberately**:

- `RecordedClass`: export the class name.
- `RecordedThread`: export thread name/ID if present.
- `RecordedStackTrace`: export only frame count or top relevant frames when permitted.
- `Instant`: export an ISO-8601 string with offset/context.
- `Duration`: export a number with explicit units, e.g., nanoseconds or milliseconds.
- `null` field: emit an explicit empty/null marker rather than converting to `0`.

## 9. Choosing Reading Strategies for Small vs. Large Files

### 9.1. `readAllEvents(Path)` is convenient but memory-heavy

```java
// Illustrative fragment: use only when the file is small enough.
java.util.List<RecordedEvent> events =
        RecordingFile.readAllEvents(Path.of("small.jfr"));
System.out.println("events=" + events.size());
```

`readAllEvents` loads all events into a `List`. It suits short scripts or small files needing multiple passes. For large files of hundreds of MB or millions of events, keeping the whole list on the heap can trigger heavy GC or `OutOfMemoryError`. The in-memory size of parsed Java objects **does not equal** the compressed/binary `.jfr` file size.

### 9.2. Streaming via `RecordingFile`

For large files, maintain a `long count` or compact aggregates and retain only required events instead of putting every `RecordedEvent` into an `ArrayList`. Example:

```java
// Illustrative counter fragment that avoids keeping all events on the heap.
long count = 0;
try (RecordingFile file =
        new RecordingFile(Path.of("service.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("jdk.JavaMonitorEnter".equals(
                event.getEventType().getName())) {
            count++;
        }
    }
}
System.out.println("monitorEvents=" + count);
```

Count only recorded events; **do not** infer total lock contentions in the application because events may have been filtered. If you need percentiles, use a bounded histogram or streaming quantile algorithm rather than storing all durations just to compute p99 on a huge recording.

`RecordingFile` is a single-pass forward reader; to re-analyze from the start, open a new `RecordingFile`. This API reads an existing file; do not use it as a live tailing mechanism.

### 9.3. File management and I/O errors

Errors to recognize:

- `NoSuchFileException`: wrong path or file not created yet.
- `IOException`: invalid file, read failure, or unsupported format.
- `EOFException`: calling `readEvent()` when no events remain; the `hasMoreEvents()` loop avoids this during normal API usage.
- `IllegalArgumentException`: reading a nonexistent field name or wrong field type.
- `SecurityException` or OS permission errors: the reader process lacks access to the file.

Read **files from trusted sources only**; recordings can contain thread info, class names, file paths, request metadata, and sensitive data. Restrict permissions on `.jfr` files, delete securely when no longer needed, and never accept arbitrary untrusted uploads into an internal parser without resource limits.

If data looks incomplete, check whether the recording stopped/dumped cleanly; the recording may still have been running, rotated, or had intervals evicted by retention settings. Never conclude from a partial/corrupt file that the application emitted no events.

## 10. Cross-Checking with the CLI Before Writing a Parser

Use the JDK's built-in tools to learn event names and schemas in a file:

```bash
jfr summary service.jfr
jfr metadata service.jfr
jfr print --events jdk.JavaMonitorEnter service.jfr
```

- `jfr summary` shows event types and counts (format varies slightly by JDK version).
- `jfr metadata` prints metadata/type descriptions, useful before hardcoding fields.
- `jfr print --events` shows real examples of field values and stacks (if present).
- If using JDK Mission Control, select the event type to inspect fields, aggregations, and stacks, then verify against your `RecordingFile` code.

A parser should explicitly record **input conditions**: which JDK/build produced the file, which host it came from, which event types were enabled, what time range was covered, and whether thresholds or sampling applied. This context is essential for interpreting numbers; a JFR file is not "the complete history of the JVM".

## 11. Practical Scenarios: From File to Diagnosis

### 11.1. Finding slow file reads

You can filter `jdk.FileRead`, read `getDuration()`, and inspect present fields such as `path` or `bytesRead` per the actual schema. Suppose you want recorded events with duration at least 20 ms:

```java
// Illustrative fragment inside a RecordedEvent reading loop.
if ("jdk.FileRead".equals(event.getEventType().getName())
        && event.getDuration().compareTo(
                java.time.Duration.ofMillis(20)) >= 0) {
    System.out.println(event.getStartTime()
            + " duration=" + event.getDuration());
}
```

**This is consumer-side filtering after the file was written.** It differs from `jdk.FileRead#threshold` applied **at collection time**: the consumer can only discard events **that already exist** in the file, and cannot recover events the recording never captured.

If `path`/`bytes` are missing from the schema, do not assume them; inspect `getFields()`. If stack trace is null, you cannot attribute the caller from this file alone; take a new recording with stacks enabled for the target event.

### 11.2. Grouping events by thread

`event.getThread()` returns the thread that executed/committed the event. To group event counts by thread, key by an appropriate ID alongside the name for readability. Note that Java thread ID, OS thread ID, and JFR event thread are distinct concepts; thread names can collide or change. For events with a sampled thread field, prefer the thread field defined by that event type.

A single request can often run across multiple threads or virtual threads; **grouping by thread does not mean grouping by request**. To group by request, use a correlation ID or application-recorded custom event payload.

### 11.3. Counting failed custom operations

For `demo.Request` in our example, we know `ok` is `boolean` and `status` is `int`, so we use typed getters and aggregate. This counts **committed/recorded custom events**. Do not use it as a substitute for web server request totals unless every request is instrumented and the recording had no threshold/retention drops.

### 11.4. Combining multiple recordings

A service can produce multiple files, each with its own time span and configuration. For comparisons, retain source metadata: filename, JVM identity, JDK version, start/end window, and event settings. Never blindly concatenate files and sum durations or counts when they overlap in time or come from concurrent recordings of the same JVM.

When merging is required, normalize time zones and define deduplication rules matching your analytical goal; JFR events do not automatically carry a cross-file unique request ID.

## 12. Common Mistakes and Corrections

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| Calling `getString("bytes")` on a `long` field | Typed getters do not convert numbers to `String` | Use `getLong("bytes")` or metadata + `getValue` |
| Calling `getInt("status")` on every event | Not every event type has a `status` field | Filter `getEventType().getName()` first |
| Assuming `hasField` true means non-null value | Schema presence differs from recorded value | Check `null` for reference fields |
| Calling `getStackTrace().getFrames()` directly | Stack may not have been recorded | Check `getStackTrace() != null` |
| Treating `event.getDuration()` as integer ms | API returns `Duration` | Convert units explicitly, preserving precision |
| Using `readAllEvents` on huge files | Loads every event into RAM | Stream with `RecordingFile` and compact aggregates |
| Printing all fields of every event | Produces massive output and leaks metadata | Filter by type, event limit, and needed fields |
| Not closing `RecordingFile` | Leaks file/parser handles | Use `try-with-resources` |
| Assuming 0 events = no incident | Event may be disabled, thresholded, or outside window | Check collection config and workload |
| Summing times/durations across threads | Events can overlap without causal links | Use timestamps/correlation and analyze separately |
| Depending on fixed internal fields across all JDKs | Schemas can evolve | Use `getFields()`/`ValueDescriptor`, handle optionals |
| Confusing `RecordedThread` with a live `java.lang.Thread` | Object is metadata snapshot, not a live JVM thread | Use metadata ID/name; do not invoke thread control APIs |

## 13. Self-Practice Exercises

**Exercise 1.** Why is `RecordingFile.readAllEvents(Path)` unsuitable for counting one event type in a multi-GB JFR file?

*Answer:* It returns all events as a list on the heap, risking massive RAM usage. For counting, simply stream with `hasMoreEvents`/`readEvent` and increment a `long` counter.

**Exercise 2.** You observe `event.hasField("path") == true` yet `event.getString("path")` returns `null`. Do these two results contradict each other?

*Answer:* No. `hasField` confirms the schema defines the field; the field's value can still be `null`.

**Exercise 3.** Can you call `event.getDuration("duration")` to read every event's duration instead of `event.getDuration()`?

*Answer:* You should not. No-arg `getDuration()` is the API for the event's own duration. The field-named overload reads a **timespan field** in the schema; never assume that field name exists on every type.

**Exercise 4.** To extract bytes read from `jdk.FileRead`, can you always call `getLong("bytes")`?

*Answer:* No. You must inspect the schema of your target JDK to learn the exact field name and type (which may be `bytesRead` or another name), then use the matching getter; our example only guarantees `bytes` on the custom `demo.Request` event.

**Exercise 5.** After a file was recorded with `stackTrace=false`, can you raise `jfr print --stack-depth=100` to see call stacks?

*Answer:* No. The tool can only display data already recorded; you must capture a new recording with stack traces enabled for the relevant events.

**Exercise 6.** `readEventTypes()` lists `jdk.JavaMonitorEnter`, yet the reading loop sees zero instances. Is the code broken?

*Answer:* Not necessarily. Metadata can exist even when 0 events occurred or passed filters; check `jfr summary`, enabled/threshold settings, recording window, workload, and type filters.

**Exercise 7.** Two events lasted 30 ms and 40 ms on two threads at the same time. Can you say the application paused for 70 ms?

*Answer:* No. Durations can overlap, and two events do not automatically indicate a global stop-the-world pause. Understand the semantics of each type and the timeline.

## 14. Checklist When Building a JFR Reader Tool

- [ ] Accept only valid `.jfr` files from trusted sources/paths; use `try-with-resources`.
- [ ] Call `hasMoreEvents()` before `readEvent()`; handle `IOException`/`EOFException`.
- [ ] Filter by **event type name**, never confusing display labels or parser Java class names.
- [ ] Use `hasField` and `getFields()`/`ValueDescriptor` for uncertain fields.
- [ ] Pick the right typed getter; distinguish absent fields, `null` fields, and `0`.
- [ ] Distinguish event `getDuration()` from field `getDuration("field")`; always record units.
- [ ] Handle nullable `RecordedThread` and `RecordedStackTrace`.
- [ ] For large files, stream with bounded aggregates rather than holding all events.
- [ ] Cross-check with `jfr summary`, `jfr metadata`, and `jfr print` when schemas are uncertain.
- [ ] When aggregating, preserve context on JDK, recording, time window, thresholds, sampling, and threads.
- [ ] Protect sensitive data; restrict logs/exports and never treat JFR files as public data.

**Takeaway:** `RecordingFile` yields a stream of `RecordedEvent` instances. To process them accurately, follow the sequence **open file → iterate → identify type → verify schema → read typed fields → aggregate → close file**. A `RecordedEvent` is evidence of **an event that was recorded**; what you can conclude from it still depends on event definitions, JFR configuration, and runtime context.

## Reference Documentation (JDK 21)

- Oracle, [`RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `readEvent`, `hasMoreEvents`, `readEventTypes`, `readAllEvents`, and closing files.
- Oracle, [`RecordedEvent`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): timestamp, duration, thread, stack, and event type.
- Oracle, [`RecordedObject`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `hasField`, typed getters, `getValue`, and nested fields.
- Oracle, [`RecordedThread`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedThread.html): Java/OS thread metadata.
- Oracle, [`RecordedStackTrace`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html) and [`RecordedFrame`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedFrame.html): frames, line numbers, and truncated stacks.
- Oracle, [`ValueDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html): field name, type, and metadata.
- Oracle, [`Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): creating and dumping recordings.
- Oracle, [`jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `metadata`, `print`.
