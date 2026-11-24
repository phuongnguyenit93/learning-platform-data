# 16.4 Name, Label, Category, Description, and Data-Unit Annotations in JFR

## 1. Why Do Custom JFR Events Need Metadata?

In Java Flight Recorder (JFR), a **custom event** is a Java class extending `jdk.jfr.Event`. Class fields describe diagnostic business data: operation code, byte count, queue wait time, cache hit ratio, retry count, etc. When written to a `.jfr` file, tools like the `jfr` CLI or JDK Mission Control (JMC) need to know the **stable event name**, **human-readable label**, **display grouping**, **field meanings**, and **value units**.

Annotations in the `jdk.jfr` package solve this:

- `@Name`: machine-readable identifier usable in event settings, queries, and recording readers.
- `@Label`: human-friendly display name for an event, field, or setting.
- `@Category`: hierarchical grouping path for events in analysis tools.
- `@Description`: semantic documentation so others interpret the data accurately.
- `@Timespan`, `@Timestamp`, `@DataAmount`, `@Percentage`, and other content-type annotations: **metadata describing field units/interpretation**.

**Key point:** metadata **does not perform measurements, alter Java values, enable recordings, or convert units automatically**. Developers must still assign values in the right units, use `begin()/end()/commit()` or `Recording` properly, and ensure JFR configuration collects the event. Metadata makes recorded files **readable and gives them a clear contract**.

This lesson uses the standard **JDK 17+** API from the `jdk.jfr` module; examples also use standard JDK packages like `java.time` and `java.nio.file`, with no external libraries required.

## 2. Distinguishing the Four Core Descriptive Annotations

| Annotation | Typical targets | Answers the question | Example | Is it a stable identifier? |
| --- | --- | --- | --- | --- |
| `@Name` | Event class, field, setting | "What do machines/APIs call it?" | `@Name("com.example.checkout.Attempt")` | **Yes**, especially for event names |
| `@Label` | Event class, field, setting | "What label does an analyst see?" | `@Label("Checkout Attempt")` | **No**; it is a display label |
| `@Category` | **Event class** | "Which group/lane does the event belong to?" | `@Category({"Application", "Checkout"})` | **No**; it is a presentation path |
| `@Description` | Event class, field, setting | "What does this value or event mean?" | `@Description("One checkout attempt")` | **No**; it is semantic documentation |

Class metadata-only example, without event recording logic yet:

```java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.checkout.Attempt")
@Label("Checkout Attempt")
@Category({"Application", "Checkout"})
@Description("One checkout attempt, including queue wait and payload size")
public class CheckoutAttempt extends Event {
}
```

The snippet above is a class example; if used as a `public` class directly, save it in `CheckoutAttempt.java`. It defines event metadata, but **does not create an event instance or a recording yet**. A complete, standalone, runnable example is in section 6.

### Three layers of information to keep separate

1. **Schema/identity:** `@Name` determines the event/field name in JFR metadata, allowing exact event selection by name.
2. **Presentation/documentation:** `@Label`, `@Category`, and `@Description` help with display, grouping, and comprehension; changing labels/categories does not necessarily change the schema.
3. **Value semantics:** `@Timespan`, `@DataAmount`, etc., state how to interpret **recorded numeric values**; annotations do not perform calculations or type conversions.

## 3. `@Name`: The Identifier Must Be Stable

`@Name` can be placed on event classes and supported fields/settings. For an **event class**, the name must be a valid name per Java identifier rules, typically using reverse-domain namespacing:

```java
@Name("com.example.checkout.Attempt")
```

If `@Name` is omitted, JFR uses the **fully qualified Java class name** as the event name. That is convenient for experiments, yet fragile during package/class refactoring: for example, moving `com.example.CheckoutEvent` to `com.example.events.CheckoutEvent` changes the default event name. In production applications, assign explicit event names and keep them stable.

For a **field** or setting, the `@Name` value must be a valid Java identifier, such as `payloadBytes`; do not use spaces like `"Payload Bytes"`. According to the Javadoc, if a `@Name` value is invalid, the annotation is ignored. **Do not rely on silent ignoring**; verify the actual metadata via `EventType.getName()`, `ValueDescriptor.getName()`, and `jfr metadata`.

Design rules:

- Use a concise, organization-namespaced, sufficiently distinct stable name: `com.example.checkout.Attempt`.
- Do not use `@Label("...")` as an event lookup key; editors may change labels while the event name remains constant.
- Do not arbitrarily rename an event's `@Name` when dashboards, `.jfc` files, `jfr print --events`, parsers, or alerts reference it.
- Avoid colliding with the built-in `jdk.*` namespace and avoid reusing the same name for two semantically different events.
- Avoid embedding display labels, environments, release versions, or dynamic business values into event names; store those as fields if needed.

Example of **changing labels without changing identity**:

```java
@Name("com.example.checkout.Attempt")
@Label("Payment Attempt")
@Category({"Application", "Payments"})
```

In this example, the event name remains `com.example.checkout.Attempt`; tools filtering by that name can still find the event. Labels and categories only change UI presentation.

## 4. `@Label`, `@Description`, `@Category`: Optimizing the Analysis Experience

### `@Label`

`@Label` provides a human-readable name, such as `@Label("Payload Size")` or `@Label("Queue Wait")`. It is used as a label by JMC and metadata-aware tools, and can be read via `EventType.getLabel()` or `ValueDescriptor.getLabel()`.

Labels should be concise, specific, consistent, and without trailing punctuation. **Do not use labels as stable identifiers**. For example, the Java field `queueWaitMs` can have the label `Queue Wait`; users see the friendly name in the UI, while code reading fields still uses the key `queueWaitMs`.

### `@Description`

Use one or two sentences to explain **when it is measured, scope, source, and meaning**. Example:

```java
@Label("Queue Wait")
@Description("Time spent waiting in the work queue before processing")
@Timespan(Timespan.MILLISECONDS)
public long queueWaitMs;
```

`@Description` clarifies that the duration covers time from entering the queue until processing begins, not the entire HTTP request. The most helpful descriptions **prevent misinterpretation**; avoid merely repeating the field name like "Queue wait duration". In particular, clarify whether measurement is server-side or client-side, whether network/queue/retry time is included, whether values can be negative/missing, and which clock source is used.

### `@Category`

`@Category({"Application", "Checkout"})` declares a **hierarchical path**: root `Application` → branch `Checkout`. Array elements are **not two independent tags**. Events sharing a path are typically grouped together in JMC's tree or timeline; category paths can be adjusted for organizational clarity without renaming the event itself.

`@Category` applies to **event types**, not fields. For events that overlap in time on a timeline, splitting categories sensibly helps tools display them in distinct lanes. Avoid excessively deep categories; `Application / Checkout` is much clearer than `Application / System / Runtime / Services / Payment / Checkout / Attempts` unless your organization truly needs that depth.

## 5. Annotations Describing Units and Value Semantics

These annotations are also called **content-type annotations**; they provide **interpretation/formatting hints** to JFR readers. In Java, the field keeps its underlying type (`long`, `int`, `double`, `boolean`, etc.).

| Annotation | Meaning and unit | Example value | Correct interpretation |
| --- | --- | --- | --- |
| `@Timespan(Timespan.MILLISECONDS)` | **Time duration** in milliseconds | `15L` | 15 ms, not a timestamp |
| `@Timespan(Timespan.NANOSECONDS)` | Time duration in nanoseconds | `1_500_000L` | 1.5 ms if converted |
| `@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)` | **Point in time** in milliseconds since Unix epoch | `System.currentTimeMillis()` | Wall-clock timestamp, not a duration |
| `@DataAmount(DataAmount.BYTES)` | Data quantity in bytes | `2048L` | 2048 bytes |
| `@DataAmount(DataAmount.BITS)` | Data quantity in bits | `16L` | 16 bits |
| `@Percentage` | Ratio as a **fraction**, typically `0.0–1.0` | `0.75` | Displayed as 75%, not 0.75% |
| `@Frequency` | Frequency in Hz | `60L` | 60 times/sec if field semantics match |
| `@MemoryAddress` | Memory address so tools format it as an address | `long` value | Not a buffer size |
| `@Unsigned` | Hint to interpret integer as unsigned | Integer value | Does not change signed Java integer semantics |
| `@BooleanFlag` | True/false flag for UI/metadata | `true` | Does not turn an arbitrary number into a boolean |

Official unit constants include `Timespan.NANOSECONDS`, `MICROSECONDS`, `MILLISECONDS`, `SECONDS`, `TICKS`; `DataAmount.BYTES`/`BITS`; `Timestamp.MILLISECONDS_SINCE_EPOCH` and `TICKS`. Without arguments, `@Timespan` defaults to **nanoseconds**, `@DataAmount` defaults to **bytes**, and `@Timestamp` defaults to **milliseconds since epoch**. Writing units explicitly in application code reduces confusion.

**Two major traps:**

1. Putting `@Timespan(Timespan.MILLISECONDS)` on a value derived from `System.nanoTime()` without converting units → tools interpret 1,000,000 nanoseconds as **1,000,000 milliseconds**, off by a factor of one million. Use `TimeUnit.NANOSECONDS.toMillis(...)` or change the annotation to `NANOSECONDS`.
2. Putting `@Percentage` on `75.0` when the contract expects the fraction `0.75` → the UI may interpret it as 7,500%. The annotation **does not divide by 100 automatically**.

Similarly, `@Timestamp(MILLISECONDS_SINCE_EPOCH)` must not be populated directly with `System.nanoTime()`, because `nanoTime()` is a monotonic clock with an arbitrary origin, **not** the Unix epoch. For timestamps, use `System.currentTimeMillis()`; for durations, subtract two `System.nanoTime()` readings and apply `@Timespan` with the matching unit.

**Additional note:** `@BooleanFlag`, `@Frequency`, `@MemoryAddress`, and `@Unsigned` are helpful when the field genuinely carries that meaning; do not attach them arbitrarily just to decorate reports. `@DataAmount` only indicates a quantity of data—it does not specify whether it is a request payload, heap memory, or network transfer; `@Description` must clarify that.

## 6. Complete Runnable Java 17+ Example: Event with Metadata and JFR File

Save as **`JfrMetadataDemo.java`**. This is **a single standalone Java file** with no framework or external config dependencies. The event class is nested inside the main class so it compiles with one `javac` command.

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Percentage;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;
import jdk.jfr.Timestamp;
import jdk.jfr.ValueDescriptor;

public class JfrMetadataDemo {

    @Name("com.example.checkout.Attempt")
    @Label("Checkout Attempt")
    @Category({"Application", "Checkout"})
    @Description("A checkout attempt with payload and queue wait")
    public static final class CheckoutAttempt extends Event {

        @Label("Order ID")
        @Description("Opaque identifier of the order")
        public String orderId;

        @Label("Payload Size")
        @Description("Number of bytes in the request payload")
        @DataAmount(DataAmount.BYTES)
        public long payloadBytes;

        @Label("Queue Wait")
        @Description("Time spent waiting before execution")
        @Timespan(Timespan.MILLISECONDS)
        public long queueWaitMs;

        @Label("Cache Hit Fraction")
        @Description("Fraction of operations served from cache")
        @Percentage
        public double cacheHitFraction;

        @Label("Requested At")
        @Description("Wall-clock time at the start of the attempt")
        @Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
        public long requestedAtMillis;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("checkout-attempt.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(CheckoutAttempt.class)
                     .withThreshold(Duration.ZERO);
            recording.start();

            CheckoutAttempt event = new CheckoutAttempt();
            event.orderId = "sample-001";
            event.payloadBytes = 2048L;
            event.queueWaitMs = 12L;
            event.cacheHitFraction = 0.75;
            event.requestedAtMillis = System.currentTimeMillis();

            event.begin();
            event.end();
            event.commit();

            recording.stop();
            recording.dump(output);
        }

        EventType type = EventType.getEventType(CheckoutAttempt.class);
        System.out.println("name=" + type.getName());
        System.out.println("label=" + type.getLabel());
        System.out.println("category=" +
                String.join(" / ", type.getCategoryNames()));

        for (String fieldName : List.of(
                "payloadBytes", "queueWaitMs",
                "cacheHitFraction", "requestedAtMillis")) {
            ValueDescriptor field = type.getField(fieldName);
            System.out.println(fieldName + "=" + field.getContentType());
        }

        System.out.println("file=" + output.getFileName());
    }
}
```

Compile and run with JDK 17 or later, with file write permissions in the working directory:

```bash
javac --release 17 JfrMetadataDemo.java
java JfrMetadataDemo
```

**Stdout lines printed by the program itself, in order:**

```text
name=com.example.checkout.Attempt
label=Checkout Attempt
category=Application / Checkout
payloadBytes=jdk.jfr.DataAmount
queueWaitMs=jdk.jfr.Timespan
cacheHitFraction=jdk.jfr.Percentage
requestedAtMillis=jdk.jfr.Timestamp
file=checkout-attempt.jfr
```

Note: other JVM tool output (if logging is configured) may include separate messages; the block above is produced by the application's `System.out.println` calls. The actual timestamp value changes at runtime **but is not printed**, so the stdout above is deterministic. `checkout-attempt.jfr` is written to the process working directory. If the environment restricts file writes, choose a writable directory before running.

### Step-by-step explanation of the mechanism

1. `recording.enable(CheckoutAttempt.class)` enables the custom event in **the recording created by the program**. `withThreshold(Duration.ZERO)` allows recording even very short events; if the threshold exceeds the event duration, the recording may discard it.
2. `recording.start()` begins collection. Creating a `CheckoutAttempt` instance and assigning fields behaves like regular Java fields. Annotations do not automatically pull values from HTTP requests, queues, or caches.
3. `event.begin()`/`event.end()` record the **event's** start/end timestamps in standard metadata; `event.commit()` submits the event to the recorder if enabled and matching settings. `queueWaitMs=12` is a **manually assigned example value** for the queue wait field, not the duration measured by JFR between `begin` and `end`.
4. `recording.stop()` stops collection; `recording.dump(output)` exports to `.jfr`. `try-with-resources` closes the `Recording` resource.
5. `EventType.getEventType(...)` reads the event type's metadata; `getName()`/`getLabel()`/`getCategoryNames()` return class-level metadata. `getField("queueWaitMs")` returns a `ValueDescriptor`; `getContentType()` reflects the unit annotation, such as the string `jdk.jfr.Timespan`.
6. Values such as `payloadBytes=2048` and `cacheHitFraction=0.75` are still stored as raw numbers; JFR tools can format them as bytes/percentages using metadata.

The consecutive `event.begin(); event.end();` creates a very short event, so we set the threshold to `Duration.ZERO`. When real code has an operation to measure, put `begin()` **before** and `end()` **after** the work so event duration carries business meaning. If extra field data is costly, use `event.isEnabled()`/`event.shouldCommit()` and selective collection to limit overhead.

## 7. Inspecting File Metadata with the `jfr` CLI

After running the example, verify that the `.jfr` file actually contains the event and schema:

```bash
jfr summary checkout-attempt.jfr
jfr metadata --events com.example.checkout.Attempt checkout-attempt.jfr
jfr print --events com.example.checkout.Attempt checkout-attempt.jfr
```

- `jfr summary` verifies the file is readable, which event types exist in the recording, and event counts.
- `jfr metadata --events ...` reads the **schema/metadata** of the selected event: name, label, description, category, fields, and units.
- `jfr print --events ...` reads **actual recorded instances**. Formatting may vary by `jfr` tool version and differ from the JMC GUI, though values come from the raw fields.

The filter name is `com.example.checkout.Attempt` from `@Name`, **not** `Checkout Attempt` from `@Label`, and **not** the Java class name `JfrMetadataDemo.CheckoutAttempt`. `@Category` aids grouping in JMC; to select events in the CLI, use the event name.

When an event is not found, check **whether the recording enabled the right event type**, threshold/enable settings, when `commit()` ran, whether you are reading the intended file, and the `--events` filter. Metadata can appear in a file when the event type is known even if the actual instance count is 0 (for example, filtered out by threshold).

## 8. Reading Metadata Directly via the API

You do not need to parse `jfr print` text to discover what a field means. The JDK provides metadata classes:

```java
EventType type = EventType.getEventType(CheckoutAttempt.class);
String name = type.getName();
String label = type.getLabel();
String description = type.getDescription();
List<String> categories = type.getCategoryNames();

ValueDescriptor field = type.getField("queueWaitMs");
String fieldName = field.getName();
String fieldLabel = field.getLabel();
String fieldDescription = field.getDescription();
String contentType = field.getContentType(); // jdk.jfr.Timespan
```

This is an **illustrative snippet** set in the context of `JfrMetadataDemo` (requiring `import jdk.jfr.*;` and `java.util.List`); if pasted into a completely separate file, you will need a wrapper class and `CheckoutAttempt` definition. These methods enable programmatic inspection independent of JMC's specific UI.

Several useful APIs:

| API | Purpose |
| --- | --- |
| `EventType.getName()` | Retrieves the event identifier with `@Name` applied |
| `EventType.getLabel()` | Retrieves the human-readable label |
| `EventType.getDescription()` | Retrieves the description |
| `EventType.getCategoryNames()` | Retrieves the category hierarchy from root to leaf |
| `EventType.getFields()` / `getField(name)` | Retrieves the list or a single field descriptor |
| `ValueDescriptor.getName()` / `getLabel()` / `getDescription()` | Retrieves field identifier and textual metadata |
| `ValueDescriptor.getContentType()` | Retrieves the content-type name for tool formatting/interpretation |
| `getAnnotationElements()` / `getAnnotation(...)` | Retrieves annotations included in JFR metadata |

For example, `ValueDescriptor.getContentType()` returns `"jdk.jfr.Percentage"` for a `@Percentage` field. If no content-type annotation is present, the method may return `null`. For custom units, inspect `getAnnotationElements()` or the corresponding annotations rather than guessing from the numeric type.

**Important:** `getContentType()` does not directly return granular units like "MILLISECONDS"; to determine the exact unit of `@Timespan`, inspect the `@Timespan` annotation/value in metadata. Two fields with the same `jdk.jfr.Timespan` content type can have **different** units if one uses `MILLISECONDS` and the other uses `NANOSECONDS`.

## 9. When to Use `@Name` at the Field Level?

Normally, JFR derives the field name from the Java identifier:

```java
@Label("Payload Size")
@DataAmount(DataAmount.BYTES)
public long payloadBytes;
```

The JFR field name is `payloadBytes`. If you need to keep the schema stable while refactoring Java code, you can declare it explicitly:

```java
@Name("payloadBytes")
@Label("Payload Size")
@DataAmount(DataAmount.BYTES)
public long requestBodySize;
```

In the second example, the Java variable name is `requestBodySize` while the **JFR metadata name** is explicitly `payloadBytes`. This preserves field identity without forcing you to keep an outdated Java variable name. Do not overuse this, as diverging code and schema names require extra documentation and testing. Field names must be valid identifiers, not phrases with spaces.

If you change a field's meaning from "request body bytes" to "response compressed bytes", **do not keep the same `@Name` pretending the schema did not change**; that is a breaking semantic change. Introduce a new field or a new event name/version when contract changes could mislead downstream consumers.

## 10. Distinguishing Timestamp, Timespan, and Built-in Event Duration

In JFR, three time-related concepts are often confused:

| Data | Source | Meaning |
| --- | --- | --- |
| Event `startTime` | JFR on `begin()/commit()` | Start timestamp of the event |
| Event `duration` | JFR measured between `begin()` and `end()` (or instant duration if unmeasured) | Time span covered by the event |
| Custom field `queueWaitMs` | Explicitly computed/assigned by the app | Time spent specifically in the queue, which may differ from event duration |
| Custom field `requestedAtMillis` | `System.currentTimeMillis()` in the example | Wall-clock time in Unix epoch milliseconds |

Practical example of measuring queue wait:

```java
long enqueueNanos = System.nanoTime();
// ... work is placed into the queue, then dequeued ...
long waitNanos = System.nanoTime() - enqueueNanos;
event.queueWaitMs = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(waitNanos);
```

This is an **illustrative snippet** that must be invoked at the two corresponding business milestones. Because `toMillis` is used, the field annotation must be `@Timespan(Timespan.MILLISECONDS)`. If you want higher resolution and want to avoid rounding short queue waits, store `waitNanos` in a field annotated with `@Timespan(Timespan.NANOSECONDS)`.

**Never apply `@Timestamp` to a time difference**, and never apply `@Timespan` to a point in time like "2026-10-29 17:00". Even though both are `long`, their interpretations are completely different.

## 11. Scenarios for Choosing the Right Unit Annotation

### A. Tracking HTTP/request size

```java
@Label("Request Size")
@Description("Uncompressed request body size in bytes")
@DataAmount(DataAmount.BYTES)
public long requestBytes;
```

If analyzing payload size before vs. after decompression matters, state it explicitly. `@DataAmount` does not distinguish network bytes, buffer bytes, or retained memory.

### B. Tracking cache hit ratio

```java
@Label("Cache Hit Ratio")
@Percentage
public double hitFraction; // Example: 0.875 means 87.5%
```

If a metric source returns `87.5` in "percentage points", convert it to `0.875` **before assigning**. The annotation does not rescale values.

### C. Tracking DB pool wait time

```java
@Label("Connection Wait")
@Description("Time waited for a database pool connection")
@Timespan(Timespan.MILLISECONDS)
public long acquireMillis;
```

This differs from the `Event.duration` of the whole request. If the DB pool fails to issue a connection and the request fails, clearly document any sentinel or missing-value convention.

### D. Tracking frequency and timestamps

```java
@Label("Retry Rate")
@Frequency
public long retriesPerSecond;

@Label("Observed At")
@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
public long observedAtMillis;
```

`@Frequency` means Hz, not "how many retries since service startup". `@Timestamp` requires proper epoch milliseconds, not `System.nanoTime()`.

### E. Tracking bits, addresses, or unsigned values

Use `@DataAmount(DataAmount.BITS)` when the metric is genuinely in bits. `@MemoryAddress` is meaningful for native address fields, not sizes. `@Unsigned` supplies unsigned interpretation metadata for integer fields, but **does not alter Java's signed integer operator semantics**. Only include native addresses or sensitive data in JFR when serving a concrete diagnostic need.

## 12. Annotations Do Not Change Event Lifecycle

Clean metadata does not guarantee events will appear in a recording. For a custom event to show up in `.jfr`, you generally need to:

1. **Define** a class `extends Event` with supported fields.
2. **Enable** the event type in the active configuration: `Recording.enable(YourEvent.class)`, or configure the matching JFR event name via startup flags/`jcmd`/`.jfc` file.
3. **Assign fields** and measure duration if applicable.
4. **Commit** with `event.commit()`; JFR may still drop it if no recording is active, the event is disabled, or threshold/filters are not met.
5. **Dump/stop the recording** to produce an analysis file, e.g., `recording.dump(Path.of("..."))`.

`@Label` or `@Category` **do not enable events**, `@Description` **does not log anything**, and `@Timespan` **does not measure time**. `@Enabled`, `@Threshold`, and `@StackTrace` relate to default event settings; those belong to a different group of behavior-configuring annotations. Which event type a recording enables by name depends on `@Name`/event type, **not on label or category**.

If payload construction is expensive (serializing objects, capturing extra stacks, concatenating large strings, etc.), use `event.isEnabled()` or `event.shouldCommit()` to avoid unnecessary work. `shouldCommit()` evaluates current settings and event state; when using a duration threshold, call it after duration is measured rather than before timing completes.

## 13. Common Mistakes When Designing JFR Schemas

| Mistake | Consequence | Correct practice |
| --- | --- | --- |
| Using `@Label` as the filter name in `jfr print --events` | Event type not found | Use `@Name`, e.g., `com.example.checkout.Attempt`. |
| Omitting `@Name` in production | Refactoring Java class/package changes event name | Use a namespaced, stable name and regression tests. |
| Treating `@Category({"App", "Checkout"})` as two independent tags | Event grouped unexpectedly | Understand it as a **hierarchical path** root → branch. |
| Changing `@Name` just to update display text | Breaks dashboards/parsers/`.jfc` referencing old event name | Change `@Label`/`@Category` for presentation-only updates. |
| `@Percentage` on value `75` | GUI may interpret as 7500% | Store `0.75` for 75%. |
| `@Timespan(MILLISECONDS)` on nanoseconds | Duration displays off by a million times | Convert units when assigning or fix the annotation. |
| `@Timestamp` on `System.nanoTime()` | Meaningless epoch timestamp | Use epoch millis for timestamps, `nanoTime` for durations. |
| Changing units while keeping the same field name | Data across versions gets misread together | Preserve contract or introduce a new field/schema version. |
| Adding `@Label`/`@Description` without `commit` | No events collected | Verify enabling, threshold, recording, and commit. |
| Looking only at `long` type and ignoring annotations | Unclear whether value is bytes, ms, or epoch | Inspect `ValueDescriptor.getContentType()` and annotation values. |
| Fields holding arbitrary complex/sensitive objects | Invalid, unhelpful, higher overhead, or data leaks | Pick valid primitive/String/Thread/Class types, shrink payloads, and enforce data policies. |
| Seeing raw numbers in `jfr print` and assuming annotations are broken | CLI formatting differs from GUI or varies by JDK tool | Use `jfr metadata` and JMC to verify underlying metadata. |

Specifically, **event names and field names are part of a data contract**. If multiple services or versions emit the same name with differently defined fields, an aggregated report may be "syntactically valid" yet analytically wrong. Document schemas and test compatibility whenever changing meanings, types, or units.

## 14. Testing Metadata Meaningfully, Not Just Checking File Existence

A solid test verifies both **metadata** and **actual recorded events**. For the example in section 6:

- `EventType.getName()` must be `com.example.checkout.Attempt`.
- `EventType.getLabel()` is `Checkout Attempt`, category is `Application / Checkout`.
- `ValueDescriptor.getContentType()` for `payloadBytes` is `jdk.jfr.DataAmount`; `queueWaitMs` is `jdk.jfr.Timespan`; `cacheHitFraction` is `jdk.jfr.Percentage`; `requestedAtMillis` is `jdk.jfr.Timestamp`.
- `@Timespan` metadata actually carries `MILLISECONDS` and `@DataAmount` carries `BYTES`; do not check only the generic content-type string.
- `jfr summary` shows the event present; `jfr print` shows `orderId="sample-001"`, `payloadBytes=2048`, `cacheHitFraction=0.75` per the raw value contract.
- When refactoring the Java class/package while keeping `@Name`, the event name stays unchanged; when changing only `@Label`/`@Category`, parsers reading by `@Name` remain unaffected.
- When changing data units, tests must catch mismatches between **actual values** and **annotations** (e.g., 1,500,000 ns corresponding to 1.5 ms).

For automated tests, do not rely solely on Java `assert` statements and forget `-ea`; use JUnit assertions or explicit checks like `if (...) throw new AssertionError(...)`. A test that only checks a field has `@Timespan` without verifying ns → ms conversion will miss the most critical bug.

## 15. Checklist When Adding Custom Events to an Application

- [ ] `@Name` uses the application's namespace, follows Java syntax, and is long-term stable.
- [ ] `@Label` is concise and clear; `@Description` states units, source, scope, and measurement timing.
- [ ] `@Category` reflects event grouping in JMC; category is never used as a substitute for identity.
- [ ] Field names, data types, semantics, and units are documented as a contract and tested.
- [ ] `@Timespan` is used for **durations**, `@Timestamp` for **timestamps**, `@DataAmount` for bytes/bits, `@Percentage` for 0–1 ratios.
- [ ] Any data originating from `System.nanoTime()` is converted to the right unit before assignment.
- [ ] Optional annotations like `Frequency`/`MemoryAddress`/`Unsigned` are attached only when semantically accurate.
- [ ] Event is enabled in the recording, calls `commit()`, uses an appropriate threshold, and has a `.jfr` file verified.
- [ ] `jfr metadata`, `jfr summary`, and `jfr print` or JMC are used to verify both schema and data.
- [ ] Class refactoring, label updates, and unit changes are evaluated for impact on parsers, dashboards, JFR config files, and docs.
- [ ] No personally identifiable information, tokens, secrets, large payloads, or sensitive objects are recorded unnecessarily.
- [ ] Custom event overhead has been measured at realistic frequencies, and string field cardinality/size are bounded.

## 16. Official API Sources

The following links reference **Java SE 26** Javadoc (the core APIs used in these examples have been present since JDK 17) to directly inspect contracts and annotation values:

1. Package `jdk.jfr` — guide to defining custom events and event metadata: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html
2. `@Name` — valid and stable identifier rules: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Name.html
3. `@Label` — user-facing label: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Label.html
4. `@Category` — event grouping path: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Category.html
5. `@Description` — semantic documentation: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Description.html
6. `@Timespan` — unit constants for nanos, micros, millis, seconds, and ticks: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Timespan.html
7. `@Timestamp` — epoch millis or ticks: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Timestamp.html
8. `@DataAmount` — bytes and bits: https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/DataAmount.html
9. `@Percentage` — fractional percentage values: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Percentage.html
10. `EventType` and `ValueDescriptor` — reading metadata via API: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventType.html and https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/ValueDescriptor.html
11. `Event` and `Recording` — JFR recording lifecycle: https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html and https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html

**Final principle:** use `@Name` for **identity**, `@Label`/`@Category`/`@Description` for **human understanding**, and content-type annotations to define **data units/semantics**. A useful event must get all three layers right; if metadata and actual values contradict each other, the JFR file may still be readable, yet diagnostic conclusions will be wrong.
