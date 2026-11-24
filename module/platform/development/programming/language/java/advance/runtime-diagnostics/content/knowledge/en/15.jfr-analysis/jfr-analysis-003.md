# 15.3. Using `jfr print` with event, category, stack depth filters, and JSON or XML output

## Lesson objectives

**Java Flight Recorder (JFR)** records JVM and application events into a binary `.jfr` file. The **`jfr print`** command-line tool in the JDK reads a saved file, prints events in human-readable text, or converts them to JSON/XML for automated processing. Filtering by **event type**, **category**, and the number of displayed **stack frames** lets you focus on the signals under investigation instead of reading the entire recording.

After this lesson, you will know how to:

1. Inspect a recording with `jfr summary` and `jfr metadata` to find the actual event and category names.
2. Filter using `--events`, `--categories`, comma-separated name lists, and globs.
3. Understand the **OR/union rule** when combining name and category filters simultaneously.
4. Use `--stack-depth` without confusing display truncation with stack trace collection.
5. Output `--json` or `--xml` for pipelines while verifying encoding and empty results.
6. Create a small recording with Java 17+ and practice on predictable events.

The commands below apply to **JDK 17+**; exact event types, categories, and output fields depend on the JDK, recording settings, and workload. The `print` syntax focuses on capabilities available in JDK 17.

## 1. From a Java recording to the `jfr print` command

```text
Java process / JVM
     |
     | JFR recording: event settings, sampling, thresholds, stack traces
     v
recording.jfr  (binary file)
     |
     +-- jfr summary    -> event type list, count, size
     +-- jfr metadata   -> type definitions, categories, and fields
     +-- jfr print      -> individual event instances matching filters
             |
             +-- default: human-readable text
             +-- --json: machine-readable
             +-- --xml:  machine-readable
```

An **event type** (for example `jdk.GarbageCollection`) is the kind of event; an **event instance** is a single recorded occurrence with a timestamp and fields. A **category** is metadata classifying types and can cover multiple different types. A stack trace is an optional field depending on the event/settings; not every event has a stack.

`jfr print` only **reads** previously recorded data. It does not start a recording, does not modify the `.jfr` file, does not replay application operations, and does not reconstruct events dropped by thresholds or sampling. If you need a fresh recording from a running JVM, use `jcmd ... JFR.start` or an equivalent JFR recording mechanism.

## 2. Standard JDK 17 `jfr print` syntax

```text
jfr print [--xml|--json]
          [--categories <filters>]
          [--events <filters>]
          [--stack-depth <depth>]
          <file>
```

| Option | Effect | Key points |
| --- | --- | --- |
| `<file>` | Path to the `.jfr` recording file | File must exist and contain valid JFR data. |
| `--events <filters>` | Select events by **type name** | Simple/qualified names, comma-separated names, or quoted globs. |
| `--categories <filters>` | Select events by **category name** | Categories differ from type names; check `jfr metadata`. |
| `--stack-depth <depth>` | Limit the number of stack trace frames **printed** | Default is **5**; does not recover unrecorded frames. |
| `--json` | Print JSON | An alternative to human-readable text and XML. |
| `--xml` | Print XML | Cannot be combined with `--json` in one command. |
| Neither `--json`/`--xml` | Print human-readable text | Good for direct inspection in a terminal. |

Check directly from the JDK you are running:

```bash
jfr --help print
```

**Important:** `jfr print` only filters **what is already in the file**. It does not filter by arbitrary field values such as `duration > 100 ms`. To filter by field values, export JSON/XML and post-process it, or use a JFR analysis API.

## 3. Preparing a file and identifying useful filters

If you already have `recording.jfr`, inspect it with:

```bash
jfr summary recording.jfr
jfr metadata recording.jfr
```

- **`summary`** summarizes instance counts by event type and data sizes. If a type has no instances, `jfr print --events ...` has nothing matching to print.
- **`metadata`** displays type names, categories, and field structures of events in the recording. It helps avoid typos, case mismatches, or guessing categories.
- **Presence in metadata does not guarantee instances exist.** Cross-check `summary` or `print` to know whether the recording captured events of that type.

To create a diagnostic recording from a running Java process, with illustrative PID `12345`:

```bash
jcmd 12345 JFR.start name=diag settings=profile duration=30s filename=diag.jfr
```

This command requests a 30-second recording. The file `diag.jfr` can only be used with `jfr print` **after the recording finishes and the file actually exists**. `settings=profile` does not guarantee all events are recorded: it depends on configuration, load, thresholds, and timing. The recording path belongs to the target JVM's environment; inside a container, verify the path and read permissions accordingly. The PID is also just an example.

## 4. Filtering by event name with `--events`

### 4.1. Selecting a single event type

```bash
jfr print --events "jdk.GarbageCollection" diag.jfr
```

This command prints only instances whose type name matches `jdk.GarbageCollection`. This is the **event name**, not a Java class name called in a stack trace, and not a field value.

Another example:

```bash
jfr print --events "jdk.CPULoad" diag.jfr
```

If the recording has no `jdk.CPULoad` instances, output may be empty. Do not conclude CPU was always 0 from an empty filter result; check `summary`, settings, and the time window.

### 4.2. Multiple events in one filter

```bash
jfr print --events "jdk.GarbageCollection,jdk.CPULoad" diag.jfr
```

Commas separate type names. This selects instances **belonging to any of the listed types**. Using fully qualified event names like `jdk.XXX` keeps filters explicit and avoids ambiguity with custom events that share a short name.

### 4.3. Wildcard/glob

```bash
jfr print --events "jdk.GC*" diag.jfr
jfr print --events "jdk.*" --stack-depth 10 diag.jfr
```

The pattern `jdk.GC*` selects type names matching the glob starting with `jdk.GC` if the file contains those types; `jdk.*` is much broader. **Globs are not Java regular expressions**. Use quotes to prevent the shell (Bash, zsh, PowerShell) from expanding `*` before passing it to `jfr`.

Name/glob lists are matched against **symbolic event type names** (metadata `@Name`), not free-form text inside stack traces or fields.

## 5. Filtering by category with `--categories`

Standard JDK example:

```bash
jfr print --categories "GC" diag.jfr
```

The command finds events whose category matches `GC`, and **may** print multiple event types. The actual category list is in `jfr metadata diag.jfr`.

You can pass a list of simple names, qualified names, or quoted globs:

```bash
jfr print --categories "GC,JVM,Java*" diag.jfr
```

Categories can be hierarchical or metadata-driven depending on the event type; for accurate results, rely on the recording's actual category names. Do not assume all "GC-related" events carry a single category named `GC` or share the same field structure.

### 5.1. Combining both filters uses OR, not AND

Oracle JDK 17 example:

```bash
jfr print --categories "GC" --events "jdk.CPULoad" diag.jfr
```

The result is:

```text
S = {events in category GC}
    ∪ {events of type jdk.CPULoad}
```

This is a **union**. It is not "only events that are both in category GC **and** of type `jdk.CPULoad`." If you want an AND across multiple criteria, choose a narrower single filter or post-process the exported results with another tool. Do not pass both options expecting them to intersect.

Similarly, `--events "A,B"` means type A **or** type B; `--categories "C,D"` means category C **or** D.

## 6. Limiting frame count with `--stack-depth`

When an event has a stack trace, `jfr print` by default **displays at most 5 frames**. Increase the display limit:

```bash
jfr print --events "jdk.ExecutionSample" --stack-depth 20 diag.jfr
```

Keep in mind:

1. **Recording stage:** the event type must be enabled; to capture stack traces, stack collection must be configured (for instance `stackTrace=true`) and the JVM must actually record frames. There may also be recording-time stack depth/sampling limits.
2. **Printing stage:** `--stack-depth 20` only increases the maximum frames printed from **frames already stored in the file**. It does not expand the captured depth, re-run the application, or attach new stacks to events.
3. **No frames:** the event may not support stacks, stack recording may be disabled, or no stack was captured; trying `--stack-depth 100` will not create new data.
4. **Large values:** output gets longer without necessarily being more useful. Pick a depth sufficient for your investigation hypothesis.

An event does not necessarily capture the full call tree of a request. It reflects where/how the event was recorded. If your goal is analyzing hot methods, sampling frequency, locks, or allocations, choose the appropriate event types and settings at recording time.

## 7. Choosing human-readable text, JSON, or XML

### 7.1. Default text format

```bash
jfr print --events "jdk.CPULoad" diag.jfr
```

This format is convenient for quickly inspecting fields, timestamps, and stacks. Some values are formatted using JFR annotations: for example, ratios may be displayed as `%`. Do not assume text-output units apply identically to every JSON/XML field without checking.

### 7.2. JSON

```bash
jfr print --json --events "jdk.CPULoad" diag.jfr
```

On Bash/sh and Windows Command Prompt, save output:

```bash
jfr print --json --events "jdk.CPULoad" diag.jfr > cpu-events.json
```

JSON is easy to feed into parsers or pipelines, containing event types, field data, and potentially nested objects/stacks/threads/timestamps. **Do not assume every field is always present, or that the schema never changes across JDK versions**. Inspect real output before writing code that accesses nested fields.

Check that the JSON file is syntactically valid (if Python is available):

```bash
python -m json.tool cpu-events.json
```

In **Windows PowerShell 5.1**, the `>` operator may write an encoding other than the UTF-8 expected by many JSON parsers. You can specify the encoding explicitly:

```powershell
jfr print --json --events "jdk.CPULoad" diag.jfr | Out-File -FilePath cpu-events.json -Encoding utf8
```

Depending on the PowerShell version, encoding/BOM behavior may vary; verify with a parser after saving. When exporting JFR containing internal details, control sensitive data in the JSON file before sharing.

### 7.3. XML

```bash
jfr print --xml --events "jdk.GarbageCollection" diag.jfr
jfr print --xml --events "jdk.GarbageCollection" diag.jfr > gc-events.xml
```

XML suits tools that expect a tree, elements/attributes, and an XML parser. Do not use manual string splitting to "parse XML." Verify exact node/field names from actual JDK output.

### 7.4. Do not enable `--json` and `--xml` together

The syntax `[--xml|--json]` means choosing **one format** per invocation. If you need both files, run two independent commands on the same `.jfr` file. The two formats **only change output serialization**; they do not make the recording more detailed, enable extra events, or increase captured stack depth.

For large recordings, printing all events as JSON/XML can generate massive output. Apply `--events`/`--categories` first before saving to a file; verify file size, encoding, timestamps, and field formats.

## 8. Standalone hands-on lab: create a recording with Java 17+

This example creates **two custom events**: a `demo.Operation` type in category `Demo` and a `demo.Checkpoint` type in category `Diagnostics`. This lets you test event filters, category filters, and the OR rule without depending on whether a real app emits GC/CPU events.

Create **`JfrPrintDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class JfrPrintDemo {
    @Name("demo.Operation")
    @Label("Operation")
    @Category({"Demo"})
    public static class Operation extends Event {
        @Label("Action")
        public String action;
    }

    @Name("demo.Checkpoint")
    @Label("Checkpoint")
    @Category({"Diagnostics"})
    public static class Checkpoint extends Event {
        @Label("Sequence")
        public int sequence;
    }

    private static void writeEvents() {
        Operation operation = new Operation();
        operation.action = "checkout";
        operation.begin();
        operation.end();
        operation.commit();

        Checkpoint checkpoint = new Checkpoint();
        checkpoint.sequence = 7;
        checkpoint.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(Operation.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();
            recording.enable(Checkpoint.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();

            recording.start();
            writeEvents();
            recording.stop();
            recording.dump(Path.of("demo.jfr"));
        }
        System.out.println("Created demo.jfr");
    }
}
```

Explanation:

- `@Name` sets the **type name** for `--events` filtering; `@Category` declares the **category** for `--categories`.
- `@Label` is only a display label and does not replace the type name.
- `withThreshold(Duration.ZERO)` sets threshold 0 so very short events are still recorded.
- `withStackTrace()` requests saving stack traces in the recording. This is why adjusting `--stack-depth` later has data to display.
- `Recording.start()`, `stop()`, and `dump()` create the file in the current directory. The program does not trigger GC or generate large amounts of data.

Compile and run:

```bash
javac --release 17 JfrPrintDemo.java
java JfrPrintDemo
```

When run successfully, the stdout emitted by the Java code itself is:

```text
Created demo.jfr
```

The JVM may print other messages in special environments. Timestamps, threads, and stacks in JFR **are not fixed**, so do not fabricate a single fixed output for the `jfr print` commands.

### 8.1. Inspection

```bash
jfr summary demo.jfr
jfr metadata demo.jfr
```

When the recording runs successfully, both custom events have been `commit()`-ted once per type. The file may also contain metadata or system events; what matters is recognizing the two types used in the experiment.

### 8.2. Filter by a single event

```bash
jfr print --events "demo.Operation" demo.jfr
```

The output includes one `demo.Operation` with field `action = checkout` (when the file recorded the event). Timestamps, duration, and stack frames have run-dependent values.

### 8.3. Filter by category

```bash
jfr print --categories "Diagnostics" demo.jfr
```

Of the two custom events, only `demo.Checkpoint` belongs to `Diagnostics`, with field `sequence = 7`.

### 8.4. Combine filters to verify OR directly

```bash
jfr print --events "demo.Operation" --categories "Diagnostics" demo.jfr
```

The result includes **both `demo.Operation` and `demo.Checkpoint`**. Anyone mistaking the two filters for an AND would expect an empty result; the demo file clearly demonstrates the JDK's union behavior.

### 8.5. Stacks and JSON/XML

```bash
jfr print --events "demo.Operation" --stack-depth 12 demo.jfr
jfr print --json --events "demo.Operation" demo.jfr
jfr print --xml --categories "Diagnostics" demo.jfr
```

Use `--stack-depth 12` to see more frames than the default when enough frames were recorded. Use JSON/XML for machine-readable analysis, and only assume field names after inspecting the real file.

## 9. Real-world analysis scenario

When investigating an application experiencing a latency spike:

1. **Verify the recording covers the right time:** record the JDK vendor/version, PID, start/stop times, clock/timezone, and load conditions.
2. **Read `summary`:** which event types are present and with what counts? If absent, check event settings/sampling/thresholds before concluding why they are missing.
3. **Read `metadata`:** find exact type names and category names. If suspecting GC, try `--events "jdk.GarbageCollection"` or the `GC` category present in the file.
4. **Filter narrowly enough:** export relevant events first instead of printing the whole recording. If using both `--events` and `--categories`, remember the result is a union.
5. **Inspect stack traces:** if only a few frames or none appear, revisit the capture configuration rather than trying to fix it with `--stack-depth`.
6. **Export JSON/XML for automation:** normalize timestamps, confirm units/fields and encoding, then join with application logs, request traces, or OS metrics.
7. **Base conclusions on evidence:** a single GC event does not prove a slow request was caused by GC; combine timestamps, durations, workload, and multiple signals.

| Signal | Check next | Do not jump to conclusion |
| --- | --- | --- |
| `jfr print` empty despite suspected heavy GC | `summary`, `metadata`, recording window/settings | "JVM did not run GC." |
| `--categories GC` returns multiple event types | Category scope in metadata | "All of them are one single GC pause." |
| `--events A --categories B` returns both A and B | OR rule in JDK docs | "The filter is broken." |
| `--stack-depth 64` only shows 3 frames | Recorded stack, event settings | "The command will fill in 61 missing frames." |
| JSON fails to parse after redirection | Encoding/BOM, truncated file, or non-JSON output | "JFR format does not support JSON." |
| No `jdk.ExecutionSample` visible | `profile`/`default` config, event enabled, workload | "The application used no CPU." |

## 10. Common mistakes

- **Confusing `jfr print` with `jcmd JFR.start`:** the first reads `.jfr`, the second asks a JVM to start recording.
- **Misspelling event/category names:** check `summary` and `metadata`; event names are distinct from Java method names appearing in stacks.
- **Assuming `--events` plus `--categories` is AND:** JDK 17 docs confirm **OR/union**.
- **Using regex in `--events`:** the syntax supports names, comma-separated lists, and globs; not Java regex by default.
- **Forgetting to quote wildcards:** the shell may expand `*` before `jfr` sees it.
- **Increasing `--stack-depth` expecting new stacks:** `print` does not change event capture.
- **Assuming every event has a stack trace:** false; it depends on event type and settings.
- **Passing both `--json` and `--xml` at once:** the two formats are mutually exclusive.
- **Treating values in human-readable format as raw field values:** JFR applies display annotations for units/percentages; use a parser and understand the underlying field type.
- **Generating huge JSON/XML outputs:** filter first, and avoid committing unnecessary output to logs or repositories.
- **Not checking file encoding after redirection:** easily causes parser errors, especially in older shells/PowerShell.
- **Not verifying events actually exist in the recording:** never turn empty output into a performance conclusion.

## 11. Self-check questions

**Question 1.** You want to print only `jdk.CPULoad` in `diag.jfr`?  
**Answer:** `jfr print --events "jdk.CPULoad" diag.jfr`.

**Question 2.** What does `--categories GC --events jdk.CPULoad` mean?  
**Answer:** Select events belonging to category `GC` **or** of type `jdk.CPULoad`, not requiring both.

**Question 3.** Why does `--stack-depth 50` still print only 4 frames?  
**Answer:** Because the file may only have 4 recorded frames for that event. `print` cannot add missing frames.

**Question 4.** You want machine-readable output in both JSON and XML?  
**Answer:** Run `jfr print` twice on the same file, once with `--json` and once with `--xml`.

**Question 5.** You want only events with `duration` greater than 100 ms; can `--events` do that?  
**Answer:** No; `--events` filters by type name. You need to process fields from JSON/XML or use the JFR consumer API.

**Question 6.** With `demo.jfr` from the hands-on lab, which types does `--events "demo.Operation" --categories "Diagnostics"` select?  
**Answer:** Both `demo.Operation` and `demo.Checkpoint`, demonstrating union behavior.

## References

- [Oracle JDK 17 — The `jfr` Command: `print`, `summary`, `metadata`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle JDK 17 — `jcmd`: `JFR.start`, `JFR.dump`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java SE 17 — `Recording` API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Java SE 17 — `EventSettings` API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Java SE 17 — `Category` API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Category.html)
- [dev.java — The JFR command-line tool](https://dev.java/learn/jvm/jfr/tools/)
