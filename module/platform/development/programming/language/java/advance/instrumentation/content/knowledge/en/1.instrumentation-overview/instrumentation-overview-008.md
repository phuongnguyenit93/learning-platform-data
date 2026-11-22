# Application Correctness, Observation Overhead, and Limits of Collected Data

Instrumentation helps us understand what a program is doing by attaching recording points to the execution path: counters, timers, logs, traces/spans, Java Flight Recorder (JFR) events, profilers, or Java agents that transform bytecode. However, the measurement operation itself also runs inside the JVM, consumes resources, and can skew the system being observed. A system with many dashboards is not necessarily more correct or easier to diagnose.

This lesson poses three questions that must be answered together:

1. **Correctness:** When instrumentation is enabled, does the application still preserve its business contract, exceptions, state, ordering of side effects, and thread safety?
2. **Observation overhead:** How much do CPU, memory, I/O, latency, throughput, GC, and storage increase under realistic load?
3. **Data limits:** Which part of the system do the collected signals represent, are samples lost or biased, and what conclusions cannot be drawn from them?

Goal after this lesson: design safe measurement points, evaluate overhead in a controlled manner, interpret data according to coverage and reliability, and define acceptance criteria for an instrumentation mechanism.

## 1. Placing instrumentation at the right position in the execution flow

A typical measurement pipeline has two parts:

~~~text
Request -> business code -> hook/interceptor/agent -> signal creation
                                        |
                                        v
                                SDK / buffer / batch
                                        |
                                        v
                             exporter -> collector -> storage/UI
~~~

A hook can be invoked before, during, or after a business operation. Even when the exporter runs asynchronously, creating a span, reading a clock, incrementing a counter, capturing a stack trace, attaching attributes, or enqueueing data can still happen on the request-handling thread. Therefore, "asynchronous export" does not mean "zero cost on the request."

Distinguishing some collection mechanisms:

| Mechanism | What is captured | Limits to keep in mind |
| --- | --- | --- |
| Metrics (counter, gauge, histogram) | Aggregated counts, states, latency distributions | Loses per-call detail; high-cardinality labels increase cost |
| Traces/spans | Execution path and step relationships of retained transactions | Sampling, missing propagation, lost or improperly ended spans |
| Logs | Context and message at the log emission point | High volume, log-level filtering, missing correlation, sensitive data |
| JFR | JVM and application events according to recording configuration | Only enabled event types, event thresholds, and the recorded time window |
| Sampling profiler | Stack/CPU/allocation samples via a sampling mechanism | Not a complete log of every call; samples have variance and bias |
| Java agent/bytecode instrumentation | Automatically adds hooks to supported classes/methods | Depends on transformation point, transform capability, class loader, and library version |

Do not treat signal sources as equivalent copies of "the truth." A counter may count accurately at its insertion point, whereas a trace only reflects spans that were recorded, sampled, and successfully delivered to the backend.

## 2. "Do not alter behavior" is a contract that must be verified

Within the business scope, good instrumentation strives to preserve the observable properties of the program:

- **Return values and state:** results, data written to the database, messages sent, and transaction state must not change due to recording code.
- **Exceptions:** when business logic fails, the exception type, cause, and propagation path must be preserved; telemetry errors must not turn into successes or different business errors.
- **Count and order of side effects:** do not re-invoke payment, do not write an extra business message, and do not change commit/rollback timing just to take a measurement.
- **Concurrency:** do not introduce a new lock order that leads to deadlock, do not leak context across requests, and do not break interrupt/cancellation handling.
- **Resources:** do not retain references to requests or payloads for too long, do not leave streams/sockets unclosed, and do not create unbounded queues.
- **Security:** do not put passwords, tokens, personal data, or secrets into logs/spans/metric labels.

This is a goal of **semantic equivalence at the business boundary**, not a promise that two runs will have the same timing or the same thread scheduling order. Even adding a single clock read can change when the scheduler runs a thread, lock contention order, JIT cache state, and the likelihood of exposing a race condition. In concurrent programs, "adding a log makes the bug disappear" is a classic sign of the *observer effect*; the data cannot be treated as a completely neutral snapshot.

For operations that have an exact recording obligation—such as ledgers, mandatory business auditing, or transactional outboxes—design a **durable recording mechanism that belongs to the business logic**. Best-effort traces/logs can be dropped and cannot replace that guarantee.

## 3. Ways instrumentation accidentally breaks correctness

### 3.1. Mixing telemetry errors with business errors

A conceptually unsafe example: placing the business operation and the exporter call inside the same `try/catch` block, then catching any error to return a default value. When the exporter fails, a business operation that already succeeded may be treated as failed, or the original exception may be swallowed.

It is usually better to separate the two boundaries: **business logic determines the outcome**, while **best-effort collection records that outcome**. A `finally` block is useful for recording duration on both success and failure, but code inside `finally` can still throw an exception and mask the original exception; expected telemetry errors must be isolated.

### 3.2. I/O or blocking on the hot path

A hook that calls an exporter synchronously while holding a lock, processing a transaction, or running on an event loop can prolong how long resources are held. When the network stalls, timeouts are large, or the backend is unresponsive, latency spikes; in the worst case, it can cause thread starvation, deadlocks, or delayed commits. Bounded queues/batches help reduce the impact, but you still need to define behavior when the queue is full and maintain a counter for dropped signals.

### 3.3. Changing concurrency conditions and context

- Putting logging inside a `synchronized` region can alter lock contention ordering.
- Using `ThreadLocal`/MDC/trace context without closing the scope in `finally` can cause the next request to inherit the wrong trace ID, especially on a thread pool.
- Offloading work to a `CompletableFuture`, executor, callback, or messaging boundary without propagating context breaks the trace; propagating context incorrectly causes leaks.
- Instrumenting the HTTP client used by the exporter itself can create a telemetry -> export -> telemetry loop; exclude the exporter path from the relevant hooks.

### 3.4. Instrumenting the wrong class or lifecycle phase

In Java, an agent can transform bytecode when a class is loaded or, when the environment permits, retransform already-loaded classes. Not every class can be modified, and not every class structure change is supported during retransformation. A mismatch between Java agent, module access, class loader, library, and JVM can cause linkage errors, verify errors, startup failures, or missing coverage. Do not assume that enabling an agent means every method in the process is being observed.

### 3.5. Observed data becomes an unintended side effect

For example: converting an entire object to a string for logging can invoke an expensive `toString()`, trigger lazy state loading, throw exceptions, or even leak sensitive information. Capturing large bodies can increase allocation and GC time. Attaching user IDs or request IDs as metric labels can cause the number of time series to grow uncontrollably. This is a resource and security correctness issue, in addition to storage cost.

## 4. Java 17+ example: preserving business exceptions when the recorder fails

The following example illustrates **one specific property**: a `RuntimeException` from the telemetry recorder is isolated so that it does not alter the business return value or exception. This is a standalone runnable example, not yet an optimal production exporter.

File: **ObservationSafetyDemo.java**

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.LongAdder;

public class ObservationSafetyDemo {
    private static final LongAdder DROPPED = new LongAdder();

    @FunctionalInterface
    interface Recorder {
        void record(long elapsedNanos);
    }

    static <T> T observe(Callable<T> business, Recorder recorder)
            throws Exception {
        long started = System.nanoTime();
        try {
            return business.call();
        } finally {
            long elapsed = System.nanoTime() - started;
            try {
                recorder.record(elapsed);
            } catch (RuntimeException telemetryFailure) {
                DROPPED.increment();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Recorder unavailable = elapsed -> {
            throw new IllegalStateException("collector offline");
        };

        System.out.println(observe(() -> "OK", unavailable));

        try {
            observe(() -> {
                throw new IllegalArgumentException("invalid order");
            }, unavailable);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println("dropped=" + DROPPED.sum());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ObservationSafetyDemo.java
java ObservationSafetyDemo
~~~

Expected standard output:

~~~text
OK
invalid order
dropped=2
~~~

On the first call, the business logic returns `"OK"`; on the second call, it throws `IllegalArgumentException` as before. Both times the recorder fails, and the failures are counted in `DROPPED` instead of altering either business outcome. `System.nanoTime()` measures relative elapsed time within the same JVM; it is not wall-clock time for stamping timestamps across multiple machines.

**Limitations of the example:** the `record` call is still synchronous; if the recorder blocks for a long time, the request still slows down. It only isolates `RuntimeException` from the recorder and does not guarantee safety against every `Error` or exhausted JVM resources. In a real system, prefer bounded queues/batching, appropriate timeouts, controlled signal dropping, recursion prevention, and metrics for dropped counts. Do not create a loop by sending exporter errors through the failing exporter itself.

## 5. Where does observation overhead come from?

A measurement can add cost at multiple layers, not just in the network send call:

| Component | Common costs | Observable symptoms |
| --- | --- | --- |
| Hook/interceptor/bytecode | Extra calls, clock reads, context lookups, code paths no longer optimized as before | Higher CPU, higher latency on the hot path |
| Detail collection | Log formatting, serialization, stack traces, body copying, attribute creation | Higher allocation/GC, higher CPU, sensitive data exposure |
| Synchronization/buffering | Locks, atomic updates, queue contention, batch management | p99 spikes, lower throughput, full queues |
| Export and network | Compression, serialization, retries, sockets, TLS | Bandwidth, CPU, threads, send errors and latency |
| Backend | Parsing/indexing/storing/querying, retention, cardinality | Storage volume, series count, storage/query cost |
| Startup/class transform | Agent initialization, class loading/transformation | Slower startup, compatibility errors, higher initial load |

You can think of observed request latency as **business latency plus critical-path overhead and interaction effects**. This is only a mental model: GC, contention, scheduler, JIT, and queueing make the effects non-linearly additive. Exporting that runs after a request can still affect the latency of other requests because they share CPU, memory, and network.

Pay special attention to:

- **Per-event cost:** events per second and payload size; even rare events can be too expensive if they always capture stack traces or bodies.
- **Cardinality:** adding a dynamic label such as full URL, user ID, or transaction ID can create a huge number of time series. Use route templates and a bounded label set.
- **Sampling:** reducing the number of exported traces does not mean a proportional percentage reduction in cost; there is still the cost of sampling decisions, context creation, and some hooks/metrics.
- **Backpressure:** bounded buffers protect memory but mean drops can occur; unbounded buffers risk exhausting the heap. Choose a policy deliberately.
- **JFR/profiling:** overhead depends on events, thresholds, and configuration. Do not apply a blanket "JFR is always zero-cost" claim to every workload or every event set.

## 6. Measure overhead empirically, do not infer from event counts

Before rolling out broadly, define an **observation budget** alongside the application's own SLO targets: latency, throughput, CPU, heap, GC, network, telemetry volume, and percentage of dropped signals. There is no single percentage threshold that fits every service.

A meaningful comparative measurement should:

1. Include a **baseline** with the evaluated hooks disabled; compare it against a configuration with hooks enabled but export disabled, and a fully enabled configuration, to separate signal-creation cost from signal-export cost.
2. Run the same business code, JDK/JVM flags, heap, infrastructure, dataset, and load representative of production. Warm up to reduce JIT/class-loading noise.
3. Compare at the **same offered load** when evaluating latency, while also measuring maximum throughput and saturation point separately. Test low load, steady load, bursts, high concurrency, and slow/disconnected telemetry backends.
4. Repeat multiple times, alternating configuration order when possible, and observe variance; avoid drawing conclusions from a single run.
5. Record p50/p95/p99, throughput, error rate, CPU, allocation, GC pauses, heap, queue length, dropped/failed exports, network, and backend storage.
6. Re-verify correctness after each configuration, because a "fast" measurement that loses business data is unacceptable.

Example **hypothetical** figures, measured on the same request mix and load conditions:

| Metric | Without instrumentation | With instrumentation |
| --- | ---: | ---: |
| p99 latency | 80 ms | 88 ms |
| Max throughput | 5,000 req/s | 4,700 req/s |
| Collector queue drop | 0 | Occurs during load spikes |

p99 overhead = (88 - 80) / 80 × 100% = **10%**. Max throughput reduction = (5,000 - 4,700) / 5,000 × 100% = **6%**. The two numbers answer two different questions; you cannot use one ratio to infer the other. "Collector queue drop" must be measured with actual counts/rates before deciding to deploy; this table does not imply a specific drop rate.

Keep the endpoint set, time window, load generation method, and percentile calculation consistent. p99 values from two different populations do not prove overhead; the p99 of a combined set cannot be computed by averaging the p99s of subgroups. If using histograms with compatible buckets, you can sum bucket counts and then estimate quantiles on the merged distribution.

## 7. Why can collected metrics be incomplete or biased?

There are at least seven layers of limitations. When looking at a dashboard, ask which layers the data has passed through.

### 7.1. Coverage: are hooks placed on the right paths?

An HTTP server span only covers request time at the instrumented server; it does not necessarily include upstream queue time, native code calls, async work after returning the response, background schedulers, message consumers, or out-of-process steps. Proxies/AOP only intercept points that actually go through the proxy; internal self-calls that bypass the proxy may not appear. An agent may lack support for a framework version, skip already-loaded classes, or lack transform permissions.

Therefore, **not seeing a span** could mean uninstrumented code, lost context, sampling, dropping, or that the work simply never ran. There is not enough evidence to pick one explanation alone.

### 7.2. Sampling: retained samples do not equal all transactions

- **Head sampling** decides early (usually based on trace ID and probability), which saves resources without yet knowing whether the request will later fail or be slow.
- **Tail sampling** decides after seeing all or most of the trace so it can prioritize errors/high latency; in return, it must buffer data temporarily, wait for the decision, and risk losing data when buffers fill or deadlines expire.
- **Non-uniform sampling** intentionally retains more anomalous transactions, which is useful for investigation but makes the trace set non-representative of overall traffic. Do not infer the error rate directly from the error ratio in prioritized traces.

Example: there are 20,000 requests, of which 20 fail; each trace is sampled independently with 1% probability, without prioritizing errors. The probability of **capturing zero error traces** is approximately (1 - 0.01)^20 = **81.8%**. A trace dashboard showing "0 observed errors" can still correspond to 20 real errors. Use an independent error counter with well-defined semantics and clear coverage to assess total errors; use traces to investigate the execution path of recorded cases.

### 7.3. Data loss: no event does not mean the event did not happen

Data can be lost at the SDK queue, during flush, on process crash, due to filters, quotas, timeouts, network, collector, storage retention, or querying the wrong time range. A late-arriving event also makes near-real-time dashboards appear incomplete. Distinguish between:

- **Measured value of 0:** the measurement system is healthy, with a defined observation window and denominator.
- **No data points:** unknown whether the event did not occur or the pipeline was disrupted.
- **Sampled:** only tells you about the retained subset.
- **Dropped or delayed export:** the pipeline recorded less or later than reality.

Monitor the "health of telemetry itself": failed exports, queue usage, dropped spans/logs, batch duration, receiving collector count, ingest latency, flush status, and retention.

### 7.4. Measurement accuracy and clocks

A timer with the right start/end points measures the intended quantity. Measuring from when the server receives a request does not measure total client-side time. Recording processing time after the response has been sent produces a different quantity. Wall-clock time can be adjusted; clocks across machines can drift. Use a monotonic clock like `System.nanoTime()` for local durations, and handle cross-machine timestamp comparisons carefully.

Histograms have resolution limits imposed by buckets; aggregation loses the detailed shape of the distribution. Measurement precision and the accuracy of a metric's **meaning** are two different issues: a microsecond-accurate timer cannot rescue instrumentation placed at the wrong business boundary.

### 7.5. Aggregation and denominators

A value like "500 errors" is meaningless without knowing the time window, service, version, route, error type, and corresponding total requests. Per-process counters can reset on restart; rates must handle resets properly. Do not average the p95/p99 of subgroups to treat it as the p95/p99 of all users. Do not multiply sampled trace counts by 100 to estimate error counts if the sampling mechanism does not satisfy the required probability and representativeness assumptions.

### 7.6. Bias from altering the system

Instrumentation can slow down the application, change scheduling, alter JIT compilation strategies, or fill queues: data after enabling an agent is data from **the system with the agent attached**. High-frequency profilers can alter the very phenomenon being investigated. Compare against a baseline, use less intrusive tools when appropriate, and clearly document the measurement environment.

### 7.7. Context, security, and interpretation

A trace ID does not prove two events are causally related if propagation is broken; temporal correlation alone does not prove root cause. Mislabeling or renaming events between versions makes dashboards look continuous while semantics have changed. Removing/redacting sensitive data can intentionally leave detail fields missing; that is a design constraint, not a bug to "fix" by logging more secrets.

## 8. Choosing the right signal for the question

| Question | Preferred signal | Do not conclude |
| --- | --- | --- |
| Request error rate in 5 minutes? | Counter with clear outcome definition and denominator; check coverage/drops | Error rate in sampled traces = system-wide error rate |
| Which step made a request slow? | Trace with complete spans/context; cross-check logs and timers | Missing span = step did not run |
| Is there lock contention/GC pause? | JVM metrics, JFR, and properly configured profiler | One stack sample represents all execution |
| Why is memory growing? | Heap/allocation metrics, JFR/profiler, heap dump when needed | One allocation event is the total allocation |
| How many orders were successfully paid? | Trusted business data source (DB/outbox/ledger) | Count of "payment success" logs is definitely exact |
| Is the collector overloaded? | Queue utilization, failed exports, drops, ingest delay | Silent dashboard means application is healthy |

Diagnostic rule: use at least **one independent source** to validate critical hypotheses, especially when the telemetry pipeline shows signs of failure. Clearly define the measurement window, environment, deployed version, tags, and sampling rate.

## 9. Design policies to control risk

### 9.1. Keep the observer fail-safe

- Avoid synchronous network I/O and heavy processing on the request path; bound the latency/CPU budget of hooks.
- Bound queues, batch sizes, payload sizes, and attribute counts; define behavior when full (counted drops, additional sampling, or another accepted mechanism).
- Separate domain errors from telemetry errors. For best-effort signals, exporter failures must not determine transaction outcomes.
- Ensure scopes/spans/contexts are closed in `finally` or `try-with-resources`; do not leak `ThreadLocal` on executors.
- Prevent instrumentation loops and recursion; avoid instrumenting the exporter's internal logic.
- Provide switches to disable/reduce detail/adjust sampling during incidents and rehearse rollback procedures.

### 9.2. Collect data intentionally

- Choose metric names, units, insertion points, and outcomes with consistent semantics; document "where start/end are measured from."
- Use low-cardinality labels, such as route templates instead of raw URIs with IDs. Avoid putting identifiers or secrets into labels.
- Only log attributes that help answer specific questions; mask or strip sensitive data before it enters the pipeline.
- Attach service/environment/version, trace/span context, and sampling policy so readers know which subset they are viewing.
- Set retention limits appropriate for investigation goals; understand that old data is deleted per policy.

### 9.3. Verifiable design

For each important measurement point, specify four things:

1. **Quantity:** exact definition of which events are counted, what the unit is, and valid labels.
2. **Source and coverage:** which execution paths have hooks; which paths are not observed.
3. **Data loss policy:** sampling, buffer limits, drop/retry, shutdown/flush, retention.
4. **Budget and guardrails:** maximum acceptable overhead per SLO, pipeline health indicators, actions when thresholds are exceeded.

This is a contract for both the instrumentation author and the dashboard user. "Having a metric" is only meaningful when accompanied by its definition, coverage, and data quality.

## 10. QA process before broad rollout

Test in a representative environment, then roll out via canary with clear stop criteria.

| Test scenario | What to verify |
| --- | --- |
| Successful request, returns data, calls DB/messaging | Result and side-effect counts match baseline; duration/attributes within scope |
| Request throws exception, rollback, timeout, interrupt/cancel | Original exception intact; not swallowed, no extra commit; scope/context closed |
| Collector disconnected, returns errors, abnormally slow | Business logic meets target SLO; retries/queues bounded; lost telemetry counted |
| High load, bursts, many threads, lock contention | p95/p99, CPU, heap, GC, throughput; no deadlocks or context leaks |
| Sampling changed, exporter queue full, process restart | Know what is sampled/dropped; flush/shutdown follows policy; data-loss alerts fire |
| JDK/framework/agent upgrade, different class loading | No class transform/linkage errors; re-verify coverage at key measurement points |
| Input contains tokens, user IDs, large payloads | Proper redaction, no high-cardinality labels; size and retention limits enforced |

Beyond testing happy-path examples, perform **fault injection** on the observation system: shut down the collector, induce timeouts, fill queues, disconnect the network, restart processes, and lower sampling. Instrumentation working normally when the collector is healthy is only a necessary condition, not a sufficient one.

Acceptance criteria should be separated into three axes:

- **Correctness PASS:** business contract and error paths hold, no unintended side effects, concurrency/security verified.
- **Overhead PASS:** latency/CPU/allocation increase and throughput drop are within the agreed budget under representative load; backend cost is known.
- **Data-quality PASS:** drops/lag are detectable, coverage is documented, sampling and semantics are documented; dashboards do not turn missing data into zero.

When any axis fails, reduce frequency/data volume, adjust hook placement, fix the exporter, or roll back. Never accept business errors just to get more traces.

## 11. Synthesis scenario: investigating slowness in the payment flow

A payment service has an agent enabled to monitor latency. After deployment, p99 increases from 80 ms to 88 ms; the trace dashboard shows few errors, while the payment system records several failed transactions.

Analyze in order:

1. **Confirm correctness:** compare transaction status, idempotency keys, and the number of gateway calls from business data sources. Verify hooks do not re-invoke payment or swallow exceptions when the exporter fails.
2. **Isolate overhead:** keep the same offered load; run baseline, local recording only, and then full export. Compare CPU, allocation, locks, queue depth, and p99 under the same request mix; test with a slow collector.
3. **Interpret data within scope:** check sampling policy, trace context across the gateway and queues, failed exports/dropped spans counts, and ingest latency. Few error traces are not enough to prove few business errors.
4. **Reduce cost with verification:** remove raw payloads, reduce attributes/high-cardinality labels, bound queues, adjust sampling appropriately; re-measure and confirm transaction semantics.
5. **Make a decision:** only keep the new configuration if correctness, overhead, and data quality all pass their thresholds, with a way to detect when telemetry degrades.

The same "10% p99 increase" can come from hooks, exporter CPU contention, GC from allocations, lock contention, or workload shifts; isolate the evidence before blaming one component. The same "0 error traces" can come from no errors, sampling, missing coverage, or pipeline data loss; use an independent source for cross-checking.

## 12. Common misconceptions to avoid

- **"We have traces, so every request is observed."** False when sampling, missing propagation, uninstrumented paths, or export losses exist.
- **"No logs means no errors."** Logs can be filtered, dropped, written to the wrong place, or not yet delivered to the backend.
- **"An async exporter does not affect latency."** Hooks, allocations, queues, and resource contention still have costs.
- **"More attributes are always better."** Cardinality, privacy, payload size, and processing costs have limits.
- **"Enabling JFR/profiler always has a fixed overhead."** Cost depends on version, events/configuration, and workload; it must be measured.
- **"Instrumentation is read-only, so it cannot change behavior."** Probe effects, locks, logging/`toString`, exceptions, bytecode transformation, and resource usage can all alter outcomes.
- **"The average of p99s equals the overall p99."** Quantiles are not additive or averageable like counts.
- **"Losing telemetry is a business failure."** Only true if the business design specifies that the signal is mandatory; normally, best-effort observability must be decoupled from transactions.

## 13. Self-check questions

1. If an exporter throws a `RuntimeException` inside an interceptor's `finally` block, what can happen to a business exception that is propagating? How would you isolate the two error sources?
2. Why does reducing trace sampling from 100% to 10% not guarantee a 90% reduction in CPU overhead?
3. A dashboard stops showing data points after a deploy. What are three different explanations, and which metrics do you need to distinguish them?
4. With 20 errors and 1% head sampling, why is it completely possible to have zero error traces stored?
5. How do you verify that instrumentation does not break transactions, hold locks too long, or leak sensitive data?
6. Which metric, trace, log, JFR, or business data source would you choose when you need to confirm that an order was actually paid?

**Core takeaway:** Observation is useful when the application remains correct, overhead stays within budget, and readers understand which part of reality the data represents. Always evaluate all three aspects together.

## Further reading

- [Oracle Java 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent mechanisms, `premain`/`agentmain`, and bytecode transformation.
- [Oracle Java 21 — Instrumentation API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities and limitations of class retransformation.
- [Oracle — Java Flight Recorder troubleshooting](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html): JFR overhead depends on the application and configuration.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head/tail sampling and implications when inferring from retained traces.