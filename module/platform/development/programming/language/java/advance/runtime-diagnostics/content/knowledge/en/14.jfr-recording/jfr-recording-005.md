# 14.5 Choosing `default.jfc`, `profile.jfc`, or a Custom Event Configuration Based on Your Question

## Learning Objectives

**Java Flight Recorder (JFR)** is a tool for recording timestamped events from the JVM and Java applications. Choosing the right recording configuration determines whether you have the data to answer your diagnostic question, while also affecting CPU usage, file size, and system interference.

This lesson focuses on three choices: **`default.jfc`**, **`profile.jfc`**, and **custom `.jfc` configurations**, in the context of capturing JFR recordings on HotSpot JDK 17 and later. After this lesson, you will be able to:

- Match the **diagnostic question to be answered** with an appropriate event group and collection level, rather than enabling every event.
- Explain why `default.jfc` is typically suited for long-term observation, `profile.jfc` is suited for a bounded profiling window, and when you need to create a custom `.jfc`.
- Tune event settings such as `enabled`, `threshold`, `period`, and `stackTrace` while keeping measurement overhead under control.
- Create configurations with `jfr configure` or JDK Mission Control (JMC), run them with `-XX:StartFlightRecording` or `jcmd JFR.start`, and inspect `.jfr` files.
- Avoid drawing wrong conclusions when events do not appear, samples are too sparse, or the measurement config alters application characteristics.

> No single template is always right for every application. **Your question, observation duration, event frequency, workload, and overhead budget** determine the choice. Preset-enabled events and supported options may differ across JDK versions; verify against the running version.

## 1. Two Different File Types: `.jfc` and `.jfr`

- **`.jfc` (JFR Configuration)**: an XML configuration file describing which events are collected, thresholds/periods/stack traces, and template-supported controls. The JDK typically ships `default.jfc` and `profile.jfc` under `<JAVA_HOME>/lib/jfr/`.
- **`.jfr` (Flight Recording)**: a binary recording file produced by JFR containing actual events, metadata, and information needed for analysis. Inspect using `jfr summary`, `jfr print`, or open in **Java Mission Control**.

Thought process:

~~~text
Diagnostic question
       |
       v
Select events + sampling rate + threshold + duration
       |
       v
Choose default.jfc / profile.jfc / custom.jfc
       |
       v
Start JFR -> write .jfr file -> verify events -> analyze
       |
       v
Evidence-based conclusion or adjust config and re-measure
~~~

`settings=default` and `settings=profile` in JFR commands are shorthand names for presets bundled with the JDK. For a custom template, pass `settings=locks.jfc` or an absolute path to a file accessible by the **target JVM**. Do not confuse configuration names with recording names.

## 2. Quick Decision Rules

| Situation / Question | Start With | Why | Signs You Need to Adjust Configuration |
| --- | --- | --- | --- |
| Want to retain history to inspect a rare incident | `default.jfc`, continuous recording with size/age caps | Low cost, general JVM, GC, thread, and system info | Not enough events or stacks to pinpoint cause |
| High CPU; need to know which methods consume CPU time | `profile.jfc` over a sufficiently long measurement window | Richer profiling/sampling information | Too few samples, no useful stacks, or excessive overhead |
| Suspect many temporary objects; need to find allocation hot spots | `profile.jfc`, then inspect allocation events | Extra data geared toward profiling | Sampling lacks resolution; need to enable/tune specific events |
| Large latency from monitor/park waits | `default.jfc` for broad observation, then `custom.jfc` lowering related thresholds | Captures only the waits of interest | Default threshold misses 5–20 ms waits |
| A thread waits too long on file/socket I/O | `default.jfc` or custom for `jdk.FileRead`, `jdk.SocketRead`, etc. | Separates I/O wait time from CPU time | I/O events disabled or threshold too high |
| Investigating frequent exceptions | **Short-lived** custom config with appropriate exception event limits | An event *per exception* can be noisy and expensive | Huge file, CPU spike, insufficient stack detail |
| Need basic footprint/GC trends over a long period | `default.jfc` | Suited for investigating overall trends | Missing detailed GC phase events or specific allocation data |

The rows above are **starting points**, not guarantees that every event is pre-enabled. Always open the preset from the exact JDK or verify effective settings; never assume "profile" means every allocation or every Java method invocation is captured.

### Three Things to Note Before Pressing Start

1. **A testable question:** "p99 rose because threads waited on the `PaymentCache` monitor for over 10 ms" is better than "the app is slow."
2. **Time range and load:** Do you need 10 minutes of history before the error, or the exact 60 seconds reproducing the error? Record RPS, concurrency, input data, and when symptoms appeared.
3. **Measurement cost budget:** CPU, file size, I/O, latency, and recording retention. If the system is near saturation, an event-heavy template can perturb what you are measuring.

## 3. `default.jfc` — Low-Overhead Observational Baseline

`default.jfc` is typically designed to collect a wide set of useful metrics and events at **low overhead**, making it suitable for long-term recording or always-on application observation. Per Oracle guidance, it is the default choice for continuous recording; overhead is usually low (often cited around under 1% in measured configurations/conditions), **not a guarantee for every system**.

Use `default` when you want a GC timeline, thread activity, CPU load, and common JVM events while the specific cause is still unknown. Some events have thresholds or periods, so very brief operations are not recorded. Some detailed events (such as potentially voluminous allocation events) may be throttled or disabled to keep cost low.

### 3.1 Continuous Capture on a Running Process

~~~sh
# Find the PID of the right JVM (same user/namespace with attach permission):
jcmd -l

# Start continuous recording; cap retained size and age.
jcmd <pid> JFR.start name=baseline settings=default disk=true maxage=1h maxsize=256m

# Verify the recording is still active:
jcmd <pid> JFR.check

# When an incident occurs, dump the most recent 15 minutes (if data exists):
jcmd <pid> JFR.dump name=baseline filename=baseline-on-incident.jfr maxage=15m

# Stop when collection is no longer needed:
jcmd <pid> JFR.stop name=baseline
~~~

`maxage` and `maxsize` bound the volume of data retained in the recording; a dump only contains data still present within retention. **They do not guarantee a full 15 minutes** if events are heavy and older data was evicted sooner. Dump files are written by the target JVM: for container/remote JVMs, `filename` is a path in the JVM's environment, not automatically on the machine running `jcmd`.

For short-lived startup/shutdown applications, you can enable recording at JVM launch:

~~~sh
java -XX:StartFlightRecording=settings=default,filename=startup.jfr,dumponexit=true -jar app.jar
~~~

Note that `dumponexit=true` requires the JVM to exit to complete the dump in this example; for long-running servers, use `jcmd JFR.dump` when you need a snapshot without stopping the application.

### 3.2 When Is `default` Not Enough?

For instance, suppose application p99 rises due to many lock waits of **around 5–15 ms**, while the current template sets `jdk.JavaMonitorEnter#threshold=20ms`. Seeing zero 5–15 ms lock events is completely expected; concluding "there is no lock contention" would be wrong. Lower that exact threshold in a **controlled measurement window**, re-capture, and inspect the change in event count and overhead.

## 4. `profile.jfc` — Higher Detail in a Short Window

`profile.jfc` typically enables or increases the frequency of profiling data such as execution sampling and allocations, at the trade-off of higher overhead and recording volume than `default`. It is suited for investigating CPU hot spots, allocation hot spots, and bottlenecks when you have a clear reproduction window.

~~~sh
# Profile for 60 seconds and write to a file:
jcmd <pid> JFR.start name=cpu-investigation settings=profile duration=60s filename=cpu-profile.jfr
~~~

Once the duration elapses, inspect the file and actual events:

~~~sh
jfr summary cpu-profile.jfr
jfr print --events jdk.ExecutionSample --stack-depth 20 cpu-profile.jfr
~~~

Do **not** read `jdk.ExecutionSample` counts as "number of method executions", "CPU percent", or a complete call graph. These are **samples**, not per-invocation traces. Few samples may reflect a short capture, threads not frequently running on CPU, too large a period, or sampling not being enabled; analysis must stick to actual events and context.

For allocations, inspect `jdk.ObjectAllocationSample`. This event is sampled and typically carries an estimated weight; raw event counts do not equal total objects or bytes allocated. For micro-level tasks, use JMH `-prof gc` or an appropriate allocation profiler to cross-check B/op.

### 4.1 Measuring the Right Window

- Capture while the application is **under the load causing the issue**, not merely while idle.
- Record long enough for samples to be meaningful; a recording of a few milliseconds may lack the events you need.
- Avoid comparing `profile` and `default` from **two different workloads** to conclude how optimization or GC changed.
- Use the same JDK/collector/config for A/B comparisons, and record the event settings; the name `profile` does not guarantee the template did not change across JDK releases.

## 5. Custom `.jfc` — Collect Only What Answers the Question

Custom configs fit when neither preset matches your needs: you need a disabled event enabled, a different threshold, another sampling period, added stack traces, or a noisy event group trimmed down. **Never assume enabling more events yields better diagnostics**: millions of irrelevant events can strain files/I/O and obscure the signal.

### 5.1 Four Foundational Settings

| Setting | Example | Meaning and Trade-off |
| --- | --- | --- |
| `enabled` | `jdk.JavaMonitorEnter#enabled=true` | Allows the event to be recorded when triggered; disable events to cut data |
| `threshold` | `jdk.JavaMonitorEnter#threshold=5ms` | Only records duration events **meeting/exceeding** the threshold; lowering increases event count and volume |
| `period` | `jdk.ExecutionSample#period=20ms` | For periodic/sampling events supporting `period`, the sampling interval; shorter period increases resolution and cost |
| `stackTrace` | `jdk.JavaMonitorEnter#stackTrace=true` | Captures call stack if supported by the event; helps locate call sites at extra data/cost |

Some events have specialized settings such as sampling throttle; **not every event supports all settings**. `threshold` only makes sense for appropriate duration events; it is not an "events-per-second rate limit." A sampling `period` does not guarantee every thread is sampled at an exact 20 ms cadence. Use only settings supported by the event and inspect the resulting template.

Inside a `.jfc` file, each event has a full name and `<setting name="...">...</setting>` elements. Templates can also define controls that back presets. Editing event settings in JFR configures the **recording**; it does not alter lock logic, GC behavior, or program execution speed beyond instrumentation overhead.

### 5.2 Creating a Template for a Lock Contention Question

Hypothesis: p99 rose and we need to find monitor waits of at least 5 ms along with Java call sites. With `jfr configure` on a supporting JDK (on JDK 17+ you can check via `jfr help configure`), create a new template **based on default**:

~~~sh
jfr configure --input default.jfc --output locks.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms' 'jdk.JavaMonitorEnter#stackTrace=true'
~~~

The command preserves the remaining settings from `default.jfc` and replaces the three settings on the named event without modifying the default template. On a supporting JDK, event setting expressions follow `<event-name>#<setting-name>=<value>`; quote expressions containing `#` when your shell requires it. Check:

~~~sh
jfr help configure
~~~

You can open `locks.jfc` to confirm `jdk.JavaMonitorEnter` actually has `enabled=true`, `threshold=5 ms`, and `stackTrace=true`. **Do not assume the file succeeded just because the command exited cleanly** if you are on a different JDK version or an event was renamed.

Start a recording with the custom template:

~~~sh
# In the directory containing locks.jfc, or use the full path to the .jfc file:
jcmd <pid> JFR.start name=lock-study settings=locks.jfc duration=60s filename=locks.jfr

# After 60 seconds:
jfr summary locks.jfr
jfr print --events jdk.JavaMonitorEnter --stack-depth 30 locks.jfr
~~~

This example additionally captures monitor contention waits around 5 ms and above; if a workload has thousands of waits per second, file size and overhead can grow sharply. If there are too many events, raise the threshold or shorten the window. Focus on **duration, monitorClass, thread, previousOwner, stackTrace, and timestamps**—do not draw conclusions from raw count alone.

### 5.3 Customizing to Find Allocation Hot Spots

When the current profile does not yield enough allocation samples, you can customize sampling events (if supported on the target JDK):

~~~sh
jfr configure --input profile.jfc --output allocations.jfc 'jdk.ObjectAllocationSample#enabled=true' 'jdk.ObjectAllocationSample#stackTrace=true'
jcmd <pid> JFR.start name=alloc-study settings=allocations.jfc duration=90s filename=allocations.jfr
~~~

Inspect:

~~~sh
jfr summary allocations.jfr
jfr print --events jdk.ObjectAllocationSample --stack-depth 30 allocations.jfr
~~~

`jdk.ObjectAllocationSample` is sampled; analysis tools can use sample weights and event metadata to estimate bytes by stack. If you need exact bytes per unit of work, pair with JMH benchmarks or other allocation metrics. TLAB-level events (`jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB`) have their own collection semantics and costs and should not be enabled wholesale for long recordings without assessing impact.

### 5.4 Customizing for I/O or Exceptions

For socket/file latency, you can choose `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, and `jdk.FileWrite`, setting `threshold`/`stackTrace` to suitable levels. You must distinguish **threads waiting on I/O** from hot CPU; a CPU sampler will not fully explain waiting time.

For frequent exceptions, `jdk.JavaExceptionThrow` can emit many events and stacks, causing noticeable overhead. Test with a short window, identify exception types, consider aggregate counts first, and enable detailed events only when justified. Do not configure lock thresholds on exception events: each event has its own valid settings.

When investigating GC, start with `jdk.GarbageCollection`, `jdk.GCPhasePause`, and `jdk.GCHeapSummary`. Enable finer-grained GC phase/region events only when existing timelines and pauses cannot answer your question. There is no single uniform detailed event set across every collector and every JDK.

### 5.5 Creating Templates via Java Mission Control

If you prefer a UI to pick templates or browse event groups:

1. Open Java Mission Control (JMC) and the JFR recording templates manager; locate `default.jfc`/`profile.jfc` matching your running JDK.
2. **Copy** the base template, adjust event groups and `enabled`/`threshold`/`period`/`stackTrace` for your goal, and save under a distinct `.jfc` name.
3. Review the modified settings and version the template alongside `.jfr` results so experiments are reproducible.

JMC menu names may vary by version. For easy review and reuse, keep `locks.jfc` version-controlled in your project; **never directly edit** `default.jfc` or `profile.jfc` inside the JDK directory.

## 6. Runnable Java 17+ Experiment: Seeing the Effect of Lock Configuration

The program below deliberately creates a **monitor contention** episode synchronized via `CountDownLatch`, followed by short-lived object allocations. The goal is to see a custom `locks.jfc` capture the **lock event** and stack without relying on scheduler luck.

Save with the exact filename **JfrSettingsDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JfrSettingsDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch LOCK_HELD = new CountDownLatch(1);
    private static volatile byte[] last;

    public static void main(String[] args) throws Exception {
        Thread holder = new Thread(() -> {
            synchronized (LOCK) {
                LOCK_HELD.countDown();
                try {
                    Thread.sleep(250);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "holder");

        holder.start();
        LOCK_HELD.await();
        synchronized (LOCK) {
            System.out.println("CONTENTION_FINISHED");
        }
        holder.join();

        for (int i = 0; i < 100_000; i++) {
            byte[] data = new byte[256];
            data[0] = (byte) i;
            last = data;
        }
        System.out.println("ALLOCATION_FINISHED");
        Thread.sleep(3_000);
        System.out.println("DONE");
    }
}
~~~

`CountDownLatch` ensures the `holder` thread acquires the monitor before `main` attempts to enter the `synchronized` block. While holding the lock, `holder` sleeps for 250 ms, forcing the `main` thread to wait on the monitor. The `volatile last` field escapes the array from local scope to prevent the JIT from eliminating all allocations; that does not mean every array stays alive until program exit.

**Commands on a JDK supporting `jfr configure`:**

~~~sh
javac --release 17 JfrSettingsDemo.java
jfr configure --input default.jfc --output locks-demo.jfc 'jdk.JavaMonitorEnter#enabled=true' 'jdk.JavaMonitorEnter#threshold=5ms' 'jdk.JavaMonitorEnter#stackTrace=true'
java -XX:StartFlightRecording=settings=locks-demo.jfc,filename=locks-demo.jfr,dumponexit=true JfrSettingsDemo
jfr summary locks-demo.jfr
jfr print --events jdk.JavaMonitorEnter locks-demo.jfr
~~~

The stdout **printed by the Java program itself** is:

~~~text
CONTENTION_FINISHED
ALLOCATION_FINISHED
DONE
~~~

The JVM may print additional `[info][jfr,startup]` lines when starting the recording. One execution on HotSpot JDK 24 recorded a `jdk.JavaMonitorEnter` event with a duration of around 251 ms and a stack at `JfrSettingsDemo.main`; **exact timings, event counts, and trace addresses are not fixed** across machines/JVMs. Focus on verifying that the `.jfr` file contains the lock event on thread `main` with the right stack, and remember that any allocation samples present are still not a full object trace.

In terms of Java language syntax, this example runs on JDK 17+ (tested with `javac --release 17`). The custom template generation command and JFR output were checked on JDK 24; if your JDK does not support `jfr configure` or uses different event names, use JMC/the equivalent `.jfc` configuration for that JDK and verify the actual event list.

## 7. Verify the Recording **Before** Analyzing

The existence of a `.jfr` file does not prove the needed data was recorded. Follow this order:

~~~sh
# 1. What data, duration, and size exist?
jfr summary locks-demo.jfr

# 2. Which event names/metadata are in the file?
jfr metadata locks-demo.jfr

# 3. What is in the target event data?
jfr print --events jdk.JavaMonitorEnter --stack-depth 30 locks-demo.jfr

# 4. Inspect the effective settings recorded by JFR (when available):
jfr print --events jdk.ActiveSetting locks-demo.jfr
~~~

`jfr summary` lists counts of recorded events; it does not directly print every requested config option. `jdk.ActiveSetting` helps verify effective settings at capture time; its presence depends on the actual recording. Inspect details in JMC to filter timelines, group by thread/stack/duration, and correlate latency milestones.

**If the expected event is missing**, check in order:

1. Is this file from the **right PID, right recording name, and right time window**? The JFR file may have been written inside a container rather than on the host.
2. Was the event enabled in the effective settings? Does that event name exist on the current JDK?
3. Did the test/workload actually trigger the condition? For example, `jdk.JavaMonitorEnter` records monitor contention only; entering an uncontended monitor emits no wait event.
4. Was `threshold` too high, `period` too sparse, the recording too short, or did sampling miss it?
5. Were excessive events evicted by size/retention limits, or did the dump only keep the tail? Cross-check timestamps and load conditions.

**No event in the file does not mean the event never occurred.** It is merely the outcome under the current configuration, time span, and measurement conditions.

## 8. Understanding Event Setting Trade-offs

### 8.1 Threshold: Sensitivity vs. Event Volume

Suppose a service experiences 10,000 monitor waits per second with this distribution:

- 9,800 waits under 1 ms;
- 180 waits from 1 to under 5 ms;
- 19 waits from 5 to under 20 ms;
- 1 wait of 20 ms or more.

With `threshold=20ms`, you might see **around 1 event/s**; with `threshold=5ms`, **around 20 events/s**; with `threshold=0ms`, the file could record nearly 10,000 events/s if no other limit applies. This is a hypothetical illustration; timing, collector, and event type make real numbers differ. Lowering the threshold does not "create contention"—it changes how much of the contention you see and the collection cost.

Do not blindly set `threshold=0ms` on every latency event if your hypothesis concerns operations over 10 ms.

### 8.2 Period: Sampling Rate and Hot Spot Visibility

For example, `jdk.ExecutionSample#period=20ms` aims to sample more frequently than `period=100ms` under the same conditions, making it more likely to catch execution frames while potentially adding overhead and file size.

- **Many stack samples** from method A suggest A appeared frequently during the observed window, to be interpreted alongside CPU state and sample cost.
- **Absence of method B** does not prove B never ran: B may be too short, rare, inlined, or missed by sampling timing.
- Do not infer exact time spent directly from sample counts unless event mechanics, duration, and sampling bias have been validated.

With a recording of only a few thousand milliseconds, sample counts may be lower than expected. Choose `period` and `duration` after determining the required resolution, then verify in the file.

### 8.3 Stack Trace: Causal Context Comes at a Cost

`stackTrace=true` helps answer "**where** did the event happen?", especially for locks, I/O, or allocations. However, high-frequency events with stacks can swell file size dramatically. If you only need overall frequency or latency, you can omit stack traces on events that do not require call sites.

### 8.4 Overhead Can Perturb the Problem Under Investigation

Sampling, exception tracing, many short events, and heap/object leak analyses each carry different costs. Modes that gather GC-root paths or heap statistics can cause significant pauses. When measuring very small latencies, always compare overhead and application metrics under the same workload. Event data that is technically accurate can still be **unrepresentative** if collection altered the workload, CPU contention, or processing speed.

## 9. Iterative Practical Configuration Workflow

1. **State the question:** "Did user CPU rise?", "How long did threads wait on monitors?", "Were socket reads slow?", "Did allocation B/op increase?", "Did GC pauses cause p99?"
2. **Pick the minimum signals:** event names, needed fields/stacks, system metrics to cross-check, and timestamps.
3. **Choose a baseline:** start with `default` for long/broad observation; `profile` for profiling in a bounded window; `custom` when a needed event/threshold/period is missing.
4. **Set a budget:** `duration`, `maxsize`/`maxage`, file location, I/O bounds, and acceptable cost. For rare incidents, keep history with `default`; for deep dives, capture a separate short `profile`/`custom` window.
5. **Verify early:** check `JFR.check` while recording and `jfr summary`/`jfr metadata`/`jfr print` after dumping; do not spend an hour recording only to discover the event was off.
6. **Analyze against the original question:** filter target events; align timestamps with load/latency/GC/CPU, inspect stacks and durations. Formulate falsifiable hypotheses rather than merely describing charts.
7. **Iterate one change at a time:** if threshold is too high, lower it on that event; if samples are sparse, increase duration or tune period; if overhead is high, drop unneeded events and raise thresholds. Record which template version was used so runs stay comparable.

### Example of Three Different Captures for One Incident

An application has request p99 jumping from 200 to 900 ms several times a day:

- **Run 1 — Continuous `default.jfc`:** keeps 1 hour of history, dumps 15 minutes around a p99 spike. Observes no matching GC pauses, but sees signs of many threads waiting.
- **Run 2 — 60-second `profile.jfc`:** has CPU samples, yet most requests are waiting rather than consuming CPU. Do not conclude a method with few CPU samples is unrelated.
- **Run 3 — `locks.jfc` with 5 ms threshold:** finds `OrderService.reserve()` stacks repeatedly waiting on a monitor because expensive work sits inside a `synchronized` block. After changing the synchronization design, p99 drops under comparable load; that is stronger evidence than merely seeing many lock events.

The scenario above illustrates reasoning, not benchmark numbers or a mandatory three-run rule. When appropriate, a single well-targeted custom recording can be enough.

## 10. Common Pitfalls

1. **"`default.jfc` is lightweight, so it has no useful information."** False: for timeline, GC/threads, and rare incident questions, it is often a strong first step.
2. **"`profile.jfc` captures all Java activity."** False: many events remain sampled or thresholded; the template is not a full instruction/method trace.
3. **"The best custom config enables every event with `threshold=0`."** False: it can sharply raise overhead and skew results.
4. **"Both files used `profile`, so raw event counts are directly comparable."** False: JDK version, duration, load, effective config, and retention may differ.
5. **"Seeing zero events in `jfr summary` proves it did not happen."** False: the event might be disabled, filtered, above threshold, in too short a file, or in the wrong window.
6. **"`jdk.ExecutionSample` counts exact method invocations."** False: samples reflect observations at sampling points, not an invocation counter.
7. **"One `jdk.ObjectAllocationSample` equals one object created."** False: sampling and sample weights must be interpreted properly.
8. **"`threshold=5ms` makes locks faster."** False: it only changes which events are recorded; observation itself still has overhead.
9. **"Passing `settings=locks.jfc` means both host and container can read the file."** False: the JVM running the recording must be able to access the template and the output path.
10. **"Seeing many events means we found the root cause."** False: event counts must be tied to durations, stacks, workload, causal chain, and before/after measurements.
11. **"Editing `default.jfc` inside the JDK is the only way."** False: create a separate copy/custom file to preserve the base preset and maintain provenance.
12. **"Opening the file in JMC is enough verification."** False: you must verify the right PID/time, effective event settings, and workload conditions.

## 11. Self-Check Questions

**Question A.** A production system slows down twice a week. You can keep a small recording running for many hours. What do you choose?

**Answer:** Start with `default.jfc` with bounded retention and size, dumping around incident timestamps. Once you know which event group is missing, schedule a short `profile` or custom recording during a reproduction window. Do not leave full allocation/exception tracing running continuously just to "have everything."

**Question B.** p99 spikes and monitor waits are 8–12 ms, yet the recording has no `jdk.JavaMonitorEnter`. Can you conclude there is no contention?

**Answer:** Not yet. Check whether the event is enabled, what its current threshold is, `stackTrace`, and whether the measurement window matches. If the threshold is 20 ms, a custom `threshold=5ms` is sensible for a controlled experiment.

**Question C.** Two recordings have 800 and 2,000 `jdk.ExecutionSample` events with durations of 20 seconds and 120 seconds respectively. Did CPU definitely increase in the second run?

**Answer:** No. Higher absolute event counts may simply reflect a longer duration, a different period, or different settings. Normalize by duration, settings, workload, and sampling interpretation.

**Question D.** When analyzing allocations, `jdk.ObjectAllocationSample` appears 500 times. Does that mean the JVM allocated exactly 500 objects?

**Answer:** No. This is a sampled event; interpret weights and sampling mechanics properly, and use an appropriate profiler, JMH, or heap metrics to verify.

**Question E.** A custom recording has lots of I/O events, yet does not explain the p99 spike. What should you do?

**Answer:** Verify you are looking at the exact failing requests and related stacks; check how much time those I/O events take, their thresholds, and workload. If uncorrelated, investigate locks, queues, GC, or other wait sources. Trim events that do not serve the hypothesis to keep measurement cost appropriate.

## Key Takeaways

- **`default.jfc`**: start here when you need history/timeline at low overhead, generally suitable for continuous recording.
- **`profile.jfc`**: for bounded profiling windows when you need more samples and hot spots.
- **`custom.jfc`**: choose when your question requires a different event, threshold, period, or stack trace; derive from a base template and verify effective settings.
- **Which events, for how long, under what conditions, at what cost?** are the four questions to ask before enabling JFR. After capturing, prove the file contains the right data before drawing conclusions.

### Official References by JDK

- Oracle Java 21, *Flight Recorder Configurations*: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Oracle Java 21, *The jfr Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 21, *The jcmd Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Dev.java, *Configuring the JDK Flight Recorder*: https://dev.java/learn/jvm/jfr/configure/
- Inside Java, *JFR Configuration Improvements*: https://inside.java/2022/06/13/sip055/
