# 18.9 Verifying Changes Using Latency Distributions and Successful Operations Under Identical Load

## 1. Purpose of this lesson

After modifying I/O code, connection pools, batching, asynchronous execution, buffer sizes, caches, or timeouts, a prettier average **is not enough to prove the system improved**. A change can speed up successful operations while simultaneously increasing timeouts, dropping requests, or returning corrupted data. To draw a valid conclusion, measure **the latency distribution** and **the count of genuinely successful operations** under **the same demanded load**.

After this lesson, you will be able to:

1. Distinguish **offered load**, issued rate, completed throughput, **goodput**, success rate, errors, timeouts, dropped, and in-flight requests.
2. Read and compare **p50, p90, p95, p99, p99.9**, histograms/CDFs, max, mean, and deadline breach rates; understand sample-size limits.
3. Design clean A/B experiments: identical workload, arrival rate, cache state, data size, resources, timeouts, warm-up conditions, and success predicate.
4. Avoid **coordinated omission** and bias when closed-loop tests automatically slow down request generation as the server slows down.
5. Correlate client end-to-end latency with JVM data, JFR `SocketRead`/`SocketWrite`/`FileRead`/`FileWrite`, queues, CPU/GC, and OS metrics.
6. Define **PASS / FAIL / INCONCLUSIVE** criteria before running, rather than cherry-picking favorable metrics after seeing the numbers.

**Core message:** a change is an improvement when, under **the same verifiable load**, **correct and successful operations per second** are not traded away for a nicer p95, and both tail latency and guardrails meet their targets.

## 2. Defining the operation, measurement points, and deadline

Before running a test, define what **one operation** is: an HTTP request, a business transaction, a database query, a file read/write, a batch, or an acknowledged message. If A reports throughput per batch while B reports per row, the two numbers cannot be compared directly.

Example of an HTTP operation calling a database:

~~~text
Load generator plans to issue request at t0
        |
        +-- may fall behind schedule or drop if generator lacks resources
        v
Client actually begins sending request
        |
        +-- network / connection pool / TLS
        v
Server receives request
        |
        +-- queue / thread scheduling / GC
        +-- application CPU / database / file / socket I/O
        v
Server completes response
        |
        +-- network / client decode / validate payload
        v
Client determines SUCCESS / ERROR / TIMEOUT at t1
~~~

Decide which interval to measure:

| Name | Scope | Purpose |
| --- | --- | --- |
| **Client end-to-end** | From client send until result receipt or deadline | Caller experience |
| **Scheduled-to-completion** | From **intended scheduled** issue time until completion | Reflects queuing/missed schedule in arrival-rate tests |
| **Server request duration** | From server receipt until completion per instrumentation | Server analysis; excludes full client network |
| **Downstream I/O duration** | While code waits on socket/file/database read/write | Pinpoints slow component; not total request time |
| **Queue wait** | From enqueue until processing starts | Detects backlogs and worker/pool limits |

**Never compare client p99 of A against server p99 of B.** They measure different spans. In Java, use **`System.nanoTime()`** differences to measure durations within the same process; `System.currentTimeMillis()` is fine for wall-clock/log timestamps, but the system clock can jump.

Set the **deadline** before running—for example, 250 ms. An operation timing out after 250 ms is a **failed outcome** that must be counted and have its wait-to-timeout recorded per test definition. Never quietly drop timeouts from statistics. If the generator failed to issue a request, that is **dropped/not issued**, not a measured latency.

An HTTP 200 counts as success only if **payload content and business postconditions** are valid. A write job returning OK while losing records, writing invalid duplicates, or violating durability contracts is not useful success.

## 3. Counters must balance

In a test window, define:

- **P / planned**: operations scheduled to be sent.
- **I / issued**: operations actually sent.
- **D / dropped**: scheduled operations the generator failed to issue.
- **C / completed**: operations with a final outcome, including errors and timeouts.
- **S / success**: completed operations valid at both protocol and business levels.
- **F / failed**: completed operations that errored, timed out, were rejected, returned wrong data, or cancelled per contract.
- **O / outstanding**: issued operations with no final outcome yet at cutoff.

If each logical operation is accounted for exactly once:

~~~text
P = I + D
I = C + O
C = S + F

issued_rate           = I / measurement_duration
completed_throughput  = C / measurement_duration
goodput               = S / measurement_duration
success_rate_finished = S / C      (only when C > 0)
success_per_planned   = S / P      (only when P > 0)
~~~

**Goodput** is useful, successful operations/second—not attempts/second. If one request retries three times to complete one business operation, count **one logical success** and track **three physical attempts** in a separate metric. Counting retries as successes inflates throughput and hides I/O cost.

**A high S/C alone is not enough:** if the generator only issued 100 of 1,000 planned requests and all 100 succeeded, S/C = 100% while S/P = 10%. Therefore report all of P, I, D, C, S, F, and O. With asynchronous work, document the **drain** period and remaining outstanding work so you do not compare A with a deep backlog against fully drained B.

For example, planned = 60,000, issued = 59,500, dropped = 500, completed = 59,400, outstanding = 100, success = 58,000, and failed = 1,400. These numbers balance. Goodput over 120 seconds is 58,000/120 ≈ 483.33 successful operations/s. Never use 59,400/120 and call it goodput.

### Relationship to serving capacity

If the server accepts 500 ops/s while completing only 400 ops/s over a sustained period, **the backlog grows**; high accepted request counts do not mean the system is healthy. In steady state, Little's Law links average work in the system to arrival/completion rate and average response time, yet it does not replace measuring queues and breaks down mechanically when an unstable backlog keeps growing.

## 4. Why inspect the entire distribution?

**Averages** hide outliers. **p50** describes the median, **p95** the common tail, and **p99/p99.9** the slowest tail. An optimization that speeds up the majority while making 1% of requests wait far longer can still break the SLO.

Over observations sorted ascending:

| Metric | Interpretation |
| --- | --- |
| **p50** | Roughly 50% of observations do not exceed this value |
| **p90/p95** | Reveals the common tail |
| **p99/p99.9** | Reveals rare slow tails; requires many observations |
| **max** | Slowest observed value; sensitive to outliers and sample size |
| **Mean** | Average; useful for capacity math, not a substitute for tails |
| **Deadline breach rate** | Fraction slower than the predefined SLO threshold |
| **Histogram / CDF / CCDF** | Full distribution shape and fraction exceeding each threshold |

**p99 is not necessarily the slowest request.** Nearest-rank for N=100 observations picks the 99th observation, while max is the 100th. Histogram systems may interpolate, so A and B must use the same algorithm and bucket boundaries.

**p99.9 over 1,000 observations sits near the maximum** and fluctuates wildly. Tails require large sample sizes and repeated runs. There is no single universal minimum sample count for every workload; confidence depends on effect size, variance, serial correlation, and independent run count.

**Never average per-pod or per-minute p99s and call it the overall p99.** Percentiles do not aggregate linearly. With Prometheus classic histograms, **sum the bucket counts** across compatible sources first, then apply `histogram_quantile`. With pre-computed per-instance summary quantiles, averaging quantiles never yields the global quantile.

### CDF and CCDF clarify the tail

- **CDF(x)** = fraction of observations with latency ≤ x.
- **CCDF(x)** = 1 − CDF(x) = fraction of observations with latency > x.
- At a 200 ms threshold, CCDF=0.03 means roughly 3% of measured observations exceeded 200 ms.
- If failures/timeouts were excluded from that latency set, report breach/censoring rates separately and never label the CCDF of successes as the CCDF of all operations.

For I/O, also watch **tail-over-time**: one p99 over 30 minutes can hide a 20-second spike severe enough to trigger an incident.

## 5. "Same load" does not mean "same 100 threads"

A **closed-loop** test typically spawns N clients, each sending the next request **after the previous response completes**. If the server slows down, clients send fewer requests. Both runs can have "100 virtual users" while applying completely different loads.

~~~text
Run A: 100 clients → ~1,000 requests/s issued
Run B: 100 clients → ~450 requests/s issued
~~~

You cannot conclude B has lower latency **at 1,000 requests/s** when B only received 450/s. "Same connection count" likewise does not guarantee identical offered load.

In an **open-loop/arrival-rate** model, the generator schedules requests independently of previous completions—for instance, 500 requests/s. However, the generator can still fall behind if it runs short on workers, CPU, sockets, or connections. Therefore measure:

1. Configured **target arrival rate**.
2. Actual **scheduled/issued rate** by timestamps.
3. **Late starts/dropped iterations** when the generator cannot keep up.
4. **Server arrival rate** to confirm it matches what the client sent.
5. **Actual goodput** and errors/timeouts.

### Coordinated omission

If the system stalls for 1 second, a closed-loop client waiting for a response fails to emit subsequent requests that real independent users would have sent. A histogram of *actually issued* requests omits those delayed arrivals, making tail latency look artificially rosy.

**Coordinated omission** is measurement bias from failing to record requests that an independent arrival process would have submitted. To reduce this bias, use a rate-scheduled load generator and measure latency from **intended start time**, while verifying the generator kept up. If it fell behind, report missed schedules separately and **never fabricate synthetic latency numbers as real observations**.

The **wrk2** tool uses a constant-throughput schedule and records latency accounting for when requests were supposed to be sent. This aids comparisons at equal offered rates, though it does not replace counting business successes or checking generator saturation.

### Controlling confounding variables

| Group | Must match between A and B |
| --- | --- |
| **Input** | Read/write ratio, payload size, key count, data distribution, route mix, random seed |
| **Arrival schedule** | Offered RPS, duration, ramp-up, burst pattern, steady-state windows |
| **State** | Planned warm/cold cache state, DB size/indexes, connection reuse and pool warm-up |
| **Resources** | CPU quota, memory, replicas, disk/network tier, JVM/JDK/GC, limits, autoscaling policy |
| **Network** | RTT, TLS, HTTP version, load balancer, keep-alive, pool sizing outside treatment |
| **Failure policy** | Timeouts, retry budgets, rate limits, circuit breakers, validation and success predicate |
| **Measurement** | Client/server instrumentation, sampling, histogram buckets, units, generator version |
| **Environment** | Noisy neighbors, background jobs, data resets, clock skew, observability overhead |

If the **intentional** change is raising the connection pool from 32→64, record that as the **treatment**; do not force pools equal and claim you tested the pool change. Still keep CPU quota, DB capacity, and offered load comparable. If B uses twice as many replicas, factor **resource cost** into the decision.

## 6. Designing a repeatable before–after experiment

### Step 1. Lock hypothesis and guardrails before running

Example: "Batched I/O improves client p99 latency without reducing successful throughput." Illustrative pass criteria:

- Offered load: **500 planned ops/s** for 120 seconds steady-state.
- Goodput ≥ **495 successful ops/s**.
- Success/planned ≥ **99.9%**.
- End-to-end p99 ≤ **250 ms**.
- Data correctness = **100%** per validator.
- Timeouts/rejects/drops do not rise beyond predefined budgets.
- CPU/memory/connection usage stays within capacity budgets.

Not every system needs these exact numbers; they are an **example of defining pass/fail**, not a universal standard.

### Step 2. Warm up with the target workload

Java has JIT compilation, class loading, GC, pool creation, and cache warm-up. Measuring A cold and B warm and calling B faster is invalid. Warm up with matching traffic, or **run a dedicated cold-start benchmark** if cold-start is the actual SLO under test.

### Step 3. Test a load curve

Run multiple levels such as **100, 300, 500, 650 ops/s** with the same payload mix. Measure p95/p99 and goodput at each step. The "knee" as the system nears saturation matters far more than numbers at low RPS.

Under overload, inspect **queue depth, in-flight, rejected, timeouts, and post-load recovery**. A system that rejects in a controlled manner may be safer than an unbounded queue, though success/planned must still be reported honestly.

### Step 4. Protect the benchmark from generator bottlenecks

Use load-generator machines with ample CPU/network/file descriptors; monitor CPU, socket errors, missed arrivals, actual rate, and client-side throttling. If the generator saturates, the run is **INCONCLUSIVE**—differences cannot be attributed to the server.

### Step 5. Repeat runs and control drift

Prefer multiple A/B runs—such as **A–B–B–A** or randomized block order—with data resets, cooldowns, and identical resource tiers. Never run A when the system is quiet and B while a batch job hammers the database, then treat it as a clean comparison.

### Step 6. Freeze windows, drain, and preserve artifacts

Separate warm-up, steady state, and cooldown/drain. Never score B's p99 before slow requests finish while A drained completely. Preserve run IDs, configs, metric snapshots, histograms, JFR files, and planned/issued/completed/failed counts.

### Step 7. Account for uncertainty

If p99 across runs swings between 200–450 ms, a "210→205 ms" difference in a single run proves nothing. Use repeated runs, appropriate CIs/uncertainty bounds, or block/run-level bootstrapping when serial correlation exists. **Never naively bootstrap tightly time-correlated individual requests** and claim overly narrow confidence intervals.

## 7. Example of drawing the right conclusion from a before/after table

Same offered **500 ops/s for 120 seconds**, planned = **60,000** operations; all figures below are **hypothetical**:

| Metric | Baseline A | Candidate B |
| --- | ---: | ---: |
| Planned | 60,000 | 60,000 |
| Issued | 59,950 | 59,900 |
| Dropped by generator | 50 | 100 |
| Completed after drain | 59,950 | 59,900 |
| Business successes | 59,880 | 58,800 |
| Failed / timeout | 70 | 1,100 |
| Goodput | **499.0/s** | **490.0/s** |
| Success / planned | **99.80%** | **98.00%** |
| Client p50 | 42 ms | **32 ms** |
| Client p95 | 140 ms | **95 ms** |
| Client p99 | **380 ms** | **540 ms** |

Check the math:

- A: **59,880/120 = 499 successful ops/s**.
- B: **58,800/120 = 490 successful ops/s**.
- Both satisfy `P=I+D`, `C=S+F`, and zero outstanding after drain.

B has better p50/p95, yet **p99, errors, drops, and goodput are all worse**. If guardrails require p99 ≤250 ms, success/planned ≥99.9%, and goodput ≥495/s, neither fully passes—and **B clearly fails**, so you cannot declare "optimization succeeded" based on p95 alone.

Possible causes include B failing fast, overloading, dropping requests, or queuing a subset of operations heavily. However, **the table alone does not prove the cause**: timelines and JFR/metrics are required.

## 8. Histograms, OpenTelemetry, and Prometheus

### Measure with accurate units and labels

In OpenTelemetry HTTP semantic conventions, **`http.server.request.duration`** and **`http.client.request.duration`** are histograms measured in **seconds**. Server and client cover different scopes and cannot be compared directly without aligning measurement points.

An example set of custom metrics:

- **`api_operation_seconds`**: classic histogram of logical operation durations, explicitly noting whether failures/timeouts are included.
- **`api_operations_total{operation,result}`**: counter incremented once per completed logical operation; `result=success/failure/timeout`.
- **`api_operations_scheduled_total`**, **`api_operations_dropped_total`**: load-generator counters if available.
- **`api_inflight_operations`**: gauge of unfinished work.
- **`api_retries_total`**: physical retries to expose hidden overhead.

Never use **request ID, user ID, dynamic full URL, or raw error message** as metric labels: cardinality will explode. Route templates and bounded error categories are much safer.

### Computing p99 from a classic histogram

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(api_operation_seconds_bucket{operation="read"}[5m])
  )
)
~~~

This estimates **p99 in seconds** for a classic histogram with consistent bucket boundaries. If buckets are too coarse around the target (e.g., 0.1 s then 1 s), a p99 near 0.25 s carries large interpolation error.

**Wrong:** averaging percentiles across instances:

~~~promql
avg(instance_request_p99{operation="read"})
~~~

That does not produce the true p99 of all requests. Native histograms use their own syntax; never inject **`le`** onto a native histogram metric lacking that label.

### Goodput from a success counter

~~~promql
sum(
  rate(api_operations_total{
    operation="read", result="success"
  }[5m])
)
~~~

This counter gives true goodput only when the app **increments once per logical success**. If instrumentation increments per retry attempt or fires multiple times from callbacks, the query still returns a clean-looking number with the wrong meaning.

Success rate among completed operations:

~~~promql
sum(rate(api_operations_total{operation="read",result="success"}[5m]))
/
sum(rate(api_operations_total{operation="read"}[5m]))
~~~

Never substitute this for **success/planned** when the generator dropped operations or work remains outstanding.

### Fraction within the 250 ms bound

If bucket **`le="0.25"`** actually exists:

~~~promql
sum(rate(api_operation_seconds_bucket{
  operation="read", le="0.25"
}[5m]))
/
sum(rate(api_operation_seconds_count{
  operation="read"
}[5m]))
~~~

If the histogram records **only successful responses**, this ratio **ignores failures/timeouts** and reflects only the SLO among succeeded operations. Pair it with client-side error accounting and success rate over planned load.

Exporters can rename metrics or alter labels; verify the **actual exposed metric** before running queries. Keep histogram boundaries and sampling identical between A and B.

## 9. Example constant-arrival-rate load test

Using **wrk2** (executable typically named **wrk**):

~~~bash
# Run only on authorized test systems.
# -R is the target rate, not actual throughput.
wrk -t4 -c100 -d3m -R500 --latency \
  http://127.0.0.1:8080/api/items
~~~

- **-t4**: 4 worker threads on the generator.
- **-c100**: 100 connections.
- **-d3m**: 3-minute measurement.
- **-R500**: target 500 requests/second.
- **--latency**: print latency statistics.

wrk2 computes latency against intended schedule times to mitigate coordinated omission. Even so, **cross-check actual arrival rate**, errors, status validation, and generator saturation. An HTTP benchmark tool does not understand business invariants; for write APIs, add a validator that reads back data and checks record counts, idempotency, or checksums.

Never run heavy load tests against unauthorized production targets. Enforce limits, stop/rollback controls, and watch out for write side effects.

## 10. Java 17+ runnable: deterministic decision illustration

The program below is a **simulated comparison** that compiles and runs standalone. It does not send HTTP traffic or measure real I/O; its goal is to demonstrate computing **success count, goodput, and p50/p95/p99** for **the same 20 planned operations over 2 seconds**. For real production tests, measure the arrival schedule and record actual operations with real histograms and sample sizes.

Create **`SameLoadLatencyCheck.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class SameLoadLatencyCheck {
    record Observation(long latencyMillis, boolean success) {}
    record Run(String name, int scheduled, long seconds,
               Observation[] completed, int dropped, int inFlight) {}

    private static long percentile(long[] sorted, double fraction) {
        if (sorted.length == 0) {
            throw new IllegalArgumentException("empty observations");
        }
        int rank = (int) Math.ceil(fraction * sorted.length);
        int index = Math.min(sorted.length - 1, Math.max(0, rank - 1));
        return sorted[index];
    }

    private static Run baseline() {
        Observation[] data = new Observation[20];
        for (int i = 0; i < 18; i++) {
            data[i] = new Observation(10, true);
        }
        data[18] = new Observation(20, true);
        data[19] = new Observation(100, true);
        return new Run("baseline", 20, 2, data, 0, 0);
    }

    private static Run candidate() {
        Observation[] data = new Observation[20];
        for (int i = 0; i < 15; i++) {
            data[i] = new Observation(8, true);
        }
        for (int i = 15; i < 19; i++) {
            data[i] = new Observation(12, i < 18);
        }
        data[19] = new Observation(200, false);
        return new Run("candidate", 20, 2, data, 0, 0);
    }

    private static void report(Run run) {
        if (run.scheduled() != run.completed().length
                + run.dropped() + run.inFlight()) {
            throw new IllegalStateException("incomplete accounting");
        }
        long successes = Arrays.stream(run.completed())
                .filter(Observation::success)
                .count();
        long[] sorted = Arrays.stream(run.completed())
                .mapToLong(Observation::latencyMillis)
                .sorted()
                .toArray();

        System.out.printf(
                Locale.ROOT,
                "%s scheduled=%d completed=%d success=%d failed=%d "
                + "goodput=%.1f/s p50=%dms p95=%dms p99=%dms%n",
                run.name(),
                run.scheduled(),
                run.completed().length,
                successes,
                run.completed().length - successes,
                successes / (double) run.seconds(),
                percentile(sorted, 0.50),
                percentile(sorted, 0.95),
                percentile(sorted, 0.99)
        );
    }

    public static void main(String[] args) {
        report(baseline());
        report(candidate());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac SameLoadLatencyCheck.java
java SameLoadLatencyCheck
~~~

**Exact stdout:**

~~~text
baseline scheduled=20 completed=20 success=20 failed=0 goodput=10.0/s p50=10ms p95=20ms p99=100ms
candidate scheduled=20 completed=20 success=18 failed=2 goodput=9.0/s p50=8ms p95=12ms p99=200ms
~~~

Why:

- Baseline has 18 samples at **10 ms**, one at **20 ms**, and one at **100 ms**. With nearest-rank, p95 is the **ceil(0.95×20)=19th** sample → 20 ms; p99 is the 20th → 100 ms.
- Candidate has 15 samples at **8 ms**, four at **12 ms**, and one at **200 ms**. p95=12 ms yet p99=200 ms.
- Candidate has only 18 successes (the first three 12 ms samples succeed, while one 12 ms sample and the 200 ms sample fail). Goodput drops from **20/2=10.0/s** to **18/2=9.0/s**.

The demo deliberately gives candidate a better p95 while degrading goodput and p99. **20 observations is far too few for production p99 estimation**; this illustrates the math, not a real benchmark.

### Java instrumentation for a real operation

Measure client-side duration with `nanoTime`, recording outcome and elapsed time **even on failures**:

~~~java
// Fragment, not a standalone program.
// Assumes HttpClient client, HttpRequest request,
// and application-defined validatePayload and recordResult exist.
long beginNanos = System.nanoTime();
boolean success = false;
try {
    var response = client.send(
            request,
            java.net.http.HttpResponse.BodyHandlers.ofString());
    success = response.statusCode() == 200
            && validatePayload(response.body());
} finally {
    long elapsed = System.nanoTime() - beginNanos;
    recordResult(elapsed, success);
}
~~~

Place this inside a method handling `IOException`/`InterruptedException` per the API contract. Do not swallow interrupts; if catching `InterruptedException`, restore the interrupt status or propagate appropriately. `recordResult` must count exactly one logical completion and duration; if the generator drops a request before sending due to resource exhaustion, increment the dropped counter in the scheduler.

**Note:** a program calling `client.send` sequentially in a loop is still closed-loop. Testing at constant arrival rate requires a scheduler/concurrency model decoupled from prior request completion, with sufficient workers.

## 11. When latency diverges, cross-check with JFR and JVM/OS

Operation latency spans multiple layers. When B's p99 degrades, JFR and JVM metrics help **test hypotheses**, not replace client end-to-end latency.

| Symptom | Observation source | Meaning |
| --- | --- | --- |
| Slow socket read | **`jdk.SocketRead`** | Duration of read/network/downstream when recorded |
| Slow socket write | **`jdk.SocketWrite`** | Write phase duration and potential backpressure |
| File/disk I/O | **`jdk.FileRead`**, **`jdk.FileWrite`** | File operations with durations and bytes |
| Thread waits | **`jdk.ThreadPark`**, **`jdk.JavaMonitorEnter`** | Waiting on queues/locks/parks |
| GC pauses | **`jdk.GarbageCollection`**, GC phase events | Whether pauses align with latency spikes |
| CPU | **`jdk.ExecutionSample`**, `CPULoad` | Whether CPU is concentrated in a specific method/path |
| Allocation | **`jdk.ObjectAllocationSample`** | Whether allocation pressure drives GC/overhead |
| Backlog/pool | Thread-pool metrics, queue depth, active/pending connections | Whether the bottleneck shifted into a queue |
| OS/container | CPU throttling, disk utilization, network retransmits, RSS | Whether resource limits differ |

CLI example:

~~~bash
jfr summary before.jfr
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite before.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite before.jfr

jfr summary after.jfr
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite after.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite after.jfr
~~~

JFR has its own thresholds, settings, sampling, and recording windows. **Count=0 does not prove the operation never ran.** JFR `SocketRead` duration **is not total client end-to-end latency**; queues, CPU, GC, other network segments, connection pools, and payload parsing remain outside it. Only aligned timestamps let you link the evidence.

A common pattern: B shortens `SocketRead` latency while increasing `ThreadPark` or queue waits, hurting request p99. The change merely **shifted the bottleneck** rather than removing it.

## 12. Reading results and making the rollout decision

A complete report should have three sections:

**A. Measurement quality**

- Were offered rate and actual arrival schedule equivalent?
- Were data, resource budgets, GC/JDK, cache state, connection reuse, warm-up, and windows consistent?
- Did the generator keep up without CPU/network saturation?
- Does each run account for all scheduled/issued/dropped/completed/success/failure/outstanding counts?
- Do histograms share units, bucket boundaries, and measurement points?

**B. Results**

- Table of goodput, success/planned, errors/timeouts/retries, p50/p95/p99, deadline breach rate, max, and CPU/IO.
- Time-series and distribution curves, not only run-wide averages.
- Repeated runs, variance, and appropriate confidence/uncertainty bounds.
- Aligned JFR/metric correlations at matching timestamps, explicitly noting gaps.

**C. Predefined decision**

| Status | Criteria |
| --- | --- |
| **PASS** | Goodput, correctness, failures, p99/tail latency, and resource guardrails pass across target load levels |
| **FAIL / ROLLBACK** | Goodput drops, errors/timeouts/drops rise, data is lost, tail worsens, or resource budgets are exceeded |
| **INCONCLUSIVE** | Generator fell behind, data missing, too few samples, mismatched environments, or run noise exceeds the effect being tested |

Latency optimizations can involve legitimate trade-offs, yet they must be stated explicitly and **approved against business SLOs**—never claim an overall win when successful operations drop. Keep all runs, including failed ones, to avoid cherry-picking.

## 13. Common mistakes

1. Looking only at averages or p50, ignoring p99 and timeouts.
2. Recording latencies only for successes so fast errors and timeouts disappear from charts.
3. Holding thread/connection count constant and claiming identical offered load.
4. Ignoring dropped/late starts that introduce coordinated omission.
5. Comparing issued RPS to completed RPS, or counting attempts as successful operations.
6. Counting retry attempts as logical successes, hiding duplicate side effects.
7. Running baseline cold and candidate warm.
8. Using a different route mix, payload, cache state, or dataset.
9. Using shorter timeouts without noting it, making B fail faster with a prettier p95.
10. Ending the test before in-flight requests finish.
11. Averaging per-instance or per-minute p99s.
12. Using overly wide buckets near the SLO and claiming a 2–3 ms gain.
13. Comparing client end-to-end latency of A with server-only latency of B.
14. Forgetting data durability: HTTP 200 may not mean the operation persisted safely.
15. Letting the generator hit CPU/network saturation with no generator metrics.
16. Running only once and ignoring GC/JIT/DB-cache variance.
17. Reporting higher performance when candidate uses more CPU/memory/replicas without noting cost.
18. Concluding I/O improved from a handful of JFR events that do not cover the whole request.

## 14. Self-check

**Question 1:** With 100 clients, A issues 600 RPS while B issues only 350 RPS. B's p95 is lower. Have you proven B is faster under identical load?  
**Answer:** No. Closed-loop clients automatically throttle down when latency rises. Hold offered arrival rate constant and check actual issued/dropped/goodput.

**Question 2:** A gets 9,990 successes out of 10,000 planned, B gets 9,000; B has a lower p99. If the SLO requires success/planned ≥99.9%, can you pick B?  
**Answer:** No. B violates the correctness/availability guardrail even though its measured subset has lower p99.

**Question 3:** Why not average the p99 of three pods?  
**Answer:** Percentiles do not aggregate linearly like counters. Combine raw samples or compatible histogram buckets before computing the global percentile.

**Question 4:** Client p99 rose while JFR `SocketRead` duration dropped. Is that a contradiction?  
**Answer:** No. Queue wait, `ThreadPark`, CPU, GC, connection pools, retries, or other network segments may have grown; JFR `SocketRead` covers only part of the path and depends on thresholds.

**Question 5:** Target is 500/s for 120 seconds, yet the generator issued only 50,000 of 60,000 planned. Can you conclude the p99 SLO passes at 500/s?  
**Answer:** No. The test failed to sustain the required load; report the 10,000 unissued scheduled operations, fix the generator, and re-run.

**Question 6:** A histogram has buckets only at 100 ms and 1 s, yielding an estimated p99 of 280 ms. Should you compare it to 275 ms and announce a 5 ms savings?  
**Answer:** No. Bucket resolution is far too coarse; add finer buckets or a more accurate sample source.

**Question 7:** Candidate p50 drops 25%, p99.9 triples, errors rise, and CPU rises 40%. Verdict?  
**Answer:** Cannot be called an overall improvement. Check guardrails, repeat matched tests, isolate the bottleneck, and evaluate resource budgets before rollout.

## References

- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): percentiles, histogram aggregation, and why averaging quantiles is wrong.
- [OpenTelemetry — HTTP metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/): client/server request duration, seconds, HTTP error attributes.
- [OpenTelemetry — Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/): histograms, counters, and metric semantics.
- [wrk2 — Constant throughput, correct latency recording](https://github.com/giltene/wrk2): arrival-rate schedules, coordinated omission, and latency recording.
- [Oracle JDK 21 — Troubleshooting Guide, I/O with JFR](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf): `SocketRead`/`SocketWrite`/`FileRead`/`FileWrite`.
- [Oracle JDK 21 — jfr CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, metadata, and event filtering.
