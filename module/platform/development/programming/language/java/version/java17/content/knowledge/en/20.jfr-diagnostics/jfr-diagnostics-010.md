# Choosing Appropriate Observability Levels and Protecting Sensitive Data in JFR Recordings

Java Flight Recorder (JFR) is the JVM and application event recording system. It helps observe garbage collection, memory allocation, thread activity, locks, I/O, exceptions, and application-defined custom events. JFR is built into the JDK and can record continuously with relatively low overhead when configured appropriately.

Recording more events, more stack traces, and finer detail makes a recording richer for certain investigations, yet it can also raise overhead, storage footprint, and the amount of sensitive data captured in the file. Operators must therefore choose an **observability level just sufficient for the question being investigated**, set recording durations and limits, and treat JFR files as operational data that may contain sensitive information.

This lesson focuses on choosing JFR configurations in Java 17, tuning events and thresholds, capturing time-bounded recordings, reviewing data before sharing, and designing safe custom events.

## 1. What Does JFR Record?

JFR captures structured events over time. Each event can contain a timestamp, duration, thread, stack trace, and event-specific data fields.

Commonly used event groups:

| Group | Examples of Observable Information | Typical Questions Answered |
| --- | --- | --- |
| JVM and GC | GC cycles, pauses, heap summary, safepoints | Is GC causing long pauses? How is the heap changing? |
| Allocation | Object allocation events or allocation samples | Which classes allocate the most objects? Is allocation spiking abnormally? |
| Threads and CPU | Execution samples, thread start/end, thread park | Where are threads spending time? Are threads blocked? |
| Synchronization | Contended monitors, lock events | Is there lock contention or prolonged monitor waits? |
| I/O | File read/write, socket read/write | Where is the app waiting on I/O? Which operations take long? |
| Exceptions and errors | Exception events per configuration | Are exceptions spiking? Which code path throws them? |
| Class loading | Class loading and class loader activity | Is startup or dynamic loading abnormal? |
| Application events | Application-defined custom events | How long did a business operation take? What type of request was it? |

JFR is a structured event system, not a complete transcript of every action inside a process. Some data is sampled; some events record only past a threshold; others appear only when explicitly enabled. Consequently, a JFR file must not be treated as a complete audit log or proof that every operation was recorded.

## 2. Choosing an Observability Level: default, profile, or Custom Configuration

JDK 17 ships two common built-in JFR configurations:

- **default.jfc**: aimed at continuous recording with low overhead. Well suited for maintaining background observability in production.
- **profile.jfc**: captures more detailed data, useful for time-bounded investigations. It can emit more events and stack traces, resulting in higher overhead and file size.

Configuration names are selected when starting a recording or through the JFR API. Built-in configuration files typically live in the JDK installation under `lib/jfr/`, though exact paths depend on the JDK layout.

### 2.1. Comparing Observability Levels

| Level | When to Choose | Characteristics | How to Manage |
| --- | --- | --- | --- |
| Continuous baseline | Need background data to spot trends or investigate recent incidents | Uses `default` settings, bounded size and retention | Continuous disk recording or governed by operational policy |
| Targeted investigation | Already have a hypothesis like GC pauses, lock contention, or socket latency | Enable relevant events, tune thresholds and stack traces | Record over a defined time window |
| Detailed profile | Root cause unclear; need broader detail over a short window | Uses `profile` settings or more detailed configuration | Bound duration, max size, and file access |
| App-specific diagnostics | Need to measure a business operation or custom event type | Create custom events recording only needed fields | Enforce clear schema, sampling, and data policy |

Do not leave detailed `profile` settings enabled permanently just to “collect as much data as possible.” Define the question first, then select the matching configuration.

### 2.2. An Observability Selection Workflow

~~~text
Define the question to answer
            |
            v
Is there a suitable JFR baseline?
       /            \
     Yes             No
     |                |
     v                v
Inspect baseline   Choose default or profile
     |                |
     v                v
Missing data?      Enable only relevant events
     |                |
     +------> Tune thresholds/stack traces
                      |
                      v
             Record for a bounded window
                      |
                      v
             Inspect data and protect the file
~~~

Examples:

- To inspect GC pauses in production, start with a `default` recording and check GC events.
- To find hot allocation sites, use `profile` settings during a reproducible load window or selectively enable allocation events.
- To find lock contention, focus on monitor/lock events and stack traces with an appropriate threshold.
- To time a business operation, consider custom events instead of logging request payloads.

## 3. Components of a JFR Configuration

A JFR configuration is a set of per-event settings. Common settings include:

| Setting | Effect |
| --- | --- |
| enabled | Turns an event on or off. |
| threshold | Records only events whose duration meets the threshold, for timed events. |
| stackTrace | Whether to capture a stack trace for the event. |
| period | Sampling interval or periodic emission interval, depending on the event. |
| cutoff | Caps event duration where supported by the event. |
| throttle | Caps event emission rate where supported by the event. |

Not every setting applies meaningfully to every event. For instance, `threshold` primarily applies to events with duration; `period` fits periodic or sampled events. Inspect event metadata and settings rather than applying one setting blindly across all events.

### 3.1. Event Thresholds

Thresholds filter out very short events to reduce noise and data volume. For example, if investigating slow I/O, record only socket reads taking 20 ms or longer:

~~~bash
jfr configure --input profile.jfc --output io-investigation.jfc \
    jdk.SocketRead#enabled=true \
    jdk.SocketRead#threshold=20ms
~~~

This creates a new configuration file from `profile` settings, enabling `SocketRead` with a 20 ms threshold. Pass this file to the recording's `settings` option. `jfr configure` lets you adjust specific events without rewriting XML from scratch.

A threshold set too high can miss moderately slow operations or many small operations summing to high latency. A threshold set too low can flood the recording with events. Pick thresholds based on target latency and real-world duration distributions.

### 3.2. Stack Traces

Stack traces reveal the call path leading to an event. They are especially valuable when investigating allocations, lock contention, I/O, or exceptions.

Stack traces also enlarge recordings and can expose:

- internal class and package names;
- method, module, or framework names;
- application architecture and integrated components;
- code paths or implementation details that should not be public.

Enable stack traces only for events needing root-cause attribution. If the question is simply “how long did GC pauses last?”, enabling stack traces on every event adds little proportional value.

### 3.3. Period and Sampling

Some events are emitted periodically or sampled. Shorter periods raise time resolution at the cost of higher event counts and overhead. Longer periods cut data volume at the risk of missing brief spikes.

Sampling is not identical to recording every execution. For example, execution sampling estimates where threads spend time; it is not an exact trace of every method call.

## 4. Choosing Events by Investigation Question

Start from the symptom and select relevant event groups:

| Symptom | Events / Groups to Consider | Configuration Tips |
| --- | --- | --- |
| Rising request latency | Execution samples, socket/file I/O, thread park, lock contention | Enable stack traces on relevant events; set thresholds near target latency |
| Long GC pauses | GarbageCollection, GCPhasePause, heap summary, allocations | Start with `default`; use `profile` if detailed analysis is needed |
| Heap growth over time | Old object/heap statistics, allocation samples, supporting class histograms | Combine JFR with heap dumps when retention paths are needed |
| Rising CPU | Execution sampling, thread events | Sample densely enough for the investigation window; avoid unrelated events |
| Lock contention | JavaMonitorEnter/Wait or matching sync events | Use thresholds and stack traces to locate contention points |
| Slow I/O | FileRead/FileWrite, SocketRead/SocketWrite | Filter long events and check hosts/paths before sharing |
| Slow startup | Class loading, relevant module loading, threads, and file I/O | Record from JVM launch when investigating startup |
| Suspected fault in a business flow | Custom event with duration and non-sensitive classification codes | Record minimal metadata; never log payloads or secrets |

Exact event names and supported settings are listed in the runtime's JFR metadata. Run `jfr metadata` to inspect events available in your running JDK.

## 5. Recording JFR via Command Line and jcmd

### 5.1. Starting a Recording at JVM Startup

You can enable JFR at application launch:

~~~bash
java -XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=6h,maxsize=256m,dumponexit=true \
    -jar app.jar
~~~

Meaning:

- `name=baseline`: recording name.
- `settings=default`: uses the built-in default configuration.
- `disk=true`: allows the recording to write data to disk.
- `maxage=6h`: caps the age of data retained in the rolling recording.
- `maxsize=256m`: caps recording size.
- `dumponexit=true`: dumps the recording when the JVM exits normally.

These numbers are examples. Choose limits based on disk capacity, investigation windows, event rates, and environment retention policies.

### 5.2. Starting a Recording on a Running JVM

Find the process:

~~~bash
jcmd
~~~

Start a time-bounded recording:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=5m filename=/secure/jfr/incident.jfr
~~~

This records for five minutes using `profile` settings. `/secure/jfr` must exist, have restricted access permissions, and have adequate disk space. On Windows, use a valid OS path and appropriate ACLs.

For continuous recordings, omit `duration`; dump and stop via the corresponding commands when needed.

### 5.3. Checking and Managing Recordings

~~~bash
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=incident filename=/secure/jfr/incident-now.jfr
jcmd <pid> JFR.stop name=incident
~~~

- `JFR.check` lists active recording status.
- `JFR.dump` writes current data to a file.
- `JFR.stop` stops the named recording.

If a recording had a `duration` configured and stopped automatically, check status before dumping or stopping. Never assume every command succeeded; verify `jcmd` output.

### 5.4. Viewing Summaries and Events in a File

The JDK provides the `jfr` tool:

~~~bash
jfr summary /secure/jfr/incident.jfr
jfr metadata /secure/jfr/incident.jfr
jfr print --events jdk.GarbageCollection /secure/jfr/incident.jfr
~~~

`jfr summary` displays a recording overview and event counts. `jfr metadata` prints event metadata. `jfr print` outputs events as text; that text output can also contain sensitive information and must be protected just like the raw JFR file.

## 6. Tuning Events with `.jfc` Files

A `.jfc` file is an XML-based JFR configuration. You can use built-in configurations or build a custom file from an existing one.

Illustrative snippet for one event:

~~~xml
<event name="jdk.SocketRead">
  <setting name="enabled">true</setting>
  <setting name="threshold">20 ms</setting>
  <setting name="stackTrace">true</setting>
</event>
~~~

This snippet illustrates a single event's settings; a complete `.jfc` file contains additional configuration elements and metadata. Never replace an entire standard config file with an abbreviated XML fragment.

Practical workflow:

1. Copy `default.jfc` or `profile.jfc` from the JDK.
2. Rename the copy to distinguish environment and purpose.
3. Enable only required events.
4. Set appropriate `threshold`, `period`, and `stackTrace` values. You can use `jfr configure` to generate a custom file:

~~~bash
jfr configure --input default.jfc --output gc-focused.jfc \
    jdk.GarbageCollection#enabled=true \
    jdk.GCPhasePause#enabled=true
~~~

5. Validate the configuration against the target Java 17 runtime.
6. Test in a production-like environment and measure overhead.

Example using a custom file:

~~~bash
java -XX:StartFlightRecording=name=targeted,settings=/etc/myapp/jfr/io-investigation.jfc,duration=3m,filename=/secure/jfr/io.jfr \
    -jar app.jar
~~~

Do not edit the JDK's bundled configuration files directly if you want to keep a clean baseline. Create separate files so changes can be reviewed, version-controlled, and rolled back.

## 7. Recording JFR via the Java API

Applications can create recordings using the `jdk.jfr` module API. If using JPMS, the module descriptor must declare `requires jdk.jfr;`. Example:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;

public class RecordingExample {
    public static void main(String[] args) throws IOException {
        Configuration configuration =
                Configuration.getConfiguration("default");

        try (Recording recording = new Recording(configuration)) {
            recording.setName("targeted-operation");
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(128L * 1024 * 1024);
            recording.setToDisk(true);

            recording.start();
            performOperation();
            recording.stop();
            recording.dump(Path.of("recordings", "operation.jfr"));
        }
    }

    private static void performOperation() {
        // Perform the operation to observe.
    }
}
~~~

The API allows configuring and managing the recording lifecycle directly in code. In the example, the output directory must exist and be protected. `try-with-resources` closes the `Recording` upon completion.

### 7.1. Enabling a Specific Event via API

You can add or tune an event on a recording:

~~~java
import jdk.jfr.EventSettings;

EventSettings socketRead = recording.enable("jdk.SocketRead");
socketRead.withThreshold(Duration.ofMillis(20));
socketRead.withStackTrace();
~~~

This assumes `recording` refers to an initialized `Recording`. The event name must exist in the runtime; enable an event only when it answers the question under investigation.

### 7.2. Setting Recording Limits

Common limits to consider:

- `maxAge`: caps the age of data inside a recording.
- `maxSize`: caps disk storage used by the recording.
- `duration`: caps runtime duration in certain launch modes.
- `setToDisk`: decides whether recording data is written to disk.

These limits keep continuous recordings from filling disk endlessly. However, as the ring buffer wraps, older data is evicted; factor in incident windows and dump cadence.

## 8. Trade-Offs Among Detail, Overhead, and Storage Size

Every observability choice carries a cost:

| Increasing Observability | Benefit | Cost / Risk |
| --- | --- | --- |
| Enabling more events | Broader visibility into JVM and app | More events, larger files, higher processing cost |
| Lowering thresholds | Captures shorter events | More events, higher noise and overhead |
| Enabling stack traces | Reveals event call origins | Larger recordings, exposes internal structure |
| Increasing sampling frequency | Finer time resolution | Higher sampling cost and data volume |
| Recording longer | Catches rare incidents | Larger files, longer retention, broader sensitive data exposure |
| Recording custom event payloads | Richer business context | High risk for PII, tokens, customer data, or secrets |

JFR is built for low overhead when properly configured, yet zero overhead does not exist. In production, measure under representative workloads rather than assuming every event setting is free.

## 9. Why Can JFR Files Contain Sensitive Data?

A JFR file holds more than aggregate numbers. Depending on events and configuration, it may contain metadata identifying systems or users:

- thread names, class names, packages, methods, and stack traces;
- host addresses, ports, or connection details from I/O events;
- file paths or resource names;
- module names, class loaders, and application structure details;
- data fields written by custom events;
- other configuration values or metadata depending on events and runtime version.

In particular, custom events can record any string or field put there by the developer. If an event logs emails, customer IDs, full URLs, request payloads, access tokens, or authorization headers, those values appear in the recording and any text exports.

Never assume JFR automatically redacts sensitive data. Nor should you assume every JFR file contains passwords; actual contents depend on enabled events, JDK version, and custom events. The safe approach is to treat recordings as potentially sensitive and inspect them before sharing.

## 10. Principles for Protecting Data in Recordings

### 10.1. Collect Minimal Data

Enable only the events needed to answer the question:

- Disable unrelated events.
- Enable stack traces only on events needing source attribution.
- Set thresholds to filter out insignificant events.
- Bound duration and storage size.
- Avoid recording request/response bodies or user data in custom events.

Minimal collection cuts both overhead and the sensitive data surface you must protect.

### 10.2. Never Record Secrets in Custom Events

Unsafe example:

~~~java
@Name("com.acme.Request")
@Label("Request")
class RequestEvent extends Event {
    String userEmail;
    String authorizationHeader;
    String requestBody;
}
~~~

These fields can contain personal data, credentials, or business payloads. Keep them out of JFR events.

Replace with bounded, non-sensitive metadata:

~~~java
@Name("com.acme.Request")
@Label("Request")
@Category({"Acme", "Service"})
class RequestEvent extends Event {
    String operation;
    String outcome;
    int statusCode;
}
~~~

Record only fields strictly needed to classify the event. If you must correlate events with logs, consider a random or internally approved pseudonymized correlation ID; never use email addresses, phone numbers, or access tokens as correlation IDs.

### 10.3. Do Not Use Simple Hashes to Anonymize Low-Entropy Data

Hashing an email, phone number, or customer ID does not automatically anonymize it. When the input space is small or predictable, anyone holding the recording can brute-force hashes to recover original values.

If cross-event correlation is required:

- use a random ID meaningful only within the recording or investigation session;
- or use tokenization/HMAC with an externally managed key per organizational security policy;
- never embed keys, secret salts, or mapping tables inside JFR files.

Use only approved pseudonymization techniques for real data.

### 10.4. Protect Files in Storage and Transit

JFR files and text exports from JFR should be handled as internal operational data:

- store in a dedicated directory readable only by authorized investigators;
- avoid placing files in web roots, public folders, or world-readable temp directories;
- apply disk or file encryption per environment policy;
- transfer over secure channels and verify recipients;
- never attach files to public issues, public chats, or improperly scoped tickets;
- avoid uploading files into artifact stores with uncontrolled retention.

JFR does not encrypt recording files simply because the application uses TLS. Transport security and data-at-rest protection are separate concerns.

### 10.5. Set Retention and Delete on Time

Define upfront:

- retention duration for background recordings;
- retention duration for incident recordings;
- who is responsible for review and deletion;
- how copies in download folders, analyst laptops, and tickets are handled;
- how deletion is verified per policy.

`maxAge` and `maxSize` govern data inside rolling recordings; they do not delete already-dumped files, downloaded copies, or text exports created with `jfr print`.

### 10.6. Review Before Sharing

Before sending JFR to colleagues or a vendor:

1. Confirm the recipient and analytical purpose.
2. Capture a minimal-scope recording if the incident is reproducible.
3. Inspect custom events and string fields.
4. Run `jfr summary` and `jfr print` on a protected copy to check emitted event types and values.
5. Strip or replace sensitive fields using an approved procedure.
6. Share over an access-controlled channel.
7. Set retention deadlines and delete copies after completion.

Do not binary-edit a JFR file with ad-hoc tools to “erase” a field. If a recording already captured a secret, assume that secret was exposed wherever the file was copied; follow incident response procedures, including rotating credentials if needed.

## 11. Designing Safe Custom JFR Events

Custom events let applications record business milestones or processing timings without logging full payloads.

Example:

~~~java
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.acme.PaymentOperation")
@Label("Payment Operation")
@Description("Processing duration of a payment operation")
@Category({"Acme", "Business"})
class PaymentOperationEvent extends Event {
    @Label("Operation")
    String operation;

    @Label("Outcome")
    String outcome;

    @Label("HTTP Status")
    int statusCode;
}
~~~

Using the event:

~~~java
PaymentOperationEvent event = new PaymentOperationEvent();
boolean recordingEnabled = event.isEnabled();
if (recordingEnabled) {
    event.operation = "authorize";
    event.begin();
}

try {
    authorizePayment();
    event.outcome = "success";
    event.statusCode = 200;
} catch (RuntimeException e) {
    event.outcome = "failure";
    event.statusCode = 500;
    throw e;
} finally {
    if (recordingEnabled) {
        event.end();
        event.commit();
    }
}
~~~

This event records operation, outcome, and status code. It does not record card numbers, security codes, tokens, emails, request bodies, or payment details.

### 11.1. Checking Whether an Event Is Enabled

To avoid building and committing events when not recorded, check `isEnabled()`:

~~~java
PaymentOperationEvent event = new PaymentOperationEvent();
boolean recordingEnabled = event.isEnabled();
if (recordingEnabled) {
    event.operation = "authorize";
    event.begin();
}

try {
    authorizePayment();
} finally {
    if (recordingEnabled) {
        event.end();
        event.commit();
    }
}
~~~

In production code, keep `begin`/`end` logic consistent: never call `end` if `begin` was never invoked. You can encapsulate creation and commit in a helper or cleaner structure when handling multiple branches.

### 11.2. Avoid Recording Re-Identifiable Data

Even fields like `customerId`, `accountId`, `tenantName`, or `orderReference` can be sensitive depending on policy and joinability with external sources.

Before adding a custom event field, ask:

- Is this field strictly needed to answer the diagnostic question?
- Can it be replaced by an operation type, status code, size bucket, or ephemeral ID?
- Could its values contain tokens, PII, user input, or free-form text?
- Who will be able to read the JFR file and its exports?

Never pass arbitrary objects or large payloads into custom events. Prefer numbers, booleans, enums, or bounded strings.

## 12. Inspecting Recordings and Controlled Exporting

### 12.1. Checking Summary First

~~~bash
jfr summary incident.jfr
~~~

Summary shows which events appear and their counts. This is the first step to ensure the recording does not contain broader data than intended.

### 12.2. Exporting Only Needed Events

~~~bash
jfr print --events jdk.GarbageCollection incident.jfr
~~~

Export only relevant event groups instead of dumping an entire recording to the console or a text file. Exported text can still contain sensitive metadata.

### 12.3. Limiting Output

When sharing is required, produce an analysis artifact containing only:

- the relevant time window;
- required events;
- aggregate figures;
- reviewed stack traces;
- necessary environment details.

If your analysis tool supports time or event filters, apply them to narrow scope. Never place an entire recording in public storage simply because the file is compressed.

## 13. Verifying Overhead and Data Quality

After creating a new configuration, verify both runtime cost and analytical usefulness:

### 13.1. Measuring Overhead

Compare the workload before and after enabling the recording:

- throughput;
- p50/p95/p99 latency;
- CPU usage;
- allocation rate;
- GC pauses and GC CPU;
- recording size per minute;
- JFR disk write I/O.

Test under representative load. A brief recording on a developer laptop cannot verify production overhead.

### 13.2. Verifying the Recording Has Enough Data

An overly minimal recording may lack needed events. Check:

- are the events under investigation enabled?
- are thresholds set too high?
- does the recording span the incident timestamp?
- are stack traces enabled on the needed events?
- did `maxAge`/`maxSize` evict old data before dumping?
- is the sampling period fine-grained enough?

If data is missing, make targeted adjustments and re-record. Do not turn on all events at once as a knee-jerk reaction.

### 13.3. Using JFR Alongside Other Observability Sources

JFR complements metrics, logs, traces, and heap dumps:

| Source | Strongest At |
| --- | --- |
| Metrics | Aggregate trends, alerting, historical comparisons. |
| Application logs | Business context and messages explicitly emitted by the app. |
| Distributed traces | Request path across multiple services. |
| JFR | Fine-grained JVM, thread, GC, allocation, I/O, and custom events. |
| Heap dump | Live retained objects and paths to GC roots at dump time. |

No single source replaces all others. Pick tools to match the question and protect all diagnostic data under consistent security policies.

## 14. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Recording too large | Running `profile` too long, too many events, or stack traces | Use `default` for baseline, cap duration/`maxSize`/`maxAge`, enable events selectively |
| Needed events missing | Events disabled, threshold too high, or recording missed incident window | Check metadata/settings, lower thresholds selectively, re-record |
| Recording overhead higher than expected | Overly detailed events, dense sampling, or too many stack traces | Measure workload, disable unrelated events, reduce detail |
| JFR file lost older data | Rolling recording hit `maxAge` or `maxSize` | Adjust retention and dump earlier in incident workflow |
| Failed to create recording file | Directory missing, lacks permissions, or out of disk | Verify path, ACL/permissions, disk space, and `jcmd` output |
| JFR file contains unshareable data | I/O events, stack traces, or custom events contain sensitive metadata | Restrict readers, inspect recording, build minimal export, follow data policy |
| Secrets appeared in custom events | Code directly logged tokens, payloads, or personal info | Stop recording that field, fix event schema, treat old recordings as potentially exposed |
| `jfr print` output exposes more than expected | Exported all events and metadata fields | Export only needed events and review output before sharing |
| Unsure whether to use `default` or `profile` | Investigation question not yet defined | Identify symptoms; start with baseline, escalate briefly if data is insufficient |
| JFR has no stack traces | `stackTrace` setting disabled or unsupported by event | Check settings for that exact event; enable stack traces only where needed |
| `.jfc` config not applied | Bad path, invalid config, or typo in event/setting name | Check file, runtime metadata, and startup output |
| Treating JFR as a complete audit log | Events may be sampled, threshold-filtered, or disabled | Use dedicated audit logging for compliance; JFR is for diagnostics |

## 15. Pre-Production Recording Checklist

Before rolling out in production, clearly confirm:

- Which operational question needs answering?
- Can `default` settings be used, or is `profile`/custom required?
- Which events are genuinely necessary?
- Are thresholds, periods, and stack traces appropriate?
- How long will the recording run, and what are `maxAge`/`maxSize` limits?
- Where will the file be stored, and who has read access?
- Could the file expose sensitive hostnames, paths, stack traces, IDs, or custom fields?
- Is pseudonymization or field removal needed before sharing?
- Is there an inspection, transfer, storage, and deletion procedure?
- Has overhead been measured under representative workload?

Include this checklist in your operations runbook so incident responders can capture recordings quickly while safeguarding data.

## 16. Self-Practice Exercises

### Exercise 1 — Choosing Recording Levels

A production service needs to retain visibility into GC and thread activity over the last six hours. When an incident hits, the team can enable `profile` for three minutes.

Select a baseline configuration and an incident configuration. Explain why detailed `profile` should not run continuously if `default` suffices for baseline.

### Exercise 2 — Choosing Thresholds

An API has a p99 target of 300 ms. The team suspects slow socket reads. Propose how to pick an initial threshold and refine it after reviewing data. Why should you avoid defaulting thresholds to 0?

### Exercise 3 — Protecting Custom Events

A developer wants to record `userEmail`, `authorizationHeader`, `requestBody`, `tenantId`, and `duration` in a custom event. Identify which fields must be removed, which can be replaced with less sensitive metadata, and why.

### Exercise 4 — Troubleshooting Missing Events in a Recording

A JFR file lacks socket read events. List what to inspect: event settings, thresholds, recording duration, event metadata, and how the recording was dumped.

### Exercise 5 — Sanitizing a JFR File Before Sending

A vendor needs a recording to help investigate an incident. Outline a workflow covering recipient verification, event selection, data inspection, producing a minimal artifact, secure transfer, and setting retention.

### Exercise 6 — Distinguishing JFR and Audit Logs

Explain why JFR should not be the sole source for compliance auditing requiring every transaction to be logged. Describe the proper roles of JFR, application logs, and audit logs.

## 17. Key Takeaways for Choosing Observability and Protecting JFR

- Use `default.jfc` for continuous baselines; consider `profile.jfc` or custom settings for short-term investigations.
- Choose events driven by diagnostic questions; do not enable every event by default.
- Tune `threshold`, `period`, and `stackTrace` intentionally, since higher detail raises overhead and file size.
- Set `duration`, `maxAge`, and `maxSize` so recordings do not consume resources indefinitely.
- Use `jcmd` to start/check/dump/stop recordings and `jfr summary`, `jfr metadata`, and `jfr print` to inspect data.
- JFR can contain hostnames, paths, stack traces, connection metadata, and custom event payloads; never assume files are automatically scrubbed of sensitive data.
- Never record passwords, tokens, authorization headers, request bodies, or PII in custom events.
- Favor minimal metadata, bounded categorical values, and approved ephemeral IDs.
- Protect JFR files and text exports using access controls, encryption, secure transport, and clear retention limits.
- Inspect recordings before sharing; if a secret was recorded, follow incident response procedures and rotate credentials when necessary.
- Measure overhead on representative workloads and verify recordings contain enough events to answer your question.
- JFR serves runtime diagnostics; it does not replace metrics, distributed tracing, or complete audit logs.

### References

- [Java SE 17 JFR Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-runtime-guide.html) — managing recordings at runtime.
- [Java SE 17 JFR Configuration](https://docs.oracle.com/en/java/javase/17/jfapi/configuration.html) — event settings and JFC files.
- [Java SE 17 JFR API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — `Recording`, `Event`, `EventSettings`, and custom events.
- [Java SE 17 jcmd documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html) — `JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` commands.
- [Java SE 17 jfr tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html) — `summary`, `metadata`, `print`, and operations on recording files.
- [JEP 328: Flight Recorder](https://openjdk.org/jeps/328) — JFR architecture and goals.
- [JEP 349: JFR Event Streaming](https://openjdk.org/jeps/349) — JFR event streaming.
