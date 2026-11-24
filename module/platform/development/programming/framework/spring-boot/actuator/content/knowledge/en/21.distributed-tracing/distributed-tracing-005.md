# Adjusting Sampling Probability and Understanding Observable Data Limits

## 1. What Problem Does Sampling Solve?

A system can handle thousands of requests per second. Each request in turn creates multiple spans across different services and libraries. If you keep every trace, the volume of data to process, transmit, and store can grow very rapidly.

Sampling (`sampling`) is the policy that selects which tracing data is recorded/exported by the tracer and collection pipeline. Sampling probability balances coverage against data volume.

What must be understood before adjusting configuration is: **the list of traces you are viewing is only the subset of data that passed through the sampling policy and the entire collection pipeline. Not seeing a trace does not mean the corresponding operation never occurred.**

In this lesson:

- `p` is the configured probability for the corresponding sampling decision.
- A root trace is a new trace started when no parent context decides sampling.
- A span is an operation within a trace; multiple spans can share a single sampling decision.
- Head sampling (`head sampling`) decides early, before knowing the entire outcome of the trace.
- Tail sampling (`tail sampling`) decides later based on the spans already collected.

This lesson focuses on Spring Boot 3.3.x tracing configuration and how to interpret the received data. Tracing probability is not a global sampling rate for all metrics and logs.

## 2. Adjusting Probability in Spring Boot 3.3.x

### 2.1. Configuration Property

In an application that already has Micrometer Tracing infrastructure, a bridge, and a compatible trace export component:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

It can be written in equivalent properties form:

```properties
management.tracing.sampling.probability=0.1
```

Spring Boot 3.3 defaults to a 10% sampling probability. To observe root traces more completely in a small experiment, you can use `1.0`. [Spring Boot 3.3: configuring tracing sampling](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

| Value | Interpretation for Root Traces Under This Policy |
| --- | --- |
| `0.0` | Do not select for recording under that root sampling decision |
| `0.01` | Target probability of 1% |
| `0.1` | Target probability of 10% |
| `1.0` | Select for recording under that root sampling decision |

Values lie in `[0, 1]`. `0.1` is 10%, and `0.01` is 1%; do not write `10` to represent 10%.

This table does not mean `0.0` turns off the entire tracer, or that `1.0` guarantees every trace from everywhere is stored. Parent decisions, custom samplers, and downstream stages still need to be considered.

### 2.2. The Configured Value Must Actually Be Used

Check the active profile, startup arguments, and configuration sources that may override it. The corresponding environment variable is `MANAGEMENT_TRACING_SAMPLING_PROBABILITY`.

The property above takes effect in Boot's matching auto-configuration path. If the application supplies its own sampler, creates its own tracer provider, or uses another trace collection mechanism, do not assume editing Boot's property will alter that mechanism.

Examples in Boot 3.3.0 auto-configuration:

- With Brave, Boot builds a sampler from the configured probability when no replacement sampler exists.
- With OpenTelemetry, Boot uses a ratio-based sampler for root traces, wrapped by a parent-based policy.

Compare with the implementations of [BraveAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/BraveAutoConfiguration.java) and [OpenTelemetryAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/OpenTelemetryAutoConfiguration.java).

This value is read to configure tracing components. Editing a file on disk does not prove the running process's sampler has changed. In normal experiments, restart the application with the new configuration and generate new traces to verify.

## 3. What Does a Parent Trace's Sampling Decision Mean?

### 3.1. Not Drawing Independently for Every Span

A distributed trace can traverse multiple services:

```text
Trace T, sampled decision made at entry
  -> service A
     -> service B
        -> service C
```

With a parent-based policy and proper context propagation, downstream spans respect the parent's decision. The goal is preserving trace continuity rather than letting each service drop different pieces.

If all three services configure `0.1`, do not conclude the probability of keeping the whole trace is `0.1 × 0.1 × 0.1`. That multiplication assumes three independent draws, whereas a parent-based inheritance policy does not work that way.

Conversely, if context is lost at a boundary, the downstream service may start a new root trace. In that case, you both lose the relationship and can get a different sampling decision.

### 3.2. Two Easily Confused Cases

| Decision from Parent | Local Probability for New Traces | Typical Inherited Behavior |
| --- | --- | --- |
| Parent was sampled | `0.0` | Downstream spans can still be recorded per parent decision |
| Parent was not sampled | `1.0` | Downstream spans can still be skipped per parent decision |

This is why you must distinguish "sample every new root trace originating at this service" from "force-store every span received from any source."

OpenTelemetry provides a `ParentBased` sampler, where behavior for sampled parent, unsampled parent, and no parent is clearly separated. [OpenTelemetry Java SDK: samplers](https://opentelemetry.io/docs/languages/java/sdk/#sampler).

Custom rules can alter inherited behavior. When investigating a specific application, inspect the actual sampler, context propagation mechanism, and override conditions.

### 3.3. Having a Trace ID Does Not Prove a Trace Is Stored

A tracer can still maintain context for propagation even when a span is not selected for recording/export. Therefore:

- A non-`null` `currentSpan()` does not prove span data will reach the storage backend.
- Logs containing a trace ID do not prove that trace ID is searchable in the query backend.
- Having no data in the tracing UI must be distinguished from the application having no trace context.

The Brave experiment later directly tests the case where current context exists yet no completed spans are collected due to the sampling decision.

## 4. Probability Is Not an Exact Count Guarantee Over a Small Window

### 4.1. Long-Term Expectation Differs from Individual Small Batches

In a simple model of `N` independent root traces, each kept with the same probability `p`, the expected number of selected traces is:

```text
E[K] = N × p
```

For example, `N = 1,000`, `p = 0.1` gives an expectation of 100 traces. Do not infer that any arbitrary window of 10 requests must display exactly one trace.

Concrete algorithms may be trace-ID-based or use another selection rule. In addition, request counts, root trace counts, span counts, and displayed record counts are different quantities. Parent-decision inheritance, changing load, and downstream filtering stages can also make the observed ratio differ from the local probability.

### 4.2. Rare Errors Easily Lack Representative Traces

Suppose an error type occurs across `n` **independent** traces, each kept with probability `p`, with no data loss downstream:

```text
P(no error trace kept) = (1 - p)^n

P(at least one error trace kept) = 1 - (1 - p)^n
```

This is a probability model for understanding coverage, not a claim that every sampler implements independent coin-flip decisions.

| Independent Error Traces | Chance of Seeing at Least One Trace, p = 1% | Chance of Seeing at Least One Trace, p = 10% |
| --- | --- | --- |
| 1 | 1% | 10% |
| 5 | 4.9010% | 40.9510% |
| 10 | 9.5618% | 65.1322% |
| 100 | 63.3968% | 99.9973% |

With five error traces and `p = 10%`, the probability of keeping zero error traces in this model is still 59.049%. Thus, "could not find an error trace" is weak evidence without knowing the sampling policy and actual error count.

Five error spans within **the same trace** are not equivalent to five independent error traces. If they share a sampling decision, do not apply the formula above with `n = 5` merely because you counted five spans.

Furthermore, if a rule preferentially keeps error traces or slow traces, the dataset is no longer a uniform sample of total traffic. Interpret according to the actual policy rather than mechanically applying formulas to a biased sample.

## 5. Metrics, Logs, and Traces Have Different Data Boundaries

### 5.1. Changing Tracing Probability Does Not Automatically Sample Timers

In an Observation pipeline with both a metric handler and a tracing handler, the tracer's sampling decision does not automatically drop timer recordings in the metric handler.

For example, with five observation executions:

```text
p = 0:
  timer count = 5
  spans collected in experiment = 0

p = 1:
  timer count = 5
  spans collected in experiment = 5
```

This applies to metrics recorded by the application via `MeterRegistry`. Statistics computed by a downstream system **from sampled traces** are a different case: their input may already be incomplete or biased by policy.

Do not use span counts directly as request counts: one request can produce many spans, one trace can cross many services, and many traces are not retained.

### 5.2. Use the Right Signal for the Right Question

| Question | Usually Suitable Source |
| --- | --- |
| Overall error rate or traffic volume over a time window | Metrics collected with appropriate scope and tags |
| Which steps a specific execution went through | Retained traces with sufficient data across the boundaries of interest |
| Event details explicitly logged by the application | Corresponding logs, per logging and retention policy |
| Are all business events needed for reconciliation present? | Dedicated event logging mechanism with an explicit completeness contract |

Increasing tracing probability does not automatically make metrics or logs more complete. Conversely, having complete aggregate metrics cannot accurately reconstruct every dropped trace.

Do not infer overall error rate solely from a trace dataset biased toward keeping errors/slow requests. That dataset is very useful for investigation, yet biased relative to total traffic. Similarly, latency percentiles computed directly from a dataset biased toward slow traces are not the percentiles of all requests.

## 6. Head Sampling and Tail Sampling

### 6.1. Head Sampling Decides Without Knowing the Future

Head sampling decides early in the lifecycle. It can use information known at decision time, yet does not know all errors and latencies that will arise in later steps.

Therefore, merely setting probability `0.1` does not mean "keep 10% of successful traces and keep all error traces." If a trace was not recorded from the start, a late error does not retroactively bring back previously skipped spans.

Head sampling has the advantage of reducing data to record/process early on. In return, you cannot rely on it alone to guarantee capturing every error occurring across an entire trace. [OpenTelemetry: head sampling and tail sampling](https://opentelemetry.io/docs/concepts/sampling/).

### 6.2. Tail Sampling Has More Information but Requires Infrastructure

Tail sampling collects spans received so far, then applies rules such as prioritizing traces with errors or high latency.

```text
Services creating/exporting span data
  -> collector component grouping by trace
     -> keep/drop decision based on received data
        -> storage and query system
```

To decide effectively, this component must receive the relevant spans, retain state long enough, and have sufficient resources. With the OpenTelemetry Collector's Tail Sampling Processor, spans from the same trace must route to the same appropriate processing instance. You also have to account for late-arriving spans, wait timeouts, and in-memory retention limits. [Tail Sampling Processor documentation](https://raw.githubusercontent.com/open-telemetry/opentelemetry-collector-contrib/main/processor/tailsamplingprocessor/README.md).

One critical limitation: **a tail sampler cannot recover data that was already dropped before reaching it**. If a head sampler only let 1% of traces through, a downstream "keep error traces" rule can only inspect errors among the portion that arrived.

Nor should an error-retention rule be interpreted as an absolute guarantee that every error trace system-wide is stored: missing instrumentation, data loss, late arrivals, or processing limits can still have an impact.

Enabling a probability property in Boot does not automatically deploy tail sampling. That is an architectural decision for the trace collection pipeline, requiring separate design and verification when needed.

## 7. Estimating Data Volume and Choosing How to Tune

An initial estimate, when new root traces occur at `R` per second, each trace averages `S` spans, and the retention ratio is approximately `p`:

```text
Selected traces per second ≈ R × p

Selected spans per second ≈ R × p × S
```

Hypothetical example `R = 2,000`, `S = 8`, `p = 0.1`:

```text
Selected traces per second ≈ 200
Selected spans per second ≈ 1,600
```

This is an estimate of selected data, not a guarantee of stored records. Attribute/event sizes, changes in spans per trace, head/tail sampling, and export pipeline limits all affect it.

Lowering from `p = 1` to `0.1` under equivalent assumptions can sharply reduce selected span volume. Do not infer that total CPU or all system costs drop by an exact factor of ten: business work and other observability costs remain.

A verifiable tuning workflow:

1. Identify the goal: learning/testing a call path, investigating a rare error, or monitoring routine traffic.
2. Record traffic rate, average spans, and the collection pipeline's ingestion capacity.
3. Choose a probability for that environment and goal; test changes within a controllable scope.
4. Generate new traces and verify the configuration actually affects the sampler.
5. Compare aggregate metrics with received traces, along with signs of data loss or processing limits.
6. Re-evaluate the ability to catch rare errors; if needed, consider prioritization policies or tail sampling rather than merely lowering/raising a single number.

There is no single universal production ratio right for every service. A very low-traffic service and a service producing thousands of traces per second have different retention needs. When temporarily raising probability for an investigation, establish an end point for the change and verify actual data volume.

## 8. Experiment: Root Probability, Parent Decision, and Metrics

### 8.1. Objective

The program below tests four scenarios using Brave and Micrometer:

1. No parent, local probability equal to 0.
2. No parent, local probability equal to 1.
3. Sampled parent, local probability equal to 0.
4. Unsampled parent, local probability equal to 1.

Each scenario runs five observations. The metric handler records timers; the tracing handler connects to Brave; a `SpanHandler` collects completed spans in memory. No traces are sent over the network.

The program fixes the two probability boundaries 0 and 1 to produce deterministic stdout. The two probability calculations at the end illustrate the mathematical model; random sampling trials are not used to decide test pass/fail.

### 8.2. Dependencies in pom.xml

Use JDK 21. Create a separate experiment directory and save `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sampling-limits-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-brave</artifactId>
            <version>1.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-nop</artifactId>
            <version>1.7.36</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
</project>
```

Maven resolves the bridge's transitive dependencies, including Micrometer Tracing and Brave. Micrometer 1.13.0 / Tracing 1.3.0 belong to the Boot 3.3.0 library generation.

In an existing Boot application, continue using Boot's dependency management. This program configures the sampler directly in Java; it does not start Boot and does not read properties in `application.yml`.

### 8.3. Complete SamplingLimitsDemo.java

Save next to `pom.xml`, without a package declaration:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;

public class SamplingLimitsDemo {
    private static final int WORK_COUNT = 5;

    public static void main(String[] args) {
        Result rootZero = run(0.0f, null);
        Result rootOne = run(1.0f, null);
        Result sampledParent = run(0.0f, true);
        Result unsampledParent = run(1.0f, false);

        print("root.p0", rootZero);
        print("root.p1", rootOne);
        print("parent.sampled.local.p0", sampledParent);
        print("parent.not.sampled.local.p1", unsampledParent);
        System.out.println("context.present.when.unsampled="
                + (rootZero.contextSeen() == WORK_COUNT));

        System.out.printf(Locale.ROOT, "chance.p0.1.n5=%.6f%n",
                1.0 - Math.pow(1.0 - 0.1, 5));
        System.out.printf(Locale.ROOT, "chance.p0.01.n5=%.6f%n",
                1.0 - Math.pow(1.0 - 0.01, 5));

        if (rootZero.spans() != 0 || rootOne.spans() != WORK_COUNT
                || sampledParent.spans() != WORK_COUNT
                || unsampledParent.spans() != 0) {
            throw new AssertionError("Unexpected sampling decisions");
        }
    }

    static Result run(float localProbability, Boolean incomingSampled) {
        List<MutableSpan> completed = new ArrayList<>();
        var meters = new SimpleMeterRegistry();
        SpanHandler collector = new SpanHandler() {
            @Override
            public boolean end(TraceContext context, MutableSpan span, Cause cause) {
                completed.add(new MutableSpan(span));
                return true;
            }
        };

        try (Tracing engine = Tracing.newBuilder()
                .localServiceName("sampling-demo")
                .sampler(Sampler.create(localProbability))
                .addSpanHandler(collector)
                .build()) {
            Tracer tracer = new BraveTracer(engine.tracer(),
                    new BraveCurrentTraceContext(engine.currentTraceContext()));
            var registry = ObservationRegistry.create();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(new DefaultTracingObservationHandler(tracer));

            TraceContext incoming = incomingSampled == null ? null
                    : TraceContext.newBuilder()
                            .traceId(0x1111111111111111L)
                            .spanId(0x2222222222222222L)
                            .sampled(incomingSampled)
                            .build();
            int[] contextSeen = {0};
            try (var scope = engine.currentTraceContext().newScope(incoming)) {
                for (int i = 0; i < WORK_COUNT; i++) {
                    Observation.createNotStarted("work", registry).observe(() -> {
                        if (tracer.currentSpan() != null) {
                            contextSeen[0]++;
                        }
                    });
                }
            }

            long metricCount = meters.get("work").timer().count();
            if (metricCount != WORK_COUNT
                    || registry.getCurrentObservation() != null
                    || tracer.currentSpan() != null) {
                throw new AssertionError("Unexpected metrics or scope");
            }
            return new Result(metricCount, completed.size(), contextSeen[0]);
        } finally {
            meters.close();
        }
    }

    static void print(String label, Result result) {
        System.out.println(label + ": metrics=" + result.metrics()
                + ", spans=" + result.spans());
    }

    record Result(long metrics, int spans, int contextSeen) {
    }
}
```

`incomingSampled = null` represents the case with no parent context supplied. The other two boolean values construct a synthetic parent context to test decision inheritance. The IDs in the parent context are only experiment data, not data from a real service.

When a parent is present, the five observations are five child spans within the same simulated trace. When there is no parent, each observation can start its own root trace. Therefore, the `spans` column must not be arbitrarily renamed to "trace count."

### 8.4. Compile, Run, and Stdout

In PowerShell, select JDK 21 for both `javac` and `java`, with Maven available, then run sequentially once each previous command succeeds:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" SamplingLimitsDemo.java
java -cp ".;$demoClasspath" SamplingLimitsDemo
```

The first run requires Maven repository access to download dependencies. The `;` in the classpath is for Windows; Linux/macOS uses `:`.

Program stdout, excluding Maven messages:

```text
root.p0: metrics=5, spans=0
root.p1: metrics=5, spans=5
parent.sampled.local.p0: metrics=5, spans=5
parent.not.sampled.local.p1: metrics=5, spans=0
context.present.when.unsampled=true
chance.p0.1.n5=0.409510
chance.p0.01.n5=0.049010
```

### 8.5. Reading the Results Within Scope

| Result | Meaning |
| --- | --- |
| Both root cases have 0 and 5 spans | The local sampler selects/skips new traces at boundaries 0 and 1 |
| Sampled parent still has 5 spans when local is 0 | The parent decision is preserved in the experiment's Brave setup |
| Unsampled parent still has 0 spans when local is 1 | Local probability does not force-record a trace the parent chose not to sample |
| All cases have `metrics=5` | Observation timers still record all five executions in the same experiment |
| `context.present.when.unsampled=true` | Brave still supplies a current span context even when no completed spans are collected |
| `0.409510` | Approximately 40.9510% chance of seeing at least one of five independent traces when p = 10% |
| `0.049010` | Approximately 4.9010% corresponding chance when p = 1% |

The experiment verifies in-memory mechanics; it does not test exporters, receivers, or query UIs. Nor does it prove every tracer shares identical details for representing unsampled spans; the current-context result here is tested directly against Brave.

## 9. Why p = 1 Still Does Not Guarantee Complete Visibility

Many steps sit between a business call and the record you view:

```text
Actual invocation
  -> observation code runs and covers that boundary
  -> sampling decision
  -> span recorded and ended
  -> exporter/transport path
  -> processor/filter/storage system
  -> retention window and current query
```

A probability of 1 only affects the specific policy controlled by that sampler. It does not:

- Create spans for code lacking observation logic.
- Recover spans dropped before the configuration change.
- Guarantee every asynchronous task and network call propagates context properly.
- Fix data loss caused by queues, export errors, process shutdowns, or receiver rejections.
- Bypass filters, retention policies, or query conditions downstream.
- Automatically capture all input values, internal state, and complete business execution details.

A visible trace can also be missing a branch or a category of information. State the scope of data for which evidence actually exists rather than inferring that the trace is a record of all system behavior.

## 10. Checks When Observed Rates Differ from Expectations

| Symptom | What to Check |
| --- | --- |
| Set 1.0 yet not seeing every request | Is it a new root trace; what did the parent decide; actual sampler and export path |
| Set 0.0 yet spans still appear | Inherited sampling decision or override rule; is the expected sampler being used? |
| Small-request trials show wildly varying rates | Small window; counting requests/traces/spans; actual algorithm and policy |
| Metrics report errors yet no error traces exist | Sampling may not keep errors; instrumentation and collection pipeline may be dropping data |
| Trace ID appears in logs yet trace cannot be found | Context does not equal an exported and stored span |
| Only seeing many slow/error traces | May be viewing a prioritized dataset or filtered query; do not treat as system-wide rate |
| Edited config yet behavior did not change | Overriding config source, custom sampler, or running component not reinitialized |
| Rare errors still missing after enabling tail sampling | Did data reach the tail sampler; upstream head sampling; trace-based routing and processing limits |

Testing workflows in Boot should start from a known call path, an adequate request volume, fresh root traces, and an easily observable sampling setup. Only after confirming the collection pipeline works should you lower probability and evaluate coverage. Do not simultaneously change sampler, exporter, context propagation, and query filters and then use an empty result to conclude everything is broken.

## 11. Practice Exercises

1. Run the program and explain why the metric column stays unchanged across all four scenarios.
2. Point out two lines proving local probability and parent decision are not the same kind of input.
3. For an error occurring on a single trace, calculate the chance of having a representative trace when p = 1%, 10%, and 100%, under the simple model with no downstream loss.
4. Explain why five errors within the same trace do not provide five independent sampling chances.
5. In a test Boot environment with tracing already enabled, change from 1.0 down to 0.1, generate new root traces, and compare metrics against received trace counts. Record the observation window and counting units clearly.
6. Design a way to prioritize investigating rare errors; state which data must reach the decision point and which portion cannot be recovered if dropped earlier.

The conclusion of an investigation must be tied to the sampling policy, observation scope, and completeness of the collection pipeline. "No evidence seen in the current trace dataset" and "that event did not occur in the system" are two statements with different levels of certainty.
