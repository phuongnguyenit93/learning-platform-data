# 15.10 Limitations of sampling and event thresholds; temporal correlation does not prove causation

## 1. Objective: know what JFR observed before inferring why

**Java Flight Recorder (JFR)** lets you observe CPU, allocations, GC, locks, I/O, threads, and custom application events. However, a `.jfr` file is **not a complete log of every operation that occurred**. Some event types are emitted per occurrence, some appear only after exceeding a **duration threshold** (`threshold`), some are **sampled** (`sampling`), and some are emitted on a **period** (`period`). Moreover, events can be disabled, lack stack traces, fall outside the recording window, or be dropped under resource pressure.

When a JFR chart shows "GC pauses rose at the same time latency rose" or "method X took 40% of samples," separate three levels of conclusion:

1. **Observation:** what is in the data? Which event types, which samples, which timestamps, and under what configuration?
2. **Mechanistic hypothesis:** did a shared execution path, load source, or third factor drive both phenomena?
3. **Causation:** when the suspected cause is changed under reasonable controls, does the outcome actually change reproducibly?

This lesson aims to read JFR reliability accurately: distinguishing samples from call counts, spotting selection bias from event thresholds, aligning events in time without "convicting" from timestamp overlap alone, and designing falsifiable verification tests.

Technical scope: Java 17+ on HotSpot, illustrated with JDK 21. Event type names and sample settings may vary by JDK/JVM release and `.jfc` file; verify the **actual** configuration before analyzing.

## 2. Four observation modes easily conflated

| Collection mode | JFR examples | When does an event appear? | What must not be inferred |
| --- | --- | --- | --- |
| **Per-occurrence event** | `jdk.ThreadStart`, application `commit()` events | When the event is enabled and recording succeeds | That every action in the system has a matching event. |
| **Thresholded duration event** | `jdk.JavaMonitorEnter`, `jdk.ThreadSleep`, custom events with `begin()/end()` | Event duration meets the configured threshold | That absent operations never occurred. |
| **Sampling/profiling event** | `jdk.ExecutionSample`, `jdk.NativeMethodSample`, `jdk.ObjectAllocationSample` | The tool records a sampled observation of activity per the event type's policy | That sample count equals call count, allocation count, or exact total CPU time. |
| **Periodic event** | Various periodic thread/CPU/JVM statistics | Whenever a periodic collection tick comes due | That one event exists per fluctuation, or every fluctuation between ticks was seen. |

Instant, duration, periodic, and sampling events have different **denominators**. If a JDK Mission Control (JMC) table mixes multiple event types, read the event names and settings before computing frequencies or ratios.

Examples:

- 500 `jdk.ExecutionSample` events: roughly 500 execution observations captured by the recorder, **not** 500 method invocations.
- 20 `jdk.JavaMonitorEnter` events with `threshold=20 ms`: 20 **recorded** monitor waits meeting the threshold. It does not prove the entire application experienced only 20 lock contentions.
- 30 periodic events at a 1-second interval: 30 statistical ticks; it does not mean only 30 changes occurred inside the JVM.
- 0 events of a type may simply mean `enabled=false` or a high threshold; insufficient to conclude the activity was zero.

## 3. Check event settings before reading results

JFR has core settings defined in the `jdk.jfr` API:

| Setting | Meaning | Question to ask |
| --- | --- | --- |
| `enabled` | Whether to collect this event | Was the event enabled in the recording being analyzed? |
| `threshold` | Durations below the cutoff are not recorded for threshold-capable events | How many short operations were filtered out? |
| `period` | Expected interval or cadence for periodic/sampled events | Is the sampling interval fine enough to catch brief phenomena? |
| `stackTrace` | Whether to capture stack traces for the event | Are missing stack traces due to config or capture failure? |

Not every event uses all four settings. For instance, `jdk.ExecutionSample` uses a sampling policy; forcing a `threshold` on it does not turn it into a duration timer for **every** method. For duration events, `threshold` is meaningful; for instant events, it does not conjure duration data.

The `jdk.jfr` docs describe defaults *as a setting mechanism*, while **active values are determined by configuration files and overrides**. Never write in a report "the default event threshold is 0" when `default.jfc` or `profile.jfc` sets 20 ms. On JDK 21, bundled profiles typically set thresholds on events such as `jdk.JavaMonitorEnter` or `jdk.ThreadSleep` and periods on `jdk.ExecutionSample`; these values are **configuration**, not laws of the JVM.

How to inspect on a running JVM, replacing `12345` with the actual PID:

```bash
jcmd -l
jcmd 12345 JFR.check verbose=true
```

`JFR.check verbose=true` shows settings for active recordings. Once you have the output file, inspect event types:

```bash
jfr summary incident.jfr
jfr metadata incident.jfr
```

`jfr summary` gives event counts and time span in the file; `jfr metadata` gives event types and field definitions. Neither replaces knowing which `.jfc` configuration was applied. Record whether `default`, `profile`, or a custom `.jfc` path was used, plus any overrides via `JFR.start`, `-XX:StartFlightRecording`, or the `Recording` API.

## 4. Threshold: a duration filter, not the truth about all requests

Suppose five real operations had **independently measured** durations:

| Run | Duration | `threshold=0 ms` | `threshold=20 ms` | `threshold=50 ms` |
| --- | ---: | --- | --- | --- |
| A | 3 ms | Qualified | Filtered out | Filtered out |
| B | 9 ms | Qualified | Filtered out | Filtered out |
| C | 25 ms | Qualified | Qualified | Filtered out |
| D | 32 ms | Qualified | Qualified | Filtered out |
| E | 70 ms | Qualified | Qualified | Qualified |

At a 20 ms threshold, JFR can record only the **three slow events** in this example. Actual invocations remain **five**. The captured data suffers from **selection bias**: observations skew toward longer operations.

If you compute an average from the three surviving events:

```text
TRUE average of 5 operations = (3 + 9 + 25 + 32 + 70) / 5 = 27.8 ms
Average of 3 events >= 20 ms = (25 + 32 + 70) / 3 ≈ 42.3 ms
```

The `42.3 ms` figure is a **conditional average over recorded events**, and must never be reported as average latency across all requests. Conversely, counting "three slow events" does not prove only three requests occurred or that the service handled three requests in total.

**Key consequences:**

- `threshold=20ms` is useful when your goal is **diagnosing abnormally slow calls**, not measuring the full latency distribution.
- Never divide slow event count by total JFR event count and call it "slow request rate": the denominator must be **actual total requests** from an appropriate independent metric/counter.
- Lowering a threshold from 50 ms to 10 ms increases event counts even when the application **did not slow down at all**.
- With stack traces enabled, lowering thresholds too aggressively increases write cost and data volume. Choose thresholds per question and benchmark overhead.
- An event must finish and be written within the recording window; work still in flight when the file closes may not yield a complete event for analysis.

Boundary values right at the threshold and small duration formatting can be affected by timestamp resolution. Do not interpret a few microseconds' difference as a major behavioral shift amid scheduler/GC jitter.

## 5. Sampling: point-in-time snapshots are not a call inventory

With **execution sampling**, the recorder inspects thread/stack states periodically to uncover **hot paths**. A very fast call may never appear in any sample. A method holding CPU for a long time may appear in many samples even if called only once.

### Thought experiment

A thread runs sequentially:

```text
0 ms        2 ms                  20 ms
| method A |------- method B -------|
           ^                       ^
        A very short            B relatively long

Expected sample times: 0, 20, 40, 60 ms, ...
```

Depending on where sample ticks fall relative to progress, 2 ms method A is easily missed, while 18 ms method B is much more likely to be caught. That **does not mean** A is called less often than B. If A is invoked very frequently for tiny durations each time, call counts and sample percentages can diverge wildly.

Under a **simplified hypothetical model** where sample times fall uniformly at random over interval `T` and a non-overlapping operation lasts `d<T`, the probability of hitting it once is roughly `d/T`. For example, `d=2 ms`, `T=20 ms` ⇒ roughly 10%. This is an **intuitive model**, not a calibrated formula for HotSpot's sampler: scheduling, collectors, safepoints, thread states, stack availability, bias, and dropped samples all shift reality.

### Typical biases

1. **Short-lived operations:** code running for a few microseconds may be absent despite huge invocation counts.
2. **Sampling bias:** threads/states easier to observe may appear more often; sample time does not always match CPU time across every JVM and config.
3. **Aliasing:** if the sampling period aligns with periodic workload cycles, one phase of the application may be over- or under-represented.
4. **Short duration:** just 10 samples in a minute is too few to judge the distribution of rare methods.
5. **Stack capture cost/capability:** stack traces may be missing, depth-limited, truncated, or fail to unwind.
6. **Recording mode:** `default`, `profile`, and custom settings toggle samplers and change periods; results are not directly comparable across config changes.
7. **Different threads:** a sample hotspot can be dominated by a single thread; inspect thread groupings and workload before generalizing to the whole service.
8. **Sample share:** "40% of samples in method X" is a share of **captured samples**, not proof that X consumes exactly 40% of wall-clock time, request time, or total CPU across all threads.

`jdk.ObjectAllocationSample` is likewise **allocation sampling**, not a complete list of every `new`. An event may carry a weight/estimate to infer allocation pressure; check how the tool/JMC aggregates it instead of treating each sample as one new object or one allocated byte.

## 6. Period is not equivalent to threshold

`period` sets the expected interval/cadence for periodic or sampled events; `threshold` filters **by event duration**. Changing period from 20 ms to 10 ms may increase observation points, yet it will not make a 5 ms duration event appear if its threshold stays 20 ms.

| Situation | What changed | What **cannot** be inferred |
| --- | --- | --- |
| `jdk.ExecutionSample#period=20ms` → `10ms` | Desired sampling density | Sample count doubled or CPU accuracy doubled |
| `jdk.JavaMonitorEnter#threshold=20ms` → `5ms` | Admits shorter monitor entries | Lock contention increased |
| `jdk.ThreadSleep#enabled=false` → `true` | Starts collecting matching sleep events | Threads started sleeping more than before |
| `stackTrace=false` → `true` | Adds attribution to events | Event count or durations increased |
| `settings=default` → `profile` | Different event bundle and capture policy | Application slowed down solely because more events appeared |

A periodic event emitted every 5 seconds cannot reconstruct 100 ms spikes occurring between ticks. That is a **temporal resolution limit**, not a charting bug.

## 7. Check JFR data quality before computing

Do not start from the hottest chart. Verify the "observation frame" first:

| What to record | How to check | Consequence if missing |
| --- | --- | --- |
| Java/JDK/JVM, PID, recording name | `java -version`, `jcmd -l`, file metadata | May mix up processes or config versions |
| Start/end, timezone, duration | `jfr summary`; standardize UTC/offset | Mixing events from different times |
| `.jfc`, event `enabled`/`threshold`/`period`/`stackTrace` | `JFR.check verbose=true` while recording runs; save config | Distortion from capture changes |
| Event counts by type | `jfr summary` | "No events seen" may mean disabled or filtered |
| Thread, stack depth, event start/duration | `jfr print` and JMC | Unknown which thread ran it or how long it lasted |
| Repository retention / recording coverage | Recording window, `maxage/maxsize`, actual dump | Missing head/tail; mistaking missing data for 0 events |
| Throughput, active requests, queue size, GC counters | Independent metrics/logs/traces | Cannot separate workload effects from causes |
| Overhead / recording impact | Compare baseline under equal load, check volume/CPU/latency | The observer may perturb what is measured |

Example commands to inspect an exported file:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 incident.jfr
jfr print --events jdk.JavaMonitorEnter incident.jfr
```

`jfr print` only shows events present in the file, and does not guarantee an unseen event never happened. For large files stdout can be huge; use JMC or suitable analysis tools to filter by thread and time window.

When correlating with application logs, prefer timestamps **with timezone**, PID/instance ID, request or trace ID, and consistent definitions of "latency" (end-to-end, server handling, waiting, database round-trip). Never use X-axis proximity alone to claim two events are causally linked.

## 8. Capturing recordings for controlled analysis

On HotSpot JDK 21+, you can start a short diagnostic recording:

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check name=triage verbose=true
```

Replace PID `12345`. The first command succeeds only if it can attach to the **right JVM** with sufficient permissions. `settings=profile` enables more events and samples more densely than `default`; never compare raw counts against a `default` recording and conclude the workload changed.

To explicitly record the configuration of two specific event types:

```bash
jcmd 12345 JFR.start name=sample20 settings=profile duration=60s filename=sample20.jfr jdk.ExecutionSample#period=20ms
```

And a separate experiment:

```bash
jcmd 12345 JFR.start name=monitor20 settings=profile duration=60s filename=monitor20.jfr jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=20ms
```

These two commands are **two illustrative configurations**; run them in separate sessions or stay aware that concurrent recordings interact in load and settings. Results can be compared only under identical workload, identical observation length, identical version, and confirmed presence of the target events.

`JFR.start` event settings follow `<event-name>#<setting-name>=<value>`; `.jfc` files can be overridden via command-line settings depending on JDK precedence. Re-run `JFR.check verbose=true` instead of assuming the command produced what you intended.

**Reading the results:**

- `jfr summary` shows how many `jdk.ExecutionSample` and `jdk.JavaMonitorEnter` events the file contains.
- In JMC, CPU/method profiling charts use **sampled stacks**; monitor contention tables rely on **duration events** that cleared the threshold.
- A 60-second recording with `0` samples for a small method is normal if the sampler never caught it; `0` `JavaMonitorEnter` events over 20 ms only means none met the condition and settings within the captured window.

## 9. Runnable Java 17+ example: same operations, different event counts

This example creates a **custom duration event**; it does not attempt to mimic HotSpot's CPU sampling algorithm. The goal is seeing firsthand how `threshold` affects event counts: the program executes the exact same **8 operations** across two runs while changing the recording cutoff.

Save **`JfrThresholdDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrThresholdDemo {
    @Name("demo.WorkInterval")
    @Label("Work interval")
    @Category({"Demo", "Diagnostics"})
    static final class WorkInterval extends Event {
        @Label("Planned sleep (ms)")
        int plannedSleepMs;
    }

    private static void runOperation(int millis)
            throws InterruptedException {
        WorkInterval event = new WorkInterval();
        event.plannedSleepMs = millis;
        event.begin();
        Thread.sleep(millis);
        event.end();
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        long thresholdMs = args.length == 0
                ? 20
                : Long.parseLong(args[0]);
        if (thresholdMs < 0) {
            throw new IllegalArgumentException(
                    "threshold must be >= 0");
        }

        Path output = Path.of("threshold-" + thresholdMs + "ms.jfr");
        int[] waits = {5, 40, 5, 80, 5, 40, 5, 80};
        int attempts = 0;

        try (Recording recording = new Recording()) {
            recording.setToDisk(true);
            recording.enable(WorkInterval.class)
                     .withThreshold(Duration.ofMillis(thresholdMs))
                     .withStackTrace();
            recording.start();

            for (int ms : waits) {
                runOperation(ms);
                attempts++;
            }

            recording.stop();
            recording.dump(output);
        }

        long recorded = 0;
        try (RecordingFile file = new RecordingFile(output)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if ("demo.WorkInterval".equals(
                        event.getEventType().getName())) {
                    recorded++;
                }
            }
        }

        System.out.println("attempted=" + attempts);
        System.out.println("recorded=" + recorded);
        System.out.println("file=" + output);
    }
}
```

Compile and run with **JDK 17+** in a directory with write permissions for `.jfr` files:

```bash
javac JfrThresholdDemo.java
java JfrThresholdDemo 0
java JfrThresholdDemo 20
jfr summary threshold-0ms.jfr
jfr summary threshold-20ms.jfr
jfr print --events demo.WorkInterval threshold-20ms.jfr
```

The two runs create `threshold-0ms.jfr` and `threshold-20ms.jfr`. The `attempted=8` line is a **deterministic result from the code** in both runs. The `recorded=...` line is the **actual number of events read back** and must come from real output rather than an invented fixed number:

- At `threshold=0`, all eight operations have the chance to appear; in a normal run with adequate resources, expect a count near **8**.
- At `threshold=20 ms`, the four planned 40/80 ms sleeps tend to pass the threshold while the four 5 ms sleeps are typically filtered out. However, `Thread.sleep` can be stretched by scheduling, GC, or CPU contention, so even a planned "5 ms" operation can exceed 20 ms and be recorded.
- If `recorded` differs from expectations, inspect **actual duration** in each event via `jfr print` instead of assuming the demo broke. The key point is that **attempted** stays constant while **recorded** depends on filters and capture conditions.

This program demonstrates three things: `event.begin()` marks the start, `event.end()` stops timing, and `event.commit()` submits the event, yet **JFR applies recording settings** before emitting an observable event. This is a duration-event example. Do not infer from it that `jdk.ExecutionSample` is generated on every method call and then filtered by threshold; that uses a **different sampling mechanism**.

### Why use application metrics in parallel?

Only `attempts` in code gives the true denominator for counting in this experiment. In production, you may need `http.server.requests`, dequeued task counts, retry counts, or request IDs from tracing to confirm "how many times the operation occurred." JFR provides visibility into JVM behavior; business metrics provide the **denominator** and load conditions.

## 10. Temporal correlation does not prove causation

Suppose a dashboard shows three bursts:

- `10:00:00–10:00:15`: request latency spikes.
- Around the same time, JFR shows many allocation samples and several GC pauses.
- CPU sampling catches stacks in `parsePayload` more frequently.

A hasty conclusion is "`parsePayload` caused GC, and GC was the sole cause slowing requests." Yet at least four distinct mechanisms fit this timeline:

1. **Shared load drives both up:** burst of requests → more parsing → more allocation → GC; simultaneously DB/queues slow down too. GC may only be one piece.
2. **Reverse dependency:** requests stay open longer due to upstream timeouts → buffers/scopes stay alive longer → heap pressure rises; GC occurs **after** latency started degrading.
3. **A third bottleneck:** CPU throttling, lock contention, or slow I/O perturbs sampling/GC scheduling and latency simultaneously.
4. **Measurement artifact:** differing JFR `threshold`, sample density, end-of-window flushing, or timestamp skew make two curves look in phase when they do not share a cause.

We can sketch the hypothetical relationships:

```text
Load rises ──> allocation rises ──> heavy GC activity
    │
    ├────────> queue/backlog grows ──> latency rises
    │
    └────────> DB/CPU contention ────> latency rises

GC pauses may contribute to latency,
but overlapping charts alone do not isolate how much.
```

To prove GC *contributed directly*, you need evidence of **specific requests being halted**, pause timestamps overlapping request processing, pause lengths matching the added delay, repetition across bursts, and control over competing causes. Even proof that a pause hit a request does not make it the **sole cause**.

## 11. Aligning timelines without misleading yourself

### 11.1. Distinguish event timestamps

JFR events have a start time and, for duration events, a duration; an event can only be completed/committed after the measured operation. When plotting buckets by **start time**, **end time**, or 1-second intervals, the visible ordering can shift.

For example, an operation starts at `12:00:00.100`, takes 900 ms, and ends at `12:00:01.000`. If a table buckets by end time, it lands in bucket `12:00:01`; a GC pause at `12:00:00.500` sits in the middle of the operation's duration, yet two aggregate columns might make it look like the operation ran after GC.

### 11.2. Clock synchronization and resolution

- JFR timestamps within one JVM correlate internally more reliably than across a distributed system; handle UTC/timezones carefully when joining application logs, traces, OS metrics, and APM.
- Clocks across servers/containers can exhibit clock skew; "12:00:00" on two machines is not guaranteed to be the same physical instant.
- Minute buckets hide 20 ms events; overly tiny buckets get noisy when samples are sparse.
- A 50 ms duration event is an interval **[start, end]**, not a single dot on a chart.
- If a recording only covers T0–T1, the repository evicted old data, or samples were dropped, an empty chart does not mean the system was quiet.

### 11.3. Look for lag and mechanistic chains, not mere coincidence

If the hypothesis is "GC pauses drove up tail latency," inspect request start/end, pause start/end, pause duration, and pre–during–post pause behavior. If latency climbs **before** GC across multiple bursts, the simple hypothesis weakens, though GC can still be an aggravating factor. A repeatable relationship under equivalent conditions is far stronger than one timestamp coincidence.

## 12. Moving from charts to a testable hypothesis

Pragmatic investigation workflow:

1. **Define the symptom independently:** e.g., server p99 latency rose from 80 ms to 400 ms on the same API at ~500 RPS. Measure from request metrics/traces, not from thresholded JFR duration event counts.
2. **Record exact observation config:** JDK/GC, recording profile, `enabled`, `threshold`, `period`, `stackTrace`, capture timestamps, sample/event counts, and whether the file covers the whole window.
3. **Construct baseline and incident windows with identical definitions:** pick periods with matching load, traffic mix, concurrency, dataset, JVM warm-up, and cache state; document remaining differences.
4. **State mechanism and predictions:** "If lock L stalls requests, slow requests will show matching wait intervals, `jdk.JavaMonitorEnter` events exceeding the threshold will appear on this code path, and reducing contention on L will lower tail latency." Predictions must distinguish this from alternative hypotheses.
5. **Gather independent evidence:** request spans, queue depth, DB latency, CPU throttling, GC logs/pauses, monitor events, thread samples, and application metrics.
6. **Check temporal direction and target:** are events on the thread/request/correlation ID of slow requests, or merely occurring concurrently on unrelated threads?
7. **Vary one factor when feasible:** adjust concurrency, shorten the critical section, change payload size, or adjust cache/queue handling. Repeat under identical conditions and compare latency/GC/locks together.
8. **Seek falsification:** if contention drops while latency stays flat, or latency spikes with zero contention, look for another mechanism.
9. **Report scoped conclusions:** label statements "consistent with," "direct evidence of," or "confirmed experimentally" matching actual certainty.

In production, never change configs arbitrarily just to "prove" a theory. Run controlled load tests on staging or canary experiments under proper procedures. Controls and repetition reduce confounding; they are not magic that eliminates every external variable.

## 13. Sample size and variance: do not treat small ratios as gospel

Suppose over one recording window, JMC method stats show:

| Method | Execution samples | Share of 100 valid samples |
| --- | ---: | ---: |
| A | 20 | 20% |
| B | 50 | 50% |
| C and other methods | 30 | 30% |

What you can say: "Out of **100 observed samples** under the current filter, A appears in 20 samples." What you cannot immediately claim: "A caused exactly 20% of total CPU" or "A was called 2.5x less often than B."

For statistical intuition, if 100 observations were **independent, representative, Bernoulli-like trials** with `p=0.2`, the estimated standard error would be:

```text
SE ≈ sqrt(p × (1 - p) / n)
   = sqrt(0.2 × 0.8 / 100)
   = 0.04 = 4 percentage points
```

A very rough 95% interval like `p ± 2 SE` spans about 12–28%. **Do not treat this interval as a formal confidence interval for JFR**: execution samples within a thread/workload are typically correlated, sample timing has bias, and samples are not strictly independent random draws. This only illustrates why a ratio from few samples already carries substantial uncertainty *even under ideal statistical assumptions*.

When sample counts are low or paths are rare, extending the observation window, using reproducible conditions, and cross-checking other metrics/tracing helps far more than quoting three decimal places off a chart.

## 14. Threshold "sensitivity analysis"

Suppose a wait-type event is recorded under two configurations; the following numbers are purely **hypothetical**:

| Run | Workload | Threshold | Wait events in 1 minute | p99 request latency |
| --- | --- | --- | ---: | ---: |
| Run A | 500 req/s | 20 ms | 120 | 240 ms |
| Run B | 500 req/s | 5 ms | 2,400 | 245 ms |

Jumping from 120 to 2,400 events is **expected** when the threshold is lowered: additional 5–20 ms waits now get recorded. The higher count **does not prove contention got 20x worse**. Similar p99 also does not prove 5–20 ms waits "have no impact": check which request paths waited, their distribution, concurrency, measurement overhead, and p99 sensitivity.

Conversely, when both threshold and sampling period **stay fixed** under comparable workload and both slow event rate and p99 rise across multiple intervals, that is **stronger evidence of an anomaly**, though still not proof of root cause.

Document every run's configuration in comparison tables. Avoid raw subtraction of event counts across unequal durations; normalize at least to `events / valid recording minute`, then normalize further by workload and collection mode. **Normalization cannot fix selection bias** introduced by differing thresholds or samplers.

## 15. False hypotheses and how to test them

| Hasty conclusion | Why it is wrong | How to verify |
| --- | --- | --- |
| "No lock events means no lock contention" | Event may be disabled, threshold high, or recording missed the window | `JFR.check verbose`, check thresholds, logs/thread dumps, wait metrics |
| "Method X has 30% of samples so it causes 30% of request latency" | CPU samples ≠ request wait time; pools/threads/workload may differ | Join with request traces and thread states; measure CPU directly |
| "Allocation samples doubled = exactly 2x objects created" | Allocation is sampled and estimates may use weights | Compare allocation rate/heap/GC under identical sampling settings |
| "Latency and GC overlap, so GC is the only culprit" | Load/CPU/DB/queues may also act simultaneously | Pause intervals, request spans, workload, and controlled tests |
| "Event count rose after enabling `profile` = app degraded" | Event bundle and capture sensitivity changed | Hold config constant when comparing or only compare identically defined metrics |
| "One stack sample in method Y = Y is always slow" | One sample does not represent the call distribution | Gather more samples, group by thread, time directly |
| "Event started before metric, so it is definitely the cause" | Both may respond to a third variable or timestamp skew | Check mechanism, temporal order on the same request, and falsification |
| "Repeated correlation is enough proof" | A confounder may repeat with load; causal pathway untested | Vary one factor, compare under controlled conditions, measure intermediate chain |

## 16. Checklist before writing an incident report

**On JFR data:**

- Correct **PID/JVM/build**, matching version/GC/recording settings across compared points?
- Known whether each event is **sampled, periodic, duration, or instant**?
- Known actual `enabled`, `threshold`, `period`, `stackTrace`?
- Checked exact time span covered by the file, any dropped/missing samples, or retention gaps?
- Do counts/ratios have an appropriate denominator and documented observation conditions?
- Was each duration event treated as a **time interval**, not just a single timestamp?

**On causation:**

- Do independent business metrics confirm the symptom?
- Is there a **concrete mechanism** connecting the events to requests/latency/throughput?
- Were load, CPU, DB, I/O, GC, locks, queues, and potential confounders checked?
- Are there before/after controls under matched conditions and multiple comparable bursts?
- Did you look for **falsifying evidence** or run a change to test the hypothesis?
- Does the conclusion clearly separate **observations**, **suspicions**, and **confirmed facts**?

## 17. Evidence-bounded report template

**Appropriate phrasing:**

> In a HotSpot JDK 21 recording using `profile`, `jdk.JavaMonitorEnter#threshold=20ms`, and `jdk.ExecutionSample#period=20ms`, the 10:00–10:02 window recorded a rise in monitor-enter events exceeding 20 ms alongside API p99 rising from 90 to 350 ms. This is a correlation worth investigating. Events under 20 ms are excluded from the count and execution sample counts are not method invocation counts. It is not yet verified which slow requests own those monitor waits or whether load/DB changed. Next steps are joining request spans with JFR stacks/threads, controlling for workload, and testing the contention hypothesis with a controlled experiment.

**Overstated phrasing:**

> In the same minute, lock events and p99 rose together. Therefore locks are definitely the sole cause; the method with 40% of samples took exactly 40% of CPU.

The second example cannot be substantiated from the data: it lacks mechanism, denominators, sampling config, confounder control, and verification testing.

## 18. Self-assessment exercises

**Exercise 1 — threshold.** A service processes 1,000 requests/minute. JFR records 80 `jdk.JavaMonitorEnter` events with `threshold=20ms` in that minute. Can we say "8% of requests experienced lock contention"?

**Hint:** No. 80 is the number of monitor-enter events meeting the threshold; one request can trigger multiple events or zero; there is no event→request mapping and event coverage is unknown. To find the fraction of affected requests, you need request IDs/traces and proper measurement conditions.

**Exercise 2 — sampling.** A method appears in 1 out of 200 execution samples. Can we say it was called only once?

**Hint:** No. It could be called thousands of times briefly each time. Sample count is a point-in-time observation.

**Exercise 3 — configuration.** Run A uses `JavaMonitorEnter#threshold=20ms` and Run B uses `5ms`. Run B has 5x more events. Does that prove lock contention grew 5x?

**Hint:** No. Lowering the threshold lets shorter events qualify. Compare under identical settings.

**Exercise 4 — causality.** A 150 ms GC pause overlaps a 300 ms request. Can you claim all 300 ms came from GC?

**Hint:** No. Check pause timing relative to request execution, latency before/after the pause, DB, queuing, and CPU; at most the pause explains a temporally overlapping portion if the request was actually halted.

**Exercise 5 — experiment.** Run `JfrThresholdDemo` with thresholds 0 and 20 ms. Record `attempted`, `recorded`, and actual event durations in both files. Why can `recorded` vary even with an identical `waits` array?

**Hint:** Threshold filters by **actual measured duration**; scheduling/GC alters actual durations and recorder state has practical limits. Count from actual output/files rather than predicting event counts from planned sleeps.

**End-of-lesson practice:** Pick a JFR recording containing `jdk.ExecutionSample` and one duration event type. Build a table for each event: setting, collection mechanism, time window, observation count, valid denominator, what can be inferred, and what cannot. Formulate two hypotheses capable of producing the same timeline, and propose a measurement or experiment to tell them apart.

## 19. Official sources to cross-check

- [Oracle Java 21 — `jdk.jfr`: definitions of `enabled`, `threshold`, `period`, `stackTrace`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Oracle Java 21 — `EventSettings`: `withThreshold`, `withPeriod`, and stack traces](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- [Oracle Java 21 — `Recording`: lifecycle, configuration, `stop`, and `dump`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle Java 21 — `RecordingFile`: reading back actually recorded events](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Oracle JDK 21 — `jcmd`: `JFR.start`, overriding event settings, `JFR.check`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `metadata`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/).

**Final principle:** `threshold` answers "which events exceeded the cutoff and were recorded"; `sampling` answers "which states did the sampler see at sample ticks"; timelines answer "how closely in time did observations occur." Answering "*why*" requires a sound mechanism, independent data, control of confounders, and reproducible evidence.
