# 16.6 Recording Correlation Codes, Outcomes, and Business Latency with Bounded Data

> **Scope:** Java 17+ and Java Flight Recorder (JFR) via the `jdk.jfr` module. The focus is designing a **custom JFR event** for a business operation: attaching a searchable correlation code, recording success/failure outcomes, measuring the exact business interval, and controlling **data types, size, and emission rate**. Examples use JDK 17+; commands were verified on OpenJDK 24.

## 1. Why Record Business Events in JFR?

Built-in JFR events such as GC, CPU sampling, lock contention, socket I/O, and file I/O show **what the JVM is doing**. However, they rarely answer directly:

- Which **reservation** or **order confirmation** request was slow?
- Did it succeed, fail business validation, time out, or get cancelled?
- Where did the business-layer slowdown start and end?
- How do you link a JFR timestamp to logs or traces of the exact operation without recording full request bodies or personal data?

A custom event lets you record just enough context:

```text
Custom JFR event: demo.BusinessOperation
  startTime       : start timestamp of the measured segment
  duration        : duration of that segment (recorded automatically by JFR)
  correlationCode : internal lookup code containing no personal data
  operation       : business operation name from a fixed list
  outcome         : SUCCESS | FAILED | CANCELLED
  failureCategory : NONE | VALIDATION | DEPENDENCY | TIMEOUT | INTERRUPTED | OTHER
  itemCount       : valid input count, bounded by policy
```

`startTime` and `duration` are managed by JFR's `Event.begin()`/`Event.end()` mechanism. The remaining fields are defined by the application. Rather than "logging as much as possible just in case", identify **the investigative question** and pick a few stable, non-sensitive, low-cost fields.

**Differences from metrics and logs:**

| Signal | Strongest when | Limitations to remember |
| --- | --- | --- |
| **JFR business event** | Correlating a transaction or group of transactions with JVM GC pauses, locks, or I/O; viewing durations on the same JVM timeline | Subject to event settings, thresholds, buffers/retention; may not capture every request |
| **Metrics (counter/histogram)** | Computing throughput, error rate, and p50/p95/p99 latency across all instrumented samples | Typically do not retain per-transaction codes; high-cardinality labels exhaust resources |
| **Structured logs** | Tracing detailed progression for a single code, tracking warnings and business errors | Must restrict personal data; standalone log timestamps often lack full duration |
| **Distributed tracing** | Following a request across services, spans, and the critical path | Requires context propagation, sampling, and collection policies; does not replace in-JVM JFR detail |

Combining JFR + metrics + logs/traces provides verifiable root-cause analysis. JFR is not a mandatory audit store, billing ledger, or 100%-guaranteed transaction capture system.

## 2. Designing the Event Contract Before Writing Code

### 2.1. Event name and stable fields

The event name should have a clear, stable namespace—for instance, `demo.BusinessOperation` in labs and `com.acme.checkout.BusinessOperation` in production. This name is used to configure events, filter with `jfr print`, and analyze in JDK Mission Control (JMC).

| Field | Suitable JFR type | Data convention | Must never include |
| --- | --- | --- | --- |
| `correlationCode` | `String` | System-issued random/opaque code; bounded length, allowed alphabet, and lifecycle | Email, phone number, customer name, login session ID, access token, request content |
| `operation` | `String` | One value from a fixed allowlist, e.g., `reserve`, `checkout`, `refund` | Raw URLs with query strings, dynamic class names, arbitrary user strings |
| `outcome` | `String` | `SUCCESS`, `FAILED`, `CANCELLED`, or an agreed schema | Arbitrary exception messages |
| `failureCategory` | `String` | Low-cardinality error category, e.g., `NONE`, `VALIDATION`, `TIMEOUT`, `DEPENDENCY`, `OTHER` | SQL, full stack traces, HTTP bodies, raw error messages that may contain secrets |
| `itemCount` | `int` | Non-negative count with a clear bound and meaning | Clamped values disguised as exact counts when truncation occurred |
| `startTime`/`duration` | Event system fields | Timing determined by `begin`/`end` | Do not manually attach timestamps from another clock unless needed for cross-checking |

For a custom event class, `jdk.jfr.Event` only records instance fields of type **Java primitive, `String`, `Thread`, or `Class`**. An `enum`, `Map`, `List`, array, DTO object, etc., is **not** automatically serialized as payload; unsupported reference types may be silently ignored without error. Therefore, if the business layer uses `enum Outcome`, convert it to an **allowlisted `String` name** before recording.

`@Name`, `@Label`, `@Category`, and `@Description` help JFR tools recognize schemas and present fields clearly. Renaming or changing field types can break existing queries or dashboards; treat the event schema as a versioned **data contract**.

### 2.2. A correlation code is a join key, not business data

A correlation code bridges signals:

```text
log/service-A  -- correlationCode=c-7f3... --> JFR/service-A
   |                                            |
   +----------- trace/context ------------------+
                      |
                  service-B logs/traces
```

**Sensible ways to generate it:**

1. Generate a server-side random opaque ID at the start of the business flow. If it crosses multiple services, propagate it through controlled channels and keep it consistent.
2. If an approved trace context already exists, use `traceId`/`spanId` with **explicit format and size bounds**; avoid dumping arbitrary tracing baggage into JFR.
3. When only a sensitive business ID exists, **do not record it directly**. Issue a safely mapped internal ID or use a keyed HMAC under an appropriate policy to create a pseudonym when correlation is truly needed. Plain hashes of emails/order IDs are easily guessed from known value sets and do not automatically protect identity.
4. Enforce length limits (e.g., max 64 ASCII characters), format validation, and trusted sources. Regex validation alone cannot guarantee a string lacks personal data if a caller passes an email or token in a matching format.

A high-cardinality code can be acceptable **in bounded-retention JFR events** because it locates an individual transaction; however, **never** put per-request codes into time-series metric labels. Distinct event counts and unique `String` values per event still carry storage, indexing, and analysis costs.

### 2.3. Outcome is the final status of the measured scope

`outcome` must describe **the business segment being measured**, not simply whether a method threw an exception:

- `SUCCESS`: the business step was confirmed complete per its contract.
- `FAILED`: the step failed (due to validation, dependency error, or other reasons).
- `CANCELLED`: the step was cancelled or interrupted with corresponding business semantics.

A method returning HTTP 200 whose business result **declines the transaction** can still be `FAILED` functionally. Conversely, a successful retry may be `SUCCESS` for the **final attempt**, while the overall flow has a different latency. Clearly define whether the event measures **a single attempt** or **the entire operation**, and do not mix the two.

## 3. Measuring "Business Latency" Accurately

### 3.1. `begin()` and `end()`

JFR API for custom events:

```java
BusinessEvent event = new BusinessEvent();
event.begin();
try {
    // Work to measure.
} finally {
    event.end();
    if (event.shouldCommit()) {
        // Only build useful payload when the event is actually captured.
        event.commit();
    }
}
```

`event.begin()` starts the JFR timer; `event.end()` closes the interval; `commit()` records the event when enabled and above threshold. JFR stores `startTime`, `duration`, and custom fields. `end()` must be called after `begin()`; if omitted, `commit()` marks the end time, but an explicit `finally` block prevents accidentally skipping error paths.

**Choose meaningful measurement boundaries:** If you want "reservation processing time", call `begin()` right before starting the business operation and `end()` once the operation's outcome is decided. It will **exclude** time spent prior to `begin()`, such as sitting in an API gateway queue, as well as async work continuing **after** the method returns. Placing `end()` before or after DB writes, retries, external calls, or transaction commits changes the SLI, so be consistent.

Points to distinguish:

- JFR `duration` is **elapsed time** between `begin` and `end`; it is not thread CPU time.
- If the measured block waits on DB/network, locks, sleep, or the scheduler, `duration` still increases even while the thread uses no CPU.
- If an operation spans multiple threads or async tasks, a single-method event does not automatically sum unawaited/unjoined tasks; pick the **logical start/end points of the operation** and propagate correlation context.
- With virtual threads, JFR still records events per `begin`/`end` logic, though `eventThread` alone is insufficient to trace a request across async boundaries.
- Do not manually store `duration` as "ms from `System.currentTimeMillis()`" in the JFR payload when JFR already records `duration`; add a separate timing field only when it carries genuinely distinct semantics.

### 3.2. `shouldCommit()` and thresholds

JFR supports configuring a `threshold`: durations **shorter than the threshold** are not recorded. After `end()`, `shouldCommit()` avoids computing/sanitizing expensive fields for events that will be dropped.

- For **labs**: threshold 0, capturing both successes and failures, even fast ones.
- For **slow-operation diagnostics**: e.g., 50 ms threshold to keep only operations taking at least 50 ms.
- For **error-rate measurement**: a very fast `FAILED` event may be dropped if it shares a 50 ms threshold. Never conclude "zero errors" from a slow-event JFR recording; if fast failures must be observed, use a separate failure event with appropriate quotas/sampling, or rely on metrics/logs.
- For **latency distribution**: capturing only operations slower than a threshold yields a **left-truncated sample**; you cannot compute p50/p95/p99 across **all requests** directly from those events. Use proper latency histograms for SLIs, and JFR for inspecting concrete slow cases.

`Event.isEnabled()` checks whether any recording enables the event type; `shouldCommit()` also evaluates the duration threshold. These are overhead-reduction tools, not guarantees that events stay on disk forever: JFR still has buffers, rotation, retention, and operational limits.

## 4. What Does "Bounded Data" Mean?

There are **three kinds of bounds to design together**.

### 4.1. Bounding data *types and size*

A well-designed event usually contains only **a few numeric fields and short structured `String`s**:

- Use an **allowlist** for `operation`, `outcome`, and `failureCategory`; unknown values collapse safely into `OTHER`.
- Correlation codes must come from a trusted source, have a max length, and carry no PII/credentials. Never use raw session IDs, JWTs, cookies, URLs/queries, arbitrary headers, or raw customer IDs directly.
- Never record request/response payloads, SQL text, exception messages, or stack traces for every event. Error messages often contain tokens, addresses, paths, or private data that authors did not anticipate.
- For counts that can grow very large, define types and caps. If recording a capped value, add `wasCapped=true` or use buckets so readers do not mistake it for an exact count.
- Never add a `String debugData` field and serialize objects or JSON into it. Event size and cardinality explode, and sensitive content becomes hard to control.

Example validation rule for a **system-generated** code separated from customer input:

```java
static String safeCode(String systemCode) {
    if (systemCode == null
            || systemCode.length() > 64
            || !systemCode.matches("[A-Za-z0-9_-]{1,64}")) {
        return "INVALID";
    }
    return systemCode;
}
```

This is an **input policy illustration**, not a standalone Java program. It checks format only; it cannot detect whether a caller put sensitive info inside a format-valid string. On invalid formats, emit `INVALID`/`MISSING` and handle details in policy-compliant logs/traces rather than stuffing the raw malformed value into JFR.

### 4.2. Bounding *frequency* and *event volume*

Suppose a system handles 30,000 operations/s with an average 200-byte event (illustrative numbers excluding metadata, chunk overhead, and sampling). Recording every operation yields roughly 6 MB/s in theoretical payload alone. Actual size depends on string fields, encoding, stack traces, and other JDK events. Never treat that back-of-the-envelope formula as a real benchmark.

Common strategies:

- Detailed events only for **slow operations** via thresholds; use histograms/counters for overall visibility.
- `FAILED` outcome events need their own capture policy if fast failures matter; never dump large payloads merely because an operation failed.
- Use **bounded sampling** at the system level, or emit events aligned with request/tracing sampling policies. Document rates and intent clearly; sampled JFR data does not represent total traffic directly.
- Disable stack traces on business events that already have correlation codes if stacks do not answer the question; enable them selectively in timed investigative recordings when overhead is acceptable.
- Configure `maxage`/`maxsize`, disk headroom, storage quotas, and retention/ACLs for exported `.jfr` files.

JFR recording settings do not natively provide "at most one event per business ID" or security sanitization for `String` fields; the application must define policies and enforce bounds at **payload construction time**.

### 4.3. Bounding *access and retention*

A `.jfr` file is a diagnostic artifact that can contain JVM/runtime details, environment info, stack/method names, and custom payloads. It is not anonymized or encrypted by default. You must:

- Restrict file readers and control storage locations, sharing, and deletion schedules.
- When extracting files to share externally, inspect contents and apply minimization/anonymization workflows if needed.
- Do not assume "we did not log emails" guarantees complete safety: correlation codes can still link back to customer records through internal systems.
- Distinguish retention of the active JFR recording from retention of exported files, logs, or reports; they often differ.

## 5. Java 17+ Lab: Recording and Reading a Complete Business Event

The standalone program below intentionally runs **two operations**: one successful and one handled failure. Events are recorded when each operation finishes, even when the failure branch throws an exception. No personal data is used: `r-0001` and `r-0002` are fixed demo codes.

### 5.1. Create `BusinessJfrDemo.java`

```java
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class BusinessJfrDemo {
    @Name("demo.BusinessOperation")
    @Label("Business operation")
    @Category({"Application", "Business"})
    @StackTrace(false)
    public static class BusinessEvent extends Event {
        @Label("Correlation code")
        public String correlationCode;
        @Label("Operation")
        public String operation;
        @Label("Outcome")
        public String outcome;
        @Label("Failure category")
        public String failureCategory;
        @Label("Item count")
        public int itemCount;
    }

    static void process(String code, boolean fail) throws InterruptedException {
        BusinessEvent event = new BusinessEvent();
        String outcome = "SUCCESS";
        String category = "NONE";
        event.begin();
        try {
            Thread.sleep(30);
            if (fail) {
                throw new IllegalArgumentException("simulated failure");
            }
        } catch (InterruptedException ex) {
            outcome = "CANCELLED";
            category = "INTERRUPTED";
            Thread.currentThread().interrupt();
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "FAILED";
            category = "VALIDATION";
            throw ex;
        } finally {
            event.end();
            if (event.shouldCommit()) {
                event.correlationCode = code;
                event.operation = "reserve";
                event.outcome = outcome;
                event.failureCategory = category;
                event.itemCount = 1;
                event.commit();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path target = Path.of("business.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(BusinessEvent.class)
                .withThreshold(Duration.ZERO)
                .withoutStackTrace();
            recording.start();
            process("r-0001", false);
            try {
                process("r-0002", true);
            } catch (IllegalArgumentException ignored) {
                // The simulated failure is expected in this lab.
            }
            recording.stop();
            recording.dump(target);
        }

        List<String> rows = new ArrayList<>();
        try (RecordingFile reader = new RecordingFile(target)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent e = reader.readEvent();
                if (!e.getEventType().getName().equals("demo.BusinessOperation")) {
                    continue;
                }
                if (e.getDuration().isNegative()) {
                    throw new IllegalStateException("Negative duration");
                }
                rows.add(e.getString("correlationCode") + "|"
                    + e.getString("operation") + "|"
                    + e.getString("outcome") + "|"
                    + e.getString("failureCategory") + "|"
                    + e.getInt("itemCount"));
            }
        }
        Collections.sort(rows);
        System.out.println("business-events=" + rows.size());
        for (String row : rows) {
            System.out.println(row);
        }
    }
}
```

How the program works:

1. `BusinessEvent` extends `jdk.jfr.Event` and declares supported JFR fields: four `String`s and one `int`.
2. `@Name("demo.BusinessOperation")` is the event name for configuration and querying. `@StackTrace(false)` indicates JFR stack traces are disabled by default for this event type.
3. `process()` calls `begin()` before the simulated business work, catches exceptions to map them into **stable outcome categories**, and calls `end()` in `finally`.
4. After `end()`, `shouldCommit()` checks recording/threshold. Only when the event is kept are fields populated; the exception message `simulated failure` is **not included in the payload**.
5. `Recording` in `main` is only used to create a lab recording. `enable(...).withThreshold(Duration.ZERO).withoutStackTrace()` enables the event, removes the duration threshold, and disables stack traces.
6. `RecordingFile` reads the binary `.jfr` file, filters for the target event name, and prints the safe fields. The program checks that duration is non-negative, without printing exact millisecond values since those depend on the host machine.

**Limitation of this lab:** `code`, `operation`, and `itemCount` are pre-controlled values. In production, invoke sanitization/allowlist functions and enforce policy **before** assigning fields; never copy untrusted request data directly into `event`.

### 5.2. Compile and run

From the directory containing the file:

```bash
javac BusinessJfrDemo.java
java BusinessJfrDemo
```

Exact stdout from the Java code above (verified on OpenJDK 24):

```text
business-events=2
r-0001|reserve|SUCCESS|NONE|1
r-0002|reserve|FAILED|VALIDATION|1
```

The program creates `business.jfr` in the current working directory. In this lab, lines are sorted with `Collections.sort()` before printing, so output does not depend on the ordering of other events that may exist in the recording.

### 5.3. Inspecting directly with JFR tools

```bash
jfr summary business.jfr
jfr print --events demo.BusinessOperation business.jfr
jfr metadata --events demo.BusinessOperation business.jfr
```

`jfr summary` lists `demo.BusinessOperation` with **2 events** in a successful lab run. `jfr print` outputs fields in this form:

```text
demo.BusinessOperation {
  startTime = ...
  duration = ...
  correlationCode = "r-0001"
  operation = "reserve"
  outcome = "SUCCESS"
  failureCategory = "NONE"
  itemCount = 1
  eventThread = "main" (...)
}
```

The `...` placeholders above **only illustrate the JFR output schema**, not fixed stdout. Timestamps, durations, thread IDs, and metadata ordering may vary across runs or JDK versions. For actual results, inspect `business.jfr` with the commands above; `duration` and `startTime` are generated by JFR without needing custom fields in your class.

An experimental run on JDK 24 produced two events with durations of a few tens of milliseconds. This only verifies **instrumentation behavior**, not a benchmark or guarantee of 30 ms latency across systems.

## 6. Applying This in Real Applications: Placement and Lifecycle

### 6.1. Placing events around meaningful business units

Suppose a reservation flow consists of:

```text
HTTP request
  -> validate input
  -> query inventory
  -> reserve inventory
  -> persist reservation
  -> return response
```

Define the boundary the business team calls "reservation time". If you want to measure from service entry through DB commit, `begin()` must span all those steps. If you only want to measure a dependency call, create a separate name like `InventoryLookup` and wrap `begin`/`end` around that call. **Never reuse the same event name for two different latency definitions**, because the data cannot be compared honestly.

An operation with retries can be designed as:

- `BusinessOperation`: one event for the **overall** operation, final outcome, and total elapsed time.
- `DependencyAttempt`: a separate event when investigating **individual retries**, carrying the same `correlationCode` and a bounded `attemptNumber`.
- Accompanying metrics recording total operations/attempts and duration histograms.

Never emit the same event name at both controller and service layers and sum them as independent transactions; that causes double counting.

### 6.2. Preserving correlation across async boundaries

Across callbacks, executors, virtual threads, or service boundaries, **the correlation code must be propagated explicitly**. `eventThread` is simply the thread committing the event; it does not automatically carry business correlation. Nor should you rely on thread names to reconstruct relationships across thread pools.

Pass a small, immutable context object containing only the opaque code and permitted attributes via method parameters or tracing context. With structured concurrency/async execution, to measure end-to-end latency, `end()` must run only after results from required branches have been awaited/completed. If `end()` runs right after task submission, duration measures **submission latency**, not business completion.

Separate three timings during analysis:

1. **Queue delay** before work actually begins.
2. **Execution/elapsed duration** from `begin()` to `end()` of the business operation.
3. **End-to-end request duration** at the client/gateway including network and phases outside the measured region.

If all three are needed, define distinct events/metrics with clear names rather than lumping them into one `duration`.

### 6.3. Keeping business logic independent of telemetry errors

A diagnostic event must never turn a business failure into a success or mask the original exception. Standard JFR recording methods do not perform synchronous I/O on the hot path, yet custom helper code normalizing payloads can throw exceptions. Therefore:

- Use `finally` to close the measurement interval on success, failure, and cancellation.
- Set outcome categories in appropriate `catch` blocks; **never swallow exceptions** just to emit an event.
- Never make extra network or DB calls inside JFR payload construction.
- Avoid serializing large objects or calling `toString()` on untrusted data inside `finally`.
- Record `InterruptedException` as `CANCELLED`/`INTERRUPTED` per application semantics, preserving the interrupt flag when appropriate.
- Never let an instrumentation error obscure the active business stack trace or exception.

The lab in section 5 demonstrates success/failure/interrupt with standard Java exception handling and no side effects outside the recording.

## 7. Enabling Custom Events in Service Recordings

### 7.1. Two configuration approaches

**Approach A — programmatic recording** (mainly for tests/tooling):

```java
try (Recording recording = new Recording()) {
    recording.enable(BusinessJfrDemo.BusinessEvent.class)
        .withThreshold(Duration.ofMillis(20))
        .withoutStackTrace();
    recording.start();
    // Execute the code under diagnosis.
    recording.stop();
    recording.dump(Path.of("sample.jfr"));
}
```

The block above is **illustrative code** that compiles only inside a class/method with imports and exception handling as in section 5. In a production server, **never create a `Recording` per request**: a recording is a JVM-level mechanism with management and resource overhead; typically create one recording for a diagnostic window, or manage it via `jcmd`/JMC.

**Approach B — recording managed via JVM/JFR settings.** Create a `.jfc` containing the custom event:

```bash
jfr configure --output business.jfc \
  "+demo.BusinessOperation#enabled=true" \
  "+demo.BusinessOperation#threshold=20ms" \
  "+demo.BusinessOperation#stackTrace=false"
```

The `+` prefixes in `jfr configure` instruct it to **add event settings** if the base profile does not already contain the custom event. `demo.BusinessOperation` must match `@Name` in code. Arguments containing `#` should be quoted in the shell. A `20ms` setting suits observing **slow** operations; it is unsuitable when you need to observe all fast failures.

Using the generated file:

```bash
java -XX:StartFlightRecording=name=business,settings=business.jfc,disk=true,filename=business-service.jfr,dumponexit=true \
  -jar app.jar
```

`app.jar` is a hypothetical application containing the custom event class and instrumentation shown above. `filename` is the output JFR file; `dumponexit=true` requests a dump on normal JVM exit, not guaranteed if the process is killed abruptly. Long-running recordings require retention/storage limits and overhead evaluation.

For a running JVM (using the actual PID and appropriate attach permissions):

```bash
jcmd -l
jcmd <PID> JFR.start name=business settings=business.jfc duration=60s filename=business-snapshot.jfr
jcmd <PID> JFR.check name=business verbose=true
```

`JFR.check verbose=true` confirms the recording's active event settings. Once duration elapses, inspect `business-snapshot.jfr`; to grab a snapshot while the recording is still live:

```bash
jcmd <PID> JFR.dump name=business filename=business-now.jfr
```

Do not mistake `jfr configure` for starting a recording: it only creates or edits `.jfc` files. Do not mistake `jcmd JFR.configure` for setting thresholds on a custom event: that command primarily configures global recorder options. Per-event names and thresholds belong in `JFR.start settings=...` or `Recording.enable(...).withThreshold(...)`.

### 7.2. Choosing thresholds based on the question

| Goal | Suggested configuration | Warning |
| --- | --- | --- |
| Lab verifying event schema | `threshold=0`, stack trace off, short recording | Do not carry this exact config to high-volume workloads without measuring overhead. |
| Finding slow business operations | `threshold=20ms`/`50ms` or aligned with actual SLO | Insufficient to infer overall success rate or full request distribution. |
| Catching fast, rare errors | Dedicated failure event or synchronized sampling/metrics | A slow-only event drops errors below threshold. |
| Needing stack at commit time | Temporarily enable `stackTrace` for targeted events | Stack traces add data; the commit location is not necessarily where the operation started. |
| Long-term behavior tracking | Metrics for counts/histograms; JFR samples/slow cases with retention | Never use JFR events as a mandatory transaction ledger. |

`@StackTrace(false)` sets the event type's default; recording-specific settings can override it. `stackTrace=true` captures the stack **at commit time**; if you want an earlier call path, check whether that commit site actually represents what you need.

## 8. Reading and Correlating Collected Data

### 8.1. Using JFR CLI / JMC

```bash
jfr summary business-service.jfr
jfr print --events demo.BusinessOperation business-service.jfr
jfr metadata --events demo.BusinessOperation business-service.jfr
```

What to inspect:

- `startTime`: align with log/trace timestamps using a consistent timezone.
- `duration`: elapsed time of the instrumented business segment.
- `correlationCode`: lookup key into logs/tracing; never rely on thread ID as a request ID.
- `operation` + `outcome` + `failureCategory`: identify the case under investigation and failure type.
- `itemCount`: compact load context; does not equal total work complexity if business logic varies on other dimensions.
- `eventThread`: helpful when correlating with JVM thread events, though insufficient to prove end-to-end relationships under async execution.

JDK Mission Control lets you filter custom events by fields and compare timestamps with GC, allocations, locks, or I/O. A sound analysis sequence:

1. Find the slow request's `correlationCode` in logs/traces.
2. Locate the `demo.BusinessOperation` event with the matching code, operation, and timeframe.
3. Check `duration`, `outcome`, and `failureCategory`.
4. Compare the event's time window against GC pauses, CPU load, and socket/monitor events in the same JVM.
5. Cross-check logs/traces to confirm the narrative; e.g., a GC pause overlapping a slow request in JFR **is not enough alone** to prove GC was the sole root cause.

### 8.2. Reading directly in Java

The lab in section 5 uses `RecordingFile` and `RecordedEvent`. For offline analysis tools, you can extract fields like this:

```java
if (e.getEventType().getName().equals("demo.BusinessOperation")) {
    String code = e.getString("correlationCode");
    String status = e.getString("outcome");
    Duration elapsed = e.getDuration();
    // Apply filters for time, operation, status, and access control.
}
```

This is an **illustrative snippet inside a loop with an existing `RecordedEvent e`**, not a standalone program. Typed getters like `getString`, `getInt`, and `getDuration` read values cleanly; handle schema/version differences properly and do not assume a newly added field exists in older recordings.

### 8.3. Representative results

Suppose you obtain three **illustrative** events:

| Code | Operation | Duration | Outcome | Failure category |
| --- | --- | ---: | --- | --- |
| `a-01` | `reserve` | 15 ms | `SUCCESS` | `NONE` |
| `a-02` | `reserve` | 760 ms | `FAILED` | `DEPENDENCY` |
| `a-03` | `reserve` | 82 ms | `CANCELLED` | `INTERRUPTED` |

If the recording has a 20 ms threshold, `a-01` **will not appear**, while `a-02`/`a-03` can appear. Investigate `a-02` using the same code in traces and JVM events to determine whether dependency timeout, pool wait, GC, or network was involved. Never use this filtered table to compute business success rate—the denominator has been altered.

## 9. Common Pitfalls

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Writing `orderId`, email, or token into correlation field | Can leak PII/credentials via `.jfr` files | Use a system-issued opaque code and clear access policies. |
| Recording `Exception.toString()` or raw error messages | May contain SQL, URLs, paths, tokens, or customer data | Map into an approved `failureCategory`. |
| Putting `Map`, `enum`, or DTO into custom Event fields | JFR does not serialize those field types automatically | Use primitive/`String`/`Thread`/`Class` and an explicit schema. |
| Wrapping `begin`/`end` only around `submit()` and calling it "end-to-end latency" | Async work may not have finished | End the measurement interval when the logical outcome is decided. |
| Recording `SUCCESS` only on the return path | Exception and cancellation paths lose events | Use `try/catch/finally`; assign outcome before committing. |
| Calling `shouldCommit()` before `end()` and assuming fast events filter right | Duration is not finalized yet | Finish timing first, then check threshold. |
| Adding stack traces/exception messages to every request | Size and data-leak risk surge | Disable stack traces by default; enable temporarily when needed. |
| Using correlation codes as metric labels | Cardinality explodes with request volume | Metrics use allowlisted operation/outcome; IDs live in controlled traces/JFR/logs. |
| Setting a 50 ms threshold yet claiming all errors are captured | Fast failures are dropped | Use a dedicated failure event or appropriate counters/histograms. |
| Computing p99 from events collected only for "slow" cases | Data is truncated by duration | Use histograms across all instrumented requests. |
| Emitting the same event at both controller and service layers | Analytics may double-count operations | Distinguish scopes/event names or pick a single canonical boundary. |
| Running unbounded continuous recordings | Can grow disk/memory footprint and complicate governance | Set duration, maxage, maxsize, quotas, sampling, and ACLs. |
| Relying on `eventThread` instead of a correlation code | Thread pools/virtual threads/async break 1 thread = 1 request | Propagate correlation context explicitly. |
| Reading one JFR file and claiming every operation was recorded | JFR has settings, thresholds, buffers, and retention | Check configuration and cross-verify with metrics/logs. |

## 10. Extension Exercises

**Exercise A — Testing threshold:** change `.withThreshold(Duration.ZERO)` to `.withThreshold(Duration.ofMillis(100))` and rerun. With each operation sleeping roughly 30 ms, the custom event is normally not recorded (though actual scheduling and elapsed time apply). Verify with `jfr summary`. If an event still appears, check elapsed time and whether it exceeded the threshold rather than relying on the requested `sleep()` ms.

**Exercise B — Adding a timeout branch:** simulate a dependency timeout, catch the exception at the business boundary, and assign outcome `FAILED` with failureCategory `TIMEOUT`. Verify via `jfr print` that **no arbitrary message** appears in the event, only the category.

**Exercise C — Async:** move the business step into a `CompletableFuture`. Choose between two latency definitions: task submission time vs. actual result completion time. Write both versions and explain why the durations differ. Pass the correlation code into callbacks explicitly via parameters/context rather than assuming `ThreadLocal` follows tasks automatically.

**Exercise D — Data limits:** design an allowlist of at most 5 operations, 3 outcomes, 6 failure categories, and a server-issued ASCII correlation code of at most 64 characters. Pass an out-of-bounds string and verify the event records only the `INVALID` sentinel without storing the rejected value.

**Exercise E — Linking with JVM events:** enable a recording with both the custom event and relevant JDK events, generate a workload with lock/I/O waits, read the timeline, and identify where events **correlate in time**. Draw root-cause conclusions only with corroborating stacks, traces, or independent measurements.

## 11. Production Readiness Checklist

- [ ] One event name maps to **one well-defined business scope**; field schema/versioning is stable.
- [ ] Correlation code is an opaque internal ID from a trusted source with bounded format/length and a policy for missing/malformed values.
- [ ] `operation`, `outcome`, and `failureCategory` all use allowlists; zero payloads, PII, tokens, URLs/queries, or raw exceptions.
- [ ] `begin`/`end` wrap the exact target latency span; `SUCCESS`, `FAILED`, and `CANCELLED` branches are all handled.
- [ ] `end()` and `shouldCommit()` are ordered properly; payload construction occurs after the check whenever possible.
- [ ] Thresholds and sampling serve diagnostic questions; **never derive success rate or latency SLIs** from a filtered JFR sample.
- [ ] Actual event settings have been verified via JFR tools/recording settings, and events are confirmed present in dumped files.
- [ ] Bounds are enforced on field sizes, event rates, stack traces, retention, file access, and sharing.
- [ ] For async/multi-service flows, context propagation does not depend on thread names; traces/logs/JFR share a standardized ID.
- [ ] Overhead, CPU, allocations, and JFR storage footprint are measured before enabling on high-throughput traffic.
- [ ] Verified with at least one success, one failure, and one cancellation/timeout, compared against metrics/logs to understand semantic differences.

**Takeaway:** The goal is not "stuffing all business data into JFR", but creating **a compact diagnostic milestone that links cleanly with other signals**. A trustworthy custom event requires four elements: **accurate timing boundaries, meaningful outcomes, a safe correlation code, and an explicit data budget**.

## References

- [Oracle JDK 21 — `jdk.jfr.Event`: field types, `begin()`, `end()`, `shouldCommit()`, `commit()`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle JDK 21 — `jdk.jfr` package and event settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle JDK 21 — `EventSettings`, threshold, and stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Oracle JDK 21 — `Recording`: enable, start, stop, dump](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle JDK 21 — `RecordingFile` (offline reading)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Dev.java — Configuring JFR (`jfr configure`)](https://dev.java/learn/jvm/jfr/configure/)
- [Oracle Java 21 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf)
