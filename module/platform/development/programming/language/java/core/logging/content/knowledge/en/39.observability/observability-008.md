# Log Sampling in Java Core Logging

## Learning Objectives

This lesson belongs to the **Observability** group, covering **Log sampling**. In a high-traffic Java system, each request, message, or background operation can generate dozens of log lines. Sending all DEBUG/INFO logs to the collector can increase CPU, I/O, bandwidth, storage costs, and noise during investigations. **Log sampling** is the deliberate selection of a subset of log events according to an explainable policy, in order to preserve useful observability signals within a defined resource budget.

After this lesson, you will be able to:

- Distinguish between **sampling**, **level-based filtering**, **rate limiting**, **aggregation**, **deduplication**, and **unintentional log loss**.
- Explain random sampling, deterministic sampling by trace/request ID, ratio-based, threshold-based, severity-based, and context-based sampling.
- Decide **where to sample** in the Java → appender → agent → collector pipeline, especially when aiming to save log-creation costs right at the source.
- Build a strategy that does not drop critical error, security, audit, or business events according to policy.
- Run a standalone Java 17 example with deterministic sampling decisions and inspect the `LogRecord`s that actually reach the `Handler`.
- Apply similar principles when using SLF4J/Logback, Log4j 2, tracing, and OpenTelemetry without confusing log sampling with trace sampling.
- Evaluate statistical bias, impact on dashboards/alerts, and how to record the number of filtered-out events.
- Test sampling under load, verify correlation, and avoid log storms, data leaks, or silent log loss.

**Principle:** Sampling is an **intentional drop** policy, not a guarantee that every kept log is durably stored. Important logs must be classified based on actual requirements before deciding whether they can be sampled.

## 1. Why Is Log Sampling Needed?

A service handling 5,000 requests/second, with each request emitting 10 INFO/DEBUG events, will generate about 50,000 log events/second before counting errors, stack traces, or background jobs. If each event averages 500 bytes, the raw payload alone is about 25 MB/second, excluding protocol overhead, indexing, replicas, compression, and metadata. These illustrative numbers show that logging everything can exceed collector capacity or storage budgets.

Sampling helps:

1. Reduce log volume from high-frequency operations with low investigative value, such as successful health checks, cache hits, heartbeats, and routine requests.
2. Keep a sample capable of helping analyze representative behavior in staging/production environments.
3. Concentrate detailed logs around selected requests/traces, instead of keeping random individual events that break causal chains.
4. Reduce serializer/appender/agent overhead **if the decision is made early enough**.
5. Reduce noise and prevent collector/queue overload from impacting application latency.

However, sampling also has an informational cost: events excluded from the sample cannot be recovered from that log sink. Therefore, you need **aggregate count metrics**, **tracing**, and a policy that preserves critical events so you do not equate "no log found" with "the event did not happen."

### A Simple Calculation

Suppose an INFO log group has a keep rate of `p=0.10`. Under an independent selection model, the expected value is about 10 events kept per 100 events. However, within any small window, 8, 13, or even 0 events might be kept. **10% sampling is not an exact cap of 10 events per 100 events.**

If the goal is not to exceed **100 events/second**, a probabilistic sampler with `p=0.10` does not guarantee that limit when input spikes to 100,000 events/second. When rate capping is needed, you must consider a rate limiter/token bucket or a separate quota mechanism.

## 2. Concepts: Sampling Is Not Synonymous with Filtering or Dropping

| Mechanism | Question It Solves | Characteristics |
| --- | --- | --- |
| **Level filter** | Should a `DEBUG` event be emitted when the logger is set to `INFO`? | Decision by severity, usually deterministic |
| **Log sampling** | Among eligible events, which events/traces are kept? | Keeps a subset per policy, can be probabilistic or deterministic |
| **Rate limiting** | At most how many events or bytes in a given time window? | Caps rate or quota; can be combined with sampling |
| **Deduplication** | Can equivalent repeated events be merged? | Requires a key and a time window/equivalence definition |
| **Aggregation** | Can individual events be replaced with summary statistics? | Keeps counters/histograms instead of detailed logs |
| **Drop due to overload** | How many events were lost due to a full queue, appender, or collector failure? | Not a valid statistical sample without a known probability policy |
| **Retention** | How long after storage are saved logs deleted? | Handled in the storage lifecycle, not initial event selection |

**A pipeline can use multiple mechanisms in sequence.** For example, the logger level blocks TRACE/DEBUG globally, a custom sampler keeps 10% of INFO from noisy packages, WARN/ERROR are kept, then the agent has a quota and the collector has an ingest filter. When debugging, you must know **every layer** that can drop events; do not label every "log not found" case as sampling.

### Sampling Before or After Formatting?

Example path:

```text
Java call site
  |
  +-> evaluate arguments / create message
  |
  +-> logger level gate
  |
  +-> early sampling decision (if any)
  |
  +-> event object / expensive formatting
  |
  +-> appender -> async queue -> stdout/file/network
  |
  +-> log shipper -> collector sampling -> index
```

This is a **conceptual diagram**; the actual order depends on the framework and how the API is called. A sampling filter attached at the collector can reduce indexing costs, but **does not reduce** Java message-creation CPU, appender throughput, serialization, or bandwidth between the JVM and the collector. A sampling filter executed before the event is created/formatted can further reduce costs at the source, but cannot prevent Java from evaluating expensive arguments **before the method call** if the caller code already computes them.

## 3. Types of Logs That Should Not Be Sampled Arbitrarily

Before choosing p=10%, classify your logs.

| Event Group | Typical Appropriate Policy | Why |
| --- | --- | --- |
| Normal flow DEBUG/TRACE | Aggressive sampling or disabled by environment | Very high volume and primarily for detailed investigation |
| INFO for successful requests, health checks, cache hits | Sampling/aggregation/rate limiting as needed | High volume; metrics are usually sufficient for an overview |
| WARN from transient, self-healing retries | Policy by frequency/error type; keep summary and terminal outcome | Avoids log storms while still showing retry status |
| Unhandled ERROR | Usually kept in full per policy, with separate alerts/metrics | High investigative value; some systems still need protective quotas |
| Mandatory audit/security decisions | **Do not sample if audit requirements mandate full retention** | May involve legal obligations and evidence |
| Money transfers, permission changes, data deletion | Dedicated event/transactional audit pipeline | Must not depend on the diagnostic log sampler |
| Sensitive data | **Redact/minimize before any logging** | 1% sampling does not make leaking a secret safe |
| Infrequent exceptions | Can be kept in full and classified by error code | Rare errors easily disappear in random samples |

There is no universal rule that "WARN/ERROR are always saved" in every system: the backend can still experience overflows, network outages, retention limits, or other filters. More accurately, **your sampler does not intentionally drop** those levels per policy, whereas delivery/durability must be tested separately.

An `ERROR` event containing a token in its stack trace is still a security violation if kept 100%. **Redaction and sampling solve two different problems.**

## 4. Sampling Strategies

### 4.1. Random/Bernoulli Sampling

For each eligible event, generate a random variate `u` in the interval [0,1), and keep when `u < p`. If `p=0.05`, the event has a 5% probability of being kept. Pros: easy to understand, cheap, requires no stable key. Cons: logs from the same request can be kept/dropped independently, breaking the investigation chain.

Pseudocode:

```text
if event.isCritical:
    KEEP
else if randomUniform0to1() < 0.05:
    KEEP
else:
    DROP
```

**Do not rely on random sampling to guarantee an exact quota per window.** A very short burst can still produce many kept events. For observing a rare incident, random sampling may miss the entire related log sequence unless there is a rule prioritizing error events.

### 4.2. Deterministic/Hash-Based Sampling

Instead of drawing randomly for each event, you can hash **a stable key** such as a trace ID or request ID and select it if the hash falls into the kept bucket set. The same key with the same configuration will yield the same decision.

```text
bucket = stableHash(traceId) mod 100
keep = bucket < 10
```

This is **pseudocode**. A production implementation should use a hash with a stable distribution, tested against the system's ID format, consistent key normalization, and a versioned policy. Using a simple `String.hashCode()` in a lesson helps illustrate the rule, but it is **not a cryptographic hash** and is not guaranteed to distribute well across all key sets.

Benefits: INFO/DEBUG logs belonging to the same trace share the same decision, so when a trace is kept, its group of detailed logs tends to stay together. However:

- If WARN/ERROR are always kept, a trace that was sampled out can still have error logs. This is a **severity override**, not a contradiction.
- If the trace ID is missing/invalid, there must be an explicit fallback—do not default to a constant `null` and accidentally route everything into the same bucket.
- If `p` changes while a request is in flight, the same trace might receive different decisions across calls. For trace-wide consistency, store the sampling decision/policy version in the context or ensure configuration stability per request.
- If different services use different hashes, the same trace might be sampled in service A but dropped in service B; a consistent cross-service policy or a clearly defined scope is needed.
- If the key is chosen by an untrusted client, the client could try IDs until one gets sampled. Do not use sampling rules as a security/authorization boundary.

### 4.3. Fixed Interval: One in N

For example, keeping every 100th event via an incrementing counter:

```text
if counter.incrementAndGet() % 100 == 0:
    KEEP
else:
    DROP
```

This pseudocode illustrates a steady cadence, making it easy to cap relatively under steady traffic. However, it depends on **arrival order**, does not preserve trace context, and can be biased if traffic has cycles correlated with the counter. A counter per JVM/pod does not create a cluster-wide quota; if restarted, the counter resets and the cycle shifts. `AtomicLong` helps make updates thread-safe within a single process, but does not synchronize across replicas.

### 4.4. Rate Limiting and Token Bucket

A token bucket allows short bursts while capping the average rate. For example, a bucket with a maximum of 100 tokens, refilling at 20 tokens/second, where each kept event consumes one token. When tokens run out, events can be dropped, deferred, or routed to another policy.

Difference from Bernoulli:

- Probabilistic sampling `p` applies **proportionally to input**: output volume grows with traffic.
- A token bucket focuses on **absolute volume**: if traffic spikes sharply, the effective keep rate drops.

A common design combines them: sample 10% of DEBUG by trace, then apply a final quota to protect the sink. However, if the final quota drops events randomly without regard to trace, a selected trace may lose some lines. If keeping the entire detailed trace is required, you must calculate **per-trace budgets** and corresponding admission/scheduling mechanisms.

### 4.5. Adaptive Sampling

The policy changes based on traffic, queue depth, CPU, log bytes, or cost budget. For example, reducing the INFO keep rate from 10% to 1% when the ingest rate exceeds a threshold. Key considerations:

- Expose/record metrics for `sampling_policy_version` and **effective sampling probability**; dashboards must be aware of the change.
- Include hysteresis and rate limits on policy changes to prevent constant oscillation.
- Distinguish intentional sampling-rate reductions from event drops caused by queue overflow.
- Do not allow adaptation to drop audit/security or critical errors outside policy authority.
- Do not base log priority control on untrusted metadata.

### 4.6. Reservoir Sampling and Windowed Representative Samples

Reservoir sampling selects **k elements from a stream** under specific statistical conditions without knowing the total number of elements in advance. It is useful when you want a fixed-size sample after a time window or dataset, but it has limitations: it must maintain state and **wait for enough data/the window to close** to know the final sample; it does not fit directly with "emit each log immediately if selected" if exact sample probabilities must be preserved. In multi-pod systems, you need a merge design or per-shard quotas.

Do not call a token bucket or "every Nth event" reservoir sampling; they have different mechanisms, biases, and probability calculations.

## 5. Head-Based, Tail-Based, and Error-Aware Sampling

In tracing, **head-based sampling** typically decides at the start of a trace before knowing the outcome. **Tail-based sampling** decides after observing enough trace data, such as keeping traces with errors or high latency. Log sampling can borrow similar ideas, but this **does not mean** Java logging frameworks or the OpenTelemetry Logs SDK automatically provide tail sampling for logs.

### Head-Based Early Selection

If the application makes the sampling decision by trace ID as soon as a request arrives:

- Detailed logs can be dropped at the source, saving allocation/transport.
- Events within the same trace can share the same decision.
- However, if the request fails later, logs from the start of the trace may have already been dropped and cannot be recovered.
- A WARN/ERROR override preserves the error marker, but does not bring back already-dropped INFO/DEBUG logs.

### Tail-Based Keeping After Knowing the Outcome

To keep **all logs of slow/failing requests**, you can buffer logs within a bounded scope until the request finishes; once the outcome is known, decide whether to flush or discard.

```text
request starts
   |
   +-- buffer limited INFO/DEBUG events, keyed by request/trace
   |
request finishes
   |
   +-- if ERROR / slow / selected route -> flush captured context
   |
   +-- otherwise -> keep small sample or discard
```

This is a **custom design**, not a guaranteed default feature. You must bound RAM, event size, buffer lifetime, handling of hung requests/worker crashes, timeout cleanup, and tenant isolation. If the buffer holds sensitive data, redaction must be applied before storing in the buffer—do not wait until flush.

Tail-based sampling does not eliminate overload on its own: you must define what happens if there are too many open requests, the queue fills up, or shutdown occurs before the decision. A safe approach is to keep **aggregate metrics**, emit critical terminal logs immediately, and only buffer supplementary logs within a quota.

### Combining with Tracing

A system can use:

- Trace sampling per OpenTelemetry policy.
- Independent log sampling by level/logger/trace ID.
- Correlation fields `trace_id` and `span_id` on kept logs.

**A sampled trace does not necessarily mean every log carrying that trace ID will be saved.** Conversely, an ERROR log may be kept even if its trace was not exported. Queries and operator expectations must be designed around this reality.

## 6. Designing an Auditable Sampling Policy

Before writing code, describe the policy in a table:

| Group | Condition | Rate/Strategy | Priority Decision |
| --- | --- | --- | --- |
| Mandatory audit/security | `event_category=AUDIT` | Do not sample under log policy | Always **eligible to keep**, separate durable sink |
| Critical errors | `level=ERROR` or `SEVERE` | Bypass general sampler | Keep error event and safe exception type |
| WARN from retried timeouts | `event_code=downstream.timeout` | Can rate-limit detailed logs, keep terminal summary | By error category and outcome |
| Normal request INFO | `event_code=request.completed` | 5–20% by trace ID if appropriate | Record rate/sequence of policy changes |
| DEBUG from noisy packages | `logger=com.example.chatty.*` | 1% or disabled in production | Configured per logger |
| Successful health checks | `event_code=healthcheck.ok` | Aggregate into metrics; optionally keep rare sample | Do not mask health check failures |

**The 1%, 5%, and 20% rates are illustrative examples**, not universal recommendations. Actual values must be derived from volume, traceability needs, cost, incident characteristics, and compliance requirements.

### Rule Evaluation Order

A policy can evaluate in this order:

1. **Data minimization/redaction:** determine what information is allowed to be logged; never rely on sampling to hide secrets.
2. **Classify severity/category:** audit, security, error, info/debug, message type, service.
3. **Critical override:** events approved as mandatory must not be intentionally dropped by the sampler.
4. **Eligible sampling:** hash/rate/random with configured `p`.
5. **Appender/sink routing:** route kept logs to the right destination.
6. **Transport/durability:** verify queues, collectors, and retention separately.

The actual technical order may vary across backends; the core requirement is that **critical events are not subjected to the general sampler** and redaction still operates on every path. If a custom sampler at an appender drops an INFO log before the security policy detects that it is an audit event, the configuration has misplaced responsibilities.

### Who Is Allowed to Adjust Sampling?

Production sampling can cause missing data during incident investigations. Changes should have an owner, review, service/logger scope, effective time, version, rollback plan, verification dashboard, and alerts if critical paths are affected. Do not allow public clients to set a `sample_rate=0` header to disable error logging. With dynamic configuration, ensure policies load safely and have defaults when the config service loses connectivity.

## 7. Java 17 Example: Consistent Sampling by Trace ID

This standalone **JDK 17+** example requires no SLF4J, Logback, broker, or collector. The program:

1. Uses a simple policy: **WARN/ERROR are always allowed to be logged**, INFO/DEBUG are kept only if `Math.floorMod(traceId.hashCode(), 4) == 0` (about 1 in 4 buckets), and events missing a trace ID are kept to avoid losing hard-to-diagnose data.
2. Calls `java.util.logging.Logger` for kept events, attaching an in-memory handler to inspect the **`LogRecord`s actually emitted**.
3. Counts KEEP/DROP decisions, verifying content/levels and trace consistency.
4. Uses no randomness or clock, so stdout is deterministic.

**Illustrative limitation:** `String.hashCode()` is not a cryptographic hash, and real-world input data may be unevenly distributed. For production sampling, use a verified stable-distribution hash or a sampling library with an established contract; the same policy does not automatically guarantee an exact 25% rate on small sets.

Create the file **`LogSamplingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogSamplingDemo {
    enum Severity {
        DEBUG, INFO, WARN, ERROR
    }

    record Event(String traceId, Severity severity, String code) {
    }

    static boolean selected(String traceId) {
        return Math.floorMod(traceId.hashCode(), 4) == 0;
    }

    static boolean keep(Event event) {
        if (event.severity() == Severity.WARN
                || event.severity() == Severity.ERROR) {
            return true;
        }
        if (event.traceId() == null || event.traceId().isBlank()) {
            return true;
        }
        return selected(event.traceId());
    }

    static Level toJulLevel(Severity severity) {
        return switch (severity) {
            case DEBUG -> Level.FINE;
            case INFO -> Level.INFO;
            case WARN -> Level.WARNING;
            case ERROR -> Level.SEVERE;
        };
    }

    static String displayTrace(String traceId) {
        return traceId == null || traceId.isBlank()
                ? "none" : traceId;
    }

    public static void main(String[] args) {
        List<Event> input = List.of(
                new Event("trace-A", Severity.INFO, "cache.hit"),
                new Event("trace-A", Severity.DEBUG, "cache.lookup"),
                new Event("trace-B", Severity.INFO, "checkout.started"),
                new Event("trace-D", Severity.INFO, "checkout.started"),
                new Event("trace-D", Severity.DEBUG, "inventory.lookup"),
                new Event("trace-C", Severity.WARN, "downstream.slow"),
                new Event("trace-B", Severity.ERROR, "payment.failed"),
                new Event("", Severity.INFO, "no.trace"),
                new Event("trace-E", Severity.INFO, "user.viewed"));

        Logger logger = Logger.getLogger("demo.sampling");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        List<String> captured = new ArrayList<>();
        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record.getLevel().getName() + " "
                            + record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };
        sink.setLevel(Level.ALL);
        logger.addHandler(sink);

        int kept = 0;
        int dropped = 0;

        try {
            for (Event event : input) {
                boolean accepted = keep(event);
                String trace = displayTrace(event.traceId());

                System.out.println("decision="
                        + (accepted ? "KEEP" : "DROP")
                        + " level=" + event.severity()
                        + " trace=" + trace
                        + " event=" + event.code());

                if (accepted) {
                    kept++;
                    logger.log(toJulLevel(event.severity()),
                            "event=" + event.code() + " trace=" + trace);
                } else {
                    dropped++;
                }
            }

            List<String> expected = List.of(
                    "INFO event=checkout.started trace=trace-D",
                    "FINE event=inventory.lookup trace=trace-D",
                    "WARNING event=downstream.slow trace=trace-C",
                    "SEVERE event=payment.failed trace=trace-B",
                    "INFO event=no.trace trace=none");

            if (!captured.equals(expected)
                    || kept != 5 || dropped != 4
                    || selected("trace-A")
                    || !selected("trace-D")) {
                throw new IllegalStateException(
                        "Sampling assertions failed");
            }

            System.out.println("kept=" + kept);
            System.out.println("dropped=" + dropped);
            System.out.println("captured=" + captured.size());
            System.out.println("trace_consistency=PASS");
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac LogSamplingDemo.java
java LogSamplingDemo
```

**Exact stdout:**

```text
decision=DROP level=INFO trace=trace-A event=cache.hit
decision=DROP level=DEBUG trace=trace-A event=cache.lookup
decision=DROP level=INFO trace=trace-B event=checkout.started
decision=KEEP level=INFO trace=trace-D event=checkout.started
decision=KEEP level=DEBUG trace=trace-D event=inventory.lookup
decision=KEEP level=WARN trace=trace-C event=downstream.slow
decision=KEEP level=ERROR trace=trace-B event=payment.failed
decision=KEEP level=INFO trace=none event=no.trace
decision=DROP level=INFO trace=trace-E event=user.viewed
kept=5
dropped=4
captured=5
trace_consistency=PASS
test=PASS
```

### Why Is the Output Correct?

- `trace-A` and `trace-B` do not fall into bucket 0 under modulo-4 hashing, so their INFO/DEBUG events are dropped.
- `trace-D` falls into bucket 0; both events with the same trace ID are kept together.
- WARN from `trace-C` and ERROR from `trace-B` are kept **even though their traces are not in the sample**; the severity override works as specified by the policy.
- The event without a trace is kept by an intentional fallback. In a system with high traffic of untraced events, this fallback can increase volume; it must be monitored and adjusted if appropriate, but never silently dropped.
- JUL uses `Level.FINE` for DEBUG, `Level.WARNING` for WARN, and `Level.SEVERE` for ERROR. The handler genuinely captures the 5 events that passed the sampling decision; it does not prove that a collector/index received them.
- `setUseParentHandlers(false)` avoids uncontrolled output from the root logger in the demo program.
- Assertions compare the **entire list** of captured logs against expectations, checking KEEP/DROP counts and trace bucket selection. Only after everything passes does the program print `test=PASS`.

This is a **call-site sampling gate**, not an official Logback/Log4j 2 implementation. In production applications, a centralized approach in a logger filter or wrapper is usually easier to keep consistent than repeating `if (selected)` across many services.

### Additional Experiments

1. Change the bucket modulus from 4 to 2 while keeping the same assertions: the test may fail because the sampled set changes. If you want to change `p`, you must update and re-verify expectations.
2. Modify `keep` so that WARN also uses the hash: the `downstream.slow` line will disappear and the expected list will no longer match. This serves as a regression test for the critical override policy.
3. Change one event's trace ID to `trace-E`: the events are no longer linked by trace consistency. This illustrates why IDs must be propagated properly across async threads/services.
4. Add many events missing a trace: output grows because the fallback currently keeps all; this is not a Java bug, but a budget issue that needs to be detected via metrics.

## 8. Logback: Logger Filter or Appender Filter?

With SLF4J + Logback Classic, there are at least two places to put filtering logic:

- **TurboFilter** operates on the logger call path in Logback and can reject before creating an `ILoggingEvent` in many situations, thereby avoiding some unnecessary allocation/formatting.
- **Appender filter** runs on each appender and decides whether an event reaches a specific sink; at this point the event has usually already been created, so it does not save all caller costs.
- **Collector filter** runs after the JVM/appender has sent the event; it saves downstream ingestion/indexing without eliminating source costs.

Always check the **exact framework and version**. `TurboFilter` is a Logback Classic-specific concept, not a standard SLF4J API. The `DENY`, `NEUTRAL`, and `ACCEPT` results must also be understood at each layer: `NEUTRAL` means **continue evaluating other rules**, not a guarantee that the event will be written to every sink.

### Trace ID TurboFilter Example

The following Java snippet is a **Logback integration class** and cannot run standalone with `javac` without dependencies. It actively drops INFO/DEBUG from a noisy package when the trace ID does not fall into the sampled bucket, while letting WARN/ERROR and other loggers pass through normally.

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.turbo.TurboFilter;
import ch.qos.logback.core.spi.FilterReply;
import org.slf4j.MDC;
import org.slf4j.Marker;

public final class TraceSamplingTurboFilter extends TurboFilter {
    @Override
    public FilterReply decide(Marker marker, Logger logger,
                              Level level, String format,
                              Object[] params, Throwable throwable) {
        if (!logger.getName().startsWith("com.example.chatty.")) {
            return FilterReply.NEUTRAL;
        }

        // Keep WARN, ERROR, and higher severity levels per rule.
        if (level.isGreaterOrEqual(Level.WARN)) {
            return FilterReply.NEUTRAL;
        }

        // Only sample INFO and DEBUG in noisy loggers.
        if (level != Level.INFO && level != Level.DEBUG) {
            return FilterReply.NEUTRAL;
        }

        String traceId = MDC.get("trace_id");
        if (traceId == null || traceId.isBlank()) {
            return FilterReply.NEUTRAL;
        }

        boolean selected =
                Math.floorMod(traceId.hashCode(), 10) == 0;
        return selected ? FilterReply.NEUTRAL : FilterReply.DENY;
    }
}
```

**Illustrative Logback configuration** (place the class above on the classpath):

```xml
<configuration>
    <turboFilter class="com.example.logging.TraceSamplingTurboFilter"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level trace=%X{trace_id} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In the XML example, the class must reside in the configured package; the Java snippet omits a `package` declaration, so in real use you must place the file in `com.example.logging` and add the package declaration, or update `class` to the exact fully-qualified name. This configuration teaches the principle and is **not a recommendation to set root to DEBUG across production**. Use appropriate production logger levels and scope strictly to the target packages.

Analysis:

1. Only loggers whose names start with `com.example.chatty.` have the sampler applied; other loggers return `NEUTRAL`.
2. WARN/ERROR proceed to other rules and **are not rejected by this filter**; however, effective levels or appender filters can still drop them at a later layer if configured differently.
3. Missing trace IDs are passed through to avoid losing uncorrelated data; monitor the missing-context rate and volume.
4. `Math.floorMod(..., 10) == 0` selects one out of 10 buckets using the demo hash; actual distribution must be tested against production trace IDs.
5. MDC is read in the caller context at the moment `TurboFilter` decides; across async boundaries, verify context propagation and cleanup.
6. The filter does not perform redaction or authorization. If a log contains secrets, sampling does not make it safe.

**Technical limitation:** This rule applies to INFO and DEBUG for a package without distinguishing individual event codes. If an audit/security INFO event happens to live under `com.example.chatty.*`, it could be sampled out. In production, separate the audit route or add reliable classification earlier; do not rely on level alone. Therefore, write regression tests for important event codes in that package.

### Unit and Integration Testing a TurboFilter

- Attach a `ListAppender` to a test logger, emit multiple trace IDs, and verify event counts and levels.
- Negative test: unselected noisy events do not reach the `ListAppender`/sink.
- Positive test: WARN/ERROR and loggers outside the package are not blocked by the sampling filter.
- Missing MDC test: has a clear fallback policy and does not accidentally attach the previous request's trace.
- Parent/additivity and async sink test: avoid duplicates at root or dropped events after sampling.
- Policy reload test: does the decision for the same trace change unexpectedly?
- Load test: is the filter thread-safe, low-allocation, and free of hot locks or shared random contention?

If the same rule must be used across multiple languages/services, define the policy and hashing algorithm **in a protocol specification**, rather than assuming Java's `String.hashCode()` matches Go/Python/Node hashes.

## 9. Log4j 2, SLF4J, and Other Libraries

**SLF4J** is a logging façade. It does not mandate that all backends support a unified sampler. Log4j 2, Logback, `java.util.logging`, and collectors each have different filter architectures.

With **Log4j 2**, you can apply sampling conditions via a custom `Filter` at the logger/logger configuration/appender level, or use existing routing/configuration. A filter can return `DENY`/`NEUTRAL`/`ACCEPT`, but you must check **where** it is attached; a `Filter` on an `AppenderRef` has different semantics and timing than a `Filter` on a `LoggerConfig`. Do not copy Logback's `TurboFilter` API into Log4j 2.

Considerations when choosing an implementation point:

| Location | What Does It Save? | What to Check |
| --- | --- | --- |
| Wrapper/call-site guard | Can avoid creating the event/expensive message at the call site | Must be used consistently; easy to miss when code calls the logger directly |
| Logger-level/custom early filter | Can reduce allocation and overhead early | Filter semantics/ordering, level, logger hierarchy |
| Appender filter | Reduces traffic to that appender/sink | Event is already created; fan-out may still keep it in another sink |
| Async queue admission | Reduces worker/queue load per rule | Must distinguish deliberate sampling from overflow drops |
| Agent/collector processor | Reduces downstream backend transmission or indexing | JVM still pays upstream costs; metadata/correlation must remain intact |
| Backend ingest/index rule | Reduces storage and search cost | Does not save upstream bandwidth/CPU; retention/audit risks |

**There is no universal configuration across all appenders.** Read the documentation for your actual backend and exporter versions, especially since routing/filtering/sampling features vary by version. Use integration tests to verify the entire pipeline rather than just inspecting XML files.

### Using SLF4J Parameterized Logging Properly

```java
logger.debug("payload={} request_id={}",
        expensiveSerialize(payload), requestId);
```

This is a snippet assuming variables and `logger` exist. **`expensiveSerialize(payload)` is still invoked by Java before the `debug` method runs**, even when DEBUG is disabled or later rejected by a sampling filter. An early guard can avoid that cost:

```java
if (logger.isDebugEnabled() && samplingPolicy.keep(requestId)) {
    logger.debug("payload={} request_id={}",
            expensiveSerialize(payload), requestId);
}
```

This is also just an **integration snippet**, not a standalone JDK program. When a `TurboFilter` can affect `isDebugEnabled`, check the actual semantics; if checking enabled already applies a sampler once and then calling `keep` applies **random sampling** again, the keep rate will be lower than intended. With deterministic sampling by ID, the two decisions usually match, though they can diverge if the policy changes between calls. Design a **single decision point** or cache the decision within the scope when stability is required.

## 10. Consistency by Trace, Request, and Message

### 10.1. Event-Based vs. Trace-Based Sampling

If you independently select each event with p=10%, a request with 20 logs might keep a few scattered lines. That is useful for some simple distribution measurements, but makes reconstructing the execution flow difficult.

Sampling by trace ID selects **an entire group of detailed logs** under one decision. However, the probability of "keeping an event" and "keeping a trace" have different statistical meanings. A long trace with 100 logs and a short trace with 2 logs have **equal trace-selection probability** when sampled uniformly by trace, but the long trace contributes far more events/bytes when kept. Therefore, sampling 10% of traces **does not guarantee** 10% of bytes or exactly 10% of events.

### 10.2. Message Processing and Retries

In message-driven Java systems, a message may be retried on another worker:

- To track an entire **logical message**, use a reliably managed stable key such as `message_id`/`operation_id`.
- To track each delivery separately, use `delivery_id`/`attempt_id` and accept that the sampling decision may differ between attempts.
- If terminal failure/failed-retry logs must be kept, override sampling for them; do not treat every retry attempt as an independent event of equal value.
- Do not use a broker offset or delivery tag as a stable key across retries if they change upon republish/requeue.
- If a stable key is missing, implement a fallback and a metric measuring the missing-context rate.

### 10.3. Distributed Tracing and OpenTelemetry

OpenTelemetry typically provides **sampling concepts for trace spans** such as `ParentBased` or `TraceIdRatioBased` on the tracer. These samplers govern span recording; **do not assume they automatically sample or keep logs at the same rate**. Logs may be collected via logger instrumentation, SDK exporters, file agents, or Collectors with different processor configurations.

In a well-designed system, you can:

1. Propagate `trace_id`/`span_id` in the appropriate context.
2. Record the trace ID field in structured logs.
3. Decide whether to keep detailed logs using a stable hash of the trace ID, **independently or linked** to trace sampling.
4. Keep ERRORs per policy even when trace spans are not exported.
5. Verify the Collector processors/filters actually in use; do not claim "OpenTelemetry auto-samples log events" unless the pipeline is explicitly configured for it.

**Sampling at the Collector** can be configured to drop/filter or use an appropriate processor depending on version and distribution. Do not apply a Tail Sampling Processor configuration meant for traces and assume it tail-samples log records. Verify that the implementation supports the `logs` signal type and the desired semantics.

## 11. Statistical Impact: A Sample Is Not the Whole Population

If a set of events is selected **independently** with a known probability `p`, you can estimate the total count by summing weights `1/p` for kept events. For example, if 120 events are kept from a set with p=0.10, an estimated total is about 1,200 events. **That is an estimate, not proof that exactly 1,200 events occurred.**

With varying probabilities per event, one form of total estimator is:

\[\widehat{N} = \sum_{i \in \mathrm{sample}} \frac{1}{p_i}\]

This is the Horvitz–Thompson-style idea for totals under appropriate inclusion probabilities; it cannot rescue biases caused by quotas, queue overflows, downstream data loss, or rules that depend on the analysis outcome itself.

### Risks When Interpreting Samples

- **Level-aware sampling:** ERROR kept 100%, INFO kept 10%. Do not multiply the total log count by 10; split by group/event type and its corresponding probability.
- **Trace sampling:** log events within the same trace are correlated. Traces have varying event-count distributions, so uncertainty is larger than in simple calculations for independent events.
- **Adaptive `p`:** the policy changes with load; you must record `policy_version`/`effective_p` at decision time if you want to estimate totals.
- **Missing context:** keep-all or drop-all fallbacks create a group with a completely different probability than ID-bearing traces.
- **Tail/error-aware:** traces are selected because of errors/high latency. This sample is outcome-biased and cannot be used as a random representative sample of all requests.
- **Rate limiting:** earlier events may be kept while later ones are dropped when tokens run out; inclusion probability no longer behaves like Bernoulli `p`.
- **Collector overflow:** unintended log loss causes the sampled count and stored count to diverge.

If you need **total requests, error rates, SLOs, or p95/p99 latency**, measure them with metrics/histograms at the source or statistically sound telemetry, rather than blindly extrapolating from sampled log line counts. Sampling is no substitute for business ground truth.

### Sampling and Querying Rare Logs

If an event occurs with low probability over a time window, 1% random sampling can cause all rare events to vanish. To investigate rare events, keep 100% of important event codes/error categories and aggressively sample routine events. Define critical groups **before** dropping and account for cases where an error occurs after a sequence of already-dropped INFO logs.

## 12. Monitoring Effectiveness and Log Loss

A responsible sampling implementation must measure not only output volume, but also **event-dropping decisions**.

Reference metrics:

| Metric | Meaning | Notes |
| --- | --- | --- |
| `logging_events_eligible_total` | Number of events eligible for sampling rules | May not see events blocked earlier by logger level |
| `logging_events_selected_total` | Number of events the sampler decided to KEEP | Not the number of events stored by the backend |
| `logging_events_sampled_out_total` | Number of events intentionally dropped by the sampler | Separate from queue overflows and sink failures |
| `logging_sampling_ratio` | KEEP / eligible ratio per rule | Tag with policy/version, bounded labels |
| `logging_queue_dropped_total` | Events dropped due to queue overload if measurable | Distinct from deliberate sampling |
| `logging_sink_write_errors_total` | Errors writing to stdout/file/network | Logs can be lost after a KEEP decision |
| `logging_collector_ingest_total` | Number of events ingested by the collector | May differ from JVM selected due to other hops |
| `logging_bytes_sent_total` | Log egress bandwidth | Shows actual cost |
| `logging_critical_events_total` | Number of critical events at source, per policy | Helps detect critical delivery gaps |
| `logging_sampling_policy_changes_total` | Number of policy updates | Useful when dashboards show sudden volume drops |

These metric names are illustrative and **are not built into** SLF4J/Logback/Log4j 2/Collector. You must design collection and appropriate cardinality. Do not use `trace_id`, `request_id`, or `user_id` as labels on aggregate metrics; their high cardinality drives up monitoring costs.

**Key measurement point:** A metric called `selected_total` in the JVM does not prove the event was stored. If an async logging appender drops events or the collector fails, you need counters and reconciliation across hops. Do not declare "10% sampling," measure 1% output, and conclude the sampler code is broken; downstream layers may be dropping more.

## 13. Security and Correctness

Sampling can reduce the amount of data stored, but it is not a data-protection technique:

- **Do not log secrets** such as passwords, tokens, API keys, cookies, or raw personal data unless explicitly approved.
- Log injection from user-controlled strings remains dangerous even for sampled events; use structured logging and proper escaping.
- A client-supplied trace ID can be manipulated; do not treat it as a trusted security key or quota mechanism.
- Audit/security events may require retention/immutable storage and completeness by obligation; do not mix them with the DEBUG/INFO sampler.
- If the sampler uses a deterministic ID, users may guess/choose keys to force messages to be kept or dropped, especially if the hash function is public. That does not make sampling useless for observability, but it means it cannot replace access control or DoS rate limiting.
- In multi-tenant systems, a sampling policy change must not leak tenant A's logs into tenant B's sink; routing and authorization are independent of sampling.
- When a collector failure causes log loss, do not automatically fall back to an HTTP/plaintext endpoint or an overly permissive sink just to "save" the sample.

**Event data quality matters more than quantity.** 100% of logs missing a trace ID, error code, or containing tokens are worse than a standardized, controlled sample combined with metrics and tracing.

## 14. Performance: Does Sampling Actually Reduce Cost?

The key is placing sampling early enough. A Java example:

```java
logger.debug("payload={}", expensiveSerialize(payload));
```

Even when DEBUG is off, Java still evaluates `expensiveSerialize(payload)` before calling the method. If a sampling filter is placed on the appender, payload serialization at the caller still happens.

You can avoid the cost with a guard when an early decision service is available:

```java
boolean eligible = logger.isDebugEnabled();
boolean selected = samplingPolicy.keep(traceId);
if (eligible && selected) {
    logger.debug("payload={}", expensiveSerialize(payload));
}
```

This is a **snippet**; variables/logger/samplingPolicy must be integrated into the application. Note that writing `eligible && selected` separately as above still calls `samplingPolicy.keep` even when DEBUG is off. To also avoid computing the sampling decision when DEBUG is disabled, combine them:

```java
if (logger.isDebugEnabled() && samplingPolicy.keep(traceId)) {
    logger.debug("payload={}", expensiveSerialize(payload));
}
```

However, avoid applying **two independent probabilistic samplers** at the guard and a downstream filter/backend unintentionally. If two layers each keep 10% independently, the combined rate is around 1% assuming independence, not 10%. In multi-hop pipelines, know the rate and semantics at each layer.

### Cost of Sampling Itself

- Hashing a short trace ID is usually cheaper than serializing a large payload, but still benchmark on real data.
- Random generation across multiple threads should use an appropriate thread-safe API; do not instantiate a new `Random` or heavy secure hash per event unnecessarily.
- A global rate limiter using a hot lock can increase contention; consider per-shard quotas and fairness.
- Tail-sampling buffers can increase heap usage and GC pauses, especially for long-lived traces or large log payloads.
- Appender-level sampling can save I/O but does not eliminate prior formatting CPU.

Benchmarks should measure **logger call p50/p95/p99**, allocation, CPU, bytes/s, queue depth, selected event count, events received at the sink, and impact on business throughput. A benchmark that only measures faster calls while dropping many critical logs is inadequate.

## 15. Testing Log Sampling

### 15.1. Policy Test Matrix

| ID | Scenario | Expectation |
| --- | --- | --- |
| S1 | Same trace ID, INFO/DEBUG under the same policy | Consistent KEEP/DROP decision |
| S2 | TRACE/DEBUG blocked earlier by level filter | No event emitted to sink; not confused with sampler drop |
| S3 | WARN/ERROR belonging to a sampled-out trace | Critical override keeps the log per rule |
| S4 | Audit/security INFO event | Not dropped by noisy INFO rule if policy requires full retention |
| S5 | Missing/blank/invalid trace ID | Explicit fallback; metric counts missing context |
| S6 | Multiple services using the same algorithm/version | Compatible decisions for the same ID if required |
| S7 | Changing sampling `p` while a request is open | Consistency preserved per contract or policy version recorded |
| S8 | IDs with different prefixes/formats | Hash distribution is not overly skewed |
| S9 | Burst at 100x normal traffic | Probabilistic sampler is not treated as a hard rate limit |
| S10 | Queue full after KEEP decision | Separate drop/blocked metrics; no false success reported |
| S11 | Collector timeout/retry | No out-of-policy duplicates; counts observable |
| S12 | Redaction/canary secret | No secret leaked in any sampled log |
| S13 | Multi-thread/MDC propagation | Previous request's trace ID never attached to subsequent events |
| S14 | Fan-out to multiple appenders | Verify where sampling occurs; no out-of-policy route divergence |
| S15 | Dynamic sampling config rollback | After rollback, decisions and metrics return to the previous policy |
| S16 | Sampled logs used for error-rate reporting | Dashboards do not miscalculate totals from heterogeneous `p` values |

### 15.2. Unit Tests

Tests should verify the **decision function** independently of the logging backend:

- For a specific trace ID, the decision is correct.
- Two events of different levels with the same trace and in the same sampling group receive the same decision.
- WARN/ERROR bypass the policy.
- Null/blank keys are handled properly.
- Changing version/seed/hash changes the sampled set in a controlled way.
- For a sufficiently large set of independent IDs, the empirical rate is close to the target within calculated error bounds; **do not** assert exactly 10% for 10 samples.

For random samplers, tests should inject a pseudo-random source or test seed so assertions are deterministic; do not rely on global production randomness for fixed unit test outcomes. For token buckets, inject a controllable clock; `Clock.fixed` can be suitable for testing time-based refills, while measuring actual durations requires a monotonic time source.

### 15.3. Logging Backend Integration Tests

Attach an in-memory `Handler`/`ListAppender` to the application logger:

1. Emit a known set of events, each with a test ID.
2. Compare both kept **and dropped** lists, verifying level/logger/routing.
3. For a Logback `TurboFilter`, verify the filter is loaded and active for the right logger name, not just that the class exists.
4. Verify audit/ERROR events still reach the right sink and do not fall into the wrong route.
5. Change levels/config and verify effective filter ordering.
6. With async appenders, wait for drain or a signal; do not conclude "no log" simply from an immediate query.

### 15.4. End-to-End Tests

With unique event IDs:

- Verify JVM selected counts against policy.
- Check how many the appender/file/stdout received.
- Check how many the agent/collector/index received and whether `trace_id`/`event_code` remain in the schema.
- Set a deadline for querying eventually-consistent backends.
- Cross-check that sampled-out events do not appear in sinks governed by the rule.
- Test pipeline outages, bursts, CPU pressure, restarts, and policy reloads.
- Evaluate whether sampling actually reduces **bytes and real costs** or merely hides logs on a dashboard.
- Restore configuration and clean up test events per procedure.

### 15.5. Assertions to Avoid

- `sampleRate == keptCount/totalCount` for every small batch: random sampling has variance.
- "No ERROR lines" = no errors: logs may have been filtered, dropped, failed ingestion, or occurred elsewhere.
- "Trace was sampled" = all logs in that trace are intact: other filters, appenders, and collectors still apply.
- "10% traces" = "10% events/bytes": traces have varying lengths.
- "Appender received" = "Index durably stored": those are two separate acknowledgment boundaries.
- "No token found in sampled logs" = source does not log tokens: must test at the source/encoder and all permitted sinks.

## 16. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Almost no INFO logs left | `p` too low, skewed ID distribution, logger level, collector filter | Check each hop and eligible/selected counts |
| All logs of a sampled trace missing | Different hash/seed/policy across services, missing context, or another filter | Compare stable key, policy version, and sampling decision |
| WARN/ERROR disappeared | Early level/filter/routing rule or overload; critical override did not run | Test events at call site, appender, and backend |
| Volume spike during tracing outage | Keep-all fallback for missing trace IDs | Measure missing-context ratio and add a budgeted fallback |
| Duplicate logs after deploy | Fan-out appenders, root additivity, or collector reading both file/stdout | Deduplicate by event ID; check routes and hierarchy |
| Sampled 10% but ingested only 2% | Queue drops, collector quota, downstream filters | Compare selected vs. sink/collector counters |
| Sampled 10% but byte volume still huge | Selected traces too long, huge exception stacks, or `p` applied per trace | Measure bytes per event/trace and heavy tails |
| Many success logs but few errors | Severity-aware policy; this may be expected behavior | Group by rule and probability |
| Dashboard error rate is wrong | Using sampled INFO as denominator with full ERROR | Use authoritative metrics or proper weighting |
| Sampling slows down caller | Heavy hash/lock or sampling happens after expensive serialization | CPU profile, p99, allocations, and filter placement |
| Wrong MDC trace ID | Thread pool reuse without cleanup/propagation | Test concurrent context; restore MDC in `finally` |
| A client can game sampling | Using raw client-controlled ID as bucket key | Issue/validate trusted IDs; never use sampler as security gate |
| Config changed `p` with no effect | Policy cache, filter not reloaded, pods running different versions | Check effective config per instance and metrics |
| Missing logs when querying by event time | Ingest lag, clock skew, or wrong index query | Compare event timestamp, observed timestamp, and namespace |

## 17. Runbook for Rolling Out and Tuning Sampling Rates

1. **Define the goal:** reduce index cost by 50%, reduce bytes/s, or ensure sample traces are kept for investigation? Each goal leads to different choices.
2. **Measure baseline:** events/s, bytes/s, CPU, collector throughput, queue depth, error ratio, and cost before sampling.
3. **Classify events:** audit/security/critical, ERROR, valuable WARN, noisy INFO/DEBUG; document policy and owner.
4. **Choose the key:** trace ID, request ID, operation ID, message ID, or event ID; define what **unit** is being sampled.
5. **Choose the algorithm:** random, deterministic hash, rate limiting, or adaptive; record `p`, seed, version, and missing-context fallback.
6. **Choose the location:** early logger filter to reduce CPU and bytes at the source; collector if only downstream indexing needs reduction and there is a valid reason.
7. **Write tests:** deterministic unit tests, negative/critical tests, cross-language tests if consistency across services is needed.
8. **Limited rollout:** canary on one service/pod, measuring selected, sampled-out, sink drops, and log visibility.
9. **Review dashboards:** fix alerts/error-rate/SLOs if they previously relied on unadjusted log counts.
10. **Monitor overload:** when queues/collectors fail, do not mask dropped critical events behind selected counts.
11. **Record changes:** who changed `p`, when, for which group, rollback capability, and policy version consistency.
12. **Periodic review:** traffic, error patterns, and investigative value change; an old `p` may no longer be appropriate.

A safe rollout does not have to start with a very low `p`. Without baseline metrics, cutting sampling by 100x immediately can wipe out investigative data right when a new release introduces bugs. Adjust one log group at a time and confirm alternative data sources for critical indicators before cutting.

## 18. Review Checklist

- [ ] I can distinguish between sampling, filtering, rate limiting, aggregation, and overload drops.
- [ ] I know event-based sampling differs from trace/request/message-based sampling.
- [ ] I know deterministic hashing aids correlation but does not guarantee a perfect distribution.
- [ ] I do not use `String.hashCode()` as a secure hash or assume cross-language compatibility.
- [ ] I have clear policies for WARN/ERROR, audit/security, business-critical events, and events missing a trace ID.
- [ ] I do not treat sampling as a substitute for redaction, privacy controls, or authorization.
- [ ] I know collector-level filtering does not save log-creation CPU in the JVM.
- [ ] I avoid building expensive messages before checking enabled levels/sampling decisions.
- [ ] I measure eligible/selected/sampled-out counts as well as downstream drops/ingest.
- [ ] I do not use sampled log counts directly as total request/error rates.
- [ ] I understand that trace sampling in OpenTelemetry does not automatically sample Java logs with the same decision.
- [ ] I have tested the policy for positive, negative, missing-context, concurrency, and dynamic-change cases.
- [ ] I have end-to-end tests when proving logs reach the backend, not just that a `Handler` received them.
- [ ] I have a rollback mechanism and version tracking when changing sampling ratios.
- [ ] I understand that error logs bypassing the sampler can still be lost due to sink/queue failures.

**Completion criteria:** You can explain when to choose trace-based sampling, why WARN/ERROR usually need exceptions, write and run `LogSamplingDemo.java`, verify kept/dropped event counts yourself, distinguish sample selection from log delivery, and build a measurable, safe sampling policy for a real observability system.

## 19. Self-Check Questions

1. If 10% of INFO logs are kept, will exactly 10 events be kept for every 100 events?
2. A request has 20 logs; how does per-event sampling differ from whole-trace sampling?
3. Why does sampling 10% of traces not mean keeping only 10% of bytes?
4. If the collector drops 50% of events after the JVM sampler already kept 10%, should that be called a "5% sampler"?
5. When an ERROR log occurs in an unselected trace, what behavior is usually helpful for diagnostics?
6. Why should sampling not be applied to mandatory audit/security events?
7. What happens if the same trace ID is hashed with different algorithms in two services?
8. Why does a sampling filter on an appender not prevent Java from evaluating `expensiveSerialize(payload)`?
9. Among random sampling, hash-based sampling, and token bucket, which mechanisms provide relative limits and which can cap absolute rate?
10. Does tail-based log sampling require a buffer? What are the memory/crash/timeout risks?
11. If a request fails after INFO logs have already been dropped, does an ERROR override restore those INFO logs?
12. How will a dashboard calculating error rate from full ERROR lines and sampled INFO lines be biased?
13. When a trace ID is missing and the fallback is keep-all, what can happen during a cascading failure?
14. Why does a sampling decision based on a raw client-controlled ID not replace rate limiting and security?
15. In Logback, how do `TurboFilter` and an appender filter differ in placement and cost?
16. How do you test that a custom filter returns `NEUTRAL` for WARN while WARN still reaches the sink?
17. If `p` changes while a trace is running, how do you maintain consistency across events?
18. Why should `message_id` not be used as a metric label for sampled-out counters?

## References

- [Oracle Java SE 17 — String.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()) — deterministic string hashing and example limitations.
- [Oracle Java SE 17 — Math.floorMod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#floorMod(int,int)) — non-negative modulo when hash is negative.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — logger, levels, and handlers in the example.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — capturing log records for verification.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — TurboFilter, appender filters, and FilterReply.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy, enabled levels, and additivity.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html) — filters across logging layers.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/) — sampling concepts in tracing and related factors.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — log records and their relationship to traces.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — security and sensitive data in logging.
